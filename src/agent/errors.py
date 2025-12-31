# Error class
"""
Standardized error definitions for L3 Agent
"""
from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class ErrorCode(Enum):
    # API Selection errors
    NO_API_MATCH = "NO_API_MATCH"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"

    # HTTP errors
    HTTP_REQUEST_FAILED = "HTTP_REQUEST_FAILED"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    TIMEOUT = "TIMEOUT"

    # Parsing errors
    INVALID_JSON_BODY = "INVALID_JSON_BODY"

    # General errors
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


@dataclass
class AgentError:
    """Structured error for agent pipeline"""

    code: ErrorCode
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "code": self.code.value,
            "message": self.message,
            "details": self.details,
        }

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"


@dataclass
class AgentResult:
    """Wrapper for agent output - either success or error"""

    success: bool
    data: Any = None
    error: AgentError | None = None

    @classmethod
    def ok(cls, data: Any) -> "AgentResult":
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: AgentError) -> "AgentResult":
        return cls(success=False, error=error)
