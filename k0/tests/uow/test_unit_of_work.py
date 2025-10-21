from __future__ import annotations

from typing import Any, Dict, Tuple

from hypothesis import given, settings
from hypothesis import strategies as st
from ward import raises, test  # type: ignore[attr-defined]

from k0.storage.offsets import Offset, OffsetStore
from k0.storage.outbox import OutboxEntry, OutboxStore
from k0.storage.receipts import Receipt, ReceiptStore
from k0.storage.wal import WalEntry, WriteAheadLog
from k0.uow.connection_pool import connection_scope
from k0.uow.unit_of_work import UnitOfWork
from tests.storage.fixtures import sqlite_runtime  # type: ignore[misc]


class MetricsRecorder:
    def __init__(self) -> None:
        self.records: list[Tuple[str, float, Dict[str, str]]] = []

    def __call__(self, metric_name: str, value: float, **labels: str) -> None:
        self.records.append((metric_name, value, dict(labels)))

    def metric_count(self, metric_name: str, **expected: str) -> int:
        count = 0
        for name, _value, labels in self.records:
            if name != metric_name:
                continue
            if all(labels.get(k) == v for k, v in expected.items()):
                count += 1
        return count


def _run_property(outcomes: list[bool]) -> None:
    _reset_database()
    wal = WriteAheadLog()
    outbox = OutboxStore()
    receipts = ReceiptStore()
    offsets = OffsetStore()
    metrics = MetricsRecorder()

    committed = 0

    for idx, should_succeed in enumerate(outcomes):
        entry_payload = f"payload-{idx}".encode()
        wal_entry = WalEntry(
            tenant_id="tenant-A",
            space_id="space-A",
            topic="memory.topic",
            envelope_json='{"key":"value"}',
            schema_uri="schema://memory/topic",
            schema_version="1.0.0",
            device_id="device-A",
            commit_ts=f"2025-09-28T12:00:0{idx}Z",
            body=entry_payload,
            payload_sha256="c" * 64,
            idem_key=f"idem-{idx}",
        )

        uow = UnitOfWork(
            outbox_store=outbox,
            write_ahead_log=wal,
            receipt_store=receipts,
            offset_store=offsets,
            metrics_emitter=metrics,
        )
        if should_succeed:
            with uow as active:
                wal_pos = active.append_wal(wal_entry)
                outbox_entry = OutboxEntry(
                    id=None,
                    wal_pos=wal_pos,
                    tenant_id=wal_entry.tenant_id,
                    space_id=wal_entry.space_id,
                    driver="driver-A",
                    op_kind="UPSERT",
                    payload=entry_payload,
                    fingerprint=f"fp-{idx}",
                    requeue_seq=0,
                    retries=0,
                    last_error=None,
                )
                receipt = Receipt(
                    receipt_id=f"receipt-{idx:02d}",
                    idem_key=wal_entry.idem_key or f"idem-{idx}",
                    wal_pos=wal_pos,
                    commit_ts=wal_entry.commit_ts,
                    tenant_id=wal_entry.tenant_id,
                    space_id=wal_entry.space_id,
                    device_id=wal_entry.device_id,
                    mls_group_id="mls-group",
                    key_version="v1",
                    device_sig="sig-placeholder",
                )
                offset = Offset(
                    subscriber_id=f"subscriber-{idx:02d}",
                    topic=wal_entry.topic,
                    space_id=wal_entry.space_id,
                    tenant_id=wal_entry.tenant_id,
                    offset=wal_pos,
                    updated_ts=wal_entry.commit_ts,
                )
                active.stage_outbox(outbox_entry)
                active.save_receipt(receipt)
                active.upsert_offset(offset)
            committed += 1
        else:
            try:
                with uow as active:
                    wal_pos = active.append_wal(wal_entry)
                    outbox_entry = OutboxEntry(
                        id=None,
                        wal_pos=wal_pos,
                        tenant_id=wal_entry.tenant_id,
                        space_id=wal_entry.space_id,
                        driver="driver-A",
                        op_kind="UPSERT",
                        payload=entry_payload,
                        fingerprint=f"fp-{idx}",
                        requeue_seq=0,
                        retries=0,
                        last_error=None,
                    )
                    receipt = Receipt(
                        receipt_id=f"receipt-failure-{idx:02d}",
                        idem_key=wal_entry.idem_key or f"idem-failure-{idx}",
                        wal_pos=wal_pos,
                        commit_ts=wal_entry.commit_ts,
                        tenant_id=wal_entry.tenant_id,
                        space_id=wal_entry.space_id,
                        device_id=wal_entry.device_id,
                        mls_group_id="mls-group",
                        key_version="v1",
                        device_sig="sig-placeholder",
                    )
                    offset = Offset(
                        subscriber_id=f"subscriber-failure-{idx:02d}",
                        topic=wal_entry.topic,
                        space_id=wal_entry.space_id,
                        tenant_id=wal_entry.tenant_id,
                        offset=wal_pos,
                        updated_ts=wal_entry.commit_ts,
                    )
                    active.stage_outbox(outbox_entry)
                    active.save_receipt(receipt)
                    active.upsert_offset(offset)
                    raise RuntimeError("simulated failure")
            except RuntimeError:
                pass

    with connection_scope() as connection:
        outbox_count = connection.execute("SELECT COUNT(*) FROM st_outbox").fetchone()[
            0
        ]
        receipt_count = connection.execute("SELECT COUNT(*) FROM st_receipts").fetchone()[
            0
        ]
        offset_count = connection.execute("SELECT COUNT(*) FROM st_offsets").fetchone()[
            0
        ]
    assert outbox_count == committed
    assert receipt_count == committed
    assert offset_count == committed

    total_rollbacks = len(outcomes) - committed
    assert metrics.metric_count("k0_uow_commit_total", outcome="success") == committed
    assert (
        metrics.metric_count("k0_uow_wal_fsync_total", outcome="success")
        == committed
    )
    assert (
        metrics.metric_count("k0_uow_wal_fsync_seconds", outcome="success")
        == committed
    )
    assert metrics.metric_count("k0_uow_rollback_total") == total_rollbacks


@given(st.lists(st.booleans(), min_size=1, max_size=5))
@settings(max_examples=50)
def _hypothesis_property(outcomes: list[bool]) -> None:
    _run_property(outcomes)


@test("unit of work commits successful transactions and rolls back failures")
def _(sqlite_runtime: Any = sqlite_runtime) -> None:
    _hypothesis_property()


@test("unit of work rejects nested usage")
def _(sqlite_runtime: Any = sqlite_runtime) -> None:
    outbox = OutboxStore()
    uow = UnitOfWork(outbox_store=outbox)

    with uow:
        with raises(RuntimeError):
            with uow:
                pass


def _reset_database() -> None:
    with connection_scope() as connection:
        connection.execute("DELETE FROM st_outbox")
        connection.execute("DELETE FROM st_wal")
        connection.execute("DELETE FROM st_receipts")
        connection.execute("DELETE FROM st_offsets")
        connection.commit()
