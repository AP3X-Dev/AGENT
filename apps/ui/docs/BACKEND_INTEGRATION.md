# AP3X-UI ↔ AG3NT Backend Integration

AP3X-UI runs the chat UI and spawns the AG3NT DeepAgents daemon (Python) over stdio (newline-delimited JSON-RPC). No UI/UX components were redesigned; only the data layer was wired to the real backend.

## Prerequisites

- Node.js (for AP3X-UI)
- Python (for AG3NT agent runtime)
- The AG3NT repo cloned at `C:\Users\Guerr\Documents\ag3nt` (or set `AG3NT_BACKEND_PATH`)

## AG3NT (Python) setup

From the AG3NT repo:

1) Create/activate the agent venv at `apps/agent/.venv`
2) Install dependencies:
   - `pip install -r apps/agent/requirements.txt`

The daemon script AP3X-UI spawns is:

- `C:\Users\Guerr\Documents\ag3nt\python\deepagents_daemon.py`

## (Optional) AG3NT Gateway setup (Dashboard / Nodes / Logs / Scheduler / Skills / Subagents / Workspace / Memory / Sessions)

The Gateway powers the “Control Panel” features and runs on port **18789** by default.

From `C:\Users\Guerr\Documents\ag3nt\apps\gateway`:

- Install deps: `npm install`
- Run dev gateway: `npm run dev`

AP3X-UI proxies Gateway HTTP endpoints through `app/api/ag3nt/gateway/[...path]/route.ts`.

## AP3X-UI setup

From `C:\Users\Guerr\Desktop\UI\AP3X-UI`:

1) Copy `.env.example` → `.env.local` and adjust paths if needed.
2) Install deps: `npm install`
3) Run: `npm run dev`

## Environment variables

These are supported by the daemon client:

- `AG3NT_BACKEND_PATH` (default: `C:\Users\Guerr\Documents\ag3nt` if present)
- `AG3NT_DAEMON_SCRIPT` (default: `python/deepagents_daemon.py`)
- `AG3NT_PYTHON` (optional; otherwise auto-detected from `apps/agent/.venv`)
- `AG3NT_GATEWAY_URL` (server-side proxy target; default `http://127.0.0.1:18789`)
- `NEXT_PUBLIC_AG3NT_GATEWAY_URL` (client-side WebSocket URL derivation for live logs; default `http://127.0.0.1:18789`)

## Troubleshooting

- **Daemon fails to start**
  - Verify `AG3NT_BACKEND_PATH` points to the AG3NT repo root.
  - Verify `AG3NT_PYTHON` points to a Python with AG3NT deps installed.
  - Try running the daemon directly:
    - `C:\Users\Guerr\Documents\ag3nt\apps\agent\.venv\Scripts\python.exe C:\Users\Guerr\Documents\ag3nt\python\deepagents_daemon.py`

- **Gateway features show errors**
  - Start the Gateway (`npm run dev` in `apps/gateway`) and confirm `http://127.0.0.1:18789/api/health` returns JSON.
  - Ensure `NEXT_PUBLIC_AG3NT_GATEWAY_URL` matches the running host/port.

- **MCP tools not loading**
  - Configure servers in `~/.ag3nt/mcp_servers.json` (AP3X-UI MCP Manager writes here).
  - Ensure `langchain-mcp-adapters` is installed in the AG3NT agent venv.
