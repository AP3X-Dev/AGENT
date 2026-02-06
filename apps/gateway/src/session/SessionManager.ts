/**
 * Session Manager for AG3NT Gateway.
 *
 * Manages session isolation per channel+user combination.
 * Handles DM pairing security for untrusted contacts.
 */

import crypto from "node:crypto";
import { generateSessionId, type DMPolicy } from "../channels/types.js";
import type { SessionStore, EnhancedSession } from "./SessionStore.js";
import { createDefaultEnhancedSession } from "./SessionStore.js";

/**
 * Session state for a channel+user combination.
 */
export interface Session {
  /** Unique session ID: `${channelType}:${channelId}:${chatId}` */
  id: string;
  /** Channel type (e.g., 'telegram', 'discord') */
  channelType: string;
  /** Channel instance ID */
  channelId: string;
  /** Chat/conversation ID */
  chatId: string;
  /** Primary user ID in this session */
  userId: string;
  /** User display name (if known) */
  userName?: string;
  /** When the session was created */
  createdAt: Date;
  /** Last activity timestamp */
  lastActivityAt: Date;
  /** Whether this session has been paired/approved */
  paired: boolean;
  /** Pending pairing code (if awaiting approval) */
  pairingCode?: string;
  /** When the pairing code expires */
  pairingCodeExpiresAt?: Date;
}

/**
 * Session Manager configuration.
 */
export interface SessionManagerConfig {
  /** DM security policy */
  dmPolicy: DMPolicy;
  /** Pairing code expiry in milliseconds (default: 10 minutes) */
  pairingCodeTTL?: number;
  /** Allowlist of pre-approved session patterns (e.g., 'telegram:*:12345') */
  allowlist?: string[];
  /** Optional callback to persist allowlist changes */
  onAllowlistChange?: (allowlist: string[]) => void | Promise<void>;
  /** Optional persistent session store */
  sessionStore?: SessionStore;
  /** Default quota overrides */
  defaultQuotas?: { maxTurnsPerHour?: number; maxTokensPerTurn?: number; maxConcurrent?: number };
}

const DEFAULT_PAIRING_TTL = 10 * 60 * 1000; // 10 minutes

/**
 * Manages sessions for the Gateway.
 * Provides session isolation and DM pairing security.
 */
export class SessionManager {
  private sessions: Map<string, Session> = new Map();
  private enhancedSessions: Map<string, EnhancedSession> = new Map();
  private allowlist: Set<string> = new Set();
  private dmPolicy: DMPolicy;
  private pairingCodeTTL: number;
  private onAllowlistChange?: (allowlist: string[]) => void | Promise<void>;
  private sessionStore?: SessionStore;
  private defaultQuotas?: SessionManagerConfig['defaultQuotas'];

  constructor(config: SessionManagerConfig) {
    this.dmPolicy = config.dmPolicy;
    this.pairingCodeTTL = config.pairingCodeTTL ?? DEFAULT_PAIRING_TTL;
    this.onAllowlistChange = config.onAllowlistChange;
    this.sessionStore = config.sessionStore;
    this.defaultQuotas = config.defaultQuotas;
    if (config.allowlist) {
      config.allowlist.forEach((pattern) => this.allowlist.add(pattern));
    }
  }

  /**
   * Notify listeners of allowlist changes.
   */
  private async notifyAllowlistChange(): Promise<void> {
    if (this.onAllowlistChange) {
      try {
        await this.onAllowlistChange(this.getAllowlist());
      } catch (error) {
        console.error("[SessionManager] Failed to persist allowlist:", error);
      }
    }
  }

