"""Jupyter notebook editing tool for AG3NT.

This module provides tools for editing Jupyter notebook cells (.ipynb files).
Supports replace, insert, and delete operations while preserving notebook structure.

Usage:
    from ag3nt_agent.notebook_tool import notebook_edit, get_notebook_tool

    # Direct edit
    result = notebook_edit(
        notebook_path="/workspace/analysis.ipynb",
        cell_index=2,
        new_source="print('Hello, World!')",
        edit_mode="replace"
    )

    # Get as LangChain tool
    tool = get_notebook_tool()
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Literal

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _get_workspace_root() -> Path:
    """Get the default workspace root directory.

    Returns:
        Path to ~/.ag3nt/workspace/
    """
    workspace = Path.home() / ".ag3nt" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _resolve_notebook_path(notebook_path: str) -> Path:
    """Resolve a notebook path, handling virtual paths.

    Args:
        notebook_path: Path to notebook (can be virtual or absolute)

    Returns:
        Resolved absolute Path
    """
    if notebook_path.startswith("/workspace/"):
        return _get_workspace_root() / notebook_path[11:]
    elif notebook_path.startswith("/"):
        return _get_workspace_root() / notebook_path[1:]
    else:
        return Path(notebook_path)


def _load_notebook(path: Path) -> dict[str, Any]:
    """Load a Jupyter notebook from disk.

    Args:
        path: Path to the notebook file

    Returns:
        Notebook dict structure

    Raises:
        FileNotFoundError: If notebook doesn't exist
        json.JSONDecodeError: If notebook is invalid JSON
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_notebook(path: Path, notebook: dict[str, Any]) -> None:
    """Save a Jupyter notebook to disk.

    Args:
        path: Path to save the notebook
        notebook: Notebook dict structure
    """
    with open(path, "w", encoding="utf-8") as f:
        json.dump(notebook, f, indent=1, ensure_ascii=False)
        f.write("\n")  # Trailing newline


def _find_cell_by_id(cells: list[dict], cell_id: str) -> int | None:
    """Find a cell's index by its ID.

    Args:
        cells: List of cell dictionaries
        cell_id: Cell ID to find

    Returns:
        Cell index or None if not found
    """
    for i, cell in enumerate(cells):
        if cell.get("id") == cell_id:
            return i
    return None


def _generate_cell_id() -> str:
    """Generate a unique cell ID.

    Returns:
        UUID-based cell ID
    """
    return str(uuid.uuid4())[:8]


def _create_cell(
    cell_type: Literal["code", "markdown"],
    source: str,
    cell_id: str | None = None,
) -> dict[str, Any]:
    """Create a new notebook cell.

    Args:
        cell_type: Type of cell ("code" or "markdown")
        source: Cell source content
        cell_id: Optional cell ID (generated if not provided)

    Returns:
        Cell dictionary
    """
    cell = {
        "cell_type": cell_type,
        "metadata": {},
        "source": source.splitlines(keepends=True) if "\n" in source else [source],
        "id": cell_id or _generate_cell_id(),
    }

    if cell_type == "code":
        cell["execution_count"] = None
        cell["outputs"] = []

    return cell


