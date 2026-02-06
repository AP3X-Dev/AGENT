"""Context Gatherer — automated context collection for planning.

Orchestrates parallel searches across existing services to build a
rich context package before the LLM generates a plan.  Ties together:
- ``codebase_search`` (FAISS semantic search)
- ``context_engine_client`` (semantic memory via MCP)
- ``learning_engine`` (past action outcomes)

All search methods fail gracefully and return empty results on error,
so partial service unavailability never blocks planning.

Usage:
    from ag3nt_agent.context_gatherer import ContextGatherer

    gatherer = ContextGatherer()
    package = await gatherer.gather_context("Add user auth", session_id="s1")
    prompt_text = package.to_prompt_text()
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from ag3nt_agent.context_blueprint import AntiPattern, CodeReference

logger = logging.getLogger("ag3nt.context_gatherer")


# ---------------------------------------------------------------------------
# Context Package
# ---------------------------------------------------------------------------

@dataclass
class ContextPackage:
    """Aggregated context from all sources."""

    code_references: list[CodeReference] = field(default_factory=list)
    relevant_memories: list[str] = field(default_factory=list)
    past_learnings: list[str] = field(default_factory=list)
    anti_patterns: list[AntiPattern] = field(default_factory=list)
    similar_blueprints: list[dict[str, Any]] = field(default_factory=list)
    gotchas: list[str] = field(default_factory=list)

    def to_prompt_text(self, max_length: int = 8000) -> str:
        """Format as markdown for system prompt injection.

        Intelligently truncates to *max_length* characters, prioritising
        code references and anti-patterns over memories and learnings.
        """
        sections: list[str] = []

        if self.code_references:
            lines = ["## Relevant Code"]
            for ref in self.code_references[:10]:
                loc = f"{ref.file_path}"
                if ref.start_line:
                    loc += f":{ref.start_line}-{ref.end_line}"
                lines.append(f"### {loc}")
                if ref.relevance:
                    lines.append(f"*{ref.relevance}*")
                if ref.content:
                    # Truncate individual snippets
                    snippet = ref.content[:500]
                    lines.append(f"```\n{snippet}\n```")
            sections.append("\n".join(lines))

        if self.anti_patterns:
            lines = ["## Anti-Patterns (Avoid These)"]
            for ap in self.anti_patterns[:5]:
                lines.append(f"- **{ap.description}**")
                if ap.example:
                    lines.append(f"  Example: {ap.example}")
            sections.append("\n".join(lines))

        if self.gotchas:
            lines = ["## Gotchas"]
            for g in self.gotchas[:5]:
                lines.append(f"- {g}")
            sections.append("\n".join(lines))

        if self.past_learnings:
            lines = ["## Past Learnings"]
            for learning in self.past_learnings[:5]:
                lines.append(f"- {learning}")
            sections.append("\n".join(lines))

        if self.relevant_memories:
            lines = ["## Relevant Memories"]
            for mem in self.relevant_memories[:5]:
                lines.append(f"- {mem}")
            sections.append("\n".join(lines))

        if self.similar_blueprints:
            lines = ["## Similar Past Blueprints"]
            for bp in self.similar_blueprints[:3]:
                lines.append(f"- **{bp.get('goal', 'Unknown')}** ({bp.get('status', '?')})")
                if bp.get("learnings"):
                    for l in bp["learnings"][:2]:
                        lines.append(f"  - {l}")
            sections.append("\n".join(lines))

        full_text = "\n\n".join(sections)

        # Truncate to max_length, cutting from the end
        if len(full_text) > max_length:
            full_text = full_text[:max_length - 20] + "\n\n... (truncated)"

        return full_text


# ---------------------------------------------------------------------------
# Context Gatherer
# ---------------------------------------------------------------------------


class ContextGatherer:
    """Orchestrates context gathering from multiple sources.

    All constructor parameters are optional; the gatherer degrades
    gracefully when services are unavailable.

    Args:
        codebase_search_fn: Callable matching
            ``codebase_search(query, path, max_results) -> dict``.
            Defaults to the module-level function.
        context_engine: ``ContextEngineClient`` instance (or None).
        learning_engine: ``LearningEngine`` instance (or None).
    """

    def __init__(
        self,
        codebase_search_fn: Callable[..., dict[str, Any]] | None = None,
        context_engine: Any | None = None,
        learning_engine: Any | None = None,
    ):
        self._codebase_search_fn = codebase_search_fn
        self._context_engine = context_engine
        self._learning_engine = learning_engine

    # -- public API ---------------------------------------------------------

    async def gather_context(
        self,
        user_request: str,
        session_id: str = "",
    ) -> ContextPackage:
        """Gather context for a user request.

        Runs all searches concurrently and merges results into a
        ``ContextPackage``.

        Args:
            user_request: The user's request text.
            session_id: Session ID for scoping.

        Returns:
            Populated ``ContextPackage``.
        """
        results = await asyncio.gather(
            self._search_codebase(user_request),
            self._search_memories(user_request),
            self._search_learnings(user_request),
            self._search_anti_patterns(user_request),
            self._find_similar_blueprints(user_request),
            return_exceptions=True,
        )

        package = ContextPackage()

        # Unpack results, ignoring exceptions
        if not isinstance(results[0], BaseException):
            package.code_references = results[0]
        if not isinstance(results[1], BaseException):
            package.relevant_memories = results[1]
        if not isinstance(results[2], BaseException):
            package.past_learnings = results[2]
        if not isinstance(results[3], BaseException):
            package.anti_patterns = results[3]
        if not isinstance(results[4], BaseException):
            package.similar_blueprints = results[4]

        logger.info(
            "Context gathered: %d code refs, %d memories, %d learnings, "
            "%d anti-patterns, %d similar blueprints",
            len(package.code_references),
            len(package.relevant_memories),
            len(package.past_learnings),
            len(package.anti_patterns),
            len(package.similar_blueprints),
        )
        return package

    # -- private search methods ---------------------------------------------

    async def _search_codebase(self, query: str) -> list[CodeReference]:
        """Search codebase using FAISS semantic search."""
        if self._codebase_search_fn is None:
            try:
                from ag3nt_agent.codebase_search import codebase_search
                self._codebase_search_fn = codebase_search
            except ImportError:
                logger.debug("codebase_search not available")
                return []

        try:
            result = self._codebase_search_fn(query=query, max_results=10)
            refs = []
            for item in result.get("results", []):
                refs.append(CodeReference(
                    file_path=item.get("file_path", ""),
                    start_line=item.get("start_line", 0),
                    end_line=item.get("end_line", 0),
                    content=item.get("content", ""),
                    relevance=item.get("name", ""),
                    source="codebase_search",
                ))
            return refs
        except Exception as exc:
            logger.debug("Codebase search failed: %s", exc)
            return []

    async def _search_memories(self, query: str) -> list[str]:
        """Search semantic memory for conversations and preferences."""
        if self._context_engine is None:
            try:
                from ag3nt_agent.context_engine_client import get_context_engine
                self._context_engine = get_context_engine()
            except ImportError:
                logger.debug("context_engine_client not available")
                return []

        memories: list[str] = []
        try:
            from ag3nt_agent.context_engine_client import ContextEngineClient
            for collection in (
                ContextEngineClient.COLLECTION_CONVERSATIONS,
                ContextEngineClient.COLLECTION_PREFERENCES,
            ):
                results = await self._context_engine.find_memories(
                    query=query, limit=5, collection=collection,
                )
                for r in results:
                    memories.append(r.content)
        except Exception as exc:
            logger.debug("Memory search failed: %s", exc)
        return memories

    async def _search_learnings(self, query: str) -> list[str]:
        """Get learning-based recommendations."""
        if self._learning_engine is None:
            try:
                from ag3nt_agent.autonomous.learning_engine import LearningEngine
                self._learning_engine = LearningEngine()
            except ImportError:
                logger.debug("learning_engine not available")
                return []

        try:
            recommendations = await self._learning_engine.get_recommendations(
                context=query, limit=5,
            )
            return [r.reason for r in recommendations]
        except Exception as exc:
            logger.debug("Learning search failed: %s", exc)
            return []

    async def _search_anti_patterns(self, query: str) -> list[AntiPattern]:
        """Find anti-patterns from past failures."""
        if self._context_engine is None:
            return []

        try:
            from ag3nt_agent.context_engine_client import ContextEngineClient
            results = await self._context_engine.find_memories(
                query=f"failure error problem: {query}",
                limit=10,
                collection=ContextEngineClient.COLLECTION_LEARNING,
            )
            anti_patterns = []
            for r in results:
                if not r.metadata.get("success", True):
                    anti_patterns.append(AntiPattern(
                        description=r.content,
                        example=r.metadata.get("error_message", ""),
                        source="learning_history",
                    ))
            return anti_patterns[:5]
        except Exception as exc:
            logger.debug("Anti-pattern search failed: %s", exc)
            return []

    async def _find_similar_blueprints(self, query: str) -> list[dict[str, Any]]:
        """Find similar past blueprints."""
        if self._context_engine is None:
            return []

        try:
            from ag3nt_agent.context_engine_client import COLLECTION_BLUEPRINTS
            results = await self._context_engine.find_memories(
                query=query, limit=3,
                collection=COLLECTION_BLUEPRINTS,
            )
            return [
                {
                    "goal": r.content,
                    "status": r.metadata.get("status", "unknown"),
                    "learnings": r.metadata.get("learnings", []),
                }
                for r in results
            ]
        except Exception as exc:
            logger.debug("Blueprint search failed: %s", exc)
            return []
