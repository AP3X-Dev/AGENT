# Gateway Control Panel

Web-based control panel for AG3NT agent management and debugging.

**URL**: `http://127.0.0.1:18789/`

## Features

### Dashboard
- **Agent Status**: Online/offline, session count, heartbeat status
- **Connected Nodes**: View all registered nodes and their status
- **Channels**: See connected messaging channels (Telegram, Discord, etc.)
- **Scheduler Controls**: Pause/resume heartbeat, view job count

### Chat
- Send messages directly to the agent
- View responses in real-time
- Persistent session within the panel

### Skills Management
- **View All Skills**: Browse bundled skills with metadata
- **Toggle Skills**: Enable/disable skills on the fly
- **Skill Details**: Name, version, description, triggers, permissions

### Nodes Management
- **Pairing Codes**: Generate 6-digit codes to pair companion devices
- **Connected Nodes**: View all registered nodes with status and capabilities
- **Approved Nodes**: Manage paired devices and remove approvals
- **Real-time Status**: See online/offline status and platform information

### Debug Logs
- **Real-time Streaming**: Logs stream via WebSocket
- **Log Levels**: Filter by debug, info, warn, error
- **Auto-scroll**: Toggle auto-scroll for live viewing
- **Clear Logs**: Reset the log buffer

## Technical Details

- Static files served from `apps/gateway/src/ui/public/`
- WebSocket connection at `/ws?debug=true` for log streaming
- API endpoints at `/api/*` (see [API.md](../../API.md))

## See Also

- [TUI Documentation](../../../tui/README.md) - Terminal UI client
- [API Reference](../../API.md) - Full API documentation
