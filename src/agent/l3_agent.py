"""
L3 Generic Agent
"""

import json
from datetime import date
from pathlib import Path

from src.config import config
from src.agent.errors import AgentError, AgentResult, ErrorCode
from src.utils.http import execute_http_request, execute_multiple_requests
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
        if (
            selection.overall_confidence < config.CONFIDENCE_THRESHOLD
        ):  # 比原先 0.8 低，鼓勵探索
            return AgentResult.fail(
                AgentError(
                    code=ErrorCode.LOW_CONFIDENCE,
                    message=f"整體信心不足（{selection.overall_confidence:.2f}），無法可靠回答",
                    details={"reasoning": selection.reasoning},
                )
            )

        # ─────────────────────────────────────────────────────────
        # Step 2: Generate HTTP Request
        # ─────────────────────────────────────────────────────────
        api_requests_to_run = []
        for idx, api_choice in enumerate(selected_apis):
            single_spec = self.parser.get_api_by_id(api_choice.api_id)
            if not single_spec:
                return AgentResult.fail(
                    AgentError(
                        code=ErrorCode.UNKNOWN_ERROR,
                        message=f"Can't fine API spec: {api_choice.api_id}",
                    )
                )

            try:
                http_request = b.GenerateHttpRequest(
                    user_query=user_query,
                    api_spec=json.dumps(single_spec, ensure_ascii=False),
                    current_date=str(date.today()),
                )
                api_requests_to_run.append((api_choice.api_id, http_request))
                print(
                    f"[Step 2] Prepared: {api_choice.api_id} -> {http_request.method} {http_request.path}"
                )
                print(f"Params: {http_request.query_params}")
            except Exception as e:
                return AgentResult.fail(
                    AgentError(
                        code=ErrorCode.UNKNOWN_ERROR,
                        message=f"第 {idx+1} 支 API 產生請求失敗: {e}",
                    )
                )

        # ─────────────────────────────────────────────────────────
        # Step 3: Execute HTTP Request(s)
        # ─────────────────────────────────────────────────────────
        all_responses = {}
        sequential = selection.needs_sequential_execution
        mode_str = "SEQUENTIAL" if sequential else "PARALLEL"

        print(f"[Step 3] Execution Mode: {mode_str}")
        print(f"[Step 3] Executing {len(api_requests_to_run)} API request(s)...")
        try:
            # Using the utility function to handle parallel/sequential logic
            all_responses = await execute_multiple_requests(
                base_url=self.base_url,
                api_requests=api_requests_to_run,
                sequential=sequential,
                timeout=config.HTTP_TIMEOUT,
            )
        except AgentError as ae:
            print(f"[Step 3] Execution Error: {ae.message}")
            return AgentResult.fail(ae)
        except Exception as e:
            print(f"[Step 3] Unexpected Error: {e}")
            return AgentResult.fail(
                AgentError(
                    code=ErrorCode.UNKNOWN_ERROR, message=f"Batch execution failed: {e}"
                )
            )
        print(
            f"[Step 3] Execution completed. Received {len(all_responses)} response(s)."
        )

        # ─────────────────────────────────────────────────────────
        # Step 4: Generate Summary
        # ─────────────────────────────────────────────────────────
        try:
            summary = b.GenerateSummary(
                user_query=user_query,
                api_response=json.dumps(all_responses, ensure_ascii=False),
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

        # Format output
        output = self._format_summary(summary)
        save_trace(
            module=self.module_name,
            user_query=user_query,
            success=True,
            result=output,
            duration_ms=(time.time() - start_time) * 1000,
            raw_response=response_data,
        )
        return AgentResult.ok(output)

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
