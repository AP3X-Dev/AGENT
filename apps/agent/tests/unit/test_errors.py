"""Unit tests for AG3NT error system."""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_error_definition_defaults():
    from ag3nt_agent.errors import ErrorDefinition

    ed = ErrorDefinition(code="TEST-001", message="Test error")
    assert ed.code == "TEST-001"
    assert ed.message == "Test error"
    assert ed.http_status == 500
    assert ed.retryable is False


@pytest.mark.unit
def test_error_definition_custom():
    from ag3nt_agent.errors import ErrorDefinition

    ed = ErrorDefinition(code="TEST-002", message="Retry me", http_status=429, retryable=True)
    assert ed.http_status == 429
    assert ed.retryable is True


@pytest.mark.unit
def test_ag3nt_error_basic():
    from ag3nt_agent.errors import AG3NTError

    err = AG3NTError(code="AG-INT-001", message="Internal error")
    assert str(err) == "Internal error"
    assert err.code == "AG-INT-001"
    assert err.http_status == 500
    assert err.retryable is False
    assert err.details == {}


@pytest.mark.unit
def test_ag3nt_error_with_details():
    from ag3nt_agent.errors import AG3NTError

    err = AG3NTError(
        code="AG-TOOL-001",
        message="Tool failed",
        http_status=502,
        retryable=True,
        details={"tool": "exec_command"},
    )
    assert err.retryable is True
    assert err.details == {"tool": "exec_command"}


@pytest.mark.unit
def test_ag3nt_error_to_dict():
    from ag3nt_agent.errors import AG3NTError

    err = AG3NTError(code="AG-API-001", message="LLM error", http_status=502, retryable=True)
    d = err.to_dict()
    assert "error" in d
    assert d["error"]["code"] == "AG-API-001"
    assert d["error"]["message"] == "LLM error"
    assert d["error"]["http_status"] == 502
    assert d["error"]["retryable"] is True
    assert d["error"]["details"] == {}


@pytest.mark.unit
def test_ag3nt_error_is_exception():
    from ag3nt_agent.errors import AG3NTError

    err = AG3NTError(code="X", message="boom")
    assert isinstance(err, Exception)
    with pytest.raises(AG3NTError, match="boom"):
        raise err


@pytest.mark.unit
def test_agent_errors_dict():
    from ag3nt_agent.errors import AGENT_ERRORS

    assert "AG-SKILL-001" in AGENT_ERRORS
    assert "AG-MEM-001" in AGENT_ERRORS
    assert "AG-API-001" in AGENT_ERRORS
    assert "AG-TOOL-001" in AGENT_ERRORS
    assert "AG-INT-001" in AGENT_ERRORS
    assert "AG-TRACE-001" in AGENT_ERRORS


@pytest.mark.unit
def test_error_registry_create_known():
    from ag3nt_agent.errors import ErrorRegistry

    reg = ErrorRegistry()
    err = reg.create_error("AG-SKILL-001")
    assert err.code == "AG-SKILL-001"
    assert str(err) == "Skill not found"
    assert err.http_status == 404


@pytest.mark.unit
def test_error_registry_create_with_details():
    from ag3nt_agent.errors import ErrorRegistry

    reg = ErrorRegistry()
    err = reg.create_error("AG-TOOL-001", details={"tool": "grep"})
    assert err.details == {"tool": "grep"}


@pytest.mark.unit
def test_error_registry_create_unknown():
    from ag3nt_agent.errors import ErrorRegistry

    reg = ErrorRegistry()
    err = reg.create_error("UNKNOWN-999")
    assert err.code == "UNKNOWN-999"
    assert str(err) == "Unknown error"
    assert err.http_status == 500


@pytest.mark.unit
def test_error_registry_get_definition():
    from ag3nt_agent.errors import ErrorRegistry

    reg = ErrorRegistry()
    defn = reg.get_definition("AG-API-002")
    assert defn is not None
    assert defn.retryable is True
    assert defn.http_status == 429


@pytest.mark.unit
def test_error_registry_get_definition_missing():
    from ag3nt_agent.errors import ErrorRegistry

    reg = ErrorRegistry()
    assert reg.get_definition("NOPE") is None


@pytest.mark.unit
def test_error_registry_get_all_definitions():
    from ag3nt_agent.errors import ErrorRegistry

    reg = ErrorRegistry()
    all_defs = reg.get_all_definitions()
    assert len(all_defs) > 10
    assert "AG-SKILL-001" in all_defs


@pytest.mark.unit
def test_error_registry_is_retryable():
    from ag3nt_agent.errors import ErrorRegistry

    reg = ErrorRegistry()
    assert reg.is_retryable("AG-API-001") is True
    assert reg.is_retryable("AG-SKILL-001") is False
    assert reg.is_retryable("NOPE") is False


@pytest.mark.unit
def test_get_error_registry_singleton():
    import ag3nt_agent.errors as mod

    # Reset singleton
    mod._registry = None
    r1 = mod.get_error_registry()
    r2 = mod.get_error_registry()
    assert r1 is r2
    mod._registry = None
