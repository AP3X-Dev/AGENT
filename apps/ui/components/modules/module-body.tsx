"use client"

import { cn } from "@/lib/utils"
import type { ModuleBodyProps } from "@/types/modules"

/**
 * Padding configuration
 */
const paddingClasses = {
  none: "p-0",
  sm: "p-2",
  md: "p-4",
  lg: "p-6",
} as const

/**
 * Background configuration
 */
const backgroundClasses = {
  transparent: "bg-transparent",
  primary: "bg-primary-background",
  surface: "bg-surface",
  elevated: "bg-surface-elevated",
} as const

/**
 * Overflow configuration
 */
const overflowClasses = {
  auto: "overflow-auto",
  hidden: "overflow-hidden",
  scroll: "overflow-scroll",
  visible: "overflow-visible",
} as const

/**
 * ModuleBody Component
 * 
 * A flexible container for module content with:
 * - Configurable padding
 * - Multiple background variants
 * - Customizable overflow behavior
 * - Optional horizontal scrolling
 */
export function ModuleBody({
  children,
  padding = "none",
  background = "primary",
  overflow = "auto",
  horizontalScroll = false,
  className,
}: ModuleBodyProps) {
  return (
    <div
      className={cn(
        "flex-1 min-h-0", // min-h-0 enables flex child to scroll properly
        paddingClasses[padding],
        backgroundClasses[background],
        overflowClasses[overflow],
        horizontalScroll && "overflow-x-auto",
        className
      )}
    >
      {children}
    </div>
  )
}

