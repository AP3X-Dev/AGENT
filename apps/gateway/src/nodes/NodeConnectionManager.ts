/**
 * NodeConnectionManager - Manages WebSocket connections to companion nodes
 */

import type { WebSocket } from "ws";
import { NodeRegistry } from "./NodeRegistry.js";
import { PairingManager } from "./PairingManager.js";
import type { NodeCapability, NodeInfo } from "./types.js";
import {
  validateNodeMessage,
  type AnyNodeMessage,
  type RegisterMessage,
  type HeartbeatMessage,
  type ActionResponseMessage,
  type CapabilityUpdateMessage,
  type DisconnectMessage,
  type RegisterAckMessage,
  type HeartbeatAckMessage,
  type ActionRequestMessage,
} from "./protocol.js";

/**
 * Connection state for a companion node
 */
interface NodeConnection {
  nodeId: string;
  ws: WebSocket;
  lastHeartbeat: Date;
  authenticated: boolean;
}

/**
 * Pending action request
 */
interface PendingAction {
  requestId: string;
  nodeId: string;
  resolve: (result: unknown) => void;
  reject: (error: Error) => void;
  timeout: NodeJS.Timeout;
}

export class NodeConnectionManager {
  private connections: Map<string, NodeConnection> = new Map();
  private pendingActions: Map<string, PendingAction> = new Map();
  private heartbeatInterval: NodeJS.Timeout | null = null;
  private readonly HEARTBEAT_INTERVAL = 30000; // 30 seconds
  private readonly HEARTBEAT_TIMEOUT = 90000; // 90 seconds

  constructor(
    private registry: NodeRegistry,
    private pairingManager: PairingManager
  ) {
    this.startHeartbeatMonitor();
  }

  /**
   * Handle a new WebSocket connection from a companion node
   */
  handleConnection(ws: WebSocket): void {
    console.log("[NodeConnectionManager] New connection received");

    ws.on("message", async (data) => {
      try {
        const msg = validateNodeMessage(JSON.parse(data.toString()));
        await this.handleMessage(ws, msg);
      } catch (err) {
        console.error("[NodeConnectionManager] Message error:", err);
        this.sendError(ws, "INVALID_MESSAGE", String(err));
      }
    });

    ws.on("close", () => {
      this.handleDisconnect(ws);
    });

    ws.on("error", (err) => {
      console.error("[NodeConnectionManager] WebSocket error:", err);
    });
  }

  /**
   * Handle incoming messages from companion nodes
   */
  private async handleMessage(ws: WebSocket, msg: AnyNodeMessage): Promise<void> {
    switch (msg.type) {
      case "register":
        await this.handleRegister(ws, msg as RegisterMessage);
        break;
      case "heartbeat":
        this.handleHeartbeat(ws, msg as HeartbeatMessage);
        break;
      case "action:response":
        this.handleActionResponse(msg as ActionResponseMessage);
        break;
      case "capability:update":
        this.handleCapabilityUpdate(msg as CapabilityUpdateMessage);
        break;
      case "disconnect":
        this.handleDisconnectMessage(ws, msg as DisconnectMessage);
        break;
      default:
        console.warn("[NodeConnectionManager] Unknown message type:", msg.type);
    }
  }

