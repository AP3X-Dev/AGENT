/**
 * Autocomplete API Route
 * Provides file path and command autocompletion
 */

import { NextRequest, NextResponse } from 'next/server'
import { promises as fs } from 'fs'
import path from 'path'

// Get workspace root
const getWorkspaceRoot = () => process.cwd()

// File extension to icon mapping
const FILE_ICONS: Record<string, string> = {
  '.ts': '📘',
  '.tsx': '⚛️',
  '.js': '📒',
  '.jsx': '⚛️',
  '.json': '📋',
  '.md': '📝',
  '.css': '🎨',
  '.scss': '🎨',
  '.html': '🌐',
  '.py': '🐍',
  '.rs': '🦀',
  '.go': '🔵',
  '.java': '☕',
  '.c': '⚙️',
  '.cpp': '⚙️',
  '.h': '📎',
  '.sh': '💻',
  '.yaml': '⚙️',
  '.yml': '⚙️',
  '.env': '🔐',
  '.gitignore': '🚫',
}

function getFileIcon(name: string, isDirectory: boolean): string {
  if (isDirectory) return '📁'
  const ext = path.extname(name).toLowerCase()
  return FILE_ICONS[ext] || '📄'
}

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams
  const query = searchParams.get('query') || ''
  const type = searchParams.get('type') || 'all'
  const limit = parseInt(searchParams.get('limit') || '20')

  const workspaceRoot = getWorkspaceRoot()

  try {
    if (type === 'file' || type === 'all') {
      // Parse the query to get directory and search term
      let searchDir = workspaceRoot
      let searchTerm = query

      // Handle path-like queries
      if (query.includes('/') || query.includes('\\')) {
        const lastSeparator = Math.max(query.lastIndexOf('/'), query.lastIndexOf('\\'))
        const dirPart = query.substring(0, lastSeparator + 1)
        searchTerm = query.substring(lastSeparator + 1)
        
        // Resolve the directory
        const resolvedDir = path.resolve(workspaceRoot, dirPart)
        if (resolvedDir.startsWith(workspaceRoot)) {
          try {
            const stats = await fs.stat(resolvedDir)
            if (stats.isDirectory()) {
              searchDir = resolvedDir
            }
          } catch {
            // Directory doesn't exist, use workspace root
          }
        }
      }

      // Read directory entries
      const entries = await fs.readdir(searchDir, { withFileTypes: true })

      // Filter and map to autocomplete items
      const items = entries
        .filter(entry => {
          if (!searchTerm) return true
          return entry.name.toLowerCase().startsWith(searchTerm.toLowerCase())
        })
        .slice(0, limit)
        .map(entry => {
          const isDir = entry.isDirectory()
          const relativePath = path.relative(workspaceRoot, path.join(searchDir, entry.name))
          return {
            value: relativePath + (isDir ? '/' : ''),
            displayText: entry.name + (isDir ? '/' : ''),
            type: isDir ? 'directory' : 'file',
            icon: getFileIcon(entry.name, isDir),
            description: isDir ? 'Directory' : path.extname(entry.name).toUpperCase().replace('.', '') + ' File',
          }
        })
        // Sort: directories first, then alphabetically
        .sort((a, b) => {
          if (a.type === 'directory' && b.type !== 'directory') return -1
          if (a.type !== 'directory' && b.type === 'directory') return 1
          return a.displayText.localeCompare(b.displayText)
        })

      return NextResponse.json({
        items,
        hasMore: entries.length > limit,
      })
    }

    return NextResponse.json({ items: [], hasMore: false })
  } catch (error: any) {
    // Return empty results on error (e.g., directory doesn't exist)
    return NextResponse.json({ items: [], hasMore: false })
  }
}

