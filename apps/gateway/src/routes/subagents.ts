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
 * Create subagent management routes.
 */
export function createSubagentRoutes(config: Config): Router {
  const router = Router();
  const agentUrl = config.agent?.url || 'http://127.0.0.1:18790';

  // GET /api/subagents - List all registered subagents
  router.get('/', async (_req: Request, res: Response) => {
    try {
      const response = await fetch(`${agentUrl}/subagents`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok) {
        const error = await response.text();
        return res.status(response.status).json({ ok: false, error });
      }

      const data = await response.json();
      res.json({ ok: true, ...data });
    } catch (err) {
      const error = err instanceof Error ? err.message : String(err);
      res.status(502).json({ ok: false, error: `Agent worker error: ${error}` });
    }
  });

  // GET /api/subagents/:name - Get a specific subagent
  router.get('/:name', async (req: Request<{ name: string }>, res: Response) => {
    try {
      const { name } = req.params;
      const response = await fetch(`${agentUrl}/subagents/${encodeURIComponent(name)}`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok) {
        if (response.status === 404) {
          return res.status(404).json({ ok: false, error: `Subagent '${name}' not found` });
        }
        const error = await response.text();
        return res.status(response.status).json({ ok: false, error });
      }

      const data = await response.json();
      res.json({ ok: true, ...data });
    } catch (err) {
      const error = err instanceof Error ? err.message : String(err);
      res.status(502).json({ ok: false, error: `Agent worker error: ${error}` });
    }
  });

  // POST /api/subagents - Register a new custom subagent
  router.post('/', async (req: Request<{}, {}, SubagentConfig>, res: Response) => {
    try {
      const subagentConfig = req.body;

      if (!subagentConfig.name || !subagentConfig.description || !subagentConfig.system_prompt) {
        return res.status(400).json({
          ok: false,
          error: 'Required fields: name, description, system_prompt',
        });
      }

      const response = await fetch(`${agentUrl}/subagents`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(subagentConfig),
      });

      if (!response.ok) {
        const error = await response.text();
        return res.status(response.status).json({ ok: false, error });
      }

      const data = await response.json();
      res.status(201).json({ ok: true, ...data });
    } catch (err) {
      const error = err instanceof Error ? err.message : String(err);
      res.status(502).json({ ok: false, error: `Agent worker error: ${error}` });
    }
  });

  // DELETE /api/subagents/:name - Unregister a custom subagent
  router.delete('/:name', async (req: Request<{ name: string }>, res: Response) => {
    try {
      const { name } = req.params;
      const response = await fetch(`${agentUrl}/subagents/${encodeURIComponent(name)}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok) {
        if (response.status === 404) {
          return res.status(404).json({ ok: false, error: `Subagent '${name}' not found` });
        }
        if (response.status === 403) {
          return res.status(403).json({ ok: false, error: 'Cannot delete builtin subagents' });
        }
        const error = await response.text();
        return res.status(response.status).json({ ok: false, error });
      }

      res.json({ ok: true, message: `Subagent '${name}' unregistered` });
    } catch (err) {
      const error = err instanceof Error ? err.message : String(err);
      res.status(502).json({ ok: false, error: `Agent worker error: ${error}` });
    }
  });

  return router;
}

