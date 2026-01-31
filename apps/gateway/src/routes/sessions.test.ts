/**
 * Tests for session routes.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import express, { Express } from "express";
import request from "supertest";
import { createSessionRoutes } from "./sessions.js";
import { SessionManager } from "../session/SessionManager.js";
import { MessageStore } from "../storage/MessageStore.js";

// Mock SessionManager
function createMockSessionManager() {
  const sessions = new Map<string, any>();

  return {
    listSessions: vi.fn(() => Array.from(sessions.values())),
    getSession: vi.fn((id: string) => sessions.get(id)),
    createSession: vi.fn((data: any) => {
      const session = {
        id: data.id || `session-${Date.now()}`,
        channelType: data.channelType || "test",
        channelId: data.channelId || "channel-1",
        chatId: data.chatId || "chat-1",
        userId: data.userId || "user-1",
        userName: data.userName || "Test User",
        createdAt: new Date(),
        lastActivityAt: new Date(),
        paired: data.paired || false,
      };
      sessions.set(session.id, session);
      return session;
    }),
    _sessions: sessions,
  } as unknown as SessionManager & { _sessions: Map<string, any> };
}

// Mock MessageStore
function createMockMessageStore() {
  const messages = new Map<string, any[]>();
  let messageId = 0;

  return {
    getMessageCount: vi.fn((sessionId: string) => messages.get(sessionId)?.length || 0),
    getMessages: vi.fn((sessionId: string, options?: any) => {
      const sessionMessages = messages.get(sessionId) || [];
      const limit = options?.limit || 50;
      return sessionMessages.slice(-limit);
    }),
    addMessage: vi.fn((sessionId: string, data: any) => {
      if (!messages.has(sessionId)) {
        messages.set(sessionId, []);
      }
      const message = {
        id: `msg-${++messageId}`,
        role: data.role,
        content: data.content,
        timestamp: new Date(),
        toolCalls: data.toolCalls,
      };
      messages.get(sessionId)!.push(message);
      return message;
    }),
    _messages: messages,
  } as unknown as MessageStore & { _messages: Map<string, any[]> };
}

describe("Session Routes", () => {
  let app: Express;
  let sessionManager: ReturnType<typeof createMockSessionManager>;
  let messageStore: ReturnType<typeof createMockMessageStore>;

  beforeEach(() => {
    sessionManager = createMockSessionManager();
    messageStore = createMockMessageStore();

    app = express();
    app.use(express.json());
    app.use("/api/sessions", createSessionRoutes(sessionManager, messageStore));
  });

  describe("GET /api/sessions", () => {
    it("should return empty list when no sessions", async () => {
      const res = await request(app).get("/api/sessions");
      expect(res.status).toBe(200);
      expect(res.body.sessions).toEqual([]);
    });

    it("should return list of sessions", async () => {
      sessionManager.createSession({ id: "session-1", channelType: "telegram" });
      sessionManager.createSession({ id: "session-2", channelType: "slack" });

      const res = await request(app).get("/api/sessions");
      expect(res.status).toBe(200);
      expect(res.body.sessions).toHaveLength(2);
    });

    it("should filter by channelType", async () => {
      sessionManager.createSession({ id: "session-1", channelType: "telegram" });
      sessionManager.createSession({ id: "session-2", channelType: "slack" });

      const res = await request(app).get("/api/sessions?channelType=telegram");
      expect(res.status).toBe(200);
      expect(res.body.sessions).toHaveLength(1);
      expect(res.body.sessions[0].channelType).toBe("telegram");
    });

    it("should respect limit parameter", async () => {
      for (let i = 0; i < 5; i++) {
        sessionManager.createSession({ id: `session-${i}` });
      }

      const res = await request(app).get("/api/sessions?limit=2");
      expect(res.status).toBe(200);
      expect(res.body.sessions).toHaveLength(2);
    });
  });

  describe("GET /api/sessions/:id", () => {
    it("should return session details", async () => {
      sessionManager.createSession({ id: "session-1", userName: "Alice" });

      const res = await request(app).get("/api/sessions/session-1");
      expect(res.status).toBe(200);
      expect(res.body.id).toBe("session-1");
      expect(res.body.userName).toBe("Alice");
    });

    it("should return 404 for non-existent session", async () => {
      const res = await request(app).get("/api/sessions/non-existent");
      expect(res.status).toBe(404);
      expect(res.body.error).toBe("Session not found");
    });
  });

  describe("GET /api/sessions/:id/history", () => {
    it("should return message history", async () => {
      sessionManager.createSession({ id: "session-1" });
      messageStore.addMessage("session-1", { role: "user", content: "Hello" });
      messageStore.addMessage("session-1", { role: "assistant", content: "Hi!" });

      const res = await request(app).get("/api/sessions/session-1/history");
      expect(res.status).toBe(200);
      expect(res.body.messages).toHaveLength(2);
    });

    it("should return 404 for non-existent session", async () => {
      const res = await request(app).get("/api/sessions/non-existent/history");
      expect(res.status).toBe(404);
    });

    it("should respect limit parameter", async () => {
      sessionManager.createSession({ id: "session-1" });
      for (let i = 0; i < 10; i++) {
        messageStore.addMessage("session-1", { role: "user", content: `Message ${i}` });
      }

      const res = await request(app).get("/api/sessions/session-1/history?limit=5");
      expect(res.status).toBe(200);
      expect(res.body.messages).toHaveLength(5);
    });
  });

  describe("POST /api/sessions/:id/message", () => {
    it("should add message to session", async () => {
      sessionManager.createSession({ id: "session-1" });

      const res = await request(app)
        .post("/api/sessions/session-1/message")
        .send({ content: "Hello from API" });

      expect(res.status).toBe(200);
      expect(res.body.success).toBe(true);
      expect(res.body.messageId).toBeDefined();
    });

    it("should return 400 when content is missing", async () => {
      sessionManager.createSession({ id: "session-1" });

      const res = await request(app)
        .post("/api/sessions/session-1/message")
        .send({});

      expect(res.status).toBe(400);
      expect(res.body.error).toBe("Content is required");
    });

    it("should return 404 for non-existent session", async () => {
      const res = await request(app)
        .post("/api/sessions/non-existent/message")
        .send({ content: "Hello" });

      expect(res.status).toBe(404);
    });

    it("should use specified role", async () => {
      sessionManager.createSession({ id: "session-1" });

      const res = await request(app)
        .post("/api/sessions/session-1/message")
        .send({ content: "System message", role: "system" });

      expect(res.status).toBe(200);
      expect(messageStore.addMessage).toHaveBeenCalledWith("session-1", {
        role: "system",
        content: "System message",
      });
    });

    it("should default to assistant role", async () => {
      sessionManager.createSession({ id: "session-1" });

      await request(app)
        .post("/api/sessions/session-1/message")
        .send({ content: "Response" });

      expect(messageStore.addMessage).toHaveBeenCalledWith("session-1", {
        role: "assistant",
        content: "Response",
      });
    });
  });
});

