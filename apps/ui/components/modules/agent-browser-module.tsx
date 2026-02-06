"use client"

import { useEffect, useRef, useState, useCallback, useMemo, useReducer } from "react"
import { ChevronLeft, ChevronRight, RefreshCw, Globe, ExternalLink, X, Eye, Home, Square, Maximize2, Minimize2, Lock, Unlock, Monitor, Users, User, Bot } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { isStandaloneUi } from "@/lib/standalone"
import type { ModuleConfig, ModuleInstanceProps } from "@/types/modules"
import { useAgentConnection } from "@/hooks/use-agent-connection"
import { closeBrowserSession } from "@/providers/browser-session-provider"
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "@/components/ui/tooltip"
import { subscribeToBrowserSession } from "@/lib/browser-session-events"

// Agent-scraper server URL - the remote server running the browser
const AGENT_SCRAPER_HOST = process.env.NEXT_PUBLIC_AGENT_SCRAPER_HOST || "158.101.33.117"
const AGENT_SCRAPER_PORT = process.env.NEXT_PUBLIC_AGENT_SCRAPER_PORT || "3000"

// Local browser server URL - for user-interactive sessions
// Run: python AP3X-UI/python/browser_ws_server.py
const LOCAL_BROWSER_WS_URL = isStandaloneUi()
  ? "mock://browser"
  : (process.env.NEXT_PUBLIC_BROWSER_WS_URL || "ws://localhost:8765")

// Use local server by default for better user interaction support
const USE_LOCAL_SERVER = isStandaloneUi() ? true : process.env.NEXT_PUBLIC_USE_LOCAL_BROWSER !== "false"

// Debug mode - enable verbose logging
const DEBUG_MODE = process.env.NEXT_PUBLIC_BROWSER_DEBUG === "true" || process.env.NODE_ENV === "development"

// Logger utility - only logs when DEBUG_MODE is enabled
const log = {
  debug: (...args: unknown[]) => DEBUG_MODE && console.log('[AgentBrowser]', ...args),
  info: (...args: unknown[]) => console.log('[AgentBrowser]', ...args),
  warn: (...args: unknown[]) => console.warn('[AgentBrowser]', ...args),
  error: (...args: unknown[]) => console.error('[AgentBrowser]', ...args),
}

// =============================================================================
// SINGLETON WebSocket Manager - Lives outside React lifecycle
// =============================================================================
// This prevents React StrictMode double-mount issues by managing the WebSocket
// connection independently of component lifecycle.

interface WsManagerState {
  ws: WebSocket | null
  status: 'disconnected' | 'connecting' | 'connected' | 'error'
  url: string | null
  listeners: Set<(state: WsManagerState) => void>
  messageListeners: Set<(data: ArrayBuffer | string) => void>
  reconnectTimer: ReturnType<typeof setTimeout> | null
  reconnectAttempt: number
  shouldReconnect: boolean
  hasConnectedBefore: boolean  // Only auto-reconnect if we previously connected
  pingTimer: ReturnType<typeof setInterval> | null
  lastPongTime: number
}

const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 30000
const RECONNECT_MAX_TRIES = 10
const PING_INTERVAL_MS = 15000
const PONG_TIMEOUT_MS = 10000

const wsManager: WsManagerState = {
  ws: null,
  status: 'disconnected',
  url: null,
  listeners: new Set(),
  messageListeners: new Set(),
  reconnectTimer: null,
  reconnectAttempt: 0,
  shouldReconnect: true,
  hasConnectedBefore: false,
  pingTimer: null,
  lastPongTime: 0,
}

type MockBrowserState = {
  url: string
  title: string
  history: string[]
  index: number
  frameBase64: string | null
  intervalId: number | null
}

const mockBrowser: MockBrowserState = {
  url: "https://www.google.com",
  title: "Mock Browser",
  history: ["https://www.google.com"],
  index: 0,
  frameBase64: null,
  intervalId: null,
}

function isMockWsUrl(url: string | null | undefined): boolean {
  return typeof url === "string" && url.startsWith("mock://")
}

function sendMockMessage(message: any) {
  const payload = typeof message === "string" ? message : JSON.stringify(message)
  wsManager.messageListeners.forEach((fn) => fn(payload))
}

function renderMockFrame(url: string, title: string): string | null {
  if (typeof document === "undefined") return null

  const canvas = document.createElement("canvas")
  canvas.width = 1280
  canvas.height = 720

  const ctx = canvas.getContext("2d")
  if (!ctx) return null

  // Background
  ctx.fillStyle = "#111111"
  ctx.fillRect(0, 0, canvas.width, canvas.height)

  // Top bar
  ctx.fillStyle = "#1E1E1E"
  ctx.fillRect(0, 0, canvas.width, 64)

  ctx.fillStyle = "#F5F5F5"
  ctx.font = "24px system-ui, -apple-system, Segoe UI, sans-serif"
  ctx.fillText("Mock Browser (Standalone)", 24, 40)

  ctx.fillStyle = "#A0A0A0"
  ctx.font =
    '18px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace'
  ctx.fillText(url, 24, 96)

  ctx.fillStyle = "#666666"
  ctx.font = "16px system-ui, -apple-system, Segoe UI, sans-serif"
  ctx.fillText("This is a stubbed browser session (no external services).", 24, 140)
  ctx.fillText("Navigation UI is interactive; page content is mocked.", 24, 164)

  ctx.fillStyle = "#2A2A2A"
  ctx.fillRect(24, 200, canvas.width - 48, 1)

  ctx.fillStyle = "#A0A0A0"
  ctx.font = "18px system-ui, -apple-system, Segoe UI, sans-serif"
  ctx.fillText(title || "Mock Page", 24, 240)

  ctx.fillStyle = "#F5F5F5"
  ctx.font = "16px system-ui, -apple-system, Segoe UI, sans-serif"
  ctx.fillText("Try:", 24, 280)
  ctx.fillStyle = "#A0A0A0"
  ctx.fillText("- Typing a URL in the bar and pressing Enter", 48, 308)
  ctx.fillText("- Back / Forward buttons", 48, 336)
  ctx.fillText("- Refresh / Stop", 48, 364)

  const dataUrl = canvas.toDataURL("image/jpeg", 0.72)
  const base64 = dataUrl.split(",")[1]
  return base64 || null
}

function updateMockFrame() {
  mockBrowser.frameBase64 = renderMockFrame(mockBrowser.url, mockBrowser.title)
}

function notifyListeners() {
  wsManager.listeners.forEach(fn => fn(wsManager))
}

function wsManagerCancelReconnect(): void {
  if (wsManager.reconnectTimer) {
    clearTimeout(wsManager.reconnectTimer)
    wsManager.reconnectTimer = null
  }
}

function wsManagerStopPing(): void {
  if (wsManager.pingTimer) {
    clearInterval(wsManager.pingTimer)
    wsManager.pingTimer = null
  }
}

function wsManagerStartPing(): void {
  wsManagerStopPing()
  wsManager.lastPongTime = Date.now()
  wsManager.pingTimer = setInterval(() => {
    if (wsManager.ws?.readyState === WebSocket.OPEN) {
      // Send application-level ping (server responds with pong)
      try {
        wsManager.ws.send(JSON.stringify({ type: 'ping', ts: Date.now() }))
      } catch { /* ignore */ }
      // Check if pong timed out
      if (Date.now() - wsManager.lastPongTime > PONG_TIMEOUT_MS + PING_INTERVAL_MS) {
        log.warn('Pong timeout - connection appears dead, reconnecting')
        wsManager.ws?.close(4000, 'Pong timeout')
      }
    }
  }, PING_INTERVAL_MS)
}

function wsManagerScheduleReconnect(): void {
  if (!wsManager.shouldReconnect || !wsManager.url) return
  if (wsManager.reconnectAttempt >= RECONNECT_MAX_TRIES) {
    log.warn('Max reconnection attempts reached (' + RECONNECT_MAX_TRIES + ')')
    wsManager.status = 'error'
    notifyListeners()
    return
  }

  const delay = Math.min(
    RECONNECT_MAX_MS,
    RECONNECT_BASE_MS * Math.pow(2, wsManager.reconnectAttempt)
  )
  const jitter = delay * 0.2 * (Math.random() * 2 - 1)
  const actualDelay = Math.round(delay + jitter)

  log.info(`Reconnect attempt ${wsManager.reconnectAttempt + 1}/${RECONNECT_MAX_TRIES} in ${actualDelay}ms`)
  wsManager.status = 'connecting'
  notifyListeners()

  wsManager.reconnectTimer = setTimeout(() => {
    wsManager.reconnectTimer = null
    wsManager.reconnectAttempt++
    if (wsManager.shouldReconnect && wsManager.url) {
      wsManagerConnect(wsManager.url, true)
    }
  }, actualDelay)
}

