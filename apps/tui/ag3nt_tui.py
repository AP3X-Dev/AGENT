#!/usr/bin/env python3
"""AG3NT TUI - A high-quality terminal interface for AG3NT.

This file is a compatibility shim that redirects to the new modular TUI package.

Usage:
    python ag3nt_tui.py
    python -m apps.tui
"""

import sys
from pathlib import Path

# Add parent directory to path so we can import the tui package
_this_dir = Path(__file__).parent
_apps_dir = _this_dir.parent
if str(_apps_dir) not in sys.path:
    sys.path.insert(0, str(_apps_dir))

# Import and run the new modular app
from tui.app import main

if __name__ == "__main__":
    main()
