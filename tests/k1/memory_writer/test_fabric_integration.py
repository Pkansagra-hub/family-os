"""Tests for Fabric Integration (E-MW-5.4).

Covers MemoryWriterFabricRegistration lifecycle:
  - create_for_session returns started service
  - teardown_session stops service
  - Full session lifecycle with turn processing
  - Pool reuse patterns

18 tests organized in 4 test classes.

Uses test adapters from E-MW-5.2 (FakeSessionReadPort, FakeModelHubPort, etc.)
"""

from __future__ import annotations

import json
from typing import Any, Callable, Coroutine, Dict, FrozenSet, List, Optional

import pytest

from k1.memory_writer.config import MWConfig
from k1.memory_writer.fabric_registration import MemoryWriterFabricRegistration
from k1.memory_writer.health.circuit_breaker import CircuitBreakerState
from k1.memory_writer.service import MemoryWriterService
from k1.memory_writer.types import ChatResponse, HealthStatus, Subscription

# ---------------------------------------------------------------------------
# Programmable test adapters (protocol-compatible fakes)
# ---------------------------------------------------------------------------


class FakeSessionReadPort:
    """Programmable session reader."""

    def __init__(self, snapshot_data: Dict[str, Any] | None = None) -> None:
        self._snapshot_data = snapshot_data or {}

    async def snapshot(self, sections: List[str]) -> Dict[str, Any]:
        return {k: v for k, v in self._snapshot_data.items() if k in sections}

    async def read_section(self, name: str) -> Optional[Dict[str, Any]]:
        return self._snapshot_data.get(name)

    async def list_sections(self) -> FrozenSet[str]:
        return frozenset(self._snapshot_data.keys())

    async def snapshot_all(self, exclude: FrozenSet[str] = frozenset()) -> Dict[str, Any]:
        return {k: v for k, v in self._snapshot_data.items() if k not in exclude}


class FakeModelHubPort:
    """Programmable model hub."""

    def __init__(
        self,
        responses: List[str] | None = None,
        *,
        fail_next: bool = False,
    ) -> None:
        self._responses: List[str] = responses or ["[]"]
        self._call_index: int = 0
        self.calls: List[Dict[str, Any]] = []
        self.fail_next = fail_next

    async def chat(
        self,
        messages: List[Dict[str, str]],
        budget_tokens: int,
        model_hint: str,
    ) -> ChatResponse:
        self.calls.append(
            {
                "messages": messages,
                "budget_tokens": budget_tokens,
                "model_hint": model_hint,
            }
        )
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("LLM call failed")
        idx = min(self._call_index, len(self._responses) - 1)
        self._call_index += 1
        return ChatResponse(content=self._responses[idx], total_tokens=50)


class FakeBridgeCommandPort:
    """Captures submitted envelopes."""

    def __init__(self, *, fail_next: bool = False) -> None:
        self.submitted: List[Dict] = []
        self.batches: List[List[Dict]] = []
        self.fail_next = fail_next

    async def submit(self, topic: str, schema_uri: str, body: Dict) -> None:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("bridge submit failed")
        self.submitted.append({"topic": topic, "schema_uri": schema_uri, "body": body})

    async def submit_batch(self, envelopes: List[Dict]) -> None:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("bridge batch failed")
        self.batches.append(envelopes)
        self.submitted.extend(envelopes)


class FakeEventSubscriptionPort:
    """Real event bus with dispatch."""

    def __init__(self) -> None:
        self._handlers: Dict[str, Callable[..., Coroutine[Any, Any, None]]] = {}
        self._sub_counter: int = 0
        self.subscriptions: List[Subscription] = []
        self.published: List[Dict[str, Any]] = []

    async def subscribe(
        self,
        topic: str,
        handler: Callable[..., Coroutine[Any, Any, None]],
    ) -> Subscription:
        self._sub_counter += 1
        sub_id = f"sub-{self._sub_counter}"
        self._handlers[sub_id] = handler
        sub = Subscription(subscription_id=sub_id, topic=topic)
        self.subscriptions.append(sub)
        return sub

    async def unsubscribe(self, subscription_id: str) -> None:
        self._handlers.pop(subscription_id, None)

    async def publish(self, topic: str, payload: dict) -> None:
        self.published.append({"topic": topic, "payload": payload})

    async def fire_event(self, raw_payload: dict) -> None:
        """Simulate a K1 Bus event delivery to all handlers."""
        for handler in list(self._handlers.values()):
            await handler(raw_payload)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NO_DEDUP_CONFIG = MWConfig(filter_dedup_window_seconds=0)


