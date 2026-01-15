"""
Tests for IntentSignalAssembler — GAP-001 Phase 4

Tests the routing of intent signals to appropriate layer writes.
"""

import json
from typing import List

import pytest

from k0.modules.consolidation.dream.intent_signals import (
    DecisionSignal,
    EmotionalSignal,
    IntentSignal,
    IntentSignalType,
    LessonSignal,
    MilestoneSignal,
    MilestoneType,
    QueryBoostSignal,
    ReminderSignal,
)
from k0.modules.consolidation.staging.intent_signal_assembler import (
    IntentSignalAssembler,
    assemble_intent_signal_writes,
)
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_KG_DOM,
    LAYER_ST_KG_EDGES,
    LAYER_ST_PROSPECTIVE,
    LAYER_ST_SEM,
    WriteOperation,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def assembler() -> IntentSignalAssembler:
    """Create IntentSignalAssembler with test context."""
    return IntentSignalAssembler(
        tenant_id="test-tenant",
        space_id="test-space",
        actor_id="test-actor",
    )


@pytest.fixture
def sample_reminder_signal() -> ReminderSignal:
    """Create sample ReminderSignal."""
    return ReminderSignal(
        signal_type=IntentSignalType.REMINDER,
        event_id="evt_001",
        confidence=0.9,
        source_text="Remind me to call mom tomorrow at 3pm",
        action_description="call mom",
        target_date=1736726400000,
    )


@pytest.fixture
def sample_decision_signal() -> DecisionSignal:
    """Create sample DecisionSignal."""
    return DecisionSignal(
        signal_type=IntentSignalType.DECISION,
        event_id="evt_002",
        confidence=0.85,
        source_text="Should we go to the beach or the mountains this weekend?",
        decision_context="weekend destination choice",
        options_mentioned=["beach", "mountains"],
    )


@pytest.fixture
def sample_lesson_signal() -> LessonSignal:
    """Create sample LessonSignal."""
    return LessonSignal(
        signal_type=IntentSignalType.LESSON,
        event_id="evt_003",
        confidence=0.75,
        source_text="I learned that adding salt early makes pasta taste better",
        lesson_description="adding salt early makes pasta taste better",
        topic_entities=["cooking", "pasta"],
    )


@pytest.fixture
def sample_emotional_signal() -> EmotionalSignal:
    """Create sample EmotionalSignal."""
    return EmotionalSignal(
        signal_type=IntentSignalType.EMOTIONAL_TREND,
        event_id="evt_004",
        confidence=0.8,
        source_text="I'm so happy about the new job offer!",
        emotion_label="happy",
        intensity=0.9,
        target_entities=["job", "career"],
    )


@pytest.fixture
def sample_milestone_signal() -> MilestoneSignal:
    """Create sample MilestoneSignal."""
    return MilestoneSignal(
        signal_type=IntentSignalType.MILESTONE,
        event_id="evt_005",
        confidence=0.95,
        source_text="Today is Sarah's 5th birthday!",
        milestone_type=MilestoneType.CELEBRATION,  # Birthday is CELEBRATION
        entity_id="entity_sarah",
        milestone_description="5th birthday",
    )


@pytest.fixture
def sample_query_boost_signal() -> QueryBoostSignal:
    """Create sample QueryBoostSignal."""
    return QueryBoostSignal(
        signal_type=IntentSignalType.QUERY_BOOST,
        event_id="evt_006",
        confidence=0.8,
        source_text="When did we visit grandma last?",
        entity_ids=["entity_grandma"],
        edge_ids=["edge_visit_grandma_001"],
    )


# =============================================================================
# TEST: IntentSignalAssembler Initialization
# =============================================================================


class TestIntentSignalAssemblerInit:
    """Tests for IntentSignalAssembler initialization."""

    def test_init_sets_context(self) -> None:
        """Assembler stores tenant, space, and actor IDs."""
        assembler = IntentSignalAssembler(
            tenant_id="t1",
            space_id="s1",
            actor_id="a1",
        )

        assert assembler.tenant_id == "t1"
        assert assembler.space_id == "s1"
        assert assembler.actor_id == "a1"

    def test_source_phase_constant(self) -> None:
        """Assembler has SOURCE_PHASE constant for provenance."""
        assert IntentSignalAssembler.SOURCE_PHASE == "R6_INTENT"


