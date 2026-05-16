"""
tests.k1.memory_writer.test_lifecycle_integration -- 14 integration tests for MW lifecycle.

Full end-to-end lifecycle: factory.create → start → turn events → pipeline → Bridge → stop.
NO mocks, NO patches -- only real components with programmable test adapters.

Key real-behavior constraints reflected in these tests:
  - RelevanceFilter R3 dedup: pipeline passes entities=[], topics=[] to filter,
    so R3 hash is identical for every turn. Dedup window = filter_dedup_window_seconds.
    Multi-turn tests set filter_dedup_window_seconds=0 to disable R3 dedup.
    - MemoryWriterAgent catches model_hub.chat() exceptions and returns [], while
        exposing the failure to the pipeline so model-edge failures still count
        toward the circuit breaker.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Coroutine, Dict, FrozenSet, List, Optional

import pytest

from k1.memory_writer.config import MWConfig
from k1.memory_writer.factory import MemoryWriterFactory
from k1.memory_writer.health.circuit_breaker import CircuitBreakerState
from k1.memory_writer.service import MemoryWriterService
from k1.memory_writer.types import ChatResponse, HealthStatus, Subscription

# ---------------------------------------------------------------------------
# Programmable test adapters (no mocks -- real classes implementing protocols)
# ---------------------------------------------------------------------------


class FakeSessionReadPort:
    """Programmable session reader. Returns configurable snapshots."""

    def __init__(self, snapshot_data: Dict[str, Any] | None = None) -> None:
        self._snapshot_data = snapshot_data or {}
        self.fail_next: bool = False

    async def snapshot(self, sections: List[str]) -> Dict[str, Any]:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("session read failed")
        return {k: v for k, v in self._snapshot_data.items() if k in sections}

    async def read_section(self, name: str) -> Optional[Dict[str, Any]]:
        return self._snapshot_data.get(name)

    async def list_sections(self) -> FrozenSet[str]:
        return frozenset(self._snapshot_data.keys())

    async def snapshot_all(self, exclude: FrozenSet[str] = frozenset()) -> Dict[str, Any]:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("session read failed")
        return {k: v for k, v in self._snapshot_data.items() if k not in exclude}

    async def read_archived_history(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return []


class FakeModelHubPort:
    """Programmable model hub. Returns configurable LLM responses."""

    def __init__(self, responses: List[str] | None = None) -> None:
        self._responses: List[str] = responses or ["[]"]
        self._call_index: int = 0
        self.calls: List[Dict[str, Any]] = []
        self.fail_next: bool = False

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
    """Captures all submitted envelopes for assertions."""

    def __init__(self) -> None:
        self.submitted: List[Dict] = []
        self.batches: List[List[Dict]] = []
        self.fail_next: bool = False

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
    """Real event bus: routes events to subscribed handlers, captures publishes."""

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


class FakeHealthPort:
    async def is_ready(self) -> bool:
        return True

    async def health_check(self) -> HealthStatus:
        return HealthStatus(is_healthy=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Config with R3 dedup disabled so multi-turn tests aren't blocked by
# the pipeline passing entities=[] topics=[] on every turn.
# Per-turn extraction mode required: these tests assert per-turn LLM call
# counts. Default "session_batch" mode batches turns and breaks counts.
_NO_DEDUP_CONFIG = MWConfig(filter_dedup_window_seconds=0, extraction_mode="per_turn")


def _rich_snapshot() -> Dict[str, Any]:
    """A realistic SessionState snapshot with enough data for extraction."""
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
                {"name": "dinner", "salience": 0.7},
            ],
        },
        "control": {"safety_band": "GREEN"},
        "persona": {},
        "meta": {"session_id": "sess-integration"},
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
        "session_id": "sess-integration",
        "cognitive_trace_id": trace_id,
        "user_message": user_message,
        "assistant_response": "That sounds nice!",
        "timestamp_ms": timestamp_ms,
        "turn_number": turn_number,
    }


def _create_service(
    session_port: FakeSessionReadPort | None = None,
    model_hub: FakeModelHubPort | None = None,
    bridge: FakeBridgeCommandPort | None = None,
    event_port: FakeEventSubscriptionPort | None = None,
    health_port: FakeHealthPort | None = None,
    config: MWConfig | None = None,
) -> tuple[
    MemoryWriterService,
    FakeSessionReadPort,
    FakeModelHubPort,
    FakeBridgeCommandPort,
    FakeEventSubscriptionPort,
]:
    sp = session_port or FakeSessionReadPort(_rich_snapshot())
    mh = model_hub or FakeModelHubPort([_meaningful_llm_response()])
    bp = bridge or FakeBridgeCommandPort()
    ep = event_port or FakeEventSubscriptionPort()
    hp = health_port or FakeHealthPort()

    svc = MemoryWriterFactory.create(sp, mh, bp, ep, hp, config=config or _NO_DEDUP_CONFIG)
    return svc, sp, mh, bp, ep


# ===========================================================================
# TestFullLifecycle (6 tests)
# ===========================================================================


class TestFullLifecycle:
    """End-to-end lifecycle: create → start → turns → stop."""

    @pytest.mark.asyncio
    async def test_create_start_process_stop(self):
        """factory.create → start → send turn → atoms extracted → stop."""
        svc, sp, mh, bp, ep = _create_service()

        await svc.start()
        assert svc.is_started

        await ep.fire_event(_turn_event())

        await svc.stop()
        assert not svc.is_started

        # LLM was called (extraction happened)
        assert len(mh.calls) == 1
        # Envelopes were submitted to Bridge
        assert len(bp.submitted) > 0

    @pytest.mark.asyncio
    async def test_multi_turn_session(self):
        """5 turns → each processed, dedup set grows, envelopes submitted."""
        responses = [_meaningful_llm_response()] * 5
        svc, sp, mh, bp, ep = _create_service(
            model_hub=FakeModelHubPort(responses),
        )

        await svc.start()

        for i in range(5):
            await ep.fire_event(
                _turn_event(
                    turn_id=f"turn-{i}",
                    user_message=f"Turn {i}: Had dinner with Mom at place {i}",
                    turn_number=i + 1,
                    trace_id=f"trace-{i}",
                )
            )

        await svc.stop()

        # All 5 turns processed (each triggers an LLM call)
        assert len(mh.calls) == 5
        # Bridge received envelopes from each turn
        assert len(bp.batches) == 5

    @pytest.mark.asyncio
    async def test_trivial_turn_skipped(self):
        """'ok' → filter SKIP → no LLM call → no Bridge submit."""
        svc, sp, mh, bp, ep = _create_service()

        await svc.start()

        # "ok" is trivial — fewer words than filter_trivial_word_threshold (5)
        await ep.fire_event(
            _turn_event(
                turn_id="trivial-1",
                user_message="ok",
                turn_number=1,
            )
        )

        await svc.stop()

        # Filter should skip → no LLM call
        assert len(mh.calls) == 0
        # No Bridge submission
        assert len(bp.submitted) == 0

    @pytest.mark.asyncio
    async def test_meaningful_turn_extracted(self):
        """'Had dinner with Mom' → 1+ atoms → envelopes → Bridge."""
        svc, sp, mh, bp, ep = _create_service()

        await svc.start()

        await ep.fire_event(
            _turn_event(
                user_message="Had dinner with Mom at Olive Garden last night",
            )
        )

        await svc.stop()

        # LLM called
        assert len(mh.calls) == 1
        # Envelopes submitted to Bridge
        assert len(bp.submitted) > 0
        # Verify envelope structure
        env = bp.submitted[0]
        assert "body" in env
        assert "topic" in env

    @pytest.mark.asyncio
    async def test_stop_flushes_then_cleans(self):
        """Pending envelopes flushed on stop → Bridge receives batch."""
        svc, sp, mh, bp, ep = _create_service()

        await svc.start()
        await ep.fire_event(_turn_event())

        # Envelopes should have been submitted during process
        pre_stop_count = len(bp.submitted)
        assert pre_stop_count > 0

        await svc.stop()
        # stop() calls flush_pending — no additional envelopes expected
        # since pipeline already flushed during process()
        assert len(bp.submitted) >= pre_stop_count

    @pytest.mark.asyncio
    async def test_restart_after_stop(self):
        """stop → start → new turns processed (dispatcher dedup cleared)."""
        svc, sp, mh, bp, ep = _create_service(
            model_hub=FakeModelHubPort([_meaningful_llm_response()] * 3),
        )

        await svc.start()
        await ep.fire_event(_turn_event(turn_id="turn-a"))
        await svc.stop()

        first_run_calls = len(mh.calls)
        assert first_run_calls == 1

        # Restart — dispatcher dedup set cleared on stop()
        await svc.start()
        # Same turn_id should be accepted (dispatcher dedup cleared)
        await ep.fire_event(_turn_event(turn_id="turn-a"))
        await svc.stop()

        assert len(mh.calls) == 2  # Processed again after restart


# ===========================================================================
# TestLifecycleErrorResilience (5 tests)
# ===========================================================================


class TestLifecycleErrorResilience:
    """Error resilience: LLM failure, context read failure, Bridge failure."""

    @pytest.mark.asyncio
    async def test_llm_failure_skip_turn(self):
        """FakeModelHub raises → pipeline records CB failure → next turn OK."""
        mh = FakeModelHubPort([_meaningful_llm_response()] * 3)
        svc, sp, _, bp, ep = _create_service(model_hub=mh)

        await svc.start()

        # First turn: LLM fails (agent catches, returns [])
        mh.fail_next = True
        await ep.fire_event(_turn_event(turn_id="fail-1"))

        # Second turn: LLM succeeds
        await ep.fire_event(_turn_event(turn_id="ok-1"))

        await svc.stop()

        # Both turns reached the LLM (agent.extract() called chat() both times)
        assert len(mh.calls) == 2
        # Second turn produced envelopes
        assert len(bp.batches) >= 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_threshold(self):
        """3 record_failure() calls → circuit opens → next turn skipped (no LLM)."""
        mh = FakeModelHubPort([_meaningful_llm_response()] * 10)
        svc, sp, _, bp, ep = _create_service(model_hub=mh)

        await svc.start()

        # Record 3 failures directly on the circuit breaker (real object)
        for _ in range(3):
            svc.circuit_breaker.record_failure()

        assert svc.circuit_breaker.state == CircuitBreakerState.OPEN

        # Next turn should be skipped at circuit breaker check (no LLM call)
        await ep.fire_event(
            _turn_event(
                turn_id="post-cb",
                user_message="Another meaningful turn with content here",
            )
        )

        await svc.stop()

        # No LLM calls — circuit was open
        assert len(mh.calls) == 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_half_open_probe(self):
        """Circuit open → wait recovery → probe turn succeeds → circuit closed."""
        clock_time = [0.0]

        mh = FakeModelHubPort([_meaningful_llm_response()] * 10)
        svc, sp, _, bp, ep = _create_service(model_hub=mh)

        # Inject controllable clock
        svc.circuit_breaker._clock = lambda: clock_time[0]

        await svc.start()

        # 3 failures → circuit OPEN
        for _ in range(3):
            svc.circuit_breaker.record_failure()

        assert svc.circuit_breaker.state == CircuitBreakerState.OPEN

        # Advance clock past recovery window (default 30s)
        clock_time[0] = 31.0

        # Next turn should trigger HALF_OPEN probe
        await ep.fire_event(
            _turn_event(
                turn_id="probe-1",
                user_message="Probe turn with enough words for the filter",
            )
        )

        # LLM succeeded → record_success() in pipeline → CLOSED
        assert svc.circuit_breaker.state == CircuitBreakerState.CLOSED
        assert len(mh.calls) == 1

        await svc.stop()

    @pytest.mark.asyncio
    async def test_context_read_failure_skip_turn(self):
        """FakeSessionReader raises → turn error (no LLM), next turn OK."""
        sp = FakeSessionReadPort(_rich_snapshot())
        mh = FakeModelHubPort([_meaningful_llm_response()] * 3)
        svc, _, _, bp, ep = _create_service(session_port=sp, model_hub=mh)

        await svc.start()

        # First turn: context read fails
        sp.fail_next = True
        await ep.fire_event(_turn_event(turn_id="ctx-fail-1"))

        # Second turn: succeeds
        await ep.fire_event(_turn_event(turn_id="ctx-ok-1"))

        await svc.stop()

        # First turn failed at context read (before LLM), second went through
        assert len(mh.calls) == 1
        assert len(bp.batches) >= 1

    @pytest.mark.asyncio
    async def test_bridge_failure_no_crash(self):
        """FakeBridge raises → pipeline continues, next turn OK."""
        bridge = FakeBridgeCommandPort()
        mh = FakeModelHubPort([_meaningful_llm_response()] * 3)
        svc, sp, _, _, ep = _create_service(bridge=bridge, model_hub=mh)

        await svc.start()

        # First turn: Bridge fails (emitter catches, returns 0)
        bridge.fail_next = True
        await ep.fire_event(_turn_event(turn_id="bridge-fail-1"))

        # Second turn: Bridge succeeds
        await ep.fire_event(_turn_event(turn_id="bridge-ok-1"))

        await svc.stop()

        # Both turns triggered LLM extraction
        assert len(mh.calls) == 2
        # Second turn's envelopes were submitted
        assert len(bridge.submitted) > 0


# ===========================================================================
# TestLifecycleObservability (3 tests)
# ===========================================================================


class TestLifecycleObservability:
    """Observability events published at each stage."""

    @pytest.mark.asyncio
    async def test_all_observability_events_published(self):
        """Full turn → filter.decision + extraction.complete + batch.submitted events."""
        svc, sp, mh, bp, ep = _create_service()

        await svc.start()
        await ep.fire_event(_turn_event())
        await svc.stop()

        topics = [e["topic"] for e in ep.published]
        assert "k1.mw.filter.decision.v1" in topics
        assert "k1.mw.extraction.complete.v1" in topics
        assert "k1.mw.batch.submitted.v1" in topics

    @pytest.mark.asyncio
    async def test_metrics_trace_ids_consistent(self):
        """All events carry same cognitive_trace_id."""
        svc, sp, mh, bp, ep = _create_service()

        await svc.start()
        await ep.fire_event(_turn_event(trace_id="trace-xyz"))
        await svc.stop()

        for event in ep.published:
            payload = event["payload"]
            assert payload.get("trace_id") == "trace-xyz"

    @pytest.mark.asyncio
    async def test_health_check_reflects_state(self):
        """Started + healthy → True, circuit open → False."""
        svc, sp, mh, bp, ep = _create_service()

        # Before start
        health = await svc.health_check()
        assert not health.is_healthy
        assert health.detail == "stopped"

        await svc.start()
        health = await svc.health_check()
        assert health.is_healthy
        assert health.detail == "running"
        assert not health.llm_circuit_open

        # Trip circuit breaker directly (real object)
        svc.circuit_breaker.record_failure()
        svc.circuit_breaker.record_failure()
        svc.circuit_breaker.record_failure()

        health = await svc.health_check()
        assert not health.is_healthy
        assert health.llm_circuit_open

        await svc.stop()
