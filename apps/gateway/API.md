# AG3NT Gateway API Reference

The Gateway provides HTTP and WebSocket APIs for interacting with the AG3NT agent.

**Base URL**: `http://127.0.0.1:18789/api`

## Health & Status

### GET /api/health

Check gateway health and status.

**Response:**
```json
{
  "ok": true,
  "name": "ag3nt-gateway",
  "channels": [
    { "id": "telegram-main", "type": "telegram", "connected": true }
  ],
  "sessions": 3,
  "scheduler": {
    "heartbeatRunning": true,
    "jobCount": 2
  }
}
```

---

## Chat

### POST /api/chat

Send a message to the agent and receive a response.

**Request:**
```json
{
  "text": "Hello, what can you help me with?",
  "session_id": "optional-session-id",
  "metadata": {}
}
```

**Response (Success):**
```json
{
  "ok": true,
  "session_id": "abc123-def456",
  "text": "I can help you with many things...",
  "events": [
    { "tool_name": "web_search", "status": "completed" }
  ]
}
```

**Response (Pairing Required):**
```json
{
  "ok": false,
  "pairingRequired": true,
  "pairingCode": "A1B2C3",
  "text": "🔒 Please approve pairing code: A1B2C3",
  "session_id": "abc123"
}
```

**Response (Approval Pending):**
```json
{
  "ok": true,
  "approvalPending": true,
  "text": "⏸️ Approval Required...",
  "session_id": "abc123"
}
```

---

## Sessions

### GET /api/sessions

List all active sessions.

**Response:**
```json
{
  "ok": true,
  "sessions": [
    {
      "id": "cli:local:abc123",
      "channelType": "cli",
      "channelId": "local",
      "userId": "local-user",
      "paired": true,
      "createdAt": "2024-01-15T10:30:00Z"
    }
  ]
}
```

### GET /api/sessions/pending

Get sessions awaiting pairing approval.

**Response:**
```json
{
  "ok": true,
  "sessions": [
    {
      "id": "telegram:123:456",
      "pairingCode": "X7Y8Z9",
      "createdAt": "2024-01-15T10:30:00Z"
    }
  ]
}
```

### POST /api/sessions/:sessionId/approve

Approve a session (with or without pairing code).

**Request (with code):**
```json
{
  "code": "A1B2C3"
}
```

**Request (manual approval):**
```json
{}
```

**Response:**
```json
{
  "ok": true,
  "message": "Session approved"
}
```

---

## Scheduler

### GET /api/scheduler/status

Get scheduler status.

**Response:**
```json
{
  "ok": true,
  "heartbeatRunning": true,
  "heartbeatPaused": false,
  "lastHeartbeat": "2024-01-15T10:30:00Z",
  "jobCount": 2,
  "jobs": [...]
}
```

### GET /api/scheduler/jobs

List all scheduled jobs.

**Response:**
```json
{
  "ok": true,
  "jobs": [
    {
      "id": "job-1",
      "schedule": "0 9 * * *",
      "message": "DAILY_BRIEFING",
      "name": "Morning Briefing",
      "sessionMode": "main",
      "paused": false,
      "nextRun": "2024-01-16T09:00:00Z",
      "createdAt": "2024-01-15T10:00:00Z"
    }
  ]
}
```

### POST /api/scheduler/jobs

Create a new scheduled job.

**Request:**
```json
{
  "schedule": "0 9 * * *",
  "message": "Good morning! What's on my agenda?",
  "name": "Morning Check-in",
  "sessionMode": "main",
  "channelTarget": "telegram",
  "oneShot": false
}
```

| Field | Type | Description |
|-------|------|-------------|
| `schedule` | string | Cron expression or relative time ("in 10 minutes") |
| `message` | string | Message to send to agent |
| `name` | string | Optional job name |
| `sessionMode` | string | "main" (shared) or "isolated" (new session) |
| `channelTarget` | string | Optional channel to notify |
| `oneShot` | boolean | Delete after first execution |

**Response:**
```json
{
  "ok": true,
  "jobId": "job-3"
}
```

### DELETE /api/scheduler/jobs/:jobId

Remove a scheduled job.

**Response:**
```json
{ "ok": true }
```

### POST /api/scheduler/jobs/:jobId/pause

Pause a scheduled job.

**Response:**
```json
{ "ok": true }
```

### POST /api/scheduler/jobs/:jobId/resume

