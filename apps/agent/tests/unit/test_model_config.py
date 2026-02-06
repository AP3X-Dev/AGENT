"""Unit tests for model_config.py."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the model cache between tests."""
    import ag3nt_agent.model_config as mod
    mod._model_cache.clear()
    yield
    mod._model_cache.clear()


@pytest.mark.unit
def test_get_model_config_explicit_provider():
    with patch.dict(os.environ, {"AG3NT_MODEL_PROVIDER": "openai", "AG3NT_MODEL_NAME": "gpt-4"}, clear=False):
        from ag3nt_agent.model_config import get_model_config
        provider, model = get_model_config()
        assert provider == "openai"
        assert model == "gpt-4"


@pytest.mark.unit
def test_get_model_config_auto_detect_anthropic():
    env = {
        "AG3NT_MODEL_PROVIDER": "",
        "AG3NT_MODEL_NAME": "",
        "ANTHROPIC_API_KEY": "sk-test",
    }
    # Remove other keys that might trigger different provider
    clear_keys = ["OPENROUTER_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "KIMI_API_KEY"]
    with patch.dict(os.environ, env, clear=False):
        for k in clear_keys:
            os.environ.pop(k, None)
        from ag3nt_agent.model_config import get_model_config
        provider, model = get_model_config()
        assert provider == "anthropic"
        assert "claude" in model or "sonnet" in model


@pytest.mark.unit
def test_get_model_config_auto_detect_openrouter():
    env = {
        "AG3NT_MODEL_PROVIDER": "",
        "AG3NT_MODEL_NAME": "",
        "OPENROUTER_API_KEY": "or-test",
    }
    with patch.dict(os.environ, env, clear=False):
        from ag3nt_agent.model_config import get_model_config
        provider, model = get_model_config()
        assert provider == "openrouter"


@pytest.mark.unit
def test_get_model_config_default_model_per_provider():
    with patch.dict(os.environ, {"AG3NT_MODEL_PROVIDER": "google", "AG3NT_MODEL_NAME": ""}, clear=False):
        from ag3nt_agent.model_config import get_model_config
        provider, model = get_model_config()
        assert provider == "google"
        assert model == "gemini-pro"


@pytest.mark.unit
def test_get_model_config_fallback():
    """When no API keys or explicit provider, defaults to anthropic."""
    env = {
        "AG3NT_MODEL_PROVIDER": "",
        "AG3NT_MODEL_NAME": "",
    }
    clear_keys = ["OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "KIMI_API_KEY"]
    with patch.dict(os.environ, env, clear=False):
        for k in clear_keys:
            os.environ.pop(k, None)
        from ag3nt_agent.model_config import get_model_config
        provider, _ = get_model_config()
        assert provider == "anthropic"


@pytest.mark.unit
def test_create_model_returns_string_for_standard_providers():
    with patch.dict(os.environ, {"AG3NT_MODEL_PROVIDER": "anthropic", "AG3NT_MODEL_NAME": "claude-sonnet-4-5-20250929"}, clear=False):
        os.environ.pop("OPENROUTER_API_KEY", None)
        os.environ.pop("KIMI_API_KEY", None)
        from ag3nt_agent.model_config import create_model
        result = create_model(use_cache=False)
        assert isinstance(result, str)
        assert "anthropic:" in result


@pytest.mark.unit
def test_create_model_openrouter_missing_key():
    with patch.dict(os.environ, {"AG3NT_MODEL_PROVIDER": "openrouter", "AG3NT_MODEL_NAME": "test"}, clear=False):
        os.environ.pop("OPENROUTER_API_KEY", None)
        from ag3nt_agent.model_config import create_model
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            create_model(use_cache=False)


@pytest.mark.unit
def test_create_model_kimi_missing_key():
    with patch.dict(os.environ, {"AG3NT_MODEL_PROVIDER": "kimi", "AG3NT_MODEL_NAME": "kimi-latest"}, clear=False):
        os.environ.pop("KIMI_API_KEY", None)
        from ag3nt_agent.model_config import create_model
        with pytest.raises(ValueError, match="KIMI_API_KEY"):
            create_model(use_cache=False)


@pytest.mark.unit
def test_get_model_config_kimi_auto_detect():
    env = {
        "AG3NT_MODEL_PROVIDER": "",
        "AG3NT_MODEL_NAME": "",
        "KIMI_API_KEY": "kimi-test",
    }
    clear_keys = ["OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"]
    with patch.dict(os.environ, env, clear=False):
        for k in clear_keys:
            os.environ.pop(k, None)
        from ag3nt_agent.model_config import get_model_config
        provider, model = get_model_config()
        assert provider == "kimi"
        assert model == "kimi-latest"
