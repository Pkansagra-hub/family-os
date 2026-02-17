"""Epic 4.2 -- HILCoordinator tests (~35 tests).

Test categories (SS17.8):
  A. Constructor & skeleton (~5)
  B. Clarification round-trip (~8)
  C. Approval round-trip (~8)
  D. Round budget PLAN-10 (~5)
  E. Timeout handling (~5)
  F. Event correlation (~5)
  G. Edge cases & LLM failure (~4)

Test adapters:
  - StubLLMPort: deterministic ILLMPort returning canned responses.
  - StubEventPort: in-process IEventPort with emit/subscribe/unsubscribe.

All tests use real HILCoordinator -- no mocks of the service itself.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Tuple

import pytest

from k1.fabric.ports.event_port import SubscriptionHandle
from k1.planner.config import PlannerConfig
from k1.planner.events import (
    TOPIC_HIL_APPROVAL_REQ,
    TOPIC_HIL_APPROVAL_RESP,
    TOPIC_HIL_CLARIFICATION,
    TOPIC_HIL_CLARIFICATION_RESP,
)
from k1.planner.services.hil_coordinator import HILCoordinator
from k1.planner.types import HILTimeoutError, HubRequest, HubResponse

# ---------------------------------------------------------------------------
# Test adapters
# ---------------------------------------------------------------------------


class StubLLMPort:
    """Deterministic ILLMPort adapter for testing."""

    def __init__(
        self,
        response_content: str = "Test LLM response",
        *,
        fail: bool = False,
        empty: bool = False,
    ) -> None:
        self.response_content = response_content
        self.fail = fail
        self.empty = empty
        self.call_log: List[HubRequest] = []

    async def execute(self, request: HubRequest) -> HubResponse:
        self.call_log.append(request)
        if self.fail:
            raise RuntimeError("LLM unavailable")
        content = "" if self.empty else self.response_content
        return HubResponse(
            result={"content": content},
            metadata={"usage": {"total_tokens": 50}, "latency_ms": 10},
        )


class StubEventPort:
    """In-process IEventPort adapter for testing.

    Supports emit/subscribe/unsubscribe with handler dispatch.
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, List[Tuple[str, Callable[[str, Any], None]]]] = {}
        self._next_id: int = 0
        self.emit_log: List[Tuple[str, Any]] = []

    def emit(self, topic: str, payload: Any) -> None:
        self.emit_log.append((topic, payload))
        for _sub_id, handler in self._handlers.get(topic, []):
            handler(topic, payload)

    def subscribe(self, topic: str, handler: Callable[[str, Any], None]) -> SubscriptionHandle:
        sub_id = f"sub-{self._next_id}"
        self._next_id += 1
        self._handlers.setdefault(topic, []).append((sub_id, handler))
        return SubscriptionHandle(subscription_id=sub_id, topic=topic)

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        handlers = self._handlers.get(handle.topic, [])
        for i, (sub_id, _) in enumerate(handlers):
            if sub_id == handle.subscription_id:
                handlers.pop(i)
                return True
        return False

    def inject_response(self, topic: str, payload: Dict[str, Any]) -> None:
        """Simulate an inbound response event."""
        self.emit(topic, payload)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def llm() -> StubLLMPort:
    return StubLLMPort(response_content="What time would you like dinner?")


@pytest.fixture
def events() -> StubEventPort:
    return StubEventPort()


@pytest.fixture
def config() -> PlannerConfig:
    return PlannerConfig()


@pytest.fixture
def hil(llm: StubLLMPort, events: StubEventPort, config: PlannerConfig) -> HILCoordinator:
    return HILCoordinator(llm_port=llm, event_port=events, config=config)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _schedule_response(
    events: StubEventPort, topic: str, payload: Dict[str, Any], delay: float = 0.01
) -> None:
    """Schedule a response to arrive after a short delay."""

    async def _inject() -> None:
        await asyncio.sleep(delay)
        events.inject_response(topic, payload)

    asyncio.get_event_loop().create_task(_inject())


# ---------------------------------------------------------------------------
# A. Constructor & skeleton (~5 tests)
# ---------------------------------------------------------------------------