# =============================================================================
# TEST: assemble_all
# =============================================================================


class TestAssembleAll:
    """Tests for assemble_all method."""

    def test_empty_signals_returns_empty_dict(
        self,
        assembler: IntentSignalAssembler,
    ) -> None:
        """Empty signal list returns empty dict."""
        result = assembler.assemble_all([])
        assert result == {}

    def test_single_reminder_routes_to_prospective(
        self,
        assembler: IntentSignalAssembler,
        sample_reminder_signal: ReminderSignal,
    ) -> None:
        """ReminderSignal routes to st_prospective layer."""
        result = assembler.assemble_all([sample_reminder_signal])

        assert LAYER_ST_PROSPECTIVE in result
        assert len(result[LAYER_ST_PROSPECTIVE]) == 1

        write = result[LAYER_ST_PROSPECTIVE][0]
        assert write.layer == LAYER_ST_PROSPECTIVE
        assert write.operation == WriteOperation.INSERT
        assert "REMINDER" in str(write.record_data.get("intention_type", ""))

    def test_single_decision_routes_to_prospective(
        self,
        assembler: IntentSignalAssembler,
        sample_decision_signal: DecisionSignal,
    ) -> None:
        """DecisionSignal routes to st_prospective layer."""
        result = assembler.assemble_all([sample_decision_signal])

        assert LAYER_ST_PROSPECTIVE in result
        assert len(result[LAYER_ST_PROSPECTIVE]) == 1

        write = result[LAYER_ST_PROSPECTIVE][0]
        assert write.operation == WriteOperation.INSERT
        assert "DECISION" in str(write.record_data.get("intention_type", ""))

    def test_single_lesson_routes_to_sem(
        self,
        assembler: IntentSignalAssembler,
        sample_lesson_signal: LessonSignal,
    ) -> None:
        """LessonSignal routes to st_sem layer."""
        result = assembler.assemble_all([sample_lesson_signal])

        assert LAYER_ST_SEM in result
        assert len(result[LAYER_ST_SEM]) == 1

        write = result[LAYER_ST_SEM][0]
        assert write.layer == LAYER_ST_SEM
        assert write.operation == WriteOperation.INSERT
        assert "LESSON" in str(write.record_data.get("pattern_type", ""))

    def test_single_emotional_routes_to_sem(
        self,
        assembler: IntentSignalAssembler,
        sample_emotional_signal: EmotionalSignal,
    ) -> None:
        """EmotionalSignal routes to st_sem layer."""
        result = assembler.assemble_all([sample_emotional_signal])

        assert LAYER_ST_SEM in result
        assert len(result[LAYER_ST_SEM]) == 1

        write = result[LAYER_ST_SEM][0]
        assert "EMOTIONAL_TREND" in str(write.record_data.get("pattern_type", ""))

    def test_single_milestone_routes_to_kg_dom(
        self,
        assembler: IntentSignalAssembler,
        sample_milestone_signal: MilestoneSignal,
    ) -> None:
        """MilestoneSignal routes to st_kg_dom layer."""
        result = assembler.assemble_all([sample_milestone_signal])

        assert LAYER_ST_KG_DOM in result
        assert len(result[LAYER_ST_KG_DOM]) == 1

        write = result[LAYER_ST_KG_DOM][0]
        assert write.layer == LAYER_ST_KG_DOM
        assert write.operation == WriteOperation.UPDATE

    def test_query_boost_routes_to_kg_dom_and_edges(
        self,
        assembler: IntentSignalAssembler,
        sample_query_boost_signal: QueryBoostSignal,
    ) -> None:
        """QueryBoostSignal routes to st_kg_dom AND st_kg_edges."""
        result = assembler.assemble_all([sample_query_boost_signal])

        # Should have both layers
        assert LAYER_ST_KG_DOM in result
        assert LAYER_ST_KG_EDGES in result

        # One entity, one edge
        assert len(result[LAYER_ST_KG_DOM]) == 1
        assert len(result[LAYER_ST_KG_EDGES]) == 1

        # Both should be UPDATE operations
        for write in result[LAYER_ST_KG_DOM]:
            assert write.operation == WriteOperation.UPDATE
        for write in result[LAYER_ST_KG_EDGES]:
            assert write.operation == WriteOperation.UPDATE

    def test_mixed_signals_route_correctly(
        self,
        assembler: IntentSignalAssembler,
        sample_reminder_signal: ReminderSignal,
        sample_lesson_signal: LessonSignal,
        sample_milestone_signal: MilestoneSignal,
    ) -> None:
        """Multiple signals of different types route to correct layers."""
        signals: List[IntentSignal] = [
            sample_reminder_signal,  # -> st_prospective
            sample_lesson_signal,  # -> st_sem
            sample_milestone_signal,  # -> st_kg_dom
        ]

        result = assembler.assemble_all(signals)

        assert LAYER_ST_PROSPECTIVE in result
        assert LAYER_ST_SEM in result
        assert LAYER_ST_KG_DOM in result

        assert len(result[LAYER_ST_PROSPECTIVE]) == 1
        assert len(result[LAYER_ST_SEM]) == 1
        assert len(result[LAYER_ST_KG_DOM]) == 1