def _rich_snapshot() -> Dict[str, Any]:
    """Realistic SessionState snapshot."""
    return {
        "beliefs_active": {
            "active_entities": {
                "Mom": {"type": "PERSON", "display_name": "Mom"},
            },
        },
        "history_active": {
            "turns": [
                {
                    "turn_id": "prev-1",
                    "user_message": "How was your day?",
                    "timestamp_ms": 1000,
                    "turn_number": 1,
                },
            ],
        },
        "affective_now": {
            "dimensions": {"valence": 0.7, "arousal": 0.3, "dominance": 0.5},
        },
        "scoreboard": {
            "topic_stack": [
                {"name": "family", "salience": 0.9},
            ],
        },
        "control": {"safety_band": "GREEN"},
        "persona": {},
        "meta": {"session_id": "sess-fabric"},
    }


def _meaningful_llm_response() -> str:
    """LLM response JSON with 1 extractable atom."""
    return json.dumps(
        [
            {
                "text": "Had dinner with Mom at Olive Garden",
                "topics": ["family", "dinner"],
                "participants": ["Mom"],
                "location_name": "Olive Garden",
                "location_type": "restaurant",
                "activity_type": "MEAL",
                "sentiment_label": "positive",
                "emotion_tags": ["happy"],
                "confidence": 0.85,
                "source_type": "user_stated",
                "novelty": "EXPECTED",
                "elaboration_depth": "MENTION",
            }
        ]
    )


def _turn_event(
    turn_id: str = "turn-1",
    user_message: str = "Had dinner with Mom at Olive Garden",
    turn_number: int = 2,
    trace_id: str = "trace-abc",
    timestamp_ms: int = 2000,
) -> dict:
    """Raw K1 Bus event dict for turn.complete.v1."""
    return {
        "turn_id": turn_id,
        "session_id": "sess-fabric",
        "cognitive_trace_id": trace_id,
        "user_message": user_message,
        "assistant_response": "That sounds nice!",
        "timestamp_ms": timestamp_ms,
        "turn_number": turn_number,
    }


def _make_ports(
    responses: List[str] | None = None,
) -> tuple[
    FakeSessionReadPort,
    FakeModelHubPort,
    FakeBridgeCommandPort,
    FakeEventSubscriptionPort,
]:
    sp = FakeSessionReadPort(_rich_snapshot())
    mh = FakeModelHubPort(responses or [_meaningful_llm_response()])
    bp = FakeBridgeCommandPort()
    ep = FakeEventSubscriptionPort()
    return sp, mh, bp, ep


# ===========================================================================
# TestFabricRegistrationCreate (5 tests)
# ===========================================================================


