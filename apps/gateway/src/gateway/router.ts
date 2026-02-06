/**
 * Router for AG3NT Gateway.
 *
 * Routes messages from channels to the agent worker.
 * Handles session management, DM pairing security, and tool approval.
 */

import type { Config } from "../config/schema.js";
import type { ChannelMessage, ChannelResponse } from "../channels/types.js";
import { SessionManager } from "../session/SessionManager.js";
import { getUsageTracker } from "../monitoring/index.js";
import { gatewayLogs } from "../logs/index.js";
import type { AgentRouter, RoutingDecision } from "../routing/AgentRouter.js";
import type { QueueManager, QueueItem } from "../routing/MessageQueue.js";
import type { ActivationChecker } from "../channels/ActivationChecker.js";
import type { DirectiveManager } from "../directives/DirectiveManager.js";
import {
  WORKER_URL,
  WORKER_FETCH_TIMEOUT_MS,
  PENDING_APPROVAL_TTL_MS,
  APPROVAL_CLEANUP_INTERVAL_MS,
  WORKER_AUTH_TOKEN,
  CONTEXT_ENGINEERING_DEFAULT,
} from "../config/constants.js";
import {
  AgentConnection,
  isWebSocketAvailable,
  getAgentConnection,
  closeAgentConnection,
  type TurnResponse as WsTurnResponse,
} from "../agent/AgentConnection.js";
import { forwardStreamEvent, type StreamMessage } from "../routes/stream.js";

// =============================================================================
// WebSocket Connection Management
// =============================================================================

/** Feature flag for WebSocket mode (enabled by default, set AG3NT_USE_WEBSOCKET=false to disable) */
const USE_WEBSOCKET = process.env.AG3NT_USE_WEBSOCKET !== "false";

/** Singleton WebSocket connection to agent worker */
let _agentConnection: AgentConnection | null = null;

/**
 * Get or create the WebSocket connection to the agent worker.
 */
async function getOrCreateAgentConnection(): Promise<AgentConnection> {
  if (!_agentConnection) {
    _agentConnection = new AgentConnection(WORKER_URL, WORKER_AUTH_TOKEN);

    // Forward stream events to SSE subscribers
    _agentConnection.on("stream", (msg: StreamMessage) => {
      forwardStreamEvent(msg);
    });

    await _agentConnection.connect();
    gatewayLogs.info("Router", "WebSocket connection established to agent worker");
  }
  return _agentConnection;
}

// =============================================================================
// Audit Logging
// =============================================================================

/**
 * Log approval-related events for security audit.
 */
function auditLog(event: {
  type: "approval_requested" | "approval_granted" | "approval_denied" | "approval_timeout";
  sessionId: string;
  userId?: string;
  actions?: Array<{ tool_name: string; args: Record<string, unknown> }>;
  decision?: "approve" | "reject";
  timestamp?: Date;
}) {
  const timestamp = event.timestamp ?? new Date();
  const logEntry = {
    ...event,
    timestamp: timestamp.toISOString(),
  };
  // Log to console with [AUDIT] prefix for easy filtering
  console.log("[AUDIT]", JSON.stringify(logEntry));
}

// =============================================================================
// Types
// =============================================================================

export interface TurnRequest {
  session_id: string;
  text: string;
  metadata?: Record<string, unknown>;
}

export interface InterruptInfo {
  interrupt_id: string;
  pending_actions: Array<{
    tool_name: string;
    args: Record<string, unknown>;
    description: string;
  }>;
  action_count: number;
}

export interface TurnResponse {
  session_id: string;
  text: string;
  events: Array<Record<string, unknown>>;
  interrupt?: InterruptInfo | null;
}

export interface ResumeRequest {
  session_id: string;
  decisions: Array<{ type: "approve" | "reject" }>;
}

export interface ResumeResponse {
  session_id: string;
  text: string;
  events: Array<Record<string, unknown>>;
  interrupt?: InterruptInfo | null;
}

