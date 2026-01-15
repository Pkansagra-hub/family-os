"""Tests for k0.uow.unit_of_work - Unit of Work abstraction for ACID transactions."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.storage.outbox import OutboxEntry
from k0.uow.unit_of_work import UnitOfWork


class TestUnitOfWorkInitialization:
    """Tests for UnitOfWork initialization."""

    def test_default_initialization(self) -> None:
        """UnitOfWork should have sensible defaults."""
        uow = UnitOfWork()
        assert uow.outbox_store is None
        assert uow.write_ahead_log is None
        assert uow.receipt_store is None
        assert uow.offset_store is None
        assert uow.metrics_emitter is None
        assert uow.on_commit == []
        assert uow.on_rollback == []
        assert uow.wal_fsync_mode == "strict"

    def test_initialization_with_stores(self) -> None:
        """UnitOfWork should accept stores."""
        outbox = MagicMock()
        wal = MagicMock()
        receipt = MagicMock()
        offset = MagicMock()

        uow = UnitOfWork(
            outbox_store=outbox,
            write_ahead_log=wal,
            receipt_store=receipt,
            offset_store=offset,
        )

        assert uow.outbox_store is outbox
        assert uow.write_ahead_log is wal
        assert uow.receipt_store is receipt
        assert uow.offset_store is offset

    def test_wal_fsync_modes(self) -> None:
        """UnitOfWork should accept different fsync modes."""
        for mode in ["strict", "wal_only", "disabled"]:
            uow = UnitOfWork(wal_fsync_mode=mode)  # type: ignore
            assert uow.wal_fsync_mode == mode


class TestUnitOfWorkContextManager:
    """Tests for UnitOfWork async context manager behavior."""

    @pytest.fixture
    def mock_connection(self) -> MagicMock:
        """Create a mock asyncpg connection."""
        conn = MagicMock()
        tx = AsyncMock()
        tx.start = AsyncMock()
        tx.commit = AsyncMock()
        tx.rollback = AsyncMock()
        conn.transaction.return_value = tx
        return conn

    @pytest.fixture
    def mock_connection_scope(self, mock_connection: MagicMock):
        """Create a mock connection_scope context manager."""

        @asynccontextmanager
        async def _scope():
            yield mock_connection

        return _scope

    @pytest.mark.asyncio
    async def test_aenter_sets_connection(
        self, mock_connection_scope, mock_connection: MagicMock, monkeypatch
    ) -> None:
        """__aenter__ should establish a connection and start transaction."""
        monkeypatch.setattr(
            "k0.uow.unit_of_work.connection_scope",
            mock_connection_scope,
        )

        uow = UnitOfWork()
        async with uow as active_uow:
            assert active_uow._connection is mock_connection
            assert active_uow._entered is True
            mock_connection.transaction.return_value.start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_aenter_sets_context_var(
        self, mock_connection_scope, mock_connection: MagicMock, monkeypatch
    ) -> None:
        """__aenter__ should set the UnitOfWork in context var."""
        monkeypatch.setattr(
            "k0.uow.unit_of_work.connection_scope",
            mock_connection_scope,
        )

        assert UnitOfWork.current() is None
        uow = UnitOfWork()
        async with uow:
            assert UnitOfWork.current() is uow
        assert UnitOfWork.current() is None

    @pytest.mark.asyncio
    async def test_not_reentrant(
        self, mock_connection_scope, mock_connection: MagicMock, monkeypatch
    ) -> None:
        """UnitOfWork instances should not be reentrant."""
        monkeypatch.setattr(
            "k0.uow.unit_of_work.connection_scope",
            mock_connection_scope,
        )

        uow = UnitOfWork()
        async with uow:
            with pytest.raises(RuntimeError, match="not reentrant"):
                async with uow:
                    pass

    @pytest.mark.asyncio
    async def test_successful_context_commits(
        self, mock_connection_scope, mock_connection: MagicMock, monkeypatch
    ) -> None:
        """Successful context exit should commit the transaction."""
        monkeypatch.setattr(
            "k0.uow.unit_of_work.connection_scope",
            mock_connection_scope,
        )

        uow = UnitOfWork()
        async with uow:
            pass

        mock_connection.transaction.return_value.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_context_rolls_back(
        self, mock_connection_scope, mock_connection: MagicMock, monkeypatch
    ) -> None:
        """Exception during context should rollback the transaction."""
        monkeypatch.setattr(
            "k0.uow.unit_of_work.connection_scope",
            mock_connection_scope,
        )

        uow = UnitOfWork()
        with pytest.raises(ValueError):
            async with uow:
                raise ValueError("Test error")

        mock_connection.transaction.return_value.rollback.assert_awaited_once()


class TestUnitOfWorkHooks:
    """Tests for commit/rollback hooks."""

    @pytest.fixture
    def mock_connection_scope(self):
        """Create a mock connection_scope context manager."""
        conn = MagicMock()
        tx = AsyncMock()
        tx.start = AsyncMock()
        tx.commit = AsyncMock()
        tx.rollback = AsyncMock()
        conn.transaction.return_value = tx

        @asynccontextmanager
        async def _scope():
            yield conn

        return _scope

    @pytest.mark.asyncio
    async def test_commit_hooks_run_on_success(self, mock_connection_scope, monkeypatch) -> None:
        """Commit hooks should run on successful commit."""
        monkeypatch.setattr(
            "k0.uow.unit_of_work.connection_scope",
            mock_connection_scope,
        )

        hook1 = MagicMock()
        hook2 = MagicMock()
        uow = UnitOfWork(on_commit=[hook1, hook2])

        async with uow:
            pass

        hook1.assert_called_once()
        hook2.assert_called_once()

    @pytest.mark.asyncio
    async def test_rollback_hooks_run_on_error(self, mock_connection_scope, monkeypatch) -> None:
        """Rollback hooks should run on error."""
        monkeypatch.setattr(
            "k0.uow.unit_of_work.connection_scope",
            mock_connection_scope,
        )

        hook = MagicMock()
        uow = UnitOfWork(on_rollback=[hook])

        with pytest.raises(ValueError):
            async with uow:
                raise ValueError("Test error")

        hook.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_commit_hook(self, mock_connection_scope, monkeypatch) -> None:
        """add_commit_hook should register a hook."""
        monkeypatch.setattr(
            "k0.uow.unit_of_work.connection_scope",
            mock_connection_scope,
        )

        hook = MagicMock()
        uow = UnitOfWork()

        async with uow:
            uow.add_commit_hook(hook)

        hook.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_rollback_hook(self, mock_connection_scope, monkeypatch) -> None:
        """add_rollback_hook should register a hook."""
        monkeypatch.setattr(
            "k0.uow.unit_of_work.connection_scope",
            mock_connection_scope,
        )

        hook = MagicMock()
        uow = UnitOfWork()

        with pytest.raises(ValueError):
            async with uow:
                uow.add_rollback_hook(hook)
                raise ValueError("Trigger rollback")

        hook.assert_called_once()


class TestStageOutbox:
    """Tests for stage_outbox method."""

    @pytest.fixture
    def mock_connection_scope(self):
        """Create a mock connection_scope context manager."""
        conn = MagicMock()
        tx = AsyncMock()
        tx.start = AsyncMock()
        tx.commit = AsyncMock()
        tx.rollback = AsyncMock()
        conn.transaction.return_value = tx

        @asynccontextmanager
        async def _scope():
            yield conn

        return _scope

    def test_stage_outbox_requires_active_uow(self) -> None:
        """stage_outbox should raise when UoW is not active."""
        uow = UnitOfWork()
        entry = OutboxEntry(
            id=None,
            wal_pos=1,
            tenant_id="tenant_123",
            space_id="space_abc",
            driver="test_driver",
            op_kind="INSERT",
            payload=b'{"key": "value"}',
            fingerprint="abc123",
            requeue_seq=0,
            retries=0,
        )

        with pytest.raises(RuntimeError, match="active UnitOfWork"):
            uow.stage_outbox(entry)

    @pytest.mark.asyncio
    async def test_stage_outbox_accepts_entry(self, mock_connection_scope, monkeypatch) -> None:
        """stage_outbox should accept entries when active."""
        monkeypatch.setattr(
            "k0.uow.unit_of_work.connection_scope",
            mock_connection_scope,
        )

        entry = OutboxEntry(
            id=None,
            wal_pos=1,
            tenant_id="tenant_123",
            space_id="space_abc",
            driver="test_driver",
            op_kind="INSERT",
            payload=b'{"key": "value"}',
            fingerprint="abc123",
            requeue_seq=0,
            retries=0,
        )

        # Provide a mock outbox_store so commit doesn't fail
        mock_outbox = MagicMock()
        mock_outbox.enqueue_async = AsyncMock()

        uow = UnitOfWork(outbox_store=mock_outbox)
        async with uow:
            uow.stage_outbox(entry)
            assert len(uow._staged_outbox) == 1


class TestAppendWal:
    """Tests for append_wal method."""

    @pytest.fixture
    def mock_connection_scope(self):
        """Create a mock connection_scope context manager."""
        conn = MagicMock()
        tx = AsyncMock()
        tx.start = AsyncMock()
        tx.commit = AsyncMock()
        tx.rollback = AsyncMock()
        conn.transaction.return_value = tx

        @asynccontextmanager
        async def _scope():
            yield conn

        return _scope

    def test_append_wal_requires_active_uow(self) -> None:
        """append_wal should raise when UoW is not active."""
        uow = UnitOfWork()
        entry = MagicMock()

        # Using pytest.mark.asyncio doesn't work here, need to run synchronously
        import asyncio

        with pytest.raises(RuntimeError, match="active UnitOfWork"):
            asyncio.get_event_loop().run_until_complete(uow.append_wal(entry))

    @pytest.mark.asyncio
    async def test_append_wal_requires_wal_configured(
        self, mock_connection_scope, monkeypatch
    ) -> None:
        """append_wal should raise when WAL is not configured."""
        monkeypatch.setattr(
            "k0.uow.unit_of_work.connection_scope",
            mock_connection_scope,
        )

        entry = MagicMock()
        uow = UnitOfWork(write_ahead_log=None)

        async with uow:
            with pytest.raises(RuntimeError, match="WriteAheadLog"):
                await uow.append_wal(entry)

    @pytest.mark.asyncio
    async def test_append_wal_returns_position(self, mock_connection_scope, monkeypatch) -> None:
        """append_wal should return position from WAL."""
        monkeypatch.setattr(
            "k0.uow.unit_of_work.connection_scope",
            mock_connection_scope,
        )

        mock_wal = MagicMock()
        mock_wal.append = AsyncMock(return_value=42)
        mock_wal.fsync = AsyncMock()  # Also mock fsync for commit phase

        entry = MagicMock()
        uow = UnitOfWork(write_ahead_log=mock_wal)

        async with uow:
            pos = await uow.append_wal(entry)
            assert pos == 42
            assert 42 in uow._wal_positions


class TestConnectionProperty:
    """Tests for connection property."""

    def test_connection_raises_when_not_active(self) -> None:
        """connection property should raise when UoW is not active."""
        uow = UnitOfWork()

        with pytest.raises(RuntimeError, match="not active"):
            _ = uow.connection

    @pytest.mark.asyncio
    async def test_connection_returns_connection_when_active(self, monkeypatch) -> None:
        """connection property should return connection when active."""
        mock_conn = MagicMock()
        tx = AsyncMock()
        tx.start = AsyncMock()
        tx.commit = AsyncMock()
        mock_conn.transaction.return_value = tx

        @asynccontextmanager
        async def mock_scope():
            yield mock_conn

        monkeypatch.setattr(
            "k0.uow.unit_of_work.connection_scope",
            mock_scope,
        )

        uow = UnitOfWork()
        async with uow:
            assert uow.connection is mock_conn


class TestMetricsEmission:
    """Tests for metrics emission."""

    @pytest.fixture
    def mock_connection_scope(self):
        """Create a mock connection_scope context manager."""
        conn = MagicMock()
        tx = AsyncMock()
        tx.start = AsyncMock()
        tx.commit = AsyncMock()
        tx.rollback = AsyncMock()
        conn.transaction.return_value = tx

        @asynccontextmanager
        async def _scope():
            yield conn

        return _scope

    @pytest.mark.asyncio
    async def test_metrics_emitted_on_success(self, mock_connection_scope, monkeypatch) -> None:
        """Metrics should be emitted on successful commit."""
        monkeypatch.setattr(
            "k0.uow.unit_of_work.connection_scope",
            mock_connection_scope,
        )

        emitter = MagicMock()
        uow = UnitOfWork(metrics_emitter=emitter)

        async with uow:
            pass

        # Check that commit total was emitted
        calls = [c for c in emitter.call_args_list if "uow_commit_total" in str(c)]
        assert len(calls) > 0

    @pytest.mark.asyncio
    async def test_metrics_emitted_on_rollback(self, mock_connection_scope, monkeypatch) -> None:
        """Metrics should be emitted on rollback."""
        monkeypatch.setattr(
            "k0.uow.unit_of_work.connection_scope",
            mock_connection_scope,
        )

        emitter = MagicMock()
        uow = UnitOfWork(metrics_emitter=emitter)

        with pytest.raises(ValueError):
            async with uow:
                raise ValueError("Test error")

        # Check that rollback total was emitted
        calls = [c for c in emitter.call_args_list if "uow_rollback_total" in str(c)]
        assert len(calls) > 0


class TestCurrentClassMethod:
    """Tests for UnitOfWork.current() class method."""

    def test_current_returns_none_when_no_active(self) -> None:
        """current() should return None when no UoW is active."""
        assert UnitOfWork.current() is None

    @pytest.mark.asyncio
    async def test_current_returns_active_uow(self, monkeypatch) -> None:
        """current() should return the active UoW."""
        mock_conn = MagicMock()
        tx = AsyncMock()
        tx.start = AsyncMock()
        tx.commit = AsyncMock()
        mock_conn.transaction.return_value = tx

        @asynccontextmanager
        async def mock_scope():
            yield mock_conn

        monkeypatch.setattr(
            "k0.uow.unit_of_work.connection_scope",
            mock_scope,
        )

        uow = UnitOfWork()
        async with uow:
            assert UnitOfWork.current() is uow


class TestCleanup:
    """Tests for cleanup behavior."""

    @pytest.fixture
    def mock_connection_scope(self):
        """Create a mock connection_scope context manager."""
        conn = MagicMock()
        tx = AsyncMock()
        tx.start = AsyncMock()
        tx.commit = AsyncMock()
        tx.rollback = AsyncMock()
        conn.transaction.return_value = tx

        @asynccontextmanager
        async def _scope():
            yield conn

        return _scope

    @pytest.mark.asyncio
    async def test_cleanup_resets_state(self, mock_connection_scope, monkeypatch) -> None:
        """Cleanup should reset all state flags."""
        monkeypatch.setattr(
            "k0.uow.unit_of_work.connection_scope",
            mock_connection_scope,
        )

        uow = UnitOfWork()
        async with uow:
            assert uow._entered is True
            assert uow._connection is not None

        assert uow._entered is False
        assert uow._connection is None
        assert uow._transaction is None

    @pytest.mark.asyncio
    async def test_staged_outbox_cleared_after_commit(
        self, mock_connection_scope, monkeypatch
    ) -> None:
        """Staged outbox should be cleared after commit."""
        monkeypatch.setattr(
            "k0.uow.unit_of_work.connection_scope",
            mock_connection_scope,
        )

        entry = OutboxEntry(
            id=None,
            wal_pos=1,
            tenant_id="tenant_123",
            space_id="space_abc",
            driver="test_driver",
            op_kind="INSERT",
            payload=b'{"key": "value"}',
            fingerprint="abc123",
            requeue_seq=0,
            retries=0,
        )

        # Provide a mock outbox_store so commit doesn't fail
        mock_outbox = MagicMock()
        mock_outbox.enqueue_async = AsyncMock()

        uow = UnitOfWork(outbox_store=mock_outbox)
        async with uow:
            uow.stage_outbox(entry)
            assert len(uow._staged_outbox) == 1

        assert len(uow._staged_outbox) == 0

    @pytest.mark.asyncio
    async def test_context_var_reset_after_exit(self, mock_connection_scope, monkeypatch) -> None:
        """Context var should be reset after exit."""
        monkeypatch.setattr(
            "k0.uow.unit_of_work.connection_scope",
            mock_connection_scope,
        )

        uow = UnitOfWork()
        assert UnitOfWork.current() is None

        async with uow:
            assert UnitOfWork.current() is uow

        assert UnitOfWork.current() is None
