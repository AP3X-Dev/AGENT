/**
 * Discord Channel Adapter for AG3NT Gateway.
 *
 * Implements the IChannelAdapter interface for Discord messaging.
 * Handles both guild (server) channels and DMs.
 */

import type {
  IChannelAdapter,
  ChannelMessage,
  ChannelResponse,
  MessageHandler,
} from "../types.js";
import type { DiscordConfig } from "../../config/schema.js";

// Types for discord.js (dynamically imported)
type DiscordClient = import("discord.js").Client;
type DiscordMessage = import("discord.js").Message;

export interface DiscordAdapterOptions {
  botToken: string;
  clientId?: string;
  allowGuilds?: boolean;
  allowDMs?: boolean;
  adapterId?: string;
}

export class DiscordAdapter implements IChannelAdapter {
  readonly type = "discord";
  readonly id: string;

  private client: DiscordClient | null = null;
  private messageHandler: MessageHandler | null = null;
  private connected = false;
  private botToken: string;
  private allowGuilds: boolean;
  private allowDMs: boolean;

  constructor(options: DiscordAdapterOptions) {
    this.botToken = options.botToken;
    this.allowGuilds = options.allowGuilds ?? true;
    this.allowDMs = options.allowDMs ?? true;
    this.id = options.adapterId ?? `discord-${Date.now()}`;
  }

  /**
   * Create a DiscordAdapter from config.
   */
  static fromConfig(config: DiscordConfig): DiscordAdapter | null {
    if (!config.enabled || !config.botToken) {
      return null;
    }
    return new DiscordAdapter({
      botToken: config.botToken,
      clientId: config.clientId,
      allowGuilds: config.allowGuilds,
      allowDMs: config.allowDMs,
    });
  }

  async connect(): Promise<void> {
    if (this.connected) return;

    try {
      // Dynamic import to avoid requiring the package if not used
      const { Client, GatewayIntentBits, Partials } = await import("discord.js");

      this.client = new Client({
        intents: [
          GatewayIntentBits.Guilds,
          GatewayIntentBits.GuildMessages,
          GatewayIntentBits.MessageContent,
          GatewayIntentBits.DirectMessages,
        ],
        partials: [Partials.Channel], // Required for DMs
      });

      // Set up message handler
      this.client.on("messageCreate", async (msg: DiscordMessage) => {
        // Ignore bot messages
        if (msg.author.bot) return;
        if (!msg.content || !this.messageHandler) return;

        // Filter by channel type
        const isDM = msg.channel.isDMBased();
        if (isDM && !this.allowDMs) return;
        if (!isDM && !this.allowGuilds) return;

        const channelMessage: ChannelMessage = {
          id: msg.id,
          channelType: this.type,
          channelId: this.id,
          chatId: msg.channel.id,
          userId: msg.author.id,
          userName: msg.author.username,
          text: msg.content,
          timestamp: msg.createdAt,
          metadata: {
            isDM,
            guildId: msg.guild?.id,
            guildName: msg.guild?.name,
            channelName: "name" in msg.channel ? msg.channel.name : undefined,
          },
          replyTo: msg.reference?.messageId,
        };

        try {
          const response = await this.messageHandler(channelMessage);
          if (response) {
            await this.send(channelMessage.chatId, response);
          }
        } catch (error) {
          console.error("[DiscordAdapter] Error handling message:", error);
        }
      });

      this.client.on("error", (error) => {
        console.error("[DiscordAdapter] Error:", error.message);
      });

      // Login to Discord
      await this.client.login(this.botToken);
      this.connected = true;
      console.log(`[DiscordAdapter] Connected: ${this.id}`);
    } catch (error) {
      console.error("[DiscordAdapter] Failed to connect:", error);
      throw error;
    }
  }

  async disconnect(): Promise<void> {
    if (!this.connected || !this.client) return;

    await this.client.destroy();
    this.client = null;
    this.connected = false;
    console.log(`[DiscordAdapter] Disconnected: ${this.id}`);
  }

  isConnected(): boolean {
    return this.connected;
  }

  async send(chatId: string, response: ChannelResponse): Promise<void> {
    if (!this.client) {
      throw new Error("Discord client not connected");
    }

    const channel = await this.client.channels.fetch(chatId);
    if (!channel || !("send" in channel)) {
      throw new Error(`Cannot send to channel: ${chatId}`);
    }

    await channel.send(response.text);
  }

  onMessage(handler: MessageHandler): void {
    this.messageHandler = handler;
  }
}

