"""
HTTP utilities for L3 Agent
"""

import json
import httpx
from typing import Any

from src.agent.errors import AgentError, ErrorCode


def parse_body(body_str: str) -> dict | None:
    """
    Parse JSON body string from LLM output

    Args:
        body_str: JSON string from LLM

    Returns:
        Parsed dict or None if empty/invalid
    """
    if not body_str:
        return None

    body_str = body_str.strip()

    # Empty body cases
    if body_str in ["", "{}", '""', "null", "None"]:
        return None

    try:
        parsed = json.loads(body_str)
        # If parsed to empty dict, return None
        if parsed == {}:
            return None
        return parsed
    except json.JSONDecodeError as e:
        print(f"[Warning] Invalid JSON body: {body_str[:100]}... Error: {e}")
        return None


async def execute_http_request(
    base_url: str,
    method: str,
    path: str,
    query_params: dict[str, str] | None = None,
    body: str = "",
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> tuple[dict[str, Any] | None, AgentError | None]:
    """
    Execute HTTP request to backend service

    Returns:
        Tuple of (response_data, error)
        - On success: (data, None)
        - On failure: (None, AgentError)
    """
    body_data = parse_body(body)

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            response = await client.request(
                method=method.upper(),
                url=path,
                params=query_params if query_params else None,
                json=body_data,
                headers=headers,
            )
            response.raise_for_status()
            return response.json(), None

    except httpx.TimeoutException:
        return None, AgentError(
            code=ErrorCode.TIMEOUT,
            message=f"Request timeout after {timeout}s",
            details={"path": path, "method": method},
        )
    except httpx.HTTPStatusError as e:
        return None, AgentError(
            code=ErrorCode.HTTP_REQUEST_FAILED,
            message=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            details={"path": path, "method": method, "status": e.response.status_code},
        )
    except Exception as e:
        return None, AgentError(
            code=ErrorCode.UNKNOWN_ERROR,
            message=str(e),
            details={"path": path, "method": method},
        )
