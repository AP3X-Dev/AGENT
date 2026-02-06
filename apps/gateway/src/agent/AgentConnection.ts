/**
 * AgentConnection - Persistent WebSocket connection to Agent Worker.
 *
 * Provides low-latency communication by:
 * 1. Eliminating per-request TCP handshake (5-15ms savings)
 * 2. Reusing a single connection for all requests
 * 3. Supporting request pipelining
 * 4. Auto-reconnecting on disconnect
 *
 * Usage:
 *   const conn = new AgentConnection('http://127.0.0.1:18790', 'token');
 *   await conn.connect();
 *   const response = await conn.sendTurn({ session_id: '...', text: '...' });
 */

import WebSocket from "ws";
import { EventEmitter } from "events";
import { WORKER_FETCH_TIMEOUT_MS } from "../config/constants.js";

// =============================================================================
// Types
// =============================================================================

export interface TurnRequest {
  session_id: string;
  text: string;
  metadata?: Record<string, unknown>;
}

export interface ResumeRequest {
  session_id: string;
  decisions: Array<{ type: "approve" | "reject" }>;
}

export interface InterruptInfo {
  interrupt_id: string;
  pending_actions?: Array<{
    tool_name: string;
    args: Record<string, unknown>;
    description: string;
  }>;
  action_count?: number;
  type?: string;
  question?: string;
  options?: string[];
  allow_custom?: boolean;
}

export interface UsageInfo {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  model: string;
  provider: string;
}

export interface TurnResponse {
  session_id: string;
  text: string;
  events: Array<Record<string, unknown>>;
  interrupt?: InterruptInfo | null;
  usage?: UsageInfo | null;
  latency_ms?: number;
}

interface PendingRequest {
  resolve: (value: TurnResponse) => void;
  reject: (error: Error) => void;
  timeout: NodeJS.Timeout;
  startTime: number;
}

interface WebSocketMessage {
  type: "response" | "error" | "pong" | "stream";
  id?: string;
  data?: TurnResponse;
  error?: string;
  error_type?: string;
  timestamp?: number;
}

// =============================================================================
// AgentConnection
// =============================================================================

export class AgentConnection extends EventEmitter {
  private ws: WebSocket | null = null;
  private pendingRequests: Map<string, PendingRequest> = new Map();
  private reconnectAttempts = 0;
  private readonly maxReconnectAttempts = 10;
  private readonly reconnectBaseDelayMs = 100;
  private isConnecting = false;
  private shouldReconnect = true;

  // Metrics
  private totalRequests = 0;
  private totalLatencyMs = 0;
  private connectionStartTime = 0;

  constructor(
    private readonly agentUrl: string,
    private readonly authToken?: string,
    private readonly timeoutMs: number = WORKER_FETCH_TIMEOUT_MS
  ) {
    super();
  }

  /**
   * Connect to the Agent Worker WebSocket endpoint.
   */
  async connect(): Promise<void> {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return; // Already connected
    }

    if (this.isConnecting) {
      // Wait for existing connection attempt
      return new Promise((resolve, reject) => {
        this.once("connected", resolve);
        this.once("connect_failed", reject);
      });
    }

    this.isConnecting = true;
    this.shouldReconnect = true;

