/**
 * Module Template System
 * 
 * A flexible, reusable module architecture for the main content area.
 * 
 * Components:
 * - ModuleContainer: Base container with optional header and flexible body
 * - ModuleHeader: Configurable header with title, breadcrumbs, actions, status
 * - ModuleBody: Flexible body with padding, background, and overflow options
 * 
 * State Components:
 * - EmptyModuleState: Display when module has no content
 * - LoadingModuleState: Display while module is loading
 * - ErrorModuleState: Display when module encounters an error
 * 
 * Registry:
 * - moduleRegistry: Central registry for dynamic module loading
 * - registerModule / unregisterModule: Registry management functions
 * - getModule / getAllModules: Registry query functions
 */

// Core components
export { ModuleContainer, EmptyModuleState, LoadingModuleState, ErrorModuleState } from './module-container'
export { ModuleHeader } from './module-header'
export { ModuleBody } from './module-body'

// Built-in modules
export { BrowserModule, browserModuleConfig } from './browser-module'
export { AgentBrowserModule, agentBrowserModuleConfig } from './agent-browser-module'
export { McpManagerModule, mcpManagerModuleConfig } from './mcp-manager-module'
export { Ag3ntControlPanelModule, ag3ntControlPanelModuleConfig } from './ag3nt-control-panel-module'
export { SchedulerModule, schedulerModuleConfig } from './scheduler-module'

// Registry
export {
  moduleRegistry,
  registerModule,
  unregisterModule,
  getModule,
  getAllModules,
  hasModule,
  getModulesByCategory,
  subscribeToRegistry,
} from './module-registry'

// Re-export types for convenience
export type {
  ModuleConfig,
  ModuleMetadata,
  ModuleState,
  ModuleHeaderConfig,
  ModuleBodyConfig,
  ModuleContainerProps,
  ModuleHeaderProps,
  ModuleBodyProps,
  ModuleComponent,
  ModuleInstanceProps,
  ModuleRegistry,
  ModuleTypeId,
  BreadcrumbItem,
  HeaderAction,
  StatusIndicator,
  BodyPadding,
  OverflowBehavior,
} from '@/types/modules'

