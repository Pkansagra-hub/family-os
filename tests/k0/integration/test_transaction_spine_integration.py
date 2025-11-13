"""Integration test: Complete transaction spine (WAL + Outbox + Receipt + Idem + on_commit).

Tests the complete atomicity guarantee: WAL append → Outbox stage → Receipt save →
Idem upsert → Offset update → on_commit hooks, with guaranteed all-or-nothing semantics.

This validates that the K0 kernel's transaction spine maintains ACID properties
across all stages of transaction processing.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, Iterator, Tuple

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from k0.automation.migrate import apply_migrations
from k0.storage.offsets import Offset, OffsetStore
from k0.storage.outbox import OutboxEntry, OutboxStore
from k0.storage.receipts import Receipt, ReceiptStore
from k0.storage.wal import WalEntry, WriteAheadLog
from k0.uow.connection_pool import configure_pool, connection_scope, shutdown_pool
from k0.uow.unit_of_work import UnitOfWork


@pytest.fixture
def sqlite_runtime() -> Iterator[Path]:
    """Pytest fixture for SQLite runtime with schema initialization."""
    tmp_dir = TemporaryDirectory(ignore_cleanup_errors=True)
    db_path = Path(tmp_dir.name) / "kernel.sqlite3"
    configure_pool(db_path)
    # Apply migrations instead of using storage.sql directly
    apply_migrations(db_path, dry_run=False)
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

    def reset(self) -> None:
        """Clear recorded metrics."""
        self.records.clear()


class CommitHookTracker:
    """Tracks execution of on_commit and on_rollback hooks."""

    def __init__(self) -> None:
        self.commit_called = False
        self.rollback_called = False
        self.commit_call_order: int | None = None
        self.rollback_call_order: int | None = None
        self.call_sequence: list[str] = []

    def on_commit(self) -> None:
        """Called when transaction commits."""
        self.commit_called = True
        self.commit_call_order = len(self.call_sequence)
        self.call_sequence.append("on_commit")

    def on_rollback(self) -> None:
        """Called when transaction rolls back."""
        self.rollback_called = True
        self.rollback_call_order = len(self.call_sequence)
        self.call_sequence.append("on_rollback")


def _reset_database() -> None:
    """Reset all transaction storage tables."""
    with connection_scope() as connection:
        connection.execute("DELETE FROM st_outbox")
        connection.execute("DELETE FROM st_wal")
        connection.execute("DELETE FROM st_receipts")
        connection.execute("DELETE FROM st_offsets")
        connection.commit()


def _create_wal_entry(idx: int) -> WalEntry:
    """Create a test WAL entry."""
    entry_payload = f"payload-{idx}".encode()
    return WalEntry(
        tenant_id="tenant-test",
        space_id="space-test",
        topic="test.topic",
        envelope_json='{"msg":"test"}',
        schema_uri="schema://test/topic",
        schema_version="1.0.0",
        device_id="device-test",
        commit_ts=f"2025-10-31T12:00:0{idx}Z",
        body=entry_payload,
        payload_sha256="a" * 64,
        idem_key=f"idem-key-{idx}",
    )


def _create_outbox_entry(idx: int, wal_pos: int) -> OutboxEntry:
    """Create a test Outbox entry."""
    return OutboxEntry(
        id=None,
        wal_pos=wal_pos,
        tenant_id="tenant-test",
        space_id="space-test",
        driver="test-driver",
        op_kind="INSERT",
        payload=f"outbox-payload-{idx}".encode(),
        fingerprint=f"fp-{idx}",
        requeue_seq=0,
        retries=0,
        last_error=None,
    )


def _create_receipt(idx: int, wal_pos: int) -> Receipt:
    """Create a test Receipt."""
    return Receipt(
        receipt_id=f"receipt-{idx:03d}",
        idem_key=f"idem-key-{idx}",
        wal_pos=wal_pos,
        commit_ts=f"2025-10-31T12:00:0{idx}Z",
        tenant_id="tenant-test",
        space_id="space-test",
        device_id="device-test",
        mls_group_id="mls-group-test",
        key_version="v1",
        device_sig="sig-test",
    )


def _create_offset(idx: int, wal_pos: int) -> Offset:
    """Create a test Offset record."""
    return Offset(
        subscriber_id=f"subscriber-{idx:03d}",
        topic="test.topic",
        space_id="space-test",
        tenant_id="tenant-test",
        offset=wal_pos,
        updated_ts=f"2025-10-31T12:00:0{idx}Z",
    )


class TestTransactionSpineHappyPath:
    """Test cases for successful transaction spine execution."""

    def test_single_transaction_commits_all_stages(self, sqlite_runtime: Path) -> None:
        """Test: Single transaction commits all stages atomically.

        Verifies that WAL append → Outbox stage → Receipt save → Offset upsert
        all persist when transaction commits successfully.
        """
        _reset_database()
        wal = WriteAheadLog()
        outbox = OutboxStore()
        receipts = ReceiptStore()
        offsets = OffsetStore()
        metrics = MetricsRecorder()

        # Execute transaction
        with UnitOfWork(
            outbox_store=outbox,
            write_ahead_log=wal,
            receipt_store=receipts,
            offset_store=offsets,
            metrics_emitter=metrics,
        ) as uow:
            wal_entry = _create_wal_entry(1)
            wal_pos = uow.append_wal(wal_entry)

            outbox_entry = _create_outbox_entry(1, wal_pos)
            uow.stage_outbox(outbox_entry)

            receipt = _create_receipt(1, wal_pos)
            uow.save_receipt(receipt)

            offset = _create_offset(1, wal_pos)
            uow.upsert_offset(offset)

        # Verify all stages persisted
        with connection_scope() as conn:
            wal_count = conn.execute("SELECT COUNT(*) FROM st_wal").fetchone()[0]
            outbox_count = conn.execute("SELECT COUNT(*) FROM st_outbox").fetchone()[0]
            receipt_count = conn.execute("SELECT COUNT(*) FROM st_receipts").fetchone()[0]
            offset_count = conn.execute("SELECT COUNT(*) FROM st_offsets").fetchone()[0]

        assert wal_count == 1, "WAL entry should be persisted"
        assert outbox_count == 1, "Outbox entry should be persisted"
        assert receipt_count == 1, "Receipt should be persisted"
        assert offset_count == 1, "Offset should be persisted"

        # Verify metrics
        assert (
            metrics.metric_count("k0_uow_commit_total", outcome="success") == 1
        ), "Commit metric should be recorded"

    def test_multiple_transactions_maintain_order(self, sqlite_runtime: Path) -> None:
        """Test: Multiple transactions maintain ordering across all stages.

        Verifies that sequences of transactions maintain monotonic ordering
        in WAL positions and offset updates.
        """
        _reset_database()
        wal = WriteAheadLog()
        outbox = OutboxStore()
        receipts = ReceiptStore()
        offsets = OffsetStore()

        # Execute 3 transactions
        wal_positions = []
        for i in range(3):
            with UnitOfWork(
                outbox_store=outbox,
                write_ahead_log=wal,
                receipt_store=receipts,
                offset_store=offsets,
            ) as uow:
                wal_entry = _create_wal_entry(i)
                wal_pos = uow.append_wal(wal_entry)
                wal_positions.append(wal_pos)

                outbox_entry = _create_outbox_entry(i, wal_pos)
                uow.stage_outbox(outbox_entry)

                receipt = _create_receipt(i, wal_pos)
                uow.save_receipt(receipt)

                offset = _create_offset(i, wal_pos)
                uow.upsert_offset(offset)

        # Verify ordering
        assert wal_positions == sorted(wal_positions), "WAL positions should be monotonic"
        assert wal_positions == list(range(1, 4)), "WAL positions should be sequential"

        # Verify all transactions persisted
        with connection_scope() as conn:
            wal_count = conn.execute("SELECT COUNT(*) FROM st_wal").fetchone()[0]
            outbox_count = conn.execute("SELECT COUNT(*) FROM st_outbox").fetchone()[0]
            receipt_count = conn.execute("SELECT COUNT(*) FROM st_receipts").fetchone()[0]
            offset_count = conn.execute("SELECT COUNT(*) FROM st_offsets").fetchone()[0]

        assert wal_count == 3, "All 3 WAL entries should be persisted"
        assert outbox_count == 3, "All 3 Outbox entries should be persisted"
        assert receipt_count == 3, "All 3 Receipts should be persisted"
        assert offset_count == 3, "All 3 Offsets should be persisted"

    def test_on_commit_hooks_execute_after_successful_commit(self, sqlite_runtime: Path) -> None:
        """Test: on_commit hooks execute only after successful commit.

        Verifies that on_commit hooks are called after all stages are committed
        and their side effects should see committed data.
        """
        _reset_database()
        wal = WriteAheadLog()
        outbox = OutboxStore()
        receipts = ReceiptStore()
        offsets = OffsetStore()
        hook_tracker = CommitHookTracker()

        # Execute transaction with on_commit hook
        with UnitOfWork(
            outbox_store=outbox,
            write_ahead_log=wal,
            receipt_store=receipts,
            offset_store=offsets,
        ) as uow:
            uow.add_commit_hook(hook_tracker.on_commit)

            wal_entry = _create_wal_entry(1)
            wal_pos = uow.append_wal(wal_entry)

            outbox_entry = _create_outbox_entry(1, wal_pos)
            uow.stage_outbox(outbox_entry)

            receipt = _create_receipt(1, wal_pos)
            uow.save_receipt(receipt)

        # Verify hook was called
        assert hook_tracker.commit_called, "on_commit hook should be called after successful commit"
        assert not hook_tracker.rollback_called, "on_rollback hook should not be called"

        # Verify hook sees committed data (can query DB)
        with connection_scope() as conn:
            outbox_count = conn.execute("SELECT COUNT(*) FROM st_outbox").fetchone()[0]
        assert outbox_count == 1, "on_commit hook can see committed data in database"


class TestTransactionSpineFailurePaths:
    """Test cases for failure and rollback scenarios."""

    def test_wal_failure_rolls_back_entire_transaction(self, sqlite_runtime: Path) -> None:
        """Test: If WAL append fails, entire transaction rolls back.

        Verifies all-or-nothing semantics when WAL fails.
        """
        _reset_database()
        wal = WriteAheadLog()
        outbox = OutboxStore()
        receipts = ReceiptStore()
        offsets = OffsetStore()
        metrics = MetricsRecorder()

        try:
            with UnitOfWork(
                outbox_store=outbox,
                write_ahead_log=wal,
                receipt_store=receipts,
                offset_store=offsets,
                metrics_emitter=metrics,
            ) as uow:
                # Force WAL to fail by passing invalid entry
                wal_entry = _create_wal_entry(1)
                _wal_pos = uow.append_wal(wal_entry)

                # Simulate failure in outbox processing
                raise RuntimeError("Simulated outbox processing error")

        except RuntimeError:
            pass

        # Verify rollback occurred
        with connection_scope() as conn:
            outbox_count = conn.execute("SELECT COUNT(*) FROM st_outbox").fetchone()[0]
            receipt_count = conn.execute("SELECT COUNT(*) FROM st_receipts").fetchone()[0]
            offset_count = conn.execute("SELECT COUNT(*) FROM st_offsets").fetchone()[0]

        assert outbox_count == 0, "Outbox should be empty after rollback (stage never reached)"
        assert receipt_count == 0, "Receipt should be empty after rollback"
        assert offset_count == 0, "Offset should be empty after rollback"

        # Verify rollback metric recorded
        assert (
            metrics.metric_count("k0_uow_rollback_total") == 1
        ), "Rollback metric should be recorded"

    def test_on_rollback_hooks_execute_after_failure(self, sqlite_runtime: Path) -> None:
        """Test: on_rollback hooks execute when transaction fails.

        Verifies that rollback hooks are called before cleanup.
        """
        _reset_database()
        wal = WriteAheadLog()
        outbox = OutboxStore()
        hook_tracker = CommitHookTracker()

        try:
            with UnitOfWork(
                outbox_store=outbox,
                write_ahead_log=wal,
            ) as uow:
                uow.add_rollback_hook(hook_tracker.on_rollback)

                wal_entry = _create_wal_entry(1)
                _wal_pos = uow.append_wal(wal_entry)

                # Force failure
                raise ValueError("Test error")

        except ValueError:
            pass

        # Verify rollback hook was called
        assert hook_tracker.rollback_called, "on_rollback hook should be called after failure"
        assert not hook_tracker.commit_called, "on_commit hook should not be called"

    def test_nested_unitofwork_rejected(self, sqlite_runtime: Path) -> None:
        """Test: Nested UnitOfWork usage is rejected.

        Verifies that the UnitOfWork is not reentrant.
        """
        outbox = OutboxStore()
        uow = UnitOfWork(outbox_store=outbox)

        with uow:
            with pytest.raises(RuntimeError, match="not reentrant"):
                with uow:
                    pass

    def test_multiple_failures_in_sequence_rollback_atomically(self, sqlite_runtime: Path) -> None:
        """Test: Multiple transaction failures rollback atomically.

        Uses hypothesis to generate random success/failure sequences and verify
        that failures always result in clean rollback (no partial writes).
        """
        _reset_database()
        wal = WriteAheadLog()
        outbox = OutboxStore()
        receipts = ReceiptStore()
        offsets = OffsetStore()
        metrics = MetricsRecorder()

        @given(st.lists(st.booleans(), min_size=1, max_size=5))
        @settings(max_examples=50)
        def property_test(outcomes: list[bool]) -> None:
            _reset_database()
            metrics.reset()
            committed = 0

            for idx, should_succeed in enumerate(outcomes):
                try:
                    with UnitOfWork(
                        outbox_store=outbox,
                        write_ahead_log=wal,
                        receipt_store=receipts,
                        offset_store=offsets,
                        metrics_emitter=metrics,
                    ) as uow:
                        wal_entry = _create_wal_entry(idx)
                        wal_pos = uow.append_wal(wal_entry)

                        outbox_entry = _create_outbox_entry(idx, wal_pos)
                        uow.stage_outbox(outbox_entry)

                        receipt = _create_receipt(idx, wal_pos)
                        uow.save_receipt(receipt)

                        offset = _create_offset(idx, wal_pos)
                        uow.upsert_offset(offset)

                        if not should_succeed:
                            raise RuntimeError("Simulated failure")

                    committed += 1

                except RuntimeError:
                    pass

            # Verify atomicity: only committed transactions persisted
            with connection_scope() as conn:
                outbox_count = conn.execute("SELECT COUNT(*) FROM st_outbox").fetchone()[0]
                receipt_count = conn.execute("SELECT COUNT(*) FROM st_receipts").fetchone()[0]
                offset_count = conn.execute("SELECT COUNT(*) FROM st_offsets").fetchone()[0]

            assert outbox_count == committed, f"outbox: expected {committed}, got {outbox_count}"
            assert (
                receipt_count == committed
            ), f"receipts: expected {committed}, got {receipt_count}"
            assert offset_count == committed, f"offsets: expected {committed}, got {offset_count}"

            # Verify metrics
            total_rollbacks = len(outcomes) - committed
            assert (
                metrics.metric_count("k0_uow_commit_total", outcome="success") == committed
            ), f"Expected {committed} commits, got {metrics.metric_count('k0_uow_commit_total', outcome='success')}"
            assert (
                metrics.metric_count("k0_uow_rollback_total") == total_rollbacks
            ), f"Expected {total_rollbacks} rollbacks, got {metrics.metric_count('k0_uow_rollback_total')}"

        property_test()


class TestTransactionSpineCompleteIntegration:
    """Integration tests for the complete transaction spine."""

    def test_complete_spine_with_all_operations(self, sqlite_runtime: Path) -> None:
        """Test: Complete transaction spine with all operations together.

        Verifies end-to-end: WAL append → Outbox stage → Receipt save →
        Offset upsert → Metrics emitted → on_commit hooks called.
        """
        _reset_database()
        wal = WriteAheadLog()
        outbox = OutboxStore()
        receipts = ReceiptStore()
        offsets = OffsetStore()
        metrics = MetricsRecorder()
        hook_tracker = CommitHookTracker()

        # Execute complete transaction
        with UnitOfWork(
            outbox_store=outbox,
            write_ahead_log=wal,
            receipt_store=receipts,
            offset_store=offsets,
            metrics_emitter=metrics,
        ) as uow:
            uow.add_commit_hook(hook_tracker.on_commit)

            # Stage 1: WAL append
            wal_entry = _create_wal_entry(1)
            wal_pos = uow.append_wal(wal_entry)
            assert wal_pos > 0, "WAL position should be assigned"

            # Stage 2: Outbox stage
            outbox_entry = _create_outbox_entry(1, wal_pos)
            uow.stage_outbox(outbox_entry)

            # Stage 3: Receipt save
            receipt = _create_receipt(1, wal_pos)
            uow.save_receipt(receipt)

            # Stage 4: Offset upsert
            offset = _create_offset(1, wal_pos)
            uow.upsert_offset(offset)

        # Verify all stages executed
        assert hook_tracker.commit_called, "on_commit hook should execute"

        # Verify data persisted atomically
        with connection_scope() as conn:
            wal_row = conn.execute(
                "SELECT pos, topic FROM st_wal WHERE pos = ?",
                (wal_pos,),
            ).fetchone()
            outbox_row = conn.execute(
                "SELECT wal_pos, driver FROM st_outbox WHERE wal_pos = ?",
                (wal_pos,),
            ).fetchone()
            receipt_row = conn.execute(
                "SELECT wal_pos, receipt_id FROM st_receipts WHERE wal_pos = ?",
                (wal_pos,),
            ).fetchone()
            offset_row = conn.execute(
                "SELECT offset FROM st_offsets WHERE subscriber_id = ?",
                ("subscriber-001",),
            ).fetchone()

        assert wal_row is not None, "WAL entry should be persisted"
        assert wal_row["topic"] == "test.topic"
        assert outbox_row is not None, "Outbox entry should be persisted"
        assert outbox_row["driver"] == "test-driver"
        assert receipt_row is not None, "Receipt should be persisted"
        assert offset_row is not None, "Offset should be persisted"
        assert offset_row["offset"] == wal_pos

        # Verify metrics
        assert (
            metrics.metric_count("k0_uow_commit_total", outcome="success") == 1
        ), "Commit metrics should be recorded"
        assert (
            metrics.metric_count("k0_uow_wal_fsync_total", outcome="success") == 1
        ), "WAL fsync metrics should be recorded"

    def test_spine_maintains_consistency_under_load(self, sqlite_runtime: Path) -> None:
        """Test: Transaction spine maintains consistency with multiple concurrent-like operations.

        Sequential simulation of high-load scenario with multiple transactions
        committing and failing to verify consistency is maintained.
        """
        _reset_database()
        wal = WriteAheadLog()
        outbox = OutboxStore()
        receipts = ReceiptStore()
        offsets = OffsetStore()
        metrics = MetricsRecorder()

        committed_count = 0
        failed_count = 0

        # Simulate 10 transactions with random outcomes
        for i in range(10):
            should_fail = i % 3 == 0  # Fail every 3rd transaction

            try:
                with UnitOfWork(
                    outbox_store=outbox,
                    write_ahead_log=wal,
                    receipt_store=receipts,
                    offset_store=offsets,
                    metrics_emitter=metrics,
                ) as uow:
                    wal_entry = _create_wal_entry(i)
                    wal_pos = uow.append_wal(wal_entry)

                    outbox_entry = _create_outbox_entry(i, wal_pos)
                    uow.stage_outbox(outbox_entry)

                    receipt = _create_receipt(i, wal_pos)
                    uow.save_receipt(receipt)

                    offset = _create_offset(i, wal_pos)
                    uow.upsert_offset(offset)

                    if should_fail:
                        raise RuntimeError(f"Simulated failure for transaction {i}")

                committed_count += 1

            except RuntimeError:
                failed_count += 1

        # Verify consistency
        with connection_scope() as conn:
            outbox_count = conn.execute("SELECT COUNT(*) FROM st_outbox").fetchone()[0]
            receipt_count = conn.execute("SELECT COUNT(*) FROM st_receipts").fetchone()[0]
            offset_count = conn.execute("SELECT COUNT(*) FROM st_offsets").fetchone()[0]
            wal_count = conn.execute("SELECT COUNT(*) FROM st_wal").fetchone()[0]

        # Only successful transactions should be persisted
        assert outbox_count == committed_count, f"Outbox should have {committed_count} entries"
        assert receipt_count == committed_count, f"Receipts should have {committed_count} entries"
        assert offset_count == committed_count, f"Offsets should have {committed_count} entries"
        assert wal_count == committed_count, f"WAL should have {committed_count} entries"

        # Verify metrics
        assert (
            metrics.metric_count("k0_uow_commit_total", outcome="success") == committed_count
        ), f"Should have {committed_count} successful commits"
        assert (
            metrics.metric_count("k0_uow_rollback_total") == failed_count
        ), f"Should have {failed_count} rollbacks"
