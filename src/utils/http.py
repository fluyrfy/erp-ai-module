"""
HTTP utilities for L3 Agent
"""

import asyncio
import json
import httpx
from typing import Any

from baml_client.types import HttpRequest


class HttpRequestError(Exception):
    """HTTP 請求失敗"""

    def __init__(self, status_code: int | None, message: str, details: dict = None):
        self.status_code = status_code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class HttpTimeoutError(HttpRequestError):
    """HTTP 請求超時"""

    pass


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
) -> dict[str, Any]:
    """
    Execute HTTP request to backend service

    Returns:
        Response data as dict

    Raises:
        HttpTimeoutError: Request timeout
        HttpRequestError: HTTP error or other failures
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
            return response.json()

    except httpx.TimeoutException:
        raise HttpTimeoutError(
            status_code=None,
            message=f"Request timeout after {timeout}s",
            details={"path": path, "method": method},
        )
    except httpx.HTTPStatusError as e:
        raise HttpRequestError(
            status_code=e.response.status_code,
            message=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            details={"path": path, "method": method},
        )
    except Exception as e:
        raise HttpRequestError(
            status_code=None,
            message=str(e),
            details={"path": path, "method": method},
        )


async def execute_multiple_requests(
    base_url: str,
    api_requests: list[tuple[str, HttpRequest]],  # (api_id, http_request)
    sequential: bool = False,
    timeout: float = 30.0,
) -> dict[str, dict]:
    """
    Execute multiple HTTP requests with support for parallel and sequential modes.

    Args:
        base_url: Backend base URL
        api_requests: List of (api_id, HttpRequest) tuples
        sequential: If True, execute in order (for dependencies); if False, execute in parallel
        timeout: Timeout per request in seconds

    Returns:
        Dictionary mapping api_id to response data

    Raises:
        HttpRequestError: If any request fails
    """
    all_responses = {}

    async def _execute_one(api_id: str, http_req: HttpRequest):
        resp_data = await execute_http_request(
            base_url=base_url,
            method=http_req.method,
            path=http_req.path,
            query_params=http_req.query_params or {},
            body=http_req.body,
            headers=http_req.headers or {},
            timeout=timeout,
        )
        return api_id, resp_data

    if sequential:
        for api_id, http_req in api_requests:
            api_id, resp_data = await _execute_one(api_id, http_req)
            all_responses[api_id] = resp_data
    else:
        tasks = [_execute_one(api_id, http_req) for api_id, http_req in api_requests]
        results = await asyncio.gather(*tasks)
        for api_id, resp_data in results:
            all_responses[api_id] = resp_data

    return all_responses


# async def execute_with_pagination(
#     http_request: HttpRequest,
#     base_url: str,
#     page_size: int = 100,
#     max_pages: int = 50,
# ) -> dict[str, Any]:
#     """
#     自動分頁獲取器：當策略為 ALL_PAGES 時，自動跑迴圈把所有資料撈回來。
#     Raises:
#         HttpRequestError: 請求失敗
#     """
#     print(f"🔄 [Auto-Pagination] Strategy: ALL_PAGES triggered for {http_request.path}")

#     # 1. 準備 Request Body (強制設定較大的 PageSize)
#     try:
#         body_json = json.loads(http_request.body) if http_request.body else {}
#     except:
#         body_json = {}

#     # 只有 POST 且是列表查詢類型的 API 才需要處理分頁參數
#     if http_request.method == "POST":
#         # 覆寫 AI 可能給的小數字，設定一個較大但安全的數字 (例如 100)
#         body_json["pageSize"] = page_size
#         body_json["pageNum"] = 1

#     all_records = []
#     total_count = 0
#     current_page = 1

#     while True:
#         # 2. 更新當前頁碼
#         if http_request.method == "POST":
#             body_json["pageNum"] = current_page
#             current_body = json.dumps(body_json)
#         else:
#             # GET 方法暫略，使用原始 body
#             current_body = http_request.body

#         # 3. 執行單次請求
#         response = await execute_http_request(
#             base_url=base_url,
#             method=http_request.method,
#             path=http_request.path,
#             query_params=http_request.query_params,
#             body=current_body,
#         )

#         # 4. 解析標準回應結構
#         data_block = response.get("data", {})
#         if not isinstance(data_block, dict):
#             # 結構不對，可能不是分頁 API，直接回傳單頁結果
#             return response

#         records = data_block.get("records", [])

#         # 第一次請求時，獲取總筆數
#         if current_page == 1:
#             total_count = data_block.get("count", 0)
#             print(f"📊 [Auto-Pagination] Target Total: {total_count} records.")

#         if not records:
#             break

#         all_records.extend(records)
#         print(
#             f"   -> Page {current_page} fetched: {len(records)} items. (Total: {len(all_records)}/{total_count})"
#         )

#         # 5. 終止條件檢查
#         if len(all_records) >= total_count:
#             print("✅ [Auto-Pagination] Complete.")
#             break

#         if current_page >= max_pages:
#             print(
#                 f"⚠️ [Auto-Pagination] Safety limit reached ({max_pages} pages). Stopping."
#             )
#             break

#         current_page += 1

#     # 6. 構造最終的合併回應
#     final_response = {
#         "code": 200,
#         "message": "Auto-Pagination Completed",
#         "data": {"records": all_records, "count": len(all_records)},
#     }
#     return final_response
