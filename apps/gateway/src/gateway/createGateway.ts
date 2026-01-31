/**
 * Gateway factory for AG3NT.
 *
 * Creates the central Gateway service that handles:
 * - HTTP API for CLI and other clients
 * - WebSocket for real-time streaming
 * - Channel adapters for multi-platform messaging
 * - Session management and DM pairing security
 * - Scheduled tasks (heartbeat and cron jobs)
 * - Node registry for multi-device architecture
 * - Control Panel UI for debugging and management
 */

import express from "express";
import http from "node:http";
import path from "node:path";
import fs from "node:fs";
import os from "node:os";
import { fileURLToPath } from "node:url";
import { WebSocketServer, WebSocket } from "ws";
import { spawn } from "node:child_process";
import type { Config } from "../config/schema.js";
import { createRouter, type Router } from "./router.js";
import { SessionManager } from "../session/SessionManager.js";
import {
  loadAllowlist,
  saveAllowlist,
} from "../session/AllowlistPersistence.js";
import { ChannelRegistry } from "../channels/ChannelRegistry.js";
import { TelegramAdapter } from "../channels/adapters/TelegramAdapter.js";
import { DiscordAdapter } from "../channels/adapters/DiscordAdapter.js";
import { SlackAdapter } from "../channels/adapters/SlackAdapter.js";
import type { DMPolicy } from "../channels/types.js";
import { Scheduler, type SchedulerConfig, type CronJobDefinition } from "../scheduler/index.js";
import { NodeRegistry, NodeConnectionManager, PairingManager } from "../nodes/index.js";
import { SkillsManager } from "../skills/index.js";
import { gatewayLogs } from "../logs/index.js";
import { getUsageTracker, getErrorRegistry } from "../monitoring/index.js";
import { MessageStore } from "../storage/MessageStore.js";
import { createSessionRoutes } from "../routes/sessions.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export interface Gateway {
  start: () => Promise<void>;
  stop: () => Promise<void>;
  getRouter: () => Router;
  getSessionManager: () => SessionManager;
  getChannelRegistry: () => ChannelRegistry;
  getScheduler: () => Scheduler;
  getNodeRegistry: () => NodeRegistry;
  getNodeConnectionManager: () => NodeConnectionManager;
}

