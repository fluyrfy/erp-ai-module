# src/agent/l2_agent.py
"""
L2 Agent - Cross-Module Orchestrator
"""

import asyncio
from typing import Any

from src.config import config
from src.agent.shared.errors import AgentError, AgentResult, ErrorCode
from src.agent.l3 import L3Agent

# BAML client (generated)
from baml_client import b
from baml_client.types import Task, ExecutionPlan, Synthesis
from src.swagger_parser import SwaggerParser


class L2Agent:
    """L2 Orchestrator: Plan → Parallel Execute → Synthesize"""

    def __init__(self):
        self.available_modules: list[str] = []

    async def query(self, user_query: str) -> AgentResult:
        """
        Process user query through L2 pipeline:
        1. Plan - Break down into tasks
        2. Execute - Run tasks in parallel via L3
        3. Synthesize - Combine results into final answer
        """
        print(f"\n{'='*60}")
        print(f"[L2] Query: {user_query}")
        print(f"{'='*60}")

        # ─────────────────────────────────────────────────────────
        # Step 0: Service Discovery
        # ─────────────────────────────────────────────────────────
        # 把結果拆成兩份：
        # 1. module_names (List[str]): 純名單 -> ["HR", "Inventory"] -> 給 Python 用
        # 2. capabilities_context (str): 詳細說明書 -> "Module: HR..." -> 給 LLM 用

        try:
            # 1. 執行掃描 (如果失敗會直接拋出 Exception)
            module_names, tools_data_list = await self._scan_active_modules()

            # 2. 更新 self，供 Step 2 驗證使用
            self.available_modules = module_names

        except Exception as e:
            # 🔥 如果連總表都拿不到，L2 直接停工
            return AgentResult.fail(
                AgentError(
                    code=ErrorCode.UNKNOWN_ERROR,  # 或 EXEC_HTTP_ERROR
                    message=f"Service Discovery Failed: {str(e)}",
                    details={
                        "suggestion": "Check if backend /v3/api-docs/swagger-config is reachable."
                    },
                )
            )

        # ─────────────────────────────────────────────────────────
        # Step 1: Plan Execution
        # ─────────────────────────────────────────────────────────
        try:
            plan = b.PlanExecution(
                user_query=user_query,
                available_modules=tools_data_list,
            )
        except Exception as e:
            return AgentResult.fail(
                AgentError(
                    code=ErrorCode.UNKNOWN_ERROR,
                    message=f"PlanExecution failed: {e}",
                )
            )

        print(f"[Step 1] Plan created: {len(plan.tasks)} task(s)")
        print(f"         Thought: {plan.thought_process[:100]}...")

        if not plan.tasks:
            return AgentResult.fail(
                AgentError(
                    code=ErrorCode.PLAN_EMPTY,
                    message="Planner generated zero tasks",
                )
            )

        for task in plan.tasks:
            print(
                f"         - {task.task_id}: [{task.target_module}] {task.action_required}"
            )

        # ─────────────────────────────────────────────────────────
        # Step 2: Parallel Execute via L3
        # ─────────────────────────────────────────────────────────
        print(f"\n[Step 2] Executing {len(plan.tasks)} task(s) in parallel...")

        results = await self._execute_tasks_parallel(plan.tasks)

        success_count = sum(1 for r in results.values() if r.success)
        print(f"[Step 2] Completed: {success_count}/{len(plan.tasks)} succeeded")

        # 護欄：如果所有子任務都掛點
        if success_count == 0:
            return AgentResult.fail(
                AgentError(
                    code=ErrorCode.ALL_TASKS_FAILED,
                    message="All execution tasks failed. Cannot proceed to synthesis.",
                    details={
                        "task_errors": [
                            r.error.message for r in results.values() if r.error
                        ]
                    },
                )
            )

        # ─────────────────────────────────────────────────────────
        # Step 3: Synthesize Results
        # ─────────────────────────────────────────────────────────
        print(f"\n[Step 3] Synthesizing final answer...")

        try:
            synthesize_results = b.SynthesizeResults(
                user_query=user_query,
                plan=plan,
                task_results=self._format_results_for_synthesis(results),
            )
        except Exception as e:
            return AgentResult.fail(
                AgentError(
                    code=ErrorCode.SYNTHESIS_FAILED,
                    message=f"SynthesizeResults failed: {e}",
                )
            )

        print(f"[Step 3] Done: {synthesize_results.answer}")

        return AgentResult.ok(self._format_output(synthesize_results))

    async def _scan_active_modules(self) -> tuple[list[str], list[dict]]:
        """
        1. 回傳 module_names (List) 給程式邏輯驗證用
        2. 回傳 modules_metadata (List) 給 LLM 閱讀用
        """
        print("[L2] 📡 Scanning active modules...")

        # 1. 查總表 -> 拿到 [{'name': 'hr', 'url': '...'}, ...]
        modules_discovery = await SwaggerParser.fetch_available_modules()

        if not modules_discovery:
            raise Exception(
                "No modules discovered from backend (swagger-config returned empty or failed)."
            )

        # 2. 提取純名單 (這就是你要的 List，可以用 not in)
        # 結果範例: ["HR", "Inventory", "Finance"]
        module_names = [m["name"] for m in modules_discovery]

        # 3. 平行抓取詳細說明 (這是給 LLM 的長字串)
        tasks = []
        for mod in modules_discovery:
            tasks.append(SwaggerParser.fetch_module_metadata(mod["name"], mod["url"]))

        results = await asyncio.gather(*tasks)
        modules_metadata = [r for r in results if r is not None]

        return module_names, modules_metadata

    async def _execute_tasks_parallel(
        self, tasks: list[Task]
    ) -> dict[str, AgentResult]:
        """Execute all tasks in parallel, wait for all to complete"""

        async def run_single_task(task: Task) -> tuple[str, AgentResult]:
            """Run one L3 task and return (task_id, result)"""
            try:
                # Validate module
                if task.target_module not in self.available_modules:
                    return (
                        task.task_id,
                        AgentResult.fail(
                            AgentError(
                                code=ErrorCode.INVALID_MODULE,
                                message=f"Unknown module: {task.target_module}",
                            )
                        ),
                    )

                # Create L3 agent for target module
                agent = L3Agent(module_name=task.target_module)
                result = await agent.execute(task)

                print(f"         ✓ {task.task_id} completed (success={result.success})")
                return (task.task_id, result)

            except Exception as e:
                print(f"         ✗ {task.task_id} failed: {e}")
                return (
                    task.task_id,
                    AgentResult.fail(
                        AgentError(
                            code=ErrorCode.UNKNOWN_ERROR,
                            message=f"Task {task.task_id} crashed: {e}",
                        )
                    ),
                )

        # Run all tasks in parallel
        coroutines = [run_single_task(t) for t in tasks]
        results_list = await asyncio.gather(*coroutines)

        return dict(results_list)

    def _format_results_for_synthesis(self, results: dict[str, AgentResult]) -> str:
        """Format task results as string for LLM synthesis"""
        lines = []
        for task_id, result in results.items():
            lines.append(f"=== {task_id} ===")
            if result.success:
                lines.append(f"Status: SUCCESS")
                lines.append(f"Data: {result.data}")
            else:
                lines.append(f"Status: FAILED")
                lines.append(
                    f"Error: {result.error.message if result.error else 'Unknown'}"
                )
            lines.append("")
        return "\n".join(lines)

    def _format_output(self, synthesis: Synthesis) -> str:
        """Format final synthesis for display"""
        lines = [f"## {synthesis.answer}", ""]

        if synthesis.key_findings:
            for finding in synthesis.key_findings:
                lines.append(f"- {finding}")
            lines.append("")

        if synthesis.conclusion:
            lines.append(f"**Conclusion:** {synthesis.conclusion}")

        return "\n".join(lines)
