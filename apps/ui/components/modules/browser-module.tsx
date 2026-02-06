"use client"

import { useEffect, useCallback } from "react"
import { ChevronLeft, ChevronRight, RefreshCw, ExternalLink, Maximize2 } from "lucide-react"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import { useApp, useTabs } from "@/providers"
import { TabBar } from "@/components/layout/tab-bar"
import Image from "next/image"
import {
  ModuleContainer,
  EmptyModuleState,
  LoadingModuleState,
  ErrorModuleState,
} from "./module-container"
import { useAgentConnection } from "@/hooks/use-agent-connection"
import type { ModuleConfig, ModuleInstanceProps } from "@/types/modules"
import type { BrowserContext, BrowserCommands } from "@/types/agent-communication"

/**
 * Browser Module Configuration
 */
export const browserModuleConfig: ModuleConfig = {
  metadata: {
    id: 'browser',
    displayName: 'Browser',
    description: 'Web browser for previewing content and navigating URLs',
    icon: 'Globe',
    category: 'browser',
    version: '1.0.0',
  },
  hasHeader: true,
  initialState: {
    isLoading: false,
    error: null,
    data: { url: null, canGoBack: false, canGoForward: false },
  },
  agentConfig: {
    enabled: true,
    supportedCommands: ['navigate', 'refresh', 'goBack', 'goForward', 'getContext'],
    emittedEvents: ['navigation', 'load-complete', 'error'],
    contextDescription: 'Browser module for web content preview with URL navigation',
  },
}

/**
 * Browser toolbar with navigation controls and URL bar
 */
function BrowserToolbar({
  url,
  onRefresh,
  onBack,
  onForward,
  onOpenExternal,
  onFullscreen,
  canGoBack = false,
  canGoForward = false,
}: {
  url: string | null
  onRefresh?: () => void
  onBack?: () => void
  onForward?: () => void
  onOpenExternal?: () => void
  onFullscreen?: () => void
  canGoBack?: boolean
  canGoForward?: boolean
}) {
  const buttonClass = "h-8 w-8 flex items-center justify-center rounded-md text-text-muted hover:text-text-primary hover:bg-surface-elevated transition-colors disabled:opacity-40 disabled:cursor-not-allowed"

  return (
    <div className="flex h-12 items-center gap-3 border-b border-interactive-border px-4 bg-surface">
      <div className="flex items-center gap-1">
        <button className={buttonClass} disabled={!canGoBack} onClick={onBack} title="Back">
          <ChevronLeft className="h-4 w-4" />
        </button>
        <button className={buttonClass} disabled={!canGoForward} onClick={onForward} title="Forward">
          <ChevronRight className="h-4 w-4" />
        </button>
        <button className={buttonClass} disabled={!url} onClick={onRefresh} title="Refresh">
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1">
        <Input
          type="text"
          value={url || "v0.dev/preview"}
          className="h-8 w-full text-sm rounded-md bg-surface border-interactive-border text-text-muted focus:border-interactive-hover focus:ring-0"
          readOnly
        />
      </div>

      <div className="flex items-center gap-1">
        {url && (
          <>
            <button className={buttonClass} onClick={onOpenExternal} title="Open in new tab">
              <ExternalLink className="h-4 w-4" />
            </button>
            <button className={buttonClass} onClick={onFullscreen} title="Fullscreen">
              <Maximize2 className="h-4 w-4" />
            </button>
          </>
        )}
      </div>
    </div>
  )
}

/**
 * Default content when no URL is loaded
 */
function BrowserDefaultContent() {
  return (
    <EmptyModuleState
      icon={({ className }) => (
        <Image src="/images/logo.png" alt="Logo" width={48} height={48} className={cn("h-12 w-12", className)} />
      )}
      title="Preview"
      description="Generate a component to see the preview here"
    />
  )
}

/**
 * BrowserModule Component
 *
 * A full-featured browser module using the module template system.
 * Demonstrates how to build modules with agent communication and tab context support.
 */
