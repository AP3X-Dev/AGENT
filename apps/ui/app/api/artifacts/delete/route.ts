import { NextRequest, NextResponse } from 'next/server'
import { unlink } from 'fs/promises'
import { findArtifactFilePath, getArtifactStorePaths, readArtifactMetadataJsonl, writeArtifactMetadataJsonl, type ArtifactMetadata } from '@/lib/artifacts/store'

/**
 * DELETE /api/artifacts/delete?id=artifact_id
 * 
 * Deletes an artifact and removes it from metadata
 */
export async function DELETE(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const artifactId = searchParams.get('id')

    if (!artifactId) {
      return NextResponse.json(
        { error: 'Artifact ID is required' },
        { status: 400 }
      )
    }

    const { metadataPath, artifactsDir } = getArtifactStorePaths()
    const artifacts: ArtifactMetadata[] = await readArtifactMetadataJsonl(metadataPath)

    if (!artifacts.length) {
      return NextResponse.json({ error: 'Metadata file not found' }, { status: 404 })
    }

    // Find the artifact to delete
    const artifactToDelete = artifacts.find(a => a.artifact_id === artifactId)
    
    if (!artifactToDelete) {
      return NextResponse.json(
        { error: 'Artifact not found' },
        { status: 404 }
      )
    }

    const artifactFilePath = await findArtifactFilePath({
      artifactId,
      artifactsDir,
      storedRawPath: artifactToDelete.stored_raw_path,
    })
    if (artifactFilePath) {
      await unlink(artifactFilePath).catch(() => undefined)
    }

    // Remove from metadata
    const updatedArtifacts = artifacts.filter(a => a.artifact_id !== artifactId)
    
    await writeArtifactMetadataJsonl(metadataPath, updatedArtifacts)

    return NextResponse.json({ 
      success: true,
      deletedArtifactId: artifactId 
    })
  } catch (error) {
    console.error('Error deleting artifact:', error)
    return NextResponse.json(
      { error: 'Failed to delete artifact' },
      { status: 500 }
    )
  }
}

