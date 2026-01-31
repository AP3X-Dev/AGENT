/**
 * Integration tests for Gateway-Agent communication.
 *
 * These tests verify the full request/response flow between the Gateway
 * and the Agent worker, including /turn and /resume endpoints.
 *
 * Prerequisites:
 * - Agent worker must be running on http://127.0.0.1:18790
 * - Gateway must be configured to connect to the agent
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';

const AGENT_URL = 'http://127.0.0.1:18790';
const TEST_TIMEOUT = 30000; // 30 seconds for integration tests

interface TurnRequest {
  session_id: string;
  text: string;
  metadata?: Record<string, unknown>;
}

interface InterruptInfo {
  interrupt_id: string;
  pending_actions: Array<{
    tool_name: string;
    args: Record<string, unknown>;
    description: string;
  }>;
  action_count: number;
}

interface TurnResponse {
  session_id: string;
  text: string;
  events: Array<Record<string, unknown>>;
  interrupt?: InterruptInfo | null;
}

interface ResumeRequest {
  session_id: string;
  decisions: Array<{ type: 'approve' | 'reject' }>;
}

interface ResumeResponse {
  session_id: string;
  text: string;
  events: Array<Record<string, unknown>>;
  interrupt?: InterruptInfo | null;
}

describe('Gateway-Agent Integration', () => {
  let agentAvailable = false;

  beforeAll(async () => {
    // Check if agent is running
    try {
      const response = await fetch(`${AGENT_URL}/health`);
      agentAvailable = response.ok;
      if (!agentAvailable) {
        console.warn('⚠️  Agent worker is not running. Integration tests will be skipped.');
        console.warn('   Start the agent with: cd apps/agent && python -m ag3nt_agent.worker');
      }
    } catch (error) {
      console.warn('⚠️  Agent worker is not running. Integration tests will be skipped.');
      agentAvailable = false;
    }
  }, TEST_TIMEOUT);

  describe('Health Check', () => {
    it('should return health status from agent', async () => {
      if (!agentAvailable) {
        console.log('⏭️  Skipping test - agent not available');
        return;
      }

      const response = await fetch(`${AGENT_URL}/health`);
      expect(response.ok).toBe(true);

      const data = await response.json();
      expect(data).toHaveProperty('ok', true);
      expect(data).toHaveProperty('name', 'ag3nt-agent');
    }, TEST_TIMEOUT);
  });

  describe('Turn Endpoint', () => {
    it('should process a simple turn request', async () => {
      if (!agentAvailable) {
        console.log('⏭️  Skipping test - agent not available');
        return;
      }

      const request: TurnRequest = {
        session_id: 'test-session-1',
        text: 'Hello, what is 2+2?',
        metadata: {
          channelType: 'test',
          userId: 'test-user',
        },
      };

      const response = await fetch(`${AGENT_URL}/turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      });

      expect(response.ok).toBe(true);

      const data: TurnResponse = await response.json();
      expect(data).toHaveProperty('session_id', 'test-session-1');
      expect(data).toHaveProperty('text');
      expect(typeof data.text).toBe('string');
      expect(data.text.length).toBeGreaterThan(0);
      expect(data).toHaveProperty('events');
      expect(Array.isArray(data.events)).toBe(true);
    }, TEST_TIMEOUT);

    it('should handle metadata in turn request', async () => {
      if (!agentAvailable) {
        console.log('⏭️  Skipping test - agent not available');
        return;
      }

      const request: TurnRequest = {
        session_id: 'test-session-2',
        text: 'Test message',
        metadata: {
          channelType: 'telegram',
          channelId: 'test-channel',
          userId: 'user-123',
          userName: 'Test User',
        },
      };

      const response = await fetch(`${AGENT_URL}/turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      });

      expect(response.ok).toBe(true);
      const data: TurnResponse = await response.json();
      expect(data.session_id).toBe('test-session-2');
    }, TEST_TIMEOUT);

    it('should maintain session context across multiple turns', async () => {
      if (!agentAvailable) {
        console.log('⏭️  Skipping test - agent not available');
        return;
      }

      const sessionId = 'test-session-context';

      // First turn
      const request1: TurnRequest = {
        session_id: sessionId,
        text: 'My name is Alice',
      };

      const response1 = await fetch(`${AGENT_URL}/turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request1),
      });

      expect(response1.ok).toBe(true);
      const data1: TurnResponse = await response1.json();
      expect(data1.session_id).toBe(sessionId);

      // Second turn - should remember the name
      const request2: TurnRequest = {
        session_id: sessionId,
        text: 'What is my name?',
      };

      const response2 = await fetch(`${AGENT_URL}/turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request2),
      });

      expect(response2.ok).toBe(true);
      const data2: TurnResponse = await response2.json();
      expect(data2.session_id).toBe(sessionId);
      // The response should mention "Alice"
      expect(data2.text.toLowerCase()).toContain('alice');
    }, TEST_TIMEOUT);
  });

  describe('Error Handling', () => {
    it('should return error for invalid request format', async () => {
      if (!agentAvailable) {
        console.log('⏭️  Skipping test - agent not available');
        return;
      }

      const response = await fetch(`${AGENT_URL}/turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ invalid: 'request' }),
      });

      expect(response.ok).toBe(false);
      expect(response.status).toBe(422); // Validation error
    }, TEST_TIMEOUT);

    it('should handle empty text gracefully', async () => {
      if (!agentAvailable) {
        console.log('⏭️  Skipping test - agent not available');
        return;
      }

      const request: TurnRequest = {
        session_id: 'test-session-empty',
        text: '',
      };

      const response = await fetch(`${AGENT_URL}/turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      });

      // Should either accept it or return validation error
      expect([200, 422]).toContain(response.status);
    }, TEST_TIMEOUT);
  });

  describe('Resume Endpoint', () => {
    it('should handle resume request structure', async () => {
      if (!agentAvailable) {
        console.log('⏭️  Skipping test - agent not available');
        return;
      }

      // Note: This test verifies the endpoint exists and accepts the correct format
      // A real interrupt scenario would require triggering a risky tool
      const request: ResumeRequest = {
        session_id: 'test-session-resume',
        decisions: [{ type: 'approve' }],
      };

      const response = await fetch(`${AGENT_URL}/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      });

      // May fail if no interrupt exists, but should not be a 404
      expect(response.status).not.toBe(404);
    }, TEST_TIMEOUT);
  });

  describe('Performance', () => {
    it('should respond to simple queries within reasonable time', async () => {
      if (!agentAvailable) {
        console.log('⏭️  Skipping test - agent not available');
        return;
      }

      const startTime = Date.now();

      const request: TurnRequest = {
        session_id: 'test-session-perf',
        text: 'Say hello',
      };

      const response = await fetch(`${AGENT_URL}/turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      });

      const endTime = Date.now();
      const duration = endTime - startTime;

      expect(response.ok).toBe(true);
      // Should respond within 10 seconds for a simple query
      expect(duration).toBeLessThan(10000);
    }, TEST_TIMEOUT);
  });
});

