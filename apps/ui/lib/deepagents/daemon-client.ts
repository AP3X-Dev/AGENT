import { spawn, type ChildProcessWithoutNullStreams } from 'child_process'
import fs from 'fs'
import path from 'path'

const DEBUG_DAEMON = process.env.DEBUG_DEEPAGENTS_DAEMON === '1'

export type DeepAgentsDaemonClientLike = {
  request: <T = any>(method: string, params?: Record<string, any>) => Promise<T>
  requestStream: (
    method: string,
    params: Record<string, any>,
    onEvent: (event: any) => void,
    onDone: () => void,
    onError: (err: Error) => void
  ) => string
  cancelStream: (id: string) => void
  clearCaches: () => Promise<{
    cleared_agents: number
    cleared_sessions: number
    cleared_interrupts: number
  }>
  listThreads: (
    agentName?: string,
    limit?: number
  ) => Promise<{
    threads: Array<{
      thread_id: string
      agent_name: string | null
      updated_at: string | null
      preview: string | null
    }>
  }>
  deleteThread: (threadId: string) => Promise<{ deleted: boolean; thread_id: string }>
  getThreadMessages: (
    threadId: string,
    limit?: number
  ) => Promise<{
    messages: Array<{ role: string; content: string; id: string }>
    thread_id: string
  }>
  killDaemon: () => void
}

type JsonRpcRequest = {
  id: string
  method: string
  params?: Record<string, any>
}

type JsonRpcResponse = {
  id: string
  ok: boolean
  result?: any
  event?: any
  error?: { message: string; type?: string; trace?: string }
}

type Pending = {
  resolve: (value: any) => void
  reject: (err: Error) => void
}

type StreamCallback = (event: any) => void

type StreamPending = {
  onEvent: StreamCallback
  onDone: () => void
  onError: (err: Error) => void
}

function resolveAg3ntBackendPath(env: Record<string, string>): string | null {
  const configured = env.AG3NT_BACKEND_PATH
  if (configured && fs.existsSync(configured)) return configured

  // Local dev default (user-requested).
  const defaultWin = 'C:\\Users\\Guerr\\Documents\\ag3nt'
  if (fs.existsSync(defaultWin)) return defaultWin

  return null
}

function resolveDaemonScriptPath(env: Record<string, string>): string {
  const backendPath = resolveAg3ntBackendPath(env)
  const scriptRelOrAbs = env.AG3NT_DAEMON_SCRIPT || path.join('python', 'deepagents_daemon.py')

  if (backendPath) {
    const candidate = path.isAbsolute(scriptRelOrAbs)
      ? scriptRelOrAbs
      : path.join(backendPath, scriptRelOrAbs)
    if (fs.existsSync(candidate)) return candidate
    // Return the configured/default candidate even if missing so errors are actionable.
    return candidate
  }

  // Fallback: legacy local daemon script in this repo (useful for development).
  const cwd = process.cwd()
  const direct = path.join(cwd, 'python', 'deepagents_daemon.py')
  if (fs.existsSync(direct)) return direct

  return direct
}

function resolvePythonCommand(env: Record<string, string>): string {
  if (env.AG3NT_PYTHON) return env.AG3NT_PYTHON
  if (env.PYTHON) return env.PYTHON

  const backendPath = resolveAg3ntBackendPath(env)
  if (backendPath) {
    const winVenv = path.join(backendPath, 'apps', 'agent', '.venv', 'Scripts', 'python.exe')
    if (fs.existsSync(winVenv)) return winVenv
    const posixVenv = path.join(backendPath, 'apps', 'agent', '.venv', 'bin', 'python')
    if (fs.existsSync(posixVenv)) return posixVenv
  }

  return 'python'
}

/**
 * Load environment variables from root .env file and merge with process.env
 * This ensures the daemon process has access to all required env vars
 */
function loadRootEnv(): Record<string, string> {
  const env: Record<string, string> = { ...process.env as Record<string, string> }
  const cwd = process.cwd()
  const ag3ntPath = resolveAg3ntBackendPath(env)

  // Try to find root .env file (parent of AP3X-UI or current directory)
  const envPaths = [
    path.join(cwd, '.env.local'),
    path.join(cwd, '.env'),
    ag3ntPath ? path.join(ag3ntPath, '.env') : null,
    path.join(cwd, '..', '.env'),
    path.join(cwd, 'AP3X-UI', '..', '.env'),
  ].filter((p): p is string => Boolean(p))

  for (const envPath of envPaths) {
    if (fs.existsSync(envPath)) {
      try {
        const content = fs.readFileSync(envPath, 'utf8')
        for (const line of content.split('\n')) {
          const trimmed = line.trim()
          if (!trimmed || trimmed.startsWith('#')) continue
          const eqIndex = trimmed.indexOf('=')
          if (eqIndex === -1) continue
          const key = trimmed.slice(0, eqIndex).trim()
          let value = trimmed.slice(eqIndex + 1).trim()
          // Remove surrounding quotes if present
          if ((value.startsWith('"') && value.endsWith('"')) ||
              (value.startsWith("'") && value.endsWith("'"))) {
            value = value.slice(1, -1)
          }
          // Only set if not already in process.env (don't override)
          if (!env[key]) {
            env[key] = value
          }
        }
        if (DEBUG_DAEMON) console.log('[deepagents-daemon] Loaded env from:', envPath)
        break
      } catch (e) {
        if (DEBUG_DAEMON) console.warn('[deepagents-daemon] Failed to load env from:', envPath, e)
      }
    }
  }

  return env
}

