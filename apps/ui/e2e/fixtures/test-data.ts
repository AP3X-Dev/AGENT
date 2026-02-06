/**
 * Generate a unique session ID for test isolation.
 */
export function uniqueSessionId(): string {
  return `test-session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/**
 * Generate a unique thread ID for test isolation.
 */
export function uniqueThreadId(): string {
  return `test-thread-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/**
 * Sample subagent registration payload.
 */
export function sampleSubagentConfig(overrides?: Record<string, unknown>) {
  return {
    name: `test-agent-${Date.now()}`,
    description: 'E2E test subagent',
    url: 'http://localhost:19999',
    capabilities: ['chat'],
    ...overrides,
  }
}

/**
 * Sample chat message payload.
 */
export function sampleChatMessage(text = 'Hello from E2E test') {
  return { text, threadId: uniqueThreadId() }
}

/**
 * Generate a unique skill ID for test isolation.
 */
export function uniqueSkillId(): string {
  return `test-skill-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/**
 * Sample skill creation payload.
 */
export function sampleSkillConfig(overrides?: Record<string, unknown>) {
  const id = uniqueSkillId()
  return {
    id,
    name: `Test Skill ${id}`,
    description: 'E2E test skill',
    mode: 'both',
    tags: ['test'],
    tools: ['*'],
    ...overrides,
  }
}

/**
 * Generate a unique MCP server ID for test isolation.
 */
export function uniqueMcpServerId(): string {
  return `test-mcp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/**
 * Sample MCP server creation payload.
 */
export function sampleMcpServerConfig(overrides?: Record<string, unknown>) {
  const id = uniqueMcpServerId()
  return {
    id,
    name: `Test MCP Server ${id}`,
    description: 'E2E test MCP server',
    command: 'echo',
    args: ['test'],
    enabled: true,
    ...overrides,
  }
}
