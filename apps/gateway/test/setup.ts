/**
 * Vitest setup file for Gateway tests.
 * 
 * This file is run before each test file and sets up global mocks,
 * test utilities, and common configuration.
 */
import { vi, beforeAll, afterAll, afterEach, expect } from 'vitest';

// ============================================================================
// Environment Setup
// ============================================================================

// Set test environment variables
vi.stubEnv('NODE_ENV', 'test');
vi.stubEnv('LOG_LEVEL', 'error');
vi.stubEnv('PORT', '18789');

// ============================================================================
// Global Mocks
// ============================================================================

// Mock console methods to reduce noise in tests (optional - can be removed for debugging)
// vi.spyOn(console, 'log').mockImplementation(() => {});
// vi.spyOn(console, 'info').mockImplementation(() => {});

// ============================================================================
// Test Lifecycle Hooks
// ============================================================================

beforeAll(() => {
  // Setup that runs once before all tests
});

afterAll(() => {
  // Cleanup that runs once after all tests
  vi.restoreAllMocks();
});

afterEach(() => {
  // Cleanup after each test
  vi.clearAllMocks();
});

// ============================================================================
// Custom Matchers
// ============================================================================

expect.extend({
  /**
   * Check if a value is a valid UUID v4
   */
  toBeUUID(received: string) {
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
    const pass = uuidRegex.test(received);
    return {
      pass,
      message: () =>
        pass
          ? `expected ${received} not to be a valid UUID`
          : `expected ${received} to be a valid UUID`,
    };
  },
  
  /**
   * Check if a value is a valid ISO date string
   */
  toBeISODateString(received: string) {
    const date = new Date(received);
    const pass = !isNaN(date.getTime()) && received.includes('T');
    return {
      pass,
      message: () =>
        pass
          ? `expected ${received} not to be a valid ISO date string`
          : `expected ${received} to be a valid ISO date string`,
    };
  },
});

// ============================================================================
// Type Declarations for Custom Matchers
// ============================================================================

declare module 'vitest' {
  interface Assertion<T = unknown> {
    toBeUUID(): T;
    toBeISODateString(): T;
  }
  interface AsymmetricMatchersContaining {
    toBeUUID(): unknown;
    toBeISODateString(): unknown;
  }
}

// ============================================================================
// Global Test Utilities
// ============================================================================

/**
 * Wait for a specified number of milliseconds
 */
export function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Create a mock WebSocket instance
 */
export function createMockWebSocket() {
  return {
    send: vi.fn(),
    close: vi.fn(),
    readyState: 1, // WebSocket.OPEN
    on: vi.fn(),
    once: vi.fn(),
    removeListener: vi.fn(),
  };
}

/**
 * Create a mock HTTP request
 */
export function createMockRequest(overrides: Partial<{
  method: string;
  url: string;
  headers: Record<string, string>;
  body: unknown;
}> = {}) {
  return {
    method: 'GET',
    url: '/',
    headers: {},
    body: null,
    ...overrides,
  };
}

/**
 * Create a mock HTTP response
 */
export function createMockResponse() {
  const res = {
    status: vi.fn().mockReturnThis(),
    json: vi.fn().mockReturnThis(),
    send: vi.fn().mockReturnThis(),
    end: vi.fn().mockReturnThis(),
    setHeader: vi.fn().mockReturnThis(),
    statusCode: 200,
  };
  return res;
}

