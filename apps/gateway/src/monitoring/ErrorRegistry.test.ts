/**
 * Tests for ErrorRegistry.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { ErrorRegistry, getErrorRegistry, type AG3NTError } from "./ErrorRegistry.js";

describe("ErrorRegistry", () => {
  let registry: ErrorRegistry;

  beforeEach(() => {
    registry = new ErrorRegistry();
  });

  describe("createError", () => {
    it("should create error from known code", () => {
      const error = registry.createError("GW-AUTH-001");
      expect(error.code).toBe("GW-AUTH-001");
      expect(error.message).toBe("Pairing code expired");
      expect(error.httpStatus).toBe(401);
      expect(error.retryable).toBe(false);
      expect(error.name).toBe("AG3NTError");
    });

    it("should create error with details", () => {
      const error = registry.createError("GW-SESS-001", { sessionId: "test-123" });
      expect(error.details).toEqual({ sessionId: "test-123" });
    });

    it("should handle unknown error code", () => {
      const error = registry.createError("UNKNOWN-CODE");
      expect(error.code).toBe("UNKNOWN-CODE");
      expect(error.message).toBe("Unknown error");
      expect(error.httpStatus).toBe(500);
    });

    it("should set retryable flag correctly", () => {
      const retryableError = registry.createError("GW-API-001");
      expect(retryableError.retryable).toBe(true);

      const nonRetryableError = registry.createError("GW-AUTH-001");
      expect(nonRetryableError.retryable).toBe(false);
    });

    it("should create agent errors", () => {
      const error = registry.createError("AG-SKILL-001");
      expect(error.code).toBe("AG-SKILL-001");
      expect(error.message).toBe("Skill not found");
      expect(error.httpStatus).toBe(404);
    });
  });

  describe("getDefinition", () => {
    it("should return definition for known code", () => {
      const def = registry.getDefinition("GW-CHAN-001");
      expect(def).toBeDefined();
      expect(def?.code).toBe("GW-CHAN-001");
      expect(def?.message).toBe("Channel not connected");
    });

    it("should return undefined for unknown code", () => {
      const def = registry.getDefinition("UNKNOWN");
      expect(def).toBeUndefined();
    });
  });

  describe("getAllDefinitions", () => {
    it("should return all error definitions", () => {
      const defs = registry.getAllDefinitions();
      expect(Object.keys(defs).length).toBeGreaterThan(0);
      expect(defs["GW-AUTH-001"]).toBeDefined();
      expect(defs["AG-SKILL-001"]).toBeDefined();
    });

    it("should return a copy of definitions", () => {
      const defs = registry.getAllDefinitions();
      defs["NEW-CODE"] = { code: "NEW-CODE", message: "New" };
      
      const defs2 = registry.getAllDefinitions();
      expect(defs2["NEW-CODE"]).toBeUndefined();
    });
  });

  describe("isRetryable", () => {
    it("should return true for retryable errors", () => {
      expect(registry.isRetryable("GW-API-001")).toBe(true);
      expect(registry.isRetryable("GW-API-002")).toBe(true);
      expect(registry.isRetryable("AG-API-001")).toBe(true);
    });

    it("should return false for non-retryable errors", () => {
      expect(registry.isRetryable("GW-AUTH-001")).toBe(false);
      expect(registry.isRetryable("GW-SESS-001")).toBe(false);
    });

    it("should return false for unknown codes", () => {
      expect(registry.isRetryable("UNKNOWN")).toBe(false);
    });
  });
});

describe("getErrorRegistry", () => {
  it("should return singleton instance", () => {
    const registry1 = getErrorRegistry();
    const registry2 = getErrorRegistry();
    expect(registry1).toBe(registry2);
  });

  it("should return functional registry", () => {
    const registry = getErrorRegistry();
    const error = registry.createError("GW-INT-001");
    expect(error.code).toBe("GW-INT-001");
  });
});

