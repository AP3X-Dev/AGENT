/**
 * Artifact Types
 * 
 * Type definitions for the artifact management system
 */

/**
 * Artifact metadata from the backend
 */
export interface ArtifactMetadata {
  artifact_id: string
  tool_name: string
  source_url?: string
  content_type: string
  content_hash: string
  stored_raw_path: string
  size_bytes: number
  title?: string
  tags: string[]
  publish_date?: string
  created_at: string
}

/**
 * Artifact with loaded content
 */
export interface Artifact extends ArtifactMetadata {
  content?: string | ArrayBuffer
}

/**
 * Artifact list response
 */
export interface ArtifactListResponse {
  artifacts: ArtifactMetadata[]
  total: number
  limit: number
  offset: number
  hasMore: boolean
}

/**
 * Artifact search/filter criteria
 */
export interface ArtifactSearchCriteria {
  search?: string
  tag?: string
  type?: string
  limit?: number
  offset?: number
}

/**
 * Artifact view mode
 */
export type ArtifactViewMode = 'list' | 'grid'

/**
 * Artifact sort field
 */
export type ArtifactSortField = 'created_at' | 'title' | 'size_bytes' | 'content_type'

/**
 * Artifact sort direction
 */
export type ArtifactSortDirection = 'asc' | 'desc'

