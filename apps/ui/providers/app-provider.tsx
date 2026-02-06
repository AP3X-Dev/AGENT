"use client"

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react"
import { APP_CONFIG, SIDEBAR_CONFIG } from "@/config/constants"

// App Context Types
interface AppState {
  previewUrl: string | null
  isGenerating: boolean
  sidebarWidth: number
  chatExpanded: boolean
  features: {
    cliIntegration: boolean
    fileOperations: boolean
    shellCommands: boolean
  }
}

interface AppContextType extends AppState {
  setPreviewUrl: (url: string | null) => void
  setIsGenerating: (generating: boolean) => void
  setSidebarWidth: (width: number) => void
  setChatExpanded: (expanded: boolean) => void
  toggleChatExpanded: () => void
  toggleFeature: (feature: keyof AppState["features"]) => void
}

// Initial state
const initialState: AppState = {
  previewUrl: null,
  isGenerating: false,
  sidebarWidth: SIDEBAR_CONFIG.DEFAULT_WIDTH,
  chatExpanded: false,
  features: { ...APP_CONFIG.features },
}

// Context
const AppContext = createContext<AppContextType | undefined>(undefined)

// Provider
interface AppProviderProps {
  children: ReactNode
}

export function AppProvider({ children }: AppProviderProps) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(initialState.previewUrl)
  const [isGenerating, setIsGenerating] = useState(initialState.isGenerating)
  const [sidebarWidth, setSidebarWidth] = useState(initialState.sidebarWidth)
  const [chatExpanded, setChatExpanded] = useState(initialState.chatExpanded)
  const [features, setFeatures] = useState(initialState.features)

  const toggleFeature = useCallback((feature: keyof AppState["features"]) => {
    setFeatures((prev) => ({
      ...prev,
      [feature]: !prev[feature],
    }))
  }, [])

  const toggleChatExpanded = useCallback(() => {
    setChatExpanded((prev) => !prev)
  }, [])

  const contextValue: AppContextType = useMemo(() => ({
    previewUrl,
    isGenerating,
    sidebarWidth,
    chatExpanded,
    features,
    setPreviewUrl,
    setIsGenerating,
    setSidebarWidth,
    setChatExpanded,
    toggleChatExpanded,
    toggleFeature,
  }), [previewUrl, isGenerating, sidebarWidth, chatExpanded, features, toggleChatExpanded, toggleFeature])

  return <AppContext.Provider value={contextValue}>{children}</AppContext.Provider>
}

// Hook to use the app context
export function useApp() {
  const context = useContext(AppContext)
  if (context === undefined) {
    throw new Error("useApp must be used within an AppProvider")
  }
  return context
}
