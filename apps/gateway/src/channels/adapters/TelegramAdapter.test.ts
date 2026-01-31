/**
 * Unit tests for TelegramAdapter.
 *
 * Tests the Telegram channel adapter with mocked telegram bot API.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { TelegramAdapter } from './TelegramAdapter.js';
import type { ChannelMessage, ChannelResponse } from '../types.js';

// Mock node-telegram-bot-api
const mockSendMessage = vi.fn();
const mockStopPolling = vi.fn();
const mockOn = vi.fn();

const MockTelegramBot = vi.fn().mockImplementation(() => ({
  sendMessage: mockSendMessage,
  stopPolling: mockStopPolling,
  on: mockOn,
}));

vi.mock('node-telegram-bot-api', () => ({
  default: MockTelegramBot,
}));

describe('TelegramAdapter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Constructor', () => {
    it('should create adapter with required options', () => {
      const adapter = new TelegramAdapter({
        botToken: 'test-token',
      });

      expect(adapter.type).toBe('telegram');
      expect(adapter.id).toMatch(/^telegram-/);
    });

    it('should use custom adapter ID if provided', () => {
      const adapter = new TelegramAdapter({
        botToken: 'test-token',
        adapterId: 'custom-id',
      });

      expect(adapter.id).toBe('custom-id');
    });

    it('should use default polling interval', () => {
      const adapter = new TelegramAdapter({
        botToken: 'test-token',
      });

      expect(adapter).toBeDefined();
    });
  });

  describe('fromConfig', () => {
    it('should create adapter from config when enabled', () => {
      const config = {
        enabled: true,
        botToken: 'test-token',
        pollingInterval: 2000,
      };

      const adapter = TelegramAdapter.fromConfig(config);

      expect(adapter).not.toBeNull();
      expect(adapter?.type).toBe('telegram');
    });

    it('should return null when disabled', () => {
      const config = {
        enabled: false,
        botToken: 'test-token',
      };

      const adapter = TelegramAdapter.fromConfig(config);

      expect(adapter).toBeNull();
    });

    it('should return null when botToken is missing', () => {
      const config = {
        enabled: true,
        botToken: '',
      };

      const adapter = TelegramAdapter.fromConfig(config);

      expect(adapter).toBeNull();
    });
  });

  describe('connect', () => {
    it('should initialize telegram bot on connect', async () => {
      const adapter = new TelegramAdapter({
        botToken: 'test-token',
      });

      await adapter.connect();

      expect(MockTelegramBot).toHaveBeenCalledWith('test-token', {
        polling: {
          interval: 1000,
          autoStart: true,
        },
      });
      expect(adapter.isConnected()).toBe(true);
    });

    it('should not reconnect if already connected', async () => {
      const adapter = new TelegramAdapter({
        botToken: 'test-token',
      });

      await adapter.connect();
      await adapter.connect();

      expect(MockTelegramBot).toHaveBeenCalledTimes(1);
    });

    it('should register message handler', async () => {
      const adapter = new TelegramAdapter({
        botToken: 'test-token',
      });

      await adapter.connect();

      expect(mockOn).toHaveBeenCalledWith('message', expect.any(Function));
    });

    it('should register polling error handler', async () => {
      const adapter = new TelegramAdapter({
        botToken: 'test-token',
      });

      await adapter.connect();

      expect(mockOn).toHaveBeenCalledWith('polling_error', expect.any(Function));
    });
  });

  describe('disconnect', () => {
    it('should stop polling on disconnect', async () => {
      const adapter = new TelegramAdapter({
        botToken: 'test-token',
      });

      await adapter.connect();
      await adapter.disconnect();

      expect(mockStopPolling).toHaveBeenCalled();
      expect(adapter.isConnected()).toBe(false);
    });

    it('should not disconnect if not connected', async () => {
      const adapter = new TelegramAdapter({
        botToken: 'test-token',
      });

      await adapter.disconnect();

      expect(mockStopPolling).not.toHaveBeenCalled();
    });
  });

  describe('send', () => {
    it('should send message to chat', async () => {
      const adapter = new TelegramAdapter({
        botToken: 'test-token',
      });

      await adapter.connect();

      const response: ChannelResponse = {
        text: 'Hello, world!',
      };

      await adapter.send('123456', response);

      expect(mockSendMessage).toHaveBeenCalledWith(
        123456,
        'Hello, world!',
        expect.objectContaining({
          parse_mode: 'Markdown',
        })
      );
    });

    it('should include reply_to_message_id when provided', async () => {
      const adapter = new TelegramAdapter({
        botToken: 'test-token',
      });

      await adapter.connect();

      const response: ChannelResponse = {
        text: 'Reply message',
        replyToMessageId: '789',
      };

      await adapter.send('123456', response);

      expect(mockSendMessage).toHaveBeenCalledWith(
        123456,
        'Reply message',
        expect.objectContaining({
          parse_mode: 'Markdown',
          reply_to_message_id: 789,
        })
      );
    });

    it('should throw error if not connected', async () => {
      const adapter = new TelegramAdapter({
        botToken: 'test-token',
      });

      const response: ChannelResponse = {
        text: 'Test',
      };

      await expect(adapter.send('123', response)).rejects.toThrow(
        'Telegram bot not connected'
      );
    });
  });

  describe('onMessage', () => {
    it('should register message handler', async () => {
      const adapter = new TelegramAdapter({
        botToken: 'test-token',
      });

      const handler = vi.fn();
      adapter.onMessage(handler);

      await adapter.connect();

      // Simulate incoming message
      const messageHandler = mockOn.mock.calls.find(
        (call) => call[0] === 'message'
      )?.[1];

      expect(messageHandler).toBeDefined();

      // Simulate a message
      const mockMessage = {
        message_id: 1,
        from: {
          id: 123,
          username: 'testuser',
          first_name: 'Test',
        },
        chat: {
          id: 456,
        },
        text: 'Hello bot',
        date: Math.floor(Date.now() / 1000),
      };

      if (messageHandler) {
        await messageHandler(mockMessage);

        expect(handler).toHaveBeenCalledWith(
          expect.objectContaining({
            channelType: 'telegram',
            userId: '123',
            userName: 'testuser',
            text: 'Hello bot',
            chatId: '456',
          })
        );
      }
    });
  });

  describe('isConnected', () => {
    it('should return false when not connected', () => {
      const adapter = new TelegramAdapter({
        botToken: 'test-token',
      });

      expect(adapter.isConnected()).toBe(false);
    });

    it('should return true when connected', async () => {
      const adapter = new TelegramAdapter({
        botToken: 'test-token',
      });

      await adapter.connect();

      expect(adapter.isConnected()).toBe(true);
    });
  });
});