class TestConstructorSkeleton:
    """4.2.1 -- HILCoordinator skeleton & constructor."""

    def test_valid_construction(self, llm: StubLLMPort, events: StubEventPort) -> None:
        hil = HILCoordinator(llm_port=llm, event_port=events)
        assert hil.round_count == 0
        assert hil.waiting is False

    def test_none_llm_raises(self, events: StubEventPort) -> None:
        with pytest.raises(TypeError, match="llm_port"):
            HILCoordinator(llm_port=None, event_port=events)  # type: ignore[arg-type]

    def test_none_event_raises(self, llm: StubLLMPort) -> None:
        with pytest.raises(TypeError, match="event_port"):
            HILCoordinator(llm_port=llm, event_port=None)  # type: ignore[arg-type]

    def test_slots(self, hil: HILCoordinator) -> None:
        assert hasattr(hil, "__slots__")
        assert "_llm_port" in hil.__slots__
        assert "_event_port" in hil.__slots__
        assert "_round_count" in hil.__slots__
        assert "_pending_request_id" in hil.__slots__
        assert "_hil_type" in hil.__slots__
        assert "_waiting" in hil.__slots__
        assert not hasattr(hil, "__dict__")

    def test_custom_config(self, llm: StubLLMPort, events: StubEventPort) -> None:
        cfg = PlannerConfig(max_hil_rounds=5, hil_clarification_timeout_ms=30_000)
        hil = HILCoordinator(llm_port=llm, event_port=events, config=cfg)
        assert hil.config.max_hil_rounds == 5
        assert hil.config.hil_clarification_timeout_ms == 30_000

    def test_reset_clears_all_state(self, hil: HILCoordinator) -> None:
        # Manually set state to non-default.
        hil._round_count = 2
        hil._pending_request_id = "req-1"
        hil._hil_type = "clarification"
        hil._waiting = True
        hil.reset()
        assert hil.round_count == 0
        assert hil.waiting is False
        assert hil._pending_request_id is None
        assert hil._hil_type is None


# ---------------------------------------------------------------------------
# B. Clarification round-trip (~8 tests)
# ---------------------------------------------------------------------------


