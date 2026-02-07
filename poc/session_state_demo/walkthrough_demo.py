"""
Walkthrough Demo - Guided Educational Mode
===========================================

EPIC: 4 - Demo Scenario Script
ISSUE: 4.2

An optional guided mode that explains what's happening behind the scenes.
This demo pauses at key moments to explain:
- How session state sections work
- What the auto-write middleware does
- How LLM tool calling updates state
- How checkpoint/restore preserves data

Usage:
    python -m poc.session_state_demo.walkthrough_demo
    python poc/session_state_demo/walkthrough_demo.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Any, Dict

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from poc.session_state_demo.bridge import SessionLLMBridge  # noqa: E402
from poc.session_state_demo.concierge import ConciergeFSM, ConciergeState  # noqa: E402
from poc.session_state_demo.config import get_config  # noqa: E402
from poc.session_state_demo.display import (  # noqa: E402
    BLUE,
    CYAN,
    GRAY,
    GREEN,
    MAGENTA,
    YELLOW,
    colorize,
    print_assistant_message,
    print_clarification_request,
    print_classification,
    print_command_result,
    print_coverage_summary,
    print_error,
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
from poc.session_state_demo.tools import SESSIONSTATE_TOOLS, parse_tool_call  # noqa: E402

# =============================================================================
# WALKTHROUGH CONTENT
# =============================================================================

INTRO_TEXT = """
Welcome to the Session State Walkthrough Demo!

This guided demo will show you how the K1 Session State system works.
We'll walk through a 5-turn conversation, pausing to explain:

  1. HOW state sections store different types of data
  2. HOW auto-write middleware captures turns automatically
  3. HOW LLM tool calling updates persona and beliefs
  4. HOW checkpoints preserve state for crash recovery

The session state uses a tiered architecture:
  - HOT tier: Frequently changing data (history, emotions, beliefs)
  - WARM tier: Less frequent updates (settings, long-term memory)
  - Each section has a fixed capacity with memory pressure management

New in this walkthrough: CONCIERGE FSM
  - L1 state machine that controls conversation flow
  - Intent classification determines request complexity
  - Gap detection triggers clarification when info is missing
  - Complexity routing decides direct vs LLM reasoning path
