"""
L3 Generic Agent
"""

import json
from datetime import date
from pathlib import Path

from src.config import config
from src.agent.errors import AgentError, AgentResult, ErrorCode
from src.utils.http import execute_http_request
import time
from src.tracing import save_trace

# BAML client (generated)
from baml_client import b


class L3Agent:
    """Generic L3 Agent for any module"""

    def __init__(
        self,
        module_name: str,
        api_doc_path: str | None = None,
        base_url: str | None = None,
        language: str | None = None,
    ):
        """
        Initialize L3 Agent

        Args:
            module_name: Module identifier (e.g., "HR", "Inventory")
            api_doc_path: Path to OpenAPI spec. Defaults to api_docs/{module}.yaml
            base_url: Backend URL. Defaults to BACKEND_BASE_URL env var
            language: Output language. Defaults to config setting
        """
        self.module_name = module_name
        self.language = language or config.DEFAULT_LANGUAGE
        self.base_url = base_url or config.BACKEND_BASE_URL

        # Load API doc
        if api_doc_path is None:
            api_doc_path = f"api_docs/{module_name.lower()}.yaml"
        self.api_doc = self._load_api_doc(api_doc_path)

        print(f"[L3Agent] Module: {module_name}")
        print(f"[L3Agent] Backend: {self.base_url}")

    def _load_api_doc(self, path: str) -> str:
        """Load OpenAPI spec from file"""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"API doc not found: {path}")
        return file_path.read_text(encoding="utf-8")

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
        # Step 1: Select API
        # ─────────────────────────────────────────────────────────
        try:
            selection = b.SelectApi(
                user_query=user_query,
                api_doc=self.api_doc,
                module_context=f"This is the {self.module_name} module.",
            )
        except Exception as e:
            return AgentResult.fail(
                AgentError(
                    code=ErrorCode.UNKNOWN_ERROR, message=f"SelectApi failed: {e}"
                )
            )

        print(
            f"[Step 1] Selected: {selection.api_id} (confidence: {selection.confidence})"
        )

        if selection.confidence < config.CONFIDENCE_THRESHOLD:
            return AgentResult.fail(
                AgentError(
                    code=ErrorCode.NO_API_MATCH,
                    message=f"No suitable API found. Reason: {selection.reasoning}",
                    details={"confidence": selection.confidence},
                )
            )

        # ─────────────────────────────────────────────────────────
        # Step 2: Generate HTTP Request
        # ─────────────────────────────────────────────────────────
        try:
            http_request = b.GenerateHttpRequest(
                user_query=user_query,
                api_spec=self.api_doc,  # TODO: extract single API spec
                current_date=str(date.today()),
            )
        except Exception as e:
            return AgentResult.fail(
                AgentError(
                    code=ErrorCode.UNKNOWN_ERROR,
                    message=f"GenerateHttpRequest failed: {e}",
                )
            )

        print(f"[Step 2] {http_request.method} {http_request.path}")
        print(f"         Params: {http_request.query_params}")

        # ─────────────────────────────────────────────────────────
        # Step 3: Execute HTTP Request
        # ─────────────────────────────────────────────────────────
        response_data, error = await execute_http_request(
            base_url=self.base_url,
            method=http_request.method,
            path=http_request.path,
            query_params=http_request.query_params,
            body=http_request.body,
            timeout=config.HTTP_TIMEOUT,
        )

        if error:
            print(f"[Step 3] Error: {error}")
            return AgentResult.fail(error)

        print(
            f"[Step 3] Response received (items: {response_data.get('total', 'N/A')})"
        )

        # ─────────────────────────────────────────────────────────
        # Step 4: Generate Summary
        # ─────────────────────────────────────────────────────────
        try:
            summary = b.GenerateSummary(
                user_query=user_query,
                api_response=json.dumps(response_data, ensure_ascii=False),
                output_language=self.language,
            )
        except Exception as e:
            save_trace(
                module=self.module_name,
                user_query=user_query,
                success=False,
                error=str(error),
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
