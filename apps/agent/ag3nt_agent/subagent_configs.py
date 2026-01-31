"""Specialized subagent configurations for AG3NT.

This module provides:
- SubagentConfig: Dataclass for defining subagent specifications
- Predefined subagent types: 8 specialized agents for different tasks
- SUBAGENT_REGISTRY: Registry of all available subagents
- SubagentResourceLimits: Resource constraints for subagent execution
- SubagentResourceManager: Manages concurrent subagent limits
- ThinkingMode: Configurable thinking levels for reasoning tasks

Matches and exceeds Moltbot reference implementation capabilities.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class ThinkingMode(str, Enum):
    """Thinking mode levels for subagent reasoning.

    These control how much "thinking" the subagent does before responding.
    Higher levels = more tokens for reasoning = better for complex tasks.
    Matches Moltbot's thinking level implementation.
    """
    OFF = "off"  # No explicit reasoning
    MINIMAL = "minimal"  # Brief reasoning (1-2 sentences)
    LOW = "low"  # Light reasoning (~100 tokens)
    MEDIUM = "medium"  # Moderate reasoning (~300 tokens)
    HIGH = "high"  # Extended reasoning (~500 tokens)
    XHIGH = "xhigh"  # Maximum reasoning (~1000+ tokens)


class ContextPruningMode(str, Enum):
    """Context pruning modes for managing token usage in long-running sessions.

    Matches Moltbot's contextPruning.mode configuration.
    """
    OFF = "off"  # No context pruning
    CACHE_TTL = "cache-ttl"  # Time-based pruning with TTL
    AGGRESSIVE = "aggressive"  # Aggressive pruning to minimize context size


@dataclass
class ContextPruningConfig:
    """Configuration for context pruning in subagent sessions.

    Context pruning manages token usage by trimming old messages from the
    conversation history when it grows too large. This is essential for
    long-running subagent sessions that would otherwise exceed token limits.

    Matches Moltbot's contextPruning configuration.

    Attributes:
        mode: Pruning strategy (off, cache-ttl, aggressive).
        ttl_minutes: Time-to-live for cached context (for cache-ttl mode).
        keep_last_assistants: Number of recent assistant messages to always keep.
        soft_trim_ratio: Ratio (0.0-1.0) of max tokens where soft trimming begins.
        hard_clear_ratio: Ratio (0.0-1.0) of max tokens where hard clear is forced.
    """
    mode: ContextPruningMode = ContextPruningMode.OFF
    ttl_minutes: int = 30  # Default 30 minutes TTL
    keep_last_assistants: int = 3  # Always keep last 3 assistant messages
    soft_trim_ratio: float = 0.7  # Start trimming at 70% of max tokens
    hard_clear_ratio: float = 0.9  # Force clear at 90% of max tokens

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not 0.0 <= self.soft_trim_ratio <= 1.0:
            raise ValueError(f"soft_trim_ratio must be 0.0-1.0, got {self.soft_trim_ratio}")
        if not 0.0 <= self.hard_clear_ratio <= 1.0:
            raise ValueError(f"hard_clear_ratio must be 0.0-1.0, got {self.hard_clear_ratio}")
        if self.soft_trim_ratio >= self.hard_clear_ratio:
            raise ValueError(
                f"soft_trim_ratio ({self.soft_trim_ratio}) must be less than "
                f"hard_clear_ratio ({self.hard_clear_ratio})"
            )
        if self.ttl_minutes < 0:
            raise ValueError(f"ttl_minutes must be >= 0, got {self.ttl_minutes}")
        if self.keep_last_assistants < 0:
            raise ValueError(f"keep_last_assistants must be >= 0, got {self.keep_last_assistants}")


# Default context pruning configurations for different use cases
CONTEXT_PRUNING_OFF = ContextPruningConfig(mode=ContextPruningMode.OFF)
CONTEXT_PRUNING_STANDARD = ContextPruningConfig(
    mode=ContextPruningMode.CACHE_TTL,
    ttl_minutes=30,
    keep_last_assistants=3,
    soft_trim_ratio=0.7,
    hard_clear_ratio=0.9,
)
CONTEXT_PRUNING_AGGRESSIVE = ContextPruningConfig(
    mode=ContextPruningMode.AGGRESSIVE,
    ttl_minutes=10,
    keep_last_assistants=2,
    soft_trim_ratio=0.5,
    hard_clear_ratio=0.75,
)


@dataclass
class SubagentConfig:
    """Configuration for a specialized subagent.

    Matches and exceeds Moltbot's agent configuration model with:
    - Per-subagent model selection (model_override)
    - Thinking mode configuration
    - Context pruning settings
    - Sandboxing options

    Attributes:
        name: Unique identifier for the subagent type.
        description: What this subagent does (used by main agent for delegation).
        system_prompt: Instructions for the subagent.
        tools: List of tool names the subagent can use.
        max_tokens: Maximum tokens for subagent responses.
        max_turns: Maximum conversation turns before termination.
        model_override: Optional model to use instead of parent's model.
        thinking_mode: Reasoning level for this subagent.
        allow_sandbox: Whether this subagent can run in sandbox mode.
        priority: Execution priority (higher = more important).
        context_pruning: Configuration for context pruning in long sessions.
    """
    name: str
    description: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)
    max_tokens: int = 4096
    max_turns: int = 10
    model_override: str | None = None  # e.g., "anthropic/claude-3-opus"
    thinking_mode: ThinkingMode = ThinkingMode.MEDIUM
    allow_sandbox: bool = True
    priority: int = 5  # 1-10, higher = more priority
    context_pruning: ContextPruningConfig = field(default_factory=lambda: CONTEXT_PRUNING_OFF)


# =============================================================================
# PREDEFINED SUBAGENT CONFIGURATIONS
# =============================================================================

RESEARCHER = SubagentConfig(
    name="researcher",
    description=(
        "Research the web for current information, news, statistics, and sources. "
        "Use this PROACTIVELY before writing content, answering questions that require "
        "up-to-date information, or when the user asks about current events."
    ),
    system_prompt="""You are a research assistant specializing in finding and synthesizing information.

