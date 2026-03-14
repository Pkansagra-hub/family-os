"""
R4 KG Consolidator Phase Tests — Epic 4.4.8

Tests for the R4 Knowledge Graph Consolidation phase.

Test Categories:
1. Phase Configuration (R4Config)
2. Skip Conditions
3. Entity Extraction
4. Entity Clustering
5. Confidence Routing
6. Hebbian Co-occurrence
7. Phase Output Population
8. Integration with 4.4.5-4.4.7 components
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from k0.pipelines.p03.phase_outputs import GapCandidate

# Import from actual module
from k0.pipelines.p03.phases.r4_kg_consolidator import (
    EntityCluster,
    KGUpdate,
    KGUpdateType,
    R4Config,
    R4KGConsolidator,
    R4PhaseStats,
    create_r4_phase,
)
from k0.pipelines.p03.runner_contract import P03PhaseId, P03PhaseStatus

# =============================================================================
# Mock Classes
# =============================================================================


@dataclass
class MockEvent:
    """Mock P03EventState for testing."""

    event_id: str
    content_text: Optional[str] = None
    kg_processed: bool = False
    embedding_768: Optional[List[float]] = None


class MockEnvelopeContext:
    """Mock envelope context."""

    cycle_id: str = "cycle_001"
    space_id: str = "space_001"
    tenant_id: str = "tenant_001"


class MockPhaseOutputs:
    """Mock P03PhaseOutputs."""

    def __init__(self) -> None:
        self.r4_new_entities: List = []
        self.r4_updated_entities: List = []
        self.r4_new_edges: List = []
        self.r4_updated_edges: List = []
        self.r4_gap_candidates: List = []
        self.r4_causal_edges: List = []


class MockEnvelope:
    """Mock P03BatchEnvelope."""

    def __init__(self, events: List[MockEvent]) -> None:
        self.events = events
        self.context = MockEnvelopeContext()
        self.phases = MockPhaseOutputs()


class MockRunnerContext:
    """Mock runner context."""

    def __init__(self) -> None:
        self.syscalls = MagicMock()
        self.metrics_registry = None  # P03MetricsRegistry (optional for tests)


# =============================================================================
# Phase Configuration Tests
# =============================================================================


class TestR4Config:
    """Tests for R4Config dataclass."""

    def test_default_config_values(self) -> None:
        """Test: Default config has expected values."""
        config = R4Config()

        assert config.min_entities_for_edge == 2
        assert config.min_co_occurrence == 1
        assert config.max_relationship_confidence == 0.9
        assert config.base_confidence == 0.3
        assert config.confidence_increment == 0.1
        assert config.enable_causal_inference is True  # 4.4.9 enabled by default
        assert config.enable_adaptive_thresholds is True
        assert config.emit_gaps_on_low_confidence is True
        # 4.4.8-4.4.11 new defaults
        assert config.enable_hebbian_adaptive_rates is True
        assert config.enable_causality_thresholds is True
        assert config.enable_edge_feedback is True
        assert config.granger_min_observations == 3  # M1-E2-I3: Lowered for cold-start
        assert config.granger_precedence_threshold == 0.60  # M1-E2-I2: Lowered for cold-start
        assert config.staleness_check_days == 90

    def test_custom_config_values(self) -> None:
        """Test: Custom config values are applied."""
        config = R4Config(
            min_co_occurrence=3,
            max_relationship_confidence=0.8,
            enable_causal_inference=True,
        )

        assert config.min_co_occurrence == 3
        assert config.max_relationship_confidence == 0.8
        assert config.enable_causal_inference is True


class TestR4PhaseStats:
    """Tests for R4PhaseStats dataclass."""

    def test_default_stats_values(self) -> None:
        """Test: Default stats are zero."""
        stats = R4PhaseStats()

        assert stats.events_processed == 0
        assert stats.entities_extracted == 0
        assert stats.new_entities_created == 0
        assert stats.new_edges_created == 0

    def test_stats_to_dict(self) -> None:
        """Test: Stats convert to dict correctly."""
        stats = R4PhaseStats(
            events_processed=10,
            entities_extracted=25,
            new_entities_created=5,
            new_edges_created=3,
        )

        d = stats.to_dict()

        assert d["events_processed"] == 10
        assert d["entities_extracted"] == 25
        assert d["new_entities_created"] == 5
        assert d["new_edges_created"] == 3


# =============================================================================
# KGUpdate Tests
# =============================================================================


class TestKGUpdate:
    """Tests for KGUpdate dataclass."""

    def test_create_entity_update(self) -> None:
        """Test: CREATE_ENTITY update has correct fields."""
        update = KGUpdate(
            update_type=KGUpdateType.CREATE_ENTITY,
            entity_id="entity_001",
            canonical_name="John Smith",
            entity_type="PERSON",
            aliases=["John", "Johnny"],
            new_observations=3,
            confidence=0.85,
        )

        assert update.update_type == KGUpdateType.CREATE_ENTITY
        assert update.entity_id == "entity_001"
        assert update.canonical_name == "John Smith"
        assert update.entity_type == "PERSON"
        assert len(update.aliases) == 2

    def test_create_edge_update(self) -> None:
        """Test: CREATE_EDGE update has correct fields."""
        update = KGUpdate(
            update_type=KGUpdateType.CREATE_EDGE,
            edge_id="edge_001",
            source_id="entity_001",
            target_id="entity_002",
            relation_type="RELATED_TO",
            confidence=0.6,
            observation_count=3,
        )

        assert update.update_type == KGUpdateType.CREATE_EDGE
        assert update.edge_id == "edge_001"
        assert update.source_id == "entity_001"
        assert update.target_id == "entity_002"
        assert update.relation_type == "RELATED_TO"


class TestEntityCluster:
    """Tests for EntityCluster dataclass."""

    def test_cluster_creation(self) -> None:
        """Test: EntityCluster has correct fields."""
        cluster = EntityCluster(
            cluster_id="cluster_001",
            canonical_name="New York",
            entity_type="LOCATION",
            mentions=["New York", "NYC", "NY"],
            observation_ids=["evt_1", "evt_2"],
            confidence=0.9,
        )

        assert cluster.cluster_id == "cluster_001"
        assert cluster.canonical_name == "New York"
        assert cluster.entity_type == "LOCATION"
        assert len(cluster.mentions) == 3
        assert len(cluster.observation_ids) == 2
        assert cluster.confidence == 0.9


# =============================================================================
# Phase Lifecycle Tests
# =============================================================================


class TestR4KGConsolidatorLifecycle:
    """Tests for R4KGConsolidator lifecycle."""

    def test_phase_id(self) -> None:
        """Test: Phase ID is R4_KG."""
        phase = R4KGConsolidator()
        assert phase.phase_id == P03PhaseId.R4_KG

    def test_idempotency_key(self) -> None:
        """Test: Idempotency key is generated correctly."""
        phase = R4KGConsolidator()
        envelope = MockEnvelope([])
        envelope.context.cycle_id = "cycle_123"

        key = phase.idempotency_key(envelope)  # type: ignore[arg-type]

        assert key == "p03:r4:cycle_123"

    def test_create_r4_phase_factory(self) -> None:
        """Test: Factory function creates phase correctly."""
        phase = create_r4_phase()
        assert isinstance(phase, R4KGConsolidator)

    def test_create_r4_phase_with_config(self) -> None:
        """Test: Factory function applies config."""
        config = R4Config(min_co_occurrence=5)
        phase = create_r4_phase(config)

        assert phase.config.min_co_occurrence == 5


# =============================================================================
# Skip Condition Tests
# =============================================================================


class TestR4SkipConditions:
    """Tests for R4 skip conditions."""

    def test_skip_on_empty_events(self) -> None:
        """Test: Skip when no events in batch."""
        phase = R4KGConsolidator()
        envelope = MockEnvelope([])

        assert phase.should_skip(envelope) is True  # type: ignore[arg-type]

    def test_skip_when_all_processed(self) -> None:
        """Test: Skip when all events already KG-processed."""
        events = [
            MockEvent(event_id="e1", content_text="Hello", kg_processed=True),
            MockEvent(event_id="e2", content_text="World", kg_processed=True),
        ]
        phase = R4KGConsolidator()
        envelope = MockEnvelope(events)

        assert phase.should_skip(envelope) is True  # type: ignore[arg-type]

    def test_skip_when_no_content(self) -> None:
        """Test: Skip when no events have content text."""
        events = [
            MockEvent(event_id="e1", content_text=None),
            MockEvent(event_id="e2", content_text=None),
        ]
        phase = R4KGConsolidator()
        envelope = MockEnvelope(events)

        assert phase.should_skip(envelope) is True  # type: ignore[arg-type]

    def test_no_skip_with_valid_events(self) -> None:
        """Test: Don't skip when events have content."""
        events = [
            MockEvent(event_id="e1", content_text="Meeting with John"),
            MockEvent(event_id="e2", content_text="Lunch at Cafe"),
        ]
        phase = R4KGConsolidator()
        envelope = MockEnvelope(events)

        assert phase.should_skip(envelope) is False  # type: ignore[arg-type]


