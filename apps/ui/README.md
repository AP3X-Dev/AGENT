# AP3X-UI Dashboard

Next.js-based web dashboard for AG3NT multi-agent platform.

## Prerequisites
- AG3NT agent running (apps/agent)
- AG3NT gateway running (apps/gateway) on port 18789

## Quick Start

**Recommended: Use the unified start script from the project root:**
```powershell
# From project root (C:\Users\Guerr\Documents\ag3nt)
.\start.ps1
```

**Manual Start:**
```bash
npm install
npm run dev
```

Access at http://localhost:3000

## Configuration
See `.env.local` or `.env.example` for configuration options.

## Architecture
- **Daemon Communication:** JSON-RPC via stdio (primary)
- **Gateway API:** HTTP proxy to AG3NT Gateway (secondary)
- **Streaming:** Server-Sent Events (SSE) for real-time updates

## Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm start` - Start production server
- `npm run dev:all` - Start UI and browser automation server

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AG3NT_BACKEND_PATH` | Path to AG3NT backend | `C:\Users\Guerr\Documents\ag3nt` |
| `AG3NT_DAEMON_SCRIPT` | Daemon script path | `python\deepagents_daemon.py` |
| `AG3NT_PYTHON` | Python executable path | `.venv\Scripts\python.exe` |
| `AG3NT_GATEWAY_URL` | Gateway API URL | `http://127.0.0.1:18789` |
| `NEXT_PUBLIC_AG3NT_GATEWAY_URL` | Public gateway URL | `http://127.0.0.1:18789` |
| `PORT` | Next.js dev server port | `3000` |

## Docs

- `docs/BACKEND_INTEGRATION.md`
