"""Tests for k0/sse/server.py"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from k0.obs import ObservabilityEmitter
from k0.qos import QoSContext
from k0.sse.server import BackpressureMetrics, BackpressureTopicMetrics, CursorState, SSEServer
from k0.storage.offsets import Offset, OffsetStore
from k0.storage.wal import WalEntry, WriteAheadLog


@pytest.fixture
def mock_wal():
    """Mock WriteAheadLog."""
    return MagicMock(spec=WriteAheadLog)


@pytest.fixture
def mock_offset_store():
    """Mock OffsetStore."""
    return MagicMock(spec=OffsetStore)


@pytest.fixture
def mock_observability():
    """Mock ObservabilityEmitter."""
    mock = MagicMock(spec=ObservabilityEmitter)
    mock.emit_metric = MagicMock()
    return mock


@pytest.fixture
def mock_qos():
    """Mock QoSContext."""
    return MagicMock(spec=QoSContext)


@pytest.fixture
def temp_acl_path(tmp_path):
    """Create a temporary ACL file."""
    acl_path = tmp_path / "acl.yaml"
    acl_content = """
roles:
  admin:
    allow:
      - "admin.*"
      - "system.*"
  user:
    allow:
      - "user.*"
      - "public.*"
"""
    acl_path.write_text(acl_content)
    return acl_path


@pytest.fixture
def sse_server(mock_wal, mock_offset_store, mock_observability, mock_qos, temp_acl_path):
    """Create SSEServer instance."""
    return SSEServer(
        wal=mock_wal,
        offset_store=mock_offset_store,
        observability=mock_observability,
        acl_path=temp_acl_path,
        qos=mock_qos,
    )


class TestCursorState:
    """Test CursorState dataclass."""

    def test_cursor_state_creation(self):
        """Test creating a CursorState."""
        state = CursorState(
            last_position=100,
            last_ts=datetime(2023, 1, 1, tzinfo=timezone.utc),
            subscriber_id="sub1",
            topic="test.topic",
            space_id="space1",
            tenant_id="tenant1",
        )
        assert state.last_position == 100
        assert state.subscriber_id == "sub1"


class TestBackpressureTopicMetrics:
    """Test BackpressureTopicMetrics dataclass."""

    def test_backpressure_topic_metrics_creation(self):
        """Test creating BackpressureTopicMetrics."""
        metrics = BackpressureTopicMetrics(
            topic="test.topic",
            pending_events=50,
            lag_ms=1000,
            cursor="cursor_token",
        )
        assert metrics.topic == "test.topic"
        assert metrics.pending_events == 50


class TestBackpressureMetrics:
    """Test BackpressureMetrics dataclass."""

    def test_backpressure_metrics_creation(self):
        """Test creating BackpressureMetrics."""
        topics = [
            BackpressureTopicMetrics(
                topic="test.topic",
                pending_events=50,
                lag_ms=1000,
                cursor="cursor_token",
            )
        ]
        metrics = BackpressureMetrics(
            level="warning",
            lag_ms=1000,
            pending_events=50,
            topics=topics,
            ack_offsets={"test.topic": 100},
        )
        assert metrics.level == "warning"
        assert len(metrics.topics) == 1


class TestSSEServer:
    """Test SSEServer class."""

    def test_init(self, sse_server):
        """Test SSEServer initialization."""
        assert sse_server.wal is not None
        assert sse_server.offset_store is not None
        assert sse_server.max_batch == 128

    @pytest.mark.asyncio
    async def test_subscribe_success(self, sse_server, mock_wal):
        """Test successful subscription."""
        # Mock WAL read_from
        mock_wal.read_from.return_value = [
            WalEntry(
                tenant_id="tenant1",
                space_id="space1",
                topic="user.events",
                envelope_json='{"test": "data"}',
                schema_uri="test://schema",
                schema_version="1.0",
                device_id="device123",
                commit_ts="2023-01-01T00:00:00Z",
            )
        ]

        entries, topics = await sse_server.subscribe(
            tenant_id="tenant1",
            space_id="space1",
            subscriber_id="sub1",
            topics=["user.events"],
            roles=["user"],
            cursor_token=None,
        )

        assert len(entries) == 1
        assert "user.events" in topics
        mock_wal.read_from.assert_called_once()

    @pytest.mark.asyncio
    async def test_subscribe_no_permissions(self, sse_server):
        """Test subscription with no topic permissions."""
        with pytest.raises(HTTPException) as exc_info:
            await sse_server.subscribe(
                tenant_id="tenant1",
                space_id="space1",
                subscriber_id="sub1",
                topics=["admin.secret"],
                roles=["user"],
                cursor_token=None,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_subscribe_invalid_fanout_limit(self, sse_server):
        """Test subscription with invalid fanout limit."""
        with pytest.raises(HTTPException) as exc_info:
            await sse_server.subscribe(
                tenant_id="tenant1",
                space_id="space1",
                subscriber_id="sub1",
                topics=["user.events"],
                roles=["user"],
                fanout_limit=-1,
                cursor_token=None,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_subscribe_with_cursor(self, sse_server, mock_wal):
        """Test subscription with cursor token."""
        mock_wal.read_from.return_value = []

        with patch("k0.sse.server.SSEServer._decode_cursor") as mock_decode:
            mock_decode.return_value = CursorState(
                last_position=50,
                last_ts=datetime(2023, 1, 1, tzinfo=timezone.utc),
                subscriber_id="sub1",
                space_id="space1",
                tenant_id="tenant1",
            )

            await sse_server.subscribe(
                tenant_id="tenant1",
                space_id="space1",
                subscriber_id="sub1",
                topics=["user.events"],
                roles=["user"],
                cursor_token="cursor_token",
            )

            # Should read from position 50
            mock_wal.read_from.assert_called_once()
            call_args = mock_wal.read_from.call_args
            assert call_args[0][0] == 50  # last_position    @pytest.mark.asyncio

    async def test_subscribe_cursor_mismatch(self, sse_server):
        """Test subscription with mismatched cursor."""
        with patch("k0.sse.server.SSEServer._decode_cursor") as mock_decode:
            mock_decode.return_value = CursorState(
                last_position=50,
                last_ts=datetime(2023, 1, 1, tzinfo=timezone.utc),
                subscriber_id="different_sub",
                space_id="space1",
                tenant_id="tenant1",
            )

            with pytest.raises(HTTPException) as exc_info:
                await sse_server.subscribe(
                    tenant_id="tenant1",
                    space_id="space1",
                    subscriber_id="sub1",
                    topics=["user.events"],
                    roles=["user"],
                    cursor_token="cursor_token",
                )
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_evaluate_backpressure(self, sse_server, mock_offset_store, mock_wal):
        """Test backpressure evaluation."""
        # Mock offset fetch
        mock_offset = Offset(
            subscriber_id="sub1",
            topic="user.events",
            space_id="space1",
            tenant_id="tenant1",
            offset=100,
            updated_ts="2023-01-01T00:00:00Z",
        )
        mock_offset_store.fetch.return_value = mock_offset

        # Mock WAL backlog stats
        mock_wal.backlog_stats.return_value = MagicMock(
            pending_events=25,
            latest_commit_ts="2023-01-01T00:00:01Z",  # 1 second later, within normal range
        )

        metrics = await sse_server.evaluate_backpressure(
            subscriber_id="sub1",
            tenant_id="tenant1",
            space_id="space1",
            topics=["user.events"],
        )

        assert metrics.level == "normal"  # Low pending events
        assert metrics.pending_events == 25
        assert len(metrics.topics) == 1

    @pytest.mark.asyncio
    async def test_evaluate_backpressure_high_load(self, sse_server, mock_offset_store, mock_wal):
        """Test backpressure evaluation under high load."""
        mock_offset_store.fetch.return_value = None
        mock_wal.backlog_stats.return_value = MagicMock(
            pending_events=100000,  # High pending
            latest_commit_ts="2023-01-01T01:00:00Z",
        )

        metrics = await sse_server.evaluate_backpressure(
            subscriber_id="sub1",
            tenant_id="tenant1",
            space_id="space1",
            topics=["user.events"],
        )

        assert metrics.level == "shed"  # High pending triggers shed

    @pytest.mark.asyncio
    async def test_acknowledge_success(self, sse_server, mock_offset_store):
        """Test successful acknowledgement."""
        mock_offset_store.upsert = AsyncMock()

        await sse_server.acknowledge(
            subscriber_id="sub1",
            tenant_id="tenant1",
            space_id="space1",
            topic="user.events",
            offset=150,
        )

        mock_offset_store.upsert.assert_called_once()
        call_args = mock_offset_store.upsert.call_args
        offset_record = call_args[0][0]
        assert offset_record.subscriber_id == "sub1"
        assert offset_record.offset == 150

    @pytest.mark.asyncio
    async def test_acknowledge_negative_offset(self, sse_server):
        """Test acknowledgement with negative offset."""
        with pytest.raises(HTTPException) as exc_info:
            await sse_server.acknowledge(
                subscriber_id="sub1",
                tenant_id="tenant1",
                space_id="space1",
                topic="user.events",
                offset=-1,
            )
        assert exc_info.value.status_code == 400

    def test_load_acl_success(self, sse_server):
        """Test ACL loading success."""
        permitted = sse_server._load_acl(["user.events", "admin.secret"], ["user"])
        assert "user.events" in permitted
        assert "admin.secret" not in permitted

    def test_load_acl_admin_role(self, sse_server):
        """Test ACL loading with admin role."""
        permitted = sse_server._load_acl(["admin.secret", "user.events"], ["admin"])
        assert "admin.secret" in permitted
        assert "user.events" not in permitted  # admin doesn't have user.* permission

    def test_load_acl_invalid_file(self, mock_wal, mock_offset_store, mock_observability, mock_qos):
        """Test ACL loading with invalid file."""
        invalid_server = SSEServer(
            wal=mock_wal,
            offset_store=mock_offset_store,
            observability=mock_observability,
            acl_path=Path("/nonexistent/acl.yaml"),
            qos=mock_qos,
        )
        with pytest.raises(FileNotFoundError):
            invalid_server._load_acl(["user.events"], ["user"])

    def test_topic_allowed_exact_match(self, sse_server):
        """Test topic permission checking with exact match."""
        assert sse_server._topic_allowed("user.events", ["user.events", "admin.*"])

    def test_topic_allowed_wildcard_match(self, sse_server):
        """Test topic permission checking with wildcard match."""
        assert sse_server._topic_allowed("admin.secret", ["admin.*", "user.*"])

    def test_topic_allowed_no_match(self, sse_server):
        """Test topic permission checking with no match."""
        assert not sse_server._topic_allowed("system.events", ["user.*", "admin.*"])

    def test_decode_cursor_success(self, sse_server):
        """Test cursor decoding success."""
        payload = {
            "offset": 100,
            "ts": "2023-01-01T00:00:00Z",
            "subscriber_id": "sub1",
            "topic": "user.events",
            "space_id": "space1",
            "tenant_id": "tenant1",
            "nonce": "abc123",
        }
        token = json.dumps(payload)

        state = sse_server._decode_cursor(token)
        assert state.last_position == 100
        assert state.subscriber_id == "sub1"

    def test_decode_cursor_malformed_json(self, sse_server, mock_observability):
        """Test cursor decoding with malformed JSON."""
        with pytest.raises(HTTPException) as exc_info:
            sse_server._decode_cursor("invalid json")
        assert exc_info.value.status_code == 400
        mock_observability.emit_metric.assert_called_with(
            "sse_invalid_cursor_total", 1.0, reason="MALFORMED"
        )

    def test_decode_cursor_missing_fields(self, sse_server, mock_observability):
        """Test cursor decoding with missing fields."""
        payload = {"ts": "2023-01-01T00:00:00Z"}  # Missing offset
        token = json.dumps(payload)

        with pytest.raises(HTTPException) as exc_info:
            sse_server._decode_cursor(token)
        assert exc_info.value.status_code == 400
        mock_observability.emit_metric.assert_called_with(
            "sse_invalid_cursor_total", 1.0, reason="MALFORMED"
        )

    def test_decode_cursor_negative_position(self, sse_server, mock_observability):
        """Test cursor decoding with negative position."""
        payload = {
            "offset": -1,
            "ts": "2023-01-01T00:00:00Z",
            "nonce": "abc123",
        }
        token = json.dumps(payload)

        with pytest.raises(HTTPException) as exc_info:
            sse_server._decode_cursor(token)
        assert exc_info.value.status_code == 400
        mock_observability.emit_metric.assert_called_with(
            "sse_invalid_cursor_total", 1.0, reason="NEGATIVE"
        )

    def test_build_cursor(self, sse_server):
        """Test cursor building."""
        token = sse_server.build_cursor(
            subscriber_id="sub1",
            tenant_id="tenant1",
            space_id="space1",
            topic="user.events",
            offset=100,
            commit_ts="2023-01-01T00:00:00Z",
        )

        payload = json.loads(token)
        assert payload["subscriber_id"] == "sub1"
        assert payload["offset"] == 100
        assert "nonce" in payload

    def test_parse_iso8601_with_z(self):
        """Test ISO8601 parsing with Z suffix."""
        dt = SSEServer._parse_iso8601("2023-01-01T00:00:00Z")
        assert dt.year == 2023
        assert dt.month == 1

    def test_parse_iso8601_without_tz(self):
        """Test ISO8601 parsing without timezone."""
        dt = SSEServer._parse_iso8601("2023-01-01T00:00:00")
        assert dt.tzinfo is not None  # Should add UTC
