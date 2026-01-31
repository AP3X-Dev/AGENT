---
name: codebase-navigation
description: Guide to navigating the AG3NT codebase, understanding project structure, and finding key files.
version: "1.0.0"
tags:
  - development
  - navigation
  - codebase
  - structure
triggers:
  - "where is"
  - "project structure"
  - "find the file"
  - "codebase layout"
  - "navigate codebase"
required_permissions: []
license: MIT
compatibility: AG3NT 1.x
metadata:
  author: ag3nt-team
  category: development
---

# Codebase Navigation Guide

Use this skill when you need to find files, understand the project structure, or navigate the AG3NT codebase.

## Top-Level Directory Structure

```
ag3nt/
├── apps/                    # Main application code
│   ├── gateway/             # TypeScript Gateway service
│   └── agent/               # Python Agent Worker service
├── vendor/                  # Vendored dependencies
│   └── deepagents/          # DeepAgents framework (core agent logic)
├── skills/                  # Bundled skills shipped with AG3NT
├── docs/                    # Documentation
├── config/                  # Configuration files and schemas
├── dev-guide/               # Development skills (you are here)
├── start.ps1                # Windows startup script
├── stop.ps1                 # Windows stop script
└── start.sh                 # Unix startup script
```

## Gateway (apps/gateway/)

The Gateway is written in TypeScript and handles:
- HTTP API, WebSocket, and Control Panel UI
- Channel integrations (Telegram, Discord, Slack, CLI)
- Session management and HITL approval flow
- Skills discovery and management

```
apps/gateway/
├── src/
│   ├── gateway/
│   │   ├── createGateway.ts    # Main server setup (HTTP + WS)
│   │   ├── router.ts           # Message routing to agent
│   │   └── middleware.ts       # Express middleware chain
│   ├── channels/
│   │   ├── cli/                # CLI channel adapter
│   │   ├── telegram/           # Telegram bot adapter
│   │   └── discord/            # Discord bot adapter
│   ├── skills/
│   │   ├── SkillManager.ts     # Skill discovery and loading
│   │   └── SkillTrigger*.ts    # Trigger matching middleware
│   ├── session/
│   │   └── SessionManager.ts   # Session lifecycle
│   ├── approval/
│   │   └── ApprovalManager.ts  # HITL approval flow
│   ├── ui/
│   │   ├── public/app.js       # Control Panel frontend JS
│   │   └── views/              # HTML templates
│   ├── logs/
│   │   └── LogBuffer.ts        # Log streaming to UI
│   └── index.ts                # Entry point
├── package.json
└── tsconfig.json
```

## Agent Worker (apps/agent/)

The Agent Worker is written in Python and handles:
- LLM reasoning via DeepAgents framework
- Tool execution (shell, file, web search)
- Memory management and state persistence

```
apps/agent/
├── ag3nt_agent/
│   ├── main.py                 # FastAPI entry point
│   ├── deepagents_runtime.py   # DeepAgents agent builder
│   ├── shell_middleware.py     # Shell execution tool
│   ├── shell_security.py       # Shell command validation
│   ├── file_security.py        # File operation validation
│   ├── audit_logger.py         # Audit trail logging
│   ├── tools/
│   │   └── web_search.py       # Web search tool
│   └── adapters/
│       └── multi_model_*.py    # LLM provider adapters
├── tests/
│   ├── unit/                   # Unit tests
│   └── integration/            # Integration tests
└── pyproject.toml
```

## Key Files Quick Reference

| Need to... | Look in... |
|------------|------------|
| Change HTTP routes | `apps/gateway/src/gateway/createGateway.ts` |
| Modify message routing | `apps/gateway/src/gateway/router.ts` |
| Add a new channel | `apps/gateway/src/channels/` |
| Add a new tool | `apps/agent/ag3nt_agent/tools/` |
| Change LLM behavior | `apps/agent/ag3nt_agent/deepagents_runtime.py` |
| Modify skill loading | `apps/gateway/src/skills/SkillManager.ts` |
| Change Control Panel | `apps/gateway/src/ui/public/app.js` |
| Update configuration | `config/default-config.yaml` |

## Finding Things

1. **Use codebase-retrieval tool** for semantic search:
   ```
   "Where is the function that handles user authentication?"
   ```

2. **Use view tool with regex** for exact matches:
   ```
   view path="apps/gateway/src" search_query_regex="SessionManager"
   ```

3. **Check the docs** for architecture explanations:
   ```
   read_file path="/docs/AG3NT_System_Architecture_and_Design.md"
   ```

## DeepAgents Framework

The vendored DeepAgents framework is at `vendor/deepagents/`. Key modules:

- `deepagents/agent/`: Core agent loop and planning
- `deepagents/middleware/`: Tool middleware (filesystem, shell)
- `deepagents/backends/`: State and storage backends
- `deepagents/reasoning/`: LLM reasoning strategies

