"use client"

import { useEffect, useMemo, useCallback, useRef } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ChevronLeft, ChevronRight, RefreshCw, ExternalLink, Maximize2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { useApp, useChat, useTabs } from "@/providers"
import Image from "next/image"
import { TabBar } from "@/components/layout/tab-bar"
import dynamic from "next/dynamic"

const AgentBrowserModule = dynamic(() => import("@/components/modules/agent-browser-module").then(m => ({ default: m.AgentBrowserModule })), { ssr: false })
const AgentsLibraryModule = dynamic(() => import("@/components/modules/agents-library-module").then(m => ({ default: m.AgentsLibraryModule })), { ssr: false })
const SkillsLibraryModule = dynamic(() => import("@/components/modules/skills-library-module").then(m => ({ default: m.SkillsLibraryModule })), { ssr: false })
const ToolsLibraryModule = dynamic(() => import("@/components/modules/tools-library-module").then(m => ({ default: m.ToolsLibraryModule })), { ssr: false })
const ArtifactsLibraryModule = dynamic(() => import("@/components/modules/artifacts-library-module").then(m => ({ default: m.ArtifactsLibraryModule })), { ssr: false })
const McpManagerModule = dynamic(() => import("@/components/modules/mcp-manager-module").then(m => ({ default: m.McpManagerModule })), { ssr: false })
const Ag3ntControlPanelModule = dynamic(() => import("@/components/modules/ag3nt-control-panel-module").then(m => ({ default: m.Ag3ntControlPanelModule })), { ssr: false })
const SchedulerModule = dynamic(() => import("@/components/modules/scheduler-module").then(m => ({ default: m.SchedulerModule })), { ssr: false })
import { subscribeToBrowserSession } from "@/lib/browser-session-events"

interface PreviewPanelProps {
  className?: string
}

const DefaultContent = () => (
  <div className="flex h-full items-center justify-center p-8 text-center bg-[#0a0a0a]">
    <div className="flex flex-col items-center gap-5">
      <div className="relative">
        <Image
          src="/images/logo.png"
          alt="Logo"
          width={56}
          height={56}
          className="h-14 w-14 animate-breathe"
        />
      </div>
      <div className="space-y-2">
        <h2 className="text-lg font-medium text-text-secondary tracking-tight">Preview</h2>
        <p className="text-sm text-text-muted max-w-[200px] leading-relaxed">
          Generated content and web pages will appear here
        </p>
      </div>
    </div>
  </div>
)

const ErrorContent = ({ error }: { error: string }) => (
  <div className="flex h-full items-center justify-center p-8 bg-[#0a0a0a]">
    <div className="flex flex-col items-center gap-5 text-center max-w-md">
      <div className="rounded-full bg-[#2a1a1a] p-4">
        <svg className="h-8 w-8 text-[#ff6b6b]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      </div>
      <div className="space-y-2">
        <h2 className="text-lg font-semibold text-text-primary tracking-tight">Something went wrong</h2>
        <p className="text-sm text-text-secondary leading-relaxed">{error}</p>
      </div>
      <Button
        variant="outline"
        onClick={() => window.location.reload()}
        className="mt-2 bg-[#1a1a1a] border-[#2a2a2a] text-text-secondary hover:bg-[#252525] hover:text-text-primary hover-underglow active:scale-[0.97] transition-all duration-150"
      >
        Try again
      </Button>
    </div>
  </div>
)

const LoadingWithStatus = () => (
  <div className="flex h-full w-full items-center justify-center bg-[#0a0a0a]">
    <div className="flex flex-col items-center gap-5 text-center">
      <div className="relative">
        <div className="h-10 w-10 rounded-full border-2 border-[#2a2a2a] border-t-text-secondary animate-spin" />
      </div>
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-text-secondary">
          <span className="text-sm font-medium tracking-tight">Generating</span>
          <span className="flex items-center gap-1">
            <span className="w-1 h-1 rounded-full bg-text-muted animate-staggered-bounce" style={{ animationDelay: '0ms' }} />
            <span className="w-1 h-1 rounded-full bg-text-muted animate-staggered-bounce" style={{ animationDelay: '150ms' }} />
            <span className="w-1 h-1 rounded-full bg-text-muted animate-staggered-bounce" style={{ animationDelay: '300ms' }} />
          </span>
        </div>
        <p className="text-xs text-text-muted">This may take a moment</p>
      </div>
    </div>
  </div>
)