export interface RouterResult {
  ok: boolean;
  session_id?: string;
  text?: string;
  events?: Array<Record<string, unknown>>;
  error?: string;
  pairingRequired?: boolean;
  pairingCode?: string;
  approvalPending?: boolean;
}

// =============================================================================
// Retry Logic with Exponential Backoff
// =============================================================================

interface RetryConfig {
  maxAttempts: number;
  baseDelayMs: number;
  maxDelayMs: number;
  jitterPct: number;
}

const DEFAULT_RETRY_CONFIG: RetryConfig = {
  maxAttempts: 3,
  baseDelayMs: 50,    // Reduced from 100ms for faster retry
  maxDelayMs: 4000,   // Reduced from 8000ms for faster recovery
  jitterPct: 0.2,     // Increased jitter to reduce thundering herd
};

/**
 * Retry a function with exponential backoff and jitter.
 * Retries on network errors and 5xx responses, but not 4xx client errors.
 */
async function callWithRetry<T>(
  fn: () => Promise<Response>,
  parseResult: (response: Response) => Promise<T>,
  context: { sessionId: string; operation: string },
  config: RetryConfig = DEFAULT_RETRY_CONFIG
): Promise<T> {
  let lastError: Error | null = null;

  for (let attempt = 0; attempt < config.maxAttempts; attempt++) {
    try {
      const response = await fn();

      // Don't retry client errors (4xx)
      if (response.status >= 400 && response.status < 500) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }

      // Retry server errors (5xx)
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }

      return await parseResult(response);
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));

      // Don't retry if it's a 4xx error (already thrown above with full message)
      if (lastError.message.startsWith("HTTP 4")) {
        throw lastError;
      }

      const isLastAttempt = attempt >= config.maxAttempts - 1;
      if (!isLastAttempt) {
        // Calculate delay with exponential backoff
        const delay = Math.min(
          config.maxDelayMs,
          config.baseDelayMs * Math.pow(2, attempt)
        );
        // Add jitter (±jitterPct)
        const jitter = delay * config.jitterPct * (Math.random() * 2 - 1);
        const finalDelay = Math.round(delay + jitter);

        gatewayLogs.warn(
          "Router",
          `${context.operation} failed (attempt ${attempt + 1}/${config.maxAttempts}), retrying in ${finalDelay}ms`,
          { session_id: context.sessionId, error: lastError.message }
        );

        await new Promise((r) => setTimeout(r, finalDelay));
      }
    }
  }

  throw lastError;
}

// =============================================================================
// Pending Approvals Store
// =============================================================================

/**
 * In-memory store for pending approvals per session.
 * Maps session_id -> { info, createdAt } with TTL-based expiry.
 */
const pendingApprovals = new Map<
  string,
  { info: InterruptInfo; createdAt: number }
>();

/** Periodically purge stale pending approvals to prevent memory leaks. */
const _approvalCleanupTimer = setInterval(() => {
  const now = Date.now();
  for (const [sessionId, entry] of pendingApprovals) {
    if (now - entry.createdAt > PENDING_APPROVAL_TTL_MS) {
      pendingApprovals.delete(sessionId);
      auditLog({ type: "approval_timeout", sessionId });
    }
  }
}, APPROVAL_CLEANUP_INTERVAL_MS);
// Allow the process to exit even if the timer is still running
if (typeof _approvalCleanupTimer === "object" && "unref" in _approvalCleanupTimer) {
  _approvalCleanupTimer.unref();
}

// =============================================================================
// Worker API Calls
// =============================================================================

/**
 * Call worker turn via WebSocket (low latency).
 */
