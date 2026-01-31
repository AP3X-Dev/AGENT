/**
 * Mock Companion Node - Test client for multi-node functionality
 * 
 * This simulates a companion device connecting to the Gateway.
 * Use this to test node registration, heartbeat, and action execution.
 * 
 * Usage:
 *   npx tsx test/mockCompanionNode.ts [pairing-code]
 */

import WebSocket from "ws";
import type {
  NodeMessage,
  RegisterMessage,
  HeartbeatMessage,
  ActionResponseMessage,
  NodeCapability,
} from "../src/nodes/protocol.js";

const GATEWAY_WS_URL = "ws://127.0.0.1:18789/ws/nodes";
const NODE_NAME = "Test Mobile Device";
const NODE_CAPABILITIES: NodeCapability[] = [
  "camera",
  "microphone",
  "audio_output",
  "notifications",
  "screen_capture",
];

class MockCompanionNode {
  private ws: WebSocket | null = null;
  private nodeId: string | null = null;
  private heartbeatInterval: NodeJS.Timeout | null = null;
  private pairingCode: string;

  constructor(pairingCode: string) {
    this.pairingCode = pairingCode;
  }

  connect(): void {
    console.log(`[MockNode] Connecting to ${GATEWAY_WS_URL}...`);
    this.ws = new WebSocket(GATEWAY_WS_URL);

    this.ws.on("open", () => {
      console.log("[MockNode] Connected! Sending registration...");
      this.sendRegister();
    });

    this.ws.on("message", (data: Buffer) => {
      try {
        const msg = JSON.parse(data.toString()) as NodeMessage;
        this.handleMessage(msg);
      } catch (err) {
        console.error("[MockNode] Failed to parse message:", err);
      }
    });

    this.ws.on("close", () => {
      console.log("[MockNode] Connection closed");
      if (this.heartbeatInterval) {
        clearInterval(this.heartbeatInterval);
      }
    });

    this.ws.on("error", (err) => {
      console.error("[MockNode] WebSocket error:", err);
    });
  }

  private sendRegister(): void {
    const msg: RegisterMessage = {
      type: "register",
      timestamp: Date.now(),
      payload: {
        name: NODE_NAME,
        capabilities: NODE_CAPABILITIES,
        platform: {
          os: "android",
          version: "13",
          arch: "arm64",
        },
        authToken: this.pairingCode,
      },
    };

    this.send(msg);
  }

  private handleMessage(msg: NodeMessage): void {
    console.log(`[MockNode] Received: ${msg.type}`);

    switch (msg.type) {
      case "register:ack":
        this.handleRegisterAck(msg);
        break;
      case "heartbeat":
        this.handleHeartbeat(msg);
        break;
      case "action:request":
        this.handleActionRequest(msg);
        break;
      default:
        console.log(`[MockNode] Unhandled message type: ${msg.type}`);
    }
  }

  private handleRegisterAck(msg: any): void {
    if (msg.payload?.success) {
      this.nodeId = msg.payload.nodeId;
      console.log(`[MockNode] ✅ Registration successful! Node ID: ${this.nodeId}`);
      this.startHeartbeat();
    } else {
      console.error(`[MockNode] ❌ Registration failed: ${msg.payload?.message}`);
      this.ws?.close();
    }
  }

  private handleHeartbeat(msg: HeartbeatMessage): void {
    // Send heartbeat acknowledgment
    this.send({
      type: "heartbeat:ack",
      nodeId: this.nodeId!,
      timestamp: Date.now(),
    });
  }

  private handleActionRequest(msg: any): void {
    const { requestId, action, params } = msg.payload;
    console.log(`[MockNode] 📥 Action request: ${action}`, params);

    // Simulate action execution
    setTimeout(() => {
      const response: ActionResponseMessage = {
        type: "action:response",
        nodeId: this.nodeId!,
        timestamp: Date.now(),
        payload: {
          requestId,
          success: true,
          result: {
            message: `Mock action '${action}' completed successfully`,
            action,
            params,
            timestamp: new Date().toISOString(),
          },
        },
      };

      this.send(response);
      console.log(`[MockNode] ✅ Action response sent for: ${action}`);
    }, 1000); // Simulate 1 second processing time
  }

  private startHeartbeat(): void {
    this.heartbeatInterval = setInterval(() => {
      this.send({
        type: "heartbeat",
        nodeId: this.nodeId!,
        timestamp: Date.now(),
      });
      console.log("[MockNode] 💓 Heartbeat sent");
    }, 30000); // Every 30 seconds
  }

  private send(msg: NodeMessage): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  disconnect(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
    }
    if (this.ws) {
      this.ws.close();
    }
  }
}

// Main
const pairingCode = process.argv[2];
if (!pairingCode) {
  console.error("Usage: npx tsx test/mockCompanionNode.ts [pairing-code]");
  console.error("Example: npx tsx test/mockCompanionNode.ts 123456");
  process.exit(1);
}

console.log("=== Mock Companion Node Test Client ===");
console.log(`Pairing Code: ${pairingCode}`);
console.log(`Capabilities: ${NODE_CAPABILITIES.join(", ")}`);
console.log("");

const node = new MockCompanionNode(pairingCode);
node.connect();

// Handle graceful shutdown
process.on("SIGINT", () => {
  console.log("\n[MockNode] Shutting down...");
  node.disconnect();
  process.exit(0);
});

