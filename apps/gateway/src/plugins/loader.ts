/**
 * AG3NT Plugin Loader
 *
 * Discovers and loads plugins from multiple sources:
 * 1. Bundled plugins (./plugins/)
 * 2. Global plugins (~/.ag3nt/plugins/)
 * 3. Workspace plugins (./.ag3nt/plugins/)
 * 4. Config-specified paths
 */

import { existsSync, readdirSync, statSync } from 'fs';
import { resolve, join, dirname, basename, extname } from 'path';
import { homedir } from 'os';
import type { Config } from '../config/schema.js';
import type {
  PluginManifest,
  PluginModule,
  PluginOrigin,
  PluginStatus,
  PluginRecord,
  PluginRegistry,
  PluginDiagnostic,
  PluginsConfig,
  PluginEntryConfig,
} from './types.js';
import {
  loadManifestFromDir,
  loadManifestFile,
  findManifestFile,
  derivePluginId,
  createDefaultManifest,
  validatePluginConfig,
} from './manifest.js';
import { createPluginAPI } from './api.js';
import { createPluginRegistry } from './registry.js';

// =============================================================================
// CONSTANTS
// =============================================================================

/** Supported plugin file extensions */
const PLUGIN_EXTENSIONS = ['.ts', '.tsx', '.mts', '.cts', '.js', '.mjs', '.cjs'];

/** Directories to skip when scanning */
const SKIP_DIRS = ['node_modules', '.git', 'dist', 'build', '__pycache__'];

/** Default bundled plugins that are enabled by default */
const DEFAULT_ENABLED_BUNDLED: Set<string> = new Set([
  // Add IDs of bundled plugins that should be enabled by default
]);

// =============================================================================
// PLUGIN CANDIDATE
// =============================================================================

/** Information about a discovered plugin candidate */
interface PluginCandidate {
  /** Derived or manifest plugin ID */
  id: string;
  /** Path to plugin entry file */
  source: string;
  /** Path to manifest file (if found) */
  manifestPath?: string;
  /** Loaded manifest (if found) */
  manifest?: PluginManifest;
  /** Plugin origin */
  origin: PluginOrigin;
}

// =============================================================================
// PLUGIN DISCOVERY
// =============================================================================

/**
 * Discover plugins from a directory.
 *
 * @param dir - Directory to scan
 * @param origin - Plugin origin for discovered plugins
 * @returns Array of plugin candidates
 */
function discoverPluginsInDir(dir: string, origin: PluginOrigin): PluginCandidate[] {
  const candidates: PluginCandidate[] = [];

  if (!existsSync(dir)) {
    return candidates;
  }

  const entries = readdirSync(dir, { withFileTypes: true });

  for (const entry of entries) {
    const fullPath = join(dir, entry.name);

    if (entry.isDirectory()) {
      // Skip common non-plugin directories
      if (SKIP_DIRS.includes(entry.name) || entry.name.startsWith('.')) {
        continue;
      }

      // Check if directory is a plugin (has manifest or index file)
      const manifestPath = findManifestFile(fullPath, 0);
      const indexFile = findIndexFile(fullPath);

      if (manifestPath || indexFile) {
        const manifest = manifestPath ? loadManifestFile(manifestPath) : null;
        const id = manifest?.manifest?.id || derivePluginId(fullPath);
        const source = indexFile || fullPath;

        candidates.push({
          id,
          source,
          manifestPath: manifestPath || undefined,
          manifest: manifest?.manifest,
          origin,
        });
      }
    } else if (entry.isFile()) {
      // Check if file is a plugin (has plugin extension)
      const ext = extname(entry.name);
      if (PLUGIN_EXTENSIONS.includes(ext) && !entry.name.startsWith('.')) {
        // Skip index files at root level (likely part of a package)
        if (entry.name.startsWith('index.')) {
          continue;
        }

        // Look for manifest in same directory or parent
        const manifestPath = findManifestFile(dir, 1);
        const manifest = manifestPath ? loadManifestFile(manifestPath) : null;
        const id = manifest?.manifest?.id || derivePluginId(fullPath);

        candidates.push({
          id,
          source: fullPath,
          manifestPath: manifestPath || undefined,
          manifest: manifest?.manifest,
          origin,
        });
      }
    }
  }

  return candidates;
}

/**
 * Find index file in a directory.
 *
 * @param dir - Directory to search
 * @returns Path to index file or null
 */
