/**
 * AG3NT Plugin Registry
 *
 * Central registry for all plugin registrations.
 */

import type {
  PluginRegistry,
  ToolRegistration,
  HookRegistration,
  ChannelRegistration,
  HttpRouteRegistration,
  ServiceRegistration,
  GatewayMethodRegistration,
  HookEvent,
  HookHandler,
  HookContext,
} from './types.js';

/**
 * Create an empty plugin registry.
 */
export function createPluginRegistry(): PluginRegistry {
  return {
    plugins: [],
    tools: [],
    hooks: [],
    channels: [],
    httpRoutes: [],
    services: [],
    gatewayMethods: [],
    diagnostics: [],
  };
}

/**
 * Get all tools from registry.
 */
export function getRegisteredTools(registry: PluginRegistry): ToolRegistration[] {
  return registry.tools;
}

/**
 * Get tool by name.
 */
export function getToolByName(registry: PluginRegistry, name: string): ToolRegistration | undefined {
  return registry.tools.find((t) => t.tool.name === name);
}

/**
 * Get all hooks for an event.
 */
export function getHooksForEvent(registry: PluginRegistry, event: HookEvent): HookRegistration[] {
  return registry.hooks
    .filter((h) => h.event === event)
    .sort((a, b) => (b.options?.priority || 0) - (a.options?.priority || 0));
}

/**
 * Execute hooks for an event (fire-and-forget).
 */
export async function executeHooks<T>(
  registry: PluginRegistry,
  event: HookEvent,
  payload: T,
  context: Omit<HookContext, 'pluginId'>
): Promise<void> {
  const hooks = getHooksForEvent(registry, event);
  await Promise.all(
    hooks.map(async (hook) => {
      try {
        await hook.handler(payload, { ...context, pluginId: hook.pluginId });
      } catch (err) {
        console.error(`Hook error [${hook.pluginId}/${event}]:`, err);
      }
    })
  );
}

/**
 * Execute modifying hooks sequentially, merging results.
 */
export async function executeModifyingHooks<T, R>(
  registry: PluginRegistry,
  event: HookEvent,
  payload: T,
  context: Omit<HookContext, 'pluginId'>
): Promise<R | undefined> {
  const hooks = getHooksForEvent(registry, event);
  let result: R | undefined;

  for (const hook of hooks) {
    try {
      const hookResult = await (hook.handler as HookHandler<T, R>)(payload, {
        ...context,
        pluginId: hook.pluginId,
      });
      if (hookResult !== undefined) {
        result = result ? { ...result, ...hookResult } : hookResult;
      }
    } catch (err) {
      console.error(`Hook error [${hook.pluginId}/${event}]:`, err);
    }
  }

  return result;
}

/**
 * Get all registered channels.
 */
export function getRegisteredChannels(registry: PluginRegistry): ChannelRegistration[] {
  return registry.channels;
}

/**
 * Get channel by type.
 */
export function getChannelByType(
  registry: PluginRegistry,
  channelType: string
): ChannelRegistration | undefined {
  return registry.channels.find((c) => c.adapter.channelType === channelType);
}

/**
 * Get all HTTP routes.
 */
export function getHttpRoutes(registry: PluginRegistry): HttpRouteRegistration[] {
  return registry.httpRoutes;
}

/**
 * Get gateway method handler.
 */
export function getGatewayMethod(
  registry: PluginRegistry,
  method: string
): GatewayMethodRegistration | undefined {
  return registry.gatewayMethods.find((m) => m.method === method);
}

/**
 * Start all registered services.
 */
export async function startServices(
  registry: PluginRegistry,
  context: import('./types.js').ServiceContext
): Promise<void> {
  for (const serviceReg of registry.services) {
    if (!serviceReg.running) {
      try {
        await serviceReg.service.start(context);
        serviceReg.running = true;
        console.log(`Started service: ${serviceReg.service.id}`);
      } catch (err) {
        console.error(`Failed to start service ${serviceReg.service.id}:`, err);
      }
    }
  }
}

/**
 * Stop all registered services.
 */
export async function stopServices(
  registry: PluginRegistry,
  context: import('./types.js').ServiceContext
): Promise<void> {
  // Stop in reverse order
  for (const serviceReg of [...registry.services].reverse()) {
    if (serviceReg.running && serviceReg.service.stop) {
      try {
        await serviceReg.service.stop(context);
        serviceReg.running = false;
        console.log(`Stopped service: ${serviceReg.service.id}`);
      } catch (err) {
        console.error(`Failed to stop service ${serviceReg.service.id}:`, err);
      }
    }
  }
}
