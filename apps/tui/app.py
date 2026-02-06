"""AG3NT TUI - Main Application.

A high-quality terminal interface for AG3NT with streaming support,
tool visualization, and real-time updates.
"""

from __future__ import annotations

import asyncio
import platform
import subprocess
import time
import uuid
import webbrowser
from typing import Optional

import httpx
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, ScrollableContainer
from textual.css.query import NoMatches
from textual.widgets import Footer, Header

from .config import VERSION
from .gateway import GatewayClient, discover_gateway_url
from .screens import CommandPalette, HelpScreen, SessionBrowser
from .utils import SessionManager, SessionInfo, HistoryManager
from .widgets import (
    AssistantMessage,
    BashOutputMessage,
    ChatInput,
    ChatTextArea,
    ContextualHints,
    DraftManager,
    ErrorMessage,
    LoadingWidget,
    RetryBanner,
    StatusBar,
    SystemMessage,
    UserMessage,
    WelcomeBanner,
    ToolCallDisplay,
    create_tool_display,
    ApprovalRequest,
    requires_approval,
)


# Sleek dark theme CSS
APP_CSS = """
/* ═══════════════════════════════════════════════════════════════════════════
   SLEEK DARK THEME - Sophisticated, minimal, modern
   ═══════════════════════════════════════════════════════════════════════════ */

Screen {
    background: #171717;
    layout: grid;
    grid-size: 1;
    grid-rows: 1fr auto auto auto;
}

/* Header styling */
Header {
    background: #0d0d0d;
    color: #ececec;
    border-bottom: solid #3a3a3a;
}

HeaderTitle {
    color: #10b981;
    text-style: bold;
}

/* Main chat container */
#chat-container {
    margin: 0;
    padding: 1 0;
    scrollbar-gutter: stable;
    background: #171717;
    scrollbar-background: #171717;
    scrollbar-color: #3a3a3a;
    scrollbar-color-hover: #6366f1;
    scrollbar-color-active: #10b981;
}

#welcome-banner {
    text-align: center;
    margin: 2 0;
}

/* Loading container */
#loading-container {
    height: auto;
    margin: 0;
    padding: 0;
}

#loading-container.hidden {
    display: none;
}

/* Input wrapper */
#input-wrapper {
    height: auto;
    margin: 0;
    padding: 0;
    background: #171717;
}

/* Footer styling */
Footer {
    background: #0d0d0d;
    color: #6b6b6b;
    border-top: solid #3a3a3a;
}

FooterKey {
    background: transparent;
    color: #6b6b6b;
}

FooterKey .footer-key--key {
    background: #2f2f2f;
    color: #a1a1a1;
}

FooterKey:hover {
    background: #2f2f2f;
}

FooterKey:hover .footer-key--key {
    background: #6366f1;
    color: #ececec;
}

/* Button styling */
Button {
    background: #2f2f2f;
    color: #ececec;
    border: solid #3a3a3a;
}

Button:hover {
    background: #3a3a3a;
    border: solid #6366f1;
}

Button.-primary {
    background: #6366f1;
    color: #ececec;
    border: none;
}

Button.-primary:hover {
    background: #4f46e5;
}
"""


