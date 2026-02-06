"""TUI widgets package."""

from .messages import (
    UserMessage,
    AssistantMessage,
    SystemMessage,
    ErrorMessage,
    BashOutputMessage,
)
from .chat_input import ChatInput, ChatTextArea
from .status_bar import StatusBar
from .loading import LoadingWidget
from .welcome import WelcomeBanner
from .tool_display import ToolCallDisplay, create_tool_display
from .tool_icons import ToolIcon, TOOL_ICONS, get_tool_icon
from .approval import (
    ApprovalRequest,
    ApprovalBanner,
    SENSITIVE_TOOLS,
    requires_approval,
)
from .diff import DiffDisplay, InlineDiff, EditPreview
from .connection import (
    ConnectionState,
    ConnectionIndicator,
    AutoReconnect,
    DraftManager,
)
from .retry import RetryBanner, TimeoutBanner, OfflineBanner
from .hints import (
    KeyHint,
    HintsBar,
    ContextualHints,
    FirstRunHints,
    ModeIndicator,
)

__all__ = [
    # Messages
    "UserMessage",
    "AssistantMessage",
    "SystemMessage",
    "ErrorMessage",
    "BashOutputMessage",
    # Input
    "ChatInput",
    "ChatTextArea",
    # Status
    "StatusBar",
    "LoadingWidget",
    "WelcomeBanner",
    # Tools
    "ToolCallDisplay",
    "create_tool_display",
    "ToolIcon",
    "TOOL_ICONS",
    "get_tool_icon",
    # Approval
    "ApprovalRequest",
    "ApprovalBanner",
    "SENSITIVE_TOOLS",
    "requires_approval",
    # Diff (Phase 5)
    "DiffDisplay",
    "InlineDiff",
    "EditPreview",
    # Connection (Phase 5)
    "ConnectionState",
    "ConnectionIndicator",
    "AutoReconnect",
    "DraftManager",
    # Retry (Phase 5)
    "RetryBanner",
    "TimeoutBanner",
    "OfflineBanner",
    # Hints (Phase 5)
    "KeyHint",
    "HintsBar",
    "ContextualHints",
    "FirstRunHints",
    "ModeIndicator",
]
