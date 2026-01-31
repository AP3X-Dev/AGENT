/**
 * Session management API routes.
 *
 * Provides REST API endpoints for session management including
 * listing sessions, getting session details, message history, and sending messages.
 */
import { Router, Request, Response } from 'express';
import { SessionManager } from '../session/SessionManager.js';
import { MessageStore } from '../storage/MessageStore.js';

export interface ListSessionsQuery {
  channelType?: string;
  limit?: string;
}

export interface GetHistoryQuery {
  limit?: string;
  before?: string;
}

export interface SendMessageBody {
  content: string;
  role?: 'user' | 'assistant' | 'system';
}

/**
 * Create session routes with dependency injection.
 */
export function createSessionRoutes(
  sessionManager: SessionManager,
  messageStore: MessageStore,
): Router {
  const router = Router();

  // GET /api/sessions - List all sessions
  router.get('/', (req: Request<{}, {}, {}, ListSessionsQuery>, res: Response) => {
    try {
      const { channelType, limit = '20' } = req.query;
      const maxLimit = Math.min(parseInt(limit, 10) || 20, 100);

      let sessions = sessionManager.listSessions();

      // Filter by channel type if provided
      if (channelType) {
        sessions = sessions.filter((s) => s.channelType === channelType);
      }

      // Apply limit
      sessions = sessions.slice(0, maxLimit);

      res.json({
        sessions: sessions.map((s) => ({
          id: s.id,
          channelType: s.channelType,
          channelId: s.channelId,
          chatId: s.chatId,
          userId: s.userId,
          userName: s.userName,
          createdAt: s.createdAt.toISOString(),
          lastActivityAt: s.lastActivityAt.toISOString(),
          paired: s.paired,
          messageCount: messageStore.getMessageCount(s.id),
        })),
      });
    } catch (error) {
      console.error('[sessions] Failed to list sessions:', error);
      res.status(500).json({ error: 'Failed to list sessions' });
    }
  });

  // GET /api/sessions/:id - Get session details
  router.get('/:id', (req: Request, res: Response) => {
    try {
      const sessionId = decodeURIComponent(req.params.id);
      const session = sessionManager.getSession(sessionId);

      if (!session) {
        return res.status(404).json({ error: 'Session not found' });
      }

      res.json({
        id: session.id,
        channelType: session.channelType,
        channelId: session.channelId,
        chatId: session.chatId,
        userId: session.userId,
        userName: session.userName,
        createdAt: session.createdAt.toISOString(),
        lastActivityAt: session.lastActivityAt.toISOString(),
        paired: session.paired,
        messageCount: messageStore.getMessageCount(session.id),
      });
    } catch (error) {
      console.error('[sessions] Failed to get session:', error);
      res.status(500).json({ error: 'Failed to get session' });
    }
  });

  // GET /api/sessions/:id/history - Get message history
  router.get(
    '/:id/history',
    (req: Request<{ id: string }, {}, {}, GetHistoryQuery>, res: Response) => {
      try {
        const sessionId = decodeURIComponent(req.params.id);
        const { limit = '50', before } = req.query;
        const maxLimit = Math.min(parseInt(limit, 10) || 50, 200);

        // Verify session exists
        const session = sessionManager.getSession(sessionId);
        if (!session) {
          return res.status(404).json({ error: 'Session not found' });
        }

        const messages = messageStore.getMessages(sessionId, {
          limit: maxLimit,
          before: before ? new Date(before) : undefined,
        });

        res.json({
          messages: messages.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            timestamp: m.timestamp.toISOString(),
            toolCalls: m.toolCalls,
          })),
        });
      } catch (error) {
        console.error('[sessions] Failed to get history:', error);
        res.status(500).json({ error: 'Failed to get history' });
      }
    },
  );

  // POST /api/sessions/:id/message - Send message to session
  router.post(
    '/:id/message',
    (req: Request<{ id: string }, {}, SendMessageBody>, res: Response) => {
      try {
        const sessionId = decodeURIComponent(req.params.id);
        const { content, role = 'assistant' } = req.body;

        if (!content || typeof content !== 'string') {
          return res.status(400).json({ error: 'Content is required' });
        }

        // Verify session exists
        const session = sessionManager.getSession(sessionId);
        if (!session) {
          return res.status(404).json({ error: 'Session not found' });
        }

        const message = messageStore.addMessage(sessionId, {
          role,
          content,
        });

        res.json({
          success: true,
          messageId: message.id,
        });
      } catch (error) {
        console.error('[sessions] Failed to send message:', error);
        res.status(500).json({ error: 'Failed to send message' });
      }
    },
  );

  return router;
}

