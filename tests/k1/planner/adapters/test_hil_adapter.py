"""TestHILAdapter -- in-memory IHILPort for planner factory tests (E5.M1.4).

Satisfies `k1.kernel.ports.hil_port.IHILPort` structurally.

Behavior is fully deterministic and configurable per test:
  - default `ask_clarification` returns ClarificationResponse(answer=None, timed_out=True)
  - default `request_approval` returns ApprovalResponse(decision="approve")
  - tests can override with `set_clarification_response(...)`,
    `set_approval_response(...)`, or by enqueueing scripted responses.

Records all calls for assertion (`clarification_calls`, `approval_calls`,
`reset_calls`).

Round budget tracking is mirrored from HumanInTheLoopService semantics so
that planner tests exercising the budget gate behave the same as production.
"""

from __future__ import annotations

from collections import deque

from k1.hil.types import (
    ApprovalRequest,
    ApprovalResponse,
    CapabilityGateRequest,
    ClarificationRequest,
    ClarificationResponse,
    GateDecision,
    GateOutcome,
    NeedsHumanRequest,
    NeedsHumanResponse,
    OverrideRequest,
    OverrideResponse,
)


class TestHILAdapter:
    """In-memory IHILPort for tests."""

    def __init__(self, *, max_clarification_rounds: int = 2) -> None:
        self._max_clar = max_clarification_rounds
        self._budget: dict[str, int] = {}

        # Default scripted responses.
        self._default_clar = ClarificationResponse(
            hil_request_id="test-hil",
            answer=None,
            timed_out=True,
            round_budget_exhausted=False,
        )
        self._default_approval = ApprovalResponse(
            hil_request_id="test-hil",
            decision="approve",
            modifications=None,
            timed_out=False,
        )

        # Per-call scripted queues (FIFO).
        self._clar_queue: deque[ClarificationResponse] = deque()
        self._approval_queue: deque[ApprovalResponse] = deque()

        # Call recordings for assertions.
        self.clarification_calls: list[ClarificationRequest] = []
        self.approval_calls: list[ApprovalRequest] = []
        self.needs_human_calls: list[NeedsHumanRequest] = []
        self.override_calls: list[OverrideRequest] = []
        self.gate_calls: list[CapabilityGateRequest] = []
        self.reset_calls: list[str] = []
        self.shutdown_called: bool = False

    # ------------------------------------------------------------------
    # Test setup helpers
    # ------------------------------------------------------------------

    def set_default_clarification(self, resp: ClarificationResponse) -> None:
        self._default_clar = resp

    def set_default_approval(self, resp: ApprovalResponse) -> None:
        self._default_approval = resp

    def enqueue_clarification(self, resp: ClarificationResponse) -> None:
        self._clar_queue.append(resp)

    def enqueue_approval(self, resp: ApprovalResponse) -> None:
        self._approval_queue.append(resp)

    # ------------------------------------------------------------------
    # IHILPort implementation
    # ------------------------------------------------------------------

    async def ask_clarification(self, req: ClarificationRequest) -> ClarificationResponse:
        self.clarification_calls.append(req)
        used = self._budget.get(req.caller_key, 0)
        if used >= self._max_clar:
            return ClarificationResponse(
                hil_request_id="",
                answer=None,
                timed_out=False,
                round_budget_exhausted=True,
            )
        self._budget[req.caller_key] = used + 1
        if self._clar_queue:
            return self._clar_queue.popleft()
        return self._default_clar

    async def request_approval(self, req: ApprovalRequest) -> ApprovalResponse:
        self.approval_calls.append(req)
        if self._approval_queue:
            return self._approval_queue.popleft()
        return self._default_approval

    async def needs_human(self, req: NeedsHumanRequest) -> NeedsHumanResponse:
        self.needs_human_calls.append(req)
        return NeedsHumanResponse(
            hil_request_id="test-hil",
            decision="timeout",
            resolution={},
            raw_user_text=None,
            timed_out=True,
        )

    async def request_override(self, req: OverrideRequest) -> OverrideResponse:
        self.override_calls.append(req)
        return OverrideResponse(
            hil_request_id="test-hil",
            choice="abort",
            selected_alternative=None,
            fallback_action=None,
            timed_out=True,
        )

    async def gate_capability(self, req: CapabilityGateRequest) -> GateDecision:
        self.gate_calls.append(req)
        return GateDecision(
            outcome=GateOutcome.ALLOW,
            hil_request_id=None,
            reason="test_adapter_default_allow",
            user_approved=None,
            audit_only=False,
        )

    def reset_round_budget(self, caller_key: str) -> None:
        self.reset_calls.append(caller_key)
        self._budget.pop(caller_key, None)

    async def shutdown(self) -> None:
        self.shutdown_called = True
