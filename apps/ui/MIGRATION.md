# Migration from Desktop UI to Integrated AG3NT

This UI was previously standalone (AP3X-UI) and has been integrated into AG3NT.

## Changes
- **Location:** Moved from `C:\Users\Guerr\Desktop\UI\AP3X-UI` to `apps/ui`
- **Configuration:** Now uses AG3NT project structure
- **Backend:** Uses ag3nt_agent runtime instead of separate deepagents_cli
- **Gateway:** Proxies to AG3NT gateway at port 18789

## Development Workflow

### Option 1: Full Stack (Recommended)
Use the unified startup script from the project root:
```powershell
.\start.ps1
```

This starts:
- Gateway (port 18789)
- Agent Worker (port 18790)
- Web UI (port 3000)

### Option 2: Manual Start
1. Start AG3NT gateway: `cd apps/gateway && npm run dev`
2. Start AG3NT agent: `cd apps/agent && .venv/Scripts/python -m uvicorn ag3nt_agent.worker:app --port 18790`
3. Start UI: `cd apps/ui && npm run dev`

### Option 3: UI Only (for development)
If gateway and agent are already running:
```bash
cd apps/ui
npm run dev
```

## Configuration
- Environment variables in `apps/ui/.env.local`
- Backend path points to AG3NT project root
- Python path uses AG3NT agent venv

## Key Integration Points

### Daemon (python/deepagents_daemon.py)
- Uses `ag3nt_agent.deepagents_runtime` for agent creation
- Communicates via JSON-RPC over stdio
- Spawned automatically by Next.js API routes

### UI Agent Factory (python/ui_agent_factory.py)
- Wraps ag3nt_agent runtime for UI compatibility
- Provides `create_ui_agent()` function

### Gateway Proxy (app/api/ag3nt/gateway/[...path]/route.ts)
- Proxies API requests to AG3NT gateway
- Preserves query strings and headers

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AG3NT_BACKEND_PATH` | Path to AG3NT backend | `C:\Users\Guerr\Documents\ag3nt` |
| `AG3NT_DAEMON_SCRIPT` | Daemon script path | `python\deepagents_daemon.py` |
| `AG3NT_PYTHON` | Python executable path | `.venv\Scripts\python.exe` |
| `AG3NT_GATEWAY_URL` | Gateway API URL | `http://127.0.0.1:18789` |
| `NEXT_PUBLIC_AG3NT_GATEWAY_URL` | Public gateway URL | `http://127.0.0.1:18789` |
| `PORT` | Next.js dev server port | `3000` |

## Breaking Changes
None - the UI remains fully compatible with the original functionality.
