"""
L3 Generic Agent
"""

from collections import Counter
import json
from datetime import date
import traceback
from typing import Any

import httpx

from baml_client.types import ApiChoice, HttpRequest, Task
from src.config import config
from src.agent.shared.errors import (
    AgentError,
    AgentException,
    AgentResult,
    ErrorCode,
    DependencyMissingError,
)
from src.utils import execute_http_request
import time
from src.tracing import save_trace

# BAML client (generated)
from baml_client import b
from src.swagger_parser import SwaggerParser
from src.utils.data import extract_value
from src.utils.http import HttpRequestError, HttpTimeoutError


class L3Agent:
    """Generic L3 Agent for any module"""

    def __init__(self, module_name: str):
        """
        Initialize L3 Agent

        Args:
            module_name: Module identifier (e.g., "HR", "Inventory")
        """
        self.module_name = module_name
        # self.language = language or config.DEFAULT_LANGUAGE
        # self.swagger_url = (
        #     f"{self.base_url}{config.SWAGGER_DOC_PATH}/{module_name.lower()}"
        # )

        self.parser: SwaggerParser = SwaggerParser(module_name)

        # Load API doc
        # if api_doc_path is None:
        #     api_doc_path = f"api_docs/{module_name.lower()}.yaml"
        # self.api_doc = self._load_api_doc(api_doc_path)

        print(f"[L3Agent] Module: {module_name}")

    # def _load_api_doc(self, path: str) -> str:
    #     """Load OpenAPI spec from file"""
    #     file_path = Path(path)
    #     if not file_path.exists():
    #         raise FileNotFoundError(f"API doc not found: {path}")
    #     return file_path.read_text(encoding="utf-8")

    async def execute(self, task: Task) -> AgentResult:
        """
        Process user query through the agent pipeline

        Args:
            task: L2 Task

        Returns:
            AgentResult with success/failure and data/error
        """
        start_time = time.time()

        print(f"\n{'='*60}")
        print(f"[Task] {task}")
        print(f"{'='*60}")
        # ─────────────────────────────────────────────────────────
        # Step 0: 載入並解析最新 Swagger spec
        # ─────────────────────────────────────────────────────────
        try:
            await self.parser.load()
        except httpx.HTTPStatusError as e:
            # 404 = module swagger 不存在
            return AgentResult.fail(
                AgentError(
                    code=ErrorCode.INVALID_MODULE,
                    message=f"Failed to load API spec for module '{self.module_name}': HTTP {e.response.status_code}",
                    details={"swagger_url": self.swagger_url},
                )
            )
        except Exception as e:
            return AgentResult.fail(
                AgentError(
                    code=ErrorCode.UNKNOWN_ERROR,
                    message=f"Failed to load Swagger spec from {self.swagger_url}: {e}",
                )
            )

        api_catalog_text = self.parser.get_catalog_text()
        if not api_catalog_text:
            return AgentResult.fail(
                AgentError(code=ErrorCode.NO_API_MATCH, message="Empty API catalog")
            )
        # ─────────────────────────────────────────────────────────
        # Step 1: Select API
        # ─────────────────────────────────────────────────────────
        try:
            selection = b.SelectApi(
                task=task,
                api_doc=api_catalog_text,
                module_context=f"This is the {self.module_name} module.",
            )
        except Exception as e:
            return AgentResult.fail(
                AgentError(
                    code=ErrorCode.UNKNOWN_ERROR, message=f"SelectApi failed: {e}"
                )
            )
        selected_apis = selection.selected_apis
        print(f"[Step 1] Selected {len(selected_apis)} API(s):")
        for api in selected_apis:
            print(
                f"   - {api.api_id} (confidence: {api.confidence:.2f}) - {api.reason}"
            )
        if not selected_apis:
            return AgentResult.fail(
                AgentError(
                    code=ErrorCode.NO_API_MATCH,
                    message="No suitable APIs found",
                )
            )

        # 整體信心門檻（設低一點，因為有多支 API 互補）
        if selection.confidence < config.CONFIDENCE_THRESHOLD:
            return AgentResult.fail(
                AgentError(
                    code=ErrorCode.LOW_CONFIDENCE,
                    message=f"Overall lack of confidence（{selection.confidence:.2f}）, unable to provide a reliable answer",
                    details={"reasoning": selection.reasoning},
                )
            )

        # ─────────────────────────────────────────────────────────
        # Step 2: Generate HTTP Request
        # ─────────────────────────────────────────────────────────
        api_requests: dict[str, tuple[ApiChoice, HttpRequest]] = {}
        for idx, api_choice in enumerate(selected_apis):
            single_spec = self.parser.get_api_by_id(api_choice.api_id)
            if not single_spec:
                return AgentResult.fail(
                    AgentError(
                        code=ErrorCode.UNKNOWN_ERROR,
                        message=f"Can't fine API spec: {api_choice.api_id}",
                    )
                )
            # 生成 http request
            api_spec = json.dumps(single_spec, ensure_ascii=False)
            try:
                http_request = b.GenerateHttpRequest(
                    task=task,
                    api_spec=api_spec,
                    current_date=str(date.today()),
                )

                api_requests[api_choice.api_id] = (api_choice, http_request)
                print(f"[Step 2] Prepared: {api_choice.api_id}")
                print(f"         {http_request.method} {http_request.path}")
                if http_request.query_params:
                    print(f"         Query: {http_request.query_params}")
                if http_request.body and http_request.body != "{}":
                    print(f"         Body: {http_request.body}")
            except Exception as e:
                return AgentResult.fail(
                    AgentError(
                        code=ErrorCode.UNKNOWN_ERROR,
                        message=f"GenerateHttpRequest failed for {api_choice.api_id}: {e}",
                    )
                )

        # ─────────────────────────────────────────────────────────
        # Step 3: Execute HTTP Request(s) in dependency order
        # ─────────────────────────────────────────────────────────
        results: dict[str, Any] = {}  # api_id -> response

        try:
            sorted_apis = self._topological_sort(selection.selected_apis)
        except Exception as e:
            return AgentResult.fail(
                AgentError(
                    code=ErrorCode.UNKNOWN_ERROR, message=f"Dependency error: {e}"
                )
            )

        for api_choice in sorted_apis:
            _, http_request = api_requests[api_choice.api_id]

            # 套用 field_mappings（從前一個 API 取值塞入）
            try:
                final_query_params, final_body = self._apply_field_mappings(
                    http_request=http_request,
                    field_mappings=api_choice.field_mappings,
                    results=results,
                    target_api_spec=single_spec,
                )
                http_request.query_params = (
                    final_query_params if http_request.method == "GET" else {}
                )
                http_request.body = final_body if http_request.method != "GET" else ""

                print(f"[Step 3]  {http_request.method} {http_request.path}")

                # Execution Strategy
                response = None

                # 判斷 BAML 決定的策略
                try:
                    # if http_request.fetch_strategy == FetchStrategy.ALL_PAGES:
                    #     # [策略 A] 全量獲取：呼叫自動分頁 Helper
                    #     response = await execute_with_pagination(
                    #         http_request, self.base_url
                    #     )
                    # else:
                    # [策略 B] 單次獲取：原有的邏輯
                    response = await execute_http_request(
                        base_url=config.BACKEND_BASE_URL,
                        method=http_request.method,
                        path=http_request.path,
                        query_params=http_request.query_params,
                        body=http_request.body,
                    )
                except (HttpRequestError, HttpTimeoutError) as e:
                    results[api_choice.api_id] = {
                        "status": "error",
                        "code": "HTTP_ERROR",
                        "message": e.message,
                    }
                    continue

                if response:
                    records = response.get("data", {}).get("records", [])
                    total = response.get("data", {}).get("count", len(records))

                    # ═══════════════════════════════════════════════════
                    # 護欄：分級截斷（永遠執行）
                    # ═══════════════════════════════════════════════════
                    if len(records) > config.RECORD_LIMIT_TRUNCATE:
                        # 🔴 危險區：資料過大，清空原始資料
                        response["data"]["records"] = []
                        response["data"]["_truncated"] = True
                        response["data"]["_note"] = (
                            f"Dataset too large ({total} records). "
                            f"Cleared raw data. Please narrow your query or use aggregation."
                        )
                        print(f"🛑 [Rejected] {total} records exceeds limit")
                        records = []  # ⭐ 清空，後續 MapReduce 也沒資料可用

                    elif len(records) > config.RECORD_LIMIT_SAFE:
                        # 🟡 警戒區：截斷
                        response["data"]["records"] = records[
                            : config.RECORD_LIMIT_SAFE
                        ]
                        response["data"]["_truncated"] = True
                        response["data"]["_note"] = (
                            f"Truncated: showing first {config.RECORD_LIMIT_SAFE} "
                            f"of {total} records."
                        )
                        print(
                            f"⚠️ [Truncate] {len(records)} → {config.RECORD_LIMIT_SAFE} records"
                        )
                        records = response["data"]["records"]  # 更新為截斷後的

                    # 🟢 安全區：不做任何處理

                    # ═══════════════════════════════════════════════════
                    # MapReduce：聚合統計（只有指定 agg_field 時執行）
                    # ═══════════════════════════════════════════════════
                    # 檢查 BAML 是否指定了聚合欄位 (例如 "lastName")
                    agg_field = getattr(http_request, "aggregation_field", None)
                    if agg_field and records:
                        print(
                            f"🧮 [MapReduce] Aggregating data by field: '{agg_field}'..."
                        )

                        # Python 統計邏輯：取出欄位 -> 計數
                        values = [str(r.get(agg_field, "Unknown")) for r in records]
                        counts = dict(Counter(values))

                        # 排序：數量多的排前面，方便 Summary 閱讀
                        sorted_counts = dict(
                            sorted(
                                counts.items(), key=lambda item: item[1], reverse=True
                            )
                        )

                        print(
                            f"   -> Reduced {len(records)} raw records into {len(sorted_counts)} stats categories."
                        )

                        # 篡改 Response，只保留統計結果，丟棄原始資料以節省 Token
                        response["data"]["records"] = []  # 清空原始資料
                        response["data"]["statistics"] = sorted_counts  # 注入統計結果
                        response["data"][
                            "note"
                        ] = f"Raw data aggregated by Python using field '{agg_field}'."

                # 儲存最終結果 (可能是原始資料，也可能是統計後的資料)
                results[api_choice.api_id] = response
                print(f"✅ Success: {api_choice.api_id}")

            except AgentException as e:
                msg = f"Skipped execution: {str(e)}"
                print(f"⚠️ [Step 3] {msg}")

                # 將這個「跳過」的狀態記下來，傳給 Step 4 的 Summary 看
                results[api_choice.api_id] = e.to_response_dict()

            # 捕捉其他未預期的錯誤
            except Exception as e:
                traceback.print_exc()
                # 真正的程式 bug 才回傳 fail
                return AgentResult.fail(
                    AgentError(
                        code=ErrorCode.UNKNOWN_ERROR,
                        message=f"System Crash at {api_choice.api_id}: {str(e)}",
                    )
                )

        # ─────────────────────────────────────────────────────────
        # Step 4: Generate Summary
        # ─────────────────────────────────────────────────────────
        try:
            summary = b.GenerateSummary(
                task=task,
                api_response=json.dumps(results, ensure_ascii=False),
            )
        except Exception as e:
            save_trace(
                module=self.module_name,
                task=task,
                success=False,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )
            return AgentResult.fail(
                AgentError(
                    code=ErrorCode.UNKNOWN_ERROR, message=f"GenerateSummary failed: {e}"
                )
            )

        summary_json = summary.model_dump_json(indent=config.JSON_INDENT)
        print(f"[Step 4] Summary: {summary_json}")
        return AgentResult.ok(summary_json)

    # def _format_summary(self, summary) -> str:
    #     """Format Summary object for display"""
    #     lines = [f"## {summary.title}", ""]

    #     if summary.key_points:
    #         for point in summary.key_points:
    #             lines.append(f"- {point}")
    #         lines.append("")

    #     if summary.metrics:
    #         lines.append("📊 **Key Metrics:**")
    #         for key, value in summary.metrics.items():
    #             lines.append(f"  - {key}: {value}")
    #         lines.append("")

    #     if summary.recommendation:
    #         lines.append(f"💡 **Recommendation:** {summary.recommendation}")

    #     return "\n".join(lines)

    def _topological_sort(self, apis: list[ApiChoice]) -> list[ApiChoice]:
        """
        根據 depends_on 拓撲排序，確保依賴先執行

        Raises:
            Exception: 發現循環依賴
        """
        result = []
        pending = {api.api_id: api for api in apis}
        completed = set()

        while pending:
            # 找出所有依賴都已完成的 API
            ready = [
                api
                for api in pending.values()
                if all(dep in completed for dep in api.depends_on)
            ]

            if not ready:
                remaining = list(pending.keys())
                raise Exception(f"Circular dependency detected: {remaining}")

            for api in ready:
                result.append(api)
                completed.add(api.api_id)
                del pending[api.api_id]

        return result

    def _apply_field_mappings(
        self,
        http_request: HttpRequest,
        field_mappings: list,
        results: dict[str, Any],
        target_api_spec: dict,
    ) -> tuple[dict[str, str], str]:
        """
        根據 field_mappings 從前一個 API 的結果取值塞入
        """
        # 1. 複製原始參數
        query_params = (
            dict(http_request.query_params) if http_request.query_params else {}
        )

        body_dict = {}
        if http_request.body and http_request.body != "{}":
            try:
                body_dict = json.loads(http_request.body)
            except json.JSONDecodeError:
                pass  # Body 可能不是 JSON，那就無法注入，略過

        # 預先從 target_api_spec 建立參數類型映射
        param_types = {}
        request_body_schema = target_api_spec.get("request_body", {}).get("schema", {})
        if request_body_schema.get("properties"):
            for key, schema in request_body_schema["properties"].items():
                param_types[key] = schema.get("type")

        # 2. 執行 Mapping
        for mapping in field_mappings:
            # --- (A) 取得來源資料 (Source) ---
            source_response = results.get(mapping.from_api)

            # 檢查依賴是否存在
            if source_response is None:
                # 這裡不一定要報錯，因為可能是平行執行的其他支 API 還沒跑
                # 但依據你的架構，depends_on 應該保證了順序，所以這裡是 Error
                raise DependencyMissingError(
                    missing_field="API_RESULT", source_api=mapping.from_api
                )

            # 檢查上游是否失敗
            if (
                isinstance(source_response, dict)
                and source_response.get("status") == "error"
            ):
                print(
                    f"🛑 Dependency Failed: '{mapping.from_api}' failed, skipping mapping."
                )
                continue  # 上游掛了，我們就不填這個參數，試著用預設值跑跑看

            # 提取數值
            value = extract_value(source_response, mapping.from_field)
            if value is None:
                # 取不到值（例如該欄位是 null），通常我們選擇跳過，不硬塞
                print(
                    f"⚠️ Mapping Warning: Extracted None for '{mapping.from_field}' from '{mapping.from_api}'"
                )
                continue

            target_key = mapping.to_param

            # --- (B) 注入目標參數 (Target) ---

            # Case 1: GET Query Params (通常都是字串)
            if http_request.method == "GET":
                query_params[target_key] = str(value)

            # Case 2: POST/PUT Body (結構化資料)
            else:
                # 取得目前該欄位的 "預設值" 或 "現有值"
                # 這很重要，我們透過它來判斷目標是不是一個 List
                current_value = body_dict.get(target_key)
                target_type = param_types.get(target_key, "string")
                if target_type == "array":
                    # 確保是 list
                    if current_value is None:
                        body_dict[target_key] = []
                    elif not isinstance(body_dict[target_key], list):
                        body_dict[target_key] = [body_dict[target_key]]

                    if isinstance(value, list):
                        body_dict[target_key].extend(value)
                    else:
                        body_dict[target_key].append(value)

                else:
                    # scalar 直接覆蓋
                    body_dict[target_key] = value

        # 3. 序列化回字串
        final_body = json.dumps(body_dict, ensure_ascii=False) if body_dict else ""

        return query_params, final_body
