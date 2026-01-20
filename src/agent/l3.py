"""
L3 Generic Agent
"""

import json
import traceback
from typing import (
    Any,
    AsyncGenerator,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
    get_args,
    ForwardRef,
)
import copy

import httpx

from baml_client.types import (
    AggregationTool,
    ApiChoice,
    FieldMapping,
    PostProcessPlan,
    PostProcessStrategy,
    SortingTool,
    Task,
    GetParams,
    BodyParams,
)
from src.agent.shared.types import AgentError, AgentResult, ChunkType, StreamChunk
from src.config import config
from src.agent.shared.errors import (
    AgentException,
    ErrorCode,
    DependencyMissingError,
    PayloadGenerationError,
)
import time

# BAML client (generated)
from baml_client import b
from src.swagger_parser import SwaggerParser
from src.utils.bamler import stream_decision
from src.utils.data import aggregate_records, extract_value, sort_records
from src.utils.http import (
    HttpClient,
    HttpClientConfig,
    HttpRequestError,
    HttpTimeoutError,
    to_error_payload,
)
from src.utils.logging import traced


class L3Agent:
    """Generic L3 Agent for any module"""

    def __init__(self, module_name: str):
        """
        Initialize L3 Agent

        Args:
            module_name: Module identifier (e.g., "HR", "Inventory")
        """
        print(f"[L3Agent] Module: {module_name}")
        self.module_name = module_name
        self.parser: SwaggerParser = SwaggerParser(module_name)
        self.http = HttpClient(
            HttpClientConfig(
                base_url=config.BACKEND_BASE_URL,
                timeout_s=config.HTTP_TIMEOUT_S,
                retries=config.HTTP_RETRIES,
                retry_backoff_s=config.HTTP_RETRY_BACKOFF_S,
            )
        )

    @traced
    async def execute(
        self, task: Task
    ) -> AsyncGenerator[Union[StreamChunk, AgentResult], None]:
        """
        Process user query through the agent pipeline

        Args:
            task: L2 Task

        Returns:
          AsyncGenerator to support thought streaming.
          Yields: StreamChunk (progress) OR AgentResult (final result)
        """

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
            yield AgentResult.fail(
                AgentError(
                    code=ErrorCode.INVALID_MODULE,
                    message=f"Failed to load API spec for module '{self.module_name}': HTTP {e.response.status_code}",
                )
            )
            return
        except Exception as e:
            yield AgentResult.fail(
                AgentError(
                    code=ErrorCode.UNKNOWN_ERROR,
                    message=f"Failed to load Swagger spec : {e}",
                )
            )
            return

        api_catalog_text = self.parser.get_catalog_text()
        if not api_catalog_text:
            yield AgentResult.fail(
                AgentError(code=ErrorCode.NO_API_MATCH, message="Empty API catalog")
            )
            return
        # ─────────────────────────────────────────────────────────
        # Step 1: Select API
        # ─────────────────────────────────────────────────────────
        try:
            postprocess_doc = self._get_postprocess_doc()

            async for item in self._select_api(
                task=task, api_doc=api_catalog_text, postprocess_doc=postprocess_doc
            ):
                if isinstance(item, StreamChunk):
                    yield item
                else:
                    selection = item
        except Exception as e:
            yield AgentResult.fail(
                AgentError(
                    code=ErrorCode.UNKNOWN_ERROR, message=f"SelectApi failed: {e}"
                )
            )
            return

        if not selection:
            yield AgentResult.fail(
                AgentError(
                    code=ErrorCode.NO_API_MATCH,
                    message="No suitable APIs found",
                )
            )
            return

        print(f"[Step 1] Selected {len(selection.selected_apis)} API(s):")

        # 整體信心門檻（設低一點，因為有多支 API 互補）
        if selection.decision.confidence < config.CONFIDENCE_THRESHOLD:
            yield AgentResult.fail(
                AgentError(
                    code=ErrorCode.LOW_CONFIDENCE,
                    message=f"Overall lack of confidence（{selection.decision.confidence:.2f}）, unable to provide a reliable answer",
                    details={"reasoning": selection.decision.reason},
                )
            )
            return

        # ─────────────────────────────────────────────────────────
        # Step 2: Generate HTTP Request
        # ─────────────────────────────────────────────────────────
        api_plans: dict[str, Any] = {}
        selected_apis = selection.selected_apis
        for api_choice in selected_apis:
            single_spec = self.parser.get_api_by_id(api_choice.api_id)
            if not single_spec:
                yield AgentResult.fail(
                    AgentError(
                        code=ErrorCode.UNKNOWN_ERROR,
                        message=f"Can't fine API spec: {api_choice.api_id}",
                    )
                )
                return
            # A. 從 Swagger 獲取 Metadata
            method = single_spec.get("method", "GET").upper()

            try:
                ai_payload = self._build_ai_payload(
                    task=task,
                    method=method,
                    single_spec=single_spec,
                    api_choice=api_choice,
                )
                api_plans[api_choice.call_id] = {
                    "choice": api_choice,
                    "payload": ai_payload,  # 這是 GetParams 或 BodyParams
                    "spec": single_spec,
                    "method": method,  # 記住這些 meta info
                    "path": single_spec.get("path"),
                    "error": None,
                }

                print(f"[Step 2] Prepared Payload for: {api_choice.call_id}")

            except Exception as e:
                ex = PayloadGenerationError(
                    call_id=api_choice.call_id,
                    api_id=api_choice.api_id,
                    reason=str(e),
                )
                api_plans[api_choice.call_id] = {
                    "choice": api_choice,
                    "payload": None,
                    "spec": single_spec,
                    "method": method,
                    "path": path,
                    "error": ex,
                }
                print(f"⚠️ [Step 2] {ex}")

        # ─────────────────────────────────────────────────────────
        # Step 3: Execute HTTP Request(s) in dependency order
        # ─────────────────────────────────────────────────────────
        # 軌道 1: 執行用 (Raw Data) - 給下一支 API 查依賴用
        execution_buffer: dict[str, Any] = {}

        # 軌道 2: 報告用 (Processed Data) - 給 Summary Agent 用
        summary_buffer: dict[str, Any] = {}
        # results: dict[str, Any] = {}  # api_id -> response

        try:
            sorted_apis = self._topological_sort(selection.selected_apis)
        except Exception as e:
            yield AgentResult.fail(
                AgentError(
                    code=ErrorCode.UNKNOWN_ERROR, message=f"Dependency error: {e}"
                )
            )
            return

        for api_choice in sorted_apis:
            plan = api_plans.get(api_choice.call_id)
            if not plan:
                ex = AgentException(
                    code=ErrorCode.GEN_INVALID_SCHEMA,
                    message=f"Missing plan for call '{api_choice.call_id}'",
                    details={
                        "call_id": api_choice.call_id,
                        "api_id": api_choice.api_id,
                    },
                )
                err_payload = ex.to_response_dict()
                execution_buffer[api_choice.call_id] = err_payload
                summary_buffer[api_choice.call_id] = err_payload
                continue
            err = plan.get("error")
            if err:
                if hasattr(err, "to_response_dict"):
                    err_payload = err.to_response_dict()
                else:
                    err_payload = {
                        "status": "error",
                        "code": ErrorCode.GEN_INVALID_SCHEMA.value,
                        "message": str(err),
                        "details": {
                            "call_id": api_choice.call_id,
                            "api_id": api_choice.api_id,
                        },
                        "data": {},
                    }
                execution_buffer[api_choice.call_id] = err_payload
                summary_buffer[api_choice.call_id] = err_payload
                continue
            method = plan["method"]
            path = plan["path"]
            ai_payload = plan["payload"]  # GetParams | BodyParams
            target_spec = plan["spec"]

            # A. 提取依賴資料 (只負責產出 dict)
            # 這是新的 Helper，下面會定義
            injected_data = self._resolve_dependencies(
                field_mappings=api_choice.field_mappings,
                results=execution_buffer,
                target_api_spec=target_spec,
                method=method,
            )

            # B. 合併資料 (Merge)
            final_query = {}
            final_body = None

            if ai_payload is None:
                # 沒有要讓 LLM 生成的欄位，完全靠 injected_data
                if method == "GET":
                    final_query = dict(injected_data)
                else:
                    final_body = json.dumps(dict(injected_data), ensure_ascii=False)

            elif isinstance(ai_payload, GetParams):
                final_query = dict(ai_payload.query_params)
                final_query.update(injected_data)

            elif isinstance(ai_payload, BodyParams):
                try:
                    body_dict = json.loads(ai_payload.body) if ai_payload.body else {}
                except:
                    body_dict = {}

                # 強制覆蓋
                body_dict.update(injected_data)
                final_body = json.dumps(body_dict, ensure_ascii=False)

            yield StreamChunk.thought(api_choice)

            try:
                print(f"[Step 3]  {method} {path}")
                # Execution Strategy
                response = None
                # 判斷 BAML 決定的策略
                try:
                    response = await self.http.request(
                        method=method,
                        path=path,
                        query_params=final_query,
                        body=final_body,
                    )
                except (HttpRequestError, HttpTimeoutError) as e:
                    err_payload = to_error_payload(
                        e, method=method, path=path, query=final_query, body=final_body
                    )
                    execution_buffer[api_choice.call_id] = err_payload
                    summary_buffer[api_choice.call_id] = err_payload
                    continue

                if response is None:
                    err_payload = {
                        "status": "error",
                        "code": "NO_RESPONSE",
                        "message": "No response",
                    }
                    execution_buffer[api_choice.call_id] = err_payload
                    summary_buffer[api_choice.call_id] = err_payload
                    continue

                execution_buffer[api_choice.call_id] = response

                # 契約護欄：非 dict 或缺 data → 視為 malformed（不是 NO_DATA）
                if (
                    (not isinstance(response, dict))
                    or ("data" not in response)
                    or (not isinstance(response.get("data"), dict))
                ):
                    err_payload = {
                        "status": "error",
                        "code": "MALFORMED_RESPONSE",
                        "message": "Response missing expected 'data' object",
                        "raw": response,  # 可選：你要不要留原始
                    }
                    execution_buffer[api_choice.call_id] = err_payload
                    summary_buffer[api_choice.call_id] = err_payload
                    continue

                raw_records = response.get("data", {}).get("records", [])
                total_raw_count = response.get("data", {}).get(
                    "count", len(raw_records)
                )

                # 複製一份出來加工 (Response 軌道)
                processed_response = copy.deepcopy(response)

                # A. Post-Process
                post_plan: Optional[PostProcessPlan] = getattr(
                    api_choice, "postprocess", None
                )
                if post_plan and raw_records:
                    try:
                        final_records, stats = self._execute_post_process(
                            raw_records, post_plan
                        )
                        processed_response["data"]["records"] = final_records
                    except Exception as e:
                        print(f"⚠️ Post-process failed: {e}. Fallback to raw data.")

                # B. Truncate
                current_records = processed_response["data"].get("records", [])
                total_len = len(current_records)

                if total_len > config.RECORD_LIMIT_TRUNCATE:
                    processed_response["data"]["records"] = []
                    processed_response["data"]["_truncated"] = True
                    processed_response["data"]["_note"] = (
                        f"Dataset too large ({total_len} records). "
                        f"Cleared raw data. Please narrow your query or use aggregation."
                    )
                    print(f"🛑 [Rejected] {total_len} records exceeds limit")

                elif total_len > config.RECORD_LIMIT_SAFE:
                    processed_response["data"]["records"] = current_records[
                        : config.RECORD_LIMIT_SAFE
                    ]
                    processed_response["data"]["_truncated"] = True
                    processed_response["data"][
                        "_note"
                    ] = f"Truncated: showing first {config.RECORD_LIMIT_SAFE} of {total_raw_count} records."
                    print(
                        f"⚠️ [Truncate] {total_len} → {config.RECORD_LIMIT_SAFE} records"
                    )

                # 最終一定要寫入 summary_buffer
                summary_buffer[api_choice.call_id] = processed_response
                print(f"✅ Success: {api_choice.call_id}")

            except AgentException as e:
                msg = f"Skipped execution: {str(e)}"
                print(f"⚠️ [Step 3] {msg}")

                # 將這個「跳過」的狀態記下來，傳給 Step 4 的 Summary 看
                summary_buffer[api_choice.call_id] = e.to_response_dict()

            # 捕捉其他未預期的錯誤
            except Exception as e:
                traceback.print_exc()
                # 真正的程式 bug 才回傳 fail
                yield AgentResult.fail(
                    AgentError(
                        code=ErrorCode.UNKNOWN_ERROR,
                        message=f"System Crash at {api_choice.call_id}: {str(e)}",
                    )
                )
                return

        # ─────────────────────────────────────────────────────────
        # Step 4: Generate Summary
        # ─────────────────────────────────────────────────────────
        try:
            api_response = json.dumps(summary_buffer, ensure_ascii=False)
            summary = self._generate_summary(task, api_response)
        except Exception as e:
            yield AgentResult.fail(
                AgentError(
                    code=ErrorCode.UNKNOWN_ERROR, message=f"GenerateSummary failed: {e}"
                )
            )
            return

        summary_dict = summary.model_dump()  # Output type: dict

        summary_json = summary.model_dump_json(indent=config.JSON_INDENT)
        print(f"[Step 4] Summary: {summary_json}")
        yield AgentResult.ok(summary_dict)

    # === Tool Method ===
    @traced
    def _generate_summary(self, task, api_response):
        summary = b.GenerateSummary(
            task=task,
            api_response=api_response,
        )
        return summary

    @traced
    async def _select_api(self, task, api_doc, postprocess_doc):
        stream = b.stream.SelectApi(
            task=task,
            api_doc=api_doc,
            module_context=f"This is the {self.module_name} module.",
            postprocess_doc=postprocess_doc,
        )
        async for item in stream_decision(stream):
            yield item

    def _resolve_dependencies(
        self,
        field_mappings: list[FieldMapping],
        results: dict[str, Any],
        target_api_spec: dict,
        method: str,
    ) -> dict[str, Any]:
        """
        提取依賴資料，並根據目標 API 的定義進行型別轉換 (Auto-boxing)
        Returns:
            dict: { "departmentId": 2, "ids": [10, 20] }
        """
        injected_data = {}

        # 預先解析目標 API 的參數型別 (為了處理 array auto-boxing)
        param_types = {}
        if method == "GET":
            # GET param types
            for p in target_api_spec.get("parameters", []):
                param_types[p["name"]] = p.get("schema", {}).get("type")
        else:
            # POST body types
            schema = target_api_spec.get("request_body", {}).get("schema", {})
            param_types = {
                k: v.get("type") for k, v in schema.get("properties", {}).items()
            }

        for mapping in field_mappings:
            # 1. 取得來源 Response
            source_response = results.get(mapping.from_call)
            if not source_response or source_response.get("status") == "error":
                print(f"⚠️ Dependency missing/failed: {mapping.from_call}")
                continue

            # 2. 提取數值
            value = extract_value(source_response, mapping.from_field)
            if value is None:
                continue

            target_key = mapping.to_param
            target_type = param_types.get(target_key, "string")

            # 3. 型別適配 (Auto-boxing)
            # 如果目標是 array，但我們拿到的是單值，幫它包成 list
            if target_type == "array" and not isinstance(value, list):
                value = [value]

            # 4. 存入字典
            # 這裡處理了 "同一個 key 多次 mapping" 的情況 (例如多個來源合併成一個 list)
            if target_key in injected_data:
                if isinstance(injected_data[target_key], list):
                    if isinstance(value, list):
                        injected_data[target_key].extend(value)
                    else:
                        injected_data[target_key].append(value)
                else:
                    # 原本是單值，現在變成 list
                    injected_data[target_key] = [injected_data[target_key], value]
            else:
                injected_data[target_key] = value

        return injected_data

    def _topological_sort(self, apis: list[ApiChoice]) -> list[ApiChoice]:
        """
        根據 depends_on 拓撲排序，確保依賴先執行

        Raises:
            Exception: 發現循環依賴
        """
        result = []
        pending = {api.call_id: api for api in apis}
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
                completed.add(api.call_id)
                del pending[api.call_id]

        return result

    @traced
    def _get_postprocess_doc(self) -> str:
        """
        動態提取 PostProcessStrategy 包含的所有 Tool Schema
        """
        # 自動從 Union Type 抓出 [AggregationTool, SortingTool]
        # 如果你在 BAML 加了新 Tool，這裡會自動抓到，完全不用改 code
        raw_args = get_args(PostProcessStrategy)

        # 解析 ForwardRef
        resolved_classes = []
        for arg in raw_args:
            if isinstance(arg, ForwardRef):
                # 方法 1：從 baml_client.types 模組中取得實際 class
                from baml_client import types as baml_types

                class_name = arg.__forward_arg__
                resolved_class = getattr(baml_types, class_name, None)
                if resolved_class:
                    resolved_classes.append(resolved_class)
            else:
                resolved_classes.append(arg)

        schema_map = {}
        for tool in resolved_classes:
            if hasattr(tool, "model_json_schema"):
                raw_schema = tool.model_json_schema()
                schema_map[tool.__name__] = {
                    "description": raw_schema.get("description", ""),
                    "properties": raw_schema.get("properties", {}),
                }

        return json.dumps(schema_map, ensure_ascii=False, indent=config.JSON_INDENT)

    def _build_ai_payload(
        self,
        task: Task,
        method: str,
        single_spec: dict,
        api_choice: ApiChoice,
    ) -> "GetParams | BodyParams | None":
        """
        Return:
          - GetParams / BodyParams: needs BAML generation
          - None: skip BAML (no remaining fields)
        """
        method = method.upper()

        if method == "GET":
            raw_params = {p["name"]: p for p in single_spec.get("parameters", [])}
            reserved_keys = [m.to_param for m in api_choice.field_mappings]
            filtered_schema = {
                k: v for k, v in raw_params.items() if k not in reserved_keys
            }

            # Fast-path：剩餘 schema 為空 → 不呼叫 BAML
            if not filtered_schema:
                return None

            return b.GenerateQueryParams(
                task=task,
                parameter_schema=json.dumps(filtered_schema, ensure_ascii=False),
            )

        # Non-GET: requestBody schema
        raw_props = (
            single_spec.get("request_body", {}).get("schema", {}).get("properties", {})
        )
        reserved_keys = [m.to_param for m in api_choice.field_mappings]
        filtered_schema = {k: v for k, v in raw_props.items() if k not in reserved_keys}

        # Fast-path：剩餘 schema 為空 → 不呼叫 BAML
        if not filtered_schema:
            return None

        return b.GenerateBodyParams(
            task=task,
            parameter_schema=json.dumps(filtered_schema, ensure_ascii=False),
        )

    def _execute_post_process(
        self,
        raw_records: List[Dict[str, Any]],
        post_plan: PostProcessPlan,  # PostProcessPlan
    ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Output type:
          - final_records: list[dict]
          - stats: dict | None   # 這版統一回 None，沿用 records truncate（不再用 statistics）
        """
        if not raw_records or not post_plan or not getattr(post_plan, "strategy", None):
            return raw_records, None

        strategy = post_plan.strategy

        # AggregationTool
        if isinstance(strategy, AggregationTool):
            target_field = getattr(strategy, "target_field", None)
            return aggregate_records(raw_records, target_field), None

        # SortingTool
        if isinstance(strategy, SortingTool):
            sort_field = getattr(strategy, "sort_field", None)
            order = getattr(strategy, "order", "ASC")
            return sort_records(raw_records, sort_field, order), None

        return raw_records, None