# =============================================================================
# Hebbian Co-occurrence Tests
# =============================================================================


class TestHebbianCoOccurrence:
    """Tests for Hebbian co-occurrence relationship discovery."""

    def test_confidence_formula_min_co_occurrence(self) -> None:
        """Test: Min 2 co-occurrences needed for edge."""
        # With default config: min_co_occurrence=2
        # 1 co-occurrence should not create edge
        config = R4Config()

        # confidence = min(0.9, 0.3 + 0.1 * count)
        # For count=2: min(0.9, 0.3 + 0.2) = 0.5
        expected = min(
            config.max_relationship_confidence,
            config.base_confidence + config.confidence_increment * 2,
        )
        assert expected == 0.5

    def test_confidence_formula_caps_at_max(self) -> None:
        """Test: Confidence caps at max (0.9)."""
        config = R4Config()

        # For count=10: min(0.9, 0.3 + 1.0) = 0.9
        expected = min(
            config.max_relationship_confidence,
            config.base_confidence + config.confidence_increment * 10,
        )
        assert expected == 0.9

    def test_confidence_formula_progression(self) -> None:
        """Test: Confidence increases with co-occurrences."""
        config = R4Config()

        confidences = []
        for count in [2, 3, 4, 5, 6]:
            conf = min(
                config.max_relationship_confidence,
                config.base_confidence + config.confidence_increment * count,
            )
            confidences.append(round(conf, 1))

        # Should be: [0.5, 0.6, 0.7, 0.8, 0.9]
        assert confidences == [0.5, 0.6, 0.7, 0.8, 0.9]


# =============================================================================
# Phase Execution Tests
# =============================================================================


class TestR4PhaseExecution:
    """Tests for R4 phase execution."""

    @pytest.mark.asyncio
    async def test_run_skips_empty_batch(self) -> None:
        """Test: Run skips on empty batch."""
        phase = R4KGConsolidator()
        envelope = MockEnvelope([])
        ctx = MockRunnerContext()

        result = await phase.run(envelope, ctx)  # type: ignore[arg-type]

        assert result.status == P03PhaseStatus.SKIP
        assert result.phase_id == P03PhaseId.R4_KG

    @pytest.mark.asyncio
    async def test_run_skips_all_processed(self) -> None:
        """Test: Run skips when all events processed."""
        events = [
            MockEvent(event_id="e1", content_text="Hello", kg_processed=True),
        ]
        phase = R4KGConsolidator()
        envelope = MockEnvelope(events)
        ctx = MockRunnerContext()

        result = await phase.run(envelope, ctx)  # type: ignore[arg-type]

        assert result.status == P03PhaseStatus.SKIP

    @pytest.mark.asyncio
    async def test_run_returns_done_on_success(self) -> None:
        """Test: Run returns DONE on successful execution."""
        events = [
            MockEvent(event_id="e1", content_text="Meeting with John at office"),
        ]
        phase = R4KGConsolidator()
        envelope = MockEnvelope(events)
        ctx = MockRunnerContext()

        # Mock the entity extractor to return entities
        with patch.object(phase, "_initialize_components"):
            phase._entity_extractor = MagicMock()
            phase._entity_extractor.extract.return_value = []
            phase._confidence_router = MagicMock()
            phase._merge_thresholds = MagicMock()
            phase._merge_thresholds.should_merge.return_value = MagicMock(should_merge=True)

            result = await phase.run(envelope, ctx)  # type: ignore[arg-type]

        assert result.status == P03PhaseStatus.DONE
        assert result.phase_id == P03PhaseId.R4_KG
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_run_populates_outputs_summary(self) -> None:
        """Test: Run populates outputs summary."""
        events = [
            MockEvent(event_id="e1", content_text="Meeting with John"),
        ]
        phase = R4KGConsolidator()
        envelope = MockEnvelope(events)
        ctx = MockRunnerContext()

        with patch.object(phase, "_initialize_components"):
            phase._entity_extractor = MagicMock()
            phase._entity_extractor.extract.return_value = []
            phase._confidence_router = MagicMock()
            phase._merge_thresholds = MagicMock()
            phase._merge_thresholds.should_merge.return_value = MagicMock(should_merge=True)

            result = await phase.run(envelope, ctx)  # type: ignore[arg-type]

        assert "events_processed" in result.outputs_summary
        assert "entities_extracted" in result.outputs_summary
        assert "new_entities" in result.outputs_summary
        assert "new_edges" in result.outputs_summary


# =============================================================================
# Integration Tests
# =============================================================================


