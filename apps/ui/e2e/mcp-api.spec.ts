import { test, expect } from '@playwright/test'
import { BASE_URL, uniqueMcpServerId } from './fixtures'

test.describe('MCP Catalog API', () => {
  test('GET /api/mcp/catalog returns catalog', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/api/mcp/catalog`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty('catalog')
    expect(Array.isArray(body.catalog)).toBe(true)
    expect(body.catalog.length).toBeGreaterThan(0)
  })

  test('GET /api/mcp/catalog supports search', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/api/mcp/catalog?q=thinking`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(Array.isArray(body.catalog)).toBe(true)
    // "Sequential Thinking" should match
    expect(body.catalog.length).toBeGreaterThan(0)
    expect(body.catalog[0].name.toLowerCase()).toContain('thinking')
  })

  test('POST /api/mcp/catalog rejects missing catalog_id', async ({ request }) => {
    const res = await request.post(`${BASE_URL}/api/mcp/catalog`, {
      data: {},
    })
    expect(res.status()).toBe(400)
    const body = await res.json()
    expect(body.error).toContain('catalog_id')
  })

  test('POST /api/mcp/catalog rejects unknown catalog_id', async ({ request }) => {
    const res = await request.post(`${BASE_URL}/api/mcp/catalog`, {
      data: { catalog_id: 'nonexistent-catalog-xyz' },
    })
    expect(res.status()).toBe(404)
    const body = await res.json()
    expect(body.error).toContain('not found')
  })
})

test.describe('MCP Servers API', () => {
  test('GET /api/mcp/servers returns server list', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/api/mcp/servers`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty('servers')
    expect(Array.isArray(body.servers)).toBe(true)
  })

  test('full lifecycle: add, get, delete MCP server', async ({ request }) => {
    const id = uniqueMcpServerId()

    // Create
    const createRes = await request.post(`${BASE_URL}/api/mcp/servers`, {
      data: {
        id,
        name: `E2E Test Server ${id}`,
        description: 'Created by e2e test',
        command: 'echo',
        args: ['test'],
        enabled: true,
      },
    })
    expect(createRes.status()).toBe(201)
    const createBody = await createRes.json()
    expect(createBody.server).toBeDefined()
    expect(createBody.server.id).toBe(id)

    // Get
    const getRes = await request.get(`${BASE_URL}/api/mcp/servers/${id}`)
    expect(getRes.status()).toBe(200)
    const getBody = await getRes.json()
    expect(getBody.server.id).toBe(id)

    // Delete
    const deleteRes = await request.delete(`${BASE_URL}/api/mcp/servers/${id}`)
    expect(deleteRes.status()).toBe(200)
    const deleteBody = await deleteRes.json()
    expect(deleteBody.ok).toBe(true)

    // Verify gone
    const verifyRes = await request.get(`${BASE_URL}/api/mcp/servers/${id}`)
    expect(verifyRes.status()).toBe(404)
  })

  test('GET /api/mcp/servers/:id returns 404 for nonexistent', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/api/mcp/servers/nonexistent-server-xyz`)
    expect(res.status()).toBe(404)
    const body = await res.json()
    expect(body.error).toContain('not found')
  })
})
