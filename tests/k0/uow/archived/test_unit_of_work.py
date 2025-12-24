"""Tests for k0/uow/unit_of_work.py and k0/uow/connection_pool.py"""

import asyncio
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from k0.obs.metrics import MetricsExporter
from k0.storage.offsets import Offset, OffsetStore
from k0.storage.outbox import OutboxEntry, OutboxStore
from k0.storage.receipts import Receipt, ReceiptStore
from k0.storage.wal import WalEntry, WriteAheadLog
from k0.uow.connection_pool import (
    SQLiteConnectionPool,
    configure_pool,
    connection_scope,
    get_pool,
    shutdown_pool,
)
from k0.uow.unit_of_work import UnitOfWork


@pytest.fixture
def temp_db_path():
    """Create a temporary database path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    yield path
    path.unlink(missing_ok=True)


@pytest.fixture
def metrics_exporter():
    """Mock metrics exporter."""
    return MagicMock(spec=MetricsExporter)


class TestSQLiteConnectionPool:
    """Test SQLiteConnectionPool class."""

    def test_init_valid_params(self, temp_db_path, metrics_exporter):
        """Test pool initialization with valid parameters."""
        pool = SQLiteConnectionPool(
            database_path=temp_db_path,
            max_size=5,
            pragmas={"journal_mode": "WAL"},
            busy_timeout_ms=10000,
            metrics_exporter=metrics_exporter,
        )
        assert pool._max_size == 5
        assert pool._busy_timeout_ms == 10000
        assert pool._metrics_exporter == metrics_exporter

    def test_init_invalid_max_size(self, temp_db_path):
        """Test pool initialization with invalid max_size."""
        with pytest.raises(ValueError, match="max_size must be greater than zero"):
            SQLiteConnectionPool(database_path=temp_db_path, max_size=0)

    def test_acquire_release_basic(self, temp_db_path):
        """Test basic acquire/release cycle."""
        pool = SQLiteConnectionPool(database_path=temp_db_path, max_size=2)

        conn1 = pool.acquire()
        assert isinstance(conn1, sqlite3.Connection)

        conn2 = pool.acquire()
        assert isinstance(conn2, sqlite3.Connection)
        assert conn1 is not conn2

        pool.release(conn1)
        pool.release(conn2)

        stats = pool.stats()
        assert stats.available == 2
        assert stats.in_use == 0

        pool.close()

    def test_acquire_timeout(self, temp_db_path):
        """Test acquire timeout when pool is exhausted."""
        pool = SQLiteConnectionPool(database_path=temp_db_path, max_size=1)

        # Exhaust the pool
        conn = pool.acquire()
        assert conn is not None

        # This should timeout
        with pytest.raises(TimeoutError):
            pool.acquire(timeout=0.1)

        pool.release(conn)
        pool.close()

    def test_connection_pragmas_applied(self, temp_db_path):
        """Test that pragmas are applied to connections."""
        pragmas = {
            "journal_mode": "WAL",
            "synchronous": "NORMAL",
            "foreign_keys": 1,
        }
        pool = SQLiteConnectionPool(database_path=temp_db_path, pragmas=pragmas)

        conn = pool.acquire()
        cursor = conn.cursor()

        # Check pragmas were applied
        cursor.execute("PRAGMA journal_mode")
        assert cursor.fetchone()[0].upper() == "WAL"

        cursor.execute("PRAGMA synchronous")
        assert cursor.fetchone()[0] == 1  # NORMAL = 1

        cursor.execute("PRAGMA foreign_keys")
        assert cursor.fetchone()[0] == 1

        cursor.close()
        pool.release(conn)
        pool.close()

    def test_close_pool(self, temp_db_path):
        """Test pool close functionality."""
        pool = SQLiteConnectionPool(database_path=temp_db_path, max_size=2)

        conn1 = pool.acquire()
        conn2 = pool.acquire()

        pool.close()

        # Should not be able to acquire after close
        with pytest.raises(RuntimeError, match="Connection pool has been closed"):
            pool.acquire()

        # Release should work but not add back to pool
        pool.release(conn1)
        pool.release(conn2)

        stats = pool.stats()
        assert stats.available == 0  # Connections not returned to pool

    def test_connection_reuse(self, temp_db_path):
        """Test that connections are reused."""
        pool = SQLiteConnectionPool(database_path=temp_db_path, max_size=1)

        conn1 = pool.acquire()
        pool.release(conn1)

        conn2 = pool.acquire()
        # Should be the same connection object
        assert conn1 is conn2

        pool.release(conn2)
        pool.close()

    def test_metrics_emission(self, temp_db_path, metrics_exporter):
        """Test that pool metrics are emitted."""
        pool = SQLiteConnectionPool(
            database_path=temp_db_path,
            max_size=2,
            metrics_exporter=metrics_exporter,
        )

        conn = pool.acquire()
        pool.release(conn)

        # Should have emitted metrics
        metrics_exporter.set_gauge.assert_called()
        metrics_exporter.observe.assert_called()

        pool.close()


class TestGlobalPoolFunctions:
    """Test global pool management functions."""

    def test_configure_shutdown_pool(self, temp_db_path, metrics_exporter):
        """Test global pool configuration and shutdown."""
        configure_pool(
            database_path=temp_db_path,
            max_size=3,
            metrics_exporter=metrics_exporter,
        )

        pool = get_pool()
        assert isinstance(pool, SQLiteConnectionPool)
        assert pool._max_size == 3

        shutdown_pool()

        # Should raise after shutdown
        with pytest.raises(RuntimeError, match="Connection pool has not been configured"):
            get_pool()

    def test_connection_scope_context_manager(self, temp_db_path):
        """Test connection_scope context manager."""
        configure_pool(database_path=temp_db_path, max_size=1)

        try:
            with connection_scope() as conn:
                assert isinstance(conn, sqlite3.Connection)
                # Should be able to execute queries
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                assert result[0] == 1
                cursor.close()
        finally:
            shutdown_pool()


class TestUnitOfWork:
    """Test UnitOfWork class."""

    @pytest.fixture
    def mock_stores(self):
        """Mock storage components."""
        return {
            "outbox_store": MagicMock(spec=OutboxStore),
            "wal": MagicMock(spec=WriteAheadLog),
            "receipt_store": MagicMock(spec=ReceiptStore),
            "offset_store": MagicMock(spec=OffsetStore),
        }

    @pytest.fixture
    def mock_metrics(self):
        """Mock metrics components."""
        return {
            "metrics_emitter": MagicMock(),
            "metrics_exporter": MagicMock(spec=MetricsExporter),
        }

    def test_init_default_values(self):
        """Test UnitOfWork initialization with defaults."""
        uow = UnitOfWork()
        assert uow.outbox_store is None
        assert uow.write_ahead_log is None
        assert uow.receipt_store is None
        assert uow.offset_store is None
        assert uow.metrics_emitter is None
        assert uow.metrics_exporter is None
        assert uow.wal_fsync_mode == "strict"
        assert uow.on_commit == []
        assert uow.on_rollback == []

    @pytest.mark.asyncio
    async def test_async_context_manager_success(self, temp_db_path, mock_stores, mock_metrics):
        """Test successful async context manager usage."""
        configure_pool(database_path=temp_db_path)

        try:
            uow = UnitOfWork(
                outbox_store=mock_stores["outbox_store"],
                write_ahead_log=mock_stores["wal"],
                metrics_emitter=mock_metrics["metrics_emitter"],
                metrics_exporter=mock_metrics["metrics_exporter"],
            )

            async with uow:
                assert uow._entered is True
                assert uow._connection is not None

                # Should be able to access connection
                conn = uow.connection
                assert isinstance(conn, sqlite3.Connection)

                # Test pragma settings
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode")
                assert cursor.fetchone()[0].upper() == "WAL"
                cursor.close()

            # Should emit success metrics
            mock_metrics["metrics_emitter"].assert_called()
            mock_metrics["metrics_exporter"].observe.assert_called()

        finally:
            shutdown_pool()

    @pytest.mark.asyncio
    async def test_async_context_manager_rollback(self, temp_db_path, mock_metrics):
        """Test rollback on exception."""
        configure_pool(database_path=temp_db_path)

        try:
            uow = UnitOfWork(metrics_emitter=mock_metrics["metrics_emitter"])

            with pytest.raises(ValueError, match="Test error"):
                async with uow:
                    raise ValueError("Test error")

            # Should emit rollback metrics
            mock_metrics["metrics_emitter"].assert_called()

        finally:
            shutdown_pool()

    def test_sync_context_manager_deprecated(self, temp_db_path):
        """Test sync context manager shows deprecation warning."""
        configure_pool(database_path=temp_db_path)

        try:
            uow = UnitOfWork()

            with pytest.raises(RuntimeError, match="Synchronous exit not supported"):
                with uow:
                    pass  # This should work for enter but fail on exit

        finally:
            shutdown_pool()

    @pytest.mark.asyncio
    async def test_current_uow_context_var(self, temp_db_path):
        """Test current UoW context variable."""
        configure_pool(database_path=temp_db_path)

        try:
            # Outside context, should be None
            assert UnitOfWork.current() is None

            uow = UnitOfWork()
            async with uow:
                assert UnitOfWork.current() is uow
            # After exit, should be None again
            assert UnitOfWork.current() is None

        finally:
            shutdown_pool()

    @pytest.mark.asyncio
    async def test_stage_outbox(self, temp_db_path, mock_stores):
        """Test outbox staging."""
        configure_pool(database_path=temp_db_path)

        try:
            uow = UnitOfWork(outbox_store=mock_stores["outbox_store"])

            entry = OutboxEntry(
                id=None,
                wal_pos=1,
                tenant_id="tenant1",
                space_id="space1",
                driver="test_driver",
                op_kind="test_op",
                payload=b"test data",
                fingerprint="test_fingerprint",
                requeue_seq=0,
                retries=0,
            )

            async with uow:
                # Should work inside active UoW
                uow.stage_outbox(entry)
                assert len(uow._staged_outbox) == 1

            # Should have flushed outbox
            mock_stores["outbox_store"].enqueue_async.assert_called_once()

        finally:
            shutdown_pool()

    @pytest.mark.asyncio
    async def test_append_wal(self, temp_db_path, mock_stores):
        """Test WAL append."""
        configure_pool(database_path=temp_db_path)

        try:
            uow = UnitOfWork(write_ahead_log=mock_stores["wal"])

            entry = WalEntry(
                tenant_id="tenant1",
                space_id="space1",
                topic="test.topic",
                envelope_json='{"test": "data"}',
                schema_uri="test://schema",
                schema_version="1.0",
                device_id="device123",
                commit_ts="2023-01-01T00:00:00Z",
                body=b"test data",
            )

            mock_stores["wal"].append.return_value = 42

            async with uow:
                position = await uow.append_wal(entry)
                assert position == 42
                assert position in uow._wal_positions

            # Should have called fsync
            mock_stores["wal"].fsync.assert_called()

        finally:
            shutdown_pool()

    @pytest.mark.asyncio
    async def test_save_receipt(self, temp_db_path, mock_stores):
        """Test receipt saving."""
        configure_pool(database_path=temp_db_path)

        try:
            uow = UnitOfWork(receipt_store=mock_stores["receipt_store"])

            receipt = Receipt(
                receipt_id="test-receipt",
                idem_key="test-key",
                wal_pos=100,
                commit_ts="2023-01-01T00:00:00Z",
                tenant_id="tenant1",
                space_id="space1",
                device_id="device123",
                mls_group_id="group123",
                key_version="v1",
                device_sig="signature",
            )

            async with uow:
                await uow.save_receipt(receipt)

            mock_stores["receipt_store"].save_async.assert_called_once()
            # Check that it was called with the receipt and a connection
            call_args = mock_stores["receipt_store"].save_async.call_args
            assert call_args[0][0] == receipt
            assert call_args[1]["connection"] is not None

        finally:
            shutdown_pool()

    @pytest.mark.asyncio
    async def test_upsert_offset(self, temp_db_path, mock_stores):
        """Test offset upsert."""
        configure_pool(database_path=temp_db_path)

        try:
            uow = UnitOfWork(offset_store=mock_stores["offset_store"])

            offset = Offset(
                subscriber_id="sub1",
                topic="test.topic",
                space_id="space1",
                tenant_id="tenant1",
                offset=100,
                updated_ts="2023-01-01T00:00:00Z",
            )

            async with uow:
                await uow.upsert_offset(offset)

            mock_stores["offset_store"].upsert.assert_called_once()
            # Check that it was called with the offset and a connection
            call_args = mock_stores["offset_store"].upsert.call_args
            assert call_args[0][0] == offset
            assert call_args[1]["connection"] is not None

        finally:
            shutdown_pool()

    def test_commit_hooks(self, temp_db_path):
        """Test commit hooks."""
        configure_pool(database_path=temp_db_path)

        try:
            uow = UnitOfWork()

            hook_called = False

            def test_hook():
                nonlocal hook_called
                hook_called = True

            uow.add_commit_hook(test_hook)

            async def test_commit():
                async with uow:
                    pass  # Successful commit
                assert hook_called

            asyncio.run(test_commit())

        finally:
            shutdown_pool()

    def test_rollback_hooks(self, temp_db_path):
        """Test rollback hooks."""
        configure_pool(database_path=temp_db_path)

        try:
            uow = UnitOfWork()

            hook_called = False

            def test_hook():
                nonlocal hook_called
                hook_called = True

            uow.add_rollback_hook(test_hook)

            async def test_rollback():
                with pytest.raises(ValueError):
                    async with uow:
                        raise ValueError("Test rollback")
                assert hook_called

            asyncio.run(test_rollback())

        finally:
            shutdown_pool()

    @pytest.mark.asyncio
    async def test_wal_fsync_modes(self, temp_db_path, mock_stores):
        """Test different WAL fsync modes."""
        configure_pool(database_path=temp_db_path)

        try:
            # Test disabled mode
            uow_disabled = UnitOfWork(
                write_ahead_log=mock_stores["wal"],
                wal_fsync_mode="disabled",
            )

            async with uow_disabled:
                await uow_disabled.append_wal(
                    WalEntry(
                        tenant_id="t",
                        space_id="s",
                        topic="test",
                        envelope_json='{"test": "data"}',
                        schema_uri="test://schema",
                        schema_version="1.0",
                        device_id="device123",
                        commit_ts="2023-01-01T00:00:00Z",
                        body=b"test",
                    )
                )

            # Should not call fsync
            mock_stores["wal"].fsync.assert_not_called()

            # Test strict mode (default)
            uow_strict = UnitOfWork(
                write_ahead_log=mock_stores["wal"],
                wal_fsync_mode="strict",
            )

            async with uow_strict:
                await uow_strict.append_wal(
                    WalEntry(
                        tenant_id="t",
                        space_id="s",
                        topic="test",
                        envelope_json='{"test": "data"}',
                        schema_uri="test://schema",
                        schema_version="1.0",
                        device_id="device123",
                        commit_ts="2023-01-01T00:00:00Z",
                        body=b"test",
                    )
                )

            # Should call fsync
            mock_stores["wal"].fsync.assert_called()

        finally:
            shutdown_pool()

    def test_connection_access_outside_context(self):
        """Test connection access outside active context."""
        uow = UnitOfWork()

        with pytest.raises(RuntimeError, match="UnitOfWork is not active"):
            _ = uow.connection
