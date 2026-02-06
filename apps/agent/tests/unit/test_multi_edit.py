"""Tests for multi-edit tool."""

import pytest
from pathlib import Path

from ag3nt_agent.multi_edit_tool import multi_edit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_file(tmp_path):
    """Create a sample file for editing."""
    p = tmp_path / "sample.py"
    p.write_text(
        "def greet(name):\n"
        "    msg = f'Hello, {name}!'\n"
        "    print(msg)\n"
        "    return msg\n"
        "\n"
        "def farewell(name):\n"
        "    msg = f'Goodbye, {name}!'\n"
        "    print(msg)\n"
        "    return msg\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def multiline_file(tmp_path):
    """Create a file with many lines for multi-edit."""
    p = tmp_path / "multi.txt"
    lines = [f"line_{i} = {i}" for i in range(20)]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Basic single edit
# ---------------------------------------------------------------------------


class TestSingleEdit:
    """Single edit works correctly via fuzzy engine."""

    def test_exact_match(self, sample_file):
        result = multi_edit.invoke({
            "file_path": str(sample_file),
            "edits": [{"old_string": "def greet(name):", "new_string": "def greet(user):"}],
        })
        assert result["success"] is True
        assert result["edits_applied"] == 1
        assert result["results"][0]["status"] == "ok"
        assert "def greet(user):" in sample_file.read_text()

    def test_reports_strategy(self, sample_file):
        result = multi_edit.invoke({
            "file_path": str(sample_file),
            "edits": [{"old_string": "def greet(name):", "new_string": "def greet(user):"}],
        })
        assert "strategy" in result["results"][0]


# ---------------------------------------------------------------------------
# Multiple sequential edits
# ---------------------------------------------------------------------------


class TestSequentialEdits:
    """Multiple edits applied in sequence, each sees previous result."""

    def test_two_edits(self, sample_file):
        result = multi_edit.invoke({
            "file_path": str(sample_file),
            "edits": [
                {"old_string": "def greet(name):", "new_string": "def greet(user):"},
                {"old_string": "def farewell(name):", "new_string": "def farewell(user):"},
            ],
        })
        assert result["success"] is True
        assert result["edits_applied"] == 2
        content = sample_file.read_text()
        assert "def greet(user):" in content
        assert "def farewell(user):" in content

    def test_chained_edits(self, sample_file):
        """Second edit depends on first edit's result."""
        result = multi_edit.invoke({
            "file_path": str(sample_file),
            "edits": [
                {"old_string": "def greet(name):", "new_string": "def hello(name):"},
                {"old_string": "def hello(name):", "new_string": "def hi(name):"},
            ],
        })
        assert result["success"] is True
        assert result["edits_applied"] == 2
        content = sample_file.read_text()
        assert "def hi(name):" in content
        assert "def greet(name):" not in content
        assert "def hello(name):" not in content

    def test_many_edits(self, multiline_file):
        """Apply 10+ edits in one call."""
        edits = [
            {"old_string": f"line_{i} = {i}", "new_string": f"var_{i} = {i * 10}"}
            for i in range(10)
        ]
        result = multi_edit.invoke({
            "file_path": str(multiline_file),
            "edits": edits,
        })
        assert result["success"] is True
        assert result["edits_applied"] == 10
        content = multiline_file.read_text()
        for i in range(10):
            assert f"var_{i} = {i * 10}" in content


# ---------------------------------------------------------------------------
# Failure mid-sequence
# ---------------------------------------------------------------------------


class TestFailureMidSequence:
    """Edit failure stops processing, file unchanged."""

    def test_second_edit_fails(self, sample_file):
        original = sample_file.read_text()
        result = multi_edit.invoke({
            "file_path": str(sample_file),
            "edits": [
                {"old_string": "def greet(name):", "new_string": "def greet(user):"},
                {"old_string": "THIS_DOES_NOT_EXIST", "new_string": "replacement"},
            ],
        })
        assert result["success"] is False
        assert result["edits_applied"] == 1
        assert result["results"][0]["status"] == "ok"
        assert result["results"][1]["status"] == "error"
        # File should NOT be modified (rollback)
        assert sample_file.read_text() == original

    def test_first_edit_fails(self, sample_file):
        original = sample_file.read_text()
        result = multi_edit.invoke({
            "file_path": str(sample_file),
            "edits": [
                {"old_string": "NONEXISTENT", "new_string": "replacement"},
            ],
        })
        assert result["success"] is False
        assert result["edits_applied"] == 0
        assert sample_file.read_text() == original

    def test_empty_old_string_fails(self, sample_file):
        original = sample_file.read_text()
        result = multi_edit.invoke({
            "file_path": str(sample_file),
            "edits": [
                {"old_string": "", "new_string": "something"},
            ],
        })
        assert result["success"] is False
        assert sample_file.read_text() == original


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestErrorCases:
    """Edge cases and error handling."""

    def test_empty_edits_list(self, sample_file):
        result = multi_edit.invoke({
            "file_path": str(sample_file),
            "edits": [],
        })
        assert result["success"] is False
        assert "No edits" in result["error"]

    def test_nonexistent_file(self, tmp_path):
        result = multi_edit.invoke({
            "file_path": str(tmp_path / "does_not_exist.py"),
            "edits": [{"old_string": "a", "new_string": "b"}],
        })
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_directory_path(self, tmp_path):
        result = multi_edit.invoke({
            "file_path": str(tmp_path),
            "edits": [{"old_string": "a", "new_string": "b"}],
        })
        assert result["success"] is False
        assert "Not a file" in result["error"]

    def test_edits_total_always_set(self, sample_file):
        result = multi_edit.invoke({
            "file_path": str(sample_file),
            "edits": [
                {"old_string": "def greet(name):", "new_string": "def greet(user):"},
                {"old_string": "NONEXISTENT", "new_string": "x"},
            ],
        })
        assert result["edits_total"] == 2


# ---------------------------------------------------------------------------
# Fuzzy matching carries through
# ---------------------------------------------------------------------------


class TestFuzzyMatching:
    """Fuzzy edit strategies work through multi_edit."""

    def test_whitespace_tolerance(self, tmp_path):
        """LineTrimmedReplacer should handle trailing spaces."""
        p = tmp_path / "ws.py"
        p.write_text("def foo():  \n    pass\n", encoding="utf-8")
        result = multi_edit.invoke({
            "file_path": str(p),
            "edits": [{"old_string": "def foo():\n    pass", "new_string": "def bar():\n    pass"}],
        })
        assert result["success"] is True
        assert "def bar():" in p.read_text()


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------


class TestResultStructure:
    """Return value has expected fields."""

    def test_success_result_fields(self, sample_file):
        result = multi_edit.invoke({
            "file_path": str(sample_file),
            "edits": [{"old_string": "def greet(name):", "new_string": "def greet(user):"}],
        })
        assert "success" in result
        assert "results" in result
        assert "edits_applied" in result
        assert "edits_total" in result

    def test_per_edit_result_fields(self, sample_file):
        result = multi_edit.invoke({
            "file_path": str(sample_file),
            "edits": [{"old_string": "def greet(name):", "new_string": "def greet(user):"}],
        })
        edit_result = result["results"][0]
        assert "index" in edit_result
        assert "status" in edit_result
        assert "strategy" in edit_result
        assert "occurrences" in edit_result
