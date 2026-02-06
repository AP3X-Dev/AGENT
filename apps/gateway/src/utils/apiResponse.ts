/**
 * Standardised API response helpers.
 *
 * Ensures consistent JSON envelope across all gateway endpoints.
 */

import type { Response } from "express";

/**
 * Send a success JSON response.
 */
export function sendSuccess(
  res: Response,
  data: Record<string, unknown> = {},
  status = 200,
): void {
  res.status(status).json({ ok: true, ...data });
}

/**
 * Send an error JSON response.
 */
export function sendError(
  res: Response,
  message: string,
  status = 500,
  code?: string,
): void {
  const body: Record<string, unknown> = { ok: false, error: message };
  if (code) body.code = code;
  res.status(status).json(body);
}
