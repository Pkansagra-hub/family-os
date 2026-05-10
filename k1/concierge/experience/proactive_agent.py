"""
k1.concierge.experience.proactive_agent -- ProactiveAgent stub.

Generates fill/status messages during long waits.

V2 Design Ref: Section 12.3.5

Fire cadence: COMPANIONING state + wait duration > 5 seconds
    (enforced by ExperienceLayer.tick()).
Budget: 50 ms.
Reads: task state, current wait duration.
Writes: FillMessage emitted as k1.proactive.fill.v1 on bus.

Pluggability:
  - Future: contextual fill generation (progress updates,
    fun facts about the domain, reassurance for complex tasks).
  - Integration (bus -> Front): FSM receives k1.proactive.fill.v1,
    routes to Front handler in PRESENT mode (Section 4).
    Front's ReAct loop presents the fill message to the user.
  - Integration (ReAct loop): The fill triggers a separate Front
    invocation. It does NOT interrupt an in-progress Front loop.
    The FSM queues fills and delivers them between Front invocations.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FillMessage:
    """Output of ProactiveAgent. Emitted as k1.proactive.fill.v1 on bus.
    FSM routes to Front handler for presentation during long Back waits.
    """

    message: str = ""  # What to say during the wait
    style: str = "informational"  # "informational" | "reassuring" | "entertaining"
    show_progress: bool = False  # Whether to include progress indicator


class ProactiveAgent:
    """Generates fill/status messages during long waits.

    Fire cadence: COMPANIONING state + wait duration > 5 seconds.
    Budget: 50 ms.
    Reads: task state, current wait duration.
    Writes: FillMessage emitted as k1.proactive.fill.v1 on bus.

    Pluggability:
      - Future: contextual fill generation (progress updates,
        fun facts about the domain, reassurance for complex tasks).
      - Integration (bus -> Front): FSM receives k1.proactive.fill.v1,
        routes to Front handler in PRESENT mode (Section 4).
        Front's ReAct loop presents the fill message to the user.
        This is a FULL Front invocation -- the fill message goes through
        DynamicPromptBuilder, gets tone/affect adjustment, and streams
        to the user like any other Front response.
      - Integration (ReAct loop): The fill triggers a separate Front
        invocation. It does NOT interrupt an in-progress Front loop.
        The FSM queues fills and delivers them between Front invocations.
    """

    async def generate_fill(
        self,
        task_state: dict,
        wait_duration_ms: int,
    ) -> FillMessage:
        """Heuristic fill-message generation (M6 E6.1).

        Template-based, no LLM, sub-50ms budget.

        Activation criteria: `task_state` carries an explicit `action`
        or `step` string describing the in-flight work.  Without this
        signal, callers receive defaults so an empty FillMessage is
        treated as "nothing to say yet" by `_tick_experience`.

        Style escalates from `informational` to `reassuring` after
        15s; `show_progress` flips on after 8s.
        """
        action = ""
        if isinstance(task_state, dict):
            raw_action = task_state.get("action") or task_state.get("step")
            if isinstance(raw_action, str):
                action = raw_action.strip()

        if not action:
            return FillMessage()

        try:
            wait_ms = int(wait_duration_ms)
        except (TypeError, ValueError):
            wait_ms = 0

        style = "reassuring" if wait_ms > 15_000 else "informational"
        show_progress = wait_ms > 8_000
        seconds = max(0, wait_ms // 1000)
        if style == "reassuring":
            message = f"Still working on {action} ({seconds}s in) -- thanks for your patience."
        else:
            message = f"Working on {action}..."

        return FillMessage(message=message, style=style, show_progress=show_progress)
