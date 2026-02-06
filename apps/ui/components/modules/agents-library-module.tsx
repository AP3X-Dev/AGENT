"use client"

import React, { useState, useEffect, useCallback, useMemo } from "react"
import {
  Users,
  Search,
  Grid3x3,
  List,
  ChevronRight,
  Bot,
  Code,
  Brain,
  Database,
  Sparkles,
  Cog,
  Filter,
  Copy,
  Check,
  X,
  Plus,
  Trash2,
  RefreshCw,
  ChevronDown,
  Wrench,
  Zap,
  Shield,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import {
  ModuleContainer,
  EmptyModuleState,
  LoadingModuleState,
  ErrorModuleState,
} from "./module-container"
import { useAgentConnection } from "@/hooks/use-agent-connection"
import type { ModuleConfig, ModuleInstanceProps } from "@/types/modules"
import type {
  Agent,
  AgentMode,
  AgentCategory,
  AgentStatus,
  AgentsListResponse,
} from "@/types/agents"

export const agentsLibraryModuleConfig: ModuleConfig = {
  metadata: {
    id: "agents-library",
    displayName: "Agents Library",
    description: "Browse, search, and manage AI agents and subagents",
    icon: "Users",
    category: "data",
    version: "1.0.0",
  },
  hasHeader: true,
  initialState: {
    isLoading: false,
    error: null,
    data: { agents: [], selectedAgent: null },
  },
  agentConfig: {
    enabled: true,
    supportedCommands: ["search", "getAgent", "listByMode", "createSubagent", "deleteSubagent"],
    emittedEvents: [
      "agent-selected",
      "search-performed",
      "subagent-created",
      "subagent-deleted",
    ],
    contextDescription:
      "Agents library for browsing, managing, creating, and deleting AI agents and subagents",
  },
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const getModeIcon = (mode: AgentMode) => {
  switch (mode) {
    case "main":
      return Bot
    case "subagent":
      return Users
    case "tool":
      return Cog
    case "custom":
      return Sparkles
    default:
      return Bot
  }
}
const getModeColor = (mode: AgentMode) => {
  switch (mode) {
    case "main":
      return "text-blue-400"
    case "subagent":
      return "text-purple-400"
    case "tool":
      return "text-emerald-400"
    case "custom":
      return "text-orange-400"
    default:
      return "text-text-muted"
  }
}
const getModeGradient = (mode: AgentMode) => {
  switch (mode) {
    case "main":
      return "from-blue-500/60 to-blue-400/20"
    case "subagent":
      return "from-purple-500/60 to-purple-400/20"
    case "tool":
      return "from-emerald-500/60 to-emerald-400/20"
    case "custom":
      return "from-orange-500/60 to-orange-400/20"
    default:
      return "from-gray-500/40 to-gray-400/10"
  }
}
const getCategoryIcon = (category: AgentCategory) => {
  switch (category) {
    case "coding":
      return Code
    case "research":
      return Brain
    case "data":
      return Database
    case "creative":
      return Sparkles
    case "automation":
      return Cog
    default:
      return Bot
  }
}
const getStatusBadge = (status: AgentStatus) => {
  switch (status) {
    case "active":
      return {
        label: "Active",
        className: "bg-[#1a2f1a] border border-[#2a4a2a] text-emerald-400",
      }
    case "inactive":
      return {
        label: "Inactive",
        className: "bg-[#1E1E1E] border border-[#2a2a2a] text-text-muted",
      }
    case "error":
      return {
        label: "Error",
        className: "bg-[#2f1a1a] border border-[#4a2a2a] text-red-400",
      }
    case "loading":
      return {
        label: "Loading",
        className: "bg-[#2a2a1a] border border-[#3a3a2a] text-amber-400",
      }
    default:
      return {
        label: "Unknown",
        className: "bg-[#1E1E1E] border border-[#2a2a2a] text-text-muted",
      }
  }
}
const getModeBadge = (mode: AgentMode) => {
  switch (mode) {
    case "main":
      return {
        label: "Main",
        className: "bg-[#1a1a2a] border border-[#2a2a3a] text-blue-400",
      }
    case "subagent":
      return {
        label: "Subagent",
        className: "bg-[#2a1a2a] border border-[#3a2a3a] text-purple-400",
      }
    case "tool":
      return {
        label: "Tool",
        className: "bg-[#1a2a1a] border border-[#2a3a2a] text-emerald-400",
      }
    case "custom":
      return {
        label: "Custom",
        className: "bg-[#2a1f1a] border border-[#3a2f2a] text-orange-400",
      }
    default:
      return {
        label: "Unknown",
        className: "bg-[#1E1E1E] border border-[#2a2a2a] text-text-muted",
      }
  }
}

const MODES: { value: AgentMode | "all"; label: string }[] = [
  { value: "all", label: "All Modes" },
  { value: "main", label: "Main Agents" },
  { value: "subagent", label: "Subagents" },
  { value: "tool", label: "Tool Agents" },
  { value: "custom", label: "Custom" },
]
const CATEGORIES: { value: AgentCategory | "all"; label: string }[] = [
  { value: "all", label: "All Categories" },
  { value: "general", label: "General" },
  { value: "coding", label: "Coding" },
  { value: "research", label: "Research" },
  { value: "data", label: "Data" },
  { value: "creative", label: "Creative" },
  { value: "automation", label: "Automation" },
  { value: "analysis", label: "Analysis" },
  { value: "custom", label: "Custom" },
]
const MODE_ORDER: AgentMode[] = ["main", "subagent", "tool", "custom"]
const MODE_LABELS: Record<AgentMode, string> = {
  main: "Main Agents",
  subagent: "Subagents",
  tool: "Tool Agents",
  custom: "Custom Agents",
}

// ---------------------------------------------------------------------------
// Gateway helpers
// ---------------------------------------------------------------------------

async function fetchGatewayJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/ag3nt/gateway/${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const msg =
      (data && (data.error || data.detail)) || res.statusText || "Gateway request failed"
    throw new Error(String(msg))
  }
  return data as T
}

// ---------------------------------------------------------------------------
// Agent Card
// ---------------------------------------------------------------------------

interface AgentCardProps {
  agent: Agent
  isSelected: boolean
  viewMode: "list" | "grid"
  onSelect: (agent: Agent) => void
  onDelete?: (name: string) => void
}

function AgentCard({ agent, isSelected, viewMode, onSelect, onDelete }: AgentCardProps) {
  const ModeIcon = getModeIcon(agent.mode)
  const statusBadge = getStatusBadge(agent.status)
  const modeBadge = getModeBadge(agent.mode)
  const isUserCreated = agent.metadata.tags.some((t) => t === "source:user")

  if (viewMode === "grid") {
    return (
      <button
        onClick={() => onSelect(agent)}
        className={cn(
          "flex flex-col text-left rounded-xl border transition-all group relative overflow-hidden",
          "hover:border-border-active hover:shadow-lg hover:-translate-y-0.5",
          isSelected
            ? "bg-surface-elevated border-status-info ring-1 ring-status-info/20"
            : "bg-[#1a1a1a] border-border hover:bg-surface-elevated"
        )}
      >
        {/* Top accent bar */}
        <div className={cn("h-1 w-full bg-gradient-to-r", getModeGradient(agent.mode))} />

        <div className="p-4 flex flex-col gap-3 flex-1">
          <div className="flex items-start justify-between">
            <div
              className={cn(
                "p-2.5 rounded-lg bg-surface-elevated",
                getModeColor(agent.mode)
              )}
            >
              <ModeIcon className="h-5 w-5" />
            </div>
            <span className={cn("text-[10px] px-2 py-0.5 rounded-full", statusBadge.className)}>
              {statusBadge.label}
            </span>
          </div>

          <div>
            <h3 className="font-semibold text-text-primary text-sm mb-1 truncate">
              {agent.name}
            </h3>
            <p className="text-xs text-text-muted line-clamp-2 leading-relaxed">
              {agent.description}
            </p>
          </div>

          <div className="flex items-center gap-2 mt-auto pt-3 border-t border-border">
            <span className={cn("text-[10px] px-1.5 py-0.5 rounded", modeBadge.className)}>
              {modeBadge.label}
            </span>
            <span className="text-[10px] text-text-muted truncate">
              {agent.model.provider}/{agent.model.model.split("-")[0]}
            </span>
            {isUserCreated && onDelete && (
              <button
                className="ml-auto p-1 rounded text-text-muted hover:text-red-400 hover:bg-[#2f1a1a] transition-colors opacity-0 group-hover:opacity-100"
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete(agent.name)
                }}
                title="Delete subagent"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>
      </button>
    )
  }

  // List view
  return (
    <button
      onClick={() => onSelect(agent)}
      className={cn(
        "flex items-center gap-4 p-4 rounded-xl border text-left transition-all w-full group",
        "hover:bg-surface-elevated hover:border-border-active hover:shadow-md",
        isSelected
          ? "bg-surface-elevated border-status-info ring-1 ring-status-info/20"
          : "bg-[#1a1a1a] border-border"
      )}
    >
      <div
        className={cn(
          "p-2.5 rounded-lg bg-surface-elevated shrink-0",
          getModeColor(agent.mode)
        )}
      >
        <ModeIcon className="h-5 w-5" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <h3 className="font-semibold text-text-primary text-sm truncate">{agent.name}</h3>
          <span className={cn("text-[10px] px-1.5 py-0.5 rounded shrink-0", modeBadge.className)}>
            {modeBadge.label}
          </span>
        </div>
        <p className="text-xs text-text-muted truncate">{agent.description}</p>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <span className={cn("text-[10px] px-2 py-0.5 rounded-full", statusBadge.className)}>
          {statusBadge.label}
        </span>
        {isUserCreated && onDelete && (
          <button
            className="p-1 rounded text-text-muted hover:text-red-400 hover:bg-[#2f1a1a] transition-colors opacity-0 group-hover:opacity-100"
            onClick={(e) => {
              e.stopPropagation()
              onDelete(agent.name)
            }}
            title="Delete subagent"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
        <ChevronRight className="h-4 w-4 text-text-muted opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>
    </button>
  )
}

// ---------------------------------------------------------------------------
// Agent Detail Panel
// ---------------------------------------------------------------------------

interface AgentDetailPanelProps {
  agent: Agent
  onClose: () => void
}

function AgentDetailPanel({ agent, onClose }: AgentDetailPanelProps) {
  const [copiedField, setCopiedField] = useState<string | null>(null)
  const copyToClipboard = (text: string, field: string) => {
    navigator.clipboard.writeText(text)
    setCopiedField(field)
    setTimeout(() => setCopiedField(null), 2000)
  }
  const ModeIcon = getModeIcon(agent.mode)
  const modeBadge = getModeBadge(agent.mode)
  const statusBadge = getStatusBadge(agent.status)

  return (
    <div className="flex flex-col h-full border-l border-border bg-surface">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-border">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              "p-2.5 rounded-lg bg-surface-elevated",
              getModeColor(agent.mode)
            )}
          >
            <ModeIcon className="h-5 w-5" />
          </div>
          <div>
            <h2 className="font-semibold text-text-primary">{agent.name}</h2>
            <div className="flex items-center gap-2 mt-0.5">
              <span className={cn("text-[10px] px-1.5 py-0.5 rounded", modeBadge.className)}>
                {modeBadge.label}
              </span>
              <span
                className={cn("text-[10px] px-1.5 py-0.5 rounded-full", statusBadge.className)}
              >
                {statusBadge.label}
              </span>
            </div>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-md hover:bg-surface-elevated text-text-muted hover:text-text-primary transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {/* Description */}
        <div>
          <h3 className="text-xs font-medium text-text-muted uppercase tracking-wider mb-2">
            Description
          </h3>
          <p className="text-sm text-text-primary leading-relaxed">{agent.description}</p>
        </div>

        {/* System Prompt */}
        {agent.systemPrompt && (
          <div>
            <h3 className="text-xs font-medium text-text-muted uppercase tracking-wider mb-2">
              System Prompt
            </h3>
            <div className="p-3 rounded-lg bg-[#1a1a1a] border border-border">
              <p className="text-xs text-text-muted whitespace-pre-wrap font-mono leading-relaxed">
                {agent.systemPrompt}
              </p>
            </div>
          </div>
        )}

        {/* Model */}
        <div>
          <h3 className="text-xs font-medium text-text-muted uppercase tracking-wider mb-2">
            Model
          </h3>
          <div className="p-3 rounded-lg bg-[#1a1a1a] border border-border space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-text-muted">Provider</span>
              <span className="text-sm text-text-primary">{agent.model.provider}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-text-muted">Model</span>
              <span className="text-sm text-text-primary font-mono">{agent.model.model}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-text-muted">Temperature</span>
              <span className="text-sm text-text-primary">{agent.model.temperature ?? 0.0}</span>
            </div>
          </div>
        </div>

        {/* Enabled Tools */}
        {agent.enabledTools.length > 0 && (
          <div>
            <h3 className="text-xs font-medium text-text-muted uppercase tracking-wider mb-2">
              <Wrench className="h-3 w-3 inline mr-1" />
              Enabled Tools ({agent.enabledTools.length})
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {agent.enabledTools.map((tool) => (
                <span
                  key={tool}
                  className="text-xs px-2 py-1 rounded-md bg-[#1a2f1a] border border-[#2a4a2a] text-emerald-400 font-mono"
                >
                  {tool}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Disabled Tools */}
        {agent.disabledTools.length > 0 && (
          <div>
            <h3 className="text-xs font-medium text-text-muted uppercase tracking-wider mb-2">
              <Shield className="h-3 w-3 inline mr-1" />
              Disabled Tools ({agent.disabledTools.length})
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {agent.disabledTools.map((tool) => (
                <span
                  key={tool}
                  className="text-xs px-2 py-1 rounded-md bg-[#2f1a1a] border border-[#4a2a2a] text-red-400 font-mono"
                >
                  {tool}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Middleware */}
        {agent.middleware.length > 0 && (
          <div>
            <h3 className="text-xs font-medium text-text-muted uppercase tracking-wider mb-2">
              <Zap className="h-3 w-3 inline mr-1" />
              Middleware ({agent.middleware.length})
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {agent.middleware.map((mw) => (
                <span
                  key={mw}
                  className="text-xs px-2 py-1 rounded-md bg-[#1a1a2a] border border-[#2a2a3a] text-blue-400 font-mono"
                >
                  {mw}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Metadata */}
        <div>
          <h3 className="text-xs font-medium text-text-muted uppercase tracking-wider mb-2">
            Metadata
          </h3>
          <div className="grid grid-cols-2 gap-2">
            <div className="p-2.5 rounded-lg bg-[#1a1a1a] border border-border">
              <span className="text-[10px] text-text-muted uppercase tracking-wider">
                Category
              </span>
              <p className="text-sm text-text-primary capitalize mt-0.5">
                {agent.metadata.category}
              </p>
            </div>
            <div className="p-2.5 rounded-lg bg-[#1a1a1a] border border-border">
              <span className="text-[10px] text-text-muted uppercase tracking-wider">
                Version
              </span>
              <p className="text-sm text-text-primary mt-0.5">
                {agent.metadata.version || "N/A"}
              </p>
            </div>
          </div>
        </div>

        {/* Tags */}
        {agent.metadata.tags.length > 0 && (
          <div>
            <h3 className="text-xs font-medium text-text-muted uppercase tracking-wider mb-2">
              Tags
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {agent.metadata.tags.map((tag) => (
                <span
                  key={tag}
                  className="text-xs px-2 py-1 rounded-full bg-surface-elevated text-text-muted border border-border"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Create Subagent Form
// ---------------------------------------------------------------------------

interface CreateSubagentFormProps {
  onCreated: () => void
}

function CreateSubagentForm({ onCreated }: CreateSubagentFormProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [systemPrompt, setSystemPrompt] = useState("")
  const [tools, setTools] = useState("")
  const [maxTokens, setMaxTokens] = useState("8000")
  const [maxTurns, setMaxTurns] = useState("3")

  const handleCreate = async () => {
    const n = name.trim()
    const d = description.trim()
    const sp = systemPrompt.trim()
    if (!n || !d || !sp) return

    const toolList = tools
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean)
    const mt = Number.parseInt(maxTokens, 10) || 8000
    const mtu = Number.parseInt(maxTurns, 10) || 3

    setCreating(true)
    try {
      await fetchGatewayJson<any>("subagents", {
        method: "POST",
        body: JSON.stringify({
          name: n,
          description: d,
          system_prompt: sp,
          tools: toolList,
          max_tokens: mt,
          max_turns: mtu,
        }),
      })
      setName("")
      setDescription("")
      setSystemPrompt("")
      setTools("")
      setMaxTokens("8000")
      setMaxTurns("3")
      setIsExpanded(false)
      onCreated()
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="rounded-xl border border-border bg-[#1a1a1a] overflow-hidden">
      <button
        className="w-full flex items-center gap-3 p-4 text-left hover:bg-surface-elevated transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="p-2 rounded-lg bg-surface-accent text-blue-400">
          <Plus className="h-4 w-4" />
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-text-primary">Create Subagent</h3>
          <p className="text-xs text-text-muted">Register a new subagent with the gateway</p>
        </div>
        <ChevronDown
          className={cn(
            "h-4 w-4 text-text-muted transition-transform",
            isExpanded && "rotate-180"
          )}
        />
      </button>

      {isExpanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-border pt-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs text-text-muted font-medium">Name *</label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. DEBUGGER"
                className="bg-surface-input border-border"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-text-muted font-medium">Tools (comma-separated)</label>
              <Input
                value={tools}
                onChange={(e) => setTools(e.target.value)}
                placeholder="fetch_url, shell"
                className="bg-surface-input border-border"
              />
            </div>
            <div className="space-y-1 col-span-2">
              <label className="text-xs text-text-muted font-medium">Description *</label>
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Brief description of what this subagent does"
                className="bg-surface-input border-border"
              />
            </div>
            <div className="space-y-1 col-span-2">
              <label className="text-xs text-text-muted font-medium">System Prompt *</label>
              <Textarea
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                rows={5}
                placeholder="You are a specialized agent that..."
                className="bg-surface-input border-border font-mono text-xs"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-text-muted font-medium">Max Tokens</label>
              <Input
                value={maxTokens}
                onChange={(e) => setMaxTokens(e.target.value)}
                className="bg-surface-input border-border"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-text-muted font-medium">Max Turns</label>
              <Input
                value={maxTurns}
                onChange={(e) => setMaxTurns(e.target.value)}
                className="bg-surface-input border-border"
              />
            </div>
          </div>
          <div className="flex items-center gap-2 pt-1">
            <Button
              size="sm"
              onClick={handleCreate}
              disabled={creating || !name.trim() || !description.trim() || !systemPrompt.trim()}
              className="gap-2"
            >
              {creating ? (
                <>
                  <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <Plus className="h-3.5 w-3.5" />
                  Create Subagent
                </>
              )}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setIsExpanded(false)}
              className="text-text-muted"
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Module
// ---------------------------------------------------------------------------

export function AgentsLibraryModule({
  instanceId,
  tabId,
  initialData,
  onStateChange,
  onTabUpdate,
  agentEnabled,
  moduleType,
}: ModuleInstanceProps) {
  const [agents, setAgents] = useState<Agent[]>([])
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [modeFilter, setModeFilter] = useState<AgentMode | "all">("all")
  const [categoryFilter, setCategoryFilter] = useState<AgentCategory | "all">("all")
  const [viewMode, setViewMode] = useState<"list" | "grid">("grid")
  const [showFilters, setShowFilters] = useState(false)

  const { updateContext, sendEvent, onCommand } = useAgentConnection({
    instanceId,
    moduleType: "agents-library",
  })

  const fetchAgents = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (searchQuery) params.set("search", searchQuery)
      if (modeFilter !== "all") params.set("mode", modeFilter)
      if (categoryFilter !== "all") params.set("category", categoryFilter)
      const response = await fetch(`/api/agents?${params.toString()}`)
      if (!response.ok) throw new Error("Failed to fetch agents")
      const data: AgentsListResponse = await response.json()
      setAgents(data.agents)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agents")
    } finally {
      setIsLoading(false)
    }
  }, [searchQuery, modeFilter, categoryFilter])

  useEffect(() => {
    fetchAgents()
  }, [fetchAgents])

  useEffect(() => {
    updateContext({
      agentCount: agents.length,
      selectedAgent: selectedAgent?.name || null,
      filters: { search: searchQuery, mode: modeFilter, category: categoryFilter },
    })
  }, [agents, selectedAgent, searchQuery, modeFilter, categoryFilter, updateContext])

  useEffect(() => {
    const sub1 = onCommand("search", async (params: { query?: string }) => {
      if (typeof params?.query === "string") {
        setSearchQuery(params.query)
        sendEvent("search-performed", { query: params.query })
      }
    })
    const sub2 = onCommand("getAgent", async (params: { name?: string }) => {
      if (typeof params?.name === "string") {
        const agent = agents.find((a) => a.name === params.name)
        if (agent) {
          setSelectedAgent(agent)
          sendEvent("agent-selected", { agent: agent.name })
        }
      }
    })
    const sub3 = onCommand("listByMode", async (params: { mode?: string }) => {
      if (typeof params?.mode === "string") {
        setModeFilter(params.mode as AgentMode)
      }
    })
    return () => {
      sub1.unsubscribe()
      sub2.unsubscribe()
      sub3.unsubscribe()
    }
  }, [onCommand, sendEvent, agents])

  const deleteSubagent = useCallback(
    async (name: string) => {
      if (typeof window !== "undefined") {
        const ok = window.confirm(`Delete subagent "${name}"?`)
        if (!ok) return
      }
      try {
        await fetchGatewayJson<any>(`subagents/${encodeURIComponent(name)}`, {
          method: "DELETE",
        })
        sendEvent("subagent-deleted", { name })
        fetchAgents()
      } catch {
        // refresh to show actual state
        fetchAgents()
      }
    },
    [fetchAgents, sendEvent]
  )

  const filteredAgents = useMemo(
    () =>
      agents.filter((agent) => {
        if (
          searchQuery &&
          !agent.name.toLowerCase().includes(searchQuery.toLowerCase()) &&
          !agent.description.toLowerCase().includes(searchQuery.toLowerCase())
        )
          return false
        if (modeFilter !== "all" && agent.mode !== modeFilter) return false
        if (categoryFilter !== "all" && agent.metadata.category !== categoryFilter)
          return false
        return true
      }),
    [agents, searchQuery, modeFilter, categoryFilter]
  )

  const agentsByMode = useMemo(() => {
    const grouped = filteredAgents.reduce(
      (acc, agent) => {
        if (!acc[agent.mode]) acc[agent.mode] = []
        acc[agent.mode].push(agent)
        return acc
      },
      {} as Record<AgentMode, Agent[]>
    )
    return MODE_ORDER.filter((mode) => grouped[mode]?.length > 0).map((mode) => ({
      mode,
      label: MODE_LABELS[mode],
      agents: grouped[mode],
    }))
  }, [filteredAgents])

  if (isLoading) return <LoadingModuleState message="Loading agents..." />
  if (error) return <ErrorModuleState error={error} onRetry={fetchAgents} />

  return (
    <ModuleContainer className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-2 p-3 border-b border-border bg-surface">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
          <input
            type="text"
            placeholder="Search agents..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-2 text-sm bg-surface-input border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-status-info text-text-primary placeholder:text-text-muted"
          />
        </div>
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={cn(
            "p-2 rounded-lg border transition-colors",
            showFilters
              ? "bg-surface-accent border-blue-500/30 text-blue-400"
              : "bg-surface-elevated border-border text-text-muted hover:text-text-primary"
          )}
        >
          <Filter className="h-4 w-4" />
        </button>
        <div className="flex items-center rounded-lg border border-border overflow-hidden">
          <button
            onClick={() => setViewMode("list")}
            className={cn(
              "p-2 transition-colors",
              viewMode === "list"
                ? "bg-surface-accent text-blue-400"
                : "bg-surface-elevated text-text-muted hover:text-text-primary"
            )}
          >
            <List className="h-4 w-4" />
          </button>
          <button
            onClick={() => setViewMode("grid")}
            className={cn(
              "p-2 transition-colors",
              viewMode === "grid"
                ? "bg-surface-accent text-blue-400"
                : "bg-surface-elevated text-text-muted hover:text-text-primary"
            )}
          >
            <Grid3x3 className="h-4 w-4" />
          </button>
        </div>
        <button
          onClick={fetchAgents}
          className="p-2 rounded-md text-text-muted hover:text-text-primary hover:bg-surface-elevated transition-colors"
          title="Refresh"
        >
          <RefreshCw className={cn("h-4 w-4", isLoading && "animate-spin")} />
        </button>
      </div>

      {/* Filters bar */}
      {showFilters && (
        <div className="flex items-center gap-2 p-3 border-b border-border bg-[#1a1a1a]">
          <select
            value={modeFilter}
            onChange={(e) => setModeFilter(e.target.value as AgentMode | "all")}
            className="px-3 py-1.5 text-sm bg-surface-input border border-border rounded-lg text-text-primary focus:outline-none focus:ring-1 focus:ring-status-info"
          >
            {MODES.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value as AgentCategory | "all")}
            className="px-3 py-1.5 text-sm bg-surface-input border border-border rounded-lg text-text-primary focus:outline-none focus:ring-1 focus:ring-status-info"
          >
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
          <span className="text-xs text-text-muted ml-auto tabular-nums">
            {filteredAgents.length} agents
          </span>
        </div>
      )}

      {/* Content */}
      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-y-auto p-3 pb-8 space-y-4">
          {/* Create subagent form */}
          <CreateSubagentForm
            onCreated={() => {
              sendEvent("subagent-created", {})
              fetchAgents()
            }}
          />

          {/* Agent list */}
          {filteredAgents.length === 0 ? (
            <EmptyModuleState
              icon={Users}
              title="No agents found"
              description={
                searchQuery
                  ? "Try adjusting your search or filters"
                  : "No agents available"
              }
            />
          ) : (
            <div className="space-y-6">
              {agentsByMode.map(({ mode, label, agents: modeAgents }) => (
                <div key={mode} className="space-y-3">
                  <h2 className="text-xs font-semibold text-text-muted uppercase tracking-wider flex items-center gap-2 pb-2 border-b border-border">
                    {React.createElement(getModeIcon(mode), {
                      className: cn("h-4 w-4", getModeColor(mode)),
                    })}
                    {label}{" "}
                    <span className="text-text-muted/60">({modeAgents.length})</span>
                  </h2>
                  <div
                    className={cn(
                      viewMode === "grid"
                        ? "grid grid-cols-2 xl:grid-cols-3 gap-3"
                        : "space-y-2"
                    )}
                  >
                    {modeAgents.map((agent) => (
                      <AgentCard
                        key={agent.name}
                        agent={agent}
                        isSelected={selectedAgent?.name === agent.name}
                        viewMode={viewMode}
                        onSelect={setSelectedAgent}
                        onDelete={deleteSubagent}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Detail panel */}
        {selectedAgent && (
          <div className="w-[420px] shrink-0">
            <AgentDetailPanel
              agent={selectedAgent}
              onClose={() => setSelectedAgent(null)}
            />
          </div>
        )}
      </div>
    </ModuleContainer>
  )
}
