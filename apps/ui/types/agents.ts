/**
 * Agent type definitions for the Agents Library module
 */

/**
 * Agent mode/type
 */
export type AgentMode = 'main' | 'subagent' | 'tool' | 'custom'

/**
 * Agent status
 */
export type AgentStatus = 'active' | 'inactive' | 'error' | 'loading'

/**
 * Agent category for grouping
 */
export type AgentCategory = 
  | 'general'
  | 'coding'
  | 'research'
  | 'data'
  | 'creative'
  | 'automation'
  | 'analysis'
  | 'custom'

/**
 * Model configuration
 */
export interface ModelConfig {
  provider: string
  model: string
  temperature?: number
}

/**
 * Permission configuration
 */
export interface PermissionConfig {
  [key: string]: 'allow' | 'deny' | Record<string, 'allow' | 'deny'>
}

/**
 * Agent metadata
 */
export interface AgentMetadata {
  category: AgentCategory
  tags: string[]
  version?: string
  author?: string
  createdAt?: string
  updatedAt?: string
}

/**
 * Agent definition
 */
export interface Agent {
  name: string
  description: string
  mode: AgentMode
  status: AgentStatus
  systemPrompt: string
  model: ModelConfig
  permissions: PermissionConfig
  enabledTools: string[]
  disabledTools: string[]
  middleware: string[]
  metadata: AgentMetadata
  sourcePath?: string
}

/**
 * Agent list response from API
 */
export interface AgentsListResponse {
  agents: Agent[]
  total: number
  limit: number
  offset: number
  hasMore: boolean
}

/**
 * Agent filter parameters
 */
export interface AgentsFilterParams {
  search?: string
  mode?: AgentMode
  category?: AgentCategory
  status?: AgentStatus
  limit?: number
  offset?: number
}

/**
 * Agents Library module data
 */
export interface AgentsLibraryModuleData {
  agents: Agent[]
  selectedAgent: Agent | null
  viewMode: 'list' | 'grid'
  searchQuery: string
  modeFilter: AgentMode | 'all'
  categoryFilter: AgentCategory | 'all'
  statusFilter: AgentStatus | 'all'
  totalAgents: number
}

