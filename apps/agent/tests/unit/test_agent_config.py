"""Unit tests for agent_config.py."""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_shell_timeout_default():
    from ag3nt_agent.agent_config import SHELL_TIMEOUT
    assert isinstance(SHELL_TIMEOUT, float)
    assert SHELL_TIMEOUT > 0


@pytest.mark.unit
def test_max_output_bytes_default():
    from ag3nt_agent.agent_config import MAX_OUTPUT_BYTES
    assert isinstance(MAX_OUTPUT_BYTES, int)
    assert MAX_OUTPUT_BYTES > 0


@pytest.mark.unit
def test_gateway_url_default():
    from ag3nt_agent.agent_config import GATEWAY_URL
    assert isinstance(GATEWAY_URL, str)
    assert "127.0.0.1" in GATEWAY_URL or "localhost" in GATEWAY_URL


@pytest.mark.unit
def test_workspace_path():
    from ag3nt_agent.agent_config import WORKSPACE_PATH
    from pathlib import Path
    assert isinstance(WORKSPACE_PATH, Path)
    assert "ag3nt" in str(WORKSPACE_PATH).lower() or ".ag3nt" in str(WORKSPACE_PATH)


@pytest.mark.unit
def test_user_data_path():
    from ag3nt_agent.agent_config import USER_DATA_PATH
    from pathlib import Path
    assert isinstance(USER_DATA_PATH, Path)


@pytest.mark.unit
def test_process_max_age():
    from ag3nt_agent.agent_config import PROCESS_MAX_AGE
    assert isinstance(PROCESS_MAX_AGE, float)
    assert PROCESS_MAX_AGE > 0


@pytest.mark.unit
def test_truncation_constants():
    from ag3nt_agent.agent_config import (
        TRUNCATION_MAX_LINES,
        TRUNCATION_MAX_BYTES,
        TRUNCATION_DIR,
    )
    from pathlib import Path
    assert isinstance(TRUNCATION_MAX_LINES, int)
    assert TRUNCATION_MAX_LINES > 0
    assert isinstance(TRUNCATION_MAX_BYTES, int)
    assert TRUNCATION_MAX_BYTES > 0
    assert isinstance(TRUNCATION_DIR, Path)


@pytest.mark.unit
def test_file_watcher_debounce():
    from ag3nt_agent.agent_config import FILE_WATCHER_DEBOUNCE
    assert isinstance(FILE_WATCHER_DEBOUNCE, float)
    assert FILE_WATCHER_DEBOUNCE > 0
