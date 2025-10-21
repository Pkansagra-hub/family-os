from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from ward import raises, test  # type: ignore[attr-defined]

from k0.bus import (
    BusDispatchContext,
    BusDispatcher,
    BusMessage,
    current_dispatch_context,
)
from k0.bus.middleware import (
    latency_metrics_middleware,
    timestamp_middleware,
    tracing_middleware,
)
from k0.obs import MetricsExporter, TracerFactory
from k0.qos import Scheduler, SchedulerProfile, SchedulerToken


class RecordingScheduler(Scheduler):
    """Scheduler variant that records band acquisitions for assertions."""

    def __init__(self, profile: SchedulerProfile) -> None:
        super().__init__(profile)
        self.bands: List[str] = []

    def acquire(self, *, band: str, port: str, cost: int) -> SchedulerToken:
        self.bands.append(band)
        return super().acquire(band=band, port=port, cost=cost)


@test("bus dispatcher preserves WAL ordering and releases scheduler tokens")
async def _() -> None:
    scheduler = Scheduler(
        SchedulerProfile(
            name="integration",
            description="integration profile",
            port_limits={"bus": 4},
            default_port_limit=4,
        )
    )
    dispatcher = BusDispatcher(scheduler=scheduler)

    received: List[int] = []

    async def sink(message: BusMessage) -> None:
        received.append(message.offset)

    dispatcher.register_sink(sink)

    await dispatcher.dispatch(
        [
            BusMessage(topic="memory.story", payload=b"c", offset=3),
            BusMessage(topic="memory.story", payload=b"a", offset=1),
            BusMessage(topic="memory.story", payload=b"b", offset=2),
        ]
    )

    assert received == [1, 2, 3]
    assert scheduler.active_tokens("bus") == 0


@test("bus dispatcher acquires scheduler tokens for each message")
async def _() -> None:
    scheduler = Scheduler(
        SchedulerProfile(
            name="integration",
            description="integration profile",
            port_limits={"bus": 1},
            default_port_limit=1,
        )
    )
    dispatcher = BusDispatcher(scheduler=scheduler)

    active_snapshot: List[int] = []

    async def sink(message: BusMessage) -> None:
        active_snapshot.append(scheduler.active_tokens("bus"))

    dispatcher.register_sink(sink)

    await dispatcher.dispatch(
        [
            BusMessage(topic="memory.story", payload=b"payload", offset=index)
            for index in range(3)
        ]
    )

    assert active_snapshot == [1, 1, 1]
    assert scheduler.active_tokens("bus") == 0


@test("bus dispatcher rejects sinks that do not return coroutines")
async def _() -> None:
    scheduler = Scheduler(
        SchedulerProfile(
            name="integration",
            description="integration profile",
            port_limits={"bus": 2},
            default_port_limit=2,
        )
    )
    dispatcher = BusDispatcher(scheduler=scheduler)

    def bad_sink(message: BusMessage) -> None:  # type: ignore[return-value]
        _ = message
        return None

    dispatcher.register_sink(bad_sink)  # type: ignore[arg-type]

    with raises(TypeError):
        await dispatcher.dispatch(
            [BusMessage(topic="memory.story", payload=b"x", offset=1)]
        )


@test("bus dispatcher enforces monotonic WAL offsets across batches")
async def _() -> None:
    scheduler = Scheduler(
        SchedulerProfile(
            name="integration",
            description="integration profile",
            port_limits={"bus": 2},
            default_port_limit=2,
        )
    )
    dispatcher = BusDispatcher(scheduler=scheduler)

    async def sink(message: BusMessage) -> None:
        _ = message

    dispatcher.register_sink(sink)

    await dispatcher.dispatch(
        [BusMessage(topic="memory.story", payload=b"x", offset=10)]
    )
    with raises(ValueError):
        await dispatcher.dispatch(
            [BusMessage(topic="memory.story", payload=b"x", offset=9)]
        )


