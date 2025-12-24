"""Unit tests for async PostgreSQL OutboxStore.

Part of K0 PostgreSQL Migration (Milestone 3.1.1 - Issue 3.1.1.2)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from k0.storage.outbox import OutboxEntry, OutboxStore


class TestOutboxEntry:
    """Tests for OutboxEntry dataclass."""

    def test_outbox_entry_creation(self) -> None:
        """OutboxEntry can be created with required fields."""
        entry = OutboxEntry(
            id=None,
            wal_pos=1,
            tenant_id="tenant1",
            space_id="space1",
            driver="hippocampus",
            op_kind="PROCESS",
            payload=b"test_payload",
            fingerprint="abc123",
            requeue_seq=0,
            retries=0,
        )
        assert entry.id is None
        assert entry.status == "PENDING"

    def test_outbox_entry_with_backoff(self) -> None:
        """OutboxEntry can be created with backoff fields."""
        entry = OutboxEntry(
            id=1,
            wal_pos=1,
            tenant_id="tenant1",
            space_id="space1",
            driver="hippocampus",
            op_kind="PROCESS",
            payload=b"test_payload",
            fingerprint="abc123",
            requeue_seq=1,
            retries=3,
            next_attempt_ts="2024-01-01T00:00:00Z",
            backoff_exp=2,
            status="PENDING",
        )
        assert entry.backoff_exp == 2
        assert entry.retries == 3


class TestOutboxStore:
    """Tests for OutboxStore async class."""

    @pytest.fixture
    def store(self) -> OutboxStore:
        """Create an OutboxStore instance."""
        return OutboxStore()

    @pytest.fixture
    def mock_connection(self) -> AsyncMock:
        """Create a mock asyncpg connection."""
        conn = AsyncMock()
        conn.fetchval = AsyncMock()
        conn.fetch = AsyncMock()
        conn.fetchrow = AsyncMock()
        conn.execute = AsyncMock()
        return conn

    @pytest.fixture
    def sample_entry(self) -> OutboxEntry:
        """Create a sample OutboxEntry for testing."""
        return OutboxEntry(
            id=None,
            wal_pos=1,
            tenant_id="tenant1",
            space_id="space1",
            driver="hippocampus",
            op_kind="PROCESS",
            payload=b"test_payload",
            fingerprint="abc123",
            requeue_seq=0,
            retries=0,
        )

    @pytest.mark.asyncio
    async def test_enqueue_returns_id(
        self, store: OutboxStore, mock_connection: AsyncMock, sample_entry: OutboxEntry
    ) -> None:
        """enqueue() returns the assigned entry ID."""
        mock_connection.fetchval.side_effect = [42, 1]  # ID, then count for metrics

        with patch("k0.storage.outbox._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__.return_value = mock_connection
            mock_resolve.return_value.__aexit__.return_value = None

            entry_id = await store.enqueue(sample_entry, connection=mock_connection)

        assert entry_id == 42
        assert sample_entry.id == 42

    @pytest.mark.asyncio
    async def test_enqueue_raises_on_none_id(
        self, store: OutboxStore, mock_connection: AsyncMock, sample_entry: OutboxEntry
    ) -> None:
        """enqueue() raises RuntimeError if ID is None."""
        mock_connection.fetchval.return_value = None

        with patch("k0.storage.outbox._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__.return_value = mock_connection
            mock_resolve.return_value.__aexit__.return_value = None

            with pytest.raises(RuntimeError, match="Failed to determine outbox entry id"):
                await store.enqueue(sample_entry, connection=mock_connection)

    @pytest.mark.asyncio
    async def test_enqueue_uses_returning(
        self, store: OutboxStore, mock_connection: AsyncMock, sample_entry: OutboxEntry
    ) -> None:
        """enqueue() uses RETURNING id in INSERT."""
        mock_connection.fetchval.side_effect = [1, 1]

        with patch("k0.storage.outbox._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__.return_value = mock_connection
            mock_resolve.return_value.__aexit__.return_value = None

            await store.enqueue(sample_entry, connection=mock_connection)

        call_args = mock_connection.fetchval.call_args_list[0]
        assert "RETURNING id" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_dequeue_batch_returns_entries(
        self, store: OutboxStore, mock_connection: AsyncMock
    ) -> None:
        """dequeue_batch() returns list of OutboxEntry objects."""
        mock_connection.fetch.return_value = [
            {
                "id": 1,
                "wal_pos": 10,
                "tenant_id": "tenant1",
                "space_id": "space1",
                "driver": "hippocampus",
                "op_kind": "PROCESS",
                "payload": b"test",
                "fingerprint": "abc",
                "requeue_seq": 0,
                "retries": 0,
                "last_error": None,
                "next_attempt_ts": None,
                "backoff_exp": 0,
                "status": "PENDING",
            }
        ]

        with patch("k0.storage.outbox._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__.return_value = mock_connection
            mock_resolve.return_value.__aexit__.return_value = None

            entries = await store.dequeue_batch("hippocampus", connection=mock_connection)

        assert len(entries) == 1
        assert entries[0].id == 1
        assert entries[0].driver == "hippocampus"

    @pytest.mark.asyncio
    async def test_dequeue_ready_batch_filters_by_time(
        self, store: OutboxStore, mock_connection: AsyncMock
    ) -> None:
        """dequeue_ready_batch() filters by next_attempt_ts."""
        mock_connection.fetch.return_value = []

        with patch("k0.storage.outbox._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__.return_value = mock_connection
            mock_resolve.return_value.__aexit__.return_value = None

            await store.dequeue_ready_batch("hippocampus", connection=mock_connection)

        call_args = mock_connection.fetch.call_args
        query = call_args[0][0]
        # Uses parameterized query with $2 for timestamp
        assert "next_attempt_ts IS NULL OR next_attempt_ts <= $2" in query
        assert "status = 'PENDING'" in query

    @pytest.mark.asyncio
    async def test_mark_applied_deletes_entry(
        self, store: OutboxStore, mock_connection: AsyncMock
    ) -> None:
        """mark_applied() deletes the entry from outbox."""
        mock_connection.fetchrow.return_value = {"driver": "hippocampus"}
        mock_connection.fetchval.return_value = 0

        with patch("k0.storage.outbox._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__.return_value = mock_connection
            mock_resolve.return_value.__aexit__.return_value = None

            await store.mark_applied(42, connection=mock_connection)

        # Verify DELETE was called
        mock_connection.execute.assert_called()
        call_args = mock_connection.execute.call_args
        assert "DELETE FROM st_outbox WHERE id = $1" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_record_failure_updates_entry(
        self, store: OutboxStore, mock_connection: AsyncMock
    ) -> None:
        """record_failure() updates retry info on entry."""
        from datetime import datetime, timezone

        entry = OutboxEntry(
            id=42,
            wal_pos=1,
            tenant_id="tenant1",
            space_id="space1",
            driver="hippocampus",
            op_kind="PROCESS",
            payload=b"test",
            fingerprint="abc",
            requeue_seq=0,
            retries=0,
        )

        next_attempt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        with patch("k0.storage.outbox._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__.return_value = mock_connection
            mock_resolve.return_value.__aexit__.return_value = None

            await store.record_failure(
                entry,
                retries=1,
                requeue_seq=1,
                last_error="Test error",
                next_attempt_ts=next_attempt,
                backoff_exp=1,
                connection=mock_connection,
            )

        # Verify UPDATE was called
        mock_connection.execute.assert_called_once()
        # Verify entry was updated
        assert entry.retries == 1
        assert entry.last_error == "Test error"
        assert entry.backoff_exp == 1

    @pytest.mark.asyncio
    async def test_record_failure_raises_without_id(
        self, store: OutboxStore, mock_connection: AsyncMock
    ) -> None:
        """record_failure() raises ValueError if entry has no ID."""
        entry = OutboxEntry(
            id=None,  # No ID
            wal_pos=1,
            tenant_id="tenant1",
            space_id="space1",
            driver="hippocampus",
            op_kind="PROCESS",
            payload=b"test",
            fingerprint="abc",
            requeue_seq=0,
            retries=0,
        )

        with pytest.raises(ValueError, match="must be persisted"):
            await store.record_failure(
                entry,
                retries=1,
                requeue_seq=1,
                last_error="Test error",
                connection=mock_connection,
            )

    @pytest.mark.asyncio
    async def test_metrics_updated_on_enqueue(
        self, mock_connection: AsyncMock, sample_entry: OutboxEntry
    ) -> None:
        """enqueue() updates metrics when attached."""
        metrics = MagicMock()
        store = OutboxStore(metrics=metrics)
        mock_connection.fetchval.side_effect = [1, 5, 3]  # ID, total, driver count

        with patch("k0.storage.outbox._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__.return_value = mock_connection
            mock_resolve.return_value.__aexit__.return_value = None

            await store.enqueue(sample_entry, connection=mock_connection)

        assert metrics.set_gauge.call_count >= 1

    def test_attach_metrics(self, store: OutboxStore) -> None:
        """attach_metrics() sets the metrics exporter."""
        metrics = MagicMock()
        store.attach_metrics(metrics)
        assert store._metrics is metrics

        store.attach_metrics(None)
        assert store._metrics is None
