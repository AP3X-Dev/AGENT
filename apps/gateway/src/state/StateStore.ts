/**
 * Shared State Store for Gateway ↔ Agent state synchronization.
 *
 * Provides a unified state store that can use:
 * 1. Redis (recommended for production) - Real pub/sub, horizontal scaling
 * 2. In-memory (default) - Simple, no dependencies, single-instance only
 *
 * Usage:
 *   const store = await createStateStore();
 *   const session = await store.getSession('session-123');
 *   await store.updateSession('session-123', { messageCount: 5 }, 'gateway');
 */

import { EventEmitter } from "events";
import type {
  SessionState,
  StateStore,
  UpdateSource,
  createSessionState,
} from "./types.js";

// =============================================================================
// In-Memory State Store
// =============================================================================

/**
 * In-memory implementation of StateStore.
 *
 * Suitable for single-instance deployments or development.
 * Does not persist across restarts.
 */
export class InMemoryStateStore extends EventEmitter implements StateStore {
  private sessions: Map<string, SessionState> = new Map();
  private sessionSubscribers: Map<string, Set<(state: SessionState) => void>> =
    new Map();
  private allSubscribers: Set<(sessionId: string, state: SessionState) => void> =
    new Set();

  async getSession(sessionId: string): Promise<SessionState | null> {
    return this.sessions.get(sessionId) ?? null;
  }

  async setSession(sessionId: string, state: SessionState): Promise<void> {
    this.sessions.set(sessionId, state);
    this.notifySubscribers(sessionId, state);
  }

  async updateSession(
    sessionId: string,
    updates: Partial<SessionState>,
    source: UpdateSource
  ): Promise<SessionState> {
    const existing = this.sessions.get(sessionId);
    if (!existing) {
      throw new Error(`Session not found: ${sessionId}`);
    }

    const updated: SessionState = {
      ...existing,
      ...updates,
      updatedAt: new Date().toISOString(),
      version: existing.version + 1,
    };

    this.sessions.set(sessionId, updated);
    this.notifySubscribers(sessionId, updated);

    return updated;
  }

  async deleteSession(sessionId: string): Promise<boolean> {
    const existed = this.sessions.has(sessionId);
    this.sessions.delete(sessionId);
    this.sessionSubscribers.delete(sessionId);
    return existed;
  }

  async listSessions(): Promise<string[]> {
    return Array.from(this.sessions.keys());
  }

  subscribe(
    sessionId: string,
    callback: (state: SessionState) => void
  ): () => void {
    if (!this.sessionSubscribers.has(sessionId)) {
      this.sessionSubscribers.set(sessionId, new Set());
    }
    this.sessionSubscribers.get(sessionId)!.add(callback);

    return () => {
      this.sessionSubscribers.get(sessionId)?.delete(callback);
    };
  }

  subscribeAll(
    callback: (sessionId: string, state: SessionState) => void
  ): () => void {
    this.allSubscribers.add(callback);
    return () => {
      this.allSubscribers.delete(callback);
    };
  }

  async close(): Promise<void> {
    this.sessions.clear();
    this.sessionSubscribers.clear();
    this.allSubscribers.clear();
  }

  private notifySubscribers(sessionId: string, state: SessionState): void {
    // Notify session-specific subscribers
    const subscribers = this.sessionSubscribers.get(sessionId);
    if (subscribers) {
      for (const callback of subscribers) {
        try {
          callback(state);
        } catch (err) {
          console.error("[StateStore] Subscriber error:", err);
        }
      }
    }

    // Notify all-session subscribers
    for (const callback of this.allSubscribers) {
      try {
        callback(sessionId, state);
      } catch (err) {
        console.error("[StateStore] Subscriber error:", err);
      }
    }

    // Emit event for external listeners
    this.emit("update", { sessionId, state });
  }

  /**
   * Get store statistics.
   */
  getStats(): {
    sessionCount: number;
    subscriberCount: number;
  } {
    let subscriberCount = this.allSubscribers.size;
    for (const subs of this.sessionSubscribers.values()) {
      subscriberCount += subs.size;
    }

    return {
      sessionCount: this.sessions.size,
      subscriberCount,
    };
  }
}

// =============================================================================
// Redis State Store
// =============================================================================

/**
 * Redis implementation of StateStore.
 *
 * Provides real pub/sub for multi-instance deployments.
 * Requires Redis server.
 */
export class RedisStateStore extends EventEmitter implements StateStore {
  private redis: any; // Redis client (ioredis)
  private subscriber: any; // Redis subscriber client
  private sessionSubscribers: Map<string, Set<(state: SessionState) => void>> =
    new Map();
  private allSubscribers: Set<(sessionId: string, state: SessionState) => void> =
    new Set();
  private readonly keyPrefix = "ag3nt:session:";
  private readonly channelPrefix = "ag3nt:updates:";

  constructor(redisUrl: string) {
    super();
    this.initRedis(redisUrl);
  }

