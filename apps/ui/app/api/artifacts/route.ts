import { NextRequest, NextResponse } from 'next/server'
import { readFile } from 'fs/promises'
import { findArtifactFilePath, getArtifactStorePaths, readArtifactMetadataJsonl } from '@/lib/artifacts/store'

/**
 * Artifact metadata structure
 */
interface ArtifactMetadata {
  artifact_id: string
  stored_raw_path: string
  content_type: string
  [key: string]: unknown
}

/**
 * GET /api/artifacts?id={artifact_id}
 *
 * Retrieves an artifact from the deepagents artifact store.
 * Uses stored_raw_path from metadata for the actual file location.
 */
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const artifactId = searchParams.get('id')

    if (!artifactId) {
      return NextResponse.json(
        { error: 'Missing artifact ID' },
        { status: 400 }
      )
    }

    // Validate artifact ID format (should be art_XXXXXXXXXXXX)
    if (!/^art_[a-f0-9]{12}$/.test(artifactId)) {
      return NextResponse.json(
        { error: 'Invalid artifact ID format' },
        { status: 400 }
      )
    }

    const { metadataPath, artifactsDir } = getArtifactStorePaths()
    const artifacts = await readArtifactMetadataJsonl(metadataPath)

    const artifactMeta = artifacts.find((a) => a.artifact_id === artifactId) || null
    const artifactPath = await findArtifactFilePath({
      artifactId,
      artifactsDir,
      storedRawPath: artifactMeta?.stored_raw_path,
    })

    if (!artifactPath) {
      return NextResponse.json({ error: `Artifact ${artifactId} not found` }, { status: 404 })
    }

    const contentType = artifactMeta?.content_type || 'text/plain'
    const content = await readFile(artifactPath)

    return new NextResponse(content, {
      status: 200,
      headers: {
        'Content-Type': contentType,
        'Cache-Control': 'public, max-age=31536000, immutable',
      },
    })
  } catch (error) {
    console.error('Error reading artifact:', error)
    return NextResponse.json(
      { error: 'Failed to read artifact' },
      { status: 500 }
    )
  }
}

