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

const WORKER_URL = "http://127.0.0.1:18790";

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
// Pending Approvals Store
// =============================================================================

/**
 * In-memory store for pending approvals per session.
 * Maps session_id -> InterruptInfo
 */
const pendingApprovals = new Map<string, InterruptInfo>();

// =============================================================================
// Worker API Calls
// =============================================================================

async function callWorkerTurn(req: TurnRequest): Promise<TurnResponse> {
  const startTime = Date.now();
  const tracker = getUsageTracker();

  // Log the request
  const textPreview = req.text.length > 80 ? req.text.slice(0, 80) + "..." : req.text;
  gatewayLogs.debug("Router", `→ Sending to worker: "${textPreview}"`, {
    session_id: req.session_id,
    text_length: req.text.length,
  });

  try {
    const response = await fetch(`${WORKER_URL}/turn`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(req),
    });

    if (!response.ok) {
      const errorText = await response.text();
      gatewayLogs.error("Router", `Worker error: HTTP ${response.status}`, {
        status: response.status,
        error: errorText.slice(0, 200),
      });
      // Track failed API call
      tracker.trackAPICall({
        timestamp: new Date(),
        provider: "agent-worker",
        model: "unknown",
        sessionId: req.session_id,
        inputTokens: 0,
        outputTokens: 0,
        totalTokens: 0,
        latencyMs: Date.now() - startTime,
        success: false,
        errorCode: `HTTP_${response.status}`,
      });
      throw new Error(`Worker returned ${response.status}: ${errorText}`);
    }

    const result = await response.json() as TurnResponse;
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
    gatewayLogs.info("Router", `← Response received (${latencyMs}ms)`, {
      latency_ms: latencyMs,
      response_length: result.text.length,
      events_count: result.events?.length ?? 0,
      has_interrupt: !!result.interrupt,
      tokens_in: usage?.input_tokens,
      tokens_out: usage?.output_tokens,
      model: usage?.model,
    });
    gatewayLogs.debug("Router", `Response preview: "${responsePreview}"`);

    return result;
  } catch (err) {
    const latencyMs = Date.now() - startTime;
    gatewayLogs.error("Router", `Worker call failed after ${latencyMs}ms: ${err instanceof Error ? err.message : String(err)}`);
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

async function callWorkerResume(req: ResumeRequest): Promise<ResumeResponse> {
  const startTime = Date.now();
  const tracker = getUsageTracker();

  const decisions = req.decisions.map(d => d.type).join(", ");
  gatewayLogs.debug("Router", `→ Resuming with decisions: [${decisions}]`, {
    session_id: req.session_id,
    decisions_count: req.decisions.length,
  });

  try {
    const response = await fetch(`${WORKER_URL}/resume`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(req),
    });

    if (!response.ok) {
      const errorText = await response.text();
      gatewayLogs.error("Router", `Resume error: HTTP ${response.status}`, {
        status: response.status,
        error: errorText.slice(0, 200),
      });
      tracker.trackAPICall({
        timestamp: new Date(),
        provider: "agent-worker",
        model: "unknown",
        sessionId: req.session_id,
        inputTokens: 0,
        outputTokens: 0,
        totalTokens: 0,
        latencyMs: Date.now() - startTime,
        success: false,
        errorCode: `HTTP_${response.status}`,
      });
      throw new Error(`Worker returned ${response.status}: ${errorText}`);
    }

    const result = await response.json() as ResumeResponse;
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

    gatewayLogs.info("Router", `← Resume completed (${latencyMs}ms)`, {
      latency_ms: latencyMs,
      response_length: result.text.length,
      has_interrupt: !!result.interrupt,
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
}

export function createRouter(config: Config, deps: RouterDependencies) {
  const { sessionManager } = deps;

  /**
   * Handle interrupt from worker response.
   * Stores pending approval and returns appropriate response.
   */
  function handleInterrupt(
    sessionId: string,
    interrupt: InterruptInfo,
    userId?: string
  ): ChannelResponse {
    // Store the pending approval
    pendingApprovals.set(sessionId, interrupt);

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
      const pendingApproval = pendingApprovals.get(session.id);
      if (pendingApproval) {
        const decision = parseApprovalResponse(message.text);
        if (decision) {
          gatewayLogs.info("Router", `✅ Approval decision: ${decision}`, {
            session_id: session.id,
            actions_count: pendingApproval.pending_actions.length,
          });

          // Clear the pending approval
          pendingApprovals.delete(session.id);

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

      // Route to agent worker
      gatewayLogs.info("Router", `🤖 Routing to agent worker...`);
      try {
        const result = await callWorkerTurn({
          session_id: session.id,
          text: message.text,
          metadata: {
            channelType: message.channelType,
            channelId: message.channelId,
            chatId: message.chatId,
            userId: message.userId,
            userName: message.userName,
            timestamp: message.timestamp.toISOString(),
            ...message.metadata,
          },
        });

        // Check if approval is required
        if (result.interrupt) {
          gatewayLogs.info("Router", `⏸️ Tool approval required`, {
            actions: result.interrupt.pending_actions.map(a => a.tool_name),
          });
          return handleInterrupt(session.id, result.interrupt, message.userId);
        }

        const latency = Date.now() - startTime;
        gatewayLogs.info("Router", `📤 Response sent (${latency}ms total)`, {
          response_length: result.text.length,
        });
        return {
          text: result.text,
          metadata: {
            events: result.events,
            sessionId: result.session_id,
          },
        };
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
      return pendingApprovals.has(sessionId);
    },

    /**
     * Get pending approval info for a session.
     */
    getPendingApproval(sessionId: string): InterruptInfo | undefined {
      return pendingApprovals.get(sessionId);
    },

    /**
     * Cancel a pending approval.
     */
    cancelPendingApproval(sessionId: string): boolean {
      return pendingApprovals.delete(sessionId);
    },

    /**
     * Get the session manager for external use.
     */
    getSessionManager(): SessionManager {
      return sessionManager;
    },
  };
}

export type Router = ReturnType<typeof createRouter>;
