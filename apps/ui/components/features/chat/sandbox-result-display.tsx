"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import {
  Check,
  X,
  ChevronDown,
  ChevronRight,
  Terminal,
  AlertCircle,
  Image as ImageIcon,
  FileText,
  Download
} from "lucide-react"
import { Button } from "@/components/ui/button"

interface SandboxResult {
  type: "text" | "image" | "html" | "json" | "error"
  format?: "png" | "jpeg"
  data?: string
  content?: string
}

interface SandboxExecutionOutput {
  success: boolean
  session_id?: string
  results?: SandboxResult[]
  stdout?: string[]
  stderr?: string[]
  error?: {
    name: string
    message: string
    traceback?: string
  }
  description?: string
}

interface SandboxResultDisplayProps {
  output: SandboxExecutionOutput | string
  className?: string
}

/**
 * Specialized display component for E2B sandbox execution results.
 * Handles text output, images, errors with proper formatting.
 */
export function SandboxResultDisplay({ output, className }: SandboxResultDisplayProps) {
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(["stdout", "results"]))

  // Parse output if it's a string
  const parsed: SandboxExecutionOutput | null = typeof output === "string"
    ? tryParseJSON(output)
    : output

  if (!parsed) {
    // Fallback to plain text display
    return (
      <pre className={cn("text-[12px] font-mono text-text-secondary whitespace-pre-wrap", className)}>
        {typeof output === "string" ? output : JSON.stringify(output, null, 2)}
      </pre>
    )
  }

  const toggleSection = (section: string) => {
    const newSet = new Set(expandedSections)
    if (newSet.has(section)) {
      newSet.delete(section)
    } else {
      newSet.add(section)
    }
    setExpandedSections(newSet)
  }

  const hasStdout = parsed.stdout && parsed.stdout.length > 0
  const hasStderr = parsed.stderr && parsed.stderr.length > 0
  const hasResults = parsed.results && parsed.results.length > 0
  const hasError = !!parsed.error
  const hasImages = parsed.results?.some(r => r.type === "image")

  return (
    <div className={cn("space-y-2", className)}>
      {/* Status header */}
      <div className="flex items-center gap-2">
        {parsed.success ? (
          <div className="flex items-center gap-1.5 text-green-400">
            <Check className="h-4 w-4" />
            <span className="text-[12px] font-medium">Execution successful</span>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 text-red-400">
            <X className="h-4 w-4" />
            <span className="text-[12px] font-medium">Execution failed</span>
          </div>
        )}
        {parsed.session_id && (
          <span className="text-[11px] text-text-muted">
            Session: {parsed.session_id.slice(0, 12)}...
          </span>
        )}
      </div>

      {/* Description if provided */}
      {parsed.description && (
        <div className="text-[12px] text-text-muted italic">
          {parsed.description}
        </div>
      )}

      {/* Stdout section */}
      {hasStdout && (
        <CollapsibleSection
          title="Output"
          icon={<Terminal className="h-3.5 w-3.5" />}
          isExpanded={expandedSections.has("stdout")}
          onToggle={() => toggleSection("stdout")}
          count={parsed.stdout!.length}
        >
          <pre className="text-[11px] font-mono text-text-secondary whitespace-pre-wrap bg-[#0a0a0a] p-2 rounded border border-[#252525]">
            {parsed.stdout!.join("\n")}
          </pre>
        </CollapsibleSection>
      )}

      {/* Stderr section (warnings) */}
      {hasStderr && (
        <CollapsibleSection
          title="Warnings"
          icon={<AlertCircle className="h-3.5 w-3.5 text-yellow-500" />}
          isExpanded={expandedSections.has("stderr")}
          onToggle={() => toggleSection("stderr")}
          count={parsed.stderr!.length}
          variant="warning"
        >
          <pre className="text-[11px] font-mono text-yellow-400/80 whitespace-pre-wrap bg-[#1a1800] p-2 rounded border border-[#3a3800]">
            {parsed.stderr!.join("\n")}
          </pre>
        </CollapsibleSection>
      )}

      {/* Results section (including images) */}
      {hasResults && (
        <CollapsibleSection
          title={hasImages ? "Results & Images" : "Results"}
          icon={hasImages ? <ImageIcon className="h-3.5 w-3.5" /> : <FileText className="h-3.5 w-3.5" />}
          isExpanded={expandedSections.has("results")}
          onToggle={() => toggleSection("results")}
          count={parsed.results!.length}
        >
          <div className="space-y-2">
            {parsed.results!.map((result, idx) => (
              <ResultItem key={idx} result={result} index={idx} />
            ))}
          </div>
        </CollapsibleSection>
      )}

      {/* Error section */}
      {hasError && (
        <div className="bg-[#1a1111] border border-[#3a2525] rounded p-2">
          <div className="flex items-center gap-2 mb-1">
            <AlertCircle className="h-3.5 w-3.5 text-red-400" />
            <span className="text-[12px] font-medium text-red-400">
              {parsed.error!.name}: {parsed.error!.message}
            </span>
          </div>
          {parsed.error!.traceback && (
            <pre className="text-[11px] font-mono text-red-300/80 whitespace-pre-wrap mt-2 bg-[#0a0505] p-2 rounded">
              {parsed.error!.traceback}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Helper Components
// ============================================================================

interface CollapsibleSectionProps {
  title: string
  icon: React.ReactNode
  isExpanded: boolean
  onToggle: () => void
  count?: number
  variant?: "default" | "warning" | "error"
  children: React.ReactNode
}

function CollapsibleSection({
  title,
  icon,
  isExpanded,
  onToggle,
  count,
  variant = "default",
  children
}: CollapsibleSectionProps) {
  return (
    <div>
      <button
        onClick={onToggle}
        className="flex items-center gap-2 w-full text-left py-1 hover:bg-white/[0.02] rounded transition-colors"
      >
        {isExpanded ? (
          <ChevronDown className="h-3 w-3 text-text-muted" />
        ) : (
          <ChevronRight className="h-3 w-3 text-text-muted" />
        )}
        {icon}
        <span className={cn(
          "text-[12px] font-medium",
          variant === "warning" && "text-yellow-400",
          variant === "error" && "text-red-400",
          variant === "default" && "text-text-primary"
        )}>
          {title}
        </span>
        {count !== undefined && (
          <span className="text-[11px] text-text-muted">({count})</span>
        )}
      </button>
      {isExpanded && (
        <div className="ml-5 mt-1">
          {children}
        </div>
      )}
    </div>
  )
}

interface ResultItemProps {
  result: SandboxResult
  index: number
}

function ResultItem({ result, index }: ResultItemProps) {
  const [imageError, setImageError] = useState(false)

  if (result.type === "image" && (result.data) && !imageError) {
    const format = result.format || "png"
    const src = `data:image/${format};base64,${result.data}`

    return (
      <div className="relative group">
        <div className="text-[11px] text-text-muted mb-1">Image {index + 1}</div>
        <div className="relative bg-[#0a0a0a] rounded border border-[#252525] p-2 inline-block max-w-full">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={src}
            alt={`Sandbox output ${index + 1}`}
            className="max-w-full max-h-[400px] object-contain rounded"
            onError={() => setImageError(true)}
          />
          <Button
            variant="ghost"
            size="sm"
            className="absolute top-2 right-2 h-7 px-2 opacity-0 group-hover:opacity-100 transition-opacity bg-[#1a1a1a] border border-[#2a2a2a]"
            onClick={() => downloadImage(src, `sandbox-output-${index + 1}.${format}`)}
          >
            <Download className="h-3.5 w-3.5 mr-1" />
            <span className="text-[11px]">Save</span>
          </Button>
        </div>
      </div>
    )
  }

  if (result.type === "text" && result.content) {
    return (
      <pre className="text-[11px] font-mono text-text-secondary whitespace-pre-wrap bg-[#0a0a0a] p-2 rounded border border-[#252525]">
        {result.content}
      </pre>
    )
  }

  if (result.type === "json" && result.data) {
    return (
      <pre className="text-[11px] font-mono text-text-secondary whitespace-pre-wrap bg-[#0a0a0a] p-2 rounded border border-[#252525]">
        {typeof result.data === "string" ? result.data : JSON.stringify(result.data, null, 2)}
      </pre>
    )
  }

  if (result.type === "html" && result.content) {
    return (
      <div
        className="bg-white rounded p-2 overflow-x-auto"
        dangerouslySetInnerHTML={{ __html: result.content }}
      />
    )
  }

  return null
}

// ============================================================================
// Utility Functions
// ============================================================================

function tryParseJSON(str: string): SandboxExecutionOutput | null {
  try {
    return JSON.parse(str)
  } catch {
    return null
  }
}

function downloadImage(dataUrl: string, filename: string) {
  const link = document.createElement("a")
  link.href = dataUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}
