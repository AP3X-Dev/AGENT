/**
 * E2B Sandbox Module
 *
 * Exports for E2B sandbox code execution capabilities.
 */

// Core service
export { E2BSandboxService, getSandboxService } from './sandbox-service'

// Agent tools
export {
  createSandboxTools,
  getSandboxToolDefinitions,
  executeSandboxTool,
  executeCode,
  getOrCreateSession,
} from './sandbox-tools'

// Middleware
export {
  SandboxMiddleware,
  getSandboxMiddleware,
  createSandboxMiddleware,
} from './sandbox-middleware'

// Re-export types
export type {
  SandboxExecutionContext,
  ExecutionHistoryEntry,
  AgentSandboxRequest,
  AgentSandboxResponse,
} from './sandbox-middleware'

