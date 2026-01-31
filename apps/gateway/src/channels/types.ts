/**
 * Channel abstraction types for AG3NT multi-channel messaging.
 *
 * This module defines the unified message format and channel adapter interface
 * that all channel implementations must follow.
 */

/**
 * Unified message format for all channels.
 * Each channel adapter normalizes incoming messages to this format.
 */
export interface ChannelMessage {
  /** Unique message ID (channel-specific) */
  id: string;
  /** Channel type identifier (e.g., 'cli', 'telegram', 'discord', 'slack') */
  channelType: string;
  /** Channel instance ID (e.g., bot account ID) */
  channelId: string;
  /** Conversation/chat identifier */
  chatId: string;
  /** Sender identifier (user ID on the platform) */
  userId: string;
  /** Display name of the sender (if available) */
  userName?: string;
  /** Message text content */
  text: string;
  /** When the message was sent */
  timestamp: Date;
  /** Optional metadata from the channel */
  metadata?: Record<string, unknown>;
  /** For reply threading (original message ID) */
  replyTo?: string;
}

/**
 * Response to be sent back through a channel.
 */
export interface ChannelResponse {
  /** Text content of the response */
  text: string;
  /** Optional metadata for the response */
  metadata?: Record<string, unknown>;
  /** Optional attachments (files, images, etc.) */
  attachments?: ChannelAttachment[];
  /** Optional: reply to a specific message */
  replyToMessageId?: string;
}

/**
 * Attachment in a channel response.
 */
export interface ChannelAttachment {
  type: "file" | "image" | "audio" | "video" | "document";
  url?: string;
  data?: Buffer;
  filename?: string;
  mimeType?: string;
}

/**
 * Handler function for incoming messages.
 */
export type MessageHandler = (
  message: ChannelMessage
) => Promise<ChannelResponse | void>;

/**
 * Channel adapter interface.
 * All channel implementations must implement this interface.
 */
export interface IChannelAdapter {
  /** Channel type identifier (e.g., 'telegram', 'discord') */
  readonly type: string;

  /** Unique adapter instance ID */
  readonly id: string;

  /**
   * Connect to the channel service.
   * This should initialize connections, authenticate, and start listening.
   */
  connect(): Promise<void>;

  /**
   * Disconnect from the channel service.
   * This should cleanly close connections and stop listening.
   */
  disconnect(): Promise<void>;

  /**
   * Check if the adapter is currently connected.
   */
  isConnected(): boolean;

  /**
   * Send a response to a specific chat.
   * @param chatId - The chat/conversation to send to
   * @param response - The response content
   */
  send(chatId: string, response: ChannelResponse): Promise<void>;

  /**
   * Register a message handler for incoming messages.
   * The handler will be called for each incoming message.
   * @param handler - Function to handle incoming messages
   */
  onMessage(handler: MessageHandler): void;
}

/**
 * Base configuration for channel adapters.
 * Specific channels will extend this with their own config.
 */
export interface ChannelAdapterConfig {
  /** Channel type (must match adapter type) */
  type: string;
  /** Whether this channel is enabled */
  enabled: boolean;
}

/**
 * DM (Direct Message) security policy.
 */
export type DMPolicy = "open" | "pairing";

/**
 * Generate a session ID from channel and chat info.
 * Session IDs are used for agent context isolation.
 */
export function generateSessionId(
  channelType: string,
  channelId: string,
  chatId: string
): string {
  return `${channelType}:${channelId}:${chatId}`;
}

/**
 * Parse a session ID back into its components.
 */
export function parseSessionId(sessionId: string): {
  channelType: string;
  channelId: string;
  chatId: string;
} | null {
  const parts = sessionId.split(":");
  if (parts.length < 3) return null;
  return {
    channelType: parts[0],
    channelId: parts[1],
    chatId: parts.slice(2).join(":"), // chatId may contain colons
  };
}