async function callWorkerTurnWs(req: TurnRequest): Promise<TurnResponse> {
  const startTime = Date.now();
  const tracker = getUsageTracker();

  const textPreview = req.text.length > 80 ? req.text.slice(0, 80) + "..." : req.text;
  gatewayLogs.debug("Router", `→ [WS] Sending to worker: "${textPreview}"`, {
    session_id: req.session_id,
    text_length: req.text.length,
  });

  try {
    const conn = await getOrCreateAgentConnection();
    const result = await conn.sendTurn(req);

    const latencyMs = Date.now() - startTime;

    // Track successful API call
    const usage = result.usage;
    tracker.trackAPICall({
      timestamp: new Date(),
      provider: usage?.provider ?? "anthropic",
      model: usage?.model ?? "claude-sonnet-4-5-20250929",
      sessionId: req.session_id,
      inputTokens: usage?.input_tokens ?? 0,
      outputTokens: usage?.output_tokens ?? 0,
      totalTokens: (usage?.input_tokens ?? 0) + (usage?.output_tokens ?? 0),
      latencyMs,
      success: true,
    });

    const responsePreview = result.text.length > 100 ? result.text.slice(0, 100) + "..." : result.text;
    gatewayLogs.info("Router", `← [WS] Response received (${latencyMs}ms)`, {
      latency_ms: latencyMs,
      response_length: result.text.length,
      events_count: result.events?.length ?? 0,
      has_interrupt: !!result.interrupt,
      tokens_in: usage?.input_tokens,
      tokens_out: usage?.output_tokens,
      model: usage?.model,
      transport: "websocket",
    });
    gatewayLogs.debug("Router", `Response preview: "${responsePreview}"`);

    return result as TurnResponse;
  } catch (err) {
    const latencyMs = Date.now() - startTime;
    gatewayLogs.warn("Router", `[WS] Call failed after ${latencyMs}ms, will fallback to HTTP: ${err instanceof Error ? err.message : String(err)}`);
    throw err;
  }
}

/**
 * Call worker turn via HTTP (fallback).
 */
async function callWorkerTurnHttp(req: TurnRequest): Promise<TurnResponse> {
  const startTime = Date.now();
  const tracker = getUsageTracker();

  // Log the request
  const textPreview = req.text.length > 80 ? req.text.slice(0, 80) + "..." : req.text;
  gatewayLogs.debug("Router", `→ [HTTP] Sending to worker: "${textPreview}"`, {
    session_id: req.session_id,
    text_length: req.text.length,
  });

  try {
    const result = await callWithRetry(
      // Fetch function
      () =>
        fetch(`${WORKER_URL}/turn`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Connection": "keep-alive",  // Enable HTTP keep-alive for connection reuse
            ...(WORKER_AUTH_TOKEN ? { "X-Gateway-Token": WORKER_AUTH_TOKEN } : {}),
          },
          body: JSON.stringify(req),
          signal: AbortSignal.timeout(WORKER_FETCH_TIMEOUT_MS),
        }),
      // Parse result function
      async (response) => response.json() as Promise<TurnResponse>,
      // Context for logging
      { sessionId: req.session_id, operation: "Worker turn" }
    );

    const latencyMs = Date.now() - startTime;

    // Track successful API call with usage info from response
    const usage = (result as TurnResponse & { usage?: { input_tokens?: number; output_tokens?: number; model?: string; provider?: string } }).usage;
    tracker.trackAPICall({
      timestamp: new Date(),
      provider: usage?.provider ?? "anthropic",
      model: usage?.model ?? "claude-sonnet-4-5-20250929",
      sessionId: req.session_id,
      inputTokens: usage?.input_tokens ?? 0,
      outputTokens: usage?.output_tokens ?? 0,
      totalTokens: (usage?.input_tokens ?? 0) + (usage?.output_tokens ?? 0),
      latencyMs,
      success: true,
    });

    // Log response summary
    const responsePreview = result.text.length > 100 ? result.text.slice(0, 100) + "..." : result.text;
    gatewayLogs.info("Router", `← [HTTP] Response received (${latencyMs}ms)`, {
      latency_ms: latencyMs,
      response_length: result.text.length,
      events_count: result.events?.length ?? 0,
      has_interrupt: !!result.interrupt,
      tokens_in: usage?.input_tokens,
      tokens_out: usage?.output_tokens,
      model: usage?.model,
      transport: "http",
    });
    gatewayLogs.debug("Router", `Response preview: "${responsePreview}"`);

    return result;
  } catch (err) {
    const latencyMs = Date.now() - startTime;
    gatewayLogs.error("Router", `[HTTP] Worker call failed after ${latencyMs}ms: ${err instanceof Error ? err.message : String(err)}`);
    // Track error case
    tracker.trackAPICall({
      timestamp: new Date(),
      provider: "agent-worker",
      model: "unknown",
      sessionId: req.session_id,
      inputTokens: 0,
      outputTokens: 0,
      totalTokens: 0,
      latencyMs,
      success: false,
      errorCode: err instanceof Error ? err.message.slice(0, 50) : "UNKNOWN",
    });
    throw err;
  }
}

