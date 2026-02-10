"""
POC Demo Runner
================

Run the full Concierge -> Planner -> Orchestrator -> Fabric pipeline
with real Google Gemini LLMs and real Fabric tool execution.

Usage:
    python -m poc.concierge_planner_orchestrator.demo

Requires:
    - GOOGLE_API_KEY in environment or .env file
    - Tool contracts in k1/contracts/tools/
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load env
load_dotenv(Path(__file__).parent.parent / "chat_experience_poc" / ".env")
load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
# Quiet noisy loggers
logging.getLogger("k1.fabric").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.WARNING)

logger = logging.getLogger("poc.demo")


# ============================================================
# Demo scenarios
# ============================================================

DEMO_SCENARIOS = [
    {
        "name": "Multi-Domain HIGH (Weather + Recipes + Notes)",
        "input": (
            "Check the weather forecast for London this week, "
            "find me a good spaghetti recipe, and create a note "
            "with the meal plan and weather summary."
        ),
    },
    {
        "name": "Single-Domain LOW (Weather only)",
        "input": "What's the weather going to be like in Tokyo?",
    },
    {
        "name": "Multi-Step MEDIUM (Calendar + Date)",
        "input": "List my calendar events and calculate how many days until Christmas.",
    },
]


async def run_demo() -> None:
    """Run the POC demo with real LLM and real Fabric."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not set.")
        print("Set it in your environment or in poc/chat_experience_poc/.env")
        sys.exit(1)

    # Import here to avoid loading Fabric at module level
    from k1.fabric.factory import FabricFactory

    from .pipeline import Pipeline

    print("\n" + "=" * 70)
    print("  Concierge -> Planner -> Orchestrator -> Fabric  POC")
    print("  Real LLMs (Google Gemini) + Real Fabric Execution")
    print("=" * 70)

    # Create Fabric with test adapters (so execution goes through
    # the full 9-step pipeline but uses test providers)
    fabric_container = FabricFactory.create_for_testing(
        capture_events=True,
        contracts_dir="k1/contracts",
    )

    # Create the pipeline
    pipeline = Pipeline.create(
        api_key=api_key,
        fabric=fabric_container.facade,
        contracts_dir=Path("k1/contracts/tools"),
    )

    # Let user choose scenario or enter custom input
    print("\nAvailable scenarios:")
    for i, scenario in enumerate(DEMO_SCENARIOS, 1):
        print(f"  {i}. {scenario['name']}")
    print(f"  {len(DEMO_SCENARIOS) + 1}. Custom input")

    choice = input(f"\nChoose (1-{len(DEMO_SCENARIOS) + 1}): ").strip()

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(DEMO_SCENARIOS):
            user_input = DEMO_SCENARIOS[idx]["input"]
        else:
            user_input = input("Enter your request: ").strip()
    except ValueError:
        user_input = DEMO_SCENARIOS[0]["input"]

    print(f"\n{'=' * 70}")
    print(f"  USER: {user_input}")
    print(f"{'=' * 70}\n")

    # Run the pipeline
    result = await pipeline.run(user_input)

    # Display results
    print(f"\n{'=' * 70}")
    print("  RESULTS")
    print(f"{'=' * 70}")

    env = result.get("envelope", {})
    print(f"\n  Tier: {env.get('tier', '?')}")
    print(f"  Intent: {env.get('intent', '?')}")
    print(f"  Domains: {env.get('domains', [])}")

    orch = result.get("orchestrator_result", {})
    print(f"\n  Execution: {'SUCCESS' if orch.get('success') else 'PARTIAL/FAILED'}")
    print(f"  Duration: {orch.get('total_duration_ms', 0)}ms")
    print(f"  Steps: {len(orch.get('steps', []))}")

    for step in orch.get("steps", []):
        status = "OK" if step.get("success") else "FAIL"
        print(f"    [{status}] {step.get('step_id', '?')}: {step.get('capability', '?')}")
        if step.get("error"):
            print(f"          Error: {step['error']}")
        if step.get("data"):
            data_str = json.dumps(step["data"], default=str)
            if len(data_str) > 200:
                data_str = data_str[:200] + "..."
            print(f"          Data: {data_str}")

    print(f"\n{'=' * 70}")
    print("  CONCIERGE RESPONSE (LLM-Synthesized)")
    print(f"{'=' * 70}")
    print(f"\n  {result.get('response', 'No response generated.')}")
    print()


def main() -> None:
    """Entry point."""
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()
