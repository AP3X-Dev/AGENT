"use client"

import { useState, useEffect, useCallback, useMemo } from 'react'
import { FileText, Download, ExternalLink, X, Edit2, Save, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkFrontmatter from 'remark-frontmatter'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/cjs/styles/prism'

// Parse YAML frontmatter from markdown content
function parseFrontmatter(content: string): { frontmatter: Record<string, unknown> | null; body: string } {
  const frontmatterMatch = content.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/)
  if (!frontmatterMatch) {
    return { frontmatter: null, body: content }
  }

  const yamlContent = frontmatterMatch[1]
  const body = frontmatterMatch[2]

  // Simple YAML parsing for common fields
  const frontmatter: Record<string, unknown> = {}
  const lines = yamlContent.split(/\r?\n/)
  for (const line of lines) {
    const match = line.match(/^([^:]+):\s*(.*)$/)
    if (match) {
      const key = match[1].trim()
      let value: unknown = match[2].trim()
      // Handle quoted strings
      if ((value as string).startsWith('"') && (value as string).endsWith('"')) {
        value = (value as string).slice(1, -1)
      }
      // Handle arrays
      if ((value as string).startsWith('[') && (value as string).endsWith(']')) {
        try {
          value = JSON.parse(value as string)
        } catch {
          // Keep as string if parsing fails
        }
      }
      frontmatter[key] = value
    }
  }

  return { frontmatter, body }
}

