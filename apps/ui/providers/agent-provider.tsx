"use client"

import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useCallback,
  useRef,
  type ReactNode,
} from 'react'
import { getAgentBus, AgentBus } from '@/lib/agent-bus'
import { initializeTabQueryHandlers } from '@/lib/tab-query-handler'
import type {
  IAgentBus,
  ModuleContext,
  ModuleInstanceId,
  AgentBusConfig,
  SpawnModuleRequest,
  SpawnModuleResponse,
  AgentMessage,
  MessageFilter,
  AgentBusSubscription,
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
} from '@/types/tab-context'

// ============================================================================
// Context Types
// ============================================================================

interface AgentContextValue {
  /** The AgentBus instance */
  bus: AgentBus
  /** Whether the agent system is ready */
  isReady: boolean
  /** Spawn a new module */
  spawnModule: (request: SpawnModuleRequest) => Promise<SpawnModuleResponse>
  /** Get all module contexts */
  getAllContexts: () => Map<ModuleInstanceId, ModuleContext>
  /** Get contexts by module type */
  getContextsByType: (moduleType: ModuleTypeId) => ModuleContext[]
  /** Send a command to a module */
  sendCommand: IAgentBus['sendCommand']
  /** Subscribe to messages */
  subscribe: IAgentBus['subscribe']

  // Tab Context Commands
  /** Get context from a specific tab */
  getTabContext: AgentBus['getTabContext']
  /** Get context from the active tab */
  getActiveTabContext: AgentBus['getActiveTabContext']
  /** Search tabs by criteria */
  searchTabs: AgentBus['searchTabs']
  /** Get background tab summaries */
  getBackgroundTabSummaries: AgentBus['getBackgroundTabSummaries']
  /** Assemble tab context for agent consumption */
  assembleTabContext: AgentBus['assembleTabContext']
  /** List all tabs (lightweight) */
  listTabs: AgentBus['listTabs']
  /** Set tab priority */
  setTabPriority: AgentBus['setTabPriority']
}

// ============================================================================
// Context
// ============================================================================

const AgentContext = createContext<AgentContextValue | null>(null)

// ============================================================================
// Provider Component
// ============================================================================

interface AgentProviderProps {
  children: ReactNode
  config?: AgentBusConfig
  onSpawnModule?: (request: SpawnModuleRequest) => Promise<SpawnModuleResponse>
  onDestroyModule?: (instanceId: ModuleInstanceId) => Promise<boolean>
}

/**
 * AgentProvider - Provides agent communication context to the application
 *
 * This provider initializes the AgentBus and makes it available to all
 * child components via the useAgent hook.
 */
export function AgentProvider({
  children,
  config,
  onSpawnModule,
  onDestroyModule,
}: AgentProviderProps) {
  const busRef = useRef<AgentBus | null>(null)
  const tabHandlersCleanupRef = useRef<(() => void) | null>(null)

  // Initialize bus
  if (!busRef.current) {
    busRef.current = getAgentBus(config)
  }

  const bus = busRef.current

  // Initialize tab query handlers
  useEffect(() => {
    // Initialize tab query command handlers
    tabHandlersCleanupRef.current = initializeTabQueryHandlers()

    if (config?.debug) {
      console.log('[AgentProvider] Tab query handlers initialized')
    }

    return () => {
      if (tabHandlersCleanupRef.current) {
        tabHandlersCleanupRef.current()
        tabHandlersCleanupRef.current = null
      }
    }
  }, [config?.debug])

  // Register spawn/destroy handlers
  useEffect(() => {
    if (onSpawnModule) {
      bus.setSpawnHandler(onSpawnModule)
    }
    if (onDestroyModule) {
      bus.setDestroyHandler(onDestroyModule)
    }
  }, [bus, onSpawnModule, onDestroyModule])

  // Memoize context value
  const value = useMemo<AgentContextValue>(
    () => ({
      bus,
      isReady: true,
      spawnModule: bus.spawnModule.bind(bus),
      getAllContexts: bus.getAllContexts.bind(bus),
      getContextsByType: bus.getContextsByType.bind(bus),
      sendCommand: bus.sendCommand.bind(bus),
      subscribe: bus.subscribe.bind(bus),
      // Tab context commands
      getTabContext: bus.getTabContext.bind(bus),
      getActiveTabContext: bus.getActiveTabContext.bind(bus),
      searchTabs: bus.searchTabs.bind(bus),
      getBackgroundTabSummaries: bus.getBackgroundTabSummaries.bind(bus),
      assembleTabContext: bus.assembleTabContext.bind(bus),
      listTabs: bus.listTabs.bind(bus),
      setTabPriority: bus.setTabPriority.bind(bus),
    }),
    [bus]
  )

  return <AgentContext.Provider value={value}>{children}</AgentContext.Provider>
}

// ============================================================================
// Hooks
// ============================================================================

/**
 * useAgent - Access the agent communication system
 */
export function useAgent(): AgentContextValue {
  const context = useContext(AgentContext)
  if (!context) {
    throw new Error('useAgent must be used within an AgentProvider')
  }
  return context
}

/**
 * useAgentSubscription - Subscribe to agent messages
 */
export function useAgentSubscription<T = unknown>(
  filter: MessageFilter,
  handler: (message: AgentMessage<T>) => void,
  deps: React.DependencyList = []
): void {
  const { subscribe } = useAgent()

  useEffect(() => {
    const subscription = subscribe(filter, handler)
    return () => subscription.unsubscribe()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subscribe, ...deps])
}

/**
 * useModuleContexts - Get all module contexts with live updates
 */
export function useModuleContexts(): ModuleContext[] {
  const { bus, subscribe } = useAgent()
  const [contexts, setContexts] = React.useState<ModuleContext[]>([])

  useEffect(() => {
    // Initial load
    setContexts(Array.from(bus.getAllContexts().values()))

    // Subscribe to context updates
    const subscription = subscribe(
      {
        type: ['context-update', 'ready', 'destroyed'],
        source: { type: 'module' },
      },
      () => {
        setContexts(Array.from(bus.getAllContexts().values()))
      }
    )

    return () => subscription.unsubscribe()
  }, [bus, subscribe])

  return contexts
}

/**
 * useModuleContext - Get a specific module's context with live updates
 */
export function useModuleContext(
  instanceId: ModuleInstanceId | undefined
): ModuleContext | undefined {
  const { bus, subscribe } = useAgent()
  const [context, setContext] = React.useState<ModuleContext | undefined>(
    instanceId ? bus.getContext(instanceId) : undefined
  )

  useEffect(() => {
    if (!instanceId) {
      setContext(undefined)
      return
    }

    // Initial load
    setContext(bus.getContext(instanceId))

    // Subscribe to updates for this specific module
    const subscription = subscribe(
      {
        type: ['context-update', 'ready', 'destroyed'],
        source: { type: 'module', id: instanceId },
      },
      (message) => {
        if (message.type === 'destroyed') {
          setContext(undefined)
        } else {
          setContext(message.payload as ModuleContext)
        }
      }
    )

    return () => subscription.unsubscribe()
  }, [bus, subscribe, instanceId])

  return context
}

