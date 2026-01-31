# AG3NT → Claude Code CLI Feature Parity Plan

**Goal:** Bring AG3NT to feature parity with Claude Code CLI while maintaining AG3NT's unique multi-channel, local-first architecture.

**Status:** In Progress
**Last Updated:** 2026-01-31

---

## Executive Summary

AG3NT already has a solid foundation with 8 specialized subagents, task management, comprehensive Git operations, and multi-channel support. The main gaps are:
- Interactive user questioning during execution
- Structured plan mode before code execution
- Automated Git workflows (commit messages, PR creation)
- Background task execution
- Jupyter notebook support
- Keybinding customization

This document outlines the implementation plan for each feature in priority order.

---

## Feature Comparison Matrix

| Feature | Claude Code | AG3NT Status | Priority | Complexity |
|---------|-------------|--------------|----------|------------|
| Edit Tool (string replacement) | ✅ | ✅ Exists, needs docs | P0 | Simple |
| AskUserQuestion | ✅ | ❌ Missing | P0 | Simple |
| Plan Mode | ✅ | 🟡 Partial (task persistence only) | P0 | Moderate |
| Git Commit Protocol | ✅ | 🟡 Basic ops only | P1 | Moderate |
| PR Creation | ✅ | ❌ Missing | P1 | Moderate |
| Specialized Agents | ✅ | ✅ 8 subagents | ✅ | Done |
| Task Management | ✅ | ✅ Via planning_tools.py | ✅ | Done |
| WebSearch | ✅ | ✅ Tavily + DuckDuckGo | ✅ | Done |
| Background Tasks | ✅ | ❌ Missing | P2 | Complex |
| Jupyter Support | ✅ | ❌ Missing | P2 | Moderate |
| Keybindings | ✅ | 🟡 Hardcoded in TUI | P2 | Simple |

**Legend:**
- P0 = Critical path (must-have)
- P1 = High value (important)
- P2 = Enhancement (nice-to-have)

---

## Implementation Phases

### Phase 0: Documentation & Quick Wins (Days 1-2)

#### 1. Edit Tool Documentation ⭐ STARTING HERE
**Status:** Not Started
**Effort:** 1 day
**Files:**
- `apps/agent/ag3nt_agent/deepagents_runtime.py` - Update system prompt

**Implementation:**
AG3NT already has `edit_file(path, old_str, new_str)` via DeepAgents FilesystemBackend. We just need to document it properly in the system prompt.

**Tasks:**
- [ ] Add edit_file guidance to system prompt in deepagents_runtime.py
- [ ] Include examples of when to use edit_file vs write_file
- [ ] Add best practices (exact string matching, whitespace handling)
- [ ] Test with subagents (especially CODER subagent)

**System Prompt Addition:**
```python
## File Editing

For precise modifications to existing files, use edit_file instead of write_file:

edit_file(path, old_str, new_str)
- path: File path (use /workspace/ prefix for user files)
- old_str: Exact string to replace (including whitespace and indentation)
- new_str: Replacement string

Benefits:
- Preserves rest of file unchanged
- Verifies exact match before applying
- Less error-prone than rewriting entire file
- Safer for large files

When to use edit_file:
✅ Small, targeted changes (function rename, parameter change, bug fix)
✅ When you know exact context around change
✅ Modifying configuration values

When to use write_file:
✅ Creating new files
✅ Completely restructuring a file
✅ When multiple scattered changes needed

Example:
# Change timeout value
edit_file(
    path="/workspace/config.py",
    old_str="TIMEOUT = 30",
    new_str="TIMEOUT = 60"
)
```

**Verification:**
- Ask CODER subagent to make small code changes
- Verify it chooses edit_file appropriately
- Check that edits are precise and correct

---

### Phase 1: Core Interactivity (Days 3-10)

#### 2. AskUserQuestion Tool ⭐ HIGH PRIORITY
**Status:** Not Started
**Effort:** 3-5 days
**Files:**
- `apps/agent/ag3nt_agent/interactive_tools.py` (NEW)
- `apps/agent/ag3nt_agent/deepagents_runtime.py` (tool registration)
- `apps/gateway/src/gateway/createGateway.ts` (question/answer handling)
- `apps/gateway/src/routes/chat.ts` (resume with answers)