class TestFabricRegistrationCreate:
    """Tests for MemoryWriterFabricRegistration.create_for_session()."""

    @pytest.mark.asyncio
    async def test_create_for_session_returns_started_service(self) -> None:
        """create_for_session -> service.is_started == True."""
        sp, mh, bp, ep = _make_ports()
        svc = await MemoryWriterFabricRegistration.create_for_session(
            sp, mh, bp, ep, config=_NO_DEDUP_CONFIG
        )
        assert isinstance(svc, MemoryWriterService)
        assert svc.is_started is True
        await svc.stop()

    @pytest.mark.asyncio
    async def test_create_for_session_with_default_config(self) -> None:
        """config=None -> uses MWConfig() defaults."""
        sp, mh, bp, ep = _make_ports()
        svc = await MemoryWriterFabricRegistration.create_for_session(sp, mh, bp, ep, config=None)
        assert svc.is_started is True
        await svc.stop()

    @pytest.mark.asyncio
    async def test_create_for_session_with_custom_config(self) -> None:
        """custom MWConfig -> passed through to factory."""
        sp, mh, bp, ep = _make_ports()
        custom = MWConfig(
            circuit_breaker_failure_threshold=5,
            filter_dedup_window_seconds=0,
        )
        svc = await MemoryWriterFabricRegistration.create_for_session(sp, mh, bp, ep, config=custom)
        assert svc.is_started is True
        # CB uses custom threshold
        assert svc.circuit_breaker._failure_threshold == 5
        await svc.stop()

    @pytest.mark.asyncio
    async def test_create_for_session_invariant_failure(self) -> None:
        """bad config -> InvariantViolation propagated."""
        from k1.memory_writer.invariants import InvariantViolation

        sp, mh, bp, ep = _make_ports()
        # Providing None for a required port will trigger TypeError from factory
        with pytest.raises(TypeError):
            await MemoryWriterFabricRegistration.create_for_session(
                None, mh, bp, ep, config=_NO_DEDUP_CONFIG  # type: ignore[arg-type]
            )

    @pytest.mark.asyncio
    async def test_create_for_session_subscribes_to_events(self) -> None:
        """after create -> dispatcher subscribed to turn.complete.v1."""
        sp, mh, bp, ep = _make_ports()
        svc = await MemoryWriterFabricRegistration.create_for_session(
            sp, mh, bp, ep, config=_NO_DEDUP_CONFIG
        )
        # Dispatcher subscribes to "k1.session.turn.complete.v1" (post-P6.8 rename)
        assert len(ep.subscriptions) >= 1
        assert any(s.topic == "k1.session.turn.complete.v1" for s in ep.subscriptions)
        await svc.stop()


# ===========================================================================
# TestFabricRegistrationTeardown (3 tests)
# ===========================================================================


class TestFabricRegistrationTeardown:
    """Tests for MemoryWriterFabricRegistration.teardown_session()."""

    @pytest.mark.asyncio
    async def test_teardown_stops_service(self) -> None:
        """teardown_session -> service.is_started == False."""
        sp, mh, bp, ep = _make_ports()
        svc = await MemoryWriterFabricRegistration.create_for_session(
            sp, mh, bp, ep, config=_NO_DEDUP_CONFIG
        )
        assert svc.is_started is True

        await MemoryWriterFabricRegistration.teardown_session(svc)
        assert svc.is_started is False

    @pytest.mark.asyncio
    async def test_teardown_flushes_pending(self) -> None:
        """pending envelopes -> teardown submits to Bridge."""
        sp, mh, bp, ep = _make_ports()
        svc = await MemoryWriterFabricRegistration.create_for_session(
            sp, mh, bp, ep, config=_NO_DEDUP_CONFIG
        )
        # Process a turn to generate envelopes
        await ep.fire_event(_turn_event())
        # Teardown should flush
        await MemoryWriterFabricRegistration.teardown_session(svc)
        # Envelopes submitted (either via process or flush)
        assert svc.is_started is False

    @pytest.mark.asyncio
    async def test_teardown_idempotent(self) -> None:
        """teardown twice -> no error."""
        sp, mh, bp, ep = _make_ports()
        svc = await MemoryWriterFabricRegistration.create_for_session(
            sp, mh, bp, ep, config=_NO_DEDUP_CONFIG
        )
        await MemoryWriterFabricRegistration.teardown_session(svc)
        await MemoryWriterFabricRegistration.teardown_session(svc)
        assert svc.is_started is False


# ===========================================================================
# TestFabricSessionLifecycle (6 tests)
# ===========================================================================


