"use client"

import { Plus, Trash2, MessageSquare, ArrowLeft, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { useChat } from "@/providers"
import type { ThreadInfo, ThreadHistoryGroup } from "@/types/types"

// Group threads by time period
function groupThreadsByDate(threads: ThreadInfo[]): ThreadHistoryGroup[] {
  const now = new Date()
  const groups: Record<string, ThreadInfo[]> = {
    "Today": [],
    "Yesterday": [],
    "Last 7 days": [],
    "Last 30 days": [],
    "Older": [],
  }

  for (const thread of threads) {
    if (!thread.updatedAt) {
      groups["Older"].push(thread)
      continue
    }
    const date = new Date(thread.updatedAt)
    const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24))

    if (diffDays === 0) groups["Today"].push(thread)
    else if (diffDays === 1) groups["Yesterday"].push(thread)
    else if (diffDays <= 7) groups["Last 7 days"].push(thread)
    else if (diffDays <= 30) groups["Last 30 days"].push(thread)
    else groups["Older"].push(thread)
  }

  return Object.entries(groups)
    .filter(([, threads]) => threads.length > 0)
    .map(([label, threads]) => ({ label, threads }))
}

// Format timestamp to relative time or date
function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return ""
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / (1000 * 60))
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
  
  if (diffMins < 1) return "Just now"
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

interface ThreadHistoryProps {
  className?: string
}

export function ThreadHistory({ className }: ThreadHistoryProps) {
  const { threads, threadsLoading, threadId, selectThread, deleteThread, createNewThread, toggleThreadHistory } = useChat()
  const groupedThreads = groupThreadsByDate(threads)

  return (
    <div className={cn("flex flex-col h-full bg-[#0a0a0a]", className)}>
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-[#1a1a1a]">
        <button
          onClick={toggleThreadHistory}
          className="p-1 rounded hover:bg-[#1a1a1a] transition-colors text-text-secondary hover:text-text-primary"
          title="Back to chat"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <h2 className="text-sm font-medium text-text-primary flex-1">Thread History</h2>
        <button
          onClick={createNewThread}
          className="flex items-center gap-1 px-2 py-1 rounded text-xs bg-[#1a1a1a] border border-[#2a2a2a] text-text-secondary hover:bg-[#252525] hover:text-text-primary transition-colors"
          title="New thread"
        >
          <Plus className="h-3 w-3" />
          <span>New</span>
        </button>
      </div>

      {/* Thread List */}
      <div className="flex-1 overflow-auto thin-scrollbar">
        {threadsLoading ? (
          <div className="flex items-center justify-center py-8 text-text-muted">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        ) : groupedThreads.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-text-muted">
            <MessageSquare className="h-8 w-8 mb-2 opacity-50" />
            <p className="text-sm">No threads yet</p>
            <p className="text-xs mt-1">Start a conversation to create a thread</p>
          </div>
        ) : (
          <div className="p-2 space-y-4">
            {groupedThreads.map((group) => (
              <div key={group.label}>
                <h3 className="text-[11px] font-medium text-text-muted uppercase tracking-wider px-2 mb-1">
                  {group.label}
                </h3>
                <div className="space-y-0.5">
                  {group.threads.map((thread) => (
                    <ThreadItem
                      key={thread.threadId}
                      thread={thread}
                      isActive={thread.threadId === threadId}
                      onSelect={() => selectThread(thread.threadId)}
                      onDelete={() => deleteThread(thread.threadId)}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

interface ThreadItemProps {
  thread: ThreadInfo
  isActive: boolean
  onSelect: () => void
  onDelete: () => void
}

function ThreadItem({ thread, isActive, onSelect, onDelete }: ThreadItemProps) {
  return (
    <div
      className={cn(
        "group flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer transition-colors",
        isActive ? "bg-[#1a1a1a] border border-[#2a2a2a]" : "hover:bg-[#141414]"
      )}
      onClick={onSelect}
    >
      <MessageSquare className="h-3.5 w-3.5 text-text-muted flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-[13px] text-text-primary truncate">
          {thread.preview || `Thread ${thread.threadId.slice(0, 8)}`}
        </p>
        <p className="text-[11px] text-text-muted">{formatRelativeTime(thread.updatedAt)}</p>
      </div>
      <button
        onClick={(e) => { e.stopPropagation(); onDelete() }}
        className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-[#2f1a1a] hover:text-red-400 text-text-muted transition-all"
        title="Delete thread"
      >
        <Trash2 className="h-3 w-3" />
      </button>
    </div>
  )
}