export async function createGateway(config: Config): Promise<Gateway> {
  const app = express();
  app.use(express.json({ limit: "2mb" }));

  const server = http.createServer(app);

  // Use noServer mode and handle upgrade manually to avoid conflicts
  // This gives us full control over which WebSocketServer handles each connection
  const wss = new WebSocketServer({
    noServer: true,
    perMessageDeflate: false,
  });
  const nodesWss = new WebSocketServer({
    noServer: true,
    perMessageDeflate: false,
  });

  // Handle HTTP upgrade requests manually
  server.on("upgrade", (request, socket, head) => {
    const pathname = request.url?.split("?")[0];
    console.log(`[Gateway] HTTP Upgrade request: ${request.url} (pathname: ${pathname})`);

    if (pathname === "/ws/nodes") {
      console.log("[Gateway] Routing to nodesWss");
      nodesWss.handleUpgrade(request, socket, head, (ws) => {
        nodesWss.emit("connection", ws, request);
      });
    } else if (pathname === "/ws" || pathname === config.gateway.wsPath) {
      console.log("[Gateway] Routing to main wss");
      wss.handleUpgrade(request, socket, head, (ws) => {
        wss.emit("connection", ws, request);
      });
    } else {
      console.log(`[Gateway] Unknown WebSocket path: ${pathname}, destroying socket`);
      socket.destroy();
    }
  });

  // Load persisted allowlist from disk
  const allowlistPath = config.storage.allowlistPath;
  const persistedAllowlist = await loadAllowlist(allowlistPath);
  const combinedAllowlist = [
    ...config.security.allowlist,
    ...persistedAllowlist,
  ];

  // Initialize session manager with DM policy from config
  const sessionManager = new SessionManager({
    dmPolicy: config.security.defaultDMPolicy as DMPolicy,
    allowlist: combinedAllowlist,
    onAllowlistChange: async (allowlist) => {
      await saveAllowlist(allowlistPath, allowlist);
    },
  });

  // Initialize message store for session history persistence
  const messageStorePath = path.join(os.homedir(), '.ag3nt', 'messages.db');
  const messageStore = new MessageStore(messageStorePath);
  gatewayLogs.info("MessageStore", `Message store path: ${messageStorePath}`);

  // Initialize channel registry
  const channelRegistry = new ChannelRegistry();

  // Register enabled channel adapters from config
  registerChannelAdapters(config, channelRegistry);

  // Initialize node registry for multi-device architecture
  const nodeRegistry = new NodeRegistry();

  // Log node events
  nodeRegistry.onNodeEvent((event) => {
    console.log(`[Gateway] Node ${event.type}: ${event.nodeId}`);
    gatewayLogs.info("NodeRegistry", `Node ${event.type}: ${event.nodeId}`, { event });
  });

  // Initialize pairing manager for node authentication
  const pairingManager = new PairingManager();

  // Initialize node connection manager for companion nodes
  const nodeConnectionManager = new NodeConnectionManager(nodeRegistry, pairingManager);

  // Handle companion node WebSocket connections
  nodesWss.on("connection", (ws) => {
    gatewayLogs.info("NodeConnectionManager", "New companion node connection");
    nodeConnectionManager.handleConnection(ws);
  });

  // Initialize skills manager
  // Resolve skills path relative to project root (go up from apps/gateway/dist/gateway/ to project root)
  const projectRoot = path.resolve(__dirname, "..", "..", "..", "..");
  const skillsPath = config.skills.bundledPath.startsWith("./")
    ? path.join(projectRoot, config.skills.bundledPath.slice(2))
    : config.skills.bundledPath;
  const skillsManager = new SkillsManager(skillsPath);
  gatewayLogs.info("Skills", `Skills path: ${skillsPath}`);

  // Track connected debug WebSocket clients
  const debugClients: Set<WebSocket> = new Set();

  // Subscribe to gateway logs for debug streaming
  gatewayLogs.subscribe((entry) => {
    let message: string;
    try {
      message = JSON.stringify({
        type: "log",
        id: entry.id,
        timestamp: entry.timestamp.toISOString(),
        level: entry.level,
        source: entry.source,
        message: entry.message,
        data: entry.data,
      });
    } catch (err) {
      console.error("[Gateway] Error serializing log entry:", err);
      return;
    }
    for (const client of debugClients) {
      if (client.readyState === WebSocket.OPEN) {
        try {
          client.send(message);
        } catch (err) {
          console.error("[Gateway] Error sending log to debug client:", err);
        }
      }
    }
  });

  // Create router with dependencies
  const router = createRouter(config, { sessionManager });

  // Wire channel registry message handler to router
  channelRegistry.setMessageHandler(async (message) => {
    return router.handleChannelMessage(message);
  });

  // Log channel events
  channelRegistry.onEvent((event) => {
    switch (event.type) {
      case "connected":
        console.log(`[Gateway] Channel connected: ${event.adapterId}`);
        break;
      case "disconnected":
        console.log(`[Gateway] Channel disconnected: ${event.adapterId}`);
        break;
      case "error":
        console.error(
          `[Gateway] Channel error (${event.adapterId}):`,
          event.error.message
        );
        break;
      case "message":
        console.log(
          `[Gateway] Message from ${event.adapterId}:`,
          event.message.text.slice(0, 50)
        );
        break;
    }
  });

  // Initialize scheduler
  const schedulerConfig: SchedulerConfig = {
    heartbeat: {
      intervalMinutes: config.scheduler.heartbeatMinutes,
    },
    cronJobs: config.scheduler.cron as CronJobDefinition[],
  };

  const scheduler = new Scheduler(
    schedulerConfig,
    // Message handler: sends scheduled messages to the agent via router
    async (message, sessionId, metadata) => {
      const result = await router.handleWsMessage({
        text: message,
        session_id: sessionId,
        metadata: { ...metadata, scheduled: true },
      });
      return {
        text: result.text ?? "",
        notify: result.ok && !result.error,
      };
    },
    // Channel notifier: sends notifications to connected channels
    async (channelTarget, message) => {
      // Get the first connected channel or target-specific channel
      const adapters = channelRegistry.all();
      const target = channelTarget
        ? adapters.find((a) => a.type === channelTarget || a.id === channelTarget)
        : adapters.find((a) => a.isConnected());

      if (target) {
        // For now, log notification - actual channel notification requires
        // storing a reference to send to (e.g., a chat ID)
        console.log(`[Scheduler] Notification to ${target.id}: ${message.slice(0, 100)}`);
        // TODO: Implement actual channel notification with stored chat IDs
      } else {
        console.log(`[Scheduler] No channel available for notification: ${message.slice(0, 100)}`);
      }
    },
    // Event handler: log scheduler events
    (event) => {
      console.log(`[Scheduler] Event: ${event.type}`, {
        jobId: event.jobId,
        timestamp: event.timestamp.toISOString(),
      });
    }
  );

  // Health check endpoint
  app.get(`${config.gateway.httpPath}/health`, (_req, res) => {
    const schedulerStatus = scheduler.getStatus();
    res.json({
      ok: true,
      name: "ag3nt-gateway",
      channels: channelRegistry.all().map((a) => ({
        id: a.id,
        type: a.type,
        connected: a.isConnected(),
      })),
      sessions: sessionManager.listSessions().length,
      scheduler: {
        heartbeatRunning: schedulerStatus.heartbeatRunning,
        jobCount: schedulerStatus.jobCount,
      },
    });
  });

  // Scheduler API endpoints
  app.get(`${config.gateway.httpPath}/scheduler/status`, (_req, res) => {
    res.json({ ok: true, ...scheduler.getStatus() });
  });

  app.get(`${config.gateway.httpPath}/scheduler/jobs`, (_req, res) => {
    res.json({ ok: true, jobs: scheduler.listJobs() });
  });

  app.post(`${config.gateway.httpPath}/scheduler/jobs`, (req, res) => {
    try {
      const { schedule, message, sessionMode, channelTarget, oneShot, name } = req.body;
      if (!schedule || !message) {
        res.status(400).json({ ok: false, error: "Missing schedule or message" });
        return;
      }
      const jobId = scheduler.addJob({ schedule, message, sessionMode, channelTarget, oneShot, name });
      res.json({ ok: true, jobId });
    } catch (err) {
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  app.delete(`${config.gateway.httpPath}/scheduler/jobs/:jobId`, (req, res) => {
    const removed = scheduler.removeJob(req.params.jobId);
    res.json({ ok: removed });
  });

  app.post(`${config.gateway.httpPath}/scheduler/jobs/:jobId/pause`, (req, res) => {
    const paused = scheduler.pauseJob(req.params.jobId);
    res.json({ ok: paused });
  });

  app.post(`${config.gateway.httpPath}/scheduler/jobs/:jobId/resume`, (req, res) => {
    const resumed = scheduler.resumeJob(req.params.jobId);
    res.json({ ok: resumed });
  });

  app.post(`${config.gateway.httpPath}/scheduler/heartbeat/pause`, (_req, res) => {
    scheduler.pauseHeartbeat();
    res.json({ ok: true });
  });

  app.post(`${config.gateway.httpPath}/scheduler/heartbeat/resume`, (_req, res) => {
    scheduler.resumeHeartbeat();
    res.json({ ok: true });
  });

  app.post(`${config.gateway.httpPath}/scheduler/reminder`, (req, res) => {
    try {
      const { when, message, channelTarget } = req.body;
      if (!when || !message) {
        res.status(400).json({ ok: false, error: "Missing when or message" });
        return;
      }
      // Parse 'when' - either a date string or milliseconds
      const targetDate = typeof when === "number" ? when : new Date(when);
      const jobId = scheduler.scheduleReminder(targetDate, message, channelTarget);
      res.json({ ok: true, jobId });
    } catch (err) {
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  // Node registry API endpoints
  app.get(`${config.gateway.httpPath}/nodes`, (_req, res) => {
    res.json({ ok: true, nodes: nodeRegistry.getAllNodes() });
  });

  app.get(`${config.gateway.httpPath}/nodes/status`, (_req, res) => {
    res.json({ ok: true, ...nodeRegistry.getStatus() });
  });

  app.get(`${config.gateway.httpPath}/nodes/:nodeId`, (req, res) => {
    const node = nodeRegistry.getNode(req.params.nodeId);
    if (node) {
      res.json({ ok: true, node });
    } else {
      res.status(404).json({ ok: false, error: "Node not found" });
    }
  });

  app.get(`${config.gateway.httpPath}/nodes/capability/:capability`, (req, res) => {
    const capability = req.params.capability as import("../nodes/types.js").NodeCapability;
    const nodes = nodeRegistry.findNodesByCapability(capability);
    res.json({ ok: true, nodes, hasCapability: nodes.length > 0 });
  });

  // Node pairing API endpoints
  app.post(`${config.gateway.httpPath}/nodes/pairing/generate`, (_req, res) => {
    try {
      const code = nodeConnectionManager.getPairingManager().generatePairingCode();
      res.json({ ok: true, code });
    } catch (err) {
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  app.get(`${config.gateway.httpPath}/nodes/pairing/active`, (_req, res) => {
    try {
      const code = nodeConnectionManager.getPairingManager().getActivePairingCode();
      res.json({ ok: true, code });
    } catch (err) {
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  app.get(`${config.gateway.httpPath}/nodes/approved`, (_req, res) => {
    try {
      const nodes = nodeConnectionManager.getPairingManager().getApprovedNodes();
      res.json({ ok: true, nodes });
    } catch (err) {
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  app.delete(`${config.gateway.httpPath}/nodes/:nodeId/approval`, (req, res) => {
    try {
      nodeConnectionManager.getPairingManager().removeApproval(req.params.nodeId);
      nodeRegistry.unregisterNode(req.params.nodeId);
      res.json({ ok: true, message: "Node approval removed" });
    } catch (err) {
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  // Node action execution endpoint
  app.post(`${config.gateway.httpPath}/nodes/:nodeId/action`, async (req, res) => {
    try {
      const { nodeId } = req.params;
      const { action, params, timeout } = req.body;

      if (!action) {
        res.status(400).json({ ok: false, error: "Missing action parameter" });
        return;
      }

      // Check if node exists and is online
      const node = nodeRegistry.getNode(nodeId);
      if (!node) {
        res.status(404).json({ ok: false, error: "Node not found" });
        return;
      }

      if (node.status !== "online") {
        res.status(503).json({ ok: false, error: "Node is offline" });
        return;
      }

      // Send action to node via NodeConnectionManager
      const result = await nodeConnectionManager.sendActionToNode(
        nodeId,
        action,
        params || {},
        timeout || 30000
      );

      res.json({ ok: true, result });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : String(err);

      // Check for timeout errors
      if (errorMessage.includes("timeout") || errorMessage.includes("Timeout")) {
        res.status(504).json({ ok: false, error: "Action timed out" });
      } else {
        res.status(500).json({ ok: false, error: errorMessage });
      }
    }
  });

  // Mount session API routes (with message history support)
  const sessionRoutes = createSessionRoutes(sessionManager, messageStore);
  app.use("/api/sessions", sessionRoutes);

  // Session management endpoints (legacy, kept for backward compatibility)
  app.get(`${config.gateway.httpPath}/sessions`, (_req, res) => {
    const sessions = sessionManager.listSessions();
    res.json({ ok: true, sessions });
  });

  app.get(`${config.gateway.httpPath}/sessions/pending`, (_req, res) => {
    const pending = sessionManager.getPendingSessions();
    res.json({ ok: true, sessions: pending });
  });

  app.post(
    `${config.gateway.httpPath}/sessions/:sessionId/approve`,
    async (req, res) => {
      const { sessionId } = req.params;
      const { code } = req.body;

      let approved: boolean;
      if (code) {
        approved = await sessionManager.approveSession(sessionId, code);
      } else {
        approved = await sessionManager.manualApprove(sessionId);
      }

      if (approved) {
        res.json({ ok: true, message: "Session approved" });
      } else {
        res.status(400).json({ ok: false, error: "Invalid session or code" });
      }
    }
  );

  // Delete a specific session
  app.delete(`${config.gateway.httpPath}/sessions/:sessionId`, (_req, res) => {
    const { sessionId } = _req.params;
    const decodedId = decodeURIComponent(sessionId);
    const removed = sessionManager.removeSession(decodedId);
    if (removed) {
      gatewayLogs.info("Sessions", `Session removed: ${decodedId}`);
      res.json({ ok: true, message: "Session removed" });
    } else {
      res.status(404).json({ ok: false, error: "Session not found" });
    }
  });

  // Clear all sessions
  app.post(`${config.gateway.httpPath}/sessions/clear`, (_req, res) => {
    const sessions = sessionManager.listSessions();
    let cleared = 0;
    for (const session of sessions) {
      if (sessionManager.removeSession(session.id)) {
        cleared++;
      }
    }
    gatewayLogs.info("Sessions", `Cleared ${cleared} sessions`);
    res.json({ ok: true, cleared });
  });

  // ==================== SKILLS API ====================

  // List all skills with metadata
  app.get(`${config.gateway.httpPath}/skills`, async (_req, res) => {
    try {
      const skills = await skillsManager.getAllSkills();
      res.json({ ok: true, skills });
    } catch (err) {
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  // Get all skill categories
  app.get(`${config.gateway.httpPath}/skills/categories`, async (_req, res) => {
    try {
      const categories = await skillsManager.getCategories();
      res.json({ ok: true, categories });
    } catch (err) {
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  // Get a specific skill's metadata
  app.get(`${config.gateway.httpPath}/skills/:skillId`, async (req, res) => {
    try {
      const skill = await skillsManager.getSkill(req.params.skillId);
      if (skill) {
        res.json({ ok: true, skill });
      } else {
        res.status(404).json({ ok: false, error: "Skill not found" });
      }
    } catch (err) {
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  // Get a skill's SKILL.md content
  app.get(`${config.gateway.httpPath}/skills/:skillId/content`, async (req, res) => {
    try {
      const content = await skillsManager.getSkillContent(req.params.skillId);
      if (content) {
        res.json({ ok: true, content });
      } else {
        res.status(404).json({ ok: false, error: "Skill not found" });
      }
    } catch (err) {
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  // Toggle a skill on/off
  app.post(`${config.gateway.httpPath}/skills/:skillId/toggle`, (req, res) => {
    const { enabled } = req.body;
    const toggled = skillsManager.toggleSkill(req.params.skillId, enabled !== false);
    gatewayLogs.info("Skills", `Skill ${req.params.skillId} ${enabled !== false ? "enabled" : "disabled"}`);
    res.json({ ok: toggled, enabled: enabled !== false });
  });

  // ==================== LOGS API ====================

  // Get recent logs
  app.get(`${config.gateway.httpPath}/logs/recent`, (req, res) => {
    const count = parseInt(req.query.count as string) || 100;
    const level = req.query.level as import("../logs/index.js").LogLevel | undefined;
    const logs = gatewayLogs.getRecent(count, level);
    res.json({ ok: true, logs });
  });

  // Clear logs
  app.post(`${config.gateway.httpPath}/logs/clear`, (_req, res) => {
    gatewayLogs.clear();
    res.json({ ok: true });
  });

  // ==================== CONTROL PANEL ====================

  // Trigger heartbeat immediately
  app.post(`${config.gateway.httpPath}/scheduler/heartbeat/trigger`, async (_req, res) => {
    try {
      gatewayLogs.info("Scheduler", "Manual heartbeat triggered");
      // Send the heartbeat message through the router
      const result = await router.handleWsMessage({
        text: "[HEARTBEAT] Check-in time. How are we doing? Any updates or tasks to report on?",
        session_id: `heartbeat:manual:${Date.now()}`,
        metadata: { scheduled: true, heartbeat: true, manual: true },
      });
      res.json({ ok: true, result });
    } catch (err) {
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  // Get agent status
  app.get(`${config.gateway.httpPath}/status`, (_req, res) => {
    const schedulerStatus = scheduler.getStatus();
    const nodeStatus = nodeRegistry.getStatus();
    res.json({
      ok: true,
      status: "online",
      scheduler: schedulerStatus,
      nodes: nodeStatus,
      sessions: sessionManager.listSessions().length,
      channels: channelRegistry.all().map((a) => ({
        id: a.id,
        type: a.type,
        connected: a.isConnected(),
      })),
    });
  });

  // Launch TUI
  app.post(`${config.gateway.httpPath}/tui/launch`, (_req, res) => {
    try {
      const projectRoot = path.resolve(__dirname, "..", "..", "..", "..");
      const tuiPath = path.join(projectRoot, "apps", "tui");

      // Determine the correct command based on platform
      const isWindows = process.platform === "win32";

      if (isWindows) {
        // On Windows, open a new terminal window with the TUI
        spawn("cmd.exe", ["/c", "start", "cmd", "/k", "python ag3nt_tui.py"], {
          cwd: tuiPath,
          detached: true,
          stdio: "ignore",
        });
      } else {
        // On macOS/Linux, try to open a new terminal
        const terminal = process.platform === "darwin" ? "open" : "x-terminal-emulator";
        spawn(terminal, ["-e", `cd "${tuiPath}" && python ag3nt_tui.py`], {
          detached: true,
          stdio: "ignore",
        });
      }

      gatewayLogs.info("ControlPanel", "TUI launched");
      res.json({ ok: true, message: "TUI launched" });
    } catch (err) {
      gatewayLogs.error("ControlPanel", `Failed to launch TUI: ${err instanceof Error ? err.message : String(err)}`);
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  // ========================================
  // Workspace Browser API
  // ========================================

  // Get workspace path (cross-platform)
  const getWorkspacePath = (): string => {
    const homeDir = os.homedir();
    return path.join(homeDir, ".ag3nt", "workspace");
  };

  // Helper to recursively list files
  interface FileEntry {
    name: string;
    path: string;
    type: "file" | "directory";
    size?: number;
    children?: FileEntry[];
  }

  const listFilesRecursive = (dirPath: string, basePath: string = ""): FileEntry[] => {
    const entries: FileEntry[] = [];
    try {
      const items = fs.readdirSync(dirPath, { withFileTypes: true });
      for (const item of items) {
        const relativePath = basePath ? `${basePath}/${item.name}` : item.name;
        const fullPath = path.join(dirPath, item.name);

        if (item.isDirectory()) {
          entries.push({
            name: item.name,
            path: relativePath,
            type: "directory",
            children: listFilesRecursive(fullPath, relativePath),
          });
        } else if (item.isFile()) {
          const stats = fs.statSync(fullPath);
          entries.push({
            name: item.name,
            path: relativePath,
            type: "file",
            size: stats.size,
          });
        }
      }
    } catch (err) {
      gatewayLogs.error("Workspace", `Failed to list files: ${err}`);
    }
    return entries;
  };

  // List all files in workspace
  app.get(`${config.gateway.httpPath}/workspace/files`, (_req, res) => {
    try {
      const workspacePath = getWorkspacePath();

      // Ensure workspace exists
      if (!fs.existsSync(workspacePath)) {
        fs.mkdirSync(workspacePath, { recursive: true });
      }

      const files = listFilesRecursive(workspacePath);
      res.json({ ok: true, files, workspacePath });
    } catch (err) {
      gatewayLogs.error("Workspace", `Failed to list workspace: ${err}`);
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  // Read file content
  app.get(`${config.gateway.httpPath}/workspace/file`, (req, res) => {
    try {
      const filePath = req.query.path as string;
      if (!filePath) {
        res.status(400).json({ ok: false, error: "Missing path parameter" });
        return;
      }

      // Security: prevent path traversal
      if (filePath.includes("..") || path.isAbsolute(filePath)) {
        res.status(400).json({ ok: false, error: "Invalid path" });
        return;
      }

      const workspacePath = getWorkspacePath();
      const fullPath = path.join(workspacePath, filePath);

      // Verify the file is within workspace
      if (!fullPath.startsWith(workspacePath)) {
        res.status(400).json({ ok: false, error: "Path outside workspace" });
        return;
      }

      if (!fs.existsSync(fullPath)) {
        res.status(404).json({ ok: false, error: "File not found" });
        return;
      }

      const stats = fs.statSync(fullPath);
      if (stats.isDirectory()) {
        res.status(400).json({ ok: false, error: "Cannot read directory" });
        return;
      }

      // Check file size (limit to 1MB for preview)
      if (stats.size > 1024 * 1024) {
        res.json({
          ok: true,
          content: null,
          truncated: true,
          size: stats.size,
          message: "File too large to preview (>1MB)"
        });
        return;
      }

      const content = fs.readFileSync(fullPath, "utf-8");
      res.json({ ok: true, content, size: stats.size });
    } catch (err) {
      gatewayLogs.error("Workspace", `Failed to read file: ${err}`);
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  // Download file
  app.get(`${config.gateway.httpPath}/workspace/download`, (req, res) => {
    try {
      const filePath = req.query.path as string;
      if (!filePath) {
        res.status(400).json({ ok: false, error: "Missing path parameter" });
        return;
      }

      // Security: prevent path traversal
      if (filePath.includes("..") || path.isAbsolute(filePath)) {
        res.status(400).json({ ok: false, error: "Invalid path" });
        return;
      }

      const workspacePath = getWorkspacePath();
      const fullPath = path.join(workspacePath, filePath);

      // Verify the file is within workspace
      if (!fullPath.startsWith(workspacePath)) {
        res.status(400).json({ ok: false, error: "Path outside workspace" });
        return;
      }

      if (!fs.existsSync(fullPath)) {
        res.status(404).json({ ok: false, error: "File not found" });
        return;
      }

      res.download(fullPath);
    } catch (err) {
      gatewayLogs.error("Workspace", `Failed to download file: ${err}`);
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  // ========================================
  // Model Selector API
  // ========================================

  // Get .env file path
  const getEnvPath = (): string => {
    // Go up from gateway to repo root
    return path.resolve(__dirname, "..", "..", "..", "..", ".env");
  };

  // Parse .env file into key-value pairs
  const parseEnvFile = (content: string): Record<string, string> => {
    const env: Record<string, string> = {};
    const lines = content.split("\n");
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const eqIndex = trimmed.indexOf("=");
      if (eqIndex > 0) {
        const key = trimmed.substring(0, eqIndex);
        const value = trimmed.substring(eqIndex + 1);
        env[key] = value;
      }
    }
    return env;
  };

  // Available model providers and their models
  // Model IDs must match what the agent runtime expects
  const MODEL_OPTIONS = {
    openrouter: {
      name: "OpenRouter",
      models: [
        { id: "anthropic/claude-sonnet-4", name: "Claude Sonnet 4" },
        { id: "anthropic/claude-3.5-sonnet", name: "Claude 3.5 Sonnet" },
        { id: "anthropic/claude-3-opus", name: "Claude 3 Opus" },
        { id: "openai/gpt-4o", name: "GPT-4o" },
        { id: "openai/gpt-4-turbo", name: "GPT-4 Turbo" },
        { id: "google/gemini-pro-1.5", name: "Gemini Pro 1.5" },
        { id: "deepseek/deepseek-chat", name: "DeepSeek Chat" },
        { id: "moonshotai/kimi-k2-thinking", name: "Kimi K2 Thinking" },
        { id: "moonshotai/kimi-k2.5", name: "Kimi K2.5" },
        { id: "meta-llama/llama-3.1-405b-instruct", name: "Llama 3.1 405B" },
      ],
    },
    kimi: {
      name: "Kimi (Direct)",
      models: [
        { id: "moonshot-v1-128k", name: "Moonshot V1 128K" },
        { id: "moonshot-v1-32k", name: "Moonshot V1 32K" },
        { id: "moonshot-v1-8k", name: "Moonshot V1 8K" },
        { id: "kimi-latest", name: "Kimi Latest" },
      ],
    },
    openai: {
      name: "OpenAI (Direct)",
      models: [
        { id: "gpt-4o", name: "GPT-4o" },
        { id: "gpt-4-turbo", name: "GPT-4 Turbo" },
        { id: "gpt-4", name: "GPT-4" },
        { id: "gpt-3.5-turbo", name: "GPT-3.5 Turbo" },
      ],
    },
    anthropic: {
      name: "Anthropic (Direct)",
      models: [
        { id: "claude-sonnet-4-5-20250929", name: "Claude Sonnet 4.5" },
        { id: "claude-3-opus-20240229", name: "Claude 3 Opus" },
        { id: "claude-3-5-sonnet-20241022", name: "Claude 3.5 Sonnet" },
      ],
    },
    google: {
      name: "Google (Direct)",
      models: [
        { id: "gemini-pro", name: "Gemini Pro" },
        { id: "gemini-pro-1.5", name: "Gemini Pro 1.5" },
      ],
    },
  };

  // Get current model configuration
  app.get(`${config.gateway.httpPath}/model/config`, (_req, res) => {
    try {
      const envPath = getEnvPath();

      if (!fs.existsSync(envPath)) {
        res.json({
          ok: true,
          provider: "openrouter",
          model: "moonshotai/kimi-k2-thinking",
          options: MODEL_OPTIONS,
        });
        return;
      }

      const content = fs.readFileSync(envPath, "utf-8");
      const env = parseEnvFile(content);

      res.json({
        ok: true,
        provider: env.AG3NT_MODEL_PROVIDER || "openrouter",
        model: env.AG3NT_MODEL_NAME || "moonshotai/kimi-k2-thinking",
        options: MODEL_OPTIONS,
      });
    } catch (err) {
      gatewayLogs.error("Model", `Failed to get model config: ${err}`);
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  // Update model configuration
  app.post(`${config.gateway.httpPath}/model/config`, (req, res) => {
    try {
      const { provider, model } = req.body;

      if (!provider || !model) {
        res.status(400).json({ ok: false, error: "Missing provider or model" });
        return;
      }

      // Validate provider
      if (!MODEL_OPTIONS[provider as keyof typeof MODEL_OPTIONS]) {
        res.status(400).json({ ok: false, error: "Invalid provider" });
        return;
      }

      const envPath = getEnvPath();
      let content = "";

      if (fs.existsSync(envPath)) {
        content = fs.readFileSync(envPath, "utf-8");
      }

      // Update or add AG3NT_MODEL_PROVIDER
      if (content.includes("AG3NT_MODEL_PROVIDER=")) {
        content = content.replace(/AG3NT_MODEL_PROVIDER=.*/g, `AG3NT_MODEL_PROVIDER=${provider}`);
      } else {
        content += `\nAG3NT_MODEL_PROVIDER=${provider}`;
      }

      // Update or add AG3NT_MODEL_NAME
      if (content.includes("AG3NT_MODEL_NAME=")) {
        content = content.replace(/AG3NT_MODEL_NAME=.*/g, `AG3NT_MODEL_NAME=${model}`);
      } else {
        content += `\nAG3NT_MODEL_NAME=${model}`;
      }

      fs.writeFileSync(envPath, content);

      gatewayLogs.info("Model", `Model config updated: ${provider}/${model}`);
      res.json({ ok: true, message: "Model configuration updated. Restart agent to apply." });
    } catch (err) {
      gatewayLogs.error("Model", `Failed to update model config: ${err}`);
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  // ========================================
  // Agent Control API
  // ========================================

  // Restart agent worker
  app.post(`${config.gateway.httpPath}/agent/restart`, (_req, res) => {
    try {
      const projectRoot = path.resolve(__dirname, "..", "..", "..", "..");
      const agentPath = path.join(projectRoot, "apps", "agent");

      const isWindows = process.platform === "win32";

      if (isWindows) {
        // On Windows, start a new agent worker process
        spawn("cmd.exe", ["/c", "start", "cmd", "/k", "python -m ag3nt_agent.worker"], {
          cwd: agentPath,
          detached: true,
          stdio: "ignore",
        });
      } else {
        // On macOS/Linux
        const terminal = process.platform === "darwin" ? "open" : "x-terminal-emulator";
        spawn(terminal, ["-e", `cd "${agentPath}" && python -m ag3nt_agent.worker`], {
          detached: true,
          stdio: "ignore",
        });
      }

      gatewayLogs.info("Agent", "Agent worker restart initiated");
      res.json({ ok: true, message: "Agent worker restart initiated. A new terminal window should open." });
    } catch (err) {
      gatewayLogs.error("Agent", `Failed to restart agent: ${err instanceof Error ? err.message : String(err)}`);
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  // Get agent health status
  app.get(`${config.gateway.httpPath}/agent/health`, async (_req, res) => {
    try {
      // Try to ping the agent worker (agent always runs on port 18790)
      const agentUrl = `http://localhost:18790/health`;
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 3000);

      try {
        const response = await fetch(agentUrl, { signal: controller.signal });
        clearTimeout(timeout);

        if (response.ok) {
          const data = await response.json();
          res.json({ ok: true, status: "online", ...data });
        } else {
          res.json({ ok: true, status: "error", message: "Agent returned error" });
        }
      } catch (fetchErr) {
        clearTimeout(timeout);
        res.json({ ok: true, status: "offline", message: "Agent not responding" });
      }
    } catch (err) {
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  // ========================================
  // Memory API
  // ========================================

  // Get user data path (cross-platform)
  const getUserDataPath = (): string => {
    const homeDir = os.homedir();
    return path.join(homeDir, ".ag3nt");
  };

  // List memory files
  app.get(`${config.gateway.httpPath}/memory/files`, (_req, res) => {
    try {
      const userDataPath = getUserDataPath();
      const memoryPath = path.join(userDataPath, "memory");

      const files: { name: string; path: string; type: "main" | "log"; size: number; modified: string }[] = [];

      // Add main memory files
      const mainFiles = ["AGENTS.md", "MEMORY.md"];
      for (const filename of mainFiles) {
        const filePath = path.join(userDataPath, filename);
        if (fs.existsSync(filePath)) {
          const stat = fs.statSync(filePath);
          files.push({
            name: filename,
            path: filename,
            type: "main",
            size: stat.size,
            modified: stat.mtime.toISOString(),
          });
        }
      }

      // Add daily log files from memory/ folder
      if (fs.existsSync(memoryPath)) {
        const logFiles = fs.readdirSync(memoryPath).filter((f) => f.endsWith(".md"));
        for (const filename of logFiles) {
          const filePath = path.join(memoryPath, filename);
          const stat = fs.statSync(filePath);
          files.push({
            name: filename,
            path: `memory/${filename}`,
            type: "log",
            size: stat.size,
            modified: stat.mtime.toISOString(),
          });
        }
      }

      // Sort by modified date (newest first)
      files.sort((a, b) => new Date(b.modified).getTime() - new Date(a.modified).getTime());

      res.json({ ok: true, files, basePath: userDataPath });
    } catch (err) {
      gatewayLogs.error("Memory", `Failed to list files: ${err}`);
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  // Read a memory file
  app.get(`${config.gateway.httpPath}/memory/file`, (req, res) => {
    try {
      const { path: filePath } = req.query;
      if (!filePath || typeof filePath !== "string") {
        res.status(400).json({ ok: false, error: "Missing path parameter" });
        return;
      }

      const userDataPath = getUserDataPath();
      const fullPath = path.join(userDataPath, filePath);

      // Security: prevent path traversal
      const normalizedPath = path.normalize(fullPath);
      if (!normalizedPath.startsWith(userDataPath)) {
        res.status(403).json({ ok: false, error: "Path traversal not allowed" });
        return;
      }

      if (!fs.existsSync(fullPath)) {
        res.status(404).json({ ok: false, error: "File not found" });
        return;
      }

      const content = fs.readFileSync(fullPath, "utf-8");
      const stat = fs.statSync(fullPath);

      res.json({
        ok: true,
        content,
        path: filePath,
        size: stat.size,
        modified: stat.mtime.toISOString(),
      });
    } catch (err) {
      gatewayLogs.error("Memory", `Failed to read file: ${err}`);
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  // Update a memory file
  app.post(`${config.gateway.httpPath}/memory/file`, (req, res) => {
    try {
      const { path: filePath, content } = req.body;
      if (!filePath || typeof filePath !== "string") {
        res.status(400).json({ ok: false, error: "Missing path parameter" });
        return;
      }
      if (content === undefined || typeof content !== "string") {
        res.status(400).json({ ok: false, error: "Missing content parameter" });
        return;
      }

      const userDataPath = getUserDataPath();
      const fullPath = path.join(userDataPath, filePath);

      // Security: prevent path traversal
      const normalizedPath = path.normalize(fullPath);
      if (!normalizedPath.startsWith(userDataPath)) {
        res.status(403).json({ ok: false, error: "Path traversal not allowed" });
        return;
      }

      // Create parent directories if needed
      const parentDir = path.dirname(fullPath);
      if (!fs.existsSync(parentDir)) {
        fs.mkdirSync(parentDir, { recursive: true });
      }

      fs.writeFileSync(fullPath, content, "utf-8");
      gatewayLogs.info("Memory", `File updated: ${filePath}`);

      res.json({ ok: true, message: "File saved successfully" });
    } catch (err) {
      gatewayLogs.error("Memory", `Failed to save file: ${err}`);
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  // Create a new memory file
  app.post(`${config.gateway.httpPath}/memory/create`, (req, res) => {
    try {
      const { filename, type } = req.body;
      if (!filename || typeof filename !== "string") {
        res.status(400).json({ ok: false, error: "Missing filename parameter" });
        return;
      }

      const userDataPath = getUserDataPath();
      const memoryPath = path.join(userDataPath, "memory");

      // Ensure memory directory exists
      if (!fs.existsSync(memoryPath)) {
        fs.mkdirSync(memoryPath, { recursive: true });
      }

      const filePath = type === "log" ? path.join(memoryPath, filename) : path.join(userDataPath, filename);

      // Security check
      const normalizedPath = path.normalize(filePath);
      if (!normalizedPath.startsWith(userDataPath)) {
        res.status(403).json({ ok: false, error: "Path traversal not allowed" });
        return;
      }

      if (fs.existsSync(filePath)) {
        res.status(400).json({ ok: false, error: "File already exists" });
        return;
      }

      const template = type === "log"
        ? `# ${filename.replace(".md", "")}\n\n## Notes\n\n`
        : `# ${filename.replace(".md", "")}\n\n`;

      fs.writeFileSync(filePath, template, "utf-8");
      gatewayLogs.info("Memory", `File created: ${filename}`);

      res.json({ ok: true, path: type === "log" ? `memory/${filename}` : filename });
    } catch (err) {
      gatewayLogs.error("Memory", `Failed to create file: ${err}`);
      res.status(500).json({ ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  });

  // Serve Control Panel UI static files
  // Path is relative to the gateway package root (works for both src and dist)
  const gatewayRoot = path.resolve(__dirname, "..", "..");
  const uiPath = path.join(gatewayRoot, "src", "ui", "public");
  app.use("/", express.static(uiPath));

  // Fallback to index.html for SPA routing
  app.get("/", (_req, res) => {
    res.sendFile(path.join(uiPath, "index.html"));
  });

  // Simple HTTP chat endpoint for CLI channel
  // POST /api/chat { text: string, session_id?: string }
  // Returns { ok: boolean, text: string, session_id: string, events: array }
  app.post(`${config.gateway.httpPath}/chat`, async (req, res) => {
    try {
      const { text, session_id, metadata } = req.body;

      if (!text || typeof text !== "string") {
        res
          .status(400)
          .json({ ok: false, error: "Missing or invalid 'text' field" });
        return;
      }

      const result = await router.handleWsMessage({
        text,
        session_id: session_id || crypto.randomUUID(),
        metadata,
      });

      res.json(result);
    } catch (err) {
      res.status(500).json({
        ok: false,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  });

  // ─────────────────────────────────────────────────────────────────
  // Monitoring Endpoints
  // ─────────────────────────────────────────────────────────────────

  // GET /api/monitoring/usage - Get usage statistics
  app.get(`${config.gateway.httpPath}/monitoring/usage`, (req, res) => {
    try {
      const tracker = getUsageTracker();
      const { start, end } = req.query;

      let timeRange;
      if (start && end) {
        timeRange = {
          start: new Date(start as string),
          end: new Date(end as string),
        };
      }

      const stats = tracker.getUsageStats(timeRange);
      res.json({ ok: true, data: stats });
    } catch (err) {
      res.status(500).json({
        ok: false,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  });

  // GET /api/monitoring/usage/export - Export usage data as downloadable JSON
  app.get(`${config.gateway.httpPath}/monitoring/usage/export`, (_req, res) => {
    try {
      const tracker = getUsageTracker();
      const stats = tracker.getUsageStats();

      res.setHeader("Content-Type", "application/json");
      res.setHeader("Content-Disposition", "attachment; filename=usage-export.json");
      res.json(stats);
    } catch (err) {
      res.status(500).json({
        ok: false,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  });

  // GET /api/monitoring/errors - Get all error definitions
  app.get(`${config.gateway.httpPath}/monitoring/errors`, (_req, res) => {
    try {
      const registry = getErrorRegistry();
      const definitions = registry.getAllDefinitions();
      res.json({ ok: true, data: definitions });
    } catch (err) {
      res.status(500).json({
        ok: false,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  });

  // GET /api/monitoring/health - Health check endpoint
  app.get(`${config.gateway.httpPath}/monitoring/health`, (_req, res) => {
    res.json({
      ok: true,
      status: "healthy",
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
      memory: process.memoryUsage(),
    });
  });

  // Add error handler at WebSocketServer level
  wss.on("error", (err) => {
    console.error("[Gateway] WebSocketServer error:", err);
  });

  // WebSocket handler for real-time streaming
  wss.on("connection", (ws, req) => {
    console.log(`[Gateway] WebSocket connection from ${req.url}`);

    // Check if this is a debug connection (for control panel)
    const isDebug = req.url?.includes("debug=true");

    if (isDebug) {
      // Add to debug clients for log streaming
      debugClients.add(ws);
      console.log("[Gateway] Debug WebSocket connected, readyState:", ws.readyState);

      ws.on("error", (err) => {
        console.log(`[Gateway] Debug WebSocket error: ${err.message}`);
      });

      ws.on("close", (code, reason) => {
        console.log(`[Gateway] Debug WebSocket closed: code=${code}, reason=${reason?.toString() || 'none'}`);
        debugClients.delete(ws);
      });

      // Don't send anything - just keep connection open for future log streaming
      return;
    }

    // Regular chat WebSocket
    console.log("[Gateway] Regular chat WebSocket connected");

    ws.on("error", (err) => {
      console.log(`[Gateway] Chat WebSocket error: ${err.message}`);
    });

    ws.on("message", async (data) => {
      try {
        const msg = JSON.parse(data.toString());
        const out = await router.handleWsMessage(msg);
        if (out) ws.send(JSON.stringify(out));
      } catch (err) {
        ws.send(JSON.stringify({ ok: false, error: String(err) }));
      }
    });
  });

  return {
    start: async () => {
      // Connect all registered channel adapters
      await channelRegistry.connectAll();

      // Start the scheduler
      scheduler.start();

      await new Promise<void>((resolve) => {
        server.listen(config.gateway.port, config.gateway.host, () => {
          console.log(
            `[Gateway] Listening on http://${config.gateway.host}:${config.gateway.port}`
          );
          resolve();
        });
      });
    },
    stop: async () => {
      // Stop the scheduler
      scheduler.stop();

      // Stop node connection manager
      nodeConnectionManager.stop();

      // Close message store
      messageStore.close();

      // Disconnect all channel adapters
      await channelRegistry.disconnectAll();

      await new Promise<void>((resolve, reject) => {
        server.close((err) => (err ? reject(err) : resolve()));
      });
    },
    getRouter: () => router,
    getSessionManager: () => sessionManager,
    getChannelRegistry: () => channelRegistry,
    getScheduler: () => scheduler,
    getNodeRegistry: () => nodeRegistry,
    getNodeConnectionManager: () => nodeConnectionManager,
  };
}

/**
 * Register channel adapters from config.
 */
function registerChannelAdapters(
  config: Config,
  registry: ChannelRegistry
): void {
  const enabledChannels = config.channels.enabled;

  // Register Telegram adapter if enabled
  if (
    enabledChannels.includes("telegram") &&
    config.channels.telegram.enabled &&
    config.channels.telegram.botToken
  ) {
    const telegramAdapter = new TelegramAdapter({
      botToken: config.channels.telegram.botToken,
      pollingInterval: config.channels.telegram.pollingInterval,
      adapterId: "telegram-main",
    });
    registry.register(telegramAdapter);
    console.log("[Gateway] Registered Telegram adapter");
  }

  // Register Discord adapter if enabled
  if (
    enabledChannels.includes("discord") &&
    config.channels.discord.enabled &&
    config.channels.discord.botToken
  ) {
    const discordAdapter = new DiscordAdapter({
      botToken: config.channels.discord.botToken,
      clientId: config.channels.discord.clientId,
      allowGuilds: config.channels.discord.allowGuilds,
      allowDMs: config.channels.discord.allowDMs,
      adapterId: "discord-main",
    });
    registry.register(discordAdapter);
    console.log("[Gateway] Registered Discord adapter");
  }

  // Register Slack adapter if enabled
  if (
    enabledChannels.includes("slack") &&
    config.channels.slack.enabled &&
    config.channels.slack.botToken &&
    config.channels.slack.appToken
  ) {
    const slackAdapter = new SlackAdapter({
      botToken: config.channels.slack.botToken,
      appToken: config.channels.slack.appToken,
      signingSecret: config.channels.slack.signingSecret,
      adapterId: "slack-main",
    });
    registry.register(slackAdapter);
    console.log("[Gateway] Registered Slack adapter");
  }
}