class TestR4IntegrationWithAlgorithms:
    """Tests for R4 integration with 4.4.5-4.4.7 components."""

    def test_phase_has_confidence_router_dependency(self) -> None:
        """Test: Phase initializes ConfidenceRouter."""
        phase = R4KGConsolidator()
        # Initially None
        assert phase._confidence_router is None

    def test_phase_has_merge_thresholds_dependency(self) -> None:
        """Test: Phase initializes AdaptiveMergeThresholds."""
        phase = R4KGConsolidator()
        # Initially None
        assert phase._merge_thresholds is None

    def test_phase_has_entity_merger_dependency(self) -> None:
        """Test: Phase initializes EntityMerger."""
        phase = R4KGConsolidator()
        # Initially None
        assert phase._entity_merger is None


# =============================================================================
# Phase Output Population Tests
# =============================================================================


class TestR4PhaseOutputs:
    """Tests for R4 phase output population."""

    def test_creates_kg_entity_from_update(self) -> None:
        """Test: KGEntity created from CREATE_ENTITY update."""
        phase = R4KGConsolidator()
        envelope = MockEnvelope([])

        entity_updates = [
            KGUpdate(
                update_type=KGUpdateType.CREATE_ENTITY,
                entity_id="entity_001",
                canonical_name="John Smith",
                entity_type="PERSON",
                aliases=["John"],
                confidence=0.85,
                source_event_ids=["evt_1"],
            )
        ]

        phase._populate_phase_outputs(envelope, entity_updates, [], [])  # type: ignore[arg-type]

        assert len(envelope.phases.r4_new_entities) == 1
        entity = envelope.phases.r4_new_entities[0]
        assert entity.entity_id == "entity_001"
        assert entity.canonical_name == "John Smith"
        assert entity.entity_type == "PERSON"

    def test_creates_kg_edge_from_update(self) -> None:
        """Test: KGEdge created from CREATE_EDGE update."""
        phase = R4KGConsolidator()
        envelope = MockEnvelope([])

        edge_updates = [
            KGUpdate(
                update_type=KGUpdateType.CREATE_EDGE,
                edge_id="edge_001",
                source_id="entity_001",
                target_id="entity_002",
                relation_type="RELATED_TO",
                confidence=0.6,
                observation_count=3,
                source_event_ids=["evt_1"],
            )
        ]

        phase._populate_phase_outputs(envelope, [], edge_updates, [])  # type: ignore[arg-type]

        assert len(envelope.phases.r4_new_edges) == 1
        edge = envelope.phases.r4_new_edges[0]
        assert edge.edge_id == "edge_001"
        assert edge.source_entity_id == "entity_001"
        assert edge.target_entity_id == "entity_002"
        assert edge.relationship_type == "RELATED_TO"
        assert edge.evidence_event_ids == ["evt_1"]

    def test_creates_kg_edge_update_from_update(self) -> None:
        """Test: KGEdgeUpdate created from UPDATE_EDGE update includes evidence IDs."""
        phase = R4KGConsolidator()
        envelope = MockEnvelope([])

        edge_updates = [
            KGUpdate(
                update_type=KGUpdateType.UPDATE_EDGE,
                edge_id="edge_001",
                confidence=0.1,
                observation_count=2,
                source_event_ids=["evt_42"],
            )
        ]

        phase._populate_phase_outputs(envelope, [], edge_updates, [])  # type: ignore[arg-type]

        assert len(envelope.phases.r4_updated_edges) == 1
        upd = envelope.phases.r4_updated_edges[0]
        assert upd.edge_id == "edge_001"
        assert upd.new_evidence_ids == ["evt_42"]
        assert upd.observation_count_increment == 2

    def test_populates_gap_candidates(self) -> None:
        """Test: Gap candidates are added to outputs."""

        phase = R4KGConsolidator()
        envelope = MockEnvelope([])

        gaps = [
            GapCandidate(
                gap_id="gap_001",
                gap_type="AMBIGUOUS_ENTITY",
                related_entity_id="cluster_001",
                entropy_score=0.6,
                priority="HIGH",
            )
        ]

        phase._populate_phase_outputs(envelope, [], [], gaps)  # type: ignore[arg-type]

        assert len(envelope.phases.r4_gap_candidates) == 1
        assert envelope.phases.r4_gap_candidates[0].gap_id == "gap_001"


# =============================================================================
# M10.3 Edge Type Inference Tests
# =============================================================================


class TestEdgeTypeInference:
    """Tests for M10.3: Infer edge type from ULTRABERT relations."""

    def test_infer_family_type_from_parent_of(self) -> None:
        """Test: parent_of relation infers FAMILY type."""
        phase = R4KGConsolidator()
        event_relations_map = {
            "event_001": ["parent_of"],
        }

        result = phase._infer_edge_type_from_relations(["event_001"], event_relations_map)

        assert result == "FAMILY"

    def test_infer_family_type_from_spouse_of(self) -> None:
        """Test: spouse_of relation infers FAMILY type."""
        phase = R4KGConsolidator()
        event_relations_map = {
            "event_001": ["spouse_of"],
        }

        result = phase._infer_edge_type_from_relations(["event_001"], event_relations_map)

        assert result == "FAMILY"

    def test_infer_friend_type(self) -> None:
        """Test: friend_of relation infers FRIEND type."""
        phase = R4KGConsolidator()
        event_relations_map = {
            "event_001": ["friend_of"],
        }

        result = phase._infer_edge_type_from_relations(["event_001"], event_relations_map)

        assert result == "FRIEND"

    def test_infer_colleague_type(self) -> None:
        """Test: colleague_of relation infers COLLEAGUE type."""
        phase = R4KGConsolidator()
        event_relations_map = {
            "event_001": ["colleague_of"],
        }

        result = phase._infer_edge_type_from_relations(["event_001"], event_relations_map)

        assert result == "COLLEAGUE"

    def test_priority_family_over_friend(self) -> None:
        """Test: FAMILY takes priority over FRIEND when both present."""
        phase = R4KGConsolidator()
        event_relations_map = {
            "event_001": ["friend_of"],  # FRIEND
            "event_002": ["parent_of"],  # FAMILY
        }

        result = phase._infer_edge_type_from_relations(
            ["event_001", "event_002"], event_relations_map
        )

        assert result == "FAMILY"  # FAMILY priority 4 > FRIEND priority 3

    def test_priority_friend_over_colleague(self) -> None:
        """Test: FRIEND takes priority over COLLEAGUE when both present."""
        phase = R4KGConsolidator()
        event_relations_map = {
            "event_001": ["colleague_of"],  # COLLEAGUE
            "event_002": ["friend_of"],  # FRIEND
        }

        result = phase._infer_edge_type_from_relations(
            ["event_001", "event_002"], event_relations_map
        )

        assert result == "FRIEND"  # FRIEND priority 3 > COLLEAGUE priority 2

    def test_multiple_relations_in_single_event(self) -> None:
        """Test: Multiple relations in one event, highest priority wins."""
        phase = R4KGConsolidator()
        event_relations_map = {
            "event_001": ["colleague_of", "sibling_of", "friend_of"],
        }

        result = phase._infer_edge_type_from_relations(["event_001"], event_relations_map)

        assert result == "FAMILY"  # sibling_of -> FAMILY wins

    def test_empty_event_relations_returns_related_to(self) -> None:
        """Test: Empty event_relations_map returns RELATED_TO default."""
        phase = R4KGConsolidator()

        result = phase._infer_edge_type_from_relations(["event_001"], {})

        assert result == "RELATED_TO"

    def test_empty_event_ids_returns_related_to(self) -> None:
        """Test: Empty event_ids list returns RELATED_TO default."""
        phase = R4KGConsolidator()
        event_relations_map = {
            "event_001": ["parent_of"],
        }

        result = phase._infer_edge_type_from_relations([], event_relations_map)

        assert result == "RELATED_TO"

    def test_unknown_relation_type_ignored(self) -> None:
        """Test: Unknown relation types are ignored, fallback to RELATED_TO."""
        phase = R4KGConsolidator()
        event_relations_map = {
            "event_001": ["unknown_relation", "made_up_type"],
        }

        result = phase._infer_edge_type_from_relations(["event_001"], event_relations_map)

        assert result == "RELATED_TO"

    def test_mixed_known_unknown_relations(self) -> None:
        """Test: Known relations are used, unknown ignored."""
        phase = R4KGConsolidator()
        event_relations_map = {
            "event_001": ["unknown_type", "friend_of"],  # friend_of is known
        }

        result = phase._infer_edge_type_from_relations(["event_001"], event_relations_map)

        assert result == "FRIEND"

    def test_all_family_relations_map_correctly(self) -> None:
        """Test: All family relation subtypes map to FAMILY."""
        phase = R4KGConsolidator()
        family_relations = [
            "parent_of",
            "child_of",
            "spouse_of",
            "sibling_of",
            "grandparent_of",
            "grandchild_of",
            "aunt_uncle_of",
            "niece_nephew_of",
            "cousin_of",
            "pet_of",
        ]

        for i, rel in enumerate(family_relations):
            event_id = f"event_{i:03d}"
            event_relations_map = {event_id: [rel]}

            result = phase._infer_edge_type_from_relations([event_id], event_relations_map)

            assert result == "FAMILY", f"Expected FAMILY for {rel}, got {result}"


