import { existsSync } from "fs"
import { readdir, readFile, writeFile } from "fs/promises"
import path from "path"
import { isStandaloneUi } from "@/lib/standalone"

export type ArtifactMetadata = {
  artifact_id: string
  tool_name?: string
  source_url?: string | null
  content_type: string
  content_hash?: string
  stored_raw_path: string
  size_bytes: number
  title?: string | null
  tags: string[]
  publish_date?: string | null
  created_at: string
  [key: string]: unknown
}

export type ArtifactStorePaths = {
  metadataPath: string
  artifactsDir: string
}

export function getArtifactStorePaths(): ArtifactStorePaths {
  const cwd = process.cwd()

  const projectMetadataPath = path.join(cwd, "artifact_metadata.jsonl")
  const projectArtifactsDir = path.join(cwd, "artifacts")

  const userHome = process.env.USERPROFILE || process.env.HOME
  const userMetadataPath = userHome
    ? path.join(userHome, ".deepagents", "agent", "compaction", "artifact_metadata.jsonl")
    : null
  const userArtifactsDir = userHome
    ? path.join(userHome, ".deepagents", "agent", "compaction", "artifacts")
    : null

  if (isStandaloneUi()) {
    return { metadataPath: projectMetadataPath, artifactsDir: projectArtifactsDir }
  }

  if (userMetadataPath && existsSync(userMetadataPath)) {
    return {
      metadataPath: userMetadataPath,
      artifactsDir: userArtifactsDir || projectArtifactsDir,
    }
  }

  return { metadataPath: projectMetadataPath, artifactsDir: projectArtifactsDir }
}

export async function readArtifactMetadataJsonl(metadataPath: string): Promise<ArtifactMetadata[]> {
  if (!existsSync(metadataPath)) return []

  const content = await readFile(metadataPath, "utf-8")
  const lines = content.trim().split("\n").filter((l) => l.trim())

  return lines
    .map((line) => {
      try {
        return JSON.parse(line) as ArtifactMetadata
      } catch {
        return null
      }
    })
    .filter((item): item is ArtifactMetadata => item !== null)
}

export async function writeArtifactMetadataJsonl(metadataPath: string, artifacts: ArtifactMetadata[]) {
  const nextContent = artifacts.map((a) => JSON.stringify(a)).join("\n") + (artifacts.length ? "\n" : "")
  await writeFile(metadataPath, nextContent, "utf-8")
}

export function toWorkspaceRelativePath(absoluteOrRelativePath: string): string {
  if (!absoluteOrRelativePath) return absoluteOrRelativePath
  if (!path.isAbsolute(absoluteOrRelativePath)) return absoluteOrRelativePath
  const rel = path.relative(process.cwd(), absoluteOrRelativePath)
  return rel || absoluteOrRelativePath
}

export async function findArtifactFilePath(args: {
  artifactId: string
  artifactsDir: string
  storedRawPath?: string | null
}): Promise<string | null> {
  const { artifactId, artifactsDir, storedRawPath } = args

  const tryPath = (p: string | null | undefined) => {
    if (!p) return null
    const resolved = path.isAbsolute(p) ? p : path.resolve(process.cwd(), p)
    return existsSync(resolved) ? resolved : null
  }

  const stored = tryPath(storedRawPath)
  if (stored) return stored

  const extensions = [".txt", ".md", ".json", ".html", ".pdf", ".png", ".jpg", ".jpeg", ".webp"]
  for (const ext of extensions) {
    const candidate = path.join(artifactsDir, `${artifactId}${ext}`)
    if (existsSync(candidate)) return candidate
  }

  // As a last resort, scan the artifacts directory for any matching prefix.
  try {
    const entries = await readdir(artifactsDir)
    const match = entries.find((name) => name.startsWith(`${artifactId}.`) || name === artifactId)
    return match ? path.join(artifactsDir, match) : null
  } catch {
    return null
  }
}

