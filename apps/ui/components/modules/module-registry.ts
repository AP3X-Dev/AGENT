/**
 * Module Registry
 * 
 * A centralized registry for dynamically loading and managing modules.
 * Modules can be registered at runtime, enabling plugin-like extensibility.
 */

import type { ModuleTypeId, ModuleComponent, ModuleRegistry } from "@/types/modules"

/**
 * Internal module storage
 */
const modules = new Map<ModuleTypeId, ModuleComponent>()

/**
 * Event listeners for registry changes
 */
type RegistryListener = (moduleId: ModuleTypeId, action: 'register' | 'unregister') => void
const listeners = new Set<RegistryListener>()

/**
 * Subscribe to registry changes
 */
export function subscribeToRegistry(listener: RegistryListener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/**
 * Notify all listeners of a registry change
 */
function notifyListeners(moduleId: ModuleTypeId, action: 'register' | 'unregister') {
  listeners.forEach(listener => listener(moduleId, action))
}

/**
 * Register a new module
 */
export function registerModule(module: ModuleComponent): void {
  const moduleId = module.config.metadata.id
  
  if (modules.has(moduleId)) {
    console.warn(`Module "${moduleId}" is already registered. It will be replaced.`)
  }
  
  modules.set(moduleId, module)
  notifyListeners(moduleId, 'register')
}

/**
 * Unregister a module
 */
export function unregisterModule(moduleId: ModuleTypeId): void {
  if (modules.has(moduleId)) {
    modules.delete(moduleId)
    notifyListeners(moduleId, 'unregister')
  }
}

/**
 * Get a registered module
 */
export function getModule(moduleId: ModuleTypeId): ModuleComponent | undefined {
  return modules.get(moduleId)
}

/**
 * Get all registered modules
 */
export function getAllModules(): ModuleComponent[] {
  return Array.from(modules.values())
}

/**
 * Check if a module is registered
 */
export function hasModule(moduleId: ModuleTypeId): boolean {
  return modules.has(moduleId)
}

/**
 * Get modules by category
 */
export function getModulesByCategory(
  category: ModuleComponent['config']['metadata']['category']
): ModuleComponent[] {
  return getAllModules().filter(m => m.config.metadata.category === category)
}

/**
 * The module registry singleton
 */
export const moduleRegistry: ModuleRegistry = {
  register: registerModule,
  unregister: unregisterModule,
  get: getModule,
  getAll: getAllModules,
  has: hasModule,
}

export default moduleRegistry