**Architecture:**
Uses DeepAgents interrupt mechanism (similar to HITL approval) to pause execution and wait for user response.

**Implementation Steps:**

1. **Create Interactive Tool** (`interactive_tools.py`):
```python
from langchain_core.tools import tool
from typing import Literal

@tool
def ask_user(
    question: str,
    options: list[str] | None = None,
    allow_custom: bool = True
) -> str:
    """Ask the user a clarifying question and wait for their response.

    Use this when you need user input to proceed:
    - Choosing between multiple approaches
    - Confirming assumptions
    - Getting preferences or requirements
    - Resolving ambiguity

    Args:
        question: The question to ask (be specific and clear)
        options: Optional list of choices for multiple choice
        allow_custom: Allow user to provide custom answer beyond options

    Returns:
        User's answer as a string

    Examples:
        # Simple question
        answer = ask_user("Which file format should I use?",
                         options=["JSON", "YAML", "TOML"])

        # Open-ended
        answer = ask_user("What should the API endpoint be named?")
    """
    # Implementation uses interrupt mechanism
    pass
```

2. **Interrupt Mechanism**:
- Use `Command(interrupt=...)` to pause execution
- Store question in interrupt metadata
- Gateway detects special interrupt type: `"user_question"`
- Return format:
```json
{
  "ok": true,
  "questionPending": true,
  "question": "Which file format should I use?",
  "options": ["JSON", "YAML", "TOML"],
  "allowCustom": true,
  "interrupt_id": "abc123",
  "session_id": "xyz789"
}
```

3. **Gateway Handling**:
```typescript
// In chat.ts
if (result.interrupt?.type === 'user_question') {
  return res.json({
    ok: true,
    questionPending: true,
    question: result.interrupt.question,
    options: result.interrupt.options,
    allowCustom: result.interrupt.allowCustom,
    interrupt_id: result.interrupt.interrupt_id,
    session_id: req.body.session_id
  });
}
```

4. **Resume Endpoint**:
```typescript
// POST /api/chat/answer
{
  "session_id": "xyz789",
  "interrupt_id": "abc123",
  "answer": "YAML"
}

// Calls worker /resume with answer in decisions
```

5. **Client Integration**:
- CLI: Prompt user with readline
- TUI: Show dialog box with options
- Messaging: Send question, wait for user reply

**Testing:**
- Unit test: Tool registration and metadata
- Integration test: Question → pause → answer → resume flow
- E2E test: Complete workflow in CLI/TUI

**Verification:**
- Agent can ask questions mid-execution
- User sees clear question with options
- Execution resumes seamlessly with answer

---

#### 3. Plan Mode ⭐ HIGH PRIORITY
**Status:** Not Started
**Effort:** 5-7 days
**Files:**
- `apps/agent/ag3nt_agent/planning_middleware.py` (NEW)
- `apps/agent/ag3nt_agent/deepagents_runtime.py` (middleware integration)
- `apps/gateway/src/routes/chat.ts` (plan_mode flag)
- `apps/cli/cli.ts` (--plan flag)
- `apps/tui/ag3nt_tui.py` (plan mode toggle)

**Architecture:**
Middleware-based system that intercepts requests and forces structured planning before execution.

**Implementation Steps:**

