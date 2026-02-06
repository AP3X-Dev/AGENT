/**
 * State API routes for Gateway ↔ Agent state synchronization.
 *
 * These routes allow the Agent Worker to read and update shared session state.
 *
 * Endpoints:
 * - GET /api/state/:sessionId - Get session state
 * - PUT /api/state/:sessionId - Set full session state
 * - PATCH /api/state/:sessionId - Update session state
 * - DELETE /api/state/:sessionId - Delete session state
 * - GET /api/state - List all sessions
 * - GET /api/state/stats - Get store statistics
 */

import { Router, Request, Response } from "express";
import { getStateStore, InMemoryStateStore } from "../state/StateStore.js";
import { createSessionState, type SessionState } from "../state/types.js";

/**
 * Create the state API router.
 */
export function createStateRouter(): Router {
  const router = Router();

  /**
   * Get session state.
   */
  router.get("/:sessionId", async (req: Request, res: Response) => {
    try {
      const { sessionId } = req.params;
      const store = await getStateStore();
      const state = await store.getSession(sessionId);

      if (!state) {
        res.status(404).json({
          ok: false,
          error: "Session not found",
          sessionId,
        });
        return;
      }

      res.json({ ok: true, state });
    } catch (err) {
      res.status(500).json({
        ok: false,
        error: err instanceof Error ? err.message : "Unknown error",
      });
    }
  });

  /**
   * Set full session state.
   */
  router.put("/:sessionId", async (req: Request, res: Response) => {
    try {
      const { sessionId } = req.params;
      const state = req.body as SessionState;

      if (!state || state.sessionId !== sessionId) {
        res.status(400).json({
          ok: false,
          error: "Invalid state: sessionId mismatch",
        });
        return;
      }

      const store = await getStateStore();
      await store.setSession(sessionId, state);

      res.json({ ok: true, state });
    } catch (err) {
      res.status(500).json({
        ok: false,
        error: err instanceof Error ? err.message : "Unknown error",
      });
    }
  });

  /**
   * Update session state (partial update).
   */
  router.patch("/:sessionId", async (req: Request, res: Response) => {
    try {
      const { sessionId } = req.params;
      const updates = req.body as Partial<SessionState>;
      const source = (req.headers["x-update-source"] as "gateway" | "agent") || "gateway";

      const store = await getStateStore();

      // Check if session exists
      const existing = await store.getSession(sessionId);
      if (!existing) {
        res.status(404).json({
          ok: false,
          error: "Session not found",
          sessionId,
        });
        return;
      }

      const updated = await store.updateSession(sessionId, updates, source);

      res.json({ ok: true, state: updated });
    } catch (err) {
      res.status(500).json({
        ok: false,
        error: err instanceof Error ? err.message : "Unknown error",
      });
    }
  });

  /**
   * Delete session state.
   */
  router.delete("/:sessionId", async (req: Request, res: Response) => {
    try {
      const { sessionId } = req.params;
      const store = await getStateStore();
      const deleted = await store.deleteSession(sessionId);

      if (!deleted) {
        res.status(404).json({
          ok: false,
          error: "Session not found",
          sessionId,
        });
        return;
      }

      res.json({ ok: true, sessionId });
    } catch (err) {
      res.status(500).json({
        ok: false,
        error: err instanceof Error ? err.message : "Unknown error",
      });
    }
  });

  /**
   * List all sessions.
   */
  router.get("/", async (_req: Request, res: Response) => {
    try {
      const store = await getStateStore();
      const sessionIds = await store.listSessions();

      res.json({
        ok: true,
        sessions: sessionIds,
        count: sessionIds.length,
      });
    } catch (err) {
      res.status(500).json({
        ok: false,
        error: err instanceof Error ? err.message : "Unknown error",
      });
    }
  });

  /**
   * Get store statistics.
   */
  router.get("/stats", async (_req: Request, res: Response) => {
    try {
      const store = await getStateStore();

      // Get stats if available (InMemoryStateStore has getStats)
      const stats =
        store instanceof InMemoryStateStore
          ? store.getStats()
          : { sessionCount: (await store.listSessions()).length };

      res.json({
        ok: true,
        stats,
        backend: store instanceof InMemoryStateStore ? "memory" : "redis",
      });
    } catch (err) {
      res.status(500).json({
        ok: false,
        error: err instanceof Error ? err.message : "Unknown error",
      });
    }
  });

  /**
   * Create a new session with defaults.
   */
  router.post("/", async (req: Request, res: Response) => {
    try {
      const { sessionId, channelType, channelId, chatId, userId, userName } =
        req.body;

      if (!sessionId || !channelType || !channelId || !chatId || !userId) {
        res.status(400).json({
          ok: false,
          error: "Missing required fields: sessionId, channelType, channelId, chatId, userId",
        });
        return;
      }

      const store = await getStateStore();

      // Check if session already exists
      const existing = await store.getSession(sessionId);
      if (existing) {
        res.status(409).json({
          ok: false,
          error: "Session already exists",
          sessionId,
        });
        return;
      }

      const state = createSessionState(
        sessionId,
        channelType,
        channelId,
        chatId,
        userId,
        userName
      );

      await store.setSession(sessionId, state);

      res.status(201).json({ ok: true, state });
    } catch (err) {
      res.status(500).json({
        ok: false,
        error: err instanceof Error ? err.message : "Unknown error",
      });
    }
  });

  return router;
}