  /**
   * Handle node registration
   */
  private async handleRegister(ws: WebSocket, msg: RegisterMessage): Promise<void> {
    console.log("[NodeConnectionManager] Registration request:", msg.payload.name);

    // Authenticate the node
    const authToken = msg.payload.authToken || "";
    const authenticated = this.authenticateNode(authToken);

    if (!authenticated) {
      this.sendRegisterAck(ws, "", false, "Authentication failed");
      ws.close();
      return;
    }

    // Generate unique node ID
    const nodeId = `companion-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

    // Register in NodeRegistry
    const nodeInfo = this.registry.registerNode({
      id: nodeId,
      name: msg.payload.name,
      type: "companion",
      status: "online",
      capabilities: msg.payload.capabilities,
      platform: msg.payload.platform,
    });

    // Store connection
    this.connections.set(nodeId, {
      nodeId,
      ws,
      lastHeartbeat: new Date(),
      authenticated: true,
    });

    // Approve the node in pairing manager
    this.pairingManager.approveNode(nodeId, msg.payload.name);

    // Send acknowledgment
    this.sendRegisterAck(ws, nodeId, true, "Registration successful");

    console.log(`[NodeConnectionManager] Node registered: ${nodeInfo.name} (${nodeId})`);
  }

  /**
   * Handle heartbeat from node
   */
  private handleHeartbeat(ws: WebSocket, msg: HeartbeatMessage): void {
    const conn = this.connections.get(msg.nodeId);
    if (!conn) {
      console.warn("[NodeConnectionManager] Heartbeat from unknown node:", msg.nodeId);
      return;
    }

    conn.lastHeartbeat = new Date();
    this.sendHeartbeatAck(ws, msg.nodeId);
  }

  /**
   * Handle action response from node
   */
  private handleActionResponse(msg: ActionResponseMessage): void {
    const pending = this.pendingActions.get(msg.payload.requestId);
    if (!pending) {
      console.warn("[NodeConnectionManager] Response for unknown request:", msg.payload.requestId);
      return;
    }

    clearTimeout(pending.timeout);
    this.pendingActions.delete(msg.payload.requestId);

    if (msg.payload.success) {
      pending.resolve(msg.payload.result);
    } else {
      pending.reject(new Error(msg.payload.error || "Action failed"));
    }
  }

  /**
   * Handle capability update from node
   */
  private handleCapabilityUpdate(msg: CapabilityUpdateMessage): void {
    const node = this.registry.getNode(msg.nodeId);
    if (!node) {
      console.warn("[NodeConnectionManager] Capability update from unknown node:", msg.nodeId);
      return;
    }

    // Update capabilities in registry
    this.registry.registerNode({
      ...node,
      capabilities: msg.payload.capabilities,
    });

    console.log(`[NodeConnectionManager] Capabilities updated for ${msg.nodeId}`);
  }

  /**
   * Handle disconnect message from node
   */
  private handleDisconnectMessage(ws: WebSocket, msg: DisconnectMessage): void {
    console.log(`[NodeConnectionManager] Node ${msg.nodeId} disconnecting:`, msg.payload?.reason);
    this.removeConnection(msg.nodeId);
    ws.close();
  }

  /**
   * Handle WebSocket disconnect
   */
  private handleDisconnect(ws: WebSocket): void {
    // Find the connection by WebSocket
    for (const [nodeId, conn] of this.connections.entries()) {
      if (conn.ws === ws) {
        console.log(`[NodeConnectionManager] Node ${nodeId} disconnected`);
        this.removeConnection(nodeId);
        break;
      }
    }
  }

  /**
   * Remove a connection and update registry
   */
  private removeConnection(nodeId: string): void {
    this.connections.delete(nodeId);
    this.registry.updateNodeStatus(nodeId, "offline");

    // Reject any pending actions for this node
    for (const [requestId, pending] of this.pendingActions.entries()) {
      if (pending.nodeId === nodeId) {
        clearTimeout(pending.timeout);
        pending.reject(new Error("Node disconnected"));
        this.pendingActions.delete(requestId);
      }
    }
  }

  /**
   * Send an action request to a node
   */
  async sendActionToNode(
    nodeId: string,
    action: string,
    params: Record<string, unknown>,
    timeout: number = 30000
  ): Promise<unknown> {
    const conn = this.connections.get(nodeId);
    if (!conn) {
      throw new Error(`Node ${nodeId} not connected`);
    }

    const requestId = `action-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

    return new Promise((resolve, reject) => {
      const timeoutHandle = setTimeout(() => {
        this.pendingActions.delete(requestId);
        reject(new Error(`Action timeout after ${timeout}ms`));
      }, timeout);

      this.pendingActions.set(requestId, {
        requestId,
        nodeId,
        resolve,
        reject,
        timeout: timeoutHandle,
      });

      const msg: ActionRequestMessage = {
        type: "action:request",
        nodeId,
        timestamp: Date.now(),
        payload: {
          requestId,
          action,
          params,
          timeout,
        },
      };

      conn.ws.send(JSON.stringify(msg));
    });
  }

  /**
   * Start heartbeat monitor
   */
  private startHeartbeatMonitor(): void {
    this.heartbeatInterval = setInterval(() => {
      const now = Date.now();

      for (const [nodeId, conn] of this.connections.entries()) {
        const timeSinceHeartbeat = now - conn.lastHeartbeat.getTime();

        if (timeSinceHeartbeat > this.HEARTBEAT_TIMEOUT) {
          console.warn(`[NodeConnectionManager] Node ${nodeId} heartbeat timeout`);
          this.removeConnection(nodeId);
          conn.ws.close();
        }
      }
    }, this.HEARTBEAT_INTERVAL);
  }

  /**
   * Stop heartbeat monitor
   */
  stop(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }

    // Close all connections
    for (const conn of this.connections.values()) {
      conn.ws.close();
    }
    this.connections.clear();
  }

  /**
   * Send registration acknowledgment
   */
  private sendRegisterAck(ws: WebSocket, nodeId: string, success: boolean, message?: string): void {
    const msg: RegisterAckMessage = {
      type: "register:ack",
      nodeId,
      timestamp: Date.now(),
      payload: {
        success,
        message: success ? message : undefined,
        error: success ? undefined : message,
      },
    };
    ws.send(JSON.stringify(msg));
  }

  /**
   * Send heartbeat acknowledgment
   */
  private sendHeartbeatAck(ws: WebSocket, nodeId: string): void {
    const msg: HeartbeatAckMessage = {
      type: "heartbeat:ack",
      nodeId,
      timestamp: Date.now(),
    };
    ws.send(JSON.stringify(msg));
  }

  /**
   * Send error message
   */
  private sendError(ws: WebSocket, code: string, message: string): void {
    const msg = {
      type: "error",
      timestamp: Date.now(),
      payload: {
        code,
        message,
      },
    };
    ws.send(JSON.stringify(msg));
  }

  /**
   * Get all active connections
   */
  getActiveConnections(): string[] {
    return Array.from(this.connections.keys());
  }

  /**
   * Check if a node is connected
   */
  isNodeConnected(nodeId: string): boolean {
    return this.connections.has(nodeId);
  }

  /**
   * Authenticate a node using pairing code or shared secret
   */
  private authenticateNode(authToken: string): boolean {
    // Try pairing code first
    if (this.pairingManager.validatePairingCode(authToken)) {
      return true;
    }

    // Try shared secret fallback
    if (this.pairingManager.validateSharedSecret(authToken)) {
      return true;
    }

    return false;
  }

  /**
   * Get the pairing manager
   */
  getPairingManager(): PairingManager {
    return this.pairingManager;
  }
}

