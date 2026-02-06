/**
 * E2B Sandbox Service
 *
 * Core service for managing E2B sandbox sessions and code execution.
 * Provides the agent with secure isolated code execution capabilities.
 */

import type {
  SandboxSessionId,
  SandboxSession,
  SandboxState,
  SandboxConfig,
  SandboxLanguage,
  CodeExecutionRequest,
  CodeExecutionResponse,
  CommandExecutionRequest,
  CommandExecutionResponse,
  PackageInstallRequest,
  PackageInstallResponse,
  FileReadRequest,
  FileReadResponse,
  FileWriteRequest,
  FileListRequest,
  SandboxFile,
  ExecutionResult,
  ExecutionError,
  OutputMessage,
  ISandboxService,
} from '@/types/e2b-sandbox'

// ============================================================================
// E2B SDK Import (Dynamic to handle SSR)
// ============================================================================

let SandboxClass: typeof import('@e2b/code-interpreter').Sandbox | null = null

async function getSandboxClass() {
  if (!SandboxClass) {
    const module = await import('@e2b/code-interpreter')
    SandboxClass = module.Sandbox
  }
  return SandboxClass
}

// ============================================================================
// Types for internal sandbox management
// ============================================================================

interface ManagedSandbox {
  session: SandboxSession
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  instance: any // E2B Sandbox instance
  cleanupTimer?: NodeJS.Timeout
}

// ============================================================================
// Sandbox Service Implementation
// ============================================================================

/**
 * E2B Sandbox Service
 * Manages sandbox sessions and provides code execution capabilities
 */
export class E2BSandboxService implements ISandboxService {
  private sandboxes = new Map<SandboxSessionId, ManagedSandbox>()
  private apiKey: string
  private defaultTimeoutMs: number
  private debug: boolean

  constructor(config?: {
    apiKey?: string
    defaultTimeoutMs?: number
    debug?: boolean
  }) {
    this.apiKey = config?.apiKey || process.env.E2B_API_KEY || ''
    this.defaultTimeoutMs = config?.defaultTimeoutMs || 5 * 60 * 1000 // 5 minutes
    this.debug = config?.debug || false

    if (!this.apiKey) {
      console.warn('[E2BSandboxService] No API key provided. Set E2B_API_KEY environment variable.')
    }
  }

  private log(...args: unknown[]) {
    if (this.debug) {
      console.log('[E2BSandboxService]', ...args)
    }
  }

  private generateSessionId(): SandboxSessionId {
    return `sbx_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`
  }

  /**
   * Create a new sandbox session
   */
  async createSession(config?: SandboxConfig): Promise<SandboxSession> {
    const Sandbox = await getSandboxClass()
    const sessionId = this.generateSessionId()
    const now = Date.now()
    const timeoutMs = config?.timeoutMs || this.defaultTimeoutMs

    this.log('Creating sandbox session:', sessionId)

    try {
      // Create E2B sandbox instance
      const instance = await Sandbox.create({
        apiKey: this.apiKey,
        timeoutMs,
        ...(config?.template && { template: config.template }),
      })

      // Set environment variables if provided
      if (config?.envVars) {
        for (const [key, value] of Object.entries(config.envVars)) {
          await instance.commands.run(`export ${key}="${value}"`)
        }
      }

      const session: SandboxSession = {
        id: sessionId,
        state: 'ready',
        createdAt: now,
        lastActivityAt: now,
        config: config || {},
        executionCount: 0,
        installedPackages: [],
      }

      const managed: ManagedSandbox = {
        session,
        instance,
      }

      // Set up cleanup timer if not keeping alive indefinitely
      if (!config?.keepAlive) {
        managed.cleanupTimer = setTimeout(() => {
          this.terminateSession(sessionId).catch(console.error)
        }, timeoutMs)
      }

      this.sandboxes.set(sessionId, managed)
      this.log('Sandbox session created:', sessionId)

      return session
    } catch (error) {
      this.log('Failed to create sandbox:', error)
      throw new Error(`Failed to create sandbox: ${(error as Error).message}`)
    }
  }

  /**
   * Get an existing session
   */
  async getSession(sessionId: SandboxSessionId): Promise<SandboxSession | null> {
    const managed = this.sandboxes.get(sessionId)
    return managed ? managed.session : null
  }

  /**
   * List active sessions
   */
  async listSessions(): Promise<SandboxSession[]> {
    return Array.from(this.sandboxes.values()).map(m => m.session)
  }

