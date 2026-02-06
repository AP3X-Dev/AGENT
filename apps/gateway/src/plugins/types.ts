/**
 * AG3NT Plugin System - Type Definitions
 *
 * This module defines all TypeScript interfaces for the AG3NT plugin system,
 * including manifests, APIs, registrations, and lifecycle hooks.
 */

import type { Request, Response, Router } from 'express';
import type { Config } from '../config/schema.js';

// =============================================================================
// PLUGIN MANIFEST
// =============================================================================

/**
 * Plugin kind determines special handling.
 * - "standard": Regular plugin (default)
 * - "memory": Memory/storage plugin (only one can be active)
 * - "channel": Provides messaging channel
 */
export type PluginKind = 'standard' | 'memory' | 'channel';

/**
 * Plugin origin indicates where the plugin was discovered.
 */
export type PluginOrigin = 'bundled' | 'global' | 'workspace' | 'config';

/**
 * Plugin status after load attempt.
 */
export type PluginStatus = 'loaded' | 'disabled' | 'error';

/**
 * UI hints for plugin configuration fields.
 */
export interface PluginConfigUiHint {
  /** Field label in UI */
  label?: string;
  /** Help text for the field */
  help?: string;
  /** Mark as advanced setting (hidden by default) */
  advanced?: boolean;
  /** Mark as sensitive (password field) */
  sensitive?: boolean;
  /** Input placeholder text */
  placeholder?: string;
}

/**
 * Plugin manifest loaded from ag3nt.plugin.json.
 */
export interface PluginManifest {
  /** Unique plugin identifier (required) */
  id: string;
  /** Human-readable plugin name */
  name?: string;
  /** Plugin description */
  description?: string;
  /** Semantic version */
  version?: string;
  /** Plugin kind for special handling */
  kind?: PluginKind;
  /** JSON schema for plugin configuration */
  configSchema?: Record<string, unknown>;
  /** Channel IDs this plugin provides */
  channels?: string[];
  /** Tool names this plugin provides */
  tools?: string[];
  /** Skill IDs this plugin provides */
  skills?: string[];
  /** Hook names this plugin registers */
  hooks?: string[];
  /** UI hints for config fields */
  uiHints?: Record<string, PluginConfigUiHint>;
  /** Plugin dependencies (other plugin IDs) */
  dependencies?: string[];
  /** Node.js/npm dependencies */
  npmDependencies?: Record<string, string>;
}

/**
 * Result of loading a plugin manifest.
 */
export interface ManifestLoadResult {
  success: boolean;
  manifest?: PluginManifest;
  manifestPath?: string;
  error?: string;
}

// =============================================================================
// PLUGIN API - What plugins can access
// =============================================================================

/**
 * Logger interface for plugins.
 */
export interface PluginLogger {
  debug(message: string, ...args: unknown[]): void;
  info(message: string, ...args: unknown[]): void;
  warn(message: string, ...args: unknown[]): void;
  error(message: string, ...args: unknown[]): void;
  child(bindings: Record<string, unknown>): PluginLogger;
}

/**
 * Runtime utilities available to plugins.
 */
export interface PluginRuntime {
  /** Gateway configuration */
  config: Config;
  /** Workspace directory path */
  workspaceDir: string;
  /** Plugin state directory */
  stateDir: string;
  /** Send message to a channel */
  sendMessage(channel: string, target: string, content: string): Promise<void>;
  /** Get session by ID */
  getSession(sessionId: string): Promise<SessionInfo | null>;
  /** List active sessions */
  listSessions(): Promise<SessionInfo[]>;
  /** Emit event to gateway */
  emitEvent(event: string, payload: unknown): void;
  /** Get registered channels */
  getChannels(): string[];
  /** Check if channel is connected */
  isChannelConnected(channel: string): boolean;
}

/**
 * Session information exposed to plugins.
 */
export interface SessionInfo {
  id: string;
  channel?: string;
  userId?: string;
  createdAt: number;
  lastActivity: number;
  metadata?: Record<string, unknown>;
}

/**
 * Tool definition for plugin-registered tools.
 */
export interface PluginTool {
  /** Tool name (used in tool calls) */
  name: string;
  /** Tool description for LLM */
  description: string;
  /** JSON schema for tool parameters */
  parameters?: Record<string, unknown>;
  /** Tool handler function */
  handler: (params: Record<string, unknown>, context: ToolContext) => Promise<unknown>;
}

