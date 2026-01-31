/**
 * Tests for ChannelRegistry.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { ChannelRegistry, type ChannelEvent } from "./ChannelRegistry.js";
import type { IChannelAdapter, ChannelMessage } from "./types.js";

// Mock adapter factory
function createMockAdapter(
  id: string,
  type: string = "test"
): IChannelAdapter & { triggerMessage: (msg: ChannelMessage) => Promise<void> } {
  let messageHandler: ((msg: ChannelMessage) => Promise<string | undefined>) | null = null;
  let connected = false;

  return {
    id,
    type,
    connect: vi.fn(async () => {
      connected = true;
    }),
    disconnect: vi.fn(async () => {
      connected = false;
    }),
    send: vi.fn(async () => {}),
    onMessage: vi.fn((handler) => {
      messageHandler = handler;
    }),
    isConnected: vi.fn(() => connected),
    triggerMessage: async (msg: ChannelMessage) => {
      if (messageHandler) {
        await messageHandler(msg);
      }
    },
  };
}

describe("ChannelRegistry", () => {
  let registry: ChannelRegistry;

  beforeEach(() => {
    registry = new ChannelRegistry();
  });

  describe("register", () => {
    it("should register an adapter", () => {
      const adapter = createMockAdapter("test-1");
      registry.register(adapter);
      expect(registry.get("test-1")).toBe(adapter);
    });

    it("should throw if adapter already registered", () => {
      const adapter = createMockAdapter("test-1");
      registry.register(adapter);
      expect(() => registry.register(adapter)).toThrow(
        "Adapter already registered: test-1"
      );
    });

    it("should wire up message handler", () => {
      const adapter = createMockAdapter("test-1");
      registry.register(adapter);
      expect(adapter.onMessage).toHaveBeenCalled();
    });
  });

  describe("unregister", () => {
    it("should unregister an adapter", async () => {
      const adapter = createMockAdapter("test-1");
      registry.register(adapter);
      await registry.unregister("test-1");
      expect(registry.get("test-1")).toBeUndefined();
    });

    it("should disconnect if connected", async () => {
      const adapter = createMockAdapter("test-1");
      registry.register(adapter);
      await adapter.connect();
      await registry.unregister("test-1");
      expect(adapter.disconnect).toHaveBeenCalled();
    });

    it("should handle non-existent adapter", async () => {
      await expect(registry.unregister("non-existent")).resolves.toBeUndefined();
    });
  });

  describe("get", () => {
    it("should return adapter by ID", () => {
      const adapter = createMockAdapter("test-1");
      registry.register(adapter);
      expect(registry.get("test-1")).toBe(adapter);
    });

    it("should return undefined for non-existent ID", () => {
      expect(registry.get("non-existent")).toBeUndefined();
    });
  });

  describe("getByType", () => {
    it("should return adapters of specific type", () => {
      const adapter1 = createMockAdapter("test-1", "telegram");
      const adapter2 = createMockAdapter("test-2", "slack");
      const adapter3 = createMockAdapter("test-3", "telegram");
      registry.register(adapter1);
      registry.register(adapter2);
      registry.register(adapter3);

      const telegramAdapters = registry.getByType("telegram");
      expect(telegramAdapters).toHaveLength(2);
      expect(telegramAdapters).toContain(adapter1);
      expect(telegramAdapters).toContain(adapter3);
    });

    it("should return empty array for non-existent type", () => {
      expect(registry.getByType("discord")).toEqual([]);
    });
  });

  describe("all", () => {
    it("should return all adapters", () => {
      const adapter1 = createMockAdapter("test-1");
      const adapter2 = createMockAdapter("test-2");
      registry.register(adapter1);
      registry.register(adapter2);

      const all = registry.all();
      expect(all).toHaveLength(2);
      expect(all).toContain(adapter1);
      expect(all).toContain(adapter2);
    });

    it("should return empty array when no adapters", () => {
      expect(registry.all()).toEqual([]);
    });
  });

  describe("connectAll", () => {
    it("should connect all adapters", async () => {
      const adapter1 = createMockAdapter("test-1");
      const adapter2 = createMockAdapter("test-2");
      registry.register(adapter1);
      registry.register(adapter2);

      await registry.connectAll();

      expect(adapter1.connect).toHaveBeenCalled();
      expect(adapter2.connect).toHaveBeenCalled();
    });

    it("should emit connected events", async () => {
      const adapter = createMockAdapter("test-1");
      registry.register(adapter);

      const events: ChannelEvent[] = [];
      registry.onEvent((e) => events.push(e));

      await registry.connectAll();

      expect(events).toContainEqual({ type: "connected", adapterId: "test-1" });
    });

    it("should emit error event on connect failure", async () => {
      const adapter = createMockAdapter("test-1");
      const error = new Error("Connection failed");
      (adapter.connect as ReturnType<typeof vi.fn>).mockRejectedValue(error);
      registry.register(adapter);

      const events: ChannelEvent[] = [];
      registry.onEvent((e) => events.push(e));

      await expect(registry.connectAll()).rejects.toThrow("Connection failed");
      expect(events).toContainEqual({ type: "error", adapterId: "test-1", error });
    });
  });

  describe("disconnectAll", () => {
    it("should disconnect all adapters", async () => {
      const adapter1 = createMockAdapter("test-1");
      const adapter2 = createMockAdapter("test-2");
      registry.register(adapter1);
      registry.register(adapter2);

      await registry.disconnectAll();

      expect(adapter1.disconnect).toHaveBeenCalled();
      expect(adapter2.disconnect).toHaveBeenCalled();
    });

    it("should emit disconnected events", async () => {
      const adapter = createMockAdapter("test-1");
      registry.register(adapter);

      const events: ChannelEvent[] = [];
      registry.onEvent((e) => events.push(e));

      await registry.disconnectAll();

      expect(events).toContainEqual({ type: "disconnected", adapterId: "test-1" });
    });

    it("should emit error event on disconnect failure", async () => {
      const adapter = createMockAdapter("test-1");
      const error = new Error("Disconnect failed");
      (adapter.disconnect as ReturnType<typeof vi.fn>).mockRejectedValue(error);
      registry.register(adapter);

      const events: ChannelEvent[] = [];
      registry.onEvent((e) => events.push(e));

      await registry.disconnectAll();
      expect(events).toContainEqual({ type: "error", adapterId: "test-1", error });
    });
  });

  describe("setMessageHandler", () => {
    it("should set global message handler", async () => {
      const adapter = createMockAdapter("test-1");
      registry.register(adapter);

      const handler = vi.fn().mockResolvedValue("response");
      registry.setMessageHandler(handler);

      const message: ChannelMessage = {
        channelId: "test-1",
        userId: "user-1",
        text: "Hello",
        timestamp: new Date(),
        raw: {},
      };

      await adapter.triggerMessage(message);

      expect(handler).toHaveBeenCalledWith(message);
    });
  });

  describe("onEvent", () => {
    it("should register event handler", async () => {
      const adapter = createMockAdapter("test-1");
      registry.register(adapter);

      const events: ChannelEvent[] = [];
      registry.onEvent((e) => events.push(e));

      const message: ChannelMessage = {
        channelId: "test-1",
        userId: "user-1",
        text: "Hello",
        timestamp: new Date(),
        raw: {},
      };

      await adapter.triggerMessage(message);

      expect(events).toHaveLength(1);
      expect(events[0].type).toBe("message");
    });

    it("should handle event handler errors gracefully", async () => {
      const adapter = createMockAdapter("test-1");
      registry.register(adapter);

      registry.onEvent(() => {
        throw new Error("Handler error");
      });

      const message: ChannelMessage = {
        channelId: "test-1",
        userId: "user-1",
        text: "Hello",
        timestamp: new Date(),
        raw: {},
      };

      // Should not throw
      await expect(adapter.triggerMessage(message)).resolves.toBeUndefined();
    });
  });
});

