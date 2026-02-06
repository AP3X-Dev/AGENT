"""Unit tests for notebook_tool module.

Tests cover:
- _resolve_notebook_path path resolution
- _find_cell_by_id cell lookup
- _generate_cell_id ID generation
- _create_cell cell dict creation
- _validate_notebook structure validation
- notebook_edit replace, insert, and delete operations
- read_notebook reading and formatting
- get_notebook_tool tool retrieval
"""

import json
from pathlib import Path

import pytest

from ag3nt_agent.notebook_tool import (
    _resolve_notebook_path,
    _find_cell_by_id,
    _generate_cell_id,
    _create_cell,
    _validate_notebook,
    notebook_edit,
    read_notebook,
    get_notebook_tool,
)


def _make_notebook(cells=None):
    """Create a minimal valid notebook dict."""
    if cells is None:
        cells = [
            {
                "cell_type": "code",
                "source": ["print('hello')"],
                "metadata": {},
                "id": "abc12345",
                "execution_count": 1,
                "outputs": [],
            },
            {
                "cell_type": "markdown",
                "source": ["# Title"],
                "metadata": {},
                "id": "def67890",
            },
        ]
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _write_notebook(path: Path, notebook=None):
    """Write a notebook dict to a file and return the path."""
    if notebook is None:
        notebook = _make_notebook()
    path.write_text(json.dumps(notebook), encoding="utf-8")
    return path


@pytest.mark.unit
class TestResolveNotebookPath:
    """Tests for _resolve_notebook_path."""

    def test_workspace_prefix_stripped(self):
        """Paths starting with /workspace/ should be resolved under the workspace root."""
        result = _resolve_notebook_path("/workspace/analysis.ipynb")
        assert result.name == "analysis.ipynb"
        assert ".ag3nt" in str(result) or "workspace" in str(result)

    def test_absolute_slash_prefix_resolved(self):
        """Paths starting with / (but not /workspace/) also go to workspace root."""
        result = _resolve_notebook_path("/my/notebook.ipynb")
        assert result.name == "notebook.ipynb"

    def test_regular_absolute_path_unchanged(self, tmp_path):
        """Non-slash-prefixed absolute paths should be returned as-is."""
        abs_path = str(tmp_path / "test.ipynb")
        result = _resolve_notebook_path(abs_path)
        assert result == Path(abs_path)


@pytest.mark.unit
class TestFindCellById:
    """Tests for _find_cell_by_id."""

    def test_finds_existing_cell(self):
        """Should return the correct index for a matching cell id."""
        cells = [
            {"id": "aaa", "cell_type": "code"},
            {"id": "bbb", "cell_type": "markdown"},
            {"id": "ccc", "cell_type": "code"},
        ]
        assert _find_cell_by_id(cells, "bbb") == 1

    def test_returns_none_for_missing_id(self):
        """Should return None when no cell has the given id."""
        cells = [{"id": "aaa"}, {"id": "bbb"}]
        assert _find_cell_by_id(cells, "zzz") is None

    def test_empty_cells_list(self):
        """Should return None when cells list is empty."""
        assert _find_cell_by_id([], "anything") is None


@pytest.mark.unit
class TestGenerateCellId:
    """Tests for _generate_cell_id."""

    def test_returns_eight_char_string(self):
        """Generated cell ID should be exactly 8 characters."""
        cell_id = _generate_cell_id()
        assert isinstance(cell_id, str)
        assert len(cell_id) == 8

    def test_unique_ids(self):
        """Multiple calls should produce distinct IDs."""
        ids = {_generate_cell_id() for _ in range(50)}
        assert len(ids) == 50


@pytest.mark.unit
class TestCreateCell:
    """Tests for _create_cell."""

    def test_code_cell_has_execution_fields(self):
        """Code cells must include execution_count and outputs."""
        cell = _create_cell("code", "x = 1")
        assert cell["cell_type"] == "code"
        assert cell["source"] == ["x = 1"]
        assert cell["execution_count"] is None
        assert cell["outputs"] == []
        assert "id" in cell
        assert cell["metadata"] == {}

    def test_markdown_cell_no_execution_fields(self):
        """Markdown cells should not have execution_count or outputs."""
        cell = _create_cell("markdown", "# Hello")
        assert cell["cell_type"] == "markdown"
        assert cell["source"] == ["# Hello"]
        assert "execution_count" not in cell
        assert "outputs" not in cell

    def test_multiline_source_split(self):
        """Source with newlines should be split with keepends=True."""
        cell = _create_cell("code", "a = 1\nb = 2\n")
        assert cell["source"] == ["a = 1\n", "b = 2\n"]

    def test_custom_cell_id(self):
        """A supplied cell_id should be used instead of generating one."""
        cell = _create_cell("code", "pass", cell_id="custom99")
        assert cell["id"] == "custom99"


