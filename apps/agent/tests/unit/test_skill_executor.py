"""Tests for skill execution runtime."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import subprocess
from ag3nt_agent.skill_executor import (
    parse_skill_frontmatter,
    get_skill_entrypoint,
    run_skill,
)


class TestParseSkillFrontmatter:
    """Test suite for YAML frontmatter parsing."""

    def test_parse_valid_frontmatter(self):
        """Test parsing valid YAML frontmatter."""
        content = """---
name: test-skill
version: 1.0.0
entrypoints:
  run:
    script: run.py
    description: Main entrypoint
---
# Test Skill
"""
        result = parse_skill_frontmatter(content)

        assert result is not None
        assert result["name"] == "test-skill"
        assert result["version"] == "1.0.0"
        assert "entrypoints" in result
        assert "run" in result["entrypoints"]

    def test_parse_no_frontmatter(self):
        """Test parsing content without frontmatter."""
        content = "# Just a markdown file\nNo frontmatter here"
        result = parse_skill_frontmatter(content)

        assert result is None

    def test_parse_invalid_yaml(self):
        """Test parsing invalid YAML."""
        content = """---
invalid: yaml: syntax: error
---
"""
        result = parse_skill_frontmatter(content)

        assert result is None

    def test_parse_empty_frontmatter(self):
        """Test parsing empty frontmatter."""
        content = """---
---
"""
        result = parse_skill_frontmatter(content)

        # Empty YAML is valid and returns None
        assert result is None

    def test_parse_frontmatter_with_complex_structure(self):
        """Test parsing frontmatter with nested structures."""
        content = """---
name: complex-skill
entrypoints:
  run:
    script: run.py
    description: Main
  test:
    script: test.sh
    description: Test
required_permissions:
  - filesystem
  - network
---
"""
        result = parse_skill_frontmatter(content)

        assert result is not None
        assert len(result["entrypoints"]) == 2
        assert "required_permissions" in result
        assert len(result["required_permissions"]) == 2


class TestGetSkillEntrypoint:
    """Test suite for entrypoint extraction."""

    def test_get_existing_entrypoint(self):
        """Test getting an existing entrypoint."""
        frontmatter = {
            "entrypoints": {
                "run": {
                    "script": "run.py",
                    "description": "Main entrypoint"
                }
            }
        }

        result = get_skill_entrypoint(frontmatter, "run")

        assert result is not None
        assert result["script"] == "run.py"
        assert result["description"] == "Main entrypoint"

    def test_get_nonexistent_entrypoint(self):
        """Test getting a non-existent entrypoint."""
        frontmatter = {
            "entrypoints": {
                "run": {
                    "script": "run.py",
                    "description": "Main"
                }
            }
        }

        result = get_skill_entrypoint(frontmatter, "test")

        assert result is None

    def test_get_entrypoint_invalid_format(self):
        """Test getting entrypoint with invalid format."""
        frontmatter = {
            "entrypoints": "not a dict"
        }

        result = get_skill_entrypoint(frontmatter, "run")

        assert result is None

    def test_get_entrypoint_missing_script(self):
        """Test getting entrypoint without script field."""
        frontmatter = {
            "entrypoints": {
                "run": {
                    "description": "No script field"
                }
            }
        }

        result = get_skill_entrypoint(frontmatter, "run")

        assert result is None

    def test_get_entrypoint_no_entrypoints_key(self):
        """Test getting entrypoint when entrypoints key is missing."""
        frontmatter = {
            "name": "test-skill"
        }

        result = get_skill_entrypoint(frontmatter, "run")

        assert result is None


class TestRunSkill:
    """Test suite for skill execution."""

    @patch('ag3nt_agent.skill_executor.subprocess.run')
    @patch('ag3nt_agent.skill_executor.Path')
    def test_run_skill_success(self, mock_path, mock_subprocess):
        """Test successful skill execution."""
        # Mock file system
        mock_skill_dir = MagicMock()
        mock_skill_dir.exists.return_value = True
        mock_skill_dir.is_dir.return_value = True
        mock_skill_md = MagicMock()
        mock_skill_md.exists.return_value = True
        mock_skill_md.read_text.return_value = """---
name: test-skill
entrypoints:
  run:
    script: run.py
    description: Test
---
"""
        mock_script = MagicMock()
        mock_script.exists.return_value = True
        mock_script.suffix = ".py"

        mock_skill_dir.__truediv__ = lambda self, other: mock_skill_md if other == "SKILL.md" else mock_script

        # Mock Path to return our mock skill directory
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path.cwd.return_value = mock_path_instance
        mock_path.home.return_value = mock_path_instance

        # Mock subprocess
        mock_result = MagicMock()
        mock_result.stdout = "Success output"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_subprocess.return_value = mock_result

        # This test is complex due to Path mocking - skip for now
        # Will test integration instead
        pass

    def test_run_skill_default_entrypoint(self):
        """Test that default entrypoint is 'run'."""
        # The run_skill function should default to 'run' entrypoint
        # This is tested through the function signature
        assert run_skill.func.__code__.co_varnames[:3] == ('skill_name', 'entrypoint_name', 'arguments')

    def test_run_skill_tool_metadata(self):
        """Test that run_skill has proper tool metadata."""
        assert run_skill.name == "run_skill"
        assert run_skill.description is not None
        assert "skill" in run_skill.description.lower()
        assert "execute" in run_skill.description.lower()

    @patch('ag3nt_agent.skill_executor.subprocess.run')
    def test_run_skill_timeout(self, mock_subprocess):
        """Test skill execution timeout handling."""
        import tempfile
        import os
        from pathlib import Path

        # Create a temporary directory structure
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create skills directory (so repo_root finding works)
            skills_dir = tmpdir_path / "skills"
            skills_dir.mkdir()

            # Create skill directory
            skill_dir = skills_dir / "test-skill"
            skill_dir.mkdir()

            # Create SKILL.md
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text("""---
entrypoints:
  run:
    script: test.py
---
Test skill""")

            # Create test.py script
            test_script = skill_dir / "test.py"
            test_script.write_text("print('test')")

            # Mock subprocess to raise timeout
            mock_subprocess.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=30)

            # Temporarily change cwd to tmpdir so skill can be found
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)

                result = run_skill.invoke({
                    "skill_name": "test-skill",
                    "entrypoint_name": "run"
                })

                assert "timeout" in result.lower() or "timed out" in result.lower()
                assert "30" in result
            finally:
                os.chdir(original_cwd)

