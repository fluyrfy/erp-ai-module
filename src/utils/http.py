"""
HTTP utilities for L3 Agent
"""

import asyncio
from dataclasses import dataclass
import json
import time
import httpx
from typing import Any, Dict, Optional
from src.context import request_token


@dataclass
class HttpResult:
    """統一回傳結構，不拋異常"""

    ok: bool
    status_code: int  # 直接給前端
    data: Any = None  # 成功時的 response body
    message: str = ""  # 錯誤訊息
    duration_ms: int = 0


class HttpError(Exception):
    """統一的 HTTP 錯誤，帶 status_code"""

    def __init__(self, status_code: int, message: str, data: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.data = data


class HttpRequestError(Exception):
    """
    Output type:
      - status_code: int | None
      - payload: dict | Any | None
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        payload: Optional[Any] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload


class HttpTimeoutError(HttpRequestError):
    """HTTP 請求超時"""

    pass


@dataclass
class HttpClientConfig:
    base_url: str
    timeout_s: float = 10.0
    retries: int = 0
    retry_backoff_s: float = 0.3


class HttpClient:
    """
    Output type:
      - success: dict response
      - error: raise HttpRequestError | HttpTimeoutError
    """

    def __init__(self, cfg: HttpClientConfig):
        self.cfg = cfg

    async def request(
        self,
        *,
        method: str,
        path: str,
        query_params: Optional[Dict[str, Any]] = None,
        body: Optional[str] = None,
        token: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        method = method.upper()
        url = f"{self.cfg.base_url.rstrip('/')}/{path.lstrip('/')}"

        headers = headers or {}

        token = request_token.get()
        if token:
            headers["yuntek-auth"] = token

        if body and "content-type" not in {k.lower() for k in headers}:
            headers["Content-Type"] = "application/json"

        for attempt in range(1, self.cfg.retries + 2):  # 1 ~ retries+1

            try:
                async with httpx.AsyncClient(timeout=self.cfg.timeout_s) as client:
                    resp = await client.request(
                        method=method,
                        url=url,
                        params=query_params,
                        content=body,
                        headers=headers,
                    )

                # 統一處理：不管 2xx 還是 4xx/5xx 都走這
                try:
                    data = resp.json()
                except Exception:
                    data = {"raw": resp.text}

                if not resp.is_success:
                    raise HttpError(resp.status_code, f"HTTP {resp.status_code}", data)

                return data

            except httpx.TimeoutException:
                if attempt > self.cfg.retries:
                    raise HttpError(408, f"Timeout after {self.cfg.timeout_s}s")

            except HttpError:
                raise

            except Exception as e:
                if attempt > self.cfg.retries:
                    raise HttpError(0, str(e))

            # Backoff
            await asyncio.sleep(self.cfg.retry_backoff_s * attempt)

        raise HttpError(0, "Unexpected error")

    async def _sleep(self, seconds: float) -> None:
        import asyncio

        await asyncio.sleep(seconds)

    def _has_header(self, headers: Dict[str, str], key: str) -> bool:
        """Output type: bool"""
        key_l = key.lower()
        return any(k.lower() == key_l for k in headers.keys())


def to_error_payload(
    e: Exception, *, method: str, path: str, query: Any, body: Any
) -> Dict[str, Any]:
    """
    Output type: dict (normalized error payload)
    """
    if isinstance(e, HttpRequestError) and isinstance(e.payload, dict):
        payload = e.payload
        payload.setdefault("meta", {})
        payload["meta"].update(
            {"method": method, "path": path, "query": query, "body": body}
        )
        return payload

    if isinstance(e, HttpTimeoutError):
        return {
            "status": "error",
            "code": "HTTP_TIMEOUT",
            "message": e.message,
            "meta": {"method": method, "path": path, "query": query, "body": body},
        }

    return {
        "status": "error",
        "code": "HTTP_ERROR",
        "message": str(e),
        "meta": {"method": method, "path": path, "query": query, "body": body},
    }


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