@pytest.mark.unit
class TestValidateNotebook:
    """Tests for _validate_notebook."""

    def test_valid_notebook_no_errors(self):
        """A well-formed notebook should produce no validation errors."""
        nb = _make_notebook()
        assert _validate_notebook(nb) == []

    def test_missing_cells_key(self):
        """Missing 'cells' should be reported."""
        nb = {"nbformat": 4, "metadata": {}}
        errors = _validate_notebook(nb)
        assert any("cells" in e for e in errors)

    def test_cells_not_a_list(self):
        """'cells' that is not a list should be reported."""
        nb = {"cells": "not a list", "nbformat": 4, "metadata": {}}
        errors = _validate_notebook(nb)
        assert any("list" in e for e in errors)

    def test_missing_nbformat(self):
        """Missing 'nbformat' should be reported."""
        nb = {"cells": [], "metadata": {}}
        errors = _validate_notebook(nb)
        assert any("nbformat" in e for e in errors)

    def test_missing_metadata(self):
        """Missing 'metadata' should be reported."""
        nb = {"cells": [], "nbformat": 4}
        errors = _validate_notebook(nb)
        assert any("metadata" in e for e in errors)

    def test_multiple_errors_reported(self):
        """All missing keys should be reported at once."""
        errors = _validate_notebook({})
        assert len(errors) == 3  # cells, nbformat, metadata


@pytest.mark.unit
class TestNotebookEditReplace:
    """Tests for notebook_edit in replace mode."""

    def test_replace_cell_source(self, tmp_path):
        """Replacing a cell should update its source."""
        nb_path = _write_notebook(tmp_path / "test.ipynb")
        result = notebook_edit(
            notebook_path=str(nb_path),
            new_source="print('updated')",
            cell_index=0,
            edit_mode="replace",
        )
        assert result["success"] is True
        assert result["cell_index"] == 0
        assert result["cell_count"] == 2

        # Verify on disk
        saved = json.loads(nb_path.read_text(encoding="utf-8"))
        assert saved["cells"][0]["source"] == ["print('updated')"]

    def test_replace_changes_cell_type(self, tmp_path):
        """Replacing with a different cell_type should update the type and fields."""
        nb_path = _write_notebook(tmp_path / "test.ipynb")
        result = notebook_edit(
            notebook_path=str(nb_path),
            new_source="# Now markdown",
            cell_index=0,
            cell_type="markdown",
            edit_mode="replace",
        )
        assert result["success"] is True
        assert result["cell_type"] == "markdown"

        saved = json.loads(nb_path.read_text(encoding="utf-8"))
        cell = saved["cells"][0]
        assert cell["cell_type"] == "markdown"
        assert "execution_count" not in cell
        assert "outputs" not in cell

    def test_replace_clears_outputs_for_code(self, tmp_path):
        """Replacing a code cell should reset execution_count and outputs."""
        nb = _make_notebook()
        nb["cells"][0]["execution_count"] = 5
        nb["cells"][0]["outputs"] = [{"output_type": "stream", "text": ["hi"]}]
        nb_path = tmp_path / "test.ipynb"
        _write_notebook(nb_path, nb)

        result = notebook_edit(
            notebook_path=str(nb_path),
            new_source="x = 42",
            cell_index=0,
            edit_mode="replace",
        )
        assert result["success"] is True
        saved = json.loads(nb_path.read_text(encoding="utf-8"))
        assert saved["cells"][0]["execution_count"] is None
        assert saved["cells"][0]["outputs"] == []

    def test_replace_no_index_or_id_fails(self, tmp_path):
        """Replace without cell_index or cell_id should fail."""
        nb_path = _write_notebook(tmp_path / "test.ipynb")
        result = notebook_edit(
            notebook_path=str(nb_path),
            new_source="x",
            edit_mode="replace",
        )
        assert result["success"] is False
        assert "cell_index" in result["error"] or "cell_id" in result["error"]

    def test_replace_out_of_range_fails(self, tmp_path):
        """Replace with an out-of-range index should fail."""
        nb_path = _write_notebook(tmp_path / "test.ipynb")
        result = notebook_edit(
            notebook_path=str(nb_path),
            new_source="x",
            cell_index=99,
            edit_mode="replace",
        )
        assert result["success"] is False
        assert "out of range" in result["error"]

    def test_replace_by_cell_id(self, tmp_path):
        """Replace using cell_id should find and update the correct cell."""
        nb_path = _write_notebook(tmp_path / "test.ipynb")
        result = notebook_edit(
            notebook_path=str(nb_path),
            new_source="# Updated title",
            cell_id="def67890",
            edit_mode="replace",
        )
        assert result["success"] is True
        assert result["cell_index"] == 1

        saved = json.loads(nb_path.read_text(encoding="utf-8"))
        assert saved["cells"][1]["source"] == ["# Updated title"]


