"""Diff rendering widget for AG3NT TUI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.widgets import Static

if TYPE_CHECKING:
    from rich.console import RenderableType


class DiffDisplay(Static):
    """Display unified diff with syntax highlighting.

    Renders diffs with color-coded additions and deletions,
    similar to GitHub's diff view.
    """

    DEFAULT_CSS = """
    DiffDisplay {
        padding: 1;
        background: #1a1a1a;
        border: solid #3a3a3a;
        margin: 1 0;
    }

    DiffDisplay .diff-header {
        color: #a1a1a1;
        text-style: bold;
    }

    DiffDisplay .diff-stats {
        margin-bottom: 1;
    }
    """

    def __init__(
        self,
        diff_text: str,
        file_path: str = "",
        show_stats: bool = True,
        max_lines: int = 50,
        **kwargs,
    ) -> None:
        """Initialize diff display.

        Args:
            diff_text: The unified diff text to display
            file_path: Optional file path for header
            show_stats: Whether to show +/- stats
            max_lines: Maximum lines to display before truncation
        """
        super().__init__(**kwargs)
        self.diff_text = diff_text
        self.file_path = file_path
        self.show_stats = show_stats
        self.max_lines = max_lines

    def on_mount(self) -> None:
        """Render the diff on mount."""
        self.update(self._render_diff())

    def _render_diff(self) -> RenderableType:
        """Render diff with colors."""
        text = Text()

        lines = self.diff_text.split("\n")

        # Count additions and deletions
        additions = 0
        deletions = 0
        for line in lines:
            if line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1

        # Stats line
        if self.show_stats:
            if self.file_path:
                text.append(f"{self.file_path}\n", style="bold #a1a1a1")
            text.append(f"+{additions} ", style="bold #10b981")
            text.append(f"-{deletions}", style="bold #ef4444")
            text.append("\n\n")

        # Render diff lines
        displayed_lines = 0
        truncated = False

        for line in lines:
            if displayed_lines >= self.max_lines:
                truncated = True
                break

            if line.startswith("+++") or line.startswith("---"):
                # File headers
                text.append(line + "\n", style="bold #6b7280")
            elif line.startswith("@@"):
                # Hunk headers
                text.append(line + "\n", style="#6366f1")
            elif line.startswith("+"):
                # Additions
                text.append("│", style="bold #10b981")
                text.append(line[1:] + "\n", style="on #064e3b #d1fae5")
            elif line.startswith("-"):
                # Deletions
                text.append("│", style="bold #ef4444")
                text.append(line[1:] + "\n", style="on #7f1d1d #fecaca")
            elif line.startswith(" "):
                # Context lines
                text.append("│", style="#4b5563")
                text.append(line[1:] + "\n", style="#9ca3af")
            elif line.strip():
                # Other lines (like "\ No newline at end of file")
                text.append(line + "\n", style="#6b7280 italic")

            displayed_lines += 1

        if truncated:
            remaining = len(lines) - self.max_lines
            text.append(
                f"\n[dim]... {remaining} more lines (expand to see all)[/dim]\n"
            )

        return text

    def set_diff(self, diff_text: str, file_path: str = "") -> None:
        """Update the diff content.

        Args:
            diff_text: New diff text
            file_path: Optional new file path
        """
        self.diff_text = diff_text
        if file_path:
            self.file_path = file_path
        self.update(self._render_diff())


class InlineDiff(Static):
    """Display inline diff showing old vs new content side by side."""

    DEFAULT_CSS = """
    InlineDiff {
        padding: 1;
        background: #1a1a1a;
        border: solid #3a3a3a;
        margin: 1 0;
    }
    """

    def __init__(
        self,
        old_content: str,
        new_content: str,
        file_path: str = "",
        context_lines: int = 3,
        **kwargs,
    ) -> None:
        """Initialize inline diff.

        Args:
            old_content: Original content
            new_content: New content
            file_path: Optional file path for header
            context_lines: Number of context lines around changes
        """
        super().__init__(**kwargs)
        self.old_content = old_content
        self.new_content = new_content
        self.file_path = file_path
        self.context_lines = context_lines

    def on_mount(self) -> None:
        """Render the diff on mount."""
        self.update(self._render_inline_diff())

    def _render_inline_diff(self) -> RenderableType:
        """Render inline diff with highlighted changes."""
        text = Text()

        if self.file_path:
            text.append(f"📄 {self.file_path}\n\n", style="bold #a1a1a1")

        old_lines = self.old_content.split("\n")
        new_lines = self.new_content.split("\n")

        # Simple line-by-line comparison
        max_lines = max(len(old_lines), len(new_lines))

        for i in range(min(max_lines, 20)):  # Limit display
            old_line = old_lines[i] if i < len(old_lines) else ""
            new_line = new_lines[i] if i < len(new_lines) else ""

            if old_line != new_line:
                if old_line:
                    text.append(f"{i+1:4} ", style="#6b7280")
                    text.append("- ", style="bold #ef4444")
                    text.append(old_line + "\n", style="on #7f1d1d #fecaca")
                if new_line:
                    text.append(f"{i+1:4} ", style="#6b7280")
                    text.append("+ ", style="bold #10b981")
                    text.append(new_line + "\n", style="on #064e3b #d1fae5")
            else:
                text.append(f"{i+1:4} ", style="#6b7280")
                text.append("  ", style="#4b5563")
                text.append(old_line + "\n", style="#9ca3af")

        if max_lines > 20:
            text.append(f"\n[dim]... {max_lines - 20} more lines[/dim]\n")

        return text


class EditPreview(Static):
    """Preview widget for file edit operations.

    Shows the target file path and the changes being made.
    """

    DEFAULT_CSS = """
    EditPreview {
        padding: 1;
        background: #1e1e1e;
        border: solid #3a3a3a;
        margin: 1 0;
    }

    EditPreview .file-path {
        color: #10b981;
        text-style: bold;
        margin-bottom: 1;
    }

    EditPreview .change-type {
        color: #f59e0b;
        text-style: italic;
    }
    """

    def __init__(
        self,
        file_path: str,
        old_string: str = "",
        new_string: str = "",
        operation: str = "edit",
        **kwargs,
    ) -> None:
        """Initialize edit preview.

        Args:
            file_path: Path to the file being edited
            old_string: Content being replaced (for edit)
            new_string: New content
            operation: Type of operation (edit, write, delete)
        """
        super().__init__(**kwargs)
        self.file_path = file_path
        self.old_string = old_string
        self.new_string = new_string
        self.operation = operation

    def on_mount(self) -> None:
        """Render the preview on mount."""
        self.update(self._render_preview())

    def _render_preview(self) -> RenderableType:
        """Render edit preview."""
        text = Text()

        # File path
        text.append("📄 ", style="#10b981")
        text.append(self.file_path + "\n", style="bold #10b981")

        # Operation type
        op_colors = {
            "edit": "#f59e0b",
            "write": "#10b981",
            "delete": "#ef4444",
            "create": "#6366f1",
        }
        op_icons = {
            "edit": "✏️",
            "write": "💾",
            "delete": "🗑️",
            "create": "📝",
        }
        color = op_colors.get(self.operation, "#a1a1a1")
        icon = op_icons.get(self.operation, "📄")
        text.append(f"{icon} {self.operation.upper()}\n\n", style=f"bold {color}")

        if self.operation == "edit" and self.old_string:
            # Show what's being replaced
            text.append("Finding:\n", style="bold #6b7280")
            old_preview = self.old_string[:200]
            if len(self.old_string) > 200:
                old_preview += "..."
            text.append(old_preview + "\n\n", style="on #7f1d1d #fecaca")

        if self.new_string:
            label = "Replacing with:" if self.operation == "edit" else "Content:"
            text.append(f"{label}\n", style="bold #6b7280")
            new_preview = self.new_string[:200]
            if len(self.new_string) > 200:
                new_preview += "..."
            text.append(new_preview + "\n", style="on #064e3b #d1fae5")

        return text
