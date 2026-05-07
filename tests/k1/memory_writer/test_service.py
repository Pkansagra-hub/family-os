"""
tests.k1.memory_writer.test_service -- 16 tests for MemoryWriterService.

Covers: lifecycle, health check, properties, integration.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine, List, Optional

import pytest

from k1.memory_writer.config import MWConfig
from k1.memory_writer.events import TurnCompletePayload
from k1.memory_writer.health.circuit_breaker import CircuitBreaker
from k1.memory_writer.pipeline.pipeline import PipelineResult
from k1.memory_writer.service import MemoryWriterService
from k1.memory_writer.types import HealthStatus, Subscription

# ---------------------------------------------------------------------------
# Fake adapters
# ---------------------------------------------------------------------------


class FakeDispatcher:
    """Captures start/stop calls."""

    def __init__(self) -> None:
        self.start_count: int = 0
        self.stop_count: int = 0

    async def start(self) -> None:
        self.start_count += 1

    async def stop(self) -> None:
        self.stop_count += 1


class FakePipeline:
    """Pipeline with controllable aggregator pending_count."""

    def __init__(self, pending: int = 0) -> None:
        self._aggregator = _FakeAggregator(pending)
        self.process_calls: List[TurnCompletePayload] = []
        self.flush_count: int = 0

    async def process(self, payload: TurnCompletePayload) -> PipelineResult:
        self.process_calls.append(payload)
        return PipelineResult(trace_id="trace-fake", atoms_extracted=1)

    async def flush_pending(self) -> int:
        self.flush_count += 1
        return 0


class _FakeAggregator:
    def __init__(self, pending: int = 0) -> None:
        self.pending_count = pending


class FakeHealthPort:
    async def is_ready(self) -> bool:
        return True

    async def health_check(self) -> HealthStatus:
        return HealthStatus(is_healthy=True)


class FakeEventPort:
    """Minimal event port for integration tests."""

    def __init__(self) -> None:
        self.subscriptions: list = []
        self.unsubscribed: list = []
        self._next_sub_id = 0

    async def subscribe(
        self,
        topic: str,
        handler: Callable[..., Coroutine[Any, Any, None]],
    ) -> Subscription:
        self._next_sub_id += 1
        self.subscriptions.append((topic, handler))
        return Subscription(subscription_id=f"sub-{self._next_sub_id}", topic=topic)

    async def unsubscribe(self, subscription_id: str) -> None:
        self.unsubscribed.append(subscription_id)

    async def publish(self, topic: str, payload: dict) -> None:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _service(
    pipeline: Optional[FakePipeline] = None,
    dispatcher: Optional[FakeDispatcher] = None,
    circuit_breaker: Optional[CircuitBreaker] = None,
    health_port: Optional[FakeHealthPort] = None,
    config: Optional[MWConfig] = None,
) -> tuple:
    p = pipeline or FakePipeline()
    d = dispatcher or FakeDispatcher()
    cb = circuit_breaker or CircuitBreaker()
    hp = health_port or FakeHealthPort()
    cfg = config or MWConfig()
    svc = MemoryWriterService(
        pipeline=p,
        dispatcher=d,
        circuit_breaker=cb,
        health_port=hp,
        config=cfg,
    )
    return svc, p, d, cb


# ===========================================================================
# TestServiceLifecycle — 5 tests
# ===========================================================================


class TestServiceLifecycle:
    """Start/stop dispatcher delegation."""

    @pytest.mark.asyncio
    async def test_start_subscribes_dispatcher(self) -> None:
        svc, _, d, _ = _service()
        await svc.start()
        assert d.start_count == 1

    @pytest.mark.asyncio
    async def test_start_idempotent(self) -> None:
        svc, _, d, _ = _service()
        await svc.start()
        await svc.start()
        assert d.start_count == 1

    @pytest.mark.asyncio
    async def test_stop_unsubscribes_dispatcher(self) -> None:
        svc, _, d, _ = _service()
        await svc.start()
        await svc.stop()
        assert d.stop_count == 1

    @pytest.mark.asyncio
    async def test_stop_idempotent(self) -> None:
        svc, _, d, _ = _service()
        await svc.start()
        await svc.stop()
        await svc.stop()
        assert d.stop_count == 1

    @pytest.mark.asyncio
    async def test_stop_before_start_noop(self) -> None:
        svc, _, d, _ = _service()
        await svc.stop()  # should not raise
        assert d.stop_count == 0


# ===========================================================================
# TestServiceHealthCheck — 5 tests
# ===========================================================================


class TestServiceHealthCheck:
    """Health check reflects service + circuit breaker state."""

    @pytest.mark.asyncio
    async def test_healthy_when_started_circuit_closed(self) -> None:
        svc, _, _, _ = _service()
        await svc.start()
        health = await svc.health_check()
        assert health.is_healthy is True

    @pytest.mark.asyncio
    async def test_unhealthy_when_stopped(self) -> None:
        svc, _, _, _ = _service()
        health = await svc.health_check()
        assert health.is_healthy is False
        assert health.detail == "stopped"

    @pytest.mark.asyncio
    async def test_unhealthy_when_circuit_open(self) -> None:
        cb = CircuitBreaker(failure_threshold=1)
        svc, _, _, _ = _service(circuit_breaker=cb)
        await svc.start()
        cb.record_failure()  # trips to OPEN
        health = await svc.health_check()
        assert health.is_healthy is False
        assert health.llm_circuit_open is True

    @pytest.mark.asyncio
    async def test_health_includes_circuit_state(self) -> None:
        cb = CircuitBreaker(failure_threshold=2)
        svc, _, _, _ = _service(circuit_breaker=cb)
        await svc.start()
        health = await svc.health_check()
        assert health.llm_circuit_open is False
        cb.record_failure()
        cb.record_failure()  # trips
        health2 = await svc.health_check()
        assert health2.llm_circuit_open is True

    @pytest.mark.asyncio
    async def test_health_includes_pending_count(self) -> None:
        p = FakePipeline(pending=5)
        svc, _, _, _ = _service(pipeline=p)
        await svc.start()
        health = await svc.health_check()
        assert health.pending_batch_count == 5


# ===========================================================================
# TestServiceProperties — 3 tests
# ===========================================================================


class TestServiceProperties:
    """is_started property tracking."""

    def test_is_started_false_initially(self) -> None:
        svc, _, _, _ = _service()
        assert svc.is_started is False

    @pytest.mark.asyncio
    async def test_is_started_true_after_start(self) -> None:
        svc, _, _, _ = _service()
        await svc.start()
        assert svc.is_started is True

    @pytest.mark.asyncio
    async def test_is_started_false_after_stop(self) -> None:
        svc, _, _, _ = _service()
        await svc.start()
        await svc.stop()
        assert svc.is_started is False


# ===========================================================================
# TestServiceIntegration — 3 tests
# ===========================================================================


class TestServiceIntegration:
    """Full lifecycle with real TurnDispatcher."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_start_process_stop(self) -> None:
        """start → send turn → pipeline processes → stop → flushed."""
        from k1.memory_writer.pipeline.turn_dispatcher import TurnDispatcher

        p = FakePipeline()
        ep = FakeEventPort()
        dispatcher = TurnDispatcher(pipeline=p, event_port=ep)
        cb = CircuitBreaker()
        svc = MemoryWriterService(
            pipeline=p,
            dispatcher=dispatcher,
            circuit_breaker=cb,
            health_port=FakeHealthPort(),
            config=MWConfig(),
        )
        await svc.start()
        assert svc.is_started is True

        # Send a turn via the subscribed handler
        handler = ep.subscriptions[0][1]
        await handler(
            {
                "turn_id": "t1",
                "session_id": "s1",
                "cognitive_trace_id": "ct-1",
                "user_message": "hi",
                "assistant_response": "hello",
                "timestamp_ms": 1700000000000,
                "turn_number": 1,
            }
        )
        assert len(p.process_calls) == 1

        await svc.stop()
        assert svc.is_started is False
        assert p.flush_count == 1

    @pytest.mark.asyncio
    async def test_multiple_turns_processed(self) -> None:
        from k1.memory_writer.pipeline.turn_dispatcher import TurnDispatcher

        p = FakePipeline()
        ep = FakeEventPort()
        dispatcher = TurnDispatcher(pipeline=p, event_port=ep)
        svc = MemoryWriterService(
            pipeline=p,
            dispatcher=dispatcher,
            circuit_breaker=CircuitBreaker(),
            health_port=FakeHealthPort(),
            config=MWConfig(),
        )
        await svc.start()
        handler = ep.subscriptions[0][1]
        for i in range(3):
            await handler(
                {
                    "turn_id": f"t{i}",
                    "session_id": "s1",
                    "cognitive_trace_id": f"ct-{i}",
                    "user_message": f"msg-{i}",
                    "assistant_response": f"resp-{i}",
                    "timestamp_ms": 1700000000000 + i,
                    "turn_number": i + 1,
                }
            )
        assert len(p.process_calls) == 3
        await svc.stop()

    @pytest.mark.asyncio
    async def test_stop_flushes_pending_batches(self) -> None:
        from k1.memory_writer.pipeline.turn_dispatcher import TurnDispatcher

        p = FakePipeline(pending=3)
        ep = FakeEventPort()
        dispatcher = TurnDispatcher(pipeline=p, event_port=ep)
        svc = MemoryWriterService(
            pipeline=p,
            dispatcher=dispatcher,
            circuit_breaker=CircuitBreaker(),
            health_port=FakeHealthPort(),
            config=MWConfig(),
        )
        await svc.start()
        await svc.stop()
        # flush_pending called by dispatcher.stop()
        assert p.flush_count == 1