function findIndexFile(dir: string): string | null {
  for (const ext of PLUGIN_EXTENSIONS) {
    const indexPath = join(dir, `index${ext}`);
    if (existsSync(indexPath)) {
      return indexPath;
    }
  }
  return null;
}

/**
 * Get all plugin discovery directories.
 *
 * @param config - Gateway configuration
 * @param workspaceDir - Current workspace directory
 * @returns Array of [directory, origin] tuples
 */
function getPluginDirectories(
  config: Config,
  workspaceDir: string
): Array<[string, PluginOrigin]> {
  const dirs: Array<[string, PluginOrigin]> = [];

  // 1. Config-specified paths (highest priority, loaded last)
  const pluginsConfig = (config as unknown as { plugins?: PluginsConfig }).plugins;
  if (pluginsConfig?.loadPaths) {
    for (const loadPath of pluginsConfig.loadPaths) {
      const resolved = resolve(loadPath);
      if (existsSync(resolved)) {
        dirs.push([resolved, 'config']);
      }
    }
  }

  // 2. Workspace plugins (./.ag3nt/plugins/)
  const workspacePlugins = join(workspaceDir, '.ag3nt', 'plugins');
  if (existsSync(workspacePlugins)) {
    dirs.push([workspacePlugins, 'workspace']);
  }

  // 3. Global plugins (~/.ag3nt/plugins/)
  const globalPlugins = join(homedir(), '.ag3nt', 'plugins');
  if (existsSync(globalPlugins)) {
    dirs.push([globalPlugins, 'global']);
  }

  // 4. Bundled plugins (./plugins/) - lowest priority
  // Find repo root by looking for skills/ directory
  let bundledDir = join(workspaceDir, 'plugins');
  if (!existsSync(bundledDir)) {
    // Try from gateway src location
    const gatewayRoot = resolve(dirname(import.meta.url.replace('file:///', '')), '..', '..', '..');
    bundledDir = join(gatewayRoot, 'plugins');
  }
  if (existsSync(bundledDir)) {
    dirs.push([bundledDir, 'bundled']);
  }

  return dirs;
}

// =============================================================================
// PLUGIN LOADING
// =============================================================================

/**
 * Options for loading plugins.
 */
export interface PluginLoadOptions {
  /** Gateway configuration */
  config: Config;
  /** Workspace directory */
  workspaceDir?: string;
  /** Custom logger */
  logger?: Console;
  /** Skip disabled plugins */
  skipDisabled?: boolean;
}

/**
 * Load all plugins.
 *
 * @param options - Load options
 * @returns PluginRegistry with all loaded plugins
 */
export async function loadPlugins(options: PluginLoadOptions): Promise<PluginRegistry> {
  const { config, logger = console } = options;
  const workspaceDir = options.workspaceDir || process.cwd();
  const registry = createPluginRegistry();

  // Get plugins config
  const pluginsConfig = (config as unknown as { plugins?: PluginsConfig }).plugins;

  // Check if plugins are globally disabled
  if (pluginsConfig?.enabled === false) {
    registry.diagnostics.push({
      level: 'info',
      message: 'Plugins are disabled globally in config',
    });
    return registry;
  }

  // Discover all plugin candidates
  const candidates: PluginCandidate[] = [];
  const seenIds = new Set<string>();

  const directories = getPluginDirectories(config, workspaceDir);

  for (const [dir, origin] of directories) {
    const discovered = discoverPluginsInDir(dir, origin);
    for (const candidate of discovered) {
      // Skip duplicates (later sources override earlier)
      if (seenIds.has(candidate.id)) {
        const existing = candidates.find((c) => c.id === candidate.id);
        if (existing) {
          // Replace with newer discovery
          const index = candidates.indexOf(existing);
          candidates[index] = candidate;
          registry.diagnostics.push({
            level: 'info',
            message: `Plugin ${candidate.id} from ${origin} overrides ${existing.origin}`,
          });
        }
      } else {
        candidates.push(candidate);
        seenIds.add(candidate.id);
      }
    }
  }

  logger.info(`Discovered ${candidates.length} plugin candidate(s)`);

  // Load each plugin
  for (const candidate of candidates) {
    const pluginRecord = await loadPlugin(candidate, config, workspaceDir, registry, logger);
    registry.plugins.push(pluginRecord);
  }

  // Log summary
  const loaded = registry.plugins.filter((p) => p.status === 'loaded');
  const disabled = registry.plugins.filter((p) => p.status === 'disabled');
  const errored = registry.plugins.filter((p) => p.status === 'error');

  logger.info(
    `Plugins: ${loaded.length} loaded, ${disabled.length} disabled, ${errored.length} errors`
  );

  return registry;
}

