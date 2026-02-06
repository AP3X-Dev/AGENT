/**
 * E2B Sandbox Middleware
 *
 * Middleware layer for managing sandbox lifecycle, security,
 * and providing a clean interface for agent code execution.
 */

import { getSandboxService, E2BSandboxService } from './sandbox-service'
import {
  getSandboxToolDefinitions,
  createSandboxTools,
  executeCode,
  getOrCreateSession,
} from './sandbox-tools'
import type {
  SandboxSessionId,
  SandboxSession,
  CodeExecutionRequest,
  CodeExecutionResponse,
  SandboxConfig,
  ExecutionResult,
} from '@/types/e2b-sandbox'

// ============================================================================
// Middleware Types
// ============================================================================

/**
 * Sandbox execution context for the agent
 */
export interface SandboxExecutionContext {
  /** Current session ID (if any) */
  sessionId: SandboxSessionId | null
  /** Current session */
  session: SandboxSession | null
  /** Execution history */
  history: ExecutionHistoryEntry[]
  /** Created files */
  createdFiles: string[]
}

/**
 * Execution history entry
 */
export interface ExecutionHistoryEntry {
  /** Execution timestamp */
  timestamp: number
  /** Code that was executed */
  code: string
  /** Language used */
  language: string
  /** Whether execution was successful */
  success: boolean
  /** Execution duration in ms */
  durationMs: number
  /** Brief description */
  description?: string
  /** Error message if failed */
  error?: string
}

/**
 * Agent sandbox request
 */
export interface AgentSandboxRequest {
  /** Tool name to execute */
  tool: string
  /** Tool input parameters */
  input: Record<string, unknown>
  /** Request metadata */
  metadata?: {
    agentId?: string
    taskId?: string
    purpose?: string
  }
}

/**
 * Agent sandbox response
 */
export interface AgentSandboxResponse {
  /** Whether the operation was successful */
  success: boolean
  /** Result data */
  result: unknown
  /** Error message if failed */
  error?: string
  /** Session ID for follow-up operations */
  sessionId?: SandboxSessionId
  /** Execution summary */
  summary?: string
}

// ============================================================================
// Sandbox Middleware
// ============================================================================

/**
 * Sandbox Middleware
 *
 * Provides a high-level interface for agent sandbox operations
 * with lifecycle management, security, and logging.
 */
export class SandboxMiddleware {
  private service: E2BSandboxService
  private context: SandboxExecutionContext
  private debug: boolean
  private maxHistorySize: number

  constructor(config?: {
    apiKey?: string
    debug?: boolean
    maxHistorySize?: number
  }) {
    this.service = getSandboxService({
      apiKey: config?.apiKey,
      debug: config?.debug,
    })
    this.debug = config?.debug || false
    this.maxHistorySize = config?.maxHistorySize || 100
    this.context = {
      sessionId: null,
      session: null,
      history: [],
      createdFiles: [],
    }
  }

  private log(...args: unknown[]) {
    if (this.debug) {
      console.log('[SandboxMiddleware]', ...args)
    }
  }

  /**
   * Get tool definitions for the agent
   */
  getToolDefinitions() {
    return getSandboxToolDefinitions()
  }

  /**
   * Get current execution context
   */
  getContext(): SandboxExecutionContext {
    return { ...this.context }
  }

  /**
   * Execute an agent sandbox request
   */
  async executeRequest(request: AgentSandboxRequest): Promise<AgentSandboxResponse> {
    this.log('Executing request:', request.tool, request.metadata?.purpose)

    try {
      const tools = createSandboxTools({ debug: this.debug })
      const tool = tools.get(request.tool)

      if (!tool) {
        return {
          success: false,
          result: null,
          error: `Unknown tool: ${request.tool}`,
        }
      }

      // Ensure session exists for tools that need it
      // TODO: Implement ensureSession method
      // if (request.tool !== 'execute_code' || !request.input.session_id) {
      //   const session = await this.ensureSession()
      //   if (!request.input.session_id) {
      //     request.input.session_id = session.id
      //   }
      // }

      const result = await tool.handler(request.input)

      // Track execution history for code execution
      if (request.tool === 'execute_code') {
        const execResult = result as CodeExecutionResponse
        this.addToHistory({
          timestamp: Date.now(),
          code: request.input.code as string,
          language: (request.input.language as string) || 'python',
          success: execResult.success,
          durationMs: execResult.durationMs,
          description: request.input.description as string,
          error: execResult.error?.message,
        })
      }

      return {
        success: true,
        result,
        sessionId: this.context.sessionId || undefined,
        summary: this.generateSummary(request.tool, result),
      }
    } catch (error) {
      this.log('Request failed:', error)
      return {
        success: false,
        result: null,
        error: (error as Error).message,
        sessionId: this.context.sessionId || undefined,
      }
    }
  }

