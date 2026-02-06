/**
 * HTTP rate limiting middleware for AG3NT Gateway.
 *
 * Provides per-IP and per-session rate limiting using a sliding
 * window counter approach. No external dependencies required.
 */
import type { Request, Response, NextFunction, RequestHandler } from 'express';

// ─────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────

export interface RateLimitConfig {
  /** Maximum requests per window */
  maxRequests: number;
  /** Window duration in milliseconds */
  windowMs: number;
  /** Custom key extractor (default: IP address) */
  keyExtractor?: (req: Request) => string;
  /** Message returned when rate limited */
  message?: string;
  /** Skip rate limiting for these paths */
  skipPaths?: string[];
}

interface WindowEntry {
  count: number;
  resetAt: number;
}

// ─────────────────────────────────────────────────────────────────
// Rate Limiter
// ─────────────────────────────────────────────────────────────────

export class HttpRateLimiter {
  private windows: Map<string, WindowEntry> = new Map();
  private config: RateLimitConfig;
  private cleanupInterval: ReturnType<typeof setInterval>;

  constructor(config: RateLimitConfig) {
    this.config = config;

    // Periodically clean up expired entries
    this.cleanupInterval = setInterval(() => {
      const now = Date.now();
      for (const [key, entry] of this.windows) {
        if (entry.resetAt <= now) {
          this.windows.delete(key);
        }
      }
    }, Math.max(config.windowMs, 60_000));
  }

  /**
   * Check if a request should be allowed.
   */
  check(key: string): { allowed: boolean; remaining: number; resetAt: number } {
    const now = Date.now();
    let entry = this.windows.get(key);

    // Reset window if expired
    if (!entry || entry.resetAt <= now) {
      entry = { count: 0, resetAt: now + this.config.windowMs };
      this.windows.set(key, entry);
    }

    entry.count++;

    return {
      allowed: entry.count <= this.config.maxRequests,
      remaining: Math.max(0, this.config.maxRequests - entry.count),
      resetAt: entry.resetAt,
    };
  }

  /**
   * Stop the cleanup interval.
   */
  stop(): void {
    clearInterval(this.cleanupInterval);
  }
}

// ─────────────────────────────────────────────────────────────────
// Middleware Factory
// ─────────────────────────────────────────────────────────────────

/**
 * Create rate limiting middleware for API endpoints.
 * Default: 100 requests per minute per IP.
 */
export function createRateLimitMiddleware(config?: Partial<RateLimitConfig>): RequestHandler {
  const fullConfig: RateLimitConfig = {
    maxRequests: config?.maxRequests ?? 100,
    windowMs: config?.windowMs ?? 60_000,
    keyExtractor: config?.keyExtractor,
    message: config?.message ?? 'Too many requests. Please try again later.',
    skipPaths: config?.skipPaths ?? ['/api/health', '/api/health/live', '/api/health/ready'],
  };

  const limiter = new HttpRateLimiter(fullConfig);

  return (req: Request, res: Response, next: NextFunction): void => {
    // Skip configured paths
    if (fullConfig.skipPaths?.some((p) => req.path === p || req.path.startsWith(p))) {
      next();
      return;
    }

    // Skip non-API routes
    if (!req.path.startsWith('/api/')) {
      next();
      return;
    }

    const key = fullConfig.keyExtractor
      ? fullConfig.keyExtractor(req)
      : getClientIp(req);

    const result = limiter.check(key);

    // Set rate limit headers
    res.setHeader('X-RateLimit-Limit', fullConfig.maxRequests);
    res.setHeader('X-RateLimit-Remaining', result.remaining);
    res.setHeader('X-RateLimit-Reset', Math.ceil(result.resetAt / 1000));

    if (!result.allowed) {
      res.status(429).json({
        ok: false,
        error: fullConfig.message,
        code: 'GW-API-004',
        retryAfter: Math.ceil((result.resetAt - Date.now()) / 1000),
      });
      return;
    }

    next();
  };
}

/**
 * Create a stricter rate limiter for chat/turn endpoints.
 * Default: 30 requests per minute per IP.
 */
export function createChatRateLimitMiddleware(config?: Partial<RateLimitConfig>): RequestHandler {
  return createRateLimitMiddleware({
    maxRequests: config?.maxRequests ?? 30,
    windowMs: config?.windowMs ?? 60_000,
    message: config?.message ?? 'Chat rate limit exceeded. Please slow down.',
    skipPaths: [],
    ...config,
  });
}

// ─────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────

function getClientIp(req: Request): string {
  const forwarded = req.headers['x-forwarded-for'];
  if (typeof forwarded === 'string') {
    return forwarded.split(',')[0].trim();
  }
  return req.socket.remoteAddress || 'unknown';
}
