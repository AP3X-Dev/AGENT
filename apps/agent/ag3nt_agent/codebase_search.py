"""Semantic codebase search tool for AG3NT.

This module provides semantic code search using embeddings and FAISS.
Code is chunked by functions/classes and indexed for natural language queries.

Features:
- Lazy indexing: Index is built on first use
- Persistent index: Stored in ~/.ag3nt/codebase_index/
- Smart chunking: Extracts functions, classes, and logical code blocks
- Incremental updates: Re-indexes only changed files

Usage:
    from ag3nt_agent.codebase_search import codebase_search, get_codebase_search_tool

    # Direct search
    result = codebase_search("authentication middleware", path="/workspace/project")

    # Get as LangChain tool
    tool = get_codebase_search_tool()
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Index storage location
INDEX_DIR = Path.home() / ".ag3nt" / "codebase_index"
INDEX_FILE = INDEX_DIR / "faiss.index"
METADATA_FILE = INDEX_DIR / "metadata.json"

# Indexing configuration
MAX_CHUNK_SIZE = 1500  # Characters per chunk
MIN_CHUNK_SIZE = 50  # Minimum chunk size to index
MAX_FILE_SIZE = 500_000  # 500KB max file size to index
DEFAULT_TOP_K = 10

# Directories to skip
SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".env", ".pytest_cache", ".mypy_cache", ".tox",
    "dist", "build", ".eggs", ".next", ".nuxt",
    "coverage", ".coverage", "htmlcov",
}

# File extensions to index
CODE_EXTENSIONS = {
    # Python
    ".py", ".pyi", ".pyw",
    # JavaScript/TypeScript
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    # Web
    ".html", ".css", ".scss", ".sass", ".less",
    # Data formats
    ".json", ".yaml", ".yml", ".toml", ".xml",
    # Other languages
    ".java", ".kt", ".scala", ".go", ".rs", ".rb",
    ".php", ".swift", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".fs", ".r", ".sql", ".sh", ".bash",
    # Config/docs
    ".md", ".rst", ".txt", ".cfg", ".ini",
}


@dataclass
class CodeChunk:
    """A chunk of code with metadata."""
    content: str
    file_path: str
    start_line: int
    end_line: int
    chunk_type: str  # "function", "class", "block", "file"
    name: str | None = None  # Function/class name if applicable


def _get_workspace_root() -> Path:
    """Get the default workspace root directory."""
    workspace = Path.home() / ".ag3nt" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _resolve_path(path: str | None) -> Path:
    """Resolve a path, handling virtual paths."""
    if path is None:
        return _get_workspace_root()
    if path.startswith("/workspace/"):
        return _get_workspace_root() / path[11:]
    elif path.startswith("/"):
        return _get_workspace_root() / path[1:]
    return Path(path)


def _compute_file_hash(file_path: Path) -> str:
    """Compute hash of file for change detection."""
    hasher = hashlib.md5()
    hasher.update(str(file_path).encode())
    try:
        hasher.update(str(file_path.stat().st_mtime).encode())
        hasher.update(str(file_path.stat().st_size).encode())
    except OSError:
        pass
    return hasher.hexdigest()


def _should_index_file(file_path: Path) -> bool:
    """Check if a file should be indexed."""
    # Check extension
    if file_path.suffix.lower() not in CODE_EXTENSIONS:
        return False

    # Check file size
    try:
        if file_path.stat().st_size > MAX_FILE_SIZE:
            return False
    except OSError:
        return False

    # Check if in skip directory
    for part in file_path.parts:
        if part in SKIP_DIRS or part.startswith("."):
            return False

    return True


def _extract_python_chunks(content: str, file_path: str) -> list[CodeChunk]:
    """Extract chunks from Python code."""
    chunks = []
    lines = content.splitlines()

    # Simple regex-based extraction (tree-sitter would be better but adds dependency)
    function_pattern = re.compile(r'^(async\s+)?def\s+(\w+)\s*\(')
    class_pattern = re.compile(r'^class\s+(\w+)\s*[:\(]')

    current_indent = 0
    current_chunk_start = 0
    current_chunk_type = "block"
    current_chunk_name = None

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        indent = len(line) - len(stripped) if stripped else current_indent

        # Check for function definition
        func_match = function_pattern.match(stripped)
        if func_match and indent == 0:
            # Save previous chunk if exists
            if i > current_chunk_start:
                chunk_content = "\n".join(lines[current_chunk_start:i])
                if len(chunk_content.strip()) >= MIN_CHUNK_SIZE:
                    chunks.append(CodeChunk(
                        content=chunk_content,
                        file_path=file_path,
                        start_line=current_chunk_start + 1,
                        end_line=i,
                        chunk_type=current_chunk_type,
                        name=current_chunk_name,
                    ))
            current_chunk_start = i
            current_chunk_type = "function"
            current_chunk_name = func_match.group(2)
            continue

        # Check for class definition
        class_match = class_pattern.match(stripped)
        if class_match and indent == 0:
            if i > current_chunk_start:
                chunk_content = "\n".join(lines[current_chunk_start:i])
                if len(chunk_content.strip()) >= MIN_CHUNK_SIZE:
                    chunks.append(CodeChunk(
                        content=chunk_content,
                        file_path=file_path,
                        start_line=current_chunk_start + 1,
                        end_line=i,
                        chunk_type=current_chunk_type,
                        name=current_chunk_name,
                    ))
            current_chunk_start = i
            current_chunk_type = "class"
            current_chunk_name = class_match.group(1)

    # Add final chunk
    if current_chunk_start < len(lines):
        chunk_content = "\n".join(lines[current_chunk_start:])
        if len(chunk_content.strip()) >= MIN_CHUNK_SIZE:
            chunks.append(CodeChunk(
                content=chunk_content,
                file_path=file_path,
                start_line=current_chunk_start + 1,
                end_line=len(lines),
                chunk_type=current_chunk_type,
                name=current_chunk_name,
            ))

    return chunks


def _extract_js_chunks(content: str, file_path: str) -> list[CodeChunk]:
    """Extract chunks from JavaScript/TypeScript code."""
    chunks = []
    lines = content.splitlines()

    # Patterns for JS/TS
    function_pattern = re.compile(r'^(export\s+)?(async\s+)?function\s+(\w+)')
    arrow_pattern = re.compile(r'^(export\s+)?(const|let|var)\s+(\w+)\s*=\s*(async\s*)?\(')
    class_pattern = re.compile(r'^(export\s+)?(abstract\s+)?class\s+(\w+)')

    current_chunk_start = 0
    current_chunk_type = "block"
    current_chunk_name = None
    brace_depth = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Track brace depth for determining chunk boundaries
        brace_depth += stripped.count("{") - stripped.count("}")

        # Only look for new definitions at depth 0
        if brace_depth <= 1:
            func_match = function_pattern.match(stripped)
            arrow_match = arrow_pattern.match(stripped)
            class_match = class_pattern.match(stripped)

            if func_match or arrow_match or class_match:
                # Save previous chunk
                if i > current_chunk_start:
                    chunk_content = "\n".join(lines[current_chunk_start:i])
                    if len(chunk_content.strip()) >= MIN_CHUNK_SIZE:
                        chunks.append(CodeChunk(
                            content=chunk_content,
                            file_path=file_path,
                            start_line=current_chunk_start + 1,
                            end_line=i,
                            chunk_type=current_chunk_type,
                            name=current_chunk_name,
                        ))

                current_chunk_start = i
                if class_match:
                    current_chunk_type = "class"
                    current_chunk_name = class_match.group(3)
                else:
                    current_chunk_type = "function"
                    current_chunk_name = (func_match.group(3) if func_match
                                         else arrow_match.group(3) if arrow_match
                                         else None)

    # Add final chunk
    if current_chunk_start < len(lines):
        chunk_content = "\n".join(lines[current_chunk_start:])
        if len(chunk_content.strip()) >= MIN_CHUNK_SIZE:
            chunks.append(CodeChunk(
                content=chunk_content,
                file_path=file_path,
                start_line=current_chunk_start + 1,
                end_line=len(lines),
                chunk_type=current_chunk_type,
                name=current_chunk_name,
            ))

    return chunks


def _extract_generic_chunks(content: str, file_path: str) -> list[CodeChunk]:
    """Extract chunks from generic code files by splitting on blank lines."""
    chunks = []
    lines = content.splitlines()

    current_chunk = []
    current_start = 0

    for i, line in enumerate(lines):
        if line.strip():
            if not current_chunk:
                current_start = i
            current_chunk.append(line)
        elif current_chunk:
            # Blank line - save chunk if big enough
            chunk_content = "\n".join(current_chunk)
            if len(chunk_content) >= MIN_CHUNK_SIZE:
                # Split large chunks
                if len(chunk_content) > MAX_CHUNK_SIZE:
                    for j in range(0, len(chunk_content), MAX_CHUNK_SIZE):
                        sub_content = chunk_content[j:j + MAX_CHUNK_SIZE]
                        if len(sub_content) >= MIN_CHUNK_SIZE:
                            chunks.append(CodeChunk(
                                content=sub_content,
                                file_path=file_path,
                                start_line=current_start + 1,
                                end_line=i,
                                chunk_type="block",
                                name=None,
                            ))
                else:
                    chunks.append(CodeChunk(
                        content=chunk_content,
                        file_path=file_path,
                        start_line=current_start + 1,
                        end_line=i,
                        chunk_type="block",
                        name=None,
                    ))
            current_chunk = []

    # Handle last chunk
    if current_chunk:
        chunk_content = "\n".join(current_chunk)
        if len(chunk_content) >= MIN_CHUNK_SIZE:
            chunks.append(CodeChunk(
                content=chunk_content,
                file_path=file_path,
                start_line=current_start + 1,
                end_line=len(lines),
                chunk_type="block",
                name=None,
            ))

    # If no chunks extracted, treat whole file as one chunk
    if not chunks and len(content.strip()) >= MIN_CHUNK_SIZE:
        chunks.append(CodeChunk(
            content=content[:MAX_CHUNK_SIZE],
            file_path=file_path,
            start_line=1,
            end_line=len(lines),
            chunk_type="file",
            name=Path(file_path).name,
        ))

    return chunks


def _extract_chunks(content: str, file_path: str) -> list[CodeChunk]:
    """Extract chunks from a file based on its type."""
    suffix = Path(file_path).suffix.lower()

    if suffix in {".py", ".pyi", ".pyw"}:
        return _extract_python_chunks(content, file_path)
    elif suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
        return _extract_js_chunks(content, file_path)
    else:
        return _extract_generic_chunks(content, file_path)


class CodebaseIndex:
    """Manages the codebase semantic search index."""

    def __init__(self, root_path: Path):
        self.root_path = root_path
        self._index = None
        self._metadata: list[dict] = []
        self._embeddings = None
        self._file_hashes: dict[str, str] = {}
        self._initialized = False

    def _get_embeddings(self):
        """Get embeddings model."""
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY")

        if api_key:
            try:
                from langchain_openai import OpenAIEmbeddings

                base_url = os.environ.get("OPENAI_BASE_URL") or os.environ.get(
                    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
                )

                return OpenAIEmbeddings(
                    model="text-embedding-3-small",
                    openai_api_key=api_key,
                    openai_api_base=base_url,
                )
            except ImportError:
                logger.warning("langchain-openai not installed")
            except Exception as e:
                logger.warning(f"Failed to init OpenAI embeddings: {e}")

        return None

    def _load_index(self) -> bool:
        """Load existing index from disk."""
        if not INDEX_FILE.exists() or not METADATA_FILE.exists():
            return False

        try:
            import faiss

            self._index = faiss.read_index(str(INDEX_FILE))

            with open(METADATA_FILE) as f:
                data = json.load(f)
                self._metadata = data.get("chunks", [])
                self._file_hashes = data.get("file_hashes", {})
                stored_root = data.get("root_path")

                # Check if index is for same root
                if stored_root != str(self.root_path):
                    logger.info(f"Index root changed: {stored_root} -> {self.root_path}")
                    return False

            logger.info(f"Loaded codebase index with {len(self._metadata)} chunks")
            return True
        except Exception as e:
            logger.warning(f"Failed to load index: {e}")
            return False

    def _save_index(self) -> None:
        """Save index to disk."""
        try:
            import faiss

            INDEX_DIR.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self._index, str(INDEX_FILE))

            with open(METADATA_FILE, "w") as f:
                json.dump({
                    "chunks": self._metadata,
                    "file_hashes": self._file_hashes,
                    "root_path": str(self.root_path),
                }, f)

            logger.info(f"Saved codebase index with {len(self._metadata)} chunks")
        except Exception as e:
            logger.error(f"Failed to save index: {e}")

    def _collect_files(self) -> list[Path]:
        """Collect all files to index."""
        files = []
        for file_path in self.root_path.rglob("*"):
            if file_path.is_file() and _should_index_file(file_path):
                files.append(file_path)
        return files

    def _build_index(self) -> None:
        """Build or rebuild the index."""
        import faiss
        import numpy as np

        self._embeddings = self._get_embeddings()
        if not self._embeddings:
            logger.warning("No embeddings available for codebase search")
            return

        files = self._collect_files()
        logger.info(f"Indexing {len(files)} files in {self.root_path}")

        all_chunks: list[dict] = []
        new_file_hashes: dict[str, str] = {}

        for file_path in files:
            rel_path = str(file_path.relative_to(self.root_path)).replace("\\", "/")
            file_hash = _compute_file_hash(file_path)
            new_file_hashes[rel_path] = file_hash

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                chunks = _extract_chunks(content, rel_path)

                for chunk in chunks:
                    all_chunks.append({
                        "content": chunk.content,
                        "file_path": chunk.file_path,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "chunk_type": chunk.chunk_type,
                        "name": chunk.name,
                    })
            except Exception as e:
                logger.debug(f"Failed to process {file_path}: {e}")

        if not all_chunks:
            logger.warning("No chunks extracted from codebase")
            return

        # Generate embeddings
        logger.info(f"Generating embeddings for {len(all_chunks)} chunks...")
        texts = [c["content"] for c in all_chunks]

        try:
            from ag3nt_agent.embedding_cache import get_embedding_cache
            cache = get_embedding_cache()

            def embed_batch(batch: list[str]) -> list[list[float]]:
                return self._embeddings.embed_documents(batch)

            embeddings = cache.get_or_compute_batch(
                texts, embed_batch, provider="openai", model="text-embedding-3-small"
            )
        except ImportError:
            embeddings = self._embeddings.embed_documents(texts)

        embeddings_np = np.array(embeddings, dtype=np.float32)

        # Create FAISS index
        dimension = embeddings_np.shape[1]
        self._index = faiss.IndexFlatL2(dimension)
        self._index.add(embeddings_np)

        self._metadata = all_chunks
        self._file_hashes = new_file_hashes

        # Save to disk
        self._save_index()

    def ensure_initialized(self) -> bool:
        """Ensure index is ready, building if needed."""
        if self._initialized:
            return self._index is not None

        self._initialized = True
        self._embeddings = self._get_embeddings()

        if not self._embeddings:
            logger.warning("No embeddings available - codebase search disabled")
            return False

        # Try loading existing index
        if self._load_index():
            # Check if files changed
            files = self._collect_files()
            needs_rebuild = False

            for file_path in files:
                rel_path = str(file_path.relative_to(self.root_path)).replace("\\", "/")
                file_hash = _compute_file_hash(file_path)

                if rel_path not in self._file_hashes:
                    needs_rebuild = True
                    break
                if self._file_hashes[rel_path] != file_hash:
                    needs_rebuild = True
                    break

            if not needs_rebuild:
                return True

            logger.info("Files changed, rebuilding index...")

        # Build fresh index
        try:
            self._build_index()
        except ImportError as e:
            logger.warning("Codebase indexing unavailable (missing dependency): %s", e)
            return False
        return self._index is not None

    def search(self, query: str, top_k: int = DEFAULT_TOP_K) -> list[dict]:
        """Search for code matching the query."""
        if not self.ensure_initialized():
            return []

        import numpy as np

        try:
            query_embedding = self._embeddings.embed_query(query)
            query_np = np.array([query_embedding], dtype=np.float32)

            k = min(top_k, len(self._metadata))
            distances, indices = self._index.search(query_np, k)

            results = []
            for i, idx in enumerate(indices[0]):
                if idx < 0 or idx >= len(self._metadata):
                    continue

                chunk = self._metadata[idx].copy()
                chunk["score"] = float(1 / (1 + distances[0][i]))
                chunk["rank"] = i + 1
                results.append(chunk)

            return results
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []


# Cache of indexes by root path
_indexes: dict[str, CodebaseIndex] = {}


def _get_index(root_path: Path) -> CodebaseIndex:
    """Get or create index for a root path."""
    key = str(root_path)
    if key not in _indexes:
        _indexes[key] = CodebaseIndex(root_path)
    return _indexes[key]


def codebase_search(
    query: str,
    path: str | None = None,
    file_types: list[str] | None = None,
    max_results: int = DEFAULT_TOP_K,
) -> dict[str, Any]:
    """Semantic search over codebase using embeddings.

    Searches for code snippets matching a natural language query.
    The codebase is indexed on first use and cached for subsequent searches.

    Args:
        query: Natural language description of code to find
        path: Directory to search (default: workspace root)
        file_types: Filter by extensions (e.g., [".py", ".ts"]). Optional.
        max_results: Maximum results to return (default: 10)

    Returns:
        Dictionary with:
        - results: List of matching code snippets with metadata
        - count: Number of results
        - search_root: Directory that was searched
    """
    root_path = _resolve_path(path)

    if not root_path.exists():
        return {
            "results": [],
            "count": 0,
            "error": f"Path does not exist: {path}",
        }

    if not root_path.is_dir():
        return {
            "results": [],
            "count": 0,
            "error": f"Path is not a directory: {path}",
        }

    index = _get_index(root_path)
    results = index.search(query, top_k=max_results * 2)  # Get extra for filtering

    # Filter by file types if specified
    if file_types:
        normalized_types = {t if t.startswith(".") else f".{t}" for t in file_types}
        results = [
            r for r in results
            if Path(r["file_path"]).suffix.lower() in normalized_types
        ]

    results = results[:max_results]

    return {
        "results": results,
        "count": len(results),
        "query": query,
        "search_root": str(root_path),
    }


@tool
def codebase_search_tool(
    query: str,
    path: str | None = None,
    file_types: list[str] | None = None,
    max_results: int = DEFAULT_TOP_K,
) -> dict[str, Any]:
    """Semantic search over codebase using embeddings.

    Search for code using natural language. The codebase is automatically
    indexed and kept up-to-date. Use this when you don't know exact file
    locations or want to find code by description.

    Args:
        query: Natural language description of what you're looking for.
               Examples: "authentication middleware", "database connection",
               "error handling for API calls", "unit tests for user model"
        path: Directory to search (default: workspace root)
        file_types: Optional filter by file extensions (e.g., [".py", ".ts"])
        max_results: Maximum results to return (default: 10)

    Returns:
        List of relevant code snippets with file paths, line numbers, and scores.

    Examples:
        # Find authentication code
        codebase_search_tool("user authentication and login")

        # Find database models
        codebase_search_tool("database models and schemas", file_types=[".py"])

        # Find React components
        codebase_search_tool("form validation components", file_types=[".tsx"])

        # Find error handling
        codebase_search_tool("exception handling and error responses")
    """
    return codebase_search(
        query=query,
        path=path,
        file_types=file_types,
        max_results=max_results,
    )


def get_codebase_search_tool():
    """Get the codebase search tool for the agent.

    Returns:
        LangChain tool for semantic codebase search
    """
    return codebase_search_tool


def clear_index(path: str | None = None) -> dict[str, Any]:
    """Clear the codebase index for a path.

    Args:
        path: Directory to clear index for (default: workspace root)

    Returns:
        Success status
    """
    root_path = _resolve_path(path)
    key = str(root_path)

    if key in _indexes:
        del _indexes[key]

    # Remove index files
    try:
        if INDEX_FILE.exists():
            INDEX_FILE.unlink()
        if METADATA_FILE.exists():
            METADATA_FILE.unlink()
        return {"success": True, "message": "Index cleared"}
    except Exception as e:
        return {"success": False, "error": str(e)}
