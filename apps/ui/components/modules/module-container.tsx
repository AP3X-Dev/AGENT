"use client"

import { cn } from "@/lib/utils"
import { ModuleHeader } from "./module-header"
import { ModuleBody } from "./module-body"
import type { ModuleContainerProps } from "@/types/modules"

/**
 * ModuleContainer Component
 * 
 * The base container for all module types. Provides a consistent structure with:
 * - Optional header section (configurable per module)
 * - Flexible body section that adapts to any content type
 * - Framework-agnostic design for future agentic control
 * 
 * Usage:
 * ```tsx
 * <ModuleContainer
 *   showHeader={true}
 *   headerConfig={{
 *     title: "Browser",
 *     rightActions: [{ id: "refresh", label: "", icon: RefreshCw, onClick: handleRefresh }]
 *   }}
 *   bodyConfig={{ background: "primary", overflow: "hidden" }}
 * >
 *   <iframe src={url} className="w-full h-full" />
 * </ModuleContainer>
 * ```
 */
export function ModuleContainer({
  config,
  headerConfig,
  bodyConfig,
  children,
  showHeader = true,
  className,
}: ModuleContainerProps) {
  // Merge default header config with provided config
  const mergedHeaderConfig = {
    ...config?.defaultHeaderConfig,
    ...headerConfig,
  }

  // Determine if header should be shown
  const shouldShowHeader = showHeader && (config?.hasHeader !== false)

  return (
    <div className={cn("flex h-full flex-col", className)}>
      {shouldShowHeader && Object.keys(mergedHeaderConfig).length > 0 && (
        <ModuleHeader {...mergedHeaderConfig} />
      )}
      <ModuleBody {...bodyConfig}>
        {children}
      </ModuleBody>
    </div>
  )
}

/**
 * EmptyModuleState Component
 * 
 * A reusable empty state for modules without content
 */
export function EmptyModuleState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon?: React.ComponentType<{ className?: string }>
  title: string
  description?: string
  action?: React.ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        "flex h-full w-full items-center justify-center p-8",
        "bg-primary-background",
        className
      )}
    >
      <div className="flex flex-col items-center gap-4 text-center max-w-md">
        {Icon && (
          <div className="rounded-full bg-surface-elevated p-4">
            <Icon className="h-8 w-8 text-text-muted" />
          </div>
        )}
        <h3 className="text-lg font-medium text-text-secondary">{title}</h3>
        {description && (
          <p className="text-sm text-text-muted">{description}</p>
        )}
        {action && <div className="mt-2">{action}</div>}
      </div>
    </div>
  )
}

/**
 * LoadingModuleState Component
 * 
 * A reusable loading state for modules
 */
export function LoadingModuleState({
  message = "Loading...",
  className,
}: {
  message?: string
  className?: string
}) {
  return (
    <div
      className={cn(
        "flex h-full w-full items-center justify-center p-8",
        "bg-primary-background",
        className
      )}
    >
      <div className="flex flex-col items-center gap-4">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-text-muted border-t-status-info" />
        <p className="text-sm text-text-secondary font-medium">{message}</p>
      </div>
    </div>
  )
}

/**
 * ErrorModuleState Component
 * 
 * A reusable error state for modules
 */
export function ErrorModuleState({
  error,
  onRetry,
  className,
}: {
  error: string
  onRetry?: () => void
  className?: string
}) {
  return (
    <div
      className={cn(
        "flex h-full w-full items-center justify-center p-8",
        "bg-primary-background",
        className
      )}
    >
      <div className="flex flex-col items-center gap-4 text-center max-w-md">
        <div className="rounded-full bg-[#2f1a1a] border border-[#4a2a2a] p-4">
          <svg
            className="h-8 w-8 text-status-error"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </div>
        <h3 className="text-lg font-medium text-text-primary">Error</h3>
        <p className="text-sm text-text-muted">{error}</p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="mt-2 px-4 py-2 text-sm font-medium text-text-primary bg-surface-elevated hover:bg-interactive-hover rounded-md transition-colors"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  )
}

