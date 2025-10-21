from __future__ import annotations

import sqlite3
from types import GeneratorType
from typing import Iterator, cast

from ward import raises, test  # type: ignore[attr-defined]

from k0.kernel.config import KernelSettings
from k0.kernel.dependencies import (
    PolicyContext,
    RequestDependencyProvider,
    database_session,
    policy_context_dependency,
    qos_context_dependency,
    scheduler_dependency,
    telemetry_span_factory,
)
from k0.obs.tracing import TracerFactory
from k0.qos import QoSContext, Scheduler


@test("dependency provider exposes database, policy, and telemetry factories")
def _() -> None:
    settings = KernelSettings.load(overrides={"database": {"path": ":memory:"}})
    provider = RequestDependencyProvider(settings=settings)
    qos_settings = getattr(settings, "qos")
    fanout_max = int(getattr(qos_settings, "fanout_max"))
    top_k_max = int(getattr(qos_settings, "top_k_max"))
    scheduler_profile = str(getattr(qos_settings, "scheduler_profile"))

    overrides = provider.as_fastapi_overrides()
    assert set(overrides.keys()) == {
        database_session,
        policy_context_dependency,
        telemetry_span_factory,
        scheduler_dependency,
        qos_context_dependency,
    }

    session_callable = overrides[database_session]
    session_gen = session_callable()
    assert isinstance(session_gen, GeneratorType)

    connection = next(cast(Iterator[sqlite3.Connection], session_gen))
    try:
        cursor = connection.execute("SELECT 1")
        assert cursor.fetchone()[0] == 1
    finally:
        session_gen.close()

    with raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")

    policy_ctx = cast(PolicyContext, overrides[policy_context_dependency]())
    assert policy_ctx.environment == settings.environment
    assert policy_ctx.scheduler_profile == scheduler_profile

    tracer = cast(TracerFactory, overrides[telemetry_span_factory]())
    trace_id = tracer.new_trace_id()
    assert isinstance(trace_id, str)
    assert len(trace_id) > 0

    scheduler = cast(Scheduler, overrides[scheduler_dependency]())
    qos_context = cast(QoSContext, overrides[qos_context_dependency]())
    assert isinstance(qos_context, QoSContext)
    assert qos_context.scheduler is scheduler
    assert qos_context.fanout_budget == fanout_max
    assert qos_context.top_k_budget == top_k_max
    assert scheduler.profile.port_limits["command"] >= max(4, fanout_max * 4)
    qos_context.tighten(fanout=fanout_max - 1)
    assert qos_context.fanout_budget == fanout_max - 1
    another_context = cast(QoSContext, overrides[qos_context_dependency]())
    assert another_context is not qos_context
    assert another_context.scheduler is scheduler
