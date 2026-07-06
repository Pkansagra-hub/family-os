from __future__ import annotations

import asyncio
import json
from collections import deque
from contextlib import suppress
from types import SimpleNamespace

import pytest

from k1.bus.envelope import Envelope
from k1.concierge.actors.back_pool import BackPool, BackPoolConfig
from k1.concierge.actors.back_router import BackTopicRouter
from k1.concierge.actors.ready_queue import ReadyQueue
from k1.concierge.bus.builders import (
    build_clarification_response,
    build_task_cancel,
    build_task_dispatch,
    build_task_resume,
)
from k1.concierge.bus.topics import (
    TOPIC_BACKPOOL_WORKER_ACQUIRED,
    TOPIC_BACKPOOL_WORKER_RELEASED,
    TOPIC_CLARIFICATION_RESPONSE,
    TOPIC_TASK_LEASED,
    TOPIC_TASK_RESUME,
)
from k1.concierge.config.concierge import ConciergeConfig
from k1.concierge.config.kernel import KernelConfig
from k1.concierge.factory import ConciergeFactory, PortBundle
from k1.concierge.protocols.cancellation import CancellationToken
from k1.concierge.react.loop import ReactResult
from k1.concierge.session import ConciergeRuntime


class _Mailbox:
    def __init__(self) -> None:
        self._items: deque[Envelope] = deque()

    def push(self, envelope: Envelope) -> None:
        self._items.append(envelope)

    def receive(self, timeout_ms: int = 0) -> Envelope | None:  # noqa: ARG002
        if not self._items:
            return None
        return self._items.popleft()


class _Bus:
    def __init__(self) -> None:
        self.published: list[Envelope] = []

    def publish(self, envelope: Envelope) -> None:
        self.published.append(envelope)


def _runtime(
    *,
    pool: BackPool | None = None,
    router: BackTopicRouter | None = None,
    ready_queue: ReadyQueue | None = None,
    back_mailbox: _Mailbox | None = None,
    fsm: object | None = None,
) -> ConciergeRuntime:
    return ConciergeRuntime(
        bus=_Bus(),
        router=SimpleNamespace(),
        front_mailbox=_Mailbox(),
        back_mailbox=back_mailbox or _Mailbox(),
        fsm=fsm or SimpleNamespace(state=SimpleNamespace(name="COMPANIONING"), _opp_pipeline=None),
        model=SimpleNamespace(),
        session_state=SimpleNamespace(),
        front_dispatcher=SimpleNamespace(),
        back_dispatcher=SimpleNamespace(),
        front_subscriptions=[],
        back_pool=pool,
        back_topic_router=router,
        ready_queue=ready_queue,
    )


def _payload(envelope: Envelope) -> dict:
    return json.loads(envelope.payload.decode("utf-8"))


def test_factory_constructs_session_backpool_router_and_ready_queue() -> None:
    """BP-27: Verify BackPool/BackTopicRouter/ReadyQueue are constructed
    and attached to FSM when enable_back_pool=True.  Config propagation
    from ConciergeConfig to BackPoolConfig is product-gated (Milestone B)."""
    config = ConciergeConfig.for_testing(enable_back_pool=True)

    runtime = ConciergeFactory.create_for_testing(config=config)

    assert runtime._back_pool is not None
    assert runtime._back_topic_router is not None
    assert runtime._ready_queue is not None
    assert getattr(runtime._fsm, "_back_pool") is runtime._back_pool
    # Default BackPoolConfig values (hardcoded in factory until Milestone B)
    assert runtime._back_pool.config.pool_size == 3
    assert runtime._back_pool.config.max_concurrent_per_session == 2
    assert runtime._back_pool.config.lease_ttl_s == 300.0
    assert runtime._back_pool.config.reclaim_check_interval_s == 30.0
    assert runtime._back_pool.config.enable_dependency_ordering is True
    assert runtime._back_pool.config.max_renewals == 3
    assert runtime._back_pool.config.lease_grace_period_s == 5.0


