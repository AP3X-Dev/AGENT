"use client"

import { useState, useEffect, useCallback } from "react"
import {
  Wand2,
  Search,
  Grid3x3,
  List,
  Power,
  PowerOff,
  RefreshCw,
  Tag,
  FileText,
  ChevronRight,
} from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/utils"
import {
  ModuleContainer,
  EmptyModuleState,
  LoadingModuleState,
  ErrorModuleState,
} from "./module-container"
import { useAgentConnection } from "@/hooks/use-agent-connection"
import { FileDocumentViewer, DocumentMeta } from "@/components/shared/file-document-viewer"
import type { ModuleConfig, ModuleInstanceProps } from "@/types/modules"
import type { SkillMeta, SkillViewMode, SkillSearchCriteria } from "@/types/skills"

export const skillsLibraryModuleConfig: ModuleConfig = {
  metadata: {
    id: "skills-library",
    displayName: "Skills Library",
    description: "Browse, search, edit, and manage agent skills",
    icon: "Wand2",
    category: "data",
    version: "1.0.0",
  },
  hasHeader: true,
  initialState: {
    isLoading: false,
    error: null,
    data: { skills: [], selectedSkill: null },
  },
  agentConfig: {
    enabled: true,
    supportedCommands: ["search", "getSkill", "createSkill", "updateSkill", "toggleSkill"],
    emittedEvents: ["skill-selected", "skill-updated", "skill-created", "skill-toggled"],
    contextDescription:
      "Skills library for browsing, editing, and toggling agent skill definitions",
  },
}

interface SkillsLibraryContext {
  totalSkills: number
  selectedSkillId: string | null
  searchQuery: string
  viewMode: SkillViewMode
}

// Gateway skill status (enabled/disabled toggle from control panel)
interface GatewaySkill {
  id: string
  name: string
  description: string
  enabled: boolean
}

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

