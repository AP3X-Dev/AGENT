/**
 * NodeRegistry - Manages connected nodes and their capabilities.
 *
 * The registry tracks all nodes (local and remote) and provides
 * capability-based routing for node actions.
 */

import os from "os";
import {
  NodeInfo,
  NodeCapability,
  NodeStatus,
  NodeEvent,
  NodeEventHandler,
  NodePlatform,
} from "./types.js";

/**
 * Detect the current platform information.
 */
function detectPlatform(): NodePlatform {
  const platform = os.platform();
  const osMap: Record<string, string> = {
    win32: "windows",
    darwin: "darwin",
    linux: "linux",
  };

  return {
    os: osMap[platform] || platform,
    version: os.release(),
    arch: os.arch(),
  };
}

/**
 * Get default capabilities for the local desktop node.
 */
function getLocalCapabilities(): NodeCapability[] {
  // Desktop nodes have these capabilities by default
  return [
    "file_management",
    "application_control",
    "system_info",
    "code_execution",
    "clipboard",
    "notifications",
    "audio_output", // TTS available on most desktops
  ];
}

export class NodeRegistry {
  private nodes: Map<string, NodeInfo> = new Map();
  private eventHandlers: NodeEventHandler[] = [];
  private localNodeId: string = "local";

  constructor() {
    // Register the local node on construction
    this.registerLocalNode();
  }

  /**
   * Register the local (primary) node representing this machine.
   */
  private registerLocalNode(): void {
    const localNode: NodeInfo = {
      id: this.localNodeId,
      name: os.hostname() || "Local Desktop",
      type: "primary",
      status: "online",
      capabilities: getLocalCapabilities(),
      platform: detectPlatform(),
      connectedAt: new Date(),
      lastSeen: new Date(),
    };

    this.nodes.set(this.localNodeId, localNode);
    console.log(
      `[NodeRegistry] Local node registered: ${localNode.name} (${localNode.platform.os})`
    );
    console.log(
      `[NodeRegistry] Capabilities: ${localNode.capabilities.join(", ")}`
    );
  }

  /**
   * Get the local node.
   */
  getLocalNode(): NodeInfo {
    return this.nodes.get(this.localNodeId)!;
  }

  /**
   * Register a new node (typically a companion device).
   */
  registerNode(node: Omit<NodeInfo, "connectedAt" | "lastSeen">): NodeInfo {
    const fullNode: NodeInfo = {
      ...node,
      connectedAt: new Date(),
      lastSeen: new Date(),
    };

    this.nodes.set(node.id, fullNode);
    console.log(`[NodeRegistry] Node registered: ${node.name} (${node.id})`);

    this.emitEvent({
      type: "connected",
      nodeId: node.id,
      node: fullNode,
      timestamp: new Date(),
    });

    return fullNode;
  }

  /**
   * Unregister a node (when it disconnects).
   */
  unregisterNode(nodeId: string): boolean {
    const node = this.nodes.get(nodeId);
    if (!node) return false;

    // Don't allow unregistering the local node
    if (nodeId === this.localNodeId) {
      console.warn("[NodeRegistry] Cannot unregister local node");
      return false;
    }

    this.nodes.delete(nodeId);
    console.log(`[NodeRegistry] Node unregistered: ${node.name} (${nodeId})`);

    this.emitEvent({
      type: "disconnected",
      nodeId,
      timestamp: new Date(),
    });

    return true;
  }

  /**
   * Update a node's status.
   */
  updateNodeStatus(nodeId: string, status: NodeStatus): boolean {
    const node = this.nodes.get(nodeId);
    if (!node) return false;

    node.status = status;
    node.lastSeen = new Date();
    return true;
  }

  /**
   * Get a node by ID.
   */
  getNode(nodeId: string): NodeInfo | undefined {
    return this.nodes.get(nodeId);
  }

  /**
   * Get all registered nodes.
   */
  getAllNodes(): NodeInfo[] {
    return Array.from(this.nodes.values());
  }

  /**
   * Get all online nodes.
   */
  getOnlineNodes(): NodeInfo[] {
    return this.getAllNodes().filter((n) => n.status === "online");
  }

  /**
   * Find nodes with a specific capability.
   */
  findNodesByCapability(capability: NodeCapability): NodeInfo[] {
    return this.getOnlineNodes().filter((n) =>
      n.capabilities.includes(capability)
    );
  }

  /**
   * Find the best node for a capability (prefers local, then first available).
   */
  findBestNode(capability: NodeCapability): NodeInfo | undefined {
    const capable = this.findNodesByCapability(capability);
    if (capable.length === 0) return undefined;

    // Prefer local node if it has the capability
    const local = capable.find((n) => n.id === this.localNodeId);
    if (local) return local;

    // Otherwise return first available
    return capable[0];
  }

  /**
   * Check if any node has a specific capability.
   */
  hasCapability(capability: NodeCapability): boolean {
    return this.findNodesByCapability(capability).length > 0;
  }

  /**
   * Get a summary of all capabilities across all nodes.
   */
  getCapabilitySummary(): Record<NodeCapability, string[]> {
    const summary: Record<string, string[]> = {};

    for (const node of this.getOnlineNodes()) {
      for (const cap of node.capabilities) {
        if (!summary[cap]) {
          summary[cap] = [];
        }
        summary[cap].push(node.id);
      }
    }

    return summary as Record<NodeCapability, string[]>;
  }

  /**
   * Subscribe to node events.
   */
  onNodeEvent(handler: NodeEventHandler): () => void {
    this.eventHandlers.push(handler);
    return () => {
      const idx = this.eventHandlers.indexOf(handler);
      if (idx >= 0) this.eventHandlers.splice(idx, 1);
    };
  }

  /**
   * Emit a node event to all handlers.
   */
  private emitEvent(event: NodeEvent): void {
    for (const handler of this.eventHandlers) {
      try {
        handler(event);
      } catch (err) {
        console.error("[NodeRegistry] Event handler error:", err);
      }
    }
  }

  /**
   * Get registry status for API response.
   */
  getStatus(): {
    nodeCount: number;
    onlineCount: number;
    localNode: NodeInfo;
    capabilities: NodeCapability[];
  } {
    const allCaps = new Set<NodeCapability>();
    for (const node of this.getOnlineNodes()) {
      for (const cap of node.capabilities) {
        allCaps.add(cap);
      }
    }

    return {
      nodeCount: this.nodes.size,
      onlineCount: this.getOnlineNodes().length,
      localNode: this.getLocalNode(),
      capabilities: Array.from(allCaps),
    };
  }
}

