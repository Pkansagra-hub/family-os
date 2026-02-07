"""
Test Scoreboard + Narrative Tracking (M9)
==========================================

Quick test to verify scoreboard referent tracking and narrative phase detection.

Usage:
    python -m poc.session_state_demo.test_tracking
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ruff: noqa: E402 (imports after sys.path manipulation)
from poc.session_state_demo.anniversary_demo.runner import NarrativeTracker, ScoreboardTracker
from poc.session_state_demo.concierge.states import NarrativePhase


def test_scoreboard():
    """Test ScoreboardTracker."""
    print("=" * 60)
    print("Scoreboard Tracker Test - M9.1")
    print("=" * 60)

    tracker = ScoreboardTracker(bridge=None)  # No persistence for this test

    # Simulate conversation turns
    turns = [
        (1, "Hey, I need help planning a surprise for Mike's 50th birthday", ""),
        (2, "We're thinking of going to Sonoma for a weekend trip", ""),
        (3, "Mike loves wine and has a shellfish allergy", ""),
        (5, "Emma will watch Jake while we're away", ""),
        (8, "What accommodations do you recommend at the Vineyard Inn?", ""),
    ]

    for turn_num, user_input, assistant_response in turns:
        changes = tracker.update_from_turn(
            turn_number=turn_num,
            user_input=user_input,
            assistant_response=assistant_response,
            tool_calls=None,
        )

        print(f"\n--- Turn {turn_num} ---")
        print(f"  Input: {user_input[:50]}...")
        if changes["referents_added"]:
            print(f"  Added referents: {changes['referents_added']}")
        if changes["qud_changed"]:
            print(f"  QUD updated: {tracker._qud}")

    # Show final scoreboard
    print("\n" + "=" * 60)
    print("Final Scoreboard State")
    print("=" * 60)

    scoreboard = tracker.get_scoreboard()
    print(f"\nTopic: {scoreboard['topic']}")
    print(f"QUD: {scoreboard['qud']}")

    print("\nTop Referents:")
    for ref in tracker.get_top_referents(8):
        print(f"  {ref['name']}: {ref['type']} (salience: {ref['salience']:.2f})")

    print("\nContext for LLM:")
    print(tracker.format_for_context())


def test_narrative():
    """Test NarrativeTracker."""
    print("\n" + "=" * 60)
    print("Narrative Tracker Test - M9.2")
    print("=" * 60)

    tracker = NarrativeTracker(bridge=None)  # No persistence for this test

    # Test phase transitions across turns
    test_turns = [
        (1, "Let's plan a trip", False),
        (5, "What do you think?", False),
        (10, "Book the Vineyard Inn", False),
        (15, "Start monitoring weather", False),
        (20, "", True),  # Crash!
        (22, "What happened?", False),
        (27, "Let's finalize everything", False),
    ]

    for turn_num, user_input, had_crash in test_turns:
        changes = tracker.update_from_turn(
            turn_number=turn_num,
            user_input=user_input,
            tool_calls=None,
            had_crash=had_crash,
        )

        print(f"\n--- Turn {turn_num} ---")
        print(f"  Phase: {tracker.current_phase.value.upper()}")
        if changes["phase_changed"]:
            print(f"  [TRANSITION] {changes['previous_phase']} -> {changes['new_phase']}")
        if had_crash:
            print("  [CRISIS DETECTED]")

    # Show final narrative state
    print("\n" + "=" * 60)
    print("Final Narrative State")
    print("=" * 60)

    narrative = tracker.get_narrative()
    print(f"\nPhase: {narrative['phase']} ({narrative['phase_description']})")
    print(f"Thread: {narrative['thread']}")

    print("\nPhase History:")
    for phase_record in narrative["history"]:
        print(
            f"  {phase_record['phase']}: turns {phase_record['start_turn']}-{phase_record['end_turn']}"
        )

    print("\nContext for LLM:")
    print(tracker.format_for_context())


def test_narrative_phase_enum():
    """Test NarrativePhase enum."""
    print("\n" + "=" * 60)
    print("NarrativePhase Enum Test")
    print("=" * 60)

    # Test all phases
    for phase in NarrativePhase:
        print(f"\n{phase.value.upper()}")
        print(f"  Description: {phase.description}")

    # Test turn-based detection
    print("\nTurn-Based Phase Detection:")
    test_turns = [1, 5, 8, 10, 14, 17, 20, 23, 28]
    for turn in test_turns:
        phase = NarrativePhase.from_turn_number(turn)
        print(f"  Turn {turn:2d}: {phase.value}")


if __name__ == "__main__":
    test_scoreboard()
    test_narrative()
    test_narrative_phase_enum()

    print("\n" + "=" * 60)
    print("Milestone 9 Tests Complete!")
    print("=" * 60)
    print("\n" + "=" * 60)
    print("Milestone 9 Tests Complete!")
    print("=" * 60)
