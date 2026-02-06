"""Help screen for AG3NT TUI."""

from __future__ import annotations

from rich.markdown import Markdown
from textual import on
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class HelpScreen(ModalScreen):
    """Help modal screen."""

    BINDINGS = [("escape", "dismiss", "Close"), ("f1", "dismiss", "Close")]

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
        background: #0d0d0d 90%;
    }

    #help-dialog {
        width: 70;
        height: auto;
        max-height: 80%;
        background: #1e1e1e;
        border: solid #3a3a3a;
        padding: 2;
    }

    #help-content {
        height: auto;
        max-height: 60;
        overflow-y: auto;
        color: #ececec;
    }

    #help-close {
        margin-top: 2;
        width: 100%;
        background: #6366f1;
        color: #ececec;
        border: none;
    }

    #help-close:hover {
        background: #4f46e5;
    }
    """

    def compose(self) -> ComposeResult:
        help_text = """
## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| **Enter** | Send message |
| **Ctrl+J / Shift+Enter** | New line in input |
| **Ctrl+L** | Clear chat |
| **Ctrl+P** | Command palette |
| **Ctrl+H** | Browse session history |
| **Ctrl+T** | Toggle auto-approve |
| **Ctrl+G** | Toggle Go mode ⚡ |
| **Ctrl+C** | Quit (double press) |
| **Escape** | Cancel / Close dialogs |
| **F1** | Show this help |
| **Up/Down** | History navigation |

## Commands

| Command | Description |
|---------|-------------|
| `/help` | Show help |
| `/clear` | Clear chat and start new session |
| `/sessions` | Browse and resume past sessions |
| `/quit` | Exit the TUI |
| `/status` | Show connection status |
| `/nodes` | Show connected nodes |
| `/tokens` | Show token usage |
| `/auto` | Toggle auto-approve mode |
| `/go` | Toggle Go mode ⚡ |

## Approval Modes

- **Manual** (default) - Prompts for approval on sensitive tools
- **Auto** - Automatically approves sensitive tools
- **Go** ⚡ - Bypasses ALL approvals for maximum speed

## Bash Commands

| Prefix | Description |
|--------|-------------|
| `!command` | Execute bash command directly |

## Tool Display

Tool calls are shown inline with status indicators:
- **⠋ Running** - Tool is executing
- **✓ Complete** - Tool finished successfully
- **✗ Error** - Tool encountered an error

## Features

- **Connection Status** - Green dot when connected, red when offline
- **Auto-Retry** - Retry button appears on failed requests
- **Draft Saving** - Your message is saved if an error occurs

## Tips

- The agent may take a while to respond to complex queries
- Code blocks in responses have syntax highlighting
- Response time is shown in the status bar
- Press Escape to cancel a running request
- Enable auto-approve with Ctrl+T for faster workflows
- Use Up/Down arrows to navigate command history
- Sessions are persisted - resume with Ctrl+H or /sessions
- Use Command Palette (Ctrl+P) to access all features
"""
        yield Container(
            Static(Markdown(help_text), id="help-content"),
            Button("Close", id="help-close", variant="primary"),
            id="help-dialog",
        )

    @on(Button.Pressed, "#help-close")
    def close_help(self) -> None:
        self.dismiss()