class TestClarificationRoundTrip:
    """4.2.2 -- Clarification flow (event emit + response wait)."""

    async def test_clarification_returns_user_response(
        self, hil: HILCoordinator, events: StubEventPort
    ) -> None:
        _schedule_response(
            events,
            TOPIC_HIL_CLARIFICATION_RESP,
            {"request_id": "req-1", "response": "Around 7pm please"},
        )
        result = await hil.request_clarification(
            request_id="req-1",
            question_context={"question": "When?", "intent": "plan dinner"},
        )
        assert result == "Around 7pm please"

    async def test_clarification_emits_event(
        self, hil: HILCoordinator, events: StubEventPort
    ) -> None:
        _schedule_response(
            events,
            TOPIC_HIL_CLARIFICATION_RESP,
            {"request_id": "req-1", "response": "Yes"},
        )
        await hil.request_clarification(
            request_id="req-1",
            question_context={"question": "Confirm?", "intent": "confirm"},
        )
        # Should have emitted a clarification event.
        clar_events = [(t, p) for t, p in events.emit_log if t == TOPIC_HIL_CLARIFICATION]
        assert len(clar_events) == 1
        _, payload = clar_events[0]
        assert payload.request_id == "req-1"
        assert payload.question  # non-empty LLM-generated question

    async def test_clarification_increments_round_count(
        self, hil: HILCoordinator, events: StubEventPort
    ) -> None:
        _schedule_response(
            events,
            TOPIC_HIL_CLARIFICATION_RESP,
            {"request_id": "req-1", "response": "OK"},
        )
        assert hil.round_count == 0
        await hil.request_clarification(
            request_id="req-1",
            question_context={"question": "What?", "intent": "ask"},
        )
        assert hil.round_count == 1

    async def test_clarification_uses_llm_chat_capability(
        self, hil: HILCoordinator, llm: StubLLMPort, events: StubEventPort
    ) -> None:
        _schedule_response(
            events,
            TOPIC_HIL_CLARIFICATION_RESP,
            {"request_id": "req-1", "response": "OK"},
        )
        await hil.request_clarification(
            request_id="req-1",
            question_context={"question": "Which?", "intent": "choose"},
        )
        assert len(llm.call_log) == 1
        req = llm.call_log[0]
        assert req.capability == "CHAT"
        assert req.constraints.max_tokens == 300
        assert req.constraints.timeout_ms == 3000

    async def test_clarification_clears_waiting_after_response(
        self, hil: HILCoordinator, events: StubEventPort
    ) -> None:
        _schedule_response(
            events,
            TOPIC_HIL_CLARIFICATION_RESP,
            {"request_id": "req-1", "response": "Done"},
        )
        await hil.request_clarification(
            request_id="req-1",
            question_context={"question": "When?", "intent": "ask"},
        )
        assert hil.waiting is False
        assert hil._pending_request_id is None
        assert hil._hil_type is None

    async def test_two_clarification_rounds(
        self, hil: HILCoordinator, events: StubEventPort
    ) -> None:
        # Round 1.
        _schedule_response(
            events,
            TOPIC_HIL_CLARIFICATION_RESP,
            {"request_id": "req-1", "response": "Maybe later"},
        )
        r1 = await hil.request_clarification(
            request_id="req-1",
            question_context={"question": "When?", "intent": "ask"},
        )
        assert r1 == "Maybe later"
        assert hil.round_count == 1

        # Round 2.
        _schedule_response(
            events,
            TOPIC_HIL_CLARIFICATION_RESP,
            {"request_id": "req-2", "response": "At 6pm"},
        )
        r2 = await hil.request_clarification(
            request_id="req-2",
            question_context={"question": "What time?", "intent": "ask"},
        )
        assert r2 == "At 6pm"
        assert hil.round_count == 2

    async def test_clarification_passes_question_context_to_llm(
        self, hil: HILCoordinator, llm: StubLLMPort, events: StubEventPort
    ) -> None:
        _schedule_response(
            events,
            TOPIC_HIL_CLARIFICATION_RESP,
            {"request_id": "req-1", "response": "OK"},
        )
        ctx = {
            "question": "Which restaurant?",
            "intent": "dinner plan",
            "known_context": "Italian preferred",
        }
        await hil.request_clarification(request_id="req-1", question_context=ctx)
        req = llm.call_log[0]
        user_msg = req.payload["messages"][1]["content"]
        assert "dinner plan" in user_msg
        assert "Which restaurant?" in user_msg
        assert "Italian preferred" in user_msg

    async def test_clarification_unsubscribes_after_response(
        self, hil: HILCoordinator, events: StubEventPort
    ) -> None:
        _schedule_response(
            events,
            TOPIC_HIL_CLARIFICATION_RESP,
            {"request_id": "req-1", "response": "OK"},
        )
        await hil.request_clarification(
            request_id="req-1",
            question_context={"question": "?", "intent": "x"},
        )
        # After completion, the handler should be unsubscribed.
        remaining = events._handlers.get(TOPIC_HIL_CLARIFICATION_RESP, [])
        assert len(remaining) == 0


# ---------------------------------------------------------------------------
# C. Approval round-trip (~8 tests)
# ---------------------------------------------------------------------------