/**
 * Context passed to tool handlers.
 */
export interface ToolContext {
  sessionId?: string;
  channel?: string;
  userId?: string;
  workspaceDir: string;
  logger: PluginLogger;
}

/**
 * Tool registration options.
 */
export interface ToolRegistrationOptions {
  /** Override tool name */
  name?: string;
  /** Multiple names for same tool */
  names?: string[];
  /** Requires explicit allowlist to enable */
  optional?: boolean;
}

/**
 * Hook handler function type.
 */
export type HookHandler<T = unknown, R = void> = (
  event: T,
  context: HookContext
) => R | Promise<R>;

/**
 * Context passed to hook handlers.
 */
export interface HookContext {
  pluginId: string;
  logger: PluginLogger;
  config: Config;
}

/**
 * Hook registration options.
 */
export interface HookRegistrationOptions {
  /** Hook priority (higher runs first) */
  priority?: number;
  /** Hook name for logging */
  name?: string;
  /** Hook description */
  description?: string;
}

/**
 * Available hook events.
 */
export type HookEvent =
  | 'gateway_start'
  | 'gateway_stop'
  | 'session_start'
  | 'session_end'
  | 'message_received'
  | 'message_sending'
  | 'message_sent'
  | 'before_agent_turn'
  | 'after_agent_turn'
  | 'before_tool_call'
  | 'after_tool_call'
  | 'channel_connected'
  | 'channel_disconnected';

/**
 * HTTP route registration parameters.
 */
export interface HttpRouteParams {
  /** HTTP method */
  method: 'get' | 'post' | 'put' | 'patch' | 'delete';
  /** Route path (e.g., '/api/my-endpoint') */
  path: string;
  /** Route handler */
  handler: (req: Request, res: Response) => void | Promise<void>;
  /** Require authentication */
  requireAuth?: boolean;
}

/**
 * Channel adapter interface for plugin-provided channels.
 */
export interface PluginChannelAdapter {
  /** Channel type identifier */
  readonly channelType: string;
  /** Channel display name */
  readonly displayName: string;
  /** Initialize and start the channel */
  start(): Promise<void>;
  /** Stop the channel */
  stop(): Promise<void>;
  /** Send a message */
  send(target: string, content: string, options?: SendOptions): Promise<void>;
  /** Register message handler */
  onMessage(handler: MessageHandler): void;
  /** Get channel status */
  getStatus(): ChannelStatus;
}

/**
 * Options for sending messages.
 */
export interface SendOptions {
  /** Reply to message ID */
  replyTo?: string;
  /** Thread ID for threaded channels */
  threadId?: string;
  /** Media attachments */
  media?: MediaAttachment[];
}

/**
 * Media attachment for messages.
 */
export interface MediaAttachment {
  type: 'image' | 'video' | 'audio' | 'file';
  url?: string;
  data?: Buffer;
  filename?: string;
  mimeType?: string;
}

/**
 * Inbound message from channel.
 */
export interface InboundMessage {
  id: string;
  channel: string;
  senderId: string;
  senderName?: string;
  content: string;
  timestamp: number;
  threadId?: string;
  replyToId?: string;
  media?: MediaAttachment[];
  raw?: unknown;
}

/**
 * Message handler function type.
 */
export type MessageHandler = (message: InboundMessage) => void | Promise<void>;

/**
 * Channel status information.
 */
export interface ChannelStatus {
  connected: boolean;
  authenticated: boolean;
  error?: string;
  lastActivity?: number;
}

/**
 * Service definition for long-running plugin services.
 */
export interface PluginService {
  /** Service identifier */
  id: string;
  /** Service display name */
  name?: string;
  /** Start the service */
  start(context: ServiceContext): Promise<void>;
  /** Stop the service */
  stop?(context: ServiceContext): Promise<void>;
}

/**
 * Context passed to services.
 */
export interface ServiceContext {
  config: Config;
  workspaceDir: string;
  stateDir: string;
  logger: PluginLogger;
}

/**
 * Gateway method handler for RPC-style calls.
 */
export type GatewayMethodHandler = (
  params: Record<string, unknown>,
  context: GatewayMethodContext
) => unknown | Promise<unknown>;

