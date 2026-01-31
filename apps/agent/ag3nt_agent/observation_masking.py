"""Observation Masking for AG3NT.

This module provides automatic masking of large tool outputs to prevent
context window overflow while preserving key information.

Features:
- Token-aware size thresholds for triggering masking
- Integration with ArtifactStore for content persistence
- Placeholder generation with artifact references
- Configurable masking strategies per tool

Usage:
    from ag3nt_agent.observation_masking import ObservationMasker

    masker = ObservationMasker(threshold_tokens=1000)
    result = masker.mask_if_needed(
        content="large tool output...",
        tool_name="shell_execute",
        source_url="/path/to/file",
    )
    if result.was_masked:
        print(f"Content stored as artifact: {result.artifact_id}")
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from langchain_core.messages import AnyMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately

from ag3nt_agent.artifact_store import ArtifactStore, get_artifact_store

if TYPE_CHECKING:
    from ag3nt_agent.artifact_store import ArtifactMeta

logger = logging.getLogger(__name__)

# Default thresholds
DEFAULT_TOKEN_THRESHOLD = 1000  # Mask outputs exceeding this token count
DEFAULT_CHAR_THRESHOLD = 4000  # Fallback char threshold
PREVIEW_LINES = 10  # Number of lines to show in preview
PREVIEW_CHARS = 500  # Max chars for preview


@dataclass
class MaskResult:
    """Result of masking operation.

    Attributes:
        content: The final content (masked or original)
        was_masked: Whether masking was applied
        artifact_id: Artifact ID if content was stored
        original_size: Original content size in chars
        masked_size: Final content size in chars
    """

    content: str
    was_masked: bool
    artifact_id: str | None = None
    original_size: int = 0
    masked_size: int = 0


class ObservationMasker:
    """Masks large tool outputs with artifact references.

    Automatically stores large outputs in the artifact store and replaces
    them with compact placeholders that reference the stored content.
    """

    def __init__(
        self,
        threshold_tokens: int = DEFAULT_TOKEN_THRESHOLD,
        threshold_chars: int = DEFAULT_CHAR_THRESHOLD,
        preview_lines: int = PREVIEW_LINES,
        preview_chars: int = PREVIEW_CHARS,
        artifact_store: ArtifactStore | None = None,
    ) -> None:
        """Initialize the observation masker.

        Args:
            threshold_tokens: Token count threshold for triggering masking
            threshold_chars: Character count fallback threshold
            preview_lines: Number of lines to include in preview
            preview_chars: Maximum characters for preview
            artifact_store: Optional artifact store (uses global if not provided)
        """
        self._threshold_tokens = threshold_tokens
        self._threshold_chars = threshold_chars
        self._preview_lines = preview_lines
        self._preview_chars = preview_chars
        self._artifact_store = artifact_store

    @property
    def artifact_store(self) -> ArtifactStore:
        """Get the artifact store instance."""
        if self._artifact_store is None:
            self._artifact_store = get_artifact_store()
        return self._artifact_store

    def _should_mask(self, content: str) -> bool:
        """Check if content should be masked based on size."""
        if len(content) < self._threshold_chars:
            return False

        # Use token count for more accurate assessment
        tokens = count_tokens_approximately([content])
        return tokens >= self._threshold_tokens

    def _create_preview(self, content: str) -> str:
        """Create a preview of the content."""
        lines = content.split("\n")
        preview_lines = lines[: self._preview_lines]
        preview = "\n".join(preview_lines)

        if len(preview) > self._preview_chars:
            preview = preview[: self._preview_chars]

        return preview

    def _create_placeholder(
        self,
        artifact_id: str,
        tool_name: str,
        original_size: int,
        preview: str,
    ) -> str:
        """Create a placeholder message with artifact reference."""
        return f"""[Output stored as artifact: {artifact_id}]

Tool: {tool_name}
Original size: {original_size:,} characters
Preview:
---
{preview}
---

