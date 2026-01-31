# AG3NT Test Suite

This directory contains tests for the AG3NT platform.

## Test Categories

### Planned Test Coverage

| Category | Status | Description |
|----------|--------|-------------|
| Gateway Unit Tests | 📋 Planned | HTTP routes, session management, scheduler |
| Agent Worker Tests | 📋 Planned | DeepAgents runtime, tool execution |
| Skills Loader Tests | 📋 Planned | SKILL.md parsing, skill discovery |
| E2E Tests | 📋 Planned | Full flow tests with Playwright |
| Integration Tests | 📋 Planned | Gateway-Agent communication |

## Running Tests

### Gateway (TypeScript)
```bash
cd apps/gateway
npm test  # Not yet configured
```

### Agent Worker (Python)
```bash
cd apps/agent
pytest  # Requires test files
```

## Test Requirements

- Gateway: Jest or Vitest for TypeScript
- Agent: pytest for Python
- E2E: Playwright for Control Panel UI

## Contributing Tests

When adding tests:
1. Follow the existing project structure
2. Add unit tests alongside source files when possible
3. Use descriptive test names
4. Mock external dependencies (API calls, file system)

See [ROADMAP.md](../docs/ROADMAP.md) Sprint 5 for testing priorities.
