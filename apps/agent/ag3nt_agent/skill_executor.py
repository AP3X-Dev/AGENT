"""
Skill Execution Runtime for AG3NT.

Provides tools for executing skill entrypoints defined in SKILL.md files.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

import yaml
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def parse_skill_frontmatter(content: str) -> dict[str, Any] | None:
    """Parse YAML frontmatter from SKILL.md content.

    Args:
        content: Content of the SKILL.md file

    Returns:
        Parsed frontmatter as a dictionary, or None if parsing fails
    """
    # Extract YAML frontmatter between --- markers
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not match:
        logger.warning("No YAML frontmatter found in SKILL.md")
        return None

    frontmatter_text = match.group(1)

    try:
        frontmatter = yaml.safe_load(frontmatter_text)
        return frontmatter if isinstance(frontmatter, dict) else None
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse YAML frontmatter: {e}")
        return None


def get_skill_entrypoint(frontmatter: dict[str, Any], entrypoint_name: str) -> dict[str, str] | None:
    """Extract a specific entrypoint from skill frontmatter.

    Args:
        frontmatter: Parsed YAML frontmatter
        entrypoint_name: Name of the entrypoint to extract

    Returns:
        Entrypoint definition with 'script' and 'description' keys, or None if not found
    """
    entrypoints = frontmatter.get("entrypoints", {})
    if not isinstance(entrypoints, dict):
        logger.warning("Invalid entrypoints format in SKILL.md")
        return None

    entrypoint = entrypoints.get(entrypoint_name)
    if not entrypoint:
        logger.warning(f"Entrypoint '{entrypoint_name}' not found")
        return None

    if not isinstance(entrypoint, dict) or "script" not in entrypoint:
        logger.warning(f"Invalid entrypoint definition for '{entrypoint_name}'")
        return None

    return entrypoint


@tool
def run_skill(
    skill_name: str,
    entrypoint_name: Optional[str] = None,
    arguments: Optional[str] = None
) -> str:
    """Execute a skill entrypoint script.

    This tool runs a skill's entrypoint script as defined in its SKILL.md file.
    Skills are executable scripts that provide specialized capabilities.

    Args:
        skill_name: Name of the skill to execute (e.g., "example-skill", "file-manager")
        entrypoint_name: Name of the entrypoint to run (default: "run")
        arguments: Optional arguments to pass to the script (space-separated string)

    Returns:
        Output from the script execution (stdout + stderr)

    Examples:
        run_skill(skill_name="example-skill", entrypoint_name="run")
        run_skill(skill_name="file-manager", entrypoint_name="open", arguments="/path/to/file.txt")
        run_skill(skill_name="system-info", entrypoint_name="cpu")
    """
    # Set defaults
    if entrypoint_name is None:
        entrypoint_name = "run"
    if arguments is None:
        arguments = ""
    try:
        # Find the skill directory
        # Check in priority order: workspace, global, bundled
        # Try to find the repository root (look for skills/ directory)
        repo_root = Path.cwd()
        while repo_root != repo_root.parent:
            if (repo_root / "skills").exists():
                break
            repo_root = repo_root.parent

        skill_paths = [
            repo_root / ".ag3nt" / "skills" / skill_name,  # Workspace
            Path.home() / ".ag3nt" / "skills" / skill_name,  # Global
            repo_root / "skills" / skill_name,  # Bundled
        ]

        skill_dir = None
        for path in skill_paths:
            if path.exists() and path.is_dir():
                skill_dir = path
                break

        if not skill_dir:
            return f"Error: Skill '{skill_name}' not found in any skill directory"

        # Read SKILL.md
        skill_md_path = skill_dir / "SKILL.md"
        if not skill_md_path.exists():
            return f"Error: SKILL.md not found for skill '{skill_name}'"

        content = skill_md_path.read_text(encoding="utf-8")

        # Parse frontmatter
        frontmatter = parse_skill_frontmatter(content)
        if not frontmatter:
            return f"Error: Failed to parse SKILL.md frontmatter for '{skill_name}'"

        # Get entrypoint
        entrypoint = get_skill_entrypoint(frontmatter, entrypoint_name)
        if not entrypoint:
            available = list(frontmatter.get("entrypoints", {}).keys())
            return f"Error: Entrypoint '{entrypoint_name}' not found. Available: {', '.join(available)}"

        # Build command
        script_path = entrypoint["script"]

        # Handle both "script.sh" and "script.py arg1 arg2" formats
        script_parts = script_path.split()
        base_script = skill_dir / script_parts[0]
        script_args = script_parts[1:] if len(script_parts) > 1 else []

        if not base_script.exists():
            return f"Error: Script not found: {base_script}"

        # Add user-provided arguments
        if arguments:
            script_args.extend(arguments.split())

        # Determine how to run the script
        import platform
        is_windows = platform.system() == "Windows"

        if base_script.suffix == ".py":
            cmd = ["python", str(base_script)] + script_args
        elif base_script.suffix == ".sh":
            if is_windows:
                # On Windows, try Git Bash or WSL, or skip shell scripts
                # For now, return an error message
                return f"Error: Shell scripts (.sh) are not supported on Windows. Please use Python scripts (.py) instead."
            else:
                cmd = ["bash", str(base_script)] + script_args
        else:
            # Try to execute directly
            cmd = [str(base_script)] + script_args

        # Execute the script
        logger.info(f"Executing skill '{skill_name}' entrypoint '{entrypoint_name}': {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            cwd=str(skill_dir),
            capture_output=True,
            text=True,
            timeout=30,  # 30 second timeout
        )

        # Combine stdout and stderr
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]: {result.stderr}"

        if result.returncode != 0:
            output += f"\n[exit code]: {result.returncode}"

        return output.strip() if output.strip() else f"Skill '{skill_name}' executed successfully (no output)"

    except subprocess.TimeoutExpired:
        return f"Error: Skill execution timed out after 30 seconds"
    except Exception as e:
        logger.error(f"Error executing skill '{skill_name}': {e}")
        return f"Error executing skill: {str(e)}"

