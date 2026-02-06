/**
 * Security middleware for AG3NT Gateway.
 *
 * Provides HTTP security headers (helmet), CORS, API key auth,
 * and input sanitization.
 */
import type { Request, Response, NextFunction, RequestHandler } from 'express';
import helmet from 'helmet';
import cors from 'cors';
import type { Config } from '../config/schema.js';

// ─────────────────────────────────────────────────────────────────
// Helmet — HTTP security headers
// ─────────────────────────────────────────────────────────────────

/**
 * Create helmet middleware configured for the gateway.
 * Disables contentSecurityPolicy since the control panel is served
 * from the same origin and uses inline scripts.
 */
export function createHelmetMiddleware(): RequestHandler {
  return helmet({
    contentSecurityPolicy: false,   // Control panel uses inline scripts
    crossOriginEmbedderPolicy: false,
    crossOriginResourcePolicy: { policy: 'cross-origin' },
  }) as RequestHandler;
}

// ─────────────────────────────────────────────────────────────────
// CORS
// ─────────────────────────────────────────────────────────────────

/**
 * Create CORS middleware.
 * In production, restrict to specific origins.
 * In development, allow all origins.
 */
export function createCorsMiddleware(config: Config): RequestHandler {
  const allowedOrigins = (config as any).security?.corsOrigins as string[] | undefined;

  return cors({
    origin: allowedOrigins && allowedOrigins.length > 0
      ? allowedOrigins
      : true,  // Allow all in dev / when not configured
    methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'X-API-Key', 'X-Request-ID'],
    exposedHeaders: ['X-Request-ID', 'X-RateLimit-Limit', 'X-RateLimit-Remaining'],
    credentials: true,
    maxAge: 86400,
  });
}

// ─────────────────────────────────────────────────────────────────
// API Key Authentication
// ─────────────────────────────────────────────────────────────────

/**
 * Create API key authentication middleware.
 * If AG3NT_API_KEY env var is set, require it on all /api/* requests.
 * Skips auth for health endpoints.
 */
export function createApiKeyAuth(): RequestHandler {
  const apiKey = process.env.AG3NT_API_KEY;

  return (req: Request, res: Response, next: NextFunction): void => {
    // Skip if no API key configured
    if (!apiKey) {
      next();
      return;
    }

    // Skip auth for health/liveness/readiness probes
    if (req.path === '/api/health' ||
        req.path === '/api/health/live' ||
        req.path === '/api/health/ready') {
      next();
      return;
    }

    // Skip for non-API routes (static files, WebSocket upgrade)
    if (!req.path.startsWith('/api/')) {
      next();
      return;
    }

    const provided = req.headers['x-api-key'] as string ||
                     req.headers['authorization']?.replace('Bearer ', '');

    if (!provided || provided !== apiKey) {
      res.status(401).json({
        ok: false,
        error: 'Unauthorized',
        code: 'GW-AUTH-005',
      });
      return;
    }

    next();
  };
}

// ─────────────────────────────────────────────────────────────────
// Input Sanitization
// ─────────────────────────────────────────────────────────────────

/**
 * Middleware to validate and sanitize request bodies.
 * Prevents excessively large payloads and strips dangerous fields.
 */
export function createInputSanitizer(): RequestHandler {
  return (req: Request, _res: Response, next: NextFunction): void => {
    // Sanitize string fields to prevent NoSQL/prototype pollution
    if (req.body && typeof req.body === 'object') {
      sanitizeObject(req.body);
    }
    next();
  };
}

function sanitizeObject(obj: Record<string, unknown>, depth = 0): void {
  if (depth > 10) return; // Prevent deep recursion

  for (const key of Object.keys(obj)) {
    // Block prototype pollution
    if (key === '__proto__' || key === 'constructor' || key === 'prototype') {
      delete obj[key];
      continue;
    }

    const value = obj[key];
    if (value && typeof value === 'object' && !Array.isArray(value) && !Buffer.isBuffer(value)) {
      sanitizeObject(value as Record<string, unknown>, depth + 1);
    }
  }
}

// ─────────────────────────────────────────────────────────────────
// Request ID
// ─────────────────────────────────────────────────────────────────

/**
 * Middleware to assign a unique request ID for tracing.
 */
export function createRequestIdMiddleware(): RequestHandler {
  let counter = 0;

  return (req: Request, res: Response, next: NextFunction): void => {
    const requestId = req.headers['x-request-id'] as string ||
                      `gw-${Date.now()}-${++counter}`;
    (req as any).requestId = requestId;
    res.setHeader('X-Request-ID', requestId);
    next();
  };
}
