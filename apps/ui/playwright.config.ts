import { defineConfig, devices } from '@playwright/test'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000'
const GATEWAY_URL = process.env.AG3NT_GATEWAY_URL || 'http://localhost:18789'
const AGENT_URL = process.env.AG3NT_AGENT_URL || 'http://localhost:18790'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [
    ['html', { open: 'never' }],
    ['list'],
  ],
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    // UI-only tests — only needs Next.js dev server
    {
      name: 'ui',
      testMatch: ['app.spec.ts', 'navigation.spec.ts'],
      use: { ...devices['Desktop Chrome'] },
    },
    // API tests — needs gateway and/or agent running
    {
      name: 'api',
      testMatch: ['api-health.spec.ts', 'sessions.spec.ts', 'subagents.spec.ts', 'threads.spec.ts'],
      use: { ...devices['Desktop Chrome'] },
    },
    // Integration tests — needs all services
    {
      name: 'integration',
      testMatch: ['chat.spec.ts'],
      use: { ...devices['Desktop Chrome'] },
    },
    // Local API tests — only needs Next.js dev server (no gateway/agent/daemon)
    {
      name: 'local-api',
      testMatch: ['skills-api.spec.ts', 'mcp-api.spec.ts', 'cli-api.spec.ts', 'file-api.spec.ts'],
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    command: 'npm run dev',
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
})

export { GATEWAY_URL, AGENT_URL }