/**
 * Call worker turn - uses WebSocket if available/enabled, falls back to HTTP.
 */
async function callWorkerTurn(req: TurnRequest): Promise<TurnResponse> {
  // Try WebSocket first if enabled
  if (USE_WEBSOCKET) {
    try {
      return await callWorkerTurnWs(req);
    } catch {
      // Fall through to HTTP
      gatewayLogs.info("Router", "Falling back to HTTP transport");
    }
  }

  return callWorkerTurnHttp(req);
}

/**
 * Call worker resume via WebSocket (low latency).
 */
async function callWorkerResumeWs(req: ResumeRequest): Promise<ResumeResponse> {
  const startTime = Date.now();
  const tracker = getUsageTracker();

  const decisions = req.decisions.map(d => d.type).join(", ");
  gatewayLogs.debug("Router", `→ [WS] Resuming with decisions: [${decisions}]`, {
    session_id: req.session_id,
    decisions_count: req.decisions.length,
  });

  try {
    const conn = await getOrCreateAgentConnection();
    const result = await conn.sendResume(req);

    const latencyMs = Date.now() - startTime;

    const usage = result.usage;
    tracker.trackAPICall({
      timestamp: new Date(),
      provider: usage?.provider ?? "anthropic",
      model: usage?.model ?? "claude-sonnet-4-5-20250929",
      sessionId: req.session_id,
      inputTokens: usage?.input_tokens ?? 0,
      outputTokens: usage?.output_tokens ?? 0,
      totalTokens: (usage?.input_tokens ?? 0) + (usage?.output_tokens ?? 0),
      latencyMs,
      success: true,
    });

    gatewayLogs.info("Router", `← [WS] Resume completed (${latencyMs}ms)`, {
      latency_ms: latencyMs,
      response_length: result.text.length,
      has_interrupt: !!result.interrupt,
      transport: "websocket",
    });

    return result as ResumeResponse;
  } catch (err) {
    const latencyMs = Date.now() - startTime;
    gatewayLogs.warn("Router", `[WS] Resume failed after ${latencyMs}ms, will fallback to HTTP: ${err instanceof Error ? err.message : String(err)}`);
    throw err;
  }
}

/**
 * Call worker resume via HTTP (fallback).
 */
