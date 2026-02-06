"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
  Activity,
  FileText,
  FolderOpen,
  Laptop,
  RefreshCw,
  ShieldCheck,
  Signal,
  Terminal,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { ModuleContainer, EmptyModuleState, ErrorModuleState, LoadingModuleState } from "./module-container"
import { useAgentConnection } from "@/hooks/use-agent-connection"
import type { ModuleConfig, ModuleInstanceProps } from "@/types/modules"

type ViewId =
  | "dashboard"
  | "nodes"
  | "logs"
  | "workspace"
  | "memory"
  | "sessions"

export const ag3ntControlPanelModuleConfig: ModuleConfig = {
  metadata: {
    id: "ag3nt-control-panel",
    displayName: "AG3NT Control Panel",
    description: "Gateway dashboard, nodes, logs, workspace, and memory",
    icon: "Activity",
    category: "utility",
    version: "1.0.0",
  },
  hasHeader: true,
  initialState: { isLoading: true, error: null, data: {} },
  agentConfig: {
    enabled: true,
    supportedCommands: ["refresh", "setView"],
    emittedEvents: ["view-changed", "refreshed"],
    contextDescription: "AG3NT Gateway control panel (status, nodes, logs, workspace, memory)",
  },
}

const VIEWS: Array<{ id: ViewId; label: string; icon: any }> = [
  { id: "dashboard", label: "Dashboard", icon: Activity },
  { id: "nodes", label: "Nodes", icon: Laptop },
  { id: "logs", label: "Logs", icon: Terminal },
  { id: "workspace", label: "Workspace", icon: FolderOpen },
  { id: "memory", label: "Memory", icon: FileText },
  { id: "sessions", label: "Sessions", icon: ShieldCheck },
]

const DEFAULT_GATEWAY_URL = process.env.NEXT_PUBLIC_AG3NT_GATEWAY_URL || "http://127.0.0.1:18789"

function toWsUrl(httpUrl: string): string {
  return httpUrl.replace(/^http/i, "ws").replace(/\/+$/, "") + "/ws?debug=true"
}

async function fetchGatewayJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/ag3nt/gateway/${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const msg = (data && (data.error || data.detail)) || res.statusText || "Gateway request failed"
    throw new Error(String(msg))
  }
  return data as T
}

type GatewayLog = {
  id?: string
  timestamp?: string
  level?: "debug" | "info" | "warn" | "error"
  source?: string
  message?: string
  type?: string
}

