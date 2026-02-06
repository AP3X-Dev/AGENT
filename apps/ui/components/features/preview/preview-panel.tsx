"use client"

import { useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ChevronLeft, ChevronRight, RefreshCw, ExternalLink, Maximize2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { useApp, useChat, useTabs } from "@/providers"
import Image from "next/image"
import { TabBar } from "@/components/layout/tab-bar"

interface PreviewPanelProps {
  className?: string
}

const DefaultContent = () => (
  <div className="flex h-full items-center justify-center p-8 text-center bg-[rgba(10,10,10,1)]">
    <div className="flex flex-col items-center gap-4">
      <Image src="/images/logo.png" alt="Logo" width={48} height={48} className="h-12 w-12" />
      <h2 className="text-xl font-medium text-gray-500">Preview</h2>
    </div>
  </div>
)

const ErrorContent = ({ error }: { error: string }) => (
  <div className="flex h-full items-center justify-center p-8">
    <div className="flex flex-col items-center gap-4 text-center">
      <div className="rounded-full bg-red-100 p-4">
        <svg className="h-8 w-8 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      </div>
      <h2 className="text-xl font-semibold text-gray-900">Error Generating Component</h2>
      <p className="text-gray-600 max-w-md">{error}</p>
      <Button variant="outline" onClick={() => window.location.reload()} className="mt-4">
        Retry
      </Button>
    </div>
  </div>
)

const LoadingWithStatus = () => (
  <div className="flex h-full w-full items-center justify-center bg-primary-background">
    <div className="w-full max-w-xl space-y-4 p-4">
      <div className="flex items-center space-x-3 font-medium text-text-secondary">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600"></div>
        <span>Generating component...</span>
      </div>
      <p className="text-sm text-text-muted">This may take a few moments.</p>
    </div>
  </div>
)

export function PreviewPanel({ className }: { className?: string }) {
  const { previewUrl, isGenerating: isLoading } = useApp()
  const { getActiveTab, updateTab, activeTabId } = useTabs()

  const activeTab = getActiveTab()
  const tabUrl = activeTab?.url
  const tabIsLoading = activeTab?.isLoading || isLoading
  const tabError = activeTab?.error

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

  const handleIframeLoad = () => {}
  const handleIframeError = () => {}

  return (
    <div className={cn("flex h-full flex-col", className)}>
      <TabBar />

      <div className="flex h-12 items-center gap-3 border-b border-[#1a1a1a] px-4 bg-[#0f0f0f]">
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-8 w-8 text-gray-500 hover:text-gray-300 hover:bg-[#1a1a1a]" disabled={!tabUrl}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8 text-gray-500 hover:text-gray-300 hover:bg-[#1a1a1a]" disabled={!tabUrl}>
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8 text-gray-500 hover:text-gray-300 hover:bg-[#1a1a1a]" disabled={!tabUrl} title="Refresh">
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex-1">
          <Input
            type="text"
            value={tabUrl || "v0.dev/preview"}
            className="h-8 w-full text-sm rounded-md bg-[#1a1a1a] border-[#2a2a2a] text-gray-400 focus:border-gray-600 focus:ring-0"
            readOnly
          />
        </div>

        <div className="flex items-center gap-1">
          {tabUrl && (
            <>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-gray-500 hover:text-gray-300 hover:bg-[#1a1a1a]"
                onClick={() => window.open(tabUrl, "_blank")}
                title="Open in new tab"
              >
                <ExternalLink className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" className="h-8 w-8 text-gray-500 hover:text-gray-300 hover:bg-[#1a1a1a]" title="Fullscreen">
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
