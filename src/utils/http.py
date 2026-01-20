"""
HTTP utilities for L3 Agent
"""

import asyncio
from dataclasses import dataclass
import json
import time
import httpx
from typing import Any, Dict, Optional


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

    def _build_headers(
        self, token: Optional[str], extra_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if extra_headers:
            headers.update(extra_headers)
        return headers

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
        url = self.cfg.base_url.rstrip("/") + "/" + path.lstrip("/")

        req_headers = self._build_headers(token, headers)
        if body is not None and not self._has_header(req_headers, "Content-Type"):
            req_headers["Content-Type"] = "application/json"

        attempt = 0
        last_err: Optional[Exception] = None

        while attempt <= self.cfg.retries:
            attempt += 1
            t0 = time.time()
            try:
                async with httpx.AsyncClient(timeout=self.cfg.timeout_s) as client:
                    resp = await client.request(
                        method=method,
                        url=url,
                        params=query_params or None,
                        content=body if body is not None else None,
                        headers=req_headers,
                    )

                duration_ms = int((time.time() - t0) * 1000)

                # 非 2xx：丟 HttpRequestError（帶上 payload/狀態碼）
                if resp.status_code < 200 or resp.status_code >= 300:
                    payload = None
                    try:
                        payload = resp.json()
                    except Exception:
                        payload = resp.text

                    raise HttpRequestError(
                        f"HTTP {resp.status_code}",
                        status_code=resp.status_code,
                        payload={
                            "status": "error",
                            "code": "HTTP_STATUS_ERROR",
                            "message": f"HTTP {resp.status_code}",
                            "meta": {
                                "method": method,
                                "path": path,
                                "url": url,
                                "duration_ms": duration_ms,
                            },
                            "raw": payload,
                        },
                    )

                # 2xx：嘗試 json
                try:
                    data = resp.json()
                except Exception:
                    raise HttpRequestError(
                        "Invalid JSON response",
                        status_code=resp.status_code,
                        payload={
                            "status": "error",
                            "code": "INVALID_JSON",
                            "message": "Response is not valid JSON",
                            "meta": {
                                "method": method,
                                "path": path,
                                "url": url,
                                "duration_ms": duration_ms,
                            },
                            "raw": resp.text,
                        },
                    )

                # 附上 meta（可觀測）
                if isinstance(data, dict):
                    data.setdefault("_meta", {})
                    data["_meta"].update(
                        {
                            "method": method,
                            "path": path,
                            "url": url,
                            "duration_ms": duration_ms,
                        }
                    )
                return data

            except httpx.TimeoutException as e:
                last_err = e
                if attempt > self.cfg.retries:
                    raise HttpTimeoutError(
                        f"Timeout after {self.cfg.timeout_s}s"
                    ) from e

            except HttpRequestError as e:
                last_err = e
                # status error 通常不重試（你可加白名單：502/503/504 才重試）
                raise

            except Exception as e:
                last_err = e
                if attempt > self.cfg.retries:
                    raise HttpRequestError(
                        "Unknown HTTP error",
                        payload={
                            "status": "error",
                            "code": "HTTP_UNKNOWN",
                            "message": str(e),
                        },
                    ) from e

            # backoff
            if attempt <= self.cfg.retries:
                await self._sleep(self.cfg.retry_backoff_s * attempt)

        # 理論上不會到這
        raise HttpRequestError(
            "HTTP failed",
            payload={
                "status": "error",
                "code": "HTTP_FAILED",
                "message": str(last_err),
            },
        )

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