  private async initRedis(redisUrl: string): Promise<void> {
    try {
      // Dynamic import to avoid dependency if not using Redis
      // @ts-expect-error ioredis types are optional - only needed when using Redis backend
      const { default: Redis } = await import("ioredis");

      this.redis = new Redis(redisUrl);
      this.subscriber = new Redis(redisUrl);

      // Subscribe to all session updates
      await this.subscriber.psubscribe(`${this.channelPrefix}*`);

      this.subscriber.on("pmessage", (_pattern: string, channel: string, message: string) => {
        try {
          const sessionId = channel.replace(this.channelPrefix, "");
          const state = JSON.parse(message) as SessionState;
          this.notifyLocalSubscribers(sessionId, state);
        } catch (err) {
          console.error("[RedisStateStore] Message parse error:", err);
        }
      });

      console.log("[RedisStateStore] Connected to Redis");
    } catch (err) {
      console.error("[RedisStateStore] Failed to connect:", err);
      throw err;
    }
  }

  async getSession(sessionId: string): Promise<SessionState | null> {
    const data = await this.redis.get(`${this.keyPrefix}${sessionId}`);
    return data ? JSON.parse(data) : null;
  }

  async setSession(sessionId: string, state: SessionState): Promise<void> {
    await this.redis.set(
      `${this.keyPrefix}${sessionId}`,
      JSON.stringify(state)
    );
    await this.publishUpdate(sessionId, state);
  }

  async updateSession(
    sessionId: string,
    updates: Partial<SessionState>,
    _source: UpdateSource
  ): Promise<SessionState> {
    // Use Lua script for atomic update
    const script = `
      local key = KEYS[1]
      local updates = cjson.decode(ARGV[1])
      local existing = redis.call('GET', key)

      if not existing then
        return nil
      end

      local state = cjson.decode(existing)

      -- Apply updates
      for k, v in pairs(updates) do
        state[k] = v
      end

      state.updatedAt = ARGV[2]
      state.version = state.version + 1

      local result = cjson.encode(state)
      redis.call('SET', key, result)

      return result
    `;

    const result = await this.redis.eval(
      script,
      1,
      `${this.keyPrefix}${sessionId}`,
      JSON.stringify(updates),
      new Date().toISOString()
    );

    if (!result) {
      throw new Error(`Session not found: ${sessionId}`);
    }

    const updated = JSON.parse(result) as SessionState;
    await this.publishUpdate(sessionId, updated);

    return updated;
  }

  async deleteSession(sessionId: string): Promise<boolean> {
    const result = await this.redis.del(`${this.keyPrefix}${sessionId}`);
    return result > 0;
  }

  async listSessions(): Promise<string[]> {
    const keys = await this.redis.keys(`${this.keyPrefix}*`);
    return keys.map((key: string) => key.replace(this.keyPrefix, ""));
  }

  subscribe(
    sessionId: string,
    callback: (state: SessionState) => void
  ): () => void {
    if (!this.sessionSubscribers.has(sessionId)) {
      this.sessionSubscribers.set(sessionId, new Set());
    }
    this.sessionSubscribers.get(sessionId)!.add(callback);

    return () => {
      this.sessionSubscribers.get(sessionId)?.delete(callback);
    };
  }

  subscribeAll(
    callback: (sessionId: string, state: SessionState) => void
  ): () => void {
    this.allSubscribers.add(callback);
    return () => {
      this.allSubscribers.delete(callback);
    };
  }

  async close(): Promise<void> {
    await this.subscriber?.quit();
    await this.redis?.quit();
    this.sessionSubscribers.clear();
    this.allSubscribers.clear();
  }

  private async publishUpdate(
    sessionId: string,
    state: SessionState
  ): Promise<void> {
    await this.redis.publish(
      `${this.channelPrefix}${sessionId}`,
      JSON.stringify(state)
    );
  }

  private notifyLocalSubscribers(
    sessionId: string,
    state: SessionState
  ): void {
    const subscribers = this.sessionSubscribers.get(sessionId);
    if (subscribers) {
      for (const callback of subscribers) {
        try {
          callback(state);
        } catch (err) {
          console.error("[RedisStateStore] Subscriber error:", err);
        }
      }
    }

    for (const callback of this.allSubscribers) {
      try {
        callback(sessionId, state);
      } catch (err) {
        console.error("[RedisStateStore] Subscriber error:", err);
      }
    }

    this.emit("update", { sessionId, state });
  }
}

// =============================================================================
// Factory
// =============================================================================

/** Global state store instance */
let _stateStore: StateStore | null = null;

/**
 * Create or get the shared state store.
 *
 * Uses Redis if AG3NT_REDIS_URL is set, otherwise uses in-memory store.
 */
export async function getStateStore(): Promise<StateStore> {
  if (_stateStore) {
    return _stateStore;
  }

  const redisUrl = process.env.AG3NT_REDIS_URL;

  if (redisUrl) {
    try {
      _stateStore = new RedisStateStore(redisUrl);
      console.log("[StateStore] Using Redis backend");
    } catch (err) {
      console.warn("[StateStore] Redis failed, falling back to in-memory:", err);
      _stateStore = new InMemoryStateStore();
    }
  } else {
    _stateStore = new InMemoryStateStore();
    console.log("[StateStore] Using in-memory backend");
  }

  return _stateStore;
}

/**
 * Close the state store.
 */
export async function closeStateStore(): Promise<void> {
  if (_stateStore) {
    await _stateStore.close();
    _stateStore = null;
  }
}

/**
 * Check if using Redis backend.
 */
export function isUsingRedis(): boolean {
  return _stateStore instanceof RedisStateStore;
}
