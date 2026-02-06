/**
 * Agent-Module Communication Protocol Types
 * 
 * Defines the bidirectional communication system between AI agents and UI modules.
 * This is the foundation for the A2UI (Agent-to-UI) protocol.
 * 
 * Architecture:
 * - AgentBus: Central event hub for message routing
 * - Modules: Register contexts and handle commands
 * - Agent: Sends commands and reads module contexts
 */

import type { ModuleTypeId, ModuleState } from './modules'

// ============================================================================
// Core Identifiers
// ============================================================================

/** Unique identifier for a module instance */
export type ModuleInstanceId = string

/** Unique identifier for a message */
export type MessageId = string

/** Message correlation ID for request-response patterns */
export type CorrelationId = string

// ============================================================================
// Message Protocol
// ============================================================================

/**
 * Base message structure for all agent-module communication
 */
export interface AgentMessage<T = unknown> {
  /** Unique message identifier */
  id: MessageId
  /** Timestamp when message was created */
  timestamp: number
  /** Message type discriminator */
  type: AgentMessageType
  /** Source of the message */
  source: MessageSource
  /** Target of the message */
  target: MessageTarget
  /** Message payload */
  payload: T
  /** Optional correlation ID for request-response */
  correlationId?: CorrelationId
  /** Message priority */
  priority?: 'low' | 'normal' | 'high' | 'critical'
}

/**
 * Message types for agent-module communication
 */
export type AgentMessageType =
  // Agent -> Module commands
  | 'command'           // Execute an action
  | 'query'             // Request data
  | 'update'            // Update module state
  | 'spawn'             // Create new module instance
  | 'destroy'           // Close module instance
  // Module -> Agent notifications  
  | 'context-update'    // Module context changed
  | 'event'             // User interaction or module event
  | 'response'          // Response to query
  | 'error'             // Error notification
  | 'ready'             // Module is ready
  | 'destroyed'         // Module was destroyed

/**
 * Message source identifier
 */
export interface MessageSource {
  type: 'agent' | 'module' | 'system'
  id: string
  moduleType?: ModuleTypeId
}

/**
 * Message target identifier
 */
export interface MessageTarget {
  type: 'agent' | 'module' | 'broadcast' | 'module-type' | 'system'
  id?: string
  moduleType?: ModuleTypeId
}

// ============================================================================
// Agent Commands (Agent -> Module)
// ============================================================================

/**
 * Base command structure
 */
export interface AgentCommand<T = unknown> {
  /** Command name */
  action: string
  /** Command parameters */
  params: T
  /** Whether to wait for completion */
  await?: boolean
  /** Timeout in milliseconds */
  timeout?: number
}

/**
 * Standard commands available to all modules
 */
export interface StandardCommands {
  /** Set focus to this module */
  focus: Record<string, never>
  /** Refresh module content */
  refresh: Record<string, never>
  /** Get current module context */
  getContext: Record<string, never>
  /** Update module data */
  setData: { data: Record<string, unknown>; merge?: boolean }
  /** Trigger a header action */
  triggerAction: { actionId: string }
  /** Scroll to position */
  scrollTo: { x?: number; y?: number; behavior?: 'auto' | 'smooth' }
}

/**
 * Browser module specific commands
 */
export interface BrowserCommands extends StandardCommands {
  navigate: { url: string }
  goBack: Record<string, never>
  goForward: Record<string, never>
  reload: { hardReload?: boolean }
  executeScript: { script: string }
}

/**
 * CRM module specific commands
 */
export interface CRMCommands extends StandardCommands {
  selectContact: { contactId: string }
  updateField: { fieldName: string; value: unknown }
  saveContact: Record<string, never>
  createContact: { initialData?: Record<string, unknown> }
  deleteContact: { contactId: string; confirm?: boolean }
}

/**
 * Email module specific commands
 */
export interface EmailCommands extends StandardCommands {
  compose: { to?: string; subject?: string; body?: string }
  setRecipients: { to?: string[]; cc?: string[]; bcc?: string[] }
  setSubject: { subject: string }
  setBody: { body: string; format?: 'text' | 'html' }
  attachFile: { path: string }
  send: Record<string, never>
  saveDraft: Record<string, never>
}

/**
 * File manager module specific commands
 */
export interface FileManagerCommands extends StandardCommands {
  navigateTo: { path: string }
  selectFiles: { paths: string[] }
  createFolder: { name: string }
  deleteFiles: { paths: string[]; confirm?: boolean }
  copyFiles: { sourcePaths: string[]; destinationPath: string }
  moveFiles: { sourcePaths: string[]; destinationPath: string }
}

