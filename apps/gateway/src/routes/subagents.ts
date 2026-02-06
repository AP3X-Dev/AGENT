/**
 * Subagent management API routes.
 *
 * Provides REST API endpoints for managing subagents:
 * - GET /api/subagents - List all registered subagents
 * - GET /api/subagents/:name - Get a specific subagent by name
 * - POST /api/subagents - Register a new custom subagent
 * - DELETE /api/subagents/:name - Unregister a custom subagent
 *
 * These endpoints proxy requests to the Agent Worker which maintains
 * the SubagentRegistry.
 */
import { Router, Request, Response } from 'express';
import type { Config } from '../config/schema.js';
import type { SessionManager } from '../session/SessionManager.js';
import type { DirectiveManager } from '../directives/DirectiveManager.js';
import { WORKER_URL, WORKER_FETCH_TIMEOUT_MS } from '../config/constants.js';

interface SubagentConfig {
  name: string;
  description: string;
  system_prompt: string;
  tools: string[];
  max_tokens?: number;
  max_turns?: number;
  model_override?: string | null;
  thinking_mode?: string;
  priority?: number;
}

interface SubagentResponse {
  config: SubagentConfig;
  source: 'builtin' | 'plugin' | 'user';
}

/**
 * Proxy a fetch request to the agent worker and forward the response.
 * Adds a standard timeout and maps network errors to 502.
 */
async function proxyToAgent(
  url: string,
  req: Request,
  res: Response,
  options: { method?: string; body?: string; successStatus?: number } = {},
): Promise<void> {
  const { method = 'GET', body, successStatus = 200 } = options;
  try {
    const fetchInit: RequestInit = {
      method,
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(WORKER_FETCH_TIMEOUT_MS),
    };
    if (body) fetchInit.body = body;

    const response = await fetch(url, fetchInit);

    if (!response.ok) {
      if (response.status === 404) {
        const error = await response.text();
        res.status(404).json({ ok: false, error: error || 'Not found' });
        return;
      }
      if (response.status === 403) {
        const error = await response.text();
        res.status(403).json({ ok: false, error: error || 'Forbidden' });
        return;
      }
      const error = await response.text();
      res.status(response.status).json({ ok: false, error });
      return;
    }

    const data = await response.json();
    res.status(successStatus).json({ ok: true, ...data });
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    res.status(502).json({ ok: false, error: `Agent worker error: ${error}` });
  }
}

/**
 * Create subagent management routes.
 */
export function createSubagentRoutes(_config: Config): Router {
  const router = Router();

  // GET /api/subagents - List all registered subagents
  router.get('/', async (req: Request, res: Response) => {
    await proxyToAgent(`${WORKER_URL}/subagents`, req, res);
  });

  // GET /api/subagents/:name - Get a specific subagent
  router.get('/:name', async (req: Request<{ name: string }>, res: Response) => {
    const { name } = req.params;
    await proxyToAgent(`${WORKER_URL}/subagents/${encodeURIComponent(name)}`, req, res);
  });

  // POST /api/subagents - Register a new custom subagent
  router.post('/', async (req: Request<{}, {}, SubagentConfig>, res: Response) => {
    const subagentConfig = req.body;

    if (!subagentConfig.name || !subagentConfig.description || !subagentConfig.system_prompt) {
      res.status(400).json({
        ok: false,
        error: 'Required fields: name, description, system_prompt',
      });
      return;
    }

    await proxyToAgent(`${WORKER_URL}/subagents`, req, res, {
      method: 'POST',
      body: JSON.stringify(subagentConfig),
      successStatus: 201,
    });
  });

  // DELETE /api/subagents/:name - Unregister a custom subagent
  router.delete('/:name', async (req: Request<{ name: string }>, res: Response) => {
    const { name } = req.params;
    await proxyToAgent(`${WORKER_URL}/subagents/${encodeURIComponent(name)}`, req, res, {
      method: 'DELETE',
    });
  });

  return router;
}

/**
 * Create enhanced session and directive management routes.
 */
