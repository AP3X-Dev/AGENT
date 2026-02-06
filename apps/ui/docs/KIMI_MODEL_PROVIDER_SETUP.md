# Kimi Model Provider Setup for Roo Code

## Overview

Kimi (by Moonshot AI) provides powerful AI models that can be integrated with Roo Code using an OpenAI-compatible API endpoint.

---

## Prerequisites

1. **Kimi API Key** - Get one from [Moonshot AI Platform](https://platform.moonshot.cn/)
2. **Roo Code Extension** - Installed in VS Code

---

## Configuration

### Step 1: Open Roo Code Settings

1. Open VS Code
2. Click the Roo Code icon in the sidebar
3. Click the gear icon (⚙️) to open settings
4. Navigate to **API Configuration** or **Model Providers**

### Step 2: Add Custom Provider

Add a new OpenAI-compatible provider with these settings:

| Setting | Value |
|---------|-------|
| **Provider Name** | `Kimi` or `Moonshot` |
| **Base URL** | `https://api.moonshot.cn/v1` |
| **API Key** | Your Kimi API key |

### Step 3: Required Headers

Kimi requires specific headers for the API requests. Add these custom headers:

```json
{
  "Authorization": "Bearer YOUR_KIMI_API_KEY",
  "Content-Type": "application/json"
}
```

---

## Available Models

| Model ID | Context Window | Best For |
|----------|----------------|----------|
| `moonshot-v1-8k` | 8K tokens | Quick tasks, simple queries |
| `moonshot-v1-32k` | 32K tokens | Medium documents, code review |
| `moonshot-v1-128k` | 128K tokens | Large codebases, long documents |
| `kimi-latest` | 128K+ tokens | Latest capabilities |

---

## Roo Code Configuration File

If using a configuration file (`.roo/config.json` or similar):

```json
{
  "providers": {
    "kimi": {
      "type": "openai-compatible",
      "baseUrl": "https://api.moonshot.cn/v1",
      "apiKey": "${KIMI_API_KEY}",
      "headers": {
        "Authorization": "Bearer ${KIMI_API_KEY}",
        "Content-Type": "application/json"
      },
      "models": [
        {
          "id": "moonshot-v1-128k",
          "displayName": "Kimi 128K",
          "contextWindow": 128000,
          "maxOutputTokens": 4096
        },
        {
          "id": "moonshot-v1-32k",
          "displayName": "Kimi 32K",
          "contextWindow": 32000,
          "maxOutputTokens": 4096
        },
        {
          "id": "moonshot-v1-8k",
          "displayName": "Kimi 8K",
          "contextWindow": 8000,
          "maxOutputTokens": 4096
        }
      ]
    }
  }
}
```

---

## Environment Variables

Set your API key as an environment variable:

**Windows (PowerShell):**
```powershell
$env:KIMI_API_KEY = "your-api-key-here"
```

**Windows (CMD):**
```cmd
set KIMI_API_KEY=your-api-key-here
```

**Linux/macOS:**
```bash
export KIMI_API_KEY="your-api-key-here"
```

**Persistent (add to shell profile):**
```bash
echo 'export KIMI_API_KEY="your-api-key-here"' >> ~/.bashrc
```

---

## API Request Format

Kimi uses OpenAI-compatible chat completions format:

```bash
curl https://api.moonshot.cn/v1/chat/completions \
  -H "Authorization: Bearer $KIMI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "moonshot-v1-128k",
    "messages": [
      {"role": "system", "content": "You are a helpful coding assistant."},
      {"role": "user", "content": "Explain this code..."}
    ],
    "temperature": 0.7,
    "max_tokens": 4096
  }'
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `401 Unauthorized` | Check API key is correct and has credits |
| `429 Rate Limited` | Reduce request frequency or upgrade plan |
| `Connection refused` | Check base URL is `https://api.moonshot.cn/v1` |
| `Model not found` | Use exact model IDs: `moonshot-v1-8k`, `moonshot-v1-32k`, `moonshot-v1-128k` |

---

## Rate Limits

| Plan | RPM (Requests/Min) | TPM (Tokens/Min) |
|------|-------------------|------------------|
| Free | 3 | 32,000 |
| Standard | 60 | 128,000 |
| Pro | 500 | 1,000,000 |

---

## Notes

- Kimi excels at Chinese language tasks but also supports English
- The 128K context model is ideal for large codebase analysis
- Streaming is supported via `"stream": true` parameter

