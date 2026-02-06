/**
 * Priority message queue with rate limiting.
 *
 * Provides ordered message processing based on session priority.
 * Includes a rate limiter that enforces per-session quotas and
 * a QueueManager that orchestrates the full flow.
 */
import { randomUUID } from 'crypto';
import type { ChannelMessage, ChannelResponse } from '../channels/types.js';
import type { EnhancedSession, SessionQuotas } from '../session/SessionStore.js';
import type { RoutingDecision } from './AgentRouter.js';

// ─────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────

export interface QueueItem {
  id: string;
  message: ChannelMessage;
  session: EnhancedSession;
  priority: number;
  enqueuedAt: number;
  routingDecision: RoutingDecision;
  resolve: (response: ChannelResponse) => void;
  reject: (error: Error) => void;
}

export interface QueueStats {
  size: number;
  processing: number;
  totalEnqueued: number;
  totalProcessed: number;
  totalRejected: number;
}

// ─────────────────────────────────────────────────────────────────
// MessageQueue - Min-Heap implementation
// ─────────────────────────────────────────────────────────────────

export class MessageQueue {
  private heap: QueueItem[] = [];

  enqueue(item: QueueItem): void {
    this.heap.push(item);
    this.bubbleUp(this.heap.length - 1);
  }

  dequeue(): QueueItem | null {
    if (this.heap.length === 0) return null;
    if (this.heap.length === 1) return this.heap.pop()!;

    const top = this.heap[0];
    this.heap[0] = this.heap.pop()!;
    this.bubbleDown(0);
    return top;
  }

  peek(): QueueItem | null {
    return this.heap.length > 0 ? this.heap[0] : null;
  }

  size(): number {
    return this.heap.length;
  }

  private bubbleUp(index: number): void {
    while (index > 0) {
      const parentIndex = Math.floor((index - 1) / 2);
      if (this.heap[parentIndex].priority <= this.heap[index].priority) break;
      [this.heap[parentIndex], this.heap[index]] = [this.heap[index], this.heap[parentIndex]];
      index = parentIndex;
    }
  }

  private bubbleDown(index: number): void {
    const length = this.heap.length;
    while (true) {
      let smallest = index;
      const left = 2 * index + 1;
      const right = 2 * index + 2;

      if (left < length && this.heap[left].priority < this.heap[smallest].priority) {
        smallest = left;
      }
      if (right < length && this.heap[right].priority < this.heap[smallest].priority) {
        smallest = right;
      }

      if (smallest === index) break;
      [this.heap[smallest], this.heap[index]] = [this.heap[index], this.heap[smallest]];
      index = smallest;
    }
  }
}

// ─────────────────────────────────────────────────────────────────
// RateLimiter - Sliding window per session
// ─────────────────────────────────────────────────────────────────

interface SessionWindow {
  timestamps: number[];
  concurrent: number;
}

export class RateLimiter {
  private windows: Map<string, SessionWindow> = new Map();

  tryAcquire(sessionId: string, quotas: SessionQuotas): boolean {
    const now = Date.now();
    const oneHourAgo = now - 3600_000;

    let window = this.windows.get(sessionId);
    if (!window) {
      window = { timestamps: [], concurrent: 0 };
      this.windows.set(sessionId, window);
    }

    // Prune old timestamps outside the 1-hour window
    window.timestamps = window.timestamps.filter((t) => t > oneHourAgo);

    // Check turns per hour
    if (window.timestamps.length >= quotas.maxTurnsPerHour) {
      return false;
    }

    // Check concurrent
    if (window.concurrent >= quotas.maxConcurrent) {
      return false;
    }

    // Acquire
    window.timestamps.push(now);
    window.concurrent++;
    return true;
  }

  release(sessionId: string): void {
    const window = this.windows.get(sessionId);
    if (window && window.concurrent > 0) {
      window.concurrent--;
    }
  }

  getStats(sessionId: string): { turnsInLastHour: number; concurrent: number } | null {
    const window = this.windows.get(sessionId);
    if (!window) return null;

    const oneHourAgo = Date.now() - 3600_000;
    const recent = window.timestamps.filter((t) => t > oneHourAgo);
    return {
      turnsInLastHour: recent.length,
      concurrent: window.concurrent,
    };
  }
}

