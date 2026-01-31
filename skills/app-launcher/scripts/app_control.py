#!/usr/bin/env python3
"""
Application Control Script for AG3NT.

Provides platform-specific application management:
- Launch applications
- Open URLs in browser
- List running applications
- Focus/switch to applications

Usage:
    python app_control.py launch <app_name>
    python app_control.py url <url>
    python app_control.py list [--all]
    python app_control.py focus <app_name>
"""

import argparse
import platform
import subprocess
import sys
import webbrowser
from typing import Any

# Try to import psutil for process listing
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def get_platform() -> str:
    """Get the current platform: 'windows', 'darwin', or 'linux'."""
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    elif system == "darwin":
        return "darwin"
    else:
        return "linux"


# Common application mappings for each platform
APP_ALIASES = {
    "windows": {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "explorer": "explorer.exe",
        "cmd": "cmd.exe",
        "powershell": "powershell.exe",
        "terminal": "wt.exe",  # Windows Terminal
        "code": "code",
        "vscode": "code",
        "chrome": "chrome",
        "firefox": "firefox",
        "edge": "msedge",
    },
    "darwin": {
        "finder": "Finder",
        "safari": "Safari",
        "terminal": "Terminal",
        "code": "Visual Studio Code",
        "vscode": "Visual Studio Code",
        "chrome": "Google Chrome",
        "firefox": "Firefox",
        "notes": "Notes",
        "calculator": "Calculator",
        "calc": "Calculator",
    },
    "linux": {
        "terminal": "gnome-terminal",
        "files": "nautilus",
        "explorer": "nautilus",
        "code": "code",
        "vscode": "code",
        "chrome": "google-chrome",
        "firefox": "firefox",
        "calculator": "gnome-calculator",
        "calc": "gnome-calculator",
    },
}


def resolve_app_name(app_name: str) -> str:
    """Resolve common app aliases to actual executable names."""
    plat = get_platform()
    aliases = APP_ALIASES.get(plat, {})
    return aliases.get(app_name.lower(), app_name)


