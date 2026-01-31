# OpenRouter Integration Guide

OpenRouter provides a unified API to access multiple LLM providers through a single interface. This is useful for:
- Accessing models without individual API keys for each provider
- Comparing different models easily
- Accessing models that might not have direct API access
- Cost optimization through competitive pricing

## Setup

1. **Get an API Key**
   - Visit https://openrouter.ai/keys
   - Sign up and create an API key
   - Add credits to your account at https://openrouter.ai/credits

2. **Configure Environment Variables**
   ```bash
   export OPENROUTER_API_KEY=sk-or-v1-...
   export AG3NT_MODEL_PROVIDER=openrouter
   export AG3NT_MODEL_NAME=moonshotai/kimi-k2-thinking
   ```

3. **Start the Worker**
   ```bash
   cd apps/agent
   source .venv/bin/activate
   python -m ag3nt_agent.worker
   ```

## Popular Models

### Anthropic Claude
- `anthropic/claude-3.5-sonnet` - Best balance of intelligence and speed
- `anthropic/claude-3-opus` - Most capable, slower
- `anthropic/claude-3-haiku` - Fastest, most affordable

### OpenAI
- `openai/gpt-4o` - Latest GPT-4 Omni
- `openai/gpt-4-turbo` - Fast GPT-4
- `openai/gpt-3.5-turbo` - Fast and affordable

### Google
- `google/gemini-pro-1.5` - Latest Gemini
- `google/gemini-flash-1.5` - Fast Gemini

### Meta Llama
- `meta-llama/llama-3.1-405b-instruct` - Largest open model
- `meta-llama/llama-3.1-70b-instruct` - Good balance
- `meta-llama/llama-3.1-8b-instruct` - Fast and affordable

### Other Providers
- `mistralai/mistral-large`
- `cohere/command-r-plus`
- `perplexity/llama-3.1-sonar-large-128k-online` - With web search

See full list: https://openrouter.ai/models

## Testing

Run the test script to verify your configuration:

```bash
cd apps/agent
export OPENROUTER_API_KEY=your_key_here
export AG3NT_MODEL_PROVIDER=openrouter
export AG3NT_MODEL_NAME=moonshotai/kimi-k2-thinking
python test_openrouter.py
```

## Pricing

OpenRouter charges per token with competitive rates. Check current pricing at:
https://openrouter.ai/models

Most models cost between $0.10 - $15 per million tokens.

## Troubleshooting

### "OPENROUTER_API_KEY environment variable is required"
- Make sure you've set the environment variable
- Check that it starts with `sk-or-v1-`

### "Insufficient credits"
- Add credits at https://openrouter.ai/credits
- Minimum is usually $5

### Model not found
- Check the model name format: `provider/model-name`
- Verify the model exists at https://openrouter.ai/models
- Some models require special access

### Rate limits
- OpenRouter has rate limits per model
- Consider using a different model or adding more credits
- Check your usage at https://openrouter.ai/activity

## Advanced Configuration

### Custom Headers
The integration automatically sets:
- `HTTP-Referer`: For OpenRouter rankings
- `X-Title`: Shows "AG3NT" in rankings

### Model Parameters
To customize temperature, max_tokens, etc., modify `_create_openrouter_model()` in `deepagents_runtime.py`:

```python
return ChatOpenAI(
    model=model_name,
    openai_api_key=api_key,
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=0.7,  # Add custom parameters
    max_tokens=4000,
    default_headers={...},
)
```

## Benefits of OpenRouter

1. **Single API Key**: Access multiple providers without managing separate keys
2. **Fallback Support**: Automatically retry with different providers
3. **Cost Optimization**: Compare prices across providers
4. **Model Discovery**: Try new models without separate integrations
5. **Usage Analytics**: Track usage across all models in one place

