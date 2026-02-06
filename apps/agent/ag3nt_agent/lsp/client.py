"""JSON-RPC LSP client over stdio.

Communicates with Language Server Protocol servers using the standard
Content-Length framing over stdin/stdout of a subprocess.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("ag3nt.lsp.client")


def file_to_uri(path: str) -> str:
    """Convert a filesystem path to a file:// URI."""
    return Path(path).resolve().as_uri()


class LspClient:
    """JSON-RPC client that communicates with an LSP server subprocess via stdio."""

    def __init__(self, command: list[str], workspace_root: str) -> None:
        """Store configuration without starting the server.

        Args:
            command: Command and arguments to launch the LSP server.
            workspace_root: Absolute path to the workspace root directory.
        """
        self._command = command
        self._workspace_root = workspace_root
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._next_id: int = 1
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._diagnostics: dict[str, list[dict]] = {}
        self._diagnostics_event: dict[str, asyncio.Event] = {}
        self._running: bool = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Whether the LSP server subprocess is alive."""
        return self._running

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Spawn the LSP server subprocess and begin the reader loop."""
        if self._running:
            logger.warning("LSP client already running for %s", self._command)
            return

        logger.info("Starting LSP server: %s", " ".join(self._command))
        try:
            self._process = await asyncio.create_subprocess_exec(
                *self._command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            logger.error("LSP server binary not found: %s", self._command[0])
            return
        except OSError as exc:
            logger.error("Failed to start LSP server: %s", exc)
            return

        self._running = True
        self._reader_task = asyncio.create_task(
            self._reader_loop(), name="lsp-reader"
        )
        logger.info("LSP server started (pid=%s)", self._process.pid)

    async def stop(self) -> None:
        """Send shutdown/exit and terminate the server process."""
        if not self._running or self._process is None:
            return

        logger.info("Stopping LSP server (pid=%s)", self._process.pid)
        try:
            await self.request("shutdown", timeout=5.0)
        except Exception:
            logger.debug("Shutdown request failed, proceeding to exit")

        try:
            await self.notify("exit")
        except Exception:
            pass

        # Give the process a moment to exit cleanly
        try:
            await asyncio.wait_for(self._process.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            logger.warning("LSP server did not exit gracefully, killing")
            try:
                self._process.kill()
                await self._process.wait()
            except ProcessLookupError:
                pass

        self._running = False

        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        # Reject any pending requests
        for future in self._pending.values():
            if not future.done():
                future.set_exception(
                    ConnectionError("LSP server stopped")
                )
        self._pending.clear()

        logger.info("LSP server stopped")

    # ------------------------------------------------------------------
    # JSON-RPC transport
    # ------------------------------------------------------------------

    def _encode_message(self, body: dict) -> bytes:
        """Encode a JSON-RPC message with Content-Length header."""
        payload = json.dumps(body).encode("utf-8")
        header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
        return header + payload

    async def _send(self, message: dict) -> None:
        """Write a JSON-RPC message to the server's stdin."""
        if not self._running or self._process is None or self._process.stdin is None:
            raise ConnectionError("LSP server is not running")
        data = self._encode_message(message)
        self._process.stdin.write(data)
        await self._process.stdin.drain()

    async def request(
        self,
        method: str,
        params: dict | None = None,
        timeout: float = 10.0,
    ) -> Any:
        """Send a JSON-RPC request and wait for the response.

        Args:
            method: The LSP method name (e.g. ``textDocument/definition``).
            params: Optional parameters dict.
            timeout: Seconds to wait for the response.

        Returns:
            The ``result`` field from the JSON-RPC response.

        Raises:
            asyncio.TimeoutError: If no response arrives within *timeout*.
            ConnectionError: If the server is not running.
            RuntimeError: If the server returns a JSON-RPC error.
        """
        request_id = self._next_id
        self._next_id += 1

        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            message["params"] = params

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self._pending[request_id] = future

        try:
            await self._send(message)
            result = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            logger.warning("Request %s (id=%d) timed out", method, request_id)
            raise
        except Exception:
            self._pending.pop(request_id, None)
            raise

        return result

    async def notify(self, method: str, params: dict | None = None) -> None:
        """Send a JSON-RPC notification (no response expected).

        Args:
            method: The LSP notification method name.
            params: Optional parameters dict.
        """
        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            message["params"] = params
        await self._send(message)

    # ------------------------------------------------------------------
    # Reader loop
    # ------------------------------------------------------------------

    async def _read_headers(self, stdout: asyncio.StreamReader) -> dict[str, str]:
        """Read LSP message headers until the blank line separator."""
        headers: dict[str, str] = {}
        while True:
            line_bytes = await stdout.readline()
            if not line_bytes:
                raise ConnectionError("LSP server stdout closed")
            line = line_bytes.decode("ascii").strip()
            if not line:
                break
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip()] = value.strip()
        return headers

    async def _reader_loop(self) -> None:
        """Continuously read JSON-RPC messages from the server's stdout."""
        assert self._process is not None
        assert self._process.stdout is not None
        stdout = self._process.stdout

        try:
            while self._running:
                try:
                    headers = await self._read_headers(stdout)
                except ConnectionError:
                    break

                content_length_str = headers.get("Content-Length")
                if content_length_str is None:
                    logger.warning("Missing Content-Length header, skipping")
                    continue

                try:
                    content_length = int(content_length_str)
                except ValueError:
                    logger.warning(
                        "Invalid Content-Length: %s", content_length_str
                    )
                    continue

                body_bytes = await stdout.readexactly(content_length)
                try:
                    message = json.loads(body_bytes.decode("utf-8"))
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from LSP server")
                    continue

                self._dispatch(message)

        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.error("LSP reader loop crashed: %s", exc, exc_info=True)
        finally:
            self._running = False
            # Reject pending requests
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(
                        ConnectionError("LSP reader loop ended")
                    )
            self._pending.clear()

    def _dispatch(self, message: dict) -> None:
        """Route an incoming JSON-RPC message to the right handler."""
        if "id" in message and "method" not in message:
            # Response to a request we sent
            request_id = message["id"]
            future = self._pending.pop(request_id, None)
            if future is None or future.done():
                logger.debug("No pending future for response id=%s", request_id)
                return
            if "error" in message:
                err = message["error"]
                future.set_exception(
                    RuntimeError(
                        f"LSP error {err.get('code')}: {err.get('message')}"
                    )
                )
            else:
                future.set_result(message.get("result"))

        elif "method" in message and "id" not in message:
            # Server notification
            self._handle_notification(message["method"], message.get("params", {}))

        elif "method" in message and "id" in message:
            # Server request — send empty response (we don't handle these)
            request_id = message["id"]
            logger.debug(
                "Ignoring server request: %s (id=%s)", message["method"], request_id
            )
            # Send back an empty result so the server doesn't hang
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": None,
            }
            if self._process and self._process.stdin:
                data = self._encode_message(response)
                self._process.stdin.write(data)
                # drain is a coroutine — schedule it on the loop
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._process.stdin.drain())
                except RuntimeError:
                    pass

    def _handle_notification(self, method: str, params: dict) -> None:
        """Handle a notification from the LSP server."""
        if method == "textDocument/publishDiagnostics":
            uri = params.get("uri", "")
            diagnostics = params.get("diagnostics", [])
            self._diagnostics[uri] = diagnostics
            event = self._diagnostics_event.get(uri)
            if event is not None:
                event.set()
            logger.debug(
                "Received %d diagnostics for %s", len(diagnostics), uri
            )
        else:
            logger.debug("Unhandled notification: %s", method)

    # ------------------------------------------------------------------
    # LSP protocol helpers
    # ------------------------------------------------------------------

    async def initialize(self) -> dict:
        """Send the ``initialize`` request to the LSP server.

        Returns:
            The server's capabilities dict.
        """
        params = {
            "processId": None,
            "rootUri": file_to_uri(self._workspace_root),
            "rootPath": self._workspace_root,
            "capabilities": {
                "textDocument": {
                    "synchronization": {
                        "dynamicRegistration": False,
                        "willSave": False,
                        "willSaveWaitUntil": False,
                        "didSave": True,
                    },
                    "completion": {
                        "dynamicRegistration": False,
                        "completionItem": {"snippetSupport": False},
                    },
                    "hover": {"dynamicRegistration": False},
                    "definition": {"dynamicRegistration": False},
                    "references": {"dynamicRegistration": False},
                    "documentSymbol": {"dynamicRegistration": False},
                    "publishDiagnostics": {
                        "relatedInformation": True,
                        "tagSupport": {"valueSet": [1, 2]},
                    },
                },
                "workspace": {
                    "symbol": {"dynamicRegistration": False},
                    "workspaceFolders": True,
                },
            },
            "workspaceFolders": [
                {
                    "uri": file_to_uri(self._workspace_root),
                    "name": Path(self._workspace_root).name,
                }
            ],
        }
        result = await self.request("initialize", params, timeout=30.0)
        await self.notify("initialized", {})
        logger.info("LSP server initialized for %s", self._workspace_root)
        return result

    async def did_open(
        self, uri: str, language_id: str, text: str
    ) -> None:
        """Notify the server that a document was opened."""
        await self.notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": language_id,
                    "version": 1,
                    "text": text,
                }
            },
        )

    async def did_change(
        self, uri: str, text: str, version: int
    ) -> None:
        """Notify the server that a document changed (full sync)."""
        await self.notify(
            "textDocument/didChange",
            {
                "textDocument": {"uri": uri, "version": version},
                "contentChanges": [{"text": text}],
            },
        )

    async def did_save(self, uri: str, text: str | None = None) -> None:
        """Notify the server that a document was saved."""
        params: dict[str, Any] = {
            "textDocument": {"uri": uri},
        }
        if text is not None:
            params["text"] = text
        await self.notify("textDocument/didSave", params)

    async def get_diagnostics(
        self, uri: str, timeout: float = 5.0
    ) -> list[dict]:
        """Wait for diagnostics for the given URI.

        If diagnostics are already cached, returns them immediately.
        Otherwise waits up to *timeout* seconds for the server to publish them.

        Returns:
            A list of LSP Diagnostic objects.
        """
        # Check if we already have diagnostics for this URI
        if uri in self._diagnostics:
            return self._diagnostics[uri]

        # Set up an event and wait for diagnostics to arrive
        if uri not in self._diagnostics_event:
            self._diagnostics_event[uri] = asyncio.Event()
        else:
            self._diagnostics_event[uri].clear()

        try:
            await asyncio.wait_for(
                self._diagnostics_event[uri].wait(), timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.debug("Timed out waiting for diagnostics on %s", uri)
            return []

        return self._diagnostics.get(uri, [])

    async def definition(
        self, uri: str, line: int, character: int
    ) -> list[dict]:
        """Request go-to-definition for a position.

        Returns:
            A list of Location objects.
        """
        result = await self.request(
            "textDocument/definition",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
            },
        )
        if result is None:
            return []
        if isinstance(result, dict):
            return [result]
        if isinstance(result, list):
            return result
        return []

    async def references(
        self, uri: str, line: int, character: int
    ) -> list[dict]:
        """Request all references for a symbol at a position.

        Returns:
            A list of Location objects.
        """
        result = await self.request(
            "textDocument/references",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
                "context": {"includeDeclaration": True},
            },
        )
        if result is None:
            return []
        if isinstance(result, list):
            return result
        return []

    async def hover(
        self, uri: str, line: int, character: int
    ) -> dict | None:
        """Request hover information for a position.

        Returns:
            A Hover object or ``None``.
        """
        result = await self.request(
            "textDocument/hover",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
            },
        )
        return result

    async def document_symbols(self, uri: str) -> list[dict]:
        """Request document symbols for a file.

        Returns:
            A list of DocumentSymbol or SymbolInformation objects.
        """
        result = await self.request(
            "textDocument/documentSymbol",
            {"textDocument": {"uri": uri}},
        )
        if result is None:
            return []
        if isinstance(result, list):
            return result
        return []

    async def workspace_symbols(self, query: str) -> list[dict]:
        """Search for symbols across the workspace.

        Args:
            query: Search query string.

        Returns:
            A list of SymbolInformation objects.
        """
        result = await self.request(
            "workspace/symbol",
            {"query": query},
        )
        if result is None:
            return []
        if isinstance(result, list):
            return result
        return []
