from __future__ import annotations

import sys
import types
from typing import Any, Callable, Iterator

from ward import fixture, test  # type: ignore[attr-defined]

from k0.drivers.alias_map import AliasMap
from k0.outbox import (
    OutboxWorker,
    RetryScheduler,
    compute_fingerprint,
    load_driver_from_alias_map,
)
from k0.storage.dlq import DeadLetterQueue
from k0.storage.outbox import OutboxEntry, OutboxStore
from k0.uow.connection_pool import connection_scope
from tests.storage.fixtures import sqlite_runtime  # type: ignore[misc]


@fixture
def driver_module_factory() -> (
    Iterator[Callable[[str, Callable[[OutboxEntry], None]], str]]
):
    registered: list[str] = []

    def _register(module_stub: str, handler: Callable[[OutboxEntry], None]) -> str:
        module_name = f"k0.drivers.{module_stub}"
        module = types.ModuleType(module_name)

        class Driver:  # noqa: D401 - simple test helper
            """Test driver wrapper delegating to the provided handler."""

            def apply(self, entry: OutboxEntry) -> None:
                handler(entry)

        setattr(module, "Driver", Driver)
        sys.modules[module_name] = module
        registered.append(module_name)
        return module_stub

    try:
        yield _register
    finally:
        for module_name in registered:
            sys.modules.pop(module_name, None)


@test("compute_fingerprint is deterministic across invocations")
def _(sqlite_runtime_fixture: Any = sqlite_runtime) -> None:
    del sqlite_runtime_fixture
    payload = b"payload"
    driver = "driver-test"
    op_kind = "UPSERT"
    first = compute_fingerprint(driver, op_kind, payload)
    second = compute_fingerprint(driver, op_kind, payload)
    altered = compute_fingerprint(driver, op_kind, b"alt")
    assert first == second
    assert first != altered


@test("outbox worker applies entries and clears them from the store")
def _(
    driver_module_factory_fixture: Any = driver_module_factory,
    sqlite_runtime_fixture: Any = sqlite_runtime,
) -> None:
    del sqlite_runtime_fixture
    applied: list[int] = []

    def _apply(entry: OutboxEntry) -> None:
        applied.append(int(entry.id or -1))

    alias_key = driver_module_factory_fixture(
        "worker_success",
        _apply,
    )

    alias_map = AliasMap(bindings={"driver-success": alias_key})
    store = OutboxStore()
    worker = OutboxWorker(
        outbox_store=store,
        dead_letter_queue=DeadLetterQueue(),
        retry_scheduler=RetryScheduler(max_attempts=3),
        driver_loader=load_driver_from_alias_map(alias_map),
        batch_size=8,
    )

    entry = OutboxEntry(
        id=None,
        wal_pos=1,
        tenant_id="tenant-A",
        space_id="space-A",
        driver="driver-success",
        op_kind="UPSERT",
        payload=b"payload",
        fingerprint=compute_fingerprint("driver-success", "UPSERT", b"payload"),
        requeue_seq=0,
        retries=0,
        last_error=None,
    )

    entry_id = store.enqueue(entry)
    worker.process_driver("driver-success")

    assert applied == [entry_id]
    assert store.dequeue_batch("driver-success", limit=4) == []


