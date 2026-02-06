/**
 * Tab Query Handler
 * 
 * Handles agent commands for querying and retrieving tab context.
 * Integrates with the AgentBus to provide tab-aware context management.
 */

import { getAgentBus } from './agent-bus'
import { getTabContextManager } from './tab-context-manager'
import type {
  TabSearchCriteria,
  ContextAssemblyOptions,
  TabPriority,
  TabQueryCommands,
  TabQueryResponses,
} from '@/types/tab-context'
import type { CommandContext } from '@/types/agent-communication'

// ============================================================================
// Command Handler Registration
// ============================================================================

/**
 * Initialize tab query command handlers
 * Call this once during app initialization
 */
export function initializeTabQueryHandlers(): () => void {
  const bus = getAgentBus()
  const manager = getTabContextManager()
  const subscriptions: Array<{ unsubscribe: () => void }> = []

  // getTabContext - Get full context from a specific tab
  subscriptions.push(
    bus.subscribeToCommands<TabQueryCommands['getTabContext'], TabQueryResponses['getTabContext']>(
      'system:tab-query',
      'getTabContext',
      async (params) => {
        return manager.getTabContext(params.tabId) || null
      }
    )
  )

  // getActiveTabContext - Get context from currently active tab
  subscriptions.push(
    bus.subscribeToCommands<TabQueryCommands['getActiveTabContext'], TabQueryResponses['getActiveTabContext']>(
      'system:tab-query',
      'getActiveTabContext',
      async () => {
        return manager.getActiveTabContext() || null
      }
    )
  )

  // searchTabsBy - Find tabs matching certain conditions
  subscriptions.push(
    bus.subscribeToCommands<TabQueryCommands['searchTabsBy'], TabQueryResponses['searchTabsBy']>(
      'system:tab-query',
      'searchTabsBy',
      async (criteria) => {
        return manager.searchTabs(criteria)
      }
    )
  )

  // summarizeBackgroundTabs - Get brief summaries of non-active tabs
  subscriptions.push(
    bus.subscribeToCommands<TabQueryCommands['summarizeBackgroundTabs'], TabQueryResponses['summarizeBackgroundTabs']>(
      'system:tab-query',
      'summarizeBackgroundTabs',
      async (params) => {
        const summaries = manager.summarizeBackgroundTabs()
        if (params.maxTabs && summaries.length > params.maxTabs) {
          return summaries.slice(0, params.maxTabs)
        }
        return summaries
      }
    )
  )

  // assembleContext - Assemble context with options
  subscriptions.push(
    bus.subscribeToCommands<TabQueryCommands['assembleContext'], TabQueryResponses['assembleContext']>(
      'system:tab-query',
      'assembleContext',
      async (options) => {
        return manager.assembleContext(options)
      }
    )
  )

  // listTabs - Get all tabs metadata (lightweight)
  subscriptions.push(
    bus.subscribeToCommands<TabQueryCommands['listTabs'], TabQueryResponses['listTabs']>(
      'system:tab-query',
      'listTabs',
      async (params) => {
        const contexts = manager.getAllTabContexts()
        return contexts.map(ctx => ({
          id: ctx.tab.id,
          title: ctx.tab.title,
          moduleType: ctx.tab.moduleType,
          isActive: ctx.isActive,
        }))
      }
    )
  )

  // setTabPriority - Set tab priority
  subscriptions.push(
    bus.subscribeToCommands<TabQueryCommands['setTabPriority'], TabQueryResponses['setTabPriority']>(
      'system:tab-query',
      'setTabPriority',
      async (params) => {
        manager.setTabPriority(params.tabId, params.priority)
        return { success: true }
      }
    )
  )

  // Return cleanup function
  return () => {
    subscriptions.forEach(sub => sub.unsubscribe())
  }
}

// ============================================================================
// Convenience Functions for Agent Use
// ============================================================================

/**
 * Query tab context by ID
 */
export async function queryTabContext(tabId: string) {
  const bus = getAgentBus()
  return bus.sendCommand<TabQueryCommands['getTabContext'], TabQueryResponses['getTabContext']>(
    { type: 'module', id: 'system:tab-query' },
    { action: 'getTabContext', params: { tabId } }
  )
}

/**
 * Query active tab context
 */
export async function queryActiveTabContext() {
  const bus = getAgentBus()
  return bus.sendCommand<TabQueryCommands['getActiveTabContext'], TabQueryResponses['getActiveTabContext']>(
    { type: 'module', id: 'system:tab-query' },
    { action: 'getActiveTabContext', params: {} }
  )
}

/**
 * Search tabs by criteria
 */
export async function searchTabs(criteria: TabSearchCriteria) {
  const bus = getAgentBus()
  return bus.sendCommand<TabQueryCommands['searchTabsBy'], TabQueryResponses['searchTabsBy']>(
    { type: 'module', id: 'system:tab-query' },
    { action: 'searchTabsBy', params: criteria }
  )
}

/**
 * Get background tab summaries
 */
export async function getBackgroundTabSummaries(maxTabs?: number) {
  const bus = getAgentBus()
  return bus.sendCommand<TabQueryCommands['summarizeBackgroundTabs'], TabQueryResponses['summarizeBackgroundTabs']>(
    { type: 'module', id: 'system:tab-query' },
    { action: 'summarizeBackgroundTabs', params: { maxTabs } }
  )
}

/**
 * Assemble context for agent consumption
 */
export async function assembleAgentContext(options?: ContextAssemblyOptions) {
  const bus = getAgentBus()
  return bus.sendCommand<TabQueryCommands['assembleContext'], TabQueryResponses['assembleContext']>(
    { type: 'module', id: 'system:tab-query' },
    { action: 'assembleContext', params: options || {} }
  )
}

/**
 * List all tabs (lightweight)
 */
export async function listAllTabs() {
  const bus = getAgentBus()
  return bus.sendCommand<TabQueryCommands['listTabs'], TabQueryResponses['listTabs']>(
    { type: 'module', id: 'system:tab-query' },
    { action: 'listTabs', params: {} }
  )
}

/**
 * Set tab priority for context loading
 */
export async function setTabPriority(tabId: string, priority: TabPriority) {
  const bus = getAgentBus()
  return bus.sendCommand<TabQueryCommands['setTabPriority'], TabQueryResponses['setTabPriority']>(
    { type: 'module', id: 'system:tab-query' },
    { action: 'setTabPriority', params: { tabId, priority } }
  )
}

