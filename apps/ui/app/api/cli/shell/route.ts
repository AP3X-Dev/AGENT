/**
 * Shell Execution API Route
 * Handles bash/shell command execution
 */

import { NextRequest, NextResponse } from 'next/server'
import { exec } from 'child_process'
import { promisify } from 'util'
import path from 'path'

const execAsync = promisify(exec)

// Configuration
const DEFAULT_TIMEOUT = 120000 // 120 seconds
const MAX_OUTPUT_BYTES = 100000 // 100KB

// Get workspace root
const getWorkspaceRoot = () => process.cwd()

// Security: Validate command (basic checks)
function isCommandAllowed(command: string): boolean {
  // Block obviously dangerous commands
  const blockedPatterns = [
    /rm\s+-rf\s+\//, // rm -rf /
    /mkfs/, // format commands
    /dd\s+if=.*of=\/dev/, // disk operations
    /:(){ :\|:& };:/, // fork bomb
  ]

  return !blockedPatterns.some(pattern => pattern.test(command))
}

export async function POST(request: NextRequest) {
  const startTime = Date.now()

  try {
    const body = await request.json()
    const { command, cwd, timeout = DEFAULT_TIMEOUT } = body

    if (!command || typeof command !== 'string') {
      return NextResponse.json({
        success: false,
        output: '',
        exitCode: 1,
        error: 'Command is required and must be a string',
      }, { status: 400 })
    }

    // Security check
    if (!isCommandAllowed(command)) {
      return NextResponse.json({
        success: false,
        output: '',
        exitCode: 1,
        error: 'Command blocked for security reasons',
      }, { status: 403 })
    }

    // Determine working directory
    const workspaceRoot = getWorkspaceRoot()
    let workingDir = workspaceRoot

    if (cwd) {
      const resolvedCwd = path.isAbsolute(cwd) ? cwd : path.resolve(workspaceRoot, cwd)
      // Security: Ensure cwd is within workspace
      if (resolvedCwd.startsWith(workspaceRoot)) {
        workingDir = resolvedCwd
      }
    }

    try {
      const { stdout, stderr } = await execAsync(command, {
        cwd: workingDir,
        timeout: Math.min(timeout, DEFAULT_TIMEOUT),
        maxBuffer: MAX_OUTPUT_BYTES,
        env: {
          ...process.env,
          // Add any additional env vars here
        },
      })

      // Combine output
      let output = stdout || ''
      if (stderr) {
        const stderrLines = stderr.trim().split('\n')
        for (const line of stderrLines) {
          output += `\n[stderr] ${line}`
        }
      }

      if (!output.trim()) {
        output = '<no output>'
      }

      // Truncate if necessary
      if (output.length > MAX_OUTPUT_BYTES) {
        output = output.substring(0, MAX_OUTPUT_BYTES)
        output += `\n\n... Output truncated at ${MAX_OUTPUT_BYTES} bytes.`
      }

      return NextResponse.json({
        success: true,
        output: output.trim(),
        exitCode: 0,
        executionTime: Date.now() - startTime,
      })
    } catch (error: any) {
      // Command failed (non-zero exit code)
      let output = ''
      let exitCode = 1

      if (error.killed) {
        output = `Error: Command timed out after ${timeout / 1000} seconds.`
      } else {
        output = error.stdout || ''
        if (error.stderr) {
          const stderrLines = error.stderr.trim().split('\n')
          for (const line of stderrLines) {
            output += `\n[stderr] ${line}`
          }
        }
        if (!output.trim()) {
          output = error.message || 'Command failed'
        }
        exitCode = error.code || 1
      }

      // Truncate if necessary
      if (output.length > MAX_OUTPUT_BYTES) {
        output = output.substring(0, MAX_OUTPUT_BYTES)
        output += `\n\n... Output truncated at ${MAX_OUTPUT_BYTES} bytes.`
      }

      return NextResponse.json({
        success: false,
        output: `${output.trim()}\n\nExit code: ${exitCode}`,
        exitCode,
        executionTime: Date.now() - startTime,
      })
    }
  } catch (error: any) {
    return NextResponse.json({
      success: false,
      output: '',
      exitCode: 1,
      error: error.message || 'Failed to execute command',
    }, { status: 500 })
  }
}