  /**
   * Execute code in sandbox
   */
  async executeCode(request: CodeExecutionRequest): Promise<CodeExecutionResponse> {
    const startTime = Date.now()
    let sessionId = request.sessionId
    let managed: ManagedSandbox | undefined

    // Get or create session
    if (sessionId) {
      managed = this.sandboxes.get(sessionId)
      if (!managed) {
        throw new Error(`Session not found: ${sessionId}`)
      }
    } else {
      const session = await this.createSession({
        timeoutMs: request.timeoutMs || this.defaultTimeoutMs,
        envVars: request.envVars,
      })
      sessionId = session.id
      managed = this.sandboxes.get(sessionId)!
    }

    const { instance, session } = managed
    session.state = 'executing'
    session.lastActivityAt = Date.now()

    this.log('Executing code in session:', sessionId, request.description || '')

    // Upload files if provided
    if (request.files && request.files.length > 0) {
      for (const file of request.files) {
        const content = file.isBase64
          ? Buffer.from(file.content, 'base64')
          : file.content
        await instance.files.write(file.path, content)
      }
    }

    const stdout: OutputMessage[] = []
    const stderr: OutputMessage[] = []
    const results: ExecutionResult[] = []
    let error: ExecutionError | undefined

    try {
      const execution = await instance.runCode(request.code, {
        language: request.language || 'python',
        timeoutMs: request.timeoutMs,
        envs: request.envVars,
        onStdout: (msg: { line: string }) => {
          stdout.push({
            type: 'stdout',
            content: msg.line,
            timestamp: Date.now(),
          })
        },
        onStderr: (msg: { line: string }) => {
          stderr.push({
            type: 'stderr',
            content: msg.line,
            timestamp: Date.now(),
          })
        },
      })

      // Process execution results
      if (execution.error) {
        error = {
          name: execution.error.name || 'ExecutionError',
          message: execution.error.value || execution.error.message || 'Unknown error',
          traceback: execution.error.traceback,
        }
      }

      // Process result objects
      if (execution.results) {
        for (const result of execution.results) {
          const execResult: ExecutionResult = {
            type: 'text',
          }

          if (result.png) {
            execResult.type = 'image'
            execResult.png = result.png
          } else if (result.jpeg) {
            execResult.type = 'image'
            execResult.jpeg = result.jpeg
          } else if (result.html) {
            execResult.type = 'html'
            execResult.html = result.html
          } else if (result.svg) {
            execResult.type = 'html'
            execResult.svg = result.svg
          } else if (result.json) {
            execResult.type = 'json'
            execResult.json = result.json
          } else if (result.text) {
            execResult.type = 'text'
            execResult.text = result.text
          }

          if (result.value !== undefined) {
            execResult.value = result.value
          }

          results.push(execResult)
        }
      }

      // Update session state
      session.executionCount++
      session.state = 'idle'
      session.lastActivityAt = Date.now()

      return {
        success: !error,
        sessionId,
        executionCount: session.executionCount,
        results,
        stdout,
        stderr,
        error,
        durationMs: Date.now() - startTime,
      }
    } catch (err) {
      session.state = 'error'
      throw err
    }
  }

  /**
   * Run shell command in sandbox
   */
  async runCommand(request: CommandExecutionRequest): Promise<CommandExecutionResponse> {
    const startTime = Date.now()
    const managed = this.sandboxes.get(request.sessionId)

    if (!managed) {
      throw new Error(`Session not found: ${request.sessionId}`)
    }

    const { instance, session } = managed
    session.lastActivityAt = Date.now()

    this.log('Running command in session:', request.sessionId, request.command)

    try {
      const result = await instance.commands.run(request.command, {
        cwd: request.cwd,
        timeoutMs: request.timeoutMs,
      })

      return {
        exitCode: result.exitCode || 0,
        stdout: result.stdout || '',
        stderr: result.stderr || '',
        durationMs: Date.now() - startTime,
      }
    } catch (error) {
      return {
        exitCode: 1,
        stdout: '',
        stderr: (error as Error).message,
        durationMs: Date.now() - startTime,
      }
    }
  }

