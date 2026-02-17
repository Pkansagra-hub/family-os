"""IDeltaEmitPort -- Planner delta emission protocol [F17].

The delta emission port broadcasts planning progress to the Delta Bus.
Every stage transition, tool call result, and plan outcome generates a
delta event on the ``k1.planner.delta.v1`` topic.

Design decisions (SS15.7)
-------------------------
- **Synchronous** (not async): ``emit()`` MUST NOT block.
- **Fire-and-forget**: ``emit()`` MUST NOT raise, even if the bus is
  unavailable.  The adapter logs a warning and returns silently.
- Deltas are best-effort observability signals, not control-plane messages.
  Delta loss is acceptable.
- PLAN-01 emphasis: delta emission is NOT a SessionState write.

Delta types (SS28.3)
--------------------
stage_transition, tool_result, hil_event, plan_update, plan_end,
micro_replan, crash_recovery

Callers
-------
- PipelineController (stage_started, stage_completed, plan_end, plan_failed,
  plan_cancelled)
- CommitService (plan_committed)
- ToolCallRouter (tool_call_result)
- HILCoordinator (hil_clarification_sent, hil_approval_sent)

Adapter: DeltaBusAdapter [F33] pre-stamps agent_id and topic

Import graph (Layer 1)
----------------------
k1.planner.ports.delta_emit_port
  -> k1.planner.types  (DeltaPayload)
  -> typing
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from k1.planner.types import DeltaPayload


@runtime_checkable
class IDeltaEmitPort(Protocol):
    """Fire-and-forget delta emission port.

    This is a structural protocol (``typing.Protocol``).  Any object with
    a matching ``emit()`` signature satisfies it via structural subtyping.

    Synchronous contract
    --------------------
    ``emit()`` is synchronous and MUST NOT block.  The bus adapter is
    responsible for internal buffering or async dispatch.  If the bus
    is unavailable, the adapter logs the failure and drops the delta.

    PLAN-01 clarification
    ---------------------
    Delta emission is NOT a SessionState write.  Deltas go to the Delta
    Bus (``k1.planner.delta.v1`` topic), which is a separate pub/sub
    channel.
    """

    def emit(self, delta: DeltaPayload) -> None:
        """Emit a progress delta to the Delta Bus.

        Fire-and-forget: this method MUST NOT raise, even on bus failure.

        Args:
            delta: ``DeltaPayload`` containing ``agent_id``,
                ``delta_type``, ``section``, ``data``, and ``trace_id``.
        """
        ...  # pragma: no cover


__all__ = ["IDeltaEmitPort"]
