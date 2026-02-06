"use client"

import { useState, useEffect, useCallback } from "react"
import { FileText, Search, Grid3x3, List, Filter, Download, Trash2, Edit2, X, Globe, Wrench, FileJson, FileCode, File } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
  ModuleContainer,
  EmptyModuleState,
  LoadingModuleState,
  ErrorModuleState,
} from "./module-container"
import { useAgentConnection } from "@/hooks/use-agent-connection"
import { ArtifactDocumentViewer } from "@/components/features/artifacts/artifact-document-viewer"
import type { ModuleConfig, ModuleInstanceProps } from "@/types/modules"
import type { ArtifactMetadata, ArtifactViewMode, ArtifactSearchCriteria } from "@/types/artifacts"

// Get icon based on content type
function getArtifactIcon(contentType: string) {
  if (contentType.includes('json')) return FileJson
  if (contentType.includes('markdown') || contentType.includes('md')) return FileText
  if (contentType.includes('html') || contentType.includes('xml')) return FileCode
  return File
}

// Get color class based on content type
function getArtifactColor(contentType: string): string {
  if (contentType.includes('json')) return 'text-amber-400'
  if (contentType.includes('markdown') || contentType.includes('md')) return 'text-cyan-400'
  if (contentType.includes('html')) return 'text-orange-400'
  if (contentType.includes('csv')) return 'text-green-400'
  return 'text-text-muted'
}

/**
 * Artifacts Library Module Configuration
 */
export const artifactsLibraryModuleConfig: ModuleConfig = {
  metadata: {
    id: 'artifacts-library',
    displayName: 'Artifacts Library',
    description: 'Browse, search, and manage research artifacts and saved content',
    icon: 'FileText',
    category: 'data',
    version: '1.0.0',
  },
  hasHeader: true,
  initialState: {
    isLoading: false,
    error: null,
    data: { artifacts: [], selectedArtifact: null },
  },
  agentConfig: {
    enabled: true,
    supportedCommands: ['search', 'filter', 'getArtifact', 'deleteArtifact', 'exportArtifact'],
    emittedEvents: ['artifact-selected', 'artifact-deleted', 'search-updated'],
    contextDescription: 'Artifacts library for browsing and managing research outputs and saved content',
  },
}

/**
 * Artifacts Library Context for agent communication
 */
interface ArtifactsLibraryContext {
  totalArtifacts: number
  selectedArtifactId: string | null
  searchQuery: string
  activeFilters: {
    tag?: string
    type?: string
  }
  viewMode: ArtifactViewMode
}

/**
 * Artifacts Library Module Component
 */
