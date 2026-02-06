import { NextRequest, NextResponse } from 'next/server'
import { readdir, readFile } from 'fs/promises'
import os from 'os'
import path from 'path'
import { existsSync } from 'fs'

// Claude Code compatible skill metadata
// Required: name, description
// Optional: everything else
interface SkillMeta {
  id: string
  name: string
  description: string
  // Optional fields for backwards compatibility
  version?: string
  mode?: string
  tags?: string[]
  tools?: string[]
  inputs?: string
  outputs?: string
  safety?: string
  triggers?: string[]
  // System fields
  path: string
  source_dir: string
  loaded_at: string
}

/**
 * Simple YAML frontmatter parser for skill files
 * Handles basic key: value pairs and arrays
 */
function parseSkillFrontmatter(content: string): Record<string, unknown> | null {
  if (!content.startsWith('---')) return null
  const parts = content.split('---', 3)
  if (parts.length < 3) return null

  try {
    const yamlContent = parts[1].trim()
    const result: Record<string, unknown> = {}
    const lines = yamlContent.split('\n')

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed || trimmed.startsWith('#')) continue

      const colonIndex = trimmed.indexOf(':')
      if (colonIndex === -1) continue

      const key = trimmed.slice(0, colonIndex).trim()
      let value: unknown = trimmed.slice(colonIndex + 1).trim()

      // Handle quoted strings
      if ((value as string).startsWith('"') && (value as string).endsWith('"')) {
        value = (value as string).slice(1, -1)
      } else if ((value as string).startsWith("'") && (value as string).endsWith("'")) {
        value = (value as string).slice(1, -1)
      }
      // Handle arrays in JSON format
      else if ((value as string).startsWith('[') && (value as string).endsWith(']')) {
        try {
          value = JSON.parse(value as string)
        } catch {
          // Keep as string if JSON parse fails
        }
      }
      // Handle empty values
      else if (value === '') {
        value = ''
      }

      result[key] = value
    }

    return result
  } catch {
    return null
  }
}

/**
 * GET /api/skills/list
 * Lists all available skills
 */
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const searchQuery = searchParams.get('search')?.toLowerCase()
    const tagFilter = searchParams.get('tag')?.toLowerCase()
    const modeFilter = searchParams.get('mode')?.toLowerCase()
    const limit = parseInt(searchParams.get('limit') || '50')
    const offset = parseInt(searchParams.get('offset') || '0')

    const defaultBackendWin = 'C:\\Users\\Guerr\\Documents\\ag3nt'
    const ag3ntBackendPath =
      process.env.AG3NT_BACKEND_PATH ||
      process.env.NEXT_PUBLIC_AG3NT_BACKEND_PATH ||
      (existsSync(defaultBackendWin) ? defaultBackendWin : null)

    const workspaceRoot = ag3ntBackendPath && existsSync(ag3ntBackendPath) ? ag3ntBackendPath : process.cwd()

    // Prefer AG3NT skill locations; keep legacy .deepagents paths as fallback.
    const skillDirsInOrder: string[] = [
      // Bundled skills (AG3NT repo root)
      path.join(workspaceRoot, 'skills'),
      // Workspace overrides (AG3NT runtime also loads these)
      path.join(workspaceRoot, '.ag3nt', 'skills'),
      // Global user skills
      path.join(os.homedir(), '.ag3nt', 'skills'),
      // Legacy locations (backwards compatibility)
      path.join(os.homedir(), '.deepagents', 'agent', 'skills'),
      path.join(os.homedir(), '.deepagents', 'skills'),
      path.join(process.cwd(), '.deepagents', 'skills'),
    ].filter((p) => existsSync(p))

    const skillsById = new Map<string, SkillMeta>()

    for (const dir of skillDirsInOrder) {
      const entries = await readdir(dir, { withFileTypes: true })
      for (const entry of entries) {
        if (!entry.isDirectory()) continue
        const skillMdPath = path.join(dir, entry.name, 'SKILL.md')
        if (!existsSync(skillMdPath)) continue

        try {
          const content = await readFile(skillMdPath, 'utf-8')
          const frontmatter = parseSkillFrontmatter(content)
          if (!frontmatter) continue

          // Claude Code compatible: use 'name' as primary identifier
          // Only include optional fields if present in frontmatter
          const meta: SkillMeta = {
            // Required fields
            id: (frontmatter.name as string) || (frontmatter.id as string) || entry.name,
            name: (frontmatter.name as string) || entry.name,
            description: (frontmatter.description as string) || '',
            // System fields
            path: skillMdPath,
            source_dir: path.join(dir, entry.name),
            loaded_at: new Date().toISOString(),
            // Optional fields - only include if present
            ...(frontmatter.version ? { version: frontmatter.version as string } : {}),
            ...(frontmatter.mode ? { mode: frontmatter.mode as string } : {}),
            ...(frontmatter.tags ? { tags: frontmatter.tags as string[] } : {}),
            ...(frontmatter.tools ? { tools: frontmatter.tools as string[] } : {}),
            ...(frontmatter.inputs ? { inputs: frontmatter.inputs as string } : {}),
            ...(frontmatter.outputs ? { outputs: frontmatter.outputs as string } : {}),
            ...(frontmatter.safety ? { safety: frontmatter.safety as string } : {}),
            ...(frontmatter.triggers ? { triggers: frontmatter.triggers as string[] } : {}),
          }
          // Later directories override earlier ones.
          skillsById.set(meta.id, meta)
        } catch (err) {
          console.error(`Failed to load skill from ${skillMdPath}:`, err)
        }
      }
    }

    let skills: SkillMeta[] = Array.from(skillsById.values())

    // Apply filters
    if (searchQuery) {
      skills = skills.filter(skill => {
        const tags = skill.tags || []
        const text = [skill.id, skill.name, skill.description, ...tags]
          .join(' ').toLowerCase()
        return text.includes(searchQuery)
      })
    }

    if (tagFilter) {
      skills = skills.filter(skill => {
        const tags = skill.tags || []
        return tags.some(tag => tag.toLowerCase().includes(tagFilter))
      })
    }

    // Sort by name
    skills.sort((a, b) => a.name.localeCompare(b.name))

    const total = skills.length
    const paginatedSkills = skills.slice(offset, offset + limit)

    return NextResponse.json({
      skills: paginatedSkills,
      total,
      limit,
      offset,
      hasMore: offset + limit < total,
    })
  } catch (error) {
    console.error('Error listing skills:', error)
    return NextResponse.json({ error: 'Failed to list skills' }, { status: 500 })
  }
}

