"use client"

import { ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"

// Available models - model IDs (Anthropic direct or OpenRouter)
export const AVAILABLE_MODELS = [
  { id: "claude-opus-4-6", name: "Claude Opus 4.6", provider: "Anthropic" },
  { id: "anthropic/claude-opus-4.5", name: "Claude Opus 4.5", provider: "Anthropic" },
  { id: "anthropic/claude-sonnet-4.5", name: "Claude Sonnet 4.5", provider: "Anthropic" },
  { id: "anthropic/claude-haiku-4.5", name: "Claude Haiku 4.5", provider: "Anthropic" },
  { id: "deepseek/deepseek-v3.2-speciale", name: "DeepSeek V3.2 Speciale", provider: "DeepSeek" },
  { id: "deepseek/deepseek-v3.2", name: "DeepSeek V3.2", provider: "DeepSeek" },
  { id: "z-ai/glm-4.7-flash", name: "GLM 4.7 Flash", provider: "Z-AI" },
  { id: "z-ai/glm-4.7", name: "GLM 4.7", provider: "Z-AI" },
  { id: "x-ai/grok-4.1-fast", name: "Grok 4.1 Fast", provider: "xAI" },
  { id: "x-ai/grok-code-fast-1", name: "Grok Code Fast 1", provider: "xAI" },
  { id: "moonshotai/kimi-k2.5", name: "Kimi K2.5", provider: "Moonshot" },
  { id: "moonshotai/kimi-k2-thinking", name: "Kimi K2 Thinking", provider: "Moonshot" },
] as const

export type ModelId = typeof AVAILABLE_MODELS[number]["id"]

interface ModelSelectorProps {
  selectedModel: string
  onModelChange: (model: string) => void
  className?: string
  disabled?: boolean
  compact?: boolean  // Compact mode for inline display
}

export function ModelSelector({
  selectedModel,
  onModelChange,
  className,
  disabled = false,
  compact = false,
}: ModelSelectorProps) {
  const currentModel = AVAILABLE_MODELS.find(m => m.id === selectedModel) || AVAILABLE_MODELS[0]

  return (
    <div className={cn("relative", compact ? "min-w-0 flex-1" : "inline-block", className)}>
      <select
        value={selectedModel}
        onChange={(e) => onModelChange(e.target.value)}
        disabled={disabled}
        aria-label="Select AI model"
        className={cn(
          "appearance-none bg-surface-elevated border border-interactive-border rounded-md cursor-pointer",
          "hover:bg-interactive-hover focus:outline-none focus:ring-1 focus:ring-blue-500",
          "disabled:opacity-50 disabled:cursor-not-allowed transition-colors",
          compact
            ? "w-full pl-2 pr-6 py-1 text-xs text-text-secondary truncate"
            : "pl-3 pr-8 py-1.5 text-sm text-text-primary"
        )}
      >
        {AVAILABLE_MODELS.map((model) => (
          <option key={model.id} value={model.id}>
            {compact ? model.name : `${model.name} (${model.provider})`}
          </option>
        ))}
      </select>
      <ChevronDown className={cn(
        "absolute top-1/2 -translate-y-1/2 text-text-muted pointer-events-none",
        compact ? "right-1 h-3 w-3" : "right-2 h-4 w-4"
      )} />
    </div>
  )
}

