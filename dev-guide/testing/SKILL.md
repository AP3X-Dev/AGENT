---
name: testing
description: Comprehensive guide to testing AG3NT including test strategies, patterns, commands, and best practices for both Python and TypeScript.
version: "1.0.0"
tags:
  - testing
  - quality
  - pytest
  - vitest
triggers:
  - "how to test"
  - "run tests"
  - "write tests"
  - "test coverage"
  - "testing guide"
required_permissions: []
license: MIT
compatibility: AG3NT 1.x
metadata:
  author: ag3nt-team
  category: development
---

# Testing Guide

Use this skill when writing tests, running test suites, or understanding AG3NT's testing strategy.

## Test Architecture

AG3NT uses a two-language test strategy:

| Component | Framework | Location | Config |
|-----------|-----------|----------|--------|
| Agent Worker | pytest | `apps/agent/tests/` | `pyproject.toml` |
| Gateway | Vitest | `apps/gateway/test/` | `vitest.config.ts` |

## Running Tests

### Python (Agent Worker)

```bash
cd apps/agent

# Run all tests with coverage
uv run pytest

# Run only unit tests
uv run pytest tests/unit/

# Run specific test file
uv run pytest tests/unit/test_shell_security.py -v

# Run tests matching pattern
uv run pytest -k "test_blocks"

# Run with verbose output
uv run pytest -v --tb=long

# Generate HTML coverage report
uv run pytest --cov-report=html
# Open htmlcov/index.html in browser
```

### TypeScript (Gateway)

```bash
cd apps/gateway

# Run all tests
npm test

# Run with coverage
npm run test:coverage

# Run in watch mode
npm run test:watch

# Run specific test file
npx vitest run src/skills/SkillManager.test.ts
```

## Test Categories

### Unit Tests
- **Purpose**: Test individual functions/classes in isolation
- **Speed**: Fast (< 100ms each)
- **I/O**: None (mock all external dependencies)
- **Location**: `tests/unit/` or `*.test.ts`

### Integration Tests
- **Purpose**: Test component interactions
- **Speed**: Medium (< 5s each)
- **I/O**: May use real files, databases
- **Location**: `tests/integration/`

### E2E Tests
- **Purpose**: Test full system flows
- **Speed**: Slow (< 30s each)
- **I/O**: Full system running
- **Location**: `tests/e2e/`

## Coverage Targets

| Sprint | Target | Current |
|--------|--------|---------|
| Sprint 1 | 40% | ~40% |
| Sprint 2 | 55% | - |
| Sprint 3 | 65% | - |
| Sprint 4 | 75% | - |
| Sprint 5 | 80%+ | - |

## Writing Tests

### Python Test Pattern

```python
import pytest
from ag3nt_agent.shell_security import ShellSecurityValidator, SecurityLevel

class TestShellSecurityValidator:
    """Tests for ShellSecurityValidator."""

    @pytest.fixture
    def validator(self):
        """Create a validator instance for testing."""
        return ShellSecurityValidator()

    def test_blocks_rm_rf_root(self, validator):
        """Should block recursive deletion of root."""
        level, reason = validator.validate("rm -rf /")
        assert level == SecurityLevel.BLOCK
        assert "root" in reason.lower()

    def test_allows_safe_commands(self, validator):
        """Should allow common safe commands."""
        safe_commands = ["ls -la", "cat file.txt", "echo hello"]
        for cmd in safe_commands:
            level, _ = validator.validate(cmd)
            assert level == SecurityLevel.ALLOW
```

### TypeScript Test Pattern

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SessionManager } from '@/session/SessionManager';

describe('SessionManager', () => {
  let manager: SessionManager;

  beforeEach(() => {
    manager = new SessionManager();
  });

  it('creates new session for unknown user', async () => {
    const session = await manager.getOrCreate({
      channelType: 'cli',
      channelId: 'test',
      userId: 'user1',
    });
    expect(session.id).toBeDefined();
    expect(session.userId).toBe('user1');
  });

  it('returns existing session for known user', async () => {
    const first = await manager.getOrCreate({ ... });
    const second = await manager.getOrCreate({ ... });
    expect(first.id).toBe(second.id);
  });
});
```

## Mocking Patterns

### Python Mocking

```python
from unittest.mock import AsyncMock, patch, MagicMock

# Mock a function
with patch('ag3nt_agent.tools.web_search.TavilyClient') as mock:
    mock.return_value.search.return_value = {'results': []}
    # test code

# Mock async function
mock_client = AsyncMock()
mock_client.generate.return_value = "response"

# Use pytest-mock fixture
def test_something(mocker):
    mocker.patch('module.function', return_value='mocked')
```

### TypeScript Mocking

```typescript
import { vi } from 'vitest';

// Mock a module
vi.mock('@/services/llm', () => ({
  LLMService: vi.fn().mockImplementation(() => ({
    generate: vi.fn().mockResolvedValue('response'),
  })),
}));

// Spy on a method
const spy = vi.spyOn(service, 'method');
expect(spy).toHaveBeenCalledWith('arg');
```

## Test File Naming

| Language | Pattern | Example |
|----------|---------|---------|
| Python | `test_{module}.py` | `test_shell_security.py` |
| TypeScript | `{module}.test.ts` | `SessionManager.test.ts` |

## Existing Test Files

### Agent Worker Tests
- `test_shell_security.py` - Shell command validation
- `test_shell_middleware.py` - Shell execution
- `test_file_security.py` - File operation validation
- `test_web_search.py` - Web search tool
- `test_audit_logger.py` - Audit logging
- `test_skill_executor.py` - Skill execution
- `test_browser_tool.py` - Browser automation

## Best Practices

1. **Test behavior, not implementation**
2. **One assertion per test** (when practical)
3. **Use descriptive test names**: `test_blocks_rm_rf_when_targeting_root`
4. **Arrange-Act-Assert** pattern
5. **Mock external dependencies** (APIs, databases, file system)
6. **Clean up after tests** (use fixtures/teardown)
7. **Test edge cases** (empty input, null, boundaries)

## Further Reading

- pytest docs: https://docs.pytest.org/
- Vitest docs: https://vitest.dev/
- Sprint breakdown: `/docs/SPRINT_1_2_TASK_BREAKDOWN.md`

