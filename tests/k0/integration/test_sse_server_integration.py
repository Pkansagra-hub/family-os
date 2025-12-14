"""Integration tests for SSE server subscriptions, acknowledgements, and backpressure."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from k0.obs import ObservabilityEmitter
from k0.qos import QoSContext
from k0.sse.server import SSEServer
from k0.storage.offsets import Offset, OffsetStore
from k0.storage.wal import WalBacklogStats, WalEntry, WriteAheadLog


@pytest.fixture
def mock_observability() -> ObservabilityEmitter:
    """Create a mock observability emitter."""
    mock = MagicMock(spec=ObservabilityEmitter)
    mock.emit_metric = MagicMock()
    return mock


@pytest.fixture
def mock_qos() -> QoSContext:
    """Create a mock QoS context."""
    return MagicMock(spec=QoSContext)


@pytest.fixture
def acl_yaml():  # type: ignore
    """Create a temporary ACL YAML file with test roles."""
    acl_config = {
        "roles": {
            "admin": {"allow": ["*"]},
            "user": {"allow": ["events/*", "notifications"]},
            "guest": {"allow": ["public/*"]},
            "empty": {"allow": []},
        }
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(acl_config, f)
        temp_path = Path(f.name)
    yield temp_path, acl_config
    temp_path.unlink()


@pytest.fixture
def wal_mock() -> WriteAheadLog:
    """Create a mock WriteAheadLog."""
    return MagicMock(spec=WriteAheadLog)


@pytest.fixture
def offset_store_mock() -> OffsetStore:
    """Create a mock OffsetStore."""
    return MagicMock(spec=OffsetStore)


@pytest.fixture
def sse_server(
    wal_mock: WriteAheadLog,
    offset_store_mock: OffsetStore,
    mock_observability: ObservabilityEmitter,
    mock_qos: QoSContext,
    acl_yaml: tuple[Path, dict],
) -> SSEServer:
    """Create SSEServer instance with mocked dependencies."""
    acl_path, _ = acl_yaml
    return SSEServer(
        wal=wal_mock,
        offset_store=offset_store_mock,
        observability=mock_observability,
        acl_path=acl_path,
        qos=mock_qos,
        database_connection=None,
        max_batch=128,
    )


class TestSSESubscribe:
    """Tests for SSEServer.subscribe() method."""

    async def test_subscribe_basic_topics(
        self, sse_server: SSEServer, wal_mock: WriteAheadLog
    ) -> None:
        """Test basic subscription with permitted topics."""
        wal_mock.read_from.return_value = [
            WalEntry(
                tenant_id="tenant1",
                space_id="space1",
                topic="events/created",
                envelope_json='{"type":"event"}',
                schema_uri="http://schema.example.com/event",
                schema_version="1.0",
                device_id="device1",
                commit_ts="2025-01-15T12:00:00Z",
                position=1,
            ),
            WalEntry(
                tenant_id="tenant1",
                space_id="space1",
                topic="events/updated",
                envelope_json='{"type":"event"}',
                schema_uri="http://schema.example.com/event",
                schema_version="1.0",
                device_id="device1",
                commit_ts="2025-01-15T12:00:01Z",
                position=2,
            ),
        ]

        rows, permitted = await sse_server.subscribe(
            tenant_id="tenant1",
            space_id="space1",
            subscriber_id="sub1",
            topics=["events/created", "events/updated"],
            roles=["user"],
            cursor_token=None,
        )

        assert len(rows) == 2
        assert rows[0].topic == "events/created"
        assert rows[1].topic == "events/updated"
        # permitted contains the filtered topic list (topics matching ACL patterns)
        assert "events/created" in permitted
        assert "events/updated" in permitted
        wal_mock.read_from.assert_called_once()

    async def test_subscribe_with_cursor_token(
        self, sse_server: SSEServer, wal_mock: WriteAheadLog
    ) -> None:
        """Test subscription with cursor token resuming from position."""
        cursor = json.dumps(
            {
                "subscriber_id": "sub1",
                "tenant_id": "tenant1",
                "space_id": "space1",
                "topic": "events/created",
                "offset": 5,
                "ts": "2025-01-15T12:00:00+00:00",
                "nonce": "abc123",
            }
        )
        wal_mock.read_from.return_value = [
            WalEntry(
                tenant_id="tenant1",
                space_id="space1",
                topic="events/created",
                envelope_json='{"type":"event"}',
                schema_uri="http://schema.example.com/event",
                schema_version="1.0",
                device_id="device1",
                commit_ts="2025-01-15T12:00:05Z",
                position=6,
            ),
        ]

        rows, _ = await sse_server.subscribe(
            tenant_id="tenant1",
            space_id="space1",
            subscriber_id="sub1",
            topics=["events/created"],
            roles=["user"],
            cursor_token=cursor,
        )

        # Should resume from position 5 (passed to read_from)
        call_args = wal_mock.read_from.call_args
        assert call_args[0][0] == 5  # last_position
        assert len(rows) == 1

    async def test_subscribe_cursor_subscriber_id_mismatch(
        self, sse_server: SSEServer, wal_mock: WriteAheadLog
    ) -> None:
        """Test cursor validation with mismatched subscriber ID."""
        cursor = json.dumps(
            {
                "subscriber_id": "different_sub",
                "offset": 5,
                "ts": "2025-01-15T12:00:00+00:00",
            }
        )
        wal_mock.read_from.return_value = []

        with pytest.raises(Exception) as exc_info:
            await sse_server.subscribe(
                tenant_id="tenant1",
                space_id="space1",
                subscriber_id="sub1",
                topics=["events/created"],
                roles=["user"],
                cursor_token=cursor,
            )
        assert "CURSOR_SUBSCRIBER_MISMATCH" in str(exc_info.value)

    async def test_subscribe_cursor_tenant_id_mismatch(
        self, sse_server: SSEServer, wal_mock: WriteAheadLog
    ) -> None:
        """Test cursor validation with mismatched tenant ID."""
        cursor = json.dumps(
            {
                "tenant_id": "different_tenant",
                "space_id": "space1",
                "offset": 5,
                "ts": "2025-01-15T12:00:00+00:00",
            }
        )
        wal_mock.read_from.return_value = []

        with pytest.raises(Exception) as exc_info:
            await sse_server.subscribe(
                tenant_id="tenant1",
                space_id="space1",
                subscriber_id="sub1",
                topics=["events/created"],
                roles=["user"],
                cursor_token=cursor,
            )
        assert "CURSOR_SCOPE_MISMATCH" in str(exc_info.value)

    async def test_subscribe_cursor_space_id_mismatch(
        self, sse_server: SSEServer, wal_mock: WriteAheadLog
    ) -> None:
        """Test cursor validation with mismatched space ID."""
        cursor = json.dumps(
            {
                "space_id": "different_space",
                "offset": 5,
                "ts": "2025-01-15T12:00:00+00:00",
            }
        )
        wal_mock.read_from.return_value = []

        with pytest.raises(Exception) as exc_info:
            await sse_server.subscribe(
                tenant_id="tenant1",
                space_id="space1",
                subscriber_id="sub1",
                topics=["events/created"],
                roles=["user"],
                cursor_token=cursor,
            )
        assert "CURSOR_SCOPE_MISMATCH" in str(exc_info.value)

    async def test_subscribe_acl_denies_topics(self, sse_server: SSEServer) -> None:
        """Test subscription blocked by ACL (no permitted topics)."""
        with pytest.raises(Exception) as exc_info:
            await sse_server.subscribe(
                tenant_id="tenant1",
                space_id="space1",
                subscriber_id="sub1",
                topics=["admin/secret"],  # admin role not granted to 'user'
                roles=["guest"],  # guest only has "public/*"
                cursor_token=None,
            )
        assert "TOPIC_ACCESS_DENIED" in str(exc_info.value)

    async def test_subscribe_invalid_fanout_limit(self, sse_server: SSEServer) -> None:
        """Test subscription with invalid fanout limit."""
        with pytest.raises(Exception) as exc_info:
            await sse_server.subscribe(
                tenant_id="tenant1",
                space_id="space1",
                subscriber_id="sub1",
                topics=["events/created"],
                roles=["user"],
                cursor_token=None,
                fanout_limit=-1,  # negative is invalid
            )
        assert "INVALID_FANOUT_LIMIT" in str(exc_info.value)

    async def test_subscribe_filters_by_scope(
        self, sse_server: SSEServer, wal_mock: WriteAheadLog
    ) -> None:
        """Test that subscribe filters WAL entries by tenant/space."""
        wal_mock.read_from.return_value = [
            WalEntry(
                tenant_id="tenant1",
                space_id="space1",
                topic="events",
                envelope_json='{"type":"event"}',
                schema_uri="http://schema.example.com/event",
                schema_version="1.0",
                device_id="device1",
                commit_ts="2025-01-15T12:00:00Z",
                position=1,
            ),
            WalEntry(
                tenant_id="tenant2",  # different tenant
                space_id="space1",
                topic="events",
                envelope_json='{"type":"event"}',
                schema_uri="http://schema.example.com/event",
                schema_version="1.0",
                device_id="device1",
                commit_ts="2025-01-15T12:00:01Z",
                position=2,
            ),
            WalEntry(
                tenant_id="tenant1",
                space_id="space2",  # different space
                topic="events",
                envelope_json='{"type":"event"}',
                schema_uri="http://schema.example.com/event",
                schema_version="1.0",
                device_id="device1",
                commit_ts="2025-01-15T12:00:02Z",
                position=3,
            ),
        ]

        rows, _ = await sse_server.subscribe(
            tenant_id="tenant1",
            space_id="space1",
            subscriber_id="sub1",
            topics=["events"],
            roles=["admin"],
            cursor_token=None,
        )

        # Only first entry matches tenant1 + space1
        assert len(rows) == 1
        assert rows[0].position == 1


class TestSSEAcknowledge:
    """Tests for SSEServer.acknowledge() method."""

    async def test_acknowledge_valid_offset(
        self, sse_server: SSEServer, offset_store_mock: OffsetStore
    ) -> None:
        """Test successful acknowledge with valid offset."""
        await sse_server.acknowledge(
            subscriber_id="sub1",
            tenant_id="tenant1",
            space_id="space1",
            topic="events",
            offset=42,
        )

        offset_store_mock.upsert.assert_called_once()
        call_arg = offset_store_mock.upsert.call_args[0][0]
        assert isinstance(call_arg, Offset)
        assert call_arg.subscriber_id == "sub1"
        assert call_arg.topic == "events"
        assert call_arg.offset == 42

    async def test_acknowledge_negative_offset_rejected(self, sse_server: SSEServer) -> None:
        """Test acknowledge rejection with negative offset."""
        with pytest.raises(Exception) as exc_info:
            await sse_server.acknowledge(
                subscriber_id="sub1",
                tenant_id="tenant1",
                space_id="space1",
                topic="events",
                offset=-1,
            )
        assert "NEGATIVE_OFFSET" in str(exc_info.value)

    async def test_acknowledge_with_custom_timestamp(
        self, sse_server: SSEServer, offset_store_mock: OffsetStore
    ) -> None:
        """Test acknowledge with custom timestamp."""
        custom_ts = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        await sse_server.acknowledge(
            subscriber_id="sub1",
            tenant_id="tenant1",
            space_id="space1",
            topic="events",
            offset=42,
            ack_ts=custom_ts,
        )

        call_arg = offset_store_mock.upsert.call_args[0][0]
        assert call_arg.updated_ts == "2025-01-15T12:00:00+00:00"

    async def test_acknowledge_zero_offset(
        self, sse_server: SSEServer, offset_store_mock: OffsetStore
    ) -> None:
        """Test acknowledge with offset of 0 (valid)."""
        await sse_server.acknowledge(
            subscriber_id="sub1",
            tenant_id="tenant1",
            space_id="space1",
            topic="events",
            offset=0,
        )

        offset_store_mock.upsert.assert_called_once()


class TestSSEBackpressure:
    """Tests for SSEServer.evaluate_backpressure() method."""

    async def test_backpressure_normal_level(
        self, sse_server: SSEServer, offset_store_mock: OffsetStore, wal_mock: WriteAheadLog
    ) -> None:
        """Test backpressure evaluation at normal level."""
        offset_store_mock.fetch.return_value = Offset(
            subscriber_id="sub1",
            topic="events",
            space_id="space1",
            tenant_id="tenant1",
            offset=100,
            updated_ts="2025-01-15T12:00:00+00:00",
        )
        wal_mock.backlog_stats.return_value = WalBacklogStats(
            pending_events=100,
            latest_position=150,
            latest_commit_ts="2025-01-15T12:00:01+00:00",
        )

        metrics = await sse_server.evaluate_backpressure(
            subscriber_id="sub1",
            tenant_id="tenant1",
            space_id="space1",
            topics=["events"],
        )

        assert metrics.level == "normal"
        assert metrics.pending_events == 100
        assert metrics.lag_ms >= 0

    async def test_backpressure_warning_level_by_lag(
        self, sse_server: SSEServer, offset_store_mock: OffsetStore, wal_mock: WriteAheadLog
    ) -> None:
        """Test backpressure warning level triggered by high lag."""
        ack_ts = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        latest_ts = ack_ts + timedelta(milliseconds=3000)  # 3000ms lag

        offset_store_mock.fetch.return_value = Offset(
            subscriber_id="sub1",
            topic="events",
            space_id="space1",
            tenant_id="tenant1",
            offset=100,
            updated_ts=ack_ts.isoformat(),
        )
        wal_mock.backlog_stats.return_value = WalBacklogStats(
            pending_events=100,
            latest_position=150,
            latest_commit_ts=latest_ts.isoformat(),
        )

        metrics = await sse_server.evaluate_backpressure(
            subscriber_id="sub1",
            tenant_id="tenant1",
            space_id="space1",
            topics=["events"],
        )

        assert metrics.level == "warning"
        assert metrics.lag_ms >= 2000

    async def test_backpressure_throttle_level_by_pending(
        self, sse_server: SSEServer, offset_store_mock: OffsetStore, wal_mock: WriteAheadLog
    ) -> None:
        """Test backpressure throttle level triggered by high pending events."""
        offset_store_mock.fetch.return_value = Offset(
            subscriber_id="sub1",
            topic="events",
            space_id="space1",
            tenant_id="tenant1",
            offset=100,
            updated_ts="2025-01-15T12:00:00+00:00",
        )
        wal_mock.backlog_stats.return_value = WalBacklogStats(
            pending_events=25000,  # > THROTTLE_PENDING (20_000)
            latest_position=150,
            latest_commit_ts="2025-01-15T12:00:01+00:00",
        )

        metrics = await sse_server.evaluate_backpressure(
            subscriber_id="sub1",
            tenant_id="tenant1",
            space_id="space1",
            topics=["events"],
        )

        assert metrics.level == "throttle"
        assert metrics.pending_events == 25000

    async def test_backpressure_shed_level_by_lag(
        self, sse_server: SSEServer, offset_store_mock: OffsetStore, wal_mock: WriteAheadLog
    ) -> None:
        """Test backpressure shed level triggered by extreme lag."""
        ack_ts = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        latest_ts = ack_ts + timedelta(milliseconds=20000)  # 20000ms lag

        offset_store_mock.fetch.return_value = Offset(
            subscriber_id="sub1",
            topic="events",
            space_id="space1",
            tenant_id="tenant1",
            offset=100,
            updated_ts=ack_ts.isoformat(),
        )
        wal_mock.backlog_stats.return_value = WalBacklogStats(
            pending_events=100,
            latest_position=150,
            latest_commit_ts=latest_ts.isoformat(),
        )

        metrics = await sse_server.evaluate_backpressure(
            subscriber_id="sub1",
            tenant_id="tenant1",
            space_id="space1",
            topics=["events"],
        )

        assert metrics.level == "shed"
        assert metrics.lag_ms >= 15000

    async def test_backpressure_shed_level_by_pending(
        self, sse_server: SSEServer, offset_store_mock: OffsetStore, wal_mock: WriteAheadLog
    ) -> None:
        """Test backpressure shed level triggered by extreme pending events."""
        offset_store_mock.fetch.return_value = Offset(
            subscriber_id="sub1",
            topic="events",
            space_id="space1",
            tenant_id="tenant1",
            offset=100,
            updated_ts="2025-01-15T12:00:00+00:00",
        )
        wal_mock.backlog_stats.return_value = WalBacklogStats(
            pending_events=60000,  # > SHED_PENDING (50_000)
            latest_position=150,
            latest_commit_ts="2025-01-15T12:00:01+00:00",
        )

        metrics = await sse_server.evaluate_backpressure(
            subscriber_id="sub1",
            tenant_id="tenant1",
            space_id="space1",
            topics=["events"],
        )

        assert metrics.level == "shed"
        assert metrics.pending_events == 60000

    async def test_backpressure_multiple_topics(
        self, sse_server: SSEServer, offset_store_mock: OffsetStore, wal_mock: WriteAheadLog
    ) -> None:
        """Test backpressure evaluation across multiple topics."""
        offset_store_mock.fetch.side_effect = [
            Offset(
                subscriber_id="sub1",
                topic="events",
                space_id="space1",
                tenant_id="tenant1",
                offset=100,
                updated_ts="2025-01-15T12:00:00+00:00",
            ),
            Offset(
                subscriber_id="sub1",
                topic="notifications",
                space_id="space1",
                tenant_id="tenant1",
                offset=50,
                updated_ts="2025-01-15T11:59:50+00:00",
            ),
        ]
        wal_mock.backlog_stats.side_effect = [
            WalBacklogStats(
                pending_events=100,
                latest_position=150,
                latest_commit_ts="2025-01-15T12:00:01+00:00",
            ),
            WalBacklogStats(
                pending_events=200,
                latest_position=250,
                latest_commit_ts="2025-01-15T12:00:01+00:00",
            ),
        ]

        metrics = await sse_server.evaluate_backpressure(
            subscriber_id="sub1",
            tenant_id="tenant1",
            space_id="space1",
            topics=["events", "notifications"],
        )

        assert len(metrics.topics) == 2
        assert metrics.pending_events == 300
        assert metrics.ack_offsets["events"] == 100
        assert metrics.ack_offsets["notifications"] == 50

    async def test_backpressure_cursor_generation(
        self, sse_server: SSEServer, offset_store_mock: OffsetStore, wal_mock: WriteAheadLog
    ) -> None:
        """Test that backpressure metrics include cursor tokens for ack'd offsets."""
        offset_store_mock.fetch.return_value = Offset(
            subscriber_id="sub1",
            topic="events",
            space_id="space1",
            tenant_id="tenant1",
            offset=42,
            updated_ts="2025-01-15T12:00:00+00:00",
        )
        wal_mock.backlog_stats.return_value = WalBacklogStats(
            pending_events=10,
            latest_position=50,
            latest_commit_ts="2025-01-15T12:00:01+00:00",
        )

        metrics = await sse_server.evaluate_backpressure(
            subscriber_id="sub1",
            tenant_id="tenant1",
            space_id="space1",
            topics=["events"],
        )

        assert len(metrics.topics) == 1
        assert metrics.topics[0].cursor is not None
        cursor_data = json.loads(metrics.topics[0].cursor)
        assert cursor_data["offset"] == 42
        assert cursor_data["subscriber_id"] == "sub1"
        assert cursor_data["topic"] == "events"


