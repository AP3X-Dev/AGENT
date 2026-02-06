import { test, expect } from '@playwright/test'
import { BASE_URL } from './fixtures'

test.describe('File Serving API', () => {
  test('GET /api/file returns 400 without path', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/api/file`)
    expect(res.status()).toBe(400)
    const body = await res.json()
    expect(body.error).toContain('path')
  })

  test('GET /api/file rejects non-image extensions', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/api/file?path=README.md`)
    expect(res.status()).toBe(403)
    const body = await res.json()
    expect(body.error).toContain('image')
  })

  test('GET /api/file returns 404 for nonexistent image', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/api/file?path=nonexistent.png`)
    expect(res.status()).toBe(404)
    const body = await res.json()
    expect(body.error).toContain('not found')
  })

  test('GET /api/file serves existing image', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/api/file?path=public/apple-icon.png`)
    expect(res.status()).toBe(200)
    const contentType = res.headers()['content-type'] || ''
    expect(contentType).toContain('image/png')
  })
})
