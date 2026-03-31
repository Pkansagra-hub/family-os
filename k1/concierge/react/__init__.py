"""
React Package -- Shared ReAct Loop for Front and Back Actors
=============================================================

V2 Design Ref: Section 7 (ReAct Loop Architecture)

Exports:
  - react_loop: Shared async ReAct loop for both actors
  - ReactResult: Return value dataclass from react_loop()
  - build_chat_history: Extract last N user/assistant turns for Front
  - build_chat_history_for_back: Extract last N decision-relevant messages for Back
  - _resolve_tool_choice: tool_choice helper (exported for testing)

Constants:
  - DEFAULT_FRONT_MAX_ITERATIONS: Default max iterations for Front (6)
  - DEFAULT_BACK_MAX_ITERATIONS: Default max iterations for Back (10)
  - MODE_MAX_ITERATIONS: Mode-specific iteration limits
  - CRISIS_MAX_ITERATIONS: Crisis override iteration limits
  - FRONT_DEGENERATE_FALLBACK: Fallback text for degenerate Front responses
  - FRONT_BUDGET_FALLBACK: Fallback text for Front budget exhaustion
"""

from k1.concierge.react.history import build_chat_history, build_chat_history_for_back
from k1.concierge.react.loop import (
    CRISIS_MAX_ITERATIONS,
    DEFAULT_BACK_MAX_ITERATIONS,
    DEFAULT_FRONT_MAX_ITERATIONS,
    FRONT_BUDGET_FALLBACK,
    FRONT_DEGENERATE_FALLBACK,
    MODE_MAX_ITERATIONS,
    ReactResult,
    _resolve_tool_choice,
    get_crisis_max_iterations,
    get_mode_max_iterations,
    react_loop,
)

__all__ = [
    "react_loop",
    "ReactResult",
    "build_chat_history",
    "build_chat_history_for_back",
    "_resolve_tool_choice",
    "DEFAULT_FRONT_MAX_ITERATIONS",
    "DEFAULT_BACK_MAX_ITERATIONS",
    "MODE_MAX_ITERATIONS",
    "CRISIS_MAX_ITERATIONS",
    "FRONT_DEGENERATE_FALLBACK",
    "FRONT_BUDGET_FALLBACK",
    "get_mode_max_iterations",
    "get_crisis_max_iterations",
]