# =============================================================================
# TEST: ReminderSignal Assembly
# =============================================================================


class TestReminderAssembly:
    """Tests for ReminderSignal -> st_prospective assembly."""

    def test_reminder_record_has_required_fields(
        self,
        assembler: IntentSignalAssembler,
        sample_reminder_signal: ReminderSignal,
    ) -> None:
        """Reminder write has all required st_prospective fields matching layer writer."""
        result = assembler.assemble_all([sample_reminder_signal])
        write = result[LAYER_ST_PROSPECTIVE][0]

        # Check required fields (aligned with ProspectiveLayerWriter expectations)
        assert "intention_id" in write.record_data
        assert "tenant_id" in write.record_data
        assert "space_id" in write.record_data
        assert "intention_type" in write.record_data
        assert "description" in write.record_data  # Was intention_description
        assert "trigger_time_ms" in write.record_data  # Was target_date
        assert "trigger_context_json" in write.record_data
        assert "confidence" in write.record_data  # Was confidence_score
        assert "source_episodes_json" in write.record_data
        assert "created_at" in write.record_data

    def test_reminder_includes_source_event_in_episodes(
        self,
        assembler: IntentSignalAssembler,
        sample_reminder_signal: ReminderSignal,
    ) -> None:
        """Reminder write includes source event in source_episodes_json."""
        result = assembler.assemble_all([sample_reminder_signal])
        write = result[LAYER_ST_PROSPECTIVE][0]

        episodes = json.loads(write.record_data["source_episodes_json"])
        assert "evt_001" in episodes
        assert write.source_event_ids == ["evt_001"]

    def test_reminder_intention_type_is_reminder(
        self,
        assembler: IntentSignalAssembler,
        sample_reminder_signal: ReminderSignal,
    ) -> None:
        """Reminder write has intention_type='REMINDER'."""
        result = assembler.assemble_all([sample_reminder_signal])
        write = result[LAYER_ST_PROSPECTIVE][0]

        assert write.record_data["intention_type"] == "REMINDER"


# =============================================================================
# TEST: DecisionSignal Assembly
# =============================================================================


class TestDecisionAssembly:
    """Tests for DecisionSignal -> st_prospective assembly."""

    def test_decision_includes_options_in_goal_inference(
        self,
        assembler: IntentSignalAssembler,
        sample_decision_signal: DecisionSignal,
    ) -> None:
        """Decision write includes options_mentioned in goal_inference_json."""
        result = assembler.assemble_all([sample_decision_signal])
        write = result[LAYER_ST_PROSPECTIVE][0]

        goal_inference = json.loads(write.record_data.get("goal_inference_json", "{}"))
        options = goal_inference.get("decision_options", [])

        assert "beach" in options
        assert "mountains" in options

    def test_decision_status_is_pending(
        self,
        assembler: IntentSignalAssembler,
        sample_decision_signal: DecisionSignal,
    ) -> None:
        """Decision write has status='pending' (lowercase for layer writer)."""
        result = assembler.assemble_all([sample_decision_signal])
        write = result[LAYER_ST_PROSPECTIVE][0]

        assert write.record_data["status"] == "pending"


# =============================================================================
# TEST: LessonSignal Assembly
# =============================================================================


