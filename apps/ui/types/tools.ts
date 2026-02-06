/**
 * Tool Types for the Tools Library Module
 * 
 * Defines types for tool discovery, management, and MCP integration.
 */

// ============================================================================
// Tool Parameter Types
// ============================================================================

/**
 * Parameter type for tool arguments
 */
export type ToolParamType = 'string' | 'number' | 'integer' | 'boolean' | 'array' | 'object'

/**
 * Tool parameter definition
 */
export interface ToolParameter {
  name: string
  type: ToolParamType
  description: string
  required: boolean
  default?: unknown
  enum?: unknown[]
}

// ============================================================================
// Tool Types
// ============================================================================

/**
 * Tool source identifier
 */
export type ToolSource = 'builtin' | 'mcp' | 'plugin' | 'custom' | 'unknown'

/**
 * Tool status
 */
export type ToolStatus = 'active' | 'deferred' | 'disabled' | 'error'

/**
 * Tool category for filtering
 */
export type ToolCategory =
  | 'filesystem'
  | 'web'
  | 'ai'
  | 'browser'
  | 'shell'
  | 'exec'
  | 'process'
  | 'patch'
  | 'data'
  | 'communication'
  | 'utility'
  | 'mcp'
  | 'general'

/**
 * Tool metadata
 */
export interface ToolMetadata {
  category: ToolCategory
  tags: string[]
  cost: 'free' | 'low' | 'medium' | 'high'
  requiresApproval: boolean
  timeoutSeconds?: number
  maxRetries: number
  cacheable: boolean
  cacheTtlSeconds: number
}

/**
 * Complete tool definition
 */
export interface Tool {
  name: string
  description: string
  parameters: ToolParameter[]
  source: ToolSource
  status: ToolStatus
  metadata: ToolMetadata
  mcpServer?: string
  usageCount?: number
  lastUsed?: string
}

// ============================================================================
// MCP Types
// ============================================================================

/**
 * MCP server connection status
 */
export type MCPConnectionStatus = 'connected' | 'disconnected' | 'connecting' | 'error'

/**
 * MCP server information
 */
export interface MCPServer {
  name: string
  status: MCPConnectionStatus
  transport: 'stdio' | 'sse' | 'websocket'
  toolCount: number
  tools: string[]
  lastConnected?: string
  error?: string
}

// ============================================================================
// API Response Types
// ============================================================================

/**
 * Response from /api/tools endpoint
 */
export interface ToolsListResponse {
  tools: Tool[]
  total: number
  limit: number
  offset: number
  hasMore: boolean
  mcpServers?: MCPServer[]
}

/**
 * Tool search/filter parameters
 */
export interface ToolsFilterParams {
  search?: string
  category?: ToolCategory
  source?: ToolSource
  status?: ToolStatus
  limit?: number
  offset?: number
}

// ============================================================================
// Module Data Types
// ============================================================================

/**
 * Tools library module specific data
 */
export interface ToolsLibraryModuleData {
  tools: Tool[]
  selectedTool: Tool | null
  viewMode: 'list' | 'grid'
  searchQuery: string
  categoryFilter: ToolCategory | 'all'
  sourceFilter: ToolSource | 'all'
  statusFilter: ToolStatus | 'all'
  totalTools: number
  mcpServers: MCPServer[]
}

