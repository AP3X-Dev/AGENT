"use client"

import { Plus, ListTodo, MessageSquare, Menu } from "lucide-react"
import { cn } from "@/lib/utils"
import { useTasks, useChat } from "@/providers"

interface ThreadHeaderProps {
  threadId: string | null
  onNewThread: () => void
  className?: string
}

export function ThreadHeader({ threadId, onNewThread, className }: ThreadHeaderProps) {
  const { tasks, isVisible: tasksVisible, toggleTasksView } = useTasks()
  const { toggleThreadHistory, showThreadHistory } = useChat()

  // Calculate task counts for badge
  const taskCount = tasks.length
  const completedCount = countCompleted(tasks)

  // Generate session title from thread ID or use default
  const sessionTitle = threadId ? `AG3NT Session` : "New Session"

  return (
    <div
      className={cn(
        "bg-surface-header flex h-8 items-center px-3 border-b border-[#1a1a1a] relative",
        className
      )}
    >
      {/* Left side: Hamburger menu + Session Title */}
      <div className="flex items-center gap-2">
        <button
          onClick={toggleThreadHistory}
          className={cn(
            "p-1 rounded transition-colors",
            showThreadHistory
              ? "bg-[#1a1a1a] text-text-primary"
              : "text-text-secondary hover:bg-[#1a1a1a] hover:text-text-primary"
          )}
          title="Thread History"
          aria-label="Toggle thread history"
        >
          <Menu className="h-4 w-4" />
        </button>
        <h1
          className="text-[13px] font-medium text-text-primary truncate"
          title={threadId || "No active session"}
        >
          {sessionTitle}
        </h1>
      </div>

      {/* Actions - Positioned absolutely on the right */}
      <div className="absolute right-3 flex items-center gap-1">
        {/* Tasks toggle button */}
        <button
          onClick={toggleTasksView}
          className={cn(
            "flex items-center gap-1.5 px-2 py-0.75 rounded-md text-xs font-medium",
            "border transition-colors",
            tasksVisible
              ? "bg-[#1E1E1E] border-[#3a3a3a] text-text-primary"
              : "bg-[#1a1a1a] border-[#2a2a2a] text-text-secondary hover:bg-[#252525] hover:border-[#3a3a3a] hover:text-text-primary"
          )}
          title={tasksVisible ? "Show Chat" : "Show Tasks"}
          aria-label={tasksVisible ? "Show Chat" : "Show Tasks"}
        >
          {tasksVisible ? (
            <MessageSquare className="h-3.5 w-3.5" />
          ) : (
            <ListTodo className="h-3.5 w-3.5" />
          )}
          <span>{tasksVisible ? "Chat" : "Tasks"}</span>
          {taskCount > 0 && !tasksVisible && (
            <span className="ml-1 px-1.5 py-0.5 text-[10px] rounded-full bg-[#2a2a2a] text-text-muted">
              {completedCount}/{taskCount}
            </span>
          )}
        </button>

        {/* New thread button */}
        <button
          onClick={onNewThread}
          className={cn(
            "flex items-center gap-1.5 px-2 py-0.75 rounded-md text-xs font-medium",
            "bg-[#1a1a1a] border border-[#2a2a2a] text-text-secondary",
            "hover:bg-[#252525] hover:border-[#3a3a3a] hover:text-text-primary",
            "transition-colors"
          )}
          title="Start a new thread"
          aria-label="Start a new thread"
        >
          <Plus className="h-3.5 w-3.5" />
          <span>New</span>
        </button>
      </div>
    </div>
  )
}

// Helper to count completed tasks recursively
function countCompleted(tasks: { status: string; children?: any[] }[]): number {
  let count = 0
  for (const task of tasks) {
    if (task.status === 'completed') count++
    if (task.children) count += countCompleted(task.children)
  }
  return count
}

