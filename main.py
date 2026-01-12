"""
L3 Agent - Single Shot Benchmark
"""

import asyncio
import time
import sys
from src.agent.l3 import L3Agent

# 維度一
# DEFAULT_QUERY = "幫我找姓『陳』的員工。"
# DEFAULT_QUERY = "列出第 2 頁的部門資料，每頁顯示 20 筆。"
# 維度二
# DEFAULT_QUERY = "幫我查『研發部』裡面所有的員工。"
# DEFAULT_QUERY = (
#     "請問員工『陳建國』現在是在哪一個部門任職？請告訴我該部門的詳細名稱與代碼。"
# )
# 維度三
# DEFAULT_QUERY = "我要找 2020 年以前到職的員工。"
# DEFAULT_QUERY = "檢查一下『業務部』有沒有員工編號是空的？"
# DEFAULT_QUERY = "列出所有已經被停用的部門。"
# 維度四
# DEFAULT_QUERY = "目前公司總共有多少個部門？"
# DEFAULT_QUERY = "研發部現在總共有幾個人？"
# DEFAULT_QUERY = "所有員工裡面，姓氏最多的是哪一個？"
# 維度五
# DEFAULT_QUERY = "幫我找『妍發部』的員工。"
# DEFAULT_QUERY = "查一下『太空總署』部門的人員名單。"
# 維度六
# DEFAULT_QUERY = "全公司所有員工和部門，只要名字裡有『金』字的都列出來。"


DEFAULT_QUERY = """
ACTION_REQUIRED: GET_ORG_STRUCTURE
TARGET_ENTITY: Department
CONTEXT: "The frontend needs to render a nested Organization Chart visualization."
OUTPUT_GOAL: Retrieve the full hierarchical tree of departments, including parent-child relationships.
CONSTRAINTS:
  - Format: Nested/Tree (Not Flat)
"""


async def main():
    # 支援從指令列帶入參數，例如: python main.py "查一下Frank"
    query = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUERY

    print("\n" + "=" * 60)
    print("  Agent - Performance Benchmark")
    print("=" * 60 + "\n")

    print(f"[Test Query] 🎯: {query}")
    print("-" * 60)

    # 1. 初始化計時 (包含連線 Ollama 的時間)
    print("[System] Initializing Agent...")
    t0 = time.perf_counter()

    agent = L3Agent(module_name="hr")

    t1 = time.perf_counter()
    print(f"[System] Agent Initialized in {t1 - t0:.4f}s")

    # 2. 執行查詢計時 (真正的推論時間)
    print(f"[L3Agent] 🤖 Executing Pipeline...")
    start_time = time.perf_counter()

    # 執行！
    result = await agent.query(query)

    end_time = time.perf_counter()
    duration = end_time - start_time

    # 3. 輸出結果
    print("\n" + "=" * 30 + " [Result] " + "=" * 30)
    if result.success:
        # 這裡印出 Summary
        print(result.data)

        # 如果你有在 result 裡塞 metrics，也可以印出來
        # print(f"\n[Metrics] Steps: {result.steps_count} | Tokens: {result.total_tokens}")
    else:
        print(f"❌ Error: {result.error}")

    print("=" * 68)

    # 4. 效能儀表板
    print(f"⏱️  Total Execution Time : {duration:.4f} seconds")
    print(f"🚀 Model Configuration  : 請檢查 functions.baml (G1~G6)")
    print("=" * 68 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
