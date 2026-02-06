/**
 * AG3NT Plugin Manifest Loader
 *
 * Loads and validates plugin manifests from ag3nt.plugin.json files.
 */

import { z } from 'zod';
import { existsSync, readFileSync } from 'fs';
import { resolve, dirname, join } from 'path';
import type { PluginManifest, ManifestLoadResult, PluginConfigUiHint } from './types.js';

// =============================================================================
// MANIFEST SCHEMA
// =============================================================================

/** UI hint schema for plugin config fields */
const PluginConfigUiHintSchema = z.object({
  label: z.string().optional(),
  help: z.string().optional(),
  advanced: z.boolean().optional(),
  sensitive: z.boolean().optional(),
  placeholder: z.string().optional(),
});

/** Plugin manifest schema */
const PluginManifestSchema = z.object({
  // Required fields
  id: z.string().min(1, 'Plugin ID is required'),

  // Optional metadata
  name: z.string().optional(),
  description: z.string().optional(),
  version: z.string().optional(),

  // Plugin kind
  kind: z.enum(['standard', 'memory', 'channel']).optional().default('standard'),

  // JSON schema for plugin configuration
  configSchema: z.record(z.unknown()).optional(),

  // Extension declarations
  channels: z.array(z.string()).optional(),
  tools: z.array(z.string()).optional(),
  skills: z.array(z.string()).optional(),
  hooks: z.array(z.string()).optional(),

  // UI hints for config
  uiHints: z.record(PluginConfigUiHintSchema).optional(),

  // Dependencies
  dependencies: z.array(z.string()).optional(),
  npmDependencies: z.record(z.string()).optional(),
});

// =============================================================================
// MANIFEST FILE NAMES
// =============================================================================

/** Supported manifest file names in priority order */
const MANIFEST_FILENAMES = [
  'ag3nt.plugin.json',
  'plugin.json',
  'moltbot.plugin.json', // Compatibility with moltbot plugins
];

// =============================================================================
// MANIFEST LOADING
// =============================================================================

/**
 * Find manifest file in a directory or its ancestors.
 *
 * @param startDir - Directory to start searching from
 * @param maxDepth - Maximum ancestor directories to search
 * @returns Path to manifest file or null if not found
 */
export function findManifestFile(startDir: string, maxDepth = 3): string | null {
  let currentDir = resolve(startDir);
  let depth = 0;

  while (depth <= maxDepth) {
    // Try each manifest filename
    for (const filename of MANIFEST_FILENAMES) {
      const manifestPath = join(currentDir, filename);
      if (existsSync(manifestPath)) {
        return manifestPath;
      }
    }

    // Move to parent directory
    const parentDir = dirname(currentDir);
    if (parentDir === currentDir) {
      // Reached root
      break;
    }
    currentDir = parentDir;
    depth++;
  }

  return null;
}

/**
 * Load and validate a plugin manifest from a file.
 *
 * @param manifestPath - Path to the manifest file
 * @returns ManifestLoadResult with success/error status
 */
export function loadManifestFile(manifestPath: string): ManifestLoadResult {
  try {
    // Read file
    const content = readFileSync(manifestPath, 'utf-8');

    // Parse JSON
    let parsed: unknown;
    try {
      parsed = JSON.parse(content);
    } catch (parseError) {
      return {
        success: false,
        error: `Invalid JSON in manifest: ${parseError instanceof Error ? parseError.message : String(parseError)}`,
        manifestPath,
      };
    }

    // Validate with Zod schema
    const result = PluginManifestSchema.safeParse(parsed);
    if (!result.success) {
      const errors = result.error.errors
        .map((e) => `${e.path.join('.')}: ${e.message}`)
        .join('; ');
      return {
        success: false,
        error: `Manifest validation failed: ${errors}`,
        manifestPath,
      };
    }

    // Normalize the manifest
    const manifest = normalizeManifest(result.data);

    return {
      success: true,
      manifest,
      manifestPath,
    };
  } catch (err) {
    return {
      success: false,
      error: `Failed to load manifest: ${err instanceof Error ? err.message : String(err)}`,
      manifestPath,
    };
  }
}

/**
 * Load manifest from a plugin directory.
 *
 * @param pluginDir - Plugin directory path
 * @returns ManifestLoadResult with success/error status
 */
export function loadManifestFromDir(pluginDir: string): ManifestLoadResult {
  const manifestPath = findManifestFile(pluginDir);

  if (!manifestPath) {
    return {
      success: false,
      error: `No manifest file found in ${pluginDir}`,
    };
  }

  return loadManifestFile(manifestPath);
}

