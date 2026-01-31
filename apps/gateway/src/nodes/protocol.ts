/**
 * Node Communication Protocol
 * 
 * Defines message types and validation for WebSocket communication
 * between the Gateway and companion nodes.
 */

import { NodeCapability, NodePlatform } from "./types.js";

/**
 * Message types for node communication
 */
export type NodeMessageType =
  | "register"           // Initial registration with capabilities
  | "register:ack"       // Registration acknowledgment
  | "heartbeat"          // Keep-alive ping
  | "heartbeat:ack"      // Heartbeat acknowledgment
  | "action:request"     // Gateway sends action to node
  | "action:response"    // Node returns action result
  | "capability:update"  // Node updates its capabilities
  | "disconnect"         // Graceful disconnect
  | "error";             // Error message

/**
 * Base message structure
 */
export interface NodeMessage {
  type: NodeMessageType;
  nodeId?: string;
  timestamp: number;
  payload?: unknown;
}

/**
 * Registration message from companion node
 */
export interface RegisterMessage extends NodeMessage {
  type: "register";
  payload: {
    name: string;
    capabilities: NodeCapability[];
    platform: NodePlatform;
    authToken?: string;      // Pairing code or shared secret
    metadata?: Record<string, unknown>;
  };
}

/**
 * Registration acknowledgment from Gateway
 */
export interface RegisterAckMessage extends NodeMessage {
  type: "register:ack";
  nodeId: string;
  payload: {
    success: boolean;
    message?: string;
    error?: string;
  };
}

/**
 * Heartbeat message from companion node
 */
export interface HeartbeatMessage extends NodeMessage {
  type: "heartbeat";
  nodeId: string;
}

/**
 * Heartbeat acknowledgment from Gateway
 */
export interface HeartbeatAckMessage extends NodeMessage {
  type: "heartbeat:ack";
  nodeId: string;
}

/**
 * Action request from Gateway to node
 */
export interface ActionRequestMessage extends NodeMessage {
  type: "action:request";
  nodeId: string;
  payload: {
    requestId: string;       // Unique request ID for tracking
    action: string;          // Action type (e.g., "take_photo", "get_battery")
    params: Record<string, unknown>;
    timeout?: number;        // Optional timeout in milliseconds
  };
}

/**
 * Action response from node to Gateway
 */
export interface ActionResponseMessage extends NodeMessage {
  type: "action:response";
  nodeId: string;
  payload: {
    requestId: string;       // Matches the request ID
    success: boolean;
    result?: unknown;
    error?: string;
  };
}

/**
 * Capability update from node
 */
export interface CapabilityUpdateMessage extends NodeMessage {
  type: "capability:update";
  nodeId: string;
  payload: {
    capabilities: NodeCapability[];
  };
}

/**
 * Disconnect message from node
 */
export interface DisconnectMessage extends NodeMessage {
  type: "disconnect";
  nodeId: string;
  payload?: {
    reason?: string;
  };
}

/**
 * Error message
 */
export interface ErrorMessage extends NodeMessage {
  type: "error";
  nodeId?: string;
  payload: {
    code: string;
    message: string;
    details?: unknown;
  };
}

/**
 * Union type of all message types
 */
export type AnyNodeMessage =
  | RegisterMessage
  | RegisterAckMessage
  | HeartbeatMessage
  | HeartbeatAckMessage
  | ActionRequestMessage
  | ActionResponseMessage
  | CapabilityUpdateMessage
  | DisconnectMessage
  | ErrorMessage;

/**
 * Validate a node message
 */
export function validateNodeMessage(data: unknown): AnyNodeMessage {
  if (!data || typeof data !== "object") {
    throw new Error("Invalid message: not an object");
  }

  const msg = data as NodeMessage;

  if (!msg.type) {
    throw new Error("Invalid message: missing type");
  }

  if (typeof msg.timestamp !== "number") {
    throw new Error("Invalid message: missing or invalid timestamp");
  }

  // Type-specific validation
  switch (msg.type) {
    case "register":
      validateRegisterMessage(msg as RegisterMessage);
      break;
    case "heartbeat":
      if (!msg.nodeId) {
        throw new Error("Heartbeat message missing nodeId");
      }
      break;
    case "action:response":
      validateActionResponseMessage(msg as ActionResponseMessage);
      break;
    case "capability:update":
      validateCapabilityUpdateMessage(msg as CapabilityUpdateMessage);
      break;
    case "disconnect":
      if (!msg.nodeId) {
        throw new Error("Disconnect message missing nodeId");
      }
      break;
  }

  return msg as AnyNodeMessage;
}

function validateRegisterMessage(msg: RegisterMessage): void {
  if (!msg.payload) {
    throw new Error("Register message missing payload");
  }
  if (!msg.payload.name || typeof msg.payload.name !== "string") {
    throw new Error("Register message missing or invalid name");
  }
  if (!Array.isArray(msg.payload.capabilities)) {
    throw new Error("Register message missing or invalid capabilities");
  }
  if (!msg.payload.platform || typeof msg.payload.platform !== "object") {
    throw new Error("Register message missing or invalid platform");
  }
}

function validateActionResponseMessage(msg: ActionResponseMessage): void {
  if (!msg.nodeId) {
    throw new Error("Action response missing nodeId");
  }
  if (!msg.payload || !msg.payload.requestId) {
    throw new Error("Action response missing requestId");
  }
  if (typeof msg.payload.success !== "boolean") {
    throw new Error("Action response missing or invalid success field");
  }
}

function validateCapabilityUpdateMessage(msg: CapabilityUpdateMessage): void {
  if (!msg.nodeId) {
    throw new Error("Capability update missing nodeId");
  }
  if (!msg.payload || !Array.isArray(msg.payload.capabilities)) {
    throw new Error("Capability update missing or invalid capabilities");
  }
}