function wsManagerConnect(url: string, isReconnect = false): void {
  // Already connected/connecting to this URL
  if (wsManager.url === url && (wsManager.status === 'connected' || wsManager.status === 'connecting') && !isReconnect) {
    log.debug('Already connected/connecting to', url)
    return
  }

  // Close existing connection if different URL
  if (wsManager.ws && wsManager.url !== url) {
    log.debug('Closing existing connection to', wsManager.url)
    wsManager.shouldReconnect = false // prevent reconnect for old URL
    wsManager.ws.close(1000, 'Switching URL')
    wsManager.ws = null
    wsManager.shouldReconnect = true
  }

  // Cancel pending reconnect for previous URL
  if (!isReconnect) {
    wsManagerCancelReconnect()
    wsManager.reconnectAttempt = 0
    wsManager.shouldReconnect = true
  }

  // Tear down mock runtime if switching away from mock.
  if (isMockWsUrl(wsManager.url) && !isMockWsUrl(url) && mockBrowser.intervalId !== null) {
    window.clearInterval(mockBrowser.intervalId)
    mockBrowser.intervalId = null
  }

  // Don't create new if already have one
  if (wsManager.ws && (wsManager.ws.readyState === WebSocket.CONNECTING || wsManager.ws.readyState === WebSocket.OPEN)) {
    log.debug('WebSocket already exists, state:', wsManager.ws.readyState)
    return
  }

  log.info('Connecting to', url)
  wsManager.url = url
  wsManager.status = 'connecting'
  notifyListeners()

  // Standalone mock WebSocket (no network)
  if (isMockWsUrl(url)) {
    if (!mockBrowser.frameBase64) updateMockFrame()

    // Pretend we connected successfully.
    window.setTimeout(() => {
      wsManager.status = "connected"
      wsManager.reconnectAttempt = 0
      notifyListeners()
      sendMockMessage({ type: "connected", url: mockBrowser.url, title: mockBrowser.title })

      // Periodic frames to keep UI feeling alive and to exercise the renderer.
      if (mockBrowser.intervalId !== null) window.clearInterval(mockBrowser.intervalId)
      mockBrowser.intervalId = window.setInterval(() => {
        if (!isMockWsUrl(wsManager.url) || wsManager.status !== "connected") return
        if (!mockBrowser.frameBase64) updateMockFrame()
        if (mockBrowser.frameBase64) sendMockMessage({ type: "frame", data: mockBrowser.frameBase64 })
      }, 900)

      if (mockBrowser.frameBase64) {
        sendMockMessage({ type: "frame", data: mockBrowser.frameBase64 })
      }
    }, 60)

    return
  }

  try {
    const ws = new WebSocket(url)
    ws.binaryType = 'arraybuffer'
    wsManager.ws = ws

    ws.onopen = () => {
      log.info('WebSocket connected')
      wsManager.status = 'connected'
      wsManager.reconnectAttempt = 0
      wsManager.hasConnectedBefore = true
      wsManagerCancelReconnect()
      wsManagerStartPing()
      notifyListeners()
    }

    ws.onclose = (event) => {
      wsManager.ws = null
      wsManagerStopPing()

      // Only auto-reconnect if:
      //  1. We previously had a successful connection (server was running and dropped)
      //  2. The close wasn't intentional (code 1000) or a fatal server error (4001, 4002)
      //  3. shouldReconnect hasn't been disabled by the user
      const noReconnectCodes = [1000, 4001, 4002]
      if (wsManager.shouldReconnect && wsManager.hasConnectedBefore && !noReconnectCodes.includes(event.code)) {
        log.info('Connection lost (code', event.code + '), scheduling reconnect')
        wsManagerScheduleReconnect()
      } else {
        if (!wsManager.hasConnectedBefore) {
          log.debug('Server not reachable at', wsManager.url, '- will retry when user starts a session')
        }
        wsManager.status = wsManager.hasConnectedBefore ? 'disconnected' : 'error'
        notifyListeners()
      }
    }

    ws.onerror = () => {
      // Downgrade to warn - this fires on normal connection refusal (server not running)
      // and onclose always fires after onerror to handle reconnection
      log.warn('WebSocket connection failed for', url)
    }

    ws.onmessage = (ev) => {
      // Handle pong responses
      if (typeof ev.data === 'string') {
        try {
          const msg = JSON.parse(ev.data)
          if (msg.type === 'pong') {
            wsManager.lastPongTime = Date.now()
            return
          }
        } catch { /* not JSON, pass through */ }
      }
      wsManager.messageListeners.forEach(fn => fn(ev.data))
    }
  } catch (err) {
    log.warn('Failed to create WebSocket:', err)
    wsManager.ws = null
    if (wsManager.shouldReconnect && wsManager.hasConnectedBefore) {
      wsManagerScheduleReconnect()
    } else {
      wsManager.status = 'error'
      notifyListeners()
    }
  }
}

function wsManagerDisconnect(): void {
  wsManager.shouldReconnect = false
  wsManagerCancelReconnect()
  wsManagerStopPing()
  if (wsManager.ws) {
    wsManager.ws.close(1000, 'User disconnect')
    wsManager.ws = null
  }
  if (isMockWsUrl(wsManager.url) && mockBrowser.intervalId !== null) {
    window.clearInterval(mockBrowser.intervalId)
    mockBrowser.intervalId = null
  }
  wsManager.status = 'disconnected'
  wsManager.url = null
  wsManager.reconnectAttempt = 0
  wsManager.hasConnectedBefore = false
  notifyListeners()
}

function wsManagerSend(data: string | ArrayBuffer): void {
  if (isMockWsUrl(wsManager.url)) {
    if (typeof data !== "string") return

    let msg: any
    try {
      msg = JSON.parse(data)
    } catch {
      return
    }

    const canGoBack = () => mockBrowser.index > 0
    const canGoForward = () => mockBrowser.index < mockBrowser.history.length - 1

    const emitNavigated = () => {
      sendMockMessage({
        type: "navigated",
        url: mockBrowser.url,
        title: mockBrowser.title,
        canGoBack: canGoBack(),
        canGoForward: canGoForward(),
      })
      if (mockBrowser.frameBase64) sendMockMessage({ type: "frame", data: mockBrowser.frameBase64 })
    }

    const setUrl = (nextUrl: string) => {
      mockBrowser.url = nextUrl
      try {
        mockBrowser.title = new URL(nextUrl).hostname
      } catch {
        mockBrowser.title = "Mock Page"
      }
      updateMockFrame()
    }

    const navigate = (nextUrl: string, pushHistory: boolean) => {
      sendMockMessage({ type: "navigating", url: nextUrl })
      window.setTimeout(() => {
        if (!isMockWsUrl(wsManager.url)) return

        if (pushHistory) {
          mockBrowser.history = mockBrowser.history.slice(0, mockBrowser.index + 1)
          mockBrowser.history.push(nextUrl)
          mockBrowser.index = mockBrowser.history.length - 1
        }

        setUrl(nextUrl)
        emitNavigated()
      }, 120)
    }

    if (msg.type === "goto" && typeof msg.url === "string") {
      navigate(msg.url, true)
      return
    }

    if (msg.type === "goBack" || msg.type === "back") {
      if (mockBrowser.index > 0) {
        mockBrowser.index -= 1
        setUrl(mockBrowser.history[mockBrowser.index])
      }
      emitNavigated()
      return
    }

    if (msg.type === "goForward" || msg.type === "forward") {
      if (mockBrowser.index < mockBrowser.history.length - 1) {
        mockBrowser.index += 1
        setUrl(mockBrowser.history[mockBrowser.index])
      }
      emitNavigated()
      return
    }

    if (msg.type === "reload" || msg.type === "refresh") {
      navigate(mockBrowser.url, false)
      return
    }

    if (msg.type === "stop") {
      sendMockMessage({ type: "status", url: mockBrowser.url, title: mockBrowser.title })
      return
    }

    // Ignore other commands in mock mode (mouse/keyboard/quality/etc).
    return
  }

  if (wsManager.ws?.readyState === WebSocket.OPEN) {
    wsManager.ws.send(data)
  }
}

