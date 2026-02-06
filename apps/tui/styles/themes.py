"""Theme definitions for AG3NT TUI.

Provides multiple theme options including a high-contrast theme
for accessibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional
import json

if TYPE_CHECKING:
    pass


@dataclass
class Theme:
    """Theme color definitions."""

    name: str
    display_name: str

    # Background colors
    background: str
    surface: str
    surface_light: str
    surface_dark: str

    # Text colors
    text_primary: str
    text_secondary: str
    text_muted: str

    # Accent colors
    accent_primary: str  # Main accent (indigo)
    accent_success: str  # Green
    accent_warning: str  # Yellow/Orange
    accent_error: str    # Red
    accent_info: str     # Cyan/Blue

    # Border colors
    border: str
    border_focus: str

    # Special UI colors
    cursor: str
    selection: str
    scrollbar: str
    scrollbar_hover: str

    def to_css_vars(self) -> str:
        """Generate CSS variable definitions for this theme."""
        return f"""
        $background: {self.background};
        $surface: {self.surface};
        $surface-light: {self.surface_light};
        $surface-dark: {self.surface_dark};
        $text-primary: {self.text_primary};
        $text-secondary: {self.text_secondary};
        $text-muted: {self.text_muted};
        $accent-primary: {self.accent_primary};
        $accent-success: {self.accent_success};
        $accent-warning: {self.accent_warning};
        $accent-error: {self.accent_error};
        $accent-info: {self.accent_info};
        $border: {self.border};
        $border-focus: {self.border_focus};
        $cursor: {self.cursor};
        $selection: {self.selection};
        $scrollbar: {self.scrollbar};
        $scrollbar-hover: {self.scrollbar_hover};
        """


# Default dark theme (current theme)
THEME_DARK = Theme(
    name="dark",
    display_name="Dark (Default)",
    background="#171717",
    surface="#1e1e1e",
    surface_light="#2f2f2f",
    surface_dark="#0d0d0d",
    text_primary="#ececec",
    text_secondary="#a1a1a1",
    text_muted="#6b6b6b",
    accent_primary="#6366f1",
    accent_success="#10b981",
    accent_warning="#f59e0b",
    accent_error="#ef4444",
    accent_info="#06b6d4",
    border="#3a3a3a",
    border_focus="#6366f1",
    cursor="#6366f1",
    selection="#4f46e5",
    scrollbar="#3a3a3a",
    scrollbar_hover="#6366f1",
)

# High contrast dark theme for accessibility
THEME_HIGH_CONTRAST = Theme(
    name="high-contrast",
    display_name="High Contrast",
    background="#000000",
    surface="#0a0a0a",
    surface_light="#1a1a1a",
    surface_dark="#000000",
    text_primary="#ffffff",
    text_secondary="#e5e5e5",
    text_muted="#a3a3a3",
    accent_primary="#818cf8",  # Brighter indigo
    accent_success="#34d399",  # Brighter green
    accent_warning="#fbbf24",  # Brighter yellow
    accent_error="#f87171",    # Brighter red
    accent_info="#22d3ee",     # Brighter cyan
    border="#525252",          # More visible borders
    border_focus="#a5b4fc",    # Very visible focus
    cursor="#a5b4fc",
    selection="#6366f1",
    scrollbar="#525252",
    scrollbar_hover="#a5b4fc",
)

# Light theme option
THEME_LIGHT = Theme(
    name="light",
    display_name="Light",
    background="#f5f5f5",
    surface="#ffffff",
    surface_light="#fafafa",
    surface_dark="#e5e5e5",
    text_primary="#171717",
    text_secondary="#525252",
    text_muted="#737373",
    accent_primary="#4f46e5",
    accent_success="#059669",
    accent_warning="#d97706",
    accent_error="#dc2626",
    accent_info="#0891b2",
    border="#d4d4d4",
    border_focus="#4f46e5",
    cursor="#4f46e5",
    selection="#c7d2fe",
    scrollbar="#d4d4d4",
    scrollbar_hover="#4f46e5",
)

# Midnight theme (deeper blue-tinted dark)
THEME_MIDNIGHT = Theme(
    name="midnight",
    display_name="Midnight Blue",
    background="#0f172a",
    surface="#1e293b",
    surface_light="#334155",
    surface_dark="#020617",
    text_primary="#f1f5f9",
    text_secondary="#94a3b8",
    text_muted="#64748b",
    accent_primary="#6366f1",
    accent_success="#10b981",
    accent_warning="#f59e0b",
    accent_error="#ef4444",
    accent_info="#06b6d4",
    border="#334155",
    border_focus="#6366f1",
    cursor="#6366f1",
    selection="#4f46e5",
    scrollbar="#334155",
    scrollbar_hover="#6366f1",
)

# All available themes
THEMES: dict[str, Theme] = {
    "dark": THEME_DARK,
    "high-contrast": THEME_HIGH_CONTRAST,
    "light": THEME_LIGHT,
    "midnight": THEME_MIDNIGHT,
}


class ThemeManager:
    """Manages theme selection and persistence.

    Stores user theme preference and provides theme-aware CSS generation.
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        """Initialize theme manager.

        Args:
            config_path: Path to config file. Defaults to ~/.ag3nt/tui_config.json
        """
        if config_path is None:
            config_path = Path.home() / ".ag3nt" / "tui_config.json"
        self.config_path = config_path
        self._current_theme_name: str = "dark"
        self._reduced_motion: bool = False
        self._load()

    def _load(self) -> None:
        """Load settings from config file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._current_theme_name = data.get("theme", "dark")
                    self._reduced_motion = data.get("reduced_motion", False)
            except Exception:
                pass

    def _save(self) -> None:
        """Save settings to config file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump({
                    "theme": self._current_theme_name,
                    "reduced_motion": self._reduced_motion,
                }, f, indent=2)
        except Exception:
            pass

    @property
    def current_theme(self) -> Theme:
        """Get the current theme."""
        return THEMES.get(self._current_theme_name, THEME_DARK)

    @property
    def reduced_motion(self) -> bool:
        """Get reduced motion preference."""
        return self._reduced_motion

    @reduced_motion.setter
    def reduced_motion(self, value: bool) -> None:
        """Set reduced motion preference."""
        self._reduced_motion = value
        self._save()

    def set_theme(self, theme_name: str) -> bool:
        """Set the current theme.

        Args:
            theme_name: Name of theme to set

        Returns:
            True if theme was set, False if theme not found
        """
        if theme_name in THEMES:
            self._current_theme_name = theme_name
            self._save()
            return True
        return False

    def cycle_theme(self) -> Theme:
        """Cycle to the next available theme.

        Returns:
            The new current theme
        """
        theme_names = list(THEMES.keys())
        current_idx = theme_names.index(self._current_theme_name)
        next_idx = (current_idx + 1) % len(theme_names)
        self._current_theme_name = theme_names[next_idx]
        self._save()
        return self.current_theme

    def list_themes(self) -> list[tuple[str, str]]:
        """List all available themes.

        Returns:
            List of (name, display_name) tuples
        """
        return [(name, theme.display_name) for name, theme in THEMES.items()]

    def generate_css(self) -> str:
        """Generate CSS for the current theme.

        Returns:
            CSS string with theme colors applied
        """
        theme = self.current_theme
        return f"""
        /* Theme: {theme.display_name} */

        Screen {{
            background: {theme.background};
        }}

        Header {{
            background: {theme.surface_dark};
            color: {theme.text_primary};
            border-bottom: solid {theme.border};
        }}

        HeaderTitle {{
            color: {theme.accent_success};
            text-style: bold;
        }}

        Footer {{
            background: {theme.surface_dark};
            color: {theme.text_muted};
            border-top: solid {theme.border};
        }}

        FooterKey {{
            background: transparent;
            color: {theme.text_muted};
        }}

        FooterKey .footer-key--key {{
            background: {theme.surface_light};
            color: {theme.text_secondary};
        }}

        FooterKey:hover {{
            background: {theme.surface_light};
        }}

        FooterKey:hover .footer-key--key {{
            background: {theme.accent_primary};
            color: {theme.text_primary};
        }}

        Button {{
            background: {theme.surface_light};
            color: {theme.text_primary};
            border: solid {theme.border};
        }}

        Button:hover {{
            background: {theme.surface};
            border: solid {theme.accent_primary};
        }}

        Button.-primary {{
            background: {theme.accent_primary};
            color: {theme.text_primary};
            border: none;
        }}

        Button.-success {{
            background: {theme.accent_success};
            color: {theme.text_primary};
        }}

        Button.-warning {{
            background: {theme.accent_warning};
            color: {theme.surface_dark};
        }}

        Button.-error {{
            background: {theme.accent_error};
            color: {theme.text_primary};
        }}

        DataTable > .datatable--header {{
            background: {theme.surface_light};
            color: {theme.text_secondary};
        }}

        DataTable > .datatable--cursor {{
            background: {theme.accent_primary};
            color: {theme.text_primary};
        }}

        /* Scrollbar */
        * {{
            scrollbar-background: {theme.background};
            scrollbar-color: {theme.scrollbar};
            scrollbar-color-hover: {theme.scrollbar_hover};
            scrollbar-color-active: {theme.accent_success};
        }}
        """


def get_animation_duration(base_ms: int, reduced_motion: bool) -> int:
    """Get animation duration respecting reduced motion preference.

    Args:
        base_ms: Base duration in milliseconds
        reduced_motion: Whether reduced motion is enabled

    Returns:
        Duration to use (0 if reduced motion, otherwise base)
    """
    return 0 if reduced_motion else base_ms
