"""Command history manager for AG3NT TUI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional


class HistoryManager:
    """Manages persistent command history with prefix search."""

    def __init__(
        self,
        path: Optional[Path] = None,
        max_entries: int = 500,
    ) -> None:
        """Initialize history manager.

        Args:
            path: Path to history file. Defaults to ~/.ag3nt/tui_history.jsonl
            max_entries: Maximum entries to keep
        """
        if path is None:
            path = Path.home() / ".ag3nt" / "tui_history.jsonl"
        self.path = path
        self.max_entries = max_entries
        self._entries: list[str] = []
        self._position: int = 0
        self._current_input: str = ""  # Stores current input when navigating
        self._load()

    def _load(self) -> None:
        """Load history from file."""
        self._entries = []
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                data = json.loads(line)
                                if isinstance(data, dict) and "text" in data:
                                    self._entries.append(data["text"])
                            except json.JSONDecodeError:
                                continue
                # Keep only recent entries
                self._entries = self._entries[-self.max_entries :]
            except Exception:
                self._entries = []
        self._position = len(self._entries)

    def _ensure_dir(self) -> None:
        """Ensure the history directory exists."""
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, text: str) -> None:
        """Add entry to history.

        Args:
            text: Command text to add
        """
        text = text.strip()
        if not text:
            return

        # Don't add duplicates of the last entry
        if self._entries and self._entries[-1] == text:
            self._position = len(self._entries)
            return

        self._entries.append(text)

        # Persist to file
        self._ensure_dir()
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"text": text}) + "\n")
        except Exception:
            pass  # Don't fail on write errors

        # Compact if needed
        if len(self._entries) > self.max_entries * 2:
            self._compact()

        self._position = len(self._entries)
        self._current_input = ""

    def previous(self, current_input: str = "") -> Optional[str]:
        """Get previous entry matching prefix.

        Args:
            current_input: Current input to use as prefix filter

        Returns:
            Previous history entry or None if at beginning
        """
        # Store current input when starting navigation
        if self._position == len(self._entries):
            self._current_input = current_input

        # Search backwards for matching entry
        for i in range(self._position - 1, -1, -1):
            entry = self._entries[i]
            if not self._current_input or entry.startswith(self._current_input):
                self._position = i
                return entry

        return None

    def next(self, current_input: str = "") -> Optional[str]:
        """Get next entry matching prefix.

        Args:
            current_input: Current input to use as prefix filter

        Returns:
            Next history entry, original input if at end, or None
        """
        # Search forwards for matching entry
        for i in range(self._position + 1, len(self._entries)):
            entry = self._entries[i]
            if not self._current_input or entry.startswith(self._current_input):
                self._position = i
                return entry

        # Return to original input
        self._position = len(self._entries)
        return self._current_input if self._current_input else None

    def reset_position(self) -> None:
        """Reset navigation position to end."""
        self._position = len(self._entries)
        self._current_input = ""

    def search(self, query: str, limit: int = 20) -> list[str]:
        """Search history for entries containing query.

        Args:
            query: Search string
            limit: Maximum results to return

        Returns:
            List of matching entries (newest first)
        """
        query_lower = query.lower()
        results = []
        for entry in reversed(self._entries):
            if query_lower in entry.lower():
                results.append(entry)
                if len(results) >= limit:
                    break
        return results

    def _compact(self) -> None:
        """Rewrite history file with recent entries only."""
        self._entries = self._entries[-self.max_entries :]
        self._ensure_dir()
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                for entry in self._entries:
                    f.write(json.dumps({"text": entry}) + "\n")
        except Exception:
            pass  # Don't fail on write errors
        self._position = len(self._entries)

    def clear(self) -> None:
        """Clear all history."""
        self._entries = []
        self._position = 0
        self._current_input = ""
        try:
            if self.path.exists():
                self.path.unlink()
        except Exception:
            pass

    @property
    def entries(self) -> list[str]:
        """Get all history entries."""
        return self._entries.copy()

    def __len__(self) -> int:
        """Get number of history entries."""
        return len(self._entries)
