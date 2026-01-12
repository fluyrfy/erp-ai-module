"""
L3 Agent - Entry Point
"""

import asyncio
from src.agent.l3 import L3Agent


async def main():
    print("\n" + "=" * 60)
    print("  L3 Agent")
    print("=" * 60 + "\n")

    # Initialize agent
    agent = L3Agent(module_name="hr")

    while True:
        try:
            # 獲取使用者輸入
            query = input("\n[User] 👤 >>> ")

            # 檢查是否退出
            if query.lower() in ["exit", "quit", "q", "退出", "離開"]:
                print("\n再見！")
                break

            # 略過空白輸入
            if not query.strip():
                continue

            print(f"[L3Agent] 🤖 思考中...")

            # 執行查詢
            result = await agent.query(query)

            print("\n" + "-" * 30 + " [回應] " + "-" * 30)
            if result.success:
                # 這裡假設你的 result.data 是字串或可列印的物件
                print(result.data)
            else:
                print(f"❌ Error: {result.error}")
            print("-" * 68)

        except KeyboardInterrupt:
            # 處理 Ctrl+C
            print("\n\n偵測到中斷指令，正在退出...")
            break
        except Exception as e:
            print(f"\n執行時發生未預期錯誤: {e}")

    # for query in test_queries:
    #     result = await agent.query(query)

    #     print("\n" + "-" * 60)
    #     if result.success:
    #         print(result.data)
    #     else:
    #         print(f"❌ Error: {result.error}")
    #     print("-" * 60 + "\n")

    #     # Pause between queries
    #     await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