Your capabilities:
- Search the web for current information
- Fetch and read content from URLs
- Analyze and summarize findings
- Cross-reference multiple sources

Your process:
1. Analyze the research request to understand what information is needed
2. Make 2-3 targeted searches with specific queries
3. For promising results, fetch the full page content
4. Gather key statistics, quotes, facts, and examples
5. Return a clear, organized summary with source citations

Guidelines:
- Always include source URLs for facts and statistics
- Distinguish between facts and opinions
- Note when information might be outdated
- Be thorough but concise in your final report
- Highlight key insights""",
    tools=["internet_search", "fetch_url", "memory_search", "read_file"],
    max_tokens=12288,  # 3x original (4096 * 3)
    max_turns=20,  # 2x original (10 * 2)
    thinking_mode=ThinkingMode.MEDIUM,
    priority=7,
    context_pruning=CONTEXT_PRUNING_STANDARD,
)

CODER = SubagentConfig(
    name="coder",
    description=(
        "Write, analyze, debug, and execute code. Use for programming tasks, "
        "code reviews, technical implementations, and debugging."
    ),
    system_prompt="""You are a coding assistant specializing in writing high-quality code.

Your capabilities:
- Read and understand existing code
- Write new code following best practices
- Debug and fix issues
- Execute shell commands to test code
- Use git for version control

Your process:
1. Understand the programming task requirements
2. If modifying existing code, read the relevant files first
3. Write or edit code following best practices
4. Test the code if possible (run it, check for errors)
5. Report the results and any issues found

