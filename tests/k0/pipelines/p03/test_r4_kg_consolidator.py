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
from unittest.mock import MagicMock, patch

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
        assert config.min_co_occurrence == 2
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
        assert config.granger_min_observations == 5
        assert config.granger_precedence_threshold == 0.75
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
            )
        ]

        phase._populate_phase_outputs(envelope, [], edge_updates, [])  # type: ignore[arg-type]

        assert len(envelope.phases.r4_new_edges) == 1
        edge = envelope.phases.r4_new_edges[0]
        assert edge.edge_id == "edge_001"
        assert edge.source_entity_id == "entity_001"
        assert edge.target_entity_id == "entity_002"
        assert edge.relationship_type == "RELATED_TO"

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