class DeepAgentsDaemonClient {
  private proc: ChildProcessWithoutNullStreams | null = null
  private buffer = ''
  private pending = new Map<string, Pending>()
  private streamPending = new Map<string, StreamPending>()
  private seq = 0
  private spawnPromise: Promise<void> | null = null

  // Buffer overflow protection
  private static readonly MAX_BUFFER_SIZE = 10 * 1024 * 1024 // 10MB

  /**
   * Ensure daemon is running. Uses a spawn lock to prevent race conditions
   * where multiple concurrent requests could spawn multiple daemons.
   */
  private async ensureRunning(): Promise<void> {
    // Fast path: already running
    if (this.proc && !this.proc.killed) return

    // If spawn already in progress, wait for it
    if (this.spawnPromise) {
      await this.spawnPromise
      return
    }

    // Start spawn and store promise for other callers to wait on
    this.spawnPromise = this.doSpawn()
    try {
      await this.spawnPromise
    } finally {
      this.spawnPromise = null
    }
  }

  /**
   * Actually spawn the daemon process. Called only from ensureRunning().
   */
  private doSpawn(): Promise<void> {
    return new Promise((resolve, reject) => {
      const env = loadRootEnv()
      const script = resolveDaemonScriptPath(env)
      const python = resolvePythonCommand(env)

      const ag3ntPath = resolveAg3ntBackendPath(env)
      const projectRoot = ag3ntPath || process.cwd()

      if (DEBUG_DAEMON) console.log('[deepagents-daemon] Starting daemon:', python, script, 'cwd:', projectRoot)

      this.proc = spawn(python, [script], {
        stdio: ['pipe', 'pipe', 'pipe'],
        env: env as NodeJS.ProcessEnv,
        cwd: projectRoot,
      })

      this.proc.stdout?.setEncoding('utf8')
      this.proc.stderr?.setEncoding('utf8')

      this.proc.stdout?.on('data', (chunk: string) => this.onStdout(chunk))
      this.proc.stderr?.on('data', (chunk: string) => {
        // Always log stderr to help debug daemon crashes
        console.error('[deepagents-daemon stderr]', chunk.trim())
      })

      // Set a startup timeout
      const startupTimeout = setTimeout(() => {
        if (this.proc && !this.proc.killed) {
          console.error('[deepagents-daemon] Startup timeout (5s)')
          this.proc.kill()
          reject(new Error('Daemon startup timeout'))
        }
      }, 5000)

      this.proc?.on('exit', (code) => {
        clearTimeout(startupTimeout)
        console.error('[deepagents-daemon] Process exited with code:', code)
        const err = new Error(`DeepAgents daemon exited (code=${code ?? 'unknown'})`)
        for (const [, p] of this.pending) p.reject(err)
        for (const [, p] of this.streamPending) p.onError(err)
        this.pending.clear()
        this.streamPending.clear()
        this.proc = null
      })

      // Consider spawned when we can write to stdin
      // Resolve immediately after spawn - actual readiness verified by first request
      clearTimeout(startupTimeout)
      resolve()
    })
  }

  private onStdout(chunk: string) {
    this.buffer += chunk

    // Buffer overflow protection: truncate oldest data if buffer too large
    if (this.buffer.length > DeepAgentsDaemonClient.MAX_BUFFER_SIZE) {
      console.warn('[deepagents-daemon] Buffer overflow, truncating oldest data')
      const newlineIdx = this.buffer.indexOf('\n', this.buffer.length - DeepAgentsDaemonClient.MAX_BUFFER_SIZE)
      this.buffer = newlineIdx >= 0 ? this.buffer.slice(newlineIdx + 1) : ''
    }

    while (true) {
      const idx = this.buffer.indexOf('\n')
      if (idx === -1) return
      const line = this.buffer.slice(0, idx).trim()
      this.buffer = this.buffer.slice(idx + 1)
      if (!line) continue

      let msg: JsonRpcResponse
      try {
        msg = JSON.parse(line)
      } catch {
        if (DEBUG_DAEMON) console.warn('[deepagents-daemon] Could not parse line:', line)
        continue
      }

      const msgId = String(msg.id)

      // Check if this is a streaming response
      const streamHandler = this.streamPending.get(msgId)
      if (streamHandler) {
        if (!msg.ok) {
          const errorMsg = msg.error?.message || 'DeepAgents daemon error'
          streamHandler.onError(new Error(errorMsg))
          this.streamPending.delete(msgId)
          continue
        }
        if (msg.event) {
          streamHandler.onEvent(msg.event)
          // Check if this is the final "done" event
          if (msg.event.type === 'done') {
            streamHandler.onDone()
            this.streamPending.delete(msgId)
          }
        }
        continue
      }

      // Regular request/response handling
      const pending = this.pending.get(msgId)
      if (!pending) continue
      this.pending.delete(msgId)

      if (msg.ok) {
        pending.resolve(msg.result)
      } else {
        const errorMsg = msg.error?.message || 'DeepAgents daemon error'
        if (msg.error?.trace) {
          if (DEBUG_DAEMON) console.error('[deepagents-daemon] Error with trace:\n', msg.error.trace)
        }
        pending.reject(new Error(errorMsg))
      }
    }
  }