function wsManagerSubscribe(listener: (state: WsManagerState) => void): () => void {
  wsManager.listeners.add(listener)
  return () => wsManager.listeners.delete(listener)
}

function wsManagerSubscribeMessages(listener: (data: ArrayBuffer | string) => void): () => void {
  wsManager.messageListeners.add(listener)
  return () => wsManager.messageListeners.delete(listener)
}

// =============================================================================

// =============================================================================
// Fast base64 decode via pre-built lookup table (avoids fetch() data-URI overhead)
// =============================================================================
const B64_LOOKUP = new Uint8Array(128)
{
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
  for (let i = 0; i < chars.length; i++) B64_LOOKUP[chars.charCodeAt(i)] = i
}

function fastBase64Decode(b64: string): ArrayBuffer {
  // Strip padding
  let len = b64.length
  while (len > 0 && b64.charCodeAt(len - 1) === 61 /* '=' */) len--

  const outLen = (len * 3) >>> 2
  const out = new Uint8Array(outLen)

  let j = 0
  for (let i = 0; i < len; ) {
    const a = B64_LOOKUP[b64.charCodeAt(i++)]
    const b = i < len ? B64_LOOKUP[b64.charCodeAt(i++)] : 0
    const c = i < len ? B64_LOOKUP[b64.charCodeAt(i++)] : 0
    const d = i < len ? B64_LOOKUP[b64.charCodeAt(i++)] : 0
    const triplet = (a << 18) | (b << 12) | (c << 6) | d
    out[j++] = (triplet >>> 16) & 0xff
    if (j < outLen) out[j++] = (triplet >>> 8) & 0xff
    if (j < outLen) out[j++] = triplet & 0xff
  }
  return out.buffer
}

// =============================================================================
// Ring buffer for perf samples (zero allocation after init)
// =============================================================================
class RingBuffer {
  private buf: Float64Array
  private head = 0
  private count = 0
  constructor(public capacity: number) {
    this.buf = new Float64Array(capacity)
  }
  push(v: number) {
    this.buf[this.head] = v
    this.head = (this.head + 1) % this.capacity
    if (this.count < this.capacity) this.count++
  }
  average(): number {
    if (this.count === 0) return 0
    let sum = 0
    for (let i = 0; i < this.count; i++) sum += this.buf[i]
    return sum / this.count
  }
  clear() { this.head = 0; this.count = 0 }
  get length() { return this.count }
}

// Performance monitoring configuration
const PERF_SAMPLE_WINDOW = 60 // Number of frames to average for FPS calculation
const LATENCY_SAMPLE_WINDOW = 30 // Number of samples for latency averaging (increased for stability)
const QUALITY_ADJUSTMENT_INTERVAL = 2500 // ms between quality adjustments
const QUALITY_STABILITY_THRESHOLD = 2 // Consecutive readings needed before changing quality

// Connection quality thresholds (latency in ms) - with hysteresis bands
type ConnectionQuality = "excellent" | "good" | "fair" | "poor"
const QUALITY_THRESHOLDS = {
  excellent: { up: 40, down: 60 },   // Upgrade if < 40ms, downgrade if > 60ms
  good: { up: 80, down: 120 },       // Upgrade if < 80ms, downgrade if > 120ms
  fair: { up: 160, down: 220 },      // Upgrade if < 160ms, downgrade if > 220ms
  // poor: >= 220ms
}

// Adaptive quality settings sent to server
interface QualitySettings {
  jpegQuality: number
  everyNthFrame: number
}

const QUALITY_PRESETS: Record<ConnectionQuality, QualitySettings> = {
  excellent: { jpegQuality: 70, everyNthFrame: 1 },  // Higher quality for excellent connections
  good: { jpegQuality: 55, everyNthFrame: 1 },       // Good quality, no frame skipping
  fair: { jpegQuality: 40, everyNthFrame: 2 },       // Reduced quality, some frame skipping
  poor: { jpegQuality: 25, everyNthFrame: 3 },       // Low quality, more frame skipping
}

/**
 * Agent Browser Module Configuration
 */
export const agentBrowserModuleConfig: ModuleConfig = {
  metadata: {
    id: 'agent-browser',
    displayName: 'Agent Browser',
    description: 'Live browser session from agent-scraper MCP for remote web automation',
    icon: 'Globe',
    category: 'browser',
    version: '1.0.0',
  },
  hasHeader: true,
  initialState: {
    isLoading: false,
    error: null,
    data: { sessionId: null, url: null, connected: false },
  },
  agentConfig: {
    enabled: true,
    supportedCommands: ['navigate', 'click', 'fill', 'screenshot', 'close'],
    emittedEvents: ['session-started', 'navigation', 'interaction', 'session-closed'],
    contextDescription: 'Remote browser session via agent-scraper for captcha assistance and visual debugging',
  },
}

// =============================================================================
// Navigation state reducer (Phase 1E - batches multiple setState calls)
// =============================================================================
interface NavigationState {
  currentUrl: string
  urlInput: string
  pageTitle: string
  isLoading: boolean
  canGoBack: boolean
  canGoForward: boolean
}

type NavigationAction =
  | { type: "SET_URL"; url: string }
  | { type: "SET_URL_INPUT"; urlInput: string }
  | { type: "SET_TITLE"; title: string }
  | { type: "SET_LOADING"; loading: boolean }
  | { type: "NAVIGATING"; url: string }
  | { type: "NAVIGATED"; url?: string; title?: string; canGoBack?: boolean; canGoForward?: boolean }
  | { type: "CONNECTED"; url?: string; title?: string }
  | { type: "PAGE_INFO"; url?: string; title?: string }
  | { type: "NAVIGATE_TO"; url: string }

function navigationReducer(state: NavigationState, action: NavigationAction): NavigationState {
  switch (action.type) {
    case "SET_URL":
      return { ...state, currentUrl: action.url, urlInput: action.url }
    case "SET_URL_INPUT":
      return { ...state, urlInput: action.urlInput }
    case "SET_TITLE":
      return { ...state, pageTitle: action.title }
    case "SET_LOADING":
      return { ...state, isLoading: action.loading }
    case "NAVIGATING":
      return { ...state, isLoading: true, currentUrl: action.url, urlInput: action.url }
    case "NAVIGATED":
      return {
        ...state,
        isLoading: false,
        ...(action.url ? { currentUrl: action.url, urlInput: action.url } : {}),
        ...(action.title ? { pageTitle: action.title } : {}),
        ...(typeof action.canGoBack === "boolean" ? { canGoBack: action.canGoBack } : {}),
        ...(typeof action.canGoForward === "boolean" ? { canGoForward: action.canGoForward } : {}),
      }
    case "CONNECTED":
      return {
        ...state,
        isLoading: false,
        ...(action.url ? { currentUrl: action.url, urlInput: action.url } : {}),
        ...(action.title ? { pageTitle: action.title } : {}),
      }
    case "PAGE_INFO":
      return {
        ...state,
        ...(action.url ? { currentUrl: action.url, urlInput: action.url } : {}),
        ...(action.title ? { pageTitle: action.title } : {}),
      }
    case "NAVIGATE_TO":
      return { ...state, isLoading: true, currentUrl: action.url, urlInput: action.url }
    default:
      return state
  }
}

// Control mode for co-browsing (Phase 4B)
type ControlMode = "shared" | "user" | "agent"

type ConnectionStatus = "disconnected" | "connecting" | "connected" | "reconnecting" | "error"

interface AgentBrowserModuleProps extends ModuleInstanceProps {
  sessionId?: string
  wsPath?: string  // WebSocket path from browser_live_start
  initialUrl?: string
  pendingNavigation?: string  // URL to navigate to (from agent request)
}

/**
 * AgentBrowserModule - Displays live browser stream from agent-scraper MCP
 * 
 * This module connects to the agent-scraper's live preview WebSocket to stream
 * the browser view. Users can interact with the page for captcha solving, etc.
 */
