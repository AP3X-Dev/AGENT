"""Tests for skill trigger matching middleware."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from ag3nt_agent.skill_trigger_middleware import (
    parse_skill_frontmatter,
    find_repo_root,
    load_skill_triggers,
    match_triggers,
    SkillTriggerMiddleware,
)
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage


class TestParseSkillFrontmatter:
    """Test suite for frontmatter parsing."""

    def test_parse_valid_frontmatter(self):
        """Test parsing valid frontmatter."""
        content = """---
name: test-skill
triggers:
  - open file
  - read file
---
# Skill
"""
        result = parse_skill_frontmatter(content)
        
        assert result is not None
        assert result["name"] == "test-skill"
        assert "triggers" in result
        assert len(result["triggers"]) == 2

    def test_parse_no_frontmatter(self):
        """Test parsing without frontmatter."""
        content = "# Just markdown"
        result = parse_skill_frontmatter(content)
        
        assert result is None

    def test_parse_invalid_yaml(self):
        """Test parsing invalid YAML."""
        content = """---
invalid: yaml: syntax
---
"""
        result = parse_skill_frontmatter(content)
        
        assert result is None


class TestFindRepoRoot:
    """Test suite for repository root finding."""

    @patch('ag3nt_agent.skill_trigger_middleware.Path')
    def test_find_repo_root_success(self, mock_path):
        """Test finding repo root successfully."""
        # Mock Path.cwd() to return a path with skills/ directory
        mock_cwd = MagicMock()
        mock_cwd.parent = MagicMock()
        mock_cwd.parent.parent = mock_cwd.parent  # Prevent infinite loop
        
        mock_skills_dir = MagicMock()
        mock_skills_dir.exists.return_value = True
        mock_cwd.__truediv__ = lambda self, other: mock_skills_dir if other == "skills" else MagicMock()
        
        mock_path.cwd.return_value = mock_cwd
        
        result = find_repo_root()
        
        assert result == mock_cwd

    @patch('ag3nt_agent.skill_trigger_middleware.Path')
    def test_find_repo_root_not_found(self, mock_path):
        """Test when repo root is not found."""
        # Mock Path.cwd() to return a path without skills/ directory
        mock_cwd = MagicMock()
        mock_cwd.parent = mock_cwd  # Simulate reaching root
        
        mock_skills_dir = MagicMock()
        mock_skills_dir.exists.return_value = False
        mock_cwd.__truediv__ = lambda self, other: mock_skills_dir
        
        mock_path.cwd.return_value = mock_cwd
        
        result = find_repo_root()
        
        assert result == mock_cwd


class TestMatchTriggers:
    """Test suite for trigger matching."""

    def test_match_single_trigger(self):
        """Test matching a single trigger."""
        triggers_map = {
            "file-manager": ["open file", "read file"],
            "web-research": ["search web", "research"]
        }
        
        result = match_triggers("Can you open file test.txt?", triggers_map)
        
        assert "file-manager" in result
        assert "web-research" not in result

    def test_match_multiple_triggers(self):
        """Test matching multiple triggers."""
        triggers_map = {
            "file-manager": ["open file"],
            "web-research": ["search", "research"]
        }
        
        result = match_triggers("Search and open file", triggers_map)
        
        assert "file-manager" in result
        assert "web-research" in result

    def test_match_case_insensitive(self):
        """Test case-insensitive matching."""
        triggers_map = {
            "test-skill": ["OPEN FILE"]
        }
        
        result = match_triggers("open file please", triggers_map)
        
        assert "test-skill" in result

    def test_match_no_triggers(self):
        """Test when no triggers match."""
        triggers_map = {
            "file-manager": ["open file"]
        }
        
        result = match_triggers("Hello world", triggers_map)
        
        assert len(result) == 0

    def test_match_empty_message(self):
        """Test matching with empty message."""
        triggers_map = {
            "test-skill": ["test"]
        }
        
        result = match_triggers("", triggers_map)
        
        assert len(result) == 0

    def test_match_partial_word(self):
        """Test that partial words match (substring matching)."""
        triggers_map = {
            "test-skill": ["file"]
        }
        
        result = match_triggers("filename", triggers_map)
        
        # Substring matching should match
        assert "test-skill" in result


class TestSkillTriggerMiddleware:
    """Test suite for SkillTriggerMiddleware."""

    def test_middleware_initialization(self):
        """Test middleware initialization."""
        middleware = SkillTriggerMiddleware()
        
        assert middleware._triggers_map is None

    @patch('ag3nt_agent.skill_trigger_middleware.load_skill_triggers')
    def test_middleware_lazy_loading(self, mock_load):
        """Test that triggers are loaded lazily."""
        mock_load.return_value = {"test-skill": ["test"]}
        
        middleware = SkillTriggerMiddleware()
        triggers = middleware._load_triggers()
        
        assert triggers == {"test-skill": ["test"]}
        assert middleware._triggers_map is not None
        
        # Second call should not reload
        triggers2 = middleware._load_triggers()
        assert mock_load.call_count == 1

    @patch('ag3nt_agent.skill_trigger_middleware.load_skill_triggers')
    @patch('deepagents.middleware._utils.append_to_system_message')
    def test_middleware_injects_suggestions(self, mock_append, mock_load):
        """Test that middleware injects skill suggestions."""
        mock_load.return_value = {"file-manager": ["open file"]}
        mock_append.return_value = "Modified system message"
        
        middleware = SkillTriggerMiddleware()
        
        # Create mock request
        request = Mock()
        request.messages = [HumanMessage(content="Can you open file test.txt?")]
        request.system_message = "Original system message"
        request.override = Mock(return_value=Mock())
        
        # Create mock handler
        handler = Mock(return_value=Mock())
        
        # Call middleware
        middleware.wrap_model_call(request, handler)
        
        # Verify system message was modified
        mock_append.assert_called_once()
        call_args = mock_append.call_args[0]
        assert "file-manager" in call_args[1]
        assert "Skill Suggestions" in call_args[1]

    @patch('ag3nt_agent.skill_trigger_middleware.load_skill_triggers')
    def test_middleware_no_match_no_injection(self, mock_load):
        """Test that middleware doesn't inject when no triggers match."""
        mock_load.return_value = {"file-manager": ["open file"]}
        
        middleware = SkillTriggerMiddleware()
        
        # Create mock request with non-matching message
        request = Mock()
        request.messages = [HumanMessage(content="Hello world")]
        
        # Create mock handler
        handler = Mock(return_value="response")
        
        # Call middleware
        result = middleware.wrap_model_call(request, handler)
        
        # Handler should be called with original request
        handler.assert_called_once_with(request)
        assert result == "response"

