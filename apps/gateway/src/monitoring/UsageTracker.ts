/**
 * API Usage Tracker for AG3NT Gateway.
 *
 * Tracks API calls, token usage, and costs across LLM providers.
 * Provides usage statistics and export capabilities.
 */

export interface UsageRecord {
  id: string;
  timestamp: Date;
  provider: string;
  model: string;
  sessionId: string;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  cost: number;
  latencyMs: number;
  success: boolean;
  errorCode?: string;
}

export interface UsageStats {
  totalCalls: number;
  successfulCalls: number;
  failedCalls: number;
  totalTokens: number;
  totalInputTokens: number;
  totalOutputTokens: number;
  totalCost: number;
  averageLatencyMs: number;
  byProvider: Record<string, ProviderStats>;
  byModel: Record<string, ModelStats>;
}

export interface ProviderStats {
  calls: number;
  tokens: number;
  cost: number;
  averageLatencyMs: number;
}

export interface ModelStats {
  calls: number;
  tokens: number;
  cost: number;
  averageLatencyMs: number;
}

export interface TimeRange {
  start: Date;
  end: Date;
}

// Pricing per 1M tokens (approximate, update as needed)
const PRICING: Record<string, { input: number; output: number }> = {
  "gpt-4o": { input: 2.5, output: 10 },
  "gpt-4o-mini": { input: 0.15, output: 0.6 },
  "gpt-4-turbo": { input: 10, output: 30 },
  "claude-3-5-sonnet": { input: 3, output: 15 },
  "claude-sonnet-4-5-20250929": { input: 3, output: 15 },
  "claude-3-opus": { input: 15, output: 75 },
  "claude-3-haiku": { input: 0.25, output: 1.25 },
  "gemini-1.5-pro": { input: 1.25, output: 5 },
  "gemini-1.5-flash": { input: 0.075, output: 0.3 },
};

/**
 * Calculate cost based on token usage and model.
 */
export function calculateCost(
  model: string,
  inputTokens: number,
  outputTokens: number
): number {
  // Find matching pricing (partial match)
  const pricing = Object.entries(PRICING).find(([key]) =>
    model.toLowerCase().includes(key.toLowerCase())
  )?.[1];

  if (!pricing) {
    // Default pricing if model not found
    return ((inputTokens + outputTokens) / 1_000_000) * 5; // $5 per 1M tokens default
  }

  const inputCost = (inputTokens / 1_000_000) * pricing.input;
  const outputCost = (outputTokens / 1_000_000) * pricing.output;
  return inputCost + outputCost;
}

/**
 * In-memory usage tracker.
 * For production, this should be backed by SQLite or another persistent store.
 */
export class UsageTracker {
  private records: UsageRecord[] = [];
  private maxRecords: number;

  constructor(options: { maxRecords?: number } = {}) {
    this.maxRecords = options.maxRecords ?? 10000;
  }

  /**
   * Track an API call.
   */
  trackAPICall(record: Omit<UsageRecord, "id" | "cost">): UsageRecord {
    const cost = calculateCost(record.model, record.inputTokens, record.outputTokens);
    const fullRecord: UsageRecord = {
      ...record,
      id: crypto.randomUUID(),
      cost,
    };

    this.records.push(fullRecord);

    // Trim old records if over limit
    if (this.records.length > this.maxRecords) {
      this.records = this.records.slice(-this.maxRecords);
    }

    return fullRecord;
  }

  /**
   * Get usage statistics for a time range.
   */
  getUsageStats(timeRange?: TimeRange): UsageStats {
    let filtered = this.records;

    if (timeRange) {
      filtered = this.records.filter(
        (r) => r.timestamp >= timeRange.start && r.timestamp <= timeRange.end
      );
    }

    const stats: UsageStats = {
      totalCalls: filtered.length,
      successfulCalls: filtered.filter((r) => r.success).length,
      failedCalls: filtered.filter((r) => !r.success).length,
      totalTokens: 0,
      totalInputTokens: 0,
      totalOutputTokens: 0,
      totalCost: 0,
      averageLatencyMs: 0,
      byProvider: {},
      byModel: {},
    };

    if (filtered.length === 0) return stats;

    let totalLatency = 0;

    for (const record of filtered) {
      stats.totalTokens += record.totalTokens;
      stats.totalInputTokens += record.inputTokens;
      stats.totalOutputTokens += record.outputTokens;
      stats.totalCost += record.cost;
      totalLatency += record.latencyMs;

      // By provider
      if (!stats.byProvider[record.provider]) {
        stats.byProvider[record.provider] = { calls: 0, tokens: 0, cost: 0, averageLatencyMs: 0 };
      }
      stats.byProvider[record.provider].calls++;
      stats.byProvider[record.provider].tokens += record.totalTokens;
      stats.byProvider[record.provider].cost += record.cost;
    }

    stats.averageLatencyMs = totalLatency / filtered.length;
    return stats;
  }
}

// Singleton instance
let _tracker: UsageTracker | null = null;

export function getUsageTracker(): UsageTracker {
  if (!_tracker) {
    _tracker = new UsageTracker();
  }
  return _tracker;
}

