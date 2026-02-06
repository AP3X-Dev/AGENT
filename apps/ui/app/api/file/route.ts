import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs/promises'
import path from 'path'

// Allowed image extensions
const ALLOWED_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp']

// MIME types for images
const MIME_TYPES: Record<string, string> = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.svg': 'image/svg+xml',
  '.bmp': 'image/bmp',
}

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams
  const filePath = searchParams.get('path')

  if (!filePath) {
    return NextResponse.json({ error: 'Missing path parameter' }, { status: 400 })
  }

  // Get file extension
  const ext = path.extname(filePath).toLowerCase()

  // Only allow image files for security
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return NextResponse.json({ error: 'Only image files are allowed' }, { status: 403 })
  }

  try {
    // Resolve the path (handle both absolute and relative paths)
    let resolvedPath = filePath

    // If it's a relative path, resolve from current working directory
    if (!path.isAbsolute(filePath)) {
      resolvedPath = path.resolve(process.cwd(), filePath)
    }

    // Security check: prevent directory traversal
    const normalizedPath = path.normalize(resolvedPath)
    
    // Read the file
    const fileBuffer = await fs.readFile(normalizedPath)

    // Get MIME type
    const mimeType = MIME_TYPES[ext] || 'application/octet-stream'

    // Return the file with appropriate headers
    return new NextResponse(fileBuffer, {
      headers: {
        'Content-Type': mimeType,
        'Cache-Control': 'public, max-age=3600',
      },
    })
  } catch (error: any) {
    if (error.code === 'ENOENT') {
      return NextResponse.json({ error: 'File not found' }, { status: 404 })
    }
    console.error('Error reading file:', error)
    return NextResponse.json({ error: 'Failed to read file' }, { status: 500 })
  }
}

