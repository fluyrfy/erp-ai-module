# src/agent/l2_agent.py
"""
L2 Agent - Cross-Module Orchestrator
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any, AsyncGenerator, Union

from src.agent.shared.types import (
    AgentError,
    AgentResult,
    ChunkType,
    StreamChunk,
)
from src.config import config
from src.agent.shared.errors import ErrorCode
from src.agent.l3 import L3Agent

# BAML client (generated)
from baml_client import b
from baml_client.types import Briefing, Task
from src.swagger_parser import SwaggerParser
from src.utils.bamler import stream_decision
from src.utils.logging import traced


class L2Agent:
    """L2 Orchestrator: Plan → Parallel Execute → Synthesize"""

    def __init__(self):
        self.available_modules: list[str] = []

    @traced
    async def query(
        self, user_query: str
    ) -> AsyncGenerator[Union[dict, AgentResult], None]:
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
            yield AgentResult.fail(
                AgentError(
                    code=ErrorCode.UNKNOWN_ERROR,  # 或 EXEC_HTTP_ERROR
                    message=f"Service Discovery Failed: {str(e)}",
                    details={
                        "suggestion": "Check if backend /v3/api-docs/swagger-config is reachable."
                    },
                )
            )
            return

        # ─────────────────────────────────────────────────────────
        # Step 1: Plan Execution
        # ─────────────────────────────────────────────────────────
        try:
            sys_context = self._get_system_context()
            # plan = await self._plan_execution(user_query, tools_data_list, sys_context)
            # 🔥 呼叫新的串流 Planning
            async for item in self._plan_execution(
                user_query, tools_data_list, sys_context
            ):
                if isinstance(item, StreamChunk):
                    yield item
                else:
                    plan = item
        except Exception as e:
            yield AgentResult.fail(
                AgentError(
                    code=ErrorCode.UNKNOWN_ERROR,
                    message=f"PlanExecution failed: {e}",
                )
            )
            return

        print(f"[Step 1] Plan created: {len(plan.tasks)} task(s)")
        print(f"         Thought: {plan.thought_process[:100]}...")

        if not plan.tasks:
            yield AgentResult.fail(
                AgentError(
                    code=ErrorCode.PLAN_EMPTY,
                    message="Planner generated zero tasks",
                )
            )
            return

        for task in plan.tasks:
            print(
                f"         - {task.task_id}: [{task.target_module}] {task.action_required}"
            )

        # ─────────────────────────────────────────────────────────
        # Step 2: Parallel Execute via L3
        # ─────────────────────────────────────────────────────────
        print(f"\n[Step 2] Executing {len(plan.tasks)} task(s) in parallel...")

        async for item in self._execute_tasks_parallel(plan.tasks):
            if isinstance(item, StreamChunk):
                # 這是 L3 傳上來的思考過程 -> 繼續往外丟給前端
                yield item
            else:
                # 這不是 Chunk，那就是最後 yield 出來的 results dict
                results = item

        success_count = sum(1 for r in results.values() if r.success)
        print(f"[Step 2] Completed: {success_count}/{len(plan.tasks)} succeeded")

        # 護欄：如果所有子任務都掛點
        if success_count == 0:
            yield AgentResult.fail(
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
            return

        # ─────────────────────────────────────────────────────────
        # Step 3: Synthesize Results
        # ─────────────────────────────────────────────────────────
        print(f"\n[Step 3] Synthesizing final answer...")
        try:
            sys_context = self._get_system_context()
            async for chunk in self._generate_briefing_stream(
                user_query=user_query,
                plan=plan,
                task_results=self._format_results_for_synthesis(results),
                sys_context=sys_context,
            ):
                yield chunk

            return
        except Exception as e:
            yield AgentResult.fail(
                AgentError(
                    code=ErrorCode.SYNTHESIS_FAILED,
                    message=f"SynthesizeResults failed: {e}",
                )
            )
            return

    @traced
    def _generate_briefing(self, user_query, plan, task_results, sys_context):
        briefing = b.GenerateBriefing(
            user_query=user_query,
            plan=plan,
            task_results=task_results,
            sys_context=sys_context,
        )
        return briefing

    @traced
    async def _generate_briefing_stream(
        self, user_query, plan, task_results, sys_context
    ) -> AsyncGenerator[Union[StreamChunk, AgentResult], None]:
        """Stream narrative.answer chunks, then yield final Briefing"""
        stream = b.stream.GenerateBriefing(
            user_query=user_query,
            plan=plan,
            task_results=task_results,
            sys_context=sys_context,
        )
        last_answer_len = 0
        last_table_len = 0
        has_yielded_attachment_header = False

        for partial in stream:
            if not partial.narrative:
                continue

            # --- 1. 處理 Answer 增量 ---
            if partial.narrative.answer:
                curr_answer = partial.narrative.answer
                if len(curr_answer) > last_answer_len:
                    delta = curr_answer[last_answer_len:]
                    yield StreamChunk(type=ChunkType.ANSWER, content=delta)
                    last_answer_len = len(curr_answer)

            # --- 2. 處理 Data Attachment (Markdown 表格) 增量 ---
            if (
                partial.narrative.data_attachment
                and partial.narrative.data_attachment.content
            ):
                attachment = partial.narrative.data_attachment.content

                # 如果是表格剛開始出現，先補兩個換行，避免跟文字黏在一起
                if not has_yielded_attachment_header:
                    yield StreamChunk(type=ChunkType.ANSWER, content="\n\n")
                    has_yielded_attachment_header = True

                if len(attachment) > last_table_len:
                    table_delta = attachment[last_table_len:]
                    yield StreamChunk(type=ChunkType.ANSWER, content=table_delta)
                    last_table_len = len(attachment)

        final = stream.get_final_response()
        yield AgentResult.ok(final.model_dump(mode="json"))

    @traced
    async def _plan_execution(
        self, user_query, tools, sys_context
    ) -> AsyncGenerator[Union[StreamChunk, Any], None]:
        stream = b.stream.PlanExecution(
            user_query=user_query,
            available_modules=tools,
            sys_context=sys_context,
        )
        async for item in stream_decision(stream):
            yield item

    @traced
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

    @traced
    async def _execute_tasks_parallel(
        self, tasks: list[Task]
    ) -> AsyncGenerator[Union[StreamChunk, dict[str, AgentResult]], None]:
        """Execute all tasks in parallel, wait for all to complete"""
        # 1. 準備工具
        queue = asyncio.Queue()
        active_tasks = len(tasks)
        results: dict[str, AgentResult] = {}

        # 2. 把東西 put 到 queue
        async def run_single_task(task: Task) -> None:
            """Run one L3 task and return (task_id, result)"""
            try:
                # Validate module
                target_module_norm = task.target_module.lower().strip()
                available_modules_norm = [m.lower() for m in self.available_modules]
                if target_module_norm not in available_modules_norm:
                    results[task.task_id] = AgentResult.fail(
                        AgentError(
                            code=ErrorCode.INVALID_MODULE,
                            message=f"Unknown module: {task.target_module}",
                        )
                    )
                    return

                # Create L3 agent for target module
                l3Agent = L3Agent(module_name=target_module_norm)
                async for item in l3Agent.execute(task):
                    if isinstance(item, StreamChunk):
                        # 這是思考過程 -> 丟進 queue 給外面
                        # item.content = f"[{task.target_module}] {item.content}"
                        await queue.put(item)
                    elif isinstance(item, AgentResult):
                        # 這是結果 -> 寫入 results
                        results[task.task_id] = item
                        print(
                            f"         ✓ {task.task_id} completed (success={item.success})"
                        )

            except Exception as e:
                print(f"         ✗ {task.task_id} failed: {e}")
                results[task.task_id] = AgentResult.fail(
                    AgentError(
                        code=ErrorCode.UNKNOWN_ERROR,
                        message=f"Task {task.task_id} crashed: {e}",
                    )
                )
            finally:
                await queue.put(None)

        # 3. 啟動任務：把 gather 改成 create_task (背景執行)
        for t in tasks:
            asyncio.create_task(run_single_task(t))

        # 4. 消費者迴圈：把 queue 的東西拿出來 yield 出去
        finished_count = 0
        while finished_count < active_tasks:
            item = await queue.get()
            if item is None:
                finished_count += 1
            else:
                yield item

        # 5. 最後回傳 results dict
        yield results

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

    def _get_system_context(self) -> str:
        """
        最簡化的系統上下文：時間 + 語系
        """
        now = datetime.now()
        # 格式範例: 2026-01-16 18:30:00 (Friday)
        time_str = now.strftime("%Y-%m-%d %H:%M:%S (%A)")

        return f"""
        [System Context]
        - Current Time: {time_str}
        - User Language: {config.DEFAULT_LANGUAGE}
        - Response Requirement: Always answer in {config.DEFAULT_LANGUAGE} unless specified otherwise.
        """