Guidelines:
- Follow the coding style of existing code when editing
- Write clear comments for complex logic
- Handle errors gracefully
- Prefer simple, readable solutions over clever ones
- Test your changes when possible""",
    tools=["read_file", "write_file", "edit_file", "shell", "git_status", "git_diff"],
    max_tokens=24576,  # 3x original (8192 * 3)
    max_turns=30,  # 2x original (15 * 2)
    thinking_mode=ThinkingMode.HIGH,
    priority=9,
    context_pruning=CONTEXT_PRUNING_STANDARD,  # Long sessions need pruning
)

REVIEWER = SubagentConfig(
    name="reviewer",
    description=(
        "Review code for quality, security, and best practices. "
        "Use for code reviews, security audits, and quality analysis."
    ),
    system_prompt="""You are a code reviewer specializing in finding issues and suggesting improvements.

Your capabilities:
- Analyze code for bugs and issues
- Check for security vulnerabilities
- Evaluate code quality and maintainability
- Suggest improvements and refactoring
- Review git diffs for changes

Your process:
1. Read the code or diff to understand the changes
2. Check for common issues: bugs, security, performance
3. Evaluate code style and maintainability
4. Provide specific, actionable feedback
5. Prioritize issues by severity

Guidelines:
- Be constructive, not just critical
- Explain why something is an issue
- Suggest specific fixes when possible
- Prioritize issues by severity (critical > major > minor)
- Acknowledge good patterns when you see them""",
    tools=["read_file", "git_diff", "git_log"],
    max_tokens=12288,  # 3x original (4096 * 3)
    max_turns=20,  # 2x original (10 * 2)
    thinking_mode=ThinkingMode.HIGH,
    priority=8,
    context_pruning=CONTEXT_PRUNING_STANDARD,
)

PLANNER = SubagentConfig(
    name="planner",
    description=(
        "Break down complex tasks into actionable steps. "
        "Use for project planning, task decomposition, and workflow design."
    ),
    system_prompt="""You are a planning assistant specializing in breaking down complex tasks.

Your capabilities:
- Analyze complex objectives
- Break tasks into subtasks
- Identify dependencies
- Estimate effort and complexity
- Create actionable todo lists

Your process:
1. Understand the overall objective
2. Identify major components or phases
3. Break each component into specific tasks
4. Order tasks by dependencies
5. Create a clear, actionable plan

Guidelines:
- Make tasks specific and measurable
- Identify blockers and dependencies
- Consider edge cases and risks
- Set realistic estimates
- Keep the plan flexible for adjustments""",
    tools=["write_todos", "read_todos", "update_todo"],
    max_tokens=6144,  # 3x original (2048 * 3)
    max_turns=16,  # 2x original (8 * 2)
    thinking_mode=ThinkingMode.HIGH,
    priority=8,
    # Planner has fewer turns, pruning not usually needed
)

# =============================================================================
# ADDITIONAL SPECIALIST SUBAGENTS (Matching Moltbot capabilities)
# =============================================================================

BROWSER = SubagentConfig(
    name="browser",
    description=(
        "Browse the web, interact with web pages, fill forms, and capture screenshots. "
        "Use for web automation, testing, and data extraction from dynamic websites."
    ),
    system_prompt="""You are a web automation specialist with browser control capabilities.

Your capabilities:
- Navigate to URLs and browse websites
- Interact with page elements (click, type, scroll)
- Fill out forms and submit them
- Capture screenshots for visual verification
- Extract data from rendered web pages
- Handle dynamic/JavaScript-heavy sites

Your process:
1. Navigate to the target URL
2. Wait for the page to load fully
3. Identify the elements you need to interact with
4. Perform actions (click, type, select)
5. Verify the result and capture evidence if needed

Guidelines:
- Wait for elements to be visible before interacting
- Take screenshots to document important states
- Handle popups and dialogs gracefully
- Respect rate limits and be polite to servers
- Report any access issues or CAPTCHAs""",
    tools=["browser_navigate", "browser_click", "browser_type", "browser_screenshot", "fetch_url"],
    max_tokens=8192,
    max_turns=20,
    thinking_mode=ThinkingMode.LOW,
    priority=6,
    context_pruning=CONTEXT_PRUNING_AGGRESSIVE,  # Browser sessions can get verbose
)

ANALYST = SubagentConfig(
    name="analyst",
    description=(
        "Analyze data, compute statistics, create visualizations, and provide insights. "
        "Use for data analysis, metrics computation, and reporting."
    ),
    system_prompt="""You are a data analyst specializing in extracting insights from data.

