"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
  AlertTriangle,
  CalendarClock,
  ChevronDown,
  ChevronUp,
  Clock,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Trash2,
  Zap,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"
import { ModuleContainer, EmptyModuleState, ErrorModuleState, LoadingModuleState } from "./module-container"
import { useAgentConnection } from "@/hooks/use-agent-connection"
import type { ModuleConfig, ModuleInstanceProps } from "@/types/modules"

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

export const schedulerModuleConfig: ModuleConfig = {
  metadata: {
    id: "scheduler",
    displayName: "Scheduler",
    description: "Manage scheduled jobs, heartbeat, and cron tasks",
    icon: "CalendarClock",
    category: "utility",
    version: "1.0.0",
  },
  hasHeader: false,
  initialState: { isLoading: true, error: null, data: {} },
  agentConfig: {
    enabled: true,
    supportedCommands: ["refresh", "createJob", "removeJob"],
    emittedEvents: ["job-created", "job-removed", "refreshed"],
    contextDescription: "Scheduler module for managing cron jobs and heartbeat",
  },
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 10_000
const POLL_INTERVAL_FAST_MS = 3_000
const STALE_THRESHOLD_MS = 30_000
const MAX_RETRIES = 3
const RETRY_BASE_DELAY_MS = 500

// ---------------------------------------------------------------------------
// Gateway fetch helper with retry
// ---------------------------------------------------------------------------

async function fetchGatewayJson<T>(path: string, init?: RequestInit, retries = MAX_RETRIES): Promise<T> {
  let lastError: Error | null = null
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 10_000)
      const res = await fetch(`/api/ag3nt/gateway/${path}`, {
        ...init,
        signal: controller.signal,
        headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
        cache: "no-store",
      })
      clearTimeout(timeout)
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        const msg = (data && (data.error || data.detail)) || res.statusText || "Gateway request failed"
        throw new Error(String(msg))
      }
      return data as T
    } catch (e: any) {
      lastError = e
      if (attempt < retries) {
        const delay = RETRY_BASE_DELAY_MS * Math.pow(2, attempt)
        await new Promise((r) => setTimeout(r, delay))
      }
    }
  }
  throw lastError ?? new Error("Request failed after retries")
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SchedulerStatus {
  heartbeatRunning?: boolean
  heartbeatPaused?: boolean
  jobCount?: number
  nextWake?: string | null
}

interface SchedulerJob {
  id: string
  name?: string
  schedule?: string
  message?: string
  sessionMode?: "isolated" | "main"
  channelTarget?: string
  oneShot?: boolean
  paused?: boolean
  nextRun?: string | null
  lastRun?: string | null
  createdAt?: string
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SchedulerModule({ instanceId, agentEnabled = true, className }: ModuleInstanceProps) {
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionMessage, setActionMessage] = useState<string | null>(null)

  // Data
  const [status, setStatus] = useState<SchedulerStatus>({})
  const [jobs, setJobs] = useState<SchedulerJob[]>([])

  // Heartbeat reliability state
  const [heartbeatBusy, setHeartbeatBusy] = useState(false)
  const [lastPollAt, setLastPollAt] = useState<number>(0)
  const [pollFailCount, setPollFailCount] = useState(0)
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  // Form
  const [formOpen, setFormOpen] = useState(false)
  const [formName, setFormName] = useState("")
  const [formSchedule, setFormSchedule] = useState("")
  const [formMessage, setFormMessage] = useState("")
  const [formSessionMode, setFormSessionMode] = useState<"isolated" | "main">("isolated")
  const [formChannelTarget, setFormChannelTarget] = useState("")
  const [formOneShot, setFormOneShot] = useState(false)
  const [formSubmitting, setFormSubmitting] = useState(false)

  const { updateContext, sendEvent, onCommand } = useAgentConnection({
    instanceId: instanceId || `scheduler-${Date.now()}`,
    moduleType: "scheduler",
    autoRegister: agentEnabled,
    initialContext: { state: { isLoading: true, error: null } },
  })