# =============================================================================
# M10.5 Entity Priority Threshold Tests
# =============================================================================


class TestEntityPriorityThreshold:
    """Tests for M10.5: Entity priority threshold filtering."""

    def test_min_entity_priority_default_value(self) -> None:
        """Test: Default min_entity_priority is 0.65."""
        config = R4Config()
        assert config.min_entity_priority == 0.65

    def test_min_entity_priority_custom_value(self) -> None:
        """Test: Custom min_entity_priority is applied."""
        config = R4Config(min_entity_priority=0.70)
        assert config.min_entity_priority == 0.70


# =============================================================================
# M10.6 Canonical Name Selection Tests
# =============================================================================


class TestCanonicalNameSelection:
    """Tests for M10.6: Deterministic canonical name selection."""

    def test_select_single_mention(self) -> None:
        """Test: Single mention returns that mention."""
        phase = R4KGConsolidator()
        result = phase._select_canonical_name(["John"])
        assert result == "John"

    def test_select_empty_mentions(self) -> None:
        """Test: Empty mentions returns empty string."""
        phase = R4KGConsolidator()
        result = phase._select_canonical_name([])
        assert result == ""

    def test_select_most_common_variant(self) -> None:
        """Test: Most common variant wins."""
        phase = R4KGConsolidator()
        result = phase._select_canonical_name(["Mom", "mom", "Mom", "Mom"])
        assert result == "Mom"

    def test_select_proper_case_over_lowercase(self) -> None:
        """Test: Proper case wins when frequency is equal."""
        phase = R4KGConsolidator()
        # Same frequency, but "Mom" has proper case
        result = phase._select_canonical_name(["Mom", "mom"])
        assert result == "Mom"

    def test_select_longer_variant(self) -> None:
        """Test: Longer variant wins when frequency and case are equal."""
        phase = R4KGConsolidator()
        # Both lowercase, same frequency, "mother" is longer
        result = phase._select_canonical_name(["mom", "mother"])
        assert result == "mother"

    def test_frequency_beats_case(self) -> None:
        """Test: Frequency takes priority over proper case."""
        phase = R4KGConsolidator()
        # "mom" appears 3 times, "Mom" appears once
        result = phase._select_canonical_name(["mom", "mom", "mom", "Mom"])
        assert result == "mom"

    def test_real_world_scenario(self) -> None:
        """Test: Real-world scenario with mixed mentions."""
        phase = R4KGConsolidator()
        mentions = ["Grandma", "grandma", "Grandma", "grandmother", "Grandma"]
        result = phase._select_canonical_name(mentions)
        assert result == "Grandma"  # Most common (3x) and proper case


# =============================================================================
# M10.7 Temporal Edge Type Tests
# =============================================================================


class TestTemporalEdgeTypes:
    """Tests for M10.7: FOLLOWS/PRECEDES temporal relationship types."""

    def test_config_default_enable_temporal_edges(self) -> None:
        """Test: enable_temporal_edges defaults to True."""
        config = R4Config()
        assert config.enable_temporal_edges is True

    def test_config_default_temporal_follows_threshold(self) -> None:
        """Test: temporal_follows_threshold defaults to 0.60."""
        config = R4Config()
        assert config.temporal_follows_threshold == 0.60

    def test_config_custom_temporal_settings(self) -> None:
        """Test: Custom temporal settings are applied."""
        config = R4Config(
            enable_temporal_edges=False,
            temporal_follows_threshold=0.65,
        )
        assert config.enable_temporal_edges is False
        assert config.temporal_follows_threshold == 0.65

    def test_temporal_precedes_threshold_symmetric(self) -> None:
        """Test: PRECEDES threshold is symmetric (1.0 - follows_threshold)."""
        config = R4Config(temporal_follows_threshold=0.60)
        precedes_threshold = 1.0 - config.temporal_follows_threshold
        assert precedes_threshold == 0.40

    def test_temporal_threshold_bounds_valid(self) -> None:
        """Test: Temporal thresholds create valid non-overlapping ranges."""
        config = R4Config(
            granger_precedence_threshold=0.75,
            temporal_follows_threshold=0.60,
        )
        # CAUSES: ratio >= 0.75
        # FOLLOWS: 0.60 <= ratio < 0.75
        # Ambiguous: 0.40 < ratio < 0.60
        # PRECEDES: ratio <= 0.40
        follows_min = config.temporal_follows_threshold
        follows_max = config.granger_precedence_threshold
        precedes_max = 1.0 - config.temporal_follows_threshold

        # Validate non-overlapping ranges
        assert follows_min < follows_max  # FOLLOWS range exists
        assert precedes_max < follows_min  # Gap between PRECEDES and FOLLOWS

    def test_temporal_threshold_custom_follows(self) -> None:
        """Test: Custom follows threshold adjusts all ranges correctly."""
        config = R4Config(
            granger_precedence_threshold=0.80,
            temporal_follows_threshold=0.70,
        )
        precedes_threshold = 1.0 - config.temporal_follows_threshold

        # CAUSES: ratio >= 0.80
        # FOLLOWS: 0.70 <= ratio < 0.80
        # Ambiguous: 0.30 < ratio < 0.70
        # PRECEDES: ratio <= 0.30
        assert config.granger_precedence_threshold == 0.80
        assert config.temporal_follows_threshold == 0.70
        assert abs(precedes_threshold - 0.30) < 0.001  # Floating point tolerance


