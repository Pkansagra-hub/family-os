"""Tests for P03 AsyncAuditLogger.

Issue 6.4.15 - AsyncAuditLogger implementation

Tests non-blocking audit logging, batched writes, and K0 metrics integration.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestAsyncAuditLogger:
    """Test non-blocking audit logging."""

    @pytest.fixture
    def metrics_exporter(self) -> MagicMock:
        """Create mock metrics exporter."""
        mock = MagicMock()
        mock_counter = MagicMock()
        mock_counter.labels.return_value.inc = MagicMock()
        mock.counter.return_value = mock_counter
        return mock

    @pytest.fixture
    def db_driver(self) -> MagicMock:
        """Create mock DB driver."""
        driver = MagicMock()
        driver.executemany = AsyncMock()
        return driver

    @pytest.fixture
    def logger(self, db_driver: MagicMock, metrics_exporter: MagicMock):
        """Create async audit logger."""
        from k0.pipelines.p03.learning.async_audit import AsyncAuditLogger

        return AsyncAuditLogger(
            db_driver,
            metrics_exporter,
            write_interval=1,  # Short interval for tests
            max_batch_size=5,
        )

    @pytest.fixture
    def record(self):
        """Create test audit record."""
        from k0.pipelines.p03.learning.async_audit import AuditRecord

        return AuditRecord(
            audit_id="audit1",
            memory_id="mem1",
            cycle_id="cycle1",
            operation="merge",
        )

    def test_log_audit_enqueues(self, logger, record) -> None:
        """Audit records enqueued."""
        result = logger.log_audit(record)

        assert result is True
        assert logger.write_queue.qsize() == 1

    def test_log_audit_multiple(self, logger) -> None:
        """Multiple audit records enqueued."""
        from k0.pipelines.p03.learning.async_audit import AuditRecord

        for i in range(5):
            record = AuditRecord(
                audit_id=f"audit{i}",
                memory_id=f"mem{i}",
                cycle_id="cycle1",
                operation="merge",
            )
            logger.log_audit(record)

        assert logger.write_queue.qsize() == 5

    def test_log_audit_drops_when_full(
        self, db_driver: MagicMock, metrics_exporter: MagicMock
    ) -> None:
        """Audit records dropped when queue full."""
        from k0.pipelines.p03.learning.async_audit import AsyncAuditLogger, AuditRecord

        logger = AsyncAuditLogger(
            db_driver,
            metrics_exporter,
            queue_max_size=2,
        )

        # Fill queue
        for i in range(2):
            record = AuditRecord(
                audit_id=f"audit{i}",
                memory_id=f"mem{i}",
                cycle_id="cycle1",
                operation="merge",
            )
            logger.log_audit(record)

        # Overflow
        overflow_record = AuditRecord(
            audit_id="overflow",
            memory_id="memX",
            cycle_id="cycle1",
            operation="merge",
        )
        result = logger.log_audit(overflow_record)

        assert result is False

    @pytest.mark.asyncio
    async def test_start_creates_task(self, logger) -> None:
        """Start creates background writer task."""
        await logger.start()

        assert logger.is_running is True
        assert logger.writer_task is not None

        await logger.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self, logger) -> None:
        """Stop cancels background writer task."""
        await logger.start()
        await logger.stop()

        assert logger.is_running is False

    @pytest.mark.asyncio
    async def test_flush_writes_batch(
        self, db_driver: MagicMock, metrics_exporter: MagicMock
    ) -> None:
        """Flush writes pending records."""
        from k0.pipelines.p03.learning.async_audit import AsyncAuditLogger, AuditRecord

        logger = AsyncAuditLogger(db_driver, metrics_exporter)

        # Enqueue records
        for i in range(3):
            record = AuditRecord(
                audit_id=f"audit{i}",
                memory_id=f"mem{i}",
                cycle_id="cycle1",
                operation="merge",
            )
            logger.log_audit(record)

        # Flush
        await logger._flush()

        # Verify write called
        db_driver.executemany.assert_called_once()
        assert logger.write_queue.qsize() == 0

    @pytest.mark.asyncio
    async def test_write_batch_respects_max_size(
        self, db_driver: MagicMock, metrics_exporter: MagicMock
    ) -> None:
        """Flush respects max_batch_size."""
        from k0.pipelines.p03.learning.async_audit import AsyncAuditLogger, AuditRecord

        logger = AsyncAuditLogger(
            db_driver,
            metrics_exporter,
            max_batch_size=2,
        )

        # Enqueue more than batch size
        for i in range(5):
            record = AuditRecord(
                audit_id=f"audit{i}",
                memory_id=f"mem{i}",
                cycle_id="cycle1",
                operation="merge",
            )
            logger.log_audit(record)

        # Flush (should only write 2)
        await logger._flush()

        # Verify only batch_size written
        call_args = db_driver.executemany.call_args
        records_written = call_args[0][1]
        assert len(records_written) == 2
        assert logger.write_queue.qsize() == 3

    def test_pending_count(self, logger, record) -> None:
        """pending_count returns queue size."""
        assert logger.pending_count == 0

        logger.log_audit(record)

        assert logger.pending_count == 1

    def test_get_stats(self, logger) -> None:
        """get_stats returns correct values."""
        stats = logger.get_stats()

        assert stats["pending_count"] == 0
        assert stats["is_running"] is False
        assert stats["write_interval"] == 1
        assert stats["max_batch_size"] == 5
        assert stats["pipeline_id"] == "p03_consolidation"


class TestAuditRecord:
    """Test AuditRecord dataclass."""

    def test_record_creation(self) -> None:
        """Record created with required fields."""
        from k0.pipelines.p03.learning.async_audit import AuditRecord

        record = AuditRecord(
            audit_id="audit1",
            memory_id="mem1",
            cycle_id="cycle1",
            operation="merge",
        )

        assert record.audit_id == "audit1"
        assert record.memory_id == "mem1"
        assert record.cycle_id == "cycle1"
        assert record.operation == "merge"

    def test_record_with_states(self) -> None:
        """Record created with before/after states."""
        from k0.pipelines.p03.learning.async_audit import AuditRecord

        record = AuditRecord(
            audit_id="audit1",
            memory_id="mem1",
            cycle_id="cycle1",
            operation="merge",
            before_state={"strength": 0.5},
            after_state={"strength": 0.8},
        )

        assert record.before_state["strength"] == 0.5
        assert record.after_state["strength"] == 0.8

    def test_record_default_timestamp(self) -> None:
        """Record has default timestamp."""
        from k0.pipelines.p03.learning.async_audit import AuditRecord

        record = AuditRecord(
            audit_id="audit1",
            memory_id="mem1",
            cycle_id="cycle1",
            operation="merge",
        )

        assert record.timestamp is not None
        assert isinstance(record.timestamp, datetime)

    def test_record_with_space_id(self) -> None:
        """Record created with space_id."""
        from k0.pipelines.p03.learning.async_audit import AuditRecord

        record = AuditRecord(
            audit_id="audit1",
            memory_id="mem1",
            cycle_id="cycle1",
            operation="merge",
            space_id="sp_test",
        )

        assert record.space_id == "sp_test"


class TestBatchConstants:
    """Test batch configuration constants."""

    def test_write_interval_default(self) -> None:
        """Default write interval is 30 seconds."""
        from k0.pipelines.p03.learning.async_audit import WRITE_INTERVAL_SECONDS

        assert WRITE_INTERVAL_SECONDS == 30

    def test_max_batch_size_default(self) -> None:
        """Default max batch size is 50."""
        from k0.pipelines.p03.learning.async_audit import MAX_BATCH_SIZE

        assert MAX_BATCH_SIZE == 50

    def test_queue_max_size_default(self) -> None:
        """Default queue max size is 500."""
        from k0.pipelines.p03.learning.async_audit import QUEUE_MAX_SIZE

        assert QUEUE_MAX_SIZE == 500


class TestMetricsIntegration:
    """Test K0 metrics integration."""

    def test_counters_registered(self) -> None:
        """Counters registered on init."""
        from k0.pipelines.p03.learning.async_audit import AsyncAuditLogger

        mock_metrics = MagicMock()
        mock_metrics.counter.return_value = MagicMock()
        mock_db = MagicMock()

        AsyncAuditLogger(mock_db, mock_metrics)

        # 3 counters should be registered
        assert mock_metrics.counter.call_count == 3

    def test_counter_names(self) -> None:
        """Counter names match spec."""
        from k0.pipelines.p03.learning.async_audit import AsyncAuditLogger

        mock_metrics = MagicMock()
        mock_metrics.counter.return_value = MagicMock()
        mock_db = MagicMock()

        AsyncAuditLogger(mock_db, mock_metrics)

        counter_names = [call[1]["name"] for call in mock_metrics.counter.call_args_list]
        assert "p03_audit_writes" in counter_names
        assert "p03_audit_drops" in counter_names
        assert "p03_audit_batches" in counter_names
