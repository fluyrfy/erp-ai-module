"""
L3 Agent - Entry Point
"""

import asyncio
from src.agent.l3_agent import L3Agent


async def main():
    print("\n" + "=" * 60)
    print("  HEBU.AI L3 Agent - PoC Demo")
    print("=" * 60 + "\n")

    # Initialize agent
    agent = L3Agent(module_name="hr")

    # Test queries
    test_queries = [
        "目前部門有哪些？",
    ]

    for query in test_queries:
        result = await agent.query(query)

        print("\n" + "-" * 60)
        if result.success:
            print(result.data)
        else:
            print(f"❌ Error: {result.error}")
        print("-" * 60 + "\n")

        # Pause between queries
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
