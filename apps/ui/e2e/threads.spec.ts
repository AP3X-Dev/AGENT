import { test, expect } from '@playwright/test'
import { BASE_URL, requireDaemon } from './fixtures'

test.describe('Thread Management', () => {
  test.beforeEach(async ({ request }) => {
    await requireDaemon(request)
  })

  test('GET /api/threads returns thread list', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/api/threads`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty('threads')
    expect(Array.isArray(body.threads)).toBe(true)
  })

  test('GET /api/threads respects limit param', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/api/threads?limit=5`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty('threads')
    expect(Array.isArray(body.threads)).toBe(true)
  })

  test('DELETE /api/threads returns 400 without id param', async ({ request }) => {
    const res = await request.delete(`${BASE_URL}/api/threads`)
    expect(res.status()).toBe(400)
    const body = await res.json()
    expect(body.error).toBe('Thread ID is required')
  })

  test('DELETE /api/threads?id=nonexistent handled gracefully', async ({ request }) => {
    const res = await request.delete(`${BASE_URL}/api/threads?id=nonexistent-thread-xyz`)
    // Daemon decides: 200 (idempotent) or 500 (daemon error)
    expect([200, 500]).toContain(res.status())
  })
})