export function ArtifactsLibraryModule({ instanceId, initialData }: ModuleInstanceProps) {
  const [artifacts, setArtifacts] = useState<ArtifactMetadata[]>([])
  const [selectedArtifact, setSelectedArtifact] = useState<ArtifactMetadata | null>(null)
  const [viewMode, setViewMode] = useState<ArtifactViewMode>('grid')
  const [searchQuery, setSearchQuery] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [total, setTotal] = useState(0)
  const [isViewerFullWidth, setIsViewerFullWidth] = useState(false)

  // Agent communication
  const { updateContext, sendEvent, onCommand } = useAgentConnection({
    instanceId: instanceId || `artifacts-library-${Date.now()}`,
    moduleType: 'artifacts-library',
    autoRegister: true,
    initialContext: {
      totalArtifacts: 0,
      selectedArtifactId: null,
      searchQuery: '',
      activeFilters: {},
      viewMode: 'list',
    } as Partial<ArtifactsLibraryContext>,
  })

  // Load artifacts
  const loadArtifacts = useCallback(async (criteria?: ArtifactSearchCriteria) => {
    try {
      setIsLoading(true)
      setError(null)

      const params = new URLSearchParams()
      if (criteria?.search) params.set('search', criteria.search)
      if (criteria?.tag) params.set('tag', criteria.tag)
      if (criteria?.type) params.set('type', criteria.type)
      if (criteria?.limit) params.set('limit', criteria.limit.toString())
      if (criteria?.offset) params.set('offset', criteria.offset.toString())

      const response = await fetch(`/api/artifacts/list?${params}`)
      if (!response.ok) throw new Error('Failed to load artifacts')

      const data = await response.json()
      setArtifacts(data.artifacts)
      setTotal(data.total)

      // Update agent context
      updateContext({
        totalArtifacts: data.total,
        searchQuery: criteria?.search || '',
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load artifacts')
    } finally {
      setIsLoading(false)
    }
  }, [updateContext])

  // Initial load
  useEffect(() => {
    loadArtifacts()
  }, [loadArtifacts])

  // Handle search
  const handleSearch = useCallback((query: string) => {
    setSearchQuery(query)
    loadArtifacts({ search: query })
    sendEvent('search-updated', { query })
  }, [loadArtifacts, sendEvent])

  // Handle artifact selection
  const handleSelectArtifact = useCallback((artifact: ArtifactMetadata) => {
    setSelectedArtifact(artifact)
    updateContext({ selectedArtifactId: artifact.artifact_id })
    sendEvent('artifact-selected', { artifactId: artifact.artifact_id })
  }, [updateContext, sendEvent])

  // Handle artifact deletion
  const handleDeleteArtifact = useCallback(async (artifactId: string) => {
    if (!confirm('Are you sure you want to delete this artifact? This action cannot be undone.')) {
      return
    }

    try {
      const response = await fetch(`/api/artifacts/delete?id=${artifactId}`, {
        method: 'DELETE',
      })

      if (!response.ok) throw new Error('Failed to delete artifact')

      // Refresh the list
      await loadArtifacts({ search: searchQuery })

      // Clear selection if deleted artifact was selected
      if (selectedArtifact?.artifact_id === artifactId) {
        setSelectedArtifact(null)
      }

      sendEvent('artifact-deleted', { artifactId })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete artifact')
    }
  }, [loadArtifacts, searchQuery, selectedArtifact, sendEvent])

  // Handle artifact rename
  const handleRenameArtifact = useCallback(async (artifactId: string, newTitle: string) => {
    try {
      const response = await fetch('/api/artifacts/rename', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ artifactId, newTitle }),
      })

      if (!response.ok) throw new Error('Failed to rename artifact')

      // Refresh the list
      await loadArtifacts({ search: searchQuery })

      // Update selected artifact if it was renamed
      if (selectedArtifact?.artifact_id === artifactId) {
        setSelectedArtifact(prev => prev ? { ...prev, title: newTitle } : null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to rename artifact')
    }
  }, [loadArtifacts, searchQuery, selectedArtifact])

  // Register command handlers
  useEffect(() => {
    const subscriptions = [
      onCommand('search', async ({ query }: { query: string }) => {
        handleSearch(query)
        return { success: true }
      }),
      onCommand('getArtifact', async ({ artifactId }: { artifactId: string }) => {
        const artifact = artifacts.find(a => a.artifact_id === artifactId)
        return { artifact: artifact || null }
      }),
      onCommand('deleteArtifact', async ({ artifactId }: { artifactId: string }) => {
        await handleDeleteArtifact(artifactId)
        return { success: true }
      }),
      onCommand('renameArtifact', async ({ artifactId, newTitle }: { artifactId: string; newTitle: string }) => {
        await handleRenameArtifact(artifactId, newTitle)
        return { success: true }
      }),
    ]

    return () => subscriptions.forEach(sub => sub.unsubscribe())
  }, [onCommand, handleSearch, artifacts, handleDeleteArtifact, handleRenameArtifact])

  // Render states
  if (isLoading && artifacts.length === 0) {
    return (
      <ModuleContainer config={artifactsLibraryModuleConfig}>
        <LoadingModuleState message="Loading artifacts..." />
      </ModuleContainer>
    )
  }

  if (error) {
    return (
      <ModuleContainer config={artifactsLibraryModuleConfig}>
        <ErrorModuleState error={error} onRetry={() => loadArtifacts()} />
      </ModuleContainer>
    )
  }

  if (artifacts.length === 0) {
    return (
      <ModuleContainer config={artifactsLibraryModuleConfig}>
        <EmptyModuleState
          icon={FileText}
          title="No artifacts yet"
          description="Artifacts from research and tool outputs will appear here"
        />
      </ModuleContainer>
    )
  }

  return (
    <ModuleContainer
      config={artifactsLibraryModuleConfig}
      showHeader={false}
    >
      <div className="flex flex-col h-full">
        {/* Toolbar */}
        <div className="flex items-center gap-3 p-4 border-b border-border bg-surface-secondary">
          {/* Search */}
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
            <Input
              type="text"
              placeholder="Search artifacts..."
              value={searchQuery}
              onChange={(e) => handleSearch(e.target.value)}
              className="pl-9 h-9 bg-surface border-border"
            />
          </div>

          {/* View mode toggle */}
          <div className="flex items-center gap-1 bg-surface rounded-md p-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setViewMode('list')}
              className={cn(
                "h-7 w-7 p-0",
                viewMode === 'list' && "bg-surface-elevated"
              )}
            >
              <List className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setViewMode('grid')}
              className={cn(
                "h-7 w-7 p-0",
                viewMode === 'grid' && "bg-surface-elevated"
              )}
            >
              <Grid3x3 className="h-4 w-4" />
            </Button>
          </div>

          {/* Total count */}
          <div className="text-sm text-text-muted">
            {total} {total === 1 ? 'artifact' : 'artifacts'}
          </div>
        </div>

        {/* Content area */}
        <div className="flex-1 overflow-hidden flex">
          {/* Artifacts list/grid - hidden when artifact is selected */}
          {!selectedArtifact && (
            <div className="w-full overflow-auto">
              {viewMode === 'list' ? (
                <ArtifactsList
                  artifacts={artifacts}
                  selectedArtifact={selectedArtifact}
                  onSelectArtifact={handleSelectArtifact}
                  onDeleteArtifact={handleDeleteArtifact}
                  onRenameArtifact={handleRenameArtifact}
                />
              ) : (
                <ArtifactsGrid
                  artifacts={artifacts}
                  selectedArtifact={selectedArtifact}
                  onSelectArtifact={handleSelectArtifact}
                  onDeleteArtifact={handleDeleteArtifact}
                  onRenameArtifact={handleRenameArtifact}
                />
              )}
            </div>
          )}

          {/* Document viewer - full width when selected */}
          {selectedArtifact && (
            <div className="w-full">
              <ArtifactDocumentViewer
                artifact={selectedArtifact}
                onClose={() => {
                  setSelectedArtifact(null)
                  setIsViewerFullWidth(false)
                }}
                isFullWidth={isViewerFullWidth}
                onToggleFullWidth={() => setIsViewerFullWidth(!isViewerFullWidth)}
              />
            </div>
          )}
        </div>
      </div>
    </ModuleContainer>
  )
}

