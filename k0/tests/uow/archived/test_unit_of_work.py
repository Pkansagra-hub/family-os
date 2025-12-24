from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, Iterator, Tuple

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from k0.storage.offsets import Offset, OffsetStore
from k0.storage.outbox import OutboxEntry, OutboxStore
from k0.storage.receipts import Receipt, ReceiptStore
from k0.storage.wal import WalEntry, WriteAheadLog
from k0.uow.connection_pool import configure_pool, connection_scope, shutdown_pool
from k0.uow.unit_of_work import UnitOfWork

REPO_ROOT = Path(__file__).resolve().parents[2]
STORAGE_SQL_PATH = REPO_ROOT / "contracts" / "sql" / "storage.sql"


@pytest.fixture
def sqlite_runtime() -> Iterator[Path]:
    """Pytest fixture for SQLite runtime with schema initialization."""
    tmp_dir = TemporaryDirectory(ignore_cleanup_errors=True)
    db_path = Path(tmp_dir.name) / "kernel.sqlite3"
    configure_pool(db_path)
    with connection_scope() as connection:
        connection.executescript(STORAGE_SQL_PATH.read_text())
        connection.commit()
    try:
        yield db_path
    finally:
        shutdown_pool()
        tmp_dir.cleanup()


class MetricsRecorder:
    """Mock metrics recorder for tracking metric emissions during tests."""

    def __init__(self) -> None:
        self.records: list[Tuple[str, float, Dict[str, str]]] = []

    def __call__(self, metric_name: str, value: float, **labels: str) -> None:
        """Record a metric with name, value, and labels."""
        self.records.append((metric_name, value, dict(labels)))

    def metric_count(self, metric_name: str, **expected: str) -> int:
        """Count metrics matching name and label filters."""
        count = 0
        for name, _value, labels in self.records:
            if name != metric_name:
                continue
            if all(labels.get(k) == v for k, v in expected.items()):
                count += 1
        return count


def _reset_database() -> None:
    """Reset all transaction storage tables."""
    with connection_scope() as connection:
        connection.execute("DELETE FROM st_outbox")
        connection.execute("DELETE FROM st_wal")
        connection.execute("DELETE FROM st_receipts")
        connection.execute("DELETE FROM st_offsets")
        connection.commit()


def _run_property_test(outcomes: list[bool]) -> None:
    """Property-based test runner: execute mixed success/failure transactions."""
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

    # Verify atomicity: only committed transactions persisted
    with connection_scope() as connection:
        outbox_count = connection.execute("SELECT COUNT(*) FROM st_outbox").fetchone()[0]
        receipt_count = connection.execute("SELECT COUNT(*) FROM st_receipts").fetchone()[0]
        offset_count = connection.execute("SELECT COUNT(*) FROM st_offsets").fetchone()[0]

    assert outbox_count == committed, f"outbox: expected {committed}, got {outbox_count}"
    assert receipt_count == committed, f"receipts: expected {committed}, got {receipt_count}"
    assert offset_count == committed, f"offsets: expected {committed}, got {offset_count}"

    # Verify metrics
    total_rollbacks = len(outcomes) - committed
    assert (
        metrics.metric_count("k0_uow_commit_total", outcome="success") == committed
    ), "commit_total metric mismatch"
    assert (
        metrics.metric_count("k0_uow_wal_fsync_total", outcome="success") == committed
    ), "wal_fsync_total metric mismatch"
    assert (
        metrics.metric_count("k0_uow_wal_fsync_seconds", outcome="success") == committed
    ), "wal_fsync_seconds metric mismatch"
    assert (
        metrics.metric_count("k0_uow_rollback_total") == total_rollbacks
    ), f"rollback_total: expected {total_rollbacks}, got {metrics.metric_count('k0_uow_rollback_total')}"


def test_uow_atomicity_property_based(sqlite_runtime: Path) -> None:
    """Property-based test: UnitOfWork maintains atomicity across random success/failure sequences.

    Uses hypothesis to generate random success/failure transaction sequences and verifies
    that atomicity is maintained: either all stages commit together or all rollback together.
    """

    @given(st.lists(st.booleans(), min_size=1, max_size=5))
    @settings(max_examples=50)
    def run_property_test(outcomes: list[bool]) -> None:
        _run_property_test(outcomes)

    run_property_test()


def test_uow_commits_successful_transactions(sqlite_runtime: Path) -> None:
    """Test: UnitOfWork commits successful transactions and rolls back failures."""
    _run_property_test([True, False, True, False, True])


def test_uow_rejects_nested_usage(sqlite_runtime: Path) -> None:
    """Test: UnitOfWork rejects nested context manager usage."""
    outbox = OutboxStore()
    uow = UnitOfWork(outbox_store=outbox)

    with uow:
        with pytest.raises(RuntimeError):
            with uow:
                pass
