"""
Anniversary Demo - 30-Turn End-to-End Demonstration
====================================================

"The Anniversary Weekend" - A complete demonstration of FamilyOS capabilities:
- SessionState persistence and learning
- LLM-driven gap detection
- Two-way concierge with background tasks
- Crash recovery
- Proactive notifications

Usage:
    python -m poc.session_state_demo.anniversary_demo.runner --auto
"""

from poc.session_state_demo.anniversary_demo.display import (
    colorize,
    print_act_header,
    print_assistant_message,
    print_crash_screen,
    print_demo_complete,
    print_demo_header,
    print_gap_detected,
    print_restore_screen,
    print_tool_call,
    print_turn_indicator,
    print_user_message,
    print_weather_alert,
)
from poc.session_state_demo.anniversary_demo.runner import DemoRunner, DemoState
from poc.session_state_demo.anniversary_demo.script import (
    DEMO_SCRIPT,
    SCRIPT_METADATA,
    Act,
    DemoTurn,
    ExpectedBehavior,
    TurnEvent,
    get_all_turns,
    get_turn,
    get_turns_by_act,
)
from poc.session_state_demo.anniversary_demo.tools.registry import ToolRegistry

__all__ = [
    # Tool Registry
    "ToolRegistry",
    # Script
    "DEMO_SCRIPT",
    "SCRIPT_METADATA",
    "Act",
    "TurnEvent",
    "DemoTurn",
    "ExpectedBehavior",
    "get_turn",
    "get_turns_by_act",
    "get_all_turns",
    # Runner
    "DemoRunner",
    "DemoState",
    # Display
    "colorize",
    "print_demo_header",
    "print_act_header",
    "print_turn_indicator",
    "print_user_message",
    "print_assistant_message",
    "print_tool_call",
    "print_gap_detected",
    "print_crash_screen",
    "print_restore_screen",
    "print_weather_alert",
    "print_demo_complete",
]
