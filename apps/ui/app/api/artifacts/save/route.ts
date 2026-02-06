import { NextRequest, NextResponse } from 'next/server'
import crypto from 'crypto'
import { writeFile } from 'fs/promises'
import { findArtifactFilePath, getArtifactStorePaths, readArtifactMetadataJsonl, toWorkspaceRelativePath, writeArtifactMetadataJsonl } from '@/lib/artifacts/store'

interface ArtifactMetadata {
  artifact_id: string
  stored_raw_path: string
  content_type: string
  content_hash: string
  size_bytes: number
  title?: string
  tags: string[]
  created_at: string
}

/**
 * PUT /api/artifacts/save
 * Updates the content of an existing artifact
 * Body: { artifactId: string, content: string }
 */
export async function PUT(request: NextRequest) {
  try {
    const body = await request.json()
    const { artifactId, content } = body

    if (!artifactId || typeof content !== 'string') {
      return NextResponse.json(
        { error: 'artifactId and content are required' },
        { status: 400 }
      )
    }

    const { metadataPath, artifactsDir } = getArtifactStorePaths()
    const artifacts = await readArtifactMetadataJsonl(metadataPath)
    const idx = artifacts.findIndex((a) => a.artifact_id === artifactId)

    if (idx === -1) {
      return NextResponse.json({ error: 'Artifact not found' }, { status: 404 })
    }

    const targetArtifact = artifacts[idx]
    const artifactPath = await findArtifactFilePath({
      artifactId,
      artifactsDir,
      storedRawPath: targetArtifact.stored_raw_path,
    })

    if (!artifactPath) {
      return NextResponse.json({ error: 'Artifact file not found' }, { status: 404 })
    }

    await writeFile(artifactPath, content, 'utf-8')

    const newSize = Buffer.byteLength(content, 'utf-8')
    const newHash = crypto.createHash('sha256').update(content, 'utf-8').digest('hex')

    artifacts[idx] = {
      ...targetArtifact,
      size_bytes: newSize,
      content_hash: newHash,
      stored_raw_path: toWorkspaceRelativePath(artifactPath),
    }

    await writeArtifactMetadataJsonl(metadataPath, artifacts)

    return NextResponse.json({
      success: true,
      artifactId,
      size: newSize,
    })
  } catch (error) {
    console.error('Error saving artifact:', error)
    return NextResponse.json({ error: 'Failed to save artifact' }, { status: 500 })
  }
}