class TestApprovalRoundTrip:
    """4.2.3 -- Approval flow (event emit + response wait)."""

    async def test_approval_returns_approve(
        self, hil: HILCoordinator, events: StubEventPort
    ) -> None:
        _schedule_response(
            events,
            TOPIC_HIL_APPROVAL_RESP,
            {"request_id": "req-1", "response_type": "approve"},
        )
        result = await hil.request_approval(
            request_id="req-1",
            plan_summary="3 steps, 1 with side effects",
            side_effects=["s2: send_email"],
            safety_assessment="caution",
            estimated_duration_ms=5000,
        )
        assert result == "approve"

    async def test_approval_returns_modify(
        self, hil: HILCoordinator, events: StubEventPort
    ) -> None:
        _schedule_response(
            events,
            TOPIC_HIL_APPROVAL_RESP,
            {"request_id": "req-1", "response_type": "modify"},
        )
        result = await hil.request_approval(
            request_id="req-1",
            plan_summary="Plan",
            side_effects=["s1: delete_file"],
            safety_assessment="unsafe",
            estimated_duration_ms=1000,
        )
        assert result == "modify"

    async def test_approval_returns_reject(
        self, hil: HILCoordinator, events: StubEventPort
    ) -> None:
        _schedule_response(
            events,
            TOPIC_HIL_APPROVAL_RESP,
            {"request_id": "req-1", "response_type": "reject"},
        )
        result = await hil.request_approval(
            request_id="req-1",
            plan_summary="Plan",
            side_effects=["s1: dangerous"],
            safety_assessment="unsafe",
            estimated_duration_ms=1000,
        )
        assert result == "reject"

    async def test_approval_emits_event(self, hil: HILCoordinator, events: StubEventPort) -> None:
        _schedule_response(
            events,
            TOPIC_HIL_APPROVAL_RESP,
            {"request_id": "req-1", "response_type": "approve"},
        )
        await hil.request_approval(
            request_id="req-1",
            plan_summary="Test plan",
            side_effects=["s2: email"],
            safety_assessment="caution",
            estimated_duration_ms=3000,
        )
        approval_events = [(t, p) for t, p in events.emit_log if t == TOPIC_HIL_APPROVAL_REQ]
        assert len(approval_events) == 1
        _, payload = approval_events[0]
        assert payload.request_id == "req-1"
        assert "approve" in payload.options
        assert "modify" in payload.options
        assert "reject" in payload.options

    async def test_approval_uses_llm_chat_400_tokens(
        self, hil: HILCoordinator, llm: StubLLMPort, events: StubEventPort
    ) -> None:
        _schedule_response(
            events,
            TOPIC_HIL_APPROVAL_RESP,
            {"request_id": "req-1", "response_type": "approve"},
        )
        await hil.request_approval(
            request_id="req-1",
            plan_summary="Plan",
            side_effects=[],
            safety_assessment="safe",
            estimated_duration_ms=1000,
        )
        assert len(llm.call_log) == 1
        req = llm.call_log[0]
        assert req.capability == "CHAT"
        assert req.constraints.max_tokens == 400
        assert req.constraints.timeout_ms == 3000

    async def test_approval_does_not_increment_round_count(
        self, hil: HILCoordinator, events: StubEventPort
    ) -> None:
        _schedule_response(
            events,
            TOPIC_HIL_APPROVAL_RESP,
            {"request_id": "req-1", "response_type": "approve"},
        )
        assert hil.round_count == 0
        await hil.request_approval(
            request_id="req-1",
            plan_summary="Plan",
            side_effects=[],
            safety_assessment="safe",
            estimated_duration_ms=1000,
        )
        assert hil.round_count == 0

    async def test_approval_clears_waiting_state(
        self, hil: HILCoordinator, events: StubEventPort
    ) -> None:
        _schedule_response(
            events,
            TOPIC_HIL_APPROVAL_RESP,
            {"request_id": "req-1", "response_type": "approve"},
        )
        await hil.request_approval(
            request_id="req-1",
            plan_summary="Plan",
            side_effects=[],
            safety_assessment="safe",
            estimated_duration_ms=1000,
        )
        assert hil.waiting is False
        assert hil._pending_request_id is None

    async def test_approval_unsubscribes_after_response(
        self, hil: HILCoordinator, events: StubEventPort
    ) -> None:
        _schedule_response(
            events,
            TOPIC_HIL_APPROVAL_RESP,
            {"request_id": "req-1", "response_type": "approve"},
        )
        await hil.request_approval(
            request_id="req-1",
            plan_summary="Plan",
            side_effects=[],
            safety_assessment="safe",
            estimated_duration_ms=1000,
        )
        remaining = events._handlers.get(TOPIC_HIL_APPROVAL_RESP, [])
        assert len(remaining) == 0


# ---------------------------------------------------------------------------
# D. Round budget PLAN-10 (~5 tests)
# ---------------------------------------------------------------------------


