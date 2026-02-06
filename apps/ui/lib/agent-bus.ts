/**
 * AgentBus - Central Communication Hub
 * 
 * Event-driven message bus for bidirectional communication between
 * AI agents and UI modules. Implements the A2UI protocol foundation.
 */

import type {
  AgentMessage,
  AgentMessageType,
  MessageSource,
  MessageTarget,
  MessageFilter,
  MessageId,
  CorrelationId,
  ModuleInstanceId,
  ModuleContext,
  AgentCommand,
  CommandResponse,
  CommandHandler,
  CommandContext,
  AgentMessageHandler,
  AgentBusSubscription,
  AgentBusConfig,
  IAgentBus,
  SpawnModuleRequest,
  SpawnModuleResponse,
  ModuleEvent,
} from '@/types/agent-communication'
import type { ModuleTypeId } from '@/types/modules'
import type {
  TabContext,
  TabSearchCriteria,
  TabSearchResult,
  TabContextSummary,
  ContextAssemblyOptions,
  AssembledContext,
  TabPriority,
  TabQueryCommands,
  TabQueryResponses,
} from '@/types/tab-context'

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Generate a unique ID
 */
function generateUniqueId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).substring(2, 9)}`
}

/**
 * Check if a message matches a filter
 */
function matchesFilter(message: AgentMessage, filter: MessageFilter): boolean {
  // Type filter
  if (filter.type) {
    const types = Array.isArray(filter.type) ? filter.type : [filter.type]
    if (!types.includes(message.type)) return false
  }
  
  // Source filter
  if (filter.source) {
    if (filter.source.type && message.source.type !== filter.source.type) return false
    if (filter.source.id && message.source.id !== filter.source.id) return false
    if (filter.source.moduleType && message.source.moduleType !== filter.source.moduleType) return false
  }
  
  // Target filter
  if (filter.target) {
    if (filter.target.type && message.target.type !== filter.target.type) return false
    if (filter.target.id && message.target.id !== filter.target.id) return false
    if (filter.target.moduleType && message.target.moduleType !== filter.target.moduleType) return false
  }
  
  // Custom filter
  if (filter.custom && !filter.custom(message)) return false
  
  return true
}

// ============================================================================
// AgentBus Implementation
// ============================================================================

interface Subscription {
  id: string
  filter: MessageFilter
  handler: AgentMessageHandler
}

interface CommandSubscription {
  id: string
  instanceId: ModuleInstanceId
  commandName: string
  handler: CommandHandler
}

interface PendingCommand {
  resolve: (response: CommandResponse) => void
  reject: (error: Error) => void
  timeout: ReturnType<typeof setTimeout>
}

/**
 * AgentBus class implementing IAgentBus interface
 */
class AgentBus implements IAgentBus {
  private config: AgentBusConfig
  private subscriptions: Map<string, Subscription> = new Map()
  private commandSubscriptions: Map<string, CommandSubscription> = new Map()
  private contexts: Map<ModuleInstanceId, ModuleContext> = new Map()
  private pendingCommands: Map<CorrelationId, PendingCommand> = new Map()
  private messageQueue: AgentMessage[] = []
  private spawnHandler?: (request: SpawnModuleRequest) => Promise<SpawnModuleResponse>
  private destroyHandler?: (instanceId: ModuleInstanceId) => Promise<boolean>

  constructor(config: AgentBusConfig = {}) {
    this.config = {
      debug: false,
      defaultTimeout: 30000,
      maxQueueSize: 1000,
      persistMessages: false,
      ...config,
    }
  }

  // --------------------------------------------------------------------------
  // Configuration
  // --------------------------------------------------------------------------

  getConfig(): AgentBusConfig {
    return { ...this.config }
  }

  generateId(): string {
    return generateUniqueId()
  }

  // --------------------------------------------------------------------------
  // Message Sending
  // --------------------------------------------------------------------------

  send<T>(messageData: Omit<AgentMessage<T>, 'id' | 'timestamp'>): MessageId {
    const message: AgentMessage<T> = {
      ...messageData,
      id: generateUniqueId(),
      timestamp: Date.now(),
    }

    if (this.config.debug) {
      console.log('[AgentBus] Sending message:', message)
    }

    // Queue message if persistence is enabled
    if (this.config.persistMessages) {
      this.messageQueue.push(message as AgentMessage)
      if (this.messageQueue.length > (this.config.maxQueueSize || 1000)) {
        this.messageQueue.shift()
      }
    }

    // Dispatch to matching subscriptions
    this.dispatch(message as AgentMessage)

    return message.id
  }

  async sendCommand<TParams, TResult>(
    target: MessageTarget,
    command: AgentCommand<TParams>
  ): Promise<CommandResponse<TResult>> {
    const correlationId = generateUniqueId()
    const timeout = command.timeout || this.config.defaultTimeout || 30000

    return new Promise((resolve, reject) => {
      // Set up timeout
      const timeoutHandle = setTimeout(() => {
        this.pendingCommands.delete(correlationId)
        resolve({
          success: false,
          error: `Command '${command.action}' timed out after ${timeout}ms`,
        })
      }, timeout)

      // Store pending command
      this.pendingCommands.set(correlationId, {
        resolve: resolve as (response: CommandResponse) => void,
        reject,
        timeout: timeoutHandle,
      })

      // Send command message
      this.send({
        type: 'command',
        source: { type: 'agent', id: 'primary-agent' },
        target,
        payload: command,
        correlationId,
        priority: 'normal',
      })
    })
  }

  // --------------------------------------------------------------------------
  // Message Dispatching
  // --------------------------------------------------------------------------

  private dispatch(message: AgentMessage): void {
    // Handle response messages
    if (message.type === 'response' && message.correlationId) {
      const pending = this.pendingCommands.get(message.correlationId)
      if (pending) {
        clearTimeout(pending.timeout)
        this.pendingCommands.delete(message.correlationId)
        pending.resolve(message.payload as CommandResponse)
        return
      }
    }

    // Dispatch to subscriptions
    for (const subscription of this.subscriptions.values()) {
      if (matchesFilter(message, subscription.filter)) {
        try {
          subscription.handler(message)
        } catch (error) {
          console.error('[AgentBus] Subscription handler error:', error)
        }
      }
    }

    // Handle commands to modules
    if (message.type === 'command' && message.target.type === 'module') {
      this.handleModuleCommand(message)
    }
  }

  private async handleModuleCommand(message: AgentMessage): Promise<void> {
    const command = message.payload as AgentCommand
    const targetId = message.target.id

    // Find matching command subscription
    for (const sub of this.commandSubscriptions.values()) {
      if (sub.instanceId === targetId && sub.commandName === command.action) {
        const context: CommandContext = {
          instanceId: sub.instanceId,
          moduleType: this.contexts.get(sub.instanceId)?.moduleType || 'unknown',
          correlationId: message.correlationId,
        }

        try {
          const startTime = Date.now()
          const result = await sub.handler(command.params, context)
          const duration = Date.now() - startTime

          // Send response
          if (message.correlationId) {
            this.send({
              type: 'response',
              source: { type: 'module', id: sub.instanceId },
              target: message.source,
              payload: { success: true, data: result, duration },
              correlationId: message.correlationId,
            })
          }
        } catch (error) {
          if (message.correlationId) {
            this.send({
              type: 'response',
              source: { type: 'module', id: sub.instanceId },
              target: message.source,
              payload: {
                success: false,
                error: error instanceof Error ? error.message : 'Unknown error',
              },
              correlationId: message.correlationId,
            })
          }
        }
        return
      }
    }

    // No handler found
    if (message.correlationId) {
      this.send({
        type: 'response',
        source: { type: 'system', id: 'agent-bus' },
        target: message.source,
        payload: {
          success: false,
          error: `No handler for command '${command.action}' on module '${targetId}'`,
        },
        correlationId: message.correlationId,
      })
    }
  }

  // --------------------------------------------------------------------------
  // Subscriptions
  // --------------------------------------------------------------------------

  subscribe<T>(
    filter: MessageFilter,
    handler: AgentMessageHandler<T>
  ): AgentBusSubscription {
    const id = generateUniqueId()
    this.subscriptions.set(id, {
      id,
      filter,
      handler: handler as AgentMessageHandler,
    })

    return {
      unsubscribe: () => {
        this.subscriptions.delete(id)
      },
    }
  }

  subscribeToCommands<TParams, TResult>(
    moduleInstanceId: ModuleInstanceId,
    commandName: string,
    handler: CommandHandler<TParams, TResult>
  ): AgentBusSubscription {
    const id = generateUniqueId()
    this.commandSubscriptions.set(id, {
      id,
      instanceId: moduleInstanceId,
      commandName,
      handler: handler as CommandHandler,
    })

    if (this.config.debug) {
      console.log(`[AgentBus] Command handler registered: ${commandName} on ${moduleInstanceId}`)
    }

    return {
      unsubscribe: () => {
        this.commandSubscriptions.delete(id)
      },
    }
  }

  // --------------------------------------------------------------------------
  // Context Management
  // --------------------------------------------------------------------------

  registerContext(instanceId: ModuleInstanceId, context: ModuleContext): void {
    this.contexts.set(instanceId, context)

    if (this.config.debug) {
      console.log(`[AgentBus] Context registered: ${instanceId}`, context)
    }

    // Notify subscribers
    this.send({
      type: 'ready',
      source: { type: 'module', id: instanceId, moduleType: context.moduleType },
      target: { type: 'agent' },
      payload: context,
    })
  }

  updateContext(instanceId: ModuleInstanceId, updates: Partial<ModuleContext>): void {
    const existing = this.contexts.get(instanceId)
    if (!existing) {
      console.warn(`[AgentBus] Cannot update context: ${instanceId} not registered`)
      return
    }

    const updated = {
      ...existing,
      ...updates,
      lastUpdated: Date.now(),
    } as ModuleContext

    this.contexts.set(instanceId, updated)

    // Notify subscribers
    this.send({
      type: 'context-update',
      source: { type: 'module', id: instanceId, moduleType: updated.moduleType },
      target: { type: 'agent' },
      payload: updated,
    })
  }

  unregisterContext(instanceId: ModuleInstanceId): void {
    const context = this.contexts.get(instanceId)
    if (context) {
      this.contexts.delete(instanceId)

      // Clean up command subscriptions for this instance
      for (const [id, sub] of this.commandSubscriptions) {
        if (sub.instanceId === instanceId) {
          this.commandSubscriptions.delete(id)
        }
      }

      // Notify subscribers
      this.send({
        type: 'destroyed',
        source: { type: 'module', id: instanceId, moduleType: context.moduleType },
        target: { type: 'agent' },
        payload: { instanceId },
      })
    }
  }

  getContext(instanceId: ModuleInstanceId): ModuleContext | undefined {
    return this.contexts.get(instanceId)
  }

  getAllContexts(): Map<ModuleInstanceId, ModuleContext> {
    return new Map(this.contexts)
  }

  getContextsByType(moduleType: ModuleTypeId): ModuleContext[] {
    return Array.from(this.contexts.values()).filter(
      (ctx) => ctx.moduleType === moduleType
    )
  }

  // --------------------------------------------------------------------------
  // Module Spawning
  // --------------------------------------------------------------------------

  setSpawnHandler(
    handler: (request: SpawnModuleRequest) => Promise<SpawnModuleResponse>
  ): void {
    this.spawnHandler = handler
  }

  setDestroyHandler(
    handler: (instanceId: ModuleInstanceId) => Promise<boolean>
  ): void {
    this.destroyHandler = handler
  }

  async spawnModule(request: SpawnModuleRequest): Promise<SpawnModuleResponse> {
    if (!this.spawnHandler) {
      return {
        success: false,
        error: 'No spawn handler registered',
      }
    }

    if (this.config.debug) {
      console.log('[AgentBus] Spawning module:', request)
    }

    try {
      const response = await this.spawnHandler(request)

      if (response.success && response.instanceId) {
        // Send spawn notification
        this.send({
          type: 'spawn',
          source: { type: 'agent', id: 'primary-agent' },
          target: { type: 'broadcast' },
          payload: { request, response },
        })

        // Execute initial commands if provided
        if (request.initialCommands && response.instanceId) {
          for (const cmd of request.initialCommands) {
            await this.sendCommand(
              { type: 'module', id: response.instanceId },
              cmd
            )
          }
        }
      }

      return response
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Spawn failed',
      }
    }
  }

  async destroyModule(instanceId: ModuleInstanceId): Promise<boolean> {
    if (!this.destroyHandler) {
      console.warn('[AgentBus] No destroy handler registered')
      return false
    }

    try {
      const result = await this.destroyHandler(instanceId)
      if (result) {
        this.unregisterContext(instanceId)
      }
      return result
    } catch (error) {
      console.error('[AgentBus] Destroy failed:', error)
      return false
    }
  }

  // --------------------------------------------------------------------------
  // Event Helpers
  // --------------------------------------------------------------------------

  /**
   * Helper for modules to emit events
   */
  emitModuleEvent<T>(
    instanceId: ModuleInstanceId,
    event: ModuleEvent<T>
  ): MessageId {
    const context = this.contexts.get(instanceId)
    return this.send({
      type: 'event',
      source: {
        type: 'module',
        id: instanceId,
        moduleType: context?.moduleType,
      },
      target: { type: 'agent' },
      payload: event,
      priority: event.requiresAttention ? 'high' : 'normal',
    })
  }

  // --------------------------------------------------------------------------
  // Tab Commands - Direct methods for querying tab context
  // --------------------------------------------------------------------------

  /**
   * Get context from a specific tab by ID
   */
  async getTabContext(tabId: string): Promise<CommandResponse<TabContext | null>> {
    return this.sendCommand<TabQueryCommands['getTabContext'], TabQueryResponses['getTabContext']>(
      { type: 'module', id: 'system:tab-query' },
      { action: 'getTabContext', params: { tabId } }
    )
  }

  /**
   * Get context from the currently active tab
   */
  async getActiveTabContext(): Promise<CommandResponse<TabContext | null>> {
    return this.sendCommand<TabQueryCommands['getActiveTabContext'], TabQueryResponses['getActiveTabContext']>(
      { type: 'module', id: 'system:tab-query' },
      { action: 'getActiveTabContext', params: {} }
    )
  }

  /**
   * Search tabs by various criteria
   */
  async searchTabs(criteria: TabSearchCriteria): Promise<CommandResponse<TabSearchResult>> {
    return this.sendCommand<TabQueryCommands['searchTabsBy'], TabQueryResponses['searchTabsBy']>(
      { type: 'module', id: 'system:tab-query' },
      { action: 'searchTabsBy', params: criteria }
    )
  }

  /**
   * Get summaries of all background (non-active) tabs
   */
  async getBackgroundTabSummaries(maxTabs?: number): Promise<CommandResponse<TabContextSummary[]>> {
    return this.sendCommand<TabQueryCommands['summarizeBackgroundTabs'], TabQueryResponses['summarizeBackgroundTabs']>(
      { type: 'module', id: 'system:tab-query' },
      { action: 'summarizeBackgroundTabs', params: { maxTabs } }
    )
  }

  /**
   * Assemble context ready for agent consumption
   * Includes active tab with full context and background tabs with summaries
   */
  async assembleTabContext(options?: ContextAssemblyOptions): Promise<CommandResponse<AssembledContext>> {
    return this.sendCommand<TabQueryCommands['assembleContext'], TabQueryResponses['assembleContext']>(
      { type: 'module', id: 'system:tab-query' },
      { action: 'assembleContext', params: options || {} }
    )
  }

  /**
   * List all tabs with minimal metadata (lightweight query)
   */
  async listTabs(): Promise<CommandResponse<Array<{ id: string; title: string; moduleType?: string; isActive: boolean }>>> {
    return this.sendCommand<TabQueryCommands['listTabs'], TabQueryResponses['listTabs']>(
      { type: 'module', id: 'system:tab-query' },
      { action: 'listTabs', params: {} }
    )
  }

  /**
   * Set tab priority for context loading decisions
   */
  async setTabPriority(tabId: string, priority: TabPriority): Promise<CommandResponse<{ success: boolean }>> {
    return this.sendCommand<TabQueryCommands['setTabPriority'], TabQueryResponses['setTabPriority']>(
      { type: 'module', id: 'system:tab-query' },
      { action: 'setTabPriority', params: { tabId, priority } }
    )
  }

  /**
   * Find tabs by module type
   */
  async findTabsByModuleType(moduleType: string): Promise<CommandResponse<TabSearchResult>> {
    return this.searchTabs({ moduleTypes: [moduleType] })
  }

  /**
   * Find tabs by URL pattern
   */
  async findTabsByUrl(pattern: string): Promise<CommandResponse<TabSearchResult>> {
    return this.searchTabs({ urlPattern: pattern })
  }
}

// ============================================================================
// Singleton Instance
// ============================================================================

let agentBusInstance: AgentBus | null = null

/**
 * Get the singleton AgentBus instance
 */
export function getAgentBus(config?: AgentBusConfig): AgentBus {
  if (!agentBusInstance) {
    agentBusInstance = new AgentBus(config)
  }
  return agentBusInstance
}

/**
 * Reset the AgentBus (for testing)
 */
export function resetAgentBus(): void {
  agentBusInstance = null
}

export { AgentBus }
export default getAgentBus

