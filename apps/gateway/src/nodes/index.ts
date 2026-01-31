/**
 * Node management module for AG3NT multi-node architecture.
 *
 * This module provides:
 * - NodeRegistry: Tracks connected nodes and their capabilities
 * - NodeConnectionManager: Manages WebSocket connections to companion nodes
 * - Node types and interfaces for type-safe node operations
 * - Capability-based routing for node actions
 * - Node communication protocol
 */

export { NodeRegistry } from "./NodeRegistry.js";
export { NodeConnectionManager } from "./NodeConnectionManager.js";
export { PairingManager, type PairingCode, type ApprovedNode } from "./PairingManager.js";
export {
  NodeInfo,
  NodeCapability,
  NodeType,
  NodeStatus,
  NodePlatform,
  NodeConfig,
  NodeActionRequest,
  NodeActionResponse,
  NodeEvent,
  NodeEventHandler,
} from "./types.js";
export {
  validateNodeMessage,
  type NodeMessageType,
  type NodeMessage,
  type AnyNodeMessage,
  type RegisterMessage,
  type RegisterAckMessage,
  type HeartbeatMessage,
  type HeartbeatAckMessage,
  type ActionRequestMessage,
  type ActionResponseMessage,
  type CapabilityUpdateMessage,
  type DisconnectMessage,
  type ErrorMessage,
} from "./protocol.js";

