"use client"

import { useState, useEffect, useCallback, useMemo } from 'react'
import { getTabContextManager, TabContextManager } from '@/lib/tab-context-manager'
import type {
  TabContext,
  TabSearchCriteria,
  TabSearchResult,
  TabStateEvent,
  TabContextSummary,
  ContextAssemblyOptions,
  AssembledContext,
  TabPriority,
} from '@/types/tab-context'

// ============================================================================
// useTabContext - Access current tab context
// ============================================================================

/**
 * Hook to get the current tab context (active tab by default)
 */
export function useTabContext(tabId?: string): TabContext | undefined {
  const manager = useMemo(() => getTabContextManager(), [])
  const [context, setContext] = useState<TabContext | undefined>(() => 
    tabId ? manager.getTabContext(tabId) : manager.getActiveTabContext()
  )

  useEffect(() => {
    // Update on tab state changes
    const unsubscribe = manager.onTabStateChange((event) => {
      if (tabId) {
        // Specific tab - only update if this tab changed
        if (event.tabId === tabId) {
          setContext(manager.getTabContext(tabId))
        }
      } else {
        // Active tab - update on activation changes or active tab updates
        if (event.type === 'tab-activated' || 
            (event.type === 'tab-updated' && manager.getActiveTabContext()?.tab.id === event.tabId) ||
            event.type === 'tab-context-changed') {
          setContext(manager.getActiveTabContext())
        }
      }
    })

    return unsubscribe
  }, [manager, tabId])

  return context
}

// ============================================================================
// useActiveTabContext - Specifically for active tab
// ============================================================================

/**
 * Hook to get the active tab's context with automatic updates
 */
export function useActiveTabContext(): TabContext | undefined {
  return useTabContext()
}

// ============================================================================
// useTabSearch - Search tabs by criteria
// ============================================================================

interface UseTabSearchOptions {
  /** Auto-update results on tab changes */
  autoUpdate?: boolean
  /** Debounce delay for updates (ms) */
  debounceMs?: number
}

/**
 * Hook to search tabs by criteria
 */
export function useTabSearch(
  criteria: TabSearchCriteria,
  options: UseTabSearchOptions = {}
): TabSearchResult {
  const { autoUpdate = true, debounceMs = 100 } = options
  const manager = useMemo(() => getTabContextManager(), [])
  
  const [result, setResult] = useState<TabSearchResult>(() => 
    manager.searchTabs(criteria)
  )

  // Re-search when criteria changes
  useEffect(() => {
    setResult(manager.searchTabs(criteria))
  }, [manager, JSON.stringify(criteria)])

  // Auto-update on tab changes
  useEffect(() => {
    if (!autoUpdate) return

    let timeoutId: ReturnType<typeof setTimeout> | null = null

    const unsubscribe = manager.onTabStateChange(() => {
      // Debounce updates
      if (timeoutId) clearTimeout(timeoutId)
      timeoutId = setTimeout(() => {
        setResult(manager.searchTabs(criteria))
      }, debounceMs)
    })

    return () => {
      if (timeoutId) clearTimeout(timeoutId)
      unsubscribe()
    }
  }, [manager, criteria, autoUpdate, debounceMs])

  return result
}

// ============================================================================
// useBackgroundTabs - Get background tab summaries
// ============================================================================

/**
 * Hook to get summaries of background (non-active) tabs
 */
export function useBackgroundTabs(maxTabs?: number): TabContextSummary[] {
  const manager = useMemo(() => getTabContextManager(), [])
  const [summaries, setSummaries] = useState<TabContextSummary[]>(() => {
    const all = manager.summarizeBackgroundTabs()
    return maxTabs ? all.slice(0, maxTabs) : all
  })

  useEffect(() => {
    const unsubscribe = manager.onTabStateChange(() => {
      const all = manager.summarizeBackgroundTabs()
      setSummaries(maxTabs ? all.slice(0, maxTabs) : all)
    })

    return unsubscribe
  }, [manager, maxTabs])

  return summaries
}

// ============================================================================
// useAssembledContext - Get assembled context for agent
// ============================================================================

/**
 * Hook to get assembled context ready for agent consumption
 */
export function useAssembledContext(
  options?: ContextAssemblyOptions
): AssembledContext {
  const manager = useMemo(() => getTabContextManager(), [])
  const [assembled, setAssembled] = useState<AssembledContext>(() => 
    manager.assembleContext(options)
  )

  useEffect(() => {
    const unsubscribe = manager.onTabStateChange(() => {
      setAssembled(manager.assembleContext(options))
    })

    return unsubscribe
  }, [manager, options])

  return assembled
}

// ============================================================================
// useTabStateEvents - Subscribe to tab state events
// ============================================================================

/**
 * Hook to subscribe to tab state change events
 */
export function useTabStateEvents(
  handler: (event: TabStateEvent) => void,
  deps: React.DependencyList = []
): void {
  const manager = useMemo(() => getTabContextManager(), [])

  useEffect(() => {
    const unsubscribe = manager.onTabStateChange(handler)
    return unsubscribe
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manager, ...deps])
}

// ============================================================================
// useTabContextManager - Direct access to manager
// ============================================================================

interface TabContextManagerActions {
  getTabContext: (tabId: string) => TabContext | undefined
  getActiveTabContext: () => TabContext | undefined
  searchTabs: (criteria: TabSearchCriteria) => TabSearchResult
  findTabsByModuleType: (moduleType: string) => TabContext[]
  findTabsByUrl: (pattern: string | RegExp) => TabContext[]
  summarizeBackgroundTabs: () => TabContextSummary[]
  assembleContext: (options?: ContextAssemblyOptions) => AssembledContext
  setTabPriority: (tabId: string, priority: TabPriority) => void
}

/**
 * Hook providing direct access to TabContextManager methods
 */
export function useTabContextManager(): TabContextManagerActions {
  const manager = useMemo(() => getTabContextManager(), [])

  return useMemo(() => ({
    getTabContext: manager.getTabContext.bind(manager),
    getActiveTabContext: manager.getActiveTabContext.bind(manager),
    searchTabs: manager.searchTabs.bind(manager),
    findTabsByModuleType: manager.findTabsByModuleType.bind(manager),
    findTabsByUrl: manager.findTabsByUrl.bind(manager),
    summarizeBackgroundTabs: manager.summarizeBackgroundTabs.bind(manager),
    assembleContext: manager.assembleContext.bind(manager),
    setTabPriority: manager.setTabPriority.bind(manager),
  }), [manager])
}