// ============================================================================
// Module Context (Module -> Agent)
// ============================================================================

/**
 * Base context structure all modules must provide
 */
export interface BaseModuleContext {
  /** Module instance ID */
  instanceId: ModuleInstanceId
  /** Module type ID */
  moduleType: ModuleTypeId
  /** Current module state */
  state: ModuleState
  /** Whether module is ready for commands */
  isReady: boolean
  /** Timestamp of last update */
  lastUpdated: number
  /** User-focused element or selection */
  focus?: {
    type: string
    id?: string
    data?: unknown
  }
}

/**
 * Browser module context
 */
export interface BrowserContext extends BaseModuleContext {
  moduleType: 'browser'
  url: string | null
  title: string | null
  canGoBack: boolean
  canGoForward: boolean
  isLoading: boolean
  isSecure: boolean
}

/**
 * CRM module context
 */
export interface CRMContext extends BaseModuleContext {
  moduleType: 'crm'
  selectedContact: {
    id: string
    name: string
    email?: string
    phone?: string
    company?: string
    [key: string]: unknown
  } | null
  isDirty: boolean
  formFields: Record<string, unknown>
  recentContacts: Array<{ id: string; name: string }>
}

/**
 * Email module context
 */
export interface EmailContext extends BaseModuleContext {
  moduleType: 'email'
  mode: 'compose' | 'read' | 'list'
  currentEmail?: {
    id?: string
    to: string[]
    cc?: string[]
    bcc?: string[]
    subject: string
    body: string
    attachments?: Array<{ name: string; size: number }>
    isDraft: boolean
  }
  selectedEmails?: string[]
}

/**
 * File manager module context
 */
export interface FileManagerContext extends BaseModuleContext {
  moduleType: 'file-manager'
  currentPath: string
  selectedFiles: Array<{
    path: string
    name: string
    type: 'file' | 'directory'
    size?: number
  }>
  viewMode: 'list' | 'grid' | 'details'
  sortBy: string
  sortDirection: 'asc' | 'desc'
}

/**
 * Union of all module contexts
 */
export type ModuleContext =
  | BrowserContext
  | CRMContext
  | EmailContext
  | FileManagerContext
  | (BaseModuleContext & Record<string, unknown>)

// ============================================================================
// Module Events (Module -> Agent)
// ============================================================================

/**
 * Base event structure
 */
export interface ModuleEvent<T = unknown> {
  /** Event type */
  type: string
  /** Event data */
  data: T
  /** Whether this event requires agent attention */
  requiresAttention?: boolean
  /** User action that triggered this event */
  userAction?: string
}

/**
 * Standard events all modules can emit
 */
export interface StandardEvents {
  'focus-changed': { previousFocus?: unknown; currentFocus: unknown }
  'selection-changed': { selection: unknown[] }
  'data-changed': { field: string; oldValue: unknown; newValue: unknown }
  'action-completed': { action: string; result: unknown }
  'error-occurred': { error: string; recoverable: boolean }
  'user-interaction': { type: string; target: string; data?: unknown }
}

// ============================================================================
// Module Spawning
// ============================================================================

/**
 * Request to spawn a new module instance
 */
export interface SpawnModuleRequest {
  /** Type of module to spawn */
  moduleType: ModuleTypeId
  /** Initial data for the module */
  initialData?: Record<string, unknown>
  /** Tab configuration */
  tabConfig?: {
    title?: string
    icon?: string
    closable?: boolean
    /** Position: 'end' adds at end, number inserts at position */
    position?: 'end' | number
    /** Whether to activate the new tab */
    activate?: boolean
  }
  /** Initial commands to execute after spawn */
  initialCommands?: AgentCommand[]
}

/**
 * Response from spawning a module
 */
export interface SpawnModuleResponse {
  success: boolean
  instanceId?: ModuleInstanceId
  tabId?: string
  error?: string
}

// ============================================================================
// Command Response
// ============================================================================

/**
 * Response from executing a command
 */
export interface CommandResponse<T = unknown> {
  success: boolean
  data?: T
  error?: string
  /** Duration in milliseconds */
  duration?: number
}

/**
 * Query response with typed data
 */
export interface QueryResponse<T = unknown> extends CommandResponse<T> {
  /** Whether data is stale */
  isStale?: boolean
  /** Cache TTL in milliseconds */
  cacheTTL?: number
}

