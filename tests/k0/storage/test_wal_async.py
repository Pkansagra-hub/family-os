"""Unit tests for async PostgreSQL WriteAheadLog.

Part of K0 PostgreSQL Migration (Milestone 3.1.1 - Issue 3.1.1.1)
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from k0.storage.wal import WalBacklogStats, WalEntry, WriteAheadLog


class TestWalEntry:
    """Tests for WalEntry dataclass."""

    def test_wal_entry_creation(self) -> None:
        """WalEntry can be created with required fields."""
        entry = WalEntry(
            tenant_id="tenant1",
            space_id="space1",
            topic="events.test",
            envelope_json='{"test": true}',
            schema_uri="urn:k0:schema:test",
            schema_version="1.0",
            device_id="device1",
            commit_ts=datetime.now(timezone.utc).isoformat(),
        )
        assert entry.tenant_id == "tenant1"
        assert entry.position is None

    def test_wal_entry_with_optional_fields(self) -> None:
        """WalEntry can be created with optional fields."""
        entry = WalEntry(
            tenant_id="tenant1",
            space_id="space1",
            topic="events.test",
            envelope_json='{"test": true}',
            schema_uri="urn:k0:schema:test",
            schema_version="1.0",
            device_id="device1",
            commit_ts=datetime.now(timezone.utc).isoformat(),
            body=b"binary_data",
            payload_sha256="abc123",
            idem_key="unique-key",
            envelope_sha256="def456",
            policy_stamp_json='{"policy": true}',
            location_geohash="u4pruyd",
            location_precision_m=100,
        )
        assert entry.body == b"binary_data"
        assert entry.location_geohash == "u4pruyd"


class TestWalBacklogStats:
    """Tests for WalBacklogStats dataclass."""

    def test_backlog_stats_creation(self) -> None:
        """WalBacklogStats can be created."""
        stats = WalBacklogStats(
            pending_events=10,
            latest_position=100,
            latest_commit_ts="2024-01-01T00:00:00Z",
        )
        assert stats.pending_events == 10
        assert stats.latest_position == 100


class TestWriteAheadLog:
    """Tests for WriteAheadLog async class."""

    @pytest.fixture
    def wal(self) -> WriteAheadLog:
        """Create a WriteAheadLog instance."""
        return WriteAheadLog()

    @pytest.fixture
    def mock_connection(self) -> AsyncMock:
        """Create a mock asyncpg connection."""
        conn = AsyncMock()
        conn.fetchval = AsyncMock()
        conn.fetch = AsyncMock()
        conn.fetchrow = AsyncMock()
        return conn

    @pytest.fixture
    def sample_entry(self) -> WalEntry:
        """Create a sample WalEntry for testing."""
        return WalEntry(
            tenant_id="tenant1",
            space_id="space1",
            topic="events.test",
            envelope_json='{"test": true}',
            schema_uri="urn:k0:schema:test",
            schema_version="1.0",
            device_id="device1",
            commit_ts=datetime.now(timezone.utc).isoformat(),
        )

    @pytest.mark.asyncio
    async def test_append_returns_position(
        self, wal: WriteAheadLog, mock_connection: AsyncMock, sample_entry: WalEntry
    ) -> None:
        """append() returns the assigned WAL position."""
        mock_connection.fetchval.return_value = 42

        with patch("k0.storage.wal._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__.return_value = mock_connection
            mock_resolve.return_value.__aexit__.return_value = None

            position = await wal.append(sample_entry, connection=mock_connection)

        assert position == 42
        mock_connection.fetchval.assert_called_once()
        # Verify RETURNING pos is in the query
        call_args = mock_connection.fetchval.call_args
        assert "RETURNING pos" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_append_raises_on_none_position(
        self, wal: WriteAheadLog, mock_connection: AsyncMock, sample_entry: WalEntry
    ) -> None:
        """append() raises RuntimeError if position is None."""
        mock_connection.fetchval.return_value = None

        with patch("k0.storage.wal._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__.return_value = mock_connection
            mock_resolve.return_value.__aexit__.return_value = None

            with pytest.raises(RuntimeError, match="Failed to determine WAL position"):
                await wal.append(sample_entry, connection=mock_connection)

    @pytest.mark.asyncio
    async def test_append_emits_metrics(
        self, mock_connection: AsyncMock, sample_entry: WalEntry
    ) -> None:
        """append() emits metrics when exporter is attached."""
        metrics = MagicMock()
        wal = WriteAheadLog(metrics=metrics)
        mock_connection.fetchval.return_value = 100

        with patch("k0.storage.wal._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__.return_value = mock_connection
            mock_resolve.return_value.__aexit__.return_value = None

            await wal.append(sample_entry, connection=mock_connection)

        metrics.set_gauge.assert_called_once_with("wal_current_position", 100.0)

    @pytest.mark.asyncio
    async def test_read_from_returns_entries(
        self, wal: WriteAheadLog, mock_connection: AsyncMock
    ) -> None:
        """read_from() returns list of WalEntry objects."""
        mock_connection.fetch.return_value = [
            {
                "pos": 1,
                "tenant_id": "tenant1",
                "space_id": "space1",
                "topic": "events.test",
                "envelope_json": '{"test": true}',
                "body": None,
                "payload_sha256": None,
                "redacted_body_json": None,
                "schema_uri": "urn:k0:schema:test",
                "schema_version": "1.0",
                "idem_key": None,
                "device_id": "device1",
                "commit_ts": "2024-01-01T00:00:00Z",
                "envelope_sha256": None,
                "ingested_at": None,
                "clock_skew_ms": None,
                "policy_stamp_json": None,
                "location_geohash": None,
                "location_precision_m": None,
            }
        ]

        with patch("k0.storage.wal._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__.return_value = mock_connection
            mock_resolve.return_value.__aexit__.return_value = None

            entries = await wal.read_from(0, 10, connection=mock_connection)

        assert len(entries) == 1
        assert entries[0].position == 1
        assert entries[0].tenant_id == "tenant1"

    @pytest.mark.asyncio
    async def test_read_from_with_limit(
        self, wal: WriteAheadLog, mock_connection: AsyncMock
    ) -> None:
        """read_from() uses position and limit parameters."""
        mock_connection.fetch.return_value = []

        with patch("k0.storage.wal._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__.return_value = mock_connection
            mock_resolve.return_value.__aexit__.return_value = None

            await wal.read_from(50, 25, connection=mock_connection)

        call_args = mock_connection.fetch.call_args
        # Position and limit should be passed as parameters
        assert call_args[0][1] == 50  # position
        assert call_args[0][2] == 25  # limit

    @pytest.mark.asyncio
    async def test_backlog_stats_returns_stats(
        self, wal: WriteAheadLog, mock_connection: AsyncMock
    ) -> None:
        """backlog_stats() returns WalBacklogStats."""
        mock_connection.fetchrow.return_value = {
            "pending": 5,
            "latest_pos": 100,
            "latest_ts": "2024-01-01T00:00:00Z",
        }

        with patch("k0.storage.wal._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__.return_value = mock_connection
            mock_resolve.return_value.__aexit__.return_value = None

            stats = await wal.backlog_stats(
                tenant_id="tenant1",
                space_id="space1",
                topic="events.test",
                offset=50,
                connection=mock_connection,
            )

        assert stats.pending_events == 5
        assert stats.latest_position == 100
        assert stats.latest_commit_ts == "2024-01-01T00:00:00Z"

    @pytest.mark.asyncio
    async def test_backlog_stats_handles_empty(
        self, wal: WriteAheadLog, mock_connection: AsyncMock
    ) -> None:
        """backlog_stats() handles empty results."""
        mock_connection.fetchrow.return_value = {
            "pending": None,
            "latest_pos": None,
            "latest_ts": None,
        }

        with patch("k0.storage.wal._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__.return_value = mock_connection
            mock_resolve.return_value.__aexit__.return_value = None

            stats = await wal.backlog_stats(
                tenant_id="tenant1",
                space_id="space1",
                topic="events.test",
                offset=0,
                connection=mock_connection,
            )

        assert stats.pending_events == 0
        assert stats.latest_position is None

    @pytest.mark.asyncio
    async def test_fsync_returns_lsn(self, wal: WriteAheadLog, mock_connection: AsyncMock) -> None:
        """fsync() returns WAL LSN for PostgreSQL."""
        mock_connection.fetchval.side_effect = ["0/15D3C8", 1234567]

        with patch("k0.storage.wal._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__.return_value = mock_connection
            mock_resolve.return_value.__aexit__.return_value = None

            lsn = await wal.fsync(connection=mock_connection)

        assert lsn == 1234567