export function PreviewPanel({ className }: { className?: string }) {
  const { previewUrl, isGenerating: isLoading } = useApp()
  const { error } = useChat()
  const { getActiveTab, updateTab, activeTabId, addTab, tabs, setActiveTab } = useTabs()

  const activeTab = getActiveTab()
  const tabUrl = activeTab?.url
  const tabIsLoading = activeTab?.isLoading || isLoading
  const tabError = activeTab?.error || error
  const moduleType = activeTab?.moduleType || 'browser'
  const moduleData = activeTab?.moduleData || {}
  const moduleInstanceId = activeTab?.moduleInstanceId

  // Sync global preview URL with active tab
  useEffect(() => {
    if (previewUrl && activeTabId && previewUrl !== tabUrl) {
      updateTab(activeTabId, {
        url: previewUrl,
        title: "Preview",
        isLoading: false,
      })
    }
  }, [previewUrl, activeTabId, tabUrl, updateTab])

  // Use a ref to access current tabs without causing re-subscriptions
  const tabsRef = useRef(tabs)
  useEffect(() => {
    tabsRef.current = tabs
  }, [tabs])

  // Subscribe to browser session events and auto-open browser tabs
  // IMPORTANT: Only subscribe once on mount, use refs for current values
  useEffect(() => {
    const unsubscribe = subscribeToBrowserSession((data) => {
      console.log('[PreviewPanel] Browser session event received:', data)

      const isSessionCreate = data.toolName === 'session_create' || data.toolName === 'session-create'
      const isLiveStart = data.toolName === 'browser_live_start' || data.toolName === 'browser-live-start' || data.toolName === 'open_live_browser'

      // For browser_live_start/open_live_browser with wsPath - always use the new session
      if (isLiveStart && data.wsPath) {
        const currentTabs = tabsRef.current
        const existingTab = currentTabs.find(t => t.moduleType === 'agent-browser')

        // Normalize wsPath to the correct format: /v1/live/ws/{sessionId}
        let wsPath = data.wsPath
        // Convert /v1/agent-browser/sessions/{id}/live/ws to /v1/live/ws/{id}
        const agentBrowserMatch = wsPath.match(/\/v1\/agent-browser\/sessions\/([^/]+)\/live\/ws/)
        if (agentBrowserMatch) {
          wsPath = `/v1/live/ws/${agentBrowserMatch[1]}`
          console.log('[PreviewPanel] Normalized wsPath from agent-browser format:', wsPath)
        }

        if (existingTab) {
          console.log('[PreviewPanel] Updating existing agent-browser tab with new session:', existingTab.id)
          updateTab(existingTab.id, {
            title: data.initialUrl ? `Agent: ${new URL(data.initialUrl).hostname}` : 'Agent Browser',
            moduleData: {
              ...existingTab.moduleData,
              wsPath: wsPath,
              sessionId: data.sessionId || existingTab.moduleData?.sessionId,
              initialUrl: data.initialUrl || existingTab.moduleData?.initialUrl,
            },
          })
          setActiveTab(existingTab.id)
        } else {
          console.log('[PreviewPanel] No existing tab found, creating new one')
          addTab({
            title: data.initialUrl ? `Agent: ${new URL(data.initialUrl).hostname}` : 'Agent Browser',
            moduleType: 'agent-browser',
            moduleData: {
              sessionId: data.sessionId || null,
              wsPath: wsPath,
              initialUrl: data.initialUrl || null,
            },
            icon: 'Globe',
          })
        }
        return
      }

      // For browser_live_start without wsPath (tool_call event) - don't create tab, wait for tool_result
      if (isLiveStart && !data.wsPath) {
        console.log('[PreviewPanel] browser_live_start without wsPath, waiting for tool_result')
        return
      }

      // For session_create - reuse existing tab if one exists, otherwise create new
      if (isSessionCreate) {
        // Parse title from URL if available
        let title = 'Agent Browser'
        if (data.initialUrl) {
          try {
            title = `Agent: ${new URL(data.initialUrl).hostname}`
          } catch {
            title = 'Agent Browser'
          }
        }

        // Check if there's already an agent-browser tab to reuse
        const currentTabs = tabsRef.current
        const existingTab = currentTabs.find(t => t.moduleType === 'agent-browser')

        if (existingTab) {
          console.log('[PreviewPanel] session_create: Reusing existing agent-browser tab:', existingTab.id)
          updateTab(existingTab.id, {
            title,
            moduleData: {
              ...existingTab.moduleData,
              sessionId: data.sessionId || existingTab.moduleData?.sessionId,
              wsPath: data.wsPath || existingTab.moduleData?.wsPath,
              initialUrl: data.initialUrl || existingTab.moduleData?.initialUrl,
            },
          })
          setActiveTab(existingTab.id)
        } else {
          console.log('[PreviewPanel] session_create: Creating new agent-browser tab')
          addTab({
            title,
            moduleType: 'agent-browser',
            moduleData: {
              sessionId: data.sessionId || null,
              wsPath: data.wsPath || null,
              initialUrl: data.initialUrl || null,
            },
            icon: 'Globe',
          })
        }
      }
    })

    return () => unsubscribe()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // Only subscribe once on mount - use refs for current values

  const handleIframeLoad = () => {}
  const handleIframeError = () => {}

  // Render module based on moduleType
  const renderModule = useMemo(() => {
    if (!moduleInstanceId) {
      return null
    }

    const commonProps = {
      instanceId: moduleInstanceId,
      tabId: activeTabId || undefined,
      className: "h-full",
      agentEnabled: true,
    }

    switch (moduleType) {
      case 'agent-browser':
        return (
          <AgentBrowserModule
            {...commonProps}
            sessionId={moduleData.sessionId as string | undefined}
            wsPath={moduleData.wsPath as string | undefined}
            initialUrl={moduleData.initialUrl as string | undefined}
            pendingNavigation={moduleData.pendingNavigation as string | undefined}
          />
        )
      case 'agents-library':
        return <AgentsLibraryModule {...commonProps} />
      case 'skills-library':
        return <SkillsLibraryModule {...commonProps} />
      case 'tools-library':
        return <ToolsLibraryModule {...commonProps} />
      case 'artifacts-library':
        return <ArtifactsLibraryModule {...commonProps} />
      case 'mcp-manager':
        return <McpManagerModule {...commonProps} />
      case 'ag3nt-control-panel':
        return <Ag3ntControlPanelModule {...commonProps} />
      case 'scheduler':
        return <SchedulerModule {...commonProps} />
      case 'browser':
      default:
        // Default browser/preview behavior
        return null
    }
  }, [moduleType, moduleInstanceId, activeTabId, moduleData])

  // If a specialized module is active, render it directly (without browser toolbar)
  if (renderModule) {
    return (
      <div className={cn("flex h-full flex-col", className)}>
        <TabBar />
        <div className="flex-1 overflow-hidden bg-surface-secondary">
          {renderModule}
        </div>
      </div>
    )
  }

  // Default browser preview with toolbar
  return (
    <div className={cn("flex h-full flex-col", className)}>
      <TabBar />

      <div className="flex h-12 items-center gap-4 border-b border-gray-800 px-4 shadow-sm bg-[rgba(15,15,15,1)]">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" className="h-8 w-8 text-gray-400" disabled={!tabUrl}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8 text-gray-400" disabled={!tabUrl}>
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8 text-gray-400" disabled={!tabUrl} title="Refresh">
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex-1">
          <Input
            type="text"
            value={tabUrl || "v0.dev/preview"}
            className="h-8 w-full border-gray-300 text-sm rounded-full bg-[rgba(39,40,45,1)] border-none"
            readOnly
          />
        </div>

        <div className="flex items-center gap-2">
          {tabUrl && (
            <>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 hover:bg-white/5"
                onClick={() => window.open(tabUrl, "_blank")}
                title="Open in new tab"
              >
                <ExternalLink className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" className="h-8 w-8 hover:bg-white/5" title="Fullscreen">
                <Maximize2 className="h-4 w-4" />
              </Button>
            </>
          )}
        </div>
      </div>

      <div className="flex-1 bg-white overflow-hidden">
        {tabIsLoading ? (
          <LoadingWithStatus />
        ) : tabError ? (
          <ErrorContent error={tabError || "Unknown error"} />
        ) : tabUrl ? (
          <div className="relative h-full w-full">
            <iframe
              key={tabUrl}
              src={tabUrl}
              className="h-full w-full border-0"
              title="v0 Component Preview"
              sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
              loading="eager"
              onLoad={handleIframeLoad}
              onError={handleIframeError}
            />
          </div>
        ) : (
          <DefaultContent />
        )}
      </div>
    </div>
  )
}
