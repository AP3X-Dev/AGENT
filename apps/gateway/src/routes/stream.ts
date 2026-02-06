/**
 * Server-Sent Events (SSE) endpoint for real-time tool streaming.
 *
 * Clients can subscribe to receive real-time updates during tool execution:
 * - tool_start: Tool execution begins
 * - tool_progress: Intermediate progress updates
 * - tool_end: Tool execution completed
 * - tool_error: Tool execution failed
 *
 * Usage:
 *   GET /api/stream/:sessionId
 *   Accept: text/event-stream
 */

import { Router, Request, Response } from "express";
import { EventEmitter } from "events";

// Global event bus for tool events
export const toolEventBus = new EventEmitter();
toolEventBus.setMaxListeners(100); // Allow many concurrent SSE connections

// Types for tool events
export interface ToolEvent {
  event_type: "tool_start" | "tool_progress" | "tool_end" | "tool_error";
  session_id: string;
  tool_name: string;
  tool_call_id: string;
  timestamp: number;
  // Additional fields depending on event type
  args?: Record<string, unknown>;
  message?: string;
  progress?: number;
  duration_ms?: number;
  error?: string;
  error_type?: string;
  preview?: string;
  total_size?: number;
}

export interface StreamMessage {
  type: "stream";
  request_id: string;
  event: ToolEvent;
}

/**
 * Forward a stream event from WebSocket to SSE subscribers.
 */
export function forwardStreamEvent(msg: StreamMessage): void {
  const { event } = msg;
  toolEventBus.emit(`session:${event.session_id}`, event);
  toolEventBus.emit("all", event); // For debugging/monitoring
}

/**
 * Create the stream router.
 */
export function createStreamRouter(): Router {
  const router = Router();

  /**
   * SSE endpoint for subscribing to tool events for a session.
   */
  router.get("/:sessionId", (req: Request, res: Response) => {
    const { sessionId } = req.params;

    // Set SSE headers
    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.setHeader("X-Accel-Buffering", "no"); // Disable nginx buffering
    res.flushHeaders();

    // Send initial connection event
    res.write(`event: connected\ndata: ${JSON.stringify({ session_id: sessionId })}\n\n`);

    // Subscribe to events for this session
    const onEvent = (event: ToolEvent) => {
      try {
        res.write(`event: ${event.event_type}\n`);
        res.write(`data: ${JSON.stringify(event)}\n\n`);
      } catch {
        // Client disconnected
      }
    };

    toolEventBus.on(`session:${sessionId}`, onEvent);

    // Send keepalive every 30 seconds
    const keepaliveInterval = setInterval(() => {
      try {
        res.write(`: keepalive\n\n`);
      } catch {
        // Client disconnected
      }
    }, 30000);

    // Clean up on disconnect
    req.on("close", () => {
      toolEventBus.off(`session:${sessionId}`, onEvent);
      clearInterval(keepaliveInterval);
    });
  });

  /**
   * SSE endpoint for subscribing to all tool events (for monitoring).
   */
  router.get("/", (req: Request, res: Response) => {
    // Set SSE headers
    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.setHeader("X-Accel-Buffering", "no");
    res.flushHeaders();

    res.write(`event: connected\ndata: ${JSON.stringify({ type: "all" })}\n\n`);

    const onEvent = (event: ToolEvent) => {
      try {
        res.write(`event: ${event.event_type}\n`);
        res.write(`data: ${JSON.stringify(event)}\n\n`);
      } catch {
        // Client disconnected
      }
    };

    toolEventBus.on("all", onEvent);

    const keepaliveInterval = setInterval(() => {
      try {
        res.write(`: keepalive\n\n`);
      } catch {
        // Client disconnected
      }
    }, 30000);

    req.on("close", () => {
      toolEventBus.off("all", onEvent);
      clearInterval(keepaliveInterval);
    });
  });

  /**
   * Get stream statistics.
   */
  router.get("/stats", (_req: Request, res: Response) => {
    res.json({
      listeners: {
        all: toolEventBus.listenerCount("all"),
      },
    });
  });

  return router;
}