    return new Promise((resolve, reject) => {
      try {
        // Convert HTTP URL to WebSocket URL
        const wsUrl = this.agentUrl.replace(/^http/, "ws") + "/ws";

        const headers: Record<string, string> = {};
        if (this.authToken) {
          headers["X-Gateway-Token"] = this.authToken;
        }

        this.ws = new WebSocket(wsUrl, { headers });
        this.connectionStartTime = Date.now();

        this.ws.on("open", () => {
          this.isConnecting = false;
          this.reconnectAttempts = 0;
          console.log("[AgentConnection] Connected to agent worker via WebSocket");
          this.emit("connected");
          resolve();
        });

        this.ws.on("message", (data) => this.handleMessage(data));

        this.ws.on("close", (code, reason) => {
          console.log(`[AgentConnection] Disconnected: ${code} ${reason.toString()}`);
          this.ws = null;
          this.handleDisconnect();
        });

        this.ws.on("error", (err) => {
          console.error("[AgentConnection] WebSocket error:", err.message);
          if (this.isConnecting) {
            this.isConnecting = false;
            this.emit("connect_failed", err);
            reject(err);
          }
        });
      } catch (err) {
        this.isConnecting = false;
        reject(err);
      }
    });
  }

  /**
   * Send a turn request and wait for response.
   */
  async sendTurn(request: TurnRequest): Promise<TurnResponse> {
    return this.sendRequest("turn", { ...request });
  }

  /**
   * Send a resume request and wait for response.
   */
  async sendResume(request: ResumeRequest): Promise<TurnResponse> {
    return this.sendRequest("resume", { ...request });
  }

  /**
   * Send a ping to check connection health.
   */
  async ping(): Promise<number> {
    const start = Date.now();
    await this.sendRequest("ping", {});
    return Date.now() - start;
  }

  /**
   * Check if connected.
   */
  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  /**
   * Get connection metrics.
   */
  getMetrics(): {
    connected: boolean;
    totalRequests: number;
    avgLatencyMs: number;
    connectionUptimeMs: number;
    pendingRequests: number;
  } {
    return {
      connected: this.isConnected(),
      totalRequests: this.totalRequests,
      avgLatencyMs:
        this.totalRequests > 0 ? this.totalLatencyMs / this.totalRequests : 0,
      connectionUptimeMs: this.connectionStartTime
        ? Date.now() - this.connectionStartTime
        : 0,
      pendingRequests: this.pendingRequests.size,
    };
  }

  /**
   * Close the connection.
   */
  close(): void {
    this.shouldReconnect = false;

    // Reject all pending requests
    for (const [id, pending] of this.pendingRequests) {
      clearTimeout(pending.timeout);
      pending.reject(new Error("Connection closed"));
    }
    this.pendingRequests.clear();

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  // ---------------------------------------------------------------------------
  // Private Methods
  // ---------------------------------------------------------------------------

  private async sendRequest(
    type: string,
    data: Record<string, unknown>
  ): Promise<TurnResponse> {
    // Ensure connected
    if (!this.isConnected()) {
      await this.connect();
    }

    const requestId = crypto.randomUUID();
    const startTime = Date.now();

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pendingRequests.delete(requestId);
        reject(new Error(`Request timeout after ${this.timeoutMs}ms`));
      }, this.timeoutMs);

      this.pendingRequests.set(requestId, {
        resolve: (value) => {
          this.totalRequests++;
          this.totalLatencyMs += Date.now() - startTime;
          resolve(value);
        },
        reject,
        timeout,
        startTime,
      });

      try {
        this.ws?.send(
          JSON.stringify({
            type,
            id: requestId,
            ...data,
          })
        );
      } catch (err) {
        clearTimeout(timeout);
        this.pendingRequests.delete(requestId);
        reject(err);
      }
    });
  }

  private handleMessage(data: WebSocket.RawData): void {
    try {
      const msg: WebSocketMessage = JSON.parse(data.toString());

      if (msg.type === "response" || msg.type === "pong") {
        const pending = this.pendingRequests.get(msg.id || "");
        if (pending) {
          clearTimeout(pending.timeout);
          this.pendingRequests.delete(msg.id || "");
          pending.resolve(msg.data || ({} as TurnResponse));
        }
      } else if (msg.type === "error" && msg.id) {
        const pending = this.pendingRequests.get(msg.id);
        if (pending) {
          clearTimeout(pending.timeout);
          this.pendingRequests.delete(msg.id);
          pending.reject(new Error(msg.error || "Unknown error"));
        }
      } else if (msg.type === "stream") {
        // Emit stream events for real-time updates (Phase 2)
        this.emit("stream", msg);
      }
    } catch (err) {
      console.error("[AgentConnection] Failed to parse message:", err);
    }
  }

  private async handleDisconnect(): Promise<void> {
    // Reject all pending requests
    for (const [id, pending] of this.pendingRequests) {
      clearTimeout(pending.timeout);
      pending.reject(new Error("Connection lost"));
    }
    this.pendingRequests.clear();

    this.emit("disconnected");

    // Attempt reconnect if enabled
    if (this.shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
      const delay =
        this.reconnectBaseDelayMs * Math.pow(2, this.reconnectAttempts);
      const jitter = Math.random() * delay * 0.2;
      const totalDelay = Math.min(delay + jitter, 30000); // Cap at 30s

      this.reconnectAttempts++;
      console.log(
        `[AgentConnection] Reconnecting in ${Math.round(totalDelay)}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`
      );

      setTimeout(() => {
        this.connect().catch((err) => {
          console.error("[AgentConnection] Reconnect failed:", err.message);
        });
      }, totalDelay);
    } else if (this.shouldReconnect) {
      console.error(
        "[AgentConnection] Max reconnect attempts reached, giving up"
      );
      this.emit("max_reconnects");
    }
  }
}

// =============================================================================
// Singleton Instance
// =============================================================================

let _agentConnection: AgentConnection | null = null;

/**
 * Get the singleton AgentConnection instance.
 * Creates and connects if not already done.
 */
export async function getAgentConnection(
  agentUrl: string,
  authToken?: string
): Promise<AgentConnection> {
  if (!_agentConnection) {
    _agentConnection = new AgentConnection(agentUrl, authToken);
    await _agentConnection.connect();
  }
  return _agentConnection;
}

/**
 * Check if WebSocket connection is available and healthy.
 */
export function isWebSocketAvailable(): boolean {
  return _agentConnection?.isConnected() ?? false;
}

/**
 * Close the singleton connection.
 */
export function closeAgentConnection(): void {
  if (_agentConnection) {
    _agentConnection.close();
    _agentConnection = null;
  }
}
