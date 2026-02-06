/**
 * Example AG3NT Plugin
 *
 * Demonstrates how to create a plugin with tools, hooks, and services.
 */

import type { PluginAPI } from '../../apps/gateway/src/plugins/types.js';

/**
 * Plugin registration function.
 */
export function register(api: PluginAPI): void {
  const { logger, pluginConfig } = api;

  const greeting = (pluginConfig.greeting as string) || 'Hello from example plugin!';

  logger.info(`Initializing with greeting: ${greeting}`);

  // Register a tool
  api.registerTool({
    name: 'example_tool',
    description: 'An example tool that echoes a message',
    parameters: {
      type: 'object',
      properties: {
        message: {
          type: 'string',
          description: 'Message to echo',
        },
      },
      required: ['message'],
    },
    handler: async (params, context) => {
      const message = params.message as string;
      context.logger.info(`Example tool called with: ${message}`);
      return {
        success: true,
        echo: message,
        greeting,
        timestamp: new Date().toISOString(),
      };
    },
  });

  // Register hooks
  api.on('gateway_start', (event, context) => {
    context.logger.info('Gateway started - example plugin ready');
  });

  api.on('message_received', (event, context) => {
    context.logger.debug('Message received event');
  });

  // Register an HTTP route
  api.registerHttpRoute({
    method: 'get',
    path: '/api/example-plugin/status',
    handler: (_req, res) => {
      res.json({
        plugin: 'example-plugin',
        status: 'ok',
        greeting,
      });
    },
  });

  // Register a gateway method
  api.registerGatewayMethod('example.ping', async (params) => {
    return {
      pong: true,
      message: params.message || 'pong',
      timestamp: Date.now(),
    };
  });

  logger.info('Example plugin registered successfully');
}

// Default export for compatibility
export default { register };
