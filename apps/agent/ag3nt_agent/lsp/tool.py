"""LSP navigation tool for AG3NT.

Exposes LSP capabilities as an agent tool: go-to-definition, find references,
hover info, document symbols, workspace symbols, and diagnostics.

Usage:
    from ag3nt_agent.lsp.tool import get_lsp_tool

    tool = get_lsp_tool()
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Literal

from langchain_core.tools import tool

logger = logging.getLogger("ag3nt.lsp.tool")


@tool
def lsp_tool(
    action: Literal[
        "definition",
        "references",
        "hover",
        "symbols",
        "workspace_symbols",
        "diagnostics",
        "implementations",
    ],
    file_path: str,
    line: int | None = None,
    character: int | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    """Navigate and inspect code using Language Server Protocol.

    Provides IDE-like code intelligence: jump to definitions, find all
    references, get type information, list symbols, and check diagnostics.

    Args:
        action: The LSP operation to perform:
            - "definition": Go to the definition of the symbol at the given position.
            - "references": Find all references to the symbol at the given position.
            - "hover": Get type info and documentation for the symbol at position.
            - "symbols": List all symbols (functions, classes, variables) in the file.
            - "workspace_symbols": Search for symbols across the entire workspace.
              Requires the `query` parameter.
            - "diagnostics": Get current errors and warnings for the file.
            - "implementations": Find implementations of an interface/abstract at position.
        file_path: Absolute path to the file to inspect.
        line: Line number (0-indexed) for position-based actions
              (definition, references, hover, implementations).
        character: Column number (0-indexed) for position-based actions.
        query: Search query for workspace_symbols action.

    Returns:
        Dictionary with results. Shape depends on action:
        - definition: {locations: [{file, line, character}]}
        - references: {locations: [{file, line, character, context}]}
        - hover: {content: str, range: {start, end}} or {content: null}
        - symbols: {symbols: [{name, kind, range, children}]}
        - workspace_symbols: {symbols: [{name, kind, file, line}]}
        - diagnostics: {diagnostics: [{severity, line, character, message, source}]}
        - implementations: {locations: [{file, line, character}]}

    Examples:
        # Find where a function is defined
        lsp_tool(action="definition", file_path="/src/app.py", line=42, character=10)

        # Find all usages of a variable
        lsp_tool(action="references", file_path="/src/app.py", line=42, character=10)

        # Get type information
        lsp_tool(action="hover", file_path="/src/app.py", line=42, character=10)

        # List all functions and classes in a file
        lsp_tool(action="symbols", file_path="/src/app.py")

        # Search for a symbol across the codebase
        lsp_tool(action="workspace_symbols", file_path="/src/app.py", query="UserService")

        # Check for compile errors
        lsp_tool(action="diagnostics", file_path="/src/app.py")
    """
    try:
        return asyncio.get_event_loop().run_until_complete(
            _lsp_action(action, file_path, line, character, query)
        )
    except RuntimeError:
        # No event loop running — create one
        return asyncio.run(
            _lsp_action(action, file_path, line, character, query)
        )


async def _lsp_action(
    action: str,
    file_path: str,
    line: int | None,
    character: int | None,
    query: str | None,
) -> dict[str, Any]:
    """Async implementation of LSP actions."""
    from ag3nt_agent.lsp.manager import LspManager

    manager = LspManager.get_instance()
    file_path = str(Path(file_path).resolve())

    # Validate position-based actions have line/character
    position_actions = {"definition", "references", "hover", "implementations"}
    if action in position_actions:
        if line is None or character is None:
            return {
                "error": f"Action '{action}' requires 'line' and 'character' parameters.",
            }

    if action == "workspace_symbols" and not query:
        return {"error": "Action 'workspace_symbols' requires a 'query' parameter."}

    try:
        if action == "definition":
            locations = await manager.definition(file_path, line, character)  # type: ignore[arg-type]
            return {
                "action": "definition",
                "file": file_path,
                "position": {"line": line, "character": character},
                "locations": _format_locations(locations),
                "count": len(locations),
            }

        elif action == "references":
            locations = await manager.references(file_path, line, character)  # type: ignore[arg-type]
            return {
                "action": "references",
                "file": file_path,
                "position": {"line": line, "character": character},
                "locations": _format_locations(locations),
                "count": len(locations),
            }

        elif action == "hover":
            result = await manager.hover(file_path, line, character)  # type: ignore[arg-type]
            if result is None:
                return {
                    "action": "hover",
                    "file": file_path,
                    "position": {"line": line, "character": character},
                    "content": None,
                }
            content = _extract_hover_content(result)
            return {
                "action": "hover",
                "file": file_path,
                "position": {"line": line, "character": character},
                "content": content,
            }

        elif action == "symbols":
            symbols = await manager.document_symbols(file_path)
            return {
                "action": "symbols",
                "file": file_path,
                "symbols": _format_symbols(symbols),
                "count": len(symbols),
            }

        elif action == "workspace_symbols":
            symbols = await manager.workspace_symbols(query)  # type: ignore[arg-type]
            return {
                "action": "workspace_symbols",
                "query": query,
                "symbols": _format_workspace_symbols(symbols),
                "count": len(symbols),
            }

        elif action == "diagnostics":
            diagnostics = await manager.get_file_diagnostics(file_path)
            formatted = _format_diagnostics(diagnostics)
            return {
                "action": "diagnostics",
                "file": file_path,
                "diagnostics": formatted,
                "error_count": sum(1 for d in formatted if d.get("severity") == "error"),
                "warning_count": sum(1 for d in formatted if d.get("severity") == "warning"),
                "count": len(formatted),
            }

        elif action == "implementations":
            # Use definition as fallback if implementations not available
            try:
                locations = await manager.definition(file_path, line, character)  # type: ignore[arg-type]
            except Exception:
                locations = []
            return {
                "action": "implementations",
                "file": file_path,
                "position": {"line": line, "character": character},
                "locations": _format_locations(locations),
                "count": len(locations),
            }

        else:
            return {"error": f"Unknown action: {action}"}

    except Exception as e:
        logger.error(f"LSP {action} failed for {file_path}: {e}")
        return {
            "error": f"LSP {action} failed: {str(e)}",
            "hint": "The language server may not be available for this file type. "
                    "Check that the appropriate language server is installed.",
        }


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_SYMBOL_KINDS: dict[int, str] = {
    1: "File", 2: "Module", 3: "Namespace", 4: "Package",
    5: "Class", 6: "Method", 7: "Property", 8: "Field",
    9: "Constructor", 10: "Enum", 11: "Interface", 12: "Function",
    13: "Variable", 14: "Constant", 15: "String", 16: "Number",
    17: "Boolean", 18: "Array", 19: "Object", 20: "Key",
    21: "Null", 22: "EnumMember", 23: "Struct", 24: "Event",
    25: "Operator", 26: "TypeParameter",
}

_SEVERITY_MAP: dict[int, str] = {
    1: "error",
    2: "warning",
    3: "info",
    4: "hint",
}


def _uri_to_path(uri: str) -> str:
    """Convert a file:// URI to a file path."""
    if uri.startswith("file:///"):
        # Handle Windows paths: file:///C:/...
        path = uri[8:] if len(uri) > 9 and uri[9] == ":" else uri[7:]
        return path.replace("/", "\\") if "\\" in path or (len(path) > 1 and path[1] == ":") else path
    if uri.startswith("file://"):
        return uri[7:]
    return uri