export function SkillsLibraryModule({ instanceId, initialData }: ModuleInstanceProps) {
  const [skills, setSkills] = useState<SkillMeta[]>([])
  const [selectedSkill, setSelectedSkill] = useState<SkillMeta | null>(null)
  const [viewMode, setViewMode] = useState<SkillViewMode>("grid")
  const [searchQuery, setSearchQuery] = useState("")
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [total, setTotal] = useState(0)
  const [isViewerFullWidth, setIsViewerFullWidth] = useState(false)

  // Gateway skill toggle state
  const [gatewaySkills, setGatewaySkills] = useState<Map<string, GatewaySkill>>(new Map())
  const [gatewayLoading, setGatewayLoading] = useState(false)

  const { updateContext, sendEvent, onCommand } = useAgentConnection({
    instanceId: instanceId || `skills-library-${Date.now()}`,
    moduleType: "skills-library",
    autoRegister: true,
    initialContext: {
      totalSkills: 0,
      selectedSkillId: null,
      searchQuery: "",
      viewMode: "grid",
    } as Partial<SkillsLibraryContext>,
  })

  // Load gateway skills for toggle state
  const loadGatewaySkills = useCallback(async () => {
    try {
      setGatewayLoading(true)
      const data = await fetchGatewayJson<any>("skills")
      const list = Array.isArray(data?.skills) ? data.skills : []
      const map = new Map<string, GatewaySkill>()
      list.forEach((s: any) => {
        map.set(String(s.id || s.name), {
          id: String(s.id || s.name),
          name: String(s.name || s.id),
          description: String(s.description || ""),
          enabled: Boolean(s.enabled),
        })
      })
      setGatewaySkills(map)
    } catch {
      // Gateway may be unavailable - toggle feature degrades gracefully
    } finally {
      setGatewayLoading(false)
    }
  }, [])

  const toggleSkill = useCallback(
    async (skillId: string, enabled: boolean) => {
      try {
        await fetchGatewayJson<any>(`skills/${encodeURIComponent(skillId)}/toggle`, {
          method: "POST",
          body: JSON.stringify({ enabled }),
        })
        setGatewaySkills((prev) => {
          const next = new Map(prev)
          const existing = next.get(skillId)
          if (existing) {
            next.set(skillId, { ...existing, enabled })
          }
          return next
        })
        sendEvent("skill-toggled", { skillId, enabled })
      } catch {
        // Refresh to get actual state
        loadGatewaySkills()
      }
    },
    [loadGatewaySkills, sendEvent]
  )

  const loadSkills = useCallback(
    async (criteria?: SkillSearchCriteria) => {
      try {
        setIsLoading(true)
        setError(null)

        const params = new URLSearchParams()
        if (criteria?.search) params.set("search", criteria.search)
        if (criteria?.tags?.length) params.set("tag", criteria.tags[0])
        if (criteria?.limit) params.set("limit", criteria.limit.toString())
        if (criteria?.offset) params.set("offset", criteria.offset.toString())

        const response = await fetch(`/api/skills/list?${params}`)
        if (!response.ok) throw new Error("Failed to load skills")

        const data = await response.json()
        setSkills(data.skills)
        setTotal(data.total)

        updateContext({
          totalSkills: data.total,
          searchQuery: criteria?.search || "",
        })
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load skills")
      } finally {
        setIsLoading(false)
      }
    },
    [updateContext]
  )

  useEffect(() => {
    loadSkills()
    loadGatewaySkills()
  }, [loadSkills, loadGatewaySkills])

  const handleSearch = useCallback(
    (query: string) => {
      setSearchQuery(query)
      loadSkills({ search: query })
    },
    [loadSkills]
  )

  const handleSelectSkill = useCallback(
    (skill: SkillMeta) => {
      setSelectedSkill(skill)
      updateContext({ selectedSkillId: skill.id })
      sendEvent("skill-selected", { skillId: skill.id })
    },
    [updateContext, sendEvent]
  )

  const handleRefresh = useCallback(() => {
    loadSkills({ search: searchQuery })
    loadGatewaySkills()
  }, [loadSkills, loadGatewaySkills, searchQuery])

  if (isLoading && skills.length === 0) {
    return (
      <ModuleContainer config={skillsLibraryModuleConfig}>
        <LoadingModuleState message="Loading skills..." />
      </ModuleContainer>
    )
  }

  if (error && skills.length === 0) {
    return (
      <ModuleContainer config={skillsLibraryModuleConfig}>
        <ErrorModuleState error={error} onRetry={() => loadSkills()} />
      </ModuleContainer>
    )
  }

  return (
    <ModuleContainer config={skillsLibraryModuleConfig}>
      <div className="flex flex-col h-full bg-surface">
        {/* Header toolbar */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border bg-surface">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
            <Input
              placeholder="Search skills..."
              value={searchQuery}
              onChange={(e) => handleSearch(e.target.value)}
              className="pl-9 h-9 bg-surface-input border-border"
            />
          </div>
          <div className="flex items-center gap-1 rounded-lg border border-border overflow-hidden">
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
            onClick={handleRefresh}
            className="p-2 rounded-md text-text-muted hover:text-text-primary hover:bg-surface-elevated transition-colors"
            title="Refresh"
          >
            <RefreshCw className={cn("h-4 w-4", isLoading && "animate-spin")} />
          </button>
          <span className="text-xs text-text-muted tabular-nums">{total} skills</span>
        </div>

        {/* Content area */}
        <div className="flex-1 overflow-hidden flex">
          {/* Skills list/grid */}
          {!selectedSkill && (
            <div className="w-full overflow-auto">
              {skills.length === 0 ? (
                <EmptyModuleState
                  icon={Wand2}
                  title="No skills found"
                  description="Skills will appear here once added"
                />
              ) : viewMode === "list" ? (
                <SkillsList
                  skills={skills}
                  selectedSkill={selectedSkill}
                  onSelectSkill={handleSelectSkill}
                  gatewaySkills={gatewaySkills}
                  onToggleSkill={toggleSkill}
                />
              ) : (
                <SkillsGrid
                  skills={skills}
                  selectedSkill={selectedSkill}
                  onSelectSkill={handleSelectSkill}
                  gatewaySkills={gatewaySkills}
                  onToggleSkill={toggleSkill}
                />
              )}
            </div>
          )}

          {/* Skill viewer/editor */}
          {selectedSkill && (
            <div className="w-full">
              <SkillDocumentViewer
                skill={selectedSkill}
                onClose={() => {
                  setSelectedSkill(null)
                  setIsViewerFullWidth(false)
                }}
                isFullWidth={isViewerFullWidth}
                onToggleFullWidth={() => setIsViewerFullWidth(!isViewerFullWidth)}
                onSave={() => loadSkills({ search: searchQuery })}
              />
            </div>
          )}
        </div>
      </div>
    </ModuleContainer>
  )
}

// ============================================================================
// Skills List View
// ============================================================================

interface SkillsViewProps {
  skills: SkillMeta[]
  selectedSkill: SkillMeta | null
  onSelectSkill: (skill: SkillMeta) => void
  gatewaySkills: Map<string, GatewaySkill>
  onToggleSkill: (id: string, enabled: boolean) => void
}

function SkillsList({
  skills,
  selectedSkill,
  onSelectSkill,
  gatewaySkills,
  onToggleSkill,
}: SkillsViewProps) {
  return (
    <div className="p-3 space-y-2">
      {skills.map((skill) => {
        const gw = gatewaySkills.get(skill.id) || gatewaySkills.get(skill.name)
        const isEnabled = gw?.enabled ?? true
        return (
          <button
            key={skill.id}
            onClick={() => onSelectSkill(skill)}
            className={cn(
              "w-full text-left p-4 rounded-xl border transition-all group",
              "hover:bg-surface-elevated hover:border-border-active hover:shadow-md",
              selectedSkill?.id === skill.id
                ? "bg-surface-elevated border-status-info ring-1 ring-status-info/20"
                : "bg-[#1a1a1a] border-border"
            )}
          >
            <div className="flex items-center gap-4">
              <div
                className={cn(
                  "p-2.5 rounded-lg shrink-0 transition-colors",
                  isEnabled
                    ? "bg-surface-accent text-blue-400"
                    : "bg-[#1E1E1E] text-text-muted"
                )}
              >
                <Wand2 className="h-5 w-5" />
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="text-sm font-semibold text-text-primary truncate">
                    {skill.name}
                  </h3>
                  {gw && (
                    <span
                      className={cn(
                        "text-[10px] px-1.5 py-0.5 rounded-full font-medium uppercase tracking-wider",
                        isEnabled
                          ? "bg-[#1a2f1a] border border-[#2a4a2a] text-emerald-400"
                          : "bg-[#2f1a1a] border border-[#4a2a2a] text-red-400"
                      )}
                    >
                      {isEnabled ? "Active" : "Disabled"}
                    </span>
                  )}
                </div>
                <p className="text-xs text-text-muted line-clamp-1">{skill.description}</p>
                {skill.tags && skill.tags.length > 0 && (
                  <div className="flex items-center gap-1.5 mt-2">
                    {skill.tags.slice(0, 4).map((tag) => (
                      <span
                        key={tag}
                        className="text-[10px] px-2 py-0.5 rounded-full bg-surface-elevated text-text-muted border border-border"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <div className="flex items-center gap-3 shrink-0">
                {gw && (
                  <div
                    onClick={(e) => {
                      e.stopPropagation()
                    }}
                  >
                    <Switch
                      checked={isEnabled}
                      onCheckedChange={(checked) =>
                        onToggleSkill(String(gw.id), checked)
                      }
                    />
                  </div>
                )}
                <ChevronRight className="h-4 w-4 text-text-muted opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
            </div>
          </button>
        )
      })}
    </div>
  )
}

// ============================================================================
// Skills Grid View
// ============================================================================

function SkillsGrid({
  skills,
  selectedSkill,
  onSelectSkill,
  gatewaySkills,
  onToggleSkill,
}: SkillsViewProps) {
  return (
    <div className="p-4 grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
      {skills.map((skill) => {
        const gw = gatewaySkills.get(skill.id) || gatewaySkills.get(skill.name)
        const isEnabled = gw?.enabled ?? true
        return (
          <button
            key={skill.id}
            onClick={() => onSelectSkill(skill)}
            className={cn(
              "text-left rounded-xl border transition-all group relative overflow-hidden",
              "hover:border-border-active hover:shadow-lg hover:-translate-y-0.5",
              selectedSkill?.id === skill.id
                ? "bg-surface-elevated border-status-info ring-1 ring-status-info/20"
                : "bg-[#1a1a1a] border-border hover:bg-surface-elevated"
            )}
          >
            {/* Top accent bar */}
            <div
              className={cn(
                "h-1 w-full",
                isEnabled ? "bg-gradient-to-r from-blue-500/60 to-blue-400/30" : "bg-border"
              )}
            />

            <div className="p-4 flex flex-col gap-3">
              <div className="flex items-start justify-between">
                <div
                  className={cn(
                    "p-2.5 rounded-lg transition-colors",
                    isEnabled
                      ? "bg-surface-accent text-blue-400"
                      : "bg-[#1E1E1E] text-text-muted"
                  )}
                >
                  <Wand2 className="h-5 w-5" />
                </div>
                {gw && (
                  <div
                    onClick={(e) => {
                      e.stopPropagation()
                    }}
                  >
                    <Switch
                      checked={isEnabled}
                      onCheckedChange={(checked) =>
                        onToggleSkill(String(gw.id), checked)
                      }
                    />
                  </div>
                )}
              </div>

              <div>
                <h3 className="text-sm font-semibold text-text-primary line-clamp-1 mb-1">
                  {skill.name}
                </h3>
                <p className="text-xs text-text-muted line-clamp-2 leading-relaxed">
                  {skill.description}
                </p>
              </div>

              {skill.tags && skill.tags.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap">
                  {skill.tags.slice(0, 3).map((tag) => (
                    <span
                      key={tag}
                      className="text-[10px] px-2 py-0.5 rounded-full bg-surface-elevated text-text-muted border border-border"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}

              <div className="flex items-center justify-between pt-2 border-t border-border mt-auto">
                {gw ? (
                  <span
                    className={cn(
                      "text-[10px] font-medium uppercase tracking-wider",
                      isEnabled ? "text-emerald-400" : "text-red-400"
                    )}
                  >
                    {isEnabled ? "Active" : "Disabled"}
                  </span>
                ) : (
                  <span className="text-[10px] text-text-muted">Skill</span>
                )}
                <FileText className="h-3.5 w-3.5 text-text-muted opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
            </div>
          </button>
        )
      })}
    </div>
  )
}

// ============================================================================
// Skill Document Viewer/Editor
// ============================================================================

interface SkillDocumentViewerProps {
  skill: SkillMeta
  onClose: () => void
  isFullWidth?: boolean
  onToggleFullWidth?: () => void
  onSave?: () => void
}

function SkillDocumentViewer({ skill, onClose, onSave }: SkillDocumentViewerProps) {
  const truncatedDesc =
    skill.description.length > 80
      ? skill.description.slice(0, 80) + "..."
      : skill.description

  const document: DocumentMeta = {
    id: skill.id,
    title: skill.name,
    contentType: "text/markdown",
    path: skill.path,
    subtitle: truncatedDesc,
  }

  const fetchContent = useCallback(async (): Promise<string> => {
    const response = await fetch(
      `/api/skills?path=${encodeURIComponent(skill.path)}`
    )
    if (!response.ok) throw new Error("Failed to load skill")
    const content = await response.text()
    const match = content.match(/^---\r?\n[\s\S]*?\r?\n---\r?\n([\s\S]*)$/)
    return match ? match[1] : content
  }, [skill.path])

  const handleSave = useCallback(
    async (content: string): Promise<boolean> => {
      const response = await fetch("/api/skills", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: skill.path, content }),
      })
      return response.ok
    },
    [skill.path]
  )

  return (
    <FileDocumentViewer
      document={document}
      icon={Wand2}
      fetchContent={fetchContent}
      onSave={handleSave}
      editable={true}
      onClose={onClose}
      onSaveComplete={onSave}
    />
  )
}