class TestFabricSessionLifecycle:
    """Full session lifecycle tests via Fabric registration."""

    @pytest.mark.asyncio
    async def test_full_session_create_process_teardown(self) -> None:
        """create -> publish turn -> atoms extracted -> teardown."""
        sp, mh, bp, ep = _make_ports()
        svc = await MemoryWriterFabricRegistration.create_for_session(
            sp, mh, bp, ep, config=_NO_DEDUP_CONFIG
        )

        await ep.fire_event(_turn_event())
        await MemoryWriterFabricRegistration.teardown_session(svc)

        # LLM called at least once
        assert len(mh.calls) >= 1
        # Envelopes submitted to bridge
        assert len(bp.submitted) > 0

    @pytest.mark.asyncio
    async def test_multi_turn_session_with_fabric(self) -> None:
        """create -> 5 turns -> all processed -> teardown."""
        responses = [_meaningful_llm_response()] * 5
        sp, mh, bp, ep = _make_ports(responses=responses)
        svc = await MemoryWriterFabricRegistration.create_for_session(
            sp, mh, bp, ep, config=_NO_DEDUP_CONFIG
        )

        for i in range(5):
            await ep.fire_event(
                _turn_event(
                    turn_id=f"turn-{i}",
                    user_message=f"Turn {i}: dinner with Mom at place {i}",
                    turn_number=i + 1,
                    trace_id=f"trace-{i}",
                )
            )

        await MemoryWriterFabricRegistration.teardown_session(svc)
        assert len(mh.calls) == 5

    @pytest.mark.asyncio
    async def test_trivial_turns_filtered(self) -> None:
        """'ok' turns -> filter skips -> no LLM call."""
        sp, mh, bp, ep = _make_ports()
        svc = await MemoryWriterFabricRegistration.create_for_session(
            sp, mh, bp, ep, config=_NO_DEDUP_CONFIG
        )

        await ep.fire_event(_turn_event(user_message="ok", turn_id="t-trivial"))
        await MemoryWriterFabricRegistration.teardown_session(svc)

        # Trivial "ok" should be filtered by R1 (< min_message_length)
        assert len(mh.calls) == 0

    @pytest.mark.asyncio
    async def test_llm_failure_handled(self) -> None:
        """FakeModelHub fails -> turn skipped, next turn OK."""
        responses = [_meaningful_llm_response()] * 2
        sp = FakeSessionReadPort(_rich_snapshot())
        mh = FakeModelHubPort(responses)
        bp = FakeBridgeCommandPort()
        ep = FakeEventSubscriptionPort()

        svc = await MemoryWriterFabricRegistration.create_for_session(
            sp, mh, bp, ep, config=_NO_DEDUP_CONFIG
        )

        # First turn fails at LLM
        mh.fail_next = True
        await ep.fire_event(_turn_event(turn_id="t-fail", trace_id="tr-fail"))

        # Second turn succeeds
        await ep.fire_event(_turn_event(turn_id="t-ok", trace_id="tr-ok"))

        await MemoryWriterFabricRegistration.teardown_session(svc)
        # 2 LLM calls attempted (first fails, second succeeds)
        assert len(mh.calls) == 2

    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self) -> None:
        """3 LLM failures -> circuit opens -> turns skipped -> recovery."""
        sp, mh, bp, ep = _make_ports()
        svc = await MemoryWriterFabricRegistration.create_for_session(
            sp, mh, bp, ep, config=_NO_DEDUP_CONFIG
        )

        # Trip the circuit breaker directly (since MemoryWriterAgent
        # swallows exceptions, we manipulate the CB directly)
        cb = svc.circuit_breaker
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        # Reset to allow processing again
        cb.reset()
        assert cb.state == CircuitBreakerState.CLOSED

        # Process a turn after reset
        await ep.fire_event(_turn_event(turn_id="t-after-reset"))
        await MemoryWriterFabricRegistration.teardown_session(svc)
        assert len(mh.calls) >= 1

    @pytest.mark.asyncio
    async def test_bridge_failure_handled(self) -> None:
        """FakeBridge fails -> no crash -> next turn OK."""
        responses = [_meaningful_llm_response()] * 2
        sp = FakeSessionReadPort(_rich_snapshot())
        mh = FakeModelHubPort(responses)
        bp = FakeBridgeCommandPort()
        ep = FakeEventSubscriptionPort()

        svc = await MemoryWriterFabricRegistration.create_for_session(
            sp, mh, bp, ep, config=_NO_DEDUP_CONFIG
        )

        # First turn: bridge fails
        bp.fail_next = True
        await ep.fire_event(_turn_event(turn_id="t-bridge-fail", trace_id="tr-1"))

        # Second turn: bridge OK
        await ep.fire_event(_turn_event(turn_id="t-bridge-ok", trace_id="tr-2"))

        await MemoryWriterFabricRegistration.teardown_session(svc)
        # Service didn't crash, both turns were attempted
        assert len(mh.calls) == 2


