"""Unit tests for glob_tool module."""

import time

import pytest
from pathlib import Path

from ag3nt_agent.glob_tool import (
    _load_gitignore_patterns,
    _should_ignore,
    glob_search,
    get_glob_tool,
    DEFAULT_IGNORE_PATTERNS,
)


# ---------------------------------------------------------------------------
# _load_gitignore_patterns tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadGitignorePatterns:
    """Tests for _load_gitignore_patterns helper."""

    def test_returns_empty_when_no_gitignore(self, tmp_path: Path):
        """Returns an empty list when no .gitignore exists."""
        result = _load_gitignore_patterns(tmp_path)
        assert result == []

    def test_reads_patterns_from_gitignore(self, tmp_path: Path):
        """Reads non-blank, non-comment lines from .gitignore."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\nbuild/\n", encoding="utf-8")
        result = _load_gitignore_patterns(tmp_path)
        assert result == ["*.log", "build/"]

    def test_skips_comments_and_blank_lines(self, tmp_path: Path):
        """Comments (# ...) and blank lines are excluded."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text(
            "# this is a comment\n"
            "\n"
            "  \n"
            "*.tmp\n"
            "# another comment\n"
            "logs/\n",
            encoding="utf-8",
        )
        result = _load_gitignore_patterns(tmp_path)
        assert result == ["*.tmp", "logs/"]


# ---------------------------------------------------------------------------
# _should_ignore tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestShouldIgnore:
    """Tests for _should_ignore helper."""

    def test_ignores_matching_filename_pattern(self, tmp_path: Path):
        """A *.pyc pattern should match a .pyc file."""
        target = tmp_path / "module.pyc"
        assert _should_ignore(target, tmp_path, ["*.pyc"]) is True

    def test_does_not_ignore_non_matching_file(self, tmp_path: Path):
        """A *.pyc pattern should not match a .py file."""
        target = tmp_path / "module.py"
        assert _should_ignore(target, tmp_path, ["*.pyc"]) is False

    def test_ignores_directory_pattern_with_trailing_slash(self, tmp_path: Path):
        """A pattern ending with / should match directory components."""
        target = tmp_path / "build" / "output.js"
        assert _should_ignore(target, tmp_path, ["build/"]) is True

    def test_ignores_nested_directory_component(self, tmp_path: Path):
        """Pattern should match any path component, not just top-level."""
        target = tmp_path / "src" / "node_modules" / "pkg" / "index.js"
        assert _should_ignore(target, tmp_path, ["node_modules"]) is True

    def test_no_match_returns_false(self, tmp_path: Path):
        """When no pattern matches, return False."""
        target = tmp_path / "src" / "main.py"
        assert _should_ignore(target, tmp_path, ["*.log", "dist/"]) is False


