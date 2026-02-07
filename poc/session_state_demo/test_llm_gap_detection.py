"""
Test LLM Gap Detection
======================

Quick test to verify LLM-powered gap detection works correctly.

Usage:
    python -m poc.session_state_demo.test_llm_gap_detection
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ruff: noqa: E402 (imports after sys.path manipulation)
from poc.session_state_demo.bridge import SessionLLMBridge
from poc.session_state_demo.concierge.gap_detector import GapDetector
from poc.session_state_demo.concierge.llm_gap_detector import HybridGapDetector, LLMGapDetector
from poc.session_state_demo.config import get_config
from poc.session_state_demo.llm_client import SimpleLLMClient


async def test_llm_gap_detection():
    """Test LLM gap detection on Turn 10 scenario."""
    print("=" * 60)
    print("LLM Gap Detection Test - M7")
    print("=" * 60)

    # Initialize components
    config = get_config()
    llm_client = SimpleLLMClient(
        model=config.google_model,
        api_key=config.google_api_key,
    )
    bridge = SessionLLMBridge(db_path=":memory:", session_id="test")

    # Create LLM gap detector
    llm_detector = LLMGapDetector(llm_client=llm_client, bridge=bridge)
    heuristic_detector = GapDetector()
    hybrid_detector = HybridGapDetector(
        llm_detector=llm_detector,
        heuristic_detector=heuristic_detector,
        llm_threshold=0.7,
    )

    # Add some context (beliefs from earlier turns) via tool execution
    # Use the bridge's execute_tool_calls interface
    tool_calls = [
        {
            "name": "add_belief",
            "args": {
                "subject": "Mike",
                "predicate": "has_allergy",
                "object": "shellfish",
            },
        },
        {
            "name": "add_belief",
            "args": {
                "subject": "trip",
                "predicate": "destination",
                "object": "Sonoma",
            },
        },
        {
            "name": "add_belief",
            "args": {
                "subject": "trip",
                "predicate": "dates",
                "object": "this weekend",
            },
        },
    ]

    print("\nSeeding beliefs...")
    for tc in tool_calls:
        try:
            bridge.execute_tool_calls([tc])
            print(
                f"  Added: {tc['args']['subject']} {tc['args']['predicate']} {tc['args']['object']}"
            )
        except Exception as e:
            print(f"  Warning: {e}")

    # Test inputs that should trigger gap detection
    test_inputs = [
        # Turn 10: Missing date, time, cuisine, party_size
        "Now I need to arrange something special for his actual birthday dinner",
        # Book a spa with missing details
        "I want to book a couples massage",
        # Search without location
        "Find me some nice wineries to visit",
        # Complete request (should NOT trigger gaps)
        "Search for Italian restaurants in Sonoma for Saturday at 7pm for 2 people",
    ]

    session_context = {
        "beliefs": bridge.get_section_data("beliefs_active"),
        "persona": {},
    }

    for i, user_input in enumerate(test_inputs, 1):
        print(f"\n{'=' * 60}")
        print(f"Test {i}: {user_input[:50]}...")
        print("=" * 60)

        # Test heuristic detector
        print("\n--- Heuristic Detection ---")
        heuristic_gaps = heuristic_detector.detect_gaps(user_input, session_context)
        if heuristic_gaps:
            for gap in heuristic_gaps:
                print(f"  Gap: {gap.gap_type} (confidence: {gap.confidence:.2f})")
                print(f"  Question: {gap.question}")
        else:
            print("  No gaps detected by heuristics")

        # Test LLM detector
        print("\n--- LLM Detection ---")
        try:
            llm_result = await llm_detector.detect_gaps(user_input, session_context)
            print(f"  Likely tool: {llm_result.likely_tool}")
            print(
                f"  Reasoning: {llm_result.reasoning[:100]}..."
                if llm_result.reasoning
                else "  No reasoning"
            )
            if llm_result.gaps:
                for gap in llm_result.gaps:
                    print(f"  Gap: {gap.gap_type} (confidence: {gap.confidence:.2f})")
                    print(f"  Question: {gap.question}")
            else:
                print("  No gaps detected by LLM")
        except Exception as e:
            print(f"  LLM detection failed: {e}")

        # Test hybrid detector
        print("\n--- Hybrid Detection ---")
        try:
            hybrid_gaps = await hybrid_detector.detect_gaps(user_input, session_context)
            if hybrid_gaps:
                for gap in hybrid_gaps:
                    print(f"  Gap: {gap.gap_type} (confidence: {gap.confidence:.2f})")
                    print(f"  Question: {gap.question}")
            else:
                print("  No gaps detected by hybrid")
        except Exception as e:
            print(f"  Hybrid detection failed: {e}")

    print("\n" + "=" * 60)
    print("Test Complete")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_llm_gap_detection())

if __name__ == "__main__":
    asyncio.run(test_llm_gap_detection())
