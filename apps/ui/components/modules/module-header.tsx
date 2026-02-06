"use client"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Loader2 } from "lucide-react"
import type { ModuleHeaderProps, BreadcrumbItem, HeaderAction, StatusIndicator } from "@/types/modules"

/**
 * Height configuration for header variants
 */
const headerHeights = {
  sm: "h-10",
  md: "h-12",
  lg: "h-14",
} as const

/**
 * Status indicator colors
 */
const statusColors = {
  success: "bg-status-success",
  warning: "bg-status-warning",
  error: "bg-status-error",
  info: "bg-status-info",
  loading: "bg-status-info",
} as const

/**
 * Breadcrumb navigation component
 */
function Breadcrumbs({ items }: { items: BreadcrumbItem[] }) {
  return (
    <nav className="flex items-center gap-1 text-sm">
      {items.map((item, index) => (
        <span key={index} className="flex items-center gap-1">
          {index > 0 && <span className="text-text-muted mx-1">/</span>}
          {item.icon && <item.icon className="h-3.5 w-3.5 text-text-muted" />}
          {item.onClick || item.href ? (
            <button
              onClick={item.onClick}
              className="text-text-secondary hover:text-text-primary transition-colors"
            >
              {item.label}
            </button>
          ) : (
            <span className="text-text-primary font-medium">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  )
}

/**
 * Action buttons component
 */
function ActionButtons({ actions }: { actions: HeaderAction[] }) {
  return (
    <div className="flex items-center gap-1">
      {actions.map((action) => (
        <Button
          key={action.id}
          variant={action.variant || "ghost"}
          size="sm"
          onClick={action.onClick}
          disabled={action.disabled}
          title={action.tooltip}
          className="h-8 px-2 text-text-secondary hover:text-text-primary hover:bg-surface-elevated"
        >
          {action.icon && <action.icon className="h-4 w-4" />}
          {action.label && <span className="ml-1.5 text-sm">{action.label}</span>}
        </Button>
      ))}
    </div>
  )
}

/**
 * Status indicator component
 */
function Status({ indicator }: { indicator: StatusIndicator }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className={cn(
          "h-2 w-2 rounded-full",
          statusColors[indicator.type],
          indicator.pulse && "animate-pulse",
          indicator.type === "loading" && "animate-spin"
        )}
      >
        {indicator.type === "loading" && (
          <Loader2 className="h-2 w-2 text-status-info" />
        )}
      </span>
      {indicator.label && (
        <span className="text-xs text-text-muted font-medium">{indicator.label}</span>
      )}
    </div>
  )
}

/**
 * ModuleHeader Component
 * 
 * A flexible header bar for modules with support for:
 * - Title and subtitle
 * - Breadcrumb navigation
 * - Left and right action buttons
 * - Status indicators
 * - Custom content injection
 */
export function ModuleHeader({
  title,
  subtitle,
  breadcrumbs,
  leftActions,
  rightActions,
  status,
  customContent,
  showBorder = true,
  height = "md",
  className,
}: ModuleHeaderProps) {
  return (
    <header
      className={cn(
        "flex items-center justify-between px-4 bg-surface shrink-0",
        headerHeights[height],
        showBorder && "border-b border-interactive-border",
        className
      )}
    >
      {/* Left section: Actions, Breadcrumbs, Title */}
      <div className="flex items-center gap-3 min-w-0 flex-1">
        {leftActions && leftActions.length > 0 && (
          <ActionButtons actions={leftActions} />
        )}
        
        {breadcrumbs && breadcrumbs.length > 0 && (
          <Breadcrumbs items={breadcrumbs} />
        )}
        
        {(title || subtitle) && !breadcrumbs && (
          <div className="flex flex-col justify-center min-w-0">
            {title && (
              <h2 className="text-sm font-medium text-text-primary truncate">
                {title}
              </h2>
            )}
            {subtitle && (
              <p className="text-xs text-text-muted truncate">{subtitle}</p>
            )}
          </div>
        )}
      </div>

      {/* Center section: Custom content */}
      {customContent && (
        <div className="flex-1 flex items-center justify-center px-4">
          {customContent}
        </div>
      )}

      {/* Right section: Status, Actions */}
      <div className="flex items-center gap-3">
        {status && <Status indicator={status} />}
        {rightActions && rightActions.length > 0 && (
          <ActionButtons actions={rightActions} />
        )}
      </div>
    </header>
  )
}

