/**
 * Slack Channel Adapter for AG3NT Gateway.
 *
 * Implements the IChannelAdapter interface for Slack messaging.
 * Uses Socket Mode for real-time messaging (no public endpoint needed).
 */

import type {
  IChannelAdapter,
  ChannelMessage,
  ChannelResponse,
  MessageHandler,
} from "../types.js";
import type { SlackConfig } from "../../config/schema.js";
import type { App as SlackAppType } from "@slack/bolt";

export interface SlackAdapterOptions {
  botToken: string;
  appToken: string;
  signingSecret?: string;
  adapterId?: string;
}

export class SlackAdapter implements IChannelAdapter {
  readonly type = "slack";
  readonly id: string;

  private botToken: string;
  private appToken: string;
  private signingSecret?: string;
  private app: SlackAppType | null = null;
  private connected = false;
  private messageHandler: MessageHandler = async () => undefined;
  private botUserId: string | null = null;

  constructor(options: SlackAdapterOptions) {
    this.botToken = options.botToken;
    this.appToken = options.appToken;
    this.signingSecret = options.signingSecret;
    this.id = options.adapterId || `slack-${Date.now()}`;
  }

  /**
   * Create a SlackAdapter from config.
   */
  static fromConfig(config: SlackConfig): SlackAdapter | null {
    if (!config.enabled || !config.botToken || !config.appToken) {
      return null;
    }
    return new SlackAdapter({
      botToken: config.botToken,
      appToken: config.appToken,
      signingSecret: config.signingSecret,
    });
  }

  async connect(): Promise<void> {
    if (this.connected) return;

    try {
      // Dynamic import to avoid requiring the package if not used
      const { App } = await import("@slack/bolt");

      this.app = new App({
        token: this.botToken,
        appToken: this.appToken,
        socketMode: true,
        signingSecret: this.signingSecret || "not-used-in-socket-mode",
      });

      // Get bot user ID to filter out own messages
      const authResult = await this.app.client.auth.test();
      this.botUserId = authResult.user_id as string;
      console.log(`[SlackAdapter] Bot user ID: ${this.botUserId}`);

      // Handle incoming messages
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      this.app.message(async ({ message, say }: { message: any; say: any }) => {
        // Ignore bot's own messages and messages without text
        if (!message.user || message.user === this.botUserId || !message.text) {
          return;
        }

        // Build channel message
        const channelMessage: ChannelMessage = {
          id: message.ts || Date.now().toString(),
          channelType: this.type,
          channelId: this.id,
          chatId: message.channel || "",
          userId: message.user,
          userName: undefined, // Slack doesn't include username in message events
          text: message.text,
          timestamp: message.ts ? new Date(parseFloat(message.ts) * 1000) : new Date(),
          metadata: { raw: message },
        };

        try {
          const response = await this.messageHandler(channelMessage);
          if (response) {
            await say(response.text);
          }
        } catch (error) {
          console.error("[SlackAdapter] Error handling message:", error);
        }
      });

      // Handle errors
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      this.app.error(async (error: any) => {
        console.error("[SlackAdapter] Error:", error);
      });

      // Start the app
      await this.app.start();
      this.connected = true;
      console.log(`[SlackAdapter] Connected: ${this.id}`);
    } catch (error) {
      console.error("[SlackAdapter] Failed to connect:", error);
      throw error;
    }
  }

  async disconnect(): Promise<void> {
    if (!this.connected || !this.app) return;

    await this.app.stop();
    this.app = null;
    this.connected = false;
    console.log(`[SlackAdapter] Disconnected: ${this.id}`);
  }

  isConnected(): boolean {
    return this.connected;
  }

  async send(chatId: string, response: ChannelResponse): Promise<void> {
    if (!this.app) {
      throw new Error("Slack app not connected");
    }

    await this.app.client.chat.postMessage({
      channel: chatId,
      text: response.text,
      ...(response.replyToMessageId && { thread_ts: response.replyToMessageId }),
    });
  }

  onMessage(handler: MessageHandler): void {
    this.messageHandler = handler;
  }
}

