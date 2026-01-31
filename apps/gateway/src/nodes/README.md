# Multi-Node Architecture

This module implements AG3NT's multi-node architecture, enabling companion devices (phones, tablets, IoT devices) to connect to the primary Gateway and extend the agent's capabilities across multiple devices.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         AG3NT Gateway                        │
│                                                              │
│  ┌──────────────────┐         ┌──────────────────┐         │
│  │  PairingManager  │         │  NodeRegistry    │         │
│  │  - Generate codes│         │  - Track nodes   │         │
│  │  - Validate auth │         │  - Capabilities  │         │
│  └──────────────────┘         └──────────────────┘         │
│           │                            │                     │
│           └────────────┬───────────────┘                     │
│                        │                                     │
│           ┌────────────▼──────────────┐                     │
│           │ NodeConnectionManager     │                     │
│           │ - WebSocket handling      │                     │
│           │ - Heartbeat monitoring    │                     │
│           │ - Action routing          │                     │
│           └────────────┬──────────────┘                     │
│                        │                                     │
│                   /ws/nodes                                  │
└────────────────────────┼──────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
    ┌────▼────┐     ┌────▼────┐    ┌────▼────┐
    │ Mobile  │     │ Tablet  │    │   IoT   │
    │ Device  │     │ Device  │    │ Device  │
    └─────────┘     └─────────┘    └─────────┘
```

## Components

### `protocol.ts`
Defines the WebSocket message protocol for node communication:
- **Message Types**: `register`, `heartbeat`, `action:request`, `action:response`, etc.
- **Type Safety**: Full TypeScript types for all messages
- **Validation**: Message validation functions

### `NodeConnectionManager.ts`
Manages WebSocket connections to companion nodes:
- **Connection Handling**: Accept and manage WebSocket connections
- **Heartbeat Monitoring**: 30-second interval, 90-second timeout
- **Action Routing**: Send actions to nodes and handle responses
- **Timeout Protection**: Configurable timeouts for all actions

### `PairingManager.ts`
Handles authentication and pairing:
- **Pairing Codes**: Generate 6-digit codes with 5-minute expiry
- **Shared Secret**: Fallback authentication for pre-approved devices
- **Approval Tracking**: Persist approved nodes

### `types.ts`
Type definitions for nodes:
- **NodeCapability**: Enum of all supported capabilities
- **NodeInfo**: Node metadata and status
- **NodePlatform**: Platform information (OS, version, arch)

## WebSocket Protocol

### Connection Flow

1. **Client connects** to `ws://gateway:18789/ws/nodes`
2. **Client sends** `register` message with:
   - Node name
   - Capabilities
   - Platform info
   - Auth token (pairing code or shared secret)
3. **Gateway validates** authentication
4. **Gateway sends** `register:ack` with success/failure
5. **Heartbeat loop** begins (every 30 seconds)

### Message Types

#### `register`
Initial registration from companion node.

#### `register:ack`
Acknowledgment from Gateway with success status.

#### `heartbeat` / `heartbeat:ack`
Keep-alive ping/pong (every 30 seconds).

#### `action:request`
Gateway sends action to node for execution.

#### `action:response`
Node returns action result to Gateway.

#### `capability:update`
Node updates its advertised capabilities.

#### `disconnect`
Graceful disconnect notification.

#### `error`
Error message from either side.

## Node Capabilities

Supported capabilities:
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

## Authentication

### Pairing Code Flow
1. User generates pairing code in Control Panel
2. Code is valid for 5 minutes
3. Companion device connects with code
4. Gateway validates and approves node
5. Node is added to approved list

### Shared Secret Flow
For pre-approved devices, a shared secret can be used instead of pairing codes.

## Testing

Use the mock companion node test client:

```bash
cd apps/gateway
npx tsx test/mockCompanionNode.ts [pairing-code]
```

This simulates a companion device with camera, microphone, audio output, notifications, and screen capture capabilities.

## API Endpoints

See [API.md](../../API.md) for full API documentation:
- `POST /api/nodes/pairing/generate` - Generate pairing code
- `GET /api/nodes/pairing/active` - Get active pairing code
- `GET /api/nodes/approved` - List approved nodes
- `DELETE /api/nodes/:nodeId/approval` - Remove node approval
- `POST /api/nodes/:nodeId/action` - Execute action on node

## Agent Integration

The Python agent can execute actions on companion nodes using the `execute_node_action` tool:

```python
execute_node_action(
    capability="camera",
    action="take_photo",
    params={"quality": "high"}
)
```

The tool automatically:
1. Queries NodeRegistry for nodes with the required capability
2. Sends action request via Gateway API
3. Returns result or error with timeout protection

