import { test, expect } from '@playwright/test'
import { MainPage } from './fixtures'

test.describe('UI Rendering', () => {
  let mainPage: MainPage

  test.beforeEach(async ({ page }) => {
    mainPage = new MainPage(page)
    await mainPage.goto()
  })

  test('page loads with core layout (sidebar, chat, preview)', async () => {
    await expect(mainPage.layout).toBeVisible()
    await expect(mainPage.iconSidebar.root).toBeVisible()
    await expect(mainPage.chatSidebar.root).toBeVisible()
  })

  test('"Welcome to AG3NT" empty state displays', async () => {
    await expect(mainPage.chatSidebar.emptyState).toBeVisible()
    await expect(mainPage.chatSidebar.emptyState).toContainText('Welcome to AG3NT')
  })

  test('all 14 sidebar buttons render', async ({ page }) => {
    const buttons = mainPage.iconSidebar.allButtons()
    for (const button of buttons) {
      await expect(button).toBeVisible()
    }
  })

  test('chat input form renders with textarea and buttons', async () => {
    await expect(mainPage.chatSidebar.inputForm).toBeVisible()
    await expect(mainPage.chatSidebar.textarea).toBeVisible()
    await expect(mainPage.chatSidebar.sendButton).toBeVisible()
    await expect(mainPage.chatSidebar.attachButton).toBeVisible()
  })

  test('preview panel renders with default content', async ({ page }) => {
    // The preview panel shows "Preview" heading and description in default state
    const previewHeading = page.getByText('Preview', { exact: true })
    await expect(previewHeading).toBeVisible()
    await expect(page.getByText('Generated content and web pages will appear here')).toBeVisible()
  })

  test('thread header renders with "New Session" title', async ({ page }) => {
    const sessionTitle = page.getByText('New Session')
    await expect(sessionTitle).toBeVisible()
  })

  test('send button disabled with empty input', async () => {
    await expect(mainPage.chatSidebar.textarea).toHaveValue('')
    await expect(mainPage.chatSidebar.sendButton).toBeDisabled()
  })

  test('send button enabled with text input', async ({ page }) => {
    const textarea = mainPage.chatSidebar.textarea
    // React 19 controlled inputs need the native value setter + input event
    // to trigger React's synthetic onChange through its event delegation.
    await expect(async () => {
      await textarea.click()
      // Use native setter to bypass React's controlled value and dispatch
      // an input event that React's event delegation will capture.
      await page.evaluate(() => {
        const el = document.querySelector('[data-testid="chat-input-form"] textarea') as HTMLTextAreaElement
        if (!el) return
        const nativeSetter = Object.getOwnPropertyDescriptor(
          HTMLTextAreaElement.prototype, 'value'
        )?.set
        if (nativeSetter) {
          nativeSetter.call(el, 'Hello')
          el.dispatchEvent(new Event('input', { bubbles: true }))
        }
      })
      await expect(mainPage.chatSidebar.sendButton).toBeEnabled({ timeout: 2_000 })
    }).toPass({ timeout: 15_000 })
  })

  test('correct page title', async ({ page }) => {
    await expect(page).toHaveTitle(/AG3NT/)
  })
})
