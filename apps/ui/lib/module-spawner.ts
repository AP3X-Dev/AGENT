/**
 * Module Spawner
 * 
 * Utility for spawning module instances as tabs.
 * Integrates the AgentBus spawn system with the TabsProvider.
 */

import { getAgentBus } from './agent-bus'
import { getModule, hasModule } from '@/components/modules/module-registry'
import type { SpawnModuleRequest, SpawnModuleResponse, ModuleInstanceId } from '@/types/agent-communication'
import type { Tab } from '@/types/types'

// ============================================================================
// Types
// ============================================================================

/**
 * Tab manager interface (provided by TabsProvider)
 */
export interface TabManager {
  addTab: (tab?: Partial<Tab>) => string
  removeTab: (id: string) => void
  updateTab: (id: string, updates: Partial<Tab>) => void
  setActiveTab: (id: string) => void
  tabs: Tab[]
}

/**
 * Module instance tracking
 */
interface ModuleInstance {
  instanceId: ModuleInstanceId
  tabId: string
  moduleType: string
  createdAt: number
}

// ============================================================================
// Module Instance Registry
// ============================================================================

const moduleInstances = new Map<ModuleInstanceId, ModuleInstance>()
const tabToInstance = new Map<string, ModuleInstanceId>()

/**
 * Generate a unique module instance ID
 */
function generateInstanceId(): ModuleInstanceId {
  return `module-${Date.now().toString(36)}-${Math.random().toString(36).substring(2, 9)}`
}

/**
 * Get module instance by ID
 */
export function getModuleInstance(instanceId: ModuleInstanceId): ModuleInstance | undefined {
  return moduleInstances.get(instanceId)
}

/**
 * Get module instance by tab ID
 */
export function getModuleInstanceByTab(tabId: string): ModuleInstance | undefined {
  const instanceId = tabToInstance.get(tabId)
  return instanceId ? moduleInstances.get(instanceId) : undefined
}

/**
 * Get all module instances
 */
export function getAllModuleInstances(): ModuleInstance[] {
  return Array.from(moduleInstances.values())
}

// ============================================================================
// Spawn Handler Factory
// ============================================================================

/**
 * Create a spawn handler for use with AgentProvider
 * 
 * @param tabManager - Tab manager from useTabs hook
 * @returns Spawn handler function
 */
export function createSpawnHandler(
  tabManager: TabManager
): (request: SpawnModuleRequest) => Promise<SpawnModuleResponse> {
  return async (request: SpawnModuleRequest): Promise<SpawnModuleResponse> => {
    const { moduleType, initialData, tabConfig } = request

    // Validate module type exists
    if (!hasModule(moduleType)) {
      return {
        success: false,
        error: `Module type '${moduleType}' is not registered`,
      }
    }

    // Get module config
    const moduleComponent = getModule(moduleType)
    if (!moduleComponent) {
      return {
        success: false,
        error: `Failed to get module '${moduleType}'`,
      }
    }

    // Generate instance ID
    const instanceId = generateInstanceId()

    // Create tab
    const tabId = tabManager.addTab({
      title: tabConfig?.title || moduleComponent.config.metadata.displayName,
      url: null,
      moduleType,
      moduleInstanceId: instanceId,
      moduleData: initialData,
      icon: tabConfig?.icon,
      closable: tabConfig?.closable ?? true,
      isLoading: false,
    })

    // Track instance
    const instance: ModuleInstance = {
      instanceId,
      tabId,
      moduleType,
      createdAt: Date.now(),
    }
    moduleInstances.set(instanceId, instance)
    tabToInstance.set(tabId, instanceId)

    // Activate tab if requested
    if (tabConfig?.activate !== false) {
      tabManager.setActiveTab(tabId)
    }

    return {
      success: true,
      instanceId,
      tabId,
    }
  }
}

/**
 * Create a destroy handler for use with AgentProvider
 * 
 * @param tabManager - Tab manager from useTabs hook
 * @returns Destroy handler function
 */
export function createDestroyHandler(
  tabManager: TabManager
): (instanceId: ModuleInstanceId) => Promise<boolean> {
  return async (instanceId: ModuleInstanceId): Promise<boolean> => {
    const instance = moduleInstances.get(instanceId)
    if (!instance) {
      return false
    }

    // Remove tab
    tabManager.removeTab(instance.tabId)

    // Clean up tracking
    moduleInstances.delete(instanceId)
    tabToInstance.delete(instance.tabId)

    // Unregister from AgentBus
    const bus = getAgentBus()
    bus.unregisterContext(instanceId)

    return true
  }
}

/**
 * Initialize the module spawner with the AgentBus
 * 
 * Call this from a component that has access to useTabs
 */
export function initializeModuleSpawner(tabManager: TabManager): void {
  const bus = getAgentBus()
  bus.setSpawnHandler(createSpawnHandler(tabManager))
  bus.setDestroyHandler(createDestroyHandler(tabManager))
}

/**
 * Clean up module instances when tabs are closed externally
 */
export function cleanupModuleInstance(tabId: string): void {
  const instanceId = tabToInstance.get(tabId)
  if (instanceId) {
    moduleInstances.delete(instanceId)
    tabToInstance.delete(tabId)

    // Notify AgentBus
    const bus = getAgentBus()
    bus.unregisterContext(instanceId)
  }
}