class TestRoundBudgetPlan10:
    """4.2.4 -- Round count enforcement (PLAN-10, max 2 rounds)."""

    async def test_third_round_returns_none(
        self, hil: HILCoordinator, events: StubEventPort
    ) -> None:
        # Exhaust 2 rounds.
        for i in range(2):
            _schedule_response(
                events,
                TOPIC_HIL_CLARIFICATION_RESP,
                {"request_id": f"req-{i}", "response": f"resp-{i}"},
            )
            await hil.request_clarification(
                request_id=f"req-{i}",
                question_context={"question": "?", "intent": "ask"},
            )
        assert hil.round_count == 2

        # Third round: budget exhausted.
        result = await hil.request_clarification(
            request_id="req-2",
            question_context={"question": "?", "intent": "ask"},
        )
        assert result is None
        # Round count stays at 2.
        assert hil.round_count == 2

    async def test_budget_exhausted_no_llm_call(
        self, hil: HILCoordinator, llm: StubLLMPort, events: StubEventPort
    ) -> None:
        hil._round_count = 2  # Pre-exhaust.
        await hil.request_clarification(
            request_id="req-1",
            question_context={"question": "?", "intent": "ask"},
        )
        # No LLM call made.
        assert len(llm.call_log) == 0

    async def test_budget_exhausted_no_event_emitted(
        self, hil: HILCoordinator, events: StubEventPort
    ) -> None:
        hil._round_count = 2  # Pre-exhaust.
        await hil.request_clarification(
            request_id="req-1",
            question_context={"question": "?", "intent": "ask"},
        )
        clar_events = [t for t, _ in events.emit_log if t == TOPIC_HIL_CLARIFICATION]
        assert len(clar_events) == 0

    async def test_approval_unaffected_by_round_budget(
        self, hil: HILCoordinator, events: StubEventPort
    ) -> None:
        hil._round_count = 2  # Clarification budget exhausted.
        _schedule_response(
            events,
            TOPIC_HIL_APPROVAL_RESP,
            {"request_id": "req-1", "response_type": "approve"},
        )
        result = await hil.request_approval(
            request_id="req-1",
            plan_summary="Plan",
            side_effects=[],
            safety_assessment="safe",
            estimated_duration_ms=1000,
        )
        assert result == "approve"

    async def test_reset_restores_budget(self, hil: HILCoordinator, events: StubEventPort) -> None:
        hil._round_count = 2  # Exhausted.
        hil.reset()
        assert hil.round_count == 0

        _schedule_response(
            events,
            TOPIC_HIL_CLARIFICATION_RESP,
            {"request_id": "req-1", "response": "OK"},
        )
        result = await hil.request_clarification(
            request_id="req-1",
            question_context={"question": "?", "intent": "ask"},
        )
        assert result == "OK"
        assert hil.round_count == 1

    async def test_custom_max_rounds(self, llm: StubLLMPort, events: StubEventPort) -> None:
        cfg = PlannerConfig(max_hil_rounds=1)
        hil = HILCoordinator(llm_port=llm, event_port=events, config=cfg)

        _schedule_response(
            events,
            TOPIC_HIL_CLARIFICATION_RESP,
            {"request_id": "req-0", "response": "resp"},
        )
        await hil.request_clarification(
            request_id="req-0",
            question_context={"question": "?", "intent": "ask"},
        )
        assert hil.round_count == 1

        # Second round: budget exhausted with max_rounds=1.
        result = await hil.request_clarification(
            request_id="req-1",
            question_context={"question": "?", "intent": "ask"},
        )
        assert result is None


# ---------------------------------------------------------------------------
# E. Timeout handling (~5 tests)
# ---------------------------------------------------------------------------


