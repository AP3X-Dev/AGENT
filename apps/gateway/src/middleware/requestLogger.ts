/**
 * HTTP request logging middleware for AG3NT Gateway.
 *
 * Logs every API request with structured JSON format, including
 * method, path, status code, latency, and request ID.
 */
import type { Request, Response, NextFunction, RequestHandler } from 'express';
import { gatewayLogs } from '../logs/index.js';

export interface RequestLogEntry {
  requestId: string;
  method: string;
  path: string;
  statusCode: number;
  latencyMs: number;
  ip: string;
  userAgent: string;
  contentLength: number;
  responseLength: number;
}

/**
 * Create request logging middleware.
 * Logs each completed HTTP request with timing and metadata.
 */
export function createRequestLogger(options?: {
  /** Paths to skip logging (e.g., health checks) */
  skipPaths?: string[];
  /** Minimum latency (ms) to log at warn level */
  slowThresholdMs?: number;
}): RequestHandler {
  const skipPaths = options?.skipPaths ?? ['/api/health/live'];
  const slowThresholdMs = options?.slowThresholdMs ?? 5000;

  return (req: Request, res: Response, next: NextFunction): void => {
    // Skip noisy paths
    if (skipPaths.some((p) => req.path === p)) {
      next();
      return;
    }

    const startTime = Date.now();
    const requestId = (req as any).requestId || 'unknown';

    // Capture response finish
    const originalEnd = res.end;
    let responseLength = 0;

    res.end = function (this: Response, ...args: any[]) {
      const latencyMs = Date.now() - startTime;
      const contentLength = parseInt(res.getHeader('content-length') as string) || 0;
      responseLength = contentLength;

      const entry: RequestLogEntry = {
        requestId,
        method: req.method,
        path: req.originalUrl || req.path,
        statusCode: res.statusCode,
        latencyMs,
        ip: getClientIp(req),
        userAgent: (req.headers['user-agent'] || '').slice(0, 100),
        contentLength: parseInt(req.headers['content-length'] as string) || 0,
        responseLength,
      };

      const level = res.statusCode >= 500
        ? 'error'
        : res.statusCode >= 400
          ? 'warn'
          : latencyMs >= slowThresholdMs
            ? 'warn'
            : 'info';

      const statusEmoji = res.statusCode >= 500 ? '💥' : res.statusCode >= 400 ? '⚠️' : '✓';

      gatewayLogs.log(
        level,
        'HTTP',
        `${statusEmoji} ${req.method} ${req.originalUrl || req.path} ${res.statusCode} (${latencyMs}ms)`,
        entry as any,
      );

      return originalEnd.apply(this, args as any);
    } as any;

    next();
  };
}

function getClientIp(req: Request): string {
  const forwarded = req.headers['x-forwarded-for'];
  if (typeof forwarded === 'string') {
    return forwarded.split(',')[0].trim();
  }
  return req.socket.remoteAddress || 'unknown';
}
