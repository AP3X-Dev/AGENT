import { NextRequest, NextResponse } from 'next/server'
import { getArtifactStorePaths, readArtifactMetadataJsonl, writeArtifactMetadataJsonl, type ArtifactMetadata } from '@/lib/artifacts/store'

/**
 * PATCH /api/artifacts/rename
 * 
 * Renames an artifact (updates its title in metadata)
 * 
 * Body: { artifactId: string, newTitle: string }
 */
export async function PATCH(request: NextRequest) {
  try {
    const body = await request.json()
    const { artifactId, newTitle } = body

    if (!artifactId || !newTitle) {
      return NextResponse.json(
        { error: 'Artifact ID and new title are required' },
        { status: 400 }
      )
    }

    const { metadataPath } = getArtifactStorePaths()
    const artifacts: ArtifactMetadata[] = await readArtifactMetadataJsonl(metadataPath)

    // Find and update the artifact
    const artifactIndex = artifacts.findIndex(a => a.artifact_id === artifactId)
    
    if (artifactIndex === -1) {
      return NextResponse.json(
        { error: 'Artifact not found' },
        { status: 404 }
      )
    }

    // Update the title
    artifacts[artifactIndex].title = newTitle

    await writeArtifactMetadataJsonl(metadataPath, artifacts)

    return NextResponse.json({ 
      success: true,
      artifact: artifacts[artifactIndex]
    })
  } catch (error) {
    console.error('Error renaming artifact:', error)
    return NextResponse.json(
      { error: 'Failed to rename artifact' },
      { status: 500 }
    )
  }
}

