---
name: ag3nt-overview
description: Comprehensive guide to understanding the AG3NT platform vision, architecture, design principles, and core concepts.
version: "1.0.0"
tags:
  - documentation
  - architecture
  - onboarding
  - development
triggers:
  - "what is ag3nt"
  - "explain the architecture"
  - "how does ag3nt work"
  - "platform overview"
  - "design principles"
required_permissions: []
license: MIT
compatibility: AG3NT 1.x
metadata:
  author: ag3nt-team
  category: development
---

# AG3NT Platform Overview

Use this skill when you need to understand what AG3NT is, how it works, and its design philosophy.

## What is AG3NT?

AG3NT is a **personal AI assistant infrastructure** that runs locally, supporting:
- **Multi-channel communication**: CLI, Telegram, Discord, Slack
- **Multi-model LLM backends**: Anthropic Claude, OpenAI, OpenRouter, Kimi, Google Gemini
- **Extensible skill system**: Modular capabilities via SKILL.md files
- **Multi-node architecture**: Control multiple devices from a single agent
- **Human-in-the-loop (HITL)**: Approval workflow for sensitive operations

## Core Architecture (Two-Service Model)

AG3NT uses a **Gateway + Agent Worker** architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│                         AG3NT SYSTEM                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │  Telegram   │    │   Discord   │    │    CLI      │         │
│  │   Channel   │    │   Channel   │    │   Channel   │         │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘         │
│         │                  │                  │                 │
│         └──────────────────┼──────────────────┘                 │
│                           │                                     │
│  ┌────────────────────────▼─────────────────────────────────┐  │
│  │                   GATEWAY (TypeScript/Node.js)           │  │
│  │                      Port: 18789                         │  │
│  │  • HTTP API (/api/*)     • Control Panel UI              │  │
│  │  • WebSocket (/ws)       • Session Management            │  │
│  │  • Skills Discovery      • HITL Approval Flow            │  │
│  └────────────────────────────┬─────────────────────────────┘  │
│                               │                                 │
│  ┌────────────────────────────▼─────────────────────────────┐  │
│  │                AGENT WORKER (Python/FastAPI)             │  │
│  │                      Port: 18790                         │  │
│  │  • DeepAgents Framework   • Multi-Model LLM Support      │  │
│  │  • Tool Execution         • Memory Management            │  │
│  │  • Skill Instructions     • State Persistence            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| **Gateway** | `apps/gateway/` | HTTP/WS server, channels, UI, skills |
| **Agent Worker** | `apps/agent/` | LLM reasoning, tool execution |
| **DeepAgents** | `vendor/deepagents/` | Core agent framework |
| **Skills** | `skills/` | Bundled skills shipped with AG3NT |
| **Config** | `config/` | Default and schema configuration |

## Design Principles

1. **Local-First**: Runs entirely on user's machine, no cloud dependency
2. **Channel-Agnostic**: Same agent works across all communication channels
3. **Security by Default**: HITL approval, DM pairing, path sandboxing
4. **Modular Extensions**: Skills extend capabilities without core changes
5. **Multi-Model**: Provider-agnostic LLM integration

## Virtual Paths

AG3NT uses virtual paths to sandbox file access:

| Virtual Path | Maps To | Purpose |
|--------------|---------|---------|
| `/` | Workspace root | Current project files |
| `/skills/` | Bundled skills dir | Read skill definitions |
| `/user-data/` | `~/.ag3nt/` | User configuration and data |
| `/global-skills/` | `~/.ag3nt/skills/` | User's custom skills |
| `/workspace/` | CWD | Alias for workspace |

## Further Reading

For deeper understanding, refer to these docs (use read_file tool):
- Architecture details: `/docs/AG3NT_System_Architecture_and_Design.md`
- Product requirements: `/docs/AG3NT_Product_Requirements_and_Functional_Requirements.md`
- Configuration options: `/docs/reference/CONFIGURATION.md`
- Skill development: `/docs/guides/SKILL_DEVELOPMENT.md`

