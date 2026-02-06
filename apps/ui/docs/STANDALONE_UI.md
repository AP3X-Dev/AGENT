# Standalone UI (Limited / UI-only)

As of **January 31, 2026**, AP3X-UI defaults to **real AG3NT backend integrations**. Standalone mode is still available for UI-only development, but **backend mocks have been removed**:

- Chat/threads/tools/agents are backed by the **AG3NT DeepAgents daemon** (Python JSON-RPC over stdio).
- MCP Manager reads/writes the **real AG3NT MCP config** at `~/.ag3nt/mcp_servers.json`.

## Quick Start

1. Install dependencies:
   - `npm ci`
2. Run the dev server:
   - `npm run dev`
3. Open:
   - `http://localhost:3000`

### Standalone Mode Toggle

Standalone mode defaults to **OFF**.

- **Standalone (opt-in):** `NEXT_PUBLIC_STANDALONE_UI=true`
- **Real integrations (default):** unset or `NEXT_PUBLIC_STANDALONE_UI=false`

## Notes

### Chat / Threads / Approvals

- `POST /api/chat/stream`
  - Integration: Python daemon JSON-RPC (`python/deepagents_daemon.py`) using `lib/deepagents/daemon-client.ts`
  - Request JSON: `{ threadId?, assistantId?, message, autoApprove?, model?, attachments?, uiContext? }`
  - Response: **SSE stream** emitting `status`, `thread_id`, `text_delta`, `done`, etc.
- `POST /api/chat/resume-stream`
  - Original integration: daemon JSON-RPC stream (`resume_stream`)
  - Request JSON: `{ threadId, assistantId?, interruptId, decision }`
  - Response: SSE stream
- `POST /api/chat`
  - Original integration: daemon JSON-RPC (`chat`)
  - Request JSON: `{ messages, threadId?, assistantId?, autoApprove? }`
  - Response JSON: daemon result object
- `POST /api/approve`
  - Original integration: daemon JSON-RPC (`resume`)
  - Request JSON: `{ threadId, assistantId?, interruptId, decision }`
  - Response JSON: daemon result object
- `POST /api/chat/clear-caches`
  - Original integration: daemon cache control
  - Response JSON: `{ success: true, ... }` (mocked)
- `GET /api/threads?limit=50&agent?=...`
  - Original integration: daemon JSON-RPC (`list_threads`)
  - Response JSON: `{ threads: [{ thread_id, agent_name, updated_at, preview }] }`
- `DELETE /api/threads?id=thread_id`
  - Original integration: daemon JSON-RPC (`delete_thread`)
  - Response JSON: `{ deleted: true, thread_id }`

### MCP Manager

- `GET /api/mcp/servers`
  - Integration: reads `~/.ag3nt/mcp_servers.json`
  - Response JSON: `{ servers: McpServerConfig[] }`
- `POST /api/mcp/servers`
  - Original: `POST {DEEPAGENTS_API_URL}/api/v1/mcp/servers`
  - Request JSON: `Partial<McpServerConfig>`
  - Response JSON: `{ server: McpServerConfig }`
- `GET /api/mcp/servers/:id`
  - Original: `GET {DEEPAGENTS_API_URL}/api/v1/mcp/servers/:id`
  - Response JSON: `{ server: McpServerConfig }`
- `PATCH /api/mcp/servers/:id`
  - Original: `PATCH {DEEPAGENTS_API_URL}/api/v1/mcp/servers/:id`
  - Request JSON: `Partial<McpServerConfig>`
  - Response JSON: `{ server: McpServerConfig }`
- `DELETE /api/mcp/servers/:id`
  - Original: `DELETE {DEEPAGENTS_API_URL}/api/v1/mcp/servers/:id`
  - Response JSON: `{ ok: true }`
- `POST /api/mcp/servers/:id/test`
  - Integration: asks the AG3NT daemon to connect and enumerate tools
  - Response JSON: `{ status, error?, tool_count, tools }`
- `GET /api/mcp/catalog?q?=...`
  - Original: `GET {DEEPAGENTS_API_URL}/api/v1/mcp/catalog`
  - Response JSON: `{ catalog: McpCatalogEntry[] }`
- `POST /api/mcp/catalog`
  - Original: `POST {DEEPAGENTS_API_URL}/api/v1/mcp/catalog/install`
  - Request JSON: `{ catalog_id: string }`
  - Response JSON: `{ ok: true, installed: boolean, server: McpServerConfig }`

### Browser Sessions

- `POST /api/browser/live/start`
  - Original: `POST http://{AGENT_SCRAPER_HOST}:{AGENT_SCRAPER_PORT}/v1/live/start`
  - Request JSON: `{ url: string }`
  - Response JSON: `{ ok: true, sessionId, wsPath }`
- `POST /api/browser/live/stop`
  - Original: `POST http://{AGENT_SCRAPER_HOST}:{AGENT_SCRAPER_PORT}/v1/live/stop`
  - Request JSON: `{ sessionId: string }`
  - Response JSON: `{ ok: true }`

### Image Generation

- `POST /api/generate-image`
  - Original: `POST https://openrouter.ai/api/v1/chat/completions`
  - Auth: `Authorization: Bearer ${OPENROUTER_API_KEY}`
  - Request JSON: `{ model, messages, modalities, image_config }`
  - If `OPENROUTER_API_KEY` is not set, this endpoint returns an error.