export function AgentBrowserModule({
  instanceId,
  tabId,
  className,
  sessionId: initialSessionId,
  wsPath: initialWsPath,
  initialUrl = "https://www.google.com",
  pendingNavigation,
}: AgentBrowserModuleProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const imgRef = useRef<HTMLImageElement | null>(null)
  const latestFrameRef = useRef<ArrayBuffer | null>(null)
  const renderingRef = useRef<boolean>(false)
  const sessionIdRef = useRef<string | null>(initialSessionId || null)

  const [status, setStatus] = useState<ConnectionStatus>("disconnected")
  const [sessionId, setSessionId] = useState<string | null>(initialSessionId || null)
  const [wsPath, setWsPath] = useState<string | null>(initialWsPath || null)

  // Keep ref in sync with state for cleanup handlers
  useEffect(() => {
    sessionIdRef.current = sessionId
  }, [sessionId])

  // Navigation state via useReducer (Phase 1E - batches setState calls)
  const [navState, navDispatch] = useReducer(navigationReducer, {
    currentUrl: initialUrl,
    urlInput: initialUrl,
    pageTitle: "Agent Browser",
    isLoading: false,
    canGoBack: false,
    canGoForward: false,
  })
  const { currentUrl, urlInput, pageTitle, isLoading, canGoBack, canGoForward } = navState

  const [isUrlFocused, setIsUrlFocused] = useState<boolean>(false)
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false)
  const urlInputRef = useRef<HTMLInputElement>(null)

  // Reconnection state (driven by singleton manager)
  const reconnectAttempts = wsManager.reconnectAttempt
  const isReconnecting = wsManager.status === 'connecting' && wsManager.reconnectAttempt > 0

  // Performance monitoring - use refs to avoid per-frame re-renders (Phase 1A)
  const fpsRef = useRef<number>(0)
  const latencyRef = useRef<number>(0)
  const connectionQualityRef_display = useRef<ConnectionQuality>("good")
  const [showPerformanceStats, setShowPerformanceStats] = useState<boolean>(DEBUG_MODE)
  // Batched perf display state - only updated on interval when overlay is visible
  const [perfDisplay, setPerfDisplay] = useState<{ fps: number; latency: number; quality: ConnectionQuality }>({
    fps: 0, latency: 0, quality: "good"
  })

  // Sync perf refs to display state on a 500ms interval (only when overlay visible)
  useEffect(() => {
    if (!showPerformanceStats) return
    const interval = setInterval(() => {
      setPerfDisplay({
        fps: fpsRef.current,
        latency: latencyRef.current,
        quality: connectionQualityRef_display.current,
      })
    }, 500)
    return () => clearInterval(interval)
  }, [showPerformanceStats])

  // Canvas 2D context cache (Phase 1B)
  const ctxRef = useRef<CanvasRenderingContext2D | null>(null)

  // Initialize cached canvas context when canvas mounts
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (ctx) {
      ctx.imageSmoothingEnabled = false
      ctxRef.current = ctx
    }
  }, [status]) // re-acquire when status changes (canvas remounts)

  // Co-browsing state (Phase 4)
  const [controlMode, setControlMode] = useState<ControlMode>("shared")
  const [agentActive, setAgentActive] = useState<boolean>(false)
  const agentActiveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const agentCursorRef = useRef<{ x: number; y: number; flash: boolean } | null>(null)

  // Performance tracking refs (ring buffers avoid per-frame GC)
  const frameTimestampsRef = useRef<number[]>([])
  const latencySamplesRef = useRef(new RingBuffer(LATENCY_SAMPLE_WINDOW))
  const lastQualityAdjustmentRef = useRef<number>(0)
  const currentQualityRef = useRef<ConnectionQuality>("good")
  const frameBytesRef = useRef(new RingBuffer(PERF_SAMPLE_WINDOW))
  const qualityStabilityCounterRef = useRef<number>(0)
  const targetQualityRef = useRef<ConnectionQuality>("good")

  // Sync state with props when they change (e.g., when tab is updated with wsPath)
  // Force update regardless of current value to allow reconnecting to new sessions
  useEffect(() => {
    if (initialSessionId && initialSessionId !== sessionId) {
      log.debug('Syncing sessionId from props:', initialSessionId)
      setSessionId(initialSessionId)
    }
  }, [initialSessionId]) // Remove sessionId from deps to avoid stale closures

  useEffect(() => {
    if (initialWsPath && initialWsPath !== wsPath) {
      log.debug('Syncing wsPath from props:', initialWsPath, '(current:', wsPath, ')')
      // Close existing connection before switching
      wsManagerDisconnect()
      setWsPath(initialWsPath)
    }
  }, [initialWsPath]) // Remove wsPath from deps to avoid stale closures

  // Handle pending navigation from agent requests
  // This effect runs when pendingNavigation changes OR when status becomes connected
  useEffect(() => {
    if (pendingNavigation && status === 'connected') {
      // Strip the #nav-{timestamp} suffix we added to make React see each request as unique
      const actualUrl = pendingNavigation.replace(/#nav-\d+$/, '')
      log.debug('Navigating to pending URL:', actualUrl)
      wsManagerSend(JSON.stringify({ type: 'goto', url: actualUrl }))
      navDispatch({ type: "SET_URL", url: actualUrl })
    }
  }, [pendingNavigation, status])

  const [viewport, setViewport] = useState({ width: 1280, height: 720 })

  // Dynamic viewport sizing (Phase 2A) - send viewport on connect and canvas resize
  const viewportResizeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || status !== "connected") return

    const sendViewport = () => {
      const rect = canvas.getBoundingClientRect()
      const dpr = Math.min(window.devicePixelRatio || 1, 2) // cap at 2x
      const w = Math.round(rect.width * dpr)
      const h = Math.round(rect.height * dpr)
      if (w > 0 && h > 0 && (w !== viewport.width || h !== viewport.height)) {
        setViewport({ width: w, height: h })
        canvas.width = w
        canvas.height = h
        // Re-acquire context after resize
        const ctx = canvas.getContext("2d")
        if (ctx) {
          ctx.imageSmoothingEnabled = false
          ctxRef.current = ctx
        }
        wsManagerSend(JSON.stringify({ type: "set_viewport", width: w, height: h }))
        log.debug("Sent viewport:", w, "x", h)
      }
    }

    // Send on connect
    sendViewport()

    // Debounced resize observer
    const observer = new ResizeObserver(() => {
      if (viewportResizeTimerRef.current) clearTimeout(viewportResizeTimerRef.current)
      viewportResizeTimerRef.current = setTimeout(sendViewport, 300)
    })
    observer.observe(canvas)

    return () => {
      observer.disconnect()
      if (viewportResizeTimerRef.current) clearTimeout(viewportResizeTimerRef.current)
    }
  }, [status]) // eslint-disable-line react-hooks/exhaustive-deps

  // Agent connection for receiving commands
  const { updateContext, sendEvent, onCommand } = useAgentConnection({
    instanceId: instanceId || `agent-browser-${Date.now()}`,
    moduleType: 'agent-browser',
    autoRegister: true,
    initialContext: {
      sessionId,
      url: currentUrl,
      connected: status === "connected",
    },
  })

  // Handle commands from agent
  useEffect(() => {
    const sub1 = onCommand('setSession', async (params: { sessionId: string; wsPath?: string }) => {
      setSessionId(params.sessionId)
      if (params.wsPath) setWsPath(params.wsPath)
      sendEvent('session-started', { sessionId: params.sessionId })
    })
    
    const sub2 = onCommand('close', async () => {
      wsManagerDisconnect()
      setSessionId(null)
      setWsPath(null)
      setStatus("disconnected")
      sendEvent('session-closed', { sessionId })
    })

    return () => {
      sub1.unsubscribe()
      sub2.unsubscribe()
    }
  }, [onCommand, sendEvent, sessionId])

  // Listen for navigation events from agent (e.g., browser_navigate tool calls)
  useEffect(() => {
    const unsubscribe = subscribeToBrowserSession((data) => {
      // Only handle navigation events for this session (or any if we don't have a session yet)
      if (data.eventType === 'navigate' && data.navigatedUrl) {
        // Check if this event is for our session or we should accept it (same session or no session filter)
        const isOurSession = !sessionId || !data.sessionId || data.sessionId === sessionId
        if (isOurSession) {
          log.debug('Received navigation event from agent:', data.navigatedUrl)
          navDispatch({ type: "SET_URL", url: data.navigatedUrl })
        }
      }
    })

    return unsubscribe
  }, [sessionId])

  // Send message to WebSocket
  const send = useCallback((data: Record<string, unknown>) => {
    wsManagerSend(JSON.stringify(data))
  }, [])

  // Cancel reconnection (delegates to singleton)
  const cancelReconnect = useCallback(() => {
    wsManager.shouldReconnect = false
    wsManagerCancelReconnect()
  }, [])

  // Performance monitoring: Calculate FPS from frame timestamps (writes to ref, not state)
  const updateFps = useCallback(() => {
    const now = performance.now()
    frameTimestampsRef.current.push(now)

    // Keep only frames within the sample window
    const cutoff = now - 1000 // Last 1 second
    frameTimestampsRef.current = frameTimestampsRef.current.filter(t => t > cutoff)

    // Calculate FPS - write to ref (no re-render)
    fpsRef.current = frameTimestampsRef.current.length
  }, [])

  // Performance monitoring: Update latency and determine target quality with hysteresis
  // Writes to refs only (no re-render) - display synced via interval
  const updateLatency = useCallback((frameLatency: number) => {
    latencySamplesRef.current.push(frameLatency)
    const avgLatency = latencySamplesRef.current.average()
    latencyRef.current = Math.round(avgLatency)

    // Determine target quality using hysteresis thresholds
    const current = currentQualityRef.current
    let targetQuality: ConnectionQuality = current

    if (avgLatency < QUALITY_THRESHOLDS.excellent.up) {
      targetQuality = "excellent"
    } else if (avgLatency < QUALITY_THRESHOLDS.good.up) {
      targetQuality = current === "excellent" && avgLatency < QUALITY_THRESHOLDS.excellent.down ? "excellent" : "good"
    } else if (avgLatency < QUALITY_THRESHOLDS.fair.up) {
      targetQuality = current === "good" && avgLatency < QUALITY_THRESHOLDS.good.down ? "good" : "fair"
    } else if (avgLatency >= QUALITY_THRESHOLDS.fair.down) {
      targetQuality = "poor"
    } else {
      targetQuality = current === "poor" ? "fair" : current
    }

    connectionQualityRef_display.current = targetQuality
    return targetQuality
  }, [])

  // Adaptive quality: Send quality adjustment to server with stability check
  const adjustQuality = useCallback((quality: ConnectionQuality) => {
    const now = Date.now()

    // Track stability - only change if we've seen the same target quality multiple times
    if (quality === targetQualityRef.current) {
      qualityStabilityCounterRef.current++
    } else {
      targetQualityRef.current = quality
      qualityStabilityCounterRef.current = 1
    }

    // Don't adjust too frequently
    if (now - lastQualityAdjustmentRef.current < QUALITY_ADJUSTMENT_INTERVAL) {
      return
    }

    // Only change if quality is different AND we've seen it consistently
    if (quality !== currentQualityRef.current &&
        qualityStabilityCounterRef.current >= QUALITY_STABILITY_THRESHOLD) {
      currentQualityRef.current = quality
      lastQualityAdjustmentRef.current = now
      qualityStabilityCounterRef.current = 0

      const settings = QUALITY_PRESETS[quality]
      log.debug('Adjusting quality to:', quality, settings, 'after', QUALITY_STABILITY_THRESHOLD, 'stable readings')
      wsManagerSend(JSON.stringify({
        type: 'set_quality',
        jpegQuality: settings.jpegQuality,
        everyNthFrame: settings.everyNthFrame,
      }))
    }
  }, [])

  // Reset performance stats
  const resetPerformanceStats = useCallback(() => {
    frameTimestampsRef.current = []
    latencySamplesRef.current.clear()
    frameBytesRef.current.clear()
    fpsRef.current = 0
    latencyRef.current = 0
    connectionQualityRef_display.current = "good"
    currentQualityRef.current = "good"
    targetQualityRef.current = "good"
    qualityStabilityCounterRef.current = 0
    lastQualityAdjustmentRef.current = 0
    setPerfDisplay({ fps: 0, latency: 0, quality: "good" })
  }, [])

  // Throttled mouse move - limit to ~30fps to reduce lag
  const lastMouseMoveRef = useRef<number>(0)
  const pendingMouseMoveRef = useRef<{ x: number; y: number } | null>(null)
  const mouseMoveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const sendThrottledMouseMove = useCallback((x: number, y: number) => {
    const now = Date.now()
    const elapsed = now - lastMouseMoveRef.current
    const throttleMs = 16 // ~60fps

    if (elapsed >= throttleMs) {
      // Send immediately
      lastMouseMoveRef.current = now
      send({ type: "mouse_move", x, y })
    } else {
      // Queue for later
      pendingMouseMoveRef.current = { x, y }
      if (!mouseMoveTimeoutRef.current) {
        mouseMoveTimeoutRef.current = setTimeout(() => {
          mouseMoveTimeoutRef.current = null
          if (pendingMouseMoveRef.current) {
            lastMouseMoveRef.current = Date.now()
            send({ type: "mouse_move", ...pendingMouseMoveRef.current })
            pendingMouseMoveRef.current = null
          }
        }, throttleMs - elapsed)
      }
    }
  }, [send])

  // Throttled scroll - batch scroll events to reduce lag
  const pendingScrollRef = useRef<number>(0)
  const scrollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const sendThrottledScroll = useCallback((deltaY: number) => {
    pendingScrollRef.current += deltaY

    if (!scrollTimeoutRef.current) {
      scrollTimeoutRef.current = setTimeout(() => {
        scrollTimeoutRef.current = null
        if (pendingScrollRef.current !== 0) {
          send({ type: "mouse_wheel", deltaY: pendingScrollRef.current })
          pendingScrollRef.current = 0
        }
      }, 50) // Batch scroll events every 50ms
    }
  }, [send])

  // Convert mouse coords to remote viewport coords
  const toRemoteCoords = useCallback((e: React.MouseEvent) => {
    const canvas = canvasRef.current
    if (!canvas) return { x: 0, y: 0 }
    const rect = canvas.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * viewport.width
    const y = ((e.clientY - rect.top) / rect.height) * viewport.height
    return { x, y }
  }, [viewport])

  // Navigation handlers (using navDispatch for batched state updates)
  const handleNavigate = useCallback((url: string) => {
    if (!url.trim()) return
    let navigateUrl = url.trim()
    if (!navigateUrl.startsWith('http://') && !navigateUrl.startsWith('https://')) {
      if (navigateUrl.includes('.') && !navigateUrl.includes(' ')) {
        navigateUrl = `https://${navigateUrl}`
      } else {
        navigateUrl = `https://www.google.com/search?q=${encodeURIComponent(navigateUrl)}`
      }
    }
    log.debug('Navigating to:', navigateUrl)
    navDispatch({ type: "NAVIGATE_TO", url: navigateUrl })
    send({ type: 'goto', url: navigateUrl })
    sendEvent('navigation', { url: navigateUrl })
  }, [send, sendEvent])

  const handleGoBack = useCallback(() => {
    log.debug('Going back')
    navDispatch({ type: "SET_LOADING", loading: true })
    send({ type: 'goBack' })
  }, [send])

  const handleGoForward = useCallback(() => {
    log.debug('Going forward')
    navDispatch({ type: "SET_LOADING", loading: true })
    send({ type: 'goForward' })
  }, [send])

  const handleRefresh = useCallback(() => {
    log.debug('Refreshing')
    navDispatch({ type: "SET_LOADING", loading: true })
    send({ type: 'reload' })
  }, [send])

  const handleStop = useCallback(() => {
    log.debug('Stopping load')
    send({ type: 'stop' })
    navDispatch({ type: "SET_LOADING", loading: false })
  }, [send])

  const handleHome = useCallback(() => {
    handleNavigate('https://www.google.com')
  }, [handleNavigate])

  // Start a new browser session (user-initiated) - must be defined before handleUrlKeyDown
  const [isStartingSession, setIsStartingSession] = useState(false)
  const [useLocalServer, setUseLocalServer] = useState(USE_LOCAL_SERVER)

  const startBrowserSession = useCallback(async (url?: string) => {
    if (isStartingSession) return

    const targetUrl = url || urlInput || 'https://www.google.com'
    log.info('Starting new session to:', targetUrl, useLocalServer ? '(local)' : '(remote)')
    setIsStartingSession(true)
    setStatus("connecting")

    try {
      if (useLocalServer) {
        // Local mode: connect directly to local WebSocket server
        // The local server creates a browser session on connection
        log.debug('Using local browser server at', LOCAL_BROWSER_WS_URL)
        const nextSessionId = LOCAL_BROWSER_WS_URL.startsWith("mock://") ? "mock" : "local"
        setSessionId(nextSessionId)
        setWsPath(LOCAL_BROWSER_WS_URL)  // Store full URL for local mode
        navDispatch({ type: "SET_URL", url: targetUrl })
        sendEvent('session-started', { sessionId: nextSessionId, url: targetUrl })
      } else {
        // Remote mode: call agent-scraper API
        const response = await fetch(`/api/browser/live/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: targetUrl }),
        })

        if (!response.ok) {
          throw new Error(`Failed to start session: ${response.status}`)
        }

        const data = await response.json()
        log.debug('Session started:', data)

        if (data.ok && data.sessionId && data.wsPath) {
          setSessionId(data.sessionId)
          setWsPath(data.wsPath)
          navDispatch({ type: "SET_URL", url: targetUrl })
          sendEvent('session-started', { sessionId: data.sessionId, url: targetUrl })
        } else {
          throw new Error(data.error || 'Failed to start session')
        }
      }
    } catch (err) {
      log.error('Failed to start session:', err)
      setStatus("error")
    } finally {
      setIsStartingSession(false)
    }
  }, [isStartingSession, urlInput, sendEvent, useLocalServer])

  const handleUrlKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      if (status !== 'connected' && !sessionId) {
        startBrowserSession(urlInput)
      } else {
        handleNavigate(urlInput)
      }
      urlInputRef.current?.blur()
    } else if (e.key === 'Escape') {
      navDispatch({ type: "SET_URL_INPUT", urlInput: currentUrl })
      urlInputRef.current?.blur()
    }
  }, [handleNavigate, urlInput, currentUrl, status, sessionId, startBrowserSession])

  const handleUrlFocus = useCallback(() => {
    setIsUrlFocused(true)
    // Select all text when focusing URL bar (like real browsers)
    setTimeout(() => urlInputRef.current?.select(), 0)
  }, [])

  const handleUrlBlur = useCallback(() => {
    setIsUrlFocused(false)
    navDispatch({ type: "SET_URL_INPUT", urlInput: currentUrl })
  }, [currentUrl])

  // Update context when status changes
  useEffect(() => {
    updateContext({ sessionId, url: currentUrl, connected: status === "connected" })
  }, [sessionId, currentUrl, status, updateContext])

  // ==========================================================================
  // WebSocket Connection via Singleton Manager
  // ==========================================================================
  // This is MUCH simpler than managing WebSocket lifecycle in React.
  // The singleton lives outside React and handles all the complexity.

  // Subscribe to connection state changes from singleton
  useEffect(() => {
    const unsubscribe = wsManagerSubscribe((state) => {
      if (state.status === 'connected') {
        setStatus('connected')
        resetPerformanceStats()
      } else if (state.status === 'connecting') {
        // Distinguish reconnecting from first connect
        setStatus(state.reconnectAttempt > 0 ? 'reconnecting' : 'connecting')
      } else if (state.status === 'error') {
        setStatus('error')
      } else {
        setStatus('disconnected')
      }
    })
    return unsubscribe
  }, [resetPerformanceStats])

  // Subscribe to messages and handle frame rendering
  useEffect(() => {
    if (!imgRef.current) {
      imgRef.current = new Image()
    }

    const unsubscribe = wsManagerSubscribeMessages((data) => {
      // Helper to enqueue a frame for rendering
      const enqueue = (buf: ArrayBuffer) => {
        const receiveTime = performance.now()

        // Track frame size via ring buffer (zero alloc)
        frameBytesRef.current.push(buf.byteLength)

        latestFrameRef.current = buf
        if (renderingRef.current) return
        renderingRef.current = true

        const renderNext = () => {
          const frameData = latestFrameRef.current
          if (!frameData) { renderingRef.current = false; return }
          latestFrameRef.current = null

          const canvas = canvasRef.current
          const ctx = ctxRef.current || canvas?.getContext("2d")
          if (!canvas || !ctx) { renderingRef.current = false; return }

          // Decode JPEG directly from ArrayBuffer — skip Blob when possible
          if (typeof createImageBitmap === "function") {
            // createImageBitmap accepts Blob; construct once, decode off-thread
            const blob = new Blob([frameData], { type: "image/jpeg" })
            createImageBitmap(blob).then((bitmap) => {
              ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
              try { bitmap.close() } catch {}

              // Draw agent cursor overlay (Phase 4C)
              const cursor = agentCursorRef.current
              if (cursor) {
                const scaleX = canvas.width / 1280
                const scaleY = canvas.height / 720
                ctx.save()
                ctx.beginPath()
                ctx.arc(cursor.x * scaleX, cursor.y * scaleY, cursor.flash ? 12 : 8, 0, Math.PI * 2)
                ctx.fillStyle = cursor.flash ? "rgba(59, 130, 246, 0.5)" : "rgba(59, 130, 246, 0.3)"
                ctx.fill()
                ctx.strokeStyle = "rgba(59, 130, 246, 0.8)"
                ctx.lineWidth = 2
                ctx.stroke()
                ctx.restore()
              }

              updateFps()
              const frameLatency = performance.now() - receiveTime
              const quality = updateLatency(frameLatency)
              adjustQuality(quality)

              // Continue render loop immediately (don't wait for next rAF if another frame queued)
              if (latestFrameRef.current) {
                renderNext()
              } else {
                renderingRef.current = false
              }
            }).catch(() => {
              if (latestFrameRef.current) renderNext()
              else renderingRef.current = false
            })
          } else {
            // Fallback for older browsers
            const blob = new Blob([frameData], { type: "image/jpeg" })
            const url = URL.createObjectURL(blob)
            const img = imgRef.current!
            img.onload = () => {
              ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
              URL.revokeObjectURL(url)
              updateFps()
              const frameLatency = performance.now() - receiveTime
              const quality = updateLatency(frameLatency)
              adjustQuality(quality)
              if (latestFrameRef.current) renderNext()
              else renderingRef.current = false
            }
            img.src = url
          }
        }
        requestAnimationFrame(renderNext)
      }

      // Handle string messages (JSON)
      if (typeof data === "string") {
        try {
          const msg = JSON.parse(data)
          if (msg.type !== "frame") {
            log.debug('Message:', msg.type, msg)
          }

          // Handle frame messages (base64 encoded) — use fast sync decoder
          if (msg.type === "frame" && msg.data) {
            enqueue(fastBase64Decode(msg.data))
            return
          }

          // Handle status messages (single dispatch per message type)
          if (msg.type === "connected" || msg.type === "status") {
            navDispatch({ type: "CONNECTED", url: msg.url, title: msg.title })
            return
          }

          if (msg.type === "navigating") {
            if (msg.url) navDispatch({ type: "NAVIGATING", url: msg.url })
            else navDispatch({ type: "SET_LOADING", loading: true })
            return
          }

          if (msg.type === "navigated") {
            navDispatch({ type: "NAVIGATED", url: msg.url, title: msg.title, canGoBack: msg.canGoBack, canGoForward: msg.canGoForward })
            return
          }

          if (msg.type === "error") {
            log.error('Server error:', msg.message, msg.details)
            navDispatch({ type: "SET_LOADING", loading: false })
            return
          }

          if (msg.type === "pageinfo" || msg.type === "page") {
            navDispatch({ type: "PAGE_INFO", url: msg.url, title: msg.title })
            return
          }

          // Handle agent action messages (Phase 4A - agent activity indicator)
          if (msg.type === "agent_action") {
            setAgentActive(true)
            if (agentActiveTimerRef.current) clearTimeout(agentActiveTimerRef.current)
            agentActiveTimerRef.current = setTimeout(() => setAgentActive(false), 3000)
            // Update agent cursor position
            if (typeof msg.x === "number" && typeof msg.y === "number") {
              agentCursorRef.current = { x: msg.x, y: msg.y, flash: msg.action === "click" }
              if (msg.action === "click") {
                setTimeout(() => {
                  if (agentCursorRef.current) agentCursorRef.current.flash = false
                }, 300)
              }
            }
            return
          }

          // Fallback for any message with url
          if (msg.url && typeof msg.url === 'string' && msg.url.startsWith('http')) {
            navDispatch({ type: "PAGE_INFO", url: msg.url, title: msg.title })
          } else if (msg.title) {
            navDispatch({ type: "SET_TITLE", title: msg.title })
          }
        } catch (e) {
          log.error('Failed to parse JSON message:', e)
        }
        return
      }

      // Handle binary frames (raw JPEG bytes)
      if (data instanceof ArrayBuffer) {
        enqueue(data)
      }
    })

    return unsubscribe
  }, [updateFps, updateLatency, adjustQuality])

  // Connect when wsPath changes (NOT when currentUrl changes - that would cause reconnects on navigation)
  const initialUrlRef = useRef(initialUrl)
  const currentUrlRef = useRef(currentUrl)
  currentUrlRef.current = currentUrl

  useEffect(() => {
    if (!wsPath) return

    // Build WebSocket URL
    const isLocalMode =
      wsPath.startsWith('ws://') ||
      wsPath.startsWith('wss://') ||
      wsPath.startsWith('mock://')
    const wsUrl = isLocalMode ? wsPath : `ws://${AGENT_SCRAPER_HOST}:${AGENT_SCRAPER_PORT}${wsPath}`

    log.info('Connecting to', wsUrl)
    wsManagerConnect(wsUrl)

    // Navigate to target URL once connected
    const targetUrl = currentUrlRef.current || initialUrlRef.current
    if (targetUrl && targetUrl !== "https://www.google.com" && targetUrl !== "https://google.com") {
      // Use a one-time listener to navigate after connection establishes
      const unsubOnce = wsManagerSubscribe((state) => {
        if (state.status === 'connected') {
          log.debug("Navigating to target URL:", targetUrl)
          navDispatch({ type: "SET_LOADING", loading: true })
          wsManagerSend(JSON.stringify({ type: 'goto', url: targetUrl }))
          unsubOnce()
        }
      })
      // Clean up listener after 10s if connection never established
      const timeoutId = setTimeout(() => unsubOnce(), 10000)
      return () => {
        clearTimeout(timeoutId)
        unsubOnce()
      }
    }
  }, [wsPath]) // Only reconnect when wsPath changes

  // Handle wheel events with non-passive listener to allow preventDefault()
  // This prevents the page from scrolling when scrolling inside the browser canvas
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault()
      sendThrottledScroll(e.deltaY)
    }

    // Add non-passive listener to allow preventDefault()
    canvas.addEventListener('wheel', handleWheel, { passive: false })
    return () => canvas.removeEventListener('wheel', handleWheel)
  }, [sendThrottledScroll])

  // Toolbar button style
  const btnClass = "h-8 w-8 flex items-center justify-center rounded-md text-text-muted hover:text-text-primary hover:bg-surface-elevated transition-colors disabled:opacity-40 disabled:cursor-not-allowed"

  const isConnected = status === "connected"

  return (
    <TooltipProvider delayDuration={200}>
    <div className={cn("flex h-full flex-col bg-surface-secondary", className)}>
      {/* Browser toolbar */}
      <div className="flex h-11 items-center gap-1.5 border-b border-interactive-border px-2">
        {/* Navigation buttons */}
        <div className="flex items-center gap-0.5">
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                className={btnClass}
                onClick={handleGoBack}
                disabled={!isConnected || !canGoBack}
                aria-label="Go back"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Go back</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <button
                className={btnClass}
                onClick={handleGoForward}
                disabled={!isConnected || !canGoForward}
                aria-label="Go forward"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Go forward</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <button
                className={btnClass}
                onClick={isLoading ? handleStop : handleRefresh}
                disabled={!isConnected}
                aria-label={isLoading ? "Stop" : "Refresh"}
              >
                {isLoading ? (
                  <X className="h-4 w-4" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">{isLoading ? "Stop" : "Refresh"}</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <button
                className={btnClass}
                onClick={handleHome}
                disabled={!isConnected}
                aria-label="Go home"
              >
                <Home className="h-4 w-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Home</TooltipContent>
          </Tooltip>
        </div>

        {/* URL bar */}
        <div className="flex-1 mx-2">
          <div className={cn(
            "flex h-8 items-center rounded-lg bg-surface border transition-colors",
            isUrlFocused ? "border-accent-primary ring-1 ring-accent-primary/30" : "border-interactive-border",
            isStartingSession && "opacity-50"
          )}>
            {/* Security indicator */}
            <div className="flex items-center pl-3 pr-1">
              {currentUrl.startsWith('https://') ? (
                <Lock className="h-3.5 w-3.5 text-green-500" />
              ) : currentUrl.startsWith('http://') ? (
                <Unlock className="h-3.5 w-3.5 text-text-muted" />
              ) : (
                <Globe className="h-3.5 w-3.5 text-text-muted" />
              )}
            </div>
            <input
              ref={urlInputRef}
              type="text"
              value={urlInput}
              onChange={(e) => navDispatch({ type: "SET_URL_INPUT", urlInput: e.target.value })}
              onKeyDown={handleUrlKeyDown}
              onFocus={handleUrlFocus}
              onBlur={handleUrlBlur}
              disabled={isStartingSession}
              placeholder={isConnected ? "Enter URL or search..." : "Type a URL and press Enter to start..."}
              className="flex-1 h-full bg-transparent text-sm text-text-primary placeholder:text-text-muted outline-none px-2"
            />
            {isLoading && (
              <div className="pr-3">
                <RefreshCw className="h-3.5 w-3.5 text-accent-primary animate-spin" />
              </div>
            )}
          </div>
        </div>

        {/* Status and actions */}
        <div className="flex items-center gap-1">
          {/* Connection status */}
          <div className="flex items-center gap-1.5 px-2">
            <div className={cn(
              "h-2 w-2 rounded-full",
              status === "connected" && "bg-green-500",
              status === "connecting" && "bg-yellow-500 animate-pulse",
              status === "disconnected" && "bg-gray-500",
              status === "error" && "bg-red-500"
            )} />
            <span className="text-xs text-text-muted capitalize hidden sm:inline">{status}</span>
          </div>

          {/* Session info (compact) */}
          {sessionId && (
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex items-center gap-1 px-2 py-1 rounded bg-surface-elevated">
                  <Eye className="h-3 w-3 text-accent-primary" />
                  <span className="text-[10px] text-text-muted font-mono">
                    {sessionId.slice(0, 6)}
                  </span>
                </div>
              </TooltipTrigger>
              <TooltipContent side="bottom">Session: {sessionId}</TooltipContent>
            </Tooltip>
          )}

          {/* Control mode selector (Phase 4B) */}
          {status === "connected" && (
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={() => {
                    const modes: ControlMode[] = ["shared", "user", "agent"]
                    const idx = modes.indexOf(controlMode)
                    setControlMode(modes[(idx + 1) % modes.length])
                  }}
                  className={cn(
                    "flex items-center gap-1 px-2 py-1 rounded transition-colors",
                    controlMode === "shared" && "bg-surface-elevated text-text-muted hover:text-text-primary",
                    controlMode === "user" && "bg-blue-500/20 text-blue-400",
                    controlMode === "agent" && "bg-purple-500/20 text-purple-400"
                  )}
                >
                  {controlMode === "shared" && <Users className="h-3 w-3" />}
                  {controlMode === "user" && <User className="h-3 w-3" />}
                  {controlMode === "agent" && <Bot className="h-3 w-3" />}
                  <span className="text-[10px] font-mono capitalize">{controlMode}</span>
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                <div className="text-xs space-y-1">
                  <div className="font-medium">Control: {controlMode}</div>
                  <div className="text-text-muted">Shared = both, User = you only, Agent = agent only</div>
                  <div className="text-text-muted">Click to cycle</div>
                </div>
              </TooltipContent>
            </Tooltip>
          )}

          {/* Performance stats toggle */}
          {status === "connected" && (
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={() => setShowPerformanceStats(!showPerformanceStats)}
                  className={cn(
                    "flex items-center gap-1 px-2 py-1 rounded transition-colors",
                    showPerformanceStats ? "bg-accent-primary/20 text-accent-primary" : "bg-surface-elevated text-text-muted hover:text-text-primary"
                  )}
                >
                  <div className={cn(
                    "h-2 w-2 rounded-full",
                    perfDisplay.quality === "excellent" && "bg-green-500",
                    perfDisplay.quality === "good" && "bg-green-400",
                    perfDisplay.quality === "fair" && "bg-yellow-500",
                    perfDisplay.quality === "poor" && "bg-red-500"
                  )} />
                  <span className="text-[10px] font-mono">{perfDisplay.fps} fps</span>
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                <div className="text-xs space-y-1">
                  <div>FPS: {perfDisplay.fps}</div>
                  <div>Latency: {perfDisplay.latency}ms</div>
                  <div>Quality: {perfDisplay.quality}</div>
                  <div className="text-text-muted">Click to {showPerformanceStats ? 'hide' : 'show'} stats</div>
                </div>
              </TooltipContent>
            </Tooltip>
          )}
        </div>
      </div>

      {/* Canvas for browser frames */}
      <div className="flex-1 overflow-hidden bg-surface-secondary flex items-center justify-center relative">
        {status === "connected" ? (
          <div className="relative w-full h-full flex items-center justify-center">
            <canvas
              ref={canvasRef}
              width={viewport.width}
              height={viewport.height}
              tabIndex={0}
              className="focus:outline-none focus:ring-2 focus:ring-accent-primary/50"
              style={{
                width: "100%",
                height: "100%",
                objectFit: "contain",
                cursor: controlMode === "agent" ? "not-allowed" : "default",
              }}
              onMouseMove={(e) => {
                if (controlMode === "agent") return
                const { x, y } = toRemoteCoords(e)
                sendThrottledMouseMove(x, y)
              }}
              onMouseDown={(e) => {
                if (controlMode === "agent") return
                canvasRef.current?.focus()
                const { x, y } = toRemoteCoords(e)
                send({ type: "mouse_move", x, y })
                send({ type: "mouse_down", button: e.button === 2 ? "right" : "left" })
              }}
              onMouseUp={(e) => {
                if (controlMode === "agent") return
                send({ type: "mouse_up", button: e.button === 2 ? "right" : "left" })
              }}
              onClick={(e) => {
                if (controlMode === "agent") return
                const { x, y } = toRemoteCoords(e)
                send({ type: "click", x, y })
                sendEvent('interaction', { type: 'click', x, y })
              }}
              onDoubleClick={(e) => {
                if (controlMode === "agent") return
                const { x, y } = toRemoteCoords(e)
                send({ type: "click", x, y })
                send({ type: "click", x, y })
              }}
              onKeyDown={(e) => {
                if (controlMode === "agent") return
                if (!e.metaKey && !e.ctrlKey) {
                  e.preventDefault()
                }
                if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
                  send({ type: "type", text: e.key })
                } else {
                  send({ type: "key_down", key: e.key })
                }
              }}
              onKeyUp={(e) => {
                if (controlMode === "agent") return
                if (!e.metaKey && !e.ctrlKey) {
                  e.preventDefault()
                }
                if (e.key.length !== 1 || e.ctrlKey || e.metaKey || e.altKey) {
                  send({ type: "key_up", key: e.key })
                }
              }}
              onContextMenu={(e) => {
                e.preventDefault()
              }}
            />
            {/* Agent activity indicator (Phase 4A) */}
            {agentActive && (
              <div className="absolute top-2 right-2 flex items-center gap-1.5 bg-blue-500/90 text-white text-xs font-medium px-3 py-1.5 rounded-full animate-pulse pointer-events-none">
                <Bot className="h-3.5 w-3.5" />
                Agent is browsing
              </div>
            )}
            {/* Performance stats overlay */}
            {showPerformanceStats && (
              <div className="absolute top-2 left-2 bg-black/70 text-white text-[10px] font-mono px-2 py-1.5 rounded space-y-0.5 pointer-events-none">
                <div className="flex items-center gap-2">
                  <span className={cn(
                    "inline-block h-2 w-2 rounded-full",
                    perfDisplay.quality === "excellent" && "bg-green-500",
                    perfDisplay.quality === "good" && "bg-green-400",
                    perfDisplay.quality === "fair" && "bg-yellow-500",
                    perfDisplay.quality === "poor" && "bg-red-500"
                  )} />
                  <span className="uppercase">{perfDisplay.quality}</span>
                </div>
                <div>FPS: <span className={cn(perfDisplay.fps >= 24 ? "text-green-400" : perfDisplay.fps >= 15 ? "text-yellow-400" : "text-red-400")}>{perfDisplay.fps}</span></div>
                <div>Latency: <span className={cn(perfDisplay.latency < 50 ? "text-green-400" : perfDisplay.latency < 100 ? "text-yellow-400" : "text-red-400")}>{perfDisplay.latency}ms</span></div>
                <div>Quality: {QUALITY_PRESETS[perfDisplay.quality].jpegQuality}%</div>
                <div>Skip: 1/{QUALITY_PRESETS[perfDisplay.quality].everyNthFrame}</div>
                <div>Viewport: {viewport.width}x{viewport.height}</div>
                <div>Mode: {controlMode}</div>
              </div>
            )}
            {/* Keyboard focus hint */}
            <div className="absolute bottom-2 right-2 text-[10px] text-text-muted bg-surface/80 px-2 py-1 rounded opacity-50">
              {controlMode === "agent" ? "Agent control mode" : "Click to interact • Keyboard enabled when focused"}
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-4 text-text-muted p-8">
            <div className={cn(
              "p-4 rounded-full",
              status === "connecting" || status === "reconnecting" ? "bg-yellow-500/10" : "bg-surface-elevated"
            )}>
              {status === "connecting" || status === "reconnecting" ? (
                <RefreshCw className="h-10 w-10 text-yellow-500 animate-spin" />
              ) : status === "error" ? (
                <X className="h-10 w-10 text-red-500" />
              ) : (
                <Globe className="h-10 w-10 opacity-50" />
              )}
            </div>
            <div className="text-center">
              <p className="text-sm font-medium text-text-secondary mb-1">
                {status === "connecting" ? "Connecting to browser..." :
                 status === "reconnecting" ? `Reconnecting... (${reconnectAttempts}/${RECONNECT_MAX_TRIES})` :
                 status === "error" ? "Connection failed" :
                 !sessionId ? "No active session" :
                 "Browser disconnected"}
              </p>
              <p className="text-xs text-text-muted max-w-xs mb-4">
                {status === "connecting" ? "Establishing connection to remote browser..." :
                 status === "reconnecting" ? "Attempting to reconnect..." :
                 status === "error" ? "Check your connection and try again." :
                 !sessionId ? "Start a session to browse the web." :
                 "The browser session has ended."}
              </p>
              {/* Cancel Reconnect button - show when reconnecting */}
              {status === "reconnecting" && (
                <button
                  onClick={() => {
                    cancelReconnect()
                    setStatus("disconnected")
                  }}
                  className={cn(
                    "inline-flex items-center gap-2 px-4 py-2 rounded-lg mb-2",
                    "bg-red-500/10 hover:bg-red-500/20 text-red-500",
                    "text-sm font-medium transition-colors"
                  )}
                >
                  <X className="h-4 w-4" />
                  Cancel Reconnection
                </button>
              )}
              {/* Start Session button - show when not connecting/reconnecting */}
              {status !== "connecting" && status !== "reconnecting" && (
                <button
                  onClick={() => {
                    wsManager.shouldReconnect = true
                    wsManager.reconnectAttempt = 0
                    startBrowserSession()
                  }}
                  disabled={isStartingSession}
                  className={cn(
                    "inline-flex items-center gap-2 px-4 py-2 rounded-lg",
                    "bg-accent-primary hover:bg-accent-primary/90 text-white",
                    "text-sm font-medium transition-colors",
                    "disabled:opacity-50 disabled:cursor-not-allowed"
                  )}
                >
                  {isStartingSession ? (
                    <>
                      <RefreshCw className="h-4 w-4 animate-spin" />
                      Starting...
                    </>
                  ) : (
                    <>
                      <Globe className="h-4 w-4" />
                      Start Browser Session
                    </>
                  )}
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
    </TooltipProvider>
  )
}

export default AgentBrowserModule