@test("outbox worker records retries before eventual success")
def _(
    driver_module_factory_fixture: Any = driver_module_factory,
    sqlite_runtime_fixture: Any = sqlite_runtime,
) -> None:
    del sqlite_runtime_fixture
    attempts = {"count": 0}

    def _handler(_: OutboxEntry) -> None:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("transient failure")

    alias_key = driver_module_factory_fixture("worker_retry", _handler)
    alias_map = AliasMap(bindings={"driver-retry": alias_key})
    store = OutboxStore()
    worker = OutboxWorker(
        outbox_store=store,
        dead_letter_queue=DeadLetterQueue(),
        retry_scheduler=RetryScheduler(max_attempts=5),
        driver_loader=load_driver_from_alias_map(alias_map),
        batch_size=2,
    )

    entry = OutboxEntry(
        id=None,
        wal_pos=2,
        tenant_id="tenant-A",
        space_id="space-A",
        driver="driver-retry",
        op_kind="UPSERT",
        payload=b"payload",
        fingerprint=compute_fingerprint("driver-retry", "UPSERT", b"payload"),
        requeue_seq=0,
        retries=0,
        last_error=None,
    )

    entry_id = store.enqueue(entry)

    worker.process_driver("driver-retry")
    with connection_scope() as connection:
        row = connection.execute(
            "SELECT retries, requeue_seq, last_error FROM st_outbox WHERE id=?",
            (entry_id,),
        ).fetchone()
        assert row["retries"] == 1
        assert row["requeue_seq"] >= 1
        assert row["last_error"] == "transient failure"

    worker.process_driver("driver-retry")
    with connection_scope() as connection:
        row = connection.execute(
            "SELECT retries, requeue_seq FROM st_outbox WHERE id=?",
            (entry_id,),
        ).fetchone()
        assert row["retries"] == 2
        assert row["requeue_seq"] > 1

    worker.process_driver("driver-retry")
    assert store.dequeue_batch("driver-retry", limit=2) == []
    assert attempts["count"] == 3


@test("outbox worker moves exhausted entries to the dead-letter queue")
def _(
    driver_module_factory_fixture: Any = driver_module_factory,
    sqlite_runtime_fixture: Any = sqlite_runtime,
) -> None:
    del sqlite_runtime_fixture

    def _handler(_: OutboxEntry) -> None:
        raise RuntimeError("permanent failure")

    alias_key = driver_module_factory_fixture("worker_dlq", _handler)
    alias_map = AliasMap(bindings={"driver-dlq": alias_key})
    dlq = DeadLetterQueue()
    store = OutboxStore()
    worker = OutboxWorker(
        outbox_store=store,
        dead_letter_queue=dlq,
        retry_scheduler=RetryScheduler(max_attempts=2),
        driver_loader=load_driver_from_alias_map(alias_map),
        batch_size=1,
    )

    entry = OutboxEntry(
        id=None,
        wal_pos=3,
        tenant_id="tenant-A",
        space_id="space-A",
        driver="driver-dlq",
        op_kind="UPSERT",
        payload=b"payload",
        fingerprint=compute_fingerprint("driver-dlq", "UPSERT", b"payload"),
        requeue_seq=0,
        retries=0,
        last_error=None,
    )

    store.enqueue(entry)

    worker.process_driver("driver-dlq")
    worker.process_driver("driver-dlq")

    assert store.dequeue_batch("driver-dlq", limit=1) == []
    letters = dlq.list_pending(limit=5)
    assert letters
    recorded = letters[0]
    assert recorded.reason.startswith("driver-dlq:RuntimeError")
    assert recorded.retries == 2
    assert recorded.requeue_seq == 1
    assert recorded.driver == "driver-dlq"
    assert recorded.op_kind == "UPSERT"
    assert recorded.fingerprint == entry.fingerprint
    assert recorded.state == "PENDING"
    assert recorded.wal_pos == 3
    assert recorded.payload == b"payload"
    assert recorded.payload == b"payload"
    assert recorded.payload == b"payload"
    assert recorded.payload == b"payload"
    assert recorded.payload == b"payload"
    assert recorded.payload == b"payload"
    assert recorded.payload == b"payload"
    assert recorded.payload == b"payload"
    assert recorded.payload == b"payload"
    assert recorded.payload == b"payload"
    assert recorded.payload == b"payload"
    assert recorded.op_kind == "UPSERT"
    assert recorded.fingerprint == entry.fingerprint
    assert recorded.state == "PENDING"
    assert recorded.wal_pos == 3
    assert recorded.payload == b"payload"