  // ---------------------------------------------------------------------------
  // Cleanup on unmount
  // ---------------------------------------------------------------------------
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
    }
  }, [])

  // ---------------------------------------------------------------------------
  // Data loading
  // ---------------------------------------------------------------------------

  const loadData = useCallback(async () => {
    const [statusRes, jobsRes] = await Promise.all([
      fetchGatewayJson<any>("scheduler/status"),
      fetchGatewayJson<any>("scheduler/jobs"),
    ])
    if (!mountedRef.current) return
    setStatus(statusRes || {})
    setJobs(Array.isArray(jobsRes?.jobs) ? jobsRes.jobs : [])
    setLastPollAt(Date.now())
    setPollFailCount(0)
  }, [])

  const refresh = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      await loadData()
      if (agentEnabled) sendEvent("refreshed", {})
    } catch (e: any) {
      if (!mountedRef.current) return
      setError(e?.message || "Failed to load scheduler data")
    } finally {
      if (mountedRef.current) setIsLoading(false)
    }
  }, [agentEnabled, loadData, sendEvent])

  // Silent background poll (doesn't set isLoading, doesn't clobber error on success
  // unless it recovers from a previous failure)
  const poll = useCallback(async () => {
    try {
      await loadData()
      if (mountedRef.current && error) setError(null)
    } catch {
      if (mountedRef.current) setPollFailCount((c) => c + 1)
    }
  }, [error, loadData])

  // Initial load
  useEffect(() => {
    refresh()
  }, [refresh])

  // ---------------------------------------------------------------------------
  // Polling loop - keeps heartbeat status accurate
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const scheduleNext = () => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
      // Poll faster right after an action, slower otherwise
      const interval = heartbeatBusy ? POLL_INTERVAL_FAST_MS : POLL_INTERVAL_MS
      pollTimerRef.current = setTimeout(async () => {
        await poll()
        if (mountedRef.current) scheduleNext()
      }, interval)
    }
    scheduleNext()
    return () => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
    }
  }, [poll, heartbeatBusy])

  // Staleness detection
  const isStale = lastPollAt > 0 && Date.now() - lastPollAt > STALE_THRESHOLD_MS
  const hasConnIssue = pollFailCount >= 2

  useEffect(() => {
    if (agentEnabled) {
      updateContext({ state: { isLoading, error }, jobCount: jobs.length } as any)
    }
  }, [agentEnabled, error, isLoading, jobs.length, updateContext])

  // Agent commands
  useEffect(() => {
    const sub1 = onCommand("refresh", async () => refresh())
    const sub2 = onCommand("createJob", async (params: any) => {
      if (params?.schedule && params?.message) {
        await fetchGatewayJson("scheduler/jobs", {
          method: "POST",
          body: JSON.stringify(params),
        })
        await refresh()
      }
    })
    const sub3 = onCommand("removeJob", async (params: { jobId?: string }) => {
      if (params?.jobId) {
        await fetchGatewayJson(`scheduler/jobs/${encodeURIComponent(params.jobId)}`, { method: "DELETE" })
        await refresh()
      }
    })
    return () => {
      sub1.unsubscribe()
      sub2.unsubscribe()
      sub3.unsubscribe()
    }
  }, [onCommand, refresh])

  // ---------------------------------------------------------------------------
  // Heartbeat actions with optimistic update, locking, and verification
  // ---------------------------------------------------------------------------

  const heartbeatAction = useCallback(async (
    action: "pause" | "resume" | "trigger",
    optimisticStatus?: Partial<SchedulerStatus>,
  ) => {
    if (heartbeatBusy) return
    setHeartbeatBusy(true)
    setActionMessage(null)

    // Optimistic update
    const prevStatus = { ...status }
    if (optimisticStatus) setStatus((s) => ({ ...s, ...optimisticStatus }))

    try {
      await fetchGatewayJson(`scheduler/heartbeat/${action}`, { method: "POST" })

      if (action === "trigger") {
        if (mountedRef.current) setActionMessage("Heartbeat triggered")
      }

      // Verify: re-fetch status and confirm the state matches expectation
      try {
        const verified = await fetchGatewayJson<SchedulerStatus>("scheduler/status", undefined, 1)
        if (!mountedRef.current) return
        setStatus(verified || {})
        setLastPollAt(Date.now())
        setPollFailCount(0)

        // Check if the action actually took effect
        if (action === "pause" && !verified.heartbeatPaused) {
          setActionMessage("Pause requested but heartbeat did not pause — retrying")
          await fetchGatewayJson("scheduler/heartbeat/pause", { method: "POST" })
          const retryVerify = await fetchGatewayJson<SchedulerStatus>("scheduler/status", undefined, 1)
          if (mountedRef.current) {
            setStatus(retryVerify || {})
            if (!retryVerify.heartbeatPaused) {
              setActionMessage("Heartbeat pause failed after retry")
            } else {
              setActionMessage(null)
            }
          }
        } else if (action === "resume" && verified.heartbeatPaused) {
          setActionMessage("Resume requested but heartbeat is still paused — retrying")
          await fetchGatewayJson("scheduler/heartbeat/resume", { method: "POST" })
          const retryVerify = await fetchGatewayJson<SchedulerStatus>("scheduler/status", undefined, 1)
          if (mountedRef.current) {
            setStatus(retryVerify || {})
            if (retryVerify.heartbeatPaused) {
              setActionMessage("Heartbeat resume failed after retry")
            } else {
              setActionMessage(null)
            }
          }
        }
      } catch {
        // Verification fetch failed — still refresh normally
        if (mountedRef.current) await poll()
      }
    } catch (e: any) {
      // Rollback optimistic update
      if (mountedRef.current) {
        setStatus(prevStatus)
        const label = action === "trigger" ? "trigger" : action
        setActionMessage(e?.message || `Failed to ${label} heartbeat`)
      }
    } finally {
      if (mountedRef.current) setHeartbeatBusy(false)
    }
  }, [heartbeatBusy, poll, status])

  const heartbeatPause = useCallback(
    () => heartbeatAction("pause", { heartbeatPaused: true }),
    [heartbeatAction],
  )

  const heartbeatResume = useCallback(
    () => heartbeatAction("resume", { heartbeatPaused: false }),
    [heartbeatAction],
  )

  const heartbeatTrigger = useCallback(
    () => heartbeatAction("trigger"),
    [heartbeatAction],
  )

  const pauseJob = useCallback(async (jobId: string) => {
    setActionMessage(null)
    try {
      await fetchGatewayJson(`scheduler/jobs/${encodeURIComponent(jobId)}/pause`, { method: "POST" })
      await refresh()
    } catch (e: any) {
      setActionMessage(e?.message || "Failed to pause job")
    }
  }, [refresh])

  const resumeJob = useCallback(async (jobId: string) => {
    setActionMessage(null)
    try {
      await fetchGatewayJson(`scheduler/jobs/${encodeURIComponent(jobId)}/resume`, { method: "POST" })
      await refresh()
    } catch (e: any) {
      setActionMessage(e?.message || "Failed to resume job")
    }
  }, [refresh])

  const removeJob = useCallback(async (jobId: string) => {
    if (typeof window !== "undefined") {
      const ok = window.confirm(`Remove job "${jobId}"?`)
      if (!ok) return
    }
    setActionMessage(null)
    try {
      await fetchGatewayJson(`scheduler/jobs/${encodeURIComponent(jobId)}`, { method: "DELETE" })
      setActionMessage(`Job removed: ${jobId}`)
      if (agentEnabled) sendEvent("job-removed", { jobId })
      await refresh()
    } catch (e: any) {
      setActionMessage(e?.message || "Failed to remove job")
    }
  }, [agentEnabled, refresh, sendEvent])

  const createJob = useCallback(async () => {
    if (!formSchedule || !formMessage) return
    setFormSubmitting(true)
    setActionMessage(null)
    try {
      const body: Record<string, any> = {
        schedule: formSchedule,
        message: formMessage,
        sessionMode: formSessionMode,
      }
      if (formName.trim()) body.name = formName.trim()
      if (formChannelTarget.trim()) body.channelTarget = formChannelTarget.trim()
      if (formOneShot) body.oneShot = true

      await fetchGatewayJson("scheduler/jobs", {
        method: "POST",
        body: JSON.stringify(body),
      })
      setActionMessage("Job created")
      if (agentEnabled) sendEvent("job-created", body)

      // Reset form
      setFormName("")
      setFormSchedule("")
      setFormMessage("")
      setFormSessionMode("isolated")
      setFormChannelTarget("")
      setFormOneShot(false)
      setFormOpen(false)

      await refresh()
    } catch (e: any) {
      setActionMessage(e?.message || "Failed to create job")
    } finally {
      setFormSubmitting(false)
    }
  }, [agentEnabled, formChannelTarget, formMessage, formName, formOneShot, formSchedule, formSessionMode, refresh, sendEvent])

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (isLoading) return (
    <ModuleContainer config={schedulerModuleConfig} className={cn("flex flex-col h-full", className)} showHeader={false}>
      <LoadingModuleState message="Loading scheduler..." />
    </ModuleContainer>
  )

  if (error) return (
    <ModuleContainer config={schedulerModuleConfig} className={cn("flex flex-col h-full", className)} showHeader={false}>
      <ErrorModuleState error={error} onRetry={refresh} />
    </ModuleContainer>
  )

  return (
    <ModuleContainer config={schedulerModuleConfig} className={cn("flex flex-col h-full", className)} showHeader={false}>
      <div className="flex-1 overflow-y-auto">
        {/* Header bar */}
        <div className="flex items-center gap-2 p-3 border-b border-border bg-surface-elevated">
          <CalendarClock className="h-4 w-4 text-text-muted" />
          <span className="text-sm font-medium text-text-primary">Scheduler</span>
          <div className="ml-auto flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={refresh} title="Refresh">
              <RefreshCw className={cn("h-4 w-4", isLoading && "animate-spin")} />
            </Button>
          </div>
        </div>

        {/* Status bar */}
        <div className="flex items-center gap-2 p-3 border-b border-border bg-surface">
          <Badge
            variant="outline"
            className={cn(
              "gap-1.5",
              status.heartbeatPaused && "text-yellow-500 border-yellow-500/30",
              !status.heartbeatRunning && !status.heartbeatPaused && "text-red-500 border-red-500/30",
              status.heartbeatRunning && !status.heartbeatPaused && "text-green-500 border-green-500/30",
            )}
          >
            <span className={cn(
              "inline-block h-2 w-2 rounded-full",
              status.heartbeatRunning && !status.heartbeatPaused && "bg-green-500 animate-pulse",
              status.heartbeatPaused && "bg-yellow-500",
              !status.heartbeatRunning && !status.heartbeatPaused && "bg-red-500",
            )} />
            Heartbeat: {status.heartbeatRunning ? (status.heartbeatPaused ? "paused" : "running") : "stopped"}
          </Badge>
          <Badge variant="outline">Jobs: {String(status.jobCount ?? jobs.length ?? 0)}</Badge>
          {status.nextWake && (
            <Badge variant="outline" className="text-text-muted">
              Next wake: {String(status.nextWake)}
            </Badge>
          )}
          {hasConnIssue && (
            <Badge variant="outline" className="gap-1 text-yellow-500 border-yellow-500/30">
              <AlertTriangle className="h-3 w-3" />
              Connection issue
            </Badge>
          )}
          {isStale && !hasConnIssue && (
            <Badge variant="outline" className="text-text-muted">
              Stale
            </Badge>
          )}
          <div className="ml-auto flex items-center gap-1.5">
            <Button
              size="sm"
              variant="outline"
              onClick={heartbeatTrigger}
              disabled={heartbeatBusy}
              title="Trigger heartbeat now"
            >
              <Zap className={cn("h-3.5 w-3.5 mr-1", heartbeatBusy && "animate-pulse")} />
              Trigger
            </Button>
            {status.heartbeatPaused ? (
              <Button
                size="sm"
                onClick={heartbeatResume}
                disabled={heartbeatBusy}
                title="Resume heartbeat"
              >
                <Play className={cn("h-3.5 w-3.5 mr-1", heartbeatBusy && "animate-spin")} />
                Resume
              </Button>
            ) : (
              <Button
                size="sm"
                variant="outline"
                onClick={heartbeatPause}
                disabled={heartbeatBusy}
                title="Pause heartbeat"
              >
                <Pause className={cn("h-3.5 w-3.5 mr-1", heartbeatBusy && "animate-spin")} />
                Pause
              </Button>
            )}
          </div>
        </div>

        {actionMessage && (
          <div className="px-3 py-2 text-sm text-text-muted bg-surface border-b border-border">
            {actionMessage}
          </div>
        )}

        {/* New Job Form (collapsible) */}
        <div className="border-b border-border">
          <button
            className="w-full flex items-center gap-2 px-3 py-2.5 text-sm font-medium text-text-primary hover:bg-interactive-hover transition-colors"
            onClick={() => setFormOpen(!formOpen)}
          >
            <Plus className="h-4 w-4" />
            New Job
            {formOpen ? <ChevronUp className="h-4 w-4 ml-auto" /> : <ChevronDown className="h-4 w-4 ml-auto" />}
          </button>

          {formOpen && (
            <div className="px-3 pb-3 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs text-text-muted">Name</Label>
                  <Input
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="e.g. Daily Standup"
                    className="h-8 text-sm"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-text-muted">Schedule *</Label>
                  <Input
                    value={formSchedule}
                    onChange={(e) => setFormSchedule(e.target.value)}
                    placeholder="e.g. 0 9 * * * or in 10 minutes"
                    className="h-8 text-sm"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs text-text-muted">Message *</Label>
                <Textarea
                  value={formMessage}
                  onChange={(e) => setFormMessage(e.target.value)}
                  placeholder="Message to send to the agent when this job fires"
                  className="text-sm min-h-[60px]"
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs text-text-muted">Session Mode</Label>
                  <select
                    value={formSessionMode}
                    onChange={(e) => setFormSessionMode(e.target.value as "isolated" | "main")}
                    className="w-full px-3 py-1.5 text-sm bg-surface border border-border rounded-md text-text-primary focus:outline-none focus:ring-1 focus:ring-status-info h-8"
                  >
                    <option value="isolated">Isolated</option>
                    <option value="main">Main</option>
                  </select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-text-muted">Channel Target</Label>
                  <Input
                    value={formChannelTarget}
                    onChange={(e) => setFormChannelTarget(e.target.value)}
                    placeholder="e.g. telegram"
                    className="h-8 text-sm"
                  />
                </div>
                <div className="flex items-end gap-2 pb-0.5">
                  <div className="flex items-center gap-2">
                    <Switch checked={formOneShot} onCheckedChange={setFormOneShot} />
                    <Label className="text-xs text-text-muted">One-shot</Label>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <Button
                  size="sm"
                  onClick={createJob}
                  disabled={!formSchedule || !formMessage || formSubmitting}
                >
                  <Plus className="h-3.5 w-3.5 mr-1" />
                  {formSubmitting ? "Creating..." : "Add Job"}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setFormOpen(false)}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* Jobs list */}
        <div className="p-3 space-y-2">
          {jobs.length === 0 ? (
            <EmptyModuleState
              icon={CalendarClock}
              title="No scheduled jobs"
              description="Create a job using the form above to get started"
            />
          ) : (
            jobs.map((job) => (
              <div
                key={String(job.id)}
                className="p-3 rounded-lg border border-border bg-surface-elevated space-y-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-sm font-medium text-text-primary truncate">
                      {String(job.name || job.id)}
                    </span>
                    <Badge variant="outline" className={cn(
                      "shrink-0",
                      job.paused ? "text-yellow-500 border-yellow-500/30" : "text-green-500 border-green-500/30"
                    )}>
                      {job.paused ? "paused" : "active"}
                    </Badge>
                    {job.oneShot && (
                      <Badge variant="outline" className="shrink-0 text-text-muted">one-shot</Badge>
                    )}
                    {job.sessionMode && (
                      <Badge variant="outline" className="shrink-0 text-text-muted">{job.sessionMode}</Badge>
                    )}
                    {job.channelTarget && (
                      <Badge variant="outline" className="shrink-0 text-text-muted">{job.channelTarget}</Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {job.paused ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => resumeJob(String(job.id))}
                        title="Resume job"
                        className="h-7 w-7 p-0"
                      >
                        <Play className="h-3.5 w-3.5" />
                      </Button>
                    ) : (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => pauseJob(String(job.id))}
                        title="Pause job"
                        className="h-7 w-7 p-0"
                      >
                        <Pause className="h-3.5 w-3.5" />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => removeJob(String(job.id))}
                      title="Remove job"
                      className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>

                <div className="flex items-center gap-3 text-xs text-text-muted">
                  <span className="font-mono">{String(job.schedule || "—")}</span>
                  <span>next: {String(job.nextRun || "n/a")}</span>
                  {job.lastRun && <span>last: {String(job.lastRun)}</span>}
                </div>

                {job.message && (
                  <div className="text-xs text-text-muted bg-surface rounded px-2 py-1.5 font-mono whitespace-pre-wrap truncate max-h-16 overflow-hidden">
                    {String(job.message)}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </ModuleContainer>
  )
}

export default SchedulerModule
