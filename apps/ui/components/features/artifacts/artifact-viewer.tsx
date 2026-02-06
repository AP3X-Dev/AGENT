"use client"

import { useState, useEffect } from 'react'
import { FileText, Download, ExternalLink, Loader2, ChevronDown, ChevronUp } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/cjs/styles/prism'

interface ArtifactViewerProps {
  artifactId: string
  className?: string
  /** Whether to start in expanded state (default: false) */
  defaultExpanded?: boolean
  /** Number of characters to show in preview (default: 200) */
  previewLength?: number
}

export function ArtifactViewer({
  artifactId,
  className,
  defaultExpanded = false,
  previewLength = 200
}: ArtifactViewerProps) {
  const [content, setContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)

  useEffect(() => {
    async function fetchArtifact() {
      try {
        setLoading(true)
        const response = await fetch(`/api/artifacts?id=${artifactId}`)
        
        if (!response.ok) {
          throw new Error(`Failed to load artifact: ${response.statusText}`)
        }

        const text = await response.text()
        setContent(text)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load artifact')
      } finally {
        setLoading(false)
      }
    }

    fetchArtifact()
  }, [artifactId])

  const handleDownload = () => {
    if (!content) return

    const blob = new Blob([content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${artifactId}.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const handleOpenInNewTab = () => {
    if (!content) return

    const blob = new Blob([content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
  }

  const toggleExpanded = () => {
    setIsExpanded(!isExpanded)
  }

  // Generate preview text
  const getPreviewText = () => {
    if (!content) return ''
    if (content.length <= previewLength) return content
    return content.substring(0, previewLength) + '...'
  }

  const showExpandButton = content && content.length > previewLength

  if (loading) {
    return (
      <div className={cn("flex items-center gap-2 p-4 bg-surface rounded-lg border border-border", className)}>
        <Loader2 className="h-4 w-4 animate-spin text-text-muted" />
        <span className="text-sm text-text-muted">Loading artifact...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className={cn("p-4 bg-red-500/10 rounded-lg border border-red-500/30", className)}>
        <p className="text-sm text-red-400">{error}</p>
      </div>
    )
  }

  return (
    <div className={cn("bg-surface rounded-lg border border-border overflow-hidden", className)}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-surface-secondary border-b border-border">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-text-muted" />
          <span className="text-sm font-medium text-text-primary">Research Report</span>
          <span className="text-xs text-text-muted font-mono">{artifactId}</span>
        </div>

        <div className="flex items-center gap-1">
          {showExpandButton && (
            <Button
              variant="ghost"
              size="sm"
              onClick={toggleExpanded}
              className="h-7 px-2 text-xs"
            >
              {isExpanded ? (
                <>
                  <ChevronUp className="h-3 w-3 mr-1" />
                  Collapse
                </>
              ) : (
                <>
                  <ChevronDown className="h-3 w-3 mr-1" />
                  Expand
                </>
              )}
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={handleOpenInNewTab}
            className="h-7 px-2"
            title="Open in new tab"
          >
            <ExternalLink className="h-3 w-3" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleDownload}
            className="h-7 px-2"
            title="Download"
          >
            <Download className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {/* Content */}
      <div className={cn(
        "p-4 overflow-y-auto transition-all duration-200",
        isExpanded ? "max-h-[600px]" : "max-h-[150px]"
      )}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          className="prose prose-invert prose-sm max-w-none
            prose-headings:text-text-primary prose-headings:font-semibold prose-headings:mt-4 prose-headings:mb-2
            prose-h2:text-base prose-h2:text-cyan-400
            prose-h3:text-sm prose-h3:text-amber-400
            prose-p:text-gray-300 prose-p:leading-relaxed prose-p:my-2
            prose-a:text-cyan-400 prose-a:no-underline hover:prose-a:underline
            prose-strong:text-white prose-strong:font-semibold
            prose-code:text-amber-400 prose-code:bg-zinc-800 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:font-mono prose-code:before:content-none prose-code:after:content-none
            prose-pre:bg-transparent prose-pre:p-0 prose-pre:my-3
            prose-ul:my-2 prose-ul:pl-5 prose-ul:list-disc
            prose-ol:my-2 prose-ol:pl-5 prose-ol:list-decimal
            prose-li:text-gray-300 prose-li:my-0.5
            [&_ul]:list-disc [&_ol]:list-decimal [&_li]:marker:text-amber-500
            prose-blockquote:border-l-2 prose-blockquote:border-amber-500 prose-blockquote:bg-zinc-800/50 prose-blockquote:py-1 prose-blockquote:px-3 prose-blockquote:rounded-r prose-blockquote:text-gray-400"
          components={{
            code(props) {
              const { className, children, node, ...rest } = props
              const match = /language-(\w+)/.exec(className || '')
              const isCodeBlock = match || String(children).includes('\n')

              if (isCodeBlock) {
                return (
                  <SyntaxHighlighter
                    style={oneDark}
                    language={match ? match[1] : 'text'}
                    PreTag="div"
                    className="rounded-lg border border-zinc-700 !bg-zinc-900 !my-3"
                    customStyle={{ margin: 0, padding: '0.75rem', fontSize: '0.75rem' }}
                  >
                    {String(children).replace(/\n$/, '')}
                  </SyntaxHighlighter>
                )
              }

              return (
                <code className="text-amber-400 bg-zinc-800 px-1 py-0.5 rounded text-xs font-mono" {...rest}>
                  {children}
                </code>
              )
            },
          }}
        >
          {isExpanded ? (content || '') : getPreviewText()}
        </ReactMarkdown>

        {!isExpanded && showExpandButton && (
          <div className="mt-2 text-xs text-text-muted italic">
            Click "Expand" to see full content
          </div>
        )}
      </div>
    </div>
  )
}

