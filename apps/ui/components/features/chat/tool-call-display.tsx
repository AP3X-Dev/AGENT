/**
 * ToolCallDisplay Component
 * Displays tool calls in compact inline style matching Augment's UI
 */

"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import {
  Terminal,
  FileText,
  Search,
  Globe,
  Wrench,
  ExternalLink,
  ListTodo,
  FolderOpen,
  Loader2,
  Copy,
  Check,
  Sparkles,
  Image as ImageIcon,
  Code,
  Package,
  Upload,
  Download,
  Play,
  Trash2,
  Bot,
  Zap
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { SandboxResultDisplay } from "./sandbox-result-display"

// E2B sandbox tool names for special handling
const SANDBOX_TOOLS = new Set([
  "execute_code",
  "install_packages",
  "sandbox_upload_file",
  "sandbox_download_file",
  "sandbox_list_files",
  "sandbox_run_command",
  "sandbox_cleanup",
])

interface ToolCallDisplayProps {
  toolName: string
  args?: Record<string, any>
  output?: string
  status?: "pending" | "success" | "error"
  error?: string
  className?: string
  /** Number to show in badge (e.g., count of tasks) */
  count?: number
  /** Whether this tool is waiting for approval */
  waitingForApproval?: boolean
  /** Approval handlers */
  onApprove?: () => void
  onSkip?: () => void
}

// Animated loading dots component for pending state
function LoadingDots({ className, color = "bg-amber-400" }: { className?: string; color?: string }) {
  return (
    <span className={cn("flex items-center gap-1", className)}>
      <span
        className={cn("w-1.5 h-1.5 rounded-full animate-staggered-bounce", color)}
        style={{ animationDelay: '0ms' }}
      />
      <span
        className={cn("w-1.5 h-1.5 rounded-full animate-staggered-bounce", color)}
        style={{ animationDelay: '150ms' }}
      />
      <span
        className={cn("w-1.5 h-1.5 rounded-full animate-staggered-bounce", color)}
        style={{ animationDelay: '300ms' }}
      />
    </span>
  )
}

// Map tool names to icons
const toolIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  shell: Terminal,
  execute: Terminal,
  bash: Terminal,
  read_file: FileText,
  read: FileText,
  write_file: FileText,
  write: FileText,
  edit_file: FileText,
  edit: FileText,
  web_search: Search,
  web: Globe,
  web_fetch: Globe,
  http_request: Globe,
  add_tasks: ListTodo,
  update_task_list: ListTodo,
  update_tasks: ListTodo,
  read_directory: FolderOpen,
  list_directory: FolderOpen,
  generate_image: ImageIcon,
  edit_image: ImageIcon,
  deep_research: Sparkles,
  // Exec/Process tools
  exec_command: Terminal,
  process_tool: Terminal,
  // Patch tools
  apply_patch: FileText,
  // Subagent/Task tool
  task: Bot,
  // E2B Sandbox tools
  execute_code: Code,
  install_packages: Package,
  sandbox_upload_file: Upload,
  sandbox_download_file: Download,
  sandbox_list_files: FolderOpen,
  sandbox_run_command: Play,
  sandbox_cleanup: Trash2,
  default: Wrench,
}

// Get icon for tool
function getToolIcon(toolName: string) {
  const Icon = toolIcons[toolName.toLowerCase()] || toolIcons.default
  return Icon
}

