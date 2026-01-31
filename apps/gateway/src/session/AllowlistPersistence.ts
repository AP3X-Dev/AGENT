/**
 * Allowlist Persistence for AG3NT Gateway.
 *
 * Persists the DM pairing allowlist to disk.
 */

import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";

export interface AllowlistStore {
  allowlist: string[];
  lastUpdated: string;
}

/**
 * Expand ~ to home directory.
 */
function expandPath(filePath: string): string {
  if (filePath.startsWith("~")) {
    return path.join(os.homedir(), filePath.slice(1));
  }
  return filePath;
}

/**
 * Load allowlist from disk.
 */
export async function loadAllowlist(filePath: string): Promise<string[]> {
  const expandedPath = expandPath(filePath);

  try {
    const content = await fs.readFile(expandedPath, "utf-8");
    const store: AllowlistStore = JSON.parse(content);
    return store.allowlist || [];
  } catch (error) {
    // File doesn't exist or is invalid - return empty allowlist
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return [];
    }
    console.warn(
      `[AllowlistPersistence] Failed to load allowlist from ${filePath}:`,
      error
    );
    return [];
  }
}

/**
 * Save allowlist to disk.
 */
export async function saveAllowlist(
  filePath: string,
  allowlist: string[]
): Promise<void> {
  const expandedPath = expandPath(filePath);

  // Ensure directory exists
  const dir = path.dirname(expandedPath);
  await fs.mkdir(dir, { recursive: true });

  const store: AllowlistStore = {
    allowlist,
    lastUpdated: new Date().toISOString(),
  };

  await fs.writeFile(expandedPath, JSON.stringify(store, null, 2), "utf-8");
}

/**
 * Add an entry to the allowlist and persist.
 */
export async function addToAllowlist(
  filePath: string,
  entry: string
): Promise<string[]> {
  const allowlist = await loadAllowlist(filePath);
  if (!allowlist.includes(entry)) {
    allowlist.push(entry);
    await saveAllowlist(filePath, allowlist);
  }
  return allowlist;
}

/**
 * Remove an entry from the allowlist and persist.
 */
export async function removeFromAllowlist(
  filePath: string,
  entry: string
): Promise<string[]> {
  let allowlist = await loadAllowlist(filePath);
  allowlist = allowlist.filter((e) => e !== entry);
  await saveAllowlist(filePath, allowlist);
  return allowlist;
}

