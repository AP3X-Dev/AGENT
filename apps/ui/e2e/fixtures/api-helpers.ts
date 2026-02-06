import { test, type APIRequestContext } from '@playwright/test'

export const GATEWAY_URL = process.env.AG3NT_GATEWAY_URL || 'http://localhost:18789'
export const AGENT_URL = process.env.AG3NT_AGENT_URL || 'http://localhost:18790'
export const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000'

/**
 * Check if the gateway is reachable. Skips the calling test if not.
 */
export async function requireGateway(request: APIRequestContext) {
  try {
    const res = await request.get(`${GATEWAY_URL}/api/health`, { timeout: 3000 })
    if (!res.ok()) {
      test.skip(true, `Gateway not available (status ${res.status()})`)
    }
  } catch {
    test.skip(true, 'Gateway not reachable')
  }
}

/**
 * Check if the agent worker is reachable. Skips the calling test if not.
 */
export async function requireAgent(request: APIRequestContext) {
  try {
    const res = await request.get(`${AGENT_URL}/health`, { timeout: 3000 })
    if (!res.ok()) {
      test.skip(true, `Agent not available (status ${res.status()})`)
    }
  } catch {
    test.skip(true, 'Agent not reachable')
  }
}

/**
 * Check if both gateway and agent are reachable. Skips if either is down.
 */
export async function requireAllServices(request: APIRequestContext) {
  await requireGateway(request)
  await requireAgent(request)
}

/**
 * Check if the DeepAgents daemon is reachable via the Next.js API.
 * Skips the calling test if not.
 */
export async function requireDaemon(request: APIRequestContext) {
  try {
    const res = await request.get(`${BASE_URL}/api/threads`, { timeout: 5000 })
    if (res.status() === 500) {
      test.skip(true, 'Daemon not available')
    }
  } catch {
    test.skip(true, 'Daemon not reachable')
  }
}