  /**
   * Get or create a session for a channel+chat combination.
   */
  getOrCreateSession(
    channelType: string,
    channelId: string,
    chatId: string,
    userId: string,
    userName?: string
  ): Session {
    const sessionId = generateSessionId(channelType, channelId, chatId);
    let session = this.sessions.get(sessionId);

    if (!session) {
      const now = new Date();
      session = {
        id: sessionId,
        channelType,
        channelId,
        chatId,
        userId,
        userName,
        createdAt: now,
        lastActivityAt: now,
        paired: this.isPreApproved(sessionId, userId),
      };
      this.sessions.set(sessionId, session);

      // Load or create enhanced session from persistent store
      this.loadOrCreateEnhancedSession(sessionId, channelType, channelId, chatId);
    } else {
      // Update activity and user info
      session.lastActivityAt = new Date();
      if (userName) session.userName = userName;
    }

    return session;
  }

  /**
   * Get an existing session by ID.
   */
  getSession(sessionId: string): Session | undefined {
    return this.sessions.get(sessionId);
  }

  /**
   * Check if a session is paired/approved.
   */
  isSessionPaired(sessionId: string): boolean {
    const session = this.sessions.get(sessionId);
    if (!session) return false;

    // In open mode, all sessions are paired
    if (this.dmPolicy === "open") return true;

    return session.paired;
  }

  /**
   * Check if a session/user is pre-approved via allowlist.
   */
  private isPreApproved(sessionId: string, userId: string): boolean {
    // Check exact match
    if (this.allowlist.has(sessionId)) return true;
    if (this.allowlist.has(userId)) return true;

    // Check wildcard patterns (simple glob: * matches any segment)
    for (const pattern of this.allowlist) {
      if (this.matchesPattern(sessionId, pattern)) return true;
    }

    // In open mode, everyone is pre-approved
    return this.dmPolicy === "open";
  }

  private matchesPattern(value: string, pattern: string): boolean {
    const regex = new RegExp(
      "^" + pattern.replace(/\*/g, "[^:]*").replace(/\?/g, ".") + "$"
    );
    return regex.test(value);
  }