export function Ag3ntControlPanelModule({ instanceId, agentEnabled = true, className }: ModuleInstanceProps) {
  const [view, setView] = useState<ViewId>("dashboard")
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionMessage, setActionMessage] = useState<string | null>(null)

  const { updateContext, sendEvent, onCommand } = useAgentConnection({
    instanceId: instanceId || `ag3nt-control-panel-${Date.now()}`,
    moduleType: "ag3nt-control-panel",
    autoRegister: agentEnabled,
    initialContext: { view, state: { isLoading: true, error: null } },
  })

  // ---------------------------------------------------------------------------
  // Shared helpers
  // ---------------------------------------------------------------------------

  const setViewSafe = useCallback(
    (next: ViewId) => {
      setView(next)
      if (agentEnabled) {
        updateContext({ view: next, lastUpdated: Date.now() } as any)
        sendEvent("view-changed", { view: next })
      }
    },
    [agentEnabled, sendEvent, updateContext]
  )

  const refreshCurrent = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      await load(view)
      if (agentEnabled) sendEvent("refreshed", { view })
    } catch (e: any) {
      setError(e?.message || "Failed to refresh")
    } finally {
      setIsLoading(false)
    }
  }, [agentEnabled, sendEvent, view])

  // Agent commands
  useEffect(() => {
    const sub1 = onCommand("refresh", async () => refreshCurrent())
    const sub2 = onCommand("setView", async (params: { view?: string }) => {
      const v = String(params?.view || "")
      if (VIEWS.some((x) => x.id === v)) setViewSafe(v as ViewId)
    })
    return () => {
      sub1.unsubscribe()
      sub2.unsubscribe()
    }
  }, [onCommand, refreshCurrent, setViewSafe])

  // ---------------------------------------------------------------------------
  // View state
  // ---------------------------------------------------------------------------

  const [dashboard, setDashboard] = useState<any>(null)
  const [modelOptions, setModelOptions] = useState<Record<string, any>>({})
  const [modelProvider, setModelProvider] = useState<string>("")
  const [modelName, setModelName] = useState<string>("")
  const [modelSaving, setModelSaving] = useState(false)
  const [agentWorker, setAgentWorker] = useState<any>(null)
  const [agentWorkerLoading, setAgentWorkerLoading] = useState(false)
  const [nodes, setNodes] = useState<any>(null)
  const [sessions, setSessions] = useState<any>(null)
  const [approveSessionId, setApproveSessionId] = useState<string>("")
  const [approveSessionCode, setApproveSessionCode] = useState<string>("")

  const [logs, setLogs] = useState<GatewayLog[]>([])
  const [logLevel, setLogLevel] = useState<"debug" | "info" | "warn" | "error">("info")
  const [logsLive, setLogsLive] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  const [workspaceTree, setWorkspaceTree] = useState<any>(null)
  const [workspaceSelected, setWorkspaceSelected] = useState<string | null>(null)
  const [workspaceContent, setWorkspaceContent] = useState<string>("")

  const [memoryFiles, setMemoryFiles] = useState<any[]>([])
  const [memorySelected, setMemorySelected] = useState<string | null>(null)
  const [memoryContent, setMemoryContent] = useState<string>("")
  const [memorySaving, setMemorySaving] = useState(false)

  const load = useCallback(async (v: ViewId) => {
    if (agentEnabled) {
      updateContext({ state: { isLoading: true, error: null } } as any)
    }

    if (v === "dashboard") {
      const [healthRes, statusRes, modelRes, agentRes] = await Promise.allSettled([
        fetchGatewayJson<any>("health"),
        fetchGatewayJson<any>("status"),
        fetchGatewayJson<any>("model/config"),
        fetchGatewayJson<any>("agent/health"),
      ])

      const health = healthRes.status === "fulfilled" ? healthRes.value : {}
      const status = statusRes.status === "fulfilled" ? statusRes.value : {}
      setDashboard({ health, status })

      if (modelRes.status === "fulfilled") {
        const provider = String(modelRes.value?.provider || "")
        const model = String(modelRes.value?.model || "")
        const options = (modelRes.value?.options && typeof modelRes.value.options === "object") ? modelRes.value.options : {}

        setModelOptions(options)
        setModelProvider(provider)

        const models = Array.isArray(options?.[provider]?.models) ? options[provider].models : []
        const hasModel = models.some((m: any) => String(m?.id) === model)
        setModelName(hasModel ? model : String(models?.[0]?.id || model || ""))
      } else {
        setModelOptions({})
        setModelProvider("")
        setModelName("")
      }

      if (agentRes.status === "fulfilled") {
        setAgentWorker(agentRes.value)
      } else {
        setAgentWorker(null)
      }
      return
    }

    if (v === "nodes") {
      const [nodesRes, approvedRes, pairingRes] = await Promise.all([
        fetchGatewayJson<any>("nodes"),
        fetchGatewayJson<any>("nodes/approved"),
        fetchGatewayJson<any>("nodes/pairing/active"),
      ])
      setNodes({ nodesRes, approvedRes, pairingRes })
      return
    }

    if (v === "logs") {
      const recent = await fetchGatewayJson<any>(`logs/recent?count=200&level=${logLevel}`)
      setLogs(Array.isArray(recent?.logs) ? recent.logs : [])
      return
    }

    if (v === "workspace") {
      const tree = await fetchGatewayJson<any>("workspace/files")
      setWorkspaceTree(tree)
      return
    }

    if (v === "memory") {
      const files = await fetchGatewayJson<any>("memory/files")
      setMemoryFiles(Array.isArray(files?.files) ? files.files : [])
      return
    }

    if (v === "sessions") {
      const [all, pending] = await Promise.all([
        fetchGatewayJson<any>("sessions"),
        fetchGatewayJson<any>("sessions/pending"),
      ])
      setSessions({ all, pending })
      return
    }
  }, [agentEnabled, logLevel, updateContext])

  useEffect(() => {
    setIsLoading(true)
    setError(null)
    load(view)
      .catch((e: any) => setError(e?.message || "Failed to load"))
      .finally(() => setIsLoading(false))
  }, [load, view])

  useEffect(() => {
    if (agentEnabled) {
      updateContext({ view, state: { isLoading, error } } as any)
    }
  }, [agentEnabled, error, isLoading, updateContext, view])

  // ---------------------------------------------------------------------------
  // Logs live stream
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!logsLive || view !== "logs") return

    const wsUrl = toWsUrl(DEFAULT_GATEWAY_URL)
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(String(ev.data))
        if (msg?.type === "log") {
          setLogs((prev) => [msg as GatewayLog, ...prev].slice(0, 500))
        }
      } catch {
        // ignore
      }
    }

    ws.onerror = () => {
      // keep existing logs; surface error via badge
    }

    return () => {
      try {
        ws.close()
      } catch {
        // ignore
      }
      wsRef.current = null
    }
  }, [logsLive, view])

  // ---------------------------------------------------------------------------
  // Actions (Nodes / Scheduler / Skills / Memory / Logs)
  // ---------------------------------------------------------------------------

  const launchTui = useCallback(async () => {
    setActionMessage(null)
    try {
      await fetchGatewayJson<any>("tui/launch", { method: "POST" })
      setActionMessage("TUI launched")
    } catch (e: any) {
      setActionMessage(e?.message ? `TUI launch failed: ${e.message}` : "TUI launch failed")
    }
  }, [])

  const restartAgentWorker = useCallback(async () => {
    if (typeof window !== "undefined") {
      const ok = window.confirm("Restart the agent worker? This may open a new terminal window.")
      if (!ok) return
    }
    setActionMessage(null)
    try {
      await fetchGatewayJson<any>("agent/restart", { method: "POST" })
      setActionMessage("Agent restart initiated")
    } catch (e: any) {
      setActionMessage(e?.message ? `Restart failed: ${e.message}` : "Restart failed")
    }
  }, [])

  const checkAgentStatus = useCallback(async () => {
    setAgentWorkerLoading(true)
    try {
      const health = await fetchGatewayJson<any>("agent/health")
      setAgentWorker(health)
    } catch (e: any) {
      setActionMessage(e?.message ? `Agent status check failed: ${e.message}` : "Agent status check failed")
    } finally {
      setAgentWorkerLoading(false)
    }
  }, [])

  const saveModelConfig = useCallback(async () => {
    if (!modelProvider || !modelName) return
    setModelSaving(true)
    setActionMessage(null)
    try {
      await fetchGatewayJson<any>("model/config", {
        method: "POST",
        body: JSON.stringify({ provider: modelProvider, model: modelName }),
      })
      setActionMessage(`Model saved: ${modelProvider}/${modelName}`)
      await refreshCurrent()
    } catch (e: any) {
      setActionMessage(e?.message ? `Model save failed: ${e.message}` : "Model save failed")
    } finally {
      setModelSaving(false)
    }
  }, [modelName, modelProvider, refreshCurrent])

  const generatePairingCode = useCallback(async () => {
    await fetchGatewayJson<any>("nodes/pairing/generate", { method: "POST" })
    await refreshCurrent()
  }, [refreshCurrent])

  const revokeNodeApproval = useCallback(
    async (nodeId: string) => {
      await fetchGatewayJson<any>(`nodes/${encodeURIComponent(nodeId)}/approval`, { method: "DELETE" })
      await refreshCurrent()
    },
    [refreshCurrent]
  )

  const clearLogs = useCallback(async () => {
    await fetchGatewayJson<any>("logs/clear", { method: "POST" })
    await refreshCurrent()
  }, [refreshCurrent])

  const openWorkspaceFile = useCallback(async (filePath: string) => {
    setWorkspaceSelected(filePath)
    const res = await fetchGatewayJson<any>(`workspace/file?path=${encodeURIComponent(filePath)}`)
    setWorkspaceContent(String(res?.content || ""))
  }, [])

  const openMemoryFile = useCallback(async (filePath: string) => {
    setMemorySelected(filePath)
    const res = await fetchGatewayJson<any>(`memory/file?path=${encodeURIComponent(filePath)}`)
    setMemoryContent(String(res?.content || ""))
  }, [])

  const saveMemoryFile = useCallback(async () => {
    if (!memorySelected) return
    setMemorySaving(true)
    try {
      await fetchGatewayJson<any>("memory/file", {
        method: "POST",
        body: JSON.stringify({ path: memorySelected, content: memoryContent }),
      })
    } finally {
      setMemorySaving(false)
    }
  }, [memoryContent, memorySelected])

  const approveSession = useCallback(
    async (sessionId: string, code?: string) => {
      await fetchGatewayJson<any>(`sessions/${encodeURIComponent(sessionId)}/approve`, {
        method: "POST",
        body: JSON.stringify(code ? { code } : {}),
      })
      await refreshCurrent()
    },
    [refreshCurrent]
  )

  const deleteSession = useCallback(
    async (sessionId: string) => {
      if (typeof window !== "undefined") {
        const ok = window.confirm(`Delete session "${sessionId}"?`)
        if (!ok) return
      }
      setActionMessage(null)
      try {
        await fetchGatewayJson<any>(`sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" })
        setActionMessage(`Session deleted: ${sessionId}`)
        await refreshCurrent()
      } catch (e: any) {
        setActionMessage(e?.message ? `Delete failed: ${e.message}` : "Delete failed")
      }
    },
    [refreshCurrent]
  )

  const clearAllSessions = useCallback(async () => {
    if (typeof window !== "undefined") {
      const ok = window.confirm("Clear all sessions? This cannot be undone.")
      if (!ok) return
    }
    setActionMessage(null)
    try {
      const res = await fetchGatewayJson<any>("sessions/clear", { method: "POST" })
      const cleared = res?.cleared
      setActionMessage(typeof cleared === "number" ? `Cleared ${cleared} sessions` : "Sessions cleared")
      await refreshCurrent()
    } catch (e: any) {
      setActionMessage(e?.message ? `Clear failed: ${e.message}` : "Clear failed")
    }
  }, [refreshCurrent])

  // ---------------------------------------------------------------------------
  // View renderers
  // ---------------------------------------------------------------------------

  const viewTabs = (
    <div className="flex items-center gap-1 p-2 border-b border-border bg-surface-elevated">
      <div className="flex items-center gap-1 flex-wrap">
        {VIEWS.map((v) => {
          const Icon = v.icon
          const active = v.id === view
          return (
            <Button
              key={v.id}
              variant={active ? "default" : "ghost"}
              size="sm"
              className={cn("gap-2", !active && "text-text-muted")}
              onClick={() => setViewSafe(v.id)}
              title={v.label}
            >
              <Icon className="h-4 w-4" />
              {v.label}
            </Button>
          )
        })}
      </div>
      <div className="ml-auto flex items-center gap-2">
        {view === "dashboard" && (
          <>
            <Button variant="outline" size="sm" onClick={launchTui} title="Launch TUI">
              Launch TUI
            </Button>
            <Button variant="outline" size="sm" onClick={restartAgentWorker} title="Restart agent worker">
              Restart Agent
            </Button>
          </>
        )}
        <Button variant="ghost" size="sm" onClick={refreshCurrent} title="Refresh">
          <RefreshCw className={cn("h-4 w-4", isLoading && "animate-spin")} />
        </Button>
      </div>
    </div>
  )

  const renderDashboard = () => {
    if (!dashboard) return <EmptyModuleState icon={Signal} title="No data" description="Gateway status not loaded" />
    const health = dashboard.health || {}
    const status = dashboard.status || {}
    const channels = Array.isArray(health.channels) ? health.channels : []
    const providerEntries = Object.entries(modelOptions || {})
    const providerLabel =
      modelProvider && modelOptions?.[modelProvider]?.name
        ? String(modelOptions[modelProvider].name)
        : modelProvider
    const models = Array.isArray(modelOptions?.[modelProvider]?.models) ? modelOptions[modelProvider].models : []
    const modelLabel = modelName
      ? String(models.find((m: any) => String(m?.id) === modelName)?.name || modelName)
      : ""
    const agentStatus = String(agentWorker?.status || "")
    return (
      <div className="p-4 space-y-4">
        {actionMessage && <div className="text-sm text-text-muted">{actionMessage}</div>}
        <div className="flex items-center gap-3">
          <Badge variant="outline" className="gap-2">
            <Signal className="h-3 w-3" />
            {health.ok ? "Gateway OK" : "Gateway Unknown"}
          </Badge>
          <span className="text-sm text-text-muted">{String(health.name || "ag3nt-gateway")}</span>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 rounded-lg border border-border bg-surface-elevated">
            <div className="text-xs text-text-muted">Sessions</div>
            <div className="text-lg font-semibold text-text-primary">{String(status.sessions ?? health.sessions ?? 0)}</div>
          </div>
          <div className="p-3 rounded-lg border border-border bg-surface-elevated">
            <div className="text-xs text-text-muted">Scheduler Jobs</div>
            <div className="text-lg font-semibold text-text-primary">
              {String(status.scheduler?.jobCount ?? health.scheduler?.jobCount ?? 0)}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 rounded-lg border border-border bg-surface-elevated space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm font-medium text-text-primary">Model</div>
              <Badge variant="outline">{providerLabel && modelLabel ? `${providerLabel} • ${modelLabel}` : "—"}</Badge>
            </div>
            {providerEntries.length === 0 ? (
              <div className="text-sm text-text-muted">Model config unavailable</div>
            ) : (
              <div className="space-y-2">
                <div className="grid grid-cols-2 gap-2">
                  <select
                    value={modelProvider}
                    onChange={(e) => {
                      const nextProvider = e.target.value
                      const nextModels = Array.isArray(modelOptions?.[nextProvider]?.models)
                        ? modelOptions[nextProvider].models
                        : []
                      const stillValid = nextModels.some((m: any) => String(m?.id) === modelName)
                      setModelProvider(nextProvider)
                      setModelName(stillValid ? modelName : String(nextModels?.[0]?.id || ""))
                    }}
                    className="px-3 py-1.5 text-sm bg-surface border border-border rounded-md text-text-primary focus:outline-none focus:ring-1 focus:ring-status-info"
                  >
                    {providerEntries.map(([key, val]: any) => (
                      <option key={String(key)} value={String(key)}>
                        {String(val?.name || key)}
                      </option>
                    ))}
                  </select>
                  <select
                    value={modelName}
                    onChange={(e) => setModelName(e.target.value)}
                    className="px-3 py-1.5 text-sm bg-surface border border-border rounded-md text-text-primary focus:outline-none focus:ring-1 focus:ring-status-info"
                  >
                    {models.map((m: any) => (
                      <option key={String(m?.id)} value={String(m?.id)}>
                        {String(m?.name || m?.id)}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex items-center gap-2">
                  <Button size="sm" onClick={saveModelConfig} disabled={!modelProvider || !modelName || modelSaving}>
                    {modelSaving ? "Saving..." : "Save"}
                  </Button>
                </div>
              </div>
            )}
          </div>

          <div className="p-3 rounded-lg border border-border bg-surface-elevated space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm font-medium text-text-primary">Agent Worker</div>
              <Badge variant="outline">{agentStatus || "unknown"}</Badge>
            </div>
            <div className="text-sm text-text-muted">{String(agentWorker?.message || "")}</div>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="outline" onClick={checkAgentStatus} disabled={agentWorkerLoading}>
                {agentWorkerLoading ? "Checking..." : "Check"}
              </Button>
              <Button size="sm" variant="outline" onClick={restartAgentWorker}>
                Restart
              </Button>
            </div>
          </div>
        </div>

        <div className="space-y-2">
          <div className="text-sm font-medium text-text-primary">Channels</div>
          {channels.length === 0 ? (
            <div className="text-sm text-text-muted">No channels reported</div>
          ) : (
            <div className="space-y-2">
              {channels.map((c: any) => (
                <div key={String(c.id)} className="flex items-center justify-between p-3 rounded-lg border border-border bg-surface">
                  <div className="text-sm text-text-primary">{String(c.id)}</div>
                  <Badge variant="outline" className={cn(c.connected ? "text-success" : "text-destructive")}>
                    {c.connected ? "connected" : "disconnected"}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    )
  }

  const renderNodes = () => {
    const pairingCode = nodes?.pairingRes?.code ?? null
    const nodeList = Array.isArray(nodes?.nodesRes?.nodes) ? nodes.nodesRes.nodes : []
    const approved = Array.isArray(nodes?.approvedRes?.nodes) ? nodes.approvedRes.nodes : []

    return (
      <div className="p-4 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div className="space-y-1">
            <div className="text-sm font-medium text-text-primary">Pairing Code</div>
            <div className="text-sm text-text-muted">{pairingCode ? String(pairingCode) : "None active"}</div>
          </div>
          <Button size="sm" onClick={generatePairingCode}>
            Generate
          </Button>
        </div>

        <div className="space-y-2">
          <div className="text-sm font-medium text-text-primary">Connected Nodes</div>
          {nodeList.length === 0 ? (
            <div className="text-sm text-text-muted">No nodes</div>
          ) : (
            <div className="space-y-2">
              {nodeList.map((n: any) => (
                <div key={String(n.id)} className="p-3 rounded-lg border border-border bg-surface-elevated">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-medium text-text-primary">{String(n.name || n.id)}</div>
                    <Badge variant="outline">{String(n.status || "unknown")}</Badge>
                  </div>
                  {Array.isArray(n.capabilities) && n.capabilities.length > 0 && (
                    <div className="text-xs text-text-muted mt-1">
                      {n.capabilities.slice(0, 8).map(String).join(", ")}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-2">
          <div className="text-sm font-medium text-text-primary">Approved Nodes</div>
          {approved.length === 0 ? (
            <div className="text-sm text-text-muted">No approved nodes</div>
          ) : (
            <div className="space-y-2">
              {approved.map((n: any) => (
                <div key={String(n.nodeId)} className="flex items-center justify-between p-3 rounded-lg border border-border bg-surface">
                  <div className="text-sm text-text-primary">{String(n.name || n.nodeId)}</div>
                  <Button variant="destructive" size="sm" onClick={() => revokeNodeApproval(String(n.nodeId))}>
                    Revoke
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    )
  }

  const renderLogs = () => {
    return (
      <div className="p-4 space-y-3">
        <div className="flex items-center gap-2">
          <select
            value={logLevel}
            onChange={(e) => setLogLevel(e.target.value as any)}
            className="px-3 py-1.5 text-sm bg-surface border border-border rounded-md text-text-primary focus:outline-none focus:ring-1 focus:ring-status-info"
          >
            <option value="debug">debug+</option>
            <option value="info">info+</option>
            <option value="warn">warn+</option>
            <option value="error">error</option>
          </select>

          <div className="flex items-center gap-2 text-sm text-text-muted">
            <Switch checked={logsLive} onCheckedChange={setLogsLive} />
            Live
          </div>

          <div className="ml-auto flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={clearLogs}>
              Clear
            </Button>
          </div>
        </div>

        {logs.length === 0 ? (
          <EmptyModuleState icon={Terminal} title="No logs" description="No recent logs available" />
        ) : (
          <div className="space-y-2">
            {logs.slice(0, 200).map((l, idx) => (
              <div
                key={l.id || `${idx}`}
                className="p-3 rounded-lg border border-border bg-surface font-mono text-xs text-text-primary"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="text-text-muted truncate">
                    {String(l.timestamp || "")} • {String(l.source || "Gateway")}
                  </div>
                  <Badge variant="outline">{String(l.level || "info")}</Badge>
                </div>
                <div className="mt-1 whitespace-pre-wrap">{String(l.message || "")}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  function renderTree(nodes: any[]) {
    return (
      <div className="space-y-1">
        {nodes.map((n) => {
          const isDir = n.type === "directory"
          return (
            <div key={String(n.path)}>
              <button
                className={cn(
                  "w-full text-left px-2 py-1 rounded hover:bg-interactive-hover text-sm",
                  workspaceSelected === n.path && "bg-surface text-text-primary"
                )}
                onClick={() => {
                  if (!isDir) openWorkspaceFile(String(n.path))
                }}
              >
                <span className="text-text-muted">{isDir ? "📁" : "📄"}</span>{" "}
                <span className="text-text-primary">{String(n.name)}</span>
              </button>
              {isDir && Array.isArray(n.children) && n.children.length > 0 && (
                <div className="pl-4">{renderTree(n.children)}</div>
              )}
            </div>
          )
        })}
      </div>
    )
  }

  const renderWorkspace = () => {
    const files = Array.isArray(workspaceTree?.files) ? workspaceTree.files : []

    return (
      <div className="flex h-full overflow-hidden">
        <div className="w-96 shrink-0 border-r border-border overflow-y-auto p-3">
          {files.length === 0 ? (
            <EmptyModuleState icon={FolderOpen} title="No files" description="Workspace is empty" />
          ) : (
            renderTree(files)
          )}
        </div>
        <div className="flex-1 overflow-hidden p-3">
          {!workspaceSelected ? (
            <EmptyModuleState icon={FolderOpen} title="Select a file" description="Choose a workspace file to view" />
          ) : (
            <div className="h-full flex flex-col gap-2">
              <div className="text-xs text-text-muted">{workspaceSelected}</div>
              <div className="flex-1 overflow-auto rounded-lg border border-border bg-surface p-3">
                <pre className="text-xs text-text-primary whitespace-pre-wrap">{workspaceContent}</pre>
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  const renderMemory = () => {
    return (
      <div className="flex h-full overflow-hidden">
        <div className="w-80 shrink-0 border-r border-border overflow-y-auto p-3 space-y-1">
          {memoryFiles.length === 0 ? (
            <EmptyModuleState icon={FileText} title="No memory files" description="Gateway returned no memory files" />
          ) : (
            memoryFiles.map((f) => (
              <button
                key={String(f.path)}
                className={cn(
                  "w-full text-left px-2 py-1 rounded hover:bg-interactive-hover text-sm",
                  memorySelected === f.path && "bg-surface text-text-primary"
                )}
                onClick={() => openMemoryFile(String(f.path))}
              >
                <span className="text-text-primary">{String(f.name || f.path)}</span>
              </button>
            ))
          )}
        </div>
        <div className="flex-1 overflow-hidden p-3">
          {!memorySelected ? (
            <EmptyModuleState icon={FileText} title="Select a file" description="Choose a memory file to view/edit" />
          ) : (
            <div className="h-full flex flex-col gap-2">
              <div className="flex items-center justify-between gap-2">
                <div className="text-xs text-text-muted">{memorySelected}</div>
                <Button size="sm" onClick={saveMemoryFile} disabled={memorySaving}>
                  {memorySaving ? "Saving..." : "Save"}
                </Button>
              </div>
              <Textarea
                value={memoryContent}
                onChange={(e) => setMemoryContent(e.target.value)}
                className="flex-1 font-mono text-xs"
              />
            </div>
          )}
        </div>
      </div>
    )
  }

  const renderSessions = () => {
    const all = Array.isArray(sessions?.all?.sessions) ? sessions.all.sessions : []
    const pending = Array.isArray(sessions?.pending?.sessions) ? sessions.pending.sessions : []

    return (
      <div className="p-4 space-y-6">
        <div className="space-y-2">
          <div className="text-sm font-medium text-text-primary">Pending Sessions</div>
          {pending.length === 0 ? (
            <div className="text-sm text-text-muted">No pending sessions</div>
          ) : (
            <div className="space-y-2">
              {pending.map((s: any) => (
                <div key={String(s.id)} className="p-3 rounded-lg border border-border bg-surface-elevated">
                  <div className="flex items-center justify-between">
                    <div className="text-sm text-text-primary">{String(s.id)}</div>
                    <Badge variant="outline">pairing: {String(s.pairingCode || "")}</Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-2">
          <div className="text-sm font-medium text-text-primary">Approve Session</div>
          <div className="flex items-center gap-2">
            <Input
              value={approveSessionId}
              onChange={(e) => setApproveSessionId(e.target.value)}
              placeholder="sessionId"
              className="max-w-sm"
            />
            <Input
              value={approveSessionCode}
              onChange={(e) => setApproveSessionCode(e.target.value)}
              placeholder="optional code"
              className="max-w-xs"
            />
            <Button
              size="sm"
              onClick={() =>
                approveSessionId &&
                approveSession(approveSessionId, approveSessionCode || undefined)
              }
            >
              Approve
            </Button>
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm font-medium text-text-primary">Active Sessions</div>
            <Button size="sm" variant="destructive" onClick={clearAllSessions} disabled={all.length === 0}>
              Clear All
            </Button>
          </div>
          {all.length === 0 ? (
            <div className="text-sm text-text-muted">No active sessions</div>
          ) : (
            <div className="space-y-2">
              {all.map((s: any) => (
                <div key={String(s.id)} className="p-3 rounded-lg border border-border bg-surface">
                  <div className="flex items-center justify-between">
                    <div className="text-sm text-text-primary">{String(s.id)}</div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">{s.paired ? "paired" : "unpaired"}</Badge>
                      <Button variant="destructive" size="sm" onClick={() => deleteSession(String(s.id))}>
                        Delete
                      </Button>
                    </div>
                  </div>
                  <div className="text-xs text-text-muted mt-1">
                    {String(s.channelType || "")} • {String(s.userId || "")}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    )
  }

  const body = (() => {
    if (isLoading) return <LoadingModuleState message="Loading AG3NT Gateway…" />
    if (error) return <ErrorModuleState error={error} onRetry={refreshCurrent} />

    switch (view) {
      case "dashboard":
        return renderDashboard()
      case "nodes":
        return renderNodes()
      case "logs":
        return renderLogs()
      case "workspace":
        return renderWorkspace()
      case "memory":
        return renderMemory()
      case "sessions":
        return renderSessions()
      default:
        return null
    }
  })()

  return (
    <ModuleContainer config={ag3ntControlPanelModuleConfig} className={cn("flex flex-col h-full", className)} showHeader={false}>
      {viewTabs}
      <div className="flex-1 overflow-hidden bg-surface-secondary">{body}</div>
    </ModuleContainer>
  )
}

export default Ag3ntControlPanelModule
