"use client"

import { createContext, useContext, useEffect, useState, useCallback, useRef, type ReactNode } from "react"
import { isStandaloneUi } from "@/lib/standalone"

const AGENT_SCRAPER_HOST = process.env.NEXT_PUBLIC_AGENT_SCRAPER_HOST || "158.101.33.117"
const AGENT_SCRAPER_PORT = process.env.NEXT_PUBLIC_AGENT_SCRAPER_PORT || "3000"
const AGENT_SCRAPER_URL = `http://${AGENT_SCRAPER_HOST}:${AGENT_SCRAPER_PORT}`

// Local browser server URL - for user-interactive sessions
// Run: python AP3X-UI/python/browser_ws_server.py
const LOCAL_BROWSER_WS_URL = isStandaloneUi()
  ? "mock://browser"
  : (process.env.NEXT_PUBLIC_BROWSER_WS_URL || "ws://localhost:8765")

// Use local server by default for better user interaction support
const USE_LOCAL_SERVER = isStandaloneUi() ? true : process.env.NEXT_PUBLIC_USE_LOCAL_BROWSER !== "false"

// Debug mode - enable verbose logging
const DEBUG_MODE = process.env.NEXT_PUBLIC_BROWSER_DEBUG === "true"

// Logger utility - info/debug only when DEBUG_MODE is on
const log = {
  debug: (...args: unknown[]) => { if (DEBUG_MODE) console.log("[BrowserSession]", ...args) },
  info: (...args: unknown[]) => { if (DEBUG_MODE) console.log("[BrowserSession]", ...args) },
  warn: (...args: unknown[]) => console.warn("[BrowserSession]", ...args),
  error: (...args: unknown[]) => console.error("[BrowserSession]", ...args),
}

export interface BrowserSession {
  sessionId: string
  wsPath: string
  streamPort?: number
  url: string
  createdAt: number
  isLocal?: boolean  // Whether this is a local browser session
}

interface BrowserSessionContextType {
  session: BrowserSession | null
  isInitializing: boolean
  error: string | null
  initSession: (startUrl?: string) => Promise<BrowserSession | null>
  closeSession: (sessionId?: string) => Promise<void>
  navigateSession: (url: string) => void
  registerSession: (session: BrowserSession) => void
}

const BrowserSessionContext = createContext<BrowserSessionContextType | undefined>(undefined)

export function useBrowserSession() {
  const context = useContext(BrowserSessionContext)
  if (!context) {
    throw new Error("useBrowserSession must be used within a BrowserSessionProvider")
  }
  return context
}

// Standalone function to close a session - can be called from anywhere
export async function closeBrowserSession(sessionId: string): Promise<void> {
  if (!sessionId) return

  // Skip remote API calls for local sessions
  if (sessionId === "local" || sessionId === "local-fallback" || sessionId === "mock") {
    log.debug("Skipping server close for local session:", sessionId)
    return
  }

  log.info("Closing session on server:", sessionId)

  // Standalone/proxied stop endpoint.
  // Original upstream endpoints:
  // - POST `${AGENT_SCRAPER_URL}/v1/live/stop` with `{ sessionId }`
  // - DELETE `${AGENT_SCRAPER_URL}/v1/sessions/{id}`
  try {
    const res = await fetch("/api/browser/live/stop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionId }),
    })
    if (res.ok) return
  } catch {
    // Ignore.
  }
}

