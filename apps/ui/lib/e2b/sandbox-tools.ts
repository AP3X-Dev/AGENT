/**
 * E2B Sandbox Tools
 *
 * Agent-facing tools for sandbox code execution.
 * These tools allow the agent to write and execute arbitrary code
 * in secure isolated sandboxes for complex tasks.
 */

import { getSandboxService, E2BSandboxService } from './sandbox-service'
import type {
  SandboxSessionId,
  SandboxLanguage,
  CodeExecutionRequest,
  CodeExecutionResponse,
  SandboxTool,
  SandboxSession,
  SandboxFile,
} from '@/types/e2b-sandbox'

// ============================================================================
// Tool Definitions (for LLM/Agent consumption)
// ============================================================================

/**
 * Get sandbox tool definitions for LLM function calling
 */
export function getSandboxToolDefinitions(): Array<{
  name: string
  description: string
  parameters: Record<string, unknown>
}> {
  return [
    {
      name: 'execute_code',
      description: `Execute Python, JavaScript, or TypeScript code in a secure isolated sandbox.
Use this tool when you need to:
- Process data (CSV, JSON, etc.)
- Perform calculations or data analysis
- Generate charts or visualizations
- Manipulate images (resize, crop, analyze)
- Run scripts that require external libraries
- Test code snippets
- Perform file operations

The sandbox has access to common libraries like pandas, numpy, matplotlib, pillow, requests, etc.
You can install additional packages using the install_packages tool.
State persists between executions in the same session.`,
      parameters: {
        type: 'object',
        properties: {
          code: {
            type: 'string',
            description: 'The code to execute. Can be Python, JavaScript, or TypeScript.',
          },
          language: {
            type: 'string',
            enum: ['python', 'javascript', 'typescript', 'js', 'ts'],
            description: 'Programming language. Defaults to python.',
          },
          session_id: {
            type: 'string',
            description: 'Session ID to reuse. Omit to create a new session.',
          },
          description: {
            type: 'string',
            description: 'Brief description of what the code does (for logging).',
          },
        },
        required: ['code'],
      },
    },
    {
      name: 'install_packages',
      description: `Install Python (pip) or JavaScript (npm) packages in the sandbox.
Use this before running code that requires external libraries not pre-installed.`,
      parameters: {
        type: 'object',
        properties: {
          packages: {
            type: 'array',
            items: { type: 'string' },
            description: 'List of packages to install (e.g., ["pillow", "requests"])',
          },
          session_id: {
            type: 'string',
            description: 'Session ID. Required.',
          },
          manager: {
            type: 'string',
            enum: ['pip', 'npm'],
            description: 'Package manager to use. Defaults to pip.',
          },
        },
        required: ['packages', 'session_id'],
      },
    },
    {
      name: 'upload_file',
      description: `Upload a file to the sandbox for processing.
Use this to provide data files, images, or other content for code to process.`,
      parameters: {
        type: 'object',
        properties: {
          session_id: {
            type: 'string',
            description: 'Session ID. Required.',
          },
          path: {
            type: 'string',
            description: 'Path in sandbox where file should be saved (e.g., "/home/user/data.csv")',
          },
          content: {
            type: 'string',
            description: 'File content. For binary files, use base64 encoding.',
          },
          is_base64: {
            type: 'boolean',
            description: 'Set to true if content is base64 encoded.',
          },
        },
        required: ['session_id', 'path', 'content'],
      },
    },
    {
      name: 'download_file',
      description: `Download a file from the sandbox.
Use this to retrieve results, generated images, processed data, etc.`,
      parameters: {
        type: 'object',
        properties: {
          session_id: {
            type: 'string',
            description: 'Session ID. Required.',
          },
          path: {
            type: 'string',
            description: 'Path of file to download from sandbox.',
          },
          as_base64: {
            type: 'boolean',
            description: 'Set to true for binary files (images, etc.).',
          },
        },
        required: ['session_id', 'path'],
      },
    },
    {
      name: 'list_files',
      description: `List files in a sandbox directory.`,
      parameters: {
        type: 'object',
        properties: {
          session_id: {
            type: 'string',
            description: 'Session ID. Required.',
          },
          path: {
            type: 'string',
            description: 'Directory path to list. Defaults to /home/user.',
          },
        },
        required: ['session_id'],
      },
    },
    {
      name: 'run_command',
      description: `Run a shell command in the sandbox.
Use for system operations, installing system packages, etc.`,
      parameters: {
        type: 'object',
        properties: {
          session_id: {
            type: 'string',
            description: 'Session ID. Required.',
          },
          command: {
            type: 'string',
            description: 'Shell command to execute.',
          },
        },
        required: ['session_id', 'command'],
      },
    },
  ]
}

// ============================================================================
// Tool Handlers
// ============================================================================

