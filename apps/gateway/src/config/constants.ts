/**
 * Shared constants for AG3NT Gateway.
 */

import { Agent as HttpAgent } from "node:http";

/** URL for the agent worker process. */
export const WORKER_URL =
  process.env.AG3NT_AGENT_URL || "http://127.0.0.1:18790";

/** Default fetch timeout for worker calls (30 seconds). */
export const WORKER_FETCH_TIMEOUT_MS = 30_000;

/** TTL for pending approvals before auto-expiry (10 minutes). */
export const PENDING_APPROVAL_TTL_MS = 10 * 60 * 1000;

/** Interval for cleaning up stale pending approvals (60 seconds). */
export const APPROVAL_CLEANUP_INTERVAL_MS = 60_000;

/** Shared secret for authenticating gateway-to-worker requests. */
export const WORKER_AUTH_TOKEN = process.env.AG3NT_GATEWAY_TOKEN || "";

/** Whether context engineering (PRP-style blueprints) is enabled by default. */
export const CONTEXT_ENGINEERING_DEFAULT =
  process.env.AG3NT_CONTEXT_ENGINEERING === "true";

// =============================================================================
// HTTP Connection Pooling (Latency Optimization)
// =============================================================================

/**
 * HTTP Agent with keep-alive for connection reuse.
 *
 * This eliminates TCP handshake overhead (5-15ms) on subsequent requests
 * by reusing existing connections to the worker.
 */
export const WORKER_HTTP_AGENT = new HttpAgent({
  keepAlive: true,
  keepAliveMsecs: 30_000,    // Send keep-alive probes every 30s
  maxSockets: 10,            // Max concurrent connections to worker
  maxFreeSockets: 5,         // Keep up to 5 idle connections ready
  timeout: WORKER_FETCH_TIMEOUT_MS,
});