@pytest.mark.unit
class TestNotebookEditInsert:
    """Tests for notebook_edit in insert mode."""

    def test_insert_after_index(self, tmp_path):
        """Insert should add a cell after the given index."""
        nb_path = _write_notebook(tmp_path / "test.ipynb")
        result = notebook_edit(
            notebook_path=str(nb_path),
            new_source="# New cell",
            cell_index=0,
            cell_type="markdown",
            edit_mode="insert",
        )
        assert result["success"] is True
        assert result["cell_index"] == 1
        assert result["cell_count"] == 3
        assert "cell_id" in result

    def test_insert_at_beginning_no_index(self, tmp_path):
        """Insert with no index should insert at position 0."""
        nb_path = _write_notebook(tmp_path / "test.ipynb")
        result = notebook_edit(
            notebook_path=str(nb_path),
            new_source="first = True",
            cell_type="code",
            edit_mode="insert",
        )
        assert result["success"] is True
        assert result["cell_index"] == 0

        saved = json.loads(nb_path.read_text(encoding="utf-8"))
        assert saved["cells"][0]["source"] == ["first = True"]

    def test_insert_defaults_to_code(self, tmp_path):
        """Insert without cell_type should default to code."""
        nb_path = _write_notebook(tmp_path / "test.ipynb")
        result = notebook_edit(
            notebook_path=str(nb_path),
            new_source="y = 2",
            cell_index=0,
            edit_mode="insert",
        )
        assert result["success"] is True

        saved = json.loads(nb_path.read_text(encoding="utf-8"))
        new_cell = saved["cells"][1]
        assert new_cell["cell_type"] == "code"
        assert new_cell["execution_count"] is None
        assert new_cell["outputs"] == []

    def test_insert_creates_new_notebook(self, tmp_path):
        """Insert on a non-existent file should create a new notebook."""
        nb_path = tmp_path / "brand_new.ipynb"
        assert not nb_path.exists()

        result = notebook_edit(
            notebook_path=str(nb_path),
            new_source="print('brand new')",
            cell_type="code",
            edit_mode="insert",
        )
        assert result["success"] is True
        assert result["cell_count"] == 1
        assert nb_path.exists()

        saved = json.loads(nb_path.read_text(encoding="utf-8"))
        assert saved["nbformat"] == 4
        assert len(saved["cells"]) == 1
        assert saved["cells"][0]["source"] == ["print('brand new')"]


@pytest.mark.unit
class TestNotebookEditDelete:
    """Tests for notebook_edit in delete mode."""

    def test_delete_cell(self, tmp_path):
        """Deleting a cell should remove it and return the correct count."""
        nb_path = _write_notebook(tmp_path / "test.ipynb")
        result = notebook_edit(
            notebook_path=str(nb_path),
            new_source="",
            cell_index=0,
            edit_mode="delete",
        )
        assert result["success"] is True
        assert result["cell_count"] == 1
        assert result["deleted_cell_type"] == "code"

        saved = json.loads(nb_path.read_text(encoding="utf-8"))
        assert len(saved["cells"]) == 1
        assert saved["cells"][0]["id"] == "def67890"

    def test_delete_out_of_range_fails(self, tmp_path):
        """Delete with out-of-range index should fail."""
        nb_path = _write_notebook(tmp_path / "test.ipynb")
        result = notebook_edit(
            notebook_path=str(nb_path),
            new_source="",
            cell_index=10,
            edit_mode="delete",
        )
        assert result["success"] is False
        assert "out of range" in result["error"]

    def test_delete_no_index_fails(self, tmp_path):
        """Delete without cell_index or cell_id should fail."""
        nb_path = _write_notebook(tmp_path / "test.ipynb")
        result = notebook_edit(
            notebook_path=str(nb_path),
            new_source="",
            edit_mode="delete",
        )
        assert result["success"] is False


