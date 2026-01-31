/**
 * Shared test utilities for Gateway tests.
 * 
 * Provides mock classes, factories, and helpers for testing.
 */
import { vi } from 'vitest';

// ============================================================================
// Types
// ============================================================================

export interface MockSession {
  sessionId: string;
  channel: string;
  userId: string;
  createdAt: string;
  state: 'active' | 'paused' | 'closed';
  metadata: Record<string, unknown>;
}

export interface MockMessage {
  messageId: string;
  sessionId: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
}

export interface MockApproval {
  approvalId: string;
  sessionId: string;
  toolName: string;
  toolInput: Record<string, unknown>;
  status: 'pending' | 'approved' | 'denied';
  createdAt: string;
}

// ============================================================================
// Test Data Generator
// ============================================================================

export class TestDataGenerator {
  private counter = 0;
  private seed: string;

  constructor(seed = 'test') {
    this.seed = seed;
  }

  private nextId(): string {
    this.counter++;
    return `${this.seed}-${String(this.counter).padStart(4, '0')}`;
  }

  session(overrides: Partial<MockSession> = {}): MockSession {
    return {
      sessionId: `session-${this.nextId()}`,
      channel: 'test',
      userId: 'test-user',
      createdAt: new Date().toISOString(),
      state: 'active',
      metadata: {},
      ...overrides,
    };
  }

  message(overrides: Partial<MockMessage> = {}): MockMessage {
    return {
      messageId: `msg-${this.nextId()}`,
      sessionId: `session-${this.nextId()}`,
      role: 'user',
      content: 'Test message',
      timestamp: new Date().toISOString(),
      ...overrides,
    };
  }

  approval(overrides: Partial<MockApproval> = {}): MockApproval {
    return {
      approvalId: `approval-${this.nextId()}`,
      sessionId: `session-${this.nextId()}`,
      toolName: 'shell',
      toolInput: { command: 'ls' },
      status: 'pending',
      createdAt: new Date().toISOString(),
      ...overrides,
    };
  }

  reset(): void {
    this.counter = 0;
  }
}

// ============================================================================
// Mock Session Manager
// ============================================================================

export class MockSessionManager {
  private sessions = new Map<string, MockSession>();
  
  create = vi.fn((channel: string, userId: string) => {
    const session: MockSession = {
      sessionId: `session-${Date.now()}`,
      channel,
      userId,
      createdAt: new Date().toISOString(),
      state: 'active',
      metadata: {},
    };
    this.sessions.set(session.sessionId, session);
    return session;
  });

  get = vi.fn((sessionId: string) => {
    return this.sessions.get(sessionId) || null;
  });

  update = vi.fn((sessionId: string, updates: Partial<MockSession>) => {
    const session = this.sessions.get(sessionId);
    if (session) {
      Object.assign(session, updates);
      return session;
    }
    return null;
  });

  delete = vi.fn((sessionId: string) => {
    return this.sessions.delete(sessionId);
  });

  list = vi.fn(() => {
    return Array.from(this.sessions.values());
  });

  reset(): void {
    this.sessions.clear();
    this.create.mockClear();
    this.get.mockClear();
    this.update.mockClear();
    this.delete.mockClear();
    this.list.mockClear();
  }
}

// ============================================================================
// Mock Agent Worker Client
// ============================================================================

export class MockAgentWorkerClient {
  private responses: Array<{ content: string; toolCalls?: unknown[] }> = [];
  private responseIndex = 0;

  sendMessage = vi.fn(async (_sessionId: string, _message: string) => {
    if (this.responses.length === 0) {
      return { content: 'Mock response', toolCalls: [] };
    }
    const response = this.responses[this.responseIndex];
    if (this.responseIndex < this.responses.length - 1) {
      this.responseIndex++;
    }
    return response;
  });

  checkHealth = vi.fn(async () => {
    return { ok: true, name: 'mock-agent' };
  });

  setResponse(content: string, toolCalls?: unknown[]): this {
    this.responses = [{ content, toolCalls }];
    this.responseIndex = 0;
    return this;
  }

  setResponses(responses: Array<{ content: string; toolCalls?: unknown[] }>): this {
    this.responses = responses;
    this.responseIndex = 0;
    return this;
  }

  reset(): void {
    this.responses = [];
    this.responseIndex = 0;
    this.sendMessage.mockClear();
    this.checkHealth.mockClear();
  }
}

// ============================================================================
// Factory Functions
// ============================================================================

export const createTestDataGenerator = (seed?: string) => new TestDataGenerator(seed);
export const createMockSessionManager = () => new MockSessionManager();
export const createMockAgentWorkerClient = () => new MockAgentWorkerClient();

