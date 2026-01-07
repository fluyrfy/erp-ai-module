"""
L3 Generic Agent
"""

import json
from datetime import date
from pathlib import Path
from typing import Any

from baml_client.types import ApiChoice, HttpRequest
from src.config import config
from src.agent.errors import AgentError, AgentResult, ErrorCode
from src.utils import get_nested, execute_http_request
import time
from src.tracing import save_trace

# BAML client (generated)
from baml_client import b
from src.swagger_parser import SwaggerParser


class L3Agent:
    """Generic L3 Agent for any module"""

    def __init__(
        self,
        module_name: str,
        base_url: str | None = None,
        language: str | None = None,
    ):
        """
        Initialize L3 Agent

        Args:
            module_name: Module identifier (e.g., "HR", "Inventory")
            base_url: Backend URL. Defaults to BACKEND_BASE_URL env var
            language: Output language. Defaults to config setting
        """
        self.module_name = module_name
        self.language = language or config.DEFAULT_LANGUAGE
        self.base_url = base_url or config.BACKEND_BASE_URL
        self.swagger_url = (
            f"{self.base_url}{config.SWAGGER_DOC_PATH}/{module_name.lower()}"
        )

        self.parser: SwaggerParser | None = SwaggerParser(self.swagger_url)

        # Load API doc
        # if api_doc_path is None:
        #     api_doc_path = f"api_docs/{module_name.lower()}.yaml"
        # self.api_doc = self._load_api_doc(api_doc_path)

        print(f"[L3Agent] Module: {module_name}")
        print(f"[L3Agent] Backend: {self.base_url}")
        print(f"[L3Agent] Swagger: {self.swagger_url}")

    # def _load_api_doc(self, path: str) -> str:
    #     """Load OpenAPI spec from file"""
    #     file_path = Path(path)
    #     if not file_path.exists():
    #         raise FileNotFoundError(f"API doc not found: {path}")
    #     return file_path.read_text(encoding="utf-8")

    async def query(self, user_query: str) -> AgentResult:
        """
        Process user query through the agent pipeline

        Args:
            user_query: Natural language question

        Returns:
            AgentResult with success/failure and data/error
        """
        start_time = time.time()

        print(f"\n{'='*60}")
        print(f"[Query] {user_query}")
        print(f"{'='*60}")
        # ─────────────────────────────────────────────────────────
        # Step 0: 載入並解析最新 Swagger spec
        # ─────────────────────────────────────────────────────────
        try:
            await self.parser.load()
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
                user_query=user_query,
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
                    user_query=user_query,
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
                )
            except Exception as e:
                return AgentResult.fail(
                    AgentError(
                        code=ErrorCode.UNKNOWN_ERROR,
                        message=f"Field mapping failed for {api_choice.api_id}: {e}",
                    )
                )

            print(f"[Step 3] Executing: {api_choice.api_id}")
            print(f"         {http_request.method} {http_request.path}")
            if final_query_params:
                print(f"         Query: {final_query_params}")
            if final_body and final_body != "{}":
                print(f"         Body: {final_body}")

            response, error = await execute_http_request(
                base_url=self.base_url,
                method=http_request.method,
                path=http_request.path,
                query_params=(
                    final_query_params if http_request.method == "GET" else None
                ),
                body=final_body if http_request.method != "GET" else "",
            )
            if error:
                print(f"[Step 3] Error: {error}")
                return AgentResult.fail(error)

            results[api_choice.api_id] = response
            print(f"[Step 3] Success: {api_choice.api_id}")

        # ─────────────────────────────────────────────────────────
        # Step 4: Generate Summary
        # ─────────────────────────────────────────────────────────
        try:
            summary = b.GenerateSummary(
                user_query=user_query,
                api_response=json.dumps(results, ensure_ascii=False),
                output_language=self.language,
            )
        except Exception as e:
            save_trace(
                module=self.module_name,
                user_query=user_query,
                success=False,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )
            return AgentResult.fail(
                AgentError(
                    code=ErrorCode.UNKNOWN_ERROR, message=f"GenerateSummary failed: {e}"
                )
            )

        print(f"[Step 4] Summary: {summary.title}")
        return AgentResult.ok(self._format_summary(summary))

    def _format_summary(self, summary) -> str:
        """Format Summary object for display"""
        lines = [f"## {summary.title}", ""]

        if summary.key_points:
            for point in summary.key_points:
                lines.append(f"- {point}")
            lines.append("")

        if summary.metrics:
            lines.append("📊 **Key Metrics:**")
            for key, value in summary.metrics.items():
                lines.append(f"  - {key}: {value}")
            lines.append("")

        if summary.recommendation:
            lines.append(f"💡 **Recommendation:** {summary.recommendation}")

        return "\n".join(lines)

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
    ) -> tuple[dict[str, str], str]:
        """
        根據 field_mappings 從前一個 API 的結果取值塞入

        Args:
            http_request: LLM 生成的 HTTP request
            field_mappings: 欄位映射列表
            results: 已執行 API 的結果

        Returns:
            (final_query_params, final_body)
        """
        # 複製原本的參數
        query_params = (
            dict(http_request.query_params) if http_request.query_params else {}
        )
        body_dict = (
            json.loads(http_request.body)
            if http_request.body and http_request.body != "{}"
            else {}
        )

        # 套用每個 mapping
        for mapping in field_mappings:
            # 從前一個 API 的 response 取值
            source_response = results.get(mapping.from_api)
            if source_response is None:
                raise Exception(f"Dependency not found: {mapping.from_api}")

            value = get_nested(source_response, mapping.from_field)

            # 根據 HTTP method 決定塞到哪裡
            if http_request.method == "GET":
                query_params[mapping.to_param] = str(value)
            else:
                body_dict[mapping.to_param] = value

        final_body = json.dumps(body_dict, ensure_ascii=False) if body_dict else ""

        return query_params, final_body
