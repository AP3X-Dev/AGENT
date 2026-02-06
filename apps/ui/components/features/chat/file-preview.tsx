/**
 * FilePreview Component
 * Displays a preview of a file mentioned with @ in chat
 */

"use client"

import { useState, useEffect } from "react"
import { cn } from "@/lib/utils"
import { readFile, getLanguageFromPath } from "@/lib/cli/file-operations"
import { File, ChevronDown, ChevronRight, Copy, Check, ExternalLink } from "lucide-react"
import { Button } from "@/components/ui/button"

interface FilePreviewProps {
  path: string
  /** If provided, the preview renders this content and does not fetch via readFile(). */
  initialContent?: string
  /** Optional language override (otherwise derived from path). */
  initialLanguage?: string
  maxLines?: number
  className?: string
  onOpenFile?: (path: string) => void
}

export function FilePreview({
  path,
  initialContent,
  initialLanguage,
  maxLines = 10,
  className,
  onOpenFile,
}: FilePreviewProps) {
  const [content, setContent] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isExpanded, setIsExpanded] = useState(false)
  const [copied, setCopied] = useState(false)
  const [totalLines, setTotalLines] = useState(0)

  const language = initialLanguage || getLanguageFromPath(path)

  useEffect(() => {
    // If content is provided (e.g., from agent tool output), do not fetch from filesystem.
    if (typeof initialContent === 'string') {
      setContent(initialContent)
      setTotalLines(initialContent.split('\n').length)
      setError(null)
      setIsLoading(false)
      return
    }

    async function loadFile() {
      setIsLoading(true)
      setError(null)

      const result = await readFile({
        path,
        startLine: 1,
        endLine: isExpanded ? undefined : maxLines,
      })

      if (result.success && result.content !== undefined) {
        setContent(result.content)
        setTotalLines(result.lineCount || 0)
      } else {
        setError(result.error || 'Failed to load file')
      }

      setIsLoading(false)
    }

    loadFile()
  }, [path, maxLines, isExpanded, initialContent])

  const handleCopy = async () => {
    if (content) {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const hasMoreLines = typeof initialContent !== 'string' && totalLines > maxLines && !isExpanded

  return (
    <div
      className={cn(
        "rounded-md border border-interactive-border bg-surface-secondary overflow-hidden",
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 bg-surface border-b border-interactive-border">
        <File className="h-4 w-4 text-text-muted" />
        <span className="flex-1 font-mono text-sm text-text-primary truncate">
          {path}
        </span>
        <span className="text-xs text-text-muted">
          {language.toUpperCase()}
        </span>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6"
          onClick={handleCopy}
          title="Copy content"
        >
          {copied ? (
            <Check className="h-3 w-3 text-green-400" />
          ) : (
            <Copy className="h-3 w-3" />
          )}
        </Button>
        {onOpenFile && (
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={() => onOpenFile(path)}
            title="Open file"
          >
            <ExternalLink className="h-3 w-3" />
          </Button>
        )}
      </div>

      {/* Content */}
      <div className="relative">
        {isLoading ? (
          <div className="px-3 py-4 text-sm text-text-muted">Loading...</div>
        ) : error ? (
          <div className="px-3 py-4 text-sm text-red-400">{error}</div>
        ) : (
          <pre className="px-3 py-2 text-sm font-mono overflow-x-auto">
            <code className={`language-${language}`}>{content}</code>
          </pre>
        )}

        {/* Expand/Collapse */}
        {hasMoreLines && (
          <button
            onClick={() => setIsExpanded(true)}
            className="w-full px-3 py-2 text-xs text-text-muted hover:text-text-primary hover:bg-interactive-hover flex items-center justify-center gap-1 border-t border-interactive-border"
          >
            <ChevronDown className="h-3 w-3" />
            Show {totalLines - maxLines} more lines
          </button>
        )}
        {isExpanded && totalLines > maxLines && (
          <button
            onClick={() => setIsExpanded(false)}
            className="w-full px-3 py-2 text-xs text-text-muted hover:text-text-primary hover:bg-interactive-hover flex items-center justify-center gap-1 border-t border-interactive-border"
          >
            <ChevronRight className="h-3 w-3" />
            Collapse
          </button>
        )}
      </div>
    </div>
  )
}

