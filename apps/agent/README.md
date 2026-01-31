# AG3NT Agent Worker

This package hosts the agent runtime and tools bridge.

It is designed to be called by the Gateway via a local RPC protocol.

## Model Provider Configuration

The agent worker supports multiple LLM providers through environment variables:

### Supported Providers

#### OpenRouter (Default)
```bash
export AG3NT_MODEL_PROVIDER=openrouter
export AG3NT_MODEL_NAME=moonshotai/kimi-k2-thinking
export OPENROUTER_API_KEY=your_key_here
```

#### OpenAI
```bash
export AG3NT_MODEL_PROVIDER=openai
export AG3NT_MODEL_NAME=gpt-4o
export OPENAI_API_KEY=your_key_here
```

#### OpenRouter
OpenRouter provides access to multiple models through a unified API:

```bash
export AG3NT_MODEL_PROVIDER=openrouter
export AG3NT_MODEL_NAME=moonshotai/kimi-k2-thinking  # or moonshotai/kimi-k2.5, openai/gpt-4o, etc.
export OPENROUTER_API_KEY=your_key_here
```

Get your OpenRouter API key from: https://openrouter.ai/keys

Popular OpenRouter models:
- `moonshotai/kimi-k2-thinking`
- `moonshotai/kimi-k2.5`
- `anthropic/claude-3.5-sonnet`
- `anthropic/claude-3-opus`
- `openai/gpt-4o`
- `openai/gpt-4-turbo`
- `google/gemini-pro-1.5`
- `meta-llama/llama-3.1-405b-instruct`

See full list at: https://openrouter.ai/models

#### Kimi (Moonshot AI)
Kimi provides powerful models with large context windows:

```bash
export AG3NT_MODEL_PROVIDER=kimi
export AG3NT_MODEL_NAME=moonshot-v1-128k  # or moonshot-v1-32k, moonshot-v1-8k
export KIMI_API_KEY=your_key_here
```

Get your Kimi API key from: https://platform.moonshot.cn/

Available Kimi models:
- `moonshot-v1-128k` - 128K context window (recommended)
- `moonshot-v1-32k` - 32K context window
- `moonshot-v1-8k` - 8K context window
- `kimi-latest` - Latest model version

#### Google Gemini
```bash
export AG3NT_MODEL_PROVIDER=google
export AG3NT_MODEL_NAME=gemini-pro
export GOOGLE_API_KEY=your_key_here
```

## Running the Worker

```bash
cd apps/agent
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m ag3nt_agent.worker
```

The worker will start on `http://127.0.0.1:18790`

## API Endpoints

### Health Check
```
GET /health
```

### Run Turn
```
POST /turn
Content-Type: application/json

{
  "session_id": "unique-session-id",
  "text": "User message here",
  "metadata": {}  // optional
}
```

Response:
```json
{
  "session_id": "unique-session-id",
  "text": "Agent response here",
  "events": [
    {
      "tool_name": "tool_name",
      "input": {},
      "status": "completed"
    }
  ],
  "interrupt": null  // or InterruptInfo if approval required
}
```

### Resume Turn (HITL Approval)
Resume an interrupted turn after user approval/rejection.

```
POST /resume
Content-Type: application/json

{
  "session_id": "unique-session-id",
  "decisions": [
    { "type": "approve" }  // or { "type": "reject" }
  ]
}
```

Response:
```json
{
  "session_id": "unique-session-id",
  "text": "Agent response after approval",
  "events": [...],
  "interrupt": null  // or another InterruptInfo if more approvals needed
}
```

**Note:** The `interrupt` field in responses contains details about pending actions requiring approval. Each decision in the `decisions` array corresponds to one pending action.

## Implementation Status

| Feature | Status | Notes |
|---------|--------|-------|
| DeepAgents integration | ✅ Done | Full agent runtime with planning |
| Multi-model providers | ✅ Done | Anthropic, OpenAI, OpenRouter, Kimi, Google |
| Skills loader bridge | ✅ Done | SKILL.md parsing and indexing |
| Memory persistence | ✅ Done | TodoListMiddleware for task tracking |
| HITL approval flow | ✅ Done | Interrupt/resume for sensitive actions |
| Tool registry | ⏳ Partial | Core tools available, extensible |
| Streaming responses | 📋 Planned | Future enhancement |
| Sub-agents | ✅ Done | Researcher and Coder sub-agents |