Resume a paused job.

**Response:**
```json
{ "ok": true }
```

### POST /api/scheduler/heartbeat/pause

Pause the heartbeat system.

**Response:**
```json
{ "ok": true }
```

### POST /api/scheduler/heartbeat/resume

Resume the heartbeat system.

**Response:**
```json
{ "ok": true }
```

### POST /api/scheduler/reminder

Schedule a one-shot reminder.

**Request:**
```json
{
  "when": "2024-01-15T15:00:00Z",
  "message": "Call Alice",
  "channelTarget": "telegram"
}
```

The `when` field can be:
- ISO date string: `"2024-01-15T15:00:00Z"`
- Milliseconds from now: `3600000` (1 hour)

**Response:**
```json
{
  "ok": true,
  "jobId": "reminder-1"
}
```

---

## Nodes

### GET /api/nodes

List all registered nodes.

**Response:**
```json
{
  "ok": true,
  "nodes": [
    {
      "id": "local",
      "name": "DESKTOP-ABC123",
      "type": "primary",
      "status": "online",
      "capabilities": [
        "file_management",
        "application_control",
        "system_info",
        "code_execution",
        "clipboard",
        "notifications",
        "audio_output"
      ],
      "platform": {
        "os": "windows",
        "version": "10.0.22631",
        "arch": "x64"
      },
      "connectedAt": "2024-01-15T10:00:00Z",
      "lastSeen": "2024-01-15T10:30:00Z"
    }
  ]
}
```

### GET /api/nodes/status

Get node registry status summary.

**Response:**
```json
{
  "ok": true,
  "nodeCount": 2,
  "onlineCount": 2,
  "localNode": { ... },
  "capabilities": [
    "file_management",
    "application_control",
    "system_info",
    "code_execution",
    "clipboard",
    "notifications",
    "audio_output"
  ]
}
```

### GET /api/nodes/:nodeId

Get a specific node by ID.

**Response:**
```json
{
  "ok": true,
  "node": {
    "id": "local",
    "name": "DESKTOP-ABC123",
    ...
  }
}
```

### GET /api/nodes/capability/:capability

Find nodes with a specific capability.

**Example:** `GET /api/nodes/capability/camera`

**Response:**
```json
{
  "ok": true,
  "nodes": [],
  "hasCapability": false
}
```

**Available Capabilities:**
- `file_management` - File operations
- `application_control` - Launch/control apps
- `system_info` - System monitoring
- `code_execution` - Run code/scripts
- `camera` - Camera capture
- `microphone` - Audio input
- `audio_output` - TTS/audio playback
- `notifications` - System notifications
- `home_automation` - Smart home control
- `clipboard` - Clipboard access
- `screen_capture` - Screenshot/recording

### POST /api/nodes/pairing/generate

Generate a new pairing code for connecting a companion device.

**Response:**
```json
{
  "ok": true,
  "code": "123456"
}
```

The pairing code expires in 5 minutes and can only be used once.

### GET /api/nodes/pairing/active

Get the currently active pairing code (if any).

**Response:**
```json
{
  "ok": true,
  "code": "123456"
}
```

Returns `null` for `code` if no active pairing code exists.

### GET /api/nodes/approved

List all approved companion nodes.

**Response:**
```json
{
  "ok": true,
  "nodes": [
    {
      "nodeId": "node-abc123",
      "name": "My Phone",
      "approvedAt": "2024-01-15T10:00:00Z",
      "sharedSecret": "..."
    }
  ]
}
```

### DELETE /api/nodes/:nodeId/approval

Remove approval for a companion node and disconnect it.

**Response:**
```json
{
  "ok": true,
  "message": "Node approval removed"
}
```

### POST /api/nodes/:nodeId/action

Execute an action on a specific node.

**Request:**
```json
{
  "action": "take_photo",
  "params": {
    "quality": "high"
  },
  "timeout": 30000
}
```

**Response:**
```json
{
  "ok": true,
  "result": {
    "message": "Photo taken successfully",
    "url": "https://..."
  }
}
```

**Error Responses:**
- `404` - Node not found
- `503` - Node is offline
- `504` - Action timed out

---

## Skills

### GET /api/skills

List all available skills with metadata.

