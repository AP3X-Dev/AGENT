export type SessionId = string;

export type ChannelName =
  | "cli"
  | "telegram"
  | "slack"
  | "discord"
  | "whatsapp"
  | "signal"
  | "http";

export interface InboundMessage {
  sessionId: SessionId;
  channel: ChannelName;
  from: string;
  text: string;
  timestampMs: number;
  metadata?: Record<string, unknown>;
}

export interface OutboundMessage {
  sessionId: SessionId;
  channel: ChannelName;
  to: string;
  text: string;
  metadata?: Record<string, unknown>;
}

export interface ToolCallEvent {
  sessionId: SessionId;
  toolName: string;
  input: unknown;
  output?: unknown;
  startedAtMs: number;
  finishedAtMs?: number;
  status: "started" | "succeeded" | "failed" | "requires_approval";
  error?: string;
}
