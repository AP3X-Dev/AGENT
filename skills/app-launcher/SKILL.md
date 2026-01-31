---
name: app-launcher
description: Launch applications, open URLs in browser, and list running processes. Requires approval for launching applications.
version: "1.0.0"
tags:
  - applications
  - desktop
  - device
  - browser
triggers:
  - "open app"
  - "launch application"
  - "start program"
  - "open browser"
  - "open url"
  - "running apps"
  - "list processes"
entrypoints:
  launch:
    script: scripts/app_control.py launch
    description: Launch an application by name
  url:
    script: scripts/app_control.py url
    description: Open a URL in the default browser
  list:
    script: scripts/app_control.py list
    description: List running applications
  focus:
    script: scripts/app_control.py focus
    description: Bring an application to the foreground
required_permissions:
  - execute
  - application_control
license: MIT
compatibility: AG3NT 1.x
metadata:
  author: ag3nt-team
  category: device-integration
  node_capability: application_control
---

# App Launcher Skill

This skill provides application control on the local system. It can launch applications, open URLs, and manage running processes.

## ⚠️ Security Note

**Launching applications requires user approval.** The agent will pause and ask for confirmation before:
- Starting any application
- Opening URLs (to prevent phishing)
- Focusing/switching to applications

## When to Use

- User asks to "open" or "launch" an application
- User wants to open a URL in their browser
- User asks what applications are running
- User wants to switch to a specific application

## Available Commands

### Launch Application
Launch an application by name.

```bash
python scripts/app_control.py launch "notepad"
python scripts/app_control.py launch "Visual Studio Code"
python scripts/app_control.py launch "chrome"
```

**Common app names:**
- Windows: notepad, calc, explorer, cmd, powershell, code, chrome, firefox
- macOS: Safari, Finder, Terminal, "Visual Studio Code", Notes
- Linux: firefox, nautilus, gnome-terminal, code

### Open URL
Open a URL in the default browser.

```bash
python scripts/app_control.py url "https://example.com"
python scripts/app_control.py url "https://github.com"
```

### List Running Applications
Show currently running applications (not all processes).

```bash
python scripts/app_control.py list
python scripts/app_control.py list --all  # Include background processes
```

### Focus Application
Bring an application window to the foreground.

```bash
python scripts/app_control.py focus "notepad"
python scripts/app_control.py focus "chrome"
```

## Platform Support

| Operation | Windows | macOS | Linux |
|-----------|---------|-------|-------|
| Launch | ✅ `start` | ✅ `open -a` | ✅ Various |
| Open URL | ✅ `webbrowser` | ✅ `webbrowser` | ✅ `webbrowser` |
| List apps | ✅ `tasklist` | ✅ `ps` | ✅ `ps` |
| Focus | ⚠️ Limited | ✅ AppleScript | ⚠️ Limited |

## Notes

- App names are case-insensitive on Windows
- On macOS, use the full app name (e.g., "Visual Studio Code")
- Focus functionality may be limited depending on OS security settings
- Some apps may take a moment to start