# ---------------------------------------------------------------------------
# glob_search tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGlobSearch:
    """Tests for the main glob_search function."""

    def _create_files(self, root: Path, names: list[str]) -> None:
        """Helper to create files (and intermediate dirs) under root."""
        for name in names:
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"file: {name}", encoding="utf-8")

    # -- basic behaviour ---------------------------------------------------

    def test_finds_matching_files(self, tmp_path: Path):
        """Should return files that match the given glob pattern."""
        self._create_files(tmp_path, ["a.py", "b.py", "c.txt"])
        result = glob_search("*.py", path=str(tmp_path))
        assert result["count"] == 2
        assert set(result["matches"]) == {"a.py", "b.py"}
        assert result["truncated"] is False

    def test_recursive_glob(self, tmp_path: Path):
        """** patterns recurse into subdirectories."""
        self._create_files(tmp_path, [
            "top.py",
            "sub/deep.py",
            "sub/nested/deeper.py",
        ])
        result = glob_search("**/*.py", path=str(tmp_path))
        assert result["count"] == 3
        assert "sub/deep.py" in result["matches"]
        assert "sub/nested/deeper.py" in result["matches"]

    # -- error cases -------------------------------------------------------

    def test_nonexistent_directory_returns_error(self, tmp_path: Path):
        """An error dict is returned when the path does not exist."""
        bad_path = str(tmp_path / "does_not_exist")
        result = glob_search("*.py", path=bad_path)
        assert "error" in result
        assert result["count"] == 0

    def test_file_path_returns_error(self, tmp_path: Path):
        """An error dict is returned when the path is a file, not a dir."""
        f = tmp_path / "file.txt"
        f.write_text("hello", encoding="utf-8")
        result = glob_search("*.py", path=str(f))
        assert "error" in result
        assert "not a directory" in result["error"]

    # -- max_results -------------------------------------------------------

    def test_max_results_limits_output(self, tmp_path: Path):
        """Only max_results entries should be returned, with truncated=True."""
        self._create_files(tmp_path, [f"f{i}.py" for i in range(10)])
        result = glob_search("*.py", path=str(tmp_path), max_results=3)
        assert result["count"] == 3
        assert result["total_found"] == 10
        assert result["truncated"] is True

    # -- hidden files ------------------------------------------------------

    def test_hidden_files_excluded_by_default(self, tmp_path: Path):
        """Hidden files (dot-prefixed) are excluded when include_hidden=False."""
        self._create_files(tmp_path, ["visible.py", ".hidden.py"])
        result = glob_search("*.py", path=str(tmp_path), include_hidden=False)
        assert result["count"] == 1
        assert result["matches"] == ["visible.py"]

    def test_hidden_files_included_when_flag_set(self, tmp_path: Path):
        """Hidden files are included when include_hidden=True."""
        self._create_files(tmp_path, ["visible.py", ".hidden.py"])
        result = glob_search("*.py", path=str(tmp_path), include_hidden=True)
        assert result["count"] == 2

    def test_hidden_files_allowed_when_pattern_starts_with_dot(self, tmp_path: Path):
        """If the pattern itself starts with '.', hidden files are allowed."""
        self._create_files(tmp_path, [".hidden_cfg", ".hidden_other", "README.md"])
        result = glob_search(
            ".hidden*",
            path=str(tmp_path),
            include_hidden=False,
            respect_gitignore=False,
        )
        matches = result["matches"]
        assert ".hidden_cfg" in matches
        assert ".hidden_other" in matches
        assert "README.md" not in matches

    # -- gitignore / ignore patterns ---------------------------------------

    def test_respects_gitignore(self, tmp_path: Path):
        """Files matching .gitignore patterns are excluded."""
        self._create_files(tmp_path, ["app.py", "debug.log"])
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\n", encoding="utf-8")
        result = glob_search("*", path=str(tmp_path), respect_gitignore=True)
        names = result["matches"]
        assert "app.py" in names
        assert "debug.log" not in names

    def test_default_ignore_patterns_applied(self, tmp_path: Path):
        """DEFAULT_IGNORE_PATTERNS (e.g. __pycache__) are always applied."""
        self._create_files(tmp_path, [
            "main.py",
            "__pycache__/main.cpython-311.pyc",
        ])
        result = glob_search("**/*", path=str(tmp_path))
        for m in result["matches"]:
            assert "__pycache__" not in m

    def test_gitignore_disabled(self, tmp_path: Path):
        """When respect_gitignore=False, .gitignore patterns are NOT loaded."""
        self._create_files(tmp_path, ["keep.py", "drop.log"])
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.log\n", encoding="utf-8")
        result = glob_search("*", path=str(tmp_path), respect_gitignore=False)
        names = result["matches"]
        assert "drop.log" in names

    # -- directories are skipped -------------------------------------------

    def test_directories_not_in_results(self, tmp_path: Path):
        """Only files are returned; directories themselves are excluded."""
        sub = tmp_path / "subdir"
        sub.mkdir()
        self._create_files(tmp_path, ["file.txt"])
        result = glob_search("*", path=str(tmp_path))
        for m in result["matches"]:
            assert m != "subdir"

    # -- mtime sorting -----------------------------------------------------

    def test_results_sorted_by_mtime_descending(self, tmp_path: Path):
        """Matches are sorted most-recently-modified first."""
        older = tmp_path / "older.py"
        older.write_text("old", encoding="utf-8")
        # Ensure a measurable mtime difference
        time.sleep(0.05)
        newer = tmp_path / "newer.py"
        newer.write_text("new", encoding="utf-8")

        result = glob_search("*.py", path=str(tmp_path))
        assert result["matches"][0] == "newer.py"
        assert result["matches"][1] == "older.py"

    # -- result dict shape -------------------------------------------------

    def test_result_dict_keys(self, tmp_path: Path):
        """The returned dict contains the expected keys."""
        self._create_files(tmp_path, ["a.py"])
        result = glob_search("*.py", path=str(tmp_path))
        expected_keys = {"matches", "count", "total_found", "truncated", "search_root", "pattern"}
        assert expected_keys == set(result.keys())
        assert result["pattern"] == "*.py"
        assert result["search_root"] == str(tmp_path)


# ---------------------------------------------------------------------------
# get_glob_tool tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetGlobTool:
    """Tests for get_glob_tool factory."""

    def test_returns_tool_object(self):
        """get_glob_tool() returns a LangChain StructuredTool."""
        tool = get_glob_tool()
        assert tool is not None
        assert tool.name == "glob_tool"
        assert hasattr(tool, "invoke")
