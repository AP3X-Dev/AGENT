/**
 * Tests for NodeRegistry.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { NodeRegistry } from './NodeRegistry.js';
import type { NodeInfo, NodeCapability } from './types.js';

describe('NodeRegistry', () => {
  let nodeRegistry: NodeRegistry;

  beforeEach(() => {
    nodeRegistry = new NodeRegistry();
  });

  describe('Initialization', () => {
    it('should register local node on construction', () => {
      const localNode = nodeRegistry.getLocalNode();

      expect(localNode).toBeDefined();
      expect(localNode.id).toBe('local');
      expect(localNode.type).toBe('primary');
      expect(localNode.status).toBe('online');
      expect(localNode.capabilities).toContain('file_management');
    });

    it('should include local node in all nodes', () => {
      const allNodes = nodeRegistry.getAllNodes();

      expect(allNodes).toHaveLength(1);
      expect(allNodes[0].id).toBe('local');
    });
  });

  describe('Node Registration', () => {
    it('should register new node', () => {
      const node: Omit<NodeInfo, 'connectedAt' | 'lastSeen'> = {
        id: 'node-1',
        name: 'Test Node',
        type: 'companion',
        status: 'online',
        capabilities: ['browser', 'notifications'],
        platform: { os: 'android', version: '13', arch: 'arm64' },
      };

      const registered = nodeRegistry.registerNode(node);

      expect(registered.id).toBe('node-1');
      expect(registered.connectedAt).toBeInstanceOf(Date);
      expect(registered.lastSeen).toBeInstanceOf(Date);
    });

    it('should add registered node to all nodes', () => {
      nodeRegistry.registerNode({
        id: 'node-1',
        name: 'Node 1',
        type: 'companion',
        status: 'online',
        capabilities: ['browser'],
        platform: { os: 'ios', version: '16', arch: 'arm64' },
      });

      const allNodes = nodeRegistry.getAllNodes();

      expect(allNodes).toHaveLength(2); // local + node-1
      expect(allNodes.map((n) => n.id)).toContain('node-1');
    });

    it('should update existing node on re-registration', () => {
      const node: Omit<NodeInfo, 'connectedAt' | 'lastSeen'> = {
        id: 'node-1',
        name: 'Original Name',
        type: 'companion',
        status: 'online',
        capabilities: ['browser'],
        platform: { os: 'android', version: '13', arch: 'arm64' },
      };

      nodeRegistry.registerNode(node);

      // Re-register with updated name
      const updated = nodeRegistry.registerNode({
        ...node,
        name: 'Updated Name',
      });

      expect(updated.name).toBe('Updated Name');
      expect(nodeRegistry.getAllNodes()).toHaveLength(2); // Still only 2 nodes
    });
  });

  describe('Node Retrieval', () => {
    beforeEach(() => {
      nodeRegistry.registerNode({
        id: 'node-1',
        name: 'Node 1',
        type: 'companion',
        status: 'online',
        capabilities: ['browser', 'notifications'],
        platform: { os: 'android', version: '13', arch: 'arm64' },
      });

      nodeRegistry.registerNode({
        id: 'node-2',
        name: 'Node 2',
        type: 'companion',
        status: 'online',
        capabilities: ['file_management', 'clipboard'],
        platform: { os: 'ios', version: '16', arch: 'arm64' },
      });
    });

    it('should get node by ID', () => {
      const node = nodeRegistry.getNode('node-1');

      expect(node).toBeDefined();
      expect(node?.name).toBe('Node 1');
    });

    it('should return undefined for non-existent node', () => {
      const node = nodeRegistry.getNode('non-existent');

      expect(node).toBeUndefined();
    });

    it('should list all nodes', () => {
      const allNodes = nodeRegistry.getAllNodes();

      expect(allNodes).toHaveLength(3); // local + node-1 + node-2
    });

    it('should find nodes by capability', () => {
      const browserNodes = nodeRegistry.findNodesByCapability('browser');

      expect(browserNodes).toHaveLength(1);
      expect(browserNodes[0].id).toBe('node-1');
    });

    it('should find multiple nodes with same capability', () => {
      const fileNodes = nodeRegistry.findNodesByCapability('file_management');

      expect(fileNodes.length).toBeGreaterThanOrEqual(2); // local + node-2
      expect(fileNodes.map((n) => n.id)).toContain('local');
      expect(fileNodes.map((n) => n.id)).toContain('node-2');
    });

    it('should return empty array for capability with no nodes', () => {
      const nodes = nodeRegistry.findNodesByCapability('audio_input' as NodeCapability);

      expect(nodes).toEqual([]);
    });
  });

  describe('Node Unregistration', () => {
    beforeEach(() => {
      nodeRegistry.registerNode({
        id: 'node-1',
        name: 'Node 1',
        type: 'companion',
        status: 'online',
        capabilities: ['browser'],
        platform: { os: 'android', version: '13', arch: 'arm64' },
      });
    });

    it('should unregister node', () => {
      const removed = nodeRegistry.unregisterNode('node-1');

      expect(removed).toBe(true);
      expect(nodeRegistry.getNode('node-1')).toBeUndefined();
    });

    it('should return false when unregistering non-existent node', () => {
      const removed = nodeRegistry.unregisterNode('non-existent');

      expect(removed).toBe(false);
    });

    it('should not allow unregistering local node', () => {
      const removed = nodeRegistry.unregisterNode('local');

      expect(removed).toBe(false);
      expect(nodeRegistry.getLocalNode()).toBeDefined();
    });
  });

  // Note: Heartbeat tracking is handled internally by the NodeRegistry
  // and doesn't expose an updateHeartbeat() method in the current implementation

  describe('Node Status', () => {
    beforeEach(() => {
      nodeRegistry.registerNode({
        id: 'node-1',
        name: 'Node 1',
        type: 'companion',
        status: 'online',
        capabilities: ['browser'],
        platform: { os: 'android', version: '13', arch: 'arm64' },
      });

      nodeRegistry.registerNode({
        id: 'node-2',
        name: 'Node 2',
        type: 'companion',
        status: 'offline',
        capabilities: ['notifications'],
        platform: { os: 'ios', version: '16', arch: 'arm64' },
      });
    });

    it('should get registry status', () => {
      const status = nodeRegistry.getStatus();

      expect(status.nodeCount).toBe(3); // local + node-1 + node-2
      expect(status.onlineCount).toBe(2); // local + node-1 (node-2 is offline)
      expect(status.localNode).toBeDefined();
      expect(status.localNode.id).toBe('local');
    });

    it('should list capabilities across all nodes', () => {
      const status = nodeRegistry.getStatus();

      expect(status.capabilities).toContain('browser');
      expect(status.capabilities).toContain('file_management');
      // Note: offline nodes are not included in capabilities list
    });
  });

  describe('Event Handling', () => {
    it('should emit event when node is registered', () => {
      const eventHandler = vi.fn();
      nodeRegistry.onNodeEvent(eventHandler);

      nodeRegistry.registerNode({
        id: 'node-1',
        name: 'Node 1',
        type: 'companion',
        status: 'online',
        capabilities: ['browser'],
        platform: { os: 'android', version: '13', arch: 'arm64' },
      });

      expect(eventHandler).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'connected',
          nodeId: 'node-1',
        })
      );
    });

    it('should emit event when node is unregistered', () => {
      nodeRegistry.registerNode({
        id: 'node-1',
        name: 'Node 1',
        type: 'companion',
        status: 'online',
        capabilities: ['browser'],
        platform: { os: 'android', version: '13', arch: 'arm64' },
      });

      const eventHandler = vi.fn();
      nodeRegistry.onNodeEvent(eventHandler);

      nodeRegistry.unregisterNode('node-1');

      expect(eventHandler).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'disconnected',
          nodeId: 'node-1',
        })
      );
    });
  });
});


