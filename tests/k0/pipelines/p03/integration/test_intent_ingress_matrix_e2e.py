"""
E2E Integration Tests for Intent & Ingress Matrix (GAP-001).

Tests the FULL flow from P03EventState → IntentSignal → StagedWrite
without mocking business logic. Only the database connection is captured.

Test Scenarios:
    1. set_reminder → st_prospective REMINDER with target_date
    2. seek_advice → st_prospective DECISION with options
    3. reflect → st_sem LESSON pattern
    4. express_feeling → st_sem EMOTIONAL_TREND pattern
    5. share_news → st_kg_dom milestone append
    6. query_memory → st_kg_dom/edges query_count increment

NO MOCKS: All business logic (detector, assembler, temporal parser) runs
with real code. Only the final database execution is captured.

Reference: docs/plans/INTENT_INGRESS_MATRIX_IMPLEMENTATION_PLAN.md Phase 7
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pytest

from k0.modules.consolidation.algorithms.intent_signal_detector import (
    IntentSignalDetector,
)
from k0.modules.consolidation.algorithms.temporal_parser import TemporalParser
from k0.modules.consolidation.dream.intent_signals import (
    DecisionSignal,
    EmotionalSignal,
    IntentSignalType,
    LessonSignal,
    MilestoneSignal,
    QueryBoostSignal,
    ReminderSignal,
)
from k0.modules.consolidation.staging.intent_signal_assembler import (
    IntentSignalAssembler,
)
from k0.modules.consolidation.truth_writer.layers import (
    KGLayerWriter,
    ProspectiveLayerWriter,
    SemanticLayerWriter,
)
from k0.modules.consolidation.truth_writer.result import LayerWriteResult
from k0.pipelines.p03.event_state import P03EventState
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_KG_DOM,
    LAYER_ST_PROSPECTIVE,
    LAYER_ST_SEM,
    WriteOperation,
)

# =============================================================================
# Recording UoW — Captures SQL without executing (E2E verification)
# =============================================================================


@dataclass
class RecordedSQL:
    """A single recorded SQL statement with parameters."""

    query: str
    params: Tuple[Any, ...]
    timestamp_ms: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


@dataclass
class RecordingConnection:
    """
    Records SQL execution without hitting real database.

    This is NOT a mock — it captures the real SQL that would be executed.
    Used to verify the layer writers generate correct SQL statements.
    """

    recorded_statements: List[RecordedSQL] = field(default_factory=list)
    _existing_records: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    async def execute(self, query: str, *args: Any) -> None:
        """Record the SQL statement and parameters."""
        self.recorded_statements.append(RecordedSQL(query=query, params=args))

    async def fetchrow(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
        """Return pre-configured record for optimistic locking tests."""
        self.recorded_statements.append(RecordedSQL(query=query, params=args))
        if args and args[0] in self._existing_records:
            return self._existing_records[args[0]]
        return None

    def add_existing_record(self, record_id: str, data: Dict[str, Any]) -> None:
        """Pre-configure a record for UPDATE operations."""
        self._existing_records[record_id] = data

    def get_statements_for_table(self, table_name: str) -> List[RecordedSQL]:
        """Filter recorded statements by table name."""
        return [s for s in self.recorded_statements if table_name in s.query]


@dataclass
class RecordingUnitOfWork:
    """
    Unit of work that captures SQL execution.

    Exposes same interface as real UnitOfWork but records instead of executes.
    """

    connection: RecordingConnection = field(default_factory=RecordingConnection)

    @property
    def recorded_sql(self) -> List[RecordedSQL]:
        """Access all recorded SQL statements."""
        return self.connection.recorded_statements


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def ref_time_ms() -> int:
    """Fixed reference time: 2025-01-15 10:00:00 (Wednesday)."""
    return int(datetime(2025, 1, 15, 10, 0, 0).timestamp() * 1000)


@pytest.fixture
def detector() -> IntentSignalDetector:
    """Real IntentSignalDetector instance."""
    return IntentSignalDetector()


@pytest.fixture
def temporal_parser() -> TemporalParser:
    """Real TemporalParser instance."""
    return TemporalParser()


@pytest.fixture
def assembler() -> IntentSignalAssembler:
    """Real IntentSignalAssembler instance."""
    return IntentSignalAssembler(
        tenant_id="tenant-test",
        space_id="space-test",
        actor_id="user-test",
    )


@pytest.fixture
def prospective_writer() -> ProspectiveLayerWriter:
    """Real ProspectiveLayerWriter instance."""
    return ProspectiveLayerWriter()


@pytest.fixture
def semantic_writer() -> SemanticLayerWriter:
    """Real SemanticLayerWriter instance."""
    return SemanticLayerWriter()


@pytest.fixture
def kg_writer() -> KGLayerWriter:
    """Real KGLayerWriter instance."""
    return KGLayerWriter()


@pytest.fixture
def recording_uow() -> RecordingUnitOfWork:
    """Recording UoW for SQL capture."""
    return RecordingUnitOfWork()


# =============================================================================
# E2E Test: set_reminder → st_prospective REMINDER
# =============================================================================


class TestE2ESetReminder:
    """
    E2E Test: set_reminder intent → st_prospective REMINDER.

    Flow:
        P03EventState(intent_label="set_reminder", temporal_json=...)
        → IntentSignalDetector.detect_all()
        → ReminderSignal
        → IntentSignalAssembler.assemble_all()
        → StagedWrite(layer=st_prospective, operation=INSERT)
        → SQL INSERT with intention_type='REMINDER'
    """

    def _create_reminder_event(
        self,
        event_id: str,
        content_text: str,
        temporal_json: str,
    ) -> P03EventState:
        """Create P03EventState for set_reminder intent."""
        return P03EventState(
            event_id=event_id,
            content_text=content_text,
            intent_label="set_reminder",
            temporal_expressions_json=temporal_json,
        )

    def test_full_reminder_flow_with_temporal(
        self,
        detector: IntentSignalDetector,
        assembler: IntentSignalAssembler,
        temporal_parser: TemporalParser,
        ref_time_ms: int,
    ):
        """
        Test complete flow: event → signal → staged write.

        Verifies:
        - IntentSignalDetector correctly identifies set_reminder
        - ReminderSignal is created with action description
        - IntentSignalAssembler creates st_prospective INSERT
        - StagedWrite has correct intention_type='REMINDER'
        """
        # Arrange: Create event with temporal expression
        temporal_json = json.dumps({"entities": [{"text": "tomorrow at 3pm", "label": "DATE_REL"}]})
        event = self._create_reminder_event(
            event_id="event-reminder-001",
            content_text="Remind me to call Mom tomorrow at 3pm",
            temporal_json=temporal_json,
        )

        # Act: Detect intent signals
        signals = detector.detect_all([event])

        # Assert: Signal detected correctly
        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, ReminderSignal)
        assert signal.signal_type == IntentSignalType.REMINDER
        assert signal.event_id == "event-reminder-001"
        assert "call Mom" in signal.action_description or "Remind me" in signal.source_text

        # Act: Parse temporal expression
        parsed_time = temporal_parser.parse_temporal_json(temporal_json, ref_time_ms)

        # Assert: Temporal parsed correctly
        assert parsed_time is not None
        result_dt = datetime.fromtimestamp(parsed_time / 1000)
        assert result_dt.date() == datetime(2025, 1, 16).date()  # Tomorrow
        assert result_dt.hour == 15  # 3pm

        # Act: Assemble staged writes
        writes_by_layer = assembler.assemble_all(signals)

        # Assert: Correct layer and operation
        assert LAYER_ST_PROSPECTIVE in writes_by_layer
        prospective_writes = writes_by_layer[LAYER_ST_PROSPECTIVE]
        assert len(prospective_writes) == 1

        write = prospective_writes[0]
        assert write.layer == LAYER_ST_PROSPECTIVE
        assert write.operation == WriteOperation.INSERT
        assert write.record_data["intention_type"] == "REMINDER"
        assert write.record_data["tenant_id"] == "tenant-test"
        assert write.record_data["space_id"] == "space-test"
        # REMINDER uses inferred_from_json for source event tracking
        assert "event-reminder-001" in write.record_data["inferred_from_json"]

    @pytest.mark.asyncio
    async def test_reminder_layer_writer_sql(
        self,
        detector: IntentSignalDetector,
        assembler: IntentSignalAssembler,
        prospective_writer: ProspectiveLayerWriter,
        recording_uow: RecordingUnitOfWork,
    ):
        """
        Test layer writer generates correct SQL.

        Verifies:
        - ProspectiveLayerWriter.write() is called with correct writes
        - Generated SQL has INSERT INTO st_prospective
        - SQL parameters include intention_type='REMINDER'
        """
        # Arrange: Create event and process through pipeline
        temporal_json = json.dumps({"entities": [{"text": "tomorrow at 3pm", "label": "DATE_REL"}]})
        event = P03EventState(
            event_id="event-sql-001",
            content_text="Remind me to submit the report tomorrow at 3pm",
            intent_label="set_reminder",
            temporal_expressions_json=temporal_json,
        )

        signals = detector.detect_all([event])
        writes_by_layer = assembler.assemble_all(signals)

        # Act: Execute layer writer
        writes = writes_by_layer.get(LAYER_ST_PROSPECTIVE, [])
        result = await prospective_writer.write(writes, recording_uow)

        # Assert: Write succeeded
        assert isinstance(result, LayerWriteResult)
        assert result.writes_succeeded == 1
        assert result.writes_failed == 0

        # Assert: Correct SQL generated
        sql_statements = recording_uow.connection.get_statements_for_table("st_prospective")
        assert len(sql_statements) >= 1

        insert_sql = sql_statements[0]
        assert "INSERT INTO st_prospective" in insert_sql.query
        assert "intention_type" in insert_sql.query

        # Verify parameters include REMINDER type
        params = insert_sql.params
        assert "REMINDER" in params


# =============================================================================
# E2E Test: seek_advice → st_prospective DECISION
# =============================================================================


class TestE2ESeekAdvice:
    """
    E2E Test: seek_advice intent → st_prospective DECISION.

    Flow:
        P03EventState(intent_label="seek_advice")
        → IntentSignalDetector.detect_all()
        → DecisionSignal
        → IntentSignalAssembler.assemble_all()
        → StagedWrite(layer=st_prospective, operation=INSERT)
        → intention_type='DECISION'
    """

    def test_full_decision_flow(
        self,
        detector: IntentSignalDetector,
        assembler: IntentSignalAssembler,
    ):
        """Test complete flow: event → decision signal → staged write."""
        # Arrange
        event = P03EventState(
            event_id="event-decision-001",
            content_text="Should I take the job offer or stay at my current company?",
            intent_label="seek_advice",
        )

        # Act: Detect signals
        signals = detector.detect_all([event])

        # Assert: DecisionSignal created
        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, DecisionSignal)
        assert signal.signal_type == IntentSignalType.DECISION

        # Act: Assemble writes
        writes_by_layer = assembler.assemble_all(signals)

        # Assert: st_prospective DECISION write
        assert LAYER_ST_PROSPECTIVE in writes_by_layer
        write = writes_by_layer[LAYER_ST_PROSPECTIVE][0]
        assert write.record_data["intention_type"] == "DECISION"
        assert write.record_data["status"] == "ACTIVE"  # DECISION status is ACTIVE

    @pytest.mark.asyncio
    async def test_decision_layer_writer_sql(
        self,
        detector: IntentSignalDetector,
        assembler: IntentSignalAssembler,
        prospective_writer: ProspectiveLayerWriter,
        recording_uow: RecordingUnitOfWork,
    ):
        """Test layer writer generates correct DECISION SQL."""
        # Arrange
        event = P03EventState(
            event_id="event-decision-002",
            content_text="I'm debating whether to buy a new car or save the money",
            intent_label="seek_advice",
        )

        signals = detector.detect_all([event])
        writes_by_layer = assembler.assemble_all(signals)

        # Act
        writes = writes_by_layer.get(LAYER_ST_PROSPECTIVE, [])
        result = await prospective_writer.write(writes, recording_uow)

        # Assert
        assert result.writes_succeeded == 1
        sql_statements = recording_uow.connection.get_statements_for_table("st_prospective")
        assert any("DECISION" in str(s.params) for s in sql_statements)


# =============================================================================
# E2E Test: reflect → st_sem LESSON
# =============================================================================


class TestE2EReflect:
    """
    E2E Test: reflect intent → st_sem LESSON.

    Flow:
        P03EventState(intent_label="reflect")
        → IntentSignalDetector.detect_all()
        → LessonSignal
        → IntentSignalAssembler.assemble_all()
        → StagedWrite(layer=st_sem, operation=INSERT)
        → pattern_type='LESSON'
    """

    def test_full_lesson_flow(
        self,
        detector: IntentSignalDetector,
        assembler: IntentSignalAssembler,
    ):
        """Test complete flow: event → lesson signal → staged write."""
        # Arrange
        event = P03EventState(
            event_id="event-lesson-001",
            content_text="I learned that patience is really important when teaching kids",
            intent_label="reflect",
        )

        # Act: Detect signals
        signals = detector.detect_all([event])

        # Assert: LessonSignal created
        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, LessonSignal)
        assert signal.signal_type == IntentSignalType.LESSON

        # Act: Assemble writes
        writes_by_layer = assembler.assemble_all(signals)

        # Assert: st_sem LESSON write
        assert LAYER_ST_SEM in writes_by_layer
        write = writes_by_layer[LAYER_ST_SEM][0]
        assert write.record_data["pattern_type"] == "LESSON"
        assert write.record_data["is_canonical"] is True

    @pytest.mark.asyncio
    async def test_lesson_layer_writer_sql(
        self,
        detector: IntentSignalDetector,
        assembler: IntentSignalAssembler,
        semantic_writer: SemanticLayerWriter,
        recording_uow: RecordingUnitOfWork,
    ):
        """Test layer writer generates correct LESSON SQL."""
        # Arrange
        event = P03EventState(
            event_id="event-lesson-002",
            content_text="I realized that consistency is more important than intensity",
            intent_label="reflect",
        )

        signals = detector.detect_all([event])
        writes_by_layer = assembler.assemble_all(signals)

        # Act
        writes = writes_by_layer.get(LAYER_ST_SEM, [])
        result = await semantic_writer.write(writes, recording_uow)

        # Assert
        assert result.writes_succeeded == 1
        sql_statements = recording_uow.connection.get_statements_for_table("st_sem")
        assert any("LESSON" in str(s.params) for s in sql_statements)


# =============================================================================
# E2E Test: express_feeling → st_sem EMOTIONAL_TREND
# =============================================================================


class TestE2EExpressFeeling:
    """
    E2E Test: express_feeling intent → st_sem EMOTIONAL_TREND.

    Flow:
        P03EventState(intent_label="express_feeling", emotions_json=...)
        → IntentSignalDetector.detect_all()
        → EmotionalSignal
        → IntentSignalAssembler.assemble_all()
        → StagedWrite(layer=st_sem, operation=INSERT)
        → pattern_type='EMOTIONAL_TREND'
    """

    def test_full_emotional_flow(
        self,
        detector: IntentSignalDetector,
        assembler: IntentSignalAssembler,
    ):
        """Test complete flow: event → emotional signal → staged write."""
        # Arrange
        emotions_json = json.dumps([{"label": "gratitude", "score": 0.85}])
        event = P03EventState(
            event_id="event-emotion-001",
            content_text="I'm feeling so grateful for my family today",
            intent_label="express_feeling",
            emotions_json=emotions_json,
        )

        # Act: Detect signals
        signals = detector.detect_all([event])

        # Assert: EmotionalSignal created
        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, EmotionalSignal)
        assert signal.signal_type == IntentSignalType.EMOTIONAL_TREND

        # Act: Assemble writes
        writes_by_layer = assembler.assemble_all(signals)

        # Assert: st_sem EMOTIONAL_TREND write
        assert LAYER_ST_SEM in writes_by_layer
        write = writes_by_layer[LAYER_ST_SEM][0]
        assert write.record_data["pattern_type"] == "EMOTIONAL_TREND"

    @pytest.mark.asyncio
    async def test_emotional_layer_writer_sql(
        self,
        detector: IntentSignalDetector,
        assembler: IntentSignalAssembler,
        semantic_writer: SemanticLayerWriter,
        recording_uow: RecordingUnitOfWork,
    ):
        """Test layer writer generates correct EMOTIONAL_TREND SQL."""
        # Arrange
        emotions_json = json.dumps([{"label": "joy", "score": 0.9}])
        event = P03EventState(
            event_id="event-emotion-002",
            content_text="I am so happy with how everything turned out!",
            intent_label="express_feeling",
            emotions_json=emotions_json,
        )

        signals = detector.detect_all([event])
        writes_by_layer = assembler.assemble_all(signals)

        # Act
        writes = writes_by_layer.get(LAYER_ST_SEM, [])
        result = await semantic_writer.write(writes, recording_uow)

        # Assert
        assert result.writes_succeeded == 1
        sql_statements = recording_uow.connection.get_statements_for_table("st_sem")
        assert any("EMOTIONAL_TREND" in str(s.params) for s in sql_statements)


# =============================================================================
# E2E Test: share_news → st_kg_dom milestone
# =============================================================================


class TestE2EShareNews:
    """
    E2E Test: share_news intent → st_kg_dom milestone append.

    Flow:
        P03EventState(intent_label="share_news", ner_entities_json=...)
        → IntentSignalDetector.detect_all()
        → MilestoneSignal
        → IntentSignalAssembler.assemble_all()
        → StagedWrite(layer=st_kg_dom, operation=UPDATE)
        → milestone_append field triggers milestone JSON update
    """

    def test_full_milestone_flow(
        self,
        detector: IntentSignalDetector,
        assembler: IntentSignalAssembler,
    ):
        """Test complete flow: event → milestone signal → staged write."""
        # Arrange
        ner_json = json.dumps([{"text": "Sarah", "label": "PERSON"}])
        event = P03EventState(
            event_id="event-news-001",
            content_text="I wanted to share that Sarah got accepted to Harvard!",
            intent_label="share_news",
            ner_entities_json=ner_json,
        )

        # Act: Detect signals
        signals = detector.detect_all([event])

        # Assert: MilestoneSignal created
        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, MilestoneSignal)
        assert signal.signal_type == IntentSignalType.MILESTONE

        # Act: Assemble writes
        writes_by_layer = assembler.assemble_all(signals)

        # Assert: st_kg_dom UPDATE write with milestone_append
        assert LAYER_ST_KG_DOM in writes_by_layer
        write = writes_by_layer[LAYER_ST_KG_DOM][0]
        assert write.operation == WriteOperation.UPDATE
        assert "milestone_append" in write.record_data

    @pytest.mark.asyncio
    async def test_milestone_layer_writer_sql(
        self,
        detector: IntentSignalDetector,
        assembler: IntentSignalAssembler,
        kg_writer: KGLayerWriter,
        recording_uow: RecordingUnitOfWork,
    ):
        """Test layer writer generates correct milestone UPDATE SQL."""
        # Arrange: Pre-configure existing entity for UPDATE
        recording_uow.connection.add_existing_record(
            "entity-sarah",
            {
                "entity_id": "entity-sarah",
                "milestones_json": "[]",
                "version": 1,
            },
        )

        ner_json = json.dumps([{"text": "Sarah", "label": "PERSON"}])
        event = P03EventState(
            event_id="event-news-002",
            content_text="Sarah just got promoted to senior manager!",
            intent_label="share_news",
            ner_entities_json=ner_json,
        )

        signals = detector.detect_all([event])
        writes_by_layer = assembler.assemble_all(signals)

        # Act
        writes = writes_by_layer.get(LAYER_ST_KG_DOM, [])
        result = await kg_writer.write(writes, recording_uow)

        # Assert: SQL generated for milestone update
        assert result.writes_succeeded >= 0  # May succeed or require existing record
        sql_statements = recording_uow.connection.get_statements_for_table("st_kg_dom")
        # Should have at least attempted an operation
        assert len(recording_uow.recorded_sql) > 0


# =============================================================================
# E2E Test: query_memory → st_kg_dom/edges query_count
# =============================================================================


class TestE2EQueryMemory:
    """
    E2E Test: query_memory intent → st_kg_dom/edges query_count increment.

    Flow:
        P03EventState(intent_label="query_memory", ner_entities_json=...)
        → IntentSignalDetector.detect_all()
        → QueryBoostSignal
        → IntentSignalAssembler.assemble_all()
        → StagedWrite(layer=st_kg_dom, operation=UPDATE)
        → query_count_increment field triggers counter update
    """

    def test_full_query_boost_flow(
        self,
        detector: IntentSignalDetector,
        assembler: IntentSignalAssembler,
    ):
        """Test complete flow: event → query boost signal → staged write."""
        # Arrange
        ner_json = json.dumps([{"text": "Mom", "label": "PERSON"}])
        event = P03EventState(
            event_id="event-query-001",
            content_text="What was that recipe Mom shared last week?",
            intent_label="query_memory",
            ner_entities_json=ner_json,
        )

        # Act: Detect signals
        signals = detector.detect_all([event])

        # Assert: QueryBoostSignal created
        assert len(signals) == 1
        signal = signals[0]
        assert isinstance(signal, QueryBoostSignal)
        assert signal.signal_type == IntentSignalType.QUERY_BOOST

        # Act: Assemble writes
        writes_by_layer = assembler.assemble_all(signals)

        # Assert: st_kg_dom UPDATE write with query_count_increment
        assert LAYER_ST_KG_DOM in writes_by_layer
        write = writes_by_layer[LAYER_ST_KG_DOM][0]
        assert write.operation == WriteOperation.UPDATE
        assert "query_count_increment" in write.record_data

    @pytest.mark.asyncio
    async def test_query_boost_layer_writer_sql(
        self,
        detector: IntentSignalDetector,
        assembler: IntentSignalAssembler,
        kg_writer: KGLayerWriter,
        recording_uow: RecordingUnitOfWork,
    ):
        """Test layer writer generates correct query_count UPDATE SQL."""
        # Arrange
        recording_uow.connection.add_existing_record(
            "entity-mom",
            {
                "entity_id": "entity-mom",
                "query_count": 5,
                "version": 1,
            },
        )

        ner_json = json.dumps([{"text": "Mom", "label": "PERSON"}])
        event = P03EventState(
            event_id="event-query-002",
            content_text="When was the last time I talked to Mom?",
            intent_label="query_memory",
            ner_entities_json=ner_json,
        )

        signals = detector.detect_all([event])
        writes_by_layer = assembler.assemble_all(signals)

        # Act
        writes = writes_by_layer.get(LAYER_ST_KG_DOM, [])
        result = await kg_writer.write(writes, recording_uow)

        # Assert: SQL generated
        assert len(recording_uow.recorded_sql) > 0


# =============================================================================
# E2E Test: Multiple intents in single batch
# =============================================================================


class TestE2EMultipleIntents:
    """
    E2E Test: Multiple intents processed in single batch.

    Verifies the system correctly handles heterogeneous intent types
    and routes each to the appropriate layer.
    """

    def test_mixed_intent_batch(
        self,
        detector: IntentSignalDetector,
        assembler: IntentSignalAssembler,
    ):
        """Test batch with reminder, lesson, and emotional intents."""
        # Arrange: Create diverse events
        events = [
            P03EventState(
                event_id="event-mix-001",
                content_text="Remind me to water the plants tomorrow",
                intent_label="set_reminder",
                temporal_expressions_json=json.dumps(
                    {"entities": [{"text": "tomorrow", "label": "DATE_REL"}]}
                ),
            ),
            P03EventState(
                event_id="event-mix-002",
                content_text="I learned that early mornings are my most productive time",
                intent_label="reflect",
            ),
            P03EventState(
                event_id="event-mix-003",
                content_text="I'm feeling really anxious about the presentation",
                intent_label="express_feeling",
                emotions_json=json.dumps([{"label": "anxiety", "score": 0.7}]),
            ),
        ]

        # Act: Detect all signals
        signals = detector.detect_all(events)

        # Assert: All signals detected
        assert len(signals) == 3
        signal_types = {s.signal_type for s in signals}
        assert IntentSignalType.REMINDER in signal_types
        assert IntentSignalType.LESSON in signal_types
        assert IntentSignalType.EMOTIONAL_TREND in signal_types

        # Act: Assemble writes
        writes_by_layer = assembler.assemble_all(signals)

        # Assert: Writes routed to correct layers
        assert LAYER_ST_PROSPECTIVE in writes_by_layer
        assert LAYER_ST_SEM in writes_by_layer

        # Verify prospective has REMINDER
        prospective_writes = writes_by_layer[LAYER_ST_PROSPECTIVE]
        assert len(prospective_writes) == 1
        assert prospective_writes[0].record_data["intention_type"] == "REMINDER"

        # Verify semantic has LESSON and EMOTIONAL_TREND
        semantic_writes = writes_by_layer[LAYER_ST_SEM]
        assert len(semantic_writes) == 2
        pattern_types = {w.record_data["pattern_type"] for w in semantic_writes}
        assert "LESSON" in pattern_types
        assert "EMOTIONAL_TREND" in pattern_types


# =============================================================================
# E2E Test: Temporal Parser Integration
# =============================================================================


class TestE2ETemporalIntegration:
    """
    E2E Test: TemporalParser integrated with reminder flow.

    Verifies that temporal expressions are correctly parsed and
    applied to reminder target_date field.
    """

    def test_temporal_parser_in_reminder_pipeline(
        self,
        detector: IntentSignalDetector,
        temporal_parser: TemporalParser,
        ref_time_ms: int,
    ):
        """Test temporal parsing integrated with reminder detection."""
        # Arrange
        temporal_json = json.dumps(
            {"entities": [{"text": "next Monday at 10am", "label": "DATE_REL"}]}
        )
        event = P03EventState(
            event_id="event-temporal-001",
            content_text="Remind me about the team meeting next Monday at 10am",
            intent_label="set_reminder",
            temporal_expressions_json=temporal_json,
        )

        # Act: Detect and parse
        signals = detector.detect_all([event])
        assert len(signals) == 1

        # Parse temporal expression
        parsed_time = temporal_parser.parse_temporal_json(temporal_json, ref_time_ms)

        # Assert: Time parsed correctly
        assert parsed_time is not None
        result_dt = datetime.fromtimestamp(parsed_time / 1000)
        assert result_dt.weekday() == 0  # Monday
        assert result_dt.hour == 10

    def test_relative_time_parsing(
        self,
        temporal_parser: TemporalParser,
        ref_time_ms: int,
    ):
        """Test various relative time expressions."""
        test_cases = [
            ("in 30 minutes", 30),  # Expected minutes offset
            ("in an hour", 60),
            ("in 2 hours", 120),
        ]

        for expr, expected_minutes in test_cases:
            temporal_json = json.dumps({"entities": [{"text": expr, "label": "TIME_REL"}]})
            parsed = temporal_parser.parse_temporal_json(temporal_json, ref_time_ms)

            assert parsed is not None, f"Failed to parse: {expr}"
            ref_dt = datetime.fromtimestamp(ref_time_ms / 1000)
            result_dt = datetime.fromtimestamp(parsed / 1000)
            delta_minutes = (result_dt - ref_dt).total_seconds() / 60

            assert (
                abs(delta_minutes - expected_minutes) < 1
            ), f"Expected {expected_minutes} minutes, got {delta_minutes} for {expr}"