**Response:**
```json
{
  "ok": true,
  "skills": [
    {
      "id": "web-research",
      "name": "Web Research",
      "version": "1.0.0",
      "description": "Search the web and summarize findings",
      "triggers": ["research", "search", "find information"],
      "entrypoints": [],
      "requiredPermissions": ["web_access"],
      "enabled": true,
      "path": "/path/to/skills/web-research"
    }
  ]
}
```

### GET /api/skills/:skillId

Get a specific skill's metadata.

### GET /api/skills/:skillId/content

Get the raw SKILL.md content for a skill.

**Response:**
```json
{
  "ok": true,
  "content": "---\nname: Web Research\n..."
}
```

### POST /api/skills/:skillId/toggle

Toggle a skill on or off.

**Request:**
```json
{
  "enabled": false
}
```

**Response:**
```json
{
  "ok": true,
  "enabled": false
}
```

---

## Subagents

Subagent management endpoints. Subagents are specialized AI personalities that can be delegated specific tasks. They can come from three sources: `builtin` (core subagents shipped with AG3NT), `user` (custom subagents defined by the user), and `plugin` (subagents registered by plugins).

### GET /api/subagents

List all registered subagents.

**Response:**
```json
{
  "subagents": [
    {
      "name": "RESEARCHER",
      "description": "Specializes in finding and synthesizing information from various sources",
      "source": "builtin",
      "tools": ["fetch_url", "bing_search"],
      "max_tokens": 8000,
      "priority": 1
    },
    {
      "name": "DEBUGGER",
      "description": "Custom debugging assistant",
      "source": "user",
      "tools": ["execute", "read_file"],
      "max_tokens": 8000,
      "priority": 5
    }
  ],
  "count": 2
}
```

### GET /api/subagents/:name

Get a specific subagent's full configuration.

**Response:**
```json
{
  "ok": true,
  "name": "RESEARCHER",
  "description": "Specializes in finding and synthesizing information from various sources",
  "source": "builtin",
  "tools": ["fetch_url", "bing_search"],
  "max_tokens": 8000,
  "max_turns": 5,
  "thinking_mode": "enabled",
  "system_prompt": "You are a research specialist..."
}
```

### POST /api/subagents

Register a new custom subagent (user-defined).

**Request:**
```json
{
  "name": "DEBUGGER",
  "description": "Specialized debugging assistant for tracking down issues",
  "system_prompt": "You are a debugging specialist...",
  "tools": ["execute", "read_file", "write_file"],
  "max_tokens": 8000,
  "max_turns": 5
}
```

**Response:**
```json
{
  "message": "Subagent 'DEBUGGER' registered successfully",
  "name": "DEBUGGER"
}
```

**Note:** User-defined subagents are persisted to `~/.ag3nt/subagents/{name}.yaml` and automatically loaded on startup.

### DELETE /api/subagents/:name

Unregister a custom subagent. Only user-defined subagents can be deleted.

**Response:**
```json
{
  "message": "Subagent 'DEBUGGER' unregistered successfully",
  "name": "DEBUGGER"
}
```

**Error (attempting to delete builtin):**
```json
{
  "detail": "Cannot delete builtin subagent 'RESEARCHER'"
}
```

---

## Logs

### GET /api/logs/recent

Get recent gateway logs.

**Query Parameters:**
- `count` - Number of logs to return (default: 100)
- `level` - Minimum log level: `debug`, `info`, `warn`, `error`

**Response:**
```json
{
  "ok": true,
  "logs": [
    {
      "id": "log-1",
      "timestamp": "2024-01-15T10:30:00Z",
      "level": "info",
      "source": "Gateway",
      "message": "Channel connected"
    }
  ]
}
```

### POST /api/logs/clear

Clear all logs from the buffer.

---

## Sessions (Additional Endpoints)

### DELETE /api/sessions/:sessionId

Delete a specific session.

**Response:**
```json
{ "ok": true, "message": "Session removed" }
```

### POST /api/sessions/clear

Clear all sessions.

**Response:**
```json
{ "ok": true, "cleared": 5 }
```

---

## Status

### GET /api/status

Get comprehensive agent status.

**Response:**
```json
{
  "ok": true,
  "status": "online",
  "sessions": 3,
  "scheduler": {
    "heartbeatRunning": true,
    "jobCount": 2
  },
  "nodes": {
    "nodeCount": 1,
    "onlineCount": 1
  },
  "channels": [
    { "id": "telegram-main", "type": "telegram", "connected": true }
  ]
}
```

### POST /api/scheduler/heartbeat/trigger