  /**
   * Install packages in sandbox
   */
  async installPackages(request: PackageInstallRequest): Promise<PackageInstallResponse> {
    const managed = this.sandboxes.get(request.sessionId)

    if (!managed) {
      throw new Error(`Session not found: ${request.sessionId}`)
    }

    const { instance, session } = managed
    session.lastActivityAt = Date.now()
    const manager = request.manager || 'pip'

    this.log('Installing packages:', request.packages, 'with', manager)

    const installed: string[] = []
    const failed: string[] = []
    let output = ''

    for (const pkg of request.packages) {
      try {
        const command = manager === 'pip'
          ? `pip install ${pkg}`
          : `npm install ${pkg}`

        const result = await instance.commands.run(command)
        output += result.stdout + '\n' + result.stderr + '\n'

        if (result.exitCode === 0) {
          installed.push(pkg)
          session.installedPackages.push(pkg)
        } else {
          failed.push(pkg)
        }
      } catch (error) {
        failed.push(pkg)
        output += (error as Error).message + '\n'
      }
    }

    return {
      success: failed.length === 0,
      installed,
      failed,
      output,
    }
  }

  /**
   * Read file from sandbox
   */
  async readFile(request: FileReadRequest): Promise<FileReadResponse> {
    const managed = this.sandboxes.get(request.sessionId)

    if (!managed) {
      throw new Error(`Session not found: ${request.sessionId}`)
    }

    const { instance, session } = managed
    session.lastActivityAt = Date.now()

    this.log('Reading file:', request.path)

    const content = await instance.files.read(request.path)
    const isBase64 = request.asBase64 || false

    return {
      content: isBase64 ? Buffer.from(content).toString('base64') : content,
      isBase64,
      path: request.path,
    }
  }

  /**
   * Write file to sandbox
   */
  async writeFile(request: FileWriteRequest): Promise<void> {
    const managed = this.sandboxes.get(request.sessionId)

    if (!managed) {
      throw new Error(`Session not found: ${request.sessionId}`)
    }

    const { instance, session } = managed
    session.lastActivityAt = Date.now()

    this.log('Writing file:', request.path)

    const content = request.isBase64
      ? Buffer.from(request.content, 'base64')
      : request.content

    await instance.files.write(request.path, content)
  }

  /**
   * List files in directory
   */
  async listFiles(request: FileListRequest): Promise<SandboxFile[]> {
    const managed = this.sandboxes.get(request.sessionId)

    if (!managed) {
      throw new Error(`Session not found: ${request.sessionId}`)
    }

    const { instance, session } = managed
    session.lastActivityAt = Date.now()

    this.log('Listing files:', request.path)

    const files = await instance.files.list(request.path)

    return files.map((f: { name: string; path: string; isDir: boolean; size?: number }) => ({
      name: f.name,
      path: f.path,
      isDirectory: f.isDir,
      size: f.size,
    }))
  }

  /**
   * Terminate a sandbox session
   */
  async terminateSession(sessionId: SandboxSessionId): Promise<void> {
    const managed = this.sandboxes.get(sessionId)

    if (!managed) {
      return // Already terminated
    }

    this.log('Terminating session:', sessionId)

    // Clear cleanup timer
    if (managed.cleanupTimer) {
      clearTimeout(managed.cleanupTimer)
    }

    // Kill the sandbox
    try {
      await managed.instance.kill()
    } catch (error) {
      this.log('Error killing sandbox:', error)
    }

    managed.session.state = 'terminated'
    this.sandboxes.delete(sessionId)
  }

  /**
   * Keep session alive
   */
  async keepAlive(sessionId: SandboxSessionId, timeoutMs?: number): Promise<void> {
    const managed = this.sandboxes.get(sessionId)

    if (!managed) {
      throw new Error(`Session not found: ${sessionId}`)
    }

    const { instance, session } = managed
    session.lastActivityAt = Date.now()

    this.log('Keeping session alive:', sessionId)

    // Reset timeout on the E2B sandbox
    await instance.setTimeout(timeoutMs || this.defaultTimeoutMs)

    // Reset cleanup timer
    if (managed.cleanupTimer) {
      clearTimeout(managed.cleanupTimer)
    }

    if (!session.config.keepAlive) {
      managed.cleanupTimer = setTimeout(() => {
        this.terminateSession(sessionId).catch(console.error)
      }, timeoutMs || this.defaultTimeoutMs)
    }
  }

  /**
   * Cleanup all sessions
   */
  async cleanup(): Promise<void> {
    this.log('Cleaning up all sessions')

    const sessionIds = Array.from(this.sandboxes.keys())
    await Promise.all(sessionIds.map(id => this.terminateSession(id)))
  }
}

// ============================================================================
// Singleton Instance
// ============================================================================

let sandboxService: E2BSandboxService | null = null

/**
 * Get the sandbox service singleton
 */
export function getSandboxService(config?: {
  apiKey?: string
  defaultTimeoutMs?: number
  debug?: boolean
}): E2BSandboxService {
  if (!sandboxService) {
    sandboxService = new E2BSandboxService(config)
  }
  return sandboxService
}