interface ExecuteCodeInput {
  code: string
  language?: SandboxLanguage
  session_id?: string
  description?: string
}

interface InstallPackagesInput {
  packages: string[]
  session_id: string
  manager?: 'pip' | 'npm'
}

interface UploadFileInput {
  session_id: string
  path: string
  content: string
  is_base64?: boolean
}

interface DownloadFileInput {
  session_id: string
  path: string
  as_base64?: boolean
}

interface ListFilesInput {
  session_id: string
  path?: string
}

interface RunCommandInput {
  session_id: string
  command: string
}

/**
 * Create sandbox tools with handlers
 */
export function createSandboxTools(config?: {
  apiKey?: string
  debug?: boolean
}): Map<string, SandboxTool> {
  const service = getSandboxService(config)
  const tools = new Map<string, SandboxTool>()

  // Execute Code Tool
  tools.set('execute_code', {
    name: 'execute_code',
    description: 'Execute code in a secure sandbox',
    inputSchema: getSandboxToolDefinitions().find(t => t.name === 'execute_code')!.parameters,
    handler: async (input: unknown): Promise<CodeExecutionResponse> => {
      const params = input as ExecuteCodeInput
      return service.executeCode({
        code: params.code,
        language: params.language,
        sessionId: params.session_id,
        description: params.description,
      })
    },
  })

  // Install Packages Tool
  tools.set('install_packages', {
    name: 'install_packages',
    description: 'Install packages in sandbox',
    inputSchema: getSandboxToolDefinitions().find(t => t.name === 'install_packages')!.parameters,
    handler: async (input: unknown) => {
      const params = input as InstallPackagesInput
      return service.installPackages({
        sessionId: params.session_id,
        packages: params.packages,
        manager: params.manager,
      })
    },
  })

  // Upload File Tool
  tools.set('upload_file', {
    name: 'upload_file',
    description: 'Upload file to sandbox',
    inputSchema: getSandboxToolDefinitions().find(t => t.name === 'upload_file')!.parameters,
    handler: async (input: unknown) => {
      const params = input as UploadFileInput
      await service.writeFile({
        sessionId: params.session_id,
        path: params.path,
        content: params.content,
        isBase64: params.is_base64,
      })
      return { success: true, path: params.path }
    },
  })

  // Download File Tool
  tools.set('download_file', {
    name: 'download_file',
    description: 'Download file from sandbox',
    inputSchema: getSandboxToolDefinitions().find(t => t.name === 'download_file')!.parameters,
    handler: async (input: unknown) => {
      const params = input as DownloadFileInput
      return service.readFile({
        sessionId: params.session_id,
        path: params.path,
        asBase64: params.as_base64,
      })
    },
  })

  // List Files Tool
  tools.set('list_files', {
    name: 'list_files',
    description: 'List files in sandbox directory',
    inputSchema: getSandboxToolDefinitions().find(t => t.name === 'list_files')!.parameters,
    handler: async (input: unknown): Promise<SandboxFile[]> => {
      const params = input as ListFilesInput
      return service.listFiles({
        sessionId: params.session_id,
        path: params.path || '/home/user',
      })
    },
  })

  // Run Command Tool
  tools.set('run_command', {
    name: 'run_command',
    description: 'Run shell command in sandbox',
    inputSchema: getSandboxToolDefinitions().find(t => t.name === 'run_command')!.parameters,
    handler: async (input: unknown) => {
      const params = input as RunCommandInput
      return service.runCommand({
        sessionId: params.session_id,
        command: params.command,
      })
    },
  })

  return tools
}

// ============================================================================
// Convenience Functions
// ============================================================================

/**
 * Execute a tool by name
 */
export async function executeSandboxTool(
  toolName: string,
  input: unknown,
  config?: { apiKey?: string; debug?: boolean }
): Promise<unknown> {
  const tools = createSandboxTools(config)
  const tool = tools.get(toolName)

  if (!tool) {
    throw new Error(`Unknown sandbox tool: ${toolName}`)
  }

  return tool.handler(input)
}

/**
 * Quick code execution helper
 */
export async function executeCode(
  code: string,
  options?: {
    language?: SandboxLanguage
    sessionId?: string
    description?: string
    apiKey?: string
  }
): Promise<CodeExecutionResponse> {
  const service = getSandboxService({ apiKey: options?.apiKey })
  return service.executeCode({
    code,
    language: options?.language,
    sessionId: options?.sessionId,
    description: options?.description,
  })
}

/**
 * Get or create a sandbox session
 */
export async function getOrCreateSession(
  sessionId?: string,
  config?: { apiKey?: string; keepAlive?: boolean }
): Promise<SandboxSession> {
  const service = getSandboxService({ apiKey: config?.apiKey })

  if (sessionId) {
    const existing = await service.getSession(sessionId)
    if (existing) return existing
  }

  return service.createSession({ keepAlive: config?.keepAlive })
}