Manually trigger a heartbeat check-in.

**Response:**
```json
{
  "ok": true,
  "result": {
    "ok": true,
    "text": "Agent response...",
    "session_id": "heartbeat:manual:123456"
  }
}
```

---

## Workspace Browser

### GET /api/workspace/files

List all files in the agent's workspace directory.

**Response:**
```json
{
  "ok": true,
  "workspacePath": "/home/user/.ag3nt/workspace",
  "files": [
    {
      "name": "project",
      "path": "project",
      "type": "directory",
      "children": [...]
    },
    {
      "name": "notes.txt",
      "path": "notes.txt",
      "type": "file",
      "size": 1024
    }
  ]
}
```

### GET /api/workspace/file?path=filename.txt

Read a file's content from the workspace.

**Response:**
```json
{
  "ok": true,
  "content": "file content here...",
  "size": 1024
}
```

### GET /api/workspace/download?path=filename.txt

Download a file from the workspace.

---

## Model Configuration

### GET /api/model/config

Get current model provider and model configuration.

**Response:**
```json
{
  "ok": true,
  "provider": "openrouter",
  "model": "moonshotai/kimi-k2-thinking",
  "options": {
    "openrouter": { "name": "OpenRouter", "models": [...] },
    "anthropic": { "name": "Anthropic (Direct)", "models": [...] }
  }
}
```

### POST /api/model/config

Update model configuration (writes to .env file).

**Request:**
```json
{
  "provider": "openrouter",
  "model": "moonshotai/kimi-k2-thinking"
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Model configuration updated. Restart agent to apply."
}
```

---

## Agent Control

### GET /api/agent/health

Check if the agent worker is running.

**Response:**
```json
{
  "ok": true,
  "status": "online",
  "name": "ag3nt-agent"
}
```

### POST /api/agent/restart

Restart the agent worker (opens new terminal window).

**Response:**
```json
{
  "ok": true,
  "message": "Agent worker restart initiated."
}
```

---

## Memory

### GET /api/memory/files

List all memory files (AGENTS.md, MEMORY.md, daily logs).

**Response:**
```json
{
  "ok": true,
  "basePath": "/home/user/.ag3nt",
  "files": [
    {
      "name": "MEMORY.md",
      "path": "MEMORY.md",
      "type": "main",
      "size": 2048,
      "modified": "2024-01-15T10:30:00Z"
    }
  ]
}
```

### GET /api/memory/file?path=MEMORY.md

Read a memory file's content.

**Response:**
```json
{
  "ok": true,
  "content": "# Memory\n...",
  "path": "MEMORY.md",
  "size": 2048,
  "modified": "2024-01-15T10:30:00Z"
}
```

### POST /api/memory/file

Update a memory file.

**Request:**
```json
{
  "path": "MEMORY.md",
  "content": "# Memory\n\nUpdated content..."
}
```

### POST /api/memory/create

Create a new memory file.

**Request:**
```json
{
  "filename": "notes.md",
  "type": "log"
}
```

---

## TUI Control

### POST /api/tui/launch

Launch the TUI in a new terminal window.

**Response:**
```json
{
  "ok": true,
  "message": "TUI launched"
}
```

---

## WebSocket

### WS /ws

Real-time bidirectional communication.

**Connect:** `ws://127.0.0.1:18789/ws`

**Send Message:**
```json
{
  "text": "Hello",
  "session_id": "optional-id"
}
```

**Receive Response:**
```json
{
  "ok": true,
  "session_id": "abc123",
  "text": "Hello! How can I help?",
  "events": []
}
```

### WS /ws?debug=true

Connect for real-time log streaming (Control Panel debug view).

**Received Messages:**
```json
{
  "type": "log",
  "id": "log-123",
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "info",
  "source": "Gateway",
  "message": "Event description"
}
```

---

## Control Panel

The Control Panel UI is served at the root URL: `http://127.0.0.1:18789/`

Features:
- Dashboard with agent status, nodes, and channels
- Live chat interface
- Skills browser with toggle controls
- Real-time debug log viewer
- Scheduler controls (pause/resume heartbeat, trigger manually)

---

## Error Responses

All endpoints return errors in this format:

```json
{
  "ok": false,
  "error": "Error message here"
}
```

Common HTTP status codes:
- `400` - Bad request (missing/invalid parameters)
- `404` - Resource not found
- `500` - Internal server error