def launch_app(app_name: str) -> dict[str, Any]:
    """Launch an application by name."""
    resolved_name = resolve_app_name(app_name)
    plat = get_platform()

    try:
        if plat == "windows":
            # Use 'start' command for Windows
            subprocess.Popen(
                f'start "" "{resolved_name}"',
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif plat == "darwin":
            # Use 'open -a' for macOS
            subprocess.Popen(
                ["open", "-a", resolved_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:  # Linux
            subprocess.Popen(
                [resolved_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        return {
            "success": True,
            "message": f"Launched: {app_name}",
            "resolved_name": resolved_name,
        }
    except FileNotFoundError:
        return {
            "success": False,
            "error": f"Application not found: {app_name}",
            "suggestion": "Check the application name or provide the full path",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def open_url(url: str) -> dict[str, Any]:
    """Open a URL in the default browser."""
    # Ensure URL has a scheme
    if not url.startswith(("http://", "https://", "file://")):
        url = "https://" + url

    try:
        webbrowser.open(url)
        return {"success": True, "message": f"Opened URL: {url}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_apps(include_all: bool = False) -> dict[str, Any]:
    """List running applications."""
    if not HAS_PSUTIL:
        return {
            "success": False,
            "error": "psutil is required for listing applications",
            "suggestion": "Install with: pip install psutil",
        }

    try:
        apps = []
        seen_names = set()

        for proc in psutil.process_iter(["pid", "name", "status"]):
            try:
                info = proc.info
                name = info["name"]

                # Skip if we've seen this app already (dedup by name)
                if name in seen_names:
                    continue

                # If not including all, filter to likely user applications
                if not include_all:
                    # Skip common system processes
                    lower_name = name.lower()
                    if any(
                        x in lower_name
                        for x in [
                            "system",
                            "svchost",
                            "runtime",
                            "csrss",
                            "lsass",
                            "services",
                            "smss",
                            "wininit",
                            "dwm",
                            "conhost",
                        ]
                    ):
                        continue

                seen_names.add(name)
                apps.append(
                    {
                        "name": name,
                        "pid": info["pid"],
                        "status": info["status"],
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Sort by name
        apps.sort(key=lambda x: x["name"].lower())

        return {
            "success": True,
            "count": len(apps),
            "apps": apps,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def focus_app(app_name: str) -> dict[str, Any]:
    """Bring an application window to the foreground."""
    plat = get_platform()
    resolved_name = resolve_app_name(app_name)

    try:
        if plat == "darwin":
            # Use AppleScript on macOS
            script = f'tell application "{resolved_name}" to activate'
            subprocess.run(["osascript", "-e", script], check=True)
            return {"success": True, "message": f"Focused: {app_name}"}

        elif plat == "windows":
            # Windows has limited focus support - try to find and activate window
            # This requires the app to be running
            if HAS_PSUTIL:
                for proc in psutil.process_iter(["name"]):
                    try:
                        if resolved_name.lower() in proc.info["name"].lower():
                            # Found the process, try to bring it forward
                            # Note: This is limited - Windows restricts SetForegroundWindow
                            return {
                                "success": True,
                                "message": f"Found process: {app_name}",
                                "note": "Windows may not allow background focus changes",
                            }
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            return {
                "success": False,
                "error": f"Could not find running application: {app_name}",
            }

        else:  # Linux
            # Try wmctrl if available
            try:
                subprocess.run(
                    ["wmctrl", "-a", resolved_name],
                    check=True,
                    capture_output=True,
                )
                return {"success": True, "message": f"Focused: {app_name}"}
            except FileNotFoundError:
                return {
                    "success": False,
                    "error": "wmctrl not found",
                    "suggestion": "Install wmctrl: sudo apt install wmctrl",
                }
            except subprocess.CalledProcessError:
                return {
                    "success": False,
                    "error": f"Could not find window: {app_name}",
                }

    except Exception as e:
        return {"success": False, "error": str(e)}


def format_result(result: dict[str, Any]) -> str:
    """Format result for human-readable output."""
    if not result.get("success"):
        msg = f"❌ Error: {result.get('error', 'Unknown error')}"
        if result.get("suggestion"):
            msg += f"\n   💡 {result['suggestion']}"
        return msg

    if "apps" in result:
        # List of applications
        lines = [f"📱 Running Applications ({result['count']} found)"]
        lines.append("=" * 40)
        for app in result["apps"][:30]:  # Limit display
            status = "🟢" if app["status"] == "running" else "🟡"
            lines.append(f"  {status} {app['name']} (PID: {app['pid']})")
        if result["count"] > 30:
            lines.append(f"  ... and {result['count'] - 30} more")
        return "\n".join(lines)

    # Generic success message
    return f"✅ {result.get('message', 'Operation completed')}"


def main():
    parser = argparse.ArgumentParser(description="Application control for AG3NT")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Launch command
    launch_parser = subparsers.add_parser("launch", help="Launch an application")
    launch_parser.add_argument("app_name", help="Name of the application to launch")
    launch_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # URL command
    url_parser = subparsers.add_parser("url", help="Open a URL in browser")
    url_parser.add_argument("url", help="URL to open")
    url_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # List command
    list_parser = subparsers.add_parser("list", help="List running applications")
    list_parser.add_argument(
        "--all", "-a", action="store_true", help="Include system processes"
    )
    list_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Focus command
    focus_parser = subparsers.add_parser("focus", help="Focus an application")
    focus_parser.add_argument("app_name", help="Name of the application to focus")
    focus_parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Execute command
    if args.command == "launch":
        result = launch_app(args.app_name)
    elif args.command == "url":
        result = open_url(args.url)
    elif args.command == "list":
        result = list_apps(args.all)
    elif args.command == "focus":
        result = focus_app(args.app_name)
    else:
        print(f"Unknown command: {args.command}")
        sys.exit(1)

    # Output
    if args.json:
        import json

        print(json.dumps(result, indent=2))
    else:
        print(format_result(result))

    # Exit with error code if failed
    if not result.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()