class TestSSECursorHandling:
    """Tests for cursor encoding/decoding operations."""

    def test_build_cursor_basic(self, sse_server: SSEServer) -> None:
        """Test cursor building with valid parameters."""
        cursor = sse_server.build_cursor(
            subscriber_id="sub1",
            tenant_id="tenant1",
            space_id="space1",
            topic="events",
            offset=42,
            commit_ts="2025-01-15T12:00:00+00:00",
        )

        decoded = json.loads(cursor)
        assert decoded["subscriber_id"] == "sub1"
        assert decoded["tenant_id"] == "tenant1"
        assert decoded["space_id"] == "space1"
        assert decoded["topic"] == "events"
        assert decoded["offset"] == 42
        assert "nonce" in decoded

    async def test_decode_cursor_valid_iso8601_with_z(self, sse_server: SSEServer) -> None:
        """Test cursor decoding with ISO8601 Z suffix."""
        cursor = json.dumps(
            {
                "subscriber_id": "sub1",
                "offset": 42,
                "ts": "2025-01-15T12:00:00Z",
            }
        )

        decoded = sse_server._decode_cursor(cursor)
        assert decoded.subscriber_id == "sub1"
        assert decoded.last_position == 42
        assert decoded.last_ts.tzinfo is not None

    async def test_decode_cursor_valid_iso8601_with_offset(self, sse_server: SSEServer) -> None:
        """Test cursor decoding with ISO8601 +HH:MM offset."""
        cursor = json.dumps(
            {
                "offset": 42,
                "ts": "2025-01-15T12:00:00+00:00",
            }
        )

        decoded = sse_server._decode_cursor(cursor)
        assert decoded.last_position == 42

    async def test_decode_cursor_with_pos_fallback(self, sse_server: SSEServer) -> None:
        """Test cursor decoding with 'pos' fallback (backward compat)."""
        cursor = json.dumps(
            {
                "pos": 42,
                "ts": "2025-01-15T12:00:00Z",
            }
        )

        decoded = sse_server._decode_cursor(cursor)
        assert decoded.last_position == 42

    async def test_decode_cursor_missing_offset_and_ts(self, sse_server: SSEServer) -> None:
        """Test cursor decode error with missing offset/ts."""
        cursor = json.dumps({"subscriber_id": "sub1"})

        with pytest.raises(Exception) as exc_info:
            sse_server._decode_cursor(cursor)
        assert "CURSOR_FIELDS_MISSING" in str(exc_info.value)

    async def test_decode_cursor_negative_position(self, sse_server: SSEServer) -> None:
        """Test cursor decode rejection with negative position."""
        cursor = json.dumps(
            {
                "offset": -1,
                "ts": "2025-01-15T12:00:00Z",
            }
        )

        with pytest.raises(Exception) as exc_info:
            sse_server._decode_cursor(cursor)
        assert "CURSOR_NEGATIVE_POSITION" in str(exc_info.value)

    async def test_decode_cursor_invalid_json(self, sse_server: SSEServer) -> None:
        """Test cursor decode error with invalid JSON."""
        with pytest.raises(Exception) as exc_info:
            sse_server._decode_cursor("{invalid json")
        assert "CURSOR_DECODE_ERROR" in str(exc_info.value)

    async def test_decode_cursor_preserves_optional_fields(self, sse_server: SSEServer) -> None:
        """Test that cursor decode preserves optional subscriber context."""
        cursor = json.dumps(
            {
                "offset": 42,
                "ts": "2025-01-15T12:00:00Z",
                "subscriber_id": "sub1",
                "topic": "events",
                "space_id": "space1",
                "tenant_id": "tenant1",
            }
        )

        decoded = sse_server._decode_cursor(cursor)
        assert decoded.subscriber_id == "sub1"
        assert decoded.topic == "events"
        assert decoded.space_id == "space1"
        assert decoded.tenant_id == "tenant1"


