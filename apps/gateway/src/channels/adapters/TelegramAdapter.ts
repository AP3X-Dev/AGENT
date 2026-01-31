/**
 * Telegram Channel Adapter for AG3NT Gateway.
 *
 * Implements the IChannelAdapter interface for Telegram messaging.
 * Uses polling mode by default (simpler than webhooks).
 */

import type {
  IChannelAdapter,
  ChannelMessage,
  ChannelResponse,
  MessageHandler,
} from "../types.js";
import type { TelegramConfig } from "../../config/schema.js";
import type TelegramBotType from "node-telegram-bot-api";

// We'll use dynamic import to avoid requiring the package if not used
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let TelegramBot: new (...args: any[]) => TelegramBotType;

export interface TelegramAdapterOptions {
  botToken: string;
  pollingInterval?: number;
  adapterId?: string;
}

export class TelegramAdapter implements IChannelAdapter {
  readonly type = "telegram";
  readonly id: string;

  private bot: TelegramBotType | null = null;
  private messageHandler: MessageHandler | null = null;
  private connected = false;
  private botToken: string;
  private pollingInterval: number;

  constructor(options: TelegramAdapterOptions) {
    this.botToken = options.botToken;
    this.pollingInterval = options.pollingInterval ?? 1000;
    this.id = options.adapterId ?? `telegram-${Date.now()}`;
  }

  /**
   * Create a TelegramAdapter from config.
   */
  static fromConfig(config: TelegramConfig): TelegramAdapter | null {
    if (!config.enabled || !config.botToken) {
      return null;
    }
    return new TelegramAdapter({
      botToken: config.botToken,
      pollingInterval: config.pollingInterval,
    });
  }

  async connect(): Promise<void> {
    if (this.connected) return;

    try {
      // Dynamic import to avoid requiring the package if not used
      const TelegramBotModule = await import("node-telegram-bot-api");
      TelegramBot = TelegramBotModule.default;

      this.bot = new TelegramBot(this.botToken, {
        polling: {
          interval: this.pollingInterval,
          autoStart: true,
        },
      });

      // Set up message handler
      this.bot.on("message", async (msg: TelegramBotType.Message) => {
        if (!msg.text || !this.messageHandler) return;

        const channelMessage: ChannelMessage = {
          id: String(msg.message_id),
          channelType: this.type,
          channelId: this.id,
          chatId: String(msg.chat.id),
          userId: String(msg.from?.id ?? msg.chat.id),
          userName:
            msg.from?.username ||
            [msg.from?.first_name, msg.from?.last_name].filter(Boolean).join(" ") ||
            undefined,
          text: msg.text,
          timestamp: new Date(msg.date * 1000),
          metadata: {
            chatType: msg.chat.type,
            chatTitle: msg.chat.title,
            messageThreadId: msg.message_thread_id,
          },
          replyTo: msg.reply_to_message
            ? String(msg.reply_to_message.message_id)
            : undefined,
        };

        try {
          const response = await this.messageHandler(channelMessage);
          if (response) {
            await this.send(channelMessage.chatId, response);
          }
        } catch (error) {
          console.error("[TelegramAdapter] Error handling message:", error);
        }
      });

      // Handle polling errors
      this.bot.on("polling_error", (error: Error) => {
        console.error("[TelegramAdapter] Polling error:", error.message);
      });

      this.connected = true;
      console.log(`[TelegramAdapter] Connected: ${this.id}`);
    } catch (error) {
      console.error("[TelegramAdapter] Failed to connect:", error);
      throw error;
    }
  }

  async disconnect(): Promise<void> {
    if (!this.connected || !this.bot) return;

    await this.bot.stopPolling();
    this.bot = null;
    this.connected = false;
    console.log(`[TelegramAdapter] Disconnected: ${this.id}`);
  }

  isConnected(): boolean {
    return this.connected;
  }

  async send(chatId: string, response: ChannelResponse): Promise<void> {
    if (!this.bot) {
      throw new Error("Telegram bot not connected");
    }

    const options: TelegramBotType.SendMessageOptions = {};

    if (response.replyToMessageId) {
      options.reply_to_message_id = parseInt(response.replyToMessageId, 10);
    }

    // Use Markdown for formatting
    options.parse_mode = "Markdown";

    await this.bot.sendMessage(parseInt(chatId, 10), response.text, options);
  }

  onMessage(handler: MessageHandler): void {
    this.messageHandler = handler;
  }
}