class TestLessonAssembly:
    """Tests for LessonSignal -> st_sem assembly."""

    def test_lesson_record_has_pattern_fields(
        self,
        assembler: IntentSignalAssembler,
        sample_lesson_signal: LessonSignal,
    ) -> None:
        """Lesson write has required st_sem pattern fields matching layer writer."""
        result = assembler.assemble_all([sample_lesson_signal])
        write = result[LAYER_ST_SEM][0]

        # Fields aligned with st_sem schema
        assert "pattern_id" in write.record_data
        assert "pattern_type" in write.record_data
        assert "pattern_name" in write.record_data
        assert "source_episodes_json" in write.record_data
        assert "source_episode_count" in write.record_data
        assert "observation_count" in write.record_data
        assert "confidence_score" in write.record_data

    def test_lesson_pattern_type_is_lesson(
        self,
        assembler: IntentSignalAssembler,
        sample_lesson_signal: LessonSignal,
    ) -> None:
        """Lesson write has pattern_type='LESSON'."""
        result = assembler.assemble_all([sample_lesson_signal])
        write = result[LAYER_ST_SEM][0]

        assert write.record_data["pattern_type"] == "LESSON"

    def test_lesson_includes_source_episodes(
        self,
        assembler: IntentSignalAssembler,
        sample_lesson_signal: LessonSignal,
    ) -> None:
        """Lesson write includes source event in source_episodes_json."""
        result = assembler.assemble_all([sample_lesson_signal])
        write = result[LAYER_ST_SEM][0]

        episodes = json.loads(write.record_data["source_episodes_json"])
        assert "evt_003" in episodes


# =============================================================================
# TEST: EmotionalSignal Assembly
# =============================================================================


class TestEmotionalAssembly:
    """Tests for EmotionalSignal -> st_sem assembly."""

    def test_emotional_pattern_type(
        self,
        assembler: IntentSignalAssembler,
        sample_emotional_signal: EmotionalSignal,
    ) -> None:
        """Emotional write has pattern_type='EMOTIONAL_TREND'."""
        result = assembler.assemble_all([sample_emotional_signal])
        write = result[LAYER_ST_SEM][0]

        assert write.record_data["pattern_type"] == "EMOTIONAL_TREND"

    def test_emotional_includes_pattern_name(
        self,
        assembler: IntentSignalAssembler,
        sample_emotional_signal: EmotionalSignal,
    ) -> None:
        """Emotional write includes descriptive pattern_name."""
        result = assembler.assemble_all([sample_emotional_signal])
        write = result[LAYER_ST_SEM][0]

        pattern_name = write.record_data["pattern_name"]
        assert "happy" in pattern_name
        assert "emotional pattern" in pattern_name


# =============================================================================
# TEST: MilestoneSignal Assembly
# =============================================================================


class TestMilestoneAssembly:
    """Tests for MilestoneSignal -> st_kg_dom assembly."""

    def test_milestone_creates_update_operation(
        self,
        assembler: IntentSignalAssembler,
        sample_milestone_signal: MilestoneSignal,
    ) -> None:
        """Milestone creates UPDATE (append to milestones_json)."""
        result = assembler.assemble_all([sample_milestone_signal])
        write = result[LAYER_ST_KG_DOM][0]

        assert write.operation == WriteOperation.UPDATE

    def test_milestone_includes_append_entry(
        self,
        assembler: IntentSignalAssembler,
        sample_milestone_signal: MilestoneSignal,
    ) -> None:
        """Milestone write includes milestone_append entry."""
        result = assembler.assemble_all([sample_milestone_signal])
        write = result[LAYER_ST_KG_DOM][0]

        milestone = write.record_data.get("milestone_append", {})
        assert milestone["milestone_type"] == "CELEBRATION"
        assert "5th birthday" in milestone["description"]

    def test_milestone_without_entity_id_returns_empty(
        self,
        assembler: IntentSignalAssembler,
    ) -> None:
        """Milestone without entity_id produces no writes."""
        signal = MilestoneSignal(
            signal_type=IntentSignalType.MILESTONE,
            event_id="evt_010",
            confidence=0.9,
            source_text="Some milestone",
            milestone_type=MilestoneType.ACHIEVEMENT,
            entity_id="",  # Empty entity_id
        )

        result = assembler.assemble_all([signal])
        assert result == {}


