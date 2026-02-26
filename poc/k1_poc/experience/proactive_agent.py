"""
poc.k1_poc.experience.proactive_agent -- ProactiveAgent stub.

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
        pass
        return FillMessage()