def _format_locations(locations: list[dict]) -> list[dict[str, Any]]:
    """Format LSP location results."""
    formatted = []
    for loc in locations:
        uri = loc.get("uri", loc.get("targetUri", ""))
        rng = loc.get("range", loc.get("targetRange", {}))
        start = rng.get("start", {})
        formatted.append({
            "file": _uri_to_path(uri),
            "line": start.get("line", 0),
            "character": start.get("character", 0),
        })
    return formatted


def _extract_hover_content(hover: dict) -> str:
    """Extract readable content from an LSP hover result."""
    contents = hover.get("contents", "")
    if isinstance(contents, str):
        return contents
    if isinstance(contents, dict):
        # MarkedString or MarkupContent
        return contents.get("value", str(contents))
    if isinstance(contents, list):
        # Array of MarkedString
        parts = []
        for item in contents:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("value", str(item)))
        return "\n\n".join(parts)
    return str(contents)


def _format_symbols(symbols: list[dict]) -> list[dict[str, Any]]:
    """Format document symbols, handling both flat and hierarchical responses."""
    formatted = []
    for sym in symbols:
        entry: dict[str, Any] = {
            "name": sym.get("name", ""),
            "kind": _SYMBOL_KINDS.get(sym.get("kind", 0), "Unknown"),
        }
        # DocumentSymbol (hierarchical) has range
        if "range" in sym:
            start = sym["range"].get("start", {})
            entry["line"] = start.get("line", 0)
        # SymbolInformation (flat) has location
        elif "location" in sym:
            start = sym["location"].get("range", {}).get("start", {})
            entry["line"] = start.get("line", 0)
            entry["file"] = _uri_to_path(sym["location"].get("uri", ""))

        if sym.get("detail"):
            entry["detail"] = sym["detail"]

        # Recurse into children (DocumentSymbol)
        children = sym.get("children", [])
        if children:
            entry["children"] = _format_symbols(children)

        formatted.append(entry)
    return formatted


def _format_workspace_symbols(symbols: list[dict]) -> list[dict[str, Any]]:
    """Format workspace symbol search results."""
    formatted = []
    for sym in symbols:
        loc = sym.get("location", {})
        uri = loc.get("uri", "")
        rng = loc.get("range", {})
        start = rng.get("start", {})
        formatted.append({
            "name": sym.get("name", ""),
            "kind": _SYMBOL_KINDS.get(sym.get("kind", 0), "Unknown"),
            "file": _uri_to_path(uri),
            "line": start.get("line", 0),
            "container": sym.get("containerName", ""),
        })
    return formatted


def _format_diagnostics(diagnostics: list[dict]) -> list[dict[str, Any]]:
    """Format LSP diagnostics for tool output."""
    formatted = []
    for diag in diagnostics:
        rng = diag.get("range", {})
        start = rng.get("start", {})
        formatted.append({
            "severity": _SEVERITY_MAP.get(diag.get("severity", 1), "error"),
            "line": start.get("line", 0),
            "character": start.get("character", 0),
            "message": diag.get("message", ""),
            "source": diag.get("source", ""),
            "code": diag.get("code"),
        })
    return formatted


def get_lsp_tool():
    """Get the LSP tool for the agent."""
    return lsp_tool
