"""LSP lifecycle manager.

Manages LSP server lifecycles across the workspace with lazy startup:
servers are only started when the agent first touches a file of that language.
One server instance per language per workspace.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import ClassVar

from ag3nt_agent.lsp.client import LspClient, file_to_uri
from ag3nt_agent.lsp.servers import (
    EXTENSION_TO_LANGUAGE,
    LspServerConfig,
    ensure_server_installed,
    find_server_for_file,
)

logger = logging.getLogger("ag3nt.lsp.manager")

# Severity values from the LSP specification
_SEVERITY_LABELS: dict[int, str] = {
    1: "error",
    2: "warning",
    3: "info",
    4: "hint",
}


class LspManager:
    """Manages LSP server lifecycles across the workspace.

    Lazy startup: servers are only started when the agent first touches
    a file of that language.  One server instance per language per workspace.
    """

    _instance: ClassVar[LspManager | None] = None

    def __init__(self, workspace_root: str) -> None:
        self._workspace_root = str(Path(workspace_root).resolve())
        self._clients: dict[str, LspClient] = {}
        self._file_versions: dict[str, int] = {}
        self._opened_files: set[str] = set()
        # Guards concurrent start attempts for the same language
        self._start_locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------
    # Singleton access
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls, workspace_root: str | None = None) -> LspManager:
        """Return the singleton ``LspManager`` instance.

        On first call ``workspace_root`` must be provided.  Subsequent calls
        may omit it and the existing instance is returned.
        """
        if cls._instance is None:
            if workspace_root is None:
                raise ValueError(
                    "workspace_root is required on first call to get_instance"
                )
            cls._instance = cls(workspace_root)
            logger.info("LspManager created for %s", workspace_root)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (primarily for testing)."""
        cls._instance = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _language_for_file(self, file_path: str) -> str | None:
        """Resolve a file path to its LSP language identifier."""
        ext = Path(file_path).suffix.lower()
        return EXTENSION_TO_LANGUAGE.get(ext)

    def _server_key(self, config: LspServerConfig) -> str:
        """Return the dict key used in ``_clients`` for a server config.

        We key by the server *name* so that one server instance covers all
        its language IDs (e.g. typescript-language-server covers TS and JS).
        """
        return config.name

    async def _ensure_lock(self, key: str) -> asyncio.Lock:
        """Get or create a per-key asyncio lock."""
        if key not in self._start_locks:
            self._start_locks[key] = asyncio.Lock()
        return self._start_locks[key]

    # ------------------------------------------------------------------
    # Server lifecycle
    # ------------------------------------------------------------------

    async def start_for_file(self, file_path: str) -> LspClient | None:
        """Start (or return existing) LSP server for the given file.

        Detects the language from the file extension, checks if a server is
        already running, and starts one if needed (auto-installing the binary
        when appropriate).

        Args:
            file_path: Absolute path to the source file.

        Returns:
            The running ``LspClient`` or ``None`` if no server is available.
        """
        config = find_server_for_file(file_path)
        if config is None:
            return None

        key = self._server_key(config)

        # Fast path: server already running
        client = self._clients.get(key)
        if client is not None and client.is_running:
            return client

        # Slow path: start server (guarded by lock to avoid double-start)
        lock = await self._ensure_lock(key)
        async with lock:
            # Re-check after acquiring the lock
            client = self._clients.get(key)
            if client is not None and client.is_running:
                return client

            # Ensure binary is installed
            available = await ensure_server_installed(config)
            if not available:
                logger.warning(
                    "LSP server %s not available for %s", config.name, file_path
                )
                return None

            # Create and start client
            client = LspClient(
                command=config.command,
                workspace_root=self._workspace_root,
            )
            try:
                await client.start()
                if not client.is_running:
                    return None
                await client.initialize()
            except Exception as exc:
                logger.error(
                    "Failed to start LSP server %s: %s",
                    config.name,
                    exc,
                    exc_info=True,
                )
                await client.stop()
                return None

            self._clients[key] = client
            logger.info("LSP server %s is now running", config.name)
            return client

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    async def _open_file_if_needed(
        self, client: LspClient, file_path: str, content: str
    ) -> str:
        """Ensure a file is opened in the LSP server, return its URI."""
        uri = file_to_uri(file_path)
        language_id = self._language_for_file(file_path) or "plaintext"

        if uri not in self._opened_files:
            await client.did_open(uri, language_id, content)
            self._opened_files.add(uri)
            self._file_versions[uri] = 1
        return uri

    async def notify_file_changed(
        self, file_path: str, content: str
    ) -> None:
        """Notify the appropriate LSP server of a file change.

        Should be called after every edit or write operation.
        """
        client = await self.start_for_file(file_path)
        if client is None:
            return

        uri = await self._open_file_if_needed(client, file_path, content)
        version = self._file_versions.get(uri, 1) + 1
        self._file_versions[uri] = version
        await client.did_change(uri, content, version)
        await client.did_save(uri, content)

    async def get_diagnostics(
        self, file_path: str, content: str, timeout: float = 5.0
    ) -> list[dict]:
        """Open/change a file in the LSP server and wait for diagnostics.

        Args:
            file_path: Absolute path to the source file.
            content: Current file contents.
            timeout: Seconds to wait for diagnostics.

        Returns:
            A list of diagnostic dicts with keys:
            ``severity``, ``line``, ``character``, ``message``, ``source``.
        """
        client = await self.start_for_file(file_path)
        if client is None:
            return []

        uri = await self._open_file_if_needed(client, file_path, content)

        # Push the latest content
        version = self._file_versions.get(uri, 1) + 1
        self._file_versions[uri] = version
        await client.did_change(uri, content, version)
        await client.did_save(uri, content)

        # Wait for diagnostics
        raw = await client.get_diagnostics(uri, timeout=timeout)
        return self._normalize_diagnostics(raw)

    async def get_file_diagnostics(
        self, file_path: str, timeout: float = 3.0
    ) -> list[dict]:
        """Get current diagnostics for a file without triggering a change.

        Returns cached diagnostics if available, otherwise waits up to
        *timeout* seconds for the server to publish them.
        """
        config = find_server_for_file(file_path)
        if config is None:
            return []

        key = self._server_key(config)
        client = self._clients.get(key)
        if client is None or not client.is_running:
            return []

        uri = file_to_uri(file_path)
        raw = await client.get_diagnostics(uri, timeout=timeout)
        return self._normalize_diagnostics(raw)

    # ------------------------------------------------------------------
    # Code intelligence proxies
    # ------------------------------------------------------------------

    async def definition(
        self, file_path: str, line: int, character: int
    ) -> list[dict]:
        """Go-to-definition for a symbol at the given position."""
        client = await self.start_for_file(file_path)
        if client is None:
            return []
        uri = file_to_uri(file_path)
        return await client.definition(uri, line, character)

    async def references(
        self, file_path: str, line: int, character: int
    ) -> list[dict]:
        """Find all references for a symbol at the given position."""
        client = await self.start_for_file(file_path)
        if client is None:
            return []
        uri = file_to_uri(file_path)
        return await client.references(uri, line, character)

    async def hover(
        self, file_path: str, line: int, character: int
    ) -> dict | None:
        """Get hover information at the given position."""
        client = await self.start_for_file(file_path)
        if client is None:
            return None
        uri = file_to_uri(file_path)
        return await client.hover(uri, line, character)

    async def document_symbols(self, file_path: str) -> list[dict]:
        """List all symbols in a document."""
        client = await self.start_for_file(file_path)
        if client is None:
            return []
        uri = file_to_uri(file_path)
        return await client.document_symbols(uri)

    async def workspace_symbols(self, query: str) -> list[dict]:
        """Search for symbols across all running LSP servers.

        Queries all active servers and merges results.
        """
        results: list[dict] = []
        for client in self._clients.values():
            if client.is_running:
                try:
                    symbols = await client.workspace_symbols(query)
                    results.extend(symbols)
                except Exception as exc:
                    logger.debug(
                        "workspace/symbol failed on a server: %s", exc
                    )
        return results

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def stop_all(self) -> None:
        """Shutdown all running LSP servers."""
        logger.info("Stopping all LSP servers (%d active)", len(self._clients))
        tasks = [client.stop() for client in self._clients.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._clients.clear()
        self._opened_files.clear()
        self._file_versions.clear()
        logger.info("All LSP servers stopped")

    # ------------------------------------------------------------------
    # Diagnostic formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_diagnostics(raw: list[dict]) -> list[dict]:
        """Convert raw LSP diagnostics into a simplified format."""
        results: list[dict] = []
        for diag in raw:
            severity_num = diag.get("severity", 1)
            rng = diag.get("range", {})
            start = rng.get("start", {})
            results.append(
                {
                    "severity": _SEVERITY_LABELS.get(severity_num, "unknown"),
                    "line": start.get("line", 0),
                    "character": start.get("character", 0),
                    "message": diag.get("message", ""),
                    "source": diag.get("source", ""),
                }
            )
        return results

    @staticmethod
    def format_diagnostics(diagnostics: list[dict]) -> str:
        """Format diagnostics as a human-readable string.

        Suitable for appending to tool results shown to the agent.

        Example output::

            LSP Diagnostics:
              error line 42: Type 'string' is not assignable to 'number' [typescript]
              warning line 15: Unused variable 'x' [typescript]
        """
        if not diagnostics:
            return ""

        lines: list[str] = ["\n\nLSP Diagnostics:"]
        for diag in diagnostics:
            severity = diag.get("severity", "unknown")
            line = diag.get("line", 0)
            message = diag.get("message", "")
            source = diag.get("source", "")
            source_suffix = f" [{source}]" if source else ""
            lines.append(
                f"  {severity} line {line + 1}: {message}{source_suffix}"
            )
        return "\n".join(lines)
