/**
 * Shared state types for Gateway ↔ Agent state synchronization.
 *
 * These types define the unified session state that is shared between
 * the Gateway (TypeScript) and Agent Worker (Python) services.
 */

// =============================================================================
// Session State
// =============================================================================

/**
 * Activation modes for sessions.
 */
export type ActivationMode = "always" | "mention" | "reply" | "keyword" | "off";

/**
 * Session quotas for rate limiting.
 */
export interface SessionQuotas {
  maxTokensPerDay: number;
  maxRequestsPerHour: number;
  tokensUsedToday: number;
  requestsThisHour: number;
  quotaResetAt: string; // ISO timestamp
}

/**
 * Directive attached to a session.
 */
export interface SessionDirective {
  id: string;
  content: string;
  priority: number;
  active: boolean;
  createdAt: string;
  expiresAt?: string;
}

/**
 * Pending approval information.
 */
export interface PendingApproval {
  interruptId: string;
  toolName: string;
  args: Record<string, unknown>;
  description: string;
  createdAt: string;
}

/**
 * Unified session state shared between Gateway and Agent.
 */
export interface SessionState {
  // Identity
  sessionId: string;
  channelType: string;
  channelId: string;
  chatId: string;
  userId: string;
  userName?: string;

  // Gateway-managed fields
  priority: number;
  assignedAgent: string | null;
  directives: SessionDirective[];
  quotas: SessionQuotas;
  activationMode: ActivationMode;
  paired: boolean;
  pairingCode?: string;

  // Agent-managed fields
  messageCount: number;
  lastTurnAt: string | null;
  activeTools: string[];
  pendingApprovals: PendingApproval[];

  // Timestamps
  createdAt: string;
  updatedAt: string;

  // Metadata
  metadata: Record<string, unknown>;

  // Version for optimistic locking
  version: number;
}

// =============================================================================
// State Updates
// =============================================================================

/**
 * Source of a state update.
 */
export type UpdateSource = "gateway" | "agent";

/**
 * A single field update in a session state.
 */
export interface StateUpdate {
  sessionId: string;
  field: keyof SessionState;
  value: unknown;
  version: number;
  source: UpdateSource;
  timestamp: number;
}

/**
 * Batch of state updates.
 */
export interface StateBatch {
  sessionId: string;
  updates: Partial<SessionState>;
  source: UpdateSource;
  timestamp: number;
}

// =============================================================================
// Sync Messages
// =============================================================================

/**
 * Message types for state synchronization.
 */
export type StateSyncMessageType =
  | "sync"        // Full state sync
  | "update"      // Partial update
  | "subscribe"   // Subscribe to session updates
  | "unsubscribe" // Unsubscribe from session updates
  | "ack";        // Acknowledge receipt

/**
 * State sync message sent between services.
 */
export interface StateSyncMessage {
  type: StateSyncMessageType;
  sessionId?: string;
  state?: Partial<SessionState>;
  updates?: StateUpdate[];
  source: UpdateSource;
  timestamp: number;
  messageId: string;
}

// =============================================================================
// Store Interface
// =============================================================================

/**
 * Interface for the shared state store.
 */
export interface StateStore {
  /**
   * Get session state by ID.
   */
  getSession(sessionId: string): Promise<SessionState | null>;

  /**
   * Set full session state.
   */
  setSession(sessionId: string, state: SessionState): Promise<void>;

  /**
   * Update specific fields of a session.
   */
  updateSession(
    sessionId: string,
    updates: Partial<SessionState>,
    source: UpdateSource
  ): Promise<SessionState>;

  /**
   * Delete a session.
   */
  deleteSession(sessionId: string): Promise<boolean>;

  /**
   * List all session IDs.
   */
  listSessions(): Promise<string[]>;

  /**
   * Subscribe to session updates.
   */
  subscribe(
    sessionId: string,
    callback: (state: SessionState) => void
  ): () => void;

  /**
   * Subscribe to all session updates.
   */
  subscribeAll(
    callback: (sessionId: string, state: SessionState) => void
  ): () => void;

  /**
   * Close the store and release resources.
   */
  close(): Promise<void>;
}

// =============================================================================
// Default Values
// =============================================================================

/**
 * Create default session quotas.
 */
export function createDefaultQuotas(): SessionQuotas {
  const now = new Date();
  const resetAt = new Date(now);
  resetAt.setHours(24, 0, 0, 0); // Reset at midnight

  return {
    maxTokensPerDay: 100000,
    maxRequestsPerHour: 60,
    tokensUsedToday: 0,
    requestsThisHour: 0,
    quotaResetAt: resetAt.toISOString(),
  };
}

/**
 * Create a new session state with defaults.
 */
export function createSessionState(
  sessionId: string,
  channelType: string,
  channelId: string,
  chatId: string,
  userId: string,
  userName?: string
): SessionState {
  const now = new Date().toISOString();

  return {
    sessionId,
    channelType,
    channelId,
    chatId,
    userId,
    userName,

    priority: 5,
    assignedAgent: null,
    directives: [],
    quotas: createDefaultQuotas(),
    activationMode: "always",
    paired: false,

    messageCount: 0,
    lastTurnAt: null,
    activeTools: [],
    pendingApprovals: [],

    createdAt: now,
    updatedAt: now,

    metadata: {},
    version: 1,
  };
}