async function callWorkerResumeHttp(req: ResumeRequest): Promise<ResumeResponse> {
  const startTime = Date.now();
  const tracker = getUsageTracker();

  const decisions = req.decisions.map(d => d.type).join(", ");
  gatewayLogs.debug("Router", `→ [HTTP] Resuming with decisions: [${decisions}]`, {
    session_id: req.session_id,
    decisions_count: req.decisions.length,
  });

  try {
    const result = await callWithRetry(
      // Fetch function
      () =>
        fetch(`${WORKER_URL}/resume`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Connection": "keep-alive",  // Enable HTTP keep-alive for connection reuse
            ...(WORKER_AUTH_TOKEN ? { "X-Gateway-Token": WORKER_AUTH_TOKEN } : {}),
          },
          body: JSON.stringify(req),
          signal: AbortSignal.timeout(WORKER_FETCH_TIMEOUT_MS),
        }),
      // Parse result function
      async (response) => response.json() as Promise<ResumeResponse>,
      // Context for logging
      { sessionId: req.session_id, operation: "Worker resume" }
    );

    const latencyMs = Date.now() - startTime;

    // Track successful resume call
    const usage = (result as ResumeResponse & { usage?: { input_tokens?: number; output_tokens?: number; model?: string; provider?: string } }).usage;
    tracker.trackAPICall({
      timestamp: new Date(),
      provider: usage?.provider ?? "anthropic",
      model: usage?.model ?? "claude-sonnet-4-5-20250929",
      sessionId: req.session_id,
      inputTokens: usage?.input_tokens ?? 0,
      outputTokens: usage?.output_tokens ?? 0,
      totalTokens: (usage?.input_tokens ?? 0) + (usage?.output_tokens ?? 0),
      latencyMs,
      success: true,
    });

    gatewayLogs.info("Router", `← [HTTP] Resume completed (${latencyMs}ms)`, {
      latency_ms: latencyMs,
      response_length: result.text.length,
      has_interrupt: !!result.interrupt,
      transport: "http",
    });

    return result;
  } catch (err) {
    const latencyMs = Date.now() - startTime;
    gatewayLogs.error("Router", `Resume call failed after ${latencyMs}ms: ${err instanceof Error ? err.message : String(err)}`);
    tracker.trackAPICall({
      timestamp: new Date(),
      provider: "agent-worker",
      model: "unknown",
      sessionId: req.session_id,
      inputTokens: 0,
      outputTokens: 0,
      totalTokens: 0,
      latencyMs,
      success: false,
      errorCode: err instanceof Error ? err.message.slice(0, 50) : "UNKNOWN",
    });
    throw err;
  }
}

/**
 * Call worker resume - uses WebSocket if available/enabled, falls back to HTTP.
 */
async function callWorkerResume(req: ResumeRequest): Promise<ResumeResponse> {
  // Try WebSocket first if enabled
  if (USE_WEBSOCKET) {
    try {
      return await callWorkerResumeWs(req);
    } catch {
      // Fall through to HTTP
      gatewayLogs.info("Router", "Falling back to HTTP transport for resume");
    }
  }

  return callWorkerResumeHttp(req);
}

// =============================================================================
// Approval Helpers
// =============================================================================

/**
 * Check if message is an approval/rejection response.
 */
function parseApprovalResponse(
  text: string
): "approve" | "reject" | null {
  const lower = text.toLowerCase().trim();
  if (lower === "approve" || lower === "yes" || lower === "y" || lower === "ok") {
    return "approve";
  }
  if (lower === "reject" || lower === "no" || lower === "n" || lower === "cancel") {
    return "reject";
  }
  return null;
}

export interface RouterDependencies {
  sessionManager: SessionManager;
  agentRouter?: AgentRouter;
  queueManager?: QueueManager;
  activationChecker?: ActivationChecker;
  directiveManager?: DirectiveManager;
}

