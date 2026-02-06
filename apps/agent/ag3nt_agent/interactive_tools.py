"""Interactive tools for user communication during agent execution.

This module provides tools that allow agents to ask users questions
and wait for responses during execution using the DeepAgents interrupt mechanism.
"""

from typing import Any, Literal
from langchain_core.tools import tool


@tool
def ask_user(
    question: str,
    options: list[str] | None = None,
    allow_custom: bool = True
) -> str:
    """Ask the user a clarifying question and wait for their response.

    Use this tool when you need user input to proceed with a task:
    - Choosing between multiple valid approaches
    - Confirming assumptions before taking action
    - Getting user preferences or requirements
    - Resolving ambiguity in the request
    - Obtaining information only the user knows

    The execution will pause until the user provides an answer.

    Args:
        question: The question to ask (be specific and clear)
        options: Optional list of predefined choices for multiple choice.
                If provided, user can select from these options.
        allow_custom: If True (default), allow user to provide custom answer
                     beyond the predefined options. If False, user must pick
                     from the provided options.

    Returns:
        The user's answer as a string

    Examples:
        # Simple yes/no question
        answer = ask_user(
            question="Should I create a new file or modify the existing one?",
            options=["Create new file", "Modify existing"],
            allow_custom=False
        )

        # Multiple choice with custom option
        format = ask_user(
            question="Which file format should I use for the config?",
            options=["JSON", "YAML", "TOML"]
        )

        # Open-ended question
        name = ask_user(
            question="What should the new API endpoint be called?",
            options=None
        )

    Raises:
        This tool uses interrupts, so it will pause execution and resume
        when the user provides an answer.
    """
    # This tool will trigger an interrupt through the interrupt_on configuration
    # The question metadata is passed through the tool arguments
    # The actual answer will be provided when execution resumes
    # For now, return a placeholder - the real answer comes from resume
    return "User response pending (will be provided when execution resumes)"


def get_interactive_tools() -> list:
    """Get all interactive tools.

    Returns:
        List of interactive tool instances
    """
    return [ask_user]
