# AG3NT Developer Guide Skills

This folder contains **agent skills** designed to help any coding AI agent quickly understand and work with the AG3NT codebase.

## How to Use

Add these skills to your coding agent's context to bring it up to speed on AG3NT development. Each skill follows the standard AG3NT SKILL.md format and can be:

1. **Read directly** by the agent as context
2. **Loaded as skills** if your agent supports AG3NT's skill system
3. **Referenced progressively** - each skill points to deeper documentation

## Available Skills

| Skill | Purpose | Start Here When... |
|-------|---------|-------------------|
| **ag3nt-overview** | Platform vision, architecture, core concepts | You're new to AG3NT |
| **sprint-planning** | Realignment loop, sprint methodology | Starting a new sprint |
| **codebase-navigation** | Project structure, key files | Looking for specific code |
| **development-workflow** | Testing, Git, code quality | Ready to contribute |
| **ui-design-system** | Control Panel, TUI, UI patterns | Working on UI |
| **gap-analysis** | Identify missing features, prioritize work | Assessing what's missing |
| **testing** | Test strategies, patterns, commands | Writing or running tests |

## Quick Start for Agents

1. **First, read the overview**:
   ```
   read_file path="/dev-guide/ag3nt-overview/SKILL.md"
   ```

2. **Then check sprint planning** (includes the critical Realignment Loop):
   ```
   read_file path="/dev-guide/sprint-planning/SKILL.md"
   ```

3. **Navigate the codebase** when you need to find things:
   ```
   read_file path="/dev-guide/codebase-navigation/SKILL.md"
   ```

4. **Follow development workflow** when contributing:
   ```
   read_file path="/dev-guide/development-workflow/SKILL.md"
   ```

## Progressive Disclosure

Each skill references deeper documentation. When you need more detail:

- **Architecture**: `/docs/AG3NT_System_Architecture_and_Design.md`
- **Requirements**: `/docs/AG3NT_Product_Requirements_and_Functional_Requirements.md`
- **Roadmap**: `/docs/ROADMAP.md`
- **Sprint Details**: `/docs/SPRINT_1_2_TASK_BREAKDOWN.md`
- **Configuration**: `/docs/reference/CONFIGURATION.md`
- **Skill Development**: `/docs/guides/SKILL_DEVELOPMENT.md`
- **Testing Guide**: `/docs/guides/TESTING.md`

## Key Concepts to Remember

1. **Two-Service Architecture**: Gateway (TypeScript, port 18789) + Agent Worker (Python, port 18790)
2. **Realignment Loop**: ALWAYS read all docs before starting a new sprint
3. **Virtual Paths**: `/skills/`, `/user-data/`, `/workspace/`, `/global-skills/`
4. **HITL Approval**: Sensitive operations require human approval
5. **Single Canonical Path**: Never have duplicate implementations

## Updating These Skills

When AG3NT evolves, update these skills to reflect:
- Architecture changes
- New development practices
- Updated workflows
- New key files

Keep skills focused and reference docs for details (progressive disclosure).

