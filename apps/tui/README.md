# AG3NT TUI

A sleek, modern terminal user interface for AG3NT.

## Features

- 🎨 **Sleek Dark Theme** - Sophisticated design inspired by modern AI interfaces
- 💬 **Rich Chat Interface** - Markdown rendering, syntax highlighting
- ⌨️ **Keyboard-First** - Full keyboard navigation and shortcuts
- 🔧 **Bash Mode** - Execute shell commands directly with `!command`
- 📝 **Slash Commands** - Quick actions with `/help`, `/clear`, etc.
- 🔄 **Auto-Session** - Automatic session management with DM pairing

## Installation

```bash
cd apps/tui
pip install -r requirements.txt
```

### Requirements

- Python 3.10+
- textual >= 0.50.0
- httpx >= 0.27.0
- rich >= 13.0.0
- python-dotenv >= 1.0.0

## Usage

```bash
# Run directly
python ag3nt_tui.py

# Or as a module
python -m ag3nt_tui
```

**Prerequisites**: Gateway and Agent Worker must be running:
```bash
# Terminal 1: Start Gateway
cd apps/gateway && pnpm dev

# Terminal 2: Start Agent Worker
cd apps/agent && python -m ag3nt_agent.worker

# Terminal 3: Start TUI
cd apps/tui && python ag3nt_tui.py
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AG3NT_GATEWAY_URL` | Gateway API URL | `http://127.0.0.1:18789` |

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| **Enter** | Send message |
| **Ctrl+J** / **Shift+Enter** | Insert new line |
| **Ctrl+L** | Clear chat and start new session |
| **Ctrl+C** | Quit (double press) |
| **Escape** | Interrupt / Close dialogs |
| **F1** | Show help modal |
| **Up/Down** | Navigate command history |

## Commands

### Slash Commands

| Command | Description |
|---------|-------------|
| `/help` | Show help modal |
| `/clear` | Clear chat and start new session |
| `/status` | Show session information |
| `/nodes` | Show connected nodes |
| `/tokens` | Show token usage (placeholder) |
| `/quit` | Exit the TUI |

### Bash Mode

Prefix any command with `!` to execute it directly in the shell:

```
!dir                    # List directory (Windows)
!ls -la                 # List directory (Unix)
!git status             # Check git status
!python --version       # Check Python version
```

Bash output is displayed in a styled panel with the command and result.

## Interface Overview

```
┌─────────────────────────────────────────────────────────────┐
│  AP3X - Personal AI Assistant                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  █████╗  ██████╗  ██████╗ ██╗  ██╗                         │
│ ██╔══██╗ ██╔══██╗ ╚════██╗╚██╗██╔╝                         │
│ ███████║ ██████╔╝  █████╔╝ ╚███╔╝                          │
│ ██╔══██║ ██╔═══╝   ╚═══██╗ ██╔██╗                          │
│ ██║  ██║ ██║      ██████╔╝██╔╝ ██╗                         │
│ ╚═╝  ╚═╝ ╚═╝      ╚═════╝ ╚═╝  ╚═╝                         │
│                                                             │
│  → Connected to Gateway!                                    │
│  → Session approved! Ready to chat.                         │
│                                                             │
│  ┌─ You ─────────────────────────────────────────────────┐ │
│  │ Hello, what can you help me with?                     │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌─ AP3X ────────────────────────────────────────────────┐ │
│  │ I can help you with many things! Here are some...     │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  READY │ Session: abc123 │ 2 messages │ 1.2s               │
├─────────────────────────────────────────────────────────────┤
│  > Type a message...                                        │
├─────────────────────────────────────────────────────────────┤
│  Ctrl+C Quit │ Ctrl+L Clear │ F1 Help                       │
└─────────────────────────────────────────────────────────────┘
```

## Message Types

| Type | Description | Style |
|------|-------------|-------|
| **User** | Your messages | Indigo left border |
| **Assistant** | AP3X responses | Emerald left border |
| **System** | Status messages | Arrow prefix (→) |
| **Error** | Error messages | Red left border |
| **Bash Output** | Shell command results | Pink left border |

## Session Management

The TUI automatically:
1. Creates a new session on startup
2. Handles DM pairing (auto-approves for local connections)
3. Maintains session across messages
4. Clears session on `/clear` or Ctrl+L

## Troubleshooting

### "Connection refused" error
- Ensure Gateway is running on port 18789
- Check `AG3NT_GATEWAY_URL` environment variable

### "Session requires approval" message
- The TUI auto-approves local sessions
- If stuck, restart the TUI

### Slow responses
- Complex agent tasks can take up to 5 minutes
- The loading indicator shows elapsed time
- Press Escape to cancel a pending request

### Input not visible
- Ensure terminal supports 256 colors
- Try a different terminal emulator

## Development

The TUI is built with:
- **Textual** - Modern TUI framework
- **Rich** - Terminal formatting and markdown
- **httpx** - Async HTTP client

### File Structure

```
apps/tui/
├── __init__.py
├── __main__.py       # Module entry point
├── ag3nt_tui.py      # Main application (~1400 lines)
├── requirements.txt  # Python dependencies
└── README.md         # This file
```

