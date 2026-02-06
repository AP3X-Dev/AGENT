"""LSP server definitions and installation helpers.

Provides a registry of language server configurations and utilities for
detecting, installing, and matching servers to source files.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("ag3nt.lsp.servers")


@dataclass
class LspServerConfig:
    """Configuration for an LSP server."""

    name: str
    """Human-readable name."""

    language_ids: list[str]
    """LSP language identifiers this server handles."""

    file_extensions: list[str]
    """File extensions (with leading dot) this server handles."""

    command: list[str]
    """Command and arguments to start the server."""

    install_command: str | None = None
    """Shell command to install the server binary if missing."""

    auto_install: bool = True
    """Whether to automatically install when missing."""

    init_options: dict | None = None
    """Optional ``initializationOptions`` to send during LSP initialize."""


# ---------------------------------------------------------------------------
# Server registry
# ---------------------------------------------------------------------------

LSP_SERVERS: list[LspServerConfig] = [
    LspServerConfig(
        name="TypeScript/JavaScript",
        language_ids=["typescript", "typescriptreact", "javascript", "javascriptreact"],
        file_extensions=[".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"],
        command=["typescript-language-server", "--stdio"],
        install_command="npm install -g typescript-language-server typescript",
        auto_install=True,
    ),
    LspServerConfig(
        name="Python (Pyright)",
        language_ids=["python"],
        file_extensions=[".py", ".pyi"],
        command=["pyright-langserver", "--stdio"],
        install_command="pip install pyright",
        auto_install=True,
    ),
    LspServerConfig(
        name="Go (gopls)",
        language_ids=["go"],
        file_extensions=[".go"],
        command=["gopls", "serve"],
        install_command="go install golang.org/x/tools/gopls@latest",
        auto_install=True,
    ),
    LspServerConfig(
        name="Rust (rust-analyzer)",
        language_ids=["rust"],
        file_extensions=[".rs"],
        command=["rust-analyzer"],
        install_command=None,
        auto_install=False,
    ),
    LspServerConfig(
        name="C/C++ (clangd)",
        language_ids=["c", "cpp"],
        file_extensions=[".c", ".cpp", ".cc", ".h", ".hpp", ".cxx"],
        command=["clangd"],
        install_command=None,
        auto_install=False,
    ),
    LspServerConfig(
        name="Ruby (RuboCop)",
        language_ids=["ruby"],
        file_extensions=[".rb", ".rake"],
        command=["rubocop", "--lsp"],
        install_command="gem install rubocop",
        auto_install=True,
    ),
    LspServerConfig(
        name="PHP (Intelephense)",
        language_ids=["php"],
        file_extensions=[".php"],
        command=["intelephense", "--stdio"],
        install_command="npm install -g intelephense",
        auto_install=True,
    ),
    LspServerConfig(
        name="Bash",
        language_ids=["shellscript"],
        file_extensions=[".sh", ".bash", ".zsh"],
        command=["bash-language-server", "start"],
        install_command="npm install -g bash-language-server",
        auto_install=True,
    ),
    LspServerConfig(
        name="CSS/SCSS",
        language_ids=["css", "scss", "less"],
        file_extensions=[".css", ".scss", ".less"],
        command=["vscode-css-language-server", "--stdio"],
        install_command="npm install -g vscode-langservers-extracted",
        auto_install=True,
    ),
    LspServerConfig(
        name="HTML",
        language_ids=["html"],
        file_extensions=[".html", ".htm"],
        command=["vscode-html-language-server", "--stdio"],
        install_command="npm install -g vscode-langservers-extracted",
        auto_install=True,
    ),
]

# ---------------------------------------------------------------------------
# Extension -> language ID mapping
# ---------------------------------------------------------------------------

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".js": "javascript",
    ".jsx": "javascriptreact",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".rake": "ruby",
    ".php": "php",
    ".sh": "shellscript",
    ".bash": "shellscript",
    ".zsh": "shellscript",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".html": "html",
    ".htm": "html",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".xml": "xml",
    ".toml": "toml",
    ".java": "java",
    ".kt": "kotlin",
    ".swift": "swift",
    ".dart": "dart",
    ".lua": "lua",
    ".zig": "zig",
}

# Pre-built lookup: language_id -> LspServerConfig
_LANGUAGE_TO_SERVER: dict[str, LspServerConfig] = {}
for _server in LSP_SERVERS:
    for _lang_id in _server.language_ids:
        _LANGUAGE_TO_SERVER[_lang_id] = _server

# Pre-built lookup: extension -> LspServerConfig
_EXTENSION_TO_SERVER: dict[str, LspServerConfig] = {}
for _server in LSP_SERVERS:
    for _ext in _server.file_extensions:
        _EXTENSION_TO_SERVER[_ext] = _server


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def find_server_for_file(file_path: str) -> LspServerConfig | None:
    """Find the appropriate LSP server config for a file based on its extension.

    Args:
        file_path: Path to the source file.

    Returns:
        The matching ``LspServerConfig`` or ``None`` if no server is registered
        for this file type.
    """
    ext = Path(file_path).suffix.lower()
    config = _EXTENSION_TO_SERVER.get(ext)
    if config is not None:
        return config
    # Fallback: check EXTENSION_TO_LANGUAGE in case there is a language but
    # no server configured for it.
    logger.debug("No LSP server registered for extension %s", ext)
    return None


def is_server_installed(config: LspServerConfig) -> bool:
    """Check if the LSP server binary is available on PATH.

    Args:
        config: The server configuration to check.

    Returns:
        ``True`` if the first element of ``config.command`` is found on PATH.
    """
    binary = config.command[0]
    found = shutil.which(binary) is not None
    if not found:
        logger.debug("%s binary not found on PATH: %s", config.name, binary)
    return found


async def ensure_server_installed(config: LspServerConfig) -> bool:
    """Install the LSP server if not already present.

    Runs ``config.install_command`` in a subprocess if the binary is missing
    and ``auto_install`` is enabled.

    Args:
        config: The server configuration.

    Returns:
        ``True`` if the server binary is available after this call (either
        it was already installed or installation succeeded).
    """
    if is_server_installed(config):
        return True

    if not config.auto_install or config.install_command is None:
        logger.info(
            "%s is not installed and auto-install is disabled", config.name
        )
        return False

    logger.info("Installing %s: %s", config.name, config.install_command)

    try:
        process = await asyncio.create_subprocess_exec(
            *config.install_command.split(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=120.0
        )
    except asyncio.TimeoutError:
        logger.error("Installation of %s timed out", config.name)
        return False
    except FileNotFoundError as exc:
        logger.error(
            "Installation command not found for %s: %s", config.name, exc
        )
        return False
    except OSError as exc:
        logger.error("Failed to run install command for %s: %s", config.name, exc)
        return False

    if process.returncode != 0:
        logger.error(
            "Installation of %s failed (exit %d):\n%s",
            config.name,
            process.returncode,
            stderr.decode(errors="replace").strip(),
        )
        return False

    # Verify binary is now available
    if is_server_installed(config):
        logger.info("%s installed successfully", config.name)
        return True

    logger.warning(
        "%s install command succeeded but binary still not found on PATH",
        config.name,
    )
    return False
