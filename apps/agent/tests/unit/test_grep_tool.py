"""Unit tests for ag3nt_agent.grep_tool module.

Tests cover all helper functions and the main grep_search function,
including output modes, filtering, context lines, pagination, and
edge cases like binary files and invalid regex.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ag3nt_agent.grep_tool import (
    _get_file_type_extensions,
    _is_binary_file,
    _matches_glob,
    _should_skip_dir,
    get_grep_tool,
    grep_search,
)


# ---------------------------------------------------------------------------
# _is_binary_file
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestIsBinaryFile:
    """Tests for _is_binary_file."""

    def test_binary_extension_detected(self, tmp_path: Path) -> None:
        """Files with known binary extensions are identified as binary."""
        binary_file = tmp_path / "image.png"
        binary_file.write_text("not really binary content")
        assert _is_binary_file(binary_file) is True

    def test_text_file_no_null_bytes(self, tmp_path: Path) -> None:
        """Regular text files are not detected as binary."""
        text_file = tmp_path / "hello.py"
        text_file.write_text("print('hello world')\n")
        assert _is_binary_file(text_file) is False

    def test_file_with_null_bytes(self, tmp_path: Path) -> None:
        """Files containing null bytes are detected as binary."""
        bin_file = tmp_path / "data.dat"
        bin_file.write_bytes(b"some content\x00more content")
        assert _is_binary_file(bin_file) is True

    def test_nonexistent_file_treated_as_binary(self, tmp_path: Path) -> None:
        """Non-existent files default to binary (unreadable)."""
        missing = tmp_path / "does_not_exist.txt"
        assert _is_binary_file(missing) is True


# ---------------------------------------------------------------------------
# _should_skip_dir
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestShouldSkipDir:
    """Tests for _should_skip_dir."""

    def test_git_directory_skipped(self) -> None:
        assert _should_skip_dir(".git") is True

    def test_node_modules_skipped(self) -> None:
        assert _should_skip_dir("node_modules") is True

    def test_pycache_skipped(self) -> None:
        assert _should_skip_dir("__pycache__") is True

    def test_hidden_directory_skipped(self) -> None:
        """Any directory starting with '.' is skipped."""
        assert _should_skip_dir(".hidden") is True

    def test_normal_directory_not_skipped(self) -> None:
        assert _should_skip_dir("src") is False

    def test_venv_skipped(self) -> None:
        assert _should_skip_dir("venv") is False or _should_skip_dir("venv") is True
        # venv is in DEFAULT_IGNORE_DIRS
        assert _should_skip_dir("venv") is True


# ---------------------------------------------------------------------------
# _matches_glob
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMatchesGlob:
    """Tests for _matches_glob."""

    def test_none_pattern_matches_everything(self) -> None:
        assert _matches_glob(Path("anything.txt"), None) is True

    def test_empty_string_pattern_matches_everything(self) -> None:
        assert _matches_glob(Path("anything.txt"), "") is True

    def test_simple_star_extension(self) -> None:
        assert _matches_glob(Path("foo.py"), "*.py") is True
        assert _matches_glob(Path("foo.js"), "*.py") is False

    def test_brace_expansion(self) -> None:
        """Brace expansion like *.{ts,tsx} matches both extensions."""
        assert _matches_glob(Path("comp.ts"), "*.{ts,tsx}") is True
        assert _matches_glob(Path("comp.tsx"), "*.{ts,tsx}") is True
        assert _matches_glob(Path("comp.js"), "*.{ts,tsx}") is False

    def test_star_matches_any_extension(self) -> None:
        assert _matches_glob(Path("readme.md"), "*") is True


# ---------------------------------------------------------------------------
# _get_file_type_extensions
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetFileTypeExtensions:
    """Tests for _get_file_type_extensions."""

    def test_python_type(self) -> None:
        exts = _get_file_type_extensions("py")
        assert ".py" in exts
        assert ".pyi" in exts

    def test_typescript_type(self) -> None:
        exts = _get_file_type_extensions("ts")
        assert ".ts" in exts
        assert ".tsx" in exts

    def test_unknown_type_returns_dotted_extension(self) -> None:
        exts = _get_file_type_extensions("zig")
        assert exts == {".zig"}

    def test_case_insensitive_lookup(self) -> None:
        assert _get_file_type_extensions("PY") == _get_file_type_extensions("py")


# ---------------------------------------------------------------------------
# grep_search — output_mode="files_with_matches"
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGrepSearchFilesWithMatches:
    """Tests for grep_search in files_with_matches mode."""

    def test_finds_matching_files(self, tmp_path: Path) -> None:
        """Returns file paths that contain a match."""
        (tmp_path / "a.py").write_text("def hello():\n    pass\n")
        (tmp_path / "b.py").write_text("class Foo:\n    pass\n")

        result = grep_search("def", path=str(tmp_path), output_mode="files_with_matches")
        assert result["count"] == 1
        assert any("a.py" in m for m in result["matches"])

    def test_no_matches_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / "c.txt").write_text("nothing here\n")
        result = grep_search("zzzzz", path=str(tmp_path), output_mode="files_with_matches")
        assert result["count"] == 0
        assert result["matches"] == []

    def test_nonexistent_path_returns_error(self, tmp_path: Path) -> None:
        result = grep_search("x", path=str(tmp_path / "nope"), output_mode="files_with_matches")
        assert "error" in result


# ---------------------------------------------------------------------------
# grep_search — output_mode="content"
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGrepSearchContent:
    """Tests for grep_search in content mode."""

    def test_returns_matching_lines(self, tmp_path: Path) -> None:
        (tmp_path / "f.py").write_text("alpha\nbeta\ngamma\n")
        result = grep_search("beta", path=str(tmp_path), output_mode="content")
        assert result["count"] == 1
        assert result["matches"][0]["content"] == "beta"
        assert result["matches"][0]["line"] == 2

    def test_context_lines(self, tmp_path: Path) -> None:
        """context_before and context_after return surrounding lines."""
        (tmp_path / "g.py").write_text("line1\nline2\nline3\nline4\nline5\n")
        result = grep_search(
            "line3",
            path=str(tmp_path),
            output_mode="content",
            context_before=1,
            context_after=1,
        )
        match = result["matches"][0]
        assert match["context_before"] == ["line2"]
        assert match["context_after"] == ["line4"]

    def test_context_lines_symmetric(self, tmp_path: Path) -> None:
        """The context_lines parameter sets both before and after."""
        (tmp_path / "h.py").write_text("a\nb\nc\nd\ne\n")
        result = grep_search(
            "c", path=str(tmp_path), output_mode="content", context_lines=2,
        )
        match = result["matches"][0]
        assert match["context_before"] == ["a", "b"]
        assert match["context_after"] == ["d", "e"]


# ---------------------------------------------------------------------------
# grep_search — output_mode="count"
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGrepSearchCount:
    """Tests for grep_search in count mode."""

    def test_counts_per_file(self, tmp_path: Path) -> None:
        (tmp_path / "one.txt").write_text("apple\napple\norange\n")
        (tmp_path / "two.txt").write_text("apple\n")

        result = grep_search("apple", path=str(tmp_path), output_mode="count")
        counts = {m["file"]: m["count"] for m in result["matches"]}
        assert counts.get("one.txt") == 2
        assert counts.get("two.txt") == 1


# ---------------------------------------------------------------------------
# grep_search — filtering
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGrepSearchFiltering:
    """Tests for file filtering in grep_search."""

    def test_glob_filter(self, tmp_path: Path) -> None:
        (tmp_path / "code.py").write_text("import os\n")
        (tmp_path / "code.js").write_text("import os\n")

        result = grep_search(
            "import", path=str(tmp_path), glob="*.py", output_mode="files_with_matches",
        )
        assert result["count"] == 1
        assert any("code.py" in m for m in result["matches"])

    def test_file_type_filter(self, tmp_path: Path) -> None:
        (tmp_path / "app.ts").write_text("const x = 1;\n")
        (tmp_path / "app.py").write_text("x = 1\n")

        result = grep_search(
            "x", path=str(tmp_path), file_type="ts", output_mode="files_with_matches",
        )
        assert result["count"] == 1
        assert any("app.ts" in m for m in result["matches"])

    def test_skips_binary_files(self, tmp_path: Path) -> None:
        (tmp_path / "good.txt").write_text("match this\n")
        bin_file = tmp_path / "bad.dat"
        bin_file.write_bytes(b"match this\x00binary stuff")

        result = grep_search("match", path=str(tmp_path), output_mode="files_with_matches")
        assert result["count"] == 1
        assert any("good.txt" in m for m in result["matches"])

    def test_skips_ignored_directories(self, tmp_path: Path) -> None:
        """Directories in DEFAULT_IGNORE_DIRS are not traversed."""
        good_dir = tmp_path / "src"
        good_dir.mkdir()
        (good_dir / "main.py").write_text("target\n")

        bad_dir = tmp_path / "node_modules"
        bad_dir.mkdir()
        (bad_dir / "dep.js").write_text("target\n")

        result = grep_search("target", path=str(tmp_path), output_mode="files_with_matches")
        paths = " ".join(result["matches"])
        assert "main.py" in paths
        assert "dep.js" not in paths


# ---------------------------------------------------------------------------
# grep_search — case sensitivity
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGrepSearchCaseInsensitive:
    """Tests for case_insensitive flag."""

    def test_case_sensitive_by_default(self, tmp_path: Path) -> None:
        (tmp_path / "f.txt").write_text("Hello\nhello\n")
        result = grep_search("Hello", path=str(tmp_path), output_mode="count")
        assert result["matches"][0]["count"] == 1

    def test_case_insensitive_matches_all(self, tmp_path: Path) -> None:
        (tmp_path / "f.txt").write_text("Hello\nhello\nHELLO\n")
        result = grep_search(
            "hello", path=str(tmp_path), output_mode="count", case_insensitive=True,
        )
        assert result["matches"][0]["count"] == 3


# ---------------------------------------------------------------------------
# grep_search — invalid regex
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGrepSearchInvalidRegex:
    """Tests for handling invalid regex patterns."""

    def test_invalid_regex_returns_error(self, tmp_path: Path) -> None:
        (tmp_path / "x.txt").write_text("content\n")
        result = grep_search("[invalid", path=str(tmp_path))
        assert "error" in result
        assert "Invalid regex" in result["error"]


# ---------------------------------------------------------------------------
# grep_search — offset and head_limit pagination
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGrepSearchPagination:
    """Tests for offset and head_limit parameters."""

    def test_head_limit_in_files_mode(self, tmp_path: Path) -> None:
        for i in range(5):
            (tmp_path / f"file{i}.txt").write_text("match\n")

        result = grep_search(
            "match", path=str(tmp_path), output_mode="files_with_matches", head_limit=2,
        )
        assert result["count"] == 2
        assert result["total_files"] == 5

    def test_offset_in_files_mode(self, tmp_path: Path) -> None:
        for i in range(5):
            (tmp_path / f"file{i}.txt").write_text("match\n")

        result = grep_search(
            "match", path=str(tmp_path), output_mode="files_with_matches", offset=3,
        )
        # 5 files total, offset=3 means 2 remain
        assert result["count"] == 2

    def test_head_limit_in_content_mode(self, tmp_path: Path) -> None:
        (tmp_path / "data.txt").write_text("a\na\na\na\na\n")
        result = grep_search(
            "a", path=str(tmp_path), output_mode="content", head_limit=2,
        )
        assert result["count"] == 2

    def test_offset_and_head_limit_in_count_mode(self, tmp_path: Path) -> None:
        for i in range(4):
            (tmp_path / f"f{i}.txt").write_text("word\n")

        result = grep_search(
            "word", path=str(tmp_path), output_mode="count", offset=1, head_limit=2,
        )
        assert result["count"] == 2


# ---------------------------------------------------------------------------
# grep_search — single file search
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGrepSearchSingleFile:
    """Tests for searching a single file path."""

    def test_search_single_file(self, tmp_path: Path) -> None:
        target = tmp_path / "solo.py"
        target.write_text("import os\nimport sys\n")
        result = grep_search("import", path=str(target), output_mode="count")
        assert result["matches"][0]["count"] == 2


# ---------------------------------------------------------------------------
# get_grep_tool
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetGrepTool:
    """Tests for get_grep_tool factory."""

    def test_returns_tool(self) -> None:
        tool = get_grep_tool()
        assert tool is not None
        assert hasattr(tool, "name")
        assert tool.name == "grep_tool"
        # LangChain StructuredTool has an invoke method
        assert hasattr(tool, "invoke")