// ─────────────────────────────────────────────────────────────────
// QueueManager - Orchestrator
// ─────────────────────────────────────────────────────────────────

export interface QueueManagerConfig {
  queueEnabled: boolean;
  queueIntervalMs: number;
  maxQueueSize: number;
}

export class QueueManager {
  private queue: MessageQueue;
  private rateLimiter: RateLimiter;
  private config: QueueManagerConfig;
  private processHandler: ((item: QueueItem) => Promise<ChannelResponse>) | null = null;
  private intervalId: ReturnType<typeof setInterval> | null = null;
  private stats: QueueStats = {
    size: 0,
    processing: 0,
    totalEnqueued: 0,
    totalProcessed: 0,
    totalRejected: 0,
  };

  constructor(config: QueueManagerConfig) {
    this.config = config;
    this.queue = new MessageQueue();
    this.rateLimiter = new RateLimiter();
  }

  /**
   * Set the handler that processes dequeued items.
   */
  setProcessHandler(handler: (item: QueueItem) => Promise<ChannelResponse>): void {
    this.processHandler = handler;
  }

  /**
   * Submit a message for processing.
   * If queueing is disabled, processes immediately.
   * Returns a promise that resolves with the response.
   */
  submit(
    message: ChannelMessage,
    session: EnhancedSession,
    routingDecision: RoutingDecision,
  ): Promise<ChannelResponse> {
    // Rate limit check
    if (!this.rateLimiter.tryAcquire(session.id, session.quotas)) {
      this.stats.totalRejected++;
      return Promise.resolve({
        text: 'Rate limit exceeded. Please try again later.',
        metadata: { rateLimited: true, sessionId: session.id },
      });
    }

    // If queue is disabled, process immediately
    if (!this.config.queueEnabled) {
      return this.processItem({
        id: randomUUID(),
        message,
        session,
        priority: session.priority,
        enqueuedAt: Date.now(),
        routingDecision,
        resolve: () => {},
        reject: () => {},
      });
    }

    // Check max queue size
    if (this.queue.size() >= this.config.maxQueueSize) {
      this.rateLimiter.release(session.id);
      this.stats.totalRejected++;
      return Promise.resolve({
        text: 'The system is currently at capacity. Please try again later.',
        metadata: { queueFull: true, sessionId: session.id },
      });
    }

    // Enqueue with promise
    return new Promise<ChannelResponse>((resolve, reject) => {
      const item: QueueItem = {
        id: randomUUID(),
        message,
        session,
        priority: session.priority,
        enqueuedAt: Date.now(),
        routingDecision,
        resolve,
        reject,
      };

      this.queue.enqueue(item);
      this.stats.totalEnqueued++;
      this.stats.size = this.queue.size();
    });
  }

  /**
   * Process the next item from the queue.
   */
  async processNext(): Promise<void> {
    const item = this.queue.dequeue();
    if (!item) return;

    this.stats.size = this.queue.size();

    try {
      const response = await this.processItem(item);
      item.resolve(response);
    } catch (err) {
      item.reject(err instanceof Error ? err : new Error(String(err)));
    }
  }

  /**
   * Start the processing loop.
   */
  start(intervalMs?: number): void {
    if (this.intervalId) return;

    const interval = intervalMs ?? this.config.queueIntervalMs;
    this.intervalId = setInterval(() => {
      if (this.queue.size() > 0) {
        this.processNext().catch((err) => {
          console.error('[QueueManager] Processing error:', err);
        });
      }
    }, interval);
  }

  /**
   * Stop the processing loop.
   */
  stop(): void {
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
  }

  /**
   * Get queue statistics.
   */
  getStats(): QueueStats {
    return { ...this.stats, size: this.queue.size() };
  }

  getRateLimiter(): RateLimiter {
    return this.rateLimiter;
  }

  private async processItem(item: QueueItem): Promise<ChannelResponse> {
    this.stats.processing++;

    try {
      if (!this.processHandler) {
        throw new Error('No process handler configured');
      }

      const response = await this.processHandler(item);
      this.stats.totalProcessed++;
      return response;
    } finally {
      this.stats.processing--;
      this.rateLimiter.release(item.session.id);
    }
  }
}
