"""E8.M2.2 — End-to-end planner clarification flow.

Verifies the planner's contract with the unified ``HumanInTheLoopService``:

  * The planner's pipeline holds the same kernel-level HIL instance.
  * ``ask_clarification`` round-trips through the bus and resolves with
    the simulator-supplied answer.
  * The clarification round budget (``hil_max_clarification_rounds``,
    default 2) is enforced per ``caller_key``: the third request without
    an intervening reset returns ``round_budget_exhausted=True``.
  * ``reset_round_budget(caller_key)`` (the hook the planner calls on
    ``LC_PLAN_START``) restores the budget for a new plan.

The ``StubProviderPlugin`` cannot drive a SKETCH/VALIDATE turn that
naturally produces ``needs_clarification=true``, so we exercise the
contract directly via the planner's HIL surface — the same path
``SketchService._execute_attempt`` takes when an LLM returns
``needs_clarification=true``. No mocks; only the user is simulated.
"""

from __future__ import annotations

import time

import pytest

from k1.hil.service import HumanInTheLoopService
from k1.hil.types import ClarificationRequest, HILKind


@pytest.mark.asyncio
async def test_planner_pipeline_holds_unified_hil(kernel_service) -> None:
    pipeline = kernel_service._planner._pipeline  # type: ignore[attr-defined]
    assert pipeline._hil_port is kernel_service.hil_service
    assert isinstance(pipeline._hil_port, HumanInTheLoopService)


@pytest.mark.asyncio
async def test_planner_clarification_round_trip(
    kernel_service, hil_user_simulator
) -> None:
    """``ask_clarification`` round-trips through the bus."""

    hil_user_simulator.script(
        HILKind.CLARIFICATION,
        lambda req: {"answer": "Tuesday at 3pm"},
    )
    pipeline = kernel_service._planner._pipeline  # type: ignore[attr-defined]
    req = ClarificationRequest(
        caller_key="planner:trace-rt",
        trace_id="trace-rt",
        question_context={"goal": "schedule meeting"},
        synthesize_with_llm=False,
        pre_formed_question="When works for you?",
        timeout_ms=2000,
    )
    t0 = time.monotonic()
    resp = await pipeline._hil_port.ask_clarification(req)
    elapsed_ms = (time.monotonic() - t0) * 1000.0

    assert resp.timed_out is False
    assert resp.round_budget_exhausted is False
    assert resp.answer == "Tuesday at 3pm"
    assert resp.hil_request_id
    assert elapsed_ms < 500.0, f"round-trip too slow: {elapsed_ms:.1f}ms"

    assert len(hil_user_simulator.received) == 1
    captured = hil_user_simulator.received[0]
    assert captured.kind is HILKind.CLARIFICATION
    assert captured.caller_key == "planner:trace-rt"
    assert captured.payload["question"] == "When works for you?"


@pytest.mark.asyncio
async def test_clarification_round_budget_enforced_and_reset(
    kernel_service, hil_user_simulator
) -> None:
    """3rd clarification (default budget=2) returns ``round_budget_exhausted=True``;
    ``reset_round_budget`` restores capacity."""

    assert kernel_service._config.hil_max_clarification_rounds == 2
    hil_user_simulator.script(
        HILKind.CLARIFICATION,
        lambda req: {"answer": "ok"},
    )
    hil = kernel_service.hil_service
    caller_key = "planner:trace-budget"

    def _req(idx: int) -> ClarificationRequest:
        return ClarificationRequest(
            caller_key=caller_key,
            trace_id=f"trace-budget-{idx}",
            question_context={"i": idx},
            synthesize_with_llm=False,
            pre_formed_question=f"q{idx}",
            timeout_ms=2000,
        )

    r1 = await hil.ask_clarification(_req(1))
    assert r1.timed_out is False
    assert r1.round_budget_exhausted is False
    assert r1.answer == "ok"

    r2 = await hil.ask_clarification(_req(2))
    assert r2.round_budget_exhausted is False
    assert r2.answer == "ok"

    # 3rd request must short-circuit on budget; simulator should NOT see it.
    received_before = len(hil_user_simulator.received)
    r3 = await hil.ask_clarification(_req(3))
    assert r3.round_budget_exhausted is True
    assert r3.answer is None
    assert r3.timed_out is False
    assert r3.hil_request_id == ""  # service returns sentinel id on exhaustion
    assert len(hil_user_simulator.received) == received_before

    # LC_PLAN_START hook resets and a new request flows again.
    hil.reset_round_budget(caller_key)
    r4 = await hil.ask_clarification(_req(4))
    assert r4.round_budget_exhausted is False
    assert r4.answer == "ok"


@pytest.mark.asyncio
async def test_clarification_timeout_returns_timed_out(
    kernel_service, hil_user_simulator
) -> None:
    """No script + short timeout → service returns ``timed_out=True``."""

    pipeline = kernel_service._planner._pipeline  # type: ignore[attr-defined]
    req = ClarificationRequest(
        caller_key="planner:trace-to",
        trace_id="trace-to",
        question_context={},
        synthesize_with_llm=False,
        pre_formed_question="ignored",
        timeout_ms=300,
    )
    resp = await pipeline._hil_port.ask_clarification(req)
    assert resp.timed_out is True
    assert resp.answer is None
    assert resp.round_budget_exhausted is False
