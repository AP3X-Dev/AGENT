# AG3NT

Local-first multi-agent platform built on DeepAgents. Three core services: Gateway (TypeScript/Express), Agent Worker (Python/FastAPI), and Web UI (Next.js).

## Architecture

- **apps/gateway/** — TypeScript HTTP + WebSocket hub. Handles routing, sessions, multi-channel adapters (Telegram, Discord, Slack), plugin system, and inter-service coordination.
- **apps/agent/** — Python FastAPI worker. Runs the DeepAgents runtime with middleware stack (shell, planning, skills, compaction, security, memory). Exposes tools for file ops, browser automation, code search.
- **apps/ui/** — Next.js 15 + React 19 dashboard (AP3X-UI). Uses Radix UI, Tailwind CSS, recharts.
- **vendor/deepagents/** — Vendored DeepAgents library, installed with `pip install -e`.
- **plugins/** — Gateway plugin extensions.
- **skills/** — Agent skills in SKILL.md format.

## Commands

### Gateway (apps/gateway)
```bash
npm ci                          # install
npx tsc --noEmit                # type check
npx vitest run                  # tests
npx vitest run --coverage       # tests with coverage
npm run build                   # compile to dist/
node --watch src/index.ts       # dev server (port 18789)
```

### Agent (apps/agent)
```bash
pip install -r requirements.txt               # install
pytest tests/                                 # all tests
pytest -m unit                                # unit tests only
pytest -m integration                         # integration tests only
pytest tests/ --cov=ag3nt_agent --cov-report=term-missing  # coverage
python -m ag3nt_agent.worker                  # dev server (port 18790)
```

### UI (apps/ui)
```bash
npm install          # install
npm run dev          # dev server (port 3000)
npm run build        # production build
npm run lint         # eslint
```

### Full Stack
```powershell
.\start.ps1                            # start all services
.\start.ps1 -NoBrowser -NoUI           # headless
.\stop.ps1                             # stop all
docker compose up -d                   # docker deployment
```

## Code Style

- **TypeScript:** Strict mode, ES2022 target, ESNext modules. No explicit linter config — rely on `tsc --noEmit` for correctness.
- **Python:** pytest with async support (`asyncio_mode = "auto"`). Markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.e2e`. 30s test timeout.
- **Coverage threshold:** 55% for both gateway and agent.
- **Commits:** Conventional commits required — `feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert` with optional scope `(gateway|agent|skills|ui|api|deps|config)`.

## Key Patterns

- Gateway ↔ Agent communication is HTTP RPC.
- Human-in-the-loop (HITL) approval flow for sensitive operations.
- Session management with `better-sqlite3` for persistence.
- FAISS vector search for semantic memory/codebase retrieval.
- Middleware stack in agent runtime: shell → planning → skill trigger → compaction → security → memory flush.
- Multi-node architecture with device pairing and capability-based routing.

## Environment

Key env vars in `.env` at project root:
- `AG3NT_MODEL_PROVIDER` / `AG3NT_MODEL_NAME` — LLM provider and model
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY` — API keys
- `AG3NT_GATEWAY_PORT` (default 18789), `AG3NT_AGENT_PORT` (default 18790)
- `NEXT_PUBLIC_AG3NT_GATEWAY_URL` — UI → Gateway URL



## MCP Servers

### Augment Context Engine (auggie-mcp)

When you need to understand the codebase — architecture, how a feature works, where

something is implemented, or how components connect — ALWAYS use the codebase-retrieval

MCP tool (auggie-mcp) BEFORE reading files manually. This gives you deep, semantic

understanding of the project that goes beyond simple file search.

Use it for:

- Understanding architecture and code organization

- Finding where specific logic is implemented

- Understanding how systems/modules connect

- Getting context before making changes to unfamiliar areas

- Answering "how does X work?" questions about the codebase

Example queries:

- "How does the authentication system work?"

- "Where is payment processing handled?"

- "What is the architecture of the API layer?"