// Detect if content looks like markdown (has markdown patterns)
function looksLikeMarkdown(content: string): boolean {
  // Check for common markdown patterns
  const markdownPatterns = [
    /^#{1,6}\s+.+$/m,           // Headers: # Header
    /\*\*[^*]+\*\*/,            // Bold: **text**
    /\*[^*]+\*/,                // Italic: *text*
    /^\s*[-*+]\s+.+$/m,         // Unordered lists: - item or * item
    /^\s*\d+\.\s+.+$/m,         // Ordered lists: 1. item
    /\[.+\]\(.+\)/,             // Links: [text](url)
    /```[\s\S]*?```/,           // Code blocks: ```code```
    /`[^`]+`/,                  // Inline code: `code`
    /^\s*>\s+.+$/m,             // Blockquotes: > quote
    /\|.+\|.+\|/,               // Tables: | col | col |
  ]

  // Count how many patterns match
  let matchCount = 0
  for (const pattern of markdownPatterns) {
    if (pattern.test(content)) {
      matchCount++
    }
  }

  // If at least 2 markdown patterns found, treat as markdown
  return matchCount >= 2
}

// Check if content should be rendered as markdown
function shouldRenderAsMarkdown(contentType: string, path: string | undefined, content: string): boolean {
  const ct = contentType.toLowerCase()

  // Explicit markdown types
  if (ct.includes('markdown') || ct.includes('md')) return true

  // File extension check
  if (path?.endsWith('.md')) return true

  // For text/plain or text/html, check if content looks like markdown
  if (ct.includes('text/plain') || ct === 'text' || ct === '') {
    return looksLikeMarkdown(content)
  }

  return false
}

export interface DocumentMeta {
  id: string
  title: string
  contentType: string
  size?: number
  path?: string
  version?: string
  subtitle?: string
}

export interface FileDocumentViewerProps {
  document: DocumentMeta
  icon?: React.ComponentType<{ className?: string }>
  fetchContent: () => Promise<string>
  onSave?: (content: string) => Promise<boolean>
  editable?: boolean
  onClose?: () => void
  onSaveComplete?: () => void
  className?: string
  /** Optional custom content to render below the header title/subtitle */
  headerContent?: React.ReactNode
}

function formatFileSize(bytes?: number): string {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function FileDocumentViewer({
  document,
  icon: Icon = FileText,
  fetchContent,
  onSave,
  editable = false,
  onClose,
  onSaveComplete,
  className,
  headerContent,
}: FileDocumentViewerProps) {
  const [content, setContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    async function loadContent() {
      try {
        setLoading(true)
        setError(null)
        const text = await fetchContent()
        setContent(text)
        setEditContent(text)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load document')
      } finally {
        setLoading(false)
      }
    }
    loadContent()
  }, [fetchContent])

  const handleSave = useCallback(async () => {
    if (!onSave) return
    try {
      setSaving(true)
      const success = await onSave(editContent)
      if (success) {
        setContent(editContent)
        setIsEditing(false)
        onSaveComplete?.()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save document')
    } finally {
      setSaving(false)
    }
  }, [editContent, onSave, onSaveComplete])

  const handleDownload = useCallback(() => {
    if (!content) return
    const blob = new Blob([content], { type: document.contentType })
    const url = URL.createObjectURL(blob)
    const a = window.document.createElement('a')
    a.href = url
    a.download = document.title || document.id
    window.document.body.appendChild(a)
    a.click()
    window.document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }, [content, document])

  const handleOpenInNewTab = useCallback(() => {
    if (!content) return
    const blob = new Blob([content], { type: document.contentType })
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
  }, [content, document.contentType])

  const handleCancelEdit = useCallback(() => {
    setEditContent(content || '')
    setIsEditing(false)
  }, [content])

  // Determine if content should render as markdown
  const isMarkdown = useMemo(() => {
    if (!content) return false
    return shouldRenderAsMarkdown(document.contentType, document.path, content)
  }, [content, document.contentType, document.path])

  // Parse frontmatter for markdown content
  const { frontmatter, markdownBody } = useMemo(() => {
    if (!content) return { frontmatter: null, markdownBody: '' }
    if (isMarkdown) {
      const parsed = parseFrontmatter(content)
      return { frontmatter: parsed.frontmatter, markdownBody: parsed.body }
    }
    return { frontmatter: null, markdownBody: content }
  }, [content, isMarkdown])

  const renderContent = () => {
    if (!content) return null
    const contentType = document.contentType.toLowerCase()

    // Render as markdown if detected
    if (isMarkdown) {
      return (
        <>
          {/* Frontmatter metadata display */}
          {frontmatter && Object.keys(frontmatter).length > 0 && (
            <div className="mb-6 p-4 bg-zinc-800/50 border border-zinc-700 rounded-lg">
              <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
                {Object.entries(frontmatter).map(([key, value]) => {
                  // Skip long values
                  const strValue = Array.isArray(value) ? value.join(', ') : String(value)
                  if (strValue.length > 100) return null
                  return (
                    <div key={key} className="flex items-center gap-2">
                      <span className="text-zinc-500 font-medium">{key}:</span>
                      <span className="text-gray-300">
                        {Array.isArray(value) ? (
                          <span className="flex gap-1 flex-wrap">
                            {value.map((v, i) => (
                              <span key={i} className="px-1.5 py-0.5 bg-zinc-700 rounded text-xs text-amber-400">{String(v)}</span>
                            ))}
                          </span>
                        ) : strValue}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
          <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkFrontmatter]}
            className="prose prose-invert prose-base max-w-none
              prose-headings:text-text-primary prose-headings:font-semibold prose-headings:mt-6 prose-headings:mb-3
              prose-h1:text-2xl prose-h1:border-b prose-h1:border-border prose-h1:pb-3
              prose-h2:text-xl prose-h2:border-b prose-h2:border-border/50 prose-h2:pb-2 prose-h2:text-cyan-400
              prose-h3:text-lg prose-h3:text-amber-400
              prose-p:text-gray-300 prose-p:leading-relaxed prose-p:my-3
              prose-a:text-cyan-400 prose-a:no-underline hover:prose-a:underline
              prose-strong:text-white prose-strong:font-semibold
              prose-em:text-gray-200
              prose-code:text-amber-400 prose-code:bg-zinc-800 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:font-mono prose-code:before:content-none prose-code:after:content-none
              prose-pre:bg-transparent prose-pre:p-0 prose-pre:my-4
              prose-ul:my-3 prose-ul:pl-6 prose-ul:list-disc
              prose-ol:my-3 prose-ol:pl-6 prose-ol:list-decimal
              prose-li:text-gray-300 prose-li:my-1 prose-li:pl-1
              [&_ul]:list-disc [&_ol]:list-decimal [&_li]:marker:text-amber-500
              prose-blockquote:border-l-4 prose-blockquote:border-amber-500 prose-blockquote:bg-zinc-800/50 prose-blockquote:py-2 prose-blockquote:px-4 prose-blockquote:rounded-r prose-blockquote:italic prose-blockquote:text-gray-400
              prose-hr:border-border prose-hr:my-8
              prose-table:border-collapse prose-table:my-6
              prose-th:bg-zinc-800 prose-th:border prose-th:border-zinc-700 prose-th:px-4 prose-th:py-2 prose-th:text-left prose-th:font-semibold prose-th:text-white
              prose-td:border prose-td:border-zinc-700 prose-td:px-4 prose-td:py-2 prose-td:text-gray-300"
            components={{
              code(props) {
                const { className, children, node, ...rest } = props
                const match = /language-(\w+)/.exec(className || '')
                // Check if it's a code block (has language class or contains newlines)
                const isCodeBlock = match || String(children).includes('\n')

                if (isCodeBlock) {
                  return (
                    <SyntaxHighlighter
                      style={oneDark}
                      language={match ? match[1] : 'text'}
                      PreTag="div"
                      className="rounded-lg border border-zinc-700 !bg-zinc-900 !my-4"
                      customStyle={{ margin: 0, padding: '1rem', fontSize: '0.875rem' }}
                    >
                      {String(children).replace(/\n$/, '')}
                    </SyntaxHighlighter>
                  )
                }

                return (
                  <code className="text-amber-400 bg-zinc-800 px-1.5 py-0.5 rounded text-sm font-mono" {...rest}>
                    {children}
                  </code>
                )
              },
            }}
          >
            {markdownBody}
          </ReactMarkdown>
        </>
      )
    }
    if (contentType.includes('json')) {
      try {
        const parsed = JSON.parse(content)
        return (
          <SyntaxHighlighter
            style={oneDark}
            language="json"
            PreTag="div"
            className="rounded-lg border border-zinc-700 !bg-zinc-900"
            customStyle={{ margin: 0, padding: '1rem', fontSize: '0.875rem' }}
          >
            {JSON.stringify(parsed, null, 2)}
          </SyntaxHighlighter>
        )
      } catch {
        return <pre className="text-sm font-mono overflow-x-auto text-gray-300 bg-zinc-900 p-4 rounded-lg border border-zinc-700"><code>{content}</code></pre>
      }
    }
    if (contentType.includes('html')) {
      return <iframe srcDoc={content} className="w-full h-full border-0" sandbox="allow-same-origin" />
    }
    return <pre className="text-sm font-mono overflow-x-auto whitespace-pre-wrap text-gray-300 leading-relaxed">{content}</pre>
  }

  if (loading) {
    return (
      <div className={cn("flex items-center justify-center h-full bg-surface", className)}>
        <div className="flex flex-col items-center gap-2">
          <Loader2 className="h-8 w-8 animate-spin text-text-muted" />
          <span className="text-sm text-text-muted">Loading document...</span>
        </div>
      </div>
    )
  }

  if (error && !content) {
    return (
      <div className={cn("flex items-center justify-center h-full bg-surface", className)}>
        <div className="text-center">
          <p className="text-sm text-red-400">{error}</p>
        </div>
      </div>
    )
  }


  return (
    <div className={cn("flex flex-col h-full bg-surface", className)}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-surface-secondary">
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <Icon className="h-5 w-5 text-text-muted flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <h2 className="text-sm font-medium text-text-primary truncate">{document.title}</h2>
            <div className="flex items-center gap-2 text-xs text-text-muted">
              <span>{document.subtitle || document.contentType}</span>
              {document.size && (
                <>
                  <span>•</span>
                  <span>{formatFileSize(document.size)}</span>
                </>
              )}
              {document.version && (
                <>
                  <span>•</span>
                  <span>v{document.version}</span>
                </>
              )}
            </div>
            {/* Optional custom header content */}
            {headerContent}
          </div>
        </div>
        <div className="flex items-center gap-1">
          {editable && onSave && (
            isEditing ? (
              <>
                <Button variant="ghost" size="sm" onClick={handleSave} disabled={saving}
                  className="h-8 px-3 text-green-400 hover:text-green-300">
                  <Save className="h-4 w-4 mr-1" />
                  {saving ? 'Saving...' : 'Save'}
                </Button>
                <Button variant="ghost" size="sm" onClick={handleCancelEdit} className="h-8 px-2">
                  Cancel
                </Button>
              </>
            ) : (
              <Button variant="ghost" size="sm" onClick={() => setIsEditing(true)}
                className="h-8 px-2" title="Edit document">
                <Edit2 className="h-4 w-4" />
              </Button>
            )
          )}
          <Button variant="ghost" size="sm" onClick={handleOpenInNewTab}
            className="h-8 px-2" title="Open in new tab">
            <ExternalLink className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" onClick={handleDownload}
            className="h-8 px-2" title="Download">
            <Download className="h-4 w-4" />
          </Button>
          {onClose && (
            <Button variant="ghost" size="sm" onClick={onClose} className="h-8 px-2" title="Close">
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
      {/* Content */}
      <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
        {isEditing ? (
          <div className="flex-1 min-h-0 p-4">
            <textarea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              className="w-full h-full bg-zinc-900 text-gray-200 font-mono text-sm resize-none focus:outline-none border border-zinc-700 rounded-lg p-4"
              spellCheck={false}
            />
          </div>
        ) : (
          <div className="flex-1 min-h-0 overflow-auto">
            <div className="p-6 pb-24">
              {renderContent()}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}