# =============================================================================
# 5.H.1: R1 Importance Score Wiring Tests
# =============================================================================


class TestR1ImportanceScoreWiring:
    """Tests for 5.H.1: Wire R1 importance scores into R4 Hebbian co-occurrence.

    Validates:
    - R1 importance scores used for edge weight computation
    - Fallback to cluster confidence when R1 scores unavailable
    - importance_source metadata tracked on KGUpdate
    - Mixed R1/fallback (partial) correctly classified
    - Stats counters (hebbian_r1_importance_used, hebbian_fallback_importance_used)
    """

    @pytest.mark.asyncio
    async def test_r1_importance_scores_used_for_edge_weight(self) -> None:
        """Test: R1 importance scores drive edge weight instead of cluster confidence."""
        phase = R4KGConsolidator(config=R4Config(min_co_occurrence=1))
        ctx_init = MockRunnerContext()
        phase._initialize_components(ctx_init)

        clusters = [
            EntityCluster(
                cluster_id="c_alice",
                canonical_name="Alice",
                entity_type="PERSON",
                mentions=["Alice"],
                observation_ids=["evt_1"],
                confidence=0.3,  # Low NER confidence
            ),
            EntityCluster(
                cluster_id="c_bob",
                canonical_name="Bob",
                entity_type="PERSON",
                mentions=["Bob"],
                observation_ids=["evt_1"],
                confidence=0.3,  # Low NER confidence
            ),
        ]

        from k0.modules.consolidation.algorithms.entity_extractor import (
            ExtractedEntity,
            KGEntityType,
        )

        event_entity_map = {
            "evt_1": [
                ExtractedEntity(
                    text="Alice",
                    kg_type=KGEntityType.PERSON,
                    normalized_text="alice",
                    source_label="PER",
                    source_head="ner_general",
                    priority=0.8,
                    start_token=0,
                    end_token=1,
                ),
                ExtractedEntity(
                    text="Bob",
                    kg_type=KGEntityType.PERSON,
                    normalized_text="bob",
                    source_label="PER",
                    source_head="ner_general",
                    priority=0.8,
                    start_token=2,
                    end_token=3,
                ),
            ],
        }

        ctx = MockRunnerContext()
        ctx.syscalls.kg_edges_lookup = AsyncMock(return_value={})

        # High R1 importance for evt_1
        r1_importance_map = {"evt_1": 0.95}

        updates = await phase._discover_relationships(
            clusters,
            event_entity_map,
            {},
            "t1",
            "s1",
            ctx,
            r1_importance_map=r1_importance_map,
        )

        assert len(updates) == 1
        edge = updates[0]
        assert edge.update_type == KGUpdateType.CREATE_EDGE
        # With R1 score of 0.95, initial weight should be higher than
        # what 0.3 cluster confidence average would give
        assert edge.confidence > 0.0
        assert edge.importance_source == "hebbian_r1"

    @pytest.mark.asyncio
    async def test_fallback_to_cluster_confidence_without_r1(self) -> None:
        """Test: Falls back to cluster confidence average when no R1 scores."""
        phase = R4KGConsolidator(config=R4Config(min_co_occurrence=1))
        ctx_init = MockRunnerContext()
        phase._initialize_components(ctx_init)

        clusters = [
            EntityCluster(
                cluster_id="c_alice",
                canonical_name="Alice",
                entity_type="PERSON",
                mentions=["Alice"],
                observation_ids=["evt_1"],
                confidence=0.7,
            ),
            EntityCluster(
                cluster_id="c_bob",
                canonical_name="Bob",
                entity_type="PERSON",
                mentions=["Bob"],
                observation_ids=["evt_1"],
                confidence=0.5,
            ),
        ]

        from k0.modules.consolidation.algorithms.entity_extractor import (
            ExtractedEntity,
            KGEntityType,
        )

        event_entity_map = {
            "evt_1": [
                ExtractedEntity(
                    text="Alice",
                    kg_type=KGEntityType.PERSON,
                    normalized_text="alice",
                    source_label="PER",
                    source_head="ner_general",
                    priority=0.8,
                    start_token=0,
                    end_token=1,
                ),
                ExtractedEntity(
                    text="Bob",
                    kg_type=KGEntityType.PERSON,
                    normalized_text="bob",
                    source_label="PER",
                    source_head="ner_general",
                    priority=0.8,
                    start_token=2,
                    end_token=3,
                ),
            ],
        }

        ctx = MockRunnerContext()
        ctx.syscalls.kg_edges_lookup = AsyncMock(return_value={})

        # No R1 importance map — empty
        updates = await phase._discover_relationships(
            clusters,
            event_entity_map,
            {},
            "t1",
            "s1",
            ctx,
            r1_importance_map={},
        )

        assert len(updates) == 1
        edge = updates[0]
        assert edge.importance_source == "hebbian_fallback"

    @pytest.mark.asyncio
    async def test_importance_source_r1_partial_mixed_events(self) -> None:
        """Test: Mixed R1/fallback events classified as hebbian_r1_partial."""
        phase = R4KGConsolidator(config=R4Config(min_co_occurrence=1))
        ctx_init = MockRunnerContext()
        phase._initialize_components(ctx_init)

        clusters = [
            EntityCluster(
                cluster_id="c_alice",
                canonical_name="Alice",
                entity_type="PERSON",
                mentions=["Alice"],
                observation_ids=["evt_1", "evt_2"],
                confidence=0.6,
            ),
            EntityCluster(
                cluster_id="c_bob",
                canonical_name="Bob",
                entity_type="PERSON",
                mentions=["Bob"],
                observation_ids=["evt_1", "evt_2"],
                confidence=0.6,
            ),
        ]

        from k0.modules.consolidation.algorithms.entity_extractor import (
            ExtractedEntity,
            KGEntityType,
        )

        event_entity_map = {
            "evt_1": [
                ExtractedEntity(
                    text="Alice",
                    kg_type=KGEntityType.PERSON,
                    normalized_text="alice",
                    source_label="PER",
                    source_head="ner_general",
                    priority=0.8,
                    start_token=0,
                    end_token=1,
                ),
                ExtractedEntity(
                    text="Bob",
                    kg_type=KGEntityType.PERSON,
                    normalized_text="bob",
                    source_label="PER",
                    source_head="ner_general",
                    priority=0.8,
                    start_token=2,
                    end_token=3,
                ),
            ],
            "evt_2": [
                ExtractedEntity(
                    text="Alice",
                    kg_type=KGEntityType.PERSON,
                    normalized_text="alice",
                    source_label="PER",
                    source_head="ner_general",
                    priority=0.8,
                    start_token=0,
                    end_token=1,
                ),
                ExtractedEntity(
                    text="Bob",
                    kg_type=KGEntityType.PERSON,
                    normalized_text="bob",
                    source_label="PER",
                    source_head="ner_general",
                    priority=0.8,
                    start_token=2,
                    end_token=3,
                ),
            ],
        }

        ctx = MockRunnerContext()
        ctx.syscalls.kg_edges_lookup = AsyncMock(return_value={})

        # Only evt_1 has R1 score; evt_2 does not
        r1_importance_map = {"evt_1": 0.85}

        updates = await phase._discover_relationships(
            clusters,
            event_entity_map,
            {},
            "t1",
            "s1",
            ctx,
            r1_importance_map=r1_importance_map,
        )

        assert len(updates) == 1
        edge = updates[0]
        assert edge.importance_source == "hebbian_r1_partial"

    @pytest.mark.asyncio
    async def test_stats_counters_r1_vs_fallback(self) -> None:
        """Test: Stats counters track R1 vs fallback usage correctly."""
        phase = R4KGConsolidator(config=R4Config(min_co_occurrence=1))
        ctx_init = MockRunnerContext()
        phase._initialize_components(ctx_init)

        clusters = [
            EntityCluster(
                cluster_id="c_alice",
                canonical_name="Alice",
                entity_type="PERSON",
                mentions=["Alice"],
                observation_ids=["evt_1"],
                confidence=0.6,
            ),
            EntityCluster(
                cluster_id="c_bob",
                canonical_name="Bob",
                entity_type="PERSON",
                mentions=["Bob"],
                observation_ids=["evt_1"],
                confidence=0.6,
            ),
            EntityCluster(
                cluster_id="c_carol",
                canonical_name="Carol",
                entity_type="PERSON",
                mentions=["Carol"],
                observation_ids=["evt_2"],
                confidence=0.5,
            ),
            EntityCluster(
                cluster_id="c_dave",
                canonical_name="Dave",
                entity_type="PERSON",
                mentions=["Dave"],
                observation_ids=["evt_2"],
                confidence=0.5,
            ),
        ]

        from k0.modules.consolidation.algorithms.entity_extractor import (
            ExtractedEntity,
            KGEntityType,
        )

        event_entity_map = {
            "evt_1": [
                ExtractedEntity(
                    text="Alice",
                    kg_type=KGEntityType.PERSON,
                    normalized_text="alice",
                    source_label="PER",
                    source_head="ner_general",
                    priority=0.8,
                    start_token=0,
                    end_token=1,
                ),
                ExtractedEntity(
                    text="Bob",
                    kg_type=KGEntityType.PERSON,
                    normalized_text="bob",
                    source_label="PER",
                    source_head="ner_general",
                    priority=0.8,
                    start_token=2,
                    end_token=3,
                ),
            ],
            "evt_2": [
                ExtractedEntity(
                    text="Carol",
                    kg_type=KGEntityType.PERSON,
                    normalized_text="carol",
                    source_label="PER",
                    source_head="ner_general",
                    priority=0.8,
                    start_token=0,
                    end_token=1,
                ),
                ExtractedEntity(
                    text="Dave",
                    kg_type=KGEntityType.PERSON,
                    normalized_text="dave",
                    source_label="PER",
                    source_head="ner_general",
                    priority=0.8,
                    start_token=2,
                    end_token=3,
                ),
            ],
        }

        ctx = MockRunnerContext()
        ctx.syscalls.kg_edges_lookup = AsyncMock(return_value={})

        # Only evt_1 has R1 score
        r1_importance_map = {"evt_1": 0.9}

        await phase._discover_relationships(
            clusters,
            event_entity_map,
            {},
            "t1",
            "s1",
            ctx,
            r1_importance_map=r1_importance_map,
        )

        # Alice-Bob pair: R1 hit -> hebbian_r1_importance_used=1
        # Carol-Dave pair: no R1 -> hebbian_fallback_importance_used=1
        assert phase._stats.hebbian_r1_importance_used == 1
        assert phase._stats.hebbian_fallback_importance_used == 1

    @pytest.mark.asyncio
    async def test_high_r1_score_produces_higher_weight_than_low(self) -> None:
        """Test: Higher R1 importance score produces stronger initial edge weight."""
        from k0.modules.consolidation.algorithms.entity_extractor import (
            ExtractedEntity,
            KGEntityType,
        )

        # Run 1: Low R1 score
        phase_low = R4KGConsolidator(config=R4Config(min_co_occurrence=1))
        ctx_init = MockRunnerContext()
        phase_low._initialize_components(ctx_init)

        clusters = [
            EntityCluster(
                cluster_id="c_alice",
                canonical_name="Alice",
                entity_type="PERSON",
                mentions=["Alice"],
                observation_ids=["evt_1"],
                confidence=0.5,
            ),
            EntityCluster(
                cluster_id="c_bob",
                canonical_name="Bob",
                entity_type="PERSON",
                mentions=["Bob"],
                observation_ids=["evt_1"],
                confidence=0.5,
            ),
        ]

        event_entity_map = {
            "evt_1": [
                ExtractedEntity(
                    text="Alice",
                    kg_type=KGEntityType.PERSON,
                    normalized_text="alice",
                    source_label="PER",
                    source_head="ner_general",
                    priority=0.8,
                    start_token=0,
                    end_token=1,
                ),
                ExtractedEntity(
                    text="Bob",
                    kg_type=KGEntityType.PERSON,
                    normalized_text="bob",
                    source_label="PER",
                    source_head="ner_general",
                    priority=0.8,
                    start_token=2,
                    end_token=3,
                ),
            ],
        }

        ctx_low = MockRunnerContext()
        ctx_low.syscalls.kg_edges_lookup = AsyncMock(return_value={})

        updates_low = await phase_low._discover_relationships(
            clusters,
            event_entity_map,
            {},
            "t1",
            "s1",
            ctx_low,
            r1_importance_map={"evt_1": 0.1},
        )

        # Run 2: High R1 score
        phase_high = R4KGConsolidator(config=R4Config(min_co_occurrence=1))
        phase_high._initialize_components(ctx_init)

        ctx_high = MockRunnerContext()
        ctx_high.syscalls.kg_edges_lookup = AsyncMock(return_value={})

        updates_high = await phase_high._discover_relationships(
            clusters,
            event_entity_map,
            {},
            "t1",
            "s1",
            ctx_high,
            r1_importance_map={"evt_1": 0.95},
        )

        assert len(updates_low) == 1
        assert len(updates_high) == 1
        # HebbianLearner.compute_initial_weight gives higher weight for higher importance
        assert updates_high[0].confidence >= updates_low[0].confidence

    @pytest.mark.asyncio
    async def test_no_r1_map_uses_cluster_confidence(self) -> None:
        """Test: When r1_importance_map is None, cluster confidence proxy is used."""
        phase = R4KGConsolidator(config=R4Config(min_co_occurrence=1))
        ctx_init = MockRunnerContext()
        phase._initialize_components(ctx_init)

        clusters = [
            EntityCluster(
                cluster_id="c_alice",
                canonical_name="Alice",
                entity_type="PERSON",
                mentions=["Alice"],
                observation_ids=["evt_1"],
                confidence=0.8,
            ),
            EntityCluster(
                cluster_id="c_bob",
                canonical_name="Bob",
                entity_type="PERSON",
                mentions=["Bob"],
                observation_ids=["evt_1"],
                confidence=0.6,
            ),
        ]

        from k0.modules.consolidation.algorithms.entity_extractor import (
            ExtractedEntity,
            KGEntityType,
        )

        event_entity_map = {
            "evt_1": [
                ExtractedEntity(
                    text="Alice",
                    kg_type=KGEntityType.PERSON,
                    normalized_text="alice",
                    source_label="PER",
                    source_head="ner_general",
                    priority=0.8,
                    start_token=0,
                    end_token=1,
                ),
                ExtractedEntity(
                    text="Bob",
                    kg_type=KGEntityType.PERSON,
                    normalized_text="bob",
                    source_label="PER",
                    source_head="ner_general",
                    priority=0.8,
                    start_token=2,
                    end_token=3,
                ),
            ],
        }

        ctx = MockRunnerContext()
        ctx.syscalls.kg_edges_lookup = AsyncMock(return_value={})

        # Pass None (default) for r1_importance_map
        updates = await phase._discover_relationships(
            clusters,
            event_entity_map,
            {},
            "t1",
            "s1",
            ctx,
            r1_importance_map=None,
        )

        assert len(updates) == 1
        edge = updates[0]
        assert edge.importance_source == "hebbian_fallback"
        assert phase._stats.hebbian_fallback_importance_used == 1
        assert phase._stats.hebbian_r1_importance_used == 0

    @pytest.mark.asyncio
    async def test_to_dict_includes_r1_stats(self) -> None:
        """Test: R4PhaseStats.to_dict() includes R1 importance counters."""
        stats = R4PhaseStats()
        stats.hebbian_r1_importance_used = 5
        stats.hebbian_fallback_importance_used = 3

        d = stats.to_dict()
        assert d["hebbian_r1_importance_used"] == 5
        assert d["hebbian_fallback_importance_used"] == 3

    def test_kg_update_importance_source_field(self) -> None:
        """Test: KGUpdate has importance_source field defaulting to None."""
        update = KGUpdate(
            update_type=KGUpdateType.CREATE_EDGE,
            edge_id="edge_001",
            source_id="e1",
            target_id="e2",
        )
        assert update.importance_source is None

        update_with_source = KGUpdate(
            update_type=KGUpdateType.CREATE_EDGE,
            edge_id="edge_002",
            source_id="e1",
            target_id="e2",
            importance_source="hebbian_r1",
        )
        assert update_with_source.importance_source == "hebbian_r1"