@pytest.mark.unit
class TestNotebookEditEdgeCases:
    """Edge case tests for notebook_edit."""

    def test_nonexistent_file_replace_fails(self, tmp_path):
        """Replace on a non-existent file should fail."""
        result = notebook_edit(
            notebook_path=str(tmp_path / "missing.ipynb"),
            new_source="x",
            cell_index=0,
            edit_mode="replace",
        )
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_invalid_json_fails(self, tmp_path):
        """A file with invalid JSON should report an error."""
        bad_path = tmp_path / "bad.ipynb"
        bad_path.write_text("{invalid json!!!", encoding="utf-8")
        result = notebook_edit(
            notebook_path=str(bad_path),
            new_source="x",
            cell_index=0,
            edit_mode="replace",
        )
        assert result["success"] is False
        assert "Invalid notebook JSON" in result["error"]

    def test_invalid_structure_fails(self, tmp_path):
        """A notebook missing required keys should fail validation."""
        bad_nb_path = tmp_path / "bad_struct.ipynb"
        bad_nb_path.write_text(json.dumps({"something": "else"}), encoding="utf-8")
        result = notebook_edit(
            notebook_path=str(bad_nb_path),
            new_source="x",
            cell_index=0,
            edit_mode="replace",
        )
        assert result["success"] is False
        assert "Invalid notebook structure" in result["error"]

    def test_cell_id_not_found_replace_fails(self, tmp_path):
        """Replace by a non-existent cell_id should fail."""
        nb_path = _write_notebook(tmp_path / "test.ipynb")
        result = notebook_edit(
            notebook_path=str(nb_path),
            new_source="x",
            cell_id="nonexistent",
            edit_mode="replace",
        )
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_replace_multiline_source(self, tmp_path):
        """Replace with multiline source should split correctly."""
        nb_path = _write_notebook(tmp_path / "test.ipynb")
        result = notebook_edit(
            notebook_path=str(nb_path),
            new_source="a = 1\nb = 2\nc = 3",
            cell_index=0,
            edit_mode="replace",
        )
        assert result["success"] is True

        saved = json.loads(nb_path.read_text(encoding="utf-8"))
        assert saved["cells"][0]["source"] == ["a = 1\n", "b = 2\n", "c = 3"]

    def test_replace_empty_source(self, tmp_path):
        """Replace with empty string should result in empty source list."""
        nb_path = _write_notebook(tmp_path / "test.ipynb")
        result = notebook_edit(
            notebook_path=str(nb_path),
            new_source="",
            cell_index=0,
            edit_mode="replace",
        )
        assert result["success"] is True

        saved = json.loads(nb_path.read_text(encoding="utf-8"))
        assert saved["cells"][0]["source"] == []


@pytest.mark.unit
class TestReadNotebook:
    """Tests for read_notebook."""

    def test_read_existing_notebook(self, tmp_path):
        """Should return formatted cells from an existing notebook."""
        nb_path = _write_notebook(tmp_path / "test.ipynb")
        result = read_notebook(str(nb_path))

        assert result["success"] is True
        assert result["cell_count"] == 2
        assert result["path"] == str(nb_path)
        assert result["kernel"] == "Python 3"

        cells = result["cells"]
        assert cells[0]["index"] == 0
        assert cells[0]["type"] == "code"
        assert cells[0]["source"] == "print('hello')"
        assert cells[0]["execution_count"] == 1
        assert cells[0]["id"] == "abc12345"

        assert cells[1]["index"] == 1
        assert cells[1]["type"] == "markdown"
        assert cells[1]["source"] == "# Title"

    def test_read_nonexistent_fails(self, tmp_path):
        """Reading a missing notebook should return an error."""
        result = read_notebook(str(tmp_path / "no_such.ipynb"))
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_read_code_cell_with_outputs(self, tmp_path):
        """Code cells with outputs should include output_count."""
        nb = _make_notebook()
        nb["cells"][0]["outputs"] = [
            {"output_type": "stream", "text": ["hello\n"]},
            {"output_type": "execute_result", "data": {"text/plain": ["42"]}},
        ]
        nb_path = _write_notebook(tmp_path / "test.ipynb", nb)
        result = read_notebook(str(nb_path))

        assert result["success"] is True
        assert result["cells"][0]["output_count"] == 2


@pytest.mark.unit
class TestGetNotebookTool:
    """Tests for get_notebook_tool."""

    def test_returns_tool(self):
        """get_notebook_tool should return the notebook_tool with correct name."""
        tool_fn = get_notebook_tool()
        assert tool_fn is not None
        assert tool_fn.name == "notebook_tool"
        assert hasattr(tool_fn, "invoke")