def test_kernel_config_maps_backpool_fields_to_concierge_config() -> None:
    """BP-27/BP-29: enable_back_pool propagates from KernelConfig to ConciergeConfig.
    Default is True (single environment, feature enabled by default)."""
    kernel_config = KernelConfig(enable_back_pool=True)

    concierge_config = ConciergeConfig.from_kernel_config(kernel_config)

    assert concierge_config.enable_back_pool is True
    # Default-on (BP-29: single environment, no staging gating)
    kernel_config_default = KernelConfig()
    concierge_config_default = ConciergeConfig.from_kernel_config(kernel_config_default)
    assert concierge_config_default.enable_back_pool is True

    # Explicit off still propagates
    kernel_config_off = KernelConfig(enable_back_pool=False)
    concierge_config_off = ConciergeConfig.from_kernel_config(kernel_config_off)
    assert concierge_config_off.enable_back_pool is False


@pytest.mark.skip(reason="BP-27: BusFactory + PortBundle observability wiring is Milestone B")
def test_factory_backpool_callbacks_emit_observability_events() -> None:
    from k1.bus.factory import BusFactory
    from k1.concierge.bus.setup import ACTOR_BACK, ACTOR_FRONT

    bus = BusFactory.create_for_testing()
    router = BusFactory.create_mailbox_router()
    adapters = ConciergeFactory._build_test_adapters()
    front_mailbox = router.register(ACTOR_FRONT)
    back_mailbox = router.register(ACTOR_BACK)
    port_bundle = PortBundle(
        delta=bus,
        input_=adapters["input_"],
        output=adapters["output"],
        state=adapters["state"],
        llm=adapters["llm"],
        dispatch=adapters["dispatch"],
        memory=adapters["memory"],
    )
    runtime = ConciergeFactory.create_with_ports(
        bus=bus,
        router=router,
        front_mailbox=front_mailbox,
        back_mailbox=back_mailbox,
        ports=port_bundle,
        config=ConciergeConfig.for_testing(),
    )

    runtime.back_pool.acquire_worker("obs-task")
    runtime.back_pool.release_worker("obs-task", reason="completed")

    topics = [envelope.topic for envelope in bus.captured]
    assert TOPIC_BACKPOOL_WORKER_ACQUIRED in topics
    assert TOPIC_TASK_LEASED in topics
    assert TOPIC_BACKPOOL_WORKER_RELEASED in topics


@pytest.mark.skip(reason="BP-27: pool dispatch uses _dispatch_via_back_pool, not route_back_envelope; test needs handler-level mocks")
@pytest.mark.asyncio
async def test_runtime_schedules_multiple_back_workers_and_overflows_when_full(monkeypatch) -> None:
    pool = BackPool(BackPoolConfig(pool_size=2, max_concurrent_per_session=2))
    router = BackTopicRouter(pool)
    ready_queue = ReadyQueue()
    back_mailbox = _Mailbox()
    runtime = _runtime(pool=pool, router=router, ready_queue=ready_queue, back_mailbox=back_mailbox)

    started: dict[str, asyncio.Event] = {tid: asyncio.Event() for tid in ("t1", "t2", "t3")}
    release: dict[str, asyncio.Event] = {tid: asyncio.Event() for tid in ("t1", "t2", "t3")}

    async def fake_route_back_envelope(envelope: Envelope, **kwargs):  # noqa: ANN202, ARG001
        task_id = _payload(envelope)["task_id"]
        started[task_id].set()
        await release[task_id].wait()
        return ReactResult(status="complete")

    monkeypatch.setattr("k1.concierge.actors.back.route_back_envelope", fake_route_back_envelope)

    for task_id in ("t1", "t2", "t3"):
        back_mailbox.push(build_task_dispatch({"task_id": task_id}))

    consumer = asyncio.create_task(runtime._mailbox_consumer())
    try:
        await asyncio.wait_for(started["t1"].wait(), timeout=1.0)
        await asyncio.wait_for(started["t2"].wait(), timeout=1.0)
        await asyncio.sleep(0)

        assert pool.active_count == 2
        assert pool.overflow_depth == 1
        assert not started["t3"].is_set()

        release["t1"].set()
        await asyncio.wait_for(started["t3"].wait(), timeout=1.0)

        assert pool.active_count == 2
    finally:
        for event in release.values():
            event.set()
        consumer.cancel()
        with suppress(asyncio.CancelledError):
            await consumer