// ============================================================================
// Agent Bus Types
// ============================================================================

/**
 * Subscription to agent bus events
 */
export interface AgentBusSubscription {
  /** Unsubscribe from events */
  unsubscribe: () => void
}

/**
 * Handler for agent messages
 */
export type AgentMessageHandler<T = unknown> = (
  message: AgentMessage<T>
) => void | Promise<void>

/**
 * Handler for commands with response
 */
export type CommandHandler<TParams = unknown, TResult = unknown> = (
  params: TParams,
  context: CommandContext
) => TResult | Promise<TResult>

/**
 * Context passed to command handlers
 */
export interface CommandContext {
  instanceId: ModuleInstanceId
  moduleType: ModuleTypeId
  correlationId?: CorrelationId
  signal?: AbortSignal
}

/**
 * Agent bus configuration
 */
export interface AgentBusConfig {
  /** Enable debug logging */
  debug?: boolean
  /** Default command timeout */
  defaultTimeout?: number
  /** Maximum queued messages */
  maxQueueSize?: number
  /** Enable message persistence */
  persistMessages?: boolean
}

/**
 * Agent bus interface
 */
export interface IAgentBus {
  // Message sending
  send<T>(message: Omit<AgentMessage<T>, 'id' | 'timestamp'>): MessageId
  sendCommand<TParams, TResult>(
    target: MessageTarget,
    command: AgentCommand<TParams>
  ): Promise<CommandResponse<TResult>>

  // Subscriptions
  subscribe<T>(
    filter: MessageFilter,
    handler: AgentMessageHandler<T>
  ): AgentBusSubscription
  subscribeToCommands<TParams, TResult>(
    moduleInstanceId: ModuleInstanceId,
    commandName: string,
    handler: CommandHandler<TParams, TResult>
  ): AgentBusSubscription

  // Context management
  registerContext(
    instanceId: ModuleInstanceId,
    context: ModuleContext
  ): void
  updateContext(
    instanceId: ModuleInstanceId,
    updates: Partial<ModuleContext>
  ): void
  unregisterContext(instanceId: ModuleInstanceId): void
  getContext(instanceId: ModuleInstanceId): ModuleContext | undefined
  getAllContexts(): Map<ModuleInstanceId, ModuleContext>
  getContextsByType(moduleType: ModuleTypeId): ModuleContext[]

  // Module spawning
  spawnModule(request: SpawnModuleRequest): Promise<SpawnModuleResponse>
  destroyModule(instanceId: ModuleInstanceId): Promise<boolean>

  // Utilities
  generateId(): string
  getConfig(): AgentBusConfig
}

/**
 * Filter for subscribing to specific messages
 */
export interface MessageFilter {
  /** Filter by message type */
  type?: AgentMessageType | AgentMessageType[]
  /** Filter by source */
  source?: Partial<MessageSource>
  /** Filter by target */
  target?: Partial<MessageTarget>
  /** Custom filter function */
  custom?: (message: AgentMessage) => boolean
}

// ============================================================================
// Module Integration Types
// ============================================================================

/**
 * Context schema definition for type-safe module contexts
 */
export interface ModuleContextSchema<T extends BaseModuleContext = BaseModuleContext> {
  /** Module type this schema applies to */
  moduleType: ModuleTypeId
  /** Default context values */
  defaultContext: Omit<T, keyof BaseModuleContext>
  /** Validate context data */
  validate?: (context: T) => boolean
  /** Transform context before sending to agent */
  serialize?: (context: T) => Record<string, unknown>
}

/**
 * Command schema for type-safe command handling
 */
export interface ModuleCommandSchema<TCommands = StandardCommands> {
  /** Module type this schema applies to */
  moduleType: ModuleTypeId
  /** Available commands */
  commands: {
    [K in keyof TCommands]: {
      description: string
      params: TCommands[K]
      returns?: unknown
    }
  }
}

/**
 * Extended module instance props with agent communication
 */
export interface AgentConnectedModuleProps {
  /** Agent bus instance for communication */
  agentBus: IAgentBus
  /** Register module context */
  registerContext: (context: Omit<BaseModuleContext, 'instanceId' | 'moduleType'>) => void
  /** Update module context */
  updateContext: (updates: Partial<ModuleContext>) => void
  /** Send event to agent */
  sendEvent: <T>(event: ModuleEvent<T>) => void
  /** Handle incoming command */
  onCommand: <TParams, TResult>(
    commandName: string,
    handler: CommandHandler<TParams, TResult>
  ) => AgentBusSubscription
}