# =============================================================================
# TEST: QueryBoostSignal Assembly
# =============================================================================


class TestQueryBoostAssembly:
    """Tests for QueryBoostSignal -> st_kg_dom/st_kg_edges assembly."""

    def test_query_boost_creates_entity_updates(
        self,
        assembler: IntentSignalAssembler,
    ) -> None:
        """Query boost creates UPDATE for each entity_id."""
        signal = QueryBoostSignal(
            signal_type=IntentSignalType.QUERY_BOOST,
            event_id="evt_020",
            confidence=0.8,
            source_text="query",
            entity_ids=["ent_1", "ent_2", "ent_3"],
            edge_ids=[],
        )

        result = assembler.assemble_all([signal])

        assert LAYER_ST_KG_DOM in result
        assert len(result[LAYER_ST_KG_DOM]) == 3

        for write in result[LAYER_ST_KG_DOM]:
            assert write.operation == WriteOperation.UPDATE
            assert "query_count_increment" in write.record_data
            assert write.record_data["query_count_increment"] == 1

    def test_query_boost_creates_edge_updates(
        self,
        assembler: IntentSignalAssembler,
    ) -> None:
        """Query boost creates UPDATE for each edge_id."""
        signal = QueryBoostSignal(
            signal_type=IntentSignalType.QUERY_BOOST,
            event_id="evt_021",
            confidence=0.8,
            source_text="query",
            entity_ids=[],
            edge_ids=["edge_1", "edge_2"],
        )

        result = assembler.assemble_all([signal])

        assert LAYER_ST_KG_EDGES in result
        assert len(result[LAYER_ST_KG_EDGES]) == 2

        for write in result[LAYER_ST_KG_EDGES]:
            assert write.operation == WriteOperation.UPDATE
            assert "query_count_increment" in write.record_data

    def test_query_boost_updates_last_queried_at(
        self,
        assembler: IntentSignalAssembler,
        sample_query_boost_signal: QueryBoostSignal,
    ) -> None:
        """Query boost updates last_queried_at timestamp."""
        result = assembler.assemble_all([sample_query_boost_signal])

        for layer_writes in result.values():
            for write in layer_writes:
                assert "last_queried_at" in write.record_data
                assert write.record_data["last_queried_at"] > 0


# =============================================================================
# TEST: Convenience Function
# =============================================================================


class TestConvenienceFunction:
    """Tests for assemble_intent_signal_writes function."""

    def test_convenience_function_works(
        self,
        sample_reminder_signal: ReminderSignal,
    ) -> None:
        """Convenience function creates assembler and processes signals."""
        result = assemble_intent_signal_writes(
            signals=[sample_reminder_signal],
            tenant_id="t1",
            space_id="s1",
            actor_id="a1",
        )

        assert LAYER_ST_PROSPECTIVE in result
        assert len(result[LAYER_ST_PROSPECTIVE]) == 1


# =============================================================================
# TEST: Write Properties
# =============================================================================


class TestWriteProperties:
    """Tests for StagedWrite properties from assembly."""

    def test_writes_have_phase_provenance(
        self,
        assembler: IntentSignalAssembler,
        sample_reminder_signal: ReminderSignal,
    ) -> None:
        """All writes have R6_INTENT as source phase."""
        result = assembler.assemble_all([sample_reminder_signal])

        for layer_writes in result.values():
            for write in layer_writes:
                assert write.source_phase == "R6_INTENT"

    def test_writes_have_event_ids(
        self,
        assembler: IntentSignalAssembler,
        sample_lesson_signal: LessonSignal,
    ) -> None:
        """All writes include source event_ids for tracing."""
        result = assembler.assemble_all([sample_lesson_signal])

        for layer_writes in result.values():
            for write in layer_writes:
                assert len(write.source_event_ids) > 0
                assert sample_lesson_signal.event_id in write.source_event_ids

    def test_tenant_and_space_propagated(
        self,
        assembler: IntentSignalAssembler,
        sample_reminder_signal: ReminderSignal,
    ) -> None:
        """Tenant and space IDs propagated to write data."""
        result = assembler.assemble_all([sample_reminder_signal])
        write = result[LAYER_ST_PROSPECTIVE][0]

        assert write.record_data["tenant_id"] == "test-tenant"
        assert write.record_data["space_id"] == "test-space"