export function BrowserSessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<BrowserSession | null>(null)
  const [isInitializing, setIsInitializing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const sessionRef = useRef<BrowserSession | null>(null)

  // Keep ref in sync with state for cleanup handlers
  useEffect(() => {
    sessionRef.current = session
  }, [session])

  // Register an externally-created session (e.g., from agent MCP tools)
  const registerSession = useCallback((newSession: BrowserSession) => {
    log.info("Registering session:", newSession.sessionId)
    setSession(newSession)
  }, [])

  // Initialize a persistent browser session with streaming enabled
  // Supports both local mode (WebSocket server) and remote mode (agent-scraper API)
  const initSession = useCallback(async (startUrl = "https://www.google.com"): Promise<BrowserSession | null> => {
    // If we already have a session, return it (reuse instead of creating new)
    if (session) {
      log.debug("Reusing existing session:", session.sessionId)
      return session
    }

    setIsInitializing(true)
    setError(null)

    // Local mode (standalone uses a mock WebSocket)
    if (USE_LOCAL_SERVER) {
      log.info("Using local browser server at", LOCAL_BROWSER_WS_URL)

      // For local mode, we create a "virtual" session that connects directly to the local WS server
      // The actual browser session is created when the WebSocket connection is established
      const localSession: BrowserSession = {
        sessionId: LOCAL_BROWSER_WS_URL.startsWith("mock://") ? "mock" : "local",
        wsPath: LOCAL_BROWSER_WS_URL,  // Full WebSocket URL for local mode
        url: startUrl,
        createdAt: Date.now(),
        isLocal: true,
      }

      setSession(localSession)
      log.info("Local session ready - browser tab will connect to local server")
      setIsInitializing(false)
      return localSession
    }

    // Remote mode: call proxied API route
    try {
      log.info("Starting remote browser session...")
      const liveRes = await fetch(`/api/browser/live/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: startUrl }),
      })

      if (!liveRes.ok) {
        throw new Error(`Failed to start live session: ${liveRes.status}`)
      }

      const liveData = await liveRes.json()
      log.debug("Live session started:", liveData)

      if (!liveData.ok || !liveData.sessionId) {
        throw new Error(liveData.error || "Failed to create session")
      }

      const newSession: BrowserSession = {
        sessionId: liveData.sessionId,
        wsPath: liveData.wsPath,
        streamPort: liveData.streamPort,
        url: startUrl,
        createdAt: Date.now(),
        isLocal: false,
      }

      setSession(newSession)
      log.info("Remote session ready:", newSession.sessionId)
      return newSession
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      log.error("Failed to initialize remote session:", message)

      // If remote fails, try local as fallback
      log.info("Attempting fallback to local browser server...")
      try {
        const fallbackSession: BrowserSession = {
          sessionId: "local-fallback",
          wsPath: LOCAL_BROWSER_WS_URL,
          url: startUrl,
          createdAt: Date.now(),
          isLocal: true,
        }

        setSession(fallbackSession)
        log.info("Fallback to local session successful")
        return fallbackSession
      } catch (fallbackErr) {
        log.error("Fallback to local also failed:", fallbackErr)
        setError(message)
        return null
      }
    } finally {
      setIsInitializing(false)
    }
  }, [session])

  // Close the session - optionally pass a specific sessionId
  const closeSession = useCallback(async (sessionId?: string) => {
    const idToClose = sessionId || session?.sessionId
    if (!idToClose) return

    await closeBrowserSession(idToClose)

    // Only clear state if closing the current session
    if (!sessionId || sessionId === session?.sessionId) {
      setSession(null)
    }
  }, [session])

  // Navigate the current session to a new URL (via WebSocket command)
  // This is a placeholder - actual navigation is handled by the module
  const navigateSession = useCallback((url: string) => {
    if (session) {
      log.debug("Navigate request to:", url)
      // The actual navigation is handled by AgentBrowserModule via pendingNavigation prop
    }
  }, [session])

  // Cleanup on browser close/refresh
  useEffect(() => {
    const handleBeforeUnload = () => {
      // Close session when browser window closes
      // Skip beacon for local sessions - they clean themselves up
      if (sessionRef.current && !sessionRef.current.isLocal) {
        // Use sendBeacon for reliable cleanup during page unload
        // Note: sendBeacon only supports POST, so we use /v1/live/stop with JSON body
        const url = `/api/browser/live/stop`
        const body = JSON.stringify({ sessionId: sessionRef.current.sessionId })
        navigator.sendBeacon(url, new Blob([body], { type: "application/json" }))
        log.debug("Sent close beacon for:", sessionRef.current.sessionId)
      }
    }

    window.addEventListener("beforeunload", handleBeforeUnload)
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload)
    }
  }, [])

  return (
    <BrowserSessionContext.Provider
      value={{
        session,
        isInitializing,
        error,
        initSession,
        closeSession,
        navigateSession,
        registerSession,
      }}
    >
      {children}
    </BrowserSessionContext.Provider>
  )
}
