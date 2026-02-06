"""LSP (Language Server Protocol) integration for AG3NT.

Provides:
- LspClient: JSON-RPC client for communicating with LSP servers
- LspServerRegistry: Definitions for 8+ language servers with auto-download
- LspManager: Lifecycle management, lazy startup, diagnostic collection
"""

from ag3nt_agent.lsp.client import LspClient
from ag3nt_agent.lsp.servers import LSP_SERVERS, LspServerConfig
from ag3nt_agent.lsp.manager import LspManager

__all__ = ["LspClient", "LSP_SERVERS", "LspServerConfig", "LspManager"]
