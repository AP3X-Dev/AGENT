/**
 * Activation checker for group channel messages.
 *
 * Controls when the bot should respond based on the session's
 * activation mode (always, mention, reply, keyword, off).
 */
import type { ChannelMessage } from './types.js';
import type { EnhancedSession } from '../session/SessionStore.js';
import type { ActivationMode } from '../session/SessionStore.js';

// ─────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────

export interface BotInfo {
  id: string;
  username: string;
  displayName: string;
}

export interface ActivationResult {
  shouldActivate: boolean;
  reason: string;
  matchedRule: string;
}

// ─────────────────────────────────────────────────────────────────
// ActivationChecker
// ─────────────────────────────────────────────────────────────────

export class ActivationChecker {
  private botInfo: BotInfo | null = null;

  setBotInfo(info: BotInfo): void {
    this.botInfo = info;
  }

  getBotInfo(): BotInfo | null {
    return this.botInfo;
  }

  shouldActivate(
    message: ChannelMessage,
    session: EnhancedSession,
    botInfo?: BotInfo,
  ): ActivationResult {
    const info = botInfo || this.botInfo;
    const mode: ActivationMode = session.activationMode;

    switch (mode) {
      case 'always':
        return { shouldActivate: true, reason: 'Activation mode is always', matchedRule: 'always' };

      case 'off':
        return { shouldActivate: false, reason: 'Activation mode is off', matchedRule: 'off' };

      case 'mention':
        return this.checkMention(message, info);

      case 'reply':
        return this.checkReply(message, info);

      case 'keyword':
        return this.checkKeyword(message, session);

      default:
        return { shouldActivate: true, reason: 'Unknown mode, defaulting to always', matchedRule: 'default' };
    }
  }

  private checkMention(message: ChannelMessage, botInfo: BotInfo | null): ActivationResult {
    if (!botInfo) {
      return { shouldActivate: false, reason: 'No bot info configured for mention detection', matchedRule: 'mention' };
    }

    const text = message.text.toLowerCase();
    const mentions = (message as any).mentions as string[] | undefined;

    // Check explicit mentions array if provided by the channel adapter
    if (mentions && mentions.length > 0) {
      if (mentions.includes(botInfo.id) || mentions.includes(botInfo.username)) {
        return { shouldActivate: true, reason: `Mentioned via mentions array`, matchedRule: 'mention' };
      }
    }

    // Check text for @username or @id patterns
    const usernamePattern = `@${botInfo.username.toLowerCase()}`;
    const idPattern = `@${botInfo.id.toLowerCase()}`;
    const displayPattern = `@${botInfo.displayName.toLowerCase()}`;

    if (text.includes(usernamePattern) || text.includes(idPattern) || text.includes(displayPattern)) {
      return { shouldActivate: true, reason: 'Bot mentioned in message text', matchedRule: 'mention' };
    }

    return { shouldActivate: false, reason: 'Bot not mentioned', matchedRule: 'mention' };
  }

  private checkReply(message: ChannelMessage, botInfo: BotInfo | null): ActivationResult {
    const isReply = (message as any).isReply as boolean | undefined;
    const replyToMessageId = (message as any).replyToMessageId as string | undefined;

    if (isReply || replyToMessageId || message.replyTo) {
      return { shouldActivate: true, reason: 'Message is a reply', matchedRule: 'reply' };
    }

    return { shouldActivate: false, reason: 'Message is not a reply', matchedRule: 'reply' };
  }

  private checkKeyword(message: ChannelMessage, session: EnhancedSession): ActivationResult {
    const keywords = session.activationKeywords;
    if (!keywords || keywords.length === 0) {
      return { shouldActivate: false, reason: 'No activation keywords configured', matchedRule: 'keyword' };
    }

    const text = message.text.toLowerCase();

    for (const keyword of keywords) {
      if (text.includes(keyword.toLowerCase())) {
        return {
          shouldActivate: true,
          reason: `Keyword matched: "${keyword}"`,
          matchedRule: `keyword:${keyword}`,
        };
      }
    }

    return { shouldActivate: false, reason: 'No keywords matched', matchedRule: 'keyword' };
  }
}
