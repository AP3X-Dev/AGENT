# Integration Tests

This directory contains integration tests that verify the interaction between AG3NT Gateway and other services.

## Prerequisites

### Gateway-Agent Integration Tests

The Gateway-Agent integration tests require the Agent worker to be running:

```bash
# Terminal 1: Start the Agent worker
cd apps/agent
python -m ag3nt_agent.worker
```

The agent should be running on `http://127.0.0.1:18790`.

## Running Integration Tests

```bash
# Run all integration tests
npm run test:integration

# Run all tests (unit + integration)
npm run test:all

# Run specific integration test file
npx vitest run src/integration/gateway-agent.integration.test.ts
```

## Test Structure

### `gateway-agent.integration.test.ts`

Tests the full request/response flow between Gateway and Agent:

- **Health Check**: Verifies agent is running and responding
- **Turn Endpoint**: Tests `/turn` endpoint with various scenarios
  - Simple turn requests
  - Metadata handling
  - Session context persistence across multiple turns
- **Error Handling**: Tests error scenarios
  - Invalid request format
  - Empty text handling
- **Resume Endpoint**: Tests `/resume` endpoint structure
- **Performance**: Verifies response times are reasonable

### Test Behavior

Integration tests are designed to be **gracefully skippable**:

- If the Agent worker is not running, tests will be skipped with a warning
- Tests will not fail if dependencies are unavailable
- This allows unit tests to run independently

## Adding New Integration Tests

When adding new integration tests:

1. Create a new file in `src/integration/` with the pattern `*.integration.test.ts`
2. Add availability checks for external dependencies
3. Use appropriate timeouts (30 seconds for integration tests)
4. Include descriptive test names and comments
5. Test both success and error scenarios

Example:

```typescript
describe('My Integration', () => {
  let serviceAvailable = false;

  beforeAll(async () => {
    try {
      const response = await fetch('http://service-url/health');
      serviceAvailable = response.ok;
    } catch (error) {
      console.warn('⚠️  Service not available. Tests will be skipped.');
      serviceAvailable = false;
    }
  }, 30000);

  it('should test something', async () => {
    if (!serviceAvailable) {
      console.log('⏭️  Skipping test - service not available');
      return;
    }

    // Test implementation
  }, 30000);
});
```

## Coverage

Integration tests are excluded from coverage reports since they test the interaction between services rather than individual code paths.

## CI/CD Considerations

In CI/CD pipelines:

1. Start all required services before running integration tests
2. Use Docker Compose or similar to orchestrate services
3. Wait for health checks to pass before running tests
4. Clean up services after tests complete

Example CI workflow:

```yaml
- name: Start services
  run: docker-compose up -d

- name: Wait for services
  run: ./scripts/wait-for-services.sh

- name: Run integration tests
  run: npm run test:integration

- name: Stop services
  run: docker-compose down
```

