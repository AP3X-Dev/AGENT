# Kimi (Moonshot AI) Integration Guide

Kimi by Moonshot AI provides powerful language models with large context windows, ideal for processing extensive codebases and long documents.

## Setup

1. **Get an API Key**
   - Visit https://platform.moonshot.cn/
   - Sign up for a Moonshot AI account
   - Create an API key in the console
   - Add credits to your account

2. **Configure Environment Variables**
   ```bash
   export KIMI_API_KEY=your-api-key-here
   export AG3NT_MODEL_PROVIDER=kimi
   export AG3NT_MODEL_NAME=moonshot-v1-128k
   ```

3. **Start the Worker**
   ```bash
   cd apps/agent
   source .venv/bin/activate
   python -m ag3nt_agent.worker
   ```

## Available Models

| Model ID | Context Window | Max Output | Best For |
|----------|----------------|------------|----------|
| `moonshot-v1-128k` | 128,000 tokens | 4,096 tokens | Large codebases, extensive documents |
| `moonshot-v1-32k` | 32,000 tokens | 4,096 tokens | Medium-sized documents, code review |
| `moonshot-v1-8k` | 8,000 tokens | 4,096 tokens | Quick tasks, simple queries |
| `kimi-latest` | 128,000+ tokens | 4,096 tokens | Latest capabilities |

**Recommendation**: Use `moonshot-v1-128k` for most AG3NT tasks to take advantage of the large context window.

## Testing

Run the test script to verify your configuration:

```bash
cd apps/agent
export KIMI_API_KEY=your_key_here
export AG3NT_MODEL_PROVIDER=kimi
export AG3NT_MODEL_NAME=moonshot-v1-128k
python test_kimi.py
```

## Pricing

Kimi uses token-based pricing. Check current rates at: https://platform.moonshot.cn/

Typical pricing (subject to change):
- Input tokens: ~¥0.012 per 1K tokens
- Output tokens: ~¥0.012 per 1K tokens

## Rate Limits

| Plan | RPM (Requests/Min) | TPM (Tokens/Min) |
|------|-------------------|------------------|
| Free Tier | 3 | 32,000 |
| Standard | 60 | 128,000 |
| Pro | 500 | 1,000,000 |

## Troubleshooting

### "KIMI_API_KEY environment variable is required"
- Ensure you've set the environment variable
- Verify the key is correct (no extra spaces or quotes)
- Check that the key hasn't expired

### "401 Unauthorized"
- Verify your API key is valid
- Check that your account has sufficient credits
- Ensure you're using the correct API endpoint

### "429 Rate Limited"
- You've exceeded your plan's rate limits
- Wait a moment before retrying
- Consider upgrading your plan for higher limits

### "Model not found"
- Use exact model IDs: `moonshot-v1-128k`, `moonshot-v1-32k`, `moonshot-v1-8k`
- Check that the model is available in your region
- Verify you have access to the requested model

### Connection Issues
- Verify the base URL is `https://api.moonshot.cn/v1`
- Check your internet connection
- Ensure no firewall is blocking the connection

## Features

### Large Context Windows
Kimi's 128K context window is ideal for:
- Analyzing entire codebases
- Processing long documents
- Maintaining extended conversation history
- Complex multi-step reasoning tasks

### OpenAI-Compatible API
Kimi uses the standard OpenAI chat completions format, making it easy to integrate and switch between providers.

### Chinese Language Support
Kimi has excellent Chinese language capabilities, making it ideal for:
- Chinese documentation
- Bilingual projects
- Chinese-English translation tasks

## Advanced Configuration

### Custom Parameters

To customize model parameters, modify `_create_kimi_model()` in `deepagents_runtime.py`:

```python
return ChatOpenAI(
    model=model_name,
    openai_api_key=api_key,
    openai_api_base="https://api.moonshot.cn/v1",
    temperature=0.7,      # Adjust creativity (0.0-1.0)
    max_tokens=4096,      # Maximum output length
    top_p=0.9,            # Nucleus sampling
)
```

### Streaming Responses

Kimi supports streaming responses. To enable streaming, you'll need to modify the worker to handle streaming:

```python
# Future enhancement - streaming support
stream=True
```

## Comparison with Other Providers

| Feature | Kimi 128K | Claude 3.5 Sonnet | GPT-4o |
|---------|-----------|-------------------|--------|
| Context Window | 128K | 200K | 128K |
| Chinese Support | Excellent | Good | Good |
| Pricing | Low | Medium | Medium |
| Speed | Fast | Fast | Fast |
| Code Generation | Good | Excellent | Excellent |

## Best Practices

1. **Use the 128K model** for complex tasks requiring large context
2. **Monitor token usage** to control costs
3. **Implement retry logic** for rate limit handling
4. **Cache responses** when appropriate to reduce API calls
5. **Use appropriate context** - don't waste tokens on unnecessary information

## Resources

- **Platform**: https://platform.moonshot.cn/
- **Documentation**: https://platform.moonshot.cn/docs
- **API Reference**: https://platform.moonshot.cn/docs/api-reference
- **Pricing**: https://platform.moonshot.cn/pricing
- **Support**: Contact through the platform console