  /**
   * Quick code execution with automatic session management
   */
  async runCode(
    code: string,
    options?: {
      language?: 'python' | 'javascript' | 'typescript'
      description?: string
    }
  ): Promise<CodeExecutionResponse> {
    // TODO: Implement ensureSession method
    // const session = await this.ensureSession()

    const response = await this.service.executeCode({
      code,
      language: options?.language || 'python',
      sessionId: '', // session.id,
      description: options?.description,
    })

    this.addToHistory({
      timestamp: Date.now(),
      code,
      language: options?.language || 'python',
      success: response.success,
      durationMs: response.durationMs,
      description: options?.description,
      error: response.error?.message,
    })

    return response
  }

  /**
   * Format execution results for agent consumption
   */
  formatResults(response: CodeExecutionResponse): string {
    const parts: string[] = []

    if (response.success) {
      parts.push('✓ Execution successful')
    } else {
      parts.push('✗ Execution failed')
    }

    parts.push(`Duration: ${response.durationMs}ms`)

    // Add stdout
    if (response.stdout.length > 0) {
      parts.push('\n--- Output ---')
      parts.push(response.stdout.map(m => m.content).join('\n'))
    }

    // Add stderr
    if (response.stderr.length > 0) {
      parts.push('\n--- Errors/Warnings ---')
      parts.push(response.stderr.map(m => m.content).join('\n'))
    }

    // Add results
    if (response.results.length > 0) {
      parts.push('\n--- Results ---')
      for (const result of response.results) {
        if (result.type === 'text' && result.text) {
          parts.push(result.text)
        } else if (result.type === 'image') {
          parts.push(`[Image: ${result.png ? 'PNG' : 'JPEG'} data]`)
        } else if (result.type === 'json') {
          parts.push(JSON.stringify(result.json, null, 2))
        }
      }
    }

    // Add error details
    if (response.error) {
      parts.push('\n--- Error Details ---')
      parts.push(`${response.error.name}: ${response.error.message}`)
      if (response.error.traceback) {
        parts.push(response.error.traceback)
      }
    }

    return parts.join('\n')
  }

  /**
   * Extract images from execution results
   */
  extractImages(response: CodeExecutionResponse): Array<{
    type: 'png' | 'jpeg'
    data: string
  }> {
    return response.results
      .filter(r => r.type === 'image')
      .map(r => ({
        type: r.png ? 'png' as const : 'jpeg' as const,
        data: r.png || r.jpeg || '',
      }))
  }

  /**
   * Clean up and terminate the session
   */
  async cleanup(): Promise<void> {
    if (this.context.sessionId) {
      await this.service.terminateSession(this.context.sessionId)
      this.context.sessionId = null
      this.context.session = null
      this.log('Session cleaned up')
    }
  }

  private addToHistory(entry: ExecutionHistoryEntry): void {
    this.context.history.push(entry)
    if (this.context.history.length > this.maxHistorySize) {
      this.context.history.shift()
    }
  }

  private generateSummary(tool: string, result: unknown): string {
    switch (tool) {
      case 'execute_code': {
        const r = result as CodeExecutionResponse
        return r.success
          ? `Code executed successfully in ${r.durationMs}ms`
          : `Code execution failed: ${r.error?.message}`
      }
      case 'install_packages': {
        const r = result as { installed: string[]; failed: string[] }
        return `Installed ${r.installed.length} packages, ${r.failed.length} failed`
      }
      case 'upload_file':
        return 'File uploaded successfully'
      case 'download_file':
        return 'File downloaded successfully'
      case 'list_files': {
        const r = result as unknown[]
        return `Found ${r.length} files/directories`
      }
      case 'run_command': {
        const r = result as { exitCode: number }
        return `Command completed with exit code ${r.exitCode}`
      }
      default:
        return 'Operation completed'
    }
  }
}

// ============================================================================
// Singleton Instance
// ============================================================================

let middlewareInstance: SandboxMiddleware | null = null

/**
 * Get the sandbox middleware singleton
 */
export function getSandboxMiddleware(config?: {
  apiKey?: string
  debug?: boolean
}): SandboxMiddleware {
  if (!middlewareInstance) {
    middlewareInstance = new SandboxMiddleware(config)
  }
  return middlewareInstance
}

/**
 * Create a new sandbox middleware instance (for isolated contexts)
 */
export function createSandboxMiddleware(config?: {
  apiKey?: string
  debug?: boolean
}): SandboxMiddleware {
  return new SandboxMiddleware(config)
}
