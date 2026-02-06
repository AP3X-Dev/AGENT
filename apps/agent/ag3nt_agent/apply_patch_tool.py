"""Multi-file structured patch tool for AG3NT.

Supports a custom patch format with Begin/End markers, file-level hunks,
and flexible line matching for reliable automated file modifications.

Patch format:
    *** Begin Patch
    *** Add File: path/to/new_file.py
    +line 1
    +line 2
    *** Delete File: path/to/old_file.py
    *** Update File: path/to/existing.py
    @@ context marker @@
     context line (unchanged)
    -removed line
    +added line
    *** End Patch

Usage:
    from ag3nt_agent.apply_patch_tool import get_apply_patch_tool

    tool = get_apply_patch_tool()
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from langchain_core.tools import tool

logger = logging.getLogger("ag3nt.patch")


@dataclass
class PatchLine:
    """A single line in a patch hunk."""

    prefix: str  # "+", "-", " " (context)
    content: str


@dataclass
class FilePatch:
    """Patch operations for a single file."""

    action: Literal["add", "delete", "update"]
    path: str
    lines: list[PatchLine] = field(default_factory=list)


@dataclass
class PatchResult:
    """Result of applying patches."""

    success: bool
    files_modified: list[str] = field(default_factory=list)
    files_added: list[str] = field(default_factory=list)
    files_deleted: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PatchParser:
    """Parse the structured patch format into FilePatch objects."""

    _FILE_PATTERN = re.compile(
        r"^\*\*\*\s+(Add|Delete|Update)\s+File:\s*(.+)$", re.IGNORECASE
    )

    @classmethod
    def parse(cls, text: str) -> list[FilePatch]:
        """Parse patch text into a list of FilePatch objects.

        Args:
            text: The full patch text with Begin/End markers

        Returns:
            List of FilePatch objects

        Raises:
            ValueError: If the patch format is invalid
        """
        lines = text.strip().split("\n")

        # Find Begin/End markers
        start_idx = None
        end_idx = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.lower() == "*** begin patch":
                start_idx = i
            elif stripped.lower() == "*** end patch":
                end_idx = i

        if start_idx is None:
            raise ValueError("Missing '*** Begin Patch' marker")
        if end_idx is None:
            raise ValueError("Missing '*** End Patch' marker")

        # Parse file hunks between markers
        patches: list[FilePatch] = []
        current_patch: FilePatch | None = None

        for i in range(start_idx + 1, end_idx):
            line = lines[i]

            # Check for file header
            match = cls._FILE_PATTERN.match(line.strip())
            if match:
                action_str = match.group(1).lower()
                file_path = match.group(2).strip()
                current_patch = FilePatch(
                    action=action_str,  # type: ignore[arg-type]
                    path=file_path,
                )
                patches.append(current_patch)
                continue

            # Skip context markers (@@)
            if line.strip().startswith("@@"):
                continue

            # Parse line with prefix
            if current_patch is not None:
                if line.startswith("+"):
                    current_patch.lines.append(PatchLine("+", line[1:]))
                elif line.startswith("-"):
                    current_patch.lines.append(PatchLine("-", line[1:]))
                elif line.startswith(" "):
                    current_patch.lines.append(PatchLine(" ", line[1:]))
                elif line.strip() == "":
                    # Empty line treated as context
                    current_patch.lines.append(PatchLine(" ", ""))

        return patches


class PatchApplier:
    """Apply parsed patches to the filesystem."""

    def __init__(self, workspace_root: str | None = None) -> None:
        self.workspace_root = workspace_root or self._get_workspace()

    @staticmethod
    def _get_workspace() -> str:
        """Get the workspace directory."""
        ws = Path.home() / ".ag3nt" / "workspace"
        ws.mkdir(parents=True, exist_ok=True)
        return str(ws)

    def apply(self, patches: list[FilePatch], dry_run: bool = False) -> PatchResult:
        """Apply a list of file patches.

        Args:
            patches: List of FilePatch objects to apply
            dry_run: If True, validate without making changes

        Returns:
            PatchResult with details of what was done
        """
        result = PatchResult(success=True)

        for patch in patches:
            try:
                resolved_path = self._resolve_path(patch.path)

                if patch.action == "add":
                    self._apply_add(resolved_path, patch, result, dry_run)
                elif patch.action == "delete":
                    self._apply_delete(resolved_path, patch, result, dry_run)
                elif patch.action == "update":
                    self._apply_update(resolved_path, patch, result, dry_run)
                else:
                    result.errors.append(f"Unknown action: {patch.action}")
                    result.success = False

            except Exception as e:
                result.errors.append(f"Error applying patch to {patch.path}: {e}")
                result.success = False

        return result

    def _resolve_path(self, file_path: str) -> str:
        """Resolve a file path relative to workspace root."""
        # Handle absolute paths and virtual paths
        if file_path.startswith("/workspace/"):
            file_path = file_path[len("/workspace/"):]
        elif file_path.startswith("/"):
            file_path = file_path.lstrip("/")

        return os.path.join(self.workspace_root, file_path)

    def _apply_add(
        self,
        resolved_path: str,
        patch: FilePatch,
        result: PatchResult,
        dry_run: bool,
    ) -> None:
        """Add a new file."""
        if os.path.exists(resolved_path):
            result.warnings.append(f"File already exists, overwriting: {patch.path}")

        content_lines = [line.content for line in patch.lines if line.prefix == "+"]
        content = "\n".join(content_lines)

        if not dry_run:
            os.makedirs(os.path.dirname(resolved_path), exist_ok=True)
            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(content)
                if content and not content.endswith("\n"):
                    f.write("\n")

        result.files_added.append(patch.path)

    def _apply_delete(
        self,
        resolved_path: str,
        patch: FilePatch,
        result: PatchResult,
        dry_run: bool,
    ) -> None:
        """Delete a file."""
        if not os.path.exists(resolved_path):
            result.warnings.append(f"File not found for deletion: {patch.path}")
            return

        if not dry_run:
            os.remove(resolved_path)

        result.files_deleted.append(patch.path)

    def _apply_update(
        self,
        resolved_path: str,
        patch: FilePatch,
        result: PatchResult,
        dry_run: bool,
    ) -> None:
        """Update an existing file using context matching."""
        if not os.path.exists(resolved_path):
            result.errors.append(f"File not found for update: {patch.path}")
            result.success = False
            return

        with open(resolved_path, "r", encoding="utf-8") as f:
            original_lines = f.read().split("\n")

        # Build the updated content by applying hunks
        new_lines = self._apply_hunk(original_lines, patch.lines, result, patch.path)
        if new_lines is None:
            result.success = False
            return

        if not dry_run:
            content = "\n".join(new_lines)
            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(content)

        result.files_modified.append(patch.path)

    def _apply_hunk(
        self,
        original_lines: list[str],
        patch_lines: list[PatchLine],
        result: PatchResult,
        file_path: str,
    ) -> list[str] | None:
        """Apply patch lines to original file lines using flexible matching.

        Uses context lines to find the right position, then applies additions
        and removals.

        Returns:
            Updated lines or None on failure
        """
        if not patch_lines:
            return original_lines

        # Collect context and removal lines for matching
        context_lines = []
        for pline in patch_lines:
            if pline.prefix in (" ", "-"):
                context_lines.append(pline)

        if not context_lines:
            # No context - just additions, append to file
            new_lines = list(original_lines)
            for pline in patch_lines:
                if pline.prefix == "+":
                    new_lines.append(pline.content)
            return new_lines

        # Find the position of the first context/removal line
        first_ctx = context_lines[0].content
        match_pos = self._find_match(original_lines, first_ctx)

        if match_pos == -1:
            result.errors.append(
                f"Could not find matching context in {file_path}: "
                f"{first_ctx[:60]!r}"
            )
            return None

        # Walk through original and patch lines in parallel
        out_lines: list[str] = []
        orig_idx = 0

        # Copy lines before the match position
        while orig_idx < match_pos:
            out_lines.append(original_lines[orig_idx])
            orig_idx += 1

        # Apply the patch
        for pline in patch_lines:
            if pline.prefix == " ":
                # Context line - copy from original (advance pointer)
                if orig_idx < len(original_lines):
                    out_lines.append(original_lines[orig_idx])
                    orig_idx += 1
                else:
                    out_lines.append(pline.content)
            elif pline.prefix == "-":
                # Removal - skip the original line
                if orig_idx < len(original_lines):
                    # Verify it matches (flexible)
                    if not self._lines_match(
                        original_lines[orig_idx], pline.content
                    ):
                        result.warnings.append(
                            f"Removal mismatch in {file_path} at line {orig_idx + 1}: "
                            f"expected {pline.content[:40]!r}, "
                            f"got {original_lines[orig_idx][:40]!r}"
                        )
                    orig_idx += 1
            elif pline.prefix == "+":
                # Addition - insert new line
                out_lines.append(pline.content)

        # Copy remaining original lines
        while orig_idx < len(original_lines):
            out_lines.append(original_lines[orig_idx])
            orig_idx += 1

        return out_lines

    def _find_match(self, lines: list[str], target: str) -> int:
        """Find the best matching line position using flexible matching.

        Tries progressively looser matching strategies:
        1. Exact match
        2. Right-stripped match
        3. Fully stripped match
        4. Normalized punctuation match

        Returns:
            Line index or -1 if not found
        """
        # Strategy 1: exact match
        for i, line in enumerate(lines):
            if line == target:
                return i

        # Strategy 2: rstrip match
        target_rstrip = target.rstrip()
        for i, line in enumerate(lines):
            if line.rstrip() == target_rstrip:
                return i

        # Strategy 3: strip match
        target_strip = target.strip()
        for i, line in enumerate(lines):
            if line.strip() == target_strip:
                return i

        # Strategy 4: normalized match (collapse whitespace, normalize unicode)
        target_norm = self._normalize(target)
        for i, line in enumerate(lines):
            if self._normalize(line) == target_norm:
                return i

        return -1

    def _lines_match(self, line1: str, line2: str) -> bool:
        """Check if two lines match using flexible matching."""
        if line1 == line2:
            return True
        if line1.rstrip() == line2.rstrip():
            return True
        if line1.strip() == line2.strip():
            return True
        if self._normalize(line1) == self._normalize(line2):
            return True
        return False

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize text for fuzzy matching."""
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text.strip())
        # Normalize unicode
        text = unicodedata.normalize("NFKC", text)
        # Normalize quotes
        text = text.replace("\u2018", "'").replace("\u2019", "'")
        text = text.replace("\u201c", '"').replace("\u201d", '"')
        return text