@pytest.mark.skip(reason="BP-27: _lease_watcher_task wiring is product-gated (Milestone B)")
@pytest.mark.asyncio
async def test_runtime_start_stop_manages_backpool_lease_watcher() -> None:
    pool = BackPool(
        BackPoolConfig(
            pool_size=1,
            reclaim_check_interval_s=60.0,
        )
    )
    runtime = _runtime(pool=pool, router=BackTopicRouter(pool), ready_queue=ReadyQueue())

    await runtime.start()
    watcher = runtime._lease_watcher_task
    assert watcher is not None
    assert not watcher.done()

    await runtime.stop()
    assert runtime._lease_watcher_task is None
    assert watcher.done()


@pytest.mark.skip(reason="BP-27: _enqueue_or_run_back_envelope not yet implemented")
@pytest.mark.asyncio
async def test_cancel_envelope_bypasses_worker_acquisition(monkeypatch) -> None:
    cancelled = asyncio.Event()
    seen_tokens: list[object] = []

    def fake_cancel_handler(
        *, envelope: Envelope, fsm_state=None, cancel_token=None
    ):  # noqa: ANN001, ANN202, ARG001
        seen_tokens.append(cancel_token)
        cancelled.set()

    monkeypatch.setattr("k1.concierge.actors.back.back_cancel_handler", fake_cancel_handler)

    pool = BackPool(BackPoolConfig(pool_size=1))
    router = BackTopicRouter(pool)
    ready_queue = ReadyQueue()
    runtime = _runtime(pool=pool, router=router, ready_queue=ready_queue)

    slot = pool.acquire_worker("t-cancel")
    active_before = pool.active_count

    await runtime._enqueue_or_run_back_envelope(build_task_cancel({"task_id": "t-cancel"}))

    assert cancelled.is_set()
    assert pool.active_count == active_before
    assert seen_tokens == [slot.lease.cancellation_token]


@pytest.mark.skip(reason="BP-27: _enqueue_or_run_back_envelope not yet implemented")
@pytest.mark.asyncio
async def test_runtime_binds_fsm_cancel_token_to_backpool_lease_and_handler(monkeypatch) -> None:
    token = CancellationToken(task_id="t-fsm")
    fsm = SimpleNamespace(
        state=SimpleNamespace(name="COMPANIONING"),
        _opp_pipeline=None,
        get_cancel_token=lambda task_id: token if task_id == "t-fsm" else None,
    )
    pool = BackPool(BackPoolConfig(pool_size=1))
    router = BackTopicRouter(pool)
    ready_queue = ReadyQueue()
    runtime = _runtime(pool=pool, router=router, ready_queue=ready_queue, fsm=fsm)
    seen: dict[str, object] = {}

    async def fake_route_back_envelope(envelope: Envelope, **kwargs):  # noqa: ANN202
        task_id = _payload(envelope)["task_id"]
        lease = pool.get_lease(task_id)
        seen["lease_token"] = lease.cancellation_token
        seen["handler_token"] = kwargs.get("cancel_token")
        return ReactResult(status="complete")

    monkeypatch.setattr("k1.concierge.actors.back.route_back_envelope", fake_route_back_envelope)

    await runtime._enqueue_or_run_back_envelope(build_task_dispatch({"task_id": "t-fsm"}))
    assert await runtime._schedule_ready_back_envelopes() == 1
    await asyncio.gather(*runtime.active_back_tasks.values())

    assert seen["lease_token"] is token
    assert seen["handler_token"] is token
    assert pool.active_count == 0