// Extract key arguments for display
function getKeyArgs(toolName: string, args?: Record<string, any>): string {
  if (!args) return ""
  
  const name = toolName.toLowerCase()
  
  // File operations - show file path
  if (name.includes("file")) {
    const path = args.file_path || args.path || args.filename
    if (path) {
      const fileName = String(path).split(/[/\\]/).pop() || path
      return String(fileName)
    }
  }
  
  // Shell commands - show first part of command
  if (name === "shell" || name === "execute" || name === "bash") {
    const cmd = args.command || args.cmd
    if (cmd) {
      const cmdStr = String(cmd)
      return cmdStr.length > 40 ? cmdStr.slice(0, 40) + "..." : cmdStr
    }
  }
  
  // Web search - show query
  if (name === "web_search") {
    const query = args.query || args.q
    if (query) {
      const queryStr = String(query)
      return queryStr.length > 40 ? queryStr.slice(0, 40) + "..." : queryStr
    }
  }
  
  // HTTP request - show URL
  if (name === "http_request") {
    const url = args.url
    if (url) {
      const urlStr = String(url)
      return urlStr.length > 40 ? urlStr.slice(0, 40) + "..." : urlStr
    }
  }

  // E2B execute_code - show language and code preview
  if (name === "execute_code") {
    const lang = args.language || "python"
    const code = args.code
    if (code) {
      const codeStr = String(code)
      const firstLine = codeStr.split('\n')[0]
      const preview = firstLine.length > 30 ? firstLine.slice(0, 30) + "..." : firstLine
      return `[${lang}] ${preview}`
    }
    return `[${lang}]`
  }

  // E2B install_packages - show packages
  if (name === "install_packages") {
    const packages = args.packages
    if (Array.isArray(packages)) {
      return packages.slice(0, 3).join(", ") + (packages.length > 3 ? "..." : "")
    }
  }

  // E2B sandbox commands - show command
  if (name === "sandbox_run_command") {
    const cmd = args.command
    if (cmd) {
      const cmdStr = String(cmd)
      return cmdStr.length > 40 ? cmdStr.slice(0, 40) + "..." : cmdStr
    }
  }

  // exec_command - show command preview + background badge
  if (name === "exec_command") {
    const cmd = args.command || args.cmd
    if (cmd) {
      const cmdStr = String(cmd)
      const bg = args.background ? " [bg]" : ""
      const preview = cmdStr.length > 40 ? cmdStr.slice(0, 40) + "..." : cmdStr
      return preview + bg
    }
  }

  // process_tool - show action: session_id
  if (name === "process_tool") {
    const action = args.action || ""
    const sessionId = args.session_id || ""
    if (sessionId) {
      return `${action}: ${sessionId}`
    }
    return String(action)
  }

  // apply_patch - show file count from patch markers
  if (name === "apply_patch") {
    const patch = args.patch || ""
    const patchStr = String(patch)
    const fileCount = (patchStr.match(/\*\*\*\s+(Add|Update|Delete)\s+File:/gi) || []).length
    if (fileCount > 0) {
      return `${fileCount} file(s)`
    }
    return ""
  }

  // Task/subagent - show task description preview
  if (name === "task") {
    const desc = args.description
    if (desc) {
      const descStr = String(desc)
      return descStr.length > 50 ? descStr.slice(0, 50) + "..." : descStr
    }
  }

  // Default: show first key-value pair
  const entries = Object.entries(args)
  if (entries.length > 0) {
    const [key, value] = entries[0]
    const valueStr = String(value)
    const display = valueStr.length > 30 ? valueStr.slice(0, 30) + "..." : valueStr
    return `${key}: ${display}`
  }
  
  return ""
}

// Parse tool name to extract the actual tool name from various formats
// e.g., "function<tool_sep>web_search" -> "web_search"
function parseToolName(name: string): string {
  // Handle "function<tool_sep>toolname" format
  if (name.includes('<tool_sep>')) {
    const parts = name.split('<tool_sep>')
    return parts[parts.length - 1] || name
  }
  // Handle "function::toolname" format
  if (name.includes('::')) {
    const parts = name.split('::')
    return parts[parts.length - 1] || name
  }
  return name
}

// Format tool name for display (e.g., "web_fetch" -> "Web Fetch")
function formatToolName(name: string, args?: Record<string, any>): string {
  // First parse to get the actual tool name
  const parsed = parseToolName(name)

  // Special case for task tool - show the subagent type as the agent name
  if (parsed === "task" && args?.subagent_type) {
    const agentType = String(args.subagent_type)
    // Format: "deep-research" -> "Deep Research Agent"
    const formatted = agentType
      .split(/[_-]/)
      .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ')
    return `${formatted} Agent`
  }

  return parsed
    .split(/[_-]/)
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ')
}

