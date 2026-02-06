/**
 * Browser Session Events
 *
 * Simple event system for signaling browser session creation from ChatProvider
 * to PreviewPanel/TabsProvider, enabling auto-open of browser tabs when
 * agent-scraper creates browser sessions.
 *
 * Features:
 * - Singleton event emitter pattern
 * - Event buffering: events emitted before any listener subscribes are
 *   held in a buffer and replayed when the first listener attaches.
 * - Deduplication: buffered events are deduped by sessionId to avoid
 *   replaying stale or duplicate session-create signals.
 */

export interface BrowserSessionEventData {
  sessionId?: string
  wsPath?: string
  initialUrl?: string
  toolName: string
  /** For navigation events, the new URL */
  navigatedUrl?: string
  /** Event type: 'session' for new sessions, 'navigate' for URL changes */
  eventType?: 'session' | 'navigate'
}

type BrowserSessionListener = (data: BrowserSessionEventData) => void

const DEBUG = process.env.NEXT_PUBLIC_BROWSER_DEBUG === "true"

// Singleton event emitter for browser session events
class BrowserSessionEvents {
  private listeners: Set<BrowserSessionListener> = new Set()
  private buffer: BrowserSessionEventData[] = []
  private static readonly MAX_BUFFER = 10

  /**
   * Subscribe to browser session creation events.
   * If events were emitted before any listener was attached, they are replayed immediately.
   * @returns Unsubscribe function
   */
  subscribe(listener: BrowserSessionListener): () => void {
    if (DEBUG) console.log('[BrowserSessionEvents] Adding listener, count:', this.listeners.size + 1)
    this.listeners.add(listener)

    // Replay buffered events to the new listener
    if (this.buffer.length > 0 && this.listeners.size === 1) {
      const pending = [...this.buffer]
      this.buffer = []
      if (DEBUG) console.log('[BrowserSessionEvents] Replaying', pending.length, 'buffered events')
      for (const data of pending) {
        this._dispatch(data)
      }
    }

    return () => {
      this.listeners.delete(listener)
      if (DEBUG) console.log('[BrowserSessionEvents] Removed listener, count:', this.listeners.size)
    }
  }

  /**
   * Emit a browser session creation event.
   * If no listeners are registered, the event is buffered for later replay.
   */
  emit(data: BrowserSessionEventData): void {
    if (DEBUG) console.log('[BrowserSessionEvents] Emitting:', data.toolName, data.eventType || 'session')

    if (this.listeners.size === 0) {
      // Buffer events when no listeners are attached (e.g., during initial render)
      // Deduplicate by sessionId for session events
      if (data.sessionId && data.eventType !== 'navigate') {
        this.buffer = this.buffer.filter(e => e.sessionId !== data.sessionId)
      }
      this.buffer.push(data)
      // Cap buffer size
      if (this.buffer.length > BrowserSessionEvents.MAX_BUFFER) {
        this.buffer = this.buffer.slice(-BrowserSessionEvents.MAX_BUFFER)
      }
      if (DEBUG) console.log('[BrowserSessionEvents] Buffered event (no listeners), buffer size:', this.buffer.length)
      return
    }

    this._dispatch(data)
  }

  private _dispatch(data: BrowserSessionEventData): void {
    this.listeners.forEach(listener => {
      try {
        listener(data)
      } catch (err) {
        console.error('[BrowserSessionEvents] Listener error:', err)
      }
    })
  }

  /**
   * Check if a tool name indicates a browser session creation
   */
  static isBrowserSessionTool(toolName: string): boolean {
    return toolName === 'session_create' ||
           toolName === 'browser_live_start' ||
           toolName === 'session-create' ||
           toolName === 'browser-live-start' ||
           toolName === 'open_live_browser'  // Custom tool (non-MCP)
  }
}

// Global singleton
export const browserSessionEvents = new BrowserSessionEvents()

// Convenience exports
export const subscribeToBrowserSession = (listener: BrowserSessionListener) =>
  browserSessionEvents.subscribe(listener)

export const emitBrowserSession = (data: BrowserSessionEventData) =>
  browserSessionEvents.emit(data)

export const isBrowserSessionTool = BrowserSessionEvents.isBrowserSessionTool
