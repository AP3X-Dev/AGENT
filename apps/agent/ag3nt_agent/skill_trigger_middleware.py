"""
Skill Trigger Matching Middleware for AG3NT.

This middleware analyzes user messages and suggests relevant skills based on
trigger keywords defined in SKILL.md files.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Awaitable, Callable

import yaml
from langchain.agents.middleware.types import AgentMiddleware, AgentState, ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


def parse_skill_frontmatter(content: str) -> dict[str, Any] | None:
    """Parse YAML frontmatter from SKILL.md content."""
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not match:
        return None
    
    try:
        frontmatter = yaml.safe_load(match.group(1))
        return frontmatter if isinstance(frontmatter, dict) else None
    except yaml.YAMLError:
        return None


def find_repo_root() -> Path:
    """Find the repository root by looking for the skills/ directory."""
    repo_root = Path.cwd()
    while repo_root != repo_root.parent:
        if (repo_root / "skills").exists():
            return repo_root
        repo_root = repo_root.parent
    return Path.cwd()


def load_skill_triggers() -> dict[str, list[str]]:
    """Load triggers from all skills.
    
    Returns:
        Dictionary mapping skill names to their trigger phrases
    """
    repo_root = find_repo_root()
    skill_dirs = [
        repo_root / "skills",  # Bundled
        Path.home() / ".ag3nt" / "skills",  # Global
        repo_root / ".ag3nt" / "skills",  # Workspace
    ]
    
    triggers_map: dict[str, list[str]] = {}
    
    for skill_dir in skill_dirs:
        if not skill_dir.exists():
            continue
        
        for skill_path in skill_dir.iterdir():
            if not skill_path.is_dir():
                continue
            
            skill_md = skill_path / "SKILL.md"
            if not skill_md.exists():
                continue
            
            try:
                content = skill_md.read_text(encoding="utf-8")
                frontmatter = parse_skill_frontmatter(content)
                
                if frontmatter and "triggers" in frontmatter:
                    skill_name = frontmatter.get("name", skill_path.name)
                    triggers = frontmatter["triggers"]
                    
                    if isinstance(triggers, list):
                        # Later sources override earlier ones
                        triggers_map[skill_name] = triggers
            except Exception as e:
                logger.warning(f"Failed to load triggers from {skill_md}: {e}")
    
    return triggers_map


def match_triggers(user_message: str, triggers_map: dict[str, list[str]]) -> list[str]:
    """Match user message against skill triggers.
    
    Args:
        user_message: The user's message
        triggers_map: Dictionary mapping skill names to trigger phrases
        
    Returns:
        List of skill names that match the user message
    """
    user_message_lower = user_message.lower()
    matched_skills = []
    
    for skill_name, triggers in triggers_map.items():
        for trigger in triggers:
            trigger_lower = trigger.lower()
            # Simple substring matching (could be enhanced with fuzzy matching)
            if trigger_lower in user_message_lower:
                matched_skills.append(skill_name)
                break  # Only match once per skill
    
    return matched_skills


class SkillTriggerMiddleware(AgentMiddleware):
    """Middleware that suggests skills based on trigger matching."""
    
    def __init__(self):
        super().__init__()
        self._triggers_map: dict[str, list[str]] | None = None
    
    def _load_triggers(self) -> dict[str, list[str]]:
        """Load triggers lazily."""
        if self._triggers_map is None:
            self._triggers_map = load_skill_triggers()
        return self._triggers_map
    
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """Inject skill suggestions based on trigger matching."""
        # Get the last user message
        last_user_message = None
        for msg in reversed(request.messages):
            if isinstance(msg, HumanMessage):
                last_user_message = msg.content
                break
        
        if not last_user_message or not isinstance(last_user_message, str):
            return handler(request)
        
        # Load triggers and match
        triggers_map = self._load_triggers()
        matched_skills = match_triggers(last_user_message, triggers_map)
        
        if not matched_skills:
            return handler(request)
        
        # Inject skill suggestions into system prompt
        suggestion_text = "\n\n**💡 Skill Suggestions:**\n\n"
        suggestion_text += f"Based on the user's message, these skills may be relevant:\n"
        for skill_name in matched_skills:
            suggestion_text += f"- **{skill_name}**: Consider reading its SKILL.md for specialized workflows\n"
        suggestion_text += "\nRemember to use the `run_skill` tool to execute skill entrypoints when appropriate."
        
        # Append to system message
        from deepagents.middleware._utils import append_to_system_message
        new_system_message = append_to_system_message(request.system_message, suggestion_text)
        modified_request = request.override(system_message=new_system_message)
        
        return handler(modified_request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """Inject skill suggestions based on trigger matching (async version)."""
        # Get the last user message
        last_user_message = None
        for msg in reversed(request.messages):
            if isinstance(msg, HumanMessage):
                last_user_message = msg.content
                break

        if not last_user_message or not isinstance(last_user_message, str):
            return await handler(request)

        # Load triggers and match
        triggers_map = self._load_triggers()
        matched_skills = match_triggers(last_user_message, triggers_map)

        if not matched_skills:
            return await handler(request)

        # Inject skill suggestions into system prompt
        suggestion_text = "\n\n**💡 Skill Suggestions:**\n\n"
        suggestion_text += "Based on the user's message, these skills may be relevant:\n"
        for skill_name in matched_skills:
            suggestion_text += (
                f"- **{skill_name}**: Consider reading its SKILL.md for specialized workflows\n"
            )
        suggestion_text += (
            "\nRemember to use the `run_skill` tool to execute skill entrypoints when appropriate."
        )

        # Append to system message
        from deepagents.middleware._utils import append_to_system_message

        new_system_message = append_to_system_message(request.system_message, suggestion_text)
        modified_request = request.override(system_message=new_system_message)

        return await handler(modified_request)
