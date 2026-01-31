/**
 * Session Lifecycle Manager for AG3NT Gateway.
 *
 * Manages session lifecycle including automatic cleanup of expired sessions,
 * session destruction with message history cleanup, and session resume validation.
 */
import { EventEmitter } from 'events';
import type { SessionManager, Session } from './SessionManager.js';
import type { MessageStore } from '../storage/MessageStore.js';

export interface SessionLifecycleConfig {
  /** Session timeout in milliseconds (default: 24 hours) */
  sessionTimeout: number;
  /** Cleanup interval in milliseconds (default: 1 hour) */
  cleanupInterval: number;
  /** Whether to persist sessions across restarts */
  persistSessions: boolean;
}

export interface SessionResumeContext {
  channelType: string;
  channelId: string;
  userId: string;
}

export interface SessionLifecycleEvents {
  sessionsCleanedUp: { count: number };
  sessionDestroyed: { sessionId: string };
  sessionResumed: { sessionId: string };
}

const DEFAULT_LIFECYCLE_CONFIG: SessionLifecycleConfig = {
  sessionTimeout: 24 * 60 * 60 * 1000, // 24 hours
  cleanupInterval: 60 * 60 * 1000, // 1 hour
  persistSessions: true,
};

/**
 * Manages session lifecycle for the Gateway.
 */
export class SessionLifecycleManager extends EventEmitter {
  private cleanupTimer: ReturnType<typeof setInterval> | null = null;
  private config: SessionLifecycleConfig;

  constructor(
    private sessionManager: SessionManager,
    private messageStore: MessageStore,
    config: Partial<SessionLifecycleConfig> = {},
  ) {
    super();
    this.config = { ...DEFAULT_LIFECYCLE_CONFIG, ...config };
  }

  /**
   * Get the current configuration.
   */
  getConfig(): SessionLifecycleConfig {
    return { ...this.config };
  }

  /**
   * Check if the lifecycle manager is running.
   */
  isRunning(): boolean {
    return this.cleanupTimer !== null;
  }

  /**
   * Start the lifecycle manager.
   * Begins periodic cleanup of expired sessions.
   */
  start(): void {
    if (this.cleanupTimer) return; // Already running

    this.cleanupTimer = setInterval(
      () => this.cleanupExpiredSessions(),
      this.config.cleanupInterval,
    );
  }

  /**
   * Stop the lifecycle manager.
   */
  stop(): void {
    if (this.cleanupTimer) {
      clearInterval(this.cleanupTimer);
      this.cleanupTimer = null;
    }
  }

  /**
   * Cleanup sessions that have been inactive longer than the timeout.
   * @returns Number of sessions cleaned up
   */
  cleanupExpiredSessions(): number {
    const now = Date.now();
    const sessions = this.sessionManager.listSessions();
    let cleaned = 0;

    for (const session of sessions) {
      const inactiveTime = now - session.lastActivityAt.getTime();
      if (inactiveTime > this.config.sessionTimeout) {
        this.destroySession(session.id);
        cleaned++;
      }
    }

    if (cleaned > 0) {
      this.emit('sessionsCleanedUp', { count: cleaned });
    }

    return cleaned;
  }

  /**
   * Destroy a session and its message history.
   */
  destroySession(sessionId: string): boolean {
    // Delete message history first
    this.messageStore.deleteSessionMessages(sessionId);

    // Remove session
    const removed = this.sessionManager.removeSession(sessionId);

    if (removed) {
      this.emit('sessionDestroyed', { sessionId });
    }

    return removed;
  }

  /**
   * Resume a session if it exists and matches the provided context.
   * @returns The session if valid for resume, null otherwise
   */
  resumeSession(sessionId: string, context: SessionResumeContext): Session | null {
    const session = this.sessionManager.getSession(sessionId);

    if (!session) {
      return null;
    }

    // Verify session matches context (ownership validation)
    if (
      session.channelType !== context.channelType ||
      session.channelId !== context.channelId ||
      session.userId !== context.userId
    ) {
      return null; // Session doesn't match - ownership validation failed
    }

    // Update last activity
    this.sessionManager.touchSession(sessionId);

    this.emit('sessionResumed', { sessionId });

    return session;
  }
}

