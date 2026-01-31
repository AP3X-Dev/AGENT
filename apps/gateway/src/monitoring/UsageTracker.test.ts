/**
 * Tests for UsageTracker.
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  UsageTracker,
  calculateCost,
  getUsageTracker,
  type UsageRecord,
} from "./UsageTracker.js";

describe("calculateCost", () => {
  it("should calculate cost for known model", () => {
    // gpt-4o: input $2.5/1M, output $10/1M
    const cost = calculateCost("gpt-4o", 1000, 500);
    // (1000/1M * 2.5) + (500/1M * 10) = 0.0025 + 0.005 = 0.0075
    expect(cost).toBeCloseTo(0.0075, 6);
  });

  it("should calculate cost for claude model", () => {
    // claude-3-5-sonnet: input $3/1M, output $15/1M
    const cost = calculateCost("claude-3-5-sonnet-20241022", 10000, 5000);
    // (10000/1M * 3) + (5000/1M * 15) = 0.03 + 0.075 = 0.105
    expect(cost).toBeCloseTo(0.105, 6);
  });

  it("should use default pricing for unknown model", () => {
    // Default: $5/1M for all tokens
    const cost = calculateCost("unknown-model", 1000, 1000);
    // (2000/1M * 5) = 0.01
    expect(cost).toBeCloseTo(0.01, 6);
  });

  it("should handle zero tokens", () => {
    const cost = calculateCost("gpt-4o", 0, 0);
    expect(cost).toBe(0);
  });

  it("should handle large token counts", () => {
    const cost = calculateCost("gpt-4o", 1_000_000, 500_000);
    // (1M/1M * 2.5) + (500K/1M * 10) = 2.5 + 5 = 7.5
    expect(cost).toBeCloseTo(7.5, 2);
  });
});

describe("UsageTracker", () => {
  let tracker: UsageTracker;

  beforeEach(() => {
    tracker = new UsageTracker({ maxRecords: 100 });
  });

  describe("trackAPICall", () => {
    it("should track API call and return record with id and cost", () => {
      const record = tracker.trackAPICall({
        timestamp: new Date(),
        provider: "openai",
        model: "gpt-4o",
        sessionId: "session-1",
        inputTokens: 1000,
        outputTokens: 500,
        totalTokens: 1500,
        latencyMs: 250,
        success: true,
      });

      expect(record.id).toBeDefined();
      expect(record.cost).toBeGreaterThan(0);
      expect(record.provider).toBe("openai");
      expect(record.model).toBe("gpt-4o");
    });

    it("should trim old records when exceeding max", () => {
      const smallTracker = new UsageTracker({ maxRecords: 3 });

      for (let i = 0; i < 5; i++) {
        smallTracker.trackAPICall({
          timestamp: new Date(),
          provider: "openai",
          model: "gpt-4o",
          sessionId: `session-${i}`,
          inputTokens: 100,
          outputTokens: 50,
          totalTokens: 150,
          latencyMs: 100,
          success: true,
        });
      }

      const stats = smallTracker.getUsageStats();
      expect(stats.totalCalls).toBe(3);
    });

    it("should track failed calls", () => {
      tracker.trackAPICall({
        timestamp: new Date(),
        provider: "openai",
        model: "gpt-4o",
        sessionId: "session-1",
        inputTokens: 100,
        outputTokens: 0,
        totalTokens: 100,
        latencyMs: 50,
        success: false,
        errorCode: "rate_limit",
      });

      const stats = tracker.getUsageStats();
      expect(stats.failedCalls).toBe(1);
      expect(stats.successfulCalls).toBe(0);
    });
  });

  describe("getUsageStats", () => {
    it("should return empty stats when no records", () => {
      const stats = tracker.getUsageStats();
      expect(stats.totalCalls).toBe(0);
      expect(stats.totalTokens).toBe(0);
      expect(stats.totalCost).toBe(0);
    });

    it("should aggregate stats correctly", () => {
      tracker.trackAPICall({
        timestamp: new Date(),
        provider: "openai",
        model: "gpt-4o",
        sessionId: "session-1",
        inputTokens: 1000,
        outputTokens: 500,
        totalTokens: 1500,
        latencyMs: 200,
        success: true,
      });

      tracker.trackAPICall({
        timestamp: new Date(),
        provider: "anthropic",
        model: "claude-3-5-sonnet",
        sessionId: "session-2",
        inputTokens: 2000,
        outputTokens: 1000,
        totalTokens: 3000,
        latencyMs: 300,
        success: true,
      });

      const stats = tracker.getUsageStats();
      expect(stats.totalCalls).toBe(2);
      expect(stats.successfulCalls).toBe(2);
      expect(stats.totalTokens).toBe(4500);
      expect(stats.totalInputTokens).toBe(3000);
      expect(stats.totalOutputTokens).toBe(1500);
      expect(stats.averageLatencyMs).toBe(250);
    });

    it("should filter by time range", () => {
      const now = new Date();
      const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);
      const tomorrow = new Date(now.getTime() + 24 * 60 * 60 * 1000);

      // Add record for yesterday
      tracker.trackAPICall({
        timestamp: yesterday,
        provider: "openai",
        model: "gpt-4o",
        sessionId: "session-1",
        inputTokens: 1000,
        outputTokens: 500,
        totalTokens: 1500,
        latencyMs: 200,
        success: true,
      });

      // Add record for today
      tracker.trackAPICall({
        timestamp: now,
        provider: "openai",
        model: "gpt-4o",
        sessionId: "session-2",
        inputTokens: 2000,
        outputTokens: 1000,
        totalTokens: 3000,
        latencyMs: 300,
        success: true,
      });

      // Filter to only today's records
      const stats = tracker.getUsageStats({
        start: new Date(now.getTime() - 60 * 60 * 1000), // 1 hour ago
        end: tomorrow,
      });

      expect(stats.totalCalls).toBe(1);
      expect(stats.totalTokens).toBe(3000);
    });

    it("should aggregate byProvider stats", () => {
      tracker.trackAPICall({
        timestamp: new Date(),
        provider: "openai",
        model: "gpt-4o",
        sessionId: "session-1",
        inputTokens: 1000,
        outputTokens: 500,
        totalTokens: 1500,
        latencyMs: 200,
        success: true,
      });

      const stats = tracker.getUsageStats();
      expect(stats.byProvider["openai"]).toBeDefined();
      expect(stats.byProvider["openai"].calls).toBe(1);
      expect(stats.byProvider["openai"].tokens).toBe(1500);
    });
  });
});

describe("getUsageTracker", () => {
  it("should return singleton instance", () => {
    const tracker1 = getUsageTracker();
    const tracker2 = getUsageTracker();
    expect(tracker1).toBe(tracker2);
  });
});

