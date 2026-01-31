"""Standardized error codes for AG3NT Agent.

Error code format: [SERVICE]-[CATEGORY]-[CODE]

Services:
- AG: Agent

Categories:
- SKILL: Skill system errors
- MEM: Memory system errors
- API: External API errors (LLM providers)
- TOOL: Tool execution errors
- INT: Internal errors
- TRACE: Tracing/observability errors

This module mirrors the ErrorRegistry in Gateway for consistency.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class ErrorDefinition:
    """Definition of a standardized error code."""
    
    code: str
    message: str
    http_status: int = 500
    retryable: bool = False


class AG3NTError(Exception):
    """Standardized AG3NT error with code and details."""
    
    def __init__(
        self,
        code: str,
        message: str,
        http_status: int = 500,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.retryable = retryable
        self.details = details or {}
    
    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary for API responses."""
        return {
            "error": {
                "code": self.code,
                "message": str(self),
                "http_status": self.http_status,
                "retryable": self.retryable,
                "details": self.details,
            }
        }


# =============================================================================
# Agent Error Definitions
# =============================================================================

AGENT_ERRORS: dict[str, ErrorDefinition] = {
    # Skill errors
    "AG-SKILL-001": ErrorDefinition("AG-SKILL-001", "Skill not found", 404),
    "AG-SKILL-002": ErrorDefinition("AG-SKILL-002", "Skill execution failed", 500),
    "AG-SKILL-003": ErrorDefinition("AG-SKILL-003", "Skill permission denied", 403),
    "AG-SKILL-004": ErrorDefinition("AG-SKILL-004", "Invalid skill definition", 400),
    "AG-SKILL-005": ErrorDefinition("AG-SKILL-005", "Skill timeout", 504, retryable=True),
    
    # Memory errors
    "AG-MEM-001": ErrorDefinition("AG-MEM-001", "Memory search failed", 500),
    "AG-MEM-002": ErrorDefinition("AG-MEM-002", "Memory index not available", 503),
    "AG-MEM-003": ErrorDefinition("AG-MEM-003", "Memory summarization failed", 500),
    "AG-MEM-004": ErrorDefinition("AG-MEM-004", "Vector store initialization failed", 500),
    
    # API/LLM errors
    "AG-API-001": ErrorDefinition("AG-API-001", "LLM API error", 502, retryable=True),
    "AG-API-002": ErrorDefinition("AG-API-002", "LLM rate limited", 429, retryable=True),
    "AG-API-003": ErrorDefinition("AG-API-003", "LLM context length exceeded", 400),
    "AG-API-004": ErrorDefinition("AG-API-004", "Invalid API key", 401),
    "AG-API-005": ErrorDefinition("AG-API-005", "Model not available", 404),
    
    # Tool errors
    "AG-TOOL-001": ErrorDefinition("AG-TOOL-001", "Tool execution failed", 500),
    "AG-TOOL-002": ErrorDefinition("AG-TOOL-002", "Tool not found", 404),
    "AG-TOOL-003": ErrorDefinition("AG-TOOL-003", "Tool approval rejected", 403),
    "AG-TOOL-004": ErrorDefinition("AG-TOOL-004", "Tool timeout", 504, retryable=True),
    "AG-TOOL-005": ErrorDefinition("AG-TOOL-005", "Invalid tool arguments", 400),
    
    # Internal errors
    "AG-INT-001": ErrorDefinition("AG-INT-001", "Internal agent error", 500),
    "AG-INT-002": ErrorDefinition("AG-INT-002", "Configuration error", 500),
    "AG-INT-003": ErrorDefinition("AG-INT-003", "Session not found", 404),
    
    # Tracing errors
    "AG-TRACE-001": ErrorDefinition("AG-TRACE-001", "Tracing configuration error", 500),
}


class ErrorRegistry:
    """Registry for creating and managing standardized errors."""
    
    def __init__(self) -> None:
        self.errors = dict(AGENT_ERRORS)
    
    def create_error(
        self,
        code: str,
        details: dict[str, Any] | None = None,
    ) -> AG3NTError:
        """Create an AG3NT error from a code."""
        definition = self.errors.get(code)
        
        if definition is None:
            return AG3NTError(
                code=code,
                message="Unknown error",
                http_status=500,
                retryable=False,
                details=details,
            )
        
        return AG3NTError(
            code=definition.code,
            message=definition.message,
            http_status=definition.http_status,
            retryable=definition.retryable,
            details=details,
        )
    
    def get_definition(self, code: str) -> ErrorDefinition | None:
        """Get error definition by code."""
        return self.errors.get(code)
    
    def get_all_definitions(self) -> dict[str, ErrorDefinition]:
        """Get all error definitions."""
        return dict(self.errors)
    
    def is_retryable(self, code: str) -> bool:
        """Check if an error is retryable."""
        definition = self.errors.get(code)
        return definition.retryable if definition else False


# Singleton instance
_registry: ErrorRegistry | None = None


def get_error_registry() -> ErrorRegistry:
    """Get the singleton error registry instance."""
    global _registry
    if _registry is None:
        _registry = ErrorRegistry()
    return _registry