1. **Create PlanningMiddleware** (`planning_middleware.py`):
```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class PlanningState:
    """Tracks planning mode state across turns."""
    enabled: bool = False
    planning_phase: bool = True  # True = planning, False = executing
    plan_confirmed: bool = False
    plan_tasks: list[str] = field(default_factory=list)
    current_task_index: int = 0

class PlanningMiddleware:
    """Middleware that enforces planning before execution."""

    def __init__(self):
        self.sessions: dict[str, PlanningState] = {}

    async def __call__(self, state: dict, config: dict) -> dict:
        """Intercept agent execution to enforce planning."""
        thread_id = config["configurable"]["thread_id"]

        # Get or create planning state for this session
        if thread_id not in self.sessions:
            # Check if plan_mode enabled in metadata
            plan_mode = config.get("metadata", {}).get("plan_mode", False)
            self.sessions[thread_id] = PlanningState(enabled=plan_mode)

        plan_state = self.sessions[thread_id]

        if not plan_state.enabled:
            return state  # Pass through if not in plan mode

        if plan_state.planning_phase and not plan_state.plan_confirmed:
            # Inject planning instructions into system prompt
            state = self._inject_planning_prompt(state)
        elif plan_state.plan_confirmed:
            # Inject execution guidance with task tracking
            state = self._inject_execution_prompt(state, plan_state)

        return state

    def _inject_planning_prompt(self, state: dict) -> dict:
        """Add planning instructions to system prompt."""
        planning_instruction = """

        🎯 PLANNING MODE ACTIVE

        You are in planning mode. Before executing any actions, you MUST:

        1. **Analyze the Request**
           - Break down what the user is asking for
           - Identify all files that need to be read or modified
           - Note any ambiguities or questions

        2. **Create a Detailed Plan**
           Use write_todos to create tasks with:
           - Clear, actionable descriptions
           - Logical order (dependencies first)
           - Estimated complexity for each task
           - Files involved in each task

        3. **Present for Approval**
           - Summarize the plan in your response
           - List all tasks clearly
           - Note any assumptions or risks
           - Ask user to confirm before proceeding

        4. **Wait for Confirmation**
           - DO NOT execute any code changes yet
           - DO NOT write, edit, or delete files
           - Only READ files to understand context

        Format your plan as:

        ## Implementation Plan

        **Summary:** [1-2 sentence overview]

        **Tasks:**
        1. [Task description] - Files: [...] - Complexity: [Low/Med/High]
        2. [Task description] - Files: [...] - Complexity: [Low/Med/High]
        ...

        **Assumptions:**
        - [List any assumptions]

        **Risks:**
        - [Note potential issues]

        **Ready to proceed?** (User will confirm)
        """

        # Prepend to system message
        state["system_message"] = state.get("system_message", "") + planning_instruction
        return state

    def _inject_execution_prompt(self, state: dict, plan_state: PlanningState) -> dict:
        """Add execution guidance with progress tracking."""
        execution_instruction = f"""

        ✅ PLAN APPROVED - EXECUTION MODE

        Execute the approved plan step-by-step:

        Current Progress: Task {plan_state.current_task_index + 1}/{len(plan_state.plan_tasks)}

        For each task:
        1. Announce which task you're starting
        2. Execute the task carefully
        3. Verify the changes work
        4. Mark task complete with update_todo
        5. Move to next task

        Report progress after each task completion.
        """

        state["system_message"] = state.get("system_message", "") + execution_instruction
        return state

    def confirm_plan(self, thread_id: str, tasks: list[str]):
        """User confirmed the plan, switch to execution mode."""
        if thread_id in self.sessions:
            plan_state = self.sessions[thread_id]
            plan_state.plan_confirmed = True
            plan_state.planning_phase = False
            plan_state.plan_tasks = tasks

    def advance_task(self, thread_id: str):
        """Move to next task in plan."""
        if thread_id in self.sessions:
            self.sessions[thread_id].current_task_index += 1
```

2. **Integration in deepagents_runtime.py**:
```python
# Create middleware instance
planning_middleware = PlanningMiddleware()

# Add to middleware list
middleware_list = [
    shell_middleware,
    SkillTriggerMiddleware(),
    planning_middleware,  # Add here
]
```

3. **Gateway Support** (`chat.ts`):
```typescript
// Accept plan_mode flag
POST /api/chat
{
  "text": "Add user authentication",
  "session_id": "abc123",
  "plan_mode": true  // Enable planning
}

// Plan confirmation endpoint
POST /api/chat/confirm-plan
{
  "session_id": "abc123",
  "tasks": ["Task 1", "Task 2", ...]
}
```

4. **CLI Flag** (`cli.ts`):
```typescript
// Add --plan flag
if (process.argv.includes('--plan')) {
  planMode = true;
}

const response = await axios.post(`${gatewayUrl}/api/chat`, {
  text: message,
  session_id: sessionId,
  plan_mode: planMode
});
```

