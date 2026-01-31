/**
 * Tests for Node Communication Protocol.
 */

import { describe, it, expect } from "vitest";
import { validateNodeMessage } from "./protocol.js";

describe("validateNodeMessage", () => {
  describe("basic validation", () => {
    it("should reject non-object data", () => {
      expect(() => validateNodeMessage(null)).toThrow("not an object");
      expect(() => validateNodeMessage("string")).toThrow("not an object");
      expect(() => validateNodeMessage(123)).toThrow("not an object");
    });

    it("should reject message without type", () => {
      expect(() => validateNodeMessage({ timestamp: Date.now() })).toThrow("missing type");
    });

    it("should reject message without timestamp", () => {
      expect(() => validateNodeMessage({ type: "heartbeat" })).toThrow("missing or invalid timestamp");
    });

    it("should reject message with non-number timestamp", () => {
      expect(() => validateNodeMessage({ type: "heartbeat", timestamp: "now" })).toThrow("missing or invalid timestamp");
    });
  });

  describe("register message", () => {
    it("should validate valid register message", () => {
      const msg = {
        type: "register",
        timestamp: Date.now(),
        payload: {
          name: "Test Node",
          capabilities: ["file_management"],
          platform: { os: "windows", arch: "x64" },
        },
      };
      expect(() => validateNodeMessage(msg)).not.toThrow();
    });

    it("should reject register without payload", () => {
      const msg = { type: "register", timestamp: Date.now() };
      expect(() => validateNodeMessage(msg)).toThrow("missing payload");
    });

    it("should reject register without name", () => {
      const msg = {
        type: "register",
        timestamp: Date.now(),
        payload: { capabilities: [], platform: {} },
      };
      expect(() => validateNodeMessage(msg)).toThrow("missing or invalid name");
    });

    it("should reject register without capabilities array", () => {
      const msg = {
        type: "register",
        timestamp: Date.now(),
        payload: { name: "Test", capabilities: "not-array", platform: {} },
      };
      expect(() => validateNodeMessage(msg)).toThrow("missing or invalid capabilities");
    });

    it("should reject register without platform", () => {
      const msg = {
        type: "register",
        timestamp: Date.now(),
        payload: { name: "Test", capabilities: [] },
      };
      expect(() => validateNodeMessage(msg)).toThrow("missing or invalid platform");
    });
  });

  describe("heartbeat message", () => {
    it("should validate valid heartbeat message", () => {
      const msg = { type: "heartbeat", nodeId: "node-1", timestamp: Date.now() };
      expect(() => validateNodeMessage(msg)).not.toThrow();
    });

    it("should reject heartbeat without nodeId", () => {
      const msg = { type: "heartbeat", timestamp: Date.now() };
      expect(() => validateNodeMessage(msg)).toThrow("missing nodeId");
    });
  });

  describe("action:response message", () => {
    it("should validate valid action response", () => {
      const msg = {
        type: "action:response",
        nodeId: "node-1",
        timestamp: Date.now(),
        payload: { requestId: "req-1", success: true, result: { data: "test" } },
      };
      expect(() => validateNodeMessage(msg)).not.toThrow();
    });

    it("should reject action response without nodeId", () => {
      const msg = {
        type: "action:response",
        timestamp: Date.now(),
        payload: { requestId: "req-1", success: true },
      };
      expect(() => validateNodeMessage(msg)).toThrow("missing nodeId");
    });

    it("should reject action response without requestId", () => {
      const msg = {
        type: "action:response",
        nodeId: "node-1",
        timestamp: Date.now(),
        payload: { success: true },
      };
      expect(() => validateNodeMessage(msg)).toThrow("missing requestId");
    });

    it("should reject action response without success field", () => {
      const msg = {
        type: "action:response",
        nodeId: "node-1",
        timestamp: Date.now(),
        payload: { requestId: "req-1" },
      };
      expect(() => validateNodeMessage(msg)).toThrow("missing or invalid success");
    });
  });

  describe("capability:update message", () => {
    it("should validate valid capability update", () => {
      const msg = {
        type: "capability:update",
        nodeId: "node-1",
        timestamp: Date.now(),
        payload: { capabilities: ["file_management", "audio_output"] },
      };
      expect(() => validateNodeMessage(msg)).not.toThrow();
    });

    it("should reject capability update without nodeId", () => {
      const msg = {
        type: "capability:update",
        timestamp: Date.now(),
        payload: { capabilities: [] },
      };
      expect(() => validateNodeMessage(msg)).toThrow("missing nodeId");
    });

    it("should reject capability update without capabilities array", () => {
      const msg = {
        type: "capability:update",
        nodeId: "node-1",
        timestamp: Date.now(),
        payload: {},
      };
      expect(() => validateNodeMessage(msg)).toThrow("missing or invalid capabilities");
    });
  });

  describe("disconnect message", () => {
    it("should validate valid disconnect message", () => {
      const msg = {
        type: "disconnect",
        nodeId: "node-1",
        timestamp: Date.now(),
        payload: { reason: "User requested" },
      };
      expect(() => validateNodeMessage(msg)).not.toThrow();
    });

    it("should reject disconnect without nodeId", () => {
      const msg = { type: "disconnect", timestamp: Date.now() };
      expect(() => validateNodeMessage(msg)).toThrow("missing nodeId");
    });
  });
});