class TestSSEACLHandling:
    """Tests for ACL (Access Control List) evaluation."""

    def test_topic_allowed_exact_match(self, sse_server: SSEServer) -> None:
        """Test topic matching with exact patterns."""
        patterns = {"events/created", "notifications"}
        assert sse_server._topic_allowed("events/created", patterns)
        assert sse_server._topic_allowed("notifications", patterns)
        assert not sse_server._topic_allowed("events/updated", patterns)

    def test_topic_allowed_wildcard_match(self, sse_server: SSEServer) -> None:
        """Test topic matching with wildcard patterns."""
        patterns = {"events/*", "notifications"}
        assert sse_server._topic_allowed("events/created", patterns)
        assert sse_server._topic_allowed("events/updated", patterns)
        assert not sse_server._topic_allowed("events", patterns)
        assert not sse_server._topic_allowed("error/critical", patterns)

    def test_topic_allowed_multiple_patterns(self, sse_server: SSEServer) -> None:
        """Test topic matching with multiple patterns."""
        patterns = {"events/*", "admin/*", "public"}
        assert sse_server._topic_allowed("events/any", patterns)
        assert sse_server._topic_allowed("admin/secret", patterns)
        assert sse_server._topic_allowed("public", patterns)
        assert not sse_server._topic_allowed("private", patterns)

    def test_load_acl_admin_all_topics(self, sse_server: SSEServer) -> None:
        """Test ACL loading for admin role (wildcard access)."""
        permitted = sse_server._load_acl(
            ["events", "notifications", "admin/secret"],
            ["admin"],
        )
        assert set(permitted) == {"events", "notifications", "admin/secret"}

    def test_load_acl_user_restricted_topics(self, sse_server: SSEServer) -> None:
        """Test ACL loading for user role (restricted access)."""
        permitted = sse_server._load_acl(
            ["events/created", "events/updated", "admin/secret"],
            ["user"],
        )
        # user role allows "events/*" and "notifications"
        assert "events/created" in permitted
        assert "events/updated" in permitted
        assert "admin/secret" not in permitted

    def test_load_acl_guest_public_only(self, sse_server: SSEServer) -> None:
        """Test ACL loading for guest role (public only)."""
        permitted = sse_server._load_acl(
            ["public/item1", "public/item2", "events"],
            ["guest"],
        )
        # guest role allows "public/*"
        assert "public/item1" in permitted
        assert "public/item2" in permitted
        assert "events" not in permitted

    def test_load_acl_empty_role_access(self, sse_server: SSEServer) -> None:
        """Test ACL loading for role with empty allow list."""
        permitted = sse_server._load_acl(
            ["events", "notifications"],
            ["empty"],
        )
        assert len(permitted) == 0

    def test_load_acl_multiple_roles_union(self, sse_server: SSEServer) -> None:
        """Test ACL loading combines permissions from multiple roles."""
        permitted = sse_server._load_acl(
            ["events/created", "public/item", "notifications"],
            ["guest", "user"],  # guest + user roles
        )
        # union of guest (public/*) + user (events/*, notifications)
        assert "public/item" in permitted
        assert "events/created" in permitted
        assert "notifications" in permitted


