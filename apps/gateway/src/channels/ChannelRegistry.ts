/**
 * Channel Registry for AG3NT Gateway.
 *
 * Manages registration and lifecycle of channel adapters.
 */

import type {
  IChannelAdapter,
  MessageHandler,
  ChannelMessage,
  ChannelResponse,
} from "./types.js";

/**
 * Event emitted when a channel adapter state changes.
 */
export type ChannelEvent =
  | { type: "connected"; adapterId: string }
  | { type: "disconnected"; adapterId: string }
  | { type: "error"; adapterId: string; error: Error }
  | { type: "message"; adapterId: string; message: ChannelMessage };

export type ChannelEventHandler = (event: ChannelEvent) => void;

/**
 * Manages all channel adapters in the Gateway.
 */
export class ChannelRegistry {
  private adapters: Map<string, IChannelAdapter> = new Map();
  private eventHandlers: ChannelEventHandler[] = [];
  private globalMessageHandler: MessageHandler | null = null;

  /**
   * Register a channel adapter.
   * @param adapter - The adapter to register
   */
  register(adapter: IChannelAdapter): void {
    if (this.adapters.has(adapter.id)) {
      throw new Error(`Adapter already registered: ${adapter.id}`);
    }

    // Wire up the message handler
    adapter.onMessage(async (message) => {
      // Emit event
      this.emit({ type: "message", adapterId: adapter.id, message });

      // Call global handler if set
      if (this.globalMessageHandler) {
        return this.globalMessageHandler(message);
      }
      return undefined;
    });

    this.adapters.set(adapter.id, adapter);
  }

  /**
   * Unregister a channel adapter.
   * Will disconnect if currently connected.
   * @param adapterId - The adapter ID to unregister
   */
  async unregister(adapterId: string): Promise<void> {
    const adapter = this.adapters.get(adapterId);
    if (!adapter) return;

    if (adapter.isConnected()) {
      await adapter.disconnect();
    }

    this.adapters.delete(adapterId);
  }

  /**
   * Get an adapter by ID.
   */
  get(adapterId: string): IChannelAdapter | undefined {
    return this.adapters.get(adapterId);
  }

  /**
   * Get all adapters of a specific type.
   */
  getByType(type: string): IChannelAdapter[] {
    return Array.from(this.adapters.values()).filter((a) => a.type === type);
  }

  /**
   * Get all registered adapters.
   */
  all(): IChannelAdapter[] {
    return Array.from(this.adapters.values());
  }

  /**
   * Connect all registered adapters.
   */
  async connectAll(): Promise<void> {
    const connectPromises = Array.from(this.adapters.values()).map(
      async (adapter) => {
        try {
          await adapter.connect();
          this.emit({ type: "connected", adapterId: adapter.id });
        } catch (error) {
          this.emit({
            type: "error",
            adapterId: adapter.id,
            error: error instanceof Error ? error : new Error(String(error)),
          });
          throw error;
        }
      }
    );

    await Promise.all(connectPromises);
  }

  /**
   * Disconnect all registered adapters.
   */
  async disconnectAll(): Promise<void> {
    const disconnectPromises = Array.from(this.adapters.values()).map(
      async (adapter) => {
        try {
          await adapter.disconnect();
          this.emit({ type: "disconnected", adapterId: adapter.id });
        } catch (error) {
          this.emit({
            type: "error",
            adapterId: adapter.id,
            error: error instanceof Error ? error : new Error(String(error)),
          });
        }
      }
    );

    await Promise.all(disconnectPromises);
  }

  /**
   * Set the global message handler for all adapters.
   * This is called when any adapter receives a message.
   */
  setMessageHandler(handler: MessageHandler): void {
    this.globalMessageHandler = handler;
  }

  /**
   * Register an event handler for channel events.
   */
  onEvent(handler: ChannelEventHandler): void {
    this.eventHandlers.push(handler);
  }

  private emit(event: ChannelEvent): void {
    for (const handler of this.eventHandlers) {
      try {
        handler(event);
      } catch {
        // Ignore handler errors
      }
    }
  }
}