Your capabilities:
- Read and parse data files (CSV, JSON, etc.)
- Compute statistics and metrics
- Identify patterns and trends
- Create data summaries and reports
- Write analysis scripts when needed

Your process:
1. Understand the analysis objective
2. Load and explore the data
3. Clean and preprocess as needed
4. Compute relevant metrics and statistics
5. Summarize findings with key insights

Guidelines:
- Always validate data quality first
- Use appropriate statistical methods
- Quantify uncertainty when possible
- Present findings clearly with context
- Highlight actionable insights""",
    tools=["read_file", "write_file", "shell", "memory_search"],
    max_tokens=16384,
    max_turns=25,
    thinking_mode=ThinkingMode.HIGH,
    priority=7,
    context_pruning=CONTEXT_PRUNING_STANDARD,  # Data analysis can be lengthy
)

WRITER = SubagentConfig(
    name="writer",
    description=(
        "Write, edit, and refine content including documentation, articles, and reports. "
        "Use for content creation, editing, and technical writing."
    ),
    system_prompt="""You are a content writer specializing in clear, engaging writing.

Your capabilities:
- Write articles, documentation, and reports
- Edit and improve existing content
- Adapt tone and style for different audiences
- Research topics for accurate content
- Structure content for readability

Your process:
1. Understand the writing objective and audience
2. Research the topic if needed
3. Create an outline or structure
4. Write the initial draft
5. Review and refine for clarity and impact

Guidelines:
- Match the tone to the audience
- Use clear, concise language
- Structure content with headers and sections
- Support claims with evidence or examples
- Proofread for grammar and style""",
    tools=["read_file", "write_file", "internet_search", "fetch_url", "memory_search"],
    max_tokens=16384,
    max_turns=20,
    thinking_mode=ThinkingMode.MEDIUM,
    priority=6,
    context_pruning=CONTEXT_PRUNING_STANDARD,  # Content creation sessions
)

MEMORY = SubagentConfig(
    name="memory",
    description=(
        "Search, index, and manage the knowledge base and memory. "
        "Use to find relevant past information or store new knowledge."
    ),
    system_prompt="""You are a memory specialist managing the knowledge base.

Your capabilities:
- Search for relevant past information
- Index and store new knowledge
- Organize and categorize information
- Find connections between pieces of information
- Summarize and consolidate knowledge

Your process:
1. Understand the information need
2. Search existing memory for relevant content
3. If storing, categorize and structure the information
4. If retrieving, synthesize and present findings
5. Suggest related information that might be relevant