  async request<T = any>(method: string, params: Record<string, any> = {}): Promise<T> {
    await this.ensureRunning()
    const id = String(++this.seq)
    const req: JsonRpcRequest = { id, method, params }

    const payload = JSON.stringify(req) + '\n'
    const proc = this.proc
    if (!proc) throw new Error('DeepAgents daemon not running')

    const result = await new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      proc.stdin.write(payload, 'utf8')
    })

    return result
  }

  /**
   * Start a streaming request. Returns an ID that can be used to stop the stream.
   * The onEvent callback is called for each event from the daemon.
   * Note: This starts the stream asynchronously - errors during spawn are delivered via onError.
   */
  requestStream(
    method: string,
    params: Record<string, any>,
    onEvent: StreamCallback,
    onDone: () => void,
    onError: (err: Error) => void
  ): string {
    const id = String(++this.seq)

    // Start async spawn, then send request
    this.ensureRunning()
      .then(() => {
        const req: JsonRpcRequest = { id, method, params }
        const payload = JSON.stringify(req) + '\n'
        const proc = this.proc
        if (!proc) {
          onError(new Error('DeepAgents daemon not running'))
          return
        }
        this.streamPending.set(id, { onEvent, onDone, onError })
        proc.stdin.write(payload, 'utf8')
      })
      .catch((err) => {
        onError(err)
      })

    return id
  }

  /**
   * Cancel a streaming request and notify the daemon.
   */
  cancelStream(id: string): void {
    const handler = this.streamPending.get(id)
    if (handler) {
      this.streamPending.delete(id)
      // Send cancel request to daemon
      if (this.proc && !this.proc.killed) {
        const cancelReq = JSON.stringify({
          id: `cancel-${id}`,
          method: 'cancel_stream',
          params: { stream_id: id }
        }) + '\n'
        this.proc.stdin.write(cancelReq, 'utf8')
      }
    }
  }

  /**
   * Clear all agent and session caches in the daemon.
   * Call this to force fresh model creation on next request.
   */
  async clearCaches(): Promise<{ cleared_agents: number; cleared_sessions: number; cleared_interrupts: number }> {
    return this.request('clear_caches', {})
  }

  /**
   * List all threads (conversations) stored in the database.
   */
  async listThreads(agentName?: string, limit: number = 50): Promise<{
    threads: Array<{
      thread_id: string
      agent_name: string | null
      updated_at: string | null
      preview: string | null
    }>
  }> {
    return this.request('list_threads', { agent_name: agentName, limit })
  }

  /**
   * Delete a thread and its checkpoints.
   */
  async deleteThread(threadId: string): Promise<{ deleted: boolean; thread_id: string }> {
    return this.request('delete_thread', { thread_id: threadId })
  }

  /**
   * Get messages from a thread for resumption.
   */
  async getThreadMessages(threadId: string, limit: number = 50): Promise<{
    messages: Array<{ role: string; content: string; id: string }>
    thread_id: string
  }> {
    return this.request('get_thread_messages', { thread_id: threadId, limit })
  }

  /**
   * Kill the daemon process. It will be restarted on next request.
   */
  killDaemon() {
    if (this.proc && !this.proc.killed) {
      if (DEBUG_DAEMON) console.log('[deepagents-daemon] Killing daemon process')
      this.proc.kill()
      this.proc = null
      this.pending.clear()
      this.streamPending.clear()
      this.buffer = ''
    }
  }
}

declare global {
  // eslint-disable-next-line no-var
  var __deepAgentsDaemonClient: DeepAgentsDaemonClientLike | undefined
}

export function getDeepAgentsDaemonClient(): DeepAgentsDaemonClientLike {
  const g = globalThis as any
  if (!g.__deepAgentsDaemonClient) {
    g.__deepAgentsDaemonClient = new DeepAgentsDaemonClient()
  }
  return g.__deepAgentsDaemonClient as DeepAgentsDaemonClientLike
}
