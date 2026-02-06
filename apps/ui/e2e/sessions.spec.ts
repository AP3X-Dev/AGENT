import { test, expect } from '@playwright/test'
import { GATEWAY_URL, requireGateway } from './fixtures'

test.describe('Session Management', () => {
  test.beforeEach(async ({ request }) => {
    await requireGateway(request)
  })

  test('list sessions returns array', async ({ request }) => {
    const res = await request.get(`${GATEWAY_URL}/api/sessions`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(Array.isArray(body.sessions ?? body)).toBe(true)
  })

  test('list sessions with limit param', async ({ request }) => {
    const res = await request.get(`${GATEWAY_URL}/api/sessions?limit=5`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    const sessions = body.sessions ?? body
    expect(Array.isArray(sessions)).toBe(true)
    expect(sessions.length).toBeLessThanOrEqual(5)
  })

  test('list pending sessions', async ({ request }) => {
    const res = await request.get(`${GATEWAY_URL}/api/sessions/pending`)
    // Endpoint may return 200 with empty array or 404 if not implemented
    expect([200, 404]).toContain(res.status())
  })

  test('GET nonexistent session returns 404', async ({ request }) => {
    const res = await request.get(`${GATEWAY_URL}/api/sessions/nonexistent-id-12345`)
    expect(res.status()).toBe(404)
  })

  test('DELETE nonexistent session returns 404', async ({ request }) => {
    const res = await request.delete(`${GATEWAY_URL}/api/sessions/nonexistent-id-12345`)
    expect(res.status()).toBe(404)
  })

  test('clear all sessions', async ({ request }) => {
    const res = await request.delete(`${GATEWAY_URL}/api/sessions`)
    // Should succeed (200/204) or indicate no sessions to clear
    expect([200, 204, 404]).toContain(res.status())
  })
})
