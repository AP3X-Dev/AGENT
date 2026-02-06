import { z } from "zod";

/**
 * DM Security Policy Schema.
 * - "open": All contacts can message the agent (less secure)
 * - "pairing": Unknown contacts receive a pairing code that must be approved
 */
const DMPolicySchema = z.enum(["open", "pairing"]).default("pairing");

/**
 * Node capability types.
 */
const NodeCapabilitySchema = z.enum([
  "file_management",
  "application_control",
  "system_info",
  "code_execution",
  "camera",
  "microphone",
  "audio_output",
  "notifications",
  "home_automation",
  "clipboard",
  "screen_capture",
]);

/**
 * Node configuration for multi-node architecture.
 */
const NodeConfigSchema = z.object({
  /** Node name */
  name: z.string(),
  /** Node type: primary (this device) or companion (remote) */
  type: z.enum(["primary", "companion"]).default("companion"),
  /** Capabilities this node provides */
  capabilities: z.array(NodeCapabilitySchema).default([]),
});

/**
 * Telegram Channel Configuration.
 */
const TelegramConfigSchema = z.object({
  enabled: z.boolean().default(false),
  botToken: z.string().optional(),
  /** Polling interval in milliseconds (default: 1000) */
  pollingInterval: z.number().int().default(1000),
  /** Use webhooks instead of polling */
  useWebhook: z.boolean().default(false),
  webhookUrl: z.string().optional(),
  /** DM policy for this channel */
  dmPolicy: DMPolicySchema,
});

/**
 * Discord Channel Configuration.
 */
const DiscordConfigSchema = z.object({
  enabled: z.boolean().default(false),
  botToken: z.string().optional(),
  clientId: z.string().optional(),
  /** Whether to respond in guild (server) channels */
  allowGuilds: z.boolean().default(true),
  /** Whether to respond in DMs */
  allowDMs: z.boolean().default(true),
  /** DM policy for this channel */
  dmPolicy: DMPolicySchema,
});

/**
 * Slack Channel Configuration.
 */
const SlackConfigSchema = z.object({
  enabled: z.boolean().default(false),
  botToken: z.string().optional(),
  appToken: z.string().optional(),
  signingSecret: z.string().optional(),
  /** DM policy for this channel */
  dmPolicy: DMPolicySchema,
});

/**
 * CLI Channel Configuration (built-in).
 */
const CLIConfigSchema = z.object({
  enabled: z.boolean().default(true),
});

export const ConfigSchema = z.object({
  gateway: z.object({
    host: z.string().default("127.0.0.1"),
    port: z.number().int().default(18789),
    wsPath: z.string().default("/ws"),
    httpPath: z.string().default("/api"),
  }),
  models: z.object({
    provider: z.string().default("openrouter"),
    model: z.string().default("moonshotai/kimi-k2-thinking"),
  }),
  security: z.object({
    /**
     * Tools that ALWAYS require approval, even in auto-approve mode.
     * Example: ["delete_file", "shell"]
     */
    alwaysRequireApproval: z.array(z.string()).default([]),
    /**
     * Tools that are exempt from approval (skip approval for these).
     * Only used when autoApprove is false.
     * Example: ["write_file"] - allow writes without approval
     */
    noApprovalRequired: z.array(z.string()).default([]),
    /**
     * Enable auto-approve mode - skip approval for all risky tools
     * except those in alwaysRequireApproval.
     * Environment variable AG3NT_AUTO_APPROVE=true overrides this.
     * WARNING: Use with caution!
     */
    autoApprove: z.boolean().default(false),
    /**
     * Timeout in seconds for approval requests before auto-rejecting.
     * 0 means no timeout (wait forever).
     */
    approvalTimeoutSeconds: z.number().int().default(0),
    /** Legacy: Tools that require approval (use alwaysRequireApproval instead) */
    requireApproval: z.array(z.string()).default([]),
    /** Default DM policy for channels that don't specify their own */
    defaultDMPolicy: DMPolicySchema,
    /** Pre-approved session patterns (e.g., 'telegram:*:12345') */
    allowlist: z.array(z.string()).default([]),
    /** YOLO mode: full autonomous operation with no approval gates */
    yoloMode: z.boolean().default(false),
  }),
  channels: z.object({
    /** List of enabled channel types */
    enabled: z.array(z.string()).default(["cli"]),
    /** CLI channel configuration */
    cli: CLIConfigSchema.default({}),
    /** Telegram channel configuration */
    telegram: TelegramConfigSchema.default({}),
    /** Discord channel configuration */
    discord: DiscordConfigSchema.default({}),
    /** Slack channel configuration */
    slack: SlackConfigSchema.default({}),
  }),
  skills: z.object({
    bundledPath: z.string().default("./skills"),
    globalPath: z.string().default("~/.ag3nt/skills"),
  }),
  storage: z.object({
    root: z.string().default("~/.ag3nt/data"),
    dbPath: z.string().default("~/.ag3nt/data/db/ag3nt.sqlite"),
    /** Path to store allowlist for DM pairing */
    allowlistPath: z.string().default("~/.ag3nt/allowlist.json"),
  }),
  scheduler: z.object({
    /** Heartbeat interval in minutes (0 = disabled) */
    heartbeatMinutes: z.number().int().default(0),
    /** Cron job definitions */
    cron: z
      .array(
        z.object({
          /** Cron expression or relative time (e.g., "0 9 * * *" or "in 10 minutes") */
          schedule: z.string(),
          /** Message to send to agent when job fires */
          message: z.string(),
          /** Session mode: "isolated" (fresh) or "main" (carries context) */
          sessionMode: z.enum(["isolated", "main"]).default("isolated"),
          /** Target channel to send response to */
          channelTarget: z.string().optional(),
          /** If true, job is deleted after first run */
          oneShot: z.boolean().default(false),
          /** Human-readable name for the job */
          name: z.string().optional(),
        })
      )
      .default([]),
  }),
  routing: z.object({
    strategy: z.enum(['auto', 'explicit', 'round-robin']).default('auto'),
    defaultAgent: z.string().default(''),
    queueEnabled: z.boolean().default(true),
    queueIntervalMs: z.number().default(100),
    maxQueueSize: z.number().default(1000),
  }).optional(),
  quotas: z.object({
    defaultMaxTurnsPerHour: z.number().default(60),
    defaultMaxTokensPerTurn: z.number().default(16000),
    defaultMaxConcurrent: z.number().default(3),
  }).optional(),
  nodes: z.object({
    /**
     * Additional companion nodes to expect connections from.
     * The local node is always registered automatically.
     */
    companions: z.array(NodeConfigSchema).default([]),
    /**
     * Override capabilities for the local node.
     * If not specified, capabilities are auto-detected.
     */
    localCapabilities: z.array(NodeCapabilitySchema).optional(),
  }),
});

export type Config = z.infer<typeof ConfigSchema>;
export type TelegramConfig = z.infer<typeof TelegramConfigSchema>;
export type DiscordConfig = z.infer<typeof DiscordConfigSchema>;
export type SlackConfig = z.infer<typeof SlackConfigSchema>;
export type DMPolicy = z.infer<typeof DMPolicySchema>;
export type NodeCapability = z.infer<typeof NodeCapabilitySchema>;
export type NodeConfig = z.infer<typeof NodeConfigSchema>;
