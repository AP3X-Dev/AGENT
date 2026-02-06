/**
 * Tests for Gateway Router.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createRouter, type RouterDependencies } from './router.js';
import { SessionManager } from '../session/SessionManager.js';
import type { Config } from '../config/schema.js';
import type { ChannelMessage } from '../channels/types.js';

// Mock fetch globally
global.fetch = vi.fn();

describe('Router', () => {
  let config: Config;
  let sessionManager: SessionManager;
  let router: ReturnType<typeof createRouter>;

  beforeEach(() => {
    vi.clearAllMocks();

    // Create minimal config
    config = {
      gateway: { port: 18789, httpPath: '/api', wsPath: '/ws' },
      agent: { url: 'http://localhost:18790' },
      security: { defaultDMPolicy: 'require-pairing', allowlist: [] },
      channels: [],
      scheduler: { heartbeatEnabled: false, heartbeatInterval: 60 },
      skills: { bundledPath: './skills' },
      storage: { allowlistPath: './.ag3nt/allowlist.json', dbPath: './.ag3nt/db.sqlite' },
      modelProvider: { provider: 'openai', model: 'gpt-4' },
    } as Config;

    sessionManager = new SessionManager({
      dmPolicy: 'require-pairing',
    });

    const deps: RouterDependencies = { sessionManager };
    router = createRouter(config, deps);

    // Clear any pending approvals from previous tests
    // The pendingApprovals Map is module-level, so it persists across router instances
    router.cancelPendingApproval('telegram:bot-1:chat-123');
    router.cancelPendingApproval('cli:local:test');
  });

  describe('Pairing Flow', () => {
    it('should require pairing for unpaired session', async () => {
      const message: ChannelMessage = {
        channelType: 'telegram',
        channelId: 'bot-1',
        chatId: 'chat-123',
        userId: 'user-456',
        userName: 'John Doe',
        text: 'Hello',
        timestamp: new Date(),
      };

      const response = await router.handleChannelMessage(message);

      expect(response.text).toContain('pairing code');
      expect(response.metadata?.pairingRequired).toBe(true);
      expect(response.metadata?.pairingCode).toBeDefined();
    });

    it('should allow message after pairing', async () => {
      // Mock worker response
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'telegram:bot-1:chat-123',
          text: 'Hello! How can I help?',
          events: [],
        }),
      });

      const message: ChannelMessage = {
        channelType: 'telegram',
        channelId: 'bot-1',
        chatId: 'chat-123',
        userId: 'user-456',
        text: 'Hello',
        timestamp: new Date(),
      };

      // Manually approve the session
      const session = sessionManager.getOrCreateSession(
        message.channelType,
        message.channelId,
        message.chatId,
        message.userId
      );
      await sessionManager.manualApprove(session.id);

      const response = await router.handleChannelMessage(message);

      expect(response.text).toBe('Hello! How can I help?');
      expect(response.metadata?.pairingRequired).toBeUndefined();
    });
  });

  describe('Open DM Policy', () => {
    beforeEach(() => {
      sessionManager = new SessionManager({
        dmPolicy: 'open',
      });
      const deps: RouterDependencies = { sessionManager };
      router = createRouter(config, deps);
    });

    it('should not require pairing in open mode', async () => {
      // Mock worker response
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'telegram:bot-1:chat-123',
          text: 'Hello! How can I help?',
          events: [],
        }),
      });

      const message: ChannelMessage = {
        channelType: 'telegram',
        channelId: 'bot-1',
        chatId: 'chat-123',
        userId: 'user-456',
        text: 'Hello',
        timestamp: new Date(),
      };

      const response = await router.handleChannelMessage(message);

      expect(response.text).toBe('Hello! How can I help?');
      expect(response.metadata?.pairingRequired).toBeUndefined();
    });
  });

  describe('Worker Communication', () => {
    beforeEach(async () => {
      // Pre-approve session for these tests
      const session = sessionManager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );
      await sessionManager.manualApprove(session.id);
    });

    it('should forward message to worker', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'telegram:bot-1:chat-123',
          text: 'Response from worker',
          events: [],
        }),
      });

      const message: ChannelMessage = {
        channelType: 'telegram',
        channelId: 'bot-1',
        chatId: 'chat-123',
        userId: 'user-456',
        text: 'Test message',
        timestamp: new Date(),
      };

      await router.handleChannelMessage(message);

      expect(global.fetch).toHaveBeenCalledWith(
        'http://127.0.0.1:18790/turn',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            'Connection': 'keep-alive',
          }),
        })
      );
    });

    it('should handle worker error', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        ok: false,
        status: 500,
        text: async () => 'Internal server error',
      });

      const message: ChannelMessage = {
        channelType: 'telegram',
        channelId: 'bot-1',
        chatId: 'chat-123',
        userId: 'user-456',
        text: 'Test message',
        timestamp: new Date(),
      };

      const response = await router.handleChannelMessage(message);

      expect(response.text).toContain('error');
      expect(response.metadata?.error).toBe(true);
    });

    it('should handle network error', async () => {
      (global.fetch as any).mockRejectedValue(new Error('Network error'));

      const message: ChannelMessage = {
        channelType: 'telegram',
        channelId: 'bot-1',
        chatId: 'chat-123',
        userId: 'user-456',
        text: 'Test message',
        timestamp: new Date(),
      };

      const response = await router.handleChannelMessage(message);

      expect(response.text).toContain('error');
      expect(response.text).toContain('Network error');
      expect(response.metadata?.error).toBe(true);
    });
  });

  describe('Interrupt Handling', () => {
    beforeEach(async () => {
      // Pre-approve session for these tests
      const session = sessionManager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );
      await sessionManager.manualApprove(session.id);
    });

    it('should handle interrupt from worker', async () => {
      const interrupt = {
        interrupt_id: 'int-123',
        pending_actions: [
          {
            tool_name: 'shell',
            args: { command: 'rm -rf /' },
            description: '**Shell Command**: `rm -rf /`',
          },
        ],
        action_count: 1,
      };

      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'telegram:bot-1:chat-123',
          text: 'Need approval',
          events: [],
          interrupt,
        }),
      });

      const message: ChannelMessage = {
        channelType: 'telegram',
        channelId: 'bot-1',
        chatId: 'chat-123',
        userId: 'user-456',
        text: 'Delete everything',
        timestamp: new Date(),
      };

      const response = await router.handleChannelMessage(message);

      expect(response.text).toContain('Approval Required');
      expect(response.text).toContain('rm -rf /');
      expect(response.metadata?.approvalPending).toBe(true);
      expect(response.metadata?.pendingActions).toEqual(interrupt.pending_actions);
    });
  });

  describe('Approval Flow', () => {
    it('should handle approve response', async () => {
      // Pre-approve session
      const session = sessionManager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );
      await sessionManager.manualApprove(session.id);

      // Mock 1: Initial message that triggers interrupt
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'telegram:bot-1:chat-123',
          text: 'Need approval',
          events: [],
          interrupt: {
            interrupt_id: 'int-123',
            pending_actions: [
              {
                tool_name: 'shell',
                args: { command: 'ls -la' },
                description: '**Shell Command**: `ls -la`',
              },
            ],
            action_count: 1,
          },
        }),
      });

      // Mock 2: Resume response after approval
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'telegram:bot-1:chat-123',
          text: 'Command executed successfully',
          events: [],
        }),
      });

      // Send initial message to create pending approval
      await router.handleChannelMessage({
        channelType: 'telegram',
        channelId: 'bot-1',
        chatId: 'chat-123',
        userId: 'user-456',
        text: 'List files',
        timestamp: new Date(),
      });

      // Send approval
      const response = await router.handleChannelMessage({
        channelType: 'telegram',
        channelId: 'bot-1',
        chatId: 'chat-123',
        userId: 'user-456',
        text: 'approve',
        timestamp: new Date(),
      });

      expect(response.text).toBe('Command executed successfully');
      expect(response.metadata?.approvalPending).toBeUndefined();
    });

    it('should handle reject response', async () => {
      // Pre-approve session
      const session = sessionManager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );
      await sessionManager.manualApprove(session.id);

      // Mock 1: Initial message that triggers interrupt
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'telegram:bot-1:chat-123',
          text: 'Need approval',
          events: [],
          interrupt: {
            interrupt_id: 'int-123',
            pending_actions: [
              {
                tool_name: 'shell',
                args: { command: 'ls -la' },
                description: '**Shell Command**: `ls -la`',
              },
            ],
            action_count: 1,
          },
        }),
      });

      // Mock 2: Resume response after rejection
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'telegram:bot-1:chat-123',
          text: 'Action cancelled',
          events: [],
        }),
      });

      // Send initial message to create pending approval
      await router.handleChannelMessage({
        channelType: 'telegram',
        channelId: 'bot-1',
        chatId: 'chat-123',
        userId: 'user-456',
        text: 'List files',
        timestamp: new Date(),
      });

      // Send rejection
      const response = await router.handleChannelMessage({
        channelType: 'telegram',
        channelId: 'bot-1',
        chatId: 'chat-123',
        userId: 'user-456',
        text: 'reject',
        timestamp: new Date(),
      });

      expect(response.text).toBe('Action cancelled');
      expect(response.metadata?.approvalPending).toBeUndefined();
    });

    it('should handle "yes" as approval', async () => {
      // Pre-approve session
      const session = sessionManager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );
      await sessionManager.manualApprove(session.id);

      // Mock 1: Initial message that triggers interrupt
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'telegram:bot-1:chat-123',
          text: 'Need approval',
          events: [],
          interrupt: {
            interrupt_id: 'int-123',
            pending_actions: [
              {
                tool_name: 'shell',
                args: { command: 'ls -la' },
                description: '**Shell Command**: `ls -la`',
              },
            ],
            action_count: 1,
          },
        }),
      });

      // Mock 2: Resume response after "yes"
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'telegram:bot-1:chat-123',
          text: 'Done',
          events: [],
        }),
      });

      // Send initial message to create pending approval
      await router.handleChannelMessage({
        channelType: 'telegram',
        channelId: 'bot-1',
        chatId: 'chat-123',
        userId: 'user-456',
        text: 'List files',
        timestamp: new Date(),
      });

      // Send "yes" approval
      const response = await router.handleChannelMessage({
        channelType: 'telegram',
        channelId: 'bot-1',
        chatId: 'chat-123',
        userId: 'user-456',
        text: 'yes',
        timestamp: new Date(),
      });

      expect(response.text).toBe('Done');
    });

    it('should handle "no" as rejection', async () => {
      // Pre-approve session
      const session = sessionManager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );
      await sessionManager.manualApprove(session.id);

      // Mock 1: Initial message that triggers interrupt
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'telegram:bot-1:chat-123',
          text: 'Need approval',
          events: [],
          interrupt: {
            interrupt_id: 'int-123',
            pending_actions: [
              {
                tool_name: 'shell',
                args: { command: 'ls -la' },
                description: '**Shell Command**: `ls -la`',
              },
            ],
            action_count: 1,
          },
        }),
      });

      // Mock 2: Resume response after "no"
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'telegram:bot-1:chat-123',
          text: 'Cancelled',
          events: [],
        }),
      });

      // Send initial message to create pending approval
      await router.handleChannelMessage({
        channelType: 'telegram',
        channelId: 'bot-1',
        chatId: 'chat-123',
        userId: 'user-456',
        text: 'List files',
        timestamp: new Date(),
      });

      // Send "no" rejection
      const response = await router.handleChannelMessage({
        channelType: 'telegram',
        channelId: 'bot-1',
        chatId: 'chat-123',
        userId: 'user-456',
        text: 'no',
        timestamp: new Date(),
      });

      expect(response.text).toBe('Cancelled');
    });

    it('should prompt again for non-approval response while pending', async () => {
      // Pre-approve session
      const session = sessionManager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );
      await sessionManager.manualApprove(session.id);

      // Mock: Initial message that triggers interrupt
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'telegram:bot-1:chat-123',
          text: 'Need approval',
          events: [],
          interrupt: {
            interrupt_id: 'int-123',
            pending_actions: [
              {
                tool_name: 'shell',
                args: { command: 'ls -la' },
                description: '**Shell Command**: `ls -la`',
              },
            ],
            action_count: 1,
          },
        }),
      });

      // Send initial message to create pending approval
      await router.handleChannelMessage({
        channelType: 'telegram',
        channelId: 'bot-1',
        chatId: 'chat-123',
        userId: 'user-456',
        text: 'List files',
        timestamp: new Date(),
      });

      // Send random message (not approval/rejection)
      const response = await router.handleChannelMessage({
        channelType: 'telegram',
        channelId: 'bot-1',
        chatId: 'chat-123',
        userId: 'user-456',
        text: 'What is the weather?',
        timestamp: new Date(),
      });

      expect(response.text).toContain('waiting for your approval');
      expect(response.text).toContain('approve');
      expect(response.text).toContain('reject');
      expect(response.metadata?.approvalPending).toBe(true);
    });

    it('should handle chained interrupts', async () => {
      // Pre-approve session
      const session = sessionManager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );
      await sessionManager.manualApprove(session.id);

      // Mock 1: Initial message that triggers first interrupt
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'telegram:bot-1:chat-123',
          text: 'Need approval',
          events: [],
          interrupt: {
            interrupt_id: 'int-123',
            pending_actions: [
              {
                tool_name: 'shell',
                args: { command: 'ls -la' },
                description: '**Shell Command**: `ls -la`',
              },
            ],
            action_count: 1,
          },
        }),
      });

      // Mock 2: Resume response that triggers second interrupt
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'telegram:bot-1:chat-123',
          text: 'Need another approval',
          events: [],
          interrupt: {
            interrupt_id: 'int-456',
            pending_actions: [
              {
                tool_name: 'shell',
                args: { command: 'rm file.txt' },
                description: '**Shell Command**: `rm file.txt`',
              },
            ],
            action_count: 1,
          },
        }),
      });

      // Send initial message to create first pending approval
      await router.handleChannelMessage({
        channelType: 'telegram',
        channelId: 'bot-1',
        chatId: 'chat-123',
        userId: 'user-456',
        text: 'List files',
        timestamp: new Date(),
      });

      // Send approval which triggers second interrupt
      const response = await router.handleChannelMessage({
        channelType: 'telegram',
        channelId: 'bot-1',
        chatId: 'chat-123',
        userId: 'user-456',
        text: 'approve',
        timestamp: new Date(),
      });

      expect(response.text).toContain('Approval Required');
      expect(response.text).toContain('rm file.txt');
      expect(response.metadata?.approvalPending).toBe(true);
    });

    it('should handle resume error', async () => {
      // Pre-approve session
      const session = sessionManager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );
      await sessionManager.manualApprove(session.id);

      // Mock 1: Initial message that triggers interrupt
      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'telegram:bot-1:chat-123',
          text: 'Need approval',
          events: [],
          interrupt: {
            interrupt_id: 'int-123',
            pending_actions: [
              {
                tool_name: 'shell',
                args: { command: 'ls -la' },
                description: '**Shell Command**: `ls -la`',
              },
            ],
            action_count: 1,
          },
        }),
      });

      // Mock 2: Resume response with error
      (global.fetch as any).mockResolvedValueOnce({
        ok: false,
        status: 500,
        text: async () => 'Worker error',
      });

      // Send initial message to create pending approval
      await router.handleChannelMessage({
        channelType: 'telegram',
        channelId: 'bot-1',
        chatId: 'chat-123',
        userId: 'user-456',
        text: 'List files',
        timestamp: new Date(),
      });

      // Send approval which triggers error
      const response = await router.handleChannelMessage({
        channelType: 'telegram',
        channelId: 'bot-1',
        chatId: 'chat-123',
        userId: 'user-456',
        text: 'approve',
        timestamp: new Date(),
      });

      expect(response.text).toContain('Error resuming');
      expect(response.metadata?.error).toBe(true);
    });
  });

  describe('WebSocket Message Handling', () => {
    it('should handle valid WebSocket message', async () => {
      // Pre-approve the session
      const session = sessionManager.getOrCreateSession('cli', 'local', 'test', 'user');
      await sessionManager.manualApprove(session.id);

      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'cli:local:test',
          text: 'Response',
          events: [],
        }),
      });

      const wsMessage = {
        session_id: 'cli:local:test',
        text: 'Hello',
      };

      const result = await router.handleWsMessage(wsMessage);

      expect(result.ok).toBe(true);
      expect(result.text).toBe('Response');
    });

    it('should reject invalid WebSocket message', async () => {
      const result = await router.handleWsMessage(null);

      expect(result.ok).toBe(false);
      expect(result.error).toContain('Invalid message format');
    });

    it('should reject WebSocket message without text', async () => {
      const result = await router.handleWsMessage({ session_id: 'test' });

      expect(result.ok).toBe(false);
      expect(result.error).toContain('Missing text field');
    });
  });
});