5. **TUI Toggle** (`ag3nt_tui.py`):
```python
# Add keybinding: Ctrl+Shift+P for plan mode toggle
self.plan_mode = False

def toggle_plan_mode(self):
    self.plan_mode = not self.plan_mode
    self.update_status_bar()  # Show "PLAN MODE" indicator
```

**Testing:**
- Unit test: Middleware injection logic
- Integration test: Planning phase → confirmation → execution flow
- E2E test: Full workflow with real tasks

**Verification:**
- Agent creates structured plan before executing
- User can review and approve plan
- Execution follows plan step-by-step
- Progress tracking works correctly

---

### Phase 2: Git Workflow Automation (Days 11-18)

#### 4. Git Commit Message Generation
**Status:** Not Started
**Effort:** 3-4 days
**Files:**
- `apps/agent/ag3nt_agent/git_tool.py` (enhance existing)
- `apps/agent/ag3nt_agent/deepagents_runtime.py` (system prompt update)

**Implementation:**
Add LLM-powered commit message generation following Conventional Commits format.

**Tasks:**
- [ ] Add `generate_commit_message()` method to GitTool
- [ ] Update system prompt with Git workflow guidance
- [ ] Add commit message validation
- [ ] Support Co-Authored-By attribution

**Details:** See full spec in Phase 2 section below.

---

#### 5. PR Creation Workflow
**Status:** Not Started
**Effort:** 2-3 days
**Files:**
- `apps/agent/ag3nt_agent/git_tool.py` (enhance)
- Dependencies: `gh` CLI tool

**Implementation:**
Automate PR creation using GitHub CLI with LLM-generated descriptions.

**Tasks:**
- [ ] Add `create_pull_request()` method
- [ ] Integrate with `gh` CLI via shell
- [ ] Generate PR title and body from commits
- [ ] Add test plan template

**Details:** See full spec in Phase 2 section below.

---

### Phase 3: Advanced Features (Days 19-35)

#### 6. Keyboard Shortcuts Customization
**Status:** Not Started
**Effort:** 2-3 days
**Files:**
- `apps/tui/keybindings.py` (NEW)
- `~/.ag3nt/keybindings.yaml` (user config)

**Implementation:**
Allow users to customize TUI keyboard shortcuts.

---

#### 7. Jupyter Notebook Support
**Status:** Not Started
**Effort:** 5-7 days
**Files:**
- `apps/agent/ag3nt_agent/notebook_tools.py` (NEW)
- Dependencies: `nbformat`, `nbconvert`

**Implementation:**
Add tools for reading, parsing, and executing Jupyter notebooks.

---

#### 8. Background Task Execution
**Status:** Not Started
**Effort:** 10-14 days
**Files:**
- `apps/gateway/src/jobs/BackgroundJobManager.ts` (NEW)
- `apps/gateway/src/routes/jobs.ts` (NEW)
- `apps/agent/ag3nt_agent/worker.py` (async execution)

**Implementation:**
Complex feature requiring job queue, progress tracking, and cancellation support.

---

## Phase 2: Git Workflow Automation (Detailed Spec)

### Git Commit Message Generation

**Conventional Commits Format:**
```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `refactor`: Code restructuring without behavior change
- `test`: Test additions/changes
- `chore`: Maintenance tasks
- `perf`: Performance improvements
- `style`: Code style/formatting changes

**Implementation in GitTool:**

```python
# In git_tool.py

