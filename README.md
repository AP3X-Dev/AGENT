# AG3NT
<img src=".github/images/AG3NT_header.png" alt="AG3NT" width="100%"/>





Local-first personal AI agent platform built on DeepAgents.

## Features

- 🤖 **Multi-Model Support** - Anthropic, OpenAI, OpenRouter, Kimi, Google Gemini
- 🔌 **Multi-Channel** - CLI, TUI, Telegram, Discord adapters
- 🛠️ **Agent Skills** - Modular skill system with SKILL.md format
- 🌐 **Browser Control** - Playwright-based web automation (navigate, screenshot, click, fill)
- 🔒 **Security** - DM pairing, HITL approval for sensitive actions
- ⏰ **Scheduler** - Heartbeat checks and cron-based automation
- 🖥️ **Multi-Node** - Primary + companion device architecture

## Repo Layout

```
ag3nt/
├── apps/
│   ├── gateway/     # Gateway daemon (HTTP + WebSocket + channels)
│   ├── agent/       # Agent worker (DeepAgents runtime)
│   ├── ui/          # Web dashboard (Next.js)
│   └── tui/         # Terminal UI client
├── skills/          # Bundled Agent Skills (SKILL.md format)
├── config/          # Default configuration templates
└── docs/            # Planning documents
```

## 🖥️ Web Dashboard

The AP3X-UI provides a comprehensive web interface for AG3NT:

### Running the UI

**Windows (Unified Script - Recommended):**
```powershell
.\start.ps1
```
This starts Gateway, Agent Worker, and UI together. Access at http://localhost:3000

**Manual Start:**
```bash
# Terminal 1: Start AG3NT Gateway
cd apps/gateway && npm run dev

# Terminal 2: Start AG3NT Agent Worker
cd apps/agent && .venv/Scripts/activate && python -m ag3nt_agent.worker

# Terminal 3: Start UI Dashboard
cd apps/ui && npm run dev
```

Access the dashboard at http://localhost:3000

### UI Features
- Real-time chat with streaming
- Artifact library and management
- Skills and tools browser
- Subagent configuration
- MCP server manager
- Browser automation interface
- System monitoring and logs

## Quick Start

### Windows (One Command)
```powershell
# Start everything: Gateway + Agent + UI
.\start.ps1

# Stop all services
.\stop.ps1
```

### Manual Setup

#### 1. Copy Configuration
```bash
# Create config directory
mkdir -p ~/.ag3nt

# Copy default config
cp config/default-config.yaml ~/.ag3nt/config.yaml
```

#### 2. Start Gateway
```bash
cd apps/gateway
pnpm install
pnpm dev
```
Gateway runs on `http://127.0.0.1:18789`

#### 3. Start Agent Worker
```bash
cd apps/agent
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
python -m ag3nt_agent.worker
```
Worker runs on `http://127.0.0.1:18790`

#### 4. Start Web UI
```bash
cd apps/ui
npm install
npm run dev
```
UI runs on `http://localhost:3000`

#### 5. Start TUI (Optional)
```bash
cd apps/tui
pip install -r requirements.txt
python ag3nt_tui.py
```

## Milestone Status

| Milestone | Status | Description |
|-----------|--------|-------------|
| M1: Core Agent Runtime | ✅ Complete | DeepAgents integration, multi-model support |
| M2: Modular Skill System | ✅ Complete | SKILL.md format, skill discovery, execution runtime, trigger matching |
| M3: Gateway & Multi-Channel | ✅ Complete | HTTP/WS API, Telegram/Discord adapters |
| M4: Planning & Memory | ✅ Complete | TodoListMiddleware, memory persistence |
| M5: Secure Execution | ✅ Complete | HITL approval flow, DM pairing security |
| M6: Scheduling | ✅ Complete | Heartbeat system, cron jobs |
| M7: Multi-Node | ✅ Complete | WebSocket protocol, pairing, capability routing |
| M8: Control Panel | ✅ Complete | Web UI, skill management, debug logs |

### Active Development

See [ROADMAP.md](docs/ROADMAP.md) for detailed sprint planning and current priorities:
- **Core Tools**: Shell execution, web search, git operations
- **Skill Execution**: Runtime for skill entrypoints, MCP integration
- **Testing**: Unit and E2E test coverage

## Documentation

- [Agent Worker](apps/agent/README.md) - Model providers and worker API
- [Web Dashboard](apps/ui/README.md) - Next.js web interface
- [TUI Client](apps/tui/README.md) - Terminal interface usage
- [Gateway API](apps/gateway/API.md) - HTTP/WebSocket API reference
- [Control Panel](apps/gateway/src/ui/README.md) - Web-based control panel
- [Multi-Node Architecture](apps/gateway/src/nodes/README.md) - Companion device support
- [Skills](skills/example-skill/SKILL.md) - Skill format documentation

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AG3NT_MODEL_PROVIDER` | LLM provider (anthropic, openai, openrouter, kimi, google) | `openrouter` |
| `AG3NT_MODEL_NAME` | Model name | `moonshotai/kimi-k2.5` |
| `ANTHROPIC_API_KEY` | Anthropic API key | - |
| `OPENAI_API_KEY` | OpenAI API key | - |
| `OPENROUTER_API_KEY` | OpenRouter API key | - |
| `KIMI_API_KEY` | Kimi/Moonshot API key | - |
| `GOOGLE_API_KEY` | Google Gemini API key | - |

## License

MIT
