/**
 * AutocompleteMenu Component
 * Displays autocomplete suggestions for @ file mentions and ! commands
 */

"use client"

import { useEffect, useRef } from "react"
import { cn } from "@/lib/utils"
import type { AutocompleteItem } from "@/types/cli"

interface AutocompleteMenuProps {
  items: AutocompleteItem[]
  selectedIndex: number
  isLoading: boolean
  type: "file" | "command" | null
  onSelect: (index: number) => void
  className?: string
}

export function AutocompleteMenu({
  items,
  selectedIndex,
  isLoading,
  type,
  onSelect,
  className,
}: AutocompleteMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null)
  const selectedRef = useRef<HTMLButtonElement>(null)

  // Scroll selected item into view
  useEffect(() => {
    if (selectedRef.current && menuRef.current) {
      selectedRef.current.scrollIntoView({
        block: "nearest",
        behavior: "smooth",
      })
    }
  }, [selectedIndex])

  if (items.length === 0 && !isLoading) {
    return null
  }

  return (
    <div
      ref={menuRef}
      className={cn(
        "absolute bottom-full left-0 right-0 mb-1 max-h-64 overflow-y-auto",
        "rounded-md border border-interactive-border bg-surface shadow-lg z-50",
        className
      )}
    >
      {/* Header */}
      <div className="sticky top-0 px-3 py-1.5 text-xs text-text-muted bg-surface border-b border-interactive-border">
        {type === "file" && "📁 Files & Directories"}
        {type === "command" && "💻 Commands"}
        {isLoading && " (loading...)"}
      </div>

      {/* Items */}
      <div className="py-1">
        {isLoading && items.length === 0 ? (
          <div className="px-3 py-2 text-sm text-text-muted">Searching...</div>
        ) : (
          items.map((item, index) => (
            <button
              key={item.value}
              ref={index === selectedIndex ? selectedRef : undefined}
              type="button"
              className={cn(
                "w-full px-3 py-1.5 flex items-center gap-2 text-left text-sm",
                "hover:bg-interactive-hover transition-colors",
                index === selectedIndex && "bg-interactive-active"
              )}
              onClick={() => onSelect(index)}
            >
              <span className="w-5 text-center">{item.icon}</span>
              <span className="flex-1 truncate font-mono text-text-primary">
                {item.displayText}
              </span>
              {item.description && (
                <span className="text-xs text-text-muted truncate max-w-[120px]">
                  {item.description}
                </span>
              )}
            </button>
          ))
        )}
      </div>

      {/* Footer hint */}
      <div className="sticky bottom-0 px-3 py-1 text-xs text-text-muted bg-surface border-t border-interactive-border flex gap-3">
        <span>↑↓ Navigate</span>
        <span>Tab Select</span>
        <span>Esc Close</span>
      </div>
    </div>
  )
}

