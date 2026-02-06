/**
 * E2B Sandbox Types
 * 
 * Type definitions for E2B sandbox code execution.
 * This provides the agent with the ability to write and execute
 * arbitrary code in secure isolated sandboxes.
 */

// ============================================================================
// Sandbox Session Types
// ============================================================================

/**
 * Unique identifier for a sandbox session
 */
export type SandboxSessionId = string

/**
 * Supported programming languages in the sandbox
 */
export type SandboxLanguage = 'python' | 'javascript' | 'typescript' | 'js' | 'ts'

/**
 * Sandbox session state
 */
export type SandboxState = 'creating' | 'ready' | 'executing' | 'idle' | 'error' | 'terminated'

/**
 * Sandbox session configuration
 */
export interface SandboxConfig {
  /** Session timeout in milliseconds (default: 5 minutes) */
  timeoutMs?: number
  /** Custom template name (optional) */
  template?: string
  /** Environment variables to set */
  envVars?: Record<string, string>
  /** Whether to keep session alive between executions */
  keepAlive?: boolean
}

/**
 * Sandbox session metadata
 */
export interface SandboxSession {
  /** Unique session identifier */
  id: SandboxSessionId
  /** Current session state */
  state: SandboxState
  /** Session creation timestamp */
  createdAt: number
  /** Last activity timestamp */
  lastActivityAt: number
  /** Session configuration */
  config: SandboxConfig
  /** Execution count in this session */
  executionCount: number
  /** Installed packages in this session */
  installedPackages: string[]
}

// ============================================================================
// Code Execution Types
// ============================================================================

/**
 * Code execution request
 */
export interface CodeExecutionRequest {
  /** The code to execute */
  code: string
  /** Programming language (default: python) */
  language?: SandboxLanguage
  /** Session ID to reuse (optional - creates new if not provided) */
  sessionId?: SandboxSessionId
  /** Execution timeout in milliseconds */
  timeoutMs?: number
  /** Environment variables for this execution */
  envVars?: Record<string, string>
  /** Description of what the code does (for logging) */
  description?: string
  /** Files to upload before execution */
  files?: FileUploadRequest[]
}

/**
 * File upload request
 */
export interface FileUploadRequest {
  /** Path in the sandbox */
  path: string
  /** File content (string or base64 for binary) */
  content: string
  /** Whether content is base64 encoded */
  isBase64?: boolean
}

/**
 * Output message from code execution
 */
export interface OutputMessage {
  /** Message type */
  type: 'stdout' | 'stderr'
  /** Message content */
  content: string
  /** Timestamp */
  timestamp: number
}

/**
 * Execution result item
 */
export interface ExecutionResult {
  /** Result type */
  type: 'text' | 'image' | 'html' | 'json' | 'error'
  /** Text representation */
  text?: string
  /** PNG image data (base64) */
  png?: string
  /** JPEG image data (base64) */
  jpeg?: string
  /** HTML content */
  html?: string
  /** JSON data */
  json?: unknown
  /** SVG content */
  svg?: string
  /** Raw value */
  value?: unknown
}

/**
 * Execution error details
 */
export interface ExecutionError {
  /** Error name/type */
  name: string
  /** Error message */
  message: string
  /** Stack trace */
  traceback?: string
}

/**
 * Complete code execution response
 */
export interface CodeExecutionResponse {
  /** Whether execution was successful */
  success: boolean
  /** Session ID used for execution */
  sessionId: SandboxSessionId
  /** Execution count in session */
  executionCount: number
  /** Execution results */
  results: ExecutionResult[]
  /** Stdout logs */
  stdout: OutputMessage[]
  /** Stderr logs */
  stderr: OutputMessage[]
  /** Execution error (if any) */
  error?: ExecutionError
  /** Execution duration in milliseconds */
  durationMs: number
  /** Files created during execution */
  filesCreated?: string[]
}

// ============================================================================
// File Operations Types
// ============================================================================

