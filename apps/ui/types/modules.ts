/**
 * Module Template System Types
 *
 * Provides a flexible, framework-agnostic module architecture for the main content area.
 * Modules can be dynamically loaded and registered, supporting various content types
 * like browsers, CRM interfaces, data visualizations, file managers, etc.
 */

import type { ReactNode, ComponentType } from "react";

// ============================================================================
// Module Configuration
// ============================================================================

/**
 * Unique identifier for a module type
 */
export type ModuleTypeId = string;

/**
 * Module metadata for registration and display
 */
export interface ModuleMetadata {
  /** Unique identifier for this module type */
  id: ModuleTypeId;
  /** Display name shown in UI */
  displayName: string;
  /** Short description of module functionality */
  description?: string;
  /** Icon name (from lucide-react) or custom icon component */
  icon?: string | ComponentType<{ className?: string }>;
  /** Category for grouping modules */
  category?:
    | "browser"
    | "editor"
    | "data"
    | "communication"
    | "utility"
    | "custom";
  /** Version string for the module */
  version?: string;
}

/**
 * Module state that persists across renders
 */
export interface ModuleState {
  /** Whether the module is currently loading */
  isLoading?: boolean;
  /** Error message if module failed */
  error?: string | null;
  /** Custom state data specific to the module */
  data?: Record<string, unknown>;
}

/**
 * Complete module configuration
 */
export interface ModuleConfig {
  /** Module metadata */
  metadata: ModuleMetadata;
  /** Initial state for the module */
  initialState?: ModuleState;
  /** Whether the module has a header bar */
  hasHeader?: boolean;
  /** Default header configuration */
  defaultHeaderConfig?: ModuleHeaderConfig;
  /** Agent communication configuration */
  agentConfig?: ModuleAgentConfig;
}

/**
 * Agent communication configuration for a module type
 */
export interface ModuleAgentConfig {
  /** Whether this module supports agent communication */
  enabled?: boolean;
  /** Commands this module can handle */
  supportedCommands?: string[];
  /** Events this module emits */
  emittedEvents?: string[];
  /** Context schema description for the agent */
  contextDescription?: string;
  /** What this module expects the agent to provide/set */
  expects?: string[];
  /** What this module provides back to the agent via context/events */
  provides?: string[];
}

// ============================================================================
// Module Header Types
// ============================================================================

/**
 * Breadcrumb item for navigation within a module
 */
export interface BreadcrumbItem {
  label: string;
  href?: string;
  onClick?: () => void;
  icon?: ComponentType<{ className?: string }>;
}

/**
 * Action button in the header
 */
export interface HeaderAction {
  id: string;
  label: string;
  icon?: ComponentType<{ className?: string }>;
  onClick: () => void;
  variant?: "default" | "ghost" | "outline" | "destructive";
  disabled?: boolean;
  tooltip?: string;
}

/**
 * Status indicator configuration
 */
export interface StatusIndicator {
  type: "success" | "warning" | "error" | "info" | "loading";
  label?: string;
  pulse?: boolean;
}

/**
 * Complete header configuration
 */
export interface ModuleHeaderConfig {
  /** Module title (optional - some modules may not need one) */
  title?: string;
  /** Subtitle or secondary info */
  subtitle?: string;
  /** Breadcrumb navigation */
  breadcrumbs?: BreadcrumbItem[];
  /** Left-side actions */
  leftActions?: HeaderAction[];
  /** Right-side actions */
  rightActions?: HeaderAction[];
  /** Status indicator */
  status?: StatusIndicator;
  /** Custom content to render in the header */
  customContent?: ReactNode;
  /** Whether to show a border at the bottom */
  showBorder?: boolean;
}

// ============================================================================
// Module Body Types
// ============================================================================

/**
 * Body padding options
 */
export type BodyPadding = "none" | "sm" | "md" | "lg";

/**
 * Overflow behavior for module body
 */
export type OverflowBehavior = "auto" | "hidden" | "scroll" | "visible";

/**
 * Body configuration
 */
export interface ModuleBodyConfig {
  /** Padding around the content */
  padding?: BodyPadding;
  /** Background color variant */
  background?: "transparent" | "primary" | "surface" | "elevated";
  /** Overflow handling */
  overflow?: OverflowBehavior;
  /** Whether content should scroll horizontally */
  horizontalScroll?: boolean;
}

// ============================================================================
// Module Component Props
// ============================================================================

/**
 * Props for the ModuleContainer component
 */
export interface ModuleContainerProps {
  /** Module configuration */
  config?: ModuleConfig;
  /** Header configuration (if header is shown) */
  headerConfig?: ModuleHeaderConfig;
  /** Body configuration */
  bodyConfig?: ModuleBodyConfig;
  /** Children to render in the body */
  children: ReactNode;
  /** Whether to show the header */
  showHeader?: boolean;
  /** Additional class name */
  className?: string;
}

/**
 * Props for the ModuleHeader component
 */
export interface ModuleHeaderProps extends ModuleHeaderConfig {
  /** Height variant */
  height?: "sm" | "md" | "lg";
  /** Additional class name */
  className?: string;
}

/**
 * Props for the ModuleBody component
 */
export interface ModuleBodyProps extends ModuleBodyConfig {
  /** Content to render */
  children: ReactNode;
  /** Additional class name */
  className?: string;
}

// ============================================================================
// Module Registry Types
// ============================================================================

/**
 * Module component that implements the module interface
 */
export interface ModuleComponent {
  /** The React component to render */
  Component: ComponentType<ModuleInstanceProps>;
  /** Module configuration */
  config: ModuleConfig;
}

/**
 * Props passed to module instances
 */
export interface ModuleInstanceProps {
  /** Instance ID (unique per tab/instance) */
  instanceId: string;
  /** Tab ID this module is associated with */
  tabId?: string;
  /** Initial data for the module */
  initialData?: Record<string, unknown>;
  /** Callback when module state changes */
  onStateChange?: (state: ModuleState) => void;
  /** Callback when module requests to update tab */
  onTabUpdate?: (updates: { title?: string; url?: string }) => void;
  /** Additional class name */
  className?: string;
  /** Whether agent communication is enabled for this instance */
  agentEnabled?: boolean;
  /** Module type ID (for agent registration) */
  moduleType?: string;
}

/**
 * Module registry for dynamic module loading
 */
export interface ModuleRegistry {
  /** Register a new module */
  register: (module: ModuleComponent) => void;
  /** Unregister a module */
  unregister: (moduleId: ModuleTypeId) => void;
  /** Get a registered module */
  get: (moduleId: ModuleTypeId) => ModuleComponent | undefined;
  /** Get all registered modules */
  getAll: () => ModuleComponent[];
  /** Check if a module is registered */
  has: (moduleId: ModuleTypeId) => boolean;
}

// ============================================================================
// Preset Module Types
// ============================================================================

/**
 * Browser module specific types
 */
export interface BrowserModuleData {
  url: string | null;
  canGoBack?: boolean;
  canGoForward?: boolean;
  isSecure?: boolean;
}

/**
 * File manager module specific types
 */
export interface FileManagerModuleData {
  currentPath: string;
  selectedFiles: string[];
  viewMode: "list" | "grid";
}

/**
 * Data visualization module specific types
 */
export interface DataVisualizationModuleData {
  chartType: "line" | "bar" | "pie" | "scatter" | "table";
  dataSource?: string;
  refreshInterval?: number;
}

/**
 * Chat/Communication module specific types
 */
export interface ChatModuleData {
  conversationId?: string;
  participants?: string[];
  unreadCount?: number;
}
