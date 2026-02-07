"""
Automated Demo Script for Session State
========================================

Runs a pre-scripted conversation to demonstrate:
1. Turn recording to history_active
2. Telemetry updates
3. LLM tool calling for persona updates
4. Checkpoint and restore

Usage:
    python -m poc.session_state_demo.scripted_demo
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
from poc.session_state_demo.config import get_config  # noqa: E402
from poc.session_state_demo.display import (  # noqa: E402
    print_assistant_message,
    print_command_result,
    print_coverage_summary,
    print_error,
    print_gate_stats,
    print_header,
    print_info,
    print_latency_sli,
    print_section_data,
    print_snapshot,
    print_state_change,
    print_stats,
    print_tool_call,
    print_user_message,
)
from poc.session_state_demo.tools import SESSIONSTATE_TOOLS, parse_tool_call  # noqa: E402

# Pre-scripted conversation
DEMO_SCRIPT = [
    "Hi! I'm planning a family trip to Japan in spring.",
    "We have two kids, ages 8 and 12. They love anime and video games.",
    "Our budget is around $5000 for the whole trip, not including flights.",
    "We'd prefer to stay in Tokyo and maybe visit Kyoto for a day.",
    "What would you recommend for activities with kids?",
]


async def run_scripted_demo():
    """Run the scripted demo."""
    try:
        config = get_config()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("Please set GOOGLE_API_KEY in .env file")
        return

    print_header("SESSION STATE DEMO - Scripted Mode")
    print_info(f"Session ID: {config.session_id}")
    print_info("Running pre-scripted conversation to demonstrate session state")

    # Initialize bridge
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    bridge = SessionLLMBridge(
        session_id=config.session_id + "-scripted",
        db_path=str(config.db_path),
        restore_on_start=False,  # Fresh session for demo
    )

    success, msg = bridge.start()
    print_info(msg)

    # Initialize LLM client (use our simple client)
    from poc.session_state_demo.llm_client import SimpleLLMClient

    llm = SimpleLLMClient(
        api_key=config.google_api_key,
        model=config.google_model,
    )

    print()
    print("=" * 60)
    print("STARTING CONVERSATION")
    print("=" * 60)

    # Run through script
    for i, user_message in enumerate(DEMO_SCRIPT, 1):
        print()
        print(f"--- Turn {i} of {len(DEMO_SCRIPT)} ---")

        # User message
        print_user_message(user_message)

        # Record user turn (buffer)
        changes = bridge.record_user_turn(user_message)
        for c in changes:
            print_state_change(c.section, c.operation, c.description, auto=c.auto)

        # Build context
        context = bridge.build_llm_context()
        messages = context["messages"].copy()
        messages.append({"role": "user", "content": user_message})

        # Call LLM
        start_time = time.time()
        try:
            response = await llm.complete_with_tools(
                system_prompt=context["system_prompt"],
                messages=messages,
                tools=SESSIONSTATE_TOOLS,
            )
        except Exception as e:
            print_error(f"LLM call failed: {e}")
            response = {"content": f"[Error: {e}]", "tool_calls": []}

        duration_ms = int((time.time() - start_time) * 1000)

        # Process tool calls
        tool_calls = parse_tool_call(response)
        for call in tool_calls:
            print_tool_call(call["name"], call["args"])

        if tool_calls:
            tool_changes = bridge.execute_tool_calls(tool_calls)
            for c in tool_changes:
                print_state_change(c.section, c.operation, c.description, auto=c.auto)

        # Get response content
        content = response.get("content", "")
        if not content:
            content = "I've noted that information."

        print_assistant_message(content)

        # Record assistant turn
        changes = bridge.record_assistant_turn(
            content=content,
            duration_ms=duration_ms,
            had_tool_call=len(tool_calls) > 0,
        )
        for c in changes:
            print_state_change(c.section, c.operation, c.description, auto=c.auto)

        # Brief pause between turns
        await asyncio.sleep(0.5)

    # Show final state
    print()
    print("=" * 60)
    print("FINAL STATE")
    print("=" * 60)

    print_snapshot(bridge.get_snapshot())
    print_stats(bridge.get_stats())
    print_gate_stats(bridge.get_gate_stats())
    print_latency_sli(bridge.get_latency_sli())
    print_coverage_summary()

    print()
    print("--- History ---")
    print_section_data("history_active", bridge.get_section_data("history_active"))

    print()
    print("--- Persona (learned) ---")
    print_section_data("persona", bridge.get_section_data("persona"))

    # Checkpoint
    print()
    print("=" * 60)
    print("CHECKPOINT TEST")
    print("=" * 60)

    success, msg, size = bridge.checkpoint()
    print_command_result(msg, success)

    # Stop
    success, msg = bridge.stop()
    print_info(msg)

    print()
    print_header("DEMO COMPLETE")
    print_info("Session state saved. Run again to see restore behavior.")


def main():
    """Entry point."""
    asyncio.run(run_scripted_demo())


if __name__ == "__main__":
    main()
