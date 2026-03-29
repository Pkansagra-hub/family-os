"""
Tests for R0 Batch Selector Phase.

M3 Issue 3.2.1: Tests for R0 Event Ingestion from st_hipp_events.

Test Coverage:
    - Offset fetching and event selection after offset
    - Empty batch (SKIP) handling
    - Event filtering (embedding_status, consolidation_status, archival_status)
    - Batch size limiting
    - Error handling
    - Envelope construction
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest

from k0.pipelines.p03.checkpoint import P03_SOURCE_TOPIC, P03_SUBSCRIBER_ID
from k0.pipelines.p03.phase_interface import P03RunnerContext
from k0.pipelines.p03.phases.r0_batch_selector import (
    R0_FIELD_SPECS,
    R0_SELECT_COLUMNS_SQL,
    R0BatchSelector,
    R0Config,
    get_r0_field_registry_for_discovery,
    get_r0_field_registry_grouped_for_discovery,
)
from k0.pipelines.p03.runner_contract import P03PhaseId, P03PhaseStatus

# =============================================================================
# MOCK INFRASTRUCTURE
# =============================================================================


@dataclass
class MockOffset:
    """Mock offset record."""

    subscriber_id: str
    topic: str
    space_id: str
    tenant_id: str
    offset: int
    updated_ts: str = "2026-01-01T00:00:00Z"


@dataclass
class MockOffsetStore:
    """Mock offset store for testing."""

    offsets: Dict[str, MockOffset] = field(default_factory=dict)

    async def fetch(
        self,
        subscriber_id: str,
        topic: str,
        space_id: str,
        tenant_id: str,
        *,
        connection: Any = None,
    ) -> Optional[MockOffset]:
        """Fetch offset by composite key."""
        key = f"{subscriber_id}:{topic}:{space_id}:{tenant_id}"
        return self.offsets.get(key)

    def set_offset(
        self,
        subscriber_id: str,
        topic: str,
        space_id: str,
        tenant_id: str,
        offset: int,
    ) -> None:
        """Set an offset for testing."""
        key = f"{subscriber_id}:{topic}:{space_id}:{tenant_id}"
        self.offsets[key] = MockOffset(
            subscriber_id=subscriber_id,
            topic=topic,
            space_id=space_id,
            tenant_id=tenant_id,
            offset=offset,
        )


@dataclass
class MockConnection:
    """Mock database connection for testing."""

    rows: List[Dict[str, Any]] = field(default_factory=list)
    st_vec_rows: List[Dict[str, Any]] = field(default_factory=list)

    async def fetch(self, query: str, *params: Any) -> List[Dict[str, Any]]:
        """Return appropriate rows based on query."""
        # Check if this is a st_vec query for embeddings
        if "st_vec" in query.lower() or "vector" in query.lower():
            return self.st_vec_rows
        return self.rows

    async def fetchval(self, query: str, *params: Any) -> Any:
        """Return a single value (for current_database() etc)."""
        if "current_database" in query:
            return "test_db"
        if "COUNT" in query.upper():
            return len(self.rows)
        return None

    async def fetchrow(self, query: str, *params: Any) -> Optional[Dict[str, Any]]:
        """Return a single row."""
        if self.rows:
            return self.rows[0]
        return None


@dataclass
class MockUnitOfWork:
    """Mock UnitOfWork for testing."""

    connection: MockConnection = field(default_factory=MockConnection)
    _connection: Optional[MockConnection] = None

    async def __aenter__(self) -> "MockUnitOfWork":
        self._connection = self.connection
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass


class MockSyscalls:
    """Mock syscalls for R0 testing."""

    def __init__(
        self,
        offset_store: MockOffsetStore,
        uow: MockUnitOfWork,
    ):
        self.offset_store = offset_store
        self._uow = uow

    def unit_of_work(self) -> MockUnitOfWork:
        """Return mock UoW."""
        return self._uow


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_offset_store() -> MockOffsetStore:
    """Create mock offset store."""
    return MockOffsetStore()


@pytest.fixture
def mock_connection() -> MockConnection:
    """Create mock connection."""
    return MockConnection()


@pytest.fixture
def mock_uow(mock_connection: MockConnection) -> MockUnitOfWork:
    """Create mock UnitOfWork."""
    return MockUnitOfWork(connection=mock_connection)


@pytest.fixture
def mock_syscalls(
    mock_offset_store: MockOffsetStore,
    mock_uow: MockUnitOfWork,
) -> MockSyscalls:
    """Create mock syscalls."""
    return MockSyscalls(offset_store=mock_offset_store, uow=mock_uow)


@pytest.fixture
def mock_runner_context(mock_syscalls: MockSyscalls) -> P03RunnerContext:
    """Create mock runner context."""
    return P03RunnerContext(
        syscalls=mock_syscalls,
        logger=logging.getLogger("test.r0"),
        qos_band="GREEN",
        priority=50,
    )


@pytest.fixture
def sample_hipp_event_rows() -> List[Dict[str, Any]]:
    """Create sample st_hipp_events rows."""
    return [
        {
            "event_id": "evt-r0-001",
            "wal_pos": 100,
            "cognitive_trace_id": "trace-001",
            "tenant_id": "tenant-r0",
            "space_id": "space-r0",
            "topic": "chat.message",
            "text": "Hello world",
            "simhash_hex": "abc123",
            "content_type": "TEXT",
            "activity_type": "CHAT",
            "embedding_id": "emb-001",
            "embedding_status": "READY",
            "sentiment_score": 0.5,
            "sentiment_label": "positive",
            "emotions_json": '["joy"]',
            "intent_category": "greeting",
            "ner_entities_json": "[]",
            "temporal_json": "[]",
            "place_id": "place_olive_garden",
            "salience_score": 0.8,
            "created_at": 1735689600000,
        },
        {
            "event_id": "evt-r0-002",
            "wal_pos": 101,
            "cognitive_trace_id": "trace-002",
            "tenant_id": "tenant-r0",
            "space_id": "space-r0",
            "topic": "chat.message",
            "text": "How are you?",
            "simhash_hex": "def456",
            "content_type": "TEXT",
            "activity_type": "CHAT",
            "embedding_id": "emb-002",
            "embedding_status": "READY",
            "sentiment_score": 0.3,
            "sentiment_label": "neutral",
            "emotions_json": "[]",
            "intent_category": "question",
            "ner_entities_json": "[]",
            "temporal_json": "[]",
            "salience_score": 0.6,
            "created_at": 1735689601000,
        },
        {
            "event_id": "evt-r0-003",
            "wal_pos": 102,
            "cognitive_trace_id": "trace-003",
            "tenant_id": "tenant-r0",
            "space_id": "space-r0",
            "topic": "chat.message",
            "text": "I am fine, thank you!",
            "simhash_hex": "ghi789",
            "content_type": "TEXT",
            "activity_type": "CHAT",
            "embedding_id": "emb-003",
            "embedding_status": "READY",
            "sentiment_score": 0.7,
            "sentiment_label": "positive",
            "emotions_json": '["gratitude"]',
            "intent_category": "response",
            "ner_entities_json": "[]",
            "temporal_json": "[]",
            "salience_score": 0.5,
            "created_at": 1735689602000,
        },
    ]


@pytest.fixture
def sample_st_vec_rows() -> List[Dict[str, Any]]:
    """Create sample st_vec rows with mock embedding vectors."""
    import struct

    # Create a mock 768-dim vector as bytes (768 floats * 4 bytes = 3072 bytes)
    mock_vector = [0.1] * 768
    vector_bytes = struct.pack(f"{768}f", *mock_vector)

    return [
        {
            "event_id": "evt-r0-001",
            "vector": vector_bytes,
            "vector_dim": 768,
        },
        {
            "event_id": "evt-r0-002",
            "vector": vector_bytes,
            "vector_dim": 768,
        },
        {
            "event_id": "evt-r0-003",
            "vector": vector_bytes,
            "vector_dim": 768,
        },
    ]


# =============================================================================
# R0 OFFSET TESTS
# =============================================================================


class TestR0OffsetHandling:
    """Tests for R0 offset fetching and handling."""

    @pytest.mark.asyncio
    async def test_r0_fetches_offset_at_startup(
        self,
        mock_offset_store: MockOffsetStore,
        mock_connection: MockConnection,
        mock_runner_context: P03RunnerContext,
        sample_hipp_event_rows: List[Dict[str, Any]],
        sample_st_vec_rows: List[Dict[str, Any]],
    ) -> None:
        """
        Given: Existing offset in store
        When: R0 runs
        Then: Uses offset to filter events
        """
        # Set offset at wal_pos 100 (should skip evt-r0-001)
        mock_offset_store.set_offset(
            subscriber_id=P03_SUBSCRIBER_ID,
            topic=P03_SOURCE_TOPIC,
            space_id="space-r0",
            tenant_id="tenant-r0",
            offset=100,
        )

        # Only return events after offset
        mock_connection.rows = [row for row in sample_hipp_event_rows if row["wal_pos"] > 100]
        # Provide embeddings for the events
        mock_connection.st_vec_rows = [
            r for r in sample_st_vec_rows if r["event_id"] != "evt-r0-001"
        ]

        r0 = R0BatchSelector()
        envelope, result = await r0.run("tenant-r0", "space-r0", mock_runner_context)

        assert result.status == P03PhaseStatus.DONE
        assert envelope is not None
        assert len(envelope.events) == 2  # evt-002 and evt-003


class TestR0FieldRegistry:
    """Regression tests for the declarative R0 field registry."""

    def test_registry_exposes_phase_metadata_for_discovery(self) -> None:
        rows = get_r0_field_registry_for_discovery()

        assert len(rows) == len(R0_FIELD_SPECS)
        assert rows[0]["row_key"] == R0_FIELD_SPECS[0].row_key
        assert rows[0]["signal_family"]
        assert rows[0]["phase_consumers"]
        assert all(isinstance(phase_id, str) for phase_id in rows[0]["phase_consumers"])

        temporal_links = next(row for row in rows if row["row_key"] == "temporal_links_json")
        assert temporal_links["state_field"] == "temporal_links_json"
        assert temporal_links["signal_family"] == "temporal_context"
        assert temporal_links["phase_consumers"] == [
            P03PhaseId.R0_INIT.value,
            P03PhaseId.R2_CLUSTER.value,
            P03PhaseId.R8_EMIT.value,
        ]

    def test_registry_grouping_exposes_signal_families(self) -> None:
        grouped = get_r0_field_registry_grouped_for_discovery()

        assert grouped
        temporal_group = next(
            group for group in grouped if group["signal_family"] == "temporal_context"
        )
        assert temporal_group["field_count"] > 0
        assert P03PhaseId.R2_CLUSTER.value in temporal_group["phase_consumers"]
        assert any(field["row_key"] == "temporal_links_json" for field in temporal_group["fields"])

    def test_registry_select_list_and_payload_mapping_stay_in_sync(self) -> None:
        row: Dict[str, Any] = {
            "event_id": "evt-sync-001",
            "intent_ultrabert": "reflect",
            "intent_category": "fallback-intent",
            "temporal_source": "conversation_anchor",
            "temporal_resolved_epoch_ms": 1712345678000,
        }

        for index, spec in enumerate(R0_FIELD_SPECS, start=1):
            if spec.row_key in row:
                continue
            if spec.default is not None:
                row[spec.row_key] = spec.default
                continue
            if spec.converter is int:
                row[spec.row_key] = index
            elif spec.converter is float:
                row[spec.row_key] = float(index)
            else:
                row[spec.row_key] = f"value-{index}"

        row["activity_type_confidence"] = 0.91
        row["intent_confidence"] = 0.87
        row["sentiment_score"] = 0.44
        row["salience_score"] = 0.66
        row["novelty_score"] = 0.55
        row["affect_valence"] = 0.22
        row["affect_arousal"] = 0.33
        row["num_participants"] = 2
        row["narrative_is_goal_event"] = True
        row["affect_dominance"] = 0.11
        row["extraction_sequence"] = 5
        row["surprise_level"] = 0.77
        row["identity_relevance"] = 0.88
        row["source_reliability"] = 0.99
        row["conversation_anchor_ms"] = 1712345678000
        row["event_time_utc"] = 1712345678
        row["created_at"] = 1712345678

        payload = R0BatchSelector._build_state_payload(row, event_time_ms=1712345678000)

        assert R0_SELECT_COLUMNS_SQL == ",\n                ".join(
            spec.select_sql for spec in R0_FIELD_SPECS
        )
        assert len({spec.row_key for spec in R0_FIELD_SPECS}) == len(R0_FIELD_SPECS)

        for spec in R0_FIELD_SPECS:
            assert spec.select_sql in R0_SELECT_COLUMNS_SQL
            if spec.state_field is None:
                continue
            expected = R0BatchSelector._spec_to_state_value(row, spec)
            assert payload[spec.state_field] == expected

        assert payload["intent_label"] == "reflect"
        assert payload["temporal_source"] == "conversation_anchor"

    def test_row_to_event_state_normalizes_second_based_conversation_anchor(self) -> None:
        row = {
            "event_id": "evt-anchor-seconds",
            "conversation_anchor_ms": 1704067200,
            "event_time_utc": 1704067200,
            "created_at": 1704067200,
        }

        for index, spec in enumerate(R0_FIELD_SPECS, start=1):
            if spec.row_key in row:
                continue
            if spec.default is not None:
                row[spec.row_key] = spec.default
                continue
            if spec.converter is int:
                row[spec.row_key] = index
            elif spec.converter is float:
                row[spec.row_key] = float(index)
            else:
                row[spec.row_key] = f"value-{index}"

        row["activity_type_confidence"] = 0.91
        row["intent_confidence"] = 0.87
        row["sentiment_score"] = 0.44
        row["salience_score"] = 0.66
        row["novelty_score"] = 0.55
        row["affect_valence"] = 0.22
        row["affect_arousal"] = 0.33
        row["num_participants"] = 2
        row["narrative_is_goal_event"] = True
        row["affect_dominance"] = 0.11
        row["extraction_sequence"] = 5
        row["surprise_level"] = 0.77
        row["identity_relevance"] = 0.88
        row["source_reliability"] = 0.99

        event = R0BatchSelector()._row_to_event_state(row)

        assert event.timestamp == 1704067200000

    @pytest.mark.asyncio
    async def test_r0_starts_at_zero_when_no_offset(
        self,
        mock_offset_store: MockOffsetStore,
        mock_connection: MockConnection,
        mock_runner_context: P03RunnerContext,
        sample_hipp_event_rows: List[Dict[str, Any]],
        sample_st_vec_rows: List[Dict[str, Any]],
    ) -> None:
        """
        Given: No prior offset in store
        When: R0 runs
        Then: Starts from offset 0 (selects all events)
        """
        # No offset set - should start from 0
        mock_connection.rows = sample_hipp_event_rows
        mock_connection.st_vec_rows = sample_st_vec_rows

        r0 = R0BatchSelector()
        envelope, result = await r0.run("tenant-r0", "space-r0", mock_runner_context)

        assert result.status == P03PhaseStatus.DONE
        assert envelope is not None
        assert len(envelope.events) == 3  # All events

    @pytest.mark.asyncio
    async def test_r0_respects_offset_exactly(
        self,
        mock_offset_store: MockOffsetStore,
        mock_connection: MockConnection,
        mock_runner_context: P03RunnerContext,
        sample_hipp_event_rows: List[Dict[str, Any]],
    ) -> None:
        """
        Given: Offset at specific wal_pos
        When: R0 runs
        Then: Only selects events with wal_pos > offset (not >=)
        """
        # Set offset exactly at last event
        mock_offset_store.set_offset(
            subscriber_id=P03_SUBSCRIBER_ID,
            topic=P03_SOURCE_TOPIC,
            space_id="space-r0",
            tenant_id="tenant-r0",
            offset=102,  # evt-003's wal_pos
        )

        # No events after offset 102
        mock_connection.rows = []

        r0 = R0BatchSelector()
        envelope, result = await r0.run("tenant-r0", "space-r0", mock_runner_context)

        # Should skip (no events)
        assert result.status == P03PhaseStatus.SKIP
        assert envelope is None


# =============================================================================
# R0 BATCH SELECTION TESTS
# =============================================================================


class TestR0BatchSelection:
    """Tests for R0 event selection logic."""

    @pytest.mark.asyncio
    async def test_r0_respects_batch_size_limit(
        self,
        mock_connection: MockConnection,
        mock_runner_context: P03RunnerContext,
        sample_hipp_event_rows: List[Dict[str, Any]],
        sample_st_vec_rows: List[Dict[str, Any]],
    ) -> None:
        """
        Given: More events than batch_size
        When: R0 runs with batch_size=2
        Then: Only selects batch_size events
        """
        # Return only 2 events (simulating LIMIT)
        mock_connection.rows = sample_hipp_event_rows[:2]
        mock_connection.st_vec_rows = sample_st_vec_rows[:2]

        r0 = R0BatchSelector(config=R0Config(batch_size=2))
        envelope, result = await r0.run("tenant-r0", "space-r0", mock_runner_context)

        assert result.status == P03PhaseStatus.DONE
        assert envelope is not None
        assert len(envelope.events) == 2

    @pytest.mark.asyncio
    async def test_r0_skip_when_no_events(
        self,
        mock_connection: MockConnection,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """
        Given: No eligible events
        When: R0 runs
        Then: Returns SKIP result with None envelope
        """
        mock_connection.rows = []

        r0 = R0BatchSelector()
        envelope, result = await r0.run("tenant-r0", "space-r0", mock_runner_context)

        assert result.status == P03PhaseStatus.SKIP
        assert result.skip_reason == "No eligible events found"
        assert envelope is None

    @pytest.mark.asyncio
    async def test_r0_creates_valid_envelope(
        self,
        mock_connection: MockConnection,
        mock_runner_context: P03RunnerContext,
        sample_hipp_event_rows: List[Dict[str, Any]],
        sample_st_vec_rows: List[Dict[str, Any]],
    ) -> None:
        """
        Given: Eligible events
        When: R0 runs
        Then: Creates valid P03BatchEnvelope with context and events
        """
        mock_connection.rows = sample_hipp_event_rows
        mock_connection.st_vec_rows = sample_st_vec_rows

        r0 = R0BatchSelector()
        envelope, result = await r0.run("tenant-r0", "space-r0", mock_runner_context)

        assert envelope is not None
        # Verify context
        assert envelope.context.tenant_id == "tenant-r0"
        assert envelope.context.space_id == "space-r0"
        assert envelope.context.batch_size == 3
        assert len(envelope.context.event_ids) == 3
        # Verify events
        assert len(envelope.events) == 3
        assert envelope.events[0].event_id == "evt-r0-001"

    @pytest.mark.asyncio
    async def test_r0_event_state_population(
        self,
        mock_connection: MockConnection,
        mock_runner_context: P03RunnerContext,
        sample_hipp_event_rows: List[Dict[str, Any]],
        sample_st_vec_rows: List[Dict[str, Any]],
    ) -> None:
        """
        Given: Events with all fields
        When: R0 runs
        Then: P03EventState is correctly populated
        """
        mock_connection.rows = sample_hipp_event_rows[:1]
        mock_connection.st_vec_rows = sample_st_vec_rows[:1]

        r0 = R0BatchSelector()
        envelope, result = await r0.run("tenant-r0", "space-r0", mock_runner_context)

        assert envelope is not None
        event = envelope.events[0]

        # Verify event state fields
        assert event.event_id == "evt-r0-001"
        assert event.content_text == "Hello world"
        assert event.content_type == "TEXT"
        assert event.simhash_hex == "abc123"
        assert event.embedding_id == "emb-001"
        assert event.sentiment_score == 0.5
        assert event.sentiment_label == "positive"
        assert event.emotions_json == '["joy"]'
        assert event.intent_label == "greeting"
        assert event.place_id == "place_olive_garden"


# =============================================================================
# R0 RESULT TESTS
# =============================================================================


class TestR0Results:
    """Tests for R0 result construction."""

    @pytest.mark.asyncio
    async def test_r0_result_includes_outputs_summary(
        self,
        mock_connection: MockConnection,
        mock_runner_context: P03RunnerContext,
        sample_hipp_event_rows: List[Dict[str, Any]],
        sample_st_vec_rows: List[Dict[str, Any]],
    ) -> None:
        """
        Given: Successful batch selection
        When: R0 completes
        Then: Result includes outputs_summary with metrics
        """
        mock_connection.rows = sample_hipp_event_rows
        mock_connection.st_vec_rows = sample_st_vec_rows

        r0 = R0BatchSelector()
        envelope, result = await r0.run("tenant-r0", "space-r0", mock_runner_context)

        assert result.outputs_summary is not None
        assert result.outputs_summary["events_selected"] == 3
        assert "offset_start" in result.outputs_summary
        assert "batch_id" in result.outputs_summary

    @pytest.mark.asyncio
    async def test_r0_result_has_idempotency_key(
        self,
        mock_connection: MockConnection,
        mock_runner_context: P03RunnerContext,
        sample_hipp_event_rows: List[Dict[str, Any]],
        sample_st_vec_rows: List[Dict[str, Any]],
    ) -> None:
        """
        Given: Successful batch selection
        When: R0 completes
        Then: Result includes idempotency key
        """
        mock_connection.rows = sample_hipp_event_rows
        mock_connection.st_vec_rows = sample_st_vec_rows

        r0 = R0BatchSelector()
        envelope, result = await r0.run("tenant-r0", "space-r0", mock_runner_context)

        assert result.idempotency_key is not None
        assert result.idempotency_key.startswith("p03:r0:")

    @pytest.mark.asyncio
    async def test_r0_result_includes_duration(
        self,
        mock_connection: MockConnection,
        mock_runner_context: P03RunnerContext,
        sample_hipp_event_rows: List[Dict[str, Any]],
    ) -> None:
        """
        Given: R0 execution
        When: R0 completes
        Then: Result includes duration_ms
        """
        mock_connection.rows = sample_hipp_event_rows

        r0 = R0BatchSelector()
        _, result = await r0.run("tenant-r0", "space-r0", mock_runner_context)

        assert result.duration_ms >= 0


# =============================================================================
# R0 ERROR HANDLING TESTS
# =============================================================================


class TestR0ErrorHandling:
    """Tests for R0 error handling."""

    @pytest.mark.asyncio
    async def test_r0_handles_db_error_gracefully(
        self,
        mock_offset_store: MockOffsetStore,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """
        Given: Database error during event query
        When: R0 runs
        Then: Returns FAIL result with error details
        """

        # Make syscalls raise an error
        async def raise_error(*args, **kwargs):
            raise RuntimeError("Database connection failed")

        mock_runner_context.syscalls.offset_store.fetch = raise_error

        r0 = R0BatchSelector()
        envelope, result = await r0.run("tenant-r0", "space-r0", mock_runner_context)

        assert result.status == P03PhaseStatus.FAIL
        assert result.error_info is not None
        assert result.error_info.error_type == "R0_INGESTION_ERROR"
        assert "Database connection failed" in result.error_info.error_message
        assert envelope is None

    @pytest.mark.asyncio
    async def test_r0_error_is_marked_recoverable(
        self,
        mock_offset_store: MockOffsetStore,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """
        Given: R0 failure
        When: Checking error
        Then: Error is marked as recoverable
        """

        async def raise_error(*args, **kwargs):
            raise RuntimeError("Transient error")

        mock_runner_context.syscalls.offset_store.fetch = raise_error

        r0 = R0BatchSelector()
        _, result = await r0.run("tenant-r0", "space-r0", mock_runner_context)

        assert result.error_info is not None
        assert result.error_info.recoverable is True


# =============================================================================
# R0 CONFIGURATION TESTS
# =============================================================================


class TestR0Configuration:
    """Tests for R0 configuration handling."""

    def test_r0_default_config(self) -> None:
        """Default configuration values."""
        config = R0Config()

        assert config.batch_size == 100
        assert config.require_embedding_ready is True
        assert config.exclude_archived is True
        assert config.max_age_hours == 0

    def test_r0_custom_config(self) -> None:
        """Custom configuration values."""
        config = R0Config(
            batch_size=50,
            require_embedding_ready=False,
            exclude_archived=False,
            max_age_hours=24,
        )

        assert config.batch_size == 50
        assert config.require_embedding_ready is False
        assert config.exclude_archived is False
        assert config.max_age_hours == 24

    @pytest.mark.asyncio
    async def test_r0_uses_configured_batch_size(
        self,
        mock_connection: MockConnection,
        mock_runner_context: P03RunnerContext,
        sample_hipp_event_rows: List[Dict[str, Any]],
        sample_st_vec_rows: List[Dict[str, Any]],
    ) -> None:
        """R0 uses configured batch size in query."""
        # This test verifies config is passed through
        mock_connection.rows = sample_hipp_event_rows[:1]
        mock_connection.st_vec_rows = sample_st_vec_rows[:1]

        config = R0Config(batch_size=1)
        r0 = R0BatchSelector(config=config)
        envelope, result = await r0.run("tenant-r0", "space-r0", mock_runner_context)

        assert result.status == P03PhaseStatus.DONE
        assert envelope is not None
        # Mock returns 1 event (simulating LIMIT 1)
        assert len(envelope.events) == 1