/**
 * Load a single plugin.
 *
 * @param candidate - Plugin candidate
 * @param config - Gateway configuration
 * @param workspaceDir - Workspace directory
 * @param registry - Plugin registry to populate
 * @param logger - Logger
 * @returns PluginRecord with load status
 */
async function loadPlugin(
  candidate: PluginCandidate,
  config: Config,
  workspaceDir: string,
  registry: PluginRegistry,
  logger: Console
): Promise<PluginRecord> {
  const { id, source, manifest, origin } = candidate;

  // Create base record
  const record: PluginRecord = {
    id,
    name: manifest?.name || id,
    version: manifest?.version,
    description: manifest?.description,
    source,
    origin,
    enabled: false,
    status: 'disabled',
    toolNames: [],
    hookNames: [],
    channelIds: [],
    gatewayMethods: [],
    services: [],
    httpRouteCount: 0,
  };

  // Check enable state
  const enableState = resolveEnableState(id, origin, config);
  if (!enableState.enabled) {
    record.status = 'disabled';
    record.error = enableState.reason;
    logger.debug(`Plugin ${id} disabled: ${enableState.reason}`);
    return record;
  }

  // Get plugin-specific config
  const pluginsConfig = (config as unknown as { plugins?: PluginsConfig }).plugins;
  const pluginConfig = pluginsConfig?.entries?.[id]?.config || {};

  // Validate config against manifest schema
  if (manifest) {
    const validation = validatePluginConfig(manifest, pluginConfig);
    if (!validation.valid) {
      record.status = 'error';
      record.error = `Config validation failed: ${validation.errors?.join('; ')}`;
      registry.diagnostics.push({
        pluginId: id,
        level: 'error',
        message: record.error,
      });
      return record;
    }
  }

  // Load the plugin module
  try {
    const module = await loadPluginModule(source);

    // Find the register function
    const registerFn = extractRegisterFunction(module);
    if (!registerFn) {
      record.status = 'error';
      record.error = 'No register or activate function exported';
      registry.diagnostics.push({
        pluginId: id,
        level: 'error',
        message: record.error,
      });
      return record;
    }

    // Create plugin API
    const api = createPluginAPI({
      id,
      name: manifest?.name || id,
      version: manifest?.version,
      description: manifest?.description,
      source,
      origin,
      config,
      pluginConfig,
      workspaceDir,
      registry,
      logger,
    });

    // Call register function
    await registerFn(api);

    // Update record with registrations
    record.enabled = true;
    record.status = 'loaded';
    record.toolNames = registry.tools
      .filter((t) => t.pluginId === id)
      .map((t) => t.tool.name);
    record.hookNames = registry.hooks
      .filter((h) => h.pluginId === id)
      .map((h) => h.event);
    record.channelIds = registry.channels
      .filter((c) => c.pluginId === id)
      .map((c) => c.adapter.channelType);
    record.gatewayMethods = registry.gatewayMethods
      .filter((m) => m.pluginId === id)
      .map((m) => m.method);
    record.services = registry.services
      .filter((s) => s.pluginId === id)
      .map((s) => s.service.id);
    record.httpRouteCount = registry.httpRoutes.filter((r) => r.pluginId === id).length;

    logger.info(
      `Loaded plugin ${id}${record.toolNames.length ? ` (${record.toolNames.length} tools)` : ''}`
    );

    return record;
  } catch (err) {
    record.status = 'error';
    record.error = err instanceof Error ? err.message : String(err);
    registry.diagnostics.push({
      pluginId: id,
      level: 'error',
      message: `Failed to load plugin: ${record.error}`,
      details: err,
    });
    logger.error(`Failed to load plugin ${id}: ${record.error}`);
    return record;
  }
}

/**
 * Load a plugin module from file.
 *
 * @param source - Path to plugin source file
 * @returns Loaded module
 */