// ============================================================================
// Artifacts List View
// ============================================================================

interface ArtifactsListProps {
  artifacts: ArtifactMetadata[]
  selectedArtifact: ArtifactMetadata | null
  onSelectArtifact: (artifact: ArtifactMetadata) => void
  onDeleteArtifact: (artifactId: string) => void
  onRenameArtifact: (artifactId: string, newTitle: string) => void
}

function ArtifactsList({
  artifacts,
  selectedArtifact,
  onSelectArtifact,
  onDeleteArtifact,
  onRenameArtifact
}: ArtifactsListProps) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')

  const handleStartEdit = (artifact: ArtifactMetadata, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingId(artifact.artifact_id)
    setEditTitle(artifact.title || artifact.artifact_id)
  }

  const handleSaveEdit = async (artifactId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (editTitle.trim()) {
      await onRenameArtifact(artifactId, editTitle.trim())
    }
    setEditingId(null)
  }

  const handleCancelEdit = (e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingId(null)
  }

  const handleDelete = (artifactId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    onDeleteArtifact(artifactId)
  }
  return (
    <div className="h-full overflow-y-auto">
      <div className="divide-y divide-border/50">
        {artifacts.map((artifact) => {
          const isEditing = editingId === artifact.artifact_id
          const IconComponent = getArtifactIcon(artifact.content_type)
          const iconColor = getArtifactColor(artifact.content_type)

          return (
            <div
              key={artifact.artifact_id}
              onClick={() => !isEditing && onSelectArtifact(artifact)}
              className={cn(
                "w-full text-left p-4 hover:bg-surface-elevated/50 transition-all duration-200 cursor-pointer group",
                "border-l-2 border-transparent hover:border-l-cyan-500",
                selectedArtifact?.artifact_id === artifact.artifact_id && "bg-surface-elevated border-l-cyan-500"
              )}
            >
              <div className="flex items-start gap-3">
                <div className={cn("p-2 rounded-lg bg-surface-elevated/50 flex-shrink-0", iconColor)}>
                  <IconComponent className="h-4 w-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    {isEditing ? (
                      <div className="flex items-center gap-2 flex-1" onClick={(e) => e.stopPropagation()}>
                        <Input
                          value={editTitle}
                          onChange={(e) => setEditTitle(e.target.value)}
                          className="h-7 text-sm bg-surface border-border"
                          autoFocus
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleSaveEdit(artifact.artifact_id, e as any)
                            if (e.key === 'Escape') handleCancelEdit(e as any)
                          }}
                        />
                        <Button size="sm" variant="ghost" className="h-7 px-2 text-green-400 hover:text-green-300"
                          onClick={(e) => handleSaveEdit(artifact.artifact_id, e)}>Save</Button>
                        <Button size="sm" variant="ghost" className="h-7 px-2" onClick={handleCancelEdit}>Cancel</Button>
                      </div>
                    ) : (
                      <>
                        <h3 className="text-sm font-medium text-text-primary truncate group-hover:text-cyan-400 transition-colors">
                          {artifact.title || artifact.artifact_id}
                        </h3>
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <Button size="sm" variant="ghost" className="h-6 w-6 p-0 hover:bg-surface"
                            onClick={(e) => handleStartEdit(artifact, e)} title="Rename">
                            <Edit2 className="h-3 w-3" />
                          </Button>
                          <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-red-400 hover:text-red-300 hover:bg-red-500/10"
                            onClick={(e) => handleDelete(artifact.artifact_id, e)} title="Delete">
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      </>
                    )}
                  </div>

                  {/* Metadata row */}
                  <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                    <span className={cn("text-xs font-medium", iconColor)}>
                      {artifact.content_type.split('/').pop()?.toUpperCase() || 'FILE'}
                    </span>
                    <span className="text-xs text-text-muted">•</span>
                    <span className="text-xs text-text-muted">{formatFileSize(artifact.size_bytes)}</span>
                    <span className="text-xs text-text-muted">•</span>
                    <span className="text-xs text-text-muted">{formatDate(artifact.created_at)}</span>
                    {artifact.tool_name && (
                      <>
                        <span className="text-xs text-text-muted">•</span>
                        <span className="text-xs text-amber-400/80 flex items-center gap-1">
                          <Wrench className="h-3 w-3" />
                          {artifact.tool_name}
                        </span>
                      </>
                    )}
                    {artifact.source_url && (
                      <>
                        <span className="text-xs text-text-muted">•</span>
                        <a href={artifact.source_url} target="_blank" rel="noopener noreferrer"
                          className="text-xs text-cyan-400/80 hover:text-cyan-400 flex items-center gap-1 hover:underline"
                          onClick={(e) => e.stopPropagation()}>
                          <Globe className="h-3 w-3" />
                          {(() => { try { return new URL(artifact.source_url).hostname } catch { return 'Link' } })()}
                        </a>
                      </>
                    )}
                  </div>

                  {/* Tags */}
                  {artifact.tags && artifact.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {artifact.tags.slice(0, 5).map((tag, idx) => (
                        <span key={idx}
                          className="px-2 py-0.5 text-xs bg-amber-500/10 text-amber-400 rounded-md border border-amber-500/20">
                          {tag}
                        </span>
                      ))}
                      {artifact.tags.length > 5 && (
                        <span className="px-2 py-0.5 text-xs text-text-muted">+{artifact.tags.length - 5}</span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ============================================================================
// Artifacts Grid View
// ============================================================================

function ArtifactsGrid({
  artifacts,
  selectedArtifact,
  onSelectArtifact,
  onDeleteArtifact,
  onRenameArtifact
}: ArtifactsListProps) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')

  const handleStartEdit = (artifact: ArtifactMetadata, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingId(artifact.artifact_id)
    setEditTitle(artifact.title || artifact.artifact_id)
  }

  const handleSaveEdit = async (artifactId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (editTitle.trim()) {
      await onRenameArtifact(artifactId, editTitle.trim())
    }
    setEditingId(null)
  }

  const handleCancelEdit = (e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingId(null)
  }

  const handleDelete = (artifactId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    onDeleteArtifact(artifactId)
  }
  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {artifacts.map((artifact) => {
          const isEditing = editingId === artifact.artifact_id
          const IconComponent = getArtifactIcon(artifact.content_type)
          const iconColor = getArtifactColor(artifact.content_type)

          return (
            <div
              key={artifact.artifact_id}
              onClick={() => !isEditing && onSelectArtifact(artifact)}
              className={cn(
                "text-left p-4 rounded-xl border border-border/50 transition-all duration-200 cursor-pointer group relative",
                "bg-gradient-to-br from-surface to-surface-elevated/30 hover:from-surface-elevated/50 hover:to-surface-elevated",
                "hover:border-cyan-500/50 hover:shadow-lg hover:shadow-cyan-500/5",
                selectedArtifact?.artifact_id === artifact.artifact_id && "border-cyan-500 bg-surface-elevated shadow-lg shadow-cyan-500/10"
              )}
            >
              {/* Action buttons */}
              {!isEditing && (
                <div className="absolute top-3 right-3 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity z-10">
                  <Button size="sm" variant="ghost"
                    className="h-6 w-6 p-0 bg-surface/80 backdrop-blur-sm hover:bg-surface border border-border/50"
                    onClick={(e) => handleStartEdit(artifact, e)} title="Rename">
                    <Edit2 className="h-3 w-3" />
                  </Button>
                  <Button size="sm" variant="ghost"
                    className="h-6 w-6 p-0 bg-surface/80 backdrop-blur-sm hover:bg-red-500/20 text-red-400 hover:text-red-300 border border-border/50"
                    onClick={(e) => handleDelete(artifact.artifact_id, e)} title="Delete">
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              )}

              <div className="flex flex-col gap-3">
                {/* Icon with background */}
                <div className={cn(
                  "w-12 h-12 rounded-xl flex items-center justify-center",
                  "bg-gradient-to-br from-zinc-800 to-zinc-900 border border-zinc-700/50",
                  iconColor
                )}>
                  <IconComponent className="h-6 w-6" />
                </div>

                {isEditing ? (
                  <div className="flex flex-col gap-2" onClick={(e) => e.stopPropagation()}>
                    <Input value={editTitle} onChange={(e) => setEditTitle(e.target.value)}
                      className="h-7 text-sm bg-surface border-border" autoFocus
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleSaveEdit(artifact.artifact_id, e as any)
                        if (e.key === 'Escape') handleCancelEdit(e as any)
                      }} />
                    <div className="flex gap-1">
                      <Button size="sm" variant="ghost" className="h-6 text-xs flex-1 text-green-400"
                        onClick={(e) => handleSaveEdit(artifact.artifact_id, e)}>Save</Button>
                      <Button size="sm" variant="ghost" className="h-6 text-xs flex-1"
                        onClick={handleCancelEdit}>Cancel</Button>
                    </div>
                  </div>
                ) : (
                  <h3 className="text-sm font-medium text-text-primary line-clamp-2 pr-8 group-hover:text-cyan-400 transition-colors">
                    {artifact.title || artifact.artifact_id}
                  </h3>
                )}

                {/* Type badge */}
                <div className="flex items-center gap-2">
                  <span className={cn("px-2 py-0.5 text-xs font-medium rounded-md border", iconColor,
                    artifact.content_type.includes('json') && "bg-amber-500/10 border-amber-500/20",
                    artifact.content_type.includes('markdown') && "bg-cyan-500/10 border-cyan-500/20",
                    artifact.content_type.includes('html') && "bg-orange-500/10 border-orange-500/20",
                    !artifact.content_type.includes('json') && !artifact.content_type.includes('markdown') && !artifact.content_type.includes('html') && "bg-zinc-500/10 border-zinc-500/20"
                  )}>
                    {artifact.content_type.split('/').pop()?.toUpperCase() || 'FILE'}
                  </span>
                  <span className="text-xs text-text-muted">{formatFileSize(artifact.size_bytes)}</span>
                </div>

                {/* Date and source */}
                <div className="flex items-center justify-between text-xs text-text-muted">
                  <span>{formatDate(artifact.created_at)}</span>
                  {artifact.source_url && (
                    <span className="flex items-center gap-1 text-cyan-400/60">
                      <Globe className="h-3 w-3" />
                    </span>
                  )}
                </div>

                {/* Tags */}
                {artifact.tags && artifact.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {artifact.tags.slice(0, 3).map((tag, idx) => (
                      <span key={idx}
                        className="px-1.5 py-0.5 text-xs bg-amber-500/10 text-amber-400 rounded border border-amber-500/20">
                        {tag}
                      </span>
                    ))}
                    {artifact.tags.length > 3 && (
                      <span className="px-1.5 py-0.5 text-xs text-text-muted">+{artifact.tags.length - 3}</span>
                    )}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ============================================================================
// Utility Functions
// ============================================================================

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays} days ago`
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`
  if (diffDays < 365) return `${Math.floor(diffDays / 30)} months ago`
  return date.toLocaleDateString()
}

