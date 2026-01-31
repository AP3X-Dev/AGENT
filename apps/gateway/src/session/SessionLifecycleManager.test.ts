/**
 * Tests for SessionLifecycleManager.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { SessionLifecycleManager } from './SessionLifecycleManager.js';
import { SessionManager } from './SessionManager.js';
import { MessageStore } from '../storage/MessageStore.js';
import fs from 'fs';
import path from 'path';
import os from 'os';

describe('SessionLifecycleManager', () => {
  let sessionManager: SessionManager;
  let messageStore: MessageStore;
  let lifecycleManager: SessionLifecycleManager;
  let testDbPath: string;

  beforeEach(() => {
    testDbPath = path.join(os.tmpdir(), `test-lifecycle-${Date.now()}.db`);
    sessionManager = new SessionManager({ dmPolicy: 'open' });
    messageStore = new MessageStore(testDbPath);
    lifecycleManager = new SessionLifecycleManager(sessionManager, messageStore);
  });

  afterEach(() => {
    lifecycleManager.stop();
    messageStore.close();
    if (fs.existsSync(testDbPath)) {
      fs.unlinkSync(testDbPath);
    }
  });

  describe('Configuration', () => {
    it('should use default config values', () => {
      const config = lifecycleManager.getConfig();

      expect(config.sessionTimeout).toBe(24 * 60 * 60 * 1000); // 24 hours
      expect(config.cleanupInterval).toBe(60 * 60 * 1000); // 1 hour
      expect(config.persistSessions).toBe(true);
    });

    it('should accept custom config', () => {
      const custom = new SessionLifecycleManager(sessionManager, messageStore, {
        sessionTimeout: 60000,
        cleanupInterval: 10000,
        persistSessions: false,
      });

      const config = custom.getConfig();

      expect(config.sessionTimeout).toBe(60000);
      expect(config.cleanupInterval).toBe(10000);
      expect(config.persistSessions).toBe(false);
    });
  });

  describe('Start/Stop', () => {
    it('should track running state', () => {
      expect(lifecycleManager.isRunning()).toBe(false);

      lifecycleManager.start();

      expect(lifecycleManager.isRunning()).toBe(true);

      lifecycleManager.stop();

      expect(lifecycleManager.isRunning()).toBe(false);
    });

    it('should not start twice', () => {
      lifecycleManager.start();
      lifecycleManager.start(); // Should not throw

      expect(lifecycleManager.isRunning()).toBe(true);
    });
  });

  describe('destroySession', () => {
    it('should delete messages and remove session', () => {
      const session = sessionManager.getOrCreateSession(
        'telegram', 'bot-1', 'chat-1', 'user-1'
      );
      messageStore.addMessage(session.id, { role: 'user', content: 'Hello' });
      messageStore.addMessage(session.id, { role: 'assistant', content: 'Hi' });

      expect(messageStore.getMessageCount(session.id)).toBe(2);

      const destroyed = lifecycleManager.destroySession(session.id);

      expect(destroyed).toBe(true);
      expect(messageStore.getMessageCount(session.id)).toBe(0);
      expect(sessionManager.getSession(session.id)).toBeUndefined();
    });

    it('should emit sessionDestroyed event', () => {
      const session = sessionManager.getOrCreateSession(
        'telegram', 'bot-1', 'chat-1', 'user-1'
      );
      const callback = vi.fn();
      lifecycleManager.on('sessionDestroyed', callback);

      lifecycleManager.destroySession(session.id);

      expect(callback).toHaveBeenCalledWith({ sessionId: session.id });
    });

    it('should return false for non-existent session', () => {
      const destroyed = lifecycleManager.destroySession('non-existent');

      expect(destroyed).toBe(false);
    });
  });

  describe('cleanupExpiredSessions', () => {
    it('should cleanup expired sessions', () => {
      vi.useFakeTimers();

      // Create session and age it
      const session = sessionManager.getOrCreateSession(
        'telegram', 'bot-1', 'chat-1', 'user-1'
      );
      messageStore.addMessage(session.id, { role: 'user', content: 'Hello' });

      // Age the session by 25 hours
      vi.advanceTimersByTime(25 * 60 * 60 * 1000);

      const cleaned = lifecycleManager.cleanupExpiredSessions();

      expect(cleaned).toBe(1);
      expect(sessionManager.getSession(session.id)).toBeUndefined();
      expect(messageStore.getMessageCount(session.id)).toBe(0);

      vi.useRealTimers();
    });

    it('should not cleanup active sessions', () => {
      const session = sessionManager.getOrCreateSession(
        'telegram', 'bot-1', 'chat-1', 'user-1'
      );

      const cleaned = lifecycleManager.cleanupExpiredSessions();

      expect(cleaned).toBe(0);
      expect(sessionManager.getSession(session.id)).toBeDefined();
    });

    it('should emit sessionsCleanedUp event', () => {
      vi.useFakeTimers();
      const callback = vi.fn();
      lifecycleManager.on('sessionsCleanedUp', callback);

      sessionManager.getOrCreateSession('telegram', 'bot-1', 'chat-1', 'user-1');
      vi.advanceTimersByTime(25 * 60 * 60 * 1000);

      lifecycleManager.cleanupExpiredSessions();

      expect(callback).toHaveBeenCalledWith({ count: 1 });

      vi.useRealTimers();
    });
  });

  describe('resumeSession', () => {
    it('should resume session with matching context', () => {
      const session = sessionManager.getOrCreateSession(
        'telegram', 'bot-1', 'chat-1', 'user-1'
      );

      const resumed = lifecycleManager.resumeSession(session.id, {
        channelType: 'telegram',
        channelId: 'bot-1',
        userId: 'user-1',
      });

      expect(resumed).not.toBeNull();
      expect(resumed?.id).toBe(session.id);
    });

    it('should return null for non-existent session', () => {
      const resumed = lifecycleManager.resumeSession('non-existent', {
        channelType: 'telegram',
        channelId: 'bot-1',
        userId: 'user-1',
      });

      expect(resumed).toBeNull();
    });

    it('should return null for mismatched channel type', () => {
      const session = sessionManager.getOrCreateSession(
        'telegram', 'bot-1', 'chat-1', 'user-1'
      );

      const resumed = lifecycleManager.resumeSession(session.id, {
        channelType: 'discord', // Different channel type
        channelId: 'bot-1',
        userId: 'user-1',
      });

      expect(resumed).toBeNull();
    });

    it('should return null for mismatched channel id', () => {
      const session = sessionManager.getOrCreateSession(
        'telegram', 'bot-1', 'chat-1', 'user-1'
      );

      const resumed = lifecycleManager.resumeSession(session.id, {
        channelType: 'telegram',
        channelId: 'bot-2', // Different channel id
        userId: 'user-1',
      });

      expect(resumed).toBeNull();
    });

    it('should return null for mismatched user id', () => {
      const session = sessionManager.getOrCreateSession(
        'telegram', 'bot-1', 'chat-1', 'user-1'
      );

      const resumed = lifecycleManager.resumeSession(session.id, {
        channelType: 'telegram',
        channelId: 'bot-1',
        userId: 'user-2', // Different user
      });

      expect(resumed).toBeNull();
    });

    it('should update lastActivityAt on resume', () => {
      vi.useFakeTimers();
      const session = sessionManager.getOrCreateSession(
        'telegram', 'bot-1', 'chat-1', 'user-1'
      );
      const originalTime = session.lastActivityAt.getTime();

      vi.advanceTimersByTime(5000);

      lifecycleManager.resumeSession(session.id, {
        channelType: 'telegram',
        channelId: 'bot-1',
        userId: 'user-1',
      });

      expect(session.lastActivityAt.getTime()).toBeGreaterThan(originalTime);

      vi.useRealTimers();
    });

    it('should emit sessionResumed event', () => {
      const session = sessionManager.getOrCreateSession(
        'telegram', 'bot-1', 'chat-1', 'user-1'
      );
      const callback = vi.fn();
      lifecycleManager.on('sessionResumed', callback);

      lifecycleManager.resumeSession(session.id, {
        channelType: 'telegram',
        channelId: 'bot-1',
        userId: 'user-1',
      });

      expect(callback).toHaveBeenCalledWith({ sessionId: session.id });
    });
  });
});