@pytest.mark.skip(reason="BP-27: _enqueue_or_run_back_envelope not yet implemented")
@pytest.mark.asyncio
async def test_resume_and_clarification_envelopes_route_to_resume_handler(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_resume_handler(envelope: Envelope, **kwargs):  # noqa: ANN202, ARG001
        calls.append(getattr(envelope, "topic", ""))
        return ReactResult(status="complete")

    monkeypatch.setattr("k1.concierge.actors.back.back_resume_handler", fake_resume_handler)

    pool = BackPool(BackPoolConfig(pool_size=2))
    router = BackTopicRouter(pool)
    ready_queue = ReadyQueue()
    runtime = _runtime(pool=pool, router=router, ready_queue=ready_queue)

    await runtime._enqueue_or_run_back_envelope(build_task_resume({"task_id": "t-resume"}))
    await runtime._enqueue_or_run_back_envelope(
        build_clarification_response({"task_id": "t-clarify", "response": "yes"})
    )
    assert await runtime._schedule_ready_back_envelopes() == 2
    await asyncio.gather(*runtime.active_back_tasks.values())

    assert calls == [
        TOPIC_TASK_RESUME,
        TOPIC_CLARIFICATION_RESPONSE,
    ]
    assert pool.active_count == 0


@pytest.mark.skip(reason="BP-27: _enqueue_or_run_back_envelope not yet implemented")
@pytest.mark.asyncio
async def test_failed_dependency_publishes_failure_without_invoking_back(monkeypatch) -> None:
    invoked: list[str] = []

    async def fake_route_back_envelope(envelope: Envelope, **kwargs):  # noqa: ANN202, ARG001
        invoked.append(_payload(envelope)["task_id"])
        return ReactResult(status="budget_exhausted")

    monkeypatch.setattr("k1.concierge.actors.back.route_back_envelope", fake_route_back_envelope)

    pool = BackPool(BackPoolConfig(pool_size=1))
    router = BackTopicRouter(pool)
    ready_queue = ReadyQueue()
    runtime = _runtime(pool=pool, router=router, ready_queue=ready_queue)

    parent = build_task_dispatch({"task_id": "parent"})
    child = build_task_dispatch({"task_id": "child", "depends_on": "parent"})

    await runtime._enqueue_or_run_back_envelope(parent)
    await runtime._enqueue_or_run_back_envelope(child)
    assert await runtime._schedule_ready_back_envelopes() == 1

    task = next(iter(runtime.active_back_tasks.values()))
    await task

    assert invoked == ["parent"]
    assert len(runtime.bus.published) == 1
    failed_payload = _payload(runtime.bus.published[0])
    assert failed_payload["task_id"] == "child"
    assert failed_payload["reason"] == "dependency_failed"


@pytest.mark.skip(reason="BP-27: KernelService Tier 2 + KernelConfig backpool fields are Milestone B")
@pytest.mark.asyncio
async def test_kernel_service_tier2_session_reaches_factory_backpool_wiring(tmp_path) -> None:
    from k1.kernel.service import KernelService

    config = KernelConfig(
        sessionstate_db_path=str(tmp_path / "sessionstate.db"),
        backpool_size=2,
        backpool_max_concurrent_per_session=1,
        backpool_lease_ttl_s=30.0,
    )
    service = KernelService(config=config)
    await service.startup()
    try:
        session = await service._create_session_tier2("m8-e5")
        runtime = session.concierge

        assert runtime.back_pool is not None
        assert runtime.back_topic_router is not None
        assert runtime.ready_queue is not None
        assert getattr(runtime.fsm, "_back_pool") is runtime.back_pool
        assert runtime.back_pool.config.pool_size == 2
        assert runtime.back_pool.config.max_concurrent_per_session == 1
        assert runtime.back_pool.config.lease_ttl_s == 30.0
    finally:
        await service.shutdown()
