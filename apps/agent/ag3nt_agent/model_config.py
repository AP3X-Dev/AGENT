"""Model configuration and creation for AG3NT.

Extracted from deepagents_runtime.py for maintainability.
Provides model provider detection, configuration, and instance creation.
"""

from __future__ import annotations

import logging
import os

from langchain_core.language_models import BaseChatModel

logger = logging.getLogger("ag3nt.model")

# ---------------------------------------------------------------------------
# Model instance cache – avoids re-creating on every agent rebuild
# ---------------------------------------------------------------------------
_model_cache: dict[str, BaseChatModel] = {}


def get_model_config() -> tuple[str, str]:
    """Get the model provider and name from environment.

    Returns:
        Tuple of (provider, model_name)
    """
    provider = os.environ.get("AG3NT_MODEL_PROVIDER")
    model = os.environ.get("AG3NT_MODEL_NAME")

    if not provider:
        if os.environ.get("OPENROUTER_API_KEY"):
            provider = "openrouter"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        elif os.environ.get("OPENAI_API_KEY"):
            provider = "openai"
        elif os.environ.get("GOOGLE_API_KEY"):
            provider = "google"
        elif os.environ.get("KIMI_API_KEY"):
            provider = "kimi"
        else:
            provider = "anthropic"

    if not model:
        defaults = {
            "openrouter": "moonshotai/kimi-k2.5",
            "anthropic": "claude-sonnet-4-5-20250929",
            "openai": "gpt-4o",
            "google": "gemini-pro",
            "kimi": "kimi-latest",
        }
        model = defaults.get(provider, "claude-sonnet-4-5-20250929")

    return provider, model


def _create_openrouter_model(model_name: str) -> BaseChatModel:
    """Create a ChatOpenAI instance configured for OpenRouter."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY environment variable is required when using OpenRouter. "
            "Get your API key from https://openrouter.ai/keys"
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model_name,
        openai_api_key=api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://github.com/ag3nt",
            "X-Title": "AG3NT",
        },
    )


def _create_kimi_model(model_name: str) -> BaseChatModel:
    """Create a ChatOpenAI instance configured for Kimi (Moonshot AI)."""
    api_key = os.environ.get("KIMI_API_KEY")
    if not api_key:
        raise ValueError(
            "KIMI_API_KEY environment variable is required when using Kimi. "
            "Get your API key from https://platform.moonshot.cn/"
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model_name,
        openai_api_key=api_key,
        openai_api_base="https://api.moonshot.cn/v1",
    )


def create_model(*, use_cache: bool = True) -> BaseChatModel | str:
    """Create the appropriate model instance based on provider.

    Args:
        use_cache: If True (default), return a cached instance when the
                   provider+model combination has been created before.

    Returns:
        Either a BaseChatModel instance (for OpenRouter, Kimi) or a string
        in ``"provider:model"`` format for LangChain's ``init_chat_model()``.
    """
    provider, model_name = get_model_config()
    cache_key = f"{provider}:{model_name}"

    if use_cache and cache_key in _model_cache:
        logger.debug("Returning cached model instance for %s", cache_key)
        return _model_cache[cache_key]

    if provider == "openrouter":
        instance = _create_openrouter_model(model_name)
        _model_cache[cache_key] = instance
        return instance

    if provider == "kimi":
        instance = _create_kimi_model(model_name)
        _model_cache[cache_key] = instance
        return instance

    # For other providers, return "provider:model" string
    return f"{provider}:{model_name}"
