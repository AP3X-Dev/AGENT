/**
 * InputModeIndicator Component
 * Shows visual indicator for current input mode (chat, file mention, bash)
 */

"use client"

import { cn } from "@/lib/utils"
import type { InputMode } from "@/types/cli"
import { MessageSquare, FolderOpen, Terminal } from "lucide-react"

interface InputModeIndicatorProps {
  mode: InputMode
  hasFileMentions: boolean
  className?: string
}

const modeConfig = {
  chat: {
    label: "Chat",
    icon: MessageSquare,
    className: "bg-[#1a1a2a] text-blue-400 border-[#2a2a3a]",
  },
  "file-mention": {
    label: "File",
    icon: FolderOpen,
    className: "bg-[#1a2a1a] text-emerald-400 border-[#2a3a2a]",
  },
  "bash-command": {
    label: "Bash",
    icon: Terminal,
    className: "bg-[#2a1a2a] text-pink-400 border-[#3a2a3a]",
  },
}

export function InputModeIndicator({
  mode,
  hasFileMentions,
  className,
}: InputModeIndicatorProps) {
  const config = modeConfig[mode]
  const Icon = config.icon

  // Show bash mode prominently
  if (mode === "bash-command") {
    return (
      <div
        className={cn(
          "flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium rounded border",
          config.className,
          className
        )}
      >
        <Icon className="h-3 w-3" />
        <span>BASH MODE</span>
      </div>
    )
  }

  // Show file indicator if there are mentions
  if (hasFileMentions) {
    return (
      <div
        className={cn(
          "flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium rounded border",
          modeConfig["file-mention"].className,
          className
        )}
      >
        <FolderOpen className="h-3 w-3" />
        <span>Files attached</span>
      </div>
    )
  }

  // Default: no indicator for normal chat
  return null
}