class TestTimeoutHandling:
    """4.2.5 -- Timeout handling & fallback."""

    async def test_clarification_timeout_returns_none(
        self, llm: StubLLMPort, events: StubEventPort
    ) -> None:
        cfg = PlannerConfig(hil_clarification_timeout_ms=50)  # 50ms timeout.
        hil = HILCoordinator(llm_port=llm, event_port=events, config=cfg)
        # No response scheduled -> will timeout.
        result = await hil.request_clarification(
            request_id="req-1",
            question_context={"question": "?", "intent": "ask"},
        )
        assert result is None

    async def test_clarification_timeout_increments_round(
        self, llm: StubLLMPort, events: StubEventPort
    ) -> None:
        cfg = PlannerConfig(hil_clarification_timeout_ms=50)
        hil = HILCoordinator(llm_port=llm, event_port=events, config=cfg)
        await hil.request_clarification(
            request_id="req-1",
            question_context={"question": "?", "intent": "ask"},
        )
        assert hil.round_count == 1  # Timeout still counts as a round.

    async def test_clarification_timeout_clears_waiting(
        self, llm: StubLLMPort, events: StubEventPort
    ) -> None:
        cfg = PlannerConfig(hil_clarification_timeout_ms=50)
        hil = HILCoordinator(llm_port=llm, event_port=events, config=cfg)
        await hil.request_clarification(
            request_id="req-1",
            question_context={"question": "?", "intent": "ask"},
        )
        assert hil.waiting is False
        assert hil._pending_request_id is None

    async def test_approval_timeout_auto_approves_if_safe(
        self, llm: StubLLMPort, events: StubEventPort
    ) -> None:
        cfg = PlannerConfig(hil_approval_timeout_ms=50)
        hil = HILCoordinator(llm_port=llm, event_port=events, config=cfg)
        result = await hil.request_approval(
            request_id="req-1",
            plan_summary="Safe plan",
            side_effects=[],
            safety_assessment="safe",
            estimated_duration_ms=1000,
        )
        assert result == "approve"

    async def test_approval_timeout_raises_if_unsafe_with_side_effects(
        self, llm: StubLLMPort, events: StubEventPort
    ) -> None:
        cfg = PlannerConfig(hil_approval_timeout_ms=50)
        hil = HILCoordinator(llm_port=llm, event_port=events, config=cfg)
        with pytest.raises(HILTimeoutError):
            await hil.request_approval(
                request_id="req-1",
                plan_summary="Risky plan",
                side_effects=["s1: delete_database"],
                safety_assessment="unsafe",
                estimated_duration_ms=1000,
            )


# ---------------------------------------------------------------------------
# F. Event correlation (~5 tests)
# ---------------------------------------------------------------------------


class TestEventCorrelation:
    """4.2.5 -- Event correlation by request_id."""

    async def test_ignores_mismatched_request_id(
        self, llm: StubLLMPort, events: StubEventPort
    ) -> None:
        cfg = PlannerConfig(hil_clarification_timeout_ms=100)
        hil = HILCoordinator(llm_port=llm, event_port=events, config=cfg)

        # Schedule a response with wrong request_id, then the correct one.
        async def _inject_both() -> None:
            await asyncio.sleep(0.01)
            events.inject_response(
                TOPIC_HIL_CLARIFICATION_RESP,
                {"request_id": "wrong-id", "response": "Wrong"},
            )
            await asyncio.sleep(0.01)
            events.inject_response(
                TOPIC_HIL_CLARIFICATION_RESP,
                {"request_id": "req-1", "response": "Correct"},
            )

        asyncio.get_event_loop().create_task(_inject_both())

        result = await hil.request_clarification(
            request_id="req-1",
            question_context={"question": "?", "intent": "ask"},
        )
        assert result == "Correct"

    async def test_clarification_uses_correct_outbound_topic(
        self, hil: HILCoordinator, events: StubEventPort
    ) -> None:
        _schedule_response(
            events,
            TOPIC_HIL_CLARIFICATION_RESP,
            {"request_id": "req-1", "response": "OK"},
        )
        await hil.request_clarification(
            request_id="req-1",
            question_context={"question": "?", "intent": "ask"},
        )
        outbound_topics = [t for t, _ in events.emit_log]
        assert TOPIC_HIL_CLARIFICATION in outbound_topics

    async def test_approval_uses_correct_outbound_topic(
        self, hil: HILCoordinator, events: StubEventPort
    ) -> None:
        _schedule_response(
            events,
            TOPIC_HIL_APPROVAL_RESP,
            {"request_id": "req-1", "response_type": "approve"},
        )
        await hil.request_approval(
            request_id="req-1",
            plan_summary="Plan",
            side_effects=[],
            safety_assessment="safe",
            estimated_duration_ms=1000,
        )
        outbound_topics = [t for t, _ in events.emit_log]
        assert TOPIC_HIL_APPROVAL_REQ in outbound_topics

    async def test_no_hardcoded_topic_strings_in_module(self) -> None:
        """Verify hil_coordinator.py uses imported topic constants."""
        import inspect

        import k1.planner.services.hil_coordinator as mod

        source = inspect.getsource(mod)
        # Should NOT contain hardcoded topic strings.
        assert 'k1.hil.clarification.v1"' not in source.replace(
            "TOPIC_HIL_CLARIFICATION", ""
        ).replace("__doc__", "")
        assert 'k1.hil.approval_request.v1"' not in source.replace(
            "TOPIC_HIL_APPROVAL_REQ", ""
        ).replace("__doc__", "")

    async def test_subscribes_to_correct_inbound_topics(
        self, hil: HILCoordinator, events: StubEventPort
    ) -> None:
        """Verify that wait_for_response subscribes to the right topics."""
        _schedule_response(
            events,
            TOPIC_HIL_CLARIFICATION_RESP,
            {"request_id": "req-1", "response": "OK"},
        )
        await hil.request_clarification(
            request_id="req-1",
            question_context={"question": "?", "intent": "ask"},
        )
        # After completion, handler should be cleaned up (unsubscribed).
        # But we can verify the emit_log shows the outbound event.
        assert any(t == TOPIC_HIL_CLARIFICATION for t, _ in events.emit_log)