export function BrowserModule({
  instanceId,
  tabId,
  className,
  onStateChange,
  onTabUpdate,
  agentEnabled = true,
}: ModuleInstanceProps) {
  const { previewUrl, isGenerating: isLoading } = useApp()
  const { getActiveTab, updateTab, activeTabId } = useTabs()

  const activeTab = getActiveTab()
  const tabUrl = activeTab?.url ?? null
  const tabIsLoading = activeTab?.isLoading || isLoading
  const tabError = activeTab?.error

  // Agent communication hook
  const { updateContext, sendEvent, onCommand } = useAgentConnection({
    instanceId: instanceId || `browser-${Date.now()}`,
    moduleType: 'browser',
    autoRegister: agentEnabled,
    initialContext: {
      url: tabUrl,
      title: activeTab?.title || null,
      canGoBack: false,
      canGoForward: false,
      isLoading: tabIsLoading,
      isSecure: tabUrl?.startsWith('https') || false,
    } as Partial<BrowserContext>,
  })

  // Update agent context when URL changes
  useEffect(() => {
    if (agentEnabled) {
      updateContext({
        url: tabUrl,
        title: activeTab?.title || null,
        isLoading: tabIsLoading,
        isSecure: tabUrl?.startsWith('https') || false,
        state: { isLoading: tabIsLoading, error: tabError },
      } as Partial<BrowserContext>)
    }
  }, [tabUrl, tabIsLoading, tabError, activeTab?.title, updateContext, agentEnabled])

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

  // Navigate handler
  const handleNavigate = useCallback((url: string) => {
    if (activeTabId) {
      updateTab(activeTabId, { url, isLoading: true })
      sendEvent('navigation', { url, previousUrl: tabUrl })
    }
  }, [activeTabId, updateTab, tabUrl, sendEvent])

  // Refresh handler
  const handleRefresh = useCallback(() => {
    if (tabUrl && activeTabId) {
      const url = new URL(tabUrl)
      url.searchParams.set('_t', Date.now().toString())
      updateTab(activeTabId, { url: url.toString() })
      sendEvent('refresh', { url: tabUrl })
    }
  }, [tabUrl, activeTabId, updateTab, sendEvent])

  const handleOpenExternal = () => {
    if (tabUrl) window.open(tabUrl, "_blank")
  }

  // Register agent command handlers
  useEffect(() => {
    if (!agentEnabled) return

    const subscriptions = [
      onCommand<BrowserCommands['navigate'], void>('navigate', async (params) => {
        handleNavigate(params.url)
      }),
      onCommand<BrowserCommands['reload'], void>('reload', async () => {
        handleRefresh()
      }),
      onCommand<BrowserCommands['refresh'], void>('refresh', async () => {
        handleRefresh()
      }),
      onCommand<Record<string, never>, BrowserContext>('getContext', async () => {
        return {
          instanceId: instanceId || '',
          moduleType: 'browser',
          url: tabUrl || null,
          title: activeTab?.title || null,
          canGoBack: false,
          canGoForward: false,
          isLoading: tabIsLoading || false,
          isSecure: tabUrl?.startsWith('https') || false,
          state: { isLoading: tabIsLoading, error: tabError },
          isReady: true,
          lastUpdated: Date.now(),
        }
      }),
    ]

    return () => {
      subscriptions.forEach(sub => sub.unsubscribe())
    }
  }, [agentEnabled, instanceId, tabUrl, tabIsLoading, tabError, activeTab?.title, onCommand, handleNavigate, handleRefresh])

  // Render content based on state
  const renderContent = () => {
    if (tabIsLoading) {
      return <LoadingModuleState message="Generating component..." />
    }
    if (tabError) {
      return <ErrorModuleState error={tabError} onRetry={handleRefresh} />
    }
    if (tabUrl) {
      return (
        <div className="relative h-full w-full bg-white">
          <iframe
            key={tabUrl}
            src={tabUrl}
            className="h-full w-full border-0"
            title="Component Preview"
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
            loading="eager"
            onLoad={() => {
              if (agentEnabled) {
                sendEvent('load-complete', { url: tabUrl })
                updateContext({ isLoading: false } as Partial<BrowserContext>)
              }
            }}
          />
        </div>
      )
    }
    return <BrowserDefaultContent />
  }

  return (
    <div className={cn("flex h-full flex-col", className)}>
      {/* Tab bar is external to module - maintained by parent */}
      <TabBar />

      {/* Browser toolbar */}
      <BrowserToolbar
        url={tabUrl}
        onRefresh={handleRefresh}
        onOpenExternal={handleOpenExternal}
        canGoBack={false}
        canGoForward={false}
      />

      {/* Content area using ModuleContainer */}
      <ModuleContainer
        config={browserModuleConfig}
        showHeader={false}
        bodyConfig={{ padding: "none", background: "primary", overflow: "hidden" }}
      >
        {renderContent()}
      </ModuleContainer>
    </div>
  )
}

export default BrowserModule