@test("bus dispatcher resolves band via resolver when provided")
async def _() -> None:
    scheduler = RecordingScheduler(
        SchedulerProfile(
            name="integration",
            description="integration profile",
            port_limits={"bus": 4},
            default_port_limit=4,
        )
    )

    dispatcher = BusDispatcher(
        scheduler=scheduler,
        band_resolver=lambda message: (
            "RED" if message.topic.endswith(".priority") else "GREEN"
        ),
    )

    async def sink(message: BusMessage) -> None:
        _ = message

    dispatcher.register_sink(sink)

    await dispatcher.dispatch(
        [
            BusMessage(topic="memory.story.priority", payload=b"p", offset=1),
            BusMessage(topic="memory.story", payload=b"q", offset=2),
        ]
    )

    assert scheduler.bands == ["RED", "GREEN"]


@test("bus timestamp middleware records dispatch timing")
async def _() -> None:
    scheduler = Scheduler(
        SchedulerProfile(
            name="integration",
            description="integration profile",
            port_limits={"bus": 2},
            default_port_limit=2,
        )
    )

    start_ts = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    end_ts = datetime(2025, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
    sequence = [start_ts, end_ts]

    call_index = {"value": 0}

    def clock() -> datetime:
        idx = call_index["value"]
        if idx >= len(sequence):
            return sequence[-1]
        call_index["value"] = idx + 1
        return sequence[idx]

    dispatcher = BusDispatcher(
        scheduler=scheduler,
        middlewares=[timestamp_middleware(clock=clock)],
    )

    contexts: List[BusDispatchContext] = []

    async def sink(message: BusMessage) -> None:
        _ = message
        context = current_dispatch_context()
        assert context is not None
        contexts.append(context)

    dispatcher.register_sink(sink)

    await dispatcher.dispatch(
        [BusMessage(topic="memory.story", payload=b"x", offset=1)]
    )

    assert current_dispatch_context() is None
    assert len(contexts) == 1
    captured = contexts[0]
    assert captured.started_at == start_ts
    assert captured.completed_at == end_ts
    assert captured.duration_seconds is not None
    assert captured.duration_seconds >= 0.0
    assert captured.monotonic_start is not None
    assert captured.monotonic_end is not None


@test("bus tracing middleware propagates cognitive trace identifiers")
async def _() -> None:
    scheduler = Scheduler(
        SchedulerProfile(
            name="integration",
            description="integration profile",
            port_limits={"bus": 2},
            default_port_limit=2,
        )
    )

    tracer_factory = TracerFactory(
        service_name="k0-test",
        service_version="0.0",
        environment="test",
        otlp_endpoint=None,
        sample_ratio=1.0,
    )

    dispatcher = BusDispatcher(
        scheduler=scheduler,
        middlewares=[tracing_middleware(tracer_factory=tracer_factory)],
    )

    observed_trace_ids: List[str | None] = []

    async def sink(message: BusMessage) -> None:
        _ = message
        observed_trace_ids.append(TracerFactory.current_cognitive_trace_id())

    dispatcher.register_sink(sink)

    await dispatcher.dispatch(
        [
            BusMessage(
                topic="memory.story",
                payload=b"x",
                offset=1,
                trace_id="trace-bus-1",
            )
        ]
    )

    assert current_dispatch_context() is None
    assert observed_trace_ids == ["trace-bus-1"]
    assert TracerFactory.current_cognitive_trace_id() is None


@test("bus latency middleware emits histogram samples")
async def _() -> None:
    scheduler = Scheduler(
        SchedulerProfile(
            name="integration",
            description="integration profile",
            port_limits={"bus": 2},
            default_port_limit=2,
        )
    )

    metrics = MetricsExporter(namespace="k0_test_bus")

    dispatcher = BusDispatcher(
        scheduler=scheduler,
        middlewares=[latency_metrics_middleware(metrics)],
    )

    async def sink(message: BusMessage) -> None:
        _ = message

    dispatcher.register_sink(sink)

    await dispatcher.dispatch(
        [BusMessage(topic="memory.story", payload=b"body", offset=1)]
    )

    count = metrics.registry.get_sample_value(
        "k0_test_bus_k0_bus_dispatch_latency_count",
        labels={"topic": "memory.story"},
    )
    total = metrics.registry.get_sample_value(
        "k0_test_bus_k0_bus_dispatch_latency_sum",
        labels={"topic": "memory.story"},
    )
    assert count == 1.0
    assert total is not None and total > 0.0