Guidelines:
- Be thorough in searches
- Use multiple search terms for better coverage
- Organize stored information consistently
- Note the source and date of information
- Highlight confidence levels in retrieved info""",
    tools=["memory_search", "memory_store", "read_file", "write_file"],
    max_tokens=8192,
    max_turns=15,
    thinking_mode=ThinkingMode.MEDIUM,
    priority=5,
    # Memory agent has short turns, pruning usually not needed
)


# =============================================================================
# SUBAGENT REGISTRY
# =============================================================================

SUBAGENT_REGISTRY: dict[str, SubagentConfig] = {
    "researcher": RESEARCHER,
    "coder": CODER,
    "reviewer": REVIEWER,
    "planner": PLANNER,
    "browser": BROWSER,
    "analyst": ANALYST,
    "writer": WRITER,
    "memory": MEMORY,
}


def get_subagent_config(name: str) -> SubagentConfig:
    """Get a subagent configuration by name.

    Args:
        name: The subagent type name.

    Returns:
        The SubagentConfig for the requested type.

    Raises:
        ValueError: If the subagent type is not found.
    """
    if name not in SUBAGENT_REGISTRY:
        available = list(SUBAGENT_REGISTRY.keys())
        raise ValueError(f"Unknown subagent: {name}. Available: {available}")
    return SUBAGENT_REGISTRY[name]


def list_subagent_types() -> list[str]:
    """List all available subagent types.

    Returns:
        List of subagent type names.
    """
    return list(SUBAGENT_REGISTRY.keys())


# =============================================================================
# RESOURCE LIMITS
# =============================================================================

@dataclass
class SubagentResourceLimits:
    """Resource limits for subagent execution.

    Attributes:
        max_execution_time_seconds: Maximum time a subagent can run.
        max_turns: Maximum conversation turns per subagent.
        max_tokens: Maximum tokens per subagent response.
        max_tool_calls: Maximum tool calls per subagent execution.
        max_concurrent_subagents: Maximum subagents running simultaneously.
        max_subagent_depth: Maximum nesting depth (subagents spawning subagents).
    """
    max_execution_time_seconds: float = 120.0
    max_turns: int = 10
    max_tokens: int = 8192
    max_tool_calls: int = 20
    max_concurrent_subagents: int = 3
    max_subagent_depth: int = 2


class SubagentResourceManager:
    """Manages resource limits for subagent execution.

    This class tracks active subagents and enforces concurrency limits
    to prevent resource exhaustion.
    """

    def __init__(self, limits: SubagentResourceLimits | None = None):
        """Initialize the resource manager.

        Args:
            limits: Resource limits to enforce. Uses defaults if None.
        """
        self.limits = limits or SubagentResourceLimits()
        self.active_count = 0
        self._active_ids: set[str] = set()

    def can_spawn(self) -> tuple[bool, str | None]:
        """Check if a new subagent can be spawned.

        Returns:
            Tuple of (can_spawn, reason_if_not).
        """
        if self.active_count >= self.limits.max_concurrent_subagents:
            return False, (
                f"Max concurrent subagents reached "
                f"({self.limits.max_concurrent_subagents})"
            )
        return True, None

    def acquire(self, execution_id: str) -> bool:
        """Acquire a slot for a new subagent.

        Args:
            execution_id: Unique identifier for the subagent execution.

        Returns:
            True if slot acquired, False if limit reached.
        """
        can_spawn, _ = self.can_spawn()
        if can_spawn:
            self.active_count += 1
            self._active_ids.add(execution_id)
            return True
        return False

    def release(self, execution_id: str) -> None:
        """Release a subagent slot.

        Args:
            execution_id: The execution ID to release.
        """
        if execution_id in self._active_ids:
            self._active_ids.discard(execution_id)
            self.active_count = max(0, self.active_count - 1)

    def check_limits(
        self,
        execution_time: float,
        turns: int,
        tokens: int,
        tool_calls: int,
    ) -> tuple[bool, str | None]:
        """Check if execution is within limits.

        Args:
            execution_time: Time elapsed in seconds.
            turns: Number of conversation turns.
            tokens: Number of tokens used.
            tool_calls: Number of tool calls made.

        Returns:
            Tuple of (within_limits, reason_if_exceeded).
        """
        if execution_time > self.limits.max_execution_time_seconds:
            return False, (
                f"Max execution time exceeded "
                f"({execution_time:.1f}s > {self.limits.max_execution_time_seconds}s)"
            )
        if turns > self.limits.max_turns:
            return False, f"Max turns exceeded ({turns} > {self.limits.max_turns})"
        if tokens > self.limits.max_tokens:
            return False, f"Max tokens exceeded ({tokens} > {self.limits.max_tokens})"
        if tool_calls > self.limits.max_tool_calls:
            return False, (
                f"Max tool calls exceeded ({tool_calls} > {self.limits.max_tool_calls})"
            )
        return True, None

    def get_active_count(self) -> int:
        """Get the number of active subagents.

        Returns:
            Number of currently active subagents.
        """
        return self.active_count

    def get_active_ids(self) -> set[str]:
        """Get the IDs of active subagent executions.

        Returns:
            Set of active execution IDs.
        """
        return self._active_ids.copy()

