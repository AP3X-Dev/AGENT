/**
 * CommandOutput Component
 * Displays bash command output with syntax highlighting
 */

"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { parseCommandOutput, type OutputSegment } from "@/lib/cli/shell"
import { Terminal, Copy, Check, ChevronDown, ChevronRight, AlertCircle, CheckCircle } from "lucide-react"
import { Button } from "@/components/ui/button"

interface CommandOutputProps {
  command: string
  output: string
  exitCode: number
  executionTime?: number
  className?: string
}

const segmentStyles: Record<OutputSegment["type"], string> = {
  normal: "text-text-primary",
  error: "text-red-400",
  warning: "text-yellow-400",
  success: "text-green-400",
  info: "text-blue-400",
}

export function CommandOutput({
  command,
  output,
  exitCode,
  executionTime,
  className,
}: CommandOutputProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [copied, setCopied] = useState(false)

  const segments = parseCommandOutput(output)
  const isSuccess = exitCode === 0
  const lines = output.split('\n')
  const isLongOutput = lines.length > 20

  const handleCopy = async () => {
    await navigator.clipboard.writeText(output)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className={cn("group mb-1", className)}>
      {/* Header - sleek modern design */}
      <div
        className={cn(
          "flex items-center gap-2.5 px-3 py-2 cursor-pointer transition-all duration-200",
          "bg-[#1a1a1a] hover:bg-[#222222] rounded-md border border-[#2a2a2a]",
          "hover:border-[#3a3a3a]"
        )}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <Terminal className={cn("h-3.5 w-3.5", isSuccess ? "text-green-400" : "text-red-400")} />
        <code className="flex-1 font-mono text-sm text-white truncate">
          {command}
        </code>

        {/* Execution time */}
        {executionTime !== undefined && (
          <span className="text-xs text-gray-500 font-mono">
            {executionTime}ms
          </span>
        )}

        {/* Status indicator - small dot */}
        <div className={cn(
          "h-1.5 w-1.5 rounded-full flex-shrink-0",
          isSuccess ? "bg-green-400" : "bg-red-400"
        )} />

        {/* Expand/Collapse */}
        {isExpanded ? (
          <ChevronDown className="h-3.5 w-3.5 text-gray-500" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-gray-500" />
        )}
      </div>

      {/* Output */}
      {isExpanded && (
        <div className="mt-1 bg-[#1a1a1a] border border-[#2a2a2a] rounded-md overflow-hidden relative">
          {/* Copy button */}
          <Button
            variant="ghost"
            size="icon"
            className="absolute top-2 right-2 h-6 w-6 opacity-50 hover:opacity-100 z-10"
            onClick={(e) => {
              e.stopPropagation()
              handleCopy()
            }}
            title="Copy output"
          >
            {copied ? (
              <Check className="h-3 w-3 text-green-400" />
            ) : (
              <Copy className="h-3 w-3" />
            )}
          </Button>

          {/* Output content */}
          <pre className={cn(
            "px-3 py-3 text-xs font-mono overflow-x-auto bg-[#0f0f0f] text-gray-300",
            isLongOutput && !isExpanded ? "max-h-[200px]" : "max-h-[400px]",
            "overflow-y-auto"
          )}>
            {segments.map((segment, index) => (
              <div key={index} className={segmentStyles[segment.type]}>
                {segment.text}
              </div>
            ))}
          </pre>

          {/* Exit code footer */}
          <div className={cn(
            "px-3 py-1.5 text-xs border-t border-[#2a2a2a] font-mono",
            isSuccess ? "text-green-400" : "text-red-400"
          )}>
            Exit code: {exitCode}
          </div>
        </div>
      )}
    </div>
  )
}

