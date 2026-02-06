"use client"

import { cn } from "@/lib/utils"
import { Loader2, Brain, Wrench, CheckCircle } from "lucide-react"

interface AgentStatusProps {
  status: string | null
  message: string | null
  className?: string
}

// Premium staggered dots component
function LoadingDots({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-1 ml-1", className)}>
      <span
        className="w-1 h-1 rounded-full bg-text-secondary animate-staggered-bounce"
        style={{ animationDelay: '0ms' }}
      />
      <span
        className="w-1 h-1 rounded-full bg-text-secondary animate-staggered-bounce"
        style={{ animationDelay: '150ms' }}
      />
      <span
        className="w-1 h-1 rounded-full bg-text-secondary animate-staggered-bounce"
        style={{ animationDelay: '300ms' }}
      />
    </span>
  )
}

export function AgentStatus({ status, message, className }: AgentStatusProps) {
  if (!status || status === 'done') return null

  // Simple status display with smooth fade-in animation
  return (
    <div className={cn(
      "flex items-center gap-2 py-1 text-[12px] text-text-muted",
      "animate-in fade-in slide-in-from-bottom-1 duration-200",
      className
    )}>
      <Loader2 className="h-3 w-3 animate-spin" />
      <span className="transition-all duration-200">{message || 'Generating response...'}</span>
    </div>
  )
}

// Shimmer skeleton for loading content
export function SkeletonShimmer({ className }: { className?: string }) {
  return (
    <div className={cn(
      "rounded-md animate-shimmer",
      className
    )} />
  )
}

// Message skeleton for loading messages
export function MessageSkeleton() {
  return (
    <div className="space-y-3 p-4">
      <div className="flex items-start gap-3">
        <SkeletonShimmer className="h-8 w-8 rounded-full" />
        <div className="flex-1 space-y-2">
          <SkeletonShimmer className="h-4 w-24" />
          <SkeletonShimmer className="h-4 w-full" />
          <SkeletonShimmer className="h-4 w-3/4" />
        </div>
      </div>
    </div>
  )
}

