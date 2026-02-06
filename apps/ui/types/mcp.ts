/**
 * MCP (Model Context Protocol) Types
 * 
 * Types for MCP server management, discovery, and configuration.
 * Mirrors the Python models in product_layer/mcp/config.py and catalog.py
 */

// ============================================================================
// MCP Server Configuration Types
// ============================================================================

/**
 * MCP server transport type
 */
export type McpTransport = 'http_jsonrpc' | 'stdio'

/**
 * MCP server connection status
 */
export type McpConnectionStatus = 'connected' | 'disconnected' | 'connecting' | 'error' | 'unknown'

/**
 * MCP server category for grouping in UI
 */
export type McpServerCategory = 
  | 'browser'
  | 'database'
  | 'ai'
  | 'search'
  | 'filesystem'
  | 'communication'
  | 'developer'
  | 'utility'
  | 'other'

/**
 * MCP server configuration
 */
export interface McpServerConfig {
  id: string
  name: string
  transport: McpTransport
  
  // HTTP transport fields
  url?: string
  headers?: Record<string, string>
  
  // Stdio transport fields
  command?: string
  args?: string[]
  env?: Record<string, string>
  
  enabled: boolean
  
  // UI/Display fields
  description: string
  icon: string
  category: McpServerCategory
  
  // Status tracking (runtime fields)
  status: McpConnectionStatus
  error?: string | null
  toolCount: number
  tools: string[]
  lastConnected?: string | null
  installedAt?: string | null
}

// ============================================================================
// MCP Catalog Types (for discovery)
// ============================================================================

/**
 * Catalog source type
 */
export type McpCatalogSource = 'official' | 'community' | 'verified'

/**
 * MCP catalog entry for discovery/installation
 */
export interface McpCatalogEntry {
  id: string
  name: string
  description: string
  category: McpServerCategory
  icon: string
  transport: McpTransport
  
  // Default configuration hints
  default_command?: string | null
  default_args?: string[] | null
  default_url?: string | null
  
  // Installation info
  install_command?: string | null
  documentation_url?: string | null
  source: McpCatalogSource
}

// ============================================================================
// API Response Types
// ============================================================================

/**
 * Response from /api/mcp/servers
 */
export interface McpServersListResponse {
  servers: McpServerConfig[]
}

/**
 * Response from /api/mcp/servers (POST) or /api/mcp/servers/:id
 */
export interface McpServerResponse {
  server: McpServerConfig
}

/**
 * Response from /api/mcp/servers/:id/test
 */
export interface McpServerTestResponse {
  status: McpConnectionStatus
  error?: string | null
  tool_count: number
  tools: string[]
}

/**
 * Response from /api/mcp/catalog
 */
export interface McpCatalogResponse {
  catalog: McpCatalogEntry[]
}

// ============================================================================
// Form/Input Types
// ============================================================================

/**
 * Form data for adding a new MCP server
 */
export interface McpServerFormData {
  id: string
  name: string
  transport: McpTransport
  url?: string
  command?: string
  args?: string
  description?: string
  icon?: string
  category?: McpServerCategory
}

/**
 * Form data for updating an MCP server
 */
export interface McpServerUpdateData {
  name?: string
  enabled?: boolean
  url?: string
  command?: string
  args?: string[]
  env?: Record<string, string>
  description?: string
}

// ============================================================================
// Module Data Types
// ============================================================================

/**
 * MCP Manager module state
 */
export interface McpManagerModuleData {
  servers: McpServerConfig[]
  catalog: McpCatalogEntry[]
  selectedServer: McpServerConfig | null
  searchQuery: string
  categoryFilter: McpServerCategory | 'all'
  view: 'installed' | 'discover'
  isLoading: boolean
  error: string | null
}

