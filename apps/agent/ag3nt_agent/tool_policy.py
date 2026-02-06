"""Tool access control via allow/deny lists for AG3NT.

Provides policy-based filtering of tools using profiles and tool groups.
Configuration loaded from ~/.ag3nt/tool_policy.yaml.

Built-in profiles:
    - minimal: Only safe read-only tools
    - coding: All development tools (default)
    - messaging: Coding + communication tools
    - full: Everything enabled

Tool groups:
    - group:fs — File system tools (read, write, edit, delete, glob, grep)
    - group:runtime — Execution tools (exec_command, process_tool, shell, execute)
    - group:web — Web tools (internet_search, fetch_url, web_search)
    - group:memory — Memory tools (memory_search, codebase_search_tool)
    - group:patch — Patch tools (apply_patch)

Usage:
    from ag3nt_agent.tool_policy import ToolPolicyManager

    manager = ToolPolicyManager()
    filtered_tools = manager.filter_tools(all_tools)
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("ag3nt.tool_policy")

# Tool group definitions
TOOL_GROUPS: dict[str, list[str]] = {
    "group:fs": [
        "read_file", "write_file", "edit_file", "delete_file",
        "read", "write", "edit",
        "glob_tool", "grep_tool", "notebook_tool",
        "read_directory", "list_directory",
    ],
    "group:runtime": [
        "exec_command", "process_tool",
        "shell", "execute", "bash",
        "sandbox_run_command",
    ],
    "group:web": [
        "internet_search", "fetch_url", "web_search",
        "web_fetch", "http_request",
    ],
    "group:memory": [
        "memory_search", "codebase_search_tool",
        "memory_summarize",
    ],
    "group:patch": [
        "apply_patch",
    ],
    "group:lsp": [
        "lsp_tool",
    ],
    "group:lint": [
        "lint_tool",
    ],
    "group:revert": [
        "undo_last", "undo_to", "unrevert", "show_undo_history",
    ],
}

# Built-in profiles
PROFILES: dict[str, dict[str, Any]] = {
    "minimal": {
        "allow": [
            "group:fs",
            "group:memory",
            "internet_search", "fetch_url",
            "ask_user",
        ],
        "deny": [
            "group:runtime",
            "group:patch",
            "write_file", "edit_file", "delete_file",
        ],
    },
    "coding": {
        "allow": [
            "group:fs",
            "group:runtime",
            "group:web",
            "group:memory",
            "group:patch",
            "ask_user", "task", "run_skill",
            "schedule_reminder", "deep_reasoning",
        ],
        "deny": [],
    },
    "messaging": {
        "allow": [
            "group:fs",
            "group:runtime",
            "group:web",
            "group:memory",
            "group:patch",
            "ask_user", "task", "run_skill",
            "schedule_reminder", "deep_reasoning",
        ],
        "deny": [],
    },
    "full": {
        "allow": ["*"],
        "deny": [],
    },
}


@dataclass
class ToolPolicy:
    """Resolved tool access policy."""

    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)
    profile: str = "coding"

    def _expand_groups(self, items: list[str]) -> set[str]:
        """Expand group references into individual tool names."""
        expanded: set[str] = set()
        for item in items:
            if item in TOOL_GROUPS:
                expanded.update(TOOL_GROUPS[item])
            elif item == "*":
                expanded.add("*")
            else:
                expanded.add(item)
        return expanded

    def is_tool_allowed(self, name: str) -> bool:
        """Check if a tool is allowed by this policy.

        Deny always wins over allow.

        Args:
            name: Tool function name

        Returns:
            True if the tool is allowed
        """
        denied = self._expand_groups(self.deny)
        allowed = self._expand_groups(self.allow)

        # Deny wins
        if name in denied:
            return False

        # Allow check
        if "*" in allowed:
            return True
        if name in allowed:
            return True

        # If allow list is non-empty and not wildcard, deny by default
        if allowed and "*" not in allowed:
            return False

        # If no allow list specified, allow everything not denied
        return True


class ToolPolicyManager:
    """Manages tool access policies from config and profiles."""

    def __init__(self, config_path: str | None = None) -> None:
        self._config_path = config_path or str(
            Path.home() / ".ag3nt" / "tool_policy.yaml"
        )
        self._policy: ToolPolicy | None = None

    def load_policy(self) -> ToolPolicy:
        """Load policy from config file or defaults.

        Returns:
            Resolved ToolPolicy
        """
        if self._policy is not None:
            return self._policy

        # Check environment override
        profile_override = os.environ.get("AG3NT_TOOL_PROFILE")

        # Try loading config file
        config = self._load_config()

        if config:
            profile = profile_override or config.get("profile", "coding")
            allow = config.get("allow", [])
            deny = config.get("deny", [])

            # If profile specified, merge profile defaults with config overrides
            if profile in PROFILES and not allow and not deny:
                profile_config = PROFILES[profile]
                allow = profile_config.get("allow", [])
                deny = profile_config.get("deny", [])

            self._policy = ToolPolicy(
                allow=allow,
                deny=deny,
                profile=profile,
            )
        elif profile_override and profile_override in PROFILES:
            profile_config = PROFILES[profile_override]
            self._policy = ToolPolicy(
                allow=profile_config.get("allow", []),
                deny=profile_config.get("deny", []),
                profile=profile_override,
            )
        else:
            # Default: coding profile
            profile_config = PROFILES["coding"]
            self._policy = ToolPolicy(
                allow=profile_config.get("allow", []),
                deny=profile_config.get("deny", []),
                profile="coding",
            )

        logger.info(f"Tool policy loaded: profile={self._policy.profile}")
        return self._policy

    def _load_config(self) -> dict[str, Any] | None:
        """Load config from YAML file."""
        config_path = Path(self._config_path)
        if not config_path.exists():
            return None

        try:
            import yaml

            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            if isinstance(config, dict):
                return config
        except ImportError:
            logger.debug("PyYAML not installed, using defaults")
        except Exception as e:
            logger.warning(f"Failed to load tool policy config: {e}")

        return None

    def filter_tools(self, tools: list) -> list:
        """Filter a list of tools based on the active policy.

        Args:
            tools: List of LangChain tool objects

        Returns:
            Filtered list with denied tools removed
        """
        policy = self.load_policy()

        filtered = []
        removed = []
        for t in tools:
            name = getattr(t, "name", str(t))
            if policy.is_tool_allowed(name):
                filtered.append(t)
            else:
                removed.append(name)

        if removed:
            logger.info(
                f"Tool policy ({policy.profile}) removed {len(removed)} tools: "
                f"{', '.join(removed)}"
            )

        return filtered


# Tools that perform write operations on the filesystem
_WRITE_TOOLS: set[str] = {
    "write_file", "edit_file", "delete_file",
    "multi_edit", "apply_patch",
    "exec_command", "shell", "bash",
    "notebook_tool",
}


class PathProtection:
    """Singleton that guards against accidental writes outside the workspace.

    Paths inside the workspace are always allowed.  Paths outside require
    explicit per-directory approval which is cached per session so the user
    is only prompted once per external directory.
    """

    _instance: PathProtection | None = None
    _instance_lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self._workspace_root: str | None = None
        # session_id -> { dir_path -> approved (bool) }
        self._approvals: dict[str, dict[str, bool]] = {}
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls, workspace_root: str | None = None) -> PathProtection:
        """Return the singleton, optionally setting the workspace root."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        if workspace_root is not None:
            cls._instance.set_workspace_root(workspace_root)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Destroy the singleton (for testing)."""
        with cls._instance_lock:
            cls._instance = None

    def set_workspace_root(self, root: str) -> None:
        """Set or update the workspace root path."""
        self._workspace_root = os.path.normpath(root)

    def is_within_workspace(self, file_path: str) -> bool:
        """Return True if *file_path* is inside the workspace."""
        if self._workspace_root is None:
            return True  # No workspace configured → allow all
        normed = os.path.normpath(os.path.abspath(file_path))
        workspace = os.path.normpath(os.path.abspath(self._workspace_root))
        # Use os.sep to avoid prefix false-positives (e.g. /workspace2)
        return normed == workspace or normed.startswith(workspace + os.sep)

    def check_path(
        self,
        file_path: str,
        session_id: str,
        operation: str = "access",
    ) -> tuple[bool, str]:
        """Check if access to *file_path* is allowed.

        Returns:
            ``(True, "")`` if allowed, or
            ``(False, message)`` with a human-readable explanation if blocked.
        """
        if self._workspace_root is None:
            return True, ""

        if self.is_within_workspace(file_path):
            return True, ""

        dir_path = os.path.dirname(os.path.normpath(os.path.abspath(file_path)))

        with self._lock:
            session_approvals = self._approvals.get(session_id, {})
            cached = session_approvals.get(dir_path)

        if cached is True:
            return True, ""
        if cached is False:
            return False, (
                f"Access to '{dir_path}' outside the project was previously denied."
            )

        return False, (
            f"Agent wants to {operation} '{file_path}' which is outside the "
            f"project workspace ({self._workspace_root}). Allow access to "
            f"'{dir_path}'?"
        )

    def record_approval(
        self, session_id: str, file_path: str, approved: bool
    ) -> None:
        """Cache the user's approval decision for a directory."""
        dir_path = os.path.dirname(os.path.normpath(os.path.abspath(file_path)))
        with self._lock:
            if session_id not in self._approvals:
                self._approvals[session_id] = {}
            self._approvals[session_id][dir_path] = approved

    def clear_session(self, session_id: str) -> None:
        """Remove cached approvals for a session."""
        with self._lock:
            self._approvals.pop(session_id, None)

    @staticmethod
    def is_write_operation(tool_name: str) -> bool:
        """Return True if *tool_name* performs filesystem writes."""
        return tool_name in _WRITE_TOOLS