class TestSSECompleteIntegration:
    """End-to-end integration tests for SSE workflows."""

    async def test_complete_subscribe_acknowledge_cycle(
        self,
        sse_server: SSEServer,
        wal_mock: WriteAheadLog,
        offset_store_mock: OffsetStore,
    ) -> None:
        """Test complete workflow: subscribe -> get entries -> acknowledge."""
        # Setup: Mock WAL returns entries
        entries = [
            WalEntry(
                tenant_id="tenant1",
                space_id="space1",
                topic="events/created",
                envelope_json='{"event":"created"}',
                schema_uri="http://schema.example.com/event",
                schema_version="1.0",
                device_id="device1",
                commit_ts="2025-01-15T12:00:00Z",
                position=1,
            ),
            WalEntry(
                tenant_id="tenant1",
                space_id="space1",
                topic="events/updated",
                envelope_json='{"event":"updated"}',
                schema_uri="http://schema.example.com/event",
                schema_version="1.0",
                device_id="device1",
                commit_ts="2025-01-15T12:00:01Z",
                position=2,
            ),
        ]
        wal_mock.read_from.return_value = entries

        # Step 1: Subscribe
        rows, permitted = await sse_server.subscribe(
            tenant_id="tenant1",
            space_id="space1",
            subscriber_id="sub1",
            topics=["events/created", "events/updated"],
            roles=["user"],
            cursor_token=None,
        )
        assert len(rows) == 2

        # Step 2: Acknowledge last processed entry
        await sse_server.acknowledge(
            subscriber_id="sub1",
            tenant_id="tenant1",
            space_id="space1",
            topic="events/updated",
            offset=2,
        )
        offset_store_mock.upsert.assert_called_once()

        # Step 3: Next subscription with cursor
        offset_store_mock.fetch.return_value = Offset(
            subscriber_id="sub1",
            topic="events/updated",
            space_id="space1",
            tenant_id="tenant1",
            offset=2,
            updated_ts="2025-01-15T12:00:01Z",
        )
        wal_mock.backlog_stats.return_value = WalBacklogStats(
            pending_events=0,
            latest_position=2,
            latest_commit_ts="2025-01-15T12:00:01Z",
        )

        metrics = await sse_server.evaluate_backpressure(
            subscriber_id="sub1",
            tenant_id="tenant1",
            space_id="space1",
            topics=["events/updated"],
        )
        assert metrics.level == "normal"

    async def test_multiple_subscribers_same_topic(
        self,
        sse_server: SSEServer,
        wal_mock: WriteAheadLog,
        offset_store_mock: OffsetStore,
    ) -> None:
        """Test multiple subscribers tracking independent progress on same topic."""
        wal_entry = WalEntry(
            tenant_id="tenant1",
            space_id="space1",
            topic="events/created",
            envelope_json='{"event":"test"}',
            schema_uri="http://schema.example.com/event",
            schema_version="1.0",
            device_id="device1",
            commit_ts="2025-01-15T12:00:00Z",
            position=1,
        )
        wal_mock.read_from.return_value = [wal_entry]

        # Subscriber 1 subscribes
        rows1, _ = await sse_server.subscribe(
            tenant_id="tenant1",
            space_id="space1",
            subscriber_id="sub1",
            topics=["events/created"],
            roles=["user"],
            cursor_token=None,
        )
        assert len(rows1) == 1

        # Subscriber 1 acknowledges
        await sse_server.acknowledge(
            subscriber_id="sub1",
            tenant_id="tenant1",
            space_id="space1",
            topic="events/created",
            offset=1,
        )

        # Subscriber 2 subscribes (no acks yet)
        rows2, _ = await sse_server.subscribe(
            tenant_id="tenant1",
            space_id="space1",
            subscriber_id="sub2",
            topics=["events/created"],
            roles=["user"],
            cursor_token=None,
        )
        assert len(rows2) == 1  # Gets same entry

        # Verify independent offsets
        offset_store_mock.fetch.side_effect = [
            Offset(
                subscriber_id="sub1",
                topic="events/created",
                space_id="space1",
                tenant_id="tenant1",
                offset=1,
                updated_ts="2025-01-15T12:00:00Z",
            ),
            Offset(
                subscriber_id="sub2",
                topic="events/created",
                space_id="space1",
                tenant_id="tenant1",
                offset=0,
                updated_ts="2025-01-15T11:59:00Z",
            ),
        ]
        wal_mock.backlog_stats.side_effect = [
            WalBacklogStats(0, 1, None),
            WalBacklogStats(1, 1, "2025-01-15T12:00:00Z"),
        ]

        metrics1 = await sse_server.evaluate_backpressure(
            subscriber_id="sub1",
            tenant_id="tenant1",
            space_id="space1",
            topics=["events/created"],
        )
        metrics2 = await sse_server.evaluate_backpressure(
            subscriber_id="sub2",
            tenant_id="tenant1",
            space_id="space1",
            topics=["events/created"],
        )

        assert metrics1.ack_offsets["events/created"] == 1
        assert metrics2.ack_offsets["events/created"] == 0

    async def test_backpressure_levels_progression(
        self,
        sse_server: SSEServer,
        offset_store_mock: OffsetStore,
        wal_mock: WriteAheadLog,
    ) -> None:
        """Test progression through backpressure levels (normal -> warning -> throttle -> shed)."""
        offset_store_mock.fetch.return_value = Offset(
            subscriber_id="sub1",
            topic="events",
            space_id="space1",
            tenant_id="tenant1",
            offset=0,
            updated_ts="2025-01-15T12:00:00+00:00",
        )

        # Test normal -> warning progression by lag
        levels_by_lag = []
        for lag_ms in [0, 1000, 3000, 6000, 20000]:
            latest_ts = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc) + timedelta(
                milliseconds=lag_ms
            )
            wal_mock.backlog_stats.return_value = WalBacklogStats(
                pending_events=100,
                latest_position=150,
                latest_commit_ts=latest_ts.isoformat(),
            )

            metrics = await sse_server.evaluate_backpressure(
                subscriber_id="sub1",
                tenant_id="tenant1",
                space_id="space1",
                topics=["events"],
            )
            levels_by_lag.append(metrics.level)

        assert levels_by_lag[0] == "normal"  # 0ms
        assert levels_by_lag[1] == "normal"  # 1000ms (below warning)
        assert levels_by_lag[2] == "warning"  # 3000ms
        assert levels_by_lag[3] == "throttle"  # 6000ms
        assert levels_by_lag[4] == "shed"  # 20000ms
