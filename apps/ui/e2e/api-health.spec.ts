import { test, expect } from '@playwright/test'
import { GATEWAY_URL, AGENT_URL, requireGateway, requireAgent } from './fixtures'

test.describe('Gateway Health Checks', () => {
  test('GET /api/health returns 200', async ({ request }) => {
    await requireGateway(request)
    const res = await request.get(`${GATEWAY_URL}/api/health`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty('status')
  })

  test('GET /api/health/live returns 200', async ({ request }) => {
    await requireGateway(request)
    const res = await request.get(`${GATEWAY_URL}/api/health/live`)
    expect(res.status()).toBe(200)
  })

  test('GET /api/health/ready returns 200', async ({ request }) => {
    await requireGateway(request)
    const res = await request.get(`${GATEWAY_URL}/api/health/ready`)
    expect(res.status()).toBe(200)
  })

  test('GET /api/health/metrics returns metrics data', async ({ request }) => {
    await requireGateway(request)
    const res = await request.get(`${GATEWAY_URL}/api/health/metrics`)
    expect(res.status()).toBe(200)
  })
})

test.describe('Agent Health Checks', () => {
  test('GET /health returns 200', async ({ request }) => {
    await requireAgent(request)
    const res = await request.get(`${AGENT_URL}/health`)
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty('status')
  })
})