export function ToolCallDisplay({
  toolName,
  args,
  output,
  status = "success",
  error,
  className,
  count,
  waitingForApproval = false,
  onApprove,
  onSkip,
}: ToolCallDisplayProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [copied, setCopied] = useState(false)

  // Parse the tool name first to handle formats like "function<tool_sep>web_search"
  const parsedToolName = parseToolName(toolName)
  const Icon = getToolIcon(parsedToolName)
  const keyArgs = getKeyArgs(parsedToolName, args)
  const displayName = formatToolName(toolName, args)

  // Debug logging
  if (parsedToolName === 'web_search') {
    console.log('[ToolCallDisplay] web_search:', { toolName, parsedToolName, args, keyArgs, waitingForApproval, status })
  }

  const handleCopy = async () => {
    const textToCopy = output || JSON.stringify(args, null, 2)
    await navigator.clipboard.writeText(textToCopy)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Pending state: DON'T show anything - AgentStatus at bottom handles this
  if (status === "pending" && !waitingForApproval) {
    return null
  }

  // Completed state: full-width bar with expand/collapse and smooth animations
  return (
    <div className={cn("group animate-in fade-in slide-in-from-top-2 duration-300", className)}>
      <div
        className={cn(
          "rounded-md bg-[#1a1a1a] border border-[#2a2a2a] px-3 py-2 cursor-pointer",
          "transition-all duration-200 ease-out",
          "hover:bg-[#1f1f1f] hover:border-[#3a3a3a]"
        )}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2 text-[13px]">
          {/* Tool icon */}
          <Icon className={cn(
            "h-4 w-4 flex-shrink-0 transition-colors duration-200",
            status === "error" ? "text-red-400" : "text-text-secondary"
          )} />

          {/* Tool name */}
          <span className="font-medium text-text-primary transition-colors duration-200">{displayName}</span>

          {/* Key arguments */}
          {keyArgs && (
            <span className="text-text-muted truncate flex-1 transition-colors duration-200">
              {keyArgs}
            </span>
          )}

          {/* Status dot with pulse animation on success */}
          <div className={cn(
            "h-2 w-2 rounded-full flex-shrink-0 transition-all duration-300",
            status === "success" && "bg-green-500 animate-pulse",
            status === "error" && "bg-red-500"
          )} />
        </div>
      </div>

      {/* Approval bar */}
      {waitingForApproval && (
        <div className="mt-2 flex items-center gap-2 py-2 px-3 bg-[#1a1a1a] rounded-md border border-[#2a2a2a]">
          <span className="text-[13px] text-text-muted flex-1">
            Waiting for approval
          </span>
          <button
            className="px-3 py-1.5 rounded-md bg-[#2a2a2a] text-text-muted text-[12px] hover:bg-[#3a3a3a]"
            onClick={(e) => {
              e.stopPropagation()
              onSkip?.()
            }}
          >
            Skip
          </button>
          <button
            className="px-3 py-1.5 rounded-md bg-green-600 text-white text-[12px] hover:bg-green-700"
            onClick={(e) => {
              e.stopPropagation()
              onApprove?.()
            }}
          >
            Approve
          </button>
        </div>
      )}

      {/* Expanded content - show output/details */}
      {isExpanded && !waitingForApproval && (output || args) && (
        <div className="mt-2 bg-[#131313] border border-[#252525] rounded-md overflow-hidden px-3 py-2 animate-in slide-in-from-top-1 fade-in duration-200">
          {/* Output - compact display */}
          {output && (
            <div className="mb-2">
              <div className="text-[11px] text-text-muted uppercase tracking-wide mb-1.5">Output</div>
              {SANDBOX_TOOLS.has(parsedToolName.toLowerCase()) ? (
                <SandboxResultDisplay
                  output={output}
                  className="max-h-[300px] overflow-y-auto"
                />
              ) : (
                <pre className="text-[12px] font-mono text-text-secondary overflow-x-auto bg-[#0a0a0a] p-2 rounded border border-[#1f1f1f] max-h-[200px] overflow-y-auto whitespace-pre-wrap leading-relaxed">
                  {output}
                </pre>
              )}
            </div>
          )}

          {/* Arguments - compact display */}
          {args && Object.keys(args).length > 0 && (
            <div>
              <div className="text-[11px] text-text-muted uppercase tracking-wide mb-1.5">Arguments</div>
              <pre className="text-[12px] font-mono text-text-secondary overflow-x-auto bg-[#0a0a0a] p-2 rounded border border-[#1f1f1f] leading-relaxed">
                {JSON.stringify(args, null, 2)}
              </pre>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="mt-2">
              <div className="text-[11px] text-red-400 uppercase tracking-wide mb-1.5">Error</div>
              <pre className="text-[12px] font-mono text-red-400 overflow-x-auto bg-[#1a1111] p-2 rounded border border-[#3a2525] whitespace-pre-wrap leading-relaxed">
                {error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

