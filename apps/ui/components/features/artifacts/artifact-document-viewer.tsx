"use client"

import { useCallback } from 'react'
import { FileText, Globe, Wrench, Calendar, HardDrive } from 'lucide-react'
import { FileDocumentViewer, DocumentMeta } from '@/components/shared/file-document-viewer'
import type { ArtifactMetadata } from '@/types/artifacts'

interface ArtifactDocumentViewerProps {
  artifact: ArtifactMetadata
  onClose?: () => void
  className?: string
  /** Whether the viewer is in full width mode */
  isFullWidth?: boolean
  /** Callback to toggle full width mode */
  onToggleFullWidth?: () => void
  /** Called after successful save */
  onSaveComplete?: () => void
}

// Format file size
function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// Format date nicely
function formatDate(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// Build a rich subtitle with artifact metadata
function buildSubtitle(artifact: ArtifactMetadata): string {
  const parts: string[] = []

  // Content type (simplified)
  const typeMap: Record<string, string> = {
    'text/markdown': 'Markdown',
    'text/plain': 'Text',
    'application/json': 'JSON',
    'text/html': 'HTML',
    'text/csv': 'CSV',
  }
  parts.push(typeMap[artifact.content_type] || artifact.content_type.split('/').pop() || 'Document')

  // Size
  parts.push(formatFileSize(artifact.size_bytes))

  // Tool name if present
  if (artifact.tool_name) {
    parts.push(`via ${artifact.tool_name}`)
  }

  return parts.join(' • ')
}

export function ArtifactDocumentViewer({
  artifact,
  onClose,
  className,
  onSaveComplete
}: ArtifactDocumentViewerProps) {
  // Convert artifact metadata to document format with rich subtitle
  const document: DocumentMeta = {
    id: artifact.artifact_id,
    title: artifact.title || artifact.artifact_id,
    contentType: artifact.content_type,
    size: artifact.size_bytes,
    path: artifact.stored_raw_path,
    subtitle: buildSubtitle(artifact),
  }

  // Fetch content from API
  const fetchContent = useCallback(async (): Promise<string> => {
    const response = await fetch(`/api/artifacts?id=${artifact.artifact_id}`)
    if (!response.ok) {
      throw new Error(`Failed to load artifact: ${response.statusText}`)
    }
    return response.text()
  }, [artifact.artifact_id])

  // Save content via API
  const handleSave = useCallback(async (content: string): Promise<boolean> => {
    const response = await fetch('/api/artifacts/save', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        artifactId: artifact.artifact_id,
        content,
      }),
    })
    return response.ok
  }, [artifact.artifact_id])

  // Custom header content with additional metadata
  const headerContent = (
    <div className="flex flex-wrap items-center gap-3 text-xs text-text-muted mt-1">
      {artifact.source_url && (
        <a
          href={artifact.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-cyan-400 hover:text-cyan-300 hover:underline"
          onClick={(e) => e.stopPropagation()}
        >
          <Globe className="h-3 w-3" />
          <span className="truncate max-w-[200px]">{new URL(artifact.source_url).hostname}</span>
        </a>
      )}
      {artifact.created_at && (
        <span className="flex items-center gap-1">
          <Calendar className="h-3 w-3" />
          {formatDate(artifact.created_at)}
        </span>
      )}
      {artifact.tags && artifact.tags.length > 0 && (
        <div className="flex items-center gap-1 flex-wrap">
          {artifact.tags.slice(0, 4).map((tag, idx) => (
            <span
              key={idx}
              className="px-1.5 py-0.5 bg-amber-500/10 text-amber-400 rounded text-xs"
            >
              {tag}
            </span>
          ))}
          {artifact.tags.length > 4 && (
            <span className="text-text-muted text-xs">+{artifact.tags.length - 4}</span>
          )}
        </div>
      )}
    </div>
  )

  return (
    <FileDocumentViewer
      document={document}
      icon={FileText}
      fetchContent={fetchContent}
      onSave={handleSave}
      editable={true}
      onClose={onClose}
      onSaveComplete={onSaveComplete}
      className={className}
      headerContent={headerContent}
    />
  )
}