export function createSessionDirectiveRoutes(
  sessionManager: SessionManager,
  directiveManager: DirectiveManager,
): Router {
  const router = Router();

  // ─────────────────────────────────────────────────────────────────
  // Session Management Routes
  // ─────────────────────────────────────────────────────────────────

  // GET /api/sessions - List enhanced sessions with optional filters
  router.get('/', (_req: Request, res: Response) => {
    try {
      const store = sessionManager.getSessionStore();
      if (!store) {
        return res.status(503).json({ ok: false, error: 'Session store not available' });
      }

      const filter: Record<string, any> = {};
      if (_req.query.channelType) filter.channelType = _req.query.channelType as string;
      if (_req.query.activationMode) filter.activationMode = _req.query.activationMode as string;
      if (_req.query.assignedAgent) filter.assignedAgent = _req.query.assignedAgent as string;
      if (_req.query.minPriority) filter.minPriority = parseInt(_req.query.minPriority as string);
      if (_req.query.maxPriority) filter.maxPriority = parseInt(_req.query.maxPriority as string);

      const sessions = store.list(Object.keys(filter).length > 0 ? filter : undefined);
      res.json({ ok: true, sessions });
    } catch (err) {
      const error = err instanceof Error ? err.message : String(err);
      res.status(500).json({ ok: false, error });
    }
  });

  // GET /api/sessions/:id - Get enhanced session details
  router.get('/:id', (req: Request<{ id: string }>, res: Response) => {
    try {
      const sessionId = decodeURIComponent(req.params.id);
      const enhanced = sessionManager.getEnhancedSession(sessionId);

      if (!enhanced) {
        return res.status(404).json({ ok: false, error: 'Session not found' });
      }

      res.json({ ok: true, session: enhanced });
    } catch (err) {
      const error = err instanceof Error ? err.message : String(err);
      res.status(500).json({ ok: false, error });
    }
  });

  // PATCH /api/sessions/:id - Update session fields
  router.patch('/:id', (req: Request<{ id: string }>, res: Response) => {
    try {
      const sessionId = decodeURIComponent(req.params.id);
      const { priority, assignedAgent, activationMode, activationKeywords, quotas, metadata } = req.body;

      const updates: Record<string, any> = {};
      if (priority !== undefined) updates.priority = priority;
      if (assignedAgent !== undefined) updates.assignedAgent = assignedAgent;
      if (activationMode !== undefined) updates.activationMode = activationMode;
      if (activationKeywords !== undefined) updates.activationKeywords = activationKeywords;
      if (quotas !== undefined) updates.quotas = quotas;
      if (metadata !== undefined) updates.metadata = metadata;

      const updated = sessionManager.updateSession(sessionId, updates);
      if (!updated) {
        return res.status(404).json({ ok: false, error: 'Session not found' });
      }

      res.json({ ok: true, session: updated });
    } catch (err) {
      const error = err instanceof Error ? err.message : String(err);
      res.status(500).json({ ok: false, error });
    }
  });

  // ─────────────────────────────────────────────────────────────────
  // Directive Routes
  // ─────────────────────────────────────────────────────────────────

  // GET /api/sessions/:id/directives - List directives
  router.get('/:id/directives', (req: Request<{ id: string }>, res: Response) => {
    try {
      const sessionId = decodeURIComponent(req.params.id);
      const directives = directiveManager.list(sessionId);
      res.json({ ok: true, directives });
    } catch (err) {
      const error = err instanceof Error ? err.message : String(err);
      res.status(500).json({ ok: false, error });
    }
  });

  // POST /api/sessions/:id/directives - Add a directive
  router.post('/:id/directives', (req: Request<{ id: string }>, res: Response) => {
    try {
      const sessionId = decodeURIComponent(req.params.id);
      const { type, content, priority, active } = req.body;

      if (!content) {
        return res.status(400).json({ ok: false, error: 'Missing content field' });
      }

      const directive = directiveManager.add(sessionId, {
        type: type || 'user',
        content,
        priority: priority ?? 5,
        active: active !== false,
      });

      res.status(201).json({ ok: true, directive });
    } catch (err) {
      const error = err instanceof Error ? err.message : String(err);
      if (error.includes('not found')) {
        return res.status(404).json({ ok: false, error });
      }
      res.status(500).json({ ok: false, error });
    }
  });

  // DELETE /api/sessions/:id/directives/:directiveId - Remove a directive
  router.delete(
    '/:id/directives/:directiveId',
    (req: Request<{ id: string; directiveId: string }>, res: Response) => {
      try {
        const sessionId = decodeURIComponent(req.params.id);
        const { directiveId } = req.params;

        const removed = directiveManager.remove(sessionId, directiveId);
        if (!removed) {
          return res.status(404).json({ ok: false, error: 'Directive not found' });
        }

        res.json({ ok: true, message: 'Directive removed' });
      } catch (err) {
        const error = err instanceof Error ? err.message : String(err);
        res.status(500).json({ ok: false, error });
      }
    },
  );

  // PATCH /api/sessions/:id/directives/:directiveId - Toggle directive active status
  router.patch(
    '/:id/directives/:directiveId',
    (req: Request<{ id: string; directiveId: string }>, res: Response) => {
      try {
        const sessionId = decodeURIComponent(req.params.id);
        const { directiveId } = req.params;
        const { active } = req.body;

        if (active === undefined) {
          return res.status(400).json({ ok: false, error: 'Missing active field' });
        }

        const toggled = directiveManager.toggle(sessionId, directiveId, active);
        if (!toggled) {
          return res.status(404).json({ ok: false, error: 'Directive not found' });
        }

        res.json({ ok: true, message: `Directive ${active ? 'activated' : 'deactivated'}` });
      } catch (err) {
        const error = err instanceof Error ? err.message : String(err);
        res.status(500).json({ ok: false, error });
      }
    },
  );

  return router;
}

