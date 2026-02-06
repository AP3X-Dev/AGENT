"""Unit tests for context_gatherer module."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ag3nt_agent.context_blueprint import AntiPattern, CodeReference
from ag3nt_agent.context_gatherer import ContextGatherer, ContextPackage


# ------------------------------------------------------------------
# ContextPackage
# ------------------------------------------------------------------


@pytest.mark.unit
class TestContextPackage:
    def test_empty_package(self):
        pkg = ContextPackage()
        text = pkg.to_prompt_text()
        assert text == ""

    def test_code_references_section(self):
        pkg = ContextPackage(
            code_references=[
                CodeReference(
                    file_path="src/auth.py",
                    start_line=10,
                    end_line=30,
                    content="def login(): pass",
                    relevance="auth handler",
                ),
            ],
        )
        text = pkg.to_prompt_text()
        assert "## Relevant Code" in text
        assert "src/auth.py:10-30" in text
        assert "def login(): pass" in text

    def test_anti_patterns_section(self):
        pkg = ContextPackage(
            anti_patterns=[
                AntiPattern(description="Don't use eval()", example="eval(user_input)"),
            ],
        )
        text = pkg.to_prompt_text()
        assert "## Anti-Patterns" in text
        assert "Don't use eval()" in text
        assert "eval(user_input)" in text

    def test_gotchas_section(self):
        pkg = ContextPackage(gotchas=["Watch for race conditions"])
        text = pkg.to_prompt_text()
        assert "## Gotchas" in text
        assert "Watch for race conditions" in text

    def test_past_learnings_section(self):
        pkg = ContextPackage(past_learnings=["Connection pooling helps"])
        text = pkg.to_prompt_text()
        assert "## Past Learnings" in text
        assert "Connection pooling helps" in text

    def test_relevant_memories_section(self):
        pkg = ContextPackage(relevant_memories=["User prefers dark mode"])
        text = pkg.to_prompt_text()
        assert "## Relevant Memories" in text
        assert "User prefers dark mode" in text

    def test_similar_blueprints_section(self):
        pkg = ContextPackage(
            similar_blueprints=[
                {"goal": "Add auth", "status": "completed", "learnings": ["Use JWT"]},
            ],
        )
        text = pkg.to_prompt_text()
        assert "## Similar Past Blueprints" in text
        assert "Add auth" in text
        assert "Use JWT" in text

    def test_truncation(self):
        # Create a package that generates a long output
        refs = [
            CodeReference(file_path=f"file_{i}.py", content="x" * 400)
            for i in range(30)
        ]
        pkg = ContextPackage(code_references=refs)
        text = pkg.to_prompt_text(max_length=500)
        assert len(text) <= 500
        assert "truncated" in text

    def test_all_sections_together(self):
        pkg = ContextPackage(
            code_references=[CodeReference(file_path="a.py", content="code")],
            relevant_memories=["Memory 1"],
            past_learnings=["Learning 1"],
            anti_patterns=[AntiPattern(description="Bad pattern")],
            gotchas=["Gotcha 1"],
            similar_blueprints=[{"goal": "Past goal", "status": "completed"}],
        )
        text = pkg.to_prompt_text()
        assert "## Relevant Code" in text
        assert "## Anti-Patterns" in text
        assert "## Gotchas" in text
        assert "## Past Learnings" in text
        assert "## Relevant Memories" in text
        assert "## Similar Past Blueprints" in text


# ------------------------------------------------------------------
# ContextGatherer
# ------------------------------------------------------------------


@pytest.mark.unit
class TestContextGatherer:
    @pytest.fixture
    def mock_codebase_search(self):
        return MagicMock(return_value={
            "results": [
                {
                    "file_path": "src/main.py",
                    "start_line": 1,
                    "end_line": 10,
                    "content": "def main(): pass",
                    "name": "main function",
                },
            ],
            "count": 1,
        })

    @pytest.fixture
    def mock_context_engine(self):
        ce = AsyncMock()
        ce.find_memories = AsyncMock(return_value=[])
        return ce

    @pytest.fixture
    def mock_learning_engine(self):
        le = AsyncMock()
        le.get_recommendations = AsyncMock(return_value=[])
        return le

    @pytest.mark.asyncio
    async def test_gather_with_all_services(
        self, mock_codebase_search, mock_context_engine, mock_learning_engine
    ):
        gatherer = ContextGatherer(
            codebase_search_fn=mock_codebase_search,
            context_engine=mock_context_engine,
            learning_engine=mock_learning_engine,
        )
        pkg = await gatherer.gather_context("test query", session_id="s1")
        assert isinstance(pkg, ContextPackage)
        assert len(pkg.code_references) == 1
        assert pkg.code_references[0].file_path == "src/main.py"
        mock_codebase_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_gather_with_no_services(self):
        """Graceful degradation when all services are unavailable."""
        gatherer = ContextGatherer(
            codebase_search_fn=None,
            context_engine=None,
            learning_engine=None,
        )
        # Patch imports to simulate missing modules
        with patch.dict("sys.modules", {
            "ag3nt_agent.codebase_search": None,
            "ag3nt_agent.context_engine_client": None,
            "ag3nt_agent.autonomous.learning_engine": None,
        }):
            pkg = await gatherer.gather_context("test query")
        assert isinstance(pkg, ContextPackage)

    @pytest.mark.asyncio
    async def test_codebase_search_error_graceful(self):
        def failing_search(**kwargs):
            raise RuntimeError("Search failed")

        gatherer = ContextGatherer(codebase_search_fn=failing_search)
        pkg = await gatherer.gather_context("query")
        assert pkg.code_references == []

    @pytest.mark.asyncio
    async def test_memory_search_results(self, mock_context_engine):
        mock_result = MagicMock()
        mock_result.content = "User likes TypeScript"
        mock_result.metadata = {}
        mock_context_engine.find_memories = AsyncMock(return_value=[mock_result])

        gatherer = ContextGatherer(context_engine=mock_context_engine)
        pkg = await gatherer.gather_context("preferences")
        assert "User likes TypeScript" in pkg.relevant_memories

    @pytest.mark.asyncio
    async def test_learning_recommendations(self, mock_learning_engine):
        mock_rec = MagicMock()
        mock_rec.reason = "JWT auth works well for APIs"
        mock_learning_engine.get_recommendations = AsyncMock(return_value=[mock_rec])

        gatherer = ContextGatherer(learning_engine=mock_learning_engine)
        pkg = await gatherer.gather_context("auth implementation")
        assert "JWT auth works well for APIs" in pkg.past_learnings

    @pytest.mark.asyncio
    async def test_anti_pattern_extraction(self, mock_context_engine):
        mock_result = MagicMock()
        mock_result.content = "eval() caused security issue"
        mock_result.metadata = {"success": False, "error_message": "RCE vulnerability"}
        mock_context_engine.find_memories = AsyncMock(return_value=[mock_result])

        gatherer = ContextGatherer(context_engine=mock_context_engine)
        pkg = await gatherer.gather_context("security review")
        assert len(pkg.anti_patterns) == 1
        assert "eval()" in pkg.anti_patterns[0].description

    @pytest.mark.asyncio
    async def test_similar_blueprints(self, mock_context_engine):
        mock_result = MagicMock()
        mock_result.content = "Add authentication"
        mock_result.metadata = {
            "status": "completed",
            "learnings": ["Use OAuth2"],
        }
        mock_context_engine.find_memories = AsyncMock(return_value=[mock_result])

        gatherer = ContextGatherer(context_engine=mock_context_engine)
        pkg = await gatherer.gather_context("auth feature")
        assert len(pkg.similar_blueprints) == 1
        assert pkg.similar_blueprints[0]["goal"] == "Add authentication"

    @pytest.mark.asyncio
    async def test_partial_failure_doesnt_block(self, mock_context_engine):
        """If one search fails, others should still return results."""
        def raise_on_search(**kwargs):
            raise RuntimeError("boom")

        mock_result = MagicMock()
        mock_result.content = "Memory content"
        mock_result.metadata = {}
        mock_context_engine.find_memories = AsyncMock(return_value=[mock_result])

        gatherer = ContextGatherer(
            codebase_search_fn=raise_on_search,
            context_engine=mock_context_engine,
        )
        pkg = await gatherer.gather_context("test")
        # Codebase search failed but memories should still be present
        assert pkg.code_references == []
        assert len(pkg.relevant_memories) > 0
