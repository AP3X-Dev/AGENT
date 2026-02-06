"""Unit tests for node_action_tool.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
def test_get_node_action_tool():
    from ag3nt_agent.node_action_tool import get_node_action_tool
    tool = get_node_action_tool()
    assert tool is not None
    assert tool.name == "execute_node_action"


@pytest.mark.unit
def test_no_node_with_capability():
    from ag3nt_agent.node_action_tool import execute_node_action

    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "hasCapability": False, "nodes": []}
    mock_response.raise_for_status = MagicMock()

    with patch("ag3nt_agent.node_action_tool.httpx.Client") as MockClient:
        ctx = MagicMock()
        ctx.get.return_value = mock_response
        MockClient.return_value.__enter__ = MagicMock(return_value=ctx)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        result = execute_node_action.invoke({
            "capability": "camera",
            "action": "take_photo",
        })
        assert "No node found" in result or "Error" in result


@pytest.mark.unit
def test_empty_nodes_list():
    from ag3nt_agent.node_action_tool import execute_node_action

    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "hasCapability": True, "nodes": []}
    mock_response.raise_for_status = MagicMock()

    with patch("ag3nt_agent.node_action_tool.httpx.Client") as MockClient:
        ctx = MagicMock()
        ctx.get.return_value = mock_response
        MockClient.return_value.__enter__ = MagicMock(return_value=ctx)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        result = execute_node_action.invoke({
            "capability": "camera",
            "action": "take_photo",
        })
        assert "No online nodes" in result


@pytest.mark.unit
def test_success_with_message():
    from ag3nt_agent.node_action_tool import execute_node_action
    import httpx

    # First call: capability lookup
    cap_response = MagicMock()
    cap_response.json.return_value = {
        "ok": True, "hasCapability": True,
        "nodes": [{"id": "n1", "name": "Phone"}],
    }
    cap_response.raise_for_status = MagicMock()

    # Second call: action execution
    action_response = MagicMock()
    action_response.json.return_value = {
        "ok": True, "result": {"message": "Photo taken"},
    }
    action_response.raise_for_status = MagicMock()

    with patch("ag3nt_agent.node_action_tool.httpx.Client") as MockClient:
        ctx = MagicMock()
        ctx.get.return_value = cap_response
        ctx.post.return_value = action_response
        MockClient.return_value.__enter__ = MagicMock(return_value=ctx)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        result = execute_node_action.invoke({
            "capability": "camera",
            "action": "take_photo",
        })
        assert "Photo taken" in result


@pytest.mark.unit
def test_success_with_explicit_node_id():
    from ag3nt_agent.node_action_tool import execute_node_action

    action_response = MagicMock()
    action_response.json.return_value = {
        "ok": True, "result": {"message": "Done"},
    }
    action_response.raise_for_status = MagicMock()

    with patch("ag3nt_agent.node_action_tool.httpx.Client") as MockClient:
        ctx = MagicMock()
        ctx.post.return_value = action_response
        MockClient.return_value.__enter__ = MagicMock(return_value=ctx)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        result = execute_node_action.invoke({
            "capability": "audio",
            "action": "play",
            "node_id": "mynode",
        })
        assert "Done" in result


@pytest.mark.unit
def test_action_error_response():
    from ag3nt_agent.node_action_tool import execute_node_action

    action_response = MagicMock()
    action_response.json.return_value = {
        "ok": False, "error": "Permission denied",
    }
    action_response.raise_for_status = MagicMock()

    with patch("ag3nt_agent.node_action_tool.httpx.Client") as MockClient:
        ctx = MagicMock()
        ctx.post.return_value = action_response
        MockClient.return_value.__enter__ = MagicMock(return_value=ctx)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        result = execute_node_action.invoke({
            "capability": "camera",
            "action": "take_photo",
            "node_id": "n1",
        })
        assert "Permission denied" in result


@pytest.mark.unit
def test_result_with_error_key():
    from ag3nt_agent.node_action_tool import execute_node_action

    action_response = MagicMock()
    action_response.json.return_value = {
        "ok": True, "result": {"error": "Lens blocked"},
    }
    action_response.raise_for_status = MagicMock()

    with patch("ag3nt_agent.node_action_tool.httpx.Client") as MockClient:
        ctx = MagicMock()
        ctx.post.return_value = action_response
        MockClient.return_value.__enter__ = MagicMock(return_value=ctx)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        result = execute_node_action.invoke({
            "capability": "camera",
            "action": "take_photo",
            "node_id": "n1",
        })
        assert "Lens blocked" in result


@pytest.mark.unit
def test_non_dict_result():
    from ag3nt_agent.node_action_tool import execute_node_action

    action_response = MagicMock()
    action_response.json.return_value = {
        "ok": True, "result": "just a string",
    }
    action_response.raise_for_status = MagicMock()

    with patch("ag3nt_agent.node_action_tool.httpx.Client") as MockClient:
        ctx = MagicMock()
        ctx.post.return_value = action_response
        MockClient.return_value.__enter__ = MagicMock(return_value=ctx)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        result = execute_node_action.invoke({
            "capability": "audio",
            "action": "play",
            "node_id": "n1",
        })
        assert "just a string" in result


@pytest.mark.unit
def test_timeout_error():
    from ag3nt_agent.node_action_tool import execute_node_action
    import httpx

    with patch("ag3nt_agent.node_action_tool.httpx.Client") as MockClient:
        ctx = MagicMock()
        ctx.post.side_effect = httpx.TimeoutException("timed out")
        MockClient.return_value.__enter__ = MagicMock(return_value=ctx)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        result = execute_node_action.invoke({
            "capability": "camera",
            "action": "take_photo",
            "node_id": "n1",
        })
        assert "timed out" in result.lower() or "timeout" in result.lower()


@pytest.mark.unit
def test_http_404_error():
    from ag3nt_agent.node_action_tool import execute_node_action
    import httpx

    resp = httpx.Response(404, text="Not found")
    with patch("ag3nt_agent.node_action_tool.httpx.Client") as MockClient:
        ctx = MagicMock()
        ctx.post.side_effect = httpx.HTTPStatusError("404", request=MagicMock(), response=resp)
        MockClient.return_value.__enter__ = MagicMock(return_value=ctx)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        result = execute_node_action.invoke({
            "capability": "camera",
            "action": "take_photo",
            "node_id": "n1",
        })
        assert "not found" in result.lower() or "404" in result


@pytest.mark.unit
def test_http_503_error():
    from ag3nt_agent.node_action_tool import execute_node_action
    import httpx

    resp = httpx.Response(503, text="Unavailable")
    with patch("ag3nt_agent.node_action_tool.httpx.Client") as MockClient:
        ctx = MagicMock()
        ctx.post.side_effect = httpx.HTTPStatusError("503", request=MagicMock(), response=resp)
        MockClient.return_value.__enter__ = MagicMock(return_value=ctx)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        result = execute_node_action.invoke({
            "capability": "camera",
            "action": "take_photo",
            "node_id": "n1",
        })
        assert "offline" in result.lower() or "unavailable" in result.lower()


@pytest.mark.unit
def test_generic_exception():
    from ag3nt_agent.node_action_tool import execute_node_action

    with patch("ag3nt_agent.node_action_tool.httpx.Client") as MockClient:
        ctx = MagicMock()
        ctx.post.side_effect = RuntimeError("connection refused")
        MockClient.return_value.__enter__ = MagicMock(return_value=ctx)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        result = execute_node_action.invoke({
            "capability": "camera",
            "action": "take_photo",
            "node_id": "n1",
        })
        assert "connection refused" in result.lower()


@pytest.mark.unit
def test_dict_result_without_special_keys():
    from ag3nt_agent.node_action_tool import execute_node_action

    action_response = MagicMock()
    action_response.json.return_value = {
        "ok": True, "result": {"data": [1, 2, 3]},
    }
    action_response.raise_for_status = MagicMock()

    with patch("ag3nt_agent.node_action_tool.httpx.Client") as MockClient:
        ctx = MagicMock()
        ctx.post.return_value = action_response
        MockClient.return_value.__enter__ = MagicMock(return_value=ctx)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        result = execute_node_action.invoke({
            "capability": "data",
            "action": "fetch",
            "node_id": "n1",
        })
        assert "completed" in result.lower()
