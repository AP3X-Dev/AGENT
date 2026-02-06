/**
 * AG3NT Plugin API Implementation
 *
 * Creates the API object that plugins receive during registration.
 */

import { join } from 'path';
import { mkdirSync, existsSync } from 'fs';
import { homedir } from 'os';
import type { Router } from 'express';
import type { Config } from '../config/schema.js';
import type {
  PluginAPI,
  PluginOrigin,
  PluginRegistry,
  PluginLogger,
  PluginRuntime,
  PluginTool,
  ToolRegistrationOptions,
  HookEvent,
  HookHandler,
  HookRegistrationOptions,
  HttpRouteParams,
  PluginChannelAdapter,
  GatewayMethodHandler,
  PluginService,
  SessionInfo,
} from './types.js';

/**
 * Options for creating a plugin API.
 */
export interface CreatePluginAPIOptions {
  id: string;
  name: string;
  version?: string;
  description?: string;
  source: string;
  origin: PluginOrigin;
  config: Config;
  pluginConfig: Record<string, unknown>;
  workspaceDir: string;
  registry: PluginRegistry;
  logger: Console;
}

/**
 * Create a plugin API instance.
 */
export function createPluginAPI(options: CreatePluginAPIOptions): PluginAPI {
  const {
    id,
    name,
    version,
    description,
    source,
    origin,
    config,
    pluginConfig,
    workspaceDir,
    registry,
    logger: baseLogger,
  } = options;

  // Create plugin-specific logger
  const logger: PluginLogger = {
    debug: (msg, ...args) => baseLogger.debug(`[${id}]`, msg, ...args),
    info: (msg, ...args) => baseLogger.info(`[${id}]`, msg, ...args),
    warn: (msg, ...args) => baseLogger.warn(`[${id}]`, msg, ...args),
    error: (msg, ...args) => baseLogger.error(`[${id}]`, msg, ...args),
    child: (bindings) => {
      const prefix = Object.entries(bindings)
        .map(([k, v]) => `${k}=${v}`)
        .join(' ');
      return {
        debug: (msg, ...args) => baseLogger.debug(`[${id}] ${prefix}`, msg, ...args),
        info: (msg, ...args) => baseLogger.info(`[${id}] ${prefix}`, msg, ...args),
        warn: (msg, ...args) => baseLogger.warn(`[${id}] ${prefix}`, msg, ...args),
        error: (msg, ...args) => baseLogger.error(`[${id}] ${prefix}`, msg, ...args),
        child: (b) => logger.child({ ...bindings, ...b }),
      };
    },
  };

  // Create state directory
  const stateDir = join(homedir(), '.ag3nt', 'plugin-state', id);
  if (!existsSync(stateDir)) {
    mkdirSync(stateDir, { recursive: true });
  }

  // Create runtime utilities
  const runtime: PluginRuntime = {
    config,
    workspaceDir,
    stateDir,
    sendMessage: async (channel, target, content) => {
      // Will be wired up when integrated with gateway
      logger.warn('sendMessage not yet connected to gateway');
    },
    getSession: async (sessionId) => {
      // Will be wired up when integrated with gateway
      return null;
    },
    listSessions: async () => {
      // Will be wired up when integrated with gateway
      return [];
    },
    emitEvent: (event, payload) => {
      // Will be wired up when integrated with gateway
      logger.debug(`Event: ${event}`, payload);
    },
    getChannels: () => {
      return registry.channels.map((c) => c.adapter.channelType);
    },
    isChannelConnected: (channel) => {
      const ch = registry.channels.find((c) => c.adapter.channelType === channel);
      return ch?.adapter.getStatus().connected || false;
    },
  };

  // Build the API object
  const api: PluginAPI = {
    // Identity
    id,
    name,
    version,
    description,
    source,
    origin,

    // Configuration
    config,
    pluginConfig,

    // Runtime
    runtime,
    logger,

    // Registration methods
    registerTool(tool: PluginTool, opts?: ToolRegistrationOptions) {
      registry.tools.push({ pluginId: id, tool, options: opts });
      logger.debug(`Registered tool: ${tool.name}`);
    },

    registerHook<T, R>(event: HookEvent, handler: HookHandler<T, R>, opts?: HookRegistrationOptions) {
      registry.hooks.push({
        pluginId: id,
        event,
        handler: handler as HookHandler,
        options: opts,
      });
      logger.debug(`Registered hook: ${event}`);
    },

    on<T, R>(event: HookEvent, handler: HookHandler<T, R>, opts?: HookRegistrationOptions) {
      api.registerHook(event, handler, opts);
    },

    registerHttpRoute(params: HttpRouteParams) {
      registry.httpRoutes.push({ pluginId: id, params });
      logger.debug(`Registered HTTP route: ${params.method.toUpperCase()} ${params.path}`);
    },

    registerRouter(prefix: string, router: Router) {
      // Store router for later mounting
      (registry as any).routers = (registry as any).routers || [];
      (registry as any).routers.push({ pluginId: id, prefix, router });
      logger.debug(`Registered router at: ${prefix}`);
    },

    registerChannel(adapter: PluginChannelAdapter) {
      registry.channels.push({ pluginId: id, adapter });
      logger.debug(`Registered channel: ${adapter.channelType}`);
    },

    registerGatewayMethod(method: string, handler: GatewayMethodHandler) {
      registry.gatewayMethods.push({ pluginId: id, method, handler });
      logger.debug(`Registered gateway method: ${method}`);
    },

    registerService(service: PluginService) {
      registry.services.push({ pluginId: id, service, running: false });
      logger.debug(`Registered service: ${service.id}`);
    },

    // Utilities
    resolvePath(input: string) {
      if (input.startsWith('/') || input.startsWith('~')) {
        return input.replace('~', homedir());
      }
      return join(source, '..', input);
    },

    getStateDir() {
      return stateDir;
    },
  };

  return api;
}
