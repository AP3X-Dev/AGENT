"""
Context-Engine Client for AG3NT

Provides integration with Context-Engine MCP servers for:
- Semantic memory storage and retrieval
- Code search and indexing
- RAG-style Q&A capabilities

This client connects to Context-Engine's Memory Server and Indexer Server
via the MCP HTTP protocol.
"""

import os
import json
import logging
from typing import Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


@dataclass
class MemoryResult:
    """Result from a memory search."""
    content: str
    score: float
    metadata: dict = field(default_factory=dict)
    collection: str = ""

    @classmethod
    def from_response(cls, data: dict) -> "MemoryResult":
        return cls(
            content=data.get("content", data.get("information", "")),
            score=data.get("score", 0.0),
            metadata=data.get("metadata", {}),
            collection=data.get("collection", "")
        )


@dataclass
class CodeSearchResult:
    """Result from a code search."""
    file_path: str
    content: str
    score: float
    language: str = ""
    start_line: int = 0
    end_line: int = 0

    @classmethod
    def from_response(cls, data: dict) -> "CodeSearchResult":
        return cls(
            file_path=data.get("file_path", data.get("path", "")),
            content=data.get("content", data.get("chunk", "")),
            score=data.get("score", 0.0),
            language=data.get("language", ""),
            start_line=data.get("start_line", 0),
            end_line=data.get("end_line", 0)
        )


class ContextEngineError(Exception):
    """Base exception for Context-Engine errors."""
    pass


class ConnectionError(ContextEngineError):
    """Failed to connect to Context-Engine server."""
    pass


class ToolCallError(ContextEngineError):
    """Error executing an MCP tool call."""
    pass


