import { test, expect } from '@playwright/test'
import { GATEWAY_URL, AGENT_URL, requireGateway, requireAgent, sampleSubagentConfig } from './fixtures'

test.describe('Subagent Management', () => {
  test.beforeEach(async ({ request }) => {
    await requireGateway(request)
  })

  test('list subagents from gateway', async ({ request }) => {
    const res = await request.get(`${GATEWAY_URL}/api/subagents`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(Array.isArray(body.subagents ?? body)).toBe(true)
  })

  test('list subagents from agent directly', async ({ request }) => {
    await requireAgent(request)
    const res = await request.get(`${AGENT_URL}/subagents`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(Array.isArray(body.subagents ?? body)).toBe(true)
  })

  test('reject registration with missing required fields', async ({ request }) => {
    const res = await request.post(`${GATEWAY_URL}/api/subagents`, {
      data: { description: 'missing name and url' },
    })
    // Should reject with 400 or 422
    expect([400, 422]).toContain(res.status())
  })

  test('full lifecycle: register, get, delete', async ({ request }) => {
    const config = sampleSubagentConfig()

    // Register
    const createRes = await request.post(`${GATEWAY_URL}/api/subagents`, {
      data: config,
    })
    // Accept 200, 201, or 409 (already exists)
    expect([200, 201, 409]).toContain(createRes.status())

    if (createRes.status() === 200 || createRes.status() === 201) {
      const created = await createRes.json()
      const agentId = created.id ?? created.name ?? config.name

      // Get
      const getRes = await request.get(`${GATEWAY_URL}/api/subagents/${agentId}`)
      expect([200, 404]).toContain(getRes.status())

      // Delete
      const deleteRes = await request.delete(`${GATEWAY_URL}/api/subagents/${agentId}`)
      expect([200, 204, 404]).toContain(deleteRes.status())

      // Verify deletion
      const verifyRes = await request.get(`${GATEWAY_URL}/api/subagents/${agentId}`)
      expect(verifyRes.status()).toBe(404)
    }
  })

  test('delete nonexistent subagent returns 404', async ({ request }) => {
    const res = await request.delete(`${GATEWAY_URL}/api/subagents/nonexistent-agent-xyz`)
    expect(res.status()).toBe(404)
  })
})