/**
 * Context for gateway method handlers.
 */
export interface GatewayMethodContext {
  sessionId?: string;
  logger: PluginLogger;
}

/**
 * Main Plugin API provided to plugins during registration.
 */
export interface PluginAPI {
  // Identity
  /** Plugin ID */
  readonly id: string;
  /** Plugin name */
  readonly name: string;
  /** Plugin version */
  readonly version?: string;
  /** Plugin description */
  readonly description?: string;
  /** Plugin source path */
  readonly source: string;
  /** Plugin origin */
  readonly origin: PluginOrigin;

  // Configuration
  /** Full gateway configuration */
  readonly config: Config;
  /** Plugin-specific configuration */
  readonly pluginConfig: Record<string, unknown>;

  // Runtime
  /** Runtime utilities */
  readonly runtime: PluginRuntime;
  /** Plugin logger */
  readonly logger: PluginLogger;

  // Registration methods
  /** Register a tool */
  registerTool(tool: PluginTool, options?: ToolRegistrationOptions): void;
  /** Register a hook handler */
  registerHook<T = unknown, R = void>(
    event: HookEvent,
    handler: HookHandler<T, R>,
    options?: HookRegistrationOptions
  ): void;
  /** Shorthand for registerHook */
  on<T = unknown, R = void>(
    event: HookEvent,
    handler: HookHandler<T, R>,
    options?: HookRegistrationOptions
  ): void;
  /** Register an HTTP route */
  registerHttpRoute(params: HttpRouteParams): void;
  /** Register an Express router */
  registerRouter(prefix: string, router: Router): void;
  /** Register a channel adapter */
  registerChannel(adapter: PluginChannelAdapter): void;
  /** Register a gateway RPC method */
  registerGatewayMethod(method: string, handler: GatewayMethodHandler): void;
  /** Register a long-running service */
  registerService(service: PluginService): void;

  // Utilities
  /** Resolve a path relative to plugin directory */
  resolvePath(input: string): string;
  /** Get plugin state directory */
  getStateDir(): string;
}

// =============================================================================
// PLUGIN MODULE
// =============================================================================

/**
 * Plugin module export - the register function.
 */
export type PluginRegisterFunction = (api: PluginAPI) => void | Promise<void>;

/**
 * Plugin module with register function.
 */
export interface PluginModule {
  /** Plugin registration function */
  register?: PluginRegisterFunction;
  /** Legacy activate function */
  activate?: PluginRegisterFunction;
  /** Default export can be function */
  default?: PluginRegisterFunction | PluginModule;
}

// =============================================================================
// PLUGIN REGISTRY
// =============================================================================

/**
 * Record of a loaded plugin.
 */
export interface PluginRecord {
  /** Plugin ID */
  id: string;
  /** Plugin name */
  name: string;
  /** Plugin version */
  version?: string;
  /** Plugin description */
  description?: string;
  /** Source file path */
  source: string;
  /** Plugin origin */
  origin: PluginOrigin;
  /** Whether plugin is enabled */
  enabled: boolean;
  /** Load status */
  status: PluginStatus;
  /** Error message if failed */
  error?: string;
  /** Registered tool names */
  toolNames: string[];
  /** Registered hook names */
  hookNames: string[];
  /** Registered channel IDs */
  channelIds: string[];
  /** Registered gateway methods */
  gatewayMethods: string[];
  /** Registered services */
  services: string[];
  /** Number of HTTP routes */
  httpRouteCount: number;
}

/**
 * Tool registration record.
 */
export interface ToolRegistration {
  pluginId: string;
  tool: PluginTool;
  options?: ToolRegistrationOptions;
}

/**
 * Hook registration record.
 */
export interface HookRegistration {
  pluginId: string;
  event: HookEvent;
  handler: HookHandler;
  options?: HookRegistrationOptions;
}

/**
 * Channel registration record.
 */
export interface ChannelRegistration {
  pluginId: string;
  adapter: PluginChannelAdapter;
}

/**
 * HTTP route registration record.
 */
export interface HttpRouteRegistration {
  pluginId: string;
  params: HttpRouteParams;
}

/**
 * Service registration record.
 */
