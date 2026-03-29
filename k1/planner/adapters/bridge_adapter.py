"""BridgeAdapter -- production K0 Bridge access adapter [F32].

Implements ``IBridgePort`` (Planner port SS15.6) by wrapping
Fabric's ``IBridgePort`` (5.1.3).

Adapter wiring (SS16.1.5, SS16.3):
    Planner IBridgePort -> BridgeAdapter -> Fabric IBridgePort

Design:
    - recall() -> Fabric bridge.query("memory.recall", selectors)
      then extract .data -> construct RecallResponse
    - persist_plan() -> Fabric bridge.send_command("memory.store", plan)
      fire-and-forget (SS9.3): plan validity does NOT depend on WAL write
    - Offline: recall returns empty RecallResponse, persist drops silently
    - All calls carry trace_id (FAB-09)

Import graph (Layer 2)
----------------------
k1.planner.adapters.bridge_adapter
  -> k1.planner.types         (RecallResponse)
  -> k1.orchestrator.types    (CommittedPlan)
  -> typing, logging
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from k1.planner.types import RecallResponse

logger = logging.getLogger(__name__)


class BridgeAdapter:
    """Production K0 Bridge adapter (SS16.1.5).

    Wraps the Fabric's ``IBridgePort`` to provide the Planner with
    ``recall()`` and ``persist_plan()`` operations against K0 memory.

    Offline handling:
        Before dispatching, checks ``_bridge.is_available()``.  If K0
        is unreachable:
        - ``recall()`` returns empty ``RecallResponse``
        - ``persist_plan()`` silently drops (WAL write is supplementary)
    """

    __slots__ = ("_bridge",)

    def __init__(self, bridge_port: Any) -> None:
        """Initialize BridgeAdapter.

        Args:
            bridge_port: Fabric ``IBridgePort`` instance (5.1.3) providing
                ``query()``, ``send_command()``, ``is_available()``.
        """
        self._bridge = bridge_port

    # ------------------------------------------------------------------
    # IBridgePort (Planner) implementation
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Check whether the K0 Bridge is reachable.

        Delegates to the underlying Fabric ``IBridgePort.is_available()``.

        Returns:
            ``True`` if K0 is online and accepting commands.
        """
        return self._bridge.is_available()

    async def recall(
        self,
        query: str,
        selectors: Optional[List[str]] = None,
        *,
        trace_id: str = "",
    ) -> RecallResponse:
        """Query K0 long-term memory for planning context.

        Translates to Fabric ``IBridgePort.query("memory.recall", ...)``.
        On offline or error, returns empty ``RecallResponse`` (degraded).

        Args:
            query: Natural-language recall query.
            selectors: Memory layer selectors (preferences, outcomes, etc.).
            trace_id: Distributed trace ID for observability.

        Returns:
            ``RecallResponse`` populated from ``BridgeCommandResult.data``.
        """
        if not self._bridge.is_available():
            logger.warning(
                "K0 offline, returning empty recall",
                extra={"trace_id": trace_id},
            )
            return RecallResponse(trace_id=trace_id)

        try:
            selector_dict: Dict[str, Any] = {
                "query": query,
            }
            if selectors:
                selector_dict["selectors"] = selectors

            result = await self._bridge.query(
                "memory.recall",
                selector_dict,
                trace_id=trace_id,
            )

            if not result.success:
                logger.warning(
                    "K0 recall failed: %s",
                    result.error_message,
                    extra={
                        "error_code": result.error_code,
                        "trace_id": trace_id,
                    },
                )
                return RecallResponse(trace_id=trace_id)

            # Extract facts and scores from BridgeCommandResult.data
            data = result.data or {}
            return RecallResponse(
                facts=data.get("facts", []),
                scores=data.get("scores", []),
                trace_id=trace_id,
            )
        except Exception:
            logger.exception(
                "recall raised, returning empty RecallResponse",
                extra={"trace_id": trace_id},
            )
            return RecallResponse(trace_id=trace_id)

    async def persist_plan(
        self,
        plan: Any,
        *,
        trace_id: str = "",
    ) -> None:
        """Persist committed plan to K0 WAL (fire-and-forget).

        SS9.3: plan validity does NOT depend on WAL success.  Plan is
        already delivered via the ``k1.planner.plan.ready.v1`` event.

        If K0 is offline, logs warning and returns silently.

        Args:
            plan: ``CommittedPlan`` instance.
            trace_id: Distributed trace ID for observability.
        """
        if not self._bridge.is_available():
            logger.warning(
                "K0 offline, dropping persist_plan",
                extra={"trace_id": trace_id},
            )
            return

        try:
            payload: Dict[str, Any] = (
                plan.to_dict() if hasattr(plan, "to_dict") else {"plan": str(plan)}
            )
            await self._bridge.send_command(
                "memory.store",
                payload,
                trace_id=trace_id,
            )
        except Exception:
            logger.exception(
                "persist_plan raised, dropping silently (fire-and-forget)",
                extra={"trace_id": trace_id},
            )


__all__ = ["BridgeAdapter"]