def _validate_notebook(notebook: dict[str, Any]) -> list[str]:
    """Validate notebook structure.

    Args:
        notebook: Notebook dictionary

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    if "cells" not in notebook:
        errors.append("Missing 'cells' key")
    elif not isinstance(notebook["cells"], list):
        errors.append("'cells' must be a list")

    if "nbformat" not in notebook:
        errors.append("Missing 'nbformat' key")

    if "metadata" not in notebook:
        errors.append("Missing 'metadata' key")

    return errors


def notebook_edit(
    notebook_path: str,
    new_source: str,
    cell_index: int | None = None,
    cell_id: str | None = None,
    cell_type: Literal["code", "markdown"] | None = None,
    edit_mode: Literal["replace", "insert", "delete"] = "replace",
) -> dict[str, Any]:
    """Edit a Jupyter notebook cell.

    Supports replacing, inserting, and deleting cells in .ipynb files.
    Cells can be identified by index (0-based) or by cell ID.

    Args:
        notebook_path: Path to .ipynb file
        new_source: New content for the cell (ignored for delete)
        cell_index: 0-based cell index (or use cell_id)
        cell_id: Cell ID to edit (alternative to cell_index)
        cell_type: Cell type ("code" or "markdown"). Required for insert,
                   defaults to existing type for replace.
        edit_mode: Operation type:
            - "replace": Replace cell content (default)
            - "insert": Insert new cell after specified position
            - "delete": Delete the specified cell

    Returns:
        Dictionary with success status and cell info:
        - success: Whether the operation succeeded
        - cell_count: Number of cells after operation
        - cell_index: Index of affected cell
        - error: Error message if failed
    """
    # Resolve path
    path = _resolve_notebook_path(notebook_path)

    # Check if notebook exists
    if not path.exists():
        # For insert mode, create new notebook if it doesn't exist
        if edit_mode == "insert":
            notebook = {
                "cells": [],
                "metadata": {
                    "kernelspec": {
                        "display_name": "Python 3",
                        "language": "python",
                        "name": "python3",
                    },
                    "language_info": {
                        "name": "python",
                        "version": "3.10.0",
                    },
                },
                "nbformat": 4,
                "nbformat_minor": 5,
            }
            # Ensure parent directory exists
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            return {
                "success": False,
                "error": f"Notebook not found: {notebook_path}",
            }
    else:
        # Load existing notebook
        try:
            notebook = _load_notebook(path)
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"Invalid notebook JSON: {e}",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to load notebook: {e}",
            }

    # Validate notebook structure
    validation_errors = _validate_notebook(notebook)
    if validation_errors:
        return {
            "success": False,
            "error": f"Invalid notebook structure: {'; '.join(validation_errors)}",
        }

    cells = notebook["cells"]

    # Resolve cell index from ID if provided
    target_index: int | None = cell_index
    if cell_id is not None and cell_index is None:
        target_index = _find_cell_by_id(cells, cell_id)
        if target_index is None and edit_mode != "insert":
            return {
                "success": False,
                "error": f"Cell with ID '{cell_id}' not found",
            }

    # Handle each edit mode
    if edit_mode == "delete":
        if target_index is None:
            return {
                "success": False,
                "error": "Must specify cell_index or cell_id for delete",
            }
        if target_index < 0 or target_index >= len(cells):
            return {
                "success": False,
                "error": f"Cell index {target_index} out of range (0-{len(cells) - 1})",
            }

        # Delete the cell
        deleted_cell = cells.pop(target_index)

        # Save notebook
        try:
            _save_notebook(path, notebook)
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to save notebook: {e}",
            }

        return {
            "success": True,
            "message": f"Deleted cell at index {target_index}",
            "cell_count": len(cells),
            "deleted_cell_type": deleted_cell.get("cell_type"),
        }

    elif edit_mode == "insert":
        if cell_type is None:
            cell_type = "code"  # Default to code cell for insert

        # Create new cell
        new_cell = _create_cell(cell_type, new_source)

        # Determine insert position
        if target_index is None or target_index < 0:
            # Insert at beginning
            insert_at = 0
        elif target_index >= len(cells):
            # Insert at end
            insert_at = len(cells)
        else:
            # Insert after specified cell
            insert_at = target_index + 1

        # Insert the cell
        cells.insert(insert_at, new_cell)

        # Save notebook
        try:
            _save_notebook(path, notebook)
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to save notebook: {e}",
            }

        return {
            "success": True,
            "message": f"Inserted {cell_type} cell at index {insert_at}",
            "cell_count": len(cells),
            "cell_index": insert_at,
            "cell_id": new_cell["id"],
        }

    else:  # replace
        if target_index is None:
            return {
                "success": False,
                "error": "Must specify cell_index or cell_id for replace",
            }
        if target_index < 0 or target_index >= len(cells):
            return {
                "success": False,
                "error": f"Cell index {target_index} out of range (0-{len(cells) - 1})",
            }

        # Get existing cell
        existing_cell = cells[target_index]
        existing_type = existing_cell.get("cell_type", "code")

        # Determine cell type (use provided or keep existing)
        final_type = cell_type if cell_type else existing_type

        # Update source
        if "\n" in new_source:
            cells[target_index]["source"] = new_source.splitlines(keepends=True)
        else:
            cells[target_index]["source"] = [new_source] if new_source else []

        # Update type if changed
        if final_type != existing_type:
            cells[target_index]["cell_type"] = final_type
            if final_type == "code":
                cells[target_index]["execution_count"] = None
                cells[target_index]["outputs"] = []
            elif "execution_count" in cells[target_index]:
                del cells[target_index]["execution_count"]
                del cells[target_index]["outputs"]

        # Clear outputs for code cells (content changed)
        if final_type == "code":
            cells[target_index]["outputs"] = []
            cells[target_index]["execution_count"] = None

        # Save notebook
        try:
            _save_notebook(path, notebook)
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to save notebook: {e}",
            }

        return {
            "success": True,
            "message": f"Replaced cell at index {target_index}",
            "cell_count": len(cells),
            "cell_index": target_index,
            "cell_type": final_type,
            "cell_id": cells[target_index].get("id"),
        }


@tool
def notebook_tool(
    notebook_path: str,
    new_source: str,
    cell_index: int | None = None,
    cell_id: str | None = None,
    cell_type: Literal["code", "markdown"] | None = None,
    edit_mode: Literal["replace", "insert", "delete"] = "replace",
) -> dict[str, Any]:
    """Edit a Jupyter notebook cell.

    Modify, insert, or delete cells in .ipynb notebook files. Preserves
    notebook structure and metadata.

    Args:
        notebook_path: Absolute path to .ipynb file
        new_source: New content for the cell
        cell_index: 0-based cell index. When inserting, new cell is added
                    after this index. When not specified with insert, adds
                    at beginning.
        cell_id: Cell ID to edit (alternative to cell_index)
        cell_type: "code" or "markdown". Required for insert, defaults to
                   existing type for replace.
        edit_mode: Operation type:
            - "replace": Replace cell content (default)
            - "insert": Insert new cell after cell_index
            - "delete": Delete the cell at cell_index

    Returns:
        Dictionary with success status and cell info.

    Examples:
        # Replace cell content
        notebook_tool(
            notebook_path="/workspace/analysis.ipynb",
            cell_index=2,
            new_source="import pandas as pd\\ndf = pd.read_csv('data.csv')"
        )

        # Insert new markdown cell after cell 0
        notebook_tool(
            notebook_path="/workspace/analysis.ipynb",
            cell_index=0,
            new_source="# Data Analysis\\nThis notebook analyzes...",
            cell_type="markdown",
            edit_mode="insert"
        )

        # Delete a cell
        notebook_tool(
            notebook_path="/workspace/analysis.ipynb",
            cell_index=5,
            new_source="",  # ignored for delete
            edit_mode="delete"
        )
    """
    return notebook_edit(
        notebook_path=notebook_path,
        new_source=new_source,
        cell_index=cell_index,
        cell_id=cell_id,
        cell_type=cell_type,
        edit_mode=edit_mode,
    )


def get_notebook_tool():
    """Get the notebook edit tool for the agent.

    Returns:
        LangChain tool for notebook editing
    """
    return notebook_tool


def read_notebook(notebook_path: str) -> dict[str, Any]:
    """Read and return notebook contents in a readable format.

    Args:
        notebook_path: Path to .ipynb file

    Returns:
        Dictionary with cells and metadata
    """
    path = _resolve_notebook_path(notebook_path)

    if not path.exists():
        return {
            "success": False,
            "error": f"Notebook not found: {notebook_path}",
        }

    try:
        notebook = _load_notebook(path)
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to load notebook: {e}",
        }

    # Format cells for readability
    formatted_cells = []
    for i, cell in enumerate(notebook.get("cells", [])):
        source = cell.get("source", [])
        if isinstance(source, list):
            source = "".join(source)

        formatted = {
            "index": i,
            "type": cell.get("cell_type", "unknown"),
            "source": source,
            "id": cell.get("id"),
        }

        # Include execution info for code cells
        if cell.get("cell_type") == "code":
            formatted["execution_count"] = cell.get("execution_count")
            outputs = cell.get("outputs", [])
            if outputs:
                formatted["output_count"] = len(outputs)

        formatted_cells.append(formatted)

    return {
        "success": True,
        "path": str(path),
        "cell_count": len(formatted_cells),
        "cells": formatted_cells,
        "kernel": notebook.get("metadata", {}).get("kernelspec", {}).get("display_name"),
    }
