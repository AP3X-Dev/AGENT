/**
 * Tab Context Management Types
 * 
 * Defines types for the tab-aware context management system that enables
 * intelligent querying and retrieval of information from specific tabs
 * without loading all contexts into the conversation window.
 */

import type { Tab } from './types'
import type { ModuleContext, ModuleInstanceId } from './agent-communication'

// ============================================================================
// Tab Context Types
// ============================================================================

/**
 * Extended tab information with context data
 */
export interface TabContext {
  /** Base tab information */
  tab: Tab
  /** Associated module context (if module is registered) */
  moduleContext?: ModuleContext
  /** Whether this is the currently active tab */
  isActive: boolean
  /** When the tab was last accessed */
  lastAccessedAt: number
  /** When the tab context was last updated */
  lastUpdatedAt: number
  /** Priority level for context loading */
  priority: TabPriority
  /** Brief summary of tab content (for background tabs) */
  summary?: TabSummary
}

/**
 * Tab priority levels for context loading
 */
export type TabPriority = 'critical' | 'high' | 'normal' | 'low' | 'background'

/**
 * Summary of a tab's content for efficient context loading
 */
export interface TabSummary {
  /** One-line description of tab content */
  title: string
  /** Brief summary (2-3 sentences max) */
  description: string
  /** Key data points */
  keyPoints?: string[]
  /** Content type classification */
  contentType?: 'webpage' | 'form' | 'document' | 'data' | 'media' | 'empty'
  /** Whether the tab has unsaved changes */
  hasUnsavedChanges?: boolean
  /** Word count or data size estimate */
  contentSize?: 'small' | 'medium' | 'large'
  /** When summary was generated */
  generatedAt: number
}

// ============================================================================
// Tab Query Types
// ============================================================================

/**
 * Criteria for searching/filtering tabs
 */
export interface TabSearchCriteria {
  /** Filter by tab ID(s) */
  tabIds?: string[]
  /** Filter by module instance ID(s) */
  instanceIds?: ModuleInstanceId[]
  /** Filter by module type(s) */
  moduleTypes?: string[]
  /** Filter by active status */
  isActive?: boolean
  /** Filter by loading status */
  isLoading?: boolean
  /** Filter by error status */
  hasError?: boolean
  /** Filter tabs with specific URL patterns */
  urlPattern?: string | RegExp
  /** Filter tabs with specific title patterns */
  titlePattern?: string | RegExp
  /** Filter tabs with unsaved changes */
  hasUnsavedChanges?: boolean
  /** Filter by content type */
  contentTypes?: TabSummary['contentType'][]
  /** Filter by priority level */
  priorities?: TabPriority[]
  /** Custom filter function */
  customFilter?: (context: TabContext) => boolean
  /** Maximum number of results */
  limit?: number
  /** Sort order */
  sortBy?: 'lastAccessed' | 'lastUpdated' | 'priority' | 'title'
  /** Sort direction */
  sortDirection?: 'asc' | 'desc'
}

/**
 * Result from tab search
 */
export interface TabSearchResult {
  /** Matching tabs */
  tabs: TabContext[]
  /** Total count before limit */
  totalCount: number
  /** Search criteria used */
  criteria: TabSearchCriteria
  /** Timestamp of search */
  searchedAt: number
}

// ============================================================================
// Context Assembly Types
// ============================================================================

/**
 * Options for context assembly
 */
export interface ContextAssemblyOptions {
  /** Include full context for active tab */
  includeActiveTabFull?: boolean
  /** Include summaries for background tabs */
  includeBackgroundSummaries?: boolean
  /** Maximum number of background tabs to include */
  maxBackgroundTabs?: number
  /** Priority threshold (only include tabs at or above this priority) */
  minPriority?: TabPriority
  /** Include module context data */
  includeModuleContext?: boolean
  /** Custom context transformer */
  transform?: (context: TabContext) => unknown
}

/**
 * Assembled context ready for agent consumption
 */
export interface AssembledContext {
  /** Active tab with full context */
  activeTab?: TabContext
  /** Background tabs with summaries */
  backgroundTabs: TabContextSummary[]
  /** Total tab count */
  totalTabs: number
  /** Assembly options used */
  options: ContextAssemblyOptions
  /** Timestamp of assembly */
  assembledAt: number
  /** Estimated token count (if applicable) */
  estimatedTokens?: number
}

/**
 * Summarized tab context for background tabs
 */
export interface TabContextSummary {
  tabId: string
  title: string
  moduleType?: string
  summary: TabSummary
  isActive: boolean
  priority: TabPriority
}

// ============================================================================
// Tab State Events
// ============================================================================

/**
 * Tab state change event types
 */
export type TabStateEventType =
  | 'tab-opened'
  | 'tab-closed'
  | 'tab-activated'
  | 'tab-deactivated'
  | 'tab-updated'
  | 'tab-context-changed'
  | 'tabs-reordered'

/**
 * Tab state change event payload
 */
export interface TabStateEvent {
  type: TabStateEventType
  tabId: string
  tab?: Tab
  previousTabId?: string
  previousTab?: Tab
  changes?: Partial<Tab>
  timestamp: number
}

// ============================================================================
// Tab Context Manager Interface
// ============================================================================

/**
 * Tab Context Manager interface for querying and managing tab contexts
 */
export interface ITabContextManager {
  // Context retrieval
  getTabContext(tabId: string): TabContext | undefined
  getActiveTabContext(): TabContext | undefined
  getAllTabContexts(): TabContext[]
  
  // Querying
  searchTabs(criteria: TabSearchCriteria): TabSearchResult
  findTabsByModuleType(moduleType: string): TabContext[]
  findTabsByUrl(pattern: string | RegExp): TabContext[]
  
  // Summaries
  getTabSummary(tabId: string): TabSummary | undefined
  generateTabSummary(tabId: string): Promise<TabSummary>
  summarizeBackgroundTabs(): TabContextSummary[]
  
  // Context assembly
  assembleContext(options?: ContextAssemblyOptions): AssembledContext
  
  // State management
  updateTabContext(tabId: string, updates: Partial<TabContext>): void
  setTabPriority(tabId: string, priority: TabPriority): void
  
  // Event subscription
  onTabStateChange(handler: (event: TabStateEvent) => void): () => void
}

// ============================================================================
// Agent Tab Commands
// ============================================================================

/**
 * Tab query command payloads
 */
export interface TabQueryCommands {
  /** Get full context from a specific tab */
  getTabContext: { tabId: string }
  /** Get context from currently active tab */
  getActiveTabContext: Record<string, never>
  /** Search for tabs matching criteria */
  searchTabsBy: TabSearchCriteria
  /** Get summaries of background tabs */
  summarizeBackgroundTabs: { maxTabs?: number }
  /** Assemble context with options */
  assembleContext: ContextAssemblyOptions
  /** Get all tabs metadata (lightweight) */
  listTabs: { includeContext?: boolean }
  /** Set tab priority */
  setTabPriority: { tabId: string; priority: TabPriority }
}

/**
 * Tab query command responses
 */
export interface TabQueryResponses {
  getTabContext: TabContext | null
  getActiveTabContext: TabContext | null
  searchTabsBy: TabSearchResult
  summarizeBackgroundTabs: TabContextSummary[]
  assembleContext: AssembledContext
  listTabs: Array<{ id: string; title: string; moduleType?: string; isActive: boolean }>
  setTabPriority: { success: boolean }
}