To retrieve the full output, use: read_artifact("{artifact_id}")"""

    def mask_if_needed(
        self,
        content: str,
        tool_name: str,
        source_url: str | None = None,
        session_id: str | None = None,
        tags: list[str] | None = None,
    ) -> MaskResult:
        """Mask content if it exceeds thresholds.

        Args:
            content: The tool output content
            tool_name: Name of the tool that produced this output
            source_url: Optional source URL or path
            session_id: Optional session ID for scoping
            tags: Optional tags for categorization

        Returns:
            MaskResult with masked or original content
        """
        original_size = len(content)

        if not self._should_mask(content):
            return MaskResult(
                content=content,
                was_masked=False,
                original_size=original_size,
                masked_size=original_size,
            )

        # Store in artifact store
        try:
            meta = self.artifact_store.write_artifact(
                content=content,
                tool_name=tool_name,
                source_url=source_url,
                session_id=session_id,
                tags=tags,
            )
        except ValueError as e:
            # Content too large even for artifact store, truncate
            logger.warning(f"Content too large for artifact store: {e}")
            truncated = content[: self._threshold_chars] + "\n\n[... truncated ...]"
            return MaskResult(
                content=truncated,
                was_masked=True,
                original_size=original_size,
                masked_size=len(truncated),
            )

        # Create preview and placeholder
        preview = self._create_preview(content)
        placeholder = self._create_placeholder(
            artifact_id=meta.artifact_id,
            tool_name=tool_name,
            original_size=original_size,
            preview=preview,
        )

        logger.info(
            f"Masked {tool_name} output: {original_size} -> {len(placeholder)} chars "
            f"(artifact: {meta.artifact_id})"
        )

        return MaskResult(
            content=placeholder,
            was_masked=True,
            artifact_id=meta.artifact_id,
            original_size=original_size,
            masked_size=len(placeholder),
        )

    def mask_tool_message(
        self,
        message: ToolMessage,
        session_id: str | None = None,
    ) -> tuple[ToolMessage, MaskResult | None]:
        """Mask a ToolMessage if its content exceeds thresholds.

        Args:
            message: The ToolMessage to potentially mask
            session_id: Optional session ID for artifact scoping

        Returns:
            Tuple of (masked_message, MaskResult) or (original_message, None)
        """
        content = message.content
        if not isinstance(content, str):
            return message, None

        tool_name = message.name or "unknown_tool"
        result = self.mask_if_needed(
            content=content,
            tool_name=tool_name,
            session_id=session_id,
        )

        if not result.was_masked:
            return message, None

        # Create a new ToolMessage with masked content
        masked_message = ToolMessage(
            content=result.content,
            tool_call_id=message.tool_call_id,
            name=message.name,
            additional_kwargs={
                **message.additional_kwargs,
                "artifact_id": result.artifact_id,
                "original_size": result.original_size,
            },
        )

        return masked_message, result

    def mask_messages(
        self,
        messages: list[AnyMessage],
        session_id: str | None = None,
    ) -> tuple[list[AnyMessage], list[MaskResult]]:
        """Mask all ToolMessages in a message list that exceed thresholds.

        Args:
            messages: List of messages to process
            session_id: Optional session ID for artifact scoping

        Returns:
            Tuple of (processed_messages, list_of_mask_results)
        """
        processed = []
        results = []

        for msg in messages:
            if isinstance(msg, ToolMessage):
                masked_msg, result = self.mask_tool_message(msg, session_id)
                processed.append(masked_msg)
                if result:
                    results.append(result)
            else:
                processed.append(msg)

        return processed, results


# Preset masking configurations
MASKER_CONSERVATIVE = ObservationMasker(
    threshold_tokens=2000,
    threshold_chars=8000,
    preview_lines=20,
    preview_chars=1000,
)

MASKER_BALANCED = ObservationMasker(
    threshold_tokens=1000,
    threshold_chars=4000,
    preview_lines=10,
    preview_chars=500,
)

MASKER_AGGRESSIVE = ObservationMasker(
    threshold_tokens=500,
    threshold_chars=2000,
    preview_lines=5,
    preview_chars=250,
)


# Global masker instance
_observation_masker: ObservationMasker | None = None


def get_observation_masker() -> ObservationMasker:
    """Get the global observation masker instance."""
    global _observation_masker
    if _observation_masker is None:
        _observation_masker = MASKER_BALANCED
    return _observation_masker


def reset_observation_masker() -> None:
    """Reset the global observation masker (for testing)."""
    global _observation_masker
    _observation_masker = None

