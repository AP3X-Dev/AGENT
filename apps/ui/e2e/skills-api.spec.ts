import { test, expect } from '@playwright/test'
import { BASE_URL } from './fixtures'

test.describe('Skills List API', () => {
  test('GET /api/skills/list returns skills array', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/api/skills/list`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty('skills')
    expect(Array.isArray(body.skills)).toBe(true)
    expect(body).toHaveProperty('total')
    expect(typeof body.total).toBe('number')
    expect(body).toHaveProperty('limit')
    expect(typeof body.limit).toBe('number')
  })

  test('GET /api/skills/list respects limit and offset', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/api/skills/list?limit=2&offset=0`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body.skills.length).toBeLessThanOrEqual(2)
    expect(body.limit).toBe(2)
    expect(body.offset).toBe(0)
  })

  test('GET /api/skills/list supports search filter', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/api/skills/list?search=nonexistent-skill-xyz`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(Array.isArray(body.skills)).toBe(true)
  })
})

test.describe('Skills CRUD API', () => {
  test('POST /api/skills rejects missing id/name', async ({ request }) => {
    const res = await request.post(`${BASE_URL}/api/skills`, {
      data: { description: 'no id or name' },
    })
    expect(res.status()).toBe(400)
    const body = await res.json()
    expect(body.error).toContain('required')
  })

  test('GET /api/skills returns 400 without path', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/api/skills`)
    expect(res.status()).toBe(400)
    const body = await res.json()
    expect(body.error).toContain('path')
  })

  test('GET /api/skills returns 404 for nonexistent path', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/api/skills?path=C%3A%5Cnonexistent%5CSKILL.md`)
    expect(res.status()).toBe(404)
    const body = await res.json()
    expect(body.error).toContain('not found')
  })
})
