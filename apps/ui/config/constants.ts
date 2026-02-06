import type { AppConfig } from "@/types/types"

// Layout constants
export const SIDEBAR_CONFIG = {
  MIN_WIDTH: 280,
  MAX_WIDTH: 700,
  DEFAULT_WIDTH: 500, // Increased by 10% from 455
} as const

// App configuration
export const APP_CONFIG: AppConfig = {
  features: {
    cliIntegration: true,
    fileOperations: true,
    shellCommands: true,
  },
}

// UI Constants
export const UI_CONFIG = {
  HEADER_HEIGHT: 48, // 12 * 4 = 48px
  ANIMATION_DURATION: 200,
  TEXTAREA_MIN_HEIGHT: 96, // 24 * 4 = 96px
} as const

// Status types for file explorer
export const FILE_STATUS = {
  GENERATED: "generated",
  MODIFIED: "modified",
  UNCHANGED: "unchanged",
} as const
