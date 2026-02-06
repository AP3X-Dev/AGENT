import type { Page, Locator } from '@playwright/test'

/**
 * Page Object Model for the main AG3NT layout.
 */
export class MainPage {
  readonly page: Page
  readonly layout: Locator
  readonly iconSidebar: IconSidebarComponent
  readonly chatSidebar: ChatSidebarComponent

  constructor(page: Page) {
    this.page = page
    this.layout = page.getByTestId('main-layout')
    this.iconSidebar = new IconSidebarComponent(page)
    this.chatSidebar = new ChatSidebarComponent(page)
  }

  async goto() {
    await this.page.goto('/')
    await this.layout.waitFor({ state: 'visible', timeout: 15_000 })
    // Wait for React 19 hydration. Next.js 15 streams server-rendered HTML
    // then hydrates client components asynchronously (~3-5s in dev mode).
    // Event handlers are only attached after hydration completes.
    // First ensure all resources are loaded, then allow time for React hydration.
    await this.page.waitForLoadState('load')
    await this.page.waitForTimeout(2_000)
  }
}

/**
 * Page Object for the left icon sidebar.
 */
export class IconSidebarComponent {
  readonly root: Locator
  readonly newChatButton: Locator
  readonly expandCollapseButton: Locator
  readonly filesButton: Locator
  readonly searchButton: Locator
  readonly mapsButton: Locator
  readonly codeButton: Locator
  readonly browserButton: Locator
  readonly agentsLibraryButton: Locator
  readonly skillsLibraryButton: Locator
  readonly toolsLibraryButton: Locator
  readonly mcpManagerButton: Locator
  readonly schedulerButton: Locator
  readonly controlPanelButton: Locator
  readonly settingsButton: Locator

  constructor(page: Page) {
    this.root = page.getByTestId('icon-sidebar')
    this.newChatButton = this.root.getByTitle('New Chat')
    this.expandCollapseButton = this.root.locator('button[title="Collapse Chat"], button[title="Expand Chat"]')
    this.filesButton = this.root.getByTitle('Files')
    this.searchButton = this.root.getByTitle('Search')
    this.mapsButton = this.root.getByTitle('Maps')
    this.codeButton = this.root.getByTitle('Code')
    this.browserButton = this.root.getByTitle('Browser')
    this.agentsLibraryButton = this.root.getByTitle('Agents Library')
    this.skillsLibraryButton = this.root.getByTitle('Skills Library')
    this.toolsLibraryButton = this.root.getByTitle('Tools Library')
    this.mcpManagerButton = this.root.getByTitle('MCP Manager')
    this.schedulerButton = this.root.getByTitle('Scheduler')
    this.controlPanelButton = this.root.getByTitle('AG3NT Control Panel')
    this.settingsButton = this.root.getByTitle('Settings')
  }

  /** Returns all sidebar buttons as an array of locators */
  allButtons(): Locator[] {
    return [
      this.newChatButton,
      this.expandCollapseButton,
      this.filesButton,
      this.searchButton,
      this.mapsButton,
      this.codeButton,
      this.browserButton,
      this.agentsLibraryButton,
      this.skillsLibraryButton,
      this.toolsLibraryButton,
      this.mcpManagerButton,
      this.schedulerButton,
      this.controlPanelButton,
      this.settingsButton,
    ]
  }
}

/**
 * Page Object for the chat sidebar.
 */
export class ChatSidebarComponent {
  readonly root: Locator
  readonly emptyState: Locator
  readonly inputForm: Locator
  readonly textarea: Locator
  readonly sendButton: Locator
  readonly stopButton: Locator
  readonly attachButton: Locator
  readonly autoApproveToggle: Locator
  readonly threadHeader: Locator
  readonly threadHistoryButton: Locator
  readonly newThreadButton: Locator
  readonly tasksToggleButton: Locator

  constructor(page: Page) {
    this.root = page.getByTestId('chat-sidebar')
    this.emptyState = page.getByTestId('chat-empty-state')
    this.inputForm = page.getByTestId('chat-input-form')
    this.textarea = this.inputForm.locator('textarea')
    this.sendButton = this.inputForm.getByLabel('Send message')
    this.stopButton = this.inputForm.getByLabel('Stop generation')
    this.attachButton = this.inputForm.getByLabel('Attach files')
    this.autoApproveToggle = page.getByTestId('auto-approve-toggle')
    this.threadHeader = this.root.locator('.bg-surface-header').first()
    this.threadHistoryButton = this.root.getByLabel('Toggle thread history')
    this.newThreadButton = this.root.getByLabel('Start a new thread')
    this.tasksToggleButton = this.root.getByLabel('Show Tasks').or(this.root.getByLabel('Show Chat'))
  }

  async typeMessage(text: string) {
    await this.textarea.fill(text)
  }

  async sendMessage(text: string) {
    await this.typeMessage(text)
    await this.sendButton.click()
  }
}