try:
    from langchain.agents.middleware.types import AgentMiddleware
    _HAS_AGENT_MIDDLEWARE = True
except ImportError:
    AgentMiddleware = object  # type: ignore
    _HAS_AGENT_MIDDLEWARE = False


class PathProtectionMiddleware(AgentMiddleware):  # type: ignore
    """Middleware wrapper that intercepts file write tool calls and checks PathProtection.

    Blocks writes to paths outside the workspace unless explicitly approved.
    Inherits from AgentMiddleware to satisfy the LangChain middleware interface.
    """

    def __init__(self, path_protection: PathProtection):
        self._protection = path_protection
        self.tools = []  # Required by AgentMiddleware interface

    @property
    def name(self) -> str:
        """Return middleware name."""
        return "path_protection"

    def wrap_model_call(self, request, handler):
        """Check file write tool calls against PathProtection."""
        response = handler(request)
        return self._check_paths(request, response)

    async def awrap_model_call(self, request, handler):
        """Async version of wrap_model_call."""
        response = await handler(request)
        return self._check_paths(request, response)

    def wrap_tool_call(self, request, handler):
        """Pass through tool calls without modification."""
        return handler(request)

    async def awrap_tool_call(self, request, handler):
        """Async pass through tool calls without modification."""
        return await handler(request)

    def _check_paths(self, request, response):
        """Check tool calls for writes outside workspace."""
        if not hasattr(response, 'tool_calls') or not response.tool_calls:
            return response

        config = getattr(request, 'config', {}) or {}
        configurable = config.get("configurable", {})
        session_id = configurable.get("thread_id", "default")

        blocked_calls = []
        allowed_calls = []

        for tc in response.tool_calls:
            tool_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")

            if not PathProtection.is_write_operation(tool_name):
                allowed_calls.append(tc)
                continue

            # Extract file path from tool args
            args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
            file_path = args.get("file_path") or args.get("path") or args.get("target", "")

            if not file_path:
                allowed_calls.append(tc)
                continue

            allowed, message = self._protection.check_path(
                file_path, session_id, operation=tool_name
            )

            if allowed:
                allowed_calls.append(tc)
            else:
                blocked_calls.append((tool_name, file_path, message))
                logger.warning(f"PathProtection blocked {tool_name} on {file_path}: {message}")

        if not blocked_calls:
            return response

        if hasattr(response, 'override'):
            return response.override(tool_calls=allowed_calls)

        return response
