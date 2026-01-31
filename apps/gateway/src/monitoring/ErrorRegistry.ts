/**
 * Error Registry for AG3NT.
 *
 * Provides standardized error codes and messages across the codebase.
 * Error code format: [SERVICE]-[CATEGORY]-[CODE]
 *
 * Services:
 * - GW: Gateway
 * - AG: Agent
 *
 * Categories:
 * - AUTH: Authentication/Authorization
 * - SESS: Session management
 * - CHAN: Channel adapters
 * - NODE: Multi-node
 * - SCHED: Scheduler
 * - SKILL: Skills
 * - MEM: Memory
 * - API: External API calls
 * - INT: Internal errors
 */

export interface ErrorDefinition {
  code: string;
  message: string;
  httpStatus?: number;
  retryable?: boolean;
}

export interface AG3NTError extends Error {
  code: string;
  httpStatus: number;
  retryable: boolean;
  details?: Record<string, unknown>;
}

// Gateway Errors
const GATEWAY_ERRORS: Record<string, ErrorDefinition> = {
  // Authentication
  "GW-AUTH-001": { code: "GW-AUTH-001", message: "Pairing code expired", httpStatus: 401 },
  "GW-AUTH-002": { code: "GW-AUTH-002", message: "Invalid pairing code", httpStatus: 401 },
  "GW-AUTH-003": { code: "GW-AUTH-003", message: "Session not paired", httpStatus: 403 },
  "GW-AUTH-004": { code: "GW-AUTH-004", message: "User not in allowlist", httpStatus: 403 },

  // Session
  "GW-SESS-001": { code: "GW-SESS-001", message: "Session not found", httpStatus: 404 },
  "GW-SESS-002": { code: "GW-SESS-002", message: "Session expired", httpStatus: 410 },
  "GW-SESS-003": { code: "GW-SESS-003", message: "Invalid session ID format", httpStatus: 400 },

  // Channel
  "GW-CHAN-001": { code: "GW-CHAN-001", message: "Channel not connected", httpStatus: 503 },
  "GW-CHAN-002": { code: "GW-CHAN-002", message: "Channel adapter not found", httpStatus: 404 },
  "GW-CHAN-003": { code: "GW-CHAN-003", message: "Channel configuration invalid", httpStatus: 400 },
  "GW-CHAN-004": { code: "GW-CHAN-004", message: "Message send failed", httpStatus: 502, retryable: true },

  // Node
  "GW-NODE-001": { code: "GW-NODE-001", message: "Node not found", httpStatus: 404 },
  "GW-NODE-002": { code: "GW-NODE-002", message: "Node not connected", httpStatus: 503 },
  "GW-NODE-003": { code: "GW-NODE-003", message: "Node capability not available", httpStatus: 400 },
  "GW-NODE-004": { code: "GW-NODE-004", message: "Action execution timeout", httpStatus: 504, retryable: true },

  // Scheduler
  "GW-SCHED-001": { code: "GW-SCHED-001", message: "Invalid cron expression", httpStatus: 400 },
  "GW-SCHED-002": { code: "GW-SCHED-002", message: "Job not found", httpStatus: 404 },
  "GW-SCHED-003": { code: "GW-SCHED-003", message: "Job already exists", httpStatus: 409 },

  // API
  "GW-API-001": { code: "GW-API-001", message: "Agent worker unavailable", httpStatus: 503, retryable: true },
  "GW-API-002": { code: "GW-API-002", message: "Agent worker timeout", httpStatus: 504, retryable: true },
  "GW-API-003": { code: "GW-API-003", message: "Invalid request format", httpStatus: 400 },

  // Internal
  "GW-INT-001": { code: "GW-INT-001", message: "Internal server error", httpStatus: 500 },
  "GW-INT-002": { code: "GW-INT-002", message: "Configuration error", httpStatus: 500 },
};

// Agent Errors
const AGENT_ERRORS: Record<string, ErrorDefinition> = {
  // Skill
  "AG-SKILL-001": { code: "AG-SKILL-001", message: "Skill not found", httpStatus: 404 },
  "AG-SKILL-002": { code: "AG-SKILL-002", message: "Skill execution failed", httpStatus: 500 },
  "AG-SKILL-003": { code: "AG-SKILL-003", message: "Skill permission denied", httpStatus: 403 },

  // Memory
  "AG-MEM-001": { code: "AG-MEM-001", message: "Memory search failed", httpStatus: 500 },
  "AG-MEM-002": { code: "AG-MEM-002", message: "Memory index not available", httpStatus: 503 },
  "AG-MEM-003": { code: "AG-MEM-003", message: "Memory summarization failed", httpStatus: 500 },

  // API
  "AG-API-001": { code: "AG-API-001", message: "LLM API error", httpStatus: 502, retryable: true },
  "AG-API-002": { code: "AG-API-002", message: "LLM rate limited", httpStatus: 429, retryable: true },
  "AG-API-003": { code: "AG-API-003", message: "LLM context length exceeded", httpStatus: 400 },

  // Tool
  "AG-TOOL-001": { code: "AG-TOOL-001", message: "Tool execution failed", httpStatus: 500 },
  "AG-TOOL-002": { code: "AG-TOOL-002", message: "Tool not found", httpStatus: 404 },
  "AG-TOOL-003": { code: "AG-TOOL-003", message: "Tool approval rejected", httpStatus: 403 },

  // Internal
  "AG-INT-001": { code: "AG-INT-001", message: "Internal agent error", httpStatus: 500 },
};

const ALL_ERRORS = { ...GATEWAY_ERRORS, ...AGENT_ERRORS };

/**
 * Error Registry for creating and managing standardized errors.
 */
export class ErrorRegistry {
  private errors: Record<string, ErrorDefinition>;

  constructor() {
    this.errors = { ...ALL_ERRORS };
  }

  /**
   * Create an AG3NT error from a code.
   */
  createError(code: string, details?: Record<string, unknown>): AG3NTError {
    const def = this.errors[code] ?? {
      code,
      message: "Unknown error",
      httpStatus: 500,
    };

    const error = new Error(def.message) as AG3NTError;
    error.code = def.code;
    error.httpStatus = def.httpStatus ?? 500;
    error.retryable = def.retryable ?? false;
    error.details = details;
    error.name = "AG3NTError";

    return error;
  }

  /**
   * Get error definition by code.
   */
  getDefinition(code: string): ErrorDefinition | undefined {
    return this.errors[code];
  }

  /**
   * Get all error definitions.
   */
  getAllDefinitions(): Record<string, ErrorDefinition> {
    return { ...this.errors };
  }

  /**
   * Check if an error is retryable.
   */
  isRetryable(code: string): boolean {
    return this.errors[code]?.retryable ?? false;
  }
}

// Singleton instance
let _registry: ErrorRegistry | null = null;

export function getErrorRegistry(): ErrorRegistry {
  if (!_registry) {
    _registry = new ErrorRegistry();
  }
  return _registry;
}

