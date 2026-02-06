"""Welcome banner widget for AG3NT TUI."""

from __future__ import annotations

from textual.widgets import Static

from ..config import AP3X_ASCII, VERSION


class WelcomeBanner(Static):
    """Welcome banner with AP3X ASCII art - Sleek dark theme."""

    DEFAULT_CSS = """
    WelcomeBanner {
        height: auto;
        padding: 1 2;
        margin: 1 0;
        text-align: center;
    }
    """

    def __init__(self, gateway_url: str = "", **kwargs) -> None:
        """Initialize the welcome banner.

        Args:
            gateway_url: Gateway URL to display
        """
        banner_text = f"{AP3X_ASCII}\n"
        banner_text += f"[#a1a1a1]v{VERSION}[/#a1a1a1]"
        if gateway_url:
            banner_text += f"  [#6b6b6b]•[/#6b6b6b]  [#6b6b6b]{gateway_url}[/#6b6b6b]"
        banner_text += "\n\n"
        banner_text += "[#10b981]What would you like to build today?[/#10b981]\n\n"
        banner_text += "[#6b6b6b]╭────────────────────────────────────────────────────────────────────────╮[/#6b6b6b]\n"
        banner_text += "[#6b6b6b]│[/#6b6b6b]  [#a1a1a1]Enter[/#a1a1a1] send  [#6b6b6b]•[/#6b6b6b]  [#a1a1a1]Ctrl+P[/#a1a1a1] commands  [#6b6b6b]•[/#6b6b6b]  [#a1a1a1]Ctrl+H[/#a1a1a1] sessions  [#6b6b6b]•[/#6b6b6b]  [#a1a1a1]F1[/#a1a1a1] help  [#6b6b6b]│[/#6b6b6b]\n"
        banner_text += "[#6b6b6b]│[/#6b6b6b]  [#a1a1a1]Ctrl+G[/#a1a1a1] [#ef4444]GO[/#ef4444] mode  [#6b6b6b]•[/#6b6b6b]  [#a1a1a1]Ctrl+T[/#a1a1a1] auto-approve  [#6b6b6b]•[/#6b6b6b]  [#ec4899]![/#ec4899] bash  [#6b6b6b]•[/#6b6b6b]  [#8b5cf6]/[/#8b5cf6] commands   [#6b6b6b]│[/#6b6b6b]\n"
        banner_text += "[#6b6b6b]╰────────────────────────────────────────────────────────────────────────╯[/#6b6b6b]"
        super().__init__(banner_text, **kwargs)
