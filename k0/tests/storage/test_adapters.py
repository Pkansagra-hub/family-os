from __future__ import annotations

from typing import Any

from ward import test  # type: ignore[attr-defined]

from k0.obs import MetricsExporter
from k0.storage.dlq import DeadLetter, DeadLetterQueue
from k0.storage.offsets import Offset, OffsetStore
from k0.storage.outbox import OutboxEntry, OutboxStore
from k0.storage.provisioning import DeviceKey, ProvisionedDevice, ProvisioningLedger
from k0.storage.receipts import Receipt, ReceiptStore
from k0.storage.wal import WalEntry, WriteAheadLog
from k0.uow.connection_pool import connection_scope
from tests.storage.fixtures import sqlite_runtime  # type: ignore[misc]


@test("write-ahead log appends entries and reads them back in order")
def _(_sqlite_runtime: Any = sqlite_runtime) -> None:
    del _sqlite_runtime
    wal = WriteAheadLog()
    entry = WalEntry(
        tenant_id="tenant-A",
        space_id="space-A",
        topic="memory.topic",
        envelope_json='{"key":"value"}',
        schema_uri="schema://memory/topic",
        schema_version="1.0.0",
        device_id="device-A",
        commit_ts="2025-09-28T12:00:00Z",
        body=b"payload",
        payload_sha256="a" * 64,
        idem_key="idem-1",
    )

    position = wal.append(entry)
    assert position > 0

    entries = wal.read_from(0, limit=10)
    assert len(entries) == 1
    stored = entries[0]
    assert stored.position == position
    assert stored.tenant_id == entry.tenant_id
    assert stored.payload_sha256 == entry.payload_sha256


@test("receipt store persists and retrieves receipts by identifier")
def _(_sqlite_runtime: Any = sqlite_runtime) -> None:
    del _sqlite_runtime
    store = ReceiptStore()
    receipt = Receipt(
        receipt_id="rcpt-123",
        idem_key="idem-123",
        wal_pos=42,
        commit_ts="2025-09-28T12:00:00Z",
        tenant_id="tenant-A",
        space_id="space-A",
        device_id="device-A",
        mls_group_id="mls-1",
        key_version="v1",
        device_sig="sig-abc",
    )

    store.save(receipt)
    fetched = store.get(receipt.receipt_id)
    assert fetched == receipt


@test("offset store upserts and fetches subscriber offsets")
def _(_sqlite_runtime: Any = sqlite_runtime) -> None:
    del _sqlite_runtime
    store = OffsetStore()
    record = Offset(
        subscriber_id="subscriber-1",
        topic="memory.topic",
        space_id="space-A",
        tenant_id="tenant-A",
        offset=100,
        updated_ts="2025-09-28T12:00:00Z",
    )

    store.upsert(record)
    fetched = store.fetch("subscriber-1", "memory.topic", "space-A", "tenant-A")
    assert fetched == record

    updated = Offset(
        subscriber_id="subscriber-1",
        topic="memory.topic",
        space_id="space-A",
        tenant_id="tenant-A",
        offset=250,
        updated_ts="2025-09-28T12:05:00Z",
    )
    store.upsert(updated)
    fetched_updated = store.fetch("subscriber-1", "memory.topic", "space-A", "tenant-A")
    assert fetched_updated == updated


@test("outbox store enqueues, dequeues, and marks entries as applied")
def _(_sqlite_runtime: Any = sqlite_runtime) -> None:
    del _sqlite_runtime
    store = OutboxStore()
    entry = OutboxEntry(
        id=None,
        wal_pos=1,
        tenant_id="tenant-A",
        space_id="space-A",
        driver="driver-A",
        op_kind="UPSERT",
        payload=b"body",
        fingerprint="fingerprint-1",
        requeue_seq=0,
        retries=0,
        last_error=None,
    )

    entry_id = store.enqueue(entry)
    assert entry_id == entry.id

    batch = store.dequeue_batch("driver-A", limit=10)
    assert batch and batch[0].id == entry_id

    store.mark_applied(entry_id)
    assert store.dequeue_batch("driver-A", limit=10) == []


@test("outbox store updates pending gauges when metrics configured")
def _(_sqlite_runtime: Any = sqlite_runtime) -> None:
    del _sqlite_runtime
    metrics = MetricsExporter(namespace="k0_outbox_test")
    store = OutboxStore(metrics=metrics)
    entry = OutboxEntry(
        id=None,
        wal_pos=1,
        tenant_id="tenant-A",
        space_id="space-A",
        driver="driver-A",
        op_kind="UPSERT",
        payload=b"body",
        fingerprint="fingerprint-1",
        requeue_seq=0,
        retries=0,
        last_error=None,
    )

    entry_id = store.enqueue(entry)
    assert entry_id == entry.id

    gauge = metrics.gauge(
        "outbox_pending_total",
        "Auto-generated gauge for outbox_pending_total",
        labelnames=("driver",),
    )
    assert gauge.labels(driver="*")._value.get() == 1.0  # type: ignore[attr-defined]
    assert gauge.labels(driver="driver-A")._value.get() == 1.0  # type: ignore[attr-defined]

    store.mark_applied(entry_id)

    assert gauge.labels(driver="*")._value.get() == 0.0  # type: ignore[attr-defined]
    assert gauge.labels(driver="driver-A")._value.get() == 0.0  # type: ignore[attr-defined]