class ContextEngineClient:
    """
    Client for interacting with Context-Engine MCP servers.

    Provides methods for:
    - Storing and retrieving memories (semantic search)
    - Searching code repositories
    - RAG-style question answering

    Example:
        client = ContextEngineClient()

        # Store a memory
        await client.store_memory(
            information="User prefers dark mode",
            metadata={"category": "preference", "session_id": "abc123"},
            collection="agent-preferences"
        )

        # Find similar memories
        results = await client.find_memories(
            query="What are the user's UI preferences?",
            limit=5,
            collection="agent-preferences"
        )

        # Search code
        code_results = await client.search_code(
            query="authentication middleware",
            limit=10
        )
    """

    # Default collection names for AG3NT
    COLLECTION_LEARNING = "agent-learning"
    COLLECTION_GOALS = "agent-goals"
    COLLECTION_PREFERENCES = "agent-preferences"
    COLLECTION_CONVERSATIONS = "agent-conversations"
    COLLECTION_STATE = "agent-state"
    COLLECTION_BLUEPRINTS = "agent-blueprints"

    def __init__(
        self,
        memory_url: Optional[str] = None,
        indexer_url: Optional[str] = None,
        qdrant_url: Optional[str] = None,
        timeout: float = 30.0
    ):
        """
        Initialize the Context-Engine client.

        Args:
            memory_url: URL for the Memory Server MCP endpoint.
                       Defaults to CONTEXT_ENGINE_MEMORY_URL env var or localhost:8002.
            indexer_url: URL for the Indexer Server MCP endpoint.
                        Defaults to CONTEXT_ENGINE_INDEXER_URL env var or localhost:8003.
            qdrant_url: URL for direct Qdrant access (optional).
                       Defaults to QDRANT_URL env var or localhost:6333.
            timeout: Request timeout in seconds.
        """
        self.memory_url = memory_url or os.getenv(
            "CONTEXT_ENGINE_MEMORY_URL",
            "http://localhost:8002/mcp"
        )
        self.indexer_url = indexer_url or os.getenv(
            "CONTEXT_ENGINE_INDEXER_URL",
            "http://localhost:8003/mcp"
        )
        self.qdrant_url = qdrant_url or os.getenv(
            "QDRANT_URL",
            "http://localhost:6333"
        )
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "ContextEngineClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _call_mcp_tool(
        self,
        server_url: str,
        tool_name: str,
        arguments: dict
    ) -> Any:
        """
        Call an MCP tool on the specified server.

        Uses the MCP HTTP protocol to invoke tools.

        Args:
            server_url: The MCP server URL
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            The tool result

        Raises:
            ToolCallError: If the tool call fails
        """
        client = await self._get_client()

        # MCP tool call request format
        request_body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        try:
            response = await client.post(
                server_url,
                json=request_body,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()

            result = response.json()

            if "error" in result:
                raise ToolCallError(f"MCP error: {result['error']}")

            return result.get("result", {})

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error calling {tool_name}: {e}")
            raise ToolCallError(f"HTTP error: {e}") from e
        except httpx.RequestError as e:
            logger.error(f"Request error calling {tool_name}: {e}")
            raise ConnectionError(f"Connection error: {e}") from e
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from {tool_name}: {e}")
            raise ToolCallError(f"Invalid response: {e}") from e

    # =========================================================================
    # Memory Operations (Memory Server)
    # =========================================================================

    async def store_memory(
        self,
        information: str,
        metadata: Optional[dict] = None,
        collection: str = "default"
    ) -> dict:
        """
        Store information in semantic memory.

        Args:
            information: The text content to store
            metadata: Optional metadata to attach (tags, timestamps, etc.)
            collection: The collection/namespace to store in

        Returns:
            Storage confirmation with ID
        """
        metadata = metadata or {}
        metadata["stored_at"] = datetime.utcnow().isoformat()

        return await self._call_mcp_tool(
            self.memory_url,
            "store",
            {
                "information": information,
                "metadata": json.dumps(metadata),
                "collection": collection
            }
        )

    async def find_memories(
        self,
        query: str,
        limit: int = 10,
        collection: str = "default",
        min_score: float = 0.0
    ) -> list[MemoryResult]:
        """
        Search for semantically similar memories.

        Uses hybrid search (dense + lexical + RRF fusion) for best results.

        Args:
            query: Natural language search query
            limit: Maximum number of results
            collection: Collection to search in
            min_score: Minimum similarity score threshold

        Returns:
            List of MemoryResult objects sorted by relevance
        """
        result = await self._call_mcp_tool(
            self.memory_url,
            "find",
            {
                "query": query,
                "n_results": limit,
                "collection": collection
            }
        )

        # Parse results
        memories = []
        items = result.get("results", result.get("content", []))

        if isinstance(items, str):
            # Handle text response format
            return [MemoryResult(content=items, score=1.0, collection=collection)]

        for item in items:
            memory = MemoryResult.from_response(item)
            memory.collection = collection
            if memory.score >= min_score:
                memories.append(memory)

        return memories

    async def delete_memory(
        self,
        memory_id: str,
        collection: str = "default"
    ) -> bool:
        """
        Delete a specific memory by ID.

        Args:
            memory_id: The memory's unique identifier
            collection: The collection containing the memory

        Returns:
            True if deleted successfully
        """
        try:
            await self._call_mcp_tool(
                self.memory_url,
                "delete",
                {
                    "id": memory_id,
                    "collection": collection
                }
            )
            return True
        except ToolCallError:
            return False

    # =========================================================================
    # Code Search Operations (Indexer Server)
    # =========================================================================

    async def search_code(
        self,
        query: str,
        limit: int = 10,
        language: Optional[str] = None,
        file_pattern: Optional[str] = None
    ) -> list[CodeSearchResult]:
        """
        Search indexed code repositories.

        Args:
            query: Natural language or code search query
            limit: Maximum number of results
            language: Filter by programming language (optional)
            file_pattern: Filter by file glob pattern (optional)

        Returns:
            List of CodeSearchResult objects
        """
        arguments = {
            "query": query,
            "n_results": limit
        }

        if language:
            arguments["language"] = language
        if file_pattern:
            arguments["file_pattern"] = file_pattern

        result = await self._call_mcp_tool(
            self.indexer_url,
            "repo_search",
            arguments
        )

        results = []
        items = result.get("results", result.get("content", []))

        if isinstance(items, str):
            return [CodeSearchResult(file_path="", content=items, score=1.0)]

        for item in items:
            results.append(CodeSearchResult.from_response(item))

        return results

    async def context_search(
        self,
        query: str,
        limit: int = 10,
        include_memory: bool = True,
        include_code: bool = True
    ) -> dict:
        """
        Search across both memory and code.

        Unified search that combines results from Memory Server
        and Indexer Server.

        Args:
            query: Search query
            limit: Maximum results from each source
            include_memory: Include memory results
            include_code: Include code results

        Returns:
            Dict with 'memory' and 'code' result lists
        """
        results = {"memory": [], "code": []}

        if include_memory:
            try:
                results["memory"] = await self.find_memories(query, limit=limit)
            except ContextEngineError as e:
                logger.warning(f"Memory search failed: {e}")

        if include_code:
            try:
                results["code"] = await self.search_code(query, limit=limit)
            except ContextEngineError as e:
                logger.warning(f"Code search failed: {e}")

        return results

    async def context_answer(
        self,
        query: str,
        limit: int = 10,
        include_sources: bool = True
    ) -> dict:
        """
        RAG-style question answering using Context-Engine.

        Retrieves relevant context and generates an answer
        using the configured LLM (if available).

        Args:
            query: The question to answer
            limit: Number of context chunks to retrieve
            include_sources: Include source references in response

        Returns:
            Dict with 'answer' and optional 'sources'
        """
        try:
            result = await self._call_mcp_tool(
                self.indexer_url,
                "context_answer",
                {
                    "query": query,
                    "n_results": limit
                }
            )

            answer = result.get("answer", result.get("content", ""))
            sources = result.get("sources", []) if include_sources else []

            return {
                "answer": answer,
                "sources": sources
            }
        except ToolCallError:
            # Fallback to context_search if context_answer not available
            context = await self.context_search(query, limit=limit)
            return {
                "answer": None,
                "sources": context,
                "fallback": True
            }

    # =========================================================================
    # AG3NT-Specific Operations
    # =========================================================================

    async def store_action(
        self,
        action_type: str,
        goal_id: str,
        success: bool,
        duration_ms: int,
        context: str,
        details: Optional[dict] = None
    ) -> dict:
        """
        Store an action outcome for learning.

        Used by the Learning Engine to track action history
        and build confidence scores.

        Args:
            action_type: Type of action (e.g., "shell", "notify", "agent")
            goal_id: ID of the goal that triggered this action
            success: Whether the action succeeded
            duration_ms: Execution time in milliseconds
            context: Description of the action context
            details: Additional details about the action

        Returns:
            Storage confirmation
        """
        information = f"{action_type} action for goal '{goal_id}': {context}"

        metadata = {
            "action_type": action_type,
            "goal_id": goal_id,
            "success": success,
            "duration_ms": duration_ms,
            "timestamp": datetime.utcnow().isoformat(),
            **(details or {})
        }

        return await self.store_memory(
            information=information,
            metadata=metadata,
            collection=self.COLLECTION_LEARNING
        )

    async def get_action_confidence(
        self,
        action_type: str,
        context: str,
        min_samples: int = 3
    ) -> tuple[float, int]:
        """
        Calculate confidence score for an action based on history.

        Uses semantic search to find similar past actions and
        calculates a weighted confidence score.

        Args:
            action_type: Type of action
            context: Current action context
            min_samples: Minimum samples required for confidence

        Returns:
            Tuple of (confidence_score, sample_count)
        """
        query = f"{action_type} action: {context}"

        results = await self.find_memories(
            query=query,
            limit=50,
            collection=self.COLLECTION_LEARNING
        )

        if len(results) < min_samples:
            return 0.0, len(results)

        # Calculate weighted confidence
        # Weight by similarity score - more similar actions count more
        weighted_success = 0.0
        total_weight = 0.0

        for result in results:
            weight = result.score
            success = result.metadata.get("success", False)

            # Apply failure weight (failures count 1.5x)
            if not success:
                weight *= 1.5

            weighted_success += weight if success else 0
            total_weight += weight

        confidence = weighted_success / total_weight if total_weight > 0 else 0.0

        return confidence, len(results)

    async def store_goal_template(
        self,
        goal_id: str,
        name: str,
        description: str,
        yaml_content: str,
        tags: Optional[list[str]] = None
    ) -> dict:
        """
        Store a goal template for reuse.

        Args:
            goal_id: Unique goal identifier
            name: Human-readable name
            description: What the goal does
            yaml_content: The full YAML configuration
            tags: Categorization tags

        Returns:
            Storage confirmation
        """
        information = f"Goal template '{name}': {description}"

        metadata = {
            "goal_id": goal_id,
            "name": name,
            "yaml_content": yaml_content,
            "tags": tags or []
        }

        return await self.store_memory(
            information=information,
            metadata=metadata,
            collection=self.COLLECTION_GOALS
        )

    async def find_similar_goals(
        self,
        description: str,
        limit: int = 5
    ) -> list[MemoryResult]:
        """
        Find goal templates similar to a description.

        Useful for natural language goal creation - find existing
        templates that match what the user is asking for.

        Args:
            description: Natural language description of desired goal
            limit: Maximum results

        Returns:
            List of similar goal templates
        """
        return await self.find_memories(
            query=description,
            limit=limit,
            collection=self.COLLECTION_GOALS
        )

    async def store_conversation_summary(
        self,
        session_id: str,
        summary: str,
        key_topics: list[str],
        decisions: Optional[list[str]] = None
    ) -> dict:
        """
        Store a conversation summary for context retrieval.

        Args:
            session_id: Session identifier
            summary: Text summary of the conversation
            key_topics: Main topics discussed
            decisions: Any decisions made

        Returns:
            Storage confirmation
        """
        information = f"Conversation {session_id}: {summary}"

        metadata = {
            "session_id": session_id,
            "key_topics": key_topics,
            "decisions": decisions or [],
            "type": "conversation_summary"
        }

        return await self.store_memory(
            information=information,
            metadata=metadata,
            collection=self.COLLECTION_CONVERSATIONS
        )

    async def get_relevant_context(
        self,
        query: str,
        session_id: Optional[str] = None,
        limit: int = 10
    ) -> dict:
        """
        Get relevant context for a query from all sources.

        Searches conversations, preferences, and learning history
        to provide comprehensive context for decision-making.

        Args:
            query: The context query
            session_id: Optional session to prioritize
            limit: Results per collection

        Returns:
            Dict with results from each collection
        """
        context = {
            "conversations": [],
            "preferences": [],
            "learning": [],
            "goals": []
        }

        # Search each collection
        collections = [
            (self.COLLECTION_CONVERSATIONS, "conversations"),
            (self.COLLECTION_PREFERENCES, "preferences"),
            (self.COLLECTION_LEARNING, "learning"),
            (self.COLLECTION_GOALS, "goals")
        ]

        for collection, key in collections:
            try:
                results = await self.find_memories(
                    query=query,
                    limit=limit,
                    collection=collection
                )
                context[key] = results
            except ContextEngineError as e:
                logger.warning(f"Failed to search {collection}: {e}")

        return context

    # =========================================================================
    # Health Check
    # =========================================================================

    async def health_check(self) -> dict:
        """
        Check connectivity to Context-Engine services.

        Returns:
            Dict with status of each service
        """
        status = {
            "memory_server": False,
            "indexer_server": False,
            "qdrant": False
        }

        client = await self._get_client()

        # Check Memory Server
        try:
            response = await client.get(
                self.memory_url.replace("/mcp", "/health"),
                timeout=5.0
            )
            status["memory_server"] = response.status_code == 200
        except Exception as e:
            logger.debug(f"Memory server health check failed: {e}")

        # Check Indexer Server
        try:
            response = await client.get(
                self.indexer_url.replace("/mcp", "/health"),
                timeout=5.0
            )
            status["indexer_server"] = response.status_code == 200
        except Exception as e:
            logger.debug(f"Indexer server health check failed: {e}")

        # Check Qdrant
        try:
            response = await client.get(
                f"{self.qdrant_url}/healthz",
                timeout=5.0
            )
            status["qdrant"] = response.status_code == 200
        except Exception as e:
            logger.debug(f"Qdrant health check failed: {e}")

        status["healthy"] = all([
            status["memory_server"],
            status["qdrant"]
        ])

        return status


# Module-level constant for blueprint collection (convenience import)
COLLECTION_BLUEPRINTS = ContextEngineClient.COLLECTION_BLUEPRINTS

# Singleton instance for easy access
_client: Optional[ContextEngineClient] = None


def get_context_engine() -> ContextEngineClient:
    """
    Get the singleton Context-Engine client instance.

    Creates the client on first call with environment-based configuration.

    Returns:
        ContextEngineClient instance
    """
    global _client
    if _client is None:
        _client = ContextEngineClient()
    return _client


async def init_context_engine(
    memory_url: Optional[str] = None,
    indexer_url: Optional[str] = None,
    qdrant_url: Optional[str] = None
) -> ContextEngineClient:
    """
    Initialize the Context-Engine client with custom configuration.

    Args:
        memory_url: Custom Memory Server URL
        indexer_url: Custom Indexer Server URL
        qdrant_url: Custom Qdrant URL

    Returns:
        Configured ContextEngineClient instance
    """
    global _client

    if _client is not None:
        await _client.close()

    _client = ContextEngineClient(
        memory_url=memory_url,
        indexer_url=indexer_url,
        qdrant_url=qdrant_url
    )

    return _client
