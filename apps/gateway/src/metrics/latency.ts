/**
 * Latency metrics tracking for Gateway ↔ Agent communication.
 *
 * Provides detailed latency measurements for diagnosing performance issues
 * and tracking optimization progress.
 */

export interface LatencyMetrics {
  // Connection metrics
  connectionSetupMs?: number;
  websocketLatencyMs?: number;

  // Request metrics
  gatewayToAgentMs: number;
  agentProcessingMs?: number;
  agentToGatewayMs?: number;
  totalRoundTripMs: number;

  // Tool metrics
  toolExecutionMs?: Record<string, number>;
  toolCount?: number;

  // Cache metrics
  cacheHit?: boolean;

  // Metadata
  timestamp: number;
  sessionId?: string;
  requestType: "turn" | "resume" | "other";
  transport: "websocket" | "http";
}

export interface AggregatedMetrics {
  count: number;
  avgRoundTripMs: number;
  p50RoundTripMs: number;
  p95RoundTripMs: number;
  p99RoundTripMs: number;
  minRoundTripMs: number;
  maxRoundTripMs: number;
  websocketCount: number;
  httpCount: number;
  errorCount: number;
}

/**
 * Latency tracker for measuring and aggregating request metrics.
 */
export class LatencyTracker {
  private metrics: LatencyMetrics[] = [];
  private readonly maxEntries: number;
  private errorCount = 0;

  constructor(maxEntries = 1000) {
    this.maxEntries = maxEntries;
  }

  /**
   * Record a latency measurement.
   */
  record(metric: Omit<LatencyMetrics, "timestamp">): void {
    const entry: LatencyMetrics = {
      ...metric,
      timestamp: Date.now(),
    };

    this.metrics.push(entry);

    // Keep only recent entries
    if (this.metrics.length > this.maxEntries) {
      this.metrics.shift();
    }
  }

  /**
   * Record an error.
   */
  recordError(): void {
    this.errorCount++;
  }

  /**
   * Get aggregated metrics.
   */
  getAggregated(windowMs?: number): AggregatedMetrics {
    const now = Date.now();
    const filtered = windowMs
      ? this.metrics.filter((m) => now - m.timestamp < windowMs)
      : this.metrics;

    if (filtered.length === 0) {
      return {
        count: 0,
        avgRoundTripMs: 0,
        p50RoundTripMs: 0,
        p95RoundTripMs: 0,
        p99RoundTripMs: 0,
        minRoundTripMs: 0,
        maxRoundTripMs: 0,
        websocketCount: 0,
        httpCount: 0,
        errorCount: this.errorCount,
      };
    }

    const roundTrips = filtered.map((m) => m.totalRoundTripMs).sort((a, b) => a - b);

    return {
      count: filtered.length,
      avgRoundTripMs: roundTrips.reduce((a, b) => a + b, 0) / roundTrips.length,
      p50RoundTripMs: this.percentile(roundTrips, 50),
      p95RoundTripMs: this.percentile(roundTrips, 95),
      p99RoundTripMs: this.percentile(roundTrips, 99),
      minRoundTripMs: roundTrips[0],
      maxRoundTripMs: roundTrips[roundTrips.length - 1],
      websocketCount: filtered.filter((m) => m.transport === "websocket").length,
      httpCount: filtered.filter((m) => m.transport === "http").length,
      errorCount: this.errorCount,
    };
  }

  /**
   * Get recent metrics.
   */
  getRecent(count = 100): LatencyMetrics[] {
    return this.metrics.slice(-count);
  }

  /**
   * Get metrics by session.
   */
  getBySession(sessionId: string, limit = 50): LatencyMetrics[] {
    return this.metrics
      .filter((m) => m.sessionId === sessionId)
      .slice(-limit);
  }

  /**
   * Clear all metrics.
   */
  clear(): void {
    this.metrics = [];
    this.errorCount = 0;
  }

  /**
   * Calculate percentile value.
   */
  private percentile(sorted: number[], p: number): number {
    if (sorted.length === 0) return 0;
    const index = Math.ceil((p / 100) * sorted.length) - 1;
    return sorted[Math.max(0, Math.min(index, sorted.length - 1))];
  }
}

/**
 * Timer utility for measuring durations.
 */
export class Timer {
  private startTime: number;
  private marks: Map<string, number> = new Map();

  constructor() {
    this.startTime = performance.now();
  }

  /**
   * Mark a point in time.
   */
  mark(name: string): void {
    this.marks.set(name, performance.now() - this.startTime);
  }

  /**
   * Get elapsed time since start.
   */
  elapsed(): number {
    return performance.now() - this.startTime;
  }

  /**
   * Get time between two marks.
   */
  between(start: string, end: string): number | undefined {
    const startMs = this.marks.get(start);
    const endMs = this.marks.get(end);
    if (startMs !== undefined && endMs !== undefined) {
      return endMs - startMs;
    }
    return undefined;
  }

  /**
   * Get all marks as object.
   */
  getMarks(): Record<string, number> {
    const result: Record<string, number> = {};
    for (const [name, time] of this.marks) {
      result[name] = time;
    }
    return result;
  }
}

// Global tracker instance
let _latencyTracker: LatencyTracker | null = null;

/**
 * Get the global latency tracker.
 */
export function getLatencyTracker(): LatencyTracker {
  if (!_latencyTracker) {
    _latencyTracker = new LatencyTracker();
  }
  return _latencyTracker;
}
