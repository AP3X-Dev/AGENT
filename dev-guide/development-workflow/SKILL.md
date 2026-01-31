---
name: development-workflow
description: Guide to AG3NT development workflow including testing, Git practices, code contribution, and quality standards.
version: "1.0.0"
tags:
  - development
  - testing
  - git
  - workflow
triggers:
  - "how to test"
  - "run tests"
  - "git workflow"
  - "contribute code"
  - "development setup"
required_permissions: []
license: MIT
compatibility: AG3NT 1.x
metadata:
  author: ag3nt-team
  category: development
---

# Development Workflow Guide

Use this skill when working on AG3NT: testing, Git workflow, code contributions, and quality standards.

## Starting AG3NT for Development

```powershell
# Windows
.\start.ps1

# Unix
./start.sh
```

This starts both Gateway (port 18789) and Agent Worker (port 18790).

To stop:
```powershell
.\stop.ps1  # Windows - kills all AG3NT processes
```

## Testing

### Python Tests (Agent Worker)

```bash
cd apps/agent

# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=ag3nt_agent --cov-report=html

# Run only unit tests
uv run pytest -m unit

# Run specific test file
uv run pytest tests/unit/test_shell_security.py -v
```

### TypeScript Tests (Gateway)

```bash
cd apps/gateway

# Run all tests
npm test

# Run with coverage
npm run test:coverage

# Watch mode
npm run test:watch
```

### Test Categories

| Category | Marker/Pattern | Speed | I/O |
|----------|----------------|-------|-----|
| Unit | `@pytest.mark.unit` | Fast | No |
| Integration | `@pytest.mark.integration` | Medium | Yes |
| E2E | `@pytest.mark.e2e` | Slow | Yes |

### Coverage Targets

| Sprint | Target |
|--------|--------|
| Sprint 1 | 40% |
| Sprint 2 | 55% |
| Sprint 5 | 80%+ |

## Building

### Gateway Build

```bash
cd apps/gateway
npm run build        # Build TypeScript
npm run lint         # Run ESLint
npm run typecheck    # Type checking only
```

### Agent Build

```bash
cd apps/agent
uv run ruff check .  # Linting
uv run mypy .        # Type checking
```

## Code Quality Standards

### Python (Agent Worker)

- **Style**: Ruff formatter + linter
- **Types**: Full type hints required
- **Docstrings**: Google style for public APIs
- **Naming**: snake_case for functions/variables, PascalCase for classes

### TypeScript (Gateway)

- **Style**: Prettier + ESLint
- **Types**: Strict mode, no `any`
- **Comments**: JSDoc for public APIs
- **Naming**: camelCase for functions/variables, PascalCase for classes

## Git Workflow

### Branch Naming

```
feature/{task-id}-{short-description}
fix/{issue-id}-{short-description}
refactor/{area}-{description}
```

### Commit Messages

```
{type}: {short description}

{optional body with more details}

Types: feat, fix, refactor, test, docs, chore
```

Example:
```
feat: add web search tool with Tavily integration

- Implements WebSearchTool with multi-provider support
- Adds caching with configurable TTL
- Falls back to DuckDuckGo when Tavily unavailable
```

### Before Pushing

1. Run tests: `uv run pytest` and `npm test`
2. Check types: `uv run mypy .` and `npm run typecheck`
3. Format code: `uv run ruff format .`
4. Review changes: `git diff --staged`

## Adding New Features

### Adding a New Tool (Agent)

1. Create tool in `apps/agent/ag3nt_agent/tools/`
2. Register in `deepagents_runtime.py`
3. Add unit tests in `tests/unit/`
4. Update tool list in docs if public

### Adding a New Channel (Gateway)

1. Create adapter in `apps/gateway/src/channels/`
2. Register in channel factory
3. Add configuration schema in `config/`
4. Add integration tests

### Adding a New Skill

1. Create folder in `skills/{skill-name}/`
2. Add `SKILL.md` with YAML frontmatter
3. Add optional `scripts/` and `references/`
4. Test via Control Panel

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Port in use | `.\stop.ps1` to kill processes |
| Tests fail | Check if AG3NT is running (some tests need it) |
| Type errors | Run typecheck command to see all errors |
| Import errors | Check virtual env is activated |

## Further Reading

- Testing guide: `/docs/guides/TESTING.md`
- Skill development: `/docs/guides/SKILL_DEVELOPMENT.md`
- Configuration: `/docs/reference/CONFIGURATION.md`

