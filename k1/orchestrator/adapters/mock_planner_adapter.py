"""
k1.orchestrator.adapters.mock_planner_adapter -- MockPlannerAdapter (6.1.10).

Test/mock adapter for IPlannerPort.

Design:
  - Scriptable: pre-configure plan results, failures, and micro-replan
    results per request_id.
  - Logs all request_plan and micro_replan calls for assertion.
  - request_plan() returns PlanAck(ACCEPTED/REJECTED) immediately.
  - Async plan delivery via callback simulates event-driven pattern
    (ADR-1.1.12) where CommittedPlan arrives via event bus.
  - cancel_plan() is a no-op (logged for assertion).

References:
  - Issue 6.1.10 in orchestrator-implementation-plan.md
  - k1/orchestrator/ports/planner_port.py (IPlannerPort)

Exports:
  MockPlannerAdapter
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Optional, Set

from k1.orchestrator.types import CommittedPlan, MicroReplanRequest, PlanAck, PlanRequest

# ---------------------------------------------------------------------------
# 6.1.10 -- MockPlannerAdapter
# ---------------------------------------------------------------------------


class MockPlannerAdapter:
    """
    Test IPlannerPort adapter with scriptable plans and failures.

    Pre-configure per-request_id behavior:
      - ``script_plan(request_id, plan)`` -- accept and optionally deliver plan
      - ``script_failure(request_id)`` -- reject with PlanAck(REJECTED)
      - ``script_micro_replan(request_id, plan)`` -- return CommittedPlan

    Plan delivery:
      If a ``plan_callback`` is provided to the constructor, scripted plans
      are delivered asynchronously via ``plan_callback(plan)`` after a short
      delay (simulates event-driven delivery per ADR-1.1.12).

    All calls are logged for test assertions.
    """

    def __init__(
        self,
        plan_callback: Optional[Callable[[CommittedPlan], Any]] = None,
    ) -> None:
        self.scripted_plans: Dict[str, CommittedPlan] = {}
        self.scripted_micro_replans: Dict[str, CommittedPlan] = {}
        self.scripted_failures: Set[str] = set()
        self.request_log: List[PlanRequest] = []
        self.micro_replan_log: List[MicroReplanRequest] = []
        self.cancel_log: List[str] = []
        self._plan_callback = plan_callback

    # ------------------------------------------------------------------
    # IPlannerPort.request_plan
    # ------------------------------------------------------------------

    async def request_plan(self, request: PlanRequest) -> PlanAck:
        """Request a plan. Returns ACCEPTED or REJECTED per scripts."""
        self.request_log.append(request)

        if request.request_id in self.scripted_failures:
            return PlanAck(request_id=request.request_id, status="REJECTED")

        ack = PlanAck(request_id=request.request_id, status="ACCEPTED")

        # If a plan is scripted and a callback exists, schedule async delivery
        if request.request_id in self.scripted_plans and self._plan_callback is not None:
            asyncio.ensure_future(self._deliver_plan(request.request_id))

        return ack

    # ------------------------------------------------------------------
    # IPlannerPort.cancel_plan
    # ------------------------------------------------------------------

    async def cancel_plan(self, request_id: str) -> None:
        """Cancel a plan request. No-op (logged for assertion)."""
        self.cancel_log.append(request_id)

    # ------------------------------------------------------------------
    # IPlannerPort.micro_replan
    # ------------------------------------------------------------------

    async def micro_replan(self, request: MicroReplanRequest) -> Optional[CommittedPlan]:
        """Return scripted micro-replan result or None."""
        self.micro_replan_log.append(request)

        if request.request_id in self.scripted_micro_replans:
            return self.scripted_micro_replans[request.request_id]

        return None

    # ------------------------------------------------------------------
    # Async plan delivery (simulates event-driven pattern)
    # ------------------------------------------------------------------

    async def _deliver_plan(self, request_id: str, delay_s: float = 0.01) -> None:
        """Deliver a scripted CommittedPlan via callback after a delay."""
        await asyncio.sleep(delay_s)
        plan = self.scripted_plans.get(request_id)
        if plan is not None and self._plan_callback is not None:
            callback_result = self._plan_callback(plan)
            # Support async callbacks
            if asyncio.iscoroutine(callback_result):
                await callback_result

    # ------------------------------------------------------------------
    # Test helpers -- scripting
    # ------------------------------------------------------------------

    def script_plan(self, request_id: str, plan: CommittedPlan) -> None:
        """Pre-configure a CommittedPlan for a request_id."""
        self.scripted_plans[request_id] = plan

    def script_failure(self, request_id: str) -> None:
        """Pre-configure a REJECTED response for a request_id."""
        self.scripted_failures.add(request_id)

    def script_micro_replan(self, request_id: str, plan: CommittedPlan) -> None:
        """Pre-configure a CommittedPlan for micro_replan by request_id."""
        self.scripted_micro_replans[request_id] = plan

    # ------------------------------------------------------------------
    # Test helpers -- assertions
    # ------------------------------------------------------------------

    def assert_plan_requested(self, count: int = 1) -> None:
        """Assert that request_plan was called exactly *count* times."""
        actual = len(self.request_log)
        assert actual == count, f"Expected {count} plan request(s), got {actual}"

    def assert_cancel_requested(self, request_id: str) -> None:
        """Assert that cancel_plan was called for request_id."""
        assert (
            request_id in self.cancel_log
        ), f"Expected cancel for {request_id}, got {self.cancel_log}"

    def assert_micro_replan_requested(self, count: int = 1) -> None:
        """Assert that micro_replan was called exactly *count* times."""
        actual = len(self.micro_replan_log)
        assert actual == count, f"Expected {count} micro_replan request(s), got {actual}"

    def reset(self) -> None:
        """Clear all scripts and logs."""
        self.scripted_plans.clear()
        self.scripted_micro_replans.clear()
        self.scripted_failures.clear()
        self.request_log.clear()
        self.micro_replan_log.clear()
        self.cancel_log.clear()