def generate_commit_message(
    self,
    staged_files: list[str],
    diff_output: str,
    recent_commits: str,
    llm: BaseChatModel
) -> str:
    """Generate conventional commit message from staged changes.

    Args:
        staged_files: List of staged file paths
        diff_output: Output from git diff --staged
        recent_commits: Recent commit messages for style reference
        llm: Language model for generation

    Returns:
        Generated commit message following Conventional Commits
    """
    prompt = f"""Generate a git commit message for the following changes.

Follow the Conventional Commits format:
<type>(<scope>): <description>

Types: feat, fix, docs, refactor, test, chore, perf, style

Rules:
- Keep description under 72 characters
- Use imperative mood ("Add feature" not "Added feature")
- Focus on WHAT changed and WHY, not HOW
- Be specific and concise
- Scope is optional but helpful (e.g., "feat(auth): add login endpoint")

Recent commits for style reference:
{recent_commits}

Staged files:
{', '.join(staged_files)}

Changes:
{diff_output[:3000]}  # Truncate if too long

Generate ONLY the commit message, nothing else.
"""

    response = llm.invoke(prompt)
    message = response.content.strip()

    # Add Co-Authored-By footer
    message += "\n\nCo-Authored-By: AG3NT Agent <noreply@ag3nt.dev>"

    return message

def smart_commit(
    self,
    files: list[str] | None = None,
    auto_message: bool = True,
    message: str | None = None,
    llm: BaseChatModel | None = None
) -> GitResult:
    """Intelligent commit with auto-generated message.

    Args:
        files: Files to stage (None = stage all changes)
        auto_message: Generate commit message automatically
        message: Manual commit message (overrides auto_message)
        llm: Language model for message generation

    Returns:
        GitResult with commit hash and message
    """
    # Stage files
    if files:
        for file in files:
            self.add(file)
    else:
        self.add(".")

    # Generate or use provided message
    if message:
        commit_msg = message
    elif auto_message and llm:
        # Get info for generation
        staged = self.diff(staged=True)
        recent = self.log(max_count=5, oneline=True)
        commit_msg = self.generate_commit_message(
            files or ["all changes"],
            staged.stdout,
            recent.stdout,
            llm
        )
    else:
        raise ValueError("Must provide message or enable auto_message with llm")

    # Commit
    return self.commit(commit_msg)
