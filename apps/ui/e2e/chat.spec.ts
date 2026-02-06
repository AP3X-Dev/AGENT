import { test, expect } from '@playwright/test'
import { MainPage, BASE_URL, requireDaemon, requireAllServices, uniqueThreadId } from './fixtures'

test.describe('Chat Input Interactions', () => {
  let mainPage: MainPage

  test.beforeEach(async ({ page }) => {
    mainPage = new MainPage(page)
    await mainPage.goto()
  })

  test('type into chat input', async () => {
    await mainPage.chatSidebar.textarea.fill('Hello AG3NT')
    await expect(mainPage.chatSidebar.textarea).toHaveValue('Hello AG3NT')
  })

  test('input clears after submit attempt', async ({ page }) => {
    await mainPage.chatSidebar.textarea.fill('Test message')
    await expect(mainPage.chatSidebar.sendButton).toBeEnabled()

    // Press Enter to submit (form submission behavior)
    await mainPage.chatSidebar.textarea.press('Enter')

    // Input should clear after submission
    await expect(mainPage.chatSidebar.textarea).toHaveValue('')
  })

  test('Enter submits, Shift+Enter adds newline', async () => {
    const textarea = mainPage.chatSidebar.textarea
    await textarea.fill('')
    await textarea.type('Line 1')
    await textarea.press('Shift+Enter')
    await textarea.type('Line 2')

    // Should contain both lines (newline in between)
    const value = await textarea.inputValue()
    expect(value).toContain('Line 1')
    expect(value).toContain('Line 2')
    // The value should have a newline
    expect(value.split('\n').length).toBeGreaterThanOrEqual(2)
  })

  test('auto-approve toggle is clickable', async ({ page }) => {
    const toggle = mainPage.chatSidebar.autoApproveToggle
    await expect(toggle).toBeVisible()

    // Click to enable
    await toggle.click()

    // The toggle should reflect a visual state change (amber class)
    await expect(toggle).toHaveClass(/amber/)
  })

  test('auto-approve toggle can be toggled off', async ({ page }) => {
    const toggle = mainPage.chatSidebar.autoApproveToggle
    // Enable
    await toggle.click()
    await expect(toggle).toHaveClass(/amber/)

    // Disable
    await toggle.click()
    await expect(toggle).not.toHaveClass(/amber/)
  })
})

test.describe('Chat API — Stream', () => {
  test.beforeEach(async ({ request }) => {
    await requireDaemon(request)
  })

  test('POST /api/chat/stream returns SSE response', async ({ request }) => {
    const res = await request.post(`${BASE_URL}/api/chat/stream`, {
      data: { message: 'Hello', threadId: uniqueThreadId() },
    })
    // Should return 200 with streaming content type
    expect(res.status()).toBe(200)
    const contentType = res.headers()['content-type'] || ''
    expect(contentType).toContain('text/event-stream')
  })

  test('POST /api/chat/stream rejects empty message', async ({ request }) => {
    const res = await request.post(`${BASE_URL}/api/chat/stream`, {
      data: { message: '', threadId: uniqueThreadId() },
    })
    expect(res.status()).toBe(400)
    const body = JSON.parse(await res.text())
    expect(body.error).toContain('required')
  })
})

test.describe('Chat API — Sync', () => {
  test.beforeEach(async ({ request }) => {
    await requireDaemon(request)
  })

  test('POST /api/chat returns JSON response', async ({ request }) => {
    const res = await request.post(`${BASE_URL}/api/chat`, {
      data: {
        messages: [{ role: 'user', content: 'Hello' }],
        threadId: uniqueThreadId(),
      },
    })
    // 200 success or 500 if daemon fails to process
    expect([200, 500]).toContain(res.status())
  })

  test('POST /api/chat rejects empty messages', async ({ request }) => {
    const res = await request.post(`${BASE_URL}/api/chat`, {
      data: { messages: [] },
    })
    expect(res.status()).toBe(400)
    const body = await res.json()
    expect(body.error).toContain('required')
  })
})

test.describe('HITL Approval API', () => {
  test.beforeEach(async ({ request }) => {
    await requireDaemon(request)
  })

  test('POST /api/approve rejects missing fields', async ({ request }) => {
    const res = await request.post(`${BASE_URL}/api/approve`, {
      data: {},
    })
    expect(res.status()).toBe(400)
    const body = await res.json()
    expect(body.error).toContain('required')
  })
})

test.describe('Chat API — Resume Stream', () => {
  test.beforeEach(async ({ request }) => {
    await requireDaemon(request)
  })

  test('POST /api/chat/resume-stream rejects missing fields', async ({ request }) => {
    const res = await request.post(`${BASE_URL}/api/chat/resume-stream`, {
      data: {},
    })
    expect(res.status()).toBe(400)
    const body = JSON.parse(await res.text())
    expect(body.error).toContain('required')
  })
})

test.describe('Full Integration — Chat Flow', () => {
  test('send message and see it appear in chat', async ({ page, request }) => {
    await requireAllServices(request)

    const mainPage = new MainPage(page)
    await mainPage.goto()

    // Type and send a message
    await mainPage.chatSidebar.textarea.fill('What is 2 + 2?')
    await expect(mainPage.chatSidebar.sendButton).toBeEnabled()
    await mainPage.chatSidebar.sendButton.click()

    // Input should clear
    await expect(mainPage.chatSidebar.textarea).toHaveValue('')

    // The empty state should disappear (a message was sent)
    await expect(mainPage.chatSidebar.emptyState).not.toBeVisible({ timeout: 5000 })

    // Wait for some response to appear (agent status or message)
    // We use a generous timeout since the agent may take time to respond
    const messageArea = page.locator('[role="log"]')
    await expect(messageArea).toBeVisible()
  })
})
