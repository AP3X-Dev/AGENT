/**
 * File Operations Service
 * Client-side service for file read/write/edit operations
 */

import type {
  FileReadRequest,
  FileReadResponse,
  FileWriteRequest,
  FileWriteResponse,
  FileEditRequest,
  FileEditResponse,
  FileInfo,
} from '@/types/cli'

const API_BASE = '/api/cli/files'

/**
 * Read a file's contents
 */
export async function readFile(request: FileReadRequest): Promise<FileReadResponse> {
  const params = new URLSearchParams({ path: request.path })
  
  if (request.startLine !== undefined) {
    params.set('startLine', request.startLine.toString())
  }
  if (request.endLine !== undefined) {
    params.set('endLine', request.endLine.toString())
  }

  try {
    const response = await fetch(`${API_BASE}?${params}`)
    const data = await response.json()
    return data
  } catch (error: any) {
    return {
      success: false,
      error: error.message || 'Failed to read file',
      path: request.path,
    }
  }
}

/**
 * Write content to a file
 */
export async function writeFile(request: FileWriteRequest): Promise<FileWriteResponse> {
  try {
    const response = await fetch(API_BASE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'write',
        path: request.path,
        content: request.content,
        createDirectories: request.createDirectories ?? true,
      }),
    })
    const data = await response.json()
    return data
  } catch (error: any) {
    return {
      success: false,
      error: error.message || 'Failed to write file',
      path: request.path,
    }
  }
}

/**
 * Edit a file by replacing text
 */
export async function editFile(request: FileEditRequest): Promise<FileEditResponse> {
  try {
    const response = await fetch(API_BASE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'edit',
        path: request.path,
        oldString: request.oldString,
        newString: request.newString,
        replaceAll: request.replaceAll ?? false,
      }),
    })
    const data = await response.json()
    return data
  } catch (error: any) {
    return {
      success: false,
      error: error.message || 'Failed to edit file',
      path: request.path,
    }
  }
}

/**
 * List files in a directory
 */
export async function listDirectory(dirPath: string): Promise<{ success: boolean; items?: FileInfo[]; error?: string }> {
  const params = new URLSearchParams({
    path: dirPath,
    action: 'list',
  })

  try {
    const response = await fetch(`${API_BASE}?${params}`)
    const data = await response.json()
    return data
  } catch (error: any) {
    return {
      success: false,
      error: error.message || 'Failed to list directory',
    }
  }
}

/**
 * Check if a file exists
 */
export async function fileExists(filePath: string): Promise<boolean> {
  const result = await readFile({ path: filePath })
  return result.success
}

/**
 * Get file extension language mapping for syntax highlighting
 */
export function getLanguageFromPath(filePath: string): string {
  const ext = filePath.split('.').pop()?.toLowerCase() || ''
  const languageMap: Record<string, string> = {
    ts: 'typescript',
    tsx: 'typescript',
    js: 'javascript',
    jsx: 'javascript',
    json: 'json',
    md: 'markdown',
    css: 'css',
    scss: 'scss',
    html: 'html',
    py: 'python',
    rs: 'rust',
    go: 'go',
    java: 'java',
    c: 'c',
    cpp: 'cpp',
    h: 'c',
    sh: 'bash',
    yaml: 'yaml',
    yml: 'yaml',
    sql: 'sql',
    graphql: 'graphql',
  }
  return languageMap[ext] || 'plaintext'
}

