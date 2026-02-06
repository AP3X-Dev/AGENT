"""AG3NT TUI - Terminal User Interface for AG3NT.

A high-quality terminal interface for AG3NT with streaming support,
tool visualization, and real-time updates.
"""

from .app import AG3NTApp, main
from .config import VERSION

__version__ = VERSION
__all__ = ["AG3NTApp", "main", "VERSION"]
