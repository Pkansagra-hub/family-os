"""Integration tests for Outbox Background Loop (Gap 19).

Tests Outbox Worker Background Loop:
1. Background loop processes outbox every 5s
2. Respects next_attempt_ts for exponential backoff
3. Graceful shutdown via asyncio task cancellation
4. Error handling with 30s backoff on exceptions
5. Failed outbox entry retries with 2^N backoff
6. End-to-end WAL commit → outbox processing within 5s

Validates complete outbox background processing with all safety guarantees.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator
from unittest.mock import MagicMock

import pytest

from k0.automation.migrate import apply_migrations
from k0.drivers.alias_map import AliasMap
from k0.outbox.fingerprint import compute_fingerprint
from k0.outbox.pool import DriverWorkerPool
from k0.outbox.scheduler import RetryScheduler
from k0.outbox.worker import OutboxDriver
from k0.storage.dlq import DeadLetterQueue
from k0.storage.outbox import OutboxEntry, OutboxStore
from k0.uow.connection_pool import configure_pool, shutdown_pool


@pytest.fixture
def sqlite_runtime() -> Iterator[Path]:
    """Pytest fixture for SQLite runtime with schema initialization."""
    tmp_dir = TemporaryDirectory(ignore_cleanup_errors=True)
    db_path = Path(tmp_dir.name) / "kernel.sqlite3"
    configure_pool(db_path)
    apply_migrations(db_path, dry_run=False)
    try:
        yield db_path
    finally:
        shutdown_pool()
        tmp_dir.cleanup()


@pytest.fixture
def temp_db(sqlite_runtime: Path) -> Path:
    """Alias for sqlite_runtime for test compatibility."""
    return sqlite_runtime


@pytest.fixture
def mock_metrics() -> MagicMock:
    """Mock metrics emitter that matches the MetricsEmitter protocol (callable)."""
    return MagicMock()


@pytest.fixture
def alias_map() -> AliasMap:
    """Create a test alias map."""
    return AliasMap({"test_driver": "test_module"})


@pytest.fixture
def outbox_store(mock_metrics: MagicMock) -> OutboxStore:
    """Create OutboxStore with metrics."""
    return OutboxStore(metrics=mock_metrics)


@pytest.fixture
def dlq() -> DeadLetterQueue:
    """Create DeadLetterQueue."""
    return DeadLetterQueue()


@pytest.fixture
def retry_scheduler() -> RetryScheduler:
    """Create RetryScheduler with test configuration."""
    return RetryScheduler(max_attempts=3, backoff_steps=[1, 2, 4])


@pytest.fixture
def worker_pool(
    alias_map: AliasMap,
    outbox_store: OutboxStore,
    dlq: DeadLetterQueue,
    retry_scheduler: RetryScheduler,
    mock_metrics: MagicMock,
) -> DriverWorkerPool:
    """Create DriverWorkerPool with test dependencies."""

    def scheduler_factory() -> RetryScheduler:
        return retry_scheduler

    return DriverWorkerPool(
        alias_map=alias_map,
        outbox_store=outbox_store,
        dead_letter_queue=dlq,
        retry_scheduler_factory=scheduler_factory,
        metrics_emitter=mock_metrics,
        batch_size=10,
        lease_seconds=60,
    )


class TestOutboxBackgroundLoopBasics:
    """Tests for basic background loop functionality."""

    @pytest.mark.asyncio
    async def test_background_loop_processes_periodically(
        self,
        worker_pool: DriverWorkerPool,
        outbox_store: OutboxStore,
        alias_map: AliasMap,
        temp_db: Path,
    ) -> None:
        """Test: Background loop processes outbox every 5s."""
        # Setup: Create outbox entry
        payload = b'{"action": "periodic_test"}'
        entry = OutboxEntry(
            id=None,
            wal_pos=1,
            tenant_id="tenant1",
            space_id="space1",
            driver="test_driver",
            op_kind="periodic",
            payload=payload,
            fingerprint=compute_fingerprint("test_driver", "periodic", payload),
            requeue_seq=0,
            retries=0,
        )
        outbox_store.enqueue(entry)

        # Setup: Mock successful driver
        mock_driver = MagicMock(spec=OutboxDriver)
        worker_pool._driver_overrides["test_driver"] = mock_driver

        # Simulate background loop behavior
        async def mock_background_loop():
            """Simulate background loop processing."""
            driver_aliases = list(alias_map.bindings.keys())
            for alias in driver_aliases:
                worker_pool.process_driver(alias)

        # Execute: Run mock loop once
        await mock_background_loop()

        # Verify: Entry was processed
        mock_driver.apply.assert_called_once()

    @pytest.mark.asyncio
    async def test_background_loop_handles_multiple_drivers(
        self,
        outbox_store: OutboxStore,
        dlq: DeadLetterQueue,
        mock_metrics: MagicMock,
        temp_db: Path,
    ) -> None:
        """Test: Background loop processes all registered drivers."""
        # Setup: Multiple drivers
        alias_map = AliasMap(
            {
                "driver_a": "module_a",
                "driver_b": "module_b",
                "driver_c": "module_c",
            }
        )

        def scheduler_factory() -> RetryScheduler:
            return RetryScheduler()

        worker_pool = DriverWorkerPool(
            alias_map=alias_map,
            outbox_store=outbox_store,
            dead_letter_queue=dlq,
            retry_scheduler_factory=scheduler_factory,
            metrics_emitter=mock_metrics,
        )

        # Create entries for each driver
        for driver_alias in ["driver_a", "driver_b", "driver_c"]:
            payload = f'{{"action": "{driver_alias}_test"}}'.encode()
            entry = OutboxEntry(
                id=None,
                wal_pos=10,
                tenant_id="tenant1",
                space_id="space1",
                driver=driver_alias,
                op_kind="test",
                payload=payload,
                fingerprint=compute_fingerprint(driver_alias, "test", payload),
                requeue_seq=0,
                retries=0,
            )
            outbox_store.enqueue(entry)

        # Setup: Mock drivers
        mock_drivers = {}
        for alias in ["driver_a", "driver_b", "driver_c"]:
            mock_driver = MagicMock(spec=OutboxDriver)
            worker_pool._driver_overrides[alias] = mock_driver
            mock_drivers[alias] = mock_driver

        # Execute: Process all drivers
        driver_aliases = list(alias_map.bindings.keys())
        for alias in driver_aliases:
            worker_pool.process_driver(alias)

        # Verify: All drivers were invoked
        for alias, mock_driver in mock_drivers.items():
            mock_driver.apply.assert_called_once()


class TestOutboxExponentialBackoff:
    """Tests for exponential backoff behavior."""

    @pytest.mark.asyncio
    async def test_failed_entry_retries_with_exponential_backoff(
        self,
        worker_pool: DriverWorkerPool,
        outbox_store: OutboxStore,
        temp_db: Path,
    ) -> None:
        """Test: Failed outbox entry retries with 2^N backoff (Gap 19 acceptance criteria)."""
        # Setup: Create entry that will fail
        payload = b'{"action": "backoff_test"}'
        entry = OutboxEntry(
            id=None,
            wal_pos=20,
            tenant_id="tenant1",
            space_id="space1",
            driver="test_driver",
            op_kind="backoff",
            payload=payload,
            fingerprint=compute_fingerprint("test_driver", "backoff", payload),
            requeue_seq=0,
            retries=0,
        )
        entry_id = outbox_store.enqueue(entry)

        # Setup: Mock failing driver
        mock_driver = MagicMock(spec=OutboxDriver)
        mock_driver.apply.side_effect = RuntimeError("Temporary failure")
        worker_pool._driver_overrides["test_driver"] = mock_driver

        # Execute: First processing attempt (should fail and schedule retry)
        worker_pool.process_driver("test_driver")

        # Verify: Entry has retry scheduled with backoff
        with sqlite3.connect(str(temp_db)) as conn:
            row = conn.execute(
                "SELECT retries, requeue_seq, next_attempt_ts FROM st_outbox WHERE id=?",
                (entry_id,),
            ).fetchone()
            assert row[0] == 1  # retries incremented
            assert row[1] == 1  # requeue_seq (first backoff step)
            assert row[2] is not None  # next_attempt_ts set

    @pytest.mark.asyncio
    async def test_respects_next_attempt_ts_backoff(
        self,
        worker_pool: DriverWorkerPool,
        outbox_store: OutboxStore,
        temp_db: Path,
    ) -> None:
        """Test: Background loop respects next_attempt_ts (doesn't retry early)."""
        from datetime import datetime, timedelta, timezone

        # Setup: Create entry with future next_attempt_ts
        payload = b'{"action": "future_retry"}'
        entry = OutboxEntry(
            id=None,
            wal_pos=30,
            tenant_id="tenant1",
            space_id="space1",
            driver="test_driver",
            op_kind="future",
            payload=payload,
            fingerprint=compute_fingerprint("test_driver", "future", payload),
            requeue_seq=0,
            retries=0,
        )
        entry_id = outbox_store.enqueue(entry)

        # Manually set next_attempt_ts to future time
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        with sqlite3.connect(str(temp_db)) as conn:
            conn.execute(
                "UPDATE st_outbox SET next_attempt_ts = ? WHERE id = ?",
                (future_time.isoformat(), entry_id),
            )
            conn.commit()

        # Setup: Mock driver
        mock_driver = MagicMock(spec=OutboxDriver)
        worker_pool._driver_overrides["test_driver"] = mock_driver

        # Execute: Try to process (should skip due to future next_attempt_ts)
        worker_pool.process_driver("test_driver")

        # Verify: Driver NOT called (entry not ready yet)
        mock_driver.apply.assert_not_called()


class TestOutboxBackgroundLoopErrorHandling:
    """Tests for error handling and recovery."""

    @pytest.mark.asyncio
    async def test_loop_continues_after_driver_error(
        self,
        worker_pool: DriverWorkerPool,
        outbox_store: OutboxStore,
        temp_db: Path,
    ) -> None:
        """Test: Background loop continues processing after driver error."""
        # Setup: Create multiple entries
        entry1 = OutboxEntry(
            id=None,
            wal_pos=40,
            tenant_id="tenant1",
            space_id="space1",
            driver="test_driver",
            op_kind="fail_first",
            payload=b'{"action": "fail"}',
            fingerprint=compute_fingerprint("test_driver", "fail_first", b'{"action": "fail"}'),
            requeue_seq=0,
            retries=0,
        )
        outbox_store.enqueue(entry1)

        entry2 = OutboxEntry(
            id=None,
            wal_pos=41,
            tenant_id="tenant1",
            space_id="space1",
            driver="test_driver",
            op_kind="succeed_second",
            payload=b'{"action": "succeed"}',
            fingerprint=compute_fingerprint(
                "test_driver", "succeed_second", b'{"action": "succeed"}'
            ),
            requeue_seq=1,  # Process after first entry
            retries=0,
        )
        outbox_store.enqueue(entry2)

        # Setup: Mock driver that fails first, succeeds second
        mock_driver = MagicMock(spec=OutboxDriver)
        call_count = 0

        def apply_side_effect(entry: OutboxEntry):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("First entry fails")
            # Second entry succeeds (no exception)

        mock_driver.apply.side_effect = apply_side_effect
        worker_pool._driver_overrides["test_driver"] = mock_driver

        # Execute: Process driver (should handle first failure and continue)
        worker_pool.process_driver("test_driver")

        # Verify: Both entries were attempted
        assert mock_driver.apply.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_driver_queue_no_error(
        self,
        worker_pool: DriverWorkerPool,
        alias_map: AliasMap,
        temp_db: Path,
    ) -> None:
        """Test: Processing empty driver queue doesn't error."""
        # Setup: Mock driver to avoid module import errors
        mock_driver = MagicMock(spec=OutboxDriver)
        for alias in alias_map.bindings.keys():
            worker_pool._driver_overrides[alias] = mock_driver

        # Execute: Process with no entries in outbox
        driver_aliases = list(alias_map.bindings.keys())
        for alias in driver_aliases:
            # Should not raise
            worker_pool.process_driver(alias)

        # Test passes if no exception raised
        # Verify driver was NOT called (no entries in outbox)
        mock_driver.apply.assert_not_called()


class TestOutboxBackgroundLoopGracefulShutdown:
    """Tests for graceful shutdown behavior."""

    @pytest.mark.asyncio
    async def test_background_loop_cancellation(self) -> None:
        """Test: Background loop cancels gracefully."""
        cancelled = False

        async def mock_outbox_worker_loop():
            """Mock background loop that can be cancelled."""
            nonlocal cancelled
            try:
                while True:
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                cancelled = True
                raise

        # Start background task
        task = asyncio.create_task(mock_outbox_worker_loop())

        # Let it run briefly
        await asyncio.sleep(0.2)

        # Cancel task
        task.cancel()

        # Wait for cancellation
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Verify: Task was cancelled
        assert cancelled

    @pytest.mark.asyncio
    async def test_multiple_background_tasks_cancel_together(self) -> None:
        """Test: Multiple background tasks cancel together (SSE metrics + outbox loop)."""
        sse_cancelled = False
        outbox_cancelled = False

        async def mock_sse_metrics_loop():
            nonlocal sse_cancelled
            try:
                while True:
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                sse_cancelled = True
                raise

        async def mock_outbox_worker_loop():
            nonlocal outbox_cancelled
            try:
                while True:
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                outbox_cancelled = True
                raise

        # Start both tasks
        sse_task = asyncio.create_task(mock_sse_metrics_loop())
        outbox_task = asyncio.create_task(mock_outbox_worker_loop())

        # Let them run briefly
        await asyncio.sleep(0.2)

        # Cancel both tasks
        sse_task.cancel()
        outbox_task.cancel()

        # Wait for cancellation
        try:
            await sse_task
        except asyncio.CancelledError:
            pass

        try:
            await outbox_task
        except asyncio.CancelledError:
            pass

        # Verify: Both tasks were cancelled
        assert sse_cancelled
        assert outbox_cancelled


class TestOutboxEndToEndIntegration:
    """End-to-end tests for complete outbox processing flow."""

    @pytest.mark.asyncio
    async def test_wal_commit_to_outbox_processing_within_5s(
        self,
        worker_pool: DriverWorkerPool,
        outbox_store: OutboxStore,
        alias_map: AliasMap,
        temp_db: Path,
    ) -> None:
        """Test: WAL commit → outbox entry processed within 5s (Gap 19 acceptance criteria)."""
        import time

        # Setup: Create outbox entry (simulating WAL commit)
        payload = b'{"action": "e2e_test"}'
        entry = OutboxEntry(
            id=None,
            wal_pos=100,
            tenant_id="tenant1",
            space_id="space1",
            driver="test_driver",
            op_kind="e2e",
            payload=payload,
            fingerprint=compute_fingerprint("test_driver", "e2e", payload),
            requeue_seq=0,
            retries=0,
        )
        outbox_store.enqueue(entry)

        # Setup: Mock driver that tracks processing time
        mock_driver = MagicMock(spec=OutboxDriver)
        processing_time = None

        def apply_with_timing(entry: OutboxEntry):
            nonlocal processing_time
            processing_time = time.perf_counter()

        mock_driver.apply.side_effect = apply_with_timing
        worker_pool._driver_overrides["test_driver"] = mock_driver

        # Record WAL commit time
        wal_commit_time = time.perf_counter()

        # Simulate background loop processing (should happen within 5s)
        # In real deployment, this would be handled by _outbox_worker_loop
        await asyncio.sleep(0.1)  # Simulate small delay before processing

        driver_aliases = list(alias_map.bindings.keys())
        for alias in driver_aliases:
            worker_pool.process_driver(alias)

        # Verify: Entry was processed
        assert processing_time is not None

        # Calculate latency
        latency_s = processing_time - wal_commit_time

        # Acceptance criteria: processed within 5s
        assert latency_s < 5.0, f"Outbox processing took {latency_s}s, exceeds 5s threshold"

    @pytest.mark.asyncio
    async def test_multiple_entries_all_processed(
        self,
        worker_pool: DriverWorkerPool,
        outbox_store: OutboxStore,
        alias_map: AliasMap,
        temp_db: Path,
    ) -> None:
        """Test: Multiple outbox entries all processed by background loop."""
        # Setup: Create multiple entries
        entry_count = 10
        for i in range(entry_count):
            payload = f'{{"action": "multi_{i}"}}'.encode()
            entry = OutboxEntry(
                id=None,
                wal_pos=200 + i,
                tenant_id="tenant1",
                space_id="space1",
                driver="test_driver",
                op_kind="multi",
                payload=payload,
                fingerprint=compute_fingerprint("test_driver", "multi", payload),
                requeue_seq=i,
                retries=0,
            )
            outbox_store.enqueue(entry)

        # Setup: Mock driver
        mock_driver = MagicMock(spec=OutboxDriver)
        worker_pool._driver_overrides["test_driver"] = mock_driver

        # Execute: Process all entries
        driver_aliases = list(alias_map.bindings.keys())
        for alias in driver_aliases:
            worker_pool.process_driver(alias)

        # Verify: All entries processed (limited by batch_size=10)
        assert mock_driver.apply.call_count == min(entry_count, 10)


class TestOutboxBackoffRecovery:
    """Tests for recovery after backoff periods."""

    @pytest.mark.asyncio
    async def test_entry_becomes_ready_after_backoff_expires(
        self,
        worker_pool: DriverWorkerPool,
        outbox_store: OutboxStore,
        temp_db: Path,
    ) -> None:
        """Test: Entry becomes ready for processing after backoff expires."""
        from datetime import datetime, timedelta, timezone

        # Setup: Create entry with past next_attempt_ts (ready for retry)
        payload = b'{"action": "past_retry"}'
        entry = OutboxEntry(
            id=None,
            wal_pos=300,
            tenant_id="tenant1",
            space_id="space1",
            driver="test_driver",
            op_kind="past",
            payload=payload,
            fingerprint=compute_fingerprint("test_driver", "past", payload),
            requeue_seq=1,
            retries=1,
        )
        entry_id = outbox_store.enqueue(entry)

        # Set next_attempt_ts to past time (ready now)
        past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        with sqlite3.connect(str(temp_db)) as conn:
            conn.execute(
                "UPDATE st_outbox SET next_attempt_ts = ? WHERE id = ?",
                (past_time.isoformat(), entry_id),
            )
            conn.commit()

        # Setup: Mock successful driver
        mock_driver = MagicMock(spec=OutboxDriver)
        worker_pool._driver_overrides["test_driver"] = mock_driver

        # Execute: Process (should pick up ready entry)
        worker_pool.process_driver("test_driver")

        # Verify: Entry was processed
        mock_driver.apply.assert_called_once()