@test("dead-letter queue records failures and lists them in order")
def _(_sqlite_runtime: Any = sqlite_runtime) -> None:
    del _sqlite_runtime
    queue = DeadLetterQueue()
    letter = DeadLetter(
        id=None,
        wal_pos=None,
        tenant_id="tenant-A",
        space_id="space-A",
        driver="driver-A",
        op_kind="UPSERT",
        fingerprint="abc123",
        payload=b"payload",
        reason="driver failure",
        retries=3,
        requeue_seq=1,
        first_failure_ts="2025-09-28T12:00:00Z",
        last_failure_ts="2025-09-28T12:05:00Z",
        state="PENDING",
    )

    record_id = queue.record(letter)
    assert record_id == letter.id

    letters = queue.list_pending(limit=5)
    assert letters and letters[0].id == record_id
    stored = letters[0]
    assert stored.driver == "driver-A"
    assert stored.retries == 3
    assert stored.requeue_seq == 1
    assert stored.state == "PENDING"


@test("dead-letter queue updates state when requeued or quarantined")
def _(_sqlite_runtime: Any = sqlite_runtime) -> None:
    del _sqlite_runtime
    queue = DeadLetterQueue()
    letter = DeadLetter(
        id=None,
        wal_pos=10,
        tenant_id="tenant-A",
        space_id="space-A",
        driver="driver-A",
        op_kind="UPSERT",
        fingerprint="fingerprint-1",
        payload=b"payload",
        reason="retry exhausted",
        retries=5,
        requeue_seq=4,
        first_failure_ts="2025-09-28T12:00:00Z",
        last_failure_ts="2025-09-28T12:05:00Z",
        state="PENDING",
    )
    queue.record(letter)
    assert letter.id is not None

    with connection_scope() as conn:
        queue.mark_requeued(letter.id, requeue_seq=5, connection=conn)
        conn.commit()

    stored = queue.get(letter.id)
    assert stored is not None and stored.state == "REQUEUED"
    assert stored.requeue_seq == 5

    assert queue.purge(letter.id) is True
    stored_after = queue.get(letter.id)
    assert stored_after is not None and stored_after.state == "QUARANTINED"


@test("provisioning ledger registers devices and updates cache on overwrite")
def _(_sqlite_runtime: Any = sqlite_runtime) -> None:
    del _sqlite_runtime
    ledger = ProvisioningLedger(cache_size=4)
    device = ProvisionedDevice(
        device_id="device-A",
        tenant_id="tenant-A",
        space_id="space-A",
        mls_group_id="mls-1",
        provisioned_ts="2025-09-28T12:00:00Z",
    )
    key_v1 = DeviceKey(
        device_id="device-A",
        key_version="v1",
        verify_key="verify-key-1",
        key_state="ACTIVE",
        registered_ts="2025-09-28T12:00:00Z",
        activated_ts="2025-09-28T12:00:00Z",
    )

    stored = ledger.register(device)
    assert stored == device
    ledger.add_key(key_v1)

    fetched = ledger.lookup("tenant-A", "space-A", "device-A")
    assert fetched == device

    keys = ledger.get_keys("device-A", states=["ACTIVE"])
    assert len(keys) == 1
    assert keys[0].key_version == "v1"
    assert keys[0].verify_key == "verify-key-1"

    # Test device update (same device, new timestamp)
    updated_device = ProvisionedDevice(
        device_id="device-A",
        tenant_id="tenant-A",
        space_id="space-A",
        mls_group_id="mls-1",
        provisioned_ts="2025-09-28T13:00:00Z",
    )
    key_v2 = DeviceKey(
        device_id="device-A",
        key_version="v2",
        verify_key="verify-key-2",
        key_state="ACTIVE",
        registered_ts="2025-09-28T13:00:00Z",
        activated_ts="2025-09-28T13:00:00Z",
    )
    ledger.register(updated_device)
    ledger.add_key(key_v2)

    refreshed = ledger.lookup("tenant-A", "space-A", "device-A")
    assert refreshed == updated_device

    keys_after = ledger.get_keys("device-A", states=["ACTIVE"])
    assert len(keys_after) == 2  # Both v1 and v2 keys are ACTIVE

    ledger.clear_cache()
    assert ledger.lookup("tenant-X", "space-X", "device-X") is None
    assert ledger.lookup("tenant-X", "space-X", "device-X") is None
    assert ledger.lookup("tenant-X", "space-X", "device-X") is None
    assert ledger.lookup("tenant-X", "space-X", "device-X") is None
    assert ledger.lookup("tenant-X", "space-X", "device-X") is None
    assert ledger.lookup("tenant-X", "space-X", "device-X") is None
