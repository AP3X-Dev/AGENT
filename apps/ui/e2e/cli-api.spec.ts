import { test, expect } from '@playwright/test'
import { BASE_URL } from './fixtures'

test.describe('CLI Shell API', () => {
  test('POST /api/cli/shell executes simple command', async ({ request }) => {
    const res = await request.post(`${BASE_URL}/api/cli/shell`, {
      data: { command: 'echo hello' },
    })
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body.output).toContain('hello')
    expect(body.exitCode).toBe(0)
  })

  test('POST /api/cli/shell rejects empty command', async ({ request }) => {
    const res = await request.post(`${BASE_URL}/api/cli/shell`, {
      data: { command: '' },
    })
    expect(res.status()).toBe(400)
    const body = await res.json()
    expect(body.error).toBeDefined()
  })

  test('POST /api/cli/shell blocks dangerous commands', async ({ request }) => {
    const res = await request.post(`${BASE_URL}/api/cli/shell`, {
      data: { command: 'rm -rf /' },
    })
    expect(res.status()).toBe(403)
    const body = await res.json()
    expect(body.error).toContain('security')
  })
})

test.describe('CLI Files API', () => {
  test('GET /api/cli/files reads a known file', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/api/cli/files?path=package.json`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body.success).toBe(true)
    expect(body.content).toBeDefined()
    expect(typeof body.content).toBe('string')
    expect(body.content.length).toBeGreaterThan(0)
  })

  test('GET /api/cli/files lists directory', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/api/cli/files?path=.&action=list`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body.success).toBe(true)
    expect(body).toHaveProperty('items')
    expect(Array.isArray(body.items)).toBe(true)
    expect(body.items.length).toBeGreaterThan(0)
  })

  test('GET /api/cli/files returns 400 without path', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/api/cli/files`)
    expect(res.status()).toBe(400)
    const body = await res.json()
    expect(body.success).toBe(false)
  })
})

test.describe('CLI Autocomplete API', () => {
  test('GET /api/cli/autocomplete returns suggestions', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/api/cli/autocomplete?query=READ`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty('items')
    expect(Array.isArray(body.items)).toBe(true)
  })
})