  /**
   * Generate a pairing code for a session.
   * User must provide this code to approve the session.
   */
  generatePairingCode(sessionId: string): string {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Session not found: ${sessionId}`);
    }

    // Generate 6-character alphanumeric code
    const code = crypto.randomBytes(3).toString("hex").toUpperCase();
    session.pairingCode = code;
    session.pairingCodeExpiresAt = new Date(Date.now() + this.pairingCodeTTL);

    return code;
  }

  /**
   * Approve a session using a pairing code.
   * @returns true if approved, false if code is invalid/expired
   */
  async approveSession(sessionId: string, code: string): Promise<boolean> {
    const session = this.sessions.get(sessionId);
    if (!session) return false;

    // Check code matches and is not expired
    if (session.pairingCode !== code.toUpperCase()) return false;
    if (
      session.pairingCodeExpiresAt &&
      session.pairingCodeExpiresAt < new Date()
    ) {
      return false;
    }

    // Approve the session
    session.paired = true;
    session.pairingCode = undefined;
    session.pairingCodeExpiresAt = undefined;

    // Add to allowlist for persistence
    this.allowlist.add(sessionId);
    await this.notifyAllowlistChange();

    return true;
  }

  /**
   * Manually approve a session (e.g., from CLI or control panel).
   */
  async manualApprove(sessionId: string): Promise<boolean> {
    const session = this.sessions.get(sessionId);
    if (!session) return false;

    session.paired = true;
    session.pairingCode = undefined;
    session.pairingCodeExpiresAt = undefined;
    this.allowlist.add(sessionId);
    await this.notifyAllowlistChange();

    return true;
  }

  /**
   * Add an entry to the allowlist.
   */
  async addToAllowlist(pattern: string): Promise<void> {
    this.allowlist.add(pattern);
    await this.notifyAllowlistChange();
  }

  /**
   * Remove an entry from the allowlist.
   */
  async removeFromAllowlist(pattern: string): Promise<void> {
    this.allowlist.delete(pattern);
    await this.notifyAllowlistChange();
  }

  /**
   * Get the current allowlist.
   */
  getAllowlist(): string[] {
    return Array.from(this.allowlist);
  }

  /**
   * List all active sessions.
   */
  listSessions(): Session[] {
    return Array.from(this.sessions.values());
  }

  /**
   * Get sessions pending pairing approval.
   */
  getPendingSessions(): Session[] {
    return this.listSessions().filter(
      (s) => !s.paired && s.pairingCode !== undefined
    );
  }

  /**
   * Remove a session.
   */
  removeSession(sessionId: string): boolean {
    this.enhancedSessions.delete(sessionId);
    if (this.sessionStore) {
      this.sessionStore.delete(sessionId);
    }
    return this.sessions.delete(sessionId);
  }

  /**
   * Update the last activity timestamp for a session.
   * @returns true if session was found and updated, false otherwise
   */
  touchSession(sessionId: string): boolean {
    const session = this.sessions.get(sessionId);
    if (!session) return false;
    session.lastActivityAt = new Date();
    return true;
  }

  // ─────────────────────────────────────────────────────────────────
  // Enhanced Session Support
  // ─────────────────────────────────────────────────────────────────

  /**
   * Load or create an enhanced session, backed by persistent store.
   */
  private loadOrCreateEnhancedSession(
    sessionId: string,
    channelType: string,
    channelId: string,
    chatId: string,
  ): EnhancedSession {
    // Check in-memory cache first
    const cached = this.enhancedSessions.get(sessionId);
    if (cached) return cached;

    // Try loading from persistent store
    if (this.sessionStore) {
      const loaded = this.sessionStore.load(sessionId);
      if (loaded) {
        this.enhancedSessions.set(sessionId, loaded);
        return loaded;
      }
    }

    // Create new enhanced session with defaults
    const enhanced = createDefaultEnhancedSession(
      sessionId,
      channelType,
      channelId,
      chatId,
      this.defaultQuotas,
    );

    this.enhancedSessions.set(sessionId, enhanced);

    // Persist to store
    if (this.sessionStore) {
      this.sessionStore.save(enhanced);
    }

    return enhanced;
  }

  /**
   * Get the enhanced session data for a session.
   */
  getEnhancedSession(sessionId: string): EnhancedSession | null {
    // Check in-memory cache
    const cached = this.enhancedSessions.get(sessionId);
    if (cached) return cached;

    // Try loading from store
    if (this.sessionStore) {
      const loaded = this.sessionStore.load(sessionId);
      if (loaded) {
        this.enhancedSessions.set(sessionId, loaded);
        return loaded;
      }
    }

    return null;
  }

  /**
   * Update enhanced session fields.
   */
  updateSession(
    sessionId: string,
    updates: Partial<Pick<EnhancedSession, 'priority' | 'assignedAgent' | 'activationMode' | 'activationKeywords' | 'quotas' | 'metadata'>>,
  ): EnhancedSession | null {
    const enhanced = this.getEnhancedSession(sessionId);
    if (!enhanced) return null;

    if (updates.priority !== undefined) enhanced.priority = updates.priority;
    if (updates.assignedAgent !== undefined) enhanced.assignedAgent = updates.assignedAgent;
    if (updates.activationMode !== undefined) enhanced.activationMode = updates.activationMode;
    if (updates.activationKeywords !== undefined) enhanced.activationKeywords = updates.activationKeywords;
    if (updates.quotas !== undefined) enhanced.quotas = { ...enhanced.quotas, ...updates.quotas };
    if (updates.metadata !== undefined) enhanced.metadata = { ...enhanced.metadata, ...updates.metadata };

    enhanced.updatedAt = new Date().toISOString();

    // Update in-memory cache
    this.enhancedSessions.set(sessionId, enhanced);

    // Persist to store
    if (this.sessionStore) {
      this.sessionStore.save(enhanced);
    }

    return enhanced;
  }

  /**
   * Get the session store.
   */
  getSessionStore(): SessionStore | undefined {
    return this.sessionStore;
  }
}