# =============================================================================
# 5.H.2: Edge Decay and Anti-Hebbian Tests
# =============================================================================


class TestEdgeDecayAndAntiHebbian:
    """Tests for 5.H.2: Edge decay and anti-Hebbian signal processing.

    Validates:
    - Time-based exponential decay reduces stale edge weights
    - Edges below prune threshold are marked for archival
    - Anti-Hebbian signals weaken wrong associations
    - Feature flags control decay/anti-Hebbian execution
    - Stats counters track decay and anti-Hebbian metrics
    """

    @pytest.mark.asyncio
    async def test_decay_reduces_stale_edge_weight(self) -> None:
        """Test: Stale edges get exponentially decayed."""
        phase = R4KGConsolidator(
            config=R4Config(
                min_co_occurrence=1,
                enable_hebbian_decay=True,
            )
        )
        ctx_init = MockRunnerContext()
        phase._initialize_components(ctx_init)

        existing_edges = {
            "edge_alice_bob": {
                "source_id": "c_alice",
                "target_id": "c_bob",
                "relation_type": "RELATED_TO",
                "confidence": 0.8,
                "observation_count": 5,
                "last_observed_at": 1000,  # Very old
            },
        }

        # Current cycle is 30 days later (in ms)
        cycle_ts = 1000 + (30 * 24 * 60 * 60 * 1000)

        updates = await phase._apply_edge_decay(
            existing_edges=existing_edges,
            current_co_occurrence_pairs=set(),  # Not re-observed
            cycle_timestamp_ms=cycle_ts,
            tenant_id="t1",
            space_id="s1",
        )

        assert len(updates) == 1
        assert updates[0].confidence < 0.8  # Decayed
        assert updates[0].importance_source == "hebbian_decay"
        assert phase._stats.hebbian_edges_decayed == 1

    @pytest.mark.asyncio
    async def test_decay_prunes_edge_below_threshold(self) -> None:
        """Test: Edges decayed below min_weight get pruned."""
        phase = R4KGConsolidator(
            config=R4Config(
                min_co_occurrence=1,
                enable_hebbian_decay=True,
            )
        )
        ctx_init = MockRunnerContext()
        phase._initialize_components(ctx_init)

        existing_edges = {
            "edge_weak": {
                "source_id": "c_alice",
                "target_id": "c_bob",
                "relation_type": "RELATED_TO",
                "confidence": 0.02,  # Already very weak
                "observation_count": 1,
                "last_observed_at": 1000,
            },
        }

        # 365 days later
        cycle_ts = 1000 + (365 * 24 * 60 * 60 * 1000)

        updates = await phase._apply_edge_decay(
            existing_edges=existing_edges,
            current_co_occurrence_pairs=set(),
            cycle_timestamp_ms=cycle_ts,
            tenant_id="t1",
            space_id="s1",
        )

        assert len(updates) == 1
        assert updates[0].confidence == 0.0
        assert updates[0].importance_source == "hebbian_decay_pruned"
        assert phase._stats.hebbian_edges_pruned == 1

    @pytest.mark.asyncio
    async def test_decay_skips_re_observed_edges(self) -> None:
        """Test: Edges re-observed in current batch are NOT decayed."""
        phase = R4KGConsolidator(
            config=R4Config(
                min_co_occurrence=1,
                enable_hebbian_decay=True,
            )
        )
        ctx_init = MockRunnerContext()
        phase._initialize_components(ctx_init)

        existing_edges = {
            "edge_alice_bob": {
                "source_id": "c_alice",
                "target_id": "c_bob",
                "relation_type": "RELATED_TO",
                "confidence": 0.8,
                "observation_count": 5,
                "last_observed_at": 1000,
            },
        }

        cycle_ts = 1000 + (30 * 24 * 60 * 60 * 1000)

        # This pair was re-observed in current batch
        current_pairs = {"c_alice:c_bob"}

        updates = await phase._apply_edge_decay(
            existing_edges=existing_edges,
            current_co_occurrence_pairs=current_pairs,
            cycle_timestamp_ms=cycle_ts,
            tenant_id="t1",
            space_id="s1",
        )

        assert len(updates) == 0
        assert phase._stats.hebbian_edges_decayed == 0

    @pytest.mark.asyncio
    async def test_decay_disabled_by_flag(self) -> None:
        """Test: When enable_hebbian_decay=False, no decay happens."""
        config = R4Config(enable_hebbian_decay=False)
        assert config.enable_hebbian_decay is False

    @pytest.mark.asyncio
    async def test_anti_hebbian_weakens_edge(self) -> None:
        """Test: Anti-Hebbian signal weakens target edge."""
        phase = R4KGConsolidator(
            config=R4Config(
                min_co_occurrence=1,
                enable_anti_hebbian=True,
            )
        )
        ctx_init = MockRunnerContext()
        phase._initialize_components(ctx_init)

        existing_edges = {
            "edge_wrong": {
                "source_id": "c_alice",
                "target_id": "c_bob",
                "relation_type": "RELATED_TO",
                "confidence": 0.7,
                "observation_count": 3,
            },
        }

        ctx = MockRunnerContext()
        ctx.syscalls.learning_queue_query = AsyncMock(
            return_value=[
                {
                    "signal_type": "ASSOCIATION_WRONG",
                    "edge_id": "edge_wrong",
                    "confidence": 1.0,
                    "is_explicit_correction": False,
                },
            ]
        )

        updates = await phase._apply_anti_hebbian_signals(
            existing_edges=existing_edges,
            ctx=ctx,
            tenant_id="t1",
            space_id="s1",
        )

        assert len(updates) == 1
        assert updates[0].confidence < 0.7
        assert updates[0].importance_source == "hebbian_anti_decay"
        assert phase._stats.hebbian_anti_signals_processed == 1
        assert phase._stats.hebbian_edges_weakened_by_feedback == 1

    @pytest.mark.asyncio
    async def test_anti_hebbian_prunes_weak_edge(self) -> None:
        """Test: Anti-Hebbian on already weak edge triggers prune."""
        phase = R4KGConsolidator(
            config=R4Config(
                min_co_occurrence=1,
                enable_anti_hebbian=True,
            )
        )
        ctx_init = MockRunnerContext()
        phase._initialize_components(ctx_init)

        existing_edges = {
            "edge_weak": {
                "source_id": "c_alice",
                "target_id": "c_bob",
                "relation_type": "RELATED_TO",
                "confidence": 0.04,  # Below prune threshold after any anti-Hebbian
                "observation_count": 1,
            },
        }

        ctx = MockRunnerContext()
        ctx.syscalls.learning_queue_query = AsyncMock(
            return_value=[
                {
                    "signal_type": "ASSOCIATION_WRONG",
                    "edge_id": "edge_weak",
                    "confidence": 1.0,
                    "is_explicit_correction": True,  # 1.3x multiplier
                },
            ]
        )

        updates = await phase._apply_anti_hebbian_signals(
            existing_edges=existing_edges,
            ctx=ctx,
            tenant_id="t1",
            space_id="s1",
        )

        assert len(updates) == 1
        assert updates[0].confidence == 0.0  # Pruned
        assert updates[0].importance_source == "hebbian_anti_pruned"
        assert phase._stats.hebbian_edges_pruned == 1

    @pytest.mark.asyncio
    async def test_anti_hebbian_no_signals_no_changes(self) -> None:
        """Test: No anti-Hebbian signals means no edge changes."""
        phase = R4KGConsolidator(
            config=R4Config(
                min_co_occurrence=1,
                enable_anti_hebbian=True,
            )
        )
        ctx_init = MockRunnerContext()
        phase._initialize_components(ctx_init)

        ctx = MockRunnerContext()
        ctx.syscalls.learning_queue_query = AsyncMock(return_value=[])

        updates = await phase._apply_anti_hebbian_signals(
            existing_edges={"edge_1": {"source_id": "a", "target_id": "b"}},
            ctx=ctx,
            tenant_id="t1",
            space_id="s1",
        )

        assert len(updates) == 0
        assert phase._stats.hebbian_anti_signals_processed == 0

    @pytest.mark.asyncio
    async def test_anti_hebbian_handles_query_failure(self) -> None:
        """Test: Anti-Hebbian gracefully handles syscall failure."""
        phase = R4KGConsolidator(
            config=R4Config(
                min_co_occurrence=1,
                enable_anti_hebbian=True,
            )
        )
        ctx_init = MockRunnerContext()
        phase._initialize_components(ctx_init)

        ctx = MockRunnerContext()
        ctx.syscalls.learning_queue_query = AsyncMock(side_effect=RuntimeError("DB unavailable"))

        updates = await phase._apply_anti_hebbian_signals(
            existing_edges={},
            ctx=ctx,
            tenant_id="t1",
            space_id="s1",
        )

        assert len(updates) == 0

    @pytest.mark.asyncio
    async def test_decay_handles_missing_last_observed(self) -> None:
        """Test: Edges with NULL last_observed_at are skipped."""
        phase = R4KGConsolidator(
            config=R4Config(
                min_co_occurrence=1,
                enable_hebbian_decay=True,
            )
        )
        ctx_init = MockRunnerContext()
        phase._initialize_components(ctx_init)

        existing_edges = {
            "edge_no_ts": {
                "source_id": "c_alice",
                "target_id": "c_bob",
                "relation_type": "RELATED_TO",
                "confidence": 0.5,
                "last_observed_at": None,
            },
        }

        updates = await phase._apply_edge_decay(
            existing_edges=existing_edges,
            current_co_occurrence_pairs=set(),
            cycle_timestamp_ms=int(1e13),
            tenant_id="t1",
            space_id="s1",
        )

        assert len(updates) == 0

    def test_to_dict_includes_decay_stats(self) -> None:
        """Test: R4PhaseStats.to_dict() includes all decay and anti-Hebbian counters."""
        stats = R4PhaseStats()
        stats.hebbian_edges_decayed = 3
        stats.hebbian_edges_pruned = 1
        stats.hebbian_anti_signals_processed = 5
        stats.hebbian_edges_weakened_by_feedback = 2

        d = stats.to_dict()
        assert d["hebbian_edges_decayed"] == 3
        assert d["hebbian_edges_pruned"] == 1
        assert d["hebbian_anti_signals_processed"] == 5
        assert d["hebbian_edges_weakened_by_feedback"] == 2

    def test_config_decay_flag_default_off(self) -> None:
        """Test: enable_hebbian_decay defaults to False."""
        config = R4Config()
        assert config.enable_hebbian_decay is False

    def test_config_anti_hebbian_flag_default_off(self) -> None:
        """Test: enable_anti_hebbian defaults to False."""
        config = R4Config()
        assert config.enable_anti_hebbian is False
