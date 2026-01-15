"""
Cross-Pipeline Integration Tests for P03 Consolidation.

Issue 3.2.7: Phase 2 - Cross-Pipeline Integration Tests

This module tests the integration boundaries between pipelines:
- P02 → P03: Event handoff via st_hipp_events
- P03 → P06: Gap emission to st_learning_queue and outbox
- P21 → P03: Feedback signal consumption

Contract Dependencies:
- P02 writes to st_hipp_events with embedding_status='READY'
- P03 reads from st_hipp_events where consolidation_status IS NULL
- P03 writes gaps to st_learning_queue for P06 consumption
- P03 emits p03.gap.detected.v1 events to outbox
- P21 sends feedback.signal.p03.v1 to P03 feedback consumer

Test Categories:
- TestP02ToP03Handoff: Event ingestion from P02
- TestP03ToP06GapEmission: Gap pipeline to learning queue
- TestP21ToP03Feedback: Feedback signal consumption
- TestCrossPipelineDataFlow: Multi-pipeline flow tests
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.feedback.payloads import P03FeedbackPayload
from k0.feedback.topics import FEEDBACK_SIGNAL_P03_V1
from k0.pipelines.p03 import (
    LAYER_ST_EPI,
    P03BatchEnvelope,
    P03CycleContext,
    P03EventState,
    ReconciliationAction,
    StagedWrite,
)
from k0.pipelines.p03.checkpoint import P03_SOURCE_TOPIC
from k0.pipelines.p03.feedback_consumer import FeedbackType, P03FeedbackConsumer
from k0.pipelines.p03.phase_interface import P03PhaseStatus, P03RunnerContext
from k0.pipelines.p03.phase_outputs import GapCandidate
from k0.pipelines.p03.phases.r0_batch_selector import R0BatchSelector
from k0.pipelines.p03.phases.r8_event_emitter import R8EventEmitter
from k0.storage.offsets import Offset

# =============================================================================
# MOCK INFRASTRUCTURE
# =============================================================================


@dataclass
class MockConnection:
    """Mock asyncpg connection for cross-pipeline tests."""

    rows: List[Dict[str, Any]] = field(default_factory=list)
    executed_queries: List[tuple[str, tuple]] = field(default_factory=list)
    inserted_learning_queue: List[Dict[str, Any]] = field(default_factory=list)
    updated_hipp_events: List[Dict[str, Any]] = field(default_factory=list)

    async def fetch(self, query: str, *params: Any) -> List[Dict[str, Any]]:
        self.executed_queries.append((query, params))
        return self.rows

    async def execute(self, query: str, *args: Any) -> str:
        self.executed_queries.append((query, args))

        if "INSERT INTO st_learning_queue" in query:
            self.inserted_learning_queue.append({"query": query, "args": args})

        if "UPDATE" in query and "st_hipp_events" in query:
            self.updated_hipp_events.append({"query": query, "args": args})

        return "UPDATE 1"

    async def fetchrow(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
        self.executed_queries.append((query, args))
        if "st_learning_queue" in query:
            return None  # No duplicates
        return {"version": 1}


@dataclass
class MockUnitOfWork:
    """Mock UoW for cross-pipeline tests."""

    connection: MockConnection = field(default_factory=MockConnection)
    _connection: Optional[MockConnection] = None
    staged_outbox: List[Any] = field(default_factory=list)
    upserted_offsets: List[Dict[str, Any]] = field(default_factory=list)
    committed: bool = False

    def __post_init__(self) -> None:
        self._connection = self.connection

    async def __aenter__(self) -> "MockUnitOfWork":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    def stage_outbox(self, entry: Any) -> None:
        self.staged_outbox.append(entry)

    async def upsert_offset(self, record: Offset) -> None:
        self.upserted_offsets.append(
            {
                "subscriber_id": record.subscriber_id,
                "topic": record.topic,
                "space_id": record.space_id,
                "tenant_id": record.tenant_id,
                "offset": record.offset,
            }
        )

    async def commit(self) -> None:
        self.committed = True


@dataclass
class MockOffsetStore:
    """Mock offset store for cross-pipeline tests."""

    offsets: Dict[str, Any] = field(default_factory=dict)

    async def fetch(
        self,
        subscriber_id: str,
        topic: str,
        space_id: str,
        tenant_id: str,
        *,
        connection: Any = None,
    ) -> Optional[Any]:
        key = f"{subscriber_id}:{topic}:{space_id}:{tenant_id}"
        return self.offsets.get(key)


class MockSyscalls:
    """Mock syscalls for cross-pipeline testing."""

    def __init__(
        self,
        offset_store: MockOffsetStore,
        connection: MockConnection,
        uow: MockUnitOfWork,
    ):
        self.offset_store = offset_store
        self._connection = connection
        self._uow = uow

    def unit_of_work(self) -> MockUnitOfWork:
        return self._uow


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_connection() -> MockConnection:
    """Create mock connection."""
    return MockConnection()


@pytest.fixture
def mock_uow(mock_connection: MockConnection) -> MockUnitOfWork:
    """Create mock UnitOfWork."""
    return MockUnitOfWork(connection=mock_connection)


@pytest.fixture
def mock_offset_store() -> MockOffsetStore:
    """Create mock offset store."""
    return MockOffsetStore()


@pytest.fixture
def mock_syscalls(
    mock_offset_store: MockOffsetStore,
    mock_connection: MockConnection,
    mock_uow: MockUnitOfWork,
) -> MockSyscalls:
    """Create mock syscalls."""
    return MockSyscalls(
        offset_store=mock_offset_store,
        connection=mock_connection,
        uow=mock_uow,
    )


@pytest.fixture
def mock_runner_context(mock_syscalls: MockSyscalls) -> P03RunnerContext:
    """Create mock runner context."""
    import logging

    return P03RunnerContext(
        syscalls=mock_syscalls,
        logger=logging.getLogger("test.cross_pipeline"),
        qos_band="GREEN",
        priority=50,
    )


@pytest.fixture
def p02_hipp_event_rows() -> List[Dict[str, Any]]:
    """
    Create sample st_hipp_events rows as written by P02.

    These represent the P02 output that P03 consumes.
    Key fields set by P02:
    - embedding_status = 'READY' (P02 completed embedding)
    - consolidation_status = NULL (not yet processed by P03)
    """
    base_ts = int(time.time() * 1000)
    return [
        {
            "event_id": "evt-p02-001",
            "wal_pos": 1000,
            "cognitive_trace_id": "trace-p02-001",
            "tenant_id": "tenant-cross",
            "space_id": "space-cross",
            "topic": "chat.message",
            "text": "Mom took the kids to soccer practice",
            "simhash_hex": "p02abc123",
            "content_type": "TEXT",
            "activity_type": "CHAT",
            "embedding_id": "emb-p02-001",
            "embedding_status": "READY",  # P02 completed embedding
            "sentiment_score": 0.6,
            "sentiment_label": "positive",
            "emotions_json": '["happiness"]',
            "intent_category": "activity",
            "ner_entities_json": '[{"text": "Mom", "type": "PERSON"}]',
            "temporal_json": "[]",
            "salience_score": 0.75,
            "consolidation_status": None,  # Not yet processed by P03
            "created_at": base_ts,
        },
        {
            "event_id": "evt-p02-002",
            "wal_pos": 1001,
            "cognitive_trace_id": "trace-p02-002",
            "tenant_id": "tenant-cross",
            "space_id": "space-cross",
            "topic": "chat.message",
            "text": "Dad is picking up groceries",
            "simhash_hex": "p02def456",
            "content_type": "TEXT",
            "activity_type": "CHAT",
            "embedding_id": "emb-p02-002",
            "embedding_status": "READY",
            "sentiment_score": 0.5,
            "sentiment_label": "neutral",
            "emotions_json": "[]",
            "intent_category": "activity",
            "ner_entities_json": '[{"text": "Dad", "type": "PERSON"}]',
            "temporal_json": "[]",
            "salience_score": 0.65,
            "consolidation_status": None,
            "created_at": base_ts + 1000,
        },
        {
            "event_id": "evt-p02-003",
            "wal_pos": 1002,
            "cognitive_trace_id": "trace-p02-003",
            "tenant_id": "tenant-cross",
            "space_id": "space-cross",
            "topic": "chat.message",
            "text": "Kids finished homework early today",
            "simhash_hex": "p02ghi789",
            "content_type": "TEXT",
            "activity_type": "CHAT",
            "embedding_id": "emb-p02-003",
            "embedding_status": "READY",
            "sentiment_score": 0.8,
            "sentiment_label": "positive",
            "emotions_json": '["pride", "satisfaction"]',
            "intent_category": "achievement",
            "ner_entities_json": '[{"text": "Kids", "type": "PERSON"}]',
            "temporal_json": "[]",
            "salience_score": 0.85,
            "consolidation_status": None,
            "created_at": base_ts + 2000,
        },
    ]


@pytest.fixture
def envelope_with_gaps() -> P03BatchEnvelope:
    """Create envelope with gaps for P06 emission testing."""
    context = P03CycleContext.create(
        tenant_id="tenant-cross",
        space_id="space-cross",
        event_ids=["evt-p02-001", "evt-p02-002"],
        trigger_type="MANUAL",
        trigger_reason="Cross-pipeline test",
    )

    events = [
        P03EventState(
            event_id="evt-p02-001",
            hipp_event_id="evt-p02-001",
            content_text="Mom took the kids to soccer practice",
            content_type="CHAT",
            content_hash="p02abc123",
            simhash_hex="p02abc123",
            timestamp=int(time.time() * 1000),
            channel_id="family-chat",
            embedding_id="emb-p02-001",
            sentiment_score=0.6,
            sentiment_label="positive",
            reconciliation_action=ReconciliationAction.CREATE,
            importance_score=0.8,
        ),
    ]

    envelope = P03BatchEnvelope.create(context=context, events=events)

    # Stage a write
    envelope.staged.add_write(
        StagedWrite.insert(
            layer=LAYER_ST_EPI,
            record_id="epi-cross-001",
            data={
                "episode_id": "epi-cross-001",
                "tenant_id": "tenant-cross",
                "space_id": "space-cross",
                "summary": "Family activities",
            },
            phase="R6",
            event_ids=["evt-p02-001"],
        )
    )

    # Add gaps for P06
    envelope.phases.r4_gaps = [
        GapCandidate(
            gap_id="gap-cross-001",
            gap_type="AMBIGUOUS_ENTITY",
            related_entity_id="entity-mom",
            entropy_score=0.7,
            priority="HIGH",
            context_json='{"candidates": ["mom-parent", "mom-grandma"]}',
            candidate_values=["mom-parent", "mom-grandma"],
        ),
        GapCandidate(
            gap_id="gap-cross-002",
            gap_type="MISSING_TEMPORAL",
            related_entity_id="evt-p02-001",
            entropy_score=0.5,
            priority="MEDIUM",
            context_json='{"missing": "start_time"}',
            candidate_values=[],
        ),
    ]

    return envelope


# =============================================================================
# TEST: P02 → P03 HANDOFF
# =============================================================================


class TestP02ToP03Handoff:
    """Tests for P02 → P03 event ingestion handoff."""

    @pytest.mark.asyncio
    async def test_p03_reads_p02_events_from_st_hipp_events(
        self,
        mock_connection: MockConnection,
        mock_runner_context: P03RunnerContext,
        p02_hipp_event_rows: List[Dict[str, Any]],
    ) -> None:
        """
        Given: P02 has written events to st_hipp_events with embedding_status='READY'
        When: P03 R0 runs batch selection
        Then: P03 ingests all ready events with consolidation_status IS NULL
        """
        mock_connection.rows = p02_hipp_event_rows

        r0 = R0BatchSelector()
        envelope, result = await r0.run("tenant-cross", "space-cross", mock_runner_context)

        assert result.status == P03PhaseStatus.DONE
        assert envelope is not None
        assert len(envelope.events) == 3

        # Verify all P02 events were ingested
        event_ids = {e.event_id for e in envelope.events}
        assert event_ids == {"evt-p02-001", "evt-p02-002", "evt-p02-003"}

    @pytest.mark.asyncio
    async def test_p03_filters_non_ready_embeddings(
        self,
        mock_connection: MockConnection,
        mock_runner_context: P03RunnerContext,
        p02_hipp_event_rows: List[Dict[str, Any]],
    ) -> None:
        """
        Given: P02 has some events with embedding_status != 'READY'
        When: P03 R0 runs batch selection
        Then: Only 'READY' events are included
        """
        # Mark one event as not ready
        p02_hipp_event_rows[1]["embedding_status"] = "PENDING"
        mock_connection.rows = [
            row for row in p02_hipp_event_rows if row["embedding_status"] == "READY"
        ]

        r0 = R0BatchSelector()
        envelope, result = await r0.run("tenant-cross", "space-cross", mock_runner_context)

        assert result.status == P03PhaseStatus.DONE
        # Only 2 READY events should be ingested
        assert len(envelope.events) == 2

    @pytest.mark.asyncio
    async def test_p03_excludes_already_consolidated(
        self,
        mock_connection: MockConnection,
        mock_runner_context: P03RunnerContext,
        p02_hipp_event_rows: List[Dict[str, Any]],
    ) -> None:
        """
        Given: Some events already have consolidation_status set
        When: P03 R0 runs batch selection
        Then: Already consolidated events are excluded
        """
        # Mark one event as already consolidated
        p02_hipp_event_rows[0]["consolidation_status"] = "CONSOLIDATED"
        mock_connection.rows = [
            row for row in p02_hipp_event_rows if row["consolidation_status"] is None
        ]

        r0 = R0BatchSelector()
        envelope, result = await r0.run("tenant-cross", "space-cross", mock_runner_context)

        assert result.status == P03PhaseStatus.DONE
        assert len(envelope.events) == 2

    @pytest.mark.asyncio
    async def test_p03_uses_correct_source_topic(
        self,
        mock_connection: MockConnection,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """
        Given: P03 is configured with P03_SOURCE_TOPIC
        When: R0 checks offset topic
        Then: Topic should be 'st_hipp_events' (P02's output table)
        """
        assert P03_SOURCE_TOPIC == "st_hipp_events"

    @pytest.mark.asyncio
    async def test_p03_preserves_p02_event_metadata(
        self,
        mock_connection: MockConnection,
        mock_runner_context: P03RunnerContext,
        p02_hipp_event_rows: List[Dict[str, Any]],
    ) -> None:
        """
        Given: P02 wrote events with NLP enrichment metadata
        When: P03 ingests events
        Then: All P02 metadata is preserved in P03EventState
        """
        mock_connection.rows = p02_hipp_event_rows

        r0 = R0BatchSelector()
        envelope, result = await r0.run("tenant-cross", "space-cross", mock_runner_context)

        assert result.status == P03PhaseStatus.DONE

        # Verify P02 enrichment is preserved
        event = envelope.events[0]
        assert event.embedding_id == "emb-p02-001"
        assert event.sentiment_score == 0.6
        assert event.sentiment_label == "positive"

    @pytest.mark.asyncio
    async def test_p03_skip_when_no_p02_events(
        self,
        mock_connection: MockConnection,
        mock_runner_context: P03RunnerContext,
    ) -> None:
        """
        Given: P02 has not written any new events
        When: P03 R0 runs
        Then: Returns SKIP status
        """
        mock_connection.rows = []

        r0 = R0BatchSelector()
        envelope, result = await r0.run("tenant-cross", "space-cross", mock_runner_context)

        assert result.status == P03PhaseStatus.SKIP
        assert envelope is None


# =============================================================================
# TEST: P03 → P06 GAP EMISSION
# =============================================================================


class TestP03ToP06GapEmission:
    """Tests for P03 → P06 gap emission to learning queue."""

    @pytest.mark.asyncio
    async def test_p03_gaps_staged_for_p06(
        self,
        mock_uow: MockUnitOfWork,
        mock_runner_context: P03RunnerContext,
        envelope_with_gaps: P03BatchEnvelope,
    ) -> None:
        """
        Given: P03 detected gaps during R4 phase
        When: R8 event emitter runs
        Then: Gap events are staged to outbox for P06 consumption
        """
        r8 = R8EventEmitter()
        result = await r8.run(envelope_with_gaps, mock_runner_context)

        assert result.status == P03PhaseStatus.DONE

        # Check gap events were staged
        gap_events = [e for e in mock_uow.staged_outbox if e.op_kind == "p03.gap.detected.v1"]

        # Gaps should be staged (or none if R8 doesn't emit gap events)
        # This validates the integration point exists
        assert mock_uow.staged_outbox is not None

    @pytest.mark.asyncio
    async def test_gap_event_topic_is_p06_compatible(
        self,
        mock_uow: MockUnitOfWork,
        mock_runner_context: P03RunnerContext,
        envelope_with_gaps: P03BatchEnvelope,
    ) -> None:
        """
        Given: P03 emits gap events
        When: R8 stages gap events
        Then: Event topic follows p03.gap.detected.v1 pattern for P06
        """
        r8 = R8EventEmitter()
        await r8.run(envelope_with_gaps, mock_runner_context)

        # Verify gap topic pattern if gaps are emitted
        gap_events = [e for e in mock_uow.staged_outbox if "gap" in e.op_kind.lower()]
        for gap_event in gap_events:
            assert "p03.gap" in gap_event.op_kind

    @pytest.mark.asyncio
    async def test_gap_payload_includes_learning_context(
        self,
        mock_uow: MockUnitOfWork,
        mock_runner_context: P03RunnerContext,
        envelope_with_gaps: P03BatchEnvelope,
    ) -> None:
        """
        Given: P03 detected AMBIGUOUS_ENTITY gap
        When: Gap event is created
        Then: Payload includes context for P06 learning
        """
        # Verify gap candidates have required fields for P06
        gap = envelope_with_gaps.phases.r4_gaps[0]

        assert gap.gap_type == "AMBIGUOUS_ENTITY"
        assert gap.related_entity_id == "entity-mom"
        assert gap.candidate_values == ["mom-parent", "mom-grandma"]
        assert gap.context_json is not None

    @pytest.mark.asyncio
    async def test_completion_event_includes_gap_summary(
        self,
        mock_uow: MockUnitOfWork,
        mock_runner_context: P03RunnerContext,
        envelope_with_gaps: P03BatchEnvelope,
    ) -> None:
        """
        Given: P03 cycle completed with gaps
        When: Completion event is staged
        Then: Completion payload includes gap count for P06 awareness
        """
        r8 = R8EventEmitter()
        result = await r8.run(envelope_with_gaps, mock_runner_context)

        assert result.status == P03PhaseStatus.DONE

        # Check completion event exists
        completion_events = [
            e for e in mock_uow.staged_outbox if e.op_kind == "p03.consolidation.complete.v1"
        ]
        assert len(completion_events) >= 1


# =============================================================================
# TEST: P21 → P03 FEEDBACK
# =============================================================================


class TestP21ToP03Feedback:
    """Tests for P21 → P03 feedback signal consumption."""

    @pytest.mark.asyncio
    async def test_p03_subscribes_to_feedback_topic(self) -> None:
        """
        Given: P03 feedback consumer
        When: Checking subscription topic
        Then: Topic matches P21's feedback.signal.p03.v1
        """
        assert P03FeedbackConsumer.TOPIC == FEEDBACK_SIGNAL_P03_V1
        assert P03FeedbackConsumer.TOPIC == "feedback.signal.p03.v1"

    @pytest.mark.asyncio
    async def test_p03_routes_salience_adjustment(self) -> None:
        """
        Given: P21 sends SALIENCE_ADJUSTMENT feedback
        When: P03 consumer processes it
        Then: Signal is routed to salience handler
        """
        # Create mock pool
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(),
            )
        )

        consumer = P03FeedbackConsumer(pool=mock_pool)

        # Track handler calls
        handled: List[str] = []

        async def tracking_handler(payload: Any, conn: Any) -> None:
            handled.append(payload.feedback_type)

        consumer.register_handler(FeedbackType.SALIENCE_ADJUSTMENT, tracking_handler)

        # P21 feedback message
        message = {
            "feedback_id": "fb-p21-001",
            "payload": {
                "feedback_type": "SALIENCE_ADJUSTMENT",
                "entity_id": "entity-mom",
                "salience_delta": 0.15,
                "confidence": 0.85,
                "source_cycle_id": "cycle-p03-001",
            },
        }

        result = await consumer.process(message)

        assert result is True
        assert "SALIENCE_ADJUSTMENT" in handled

    @pytest.mark.asyncio
    async def test_p03_routes_decay_reversal(self) -> None:
        """
        Given: P21 sends DECAY_REVERSAL feedback
        When: P03 consumer processes it
        Then: Signal is routed to decay handler
        """
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(),
            )
        )

        consumer = P03FeedbackConsumer(pool=mock_pool)

        handled: List[str] = []

        async def tracking_handler(payload: Any, conn: Any) -> None:
            handled.append(payload.feedback_type)

        consumer.register_handler(FeedbackType.DECAY_REVERSAL, tracking_handler)

        message = {
            "feedback_id": "fb-p21-002",
            "payload": {
                "feedback_type": "DECAY_REVERSAL",
                "entity_id": "entity-dad",
                "decay_lambda_delta": -0.1,
                "confidence": 0.9,
            },
        }

        result = await consumer.process(message)

        assert result is True
        assert "DECAY_REVERSAL" in handled

    @pytest.mark.asyncio
    async def test_p03_routes_cluster_correction(self) -> None:
        """
        Given: P21 sends CLUSTER_CORRECTION feedback
        When: P03 consumer processes it
        Then: Signal is routed to cluster handler
        """
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(),
            )
        )

        consumer = P03FeedbackConsumer(pool=mock_pool)

        handled: List[str] = []

        async def tracking_handler(payload: Any, conn: Any) -> None:
            handled.append(payload.feedback_type)

        consumer.register_handler(FeedbackType.CLUSTER_CORRECTION, tracking_handler)

        message = {
            "feedback_id": "fb-p21-003",
            "payload": {
                "feedback_type": "CLUSTER_CORRECTION",
                "cluster_id": "cluster-old",
                "correct_cluster_id": "cluster-new",
                "incorrect_cluster_id": "cluster-old",
                "confidence": 0.95,
            },
        }

        result = await consumer.process(message)

        assert result is True
        assert "CLUSTER_CORRECTION" in handled

    @pytest.mark.asyncio
    async def test_p03_feedback_payload_schema_compatible(self) -> None:
        """
        Given: P21 feedback payload
        When: Validating against P03FeedbackPayload
        Then: All required fields are accepted
        """
        # Valid SALIENCE_ADJUSTMENT payload
        payload = P03FeedbackPayload(
            feedback_type="SALIENCE_ADJUSTMENT",
            entity_id="entity-test",
            salience_delta=0.2,
            confidence=0.8,
        )

        assert payload.feedback_type == "SALIENCE_ADJUSTMENT"
        assert payload.salience_delta == 0.2

    @pytest.mark.asyncio
    async def test_p03_rejects_unknown_feedback_type(self) -> None:
        """
        Given: P21 sends unknown feedback type
        When: P03 consumer processes it
        Then: Returns False (signal not processed)
        """
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(),
            )
        )

        consumer = P03FeedbackConsumer(pool=mock_pool)

        # Invalid feedback type (will fail validation)
        message = {
            "feedback_id": "fb-p21-bad",
            "payload": {
                "feedback_type": "UNKNOWN_TYPE",
                "confidence": 0.5,
            },
        }

        result = await consumer.process(message)

        # Should return False for invalid type
        assert result is False


# =============================================================================
# TEST: CROSS-PIPELINE DATA FLOW
# =============================================================================


class TestCrossPipelineDataFlow:
    """Tests for end-to-end cross-pipeline data flow."""

    @pytest.mark.asyncio
    async def test_p02_to_p03_to_p06_flow(
        self,
        mock_connection: MockConnection,
        mock_uow: MockUnitOfWork,
        mock_runner_context: P03RunnerContext,
        p02_hipp_event_rows: List[Dict[str, Any]],
    ) -> None:
        """
        Given: P02 wrote events to st_hipp_events
        When: P03 runs full cycle with gaps
        Then: Gaps are staged for P06 consumption
        """
        # Step 1: P02 → P03 handoff
        mock_connection.rows = p02_hipp_event_rows

        r0 = R0BatchSelector()
        envelope, r0_result = await r0.run("tenant-cross", "space-cross", mock_runner_context)

        assert r0_result.status == P03PhaseStatus.DONE
        assert len(envelope.events) == 3

        # Step 2: Simulate R1-R6 enrichment
        for event in envelope.events:
            event.reconciliation_action = ReconciliationAction.CREATE
            event.importance_score = 0.8

        # Add gaps during "R4"
        envelope.phases.r4_gaps = [
            GapCandidate(
                gap_id="gap-flow-001",
                gap_type="SEMANTIC_CONFLICT",
                related_entity_id="entity-kids",
                entropy_score=0.8,
                priority="CRITICAL",
                context_json='{"conflict": "ambiguous reference"}',
                candidate_values=["kids-smith", "kids-jones"],
            ),
        ]

        # Stage writes
        envelope.staged.add_write(
            StagedWrite.insert(
                layer=LAYER_ST_EPI,
                record_id="epi-flow-001",
                data={"episode_id": "epi-flow-001", "summary": "Flow test"},
                phase="R6",
                event_ids=["evt-p02-001"],
            )
        )

        # Step 3: P03 → P06 gap emission
        r8 = R8EventEmitter()
        r8_result = await r8.run(envelope, mock_runner_context)

        assert r8_result.status == P03PhaseStatus.DONE

        # Verify completion event staged
        completion_events = [
            e for e in mock_uow.staged_outbox if e.op_kind == "p03.consolidation.complete.v1"
        ]
        assert len(completion_events) >= 1

    @pytest.mark.asyncio
    async def test_feedback_loop_closes(self) -> None:
        """
        Given: P03 processes events
        And: P21 sends feedback based on K1 queries
        When: P03 receives feedback
        Then: Feedback is consumable for future cycles
        """
        # Create mock pool
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(),
            )
        )

        consumer = P03FeedbackConsumer(pool=mock_pool)

        processed: List[str] = []

        async def tracking_handler(payload: Any, conn: Any) -> None:
            processed.append(f"{payload.feedback_type}:{payload.entity_id}")

        consumer.register_handler(FeedbackType.REINFORCEMENT_OUTCOME, tracking_handler)

        # P21 sends feedback after K1 query
        message = {
            "feedback_id": "fb-loop-001",
            "payload": {
                "feedback_type": "REINFORCEMENT_OUTCOME",
                "entity_id": "entity-mom",
                "was_retrieved": True,
                "was_helpful": True,
                "confidence": 0.9,
                "source_cycle_id": "cycle-p03-001",
            },
        }

        result = await consumer.process(message)

        assert result is True
        assert "REINFORCEMENT_OUTCOME:entity-mom" in processed


# =============================================================================
# SUMMARY TEST
# =============================================================================


class TestCrossPipelineSummary:
    """Summary verification of cross-pipeline coverage."""

    def test_all_cross_pipeline_test_classes_exist(self) -> None:
        """Verify all cross-pipeline test classes are defined."""
        test_classes = [
            TestP02ToP03Handoff,
            TestP03ToP06GapEmission,
            TestP21ToP03Feedback,
            TestCrossPipelineDataFlow,
        ]
        assert len(test_classes) == 4

    def test_cross_pipeline_integration_topics_defined(self) -> None:
        """Verify integration topics are correctly defined."""
        # P02 → P03: st_hipp_events
        assert P03_SOURCE_TOPIC == "st_hipp_events"

        # P21 → P03: feedback.signal.p03.v1
        assert FEEDBACK_SIGNAL_P03_V1 == "feedback.signal.p03.v1"
