/**
 * File Operations API Route
 * Handles file reading, writing, editing, and listing
 */

import { NextRequest, NextResponse } from 'next/server'
import { promises as fs } from 'fs'
import path from 'path'

// Get workspace root (current working directory or configurable)
const getWorkspaceRoot = () => process.cwd()

// Security: Ensure path is within workspace
function isPathSafe(filePath: string, workspaceRoot: string): boolean {
  const resolvedPath = path.resolve(workspaceRoot, filePath)
  return resolvedPath.startsWith(workspaceRoot)
}

// GET: Read file or list directory
export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams
  const filePath = searchParams.get('path')
  const action = searchParams.get('action') || 'read'
  const startLine = parseInt(searchParams.get('startLine') || '0')
  const endLine = parseInt(searchParams.get('endLine') || '-1')

  if (!filePath) {
    return NextResponse.json({ success: false, error: 'Path is required' }, { status: 400 })
  }

  const workspaceRoot = getWorkspaceRoot()
  const absolutePath = path.isAbsolute(filePath) ? filePath : path.resolve(workspaceRoot, filePath)

  if (!isPathSafe(absolutePath, workspaceRoot)) {
    return NextResponse.json({ success: false, error: 'Path outside workspace' }, { status: 403 })
  }

  try {
    if (action === 'list') {
      const stats = await fs.stat(absolutePath)
      if (!stats.isDirectory()) {
        return NextResponse.json({ success: false, error: 'Not a directory' }, { status: 400 })
      }

      const entries = await fs.readdir(absolutePath, { withFileTypes: true })
      const items = entries.map(entry => ({
        name: entry.name,
        path: path.join(filePath, entry.name),
        isDirectory: entry.isDirectory(),
      }))

      return NextResponse.json({ success: true, items, path: filePath })
    }

    // Read file
    const content = await fs.readFile(absolutePath, 'utf-8')
    const lines = content.split('\n')
    const totalLines = lines.length

    let resultContent = content
    if (startLine > 0 || endLine > 0) {
      const start = Math.max(0, startLine - 1)
      const end = endLine > 0 ? endLine : lines.length
      resultContent = lines.slice(start, end).join('\n')
    }

    return NextResponse.json({
      success: true,
      content: resultContent,
      path: filePath,
      lineCount: totalLines,
      startLine: startLine > 0 ? startLine : 1,
      endLine: endLine > 0 ? endLine : totalLines,
    })
  } catch (error: any) {
    if (error.code === 'ENOENT') {
      return NextResponse.json({ success: false, error: 'File not found', path: filePath }, { status: 404 })
    }
    return NextResponse.json({ success: false, error: error.message, path: filePath }, { status: 500 })
  }
}

// POST: Write or edit file
export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { action, path: filePath, content, oldString, newString, replaceAll, createDirectories } = body

    if (!filePath) {
      return NextResponse.json({ success: false, error: 'Path is required' }, { status: 400 })
    }

    const workspaceRoot = getWorkspaceRoot()
    const absolutePath = path.isAbsolute(filePath) ? filePath : path.resolve(workspaceRoot, filePath)

    if (!isPathSafe(absolutePath, workspaceRoot)) {
      return NextResponse.json({ success: false, error: 'Path outside workspace' }, { status: 403 })
    }

    if (action === 'write') {
      if (content === undefined) {
        return NextResponse.json({ success: false, error: 'Content is required' }, { status: 400 })
      }

      if (createDirectories) {
        await fs.mkdir(path.dirname(absolutePath), { recursive: true })
      }

      await fs.writeFile(absolutePath, content, 'utf-8')
      return NextResponse.json({
        success: true,
        path: filePath,
        bytesWritten: Buffer.byteLength(content, 'utf-8'),
      })
    }

    if (action === 'edit') {
      if (!oldString) {
        return NextResponse.json({ success: false, error: 'oldString is required' }, { status: 400 })
      }

      const existingContent = await fs.readFile(absolutePath, 'utf-8')
      let newContent: string
      let occurrences = 0

      if (replaceAll) {
        const regex = new RegExp(escapeRegExp(oldString), 'g')
        occurrences = (existingContent.match(regex) || []).length
        newContent = existingContent.replace(regex, newString || '')
      } else {
        occurrences = existingContent.includes(oldString) ? 1 : 0
        newContent = existingContent.replace(oldString, newString || '')
      }

      if (occurrences === 0) {
        return NextResponse.json({ success: false, error: 'String not found in file', path: filePath }, { status: 400 })
      }

      await fs.writeFile(absolutePath, newContent, 'utf-8')
      return NextResponse.json({
        success: true,
        path: filePath,
        occurrencesReplaced: occurrences,
      })
    }

    return NextResponse.json({ success: false, error: 'Invalid action' }, { status: 400 })
  } catch (error: any) {
    return NextResponse.json({ success: false, error: error.message }, { status: 500 })
  }
}

function escapeRegExp(string: string): string {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

