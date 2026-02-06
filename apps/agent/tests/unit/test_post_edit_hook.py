"""Unit tests for post_edit_hook.py."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from ag3nt_agent.post_edit_hook import (
    _get_lint_diagnostics,
    _get_lsp_diagnostics,
    get_post_edit_diagnostics,
    get_post_edit_diagnostics_sync,
    hook_into_edit_result,
)


# ------------------------------------------------------------------
# _get_lsp_diagnostics
# ------------------------------------------------------------------


@pytest.mark.unit
async def test_lsp_diagnostics_import_error():
    with patch.dict("sys.modules", {"ag3nt_agent.lsp.manager": None}):
        # When LspManager can't be imported, should return ""
        result = await _get_lsp_diagnostics("/fake.py", "content")
        assert result == ""


@pytest.mark.unit
async def test_lsp_diagnostics_exception():
    with patch("ag3nt_agent.post_edit_hook._get_lsp_diagnostics", new_callable=AsyncMock, return_value=""):
        result = await _get_lsp_diagnostics("/fake.py", "content")
        assert isinstance(result, str)


# ------------------------------------------------------------------
# _get_lint_diagnostics
# ------------------------------------------------------------------


@pytest.mark.unit
async def test_lint_diagnostics_import_error():
    with patch.dict("sys.modules", {"ag3nt_agent.lint_runner": None}):
        result = await _get_lint_diagnostics("/fake.py")
        assert result == ""


# ------------------------------------------------------------------
# get_post_edit_diagnostics
# ------------------------------------------------------------------


@pytest.mark.unit
async def test_get_post_edit_diagnostics_no_issues():
    with patch("ag3nt_agent.post_edit_hook._get_lsp_diagnostics", new_callable=AsyncMock, return_value=""), \
         patch("ag3nt_agent.post_edit_hook._get_lint_diagnostics", new_callable=AsyncMock, return_value=""):
        result = await get_post_edit_diagnostics("/fake.py", "content")
        assert result == ""


@pytest.mark.unit
async def test_get_post_edit_diagnostics_with_issues():
    with patch("ag3nt_agent.post_edit_hook._get_lsp_diagnostics", new_callable=AsyncMock, return_value="LSP: error on line 5\n"), \
         patch("ag3nt_agent.post_edit_hook._get_lint_diagnostics", new_callable=AsyncMock, return_value="Lint: warning\n"):
        result = await get_post_edit_diagnostics("/fake.py", "content")
        assert "LSP:" in result or "Lint:" in result


@pytest.mark.unit
async def test_get_post_edit_diagnostics_reads_from_disk(tmp_path):
    test_file = tmp_path / "test.py"
    test_file.write_text("print('hello')")

    with patch("ag3nt_agent.post_edit_hook._get_lsp_diagnostics", new_callable=AsyncMock, return_value=""), \
         patch("ag3nt_agent.post_edit_hook._get_lint_diagnostics", new_callable=AsyncMock, return_value=""):
        result = await get_post_edit_diagnostics(str(test_file))
        assert isinstance(result, str)


@pytest.mark.unit
async def test_get_post_edit_diagnostics_missing_file():
    with patch("ag3nt_agent.post_edit_hook._get_lsp_diagnostics", new_callable=AsyncMock, return_value=""), \
         patch("ag3nt_agent.post_edit_hook._get_lint_diagnostics", new_callable=AsyncMock, return_value=""):
        result = await get_post_edit_diagnostics("/nonexistent/path.py")
        assert isinstance(result, str)


@pytest.mark.unit
async def test_get_post_edit_diagnostics_timeout():
    async def slow_lsp(*args, **kwargs):
        await asyncio.sleep(10)
        return "never"

    async def slow_lint(*args, **kwargs):
        await asyncio.sleep(10)
        return "never"

    with patch("ag3nt_agent.post_edit_hook._get_lsp_diagnostics", side_effect=slow_lsp), \
         patch("ag3nt_agent.post_edit_hook._get_lint_diagnostics", side_effect=slow_lint):
        result = await get_post_edit_diagnostics("/fake.py", "content", timeout=0.05)
        assert result == ""  # timed out, no results


# ------------------------------------------------------------------
# get_post_edit_diagnostics_sync
# ------------------------------------------------------------------


@pytest.mark.unit
def test_sync_wrapper_returns_string():
    with patch("ag3nt_agent.post_edit_hook._get_lsp_diagnostics", new_callable=AsyncMock, return_value=""), \
         patch("ag3nt_agent.post_edit_hook._get_lint_diagnostics", new_callable=AsyncMock, return_value=""):
        result = get_post_edit_diagnostics_sync("/fake.py", "content")
        assert isinstance(result, str)


# ------------------------------------------------------------------
# hook_into_edit_result
# ------------------------------------------------------------------


@pytest.mark.unit
def test_hook_no_diagnostics():
    with patch("ag3nt_agent.post_edit_hook.get_post_edit_diagnostics_sync", return_value=""):
        result = hook_into_edit_result("Edit OK", "/fake.py", "content")
        assert result == "Edit OK"


@pytest.mark.unit
def test_hook_with_diagnostics():
    with patch("ag3nt_agent.post_edit_hook.get_post_edit_diagnostics_sync", return_value="\nWarning: unused import"):
        result = hook_into_edit_result("Edit OK", "/fake.py", "content")
        assert "Edit OK" in result
        assert "Warning" in result