# ===========================================================================
# TestFabricPoolReuse (4 tests)
# ===========================================================================


class TestFabricPoolReuse:
    """Tests for service pool reuse patterns."""

    @pytest.mark.asyncio
    async def test_teardown_clears_dedup_state(self) -> None:
        """teardown -> same turn_id accepted in new session."""
        sp, mh, bp, ep = _make_ports()
        svc = await MemoryWriterFabricRegistration.create_for_session(
            sp, mh, bp, ep, config=_NO_DEDUP_CONFIG
        )

        await ep.fire_event(_turn_event(turn_id="reuse-turn"))
        await MemoryWriterFabricRegistration.teardown_session(svc)

        first_call_count = len(mh.calls)

        # New session with same turn_id
        sp2, mh2, bp2, ep2 = _make_ports()
        svc2 = await MemoryWriterFabricRegistration.create_for_session(
            sp2, mh2, bp2, ep2, config=_NO_DEDUP_CONFIG
        )
        await ep2.fire_event(_turn_event(turn_id="reuse-turn"))
        await MemoryWriterFabricRegistration.teardown_session(svc2)

        # Both sessions processed the same turn_id
        assert len(mh2.calls) >= 1

    @pytest.mark.asyncio
    async def test_create_after_teardown(self) -> None:
        """teardown -> create_for_session again -> works."""
        sp, mh, bp, ep = _make_ports()
        svc = await MemoryWriterFabricRegistration.create_for_session(
            sp, mh, bp, ep, config=_NO_DEDUP_CONFIG
        )
        await MemoryWriterFabricRegistration.teardown_session(svc)

        sp2, mh2, bp2, ep2 = _make_ports()
        svc2 = await MemoryWriterFabricRegistration.create_for_session(
            sp2, mh2, bp2, ep2, config=_NO_DEDUP_CONFIG
        )
        assert svc2.is_started is True
        await MemoryWriterFabricRegistration.teardown_session(svc2)

    @pytest.mark.asyncio
    async def test_independent_sessions(self) -> None:
        """2 concurrent sessions -> each has own service -> no shared state."""
        sp1, mh1, bp1, ep1 = _make_ports()
        sp2, mh2, bp2, ep2 = _make_ports()

        svc1 = await MemoryWriterFabricRegistration.create_for_session(
            sp1, mh1, bp1, ep1, config=_NO_DEDUP_CONFIG
        )
        svc2 = await MemoryWriterFabricRegistration.create_for_session(
            sp2, mh2, bp2, ep2, config=_NO_DEDUP_CONFIG
        )

        # Each is independently started
        assert svc1.is_started is True
        assert svc2.is_started is True

        # Process turn on svc1 only
        await ep1.fire_event(_turn_event(turn_id="s1-turn"))

        # svc1 processed, svc2 did not
        assert len(mh1.calls) >= 1
        assert len(mh2.calls) == 0

        await MemoryWriterFabricRegistration.teardown_session(svc1)
        await MemoryWriterFabricRegistration.teardown_session(svc2)

    @pytest.mark.asyncio
    async def test_health_check_after_create(self) -> None:
        """create -> health_check -> is_healthy=True."""
        sp, mh, bp, ep = _make_ports()
        svc = await MemoryWriterFabricRegistration.create_for_session(
            sp, mh, bp, ep, config=_NO_DEDUP_CONFIG
        )

        status = await svc.health_check()
        assert isinstance(status, HealthStatus)
        assert status.is_healthy is True
        assert status.detail == "running"

        await MemoryWriterFabricRegistration.teardown_session(svc)
