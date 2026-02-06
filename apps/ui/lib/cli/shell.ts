/**
 * Shell Execution Service
 * Client-side service for executing shell commands
 */

import type { ShellExecuteRequest, ShellExecuteResponse } from '@/types/cli'

const API_BASE = '/api/cli/shell'

/**
 * Execute a shell command
 */
export async function executeCommand(request: ShellExecuteRequest): Promise<ShellExecuteResponse> {
  try {
    const response = await fetch(API_BASE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        command: request.command,
        cwd: request.cwd,
        timeout: request.timeout,
      }),
    })
    const data = await response.json()
    return data
  } catch (error: any) {
    return {
      success: false,
      output: '',
      exitCode: 1,
      error: error.message || 'Failed to execute command',
    }
  }
}

/**
 * Check if input starts with bash command prefix
 */
export function isBashCommand(input: string): boolean {
  return input.trim().startsWith('!')
}

/**
 * Extract command from bash input (removes ! prefix)
 */
export function extractBashCommand(input: string): string {
  const trimmed = input.trim()
  if (trimmed.startsWith('!')) {
    return trimmed.substring(1).trim()
  }
  return trimmed
}

/**
 * Common shell commands for autocomplete
 */
export const COMMON_COMMANDS = [
  { command: 'ls', description: 'List directory contents' },
  { command: 'cd', description: 'Change directory' },
  { command: 'pwd', description: 'Print working directory' },
  { command: 'cat', description: 'Display file contents' },
  { command: 'grep', description: 'Search text patterns' },
  { command: 'find', description: 'Search for files' },
  { command: 'mkdir', description: 'Create directory' },
  { command: 'rm', description: 'Remove files' },
  { command: 'cp', description: 'Copy files' },
  { command: 'mv', description: 'Move files' },
  { command: 'echo', description: 'Display text' },
  { command: 'git', description: 'Git version control' },
  { command: 'npm', description: 'Node package manager' },
  { command: 'pnpm', description: 'Fast package manager' },
  { command: 'yarn', description: 'Yarn package manager' },
  { command: 'node', description: 'Run Node.js' },
  { command: 'python', description: 'Run Python' },
  { command: 'pip', description: 'Python package manager' },
]

/**
 * Format command output for display
 */
export function formatCommandOutput(response: ShellExecuteResponse): string {
  let output = response.output

  // Add execution time if available
  if (response.executionTime !== undefined) {
    output += `\n\n⏱️ Executed in ${response.executionTime}ms`
  }

  return output
}

/**
 * Parse command output for syntax highlighting
 * Returns an array of segments with their types
 */
export interface OutputSegment {
  text: string
  type: 'normal' | 'error' | 'warning' | 'success' | 'info'
}

export function parseCommandOutput(output: string): OutputSegment[] {
  const lines = output.split('\n')
  const segments: OutputSegment[] = []

  for (const line of lines) {
    let type: OutputSegment['type'] = 'normal'

    if (line.startsWith('[stderr]')) {
      type = 'error'
    } else if (line.toLowerCase().includes('error') || line.toLowerCase().includes('failed')) {
      type = 'error'
    } else if (line.toLowerCase().includes('warning') || line.toLowerCase().includes('warn')) {
      type = 'warning'
    } else if (line.toLowerCase().includes('success') || line.toLowerCase().includes('done')) {
      type = 'success'
    } else if (line.startsWith('⏱️') || line.startsWith('Exit code:')) {
      type = 'info'
    }

    segments.push({ text: line, type })
  }

  return segments
}