async function loadPluginModule(source: string): Promise<PluginModule> {
  // For TypeScript files, we need a transpiler
  // Try to use jiti if available, otherwise fall back to native import

  const ext = extname(source);
  const isTypeScript = ['.ts', '.tsx', '.mts', '.cts'].includes(ext);

  if (isTypeScript) {
    try {
      // Try jiti for TypeScript transpilation
      const { createJiti } = await import('jiti');
      const jiti = createJiti(import.meta.url, {
        interopDefault: true,
        moduleCache: false,
      });
      return jiti(source) as PluginModule;
    } catch {
      // If jiti not available, try tsx or ts-node
      try {
        // Convert to file URL for ESM import
        const fileUrl = `file:///${source.replace(/\\/g, '/')}`;
        return (await import(fileUrl)) as PluginModule;
      } catch (importErr) {
        throw new Error(
          `Cannot load TypeScript plugin. Install jiti: npm install jiti. Error: ${importErr}`
        );
      }
    }
  } else {
    // JavaScript files can be imported directly
    const fileUrl = `file:///${source.replace(/\\/g, '/')}`;
    return (await import(fileUrl)) as PluginModule;
  }
}

/**
 * Extract the register function from a plugin module.
 *
 * @param module - Loaded plugin module
 * @returns Register function or null
 */
function extractRegisterFunction(
  module: PluginModule
): ((api: import('./types.js').PluginAPI) => void | Promise<void>) | null {
  // Check for named register export
  if (typeof module.register === 'function') {
    return module.register;
  }

  // Check for named activate export (legacy)
  if (typeof module.activate === 'function') {
    return module.activate;
  }

  // Check for default export
  if (module.default) {
    if (typeof module.default === 'function') {
      return module.default;
    }
    if (typeof module.default === 'object') {
      if (typeof module.default.register === 'function') {
        return module.default.register;
      }
      if (typeof module.default.activate === 'function') {
        return module.default.activate;
      }
    }
  }

  return null;
}

/**
 * Resolve whether a plugin should be enabled.
 *
 * @param id - Plugin ID
 * @param origin - Plugin origin
 * @param config - Gateway configuration
 * @returns Enable state with reason
 */
function resolveEnableState(
  id: string,
  origin: PluginOrigin,
  config: Config
): { enabled: boolean; reason?: string } {
  const pluginsConfig = (config as unknown as { plugins?: PluginsConfig }).plugins;

  // Check global disable
  if (pluginsConfig?.enabled === false) {
    return { enabled: false, reason: 'plugins disabled globally' };
  }

  // Check denylist
  if (pluginsConfig?.deny?.includes(id)) {
    return { enabled: false, reason: 'blocked by denylist' };
  }

  // Check allowlist (if set, only allowed plugins load)
  if (pluginsConfig?.allow?.length && !pluginsConfig.allow.includes(id)) {
    return { enabled: false, reason: 'not in allowlist' };
  }

  // Check slot assignment (e.g., memory plugin)
  if (pluginsConfig?.slots) {
    for (const [slot, slotPluginId] of Object.entries(pluginsConfig.slots)) {
      if (slotPluginId === id) {
        return { enabled: true };
      }
    }
  }

  // Check per-plugin config
  const entry = pluginsConfig?.entries?.[id];
  if (entry?.enabled === true) {
    return { enabled: true };
  }
  if (entry?.enabled === false) {
    return { enabled: false, reason: 'disabled in config' };
  }

  // Bundled plugins: check default enabled list
  if (origin === 'bundled') {
    if (DEFAULT_ENABLED_BUNDLED.has(id)) {
      return { enabled: true };
    }
    return { enabled: false, reason: 'bundled (disabled by default)' };
  }

  // Global/workspace/config plugins enabled by default
  return { enabled: true };
}

/**
 * Reload plugins (useful for hot reload).
 *
 * @param options - Load options
 * @param existingRegistry - Existing registry to update
 * @returns Updated PluginRegistry
 */
export async function reloadPlugins(
  options: PluginLoadOptions,
  existingRegistry?: PluginRegistry
): Promise<PluginRegistry> {
  // Stop existing services
  if (existingRegistry) {
    for (const serviceReg of existingRegistry.services) {
      if (serviceReg.running && serviceReg.service.stop) {
        try {
          await serviceReg.service.stop({
            config: options.config,
            workspaceDir: options.workspaceDir || process.cwd(),
            stateDir: join(homedir(), '.ag3nt', 'plugin-state', serviceReg.pluginId),
            logger: console as unknown as import('./types.js').PluginLogger,
          });
        } catch (err) {
          console.error(`Failed to stop service ${serviceReg.service.id}:`, err);
        }
      }
    }
  }

  // Load fresh
  return loadPlugins(options);
}
