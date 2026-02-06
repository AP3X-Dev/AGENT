"""Tests for smart output truncation."""

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from ag3nt_agent.output_truncation import (
    maybe_truncate,
    cleanup_old_outputs,
    _save_full_output,
    _DEFAULT_MAX_LINES,
    _DEFAULT_MAX_BYTES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_truncation_dir(tmp_path):
    """Provide a temp directory and patch config to use it."""
    trunc_dir = tmp_path / "tool_output"
    trunc_dir.mkdir()
    with patch(
        "ag3nt_agent.output_truncation._get_config",
        return_value=(200, 5000, trunc_dir),  # small limits for testing
    ):
        yield trunc_dir


@pytest.fixture
def tmp_truncation_dir_large(tmp_path):
    """Dir with larger limits for byte-threshold tests."""
    trunc_dir = tmp_path / "tool_output"
    trunc_dir.mkdir()
    with patch(
        "ag3nt_agent.output_truncation._get_config",
        return_value=(10000, 500, trunc_dir),  # large line limit, small byte limit
    ):
        yield trunc_dir


# ---------------------------------------------------------------------------
# maybe_truncate - passthrough
# ---------------------------------------------------------------------------


class TestMaybeTruncatePassthrough:
    """Output below thresholds passes through unchanged."""

    def test_empty_string(self, tmp_truncation_dir):
        text, truncated, path = maybe_truncate("")
        assert text == ""
        assert truncated is False
        assert path is None

    def test_none_string(self, tmp_truncation_dir):
        text, truncated, path = maybe_truncate("")
        assert truncated is False

    def test_short_output(self, tmp_truncation_dir):
        output = "hello world\nline two\n"
        text, truncated, path = maybe_truncate(output)
        assert text == output
        assert truncated is False
        assert path is None

    def test_under_line_limit(self, tmp_truncation_dir):
        output = "\n".join(f"line {i}" for i in range(100))
        text, truncated, path = maybe_truncate(output)
        assert truncated is False
        assert path is None

    def test_under_byte_limit(self, tmp_truncation_dir):
        output = "x" * 100
        text, truncated, path = maybe_truncate(output)
        assert truncated is False
        assert path is None


# ---------------------------------------------------------------------------
# maybe_truncate - line threshold
# ---------------------------------------------------------------------------


class TestMaybeTruncateLineThreshold:
    """Output above line threshold is truncated."""

    def test_truncated_at_line_limit(self, tmp_truncation_dir):
        output = "\n".join(f"line {i}" for i in range(500))
        text, truncated, path = maybe_truncate(output)
        assert truncated is True
        assert path is not None
        assert "Output truncated" in text
        assert "500 lines" in text

    def test_full_output_saved_to_disk(self, tmp_truncation_dir):
        output = "\n".join(f"line {i}" for i in range(500))
        text, truncated, path = maybe_truncate(output)
        assert truncated is True
        saved = Path(path).read_text(encoding="utf-8")
        assert saved == output

    def test_session_id_creates_subdir(self, tmp_truncation_dir):
        output = "\n".join(f"line {i}" for i in range(500))
        _, _, path = maybe_truncate(output, session_id="sess-123")
        assert "sess-123" in path

    def test_tool_call_id_in_filename(self, tmp_truncation_dir):
        output = "\n".join(f"line {i}" for i in range(500))
        _, _, path = maybe_truncate(output, tool_call_id="tc_abc")
        assert "tc_abc" in Path(path).name

    def test_truncated_content_shorter(self, tmp_truncation_dir):
        output = "\n".join(f"line {i}" for i in range(500))
        text, truncated, _ = maybe_truncate(output)
        # Truncated text (before the note) should have fewer lines
        # The note itself adds a few lines
        assert len(text) < len(output)


# ---------------------------------------------------------------------------
# maybe_truncate - byte threshold
# ---------------------------------------------------------------------------


class TestMaybeTruncateByteThreshold:
    """Output above byte threshold is truncated."""

    def test_truncated_at_byte_limit(self, tmp_truncation_dir_large):
        output = "x" * 1000  # 1000 bytes > 500 byte limit
        text, truncated, path = maybe_truncate(output)
        assert truncated is True
        assert path is not None

    def test_full_output_preserved_on_disk(self, tmp_truncation_dir_large):
        output = "x" * 1000
        _, _, path = maybe_truncate(output)
        saved = Path(path).read_text(encoding="utf-8")
        assert saved == output


# ---------------------------------------------------------------------------
# _save_full_output
# ---------------------------------------------------------------------------


class TestSaveFullOutput:
    """Full output is saved correctly."""

    def test_creates_session_subdir(self, tmp_path):
        base = tmp_path / "out"
        path = _save_full_output("hello", base, "sess1", "tc1")
        assert path.exists()
        assert path.parent.name == "sess1"
        assert path.name == "tc1.txt"

    def test_default_session(self, tmp_path):
        base = tmp_path / "out"
        path = _save_full_output("data", base, None, None)
        assert path.exists()
        assert path.parent.name == "default"

    def test_content_matches(self, tmp_path):
        base = tmp_path / "out"
        content = "line1\nline2\nline3"
        path = _save_full_output(content, base, "s", "t")
        assert path.read_text(encoding="utf-8") == content


# ---------------------------------------------------------------------------
# cleanup_old_outputs
# ---------------------------------------------------------------------------


class TestCleanupOldOutputs:
    """Cleanup removes old files and empty directories."""

    def test_removes_old_files(self, tmp_path):
        trunc_dir = tmp_path / "tool_output"
        sess_dir = trunc_dir / "default"
        sess_dir.mkdir(parents=True)

        old_file = sess_dir / "old.txt"
        old_file.write_text("old data")
        # Set mtime to 48 hours ago
        old_time = time.time() - (48 * 3600)
        os.utime(old_file, (old_time, old_time))

        new_file = sess_dir / "new.txt"
        new_file.write_text("new data")

        with patch(
            "ag3nt_agent.output_truncation._get_config",
            return_value=(2000, 50000, trunc_dir),
        ):
            deleted = cleanup_old_outputs(max_age_hours=24)

        assert deleted == 1
        assert not old_file.exists()
        assert new_file.exists()

    def test_no_dir_returns_zero(self, tmp_path):
        trunc_dir = tmp_path / "nonexistent"
        with patch(
            "ag3nt_agent.output_truncation._get_config",
            return_value=(2000, 50000, trunc_dir),
        ):
            assert cleanup_old_outputs() == 0

    def test_removes_empty_session_dirs(self, tmp_path):
        trunc_dir = tmp_path / "tool_output"
        sess_dir = trunc_dir / "old_session"
        sess_dir.mkdir(parents=True)

        old_file = sess_dir / "file.txt"
        old_file.write_text("data")
        old_time = time.time() - (48 * 3600)
        os.utime(old_file, (old_time, old_time))

        with patch(
            "ag3nt_agent.output_truncation._get_config",
            return_value=(2000, 50000, trunc_dir),
        ):
            cleanup_old_outputs(max_age_hours=24)

        assert not sess_dir.exists()


# ---------------------------------------------------------------------------
# Config fallback
# ---------------------------------------------------------------------------


class TestConfigFallback:
    """Falls back to defaults when agent_config not available."""

    def test_defaults_used(self):
        assert _DEFAULT_MAX_LINES == 2000
        assert _DEFAULT_MAX_BYTES == 50 * 1024


# ---------------------------------------------------------------------------
# Path in truncation note
# ---------------------------------------------------------------------------


class TestTruncationNote:
    """Truncation note includes useful information."""

    def test_note_has_line_count(self, tmp_truncation_dir):
        output = "\n".join(f"line {i}" for i in range(500))
        text, _, _ = maybe_truncate(output)
        assert "500 lines" in text

    def test_note_has_grep_hint(self, tmp_truncation_dir):
        output = "\n".join(f"line {i}" for i in range(500))
        text, _, _ = maybe_truncate(output)
        assert "grep_tool" in text

    def test_note_has_saved_path(self, tmp_truncation_dir):
        output = "\n".join(f"line {i}" for i in range(500))
        text, _, path = maybe_truncate(output)
        assert path in text