export function createRouter(config: Config, deps: RouterDependencies) {
  const { sessionManager, agentRouter, queueManager, activationChecker, directiveManager } = deps;

  // Wire queue manager to process items through callWorkerTurn
  if (queueManager) {
    queueManager.setProcessHandler(async (item: QueueItem) => {
      return processWorkerTurn(item.message, item.session.id, item.routingDecision);
    });
    queueManager.start();
  }

  /**
   * Process a worker turn call with optional directive injection and routing metadata.
   */
  async function processWorkerTurn(
    message: ChannelMessage,
    sessionId: string,
    routingDecision?: RoutingDecision,
  ): Promise<ChannelResponse> {
    // Build directive prefix if available
    let directivePrefix = '';
    if (directiveManager) {
      directivePrefix = directiveManager.buildPromptPrefix(sessionId);
    }

    const turnReq: TurnRequest = {
      session_id: sessionId,
      text: message.text,
      metadata: {
        channelType: message.channelType,
        channelId: message.channelId,
        chatId: message.chatId,
        userId: message.userId,
        userName: message.userName,
        timestamp: message.timestamp.toISOString(),
        ...(directivePrefix ? { directives: directivePrefix } : {}),
        ...(routingDecision ? { routing: { agent: routingDecision.agentName, reason: routingDecision.reason } } : {}),
        // Context engineering defaults (can be overridden per-request via message.metadata)
        ...(CONTEXT_ENGINEERING_DEFAULT ? { plan_mode: true, context_engineering: true } : {}),
        ...message.metadata,
      },
    };

    const result = await callWorkerTurn(turnReq);

    // Check if approval is required
    if (result.interrupt) {
      return handleInterrupt(sessionId, result.interrupt, message.userId);
    }

    return {
      text: result.text,
      metadata: {
        events: result.events,
        sessionId: result.session_id,
      },
    };
  }

  /**
   * Handle interrupt from worker response.
   * Stores pending approval and returns appropriate response.
   */
  function handleInterrupt(
    sessionId: string,
    interrupt: InterruptInfo,
    userId?: string
  ): ChannelResponse {
    // Store the pending approval with timestamp for TTL expiry
    const approvalKey = `${sessionId}:${interrupt.interrupt_id}`;
    pendingApprovals.set(approvalKey, { info: interrupt, createdAt: Date.now() });

    // Audit log the approval request
    auditLog({
      type: "approval_requested",
      sessionId,
      userId,
      actions: interrupt.pending_actions.map((a) => ({
        tool_name: a.tool_name,
        args: a.args,
      })),
    });

    // Return approval request message (already formatted by worker)
    return {
      text: `⏸️ **Approval Required**\n\nI need your permission to proceed with:\n\n${interrupt.pending_actions.map((a) => a.description).join("\n\n")}\n\nReply with **approve** or **reject**.`,
      metadata: {
        approvalPending: true,
        sessionId,
        pendingActions: interrupt.pending_actions,
      },
    };
  }

  return {
    /**
     * Handle a message from a channel.
     * Checks pairing status, pending approvals, and routes to agent worker.
     */
    async handleChannelMessage(
      message: ChannelMessage
    ): Promise<ChannelResponse> {
      const startTime = Date.now();
      const textPreview = message.text.length > 60 ? message.text.slice(0, 60) + "..." : message.text;

      gatewayLogs.info("Router", `📨 Incoming message from ${message.channelType}/${message.userId || "anonymous"}`, {
        channel: message.channelType,
        user: message.userId,
        text_length: message.text.length,
      });
      gatewayLogs.debug("Router", `Message: "${textPreview}"`);

      // Get or create session
      const session = sessionManager.getOrCreateSession(
        message.channelType,
        message.channelId,
        message.chatId,
        message.userId,
        message.userName
      );
      const isNewSession = session.createdAt.getTime() === session.lastActivityAt.getTime();
      gatewayLogs.debug("Router", `Session: ${session.id.slice(0, 24)}... (new: ${isNewSession})`);

      // YOLO mode: skip pairing check
      if (config.security?.yoloMode) {
        session.paired = true;
      }

      // Check if session is paired (for DM pairing security)
      if (!sessionManager.isSessionPaired(session.id)) {
        // Generate pairing code if not already pending
        const code =
          session.pairingCode ?? sessionManager.generatePairingCode(session.id);
        gatewayLogs.info("Router", `🔒 Pairing required for session ${session.id.slice(0, 16)}...`, { code });

        return {
          text: `🔒 I don't recognize you yet. To chat with me, please have the owner approve this pairing code:\n\n**${code}**\n\nOnce approved, send your message again.`,
          metadata: {
            pairingRequired: true,
            pairingCode: code,
            sessionId: session.id,
          },
        };
      }

      // Check if there's a pending approval for this session
      // Find any pending approval for this session (keyed by session:interruptId)
      let pendingApproval: InterruptInfo | undefined;
      let pendingApprovalKey: string | undefined;
      for (const [key, entry] of pendingApprovals) {
        if (key.startsWith(session.id + ':')) {
          pendingApproval = entry.info;
          pendingApprovalKey = key;
          break;
        }
      }
      if (pendingApproval) {
        const decision = parseApprovalResponse(message.text);
        if (decision) {
          gatewayLogs.info("Router", `✅ Approval decision: ${decision}`, {
            session_id: session.id,
            actions_count: pendingApproval.pending_actions.length,
          });

          // Clear the pending approval
          if (pendingApprovalKey) pendingApprovals.delete(pendingApprovalKey);

          // Audit log the decision
          auditLog({
            type: decision === "approve" ? "approval_granted" : "approval_denied",
            sessionId: session.id,
            userId: message.userId,
            decision,
            actions: pendingApproval.pending_actions.map((a) => ({
              tool_name: a.tool_name,
              args: a.args,
            })),
          });

          // Build decisions array (one per pending action)
          const decisions = pendingApproval.pending_actions.map(() => ({
            type: decision,
          }));

          try {
            gatewayLogs.debug("Router", `Resuming interrupted turn...`);
            // Resume the interrupted turn
            const result = await callWorkerResume({
              session_id: session.id,
              decisions,
            });

            // Check if another approval is needed
            if (result.interrupt) {
              gatewayLogs.info("Router", `⏸️ Another approval needed`);
              return handleInterrupt(session.id, result.interrupt, message.userId);
            }

            const latency = Date.now() - startTime;
            gatewayLogs.info("Router", `📤 Response sent (${latency}ms total)`);
            return {
              text: result.text,
              metadata: {
                events: result.events,
                sessionId: result.session_id,
              },
            };
          } catch (err) {
            gatewayLogs.error("Router", `Resume failed: ${err instanceof Error ? err.message : String(err)}`);
            return {
              text: `⚠️ Error resuming: ${err instanceof Error ? err.message : String(err)}`,
              metadata: { error: true },
            };
          }
        } else {
          // User said something else while approval is pending
          gatewayLogs.debug("Router", `Awaiting approval decision (got: "${textPreview}")`);
          return {
            text: `⏸️ I'm waiting for your approval. Please reply with **approve** or **reject**.\n\nPending action(s):\n${pendingApproval.pending_actions.map((a) => a.description).join("\n\n")}`,
            metadata: {
              approvalPending: true,
              sessionId: session.id,
            },
          };
        }
      }

      // Check activation mode for enhanced sessions
      const enhancedSession = sessionManager.getEnhancedSession(session.id);
      if (enhancedSession && activationChecker) {
        const activation = activationChecker.shouldActivate(message, enhancedSession);
        if (!activation.shouldActivate) {
          gatewayLogs.debug("Router", `Skipping message (activation: ${activation.reason})`, {
            session_id: session.id,
            mode: enhancedSession.activationMode,
          });
          // Return empty to signal no response should be sent
          return { text: '', metadata: { skipped: true, reason: activation.reason } };
        }
      }

      // Get routing decision
      let routingDecision: RoutingDecision | undefined;
      if (agentRouter && enhancedSession) {
        try {
          routingDecision = await agentRouter.route(message, enhancedSession);
          gatewayLogs.debug("Router", `Routing decision: ${routingDecision.reason}`, {
            agent: routingDecision.agentName,
            priority: routingDecision.priority,
          });
        } catch (err) {
          gatewayLogs.warn("Router", `Routing failed, using default: ${err instanceof Error ? err.message : String(err)}`);
        }
      }

      // Submit to queue or process directly
      gatewayLogs.info("Router", `🤖 Routing to agent worker...`);
      try {
        let response: ChannelResponse;

        if (queueManager && enhancedSession) {
          response = await queueManager.submit(
            message,
            enhancedSession,
            routingDecision || { agentName: 'main', workerUrl: WORKER_URL, reason: 'default', priority: 5 },
          );
        } else {
          response = await processWorkerTurn(message, session.id, routingDecision);
        }

        const latency = Date.now() - startTime;
        gatewayLogs.info("Router", `📤 Response sent (${latency}ms total)`, {
          response_length: response.text.length,
        });
        return response;
      } catch (err) {
        const latency = Date.now() - startTime;
        gatewayLogs.error("Router", `❌ Request failed after ${latency}ms: ${err instanceof Error ? err.message : String(err)}`);
        return {
          text: `⚠️ Sorry, I encountered an error: ${err instanceof Error ? err.message : String(err)}`,
          metadata: { error: true },
        };
      }
    },

    /**
     * Handle a WebSocket message (legacy format).
     * Kept for backwards compatibility with existing CLI.
     */
    async handleWsMessage(msg: unknown): Promise<RouterResult> {
      // Route inbound messages to the agent worker
      // Expected message format: { session_id, text, metadata? }
      if (!msg || typeof msg !== "object") {
        return { ok: false, error: "Invalid message format" };
      }

      const msgObj = msg as Record<string, unknown>;
      const sessionId =
        (msgObj.session_id as string) ||
        (msgObj.sessionId as string) ||
        `cli:local:${crypto.randomUUID()}`;
      const text =
        (msgObj.text as string) || (msgObj.message as string) || "";

      if (!text) {
        return { ok: false, error: "Missing text field" };
      }

      // For legacy WebSocket messages, create a ChannelMessage
      const channelMessage: ChannelMessage = {
        id: crypto.randomUUID(),
        channelType: "cli",
        channelId: "local",
        chatId: sessionId.includes(":") ? sessionId.split(":")[2] : sessionId,
        userId: "local-user",
        text,
        timestamp: new Date(),
        metadata: msgObj.metadata as Record<string, unknown>,
      };

      const response = await this.handleChannelMessage(channelMessage);

      // Check if pairing is required
      if (response.metadata?.pairingRequired) {
        return {
          ok: false,
          pairingRequired: true,
          pairingCode: response.metadata.pairingCode as string,
          text: response.text,
          session_id: sessionId,
        };
      }

      // Check if approval is pending
      if (response.metadata?.approvalPending) {
        return {
          ok: true,
          approvalPending: true,
          text: response.text,
          session_id: sessionId,
        };
      }

      return {
        ok: true,
        session_id: sessionId,
        text: response.text,
        events: (response.metadata?.events as Array<Record<string, unknown>>) || [],
      };
    },

    /**
     * Check if a session has a pending approval.
     */
    hasPendingApproval(sessionId: string): boolean {
      for (const key of pendingApprovals.keys()) {
        if (key.startsWith(sessionId + ':')) return true;
      }
      return false;
    },

    /**
     * Get pending approval info for a session.
     */
    getPendingApproval(sessionId: string): InterruptInfo | undefined {
      for (const [key, entry] of pendingApprovals) {
        if (key.startsWith(sessionId + ':')) return entry.info;
      }
      return undefined;
    },

    /**
     * Cancel a pending approval.
     */
    cancelPendingApproval(sessionId: string): boolean {
      let deleted = false;
      for (const key of pendingApprovals.keys()) {
        if (key.startsWith(sessionId + ':')) {
          pendingApprovals.delete(key);
          deleted = true;
        }
      }
      return deleted;
    },

    /**
     * Get the session manager for external use.
     */
    getSessionManager(): SessionManager {
      return sessionManager;
    },

    /**
     * Stop the router (graceful shutdown of queue manager and WebSocket).
     */
    stop(): void {
      if (queueManager) {
        queueManager.stop();
      }
      clearInterval(_approvalCleanupTimer);
      pendingApprovals.clear();

      // Close WebSocket connection to agent worker
      if (_agentConnection) {
        _agentConnection.close();
        _agentConnection = null;
        gatewayLogs.info("Router", "WebSocket connection to agent worker closed");
      }
    },
  };
}

export type Router = ReturnType<typeof createRouter>;
