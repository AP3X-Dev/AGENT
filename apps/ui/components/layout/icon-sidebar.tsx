"use client"

import { Button } from "@/components/ui/button"
import { MessageSquare, Files, Search, Map, Code, Settings, PlusCircle, Globe, Users, Wrench, Zap, Maximize2, Minimize2, Plug, Activity, CalendarClock } from "lucide-react"
import { cn } from "@/lib/utils"
import { useTabs } from "@/providers/tabs-provider"
import { useBrowserSession, useApp } from "@/providers"
import { useState } from "react"
import Image from "next/image"

interface IconSidebarProps {
  className?: string
}

export function IconSidebar({ className }: IconSidebarProps) {
  const { addTab, tabs, setActiveTab } = useTabs()
  const { session, initSession, isInitializing } = useBrowserSession()
  const { chatExpanded, toggleChatExpanded } = useApp()
  const [isStartingBrowser, setIsStartingBrowser] = useState(false)

  const handleMapClick = () => {
    addTab({
      title: "Google Maps",
      url: "https://www.google.com/maps",
      isLoading: false,
    })
    addTab({
      title: "Street View",
      url: "https://www.google.com/maps/@40.7580,-73.9855,3a,75y,90t/data=!3m6!1e1!3m4!1s0x0:0x0!2e0!7i16384!8i8192",
      isLoading: false,
    })
  }

  const handleBrowserClick = async () => {
    if (isStartingBrowser || isInitializing) return

    // Check if there's already an agent-browser tab
    const existingTab = tabs.find(t => t.moduleType === 'agent-browser')
    if (existingTab) {
      console.log("[Sidebar] Reusing existing browser tab:", existingTab.id)
      setActiveTab(existingTab.id)
      return
    }

    setIsStartingBrowser(true)

    try {
      // Use the centralized session provider - it will reuse if one exists
      const browserSession = await initSession("https://www.google.com")

      if (browserSession) {
        console.log("[Sidebar] Browser session ready:", browserSession.sessionId)
        addTab({
          title: "Agent Browser",
          moduleType: "agent-browser",
          moduleData: {
            sessionId: browserSession.sessionId,
            wsPath: browserSession.wsPath,
            initialUrl: "https://www.google.com",
          },
          icon: "Globe",
        })
      } else {
        console.error("[Sidebar] Failed to start browser session")
      }
    } catch (err) {
      console.error("[Sidebar] Browser start error:", err)
    } finally {
      setIsStartingBrowser(false)
    }
  }

  const handleAgentsLibraryClick = () => {
    // Check if there's already an agents-library tab
    const existingTab = tabs.find(t => t.moduleType === 'agents-library')
    if (existingTab) {
      setActiveTab(existingTab.id)
      return
    }
    addTab({
      title: "Agents Library",
      moduleType: "agents-library",
      icon: "Users",
    })
  }

  const handleSkillsLibraryClick = () => {
    // Check if there's already a skills-library tab
    const existingTab = tabs.find(t => t.moduleType === 'skills-library')
    if (existingTab) {
      setActiveTab(existingTab.id)
      return
    }
    addTab({
      title: "Skills Library",
      moduleType: "skills-library",
      icon: "Zap",
    })
  }

  const handleToolsLibraryClick = () => {
    // Check if there's already a tools-library tab
    const existingTab = tabs.find(t => t.moduleType === 'tools-library')
    if (existingTab) {
      setActiveTab(existingTab.id)
      return
    }
    addTab({
      title: "Tools Library",
      moduleType: "tools-library",
      icon: "Wrench",
    })
  }

  const handleMcpManagerClick = () => {
    // Check if there's already an mcp-manager tab
    const existingTab = tabs.find(t => t.moduleType === 'mcp-manager')
    if (existingTab) {
      setActiveTab(existingTab.id)
      return
    }
    addTab({
      title: "MCP Manager",
      moduleType: "mcp-manager",
      icon: "Plug",
    })
  }

  const handleSchedulerClick = () => {
    const existingTab = tabs.find(t => t.moduleType === 'scheduler')
    if (existingTab) {
      setActiveTab(existingTab.id)
      return
    }
    addTab({
      title: "Scheduler",
      moduleType: "scheduler",
      icon: "CalendarClock",
    })
  }

  const handleAg3ntControlPanelClick = () => {
    const existingTab = tabs.find(t => t.moduleType === 'ag3nt-control-panel')
    if (existingTab) {
      setActiveTab(existingTab.id)
      return
    }
    addTab({
      title: "AG3NT Control Panel",
      moduleType: "ag3nt-control-panel",
      icon: "Activity",
    })
  }

  return (
    <aside
      data-testid="icon-sidebar"
      className={cn(
        "flex flex-col items-center gap-2 bg-secondary-background py-3 px-2",
        className,
      )}
    >
      {/* Logo at top */}
      <div className="mb-2">
        <Image src="/images/logo.png" alt="Logo" width={32} height={32} className="h-8 w-8" />
      </div>

      {/* Top icons */}
      <div className="flex flex-col items-center gap-1">
        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 rounded-lg bg-[#2a2a2a] text-text-primary hover:bg-[#333333]"
          title="New Chat"
        >
          <PlusCircle className="h-5 w-5" />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className={cn(
            "h-10 w-10 rounded-lg hover:bg-interactive-hover hover:text-text-primary",
            chatExpanded
              ? "bg-[#2a2a2a] text-text-primary"
              : "text-text-secondary"
          )}
          title={chatExpanded ? "Collapse Chat" : "Expand Chat"}
          onClick={toggleChatExpanded}
        >
          {chatExpanded ? (
            <Minimize2 className="h-5 w-5" />
          ) : (
            <Maximize2 className="h-5 w-5" />
          )}
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 rounded-lg text-text-secondary hover:bg-interactive-hover hover:text-text-primary"
          title="Files"
        >
          <Files className="h-5 w-5" />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 rounded-lg text-text-secondary hover:bg-interactive-hover hover:text-text-primary"
          title="Search"
        >
          <Search className="h-5 w-5" />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 rounded-lg text-text-secondary hover:bg-interactive-hover hover:text-text-primary"
          title="Maps"
          onClick={handleMapClick}
        >
          <Map className="h-5 w-5" />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 rounded-lg text-text-secondary hover:bg-interactive-hover hover:text-text-primary"
          title="Code"
        >
          <Code className="h-5 w-5" />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className={cn(
            "h-10 w-10 rounded-lg text-text-secondary hover:bg-interactive-hover hover:text-text-primary",
            isStartingBrowser && "animate-pulse"
          )}
          title="Browser"
          onClick={handleBrowserClick}
          disabled={isStartingBrowser}
        >
          <Globe className="h-5 w-5" />
        </Button>

        {/* Library buttons */}
        <div className="w-8 border-t border-[#2a2a2a] my-1" />

        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 rounded-lg text-text-secondary hover:bg-interactive-hover hover:text-text-primary"
          title="Agents Library"
          onClick={handleAgentsLibraryClick}
        >
          <Users className="h-5 w-5" />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 rounded-lg text-text-secondary hover:bg-interactive-hover hover:text-text-primary"
          title="Skills Library"
          onClick={handleSkillsLibraryClick}
        >
          <Zap className="h-5 w-5" />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 rounded-lg text-text-secondary hover:bg-interactive-hover hover:text-text-primary"
          title="Tools Library"
          onClick={handleToolsLibraryClick}
        >
          <Wrench className="h-5 w-5" />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 rounded-lg text-text-secondary hover:bg-interactive-hover hover:text-text-primary"
          title="MCP Manager"
          onClick={handleMcpManagerClick}
        >
          <Plug className="h-5 w-5" />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 rounded-lg text-text-secondary hover:bg-interactive-hover hover:text-text-primary"
          title="Scheduler"
          onClick={handleSchedulerClick}
        >
          <CalendarClock className="h-5 w-5" />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 rounded-lg text-text-secondary hover:bg-interactive-hover hover:text-text-primary"
          title="AG3NT Control Panel"
          onClick={handleAg3ntControlPanelClick}
        >
          <Activity className="h-5 w-5" />
        </Button>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Bottom icons */}
      <div className="flex flex-col items-center gap-1">
        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 rounded-lg text-text-secondary hover:bg-interactive-hover hover:text-text-primary"
          title="Settings"
        >
          <Settings className="h-5 w-5" />
        </Button>
      </div>
    </aside>
  )
}