@tool
def apply_patch(
    patch: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Apply a multi-file structured patch to the workspace.

    Uses a custom patch format with explicit file-level operations.
    Supports creating, deleting, and updating files with context-based matching.

    Patch format:
    ```
    *** Begin Patch
    *** Add File: path/to/new_file.py
    +new line 1
    +new line 2

    *** Update File: path/to/existing.py
    @@ near function definition @@
     context line (unchanged)
    -old line to remove
    +new line to add
     more context

    *** Delete File: path/to/old_file.py
    *** End Patch
    ```

    Line prefixes:
    - `+` = add this line
    - `-` = remove this line
    - ` ` (space) = context line (must exist, stays unchanged)
    - `@@` = context marker (optional, for readability)

    Args:
        patch: The patch text in the format above
        dry_run: If True, validate the patch without making changes

    Returns:
        Dictionary with:
        - success: Whether all patches applied successfully
        - files_modified: List of updated files
        - files_added: List of new files created
        - files_deleted: List of deleted files
        - errors: List of error messages
        - warnings: List of warning messages
    """
    try:
        patches = PatchParser.parse(patch)
    except ValueError as e:
        return {
            "success": False,
            "errors": [str(e)],
            "files_modified": [],
            "files_added": [],
            "files_deleted": [],
            "warnings": [],
        }

    if not patches:
        return {
            "success": False,
            "errors": ["No file patches found in patch text"],
            "files_modified": [],
            "files_added": [],
            "files_deleted": [],
            "warnings": [],
        }

    applier = PatchApplier()
    result = applier.apply(patches, dry_run=dry_run)

    logger.info(
        f"apply_patch: success={result.success}, "
        f"modified={len(result.files_modified)}, "
        f"added={len(result.files_added)}, "
        f"deleted={len(result.files_deleted)}"
    )

    return {
        "success": result.success,
        "files_modified": result.files_modified,
        "files_added": result.files_added,
        "files_deleted": result.files_deleted,
        "errors": result.errors,
        "warnings": result.warnings,
        "dry_run": dry_run,
    }


def get_apply_patch_tool():
    """Get the apply_patch tool for the agent.

    Returns:
        LangChain tool for structured patching
    """
    return apply_patch