export interface ServiceRegistration {
  pluginId: string;
  service: PluginService;
  running: boolean;
}

/**
 * Gateway method registration record.
 */
export interface GatewayMethodRegistration {
  pluginId: string;
  method: string;
  handler: GatewayMethodHandler;
}

/**
 * Complete plugin registry containing all registrations.
 */
export interface PluginRegistry {
  /** All plugin records */
  plugins: PluginRecord[];
  /** Registered tools */
  tools: ToolRegistration[];
  /** Registered hooks */
  hooks: HookRegistration[];
  /** Registered channels */
  channels: ChannelRegistration[];
  /** Registered HTTP routes */
  httpRoutes: HttpRouteRegistration[];
  /** Registered services */
  services: ServiceRegistration[];
  /** Registered gateway methods */
  gatewayMethods: GatewayMethodRegistration[];
  /** Load diagnostics/errors */
  diagnostics: PluginDiagnostic[];
}

/**
 * Diagnostic information from plugin loading.
 */
export interface PluginDiagnostic {
  pluginId?: string;
  level: 'info' | 'warn' | 'error';
  message: string;
  details?: unknown;
}

// =============================================================================
// PLUGIN CONFIGURATION
// =============================================================================

/**
 * Plugin configuration in gateway config.
 */
export interface PluginsConfig {
  /** Enable plugin system */
  enabled?: boolean;
  /** Allowlist of plugin IDs (if set, only these load) */
  allow?: string[];
  /** Denylist of plugin IDs (blocked from loading) */
  deny?: string[];
  /** Additional load paths */
  loadPaths?: string[];
  /** Plugin slots (e.g., memory: "plugin-id") */
  slots?: Record<string, string>;
  /** Per-plugin configuration */
  entries?: Record<string, PluginEntryConfig>;
}

/**
 * Per-plugin configuration entry.
 */
export interface PluginEntryConfig {
  /** Enable/disable this plugin */
  enabled?: boolean;
  /** Plugin-specific configuration */
  config?: Record<string, unknown>;
}

// =============================================================================
// HOOK EVENT PAYLOADS
// =============================================================================

/** Gateway start event payload */
export interface GatewayStartEvent {
  config: Config;
  port: number;
}

/** Gateway stop event payload */
export interface GatewayStopEvent {
  reason?: string;
}

/** Session start event payload */
export interface SessionStartEvent {
  sessionId: string;
  channel?: string;
  userId?: string;
}

/** Session end event payload */
export interface SessionEndEvent {
  sessionId: string;
  reason?: string;
}

/** Message received event payload */
export interface MessageReceivedEvent {
  message: InboundMessage;
  sessionId?: string;
}

/** Message sending event payload (can modify) */
export interface MessageSendingEvent {
  content: string;
  channel: string;
  target: string;
  sessionId?: string;
}

/** Message sending result (returned from hook) */
export interface MessageSendingResult {
  content?: string;
  cancel?: boolean;
}

/** Message sent event payload */
export interface MessageSentEvent {
  content: string;
  channel: string;
  target: string;
  messageId?: string;
}

/** Before agent turn event payload */
export interface BeforeAgentTurnEvent {
  sessionId: string;
  userMessage: string;
}

/** Before agent turn result (returned from hook) */
export interface BeforeAgentTurnResult {
  systemPrompt?: string;
  prependContext?: string;
}

/** After agent turn event payload */
export interface AfterAgentTurnEvent {
  sessionId: string;
  userMessage: string;
  agentResponse: string;
  toolCalls?: unknown[];
}

/** Before tool call event payload */
export interface BeforeToolCallEvent {
  sessionId: string;
  toolName: string;
  params: Record<string, unknown>;
}

/** Before tool call result (returned from hook) */
export interface BeforeToolCallResult {
  params?: Record<string, unknown>;
  block?: boolean;
  blockReason?: string;
}

/** After tool call event payload */
export interface AfterToolCallEvent {
  sessionId: string;
  toolName: string;
  params: Record<string, unknown>;
  result: unknown;
  error?: string;
}

/** Channel connected event payload */
export interface ChannelConnectedEvent {
  channelType: string;
  channelId?: string;
}

/** Channel disconnected event payload */
export interface ChannelDisconnectedEvent {
  channelType: string;
  channelId?: string;
  reason?: string;
}