class AG3NTApp(App):
    """AG3NT Terminal User Interface - Sleek Dark Theme Edition."""

    # Very smooth scrolling
    SCROLL_SENSITIVITY_Y = 0.25

    CSS = APP_CSS

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear", "Clear", show=True),
        Binding("ctrl+p", "command_palette", "Commands", show=True),
        Binding("ctrl+h", "session_browser", "History", show=True),
        Binding("ctrl+t", "toggle_auto_approve", "Auto", show=True),
        Binding("ctrl+g", "toggle_go_mode", "Go", show=True),
        Binding("f1", "help", "Help", show=True),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    TITLE = "AP3X"
    SUB_TITLE = f"Personal AI Assistant v{VERSION}"

    def __init__(self) -> None:
        super().__init__()
        self.gateway_url = discover_gateway_url()
        self.gateway = GatewayClient(self.gateway_url)
        self.session_id: Optional[str] = None
        self._pending_request = False
        self._current_request_id: Optional[str] = None
        self._request_start_time: Optional[float] = None
        self._loading_widget: Optional[LoadingWidget] = None
        self._last_user_message: str = ""  # For retry functionality
        # Session, history, and draft persistence
        self.session_manager = SessionManager()
        self.history_manager = HistoryManager()
        self.draft_manager = DraftManager()
        self._auto_approve: bool = False
        self._go_mode: bool = False
        self._total_tokens: int = 0
        self._tool_displays: dict[str, ToolCallDisplay] = {}
        self._streaming_message: Optional[AssistantMessage] = None
        self._pending_approvals: dict[str, ApprovalRequest] = {}
        self._approval_queue: asyncio.Queue = asyncio.Queue()

    def compose(self) -> ComposeResult:
        yield Header()
        yield ScrollableContainer(
            WelcomeBanner(gateway_url=self.gateway_url, id="welcome-banner"),
            id="chat-container",
        )
        yield Container(id="loading-container", classes="hidden")
        yield ContextualHints(
            "[dim]Enter[/] send • [dim]Shift+Enter[/] new line • "
            "[dim]Ctrl+P[/] commands • [dim]Ctrl+H[/] history • "
            "[dim]F1[/] help",
            id="hints-bar",
        )
        yield Container(ChatInput(id="chat-input"), id="input-wrapper")
        yield StatusBar(id="status-bar")
        yield Footer()

    def on_ready(self) -> None:
        """Focus the input when app is ready."""
        chat_input = self.query_one("#chat-input", ChatInput)
        chat_input.focus_input()

    def on_click(self, event: events.Click) -> None:
        """Focus the input when clicking anywhere."""
        chat_input = self.query_one("#chat-input", ChatInput)
        chat_input.focus_input()

    def action_help(self) -> None:
        """Show help screen."""
        self.push_screen(HelpScreen())

    def action_command_palette(self) -> None:
        """Show command palette."""
        self.push_screen(CommandPalette())

    def action_toggle_auto_approve(self) -> None:
        """Toggle auto-approve mode."""
        self._auto_approve = not self._auto_approve
        try:
            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.auto_approve = self._auto_approve
        except NoMatches:
            pass
        mode = "enabled" if self._auto_approve else "disabled"
        self.add_system_message(f"Auto-approve {mode}")

    def action_toggle_go_mode(self) -> None:
        """Toggle Go mode - bypasses ALL approvals and safety checks."""
        self._go_mode = not self._go_mode
        try:
            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.go_mode = self._go_mode
        except NoMatches:
            pass

        if self._go_mode:
            # Also enable auto-approve when Go mode is on
            self._auto_approve = True
            try:
                status_bar = self.query_one("#status-bar", StatusBar)
                status_bar.auto_approve = True
            except NoMatches:
                pass
            self.add_system_message(
                "[bold #10b981]⚡ GO MODE ENABLED[/bold #10b981] - "
                "All approvals bypassed. Full speed ahead!"
            )
        else:
            self.add_system_message("Go mode disabled")

    def action_session_browser(self) -> None:
        """Open the session browser to resume or manage sessions."""
        sessions = self.session_manager.list_sessions()
        self.push_screen(SessionBrowser(sessions))

    def on_session_browser_session_selected(
        self, event: SessionBrowser.SessionSelected
    ) -> None:
        """Handle session selection from browser."""
        self.resume_session(event.session_id)

    def on_session_browser_session_deleted(
        self, event: SessionBrowser.SessionDeleted
    ) -> None:
        """Handle session deletion from browser."""
        self.session_manager.delete_session(event.session_id)
        self.add_system_message(f"Session deleted: {event.session_id[:8]}...")

    @work(exclusive=True, thread=False)
    async def resume_session(self, session_id: str) -> None:
        """Resume a previous session."""
        session = self.session_manager.get_session(session_id)
        if not session:
            self.add_error_message(f"Session not found: {session_id}")
            return

        # Clear current chat
        container = self.query_one("#chat-container", ScrollableContainer)
        container.remove_children()
        container.mount(
            WelcomeBanner(gateway_url=self.gateway_url, id="welcome-banner")
        )

        # Set the session ID
        self.session_id = session_id
        self._total_tokens = session.total_tokens

        # Update status bar
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update_info(session_id=session_id)
        status_bar.token_count = self._total_tokens

        self.add_system_message(
            f"Resumed session: {session.title or 'Untitled'}\n"
            f"Messages: {session.message_count} | Tokens: {session.total_tokens}"
        )

    def on_command_palette_command_selected(
        self, event: CommandPalette.CommandSelected
    ) -> None:
        """Handle command selection from palette."""
        command_id = event.command_id

        if command_id == "cmd-reconnect":
            self.check_gateway()
        elif command_id == "cmd-clear":
            self.action_clear()
        elif command_id == "cmd-copy-session":
            self._copy_session_id()
        elif command_id == "cmd-session-info":
            if self.session_id:
                self.add_system_message(f"Session ID: {self.session_id}")
            else:
                self.add_system_message("No active session")
        elif command_id == "cmd-control-panel":
            webbrowser.open("http://127.0.0.1:18789/")
            self.add_system_message("Opening Control Panel in browser...")
        elif command_id == "cmd-node-status":
            self.show_node_status()
        elif command_id == "cmd-toggle-auto":
            self.action_toggle_auto_approve()
        elif command_id == "cmd-toggle-go":
            self.action_toggle_go_mode()
        elif command_id == "cmd-sessions":
            self.action_session_browser()
        elif command_id == "cmd-help":
            self.action_help()
        elif command_id == "cmd-quit":
            self.action_quit()

    def _copy_session_id(self) -> None:
        """Copy session ID to clipboard."""
        if not self.session_id:
            self.add_system_message("No active session")
            return
        try:
            if platform.system() == "Windows":
                subprocess.run(
                    ["clip"], input=self.session_id.encode(), check=True
                )
            elif platform.system() == "Darwin":
                subprocess.run(
                    ["pbcopy"], input=self.session_id.encode(), check=True
                )
            else:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=self.session_id.encode(),
                    check=True,
                )
            self.add_system_message(
                f"Session ID copied to clipboard: {self.session_id}"
            )
        except Exception as e:
            self.add_system_message(
                f"Session ID: {self.session_id} (copy failed: {e})"
            )

    @work(exclusive=False, thread=False)
    async def show_node_status(self) -> None:
        """Show node status information."""
        try:
            data = await self.gateway.get_node_status()
            local = data.get("localNode", {})
            node_name = local.get("name", "Unknown")
            node_type = local.get("type", "Unknown")
            caps = local.get("capabilities", [])
            caps_str = ", ".join(caps) if caps else "None"

            self.add_system_message(
                f"Node: {node_name}\n"
                f"Type: {node_type}\n"
                f"Capabilities: {caps_str}"
            )
        except Exception as e:
            self.add_error_message(f"Error getting node status: {e}")

    async def on_mount(self) -> None:
        """Initialize the app on mount."""
        self.add_system_message("Connecting to AP3X...")
        self.check_gateway()

    def on_chat_input_mode_changed(self, event: ChatInput.ModeChanged) -> None:
        """Handle mode change from chat input."""
        try:
            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.set_mode(event.mode)
        except NoMatches:
            pass

    def on_chat_text_area_history_navigate(
        self, event: ChatTextArea.HistoryNavigate
    ) -> None:
        """Handle history navigation from chat input."""
        chat_input = self.query_one("#chat-input", ChatInput)

        if event.direction == "up":
            entry = self.history_manager.previous(event.current_input)
            if entry is not None:
                chat_input.set_text(entry)
        elif event.direction == "down":
            entry = self.history_manager.next(event.current_input)
            if entry is not None:
                chat_input.set_text(entry)
            else:
                # At the end of history, clear input or restore original
                chat_input.set_text("")

    @work(exclusive=True, thread=False)
    async def check_gateway(self) -> None:
        """Check gateway connection and initialize session."""
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.set_connecting()
        try:
            # Check health
            await self.gateway.health()
            status_bar.set_connected()
            status_bar.set_status_message("Connected to AP3X")
            self.add_system_message("Connected to AP3X!")

            # Get node info
            try:
                data = await self.gateway.get_node_status()
                local = data.get("localNode", {})
                node_name = local.get("name", "Unknown")
                status_bar.set_status_message(f"Node: {node_name}")
            except Exception:
                pass

            # Create session
            await self.create_session()
        except httpx.ConnectError:
            status_bar.set_disconnected()
            status_bar.set_status_message("Gateway disconnected")
            self.add_error_message(
                f"Cannot connect to Gateway at {self.gateway_url}\n"
                "Make sure the Gateway is running: cd apps/gateway && node dist/index.js"
            )
        except Exception as e:
            status_bar.set_connection_error()
            status_bar.set_status_message("Error")
            self.add_error_message(f"Error: {e}")

    async def create_session(self) -> None:
        """Create and auto-approve a new session for local dev."""
        self.session_id = f"tui-{uuid.uuid4()}"
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update_info(session_id=self.session_id)

        # Save session to persistence
        self.session_manager.create_session(self.session_id, title="New Session")

        # Send initial message to trigger session creation
        try:
            data = await self.gateway.chat("hello", self.session_id)

            # Check if pairing is needed (API uses camelCase)
            if data.get("pairingRequired") or data.get("pairing_required"):
                code = data.get("pairingCode") or data.get("pairing_code", "")
                session_key = data.get("session_id", self.session_id)
                self.add_system_message(
                    f"Session requires approval (code: {code}). Auto-approving..."
                )

                # Auto-approve for local TUI
                try:
                    await self.gateway.approve_session(
                        f"cli:local:{session_key}", code, True
                    )
                    self.add_system_message("Session approved! Ready to chat.")
                except Exception as e:
                    self.add_error_message(f"Failed to approve: {e}")
            elif data.get("ok"):
                self.add_system_message("Session ready! Type a message to start.")
            else:
                self.add_system_message("Session created. Type a message to start.")
        except Exception as e:
            self.add_error_message(f"Session error: {e}")

    def add_user_message(self, content: str) -> None:
        """Add a user message to the chat."""
        container = self.query_one("#chat-container", ScrollableContainer)
        container.mount(UserMessage(content))
        container.scroll_end(animate=True)
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update_info(increment_messages=True)

        # Update session with first message as title
        if self.session_id:
            session = self.session_manager.get_session(self.session_id)
            if session:
                # Set title from first user message if not set
                new_title = session.title if session.title != "New Session" else content[:100]
                self.session_manager.update_session(
                    self.session_id,
                    message_count=session.message_count + 1,
                    title=new_title,
                )

    def add_assistant_message(
        self, content: str, response_time: Optional[float] = None
    ) -> None:
        """Add an assistant message to the chat."""
        container = self.query_one("#chat-container", ScrollableContainer)
        container.mount(AssistantMessage(content, response_time=response_time))
        container.scroll_end(animate=True)
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update_info(response_time=response_time, increment_messages=True)

    def _start_streaming_message(self) -> AssistantMessage:
        """Start a new streaming assistant message."""
        container = self.query_one("#chat-container", ScrollableContainer)
        msg = AssistantMessage("")  # Empty content for streaming
        container.mount(msg)
        container.scroll_end(animate=True)
        self._streaming_message = msg
        return msg

    def _finalize_streaming_message(self, response_time: float) -> None:
        """Finalize the current streaming message."""
        if self._streaming_message:
            self._streaming_message.finalize(response_time)
            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.update_info(
                response_time=response_time, increment_messages=True
            )
            self._streaming_message = None

    def add_system_message(self, content: str) -> None:
        """Add a system message to the chat."""
        container = self.query_one("#chat-container", ScrollableContainer)
        container.mount(SystemMessage(content))
        container.scroll_end(animate=True)

    def add_error_message(self, content: str) -> None:
        """Add an error message to the chat."""
        container = self.query_one("#chat-container", ScrollableContainer)
        container.mount(ErrorMessage(content))
        container.scroll_end(animate=True)

    def add_bash_output(self, command: str, output: str, exit_code: int = 0) -> None:
        """Add a bash command output to the chat."""
        container = self.query_one("#chat-container", ScrollableContainer)
        container.mount(BashOutputMessage(command, output, exit_code))
        container.scroll_end(animate=True)

    def _add_tool_display(
        self, tool_name: str, tool_args: dict, tool_call_id: str
    ) -> ToolCallDisplay:
        """Add a tool call display to the chat."""
        container = self.query_one("#chat-container", ScrollableContainer)
        display = create_tool_display(tool_name, tool_args, tool_call_id)
        self._tool_displays[tool_call_id] = display
        container.mount(display)
        container.scroll_end(animate=True)
        display.set_running()
        return display

    def _update_tool_display(
        self, tool_call_id: str, result: str | None = None, error: str | None = None
    ) -> None:
        """Update a tool call display with result or error."""
        display = self._tool_displays.get(tool_call_id)
        if display:
            if error:
                display.set_error(error)
            elif result:
                display.set_complete(result)

    # Approval flow methods
    def _request_approval(
        self,
        tool_name: str,
        tool_args: dict,
        tool_call_id: str,
        description: str = "",
    ) -> None:
        """Show approval request for a tool.

        In Go mode or auto-approve mode, automatically approve.
        Otherwise, show inline approval widget.
        """
        if self._go_mode or self._auto_approve:
            # Go/Auto-approve - send approval immediately
            self._handle_approval(tool_call_id, approved=True)
            return

        # Show approval widget
        container = self.query_one("#chat-container", ScrollableContainer)
        approval = ApprovalRequest(
            tool_name=tool_name,
            tool_args=tool_args,
            tool_call_id=tool_call_id,
            description=description,
        )
        self._pending_approvals[tool_call_id] = approval
        container.mount(approval)
        container.scroll_end(animate=True)

        # Pause loading indicator
        if self._loading_widget:
            self._loading_widget.pause("Awaiting approval")

    def on_approval_request_approved(self, event: ApprovalRequest.Approved) -> None:
        """Handle approval of tool execution."""
        tool_call_id = event.tool_call_id

        # Enable auto-approve if requested
        if event.auto_approve:
            self._auto_approve = True
            try:
                status_bar = self.query_one("#status-bar", StatusBar)
                status_bar.auto_approve = True
            except NoMatches:
                pass
            self.add_system_message("Auto-approve enabled for this session")

        # Remove from pending
        self._pending_approvals.pop(tool_call_id, None)

        # Resume loading
        if self._loading_widget:
            self._loading_widget.resume()

        # Send approval to gateway
        self._handle_approval(tool_call_id, approved=True)

    def on_approval_request_rejected(self, event: ApprovalRequest.Rejected) -> None:
        """Handle rejection of tool execution."""
        tool_call_id = event.tool_call_id

        # Remove from pending
        self._pending_approvals.pop(tool_call_id, None)

        # Resume loading
        if self._loading_widget:
            self._loading_widget.resume()

        # Send rejection to gateway
        self._handle_approval(tool_call_id, approved=False)

    @work(exclusive=False, thread=False)
    async def _handle_approval(self, tool_call_id: str, approved: bool) -> None:
        """Send approval/rejection to gateway."""
        try:
            await self.gateway.approve_tool(
                self.session_id, tool_call_id, approved
            )
            if not approved:
                self.add_system_message(f"Tool execution rejected")
        except Exception as e:
            self.add_error_message(f"Approval error: {e}")

    def _clear_pending_approvals(self) -> None:
        """Remove all pending approval widgets."""
        for approval in self._pending_approvals.values():
            try:
                approval.remove()
            except Exception:
                pass
        self._pending_approvals.clear()

    def show_loading(self, show: bool = True, status: str = "Thinking") -> None:
        """Show/hide loading indicator."""
        loading_container = self.query_one("#loading-container", Container)
        if show:
            loading_container.remove_class("hidden")
            # Create and mount the loading widget
            if self._loading_widget is None:
                self._loading_widget = LoadingWidget(status)
                loading_container.mount(self._loading_widget)
            else:
                self._loading_widget.set_status(status)
            # Disable input while loading
            chat_input = self.query_one("#chat-input", ChatInput)
            chat_input.set_submit_enabled(False)
        else:
            loading_container.add_class("hidden")
            # Remove loading widget
            if self._loading_widget is not None:
                self._loading_widget.remove()
                self._loading_widget = None
            # Re-enable input
            chat_input = self.query_one("#chat-input", ChatInput)
            chat_input.set_submit_enabled(True)
            chat_input.focus_input()

    def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        """Handle message submission from ChatInput."""
        text = event.value
        mode = event.mode
        if not text or self._pending_request:
            return

        # Add to persistent history
        self.history_manager.add(text)

        # Handle bash commands (! prefix)
        if mode == "bash" or text.startswith("!"):
            cmd = text[1:] if text.startswith("!") else text
            self.add_user_message(f"!{cmd}")
            self.run_bash_command(cmd)
            return

        # Handle slash commands
        if mode == "command" or text.startswith("/"):
            cmd = text.lower().strip()
            if cmd in ("/quit", "/exit", "/q"):
                self.exit()
                return
            if cmd in ("/clear", "/cls"):
                self.action_clear()
                return
            if cmd == "/help":
                self.action_help()
                return
            if cmd == "/status":
                self.add_system_message(f"Session: {self.session_id or 'None'}")
                return
            if cmd == "/nodes":
                self.fetch_node_info()
                return
            if cmd == "/tokens":
                self.add_system_message(
                    f"Total tokens used: {self._total_tokens}"
                )
                return
            if cmd == "/auto":
                self.action_toggle_auto_approve()
                return
            if cmd == "/go":
                self.action_toggle_go_mode()
                return
            if cmd in ("/sessions", "/history"):
                self.action_session_browser()
                return
            # Unknown command
            self.add_error_message(f"Unknown command: {cmd}")
            return

        # Regular message - send to agent
        self.add_user_message(text)
        self.send_message(text)

    @work(exclusive=True, thread=False)
    async def run_bash_command(self, command: str) -> None:
        """Run a bash command and display output."""
        self.show_loading(True, "Running command")
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            output = result.stdout + result.stderr
            self.add_bash_output(command, output.strip(), result.returncode)
        except subprocess.TimeoutExpired:
            self.add_error_message(f"Command timed out: {command}")
        except Exception as e:
            self.add_error_message(f"Command error: {e}")
        finally:
            self.show_loading(False)

    @work(exclusive=True, thread=False)
    async def fetch_node_info(self) -> None:
        """Fetch and display node information."""
        try:
            nodes = await self.gateway.get_nodes()
            if nodes:
                info = "**Connected Nodes:**\n\n"
                for node in nodes:
                    info += f"- **{node.get('name', 'Unknown')}** ({node.get('type', 'unknown')})\n"
                    caps = node.get("capabilities", [])
                    if caps:
                        info += f"  Capabilities: {', '.join(caps)}\n"
                self.add_assistant_message(info)
            else:
                self.add_system_message("No nodes connected.")
        except Exception as e:
            self.add_error_message(f"Error fetching nodes: {e}")

    @work(exclusive=True, thread=False)
    async def send_message(self, text: str) -> None:
        """Send message to the agent with streaming support."""
        self._pending_request = True
        self._current_request_id = str(uuid.uuid4())
        self._request_start_time = time.time()
        self._last_user_message = text  # Save for retry
        self.show_loading(True)

        # Save draft in case of error
        if self.session_id:
            self.draft_manager.save_draft(self.session_id, text)

        try:
            # Try streaming first
            try:
                await self._send_streaming(text)
                # Clear draft on success
                if self.session_id:
                    self.draft_manager.clear_draft(self.session_id)
            except Exception as e:
                # Fall back to non-streaming
                try:
                    await self._send_non_streaming(text)
                    # Clear draft on success
                    if self.session_id:
                        self.draft_manager.clear_draft(self.session_id)
                except Exception as inner_e:
                    # Show retry banner on failure
                    self._show_retry_banner(str(inner_e), text)
        finally:
            self._pending_request = False
            self._current_request_id = None
            self.show_loading(False)

    def _show_retry_banner(self, error_message: str, original_message: str) -> None:
        """Show a retry banner for failed requests."""
        container = self.query_one("#chat-container", ScrollableContainer)
        banner = RetryBanner(
            error_message=error_message,
            original_message=original_message,
            request_id=self._current_request_id or "",
        )
        container.mount(banner)
        container.scroll_end(animate=True)

    def on_retry_banner_retry_requested(self, event: RetryBanner.RetryRequested) -> None:
        """Handle retry request from banner."""
        if event.original_message:
            self.send_message(event.original_message)
            self._tool_displays.clear()
            self._clear_pending_approvals()

    async def _send_streaming(self, text: str) -> None:
        """Send message with streaming response."""
        streaming_msg = self._start_streaming_message()
        content_buffer = ""

        # Small delay to ensure widget is mounted before we start appending
        await asyncio.sleep(0.05)

        async for event in self.gateway.chat_stream(text, self.session_id):
            event_type = event.get("type")

            if event_type == "chunk":
                chunk = event.get("content", "")
                content_buffer += chunk
                streaming_msg.append_content(chunk)
                container = self.query_one("#chat-container", ScrollableContainer)
                container.scroll_end(animate=False)
                # Yield to allow UI refresh
                await asyncio.sleep(0)

            elif event_type == "tool_start":
                tool_name = event.get("tool_name", "unknown")
                tool_args = event.get("args", {})
                tool_call_id = event.get("tool_call_id", "")
                self._add_tool_display(tool_name, tool_args, tool_call_id)
                if self._loading_widget:
                    args_preview = str(tool_args)[:30]
                    self._loading_widget.set_tool(tool_name, args_preview)

            elif event_type == "tool_end":
                tool_call_id = event.get("tool_call_id", "")
                result = event.get("result", "")
                self._update_tool_display(tool_call_id, result=result)
                if self._loading_widget:
                    self._loading_widget.clear_tool()

            elif event_type == "tool_error":
                tool_call_id = event.get("tool_call_id", "")
                error = event.get("error", "Unknown error")
                self._update_tool_display(tool_call_id, error=error)
                if self._loading_widget:
                    self._loading_widget.clear_tool()

            elif event_type == "approval_required":
                # Tool requires user approval
                tool_name = event.get("tool_name", "unknown")
                tool_args = event.get("args", {})
                tool_call_id = event.get("tool_call_id", "")
                description = event.get("description", "")

                # Go mode bypasses ALL approvals
                if self._go_mode:
                    await self._handle_approval(tool_call_id, approved=True)
                # Auto-approve or non-sensitive tools
                elif self._auto_approve or not requires_approval(tool_name):
                    await self._handle_approval(tool_call_id, approved=True)
                else:
                    # Show approval widget
                    self._request_approval(
                        tool_name, tool_args, tool_call_id, description
                    )

            elif event_type == "usage":
                total = event.get("total_tokens", 0)
                self._total_tokens += total
                try:
                    status_bar = self.query_one("#status-bar", StatusBar)
                    status_bar.token_count = self._total_tokens
                except NoMatches:
                    pass
                # Persist tokens to session
                if self.session_id:
                    self.session_manager.update_session(
                        self.session_id, total_tokens=self._total_tokens
                    )

            elif event_type == "complete":
                response_time = time.time() - self._request_start_time
                self._finalize_streaming_message(response_time)
                return

            elif event_type == "error":
                error = event.get("error") or event.get("message", "Unknown error")
                self.add_error_message(f"Error: {error}")
                return

        # If we get here, stream ended without complete event
        response_time = time.time() - self._request_start_time
        self._finalize_streaming_message(response_time)

    async def _send_non_streaming(self, text: str) -> None:
        """Send message without streaming (fallback)."""
        try:
            data = await self.gateway.chat(text, self.session_id)

            # Check if pairing is required
            if data.get("pairingRequired") or data.get("pairing_required"):
                code = data.get("pairingCode") or data.get("pairing_code", "")
                session_key = data.get("session_id", self.session_id)
                self.add_system_message(
                    f"Session needs re-approval (code: {code}). Auto-approving..."
                )

                # Auto-approve
                try:
                    await self.gateway.approve_session(
                        f"cli:local:{session_key}", code, True
                    )
                    self.add_system_message("Re-approved! Resending message...")
                    data = await self.gateway.chat(text, self.session_id)
                except Exception:
                    self.add_error_message("Failed to re-approve session")
                    return

            # Calculate response time
            response_time = time.time() - self._request_start_time

            # Update token count
            if "usage" in data:
                total = data["usage"].get("total_tokens", 0)
                self._total_tokens += total
                try:
                    status_bar = self.query_one("#status-bar", StatusBar)
                    status_bar.token_count = self._total_tokens
                except NoMatches:
                    pass
                # Persist tokens to session
                if self.session_id:
                    self.session_manager.update_session(
                        self.session_id, total_tokens=self._total_tokens
                    )

            if data.get("ok"):
                agent_text = data.get("text", "")
                if agent_text:
                    self.add_assistant_message(agent_text, response_time=response_time)
                else:
                    self.add_system_message("(Agent returned empty response)")
            else:
                agent_text = data.get("text", "")
                if agent_text:
                    self.add_assistant_message(agent_text, response_time=response_time)
                else:
                    error = data.get("error", "Unknown error")
                    self.add_error_message(f"API Error: {error}")
        except httpx.TimeoutException:
            self.add_error_message(
                "Request timed out (5 min). The agent may still be processing."
            )
        except Exception as e:
            self.add_error_message(f"Error: {e}")

    def action_clear(self) -> None:
        """Clear chat history and create new session."""
        # Clear tracking state
        self._tool_displays.clear()
        self._pending_approvals.clear()
        self._streaming_message = None

        container = self.query_one("#chat-container", ScrollableContainer)
        container.remove_children()
        # Mount welcome banner again
        container.mount(
            WelcomeBanner(gateway_url=self.gateway_url, id="welcome-banner")
        )
        self.add_system_message("Chat cleared. Starting new session...")
        # Create new session
        self.session_id = f"tui-{uuid.uuid4()}"
        self._total_tokens = 0
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update_info(session_id=self.session_id)
        status_bar.token_count = 0

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()

    async def action_cancel(self) -> None:
        """Cancel current operation."""
        # If there are pending approvals, reject them all
        if self._pending_approvals:
            for tool_call_id in list(self._pending_approvals.keys()):
                await self._handle_approval(tool_call_id, approved=False)
            self._clear_pending_approvals()
            self.add_system_message("Pending approvals cancelled")
            return

        if self._pending_request and self._current_request_id:
            try:
                await self.gateway.cancel_request(
                    self.session_id, self._current_request_id
                )
                self.add_system_message("Request cancelled")
            except Exception as e:
                self.add_system_message(f"Could not cancel: {e}")
            finally:
                self._pending_request = False
                self._current_request_id = None
                self.show_loading(False)
                self._clear_pending_approvals()
        elif self._pending_request:
            self.add_system_message("(Cancellation not supported yet)")

    async def on_unmount(self) -> None:
        """Cleanup on exit."""
        await self.gateway.close()


def main() -> None:
    """Run the AP3X TUI."""
    from dotenv import load_dotenv

    load_dotenv()
    app = AG3NTApp()
    app.run()


if __name__ == "__main__":
    main()
