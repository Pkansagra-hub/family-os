#!/usr/bin/env python3
"""Test PATH 5 memory recall in isolation."""

import asyncio
import sys
from pathlib import Path

# Ensure PoC package is importable
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


async def test_path5():
    from l3_execution.agents.specialists.memory_recall_agent import MemoryRecallAgent
    from system_coordinator import get_system_coordinator

    coord = get_system_coordinator()
    ok = await coord.initialize_system()
    if not ok:
        print("System init failed")
        return

    print("=" * 80)
    print("  PATH 5: Memory Recall & Life Wisdom")
    print("=" * 80)

    recall_agent = MemoryRecallAgent(
        agent_id="memory_recall_demo",
        session_id="session_test",
        groq_client=coord.groq_client,
        trace_id="path5_test",
    )

    # Turn 1: Memory queries
    print("\n--- TURN 1: Memory Queries ---")

    questions = [
        "What travel plans are pending?",
        "Who are my key colleagues?",
        "What decisions do I need to make?",
    ]

    for q in questions:
        print(f"\n[USER] {q}")
        result = await recall_agent.process_message({"query": q, "turn": 1})
        print(f"[ANSWER] {result['answer']}")
        print(f"[SOURCES] {result.get('memory_sources', [])}")

    # Turn 2: Wisdom request
    print("\n--- TURN 2: Wisdom Request ---")
    q2 = "Based on my memories, what should I prioritize?"
    print(f"\n[USER] {q2}")
    result = await recall_agent.process_message({"query": q2, "turn": 2})
    print(f"[WISDOM] {result['answer']}")

    await recall_agent.cleanup()
    await coord.shutdown_system()


if __name__ == "__main__":
    asyncio.run(test_path5())