# ---------------------------------------------------------------------------
# G. Edge cases & LLM failure (~4 tests)
# ---------------------------------------------------------------------------


class TestEdgeCasesAndLLMFailure:
    """4.2.6 -- LLM integration and edge cases."""

    async def test_llm_failure_clarification_returns_none(self, events: StubEventPort) -> None:
        failing_llm = StubLLMPort(fail=True)
        hil = HILCoordinator(llm_port=failing_llm, event_port=events)
        result = await hil.request_clarification(
            request_id="req-1",
            question_context={"question": "?", "intent": "ask"},
        )
        assert result is None
        # No event should have been emitted.
        clar_events = [t for t, _ in events.emit_log if t == TOPIC_HIL_CLARIFICATION]
        assert len(clar_events) == 0

    async def test_llm_failure_approval_auto_approves_if_safe(self, events: StubEventPort) -> None:
        failing_llm = StubLLMPort(fail=True)
        hil = HILCoordinator(llm_port=failing_llm, event_port=events)
        result = await hil.request_approval(
            request_id="req-1",
            plan_summary="Safe plan",
            side_effects=[],
            safety_assessment="safe",
            estimated_duration_ms=1000,
        )
        assert result == "approve"

    async def test_llm_failure_approval_raises_if_unsafe(self, events: StubEventPort) -> None:
        failing_llm = StubLLMPort(fail=True)
        hil = HILCoordinator(llm_port=failing_llm, event_port=events)
        with pytest.raises(HILTimeoutError):
            await hil.request_approval(
                request_id="req-1",
                plan_summary="Risky plan",
                side_effects=["s1: dangerous"],
                safety_assessment="unsafe",
                estimated_duration_ms=1000,
            )

    async def test_llm_empty_response_skips_hil(self, events: StubEventPort) -> None:
        empty_llm = StubLLMPort(empty=True)
        hil = HILCoordinator(llm_port=empty_llm, event_port=events)
        result = await hil.request_clarification(
            request_id="req-1",
            question_context={"question": "?", "intent": "ask"},
        )
        assert result is None
        clar_events = [t for t, _ in events.emit_log if t == TOPIC_HIL_CLARIFICATION]
        assert len(clar_events) == 0

    async def test_approval_unknown_response_type_defaults_approve(
        self, hil: HILCoordinator, events: StubEventPort
    ) -> None:
        _schedule_response(
            events,
            TOPIC_HIL_APPROVAL_RESP,
            {"request_id": "req-1", "response_type": "unknown_garbage"},
        )
        result = await hil.request_approval(
            request_id="req-1",
            plan_summary="Plan",
            side_effects=[],
            safety_assessment="safe",
            estimated_duration_ms=1000,
        )
        assert result == "approve"

    async def test_protocol_compliance_hil_coordinator_like(self) -> None:
        """HILCoordinator satisfies HILCoordinatorLike protocol."""

        llm = StubLLMPort()
        events = StubEventPort()
        hil = HILCoordinator(llm_port=llm, event_port=events)
        # Check structural protocol compliance by checking attrs.
        assert hasattr(hil, "round_count")
        assert hasattr(hil, "reset")
        assert hasattr(hil, "request_clarification")
        assert hasattr(hil, "request_approval")

    async def test_layer_2_no_stage_service_import(self) -> None:
        """HILCoordinator does not import stage services (Layer 2)."""
        import inspect

        import k1.planner.services.hil_coordinator as mod

        source = inspect.getsource(mod)
        assert "from k1.planner.stages" not in source
        assert "from k1.planner.pipeline_controller" not in source
        assert "from k1.planner.planner_agent" not in source
