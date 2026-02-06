/**
 * Shared path security utility for workspace/memory endpoints.
 *
 * Uses path.resolve() for Windows-safe path traversal prevention.
 */

import path from "node:path";

export interface PathValidationResult {
  ok: boolean;
  fullPath: string;
  error?: string;
  status?: number;
}

/**
 * Validate that a user-supplied path resolves within the given base directory.
 *
 * @param basePath - The trusted base directory (e.g. workspace root)
 * @param userPath - The untrusted user-supplied relative path
 * @returns Validation result with resolved full path or error
 */
export function validateWorkspacePath(
  basePath: string,
  userPath: string,
): PathValidationResult {
  if (!userPath) {
    return { ok: false, fullPath: "", error: "Missing path parameter", status: 400 };
  }

  // Block obvious traversal patterns and absolute paths
  if (path.isAbsolute(userPath)) {
    return { ok: false, fullPath: "", error: "Invalid path", status: 400 };
  }

  // Resolve to an absolute path — handles "..", ".", and mixed separators
  const resolved = path.resolve(basePath, userPath);

  // Ensure the resolved path is still inside the base directory.
  // Use path.resolve on basePath too so both are normalised.
  const normalBase = path.resolve(basePath);

  if (!resolved.startsWith(normalBase + path.sep) && resolved !== normalBase) {
    return { ok: false, fullPath: resolved, error: "Path outside allowed directory", status: 400 };
  }

  return { ok: true, fullPath: resolved };
}