/**
 * File info in sandbox
 */
export interface SandboxFile {
  /** File name */
  name: string
  /** Full path */
  path: string
  /** Whether it's a directory */
  isDirectory: boolean
  /** File size in bytes (for files) */
  size?: number
}

/**
 * File read request
 */
export interface FileReadRequest {
  /** Session ID */
  sessionId: SandboxSessionId
  /** File path in sandbox */
  path: string
  /** Whether to return as base64 (for binary files) */
  asBase64?: boolean
}

/**
 * File read response
 */
export interface FileReadResponse {
  /** File content */
  content: string
  /** Whether content is base64 encoded */
  isBase64: boolean
  /** File path */
  path: string
}

/**
 * File write request
 */
export interface FileWriteRequest {
  /** Session ID */
  sessionId: SandboxSessionId
  /** File path in sandbox */
  path: string
  /** File content */
  content: string
  /** Whether content is base64 encoded */
  isBase64?: boolean
}

/**
 * File list request
 */
export interface FileListRequest {
  /** Session ID */
  sessionId: SandboxSessionId
  /** Directory path to list */
  path: string
}

// ============================================================================
// Command Execution Types
// ============================================================================

/**
 * Shell command execution request
 */
export interface CommandExecutionRequest {
  /** Session ID */
  sessionId: SandboxSessionId
  /** Command to execute */
  command: string
  /** Working directory (optional) */
  cwd?: string
  /** Timeout in milliseconds */
  timeoutMs?: number
}

/**
 * Shell command execution response
 */
export interface CommandExecutionResponse {
  /** Exit code */
  exitCode: number
  /** Standard output */
  stdout: string
  /** Standard error */
  stderr: string
  /** Execution duration in milliseconds */
  durationMs: number
}

// ============================================================================
// Package Management Types
// ============================================================================

/**
 * Package installation request
 */
export interface PackageInstallRequest {
  /** Session ID */
  sessionId: SandboxSessionId
  /** Packages to install */
  packages: string[]
  /** Package manager to use */
  manager?: 'pip' | 'npm'
}

/**
 * Package installation response
 */
export interface PackageInstallResponse {
  /** Whether installation was successful */
  success: boolean
  /** Installed packages */
  installed: string[]
  /** Failed packages */
  failed: string[]
  /** Installation output */
  output: string
}

// ============================================================================
// Agent Tool Types
// ============================================================================

/**
 * Sandbox tool definition for agent use
 */
export interface SandboxTool {
  /** Tool name */
  name: string
  /** Tool description */
  description: string
  /** Input schema */
  inputSchema: Record<string, unknown>
  /** Tool handler */
  handler: (input: unknown) => Promise<unknown>
}

/**
 * Sandbox service interface
 */
export interface ISandboxService {
  /** Create a new sandbox session */
  createSession(config?: SandboxConfig): Promise<SandboxSession>
  /** Get an existing session */
  getSession(sessionId: SandboxSessionId): Promise<SandboxSession | null>
  /** List active sessions */
  listSessions(): Promise<SandboxSession[]>
  /** Execute code in sandbox */
  executeCode(request: CodeExecutionRequest): Promise<CodeExecutionResponse>
  /** Run shell command */
  runCommand(request: CommandExecutionRequest): Promise<CommandExecutionResponse>
  /** Install packages */
  installPackages(request: PackageInstallRequest): Promise<PackageInstallResponse>
  /** Read file from sandbox */
  readFile(request: FileReadRequest): Promise<FileReadResponse>
  /** Write file to sandbox */
  writeFile(request: FileWriteRequest): Promise<void>
  /** List files in directory */
  listFiles(request: FileListRequest): Promise<SandboxFile[]>
  /** Terminate a session */
  terminateSession(sessionId: SandboxSessionId): Promise<void>
  /** Keep session alive */
  keepAlive(sessionId: SandboxSessionId, timeoutMs?: number): Promise<void>
}

