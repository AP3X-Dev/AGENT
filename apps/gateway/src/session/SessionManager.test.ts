/**
 * Tests for SessionManager.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { SessionManager } from './SessionManager.js';
import type { SessionManagerConfig } from './SessionManager.js';

describe('SessionManager', () => {
  let manager: SessionManager;
  let mockAllowlistCallback: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockAllowlistCallback = vi.fn();
  });

  describe('Initialization', () => {
    it('should initialize with default values', () => {
      const config: SessionManagerConfig = {
        dmPolicy: 'require-pairing',
      };
      manager = new SessionManager(config);

      expect(manager).toBeDefined();
      expect(manager.getAllowlist()).toEqual([]);
      expect(manager.listSessions()).toEqual([]);
    });

    it('should initialize with allowlist', () => {
      const config: SessionManagerConfig = {
        dmPolicy: 'require-pairing',
        allowlist: ['telegram:*:12345', 'discord:*:67890'],
      };
      manager = new SessionManager(config);

      const allowlist = manager.getAllowlist();
      expect(allowlist).toContain('telegram:*:12345');
      expect(allowlist).toContain('discord:*:67890');
    });

    it('should initialize with custom pairing TTL', () => {
      const config: SessionManagerConfig = {
        dmPolicy: 'require-pairing',
        pairingCodeTTL: 5 * 60 * 1000, // 5 minutes
      };
      manager = new SessionManager(config);

      expect(manager).toBeDefined();
    });
  });

  describe('Session Creation', () => {
    beforeEach(() => {
      manager = new SessionManager({ dmPolicy: 'require-pairing' });
    });

    it('should create a new session', () => {
      const session = manager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456',
        'John Doe'
      );

      expect(session).toBeDefined();
      expect(session.id).toBe('telegram:bot-1:chat-123');
      expect(session.channelType).toBe('telegram');
      expect(session.channelId).toBe('bot-1');
      expect(session.chatId).toBe('chat-123');
      expect(session.userId).toBe('user-456');
      expect(session.userName).toBe('John Doe');
      expect(session.paired).toBe(false);
      expect(session.createdAt).toBeInstanceOf(Date);
      expect(session.lastActivityAt).toBeInstanceOf(Date);
    });

    it('should return existing session on subsequent calls', () => {
      const session1 = manager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );
      const session2 = manager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );

      expect(session1.id).toBe(session2.id);
      expect(session1.createdAt).toEqual(session2.createdAt);
    });

    it('should update lastActivityAt on existing session', () => {
      const session1 = manager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );
      const firstActivity = session1.lastActivityAt;

      // Wait a bit
      vi.useFakeTimers();
      vi.advanceTimersByTime(1000);

      const session2 = manager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );

      expect(session2.lastActivityAt.getTime()).toBeGreaterThan(
        firstActivity.getTime()
      );

      vi.useRealTimers();
    });

    it('should update userName on existing session', () => {
      const session1 = manager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );
      expect(session1.userName).toBeUndefined();

      const session2 = manager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456',
        'Jane Doe'
      );

      expect(session2.userName).toBe('Jane Doe');
    });
  });

  describe('Session Retrieval', () => {
    beforeEach(() => {
      manager = new SessionManager({ dmPolicy: 'require-pairing' });
    });

    it('should get existing session by ID', () => {
      manager.getOrCreateSession('telegram', 'bot-1', 'chat-123', 'user-456');
      const session = manager.getSession('telegram:bot-1:chat-123');

      expect(session).toBeDefined();
      expect(session?.id).toBe('telegram:bot-1:chat-123');
    });

    it('should return undefined for non-existent session', () => {
      const session = manager.getSession('non-existent');

      expect(session).toBeUndefined();
    });

    it('should list all sessions', () => {
      manager.getOrCreateSession('telegram', 'bot-1', 'chat-1', 'user-1');
      manager.getOrCreateSession('discord', 'bot-2', 'chat-2', 'user-2');
      manager.getOrCreateSession('slack', 'bot-3', 'chat-3', 'user-3');

      const sessions = manager.listSessions();

      expect(sessions).toHaveLength(3);
      expect(sessions.map((s) => s.channelType)).toContain('telegram');
      expect(sessions.map((s) => s.channelType)).toContain('discord');
      expect(sessions.map((s) => s.channelType)).toContain('slack');
    });
  });

  describe('Pairing', () => {
    beforeEach(() => {
      manager = new SessionManager({ dmPolicy: 'require-pairing' });
    });

    it('should generate pairing code', () => {
      const session = manager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );
      const code = manager.generatePairingCode(session.id);

      expect(code).toBeDefined();
      expect(code).toHaveLength(6);
      expect(code).toMatch(/^[0-9A-F]{6}$/);
    });

    it('should throw error when generating code for non-existent session', () => {
      expect(() => manager.generatePairingCode('non-existent')).toThrow(
        'Session not found'
      );
    });

    it('should approve session with valid code', async () => {
      const session = manager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );
      const code = manager.generatePairingCode(session.id);

      const approved = await manager.approveSession(session.id, code);

      expect(approved).toBe(true);
      expect(session.paired).toBe(true);
      expect(session.pairingCode).toBeUndefined();
      expect(session.pairingCodeExpiresAt).toBeUndefined();
    });

    it('should reject invalid pairing code', async () => {
      const session = manager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );
      manager.generatePairingCode(session.id);

      const approved = await manager.approveSession(session.id, 'WRONG1');

      expect(approved).toBe(false);
      expect(session.paired).toBe(false);
    });

    it('should reject expired pairing code', async () => {
      vi.useFakeTimers();
      const session = manager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );
      const code = manager.generatePairingCode(session.id);

      // Advance time past expiry (default 10 minutes)
      vi.advanceTimersByTime(11 * 60 * 1000);

      const approved = await manager.approveSession(session.id, code);

      expect(approved).toBe(false);
      expect(session.paired).toBe(false);

      vi.useRealTimers();
    });

    it('should manually approve session', async () => {
      const session = manager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );

      const approved = await manager.manualApprove(session.id);

      expect(approved).toBe(true);
      expect(session.paired).toBe(true);
    });

    it('should return false when manually approving non-existent session', async () => {
      const approved = await manager.manualApprove('non-existent');

      expect(approved).toBe(false);
    });

    it('should list pending sessions', () => {
      const session1 = manager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-1',
        'user-1'
      );
      const session2 = manager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-2',
        'user-2'
      );
      manager.getOrCreateSession('telegram', 'bot-1', 'chat-3', 'user-3');

      manager.generatePairingCode(session1.id);
      manager.generatePairingCode(session2.id);

      const pending = manager.getPendingSessions();

      expect(pending).toHaveLength(2);
      expect(pending.map((s) => s.id)).toContain(session1.id);
      expect(pending.map((s) => s.id)).toContain(session2.id);
    });
  });

  describe('Allowlist', () => {
    beforeEach(() => {
      manager = new SessionManager({
        dmPolicy: 'require-pairing',
        onAllowlistChange: mockAllowlistCallback,
      });
    });

    it('should add to allowlist', async () => {
      await manager.addToAllowlist('telegram:*:12345');

      const allowlist = manager.getAllowlist();
      expect(allowlist).toContain('telegram:*:12345');
      expect(mockAllowlistCallback).toHaveBeenCalled();
    });

    it('should remove from allowlist', async () => {
      await manager.addToAllowlist('telegram:*:12345');
      await manager.removeFromAllowlist('telegram:*:12345');

      const allowlist = manager.getAllowlist();
      expect(allowlist).not.toContain('telegram:*:12345');
      expect(mockAllowlistCallback).toHaveBeenCalledTimes(2);
    });

    it('should pre-approve sessions matching allowlist', () => {
      manager = new SessionManager({
        dmPolicy: 'require-pairing',
        allowlist: ['telegram:*:chat-123'],
      });

      const session = manager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );

      expect(session.paired).toBe(true);
    });

    it('should add to allowlist when approving session', async () => {
      const session = manager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );
      const code = manager.generatePairingCode(session.id);

      await manager.approveSession(session.id, code);

      const allowlist = manager.getAllowlist();
      expect(allowlist).toContain(session.id);
    });
  });

  describe('DM Policy', () => {
    it('should auto-approve all sessions in open mode', () => {
      manager = new SessionManager({ dmPolicy: 'open' });

      const session = manager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );

      expect(session.paired).toBe(true);
      expect(manager.isSessionPaired(session.id)).toBe(true);
    });

    it('should require pairing in require-pairing mode', () => {
      manager = new SessionManager({ dmPolicy: 'require-pairing' });

      const session = manager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );

      expect(session.paired).toBe(false);
      expect(manager.isSessionPaired(session.id)).toBe(false);
    });

    it('should check pairing status correctly', () => {
      manager = new SessionManager({ dmPolicy: 'require-pairing' });

      const session = manager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );

      expect(manager.isSessionPaired(session.id)).toBe(false);

      session.paired = true;

      expect(manager.isSessionPaired(session.id)).toBe(true);
    });

    it('should return false for non-existent session pairing check', () => {
      manager = new SessionManager({ dmPolicy: 'require-pairing' });

      expect(manager.isSessionPaired('non-existent')).toBe(false);
    });
  });

  describe('Session Cleanup', () => {
    beforeEach(() => {
      manager = new SessionManager({ dmPolicy: 'require-pairing' });
    });

    it('should remove session', () => {
      const session = manager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );

      const removed = manager.removeSession(session.id);

      expect(removed).toBe(true);
      expect(manager.getSession(session.id)).toBeUndefined();
    });

    it('should return false when removing non-existent session', () => {
      const removed = manager.removeSession('non-existent');

      expect(removed).toBe(false);
    });
  });

  describe('Touch Session', () => {
    beforeEach(() => {
      manager = new SessionManager({ dmPolicy: 'require-pairing' });
    });

    it('should update lastActivityAt for existing session', () => {
      vi.useFakeTimers();
      const session = manager.getOrCreateSession(
        'telegram',
        'bot-1',
        'chat-123',
        'user-456'
      );
      const originalTime = session.lastActivityAt.getTime();

      // Advance time
      vi.advanceTimersByTime(5000);

      const touched = manager.touchSession(session.id);

      expect(touched).toBe(true);
      expect(session.lastActivityAt.getTime()).toBeGreaterThan(originalTime);

      vi.useRealTimers();
    });

    it('should return false for non-existent session', () => {
      const touched = manager.touchSession('non-existent');

      expect(touched).toBe(false);
    });
  });
});