```

**System Prompt Update:**

```python
git_workflow_guidance = """
## Git Workflow Best Practices

### Creating Commits

When the user asks to commit changes:

1. **Review Changes**
   ```python
   status = git_status()
   diff = git_diff(staged=False)  # See unstaged changes
   ```

2. **Stage Files**
   - Be selective: Only stage related changes
   - Avoid staging unrelated files together
   ```python
   git_add(["file1.py", "file2.py"])  # Specific files
   # NOT: git_add(["."])  # Stages everything
   ```

3. **Generate Commit Message**
   - Use Conventional Commits format
   - Run `generate_commit_message()` or use `smart_commit()`
   - Types: feat, fix, docs, refactor, test, chore, perf, style
   - Keep description under 72 characters
   - Be specific: "feat(auth): add JWT token validation" not "update auth"

4. **Commit**
   ```python
   # Auto-generated message
   result = smart_commit(files=["src/auth.py"], auto_message=True)

   # Manual message
   result = git_commit("feat(api): add user registration endpoint")
   ```

5. **Verify**
   ```python
   log = git_log(max_count=1)  # Check last commit
   ```

### Commit Message Examples

✅ Good:
- `feat(auth): add password reset functionality`
- `fix(api): resolve null pointer in user lookup`
- `docs(readme): update installation instructions`
- `refactor(db): extract query builder to separate class`

❌ Bad:
- `updated files` (too vague)
- `fix bug` (not specific)
- `WIP` (not descriptive)
- `changes` (meaningless)

### Safety Checks

Before committing:
- Ensure no sensitive data (API keys, passwords, tokens)
- Check for debug code or console.logs
- Verify tests pass
- Review diff carefully
"""
```

---

### PR Creation Workflow

**Requirements:**
- GitHub CLI (`gh`) installed
- Repository has remote on GitHub
- User authenticated with `gh auth login`

**Implementation in GitTool:**

```python
def create_pull_request(
    self,
    title: str | None = None,
    body: str | None = None,
    base: str = "main",
    draft: bool = False,
    auto_generate: bool = True,
    llm: BaseChatModel | None = None
) -> GitResult:
    """Create a GitHub pull request.

    Args:
        title: PR title (auto-generated if None and auto_generate=True)
        body: PR description (auto-generated if None)
        base: Base branch to merge into
        draft: Create as draft PR
        auto_generate: Auto-generate title and body from commits
        llm: Language model for generation

    Returns:
        GitResult with PR URL
    """
    # Get current branch
    current_branch = self._get_current_branch()

    if current_branch == base:
        return GitResult(
            success=False,
            error=f"Cannot create PR: already on base branch '{base}'"
        )

    # Generate title and body if needed
    if auto_generate and llm:
        # Get commits since divergence from base
        log_result = self.log(
            max_count=50,
            pretty="format:%H %s",
            extra_args=[f"{base}..HEAD"]
        )

        # Get full diff
        diff_result = self.diff(
            ref1=base,
            ref2="HEAD",
            stat=True
        )

        # Generate PR content
        pr_content = self._generate_pr_content(
            commits=log_result.stdout,
            diff=diff_result.stdout,
            llm=llm
        )

        title = title or pr_content["title"]
        body = body or pr_content["body"]

    # Push current branch to remote
    push_result = self.push(set_upstream=True)
    if not push_result.success:
        return push_result

    # Create PR using gh CLI
    gh_args = [
        "gh", "pr", "create",
        "--title", title,
        "--body", body,
        "--base", base
    ]

    if draft:
        gh_args.append("--draft")

    # Execute gh CLI
    result = subprocess.run(
        gh_args,
        cwd=self.repo_path,
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        pr_url = result.stdout.strip()
        return GitResult(
            success=True,
            stdout=pr_url,
            message=f"Pull request created: {pr_url}"
        )
    else:
        return GitResult(
            success=False,
            stderr=result.stderr,
            error="Failed to create pull request"
        )

def _generate_pr_content(
    self,
    commits: str,
    diff: str,
    llm: BaseChatModel
) -> dict[str, str]:
    """Generate PR title and description from commits and diff."""
    prompt = f"""Generate a GitHub pull request title and description for the following changes.

Commits:
{commits}

Diff summary:
{diff[:1000]}

Generate:
1. **Title** (max 72 chars) - Concise summary of changes
2. **Description** - Detailed explanation with:
   - ## Summary: What changed and why
   - ## Changes: Bullet list of key changes
   - ## Testing: How to test/verify changes
   - ## Related Issues: Link any related issues

Use markdown formatting for the description.
Output format:
TITLE: <title here>
DESCRIPTION:
<description here>
"""

    response = llm.invoke(prompt)
    content = response.content

    # Parse response
    lines = content.split('\n')
    title = ""
    description_lines = []
    in_description = False

    for line in lines:
        if line.startswith("TITLE:"):
            title = line.replace("TITLE:", "").strip()
        elif line.startswith("DESCRIPTION:"):
            in_description = True
        elif in_description:
            description_lines.append(line)

    description = '\n'.join(description_lines).strip()

    # Add footer
    description += "\n\n---\n🤖 Generated by AG3NT"

    return {
        "title": title,
        "body": description
    }
```

**System Prompt Update:**

```python
pr_workflow_guidance = """
## Pull Request Creation

When user asks to create a PR:

1. **Verify Prerequisites**
   - Check current branch: `git_status()`
   - Ensure not on main/master branch
   - Check for uncommitted changes
   - Verify gh CLI available: Check for gh command

2. **Review Changes**
   ```python
   # Get all commits on branch
   commits = git_log(extra_args=["main..HEAD"])

   # Get diff summary
   diff = git_diff(ref1="main", ref2="HEAD", stat=True)
   ```

3. **Create PR**
   ```python
   # Auto-generated title and description
   result = create_pull_request(
       base="main",
       auto_generate=True
   )

   # Manual
   result = create_pull_request(
       title="feat: Add user authentication system",
       body="## Summary\n...",
       base="main"
   )
   ```

4. **Return PR URL**
   - Show user the PR URL
   - Summarize what was included
   - Mention any follow-up actions

### PR Description Template

```markdown
## Summary
[1-2 sentences: What does this PR do and why?]

## Changes
- Added X feature to handle Y
- Modified Z component to support W
- Refactored A for better B

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed
- [ ] Tested on [environment]

## Related Issues
Closes #123
Relates to #456
```

### Safety Checks

Before creating PR:
- ✅ All tests passing
- ✅ No merge conflicts with base branch
- ✅ Commits are clean and well-documented
- ✅ No WIP or debug commits
- ✅ Branch is up to date with base
"""
```

---

## Testing Strategy

### Unit Tests
- Each new tool has dedicated unit tests
- Test tool metadata, parameters, validation
- Mock external dependencies (LLM, git, shell)

### Integration Tests
- Test tool integration with DeepAgents
- Test middleware injection and state management
- Test Gateway ↔ Worker communication

### End-to-End Tests
- Full user workflows in CLI and TUI
- Plan mode: request → plan → approve → execute
- Git workflow: changes → commit → PR
- Interactive questions: ask → answer → resume

### Test Files Structure
```
apps/agent/tests/
├── unit/
│   ├── test_interactive_tools.py
│   ├── test_planning_middleware.py
│   ├── test_git_workflows.py
│   └── test_notebook_tools.py
├── integration/
│   ├── test_plan_mode_integration.py
│   ├── test_question_flow.py
│   └── test_git_integration.py
└── e2e/
    ├── test_complete_workflows.py
    └── test_multi_channel.py
```

---

## Documentation Updates

### 1. System Prompt (deepagents_runtime.py)
- Add guidance for each new tool
- Include examples and best practices
- Update with workflow patterns

### 2. API Documentation (API.md)
- Document new endpoints
- Add request/response examples
- Note authentication requirements

### 3. User Guide (README.md)
- Add feature documentation
- Include usage examples
- Update CLI flags and options

### 4. Skills
Create skills for common workflows:
- `/skills/plan-and-execute/SKILL.md`
- `/skills/smart-commit/SKILL.md`
- `/skills/create-pr/SKILL.md`

---

## Migration & Backwards Compatibility

All features are **opt-in** and **backwards compatible**:

- Plan mode: Disabled by default, enable with `--plan` flag or `plan_mode: true`
- AskUserQuestion: Optional tool, only used when agent needs clarification
- Git workflows: Extend existing GitTool, old methods still work
- Background execution: New endpoints, doesn't affect existing sync API
- Jupyter support: New tools, doesn't affect existing file tools
- Keybindings: Defaults match current hardcoded bindings

**No breaking changes to existing functionality.**

---

## Success Metrics

### Feature Completeness
- ✅ All P0 features implemented and tested
- ✅ All P1 features implemented and tested
- ✅ At least 2 P2 features implemented

### Code Quality
- ✅ >80% test coverage for new code
- ✅ All tests passing
- ✅ No regression in existing functionality
- ✅ Documentation complete

### User Experience
- ✅ Features work across CLI, TUI, and messaging channels
- ✅ Error messages are clear and actionable
- ✅ Performance impact <10% on average turn time
- ✅ Positive user feedback

---

## Critical Files Reference

### Core Implementation Files
1. `apps/agent/ag3nt_agent/deepagents_runtime.py` - Central runtime, tool registration, system prompt
2. `apps/agent/ag3nt_agent/interactive_tools.py` - NEW - AskUserQuestion tool
3. `apps/agent/ag3nt_agent/planning_middleware.py` - NEW - Plan mode implementation
4. `apps/agent/ag3nt_agent/git_tool.py` - Git workflow enhancements
5. `apps/gateway/src/gateway/createGateway.ts` - Gateway routing and WebSocket

### Supporting Files
6. `apps/gateway/src/routes/chat.ts` - Chat API with interrupts
7. `apps/cli/cli.ts` - CLI interface and flags
8. `apps/tui/ag3nt_tui.py` - TUI with keybindings
9. `apps/agent/ag3nt_agent/notebook_tools.py` - NEW - Jupyter support
10. `apps/gateway/src/jobs/BackgroundJobManager.ts` - NEW - Background jobs

---

## Next Steps

1. ✅ Document Edit tool (this is first task)
2. ⬜ Implement AskUserQuestion
3. ⬜ Implement Plan Mode
4. ⬜ Add Git workflow automation
5. ⬜ Add remaining P2 features

---

**Last Updated:** 2026-01-31
**Maintainer:** AG3NT Development Team
