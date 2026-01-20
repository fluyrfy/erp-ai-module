"""
L3 Agent - Single Shot workflow
"""

import asyncio
import time
import sys

# from src.agent.l3 import L3Agent
from src.agent.l2 import L2Agent

from src.agent.shared.types import AgentResult
from src.observability import setup_tracing

from opentelemetry import trace
import inspect
from baml_client import b

print("SelectApi is coroutine function:", inspect.iscoroutinefunction(b.SelectApi))

# 也可以直接看回傳型態（不呼叫 LLM 的前提下不一定能測；但 iscoroutinefunction 最準）


setup_tracing(service_name="erp-ai-module")
tracer = trace.get_tracer(__name__)

DEFAULT_QUERY = "目前有哪些部門。"


def pretty_print_result(data):
    """
    專門用來處理 Briefing 結構的顯示函式
    """
    # 1. 如果 L2 還是回傳純字串 (舊兼容)
    if isinstance(data, str):
        print(data)
        return

    # 2. 如果是 Briefing 結構 (Dict)
    if isinstance(data, dict):
        narrative = data.get("narrative", {})
        insight = data.get("insight", {})

        # A. 印出主要回答
        answer = narrative.get("answer", "")
        print(answer)

        # B. 檢查有沒有附件 (表格/列表)，有的話印出來
        attachment = narrative.get("data_attachment")
        if attachment and attachment.get("content"):
            print("\n" + "-" * 30 + " [詳細資料] " + "-" * 30)
            # 這裡就是把表格 "接" 在後面的時刻
            print(attachment["content"])

            if attachment.get("record_count"):
                print(f"\n(共 {attachment['record_count']} 筆資料)")

        # C. (選用) 如果你想看 Insight 裡的 ID 或 Metrics，也可以印
        # print("\n[System Insight]:", insight.get("extracted_entities"))


async def main():
    # 支援從指令列帶入參數，例如: python main.py "查一下Frank"
    query = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUERY

    print("\n" + "=" * 60)
    print("  Agent - Performance workflow")
    print("=" * 60 + "\n")
    with tracer.start_as_current_span(
        "workflow.run",
        attributes={
            "workflow.goal": query,
        },
    ) as root_span:
        print(f"[Test Query] 🎯: {query}")
        print("-" * 60)

        # 1. 初始化計時 (包含連線 Ollama 的時間)
        print("[System] Initializing Agent...")
        t0 = time.perf_counter()

        agent = L2Agent()

        t1 = time.perf_counter()
        print(f"[System] Agent Initialized in {t1 - t0:.4f}s")

        # 2. 執行查詢計時 (真正的推論時間)
        print(f" 🤖 Executing Pipeline...")
        start_time = time.perf_counter()

        with tracer.start_as_current_span("workflow.execute") as exec_span:
            # 執行！
            # ❌ 舊的寫法 (會噴 TypeError)
            # result = await agent.query(query)

            # ✅ 新的寫法：準備一個變數接最終結果
            result = None

            # 視覺優化：提示開始串流
            print(" 💬 ", end="", flush=True)

            # 使用 async for 接水管
            async for event in agent.query(query):

                # Case A: 收到文字片段 (Delta Chunk) -> 即時印出
                if isinstance(event, dict):
                    content = event.get("content", "")
                    print(content, end="", flush=True)

                # Case B: 收到最終結果 (AgentResult) -> 存起來給後面用
                elif isinstance(event, AgentResult):
                    result = event

            # 串流結束，換行
            print("\n")

            # 以下維持原本的 Tracing 邏輯，但在 result 存在時才執行
            if result:
                exec_span.set_attribute("result.success", result.success)
                if not result.success:
                    exec_span.set_status(trace.Status(trace.StatusCode.ERROR))
                    if result.error:
                        exec_span.set_attribute("error.code", result.error.code.value)
                        exec_span.set_attribute("error.message", result.error.message)
            else:
                print("❌ Error: Stream finished but no final result returned.")
                return

        end_time = time.perf_counter()
        duration = end_time - start_time

        # 3. 輸出結果
        print("\n" + "=" * 30 + " [Result] " + "=" * 30)
        if result.success:
            # 這裡印出 Summary
            pretty_print_result(result.data)
        else:
            print(f"❌ Error: {result.error.code}")
            print(f"   Message: {result.error.message}")
            if result.error.details:
                print(f"   Details: {result.error.details}")

        print("=" * 68)

        # 4. 效能儀表板
        print(f"⏱️  Total Execution Time : {duration:.4f} seconds")

        root_span.set_attribute("workflow.duration_s", duration)
        root_span.set_attribute("workflow.success", result.success)
        print("=" * 68 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
