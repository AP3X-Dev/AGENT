/**
 * Skills types for the Skills Library module
 * Compatible with Claude Code skill format (https://github.com/anthropics/skills)
 */

export type SkillViewMode = 'list' | 'grid'

/**
 * Compact metadata for a skill (loaded from frontmatter)
 * Claude Code format only requires 'name' and 'description'
 * Other fields are optional for backwards compatibility
 */
export interface SkillMeta {
  // Claude Code required fields
  id: string              // Derived from folder name or 'name' field
  name: string            // Human-readable skill name
  description: string     // What the skill does and when to use it

  // Optional metadata (for backwards compatibility)
  version?: string
  mode?: string
  tags?: string[]
  tools?: string[]
  inputs?: string
  outputs?: string
  safety?: string
  model_hint?: string
  budget_hint?: number
  triggers?: string[]

  // System fields
  path: string            // Path to SKILL.md
  source_dir: string      // Directory containing the skill
  loaded_at: string       // When the skill was loaded
}

/**
 * Full skill content including markdown body
 */
export interface Skill {
  meta: SkillMeta
  raw_content: string
}

/**
 * Search criteria for skills
 */
export interface SkillSearchCriteria {
  search?: string
  tags?: string[]
  limit?: number
  offset?: number
}

/**
 * Response from skills list API
 */
export interface SkillsListResponse {
  skills: SkillMeta[]
  total: number
  limit: number
  offset: number
  hasMore: boolean
}

