"""
Concierge FSM Demo
==================

Demonstrates the L1 Concierge FSM with:
- FSM state transitions (LISTENING -> ACKING -> DISPATCHING -> etc.)
- Intent classification
- Complexity-based routing (LOW/MEDIUM)
- Gap detection and clarification

Usage:
    python -m poc.session_state_demo.concierge_demo
    python poc/session_state_demo/concierge_demo.py --auto  # No pauses
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from poc.session_state_demo.bridge import SessionLLMBridge  # noqa: E402
from poc.session_state_demo.concierge.fsm import ConciergeFSM  # noqa: E402
from poc.session_state_demo.concierge.states import ConciergeState  # noqa: E402
from poc.session_state_demo.config import get_config  # noqa: E402
from poc.session_state_demo.display import (  # noqa: E402
    CYAN,
    GREEN,
    MAGENTA,
    YELLOW,
    colorize,
    print_assistant_message,
    print_clarification_request,
    print_classification,
    print_command_result,
    print_coverage_summary,
    print_fsm_stats,
    print_gate_stats,
    print_header,
    print_info,
    print_latency_sli,
    print_routing_decision,
    print_snapshot,
    print_state_change,
    print_state_history,
    print_stats,
    print_tool_call,
    print_user_message,
)

# Demo scenarios that exercise different FSM paths
DEMO_SCENARIOS = [
    # Scenario 1: Simple greeting (LOW tier, no tools)
    {
        "name": "Greeting (LOW tier)",
        "input": "Hi there!",
        "expected_tier": "LOW",
        "expected_clarification": False,
    },
    # Scenario 2: Information sharing (MEDIUM tier, tools)
    {
        "name": "Information Share (MEDIUM tier)",
        "input": "I'm planning a family trip to Japan with my two kids, ages 8 and 12.",
        "expected_tier": "MEDIUM",
        "expected_clarification": False,
    },
    # Scenario 3: Request with missing info (triggers clarification)
    {
        "name": "Reminder Request (needs clarification)",
        "input": "Remind me about the meeting",
        "expected_tier": "LOW",
        "expected_clarification": True,
    },
    # Scenario 4: Clarification response
    {
        "name": "Clarification Response",
        "input": "Tomorrow at 9am",
        "expected_tier": "LOW",
        "expected_clarification": False,
        "is_clarification_response": True,
    },
    # Scenario 5: Question (MEDIUM tier)
    {
        "name": "Question (MEDIUM tier)",
        "input": "What activities would you recommend for kids in Tokyo?",
        "expected_tier": "MEDIUM",
        "expected_clarification": False,
    },
]


def on_state_change(from_state: ConciergeState, to_state: ConciergeState) -> None:
    """Callback for FSM state changes."""
    print(
        colorize("  FSM: ", CYAN)
        + colorize(from_state.name, YELLOW)
        + colorize(" -> ", CYAN)
        + colorize(to_state.name, GREEN)
    )


async def run_concierge_demo(auto_mode: bool = False) -> None:
    """Run the Concierge FSM demo."""
    try:
        config = get_config()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("Please set GOOGLE_API_KEY in .env file")
        return

    print_header("CONCIERGE FSM DEMO - L1 State Machine")
    print_info(f"Session ID: {config.session_id}-concierge")
    print_info("Demonstrating FSM-based conversation flow")
    print()

    # Initialize bridge
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    bridge = SessionLLMBridge(
        session_id=config.session_id + "-concierge",
        db_path=str(config.db_path),
        restore_on_start=False,  # Fresh session for demo
    )

    success, msg = bridge.start()
    print_info(msg)

    # Initialize LLM client
    from poc.session_state_demo.llm_client import SimpleLLMClient

    llm = SimpleLLMClient(
        api_key=config.google_api_key,
        model=config.google_model,
    )

    # Initialize Concierge FSM
    fsm = ConciergeFSM(
        bridge=bridge,
        llm_client=llm,
        on_state_change=on_state_change,
    )

    print()
    print("=" * 70)
    print(
        colorize("  FSM STATES: ", CYAN)
        + "LISTENING -> ACKING -> CLARIFYING? -> DISPATCHING -> EXECUTING -> DELIVERING"
    )
    print("=" * 70)

    # Run demo scenarios
    for i, scenario in enumerate(DEMO_SCENARIOS, 1):
        print()
        print(colorize(f"{'='*70}", YELLOW))
        print(colorize(f"  Scenario {i}: {scenario['name']}", YELLOW, bold=True))
        print(colorize(f"{'='*70}", YELLOW))

        # Show expected behavior
        print(
            f"  Expected: Tier={scenario['expected_tier']}, Clarification={scenario['expected_clarification']}"
        )
        print()

        if not auto_mode:
            input("  Press Enter to continue...")
            print()

        # User message
        print_user_message(scenario["input"])

        # Record user turn
        changes = bridge.record_user_turn(scenario["input"])
        for c in changes:
            print_state_change(c.section, c.operation, c.description, auto=c.auto)

        # Process through FSM
        print()
        print(colorize("  [FSM Processing]", CYAN, bold=True))

        start_time = time.time()
        result = await fsm.process_input(scenario["input"])
        duration_ms = int((time.time() - start_time) * 1000)

        # Show state history
        print()
        print_state_history(result.state_history)

        # Show classification if available
        if result.classification:
            print_classification(result.classification)

        # Show routing
        print_routing_decision(
            result.tier.value, "direct" if result.tier.value == "low" else "llm_reasoning"
        )

        # Handle result
        if result.needs_clarification:
            print_clarification_request(result.clarification_question)
            print()
            print(colorize("  (Waiting for user response...)", MAGENTA))
        else:
            # Show tool calls
            for call in result.tool_calls:
                print_tool_call(call["name"], call["args"])

            # Show response
            if result.response:
                print_assistant_message(result.response)

            # Record assistant turn
            changes = bridge.record_assistant_turn(
                content=result.response or "OK",
                duration_ms=duration_ms,
                had_tool_call=len(result.tool_calls) > 0,
            )
            for c in changes:
                print_state_change(c.section, c.operation, c.description, auto=c.auto)

        # Show timing
        print()
        print(f"  Turn timing: {duration_ms}ms (classification: {result.classification_ms}ms)")

        # Brief pause between scenarios
        await asyncio.sleep(0.5)

    # Show final stats
    print()
    print("=" * 70)
    print(colorize("  FINAL STATISTICS", YELLOW, bold=True))
    print("=" * 70)

    print_snapshot(bridge.get_snapshot())
    print_stats(bridge.get_stats())
    print_fsm_stats(fsm.get_stats_dict())
    print_gate_stats(bridge.get_gate_stats())
    print_latency_sli(bridge.get_latency_sli())
    print_coverage_summary(include_fsm=True)

    # Checkpoint
    print()
    success, msg, size = bridge.checkpoint()
    print_command_result(msg, success)

    # Stop
    success, msg = bridge.stop()
    print_info(msg)

    print()
    print_header("CONCIERGE FSM DEMO COMPLETE")
    print_info("FSM demonstrated: LISTENING -> ACKING -> DISPATCHING -> EXECUTING -> DELIVERING")
    print_info("Plus: CLARIFYING state when gaps detected")


def main() -> None:
    """Entry point."""
    auto_mode = "--auto" in sys.argv
    asyncio.run(run_concierge_demo(auto_mode=auto_mode))


if __name__ == "__main__":
    main()
