/**
 * Enhanced health and monitoring endpoints for AG3NT Gateway.
 *
 * Provides Kubernetes-style liveness/readiness probes plus
 * detailed health checks with dependency status.
 */
import { Router, type Request, type Response } from 'express';
import type { SessionManager } from '../session/SessionManager.js';
import type { ChannelRegistry } from '../channels/ChannelRegistry.js';
import { getUsageTracker } from '../monitoring/index.js';

const AGENT_URL = process.env.AG3NT_AGENT_URL || 'http://127.0.0.1:18790';
const startedAt = Date.now();

interface DependencyCheck {
  name: string;
  status: 'healthy' | 'degraded' | 'unhealthy';
  latencyMs?: number;
  message?: string;
}

/**
 * Create health check routes.
 */
export function createHealthRoutes(deps: {
  sessionManager: SessionManager;
  channelRegistry: ChannelRegistry;
}): Router {
  const { sessionManager, channelRegistry } = deps;
  const router = Router();

  // ─────────────────────────────────────────────────────────────
  // GET /api/health — Full health check with dependency status
  // ─────────────────────────────────────────────────────────────
  router.get('/', async (_req: Request, res: Response) => {
    const checks: DependencyCheck[] = [];

    // Check agent worker
    checks.push(await checkAgentWorker());

    // Check SQLite (session store)
    checks.push(checkSessionStore(sessionManager));

    // Check channels
    checks.push(checkChannels(channelRegistry));

    const overall = checks.every((c) => c.status === 'healthy')
      ? 'healthy'
      : checks.some((c) => c.status === 'unhealthy')
        ? 'unhealthy'
        : 'degraded';

    const statusCode = overall === 'healthy' ? 200 : overall === 'degraded' ? 200 : 503;

    res.status(statusCode).json({
      ok: overall !== 'unhealthy',
      status: overall,
      name: 'ag3nt-gateway',
      version: process.env.npm_package_version || '0.0.1',
      uptime: Math.floor((Date.now() - startedAt) / 1000),
      timestamp: new Date().toISOString(),
      dependencies: checks,
      sessions: sessionManager.listSessions().length,
      channels: channelRegistry.all().map((a) => ({
        id: a.id,
        type: a.type,
        connected: a.isConnected(),
      })),
      process: {
        pid: process.pid,
        memoryMB: Math.round(process.memoryUsage().rss / 1024 / 1024),
        uptimeSeconds: Math.floor(process.uptime()),
        nodeVersion: process.version,
      },
    });
  });

  // ─────────────────────────────────────────────────────────────
  // GET /api/health/live — Kubernetes liveness probe
  // Lightweight: just checks if the process is running
  // ─────────────────────────────────────────────────────────────
  router.get('/live', (_req: Request, res: Response) => {
    res.json({
      ok: true,
      status: 'alive',
      uptime: Math.floor((Date.now() - startedAt) / 1000),
    });
  });

  // ─────────────────────────────────────────────────────────────
  // GET /api/health/ready — Kubernetes readiness probe
  // Checks if the gateway is ready to accept traffic
  // ─────────────────────────────────────────────────────────────
  router.get('/ready', async (_req: Request, res: Response) => {
    // Check that the agent worker is reachable
    const agentCheck = await checkAgentWorker();

    if (agentCheck.status === 'unhealthy') {
      res.status(503).json({
        ok: false,
        status: 'not_ready',
        reason: 'Agent worker is not available',
        agent: agentCheck,
      });
      return;
    }

    res.json({
      ok: true,
      status: 'ready',
      agent: agentCheck,
    });
  });

  // ─────────────────────────────────────────────────────────────
  // GET /api/health/metrics — Operational metrics
  // ─────────────────────────────────────────────────────────────
  router.get('/metrics', (_req: Request, res: Response) => {
    const tracker = getUsageTracker();
    const stats = tracker.getUsageStats();
    const mem = process.memoryUsage();

    res.json({
      ok: true,
      timestamp: new Date().toISOString(),
      uptime: Math.floor(process.uptime()),
      process: {
        pid: process.pid,
        memory: {
          rss: mem.rss,
          heapUsed: mem.heapUsed,
          heapTotal: mem.heapTotal,
          external: mem.external,
        },
        cpu: process.cpuUsage(),
      },
      api: {
        totalCalls: stats.totalCalls,
        successfulCalls: stats.successfulCalls,
        failedCalls: stats.failedCalls,
        averageLatencyMs: stats.averageLatencyMs,
        totalTokens: stats.totalTokens,
        totalCost: stats.totalCost,
      },
      sessions: {
        active: sessionManager.listSessions().length,
        pending: sessionManager.getPendingSessions().length,
      },
      channels: {
        total: channelRegistry.all().length,
        connected: channelRegistry.all().filter((a) => a.isConnected()).length,
      },
    });
  });

  return router;
}

// ─────────────────────────────────────────────────────────────────
// Dependency Check Helpers
// ─────────────────────────────────────────────────────────────────

async function checkAgentWorker(): Promise<DependencyCheck> {
  const startTime = Date.now();
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);
    const response = await fetch(`${AGENT_URL}/health`, { signal: controller.signal });
    clearTimeout(timeout);
    const latencyMs = Date.now() - startTime;

    if (response.ok) {
      return { name: 'agent-worker', status: 'healthy', latencyMs };
    }
    return { name: 'agent-worker', status: 'degraded', latencyMs, message: `HTTP ${response.status}` };
  } catch (err) {
    return {
      name: 'agent-worker',
      status: 'unhealthy',
      latencyMs: Date.now() - startTime,
      message: err instanceof Error ? err.message : 'Connection failed',
    };
  }
}

function checkSessionStore(sessionManager: SessionManager): DependencyCheck {
  try {
    const store = sessionManager.getSessionStore();
    if (!store) {
      return { name: 'session-store', status: 'degraded', message: 'No persistent store configured' };
    }
    // Quick read test
    store.list({ channelType: '__healthcheck__' });
    return { name: 'session-store', status: 'healthy' };
  } catch (err) {
    return {
      name: 'session-store',
      status: 'unhealthy',
      message: err instanceof Error ? err.message : 'Query failed',
    };
  }
}

function checkChannels(channelRegistry: ChannelRegistry): DependencyCheck {
  const adapters = channelRegistry.all();
  if (adapters.length === 0) {
    return { name: 'channels', status: 'healthy', message: 'No channel adapters registered' };
  }
  const connected = adapters.filter((a) => a.isConnected()).length;
  if (connected === adapters.length) {
    return { name: 'channels', status: 'healthy', message: `${connected}/${adapters.length} connected` };
  }
  if (connected > 0) {
    return { name: 'channels', status: 'degraded', message: `${connected}/${adapters.length} connected` };
  }
  return { name: 'channels', status: 'unhealthy', message: `0/${adapters.length} connected` };
}
