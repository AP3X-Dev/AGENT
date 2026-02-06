import { NextRequest, NextResponse } from 'next/server'
import { findArtifactFilePath, getArtifactStorePaths, readArtifactMetadataJsonl, toWorkspaceRelativePath, type ArtifactMetadata } from '@/lib/artifacts/store'

/**
 * GET /api/artifacts/metadata
 * 
 * Retrieves all artifact metadata from artifacts_metadata.jsonl
 */
export async function GET(request: NextRequest) {
  try {
    const { metadataPath, artifactsDir } = getArtifactStorePaths()
    let artifacts: ArtifactMetadata[] = await readArtifactMetadataJsonl(metadataPath)

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

    // Sort by created_at descending (newest first)
    artifacts.sort((a, b) => {
      const dateA = new Date(a.created_at || 0).getTime()
      const dateB = new Date(b.created_at || 0).getTime()
      return dateB - dateA
    })

    return NextResponse.json({ 
      artifacts,
      total: artifacts.length 
    })
  } catch (error) {
    console.error('Error reading artifact metadata:', error)
    return NextResponse.json(
      { error: 'Failed to read artifact metadata' },
      { status: 500 }
    )
  }
}

