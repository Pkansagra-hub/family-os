"""Round budget enforcement tests for HumanInTheLoopService (E5.M1.2).

Verifies:
  - max_clarification_rounds is enforced per caller_key
  - reset_round_budget(caller_key) clears the counter for one caller only
  - separate caller_keys have independent budgets
  - exhausted budget returns ClarificationResponse(round_budget_exhausted=True)
    without publishing a request envelope
  - reset is sync and safe to call when caller has no recorded budget
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from k1.hil.config import HILConfig
from k1.hil.ledger import HILLedgerAdapter
from k1.hil.safety import SafetyBandPolicy
from k1.hil.service import HumanInTheLoopService
from k1.hil.topics import TOPIC_HIL_REQUEST, TOPIC_HIL_RESPONSE
from k1.hil.types import (
    ClarificationRequest,
    HILKind,
    HILResponseEnvelope,
)


class FakeBus:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []
        self.handlers: dict[str, list] = {}

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self.published.append((topic, dict(payload)))

    def subscribe(self, topic: str, handler: Any) -> tuple[str, Any]:
        self.handlers.setdefault(topic, []).append(handler)
        return (topic, handler)

    def unsubscribe(self, handle: tuple[str, Any]) -> None:
        topic, handler = handle
        self.handlers.get(topic, []).remove(handler)

    async def deliver_response(self, hil_id: str, payload: dict) -> None:
        env = HILResponseEnvelope(
            hil_request_id=hil_id,
            kind=HILKind.CLARIFICATION,
            responded_at_ms=2_000,
            payload=payload,
        )
        for h in list(self.handlers.get(TOPIC_HIL_RESPONSE, [])):
            await h(TOPIC_HIL_RESPONSE, env.to_dict())

    def request_envelopes(self) -> list[dict]:
        return [p for t, p in self.published if t == TOPIC_HIL_REQUEST]


def _svc(bus: FakeBus, *, config: HILConfig | None = None) -> HumanInTheLoopService:
    return HumanInTheLoopService(
        event_port=bus,
        ledger=HILLedgerAdapter(None),
        suspension_mgr=None,
        safety_policy=SafetyBandPolicy(),
        config=config or HILConfig(),
        llm_port=None,
    )


async def _drive(bus: FakeBus, answer: str = "ok") -> None:
    for _ in range(50):
        envs = bus.request_envelopes()
        if envs:
            await bus.deliver_response(envs[-1]["hil_request_id"], {"answer": answer})
            return
        await asyncio.sleep(0.01)
    raise RuntimeError("no request published")


def _req(caller_key: str = "planner:sketch:plan-1") -> ClarificationRequest:
    return ClarificationRequest(
        caller_key=caller_key,
        trace_id="t",
        pre_formed_question="?",
        synthesize_with_llm=False,
    )


async def test_max_rounds_enforced_per_caller_key() -> None:
    """After max_clarification_rounds calls succeed, next call returns
    round_budget_exhausted=True without publishing a request."""
    bus = FakeBus()
    svc = _svc(bus, config=HILConfig(max_clarification_rounds=2))

    # Round 1
    task = asyncio.create_task(svc.ask_clarification(_req()))
    await _drive(bus, "answer-1")
    r1 = await task
    assert r1.answer == "answer-1"
    assert r1.round_budget_exhausted is False

    # Round 2
    task = asyncio.create_task(svc.ask_clarification(_req()))
    await _drive(bus, "answer-2")
    r2 = await task
    assert r2.answer == "answer-2"
    assert r2.round_budget_exhausted is False

    # Round 3 (over budget) -- short-circuits, no publish, no LLM
    publish_count_before = len(bus.request_envelopes())
    r3 = await svc.ask_clarification(_req())
    assert r3.round_budget_exhausted is True
    assert r3.answer is None
    assert r3.timed_out is False
    assert len(bus.request_envelopes()) == publish_count_before


async def test_separate_caller_keys_have_independent_budgets() -> None:
    bus = FakeBus()
    svc = _svc(bus, config=HILConfig(max_clarification_rounds=1))

    # Caller A consumes its budget.
    task = asyncio.create_task(svc.ask_clarification(_req("planner:sketch:plan-A")))
    await _drive(bus, "a")
    await task
    r_a2 = await svc.ask_clarification(_req("planner:sketch:plan-A"))
    assert r_a2.round_budget_exhausted is True

    # Caller B still has its full budget.
    task = asyncio.create_task(svc.ask_clarification(_req("planner:sketch:plan-B")))
    await _drive(bus, "b")
    r_b = await task
    assert r_b.answer == "b"
    assert r_b.round_budget_exhausted is False


async def test_reset_round_budget_clears_single_caller() -> None:
    bus = FakeBus()
    svc = _svc(bus, config=HILConfig(max_clarification_rounds=1))

    # Exhaust caller A.
    task = asyncio.create_task(svc.ask_clarification(_req("planner:sketch:plan-A")))
    await _drive(bus, "a1")
    await task
    r_exhausted = await svc.ask_clarification(_req("planner:sketch:plan-A"))
    assert r_exhausted.round_budget_exhausted is True

    # Reset caller A only.
    svc.reset_round_budget("planner:sketch:plan-A")

    # Caller A should be able to ask again.
    task = asyncio.create_task(svc.ask_clarification(_req("planner:sketch:plan-A")))
    await _drive(bus, "a2")
    r_after_reset = await task
    assert r_after_reset.answer == "a2"
    assert r_after_reset.round_budget_exhausted is False


async def test_reset_round_budget_does_not_affect_other_callers() -> None:
    bus = FakeBus()
    svc = _svc(bus, config=HILConfig(max_clarification_rounds=1))

    # Exhaust both A and B.
    task = asyncio.create_task(svc.ask_clarification(_req("planner:sketch:plan-A")))
    await _drive(bus, "a")
    await task
    task = asyncio.create_task(svc.ask_clarification(_req("planner:sketch:plan-B")))
    await _drive(bus, "b")
    await task

    # Reset only A.
    svc.reset_round_budget("planner:sketch:plan-A")

    # B remains exhausted.
    r_b = await svc.ask_clarification(_req("planner:sketch:plan-B"))
    assert r_b.round_budget_exhausted is True

    # A can ask again.
    task = asyncio.create_task(svc.ask_clarification(_req("planner:sketch:plan-A")))
    await _drive(bus, "a2")
    r_a = await task
    assert r_a.round_budget_exhausted is False


def test_reset_round_budget_is_sync_and_idempotent_for_unknown_caller() -> None:
    """reset_round_budget on a caller that was never seen is a no-op."""
    bus = FakeBus()
    svc = _svc(bus)
    # Sync call -- no await; must not raise.
    svc.reset_round_budget("planner:sketch:never-seen")
    svc.reset_round_budget("planner:sketch:never-seen")  # idempotent
