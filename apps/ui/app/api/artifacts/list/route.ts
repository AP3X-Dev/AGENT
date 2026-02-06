import { NextRequest, NextResponse } from 'next/server'
import { findArtifactFilePath, getArtifactStorePaths, readArtifactMetadataJsonl, toWorkspaceRelativePath, type ArtifactMetadata } from '@/lib/artifacts/store'

/**
 * GET /api/artifacts/list?search=query&tag=research&type=text/markdown&limit=50&offset=0
 * 
 * Lists and searches artifacts with filtering and pagination
 */
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const searchQuery = searchParams.get('search')?.toLowerCase()
    const tagFilter = searchParams.get('tag')?.toLowerCase()
    const typeFilter = searchParams.get('type')?.toLowerCase()
    const limit = parseInt(searchParams.get('limit') || '50')
    const offset = parseInt(searchParams.get('offset') || '0')

    const { metadataPath, artifactsDir } = getArtifactStorePaths()
    let artifacts: ArtifactMetadata[] = await readArtifactMetadataJsonl(metadataPath)

    // Normalize stored_raw_path to the local workspace for display.
    artifacts = await Promise.all(
      artifacts.map(async (artifact) => {
        const resolved = await findArtifactFilePath({
          artifactId: artifact.artifact_id,
          artifactsDir,
          storedRawPath: artifact.stored_raw_path,
        })
        return {
          ...artifact,
          stored_raw_path: resolved ? toWorkspaceRelativePath(resolved) : toWorkspaceRelativePath(artifact.stored_raw_path),
        }
      })
    )

    // Apply filters
    if (searchQuery) {
      artifacts = artifacts.filter(artifact => {
        const searchableText = [
          artifact.artifact_id,
          artifact.title,
          artifact.tool_name,
          artifact.source_url,
          ...artifact.tags
        ].filter(Boolean).join(' ').toLowerCase()
        
        return searchableText.includes(searchQuery)
      })
    }

    if (tagFilter) {
      artifacts = artifacts.filter(artifact => 
        artifact.tags.some(tag => tag.toLowerCase().includes(tagFilter))
      )
    }

    if (typeFilter) {
      artifacts = artifacts.filter(artifact => 
        artifact.content_type.toLowerCase().includes(typeFilter)
      )
    }

    // Sort by created_at descending (newest first)
    artifacts.sort((a, b) => {
      const dateA = new Date(a.created_at || 0).getTime()
      const dateB = new Date(b.created_at || 0).getTime()
      return dateB - dateA
    })

    const total = artifacts.length
    const paginatedArtifacts = artifacts.slice(offset, offset + limit)

    return NextResponse.json({ 
      artifacts: paginatedArtifacts,
      total,
      limit,
      offset,
      hasMore: offset + limit < total
    })
  } catch (error) {
    console.error('Error listing artifacts:', error)
    return NextResponse.json(
      { error: 'Failed to list artifacts' },
      { status: 500 }
    )
  }
}

