"""Artifact Store for AG3NT.

This module provides persistent storage for large tool outputs that would
otherwise consume excessive context window space.

Features:
- SHA256 content hashing for deduplication
- JSONL metadata ledger at ~/.ag3nt/artifacts/
- Efficient retrieval by artifact ID
- Automatic cleanup of stale artifacts

Usage:
    from ag3nt_agent.artifact_store import ArtifactStore, get_artifact_store

    store = get_artifact_store()
    artifact = store.write_artifact(
        content="large output content...",
        tool_name="shell_execute",
        source_url="/path/to/file",
    )
    print(f"Stored as artifact {artifact.artifact_id}")

    # Retrieve later
    content = store.read_artifact(artifact.artifact_id)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

logger = logging.getLogger(__name__)

# Default storage location
ARTIFACTS_DIR = Path.home() / ".ag3nt" / "artifacts"
METADATA_FILE = ARTIFACTS_DIR / "metadata.jsonl"
CONTENT_DIR = ARTIFACTS_DIR / "content"

# Artifact settings
MAX_ARTIFACT_AGE_DAYS = 30  # Artifacts older than this may be cleaned up
MAX_ARTIFACT_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB max per artifact


@dataclass
class ArtifactMeta:
    """Metadata for a stored artifact.

    Attributes:
        artifact_id: Unique identifier (SHA256 prefix + timestamp)
        tool_name: Name of the tool that produced this output
        source_url: Optional source URL or path
        content_hash: SHA256 hash of the content
        size_bytes: Size of the content in bytes
        created_at: ISO timestamp of creation
        session_id: Optional session ID for scoping
        tags: Optional tags for categorization
    """

    artifact_id: str
    tool_name: str
    content_hash: str
    size_bytes: int
    created_at: str
    source_url: str | None = None
    session_id: str | None = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArtifactMeta:
        """Create from dictionary."""
        return cls(
            artifact_id=data["artifact_id"],
            tool_name=data["tool_name"],
            content_hash=data["content_hash"],
            size_bytes=data["size_bytes"],
            created_at=data["created_at"],
            source_url=data.get("source_url"),
            session_id=data.get("session_id"),
            tags=data.get("tags", []),
        )


class ArtifactStore:
    """Persistent storage for large tool outputs.

    Thread-safe artifact storage with content-addressable hashing.
    Artifacts are stored as files with a JSONL metadata ledger.
    """

    def __init__(
        self,
        artifacts_dir: Path | str | None = None,
        max_age_days: int = MAX_ARTIFACT_AGE_DAYS,
        max_size_bytes: int = MAX_ARTIFACT_SIZE_BYTES,
    ) -> None:
        """Initialize the artifact store.

        Args:
            artifacts_dir: Directory for artifact storage (default: ~/.ag3nt/artifacts)
            max_age_days: Maximum age of artifacts before cleanup eligibility
            max_size_bytes: Maximum size per artifact
        """
        self._artifacts_dir = Path(artifacts_dir) if artifacts_dir else ARTIFACTS_DIR
        self._content_dir = self._artifacts_dir / "content"
        self._metadata_file = self._artifacts_dir / "metadata.jsonl"
        self._max_age_days = max_age_days
        self._max_size_bytes = max_size_bytes
        self._lock = threading.Lock()
        self._metadata_cache: dict[str, ArtifactMeta] = {}
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Ensure storage directories and metadata are initialized."""
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return

            self._artifacts_dir.mkdir(parents=True, exist_ok=True)
            self._content_dir.mkdir(parents=True, exist_ok=True)

            # Load existing metadata
            if self._metadata_file.exists():
                self._load_metadata()

            self._initialized = True

    def _load_metadata(self) -> None:
        """Load metadata from JSONL file."""
        try:
            with open(self._metadata_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        meta = ArtifactMeta.from_dict(data)
                        self._metadata_cache[meta.artifact_id] = meta
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Skipping invalid metadata line: {e}")
        except OSError as e:
            logger.warning(f"Failed to load artifact metadata: {e}")

    def _append_metadata(self, meta: ArtifactMeta) -> None:
        """Append metadata entry to JSONL file."""
        with self._lock:
            with open(self._metadata_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(meta.to_dict()) + "\n")
            self._metadata_cache[meta.artifact_id] = meta

    def _generate_artifact_id(self, content_hash: str) -> str:
        """Generate a unique artifact ID from content hash and timestamp."""
        timestamp = int(time.time() * 1000)
        return f"{content_hash[:12]}_{timestamp:x}"

    def _compute_hash(self, content: str | bytes) -> str:
        """Compute SHA256 hash of content."""
        if isinstance(content, str):
            content = content.encode("utf-8")
        return hashlib.sha256(content).hexdigest()

    def _get_content_path(self, artifact_id: str) -> Path:
        """Get the file path for artifact content."""
        return self._content_dir / f"{artifact_id}.txt"

    def write_artifact(
        self,
        content: str,
        tool_name: str,
        source_url: str | None = None,
        session_id: str | None = None,
        tags: list[str] | None = None,
    ) -> ArtifactMeta:
        """Write an artifact to storage.

        Args:
            content: The artifact content to store
            tool_name: Name of the tool that produced this output
            source_url: Optional source URL or file path
            session_id: Optional session ID for scoping
            tags: Optional tags for categorization

        Returns:
            ArtifactMeta with the artifact's metadata

        Raises:
            ValueError: If content exceeds max size
        """
        self._ensure_initialized()

        content_bytes = content.encode("utf-8")
        if len(content_bytes) > self._max_size_bytes:
            raise ValueError(
                f"Artifact size ({len(content_bytes)} bytes) exceeds maximum "
                f"({self._max_size_bytes} bytes)"
            )

        content_hash = self._compute_hash(content_bytes)
        artifact_id = self._generate_artifact_id(content_hash)

        # Check for duplicate by hash
        for existing in self._metadata_cache.values():
            if existing.content_hash == content_hash:
                logger.debug(f"Artifact with hash {content_hash[:12]} already exists")
                return existing

        # Write content file
        content_path = self._get_content_path(artifact_id)
        with open(content_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Create and store metadata
        meta = ArtifactMeta(
            artifact_id=artifact_id,
            tool_name=tool_name,
            content_hash=content_hash,
            size_bytes=len(content_bytes),
            created_at=datetime.now(UTC).isoformat(),
            source_url=source_url,
            session_id=session_id,
            tags=tags or [],
        )
        self._append_metadata(meta)

        logger.info(f"Stored artifact {artifact_id} ({len(content_bytes)} bytes)")
        return meta

    def read_artifact(self, artifact_id: str) -> str | None:
        """Read artifact content by ID.

        Args:
            artifact_id: The artifact ID to retrieve

        Returns:
            The artifact content, or None if not found
        """
        self._ensure_initialized()

        if artifact_id not in self._metadata_cache:
            logger.warning(f"Artifact {artifact_id} not found in metadata")
            return None

        content_path = self._get_content_path(artifact_id)
        if not content_path.exists():
            logger.warning(f"Artifact file missing for {artifact_id}")
            return None

        try:
            with open(content_path, encoding="utf-8") as f:
                return f.read()
        except OSError as e:
            logger.error(f"Failed to read artifact {artifact_id}: {e}")
            return None

    def get_metadata(self, artifact_id: str) -> ArtifactMeta | None:
        """Get artifact metadata by ID."""
        self._ensure_initialized()
        return self._metadata_cache.get(artifact_id)

    def list_artifacts(
        self,
        tool_name: str | None = None,
        session_id: str | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[ArtifactMeta]:
        """List artifacts with optional filtering.

        Args:
            tool_name: Filter by tool name
            session_id: Filter by session ID
            tags: Filter by tags (any match)
            limit: Maximum number of results

        Returns:
            List of matching ArtifactMeta objects
        """
        self._ensure_initialized()

        results = []
        for meta in self._metadata_cache.values():
            if tool_name and meta.tool_name != tool_name:
                continue
            if session_id and meta.session_id != session_id:
                continue
            if tags and not any(t in meta.tags for t in tags):
                continue
            results.append(meta)
            if len(results) >= limit:
                break

        return sorted(results, key=lambda m: m.created_at, reverse=True)

    def delete_artifact(self, artifact_id: str) -> bool:
        """Delete an artifact by ID.

        Args:
            artifact_id: The artifact ID to delete

        Returns:
            True if deleted, False if not found
        """
        self._ensure_initialized()

        if artifact_id not in self._metadata_cache:
            return False

        # Delete content file
        content_path = self._get_content_path(artifact_id)
        try:
            if content_path.exists():
                content_path.unlink()
        except OSError as e:
            logger.warning(f"Failed to delete artifact file {artifact_id}: {e}")

        # Remove from cache (metadata file is append-only, cleanup rewrites it)
        with self._lock:
            del self._metadata_cache[artifact_id]

        logger.info(f"Deleted artifact {artifact_id}")
        return True

    def cleanup_stale(self, max_age_days: int | None = None) -> int:
        """Remove artifacts older than max_age_days.

        Args:
            max_age_days: Override default max age

        Returns:
            Number of artifacts deleted
        """
        self._ensure_initialized()
        max_age = max_age_days or self._max_age_days
        cutoff = datetime.now(UTC).timestamp() - (max_age * 24 * 60 * 60)
        deleted = 0

        stale_ids = []
        for artifact_id, meta in self._metadata_cache.items():
            try:
                created = datetime.fromisoformat(meta.created_at).timestamp()
                if created < cutoff:
                    stale_ids.append(artifact_id)
            except ValueError:
                continue

        for artifact_id in stale_ids:
            if self.delete_artifact(artifact_id):
                deleted += 1

        # Rewrite metadata file without deleted entries
        if deleted > 0:
            self._rewrite_metadata()

        logger.info(f"Cleaned up {deleted} stale artifacts")
        return deleted

    def _rewrite_metadata(self) -> None:
        """Rewrite metadata file with current cache contents."""
        with self._lock:
            with open(self._metadata_file, "w", encoding="utf-8") as f:
                for meta in self._metadata_cache.values():
                    f.write(json.dumps(meta.to_dict()) + "\n")

    def get_stats(self) -> dict[str, Any]:
        """Get storage statistics."""
        self._ensure_initialized()
        total_size = sum(m.size_bytes for m in self._metadata_cache.values())
        return {
            "total_artifacts": len(self._metadata_cache),
            "total_size_bytes": total_size,
            "artifacts_dir": str(self._artifacts_dir),
        }


# Global artifact store instance
_artifact_store: ArtifactStore | None = None


def get_artifact_store() -> ArtifactStore:
    """Get the global artifact store instance."""
    global _artifact_store
    if _artifact_store is None:
        _artifact_store = ArtifactStore()
    return _artifact_store


def reset_artifact_store() -> None:
    """Reset the global artifact store (for testing)."""
    global _artifact_store
    _artifact_store = None