/**
 * Normalize a parsed manifest.
 *
 * @param data - Parsed manifest data
 * @returns Normalized PluginManifest
 */
function normalizeManifest(data: z.infer<typeof PluginManifestSchema>): PluginManifest {
  return {
    id: data.id.trim(),
    name: data.name?.trim() || data.id,
    description: data.description?.trim(),
    version: data.version?.trim(),
    kind: data.kind,
    configSchema: data.configSchema,
    channels: data.channels?.map((c) => c.trim()).filter(Boolean),
    tools: data.tools?.map((t) => t.trim()).filter(Boolean),
    skills: data.skills?.map((s) => s.trim()).filter(Boolean),
    hooks: data.hooks?.map((h) => h.trim()).filter(Boolean),
    uiHints: data.uiHints as Record<string, PluginConfigUiHint> | undefined,
    dependencies: data.dependencies?.map((d) => d.trim()).filter(Boolean),
    npmDependencies: data.npmDependencies,
  };
}

/**
 * Validate plugin configuration against manifest schema.
 *
 * @param manifest - Plugin manifest
 * @param config - Configuration to validate
 * @returns Validation result with errors if any
 */
export function validatePluginConfig(
  manifest: PluginManifest,
  config: Record<string, unknown>
): { valid: boolean; errors?: string[] } {
  if (!manifest.configSchema) {
    // No schema = any config is valid
    return { valid: true };
  }

  // Use Zod to validate against the schema
  // The configSchema is a JSON Schema, we need to convert it to Zod
  // For simplicity, we'll do basic type checking here
  // In production, consider using a JSON Schema validator

  const errors: string[] = [];
  const schema = manifest.configSchema;

  // Check required fields
  if (schema.required && Array.isArray(schema.required)) {
    for (const field of schema.required) {
      if (!(field in config)) {
        errors.push(`Missing required field: ${field}`);
      }
    }
  }

  // Check property types
  if (schema.properties && typeof schema.properties === 'object') {
    for (const [key, propSchema] of Object.entries(schema.properties)) {
      if (key in config && propSchema && typeof propSchema === 'object') {
        const prop = propSchema as Record<string, unknown>;
        const value = config[key];

        // Type checking
        if (prop.type === 'string' && typeof value !== 'string') {
          errors.push(`Field ${key} should be a string`);
        } else if (prop.type === 'number' && typeof value !== 'number') {
          errors.push(`Field ${key} should be a number`);
        } else if (prop.type === 'boolean' && typeof value !== 'boolean') {
          errors.push(`Field ${key} should be a boolean`);
        } else if (prop.type === 'array' && !Array.isArray(value)) {
          errors.push(`Field ${key} should be an array`);
        } else if (prop.type === 'object' && (typeof value !== 'object' || value === null)) {
          errors.push(`Field ${key} should be an object`);
        }

        // Enum validation
        if (prop.enum && Array.isArray(prop.enum) && !prop.enum.includes(value)) {
          errors.push(`Field ${key} must be one of: ${prop.enum.join(', ')}`);
        }
      }
    }
  }

  return {
    valid: errors.length === 0,
    errors: errors.length > 0 ? errors : undefined,
  };
}

/**
 * Create a default manifest for a plugin without one.
 *
 * @param id - Plugin ID to use
 * @param source - Plugin source path
 * @returns Default PluginManifest
 */
export function createDefaultManifest(id: string, source: string): PluginManifest {
  return {
    id,
    name: id,
    description: `Plugin loaded from ${source}`,
    kind: 'standard',
  };
}

/**
 * Extract plugin ID from a file path.
 *
 * @param filePath - Path to plugin file
 * @returns Derived plugin ID
 */
export function derivePluginId(filePath: string): string {
  const resolved = resolve(filePath);
  const parts = resolved.split(/[/\\]/);

  // Try to find a meaningful name
  // Look for last non-index filename
  for (let i = parts.length - 1; i >= 0; i--) {
    const part = parts[i];
    // Skip common non-meaningful names
    if (
      part &&
      !part.startsWith('.') &&
      part !== 'index.ts' &&
      part !== 'index.js' &&
      part !== 'src' &&
      part !== 'dist'
    ) {
      // Remove extension
      return part.replace(/\.(ts|js|mts|mjs|cts|cjs)$/, '');
    }
  }

  // Fallback to hash of path
  return `plugin-${hashString(resolved).slice(0, 8)}`;
}

/**
 * Simple string hash function.
 */
function hashString(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  return Math.abs(hash).toString(16);
}
