/**
 * Tests for MessageStore.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { MessageStore } from './MessageStore.js';
import fs from 'fs';
import path from 'path';
import os from 'os';

describe('MessageStore', () => {
  let store: MessageStore;
  let testDbPath: string;

  beforeEach(() => {
    // Use a temp directory for tests
    testDbPath = path.join(os.tmpdir(), `test-messages-${Date.now()}.db`);
    store = new MessageStore(testDbPath);
  });

  afterEach(() => {
    store.close();
    // Clean up test database
    if (fs.existsSync(testDbPath)) {
      fs.unlinkSync(testDbPath);
    }
  });

  describe('Initialization', () => {
    it('should create database file', () => {
      expect(fs.existsSync(testDbPath)).toBe(true);
    });

    it('should return correct db path', () => {
      expect(store.getDbPath()).toBe(testDbPath);
    });
  });

  describe('addMessage', () => {
    it('should add a message and return it with id', () => {
      const message = store.addMessage('session-1', {
        role: 'user',
        content: 'Hello world',
      });

      expect(message.id).toBeDefined();
      expect(message.sessionId).toBe('session-1');
      expect(message.role).toBe('user');
      expect(message.content).toBe('Hello world');
      expect(message.timestamp).toBeInstanceOf(Date);
    });

    it('should add message with tool calls', () => {
      const toolCalls = [
        {
          id: 'call-1',
          name: 'search',
          arguments: { query: 'test' },
          result: 'Found results',
        },
      ];

      const message = store.addMessage('session-1', {
        role: 'assistant',
        content: 'Let me search',
        toolCalls,
      });

      expect(message.toolCalls).toEqual(toolCalls);
    });
  });

  describe('getMessages', () => {
    it('should get messages for a session', () => {
      store.addMessage('session-1', { role: 'user', content: 'Message 1' });
      store.addMessage('session-1', { role: 'assistant', content: 'Message 2' });
      store.addMessage('session-2', { role: 'user', content: 'Other session' });

      const messages = store.getMessages('session-1');

      expect(messages).toHaveLength(2);
      expect(messages[0].content).toBe('Message 1');
      expect(messages[1].content).toBe('Message 2');
    });

    it('should return messages in chronological order', () => {
      store.addMessage('session-1', { role: 'user', content: 'First' });
      store.addMessage('session-1', { role: 'assistant', content: 'Second' });
      store.addMessage('session-1', { role: 'user', content: 'Third' });

      const messages = store.getMessages('session-1');

      expect(messages[0].content).toBe('First');
      expect(messages[1].content).toBe('Second');
      expect(messages[2].content).toBe('Third');
    });

    it('should respect limit option', () => {
      for (let i = 0; i < 10; i++) {
        store.addMessage('session-1', { role: 'user', content: `Message ${i}` });
      }

      const messages = store.getMessages('session-1', { limit: 5 });

      expect(messages).toHaveLength(5);
    });

    it('should return empty array for non-existent session', () => {
      const messages = store.getMessages('non-existent');

      expect(messages).toEqual([]);
    });
  });

  describe('getMessageCount', () => {
    it('should return correct count', () => {
      store.addMessage('session-1', { role: 'user', content: 'Message 1' });
      store.addMessage('session-1', { role: 'assistant', content: 'Message 2' });
      store.addMessage('session-1', { role: 'user', content: 'Message 3' });

      const count = store.getMessageCount('session-1');

      expect(count).toBe(3);
    });

    it('should return 0 for non-existent session', () => {
      const count = store.getMessageCount('non-existent');

      expect(count).toBe(0);
    });
  });

  describe('deleteSessionMessages', () => {
    it('should delete all messages for a session', () => {
      store.addMessage('session-1', { role: 'user', content: 'Message 1' });
      store.addMessage('session-1', { role: 'assistant', content: 'Message 2' });
      store.addMessage('session-2', { role: 'user', content: 'Other session' });

      const deleted = store.deleteSessionMessages('session-1');

      expect(deleted).toBe(2);
      expect(store.getMessageCount('session-1')).toBe(0);
      expect(store.getMessageCount('session-2')).toBe(1);
    });

    it('should return 0 for non-existent session', () => {
      const deleted = store.deleteSessionMessages('non-existent');

      expect(deleted).toBe(0);
    });
  });
});

