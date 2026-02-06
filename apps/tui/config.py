"""Configuration and constants for AG3NT TUI."""

VERSION = "0.1.0"

# Default ports to probe in order
DEFAULT_PORTS = [18789, 18790, 18791, 18792, 18793]

# Color Palette - Sleek dark theme inspired by modern AI interfaces
COLORS = {
    "bg_dark": "#0d0d0d",        # Deep black background
    "bg_main": "#171717",        # Main background (like ChatGPT)
    "bg_surface": "#1e1e1e",     # Elevated surface
    "bg_input": "#2f2f2f",       # Input field background
    "bg_hover": "#3a3a3a",       # Hover state
    "border": "#3a3a3a",         # Subtle borders
    "border_focus": "#6366f1",   # Focus border (indigo)
    "text_primary": "#ececec",   # Primary text
    "text_secondary": "#a1a1a1", # Secondary/muted text
    "text_dim": "#6b6b6b",       # Dimmed text
    "accent": "#10b981",         # Primary accent (emerald green)
    "accent_alt": "#6366f1",     # Secondary accent (indigo)
    "error": "#ef4444",          # Error red
    "warning": "#f59e0b",        # Warning amber
    "success": "#10b981",        # Success green
    "bash": "#ec4899",           # Bash mode (pink)
    "command": "#8b5cf6",        # Command mode (purple)
}

# AP3X ASCII Art Banner - Clean, no box (X in red!)
AP3X_ASCII = """
  [bold #ececec]█████╗  ██████╗  ██████╗[/bold #ececec] [bold #ef4444]██╗  ██╗[/bold #ef4444]
 [bold #ececec]██╔══██╗ ██╔══██╗ ╚════██╗[/bold #ececec][bold #ef4444]╚██╗██╔╝[/bold #ef4444]
 [bold #ececec]███████║ ██████╔╝  █████╔╝[/bold #ececec] [bold #ef4444]╚███╔╝[/bold #ef4444]
 [bold #ececec]██╔══██║ ██╔═══╝   ╚═══██╗[/bold #ececec] [bold #ef4444]██╔██╗[/bold #ef4444]
 [bold #ececec]██║  ██║ ██║      ██████╔╝[/bold #ececec][bold #ef4444]██╔╝ ██╗[/bold #ef4444]
 [bold #ececec]╚═╝  ╚═╝ ╚═╝      ╚═════╝[/bold #ececec] [bold #ef4444]╚═╝  ╚═╝[/bold #ef4444]
"""