"""

SECTION_EXPLANATIONS = {
    "history_active": """
    SECTION: history_active (HOT tier)
    ===================================
    Stores the active conversation history as complete turns.
    Each turn contains both user message and assistant response.

    Capacity: 8KB (can hold ~20-30 turns typically)
    Auto-write: YES - written automatically after each turn

    Used for: Building LLM context, conversation continuity
    """,
    "telemetry": """
    SECTION: telemetry (HOT tier)
    ==============================
    Tracks conversation metrics: timing, token counts, errors.
    Helps monitor performance and detect issues.

    Capacity: 8KB
    Auto-write: YES - recorded after each assistant response

    Used for: Performance monitoring, debugging, analytics
    """,
    "persona": """
    SECTION: persona (HOT tier)
    ============================
    Stores learned user preferences and personality calibration.
    The LLM uses tool calls to update this section.

    Capacity: 8KB
    Auto-write: NO - updated via LLM tool calls

    Used for: Personalizing responses, remembering preferences
    """,
    "beliefs_active": """
    SECTION: beliefs_active (HOT tier)
    ====================================
    Stores facts the LLM has learned about the user.
    Structured as subject-predicate-object triples with confidence.

    Capacity: 8KB
    Auto-write: NO - updated via LLM tool calls

    Used for: Maintaining user knowledge graph, fact recall
    """,
    "affective_now": """
    SECTION: affective_now (HOT tier)
    ==================================
    Tracks current emotional state of the conversation.
    Helps calibrate tone and empathy in responses.

    Capacity: 4KB
    Auto-write: NO - updated via LLM tool calls

    Used for: Emotional intelligence, appropriate tone
    """,
}

STEP_EXPLANATIONS = {
    "user_input": """
    STEP: User Input Received
    =========================
    When you send a message, the bridge:
    1. Increments the turn counter
    2. Buffers the message (NOT written to storage yet)
    3. Prepares for LLM context building

    Why buffer? Because history_active stores COMPLETE turns
    (user + assistant together). We wait for the response.
    """,
    "context_build": """
    STEP: Building LLM Context
    ==========================
    Before calling the LLM, we read from session state:

    1. history_active -> Recent conversation for continuity
    2. persona -> User preferences for personalization
    3. affective_now -> Emotional state for tone calibration

    This context is combined into a system prompt and message list.
    """,
    "llm_call": """
    STEP: LLM API Call
    ==================
    The LLM receives:
    - System prompt with session context
    - Conversation history
    - Available tools (update_persona, update_emotion, add_belief)

    The LLM may return:
    - Text response
    - Tool calls to update session state
    - Both text and tool calls
    """,
    "tool_execution": """
    STEP: Tool Execution
    ====================
    The LLM decided to use tools! This means it learned something.

    Tools available:
    - update_persona: Save user preferences (interests, constraints)
    - update_emotion: Track emotional state changes
    - add_belief: Record facts about the user

    Each tool call mutates the appropriate session state section.
    """,
    "auto_write": """
    STEP: Auto-Write Middleware
    ===========================
    After the LLM response, auto-write kicks in:

    1. history_active.append() - Complete turn (user + assistant)
    2. telemetry.record_turn() - Timing and metrics

    This happens automatically - no LLM tool call needed.
    The session state now reflects the completed turn.
    """,
    "checkpoint": """
    STEP: Checkpoint to SQLite
    ==========================
    Checkpointing serializes ALL section data to SQLite.

    Process:
    1. Each section serializes via FlatBuffers (fast, compact)
    2. Binary data written to SQLite tables
    3. Metadata recorded (timestamps, sizes, versions)

    After crash, restore reads this data back into memory.
    """,
    "restore": """
    STEP: Restore from Checkpoint
    ==============================
    Restoring loads session state from the SQLite checkpoint.

    Process:
    1. Read binary data from SQLite tables
    2. Deserialize each section via FlatBuffers
    3. Reconstruct in-memory state exactly as it was

    The conversation can continue seamlessly!
    """,
    "fsm_intro": """
    CONCIERGE FSM: L1 State Machine
    ================================
    The Concierge FSM controls the conversation loop:

    LISTENING -> ACKING -> DISPATCHING -> EXECUTING -> DELIVERING
                   |
                   v (gaps found)
              CLARIFYING -> (user responds) -> ACKING

    Each input goes through classification, gap detection,
    and complexity-based routing before execution.
    """,
    "fsm_classification": """
    STEP: Intent Classification
    ============================
    The classifier analyzes user input to determine:

    1. PRIMARY INTENT: greeting, question, request, info_share
    2. COMPLEXITY TIER: LOW (<2s), MEDIUM (2-10s), HIGH (>10s)
    3. ENTITIES: names, numbers, dates extracted from text
    4. CONFIDENCE: How certain the classification is

    This drives routing decisions.
    """,
    "fsm_gap_detection": """
    STEP: Gap Detection
    ====================
    The gap detector looks for missing information:

    - missing_time: "remind me about meeting" (when?)
    - missing_quantity: "buy some milk" (how much?)
    - vague_reference: "that thing" (which thing?)
    - missing_location: "meet you there" (where?)
    - missing_person: "tell them" (who?)

    If gaps found -> FSM enters CLARIFYING state
    """,
    "fsm_routing": """
    STEP: Complexity Routing
    =========================
    Based on complexity tier, requests are routed:

    LOW TIER (<2s):
      - Simple greetings, acknowledgments
      - Direct response, no LLM reasoning needed

    MEDIUM TIER (2-10s):
      - Questions, information sharing
      - LLM reasoning + optional tool calls

    HIGH TIER (>10s): [Not in this demo]
      - Multi-step planning, complex tasks
      - Would go to Planner (L3)
    """,
    "fsm_clarification": """
    STEP: Clarification Flow
    =========================
    When gaps are detected, the FSM:

    1. Enters CLARIFYING state
    2. Generates targeted question for the gap
    3. Waits for user response
    4. Returns to ACKING to re-classify

    Max 2 clarifications per turn to avoid loops.
    """,
}

# Pre-scripted conversation with explanatory context
DEMO_SCRIPT = [
    {
        "message": "Hi! I'm planning a family trip to Japan in spring.",
        "explanation": """
    This opening message introduces the topic and shares some preferences.
    Watch for:
    - Auto-write buffering the user message
    - LLM tool calls to learn travel interest and timing
    - Complete turn written to history_active
        """,
    },
    {
        "message": "We have two kids, ages 8 and 12. They love anime and video games.",
        "explanation": """
    Now sharing family details that the LLM should remember.
    Watch for:
    - add_belief tool calls recording family facts
    - Multiple facts stored in beliefs_active section
        """,
    },
    {
        "message": "Our budget is around $5000 for the whole trip, not including flights.",
        "explanation": """
    Budget is a key constraint for trip planning.
    Watch for:
    - add_belief recording the budget constraint
    - Category tagging (likely 'travel' category)
        """,
    },
    {
        "message": "We'd prefer to stay in Tokyo and maybe visit Kyoto for a day.",
        "explanation": """
    Location preferences that should be remembered.
    Watch for:
    - update_persona learning location preferences
    - Building up the user profile
        """,
    },
    {
        "message": "What would you recommend for activities with kids?",
        "explanation": """
    Final turn asks for recommendations using learned context.
    The LLM should:
    - Reference all the learned information
    - Provide personalized recommendations
    - Possibly reinforce beliefs with tool calls
        """,
    },
]


# =============================================================================
# WALKTHROUGH UTILITIES
# =============================================================================


def print_explanation(text: str) -> None:
    """Print explanation text in a box."""
    lines = text.strip().split("\n")
    width = max(len(line) for line in lines) + 4

    print()
    print(colorize("+" + "-" * (width - 2) + "+", CYAN))
    for line in lines:
        padded = line.ljust(width - 4)
        print(colorize("|", CYAN) + f" {padded} " + colorize("|", CYAN))
    print(colorize("+" + "-" * (width - 2) + "+", CYAN))


def print_section_explanation(section: str) -> None:
    """Print explanation for a specific section."""
    if section in SECTION_EXPLANATIONS:
        print_explanation(SECTION_EXPLANATIONS[section])


def print_step_explanation(step: str) -> None:
    """Print explanation for a specific step."""
    if step in STEP_EXPLANATIONS:
        print_explanation(STEP_EXPLANATIONS[step])


# Global flag for auto mode (no pauses)
_AUTO_MODE = False


def wait_for_continue(prompt: str = "Press Enter to continue...") -> None:
    """Wait for user to press Enter (skipped in auto mode)."""
    if _AUTO_MODE:
        print()
        print(colorize(f"  >>> {prompt} (auto-continuing...)", GRAY))
        return
    print()
    print(colorize(f"  >>> {prompt}", YELLOW))
    input()


def print_memory_visualization(snapshot: Dict[str, Any]) -> None:
    """Print a visual memory diagram."""
    sections = snapshot.get("sections", {})
    hot_sections = [
        "history_active",
        "telemetry",
        "persona",
        "affective_now",
        "beliefs_active",
        "scoreboard",
        "clarifications",
        "narrative_active",
    ]
    warm_sections = ["history_recent", "beliefs_history", "control", "meta"]

    print()
    print(colorize("  MEMORY LAYOUT", YELLOW, bold=True))
    print()

    # HOT tier
    print(colorize("  HOT TIER (fast access, frequently updated)", GREEN))
    print("  " + "=" * 60)
    for name in hot_sections:
        if name in sections:
            info = sections[name]
            util = info.get("utilization_pct", 0)
            bar_len = int(util / 2.5)  # 40 char max
            bar = colorize("=" * bar_len, GREEN) + colorize("-" * (40 - bar_len), GRAY)
            print(f"  {name:18} {bar} {util:5.1f}%")
    print()

    # WARM tier
    print(colorize("  WARM TIER (persistent, less frequent updates)", BLUE))
    print("  " + "=" * 60)
    for name in warm_sections:
        if name in sections:
            info = sections[name]
            util = info.get("utilization_pct", 0)
            bar_len = int(util / 2.5)
            bar = colorize("=" * bar_len, BLUE) + colorize("-" * (40 - bar_len), GRAY)
            print(f"  {name:18} {bar} {util:5.1f}%")


# =============================================================================
# MAIN WALKTHROUGH
# =============================================================================


async def run_walkthrough():
    """Run the interactive walkthrough demo."""
    try:
        config = get_config()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("Please set GOOGLE_API_KEY in .env file")
        return

    # Introduction
    print_header("SESSION STATE WALKTHROUGH DEMO")
    print_explanation(INTRO_TEXT)
    wait_for_continue("Press Enter to begin the walkthrough...")

    # Initialize
    print_header("INITIALIZATION")
    print_info(f"Session ID: {config.session_id}-walkthrough")
    print()

    print_step_explanation("context_build")
    wait_for_continue()

    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    bridge = SessionLLMBridge(
        session_id=config.session_id + "-walkthrough",
        db_path=str(config.db_path),
        restore_on_start=False,
    )

    success, msg = bridge.start()
    print_info(msg)
    print()

    # Show initial state
    print(colorize("Initial Session State:", YELLOW, bold=True))
    print_memory_visualization(bridge.get_snapshot())
    wait_for_continue()

    # Initialize LLM
    from poc.session_state_demo.llm_client import SimpleLLMClient

    llm = SimpleLLMClient(
        api_key=config.google_api_key,
        model=config.google_model,
    )

    # Run conversation
    print_header("CONVERSATION BEGINS")

    for i, turn in enumerate(DEMO_SCRIPT, 1):
        user_message = turn["message"]
        explanation = turn["explanation"]

        print()
        print(colorize(f"{'='*60}", CYAN))
        print(colorize(f"  TURN {i} of {len(DEMO_SCRIPT)}", CYAN, bold=True))
        print(colorize(f"{'='*60}", CYAN))

        # Explain what to watch for
        print_explanation(explanation)
        wait_for_continue("Press Enter to send this message...")

        # === User Input Phase ===
        print_step_explanation("user_input")
        print_user_message(user_message)

        changes = bridge.record_user_turn(user_message)
        for c in changes:
            print_state_change(c.section, c.operation, c.description, auto=c.auto)

        wait_for_continue()

        # === Context Build Phase ===
        print_step_explanation("context_build")
        context = bridge.build_llm_context()

        print()
        print(colorize("  Context built from:", GRAY))
        print(colorize(f"    - {len(context['messages'])} messages from history", GRAY))
        print(
            colorize(
                f"    - Persona: {len(context['metadata'].get('persona_traits', {}))} traits", GRAY
            )
        )
        print(colorize(f"    - Emotion: {context['metadata'].get('emotional_state', {})}", GRAY))

        wait_for_continue()

        # === LLM Call Phase ===
        print_step_explanation("llm_call")
        print_info("Calling LLM API...")

        messages = context["messages"].copy()
        messages.append({"role": "user", "content": user_message})

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
        print_info(f"Response received in {duration_ms}ms")

        # === Tool Execution Phase ===
        tool_calls = parse_tool_call(response)

        if tool_calls:
            print_step_explanation("tool_execution")

            for call in tool_calls:
                print_tool_call(call["name"], call["args"])

                # Explain which section this affects
                section_map = {
                    "update_persona": "persona",
                    "update_emotion": "affective_now",
                    "add_belief": "beliefs_active",
                }
                affected = section_map.get(call["name"])
                if affected:
                    print_section_explanation(affected)

            tool_changes = bridge.execute_tool_calls(tool_calls)
            for c in tool_changes:
                print_state_change(c.section, c.operation, c.description, auto=c.auto)

            wait_for_continue()

        # === Response and Auto-Write Phase ===
        content = response.get("content", "")
        if not content:
            content = "I've noted that information."

        print_assistant_message(content)

        print_step_explanation("auto_write")

        changes = bridge.record_assistant_turn(
            content=content,
            duration_ms=duration_ms,
            had_tool_call=len(tool_calls) > 0,
        )
        for c in changes:
            print_state_change(c.section, c.operation, c.description, auto=c.auto)

        # Show memory state after turn
        print()
        print(colorize("Memory after this turn:", YELLOW))
        print_memory_visualization(bridge.get_snapshot())

        if i < len(DEMO_SCRIPT):
            wait_for_continue("Press Enter for next turn...")

    # === Checkpoint Phase ===
    print()
    print_header("CHECKPOINT DEMONSTRATION")
    print_step_explanation("checkpoint")
    wait_for_continue("Press Enter to create checkpoint...")

    success, msg, size = bridge.checkpoint()
    print_command_result(msg, success)
    print_info(f"All {len(bridge.get_snapshot()['sections'])} sections serialized to SQLite")

    # === Final State ===
    print()
    print_header("FINAL SESSION STATE")
    print_snapshot(bridge.get_snapshot())
    print_stats(bridge.get_stats())

    # Show what was learned
    print()
    print(colorize("What the LLM Learned:", YELLOW, bold=True))
    print()
    print(colorize("  Persona (preferences):", GREEN))
    persona_data = bridge.get_section_data("persona")
    if "traits" in persona_data:
        for k, v in persona_data.get("traits", {}).items():
            print(f"    - {k}")

    print()
    print(colorize("  Beliefs (facts):", GREEN))
    _ = bridge.get_section_data("beliefs_active")  # Verify section exists
    print("    (Stored in beliefs_active section)")

    print()
    print(colorize("  History:", GREEN))
    history_data = bridge.get_section_data("history_active")
    print(f"    {history_data.get('turn_count', 0)} complete turns stored")

    # === Restore Demonstration ===
    print()
    print_header("RESTORE DEMONSTRATION")
    print_step_explanation("restore")
    wait_for_continue("Press Enter to simulate crash and restore...")

    # Stop current session
    bridge.stop(checkpoint_before_stop=False)
    print_info("Session stopped (simulating app restart)")

    # Create new bridge and restore
    bridge2 = SessionLLMBridge(
        session_id=config.session_id + "-walkthrough",
        db_path=str(config.db_path),
        restore_on_start=True,
    )
    success, msg = bridge2.start()
    print_command_result(msg, success)

    # Verify restoration
    snapshot = bridge2.get_snapshot()
    print()
    print(colorize("Restored State Verification:", YELLOW, bold=True))
    print(f"  Turn Number: {snapshot.get('turn_number', 0)} (should be 5)")
    print(f"  Total Size: {snapshot.get('total_size_bytes', 0):,} bytes")

    history = bridge2.get_section_data("history_active")
    print(f"  History Turns: {history.get('turn_count', 0)} (all restored)")

    bridge2.stop()

    # === Concierge FSM Demonstration ===
    await run_concierge_walkthrough(config, wait_for_continue, print_explanation)

    # === Conclusion ===
    print()
    print_header("WALKTHROUGH COMPLETE")
    print_explanation(
        """
    You've seen how the K1 Session State + Concierge FSM works:

    SESSION STATE (L5):
    1. Automatically records conversation turns
    2. Allows LLMs to learn via tool calling
    3. Maintains separate sections for different data types
    4. Checkpoints to SQLite for crash recovery
    5. Restores seamlessly after restart

    CONCIERGE FSM (L1):
    6. Intent classification determines request type
    7. Complexity routing picks direct vs LLM path
    8. Gap detection triggers clarification flow
    9. State machine controls conversation loop

    Coverage: ~67% of K1 Concierge Architecture

    Run 'python -m poc.session_state_demo.demo' for interactive mode!
    Run 'python -m poc.session_state_demo.concierge_demo' for FSM-only demo!
    """
    )


# =============================================================================
# CONCIERGE FSM WALKTHROUGH
# =============================================================================

# Concierge-specific scenarios that demonstrate FSM states
CONCIERGE_SCRIPT = [
    {
        "message": "Hi there!",
        "explanation": """
    SCENARIO 1: Simple Greeting (LOW tier)
    =======================================
    A greeting is the simplest case:
    - Classification: GREETING intent, LOW complexity
    - No gaps detected (greetings don't need clarification)
    - Direct routing: skip LLM reasoning
    - FSM: LISTENING -> ACKING -> DISPATCHING -> EXECUTING -> DELIVERING
        """,
        "expect_clarification": False,
    },
    {
        "message": "Remind me about the meeting",
        "explanation": """
    SCENARIO 2: Request with Missing Info (CLARIFYING state)
    =========================================================
    This request is missing crucial information:
    - Classification: REQUEST intent
    - Gap detected: missing_time (WHEN is the meeting?)
    - FSM enters CLARIFYING state
    - Generates targeted question for user
    - FSM: LISTENING -> ACKING -> CLARIFYING (wait for answer)
        """,
        "expect_clarification": True,
    },
    {
        "message": "Tomorrow at 3pm",
        "explanation": """
    SCENARIO 3: Clarification Response
    ===================================
    User provides the missing information:
    - Classification: CLARIFICATION_RESPONSE intent
    - Context includes the pending gap (missing_time)
    - FSM resumes: ACKING -> DISPATCHING -> EXECUTING -> DELIVERING
    - Gap is resolved, can proceed with action
        """,
        "expect_clarification": False,
    },
    {
        "message": "What activities would you recommend for kids in Tokyo?",
        "explanation": """
    SCENARIO 4: Question (MEDIUM tier)
    ===================================
    A question requires LLM reasoning:
    - Classification: QUESTION intent, MEDIUM complexity
    - No gaps (question is complete)
    - LLM reasoning path with tool calls possible
    - FSM: LISTENING -> ACKING -> DISPATCHING -> EXECUTING -> DELIVERING
        """,
        "expect_clarification": False,
    },
]


def on_fsm_state_change(from_state: ConciergeState, to_state: ConciergeState) -> None:
    """Callback for FSM state transitions."""
    print(
        colorize("      FSM: ", CYAN)
        + colorize(from_state.name, YELLOW)
        + colorize(" -> ", CYAN)
        + colorize(to_state.name, GREEN)
    )


async def run_concierge_walkthrough(config, wait_fn, explain_fn):
    """Run the Concierge FSM walkthrough section."""
    print()
    print_header("CONCIERGE FSM DEMONSTRATION")
    print_step_explanation("fsm_intro")
    wait_fn("Press Enter to begin Concierge FSM walkthrough...")

    # Create fresh bridge for FSM demo
    bridge = SessionLLMBridge(
        session_id=config.session_id + "-fsm-walkthrough",
        db_path=str(config.db_path),
        restore_on_start=False,
    )
    success, msg = bridge.start()
    print_info(msg)

    # Initialize LLM
    from poc.session_state_demo.llm_client import SimpleLLMClient

    llm = SimpleLLMClient(
        api_key=config.google_api_key,
        model=config.google_model,
    )

    # Initialize Concierge FSM
    fsm = ConciergeFSM(
        bridge=bridge,
        llm_client=llm,
        on_state_change=on_fsm_state_change,
    )

    print()
    print(colorize("  FSM States:", YELLOW, bold=True))
    print("  LISTENING -> ACKING -> DISPATCHING -> EXECUTING -> DELIVERING")
    print("                 |")
    print("                 v (gaps)")
    print("            CLARIFYING")
    print()

    # Run FSM scenarios
    for i, scenario in enumerate(CONCIERGE_SCRIPT, 1):
        user_message = scenario["message"]
        explanation = scenario["explanation"]
        expect_clarification = scenario["expect_clarification"]

        print()
        print(colorize(f"{'='*60}", MAGENTA))
        print(colorize(f"  FSM SCENARIO {i} of {len(CONCIERGE_SCRIPT)}", MAGENTA, bold=True))
        print(colorize(f"{'='*60}", MAGENTA))

        # Explain scenario
        explain_fn(explanation)
        wait_fn("Press Enter to process this input...")

        # User message
        print_user_message(user_message)
        changes = bridge.record_user_turn(user_message)
        for c in changes:
            print_state_change(c.section, c.operation, c.description, auto=c.auto)

        # Classification explanation
        print()
        print_step_explanation("fsm_classification")

        # Process through FSM
        print()
        print(colorize("  [FSM Processing]", CYAN, bold=True))
        start_time = time.time()
        result = await fsm.process_input(user_message)
        duration_ms = int((time.time() - start_time) * 1000)

        # Show state history
        print()
        print_state_history(result.state_history)

        # Show classification
        if result.classification:
            print_classification(result.classification)
            wait_fn()

        # Handle result based on whether clarification is needed
        if result.needs_clarification:
            print_step_explanation("fsm_clarification")
            print_clarification_request(result.clarification_question)
            print()
            print(
                colorize("  FSM is now in CLARIFYING state, waiting for user response...", MAGENTA)
            )
        else:
            # Show routing
            print_step_explanation("fsm_routing")
            route = "direct" if result.tier.value == "low" else "llm_reasoning"
            print_routing_decision(result.tier.value, route)

            # Show tool calls if any
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

        print()
        print(f"  Turn timing: {duration_ms}ms (classification: {result.classification_ms}ms)")

        if i < len(CONCIERGE_SCRIPT):
            wait_fn("Press Enter for next FSM scenario...")

    # Show FSM stats
    print()
    print_header("CONCIERGE FSM STATISTICS")
    print_fsm_stats(fsm.get_stats_dict())
    print_gate_stats(bridge.get_gate_stats())
    print_latency_sli(bridge.get_latency_sli())
    print_coverage_summary(include_fsm=True)

    # Checkpoint and stop
    bridge.checkpoint()
    bridge.stop()

    print()
    print(colorize("Concierge FSM walkthrough complete!", GREEN, bold=True))


def main():
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Session State Walkthrough Demo")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Run in auto mode without pauses (for testing)",
    )
    args = parser.parse_args()

    global _AUTO_MODE
    _AUTO_MODE = args.auto

    asyncio.run(run_walkthrough())


if __name__ == "__main__":
    main()
    main()
