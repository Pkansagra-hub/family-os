"""IBridgePort -- Planner K0 Bridge access protocol [F16].

The Bridge port provides access to K0 via the Cross-Kernel Bridge.
The Planner uses it for two operations:

1. Reading long-term memory (recall) -- SKETCH stage only
2. Persisting committed plans (WAL write) -- COMMIT stage

Design decisions (SS15.6)
-------------------------
- ``recall()`` returns ``RecallResponse`` (Planner abstraction over
  ``BridgeCommandResult.data``).
- ``persist_plan()`` is fire-and-forget: plan validity does NOT depend on
  WAL success (SS9.3).
- Offline handling: when K0 is unavailable, ``recall()`` returns an empty
  ``RecallResponse`` and ``persist_plan()`` silently drops.  Planning
  quality degrades but does NOT fail.

Callers
-------
- ToolCallRouter: ``recall()`` via ``recall_for_planning`` tool (SKETCH)
- CommitService: ``persist_plan()`` after plan assembly

Adapter: BridgeAdapter [F32] wraps K0 Bridge client
         recall <100ms, persist_plan fire-and-forget

Import graph (Layer 1)
----------------------
k1.planner.ports.bridge_port
  -> k1.orchestrator.types  (CommittedPlan)
  -> k1.planner.types       (RecallResponse)
  -> typing
"""

from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from k1.orchestrator.types import CommittedPlan
from k1.planner.types import RecallResponse


@runtime_checkable
class IPlannerWritePort(Protocol):
    """K0 Bridge access port -- recall and persist.

    This is a structural protocol (``typing.Protocol``).  Any object with
    matching method signatures satisfies it via structural subtyping.

    Offline handling
    ----------------
    The adapter checks ``is_available()`` on the underlying Fabric
    ``IBridgePort`` before dispatching.  If K0 is offline:

    - ``recall()`` returns empty ``RecallResponse`` (no long-term context)
    - ``persist_plan()`` silently drops (plan still delivered via event bus)

    The Planner's pipeline continues in both cases (graceful degradation).
    """

    async def recall(
        self,
        query: str,
        selectors: Optional[List[str]] = None,
        *,
        trace_id: str = "",
    ) -> RecallResponse:
        """Query K0 long-term memory for planning context.

        Returns facts, prior outcomes, and preferences relevant to the
        planning query.  Used by ToolCallRouter during SKETCH stage.

        Args:
            query: Natural-language recall query.
            selectors: Memory layer selectors to filter recall
                (e.g. ``["preferences", "outcomes", "constraints"]``).
            trace_id: Distributed trace ID for observability.

        Returns:
            ``RecallResponse`` with matched facts and similarity scores.
            Empty response if K0 is offline.
        """
        ...  # pragma: no cover

    async def persist_plan(
        self,
        plan: CommittedPlan,
        *,
        trace_id: str = "",
    ) -> None:
        """Persist committed plan to K0 WAL.

        Fire-and-forget: the plan is already delivered via
        ``k1.planner.plan.ready.v1`` event.  WAL persistence is
        supplementary.  If K0 is offline, the adapter logs a warning
        and returns silently.

        Args:
            plan: The committed plan to persist.
            trace_id: Distributed trace ID for observability.
        """
        ...  # pragma: no cover


__all__ = ["IPlannerWritePort"]
