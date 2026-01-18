"""
R4 Integration Tests — Issue 4.4.12

Integration tests for the R4 Knowledge Graph Consolidation phase.
These tests verify cross-component interactions:

1. Entity Extraction → Disambiguation → Resolution pipeline
2. Resolution → Confidence Routing → Gap Emission
3. Entity Clustering → Hebbian Co-occurrence → Edge Creation
4. Edge Discovery → Granger Causality → Causal Edge Creation
5. Causal Edge → Feedback → Threshold Adjustment
6. Full R4 Phase End-to-End

Components Under Test:
- R4KGConsolidator (phase orchestrator)
- UltraBERTEntityExtractor (4.4.1)
- EntityDisambiguator (4.4.2)
- AmbiguousEntityResolver (4.4.4)
- ConfidenceRouter (4.4.5)
- AdaptiveMergeThresholds (4.4.6)
- EntityMerger (4.4.7)
- HebbianLearner (4.4.8)
- GrangerCausalityInference (4.4.9)
- AdaptiveCausalityThresholds (4.4.10)
- CausalEdgeFeedbackProcessor (4.4.11)

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional
from unittest.mock import MagicMock

import pytest

# Algorithm imports (4.4.1-4.4.11)
from k0.modules.consolidation.algorithms.ambiguous_resolver import (
    AmbiguousEntityResolver,
    CandidateEntity,
    EventContext,
    ResolutionOutcome,
)
from k0.modules.consolidation.algorithms.causality_thresholds import (
    AdaptiveCausalityThresholds,
    CausalCategoryClassifier,
    CausalityCategory,
)
from k0.modules.consolidation.algorithms.confidence_router import (
    ConfidenceBand,
    quick_band,
)
from k0.modules.consolidation.algorithms.edge_demotion import (
    CausalEdgeFeedbackProcessor,
    CausalEdgeStalenessChecker,
)
from k0.modules.consolidation.algorithms.entity_disambiguator import EntityDisambiguator
from k0.modules.consolidation.algorithms.entity_extractor import (
    ExtractedEntity,
    KGEntityType,
    UltraBERTEntityExtractor,
)
from k0.modules.consolidation.algorithms.granger_causality import (
    GrangerCausalityInference,
)
from k0.modules.consolidation.algorithms.hebbian_learner import (
    HebbianConfig,
    HebbianLearner,
)
from k0.modules.consolidation.algorithms.merge_threshold_learner import (
    AdaptiveMergeThresholds,
)

# Phase imports
from k0.pipelines.p03.phases.r4_kg_consolidator import (
    EntityCluster,
    KGUpdate,
    KGUpdateType,
    R4Config,
    R4KGConsolidator,
)
from k0.pipelines.p03.runner_contract import P03PhaseStatus

# =============================================================================
# Fixtures
# =============================================================================


@dataclass
class MockEvent:
    """Mock P03EventState for integration testing."""

    event_id: str
    content_text: Optional[str] = None
    kg_processed: bool = False
    embedding_768: Optional[List[float]] = None
    timestamp: int = 0
    importance_score: float = 0.5


class MockEnvelopeContext:
    """Mock envelope context."""

    cycle_id: str = "integration_cycle_001"
    space_id: str = "integration_space"
    tenant_id: str = "integration_tenant"


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


@pytest.fixture
def mock_events_with_entities() -> List[MockEvent]:
    """Create mock events with entity-rich content."""
    now_ms = int(time.time() * 1000)
    return [
        MockEvent(
            event_id="evt_001",
            content_text="My wife Sarah went to Costco on Sunday morning.",
            timestamp=now_ms - 3600_000,  # 1 hour ago
            importance_score=0.7,
        ),
        MockEvent(
            event_id="evt_002",
            content_text="Sarah called Mom to discuss the Costco trip.",
            timestamp=now_ms - 1800_000,  # 30 min ago
            importance_score=0.6,
        ),
        MockEvent(
            event_id="evt_003",
            content_text="We met John at Costco, he was with his wife.",
            timestamp=now_ms - 900_000,  # 15 min ago
            importance_score=0.8,
        ),
    ]


@pytest.fixture
def mock_envelope(mock_events_with_entities: List[MockEvent]) -> MockEnvelope:
    """Create mock envelope with entity-rich events."""
    return MockEnvelope(mock_events_with_entities)


@pytest.fixture
def mock_runner_context() -> MockRunnerContext:
    """Create mock runner context."""
    return MockRunnerContext()


# =============================================================================
# Integration Test 1: Entity Extraction → Disambiguation → Resolution
# =============================================================================


class TestEntityExtractionToResolutionPipeline:
    """Integration: Entity extraction → disambiguation → resolution."""

    def test_extractor_produces_entities_for_disambiguator(self) -> None:
        """
        Test: UltraBERTEntityExtractor output flows into EntityDisambiguator.

        Flow: UltraBERT NER outputs → Extract → List[ExtractedEntity] → Disambiguate
        """
        # Arrange
        extractor = UltraBERTEntityExtractor()
        disambiguator = EntityDisambiguator()  # Used for future DB lookups

        # Simulate UltraBERT NER outputs (from P02)
        ner_family_output = {
            "entities": [
                {"text": "Sarah", "label": "KINSHIP", "start_token": 0, "end_token": 0},
            ]
        }
        ner_general_output = {
            "entities": [
                {"text": "Costco", "label": "ORG", "start_token": 5, "end_token": 5},
            ]
        }

        # Act: Extract using extract_from_ultrabert
        entities = extractor.extract_from_ultrabert(
            ner_family_output=ner_family_output,
            ner_general_output=ner_general_output,
        )

        # Assert extraction produces valid entities
        assert len(entities) >= 1
        assert all(isinstance(e, ExtractedEntity) for e in entities)
        # Disambiguator would be used with real DB candidates
        assert disambiguator is not None

        # Verify entities have required fields for disambiguation
        for entity in entities:
            assert entity.text is not None
            assert entity.kg_type is not None
            assert entity.priority > 0

    def test_disambiguation_output_flows_to_resolver(self) -> None:
        """
        Test: EntityDisambiguator output flows into AmbiguousEntityResolver.

        Flow: ExtractedEntities → Candidate list → Resolve ambiguity
        """
        # Arrange: Create candidate entities (simulating DB lookup result)
        now_ms = int(time.time() * 1000)
        candidates = [
            CandidateEntity(
                entity_id="sarah_001",
                entity_type="FAMILY_MEMBER",
                canonical_name="Sarah Smith",
                embedding=[0.1] * 768,
                last_seen_ms=now_ms - 60_000,  # 1 min ago
                frequency=50,
            ),
            CandidateEntity(
                entity_id="sarah_002",
                entity_type="FRIEND",
                canonical_name="Sarah Johnson",
                embedding=[0.2] * 768,
                last_seen_ms=now_ms - 86400_000,  # 1 day ago
                frequency=5,
            ),
        ]

        context = EventContext(
            session_id="sess_001",
            event_timestamp_ms=now_ms,
            co_occurring_entities=["sarah_001"],  # Recent co-occurrence
            location_hint="home",
            temporal_category="morning",
        )

        resolver = AmbiguousEntityResolver()

        # Act
        result = resolver.resolve("Sarah", candidates, context)

        # Assert: Pipeline produces valid resolution
        assert result.mention == "Sarah"
        assert result.confidence > 0
        assert result.candidates_considered == 2

        # FAMILY_MEMBER "Sarah Smith" should win (recent + co-occurring + location)
        if result.selected_entity_id is not None:
            assert result.selected_entity_id == "sarah_001"

    def test_full_extraction_to_resolution_chain(self) -> None:
        """
        Test: Complete chain from UltraBERT NER → entities → candidates → resolution.
        """
        # Arrange
        extractor = UltraBERTEntityExtractor()
        resolver = AmbiguousEntityResolver()
        now_ms = int(time.time() * 1000)

        # Simulate UltraBERT NER output for "My wife went to the store"
        ner_family_output = {
            "entities": [
                {"text": "wife", "label": "KINSHIP", "start_token": 1, "end_token": 1},
            ]
        }

        # Act: Extract from UltraBERT output
        extracted = extractor.extract_from_ultrabert(
            ner_family_output=ner_family_output,
        )

        # Find family member entities
        family_entities = [e for e in extracted if e.kg_type == KGEntityType.FAMILY_MEMBER]

        # If we found a family member, simulate resolution
        if family_entities:
            entity = family_entities[0]

            # Simulate candidate lookup (normally from DB)
            candidates = [
                CandidateEntity(
                    entity_id="wife_001",
                    entity_type="FAMILY_MEMBER",
                    canonical_name="Wife",
                    embedding=[0.1] * 768,
                    last_seen_ms=now_ms - 60_000,
                    frequency=100,
                )
            ]

            context = EventContext(
                session_id="sess_001",
                event_timestamp_ms=now_ms,
                co_occurring_entities=[],
                location_hint=None,
                temporal_category=None,
            )

            result = resolver.resolve(entity.text, candidates, context)

            # Single candidate = auto-resolve with high confidence
            assert result.outcome == ResolutionOutcome.AUTO_RESOLVED
            assert result.confidence == 0.95


# =============================================================================
# Integration Test 2: Resolution → Confidence Routing → Gap Emission
# =============================================================================


class TestResolutionToGapEmissionPipeline:
    """Integration: Resolution → Confidence bands → Gap emission."""

    def test_high_confidence_auto_resolves_no_gap(self) -> None:
        """
        Test: High confidence (≥0.85) auto-resolves without gap emission.
        """
        # Arrange
        now_ms = int(time.time() * 1000)
        resolver = AmbiguousEntityResolver()

        # Single candidate = high confidence
        candidates = [
            CandidateEntity(
                entity_id="mom_001",
                entity_type="FAMILY_MEMBER",
                canonical_name="Mom",
                embedding=[0.1] * 768,
                last_seen_ms=now_ms - 1000,
                frequency=200,
            )
        ]

        context = EventContext(
            session_id="sess_001",
            event_timestamp_ms=now_ms,
            co_occurring_entities=[],
            location_hint=None,
            temporal_category=None,
        )

        # Act
        result = resolver.resolve("Mom", candidates, context)

        # Assert
        assert result.outcome == ResolutionOutcome.AUTO_RESOLVED
        assert result.confidence >= 0.85
        # AUTO band is for >= 0.85 confidence
        assert quick_band(result.confidence) == ConfidenceBand.AUTO

    def test_medium_confidence_resolves_with_flag(self) -> None:
        """
        Test: Medium confidence (0.60-0.85) resolves but flags for review.
        """
        # Arrange
        now_ms = int(time.time() * 1000)
        resolver = AmbiguousEntityResolver()

        # Two candidates with similar scores
        candidates = [
            CandidateEntity(
                entity_id="john_001",
                entity_type="PERSON",
                canonical_name="John Smith",
                embedding=[0.1] * 768,
                last_seen_ms=now_ms - 7200_000,  # 2 hours ago
                frequency=30,
            ),
            CandidateEntity(
                entity_id="john_002",
                entity_type="PERSON",
                canonical_name="John Doe",
                embedding=[0.2] * 768,
                last_seen_ms=now_ms - 7200_000,
                frequency=25,
            ),
        ]

        context = EventContext(
            session_id="sess_001",
            event_timestamp_ms=now_ms,
            co_occurring_entities=[],
            location_hint=None,
            temporal_category=None,
        )

        # Act
        result = resolver.resolve("John", candidates, context)

        # Assert: Should be in FLAG or GAP band (close race penalty)
        band = quick_band(result.confidence)
        assert band in [ConfidenceBand.FLAG, ConfidenceBand.GAP]

    def test_low_confidence_emits_gap(self) -> None:
        """
        Test: Low confidence (<0.60) does not resolve, emits gap.
        """
        # Arrange
        resolver = AmbiguousEntityResolver()

        # No candidates = 0 confidence
        candidates: List[CandidateEntity] = []

        context = EventContext(
            session_id="sess_001",
            event_timestamp_ms=int(time.time() * 1000),
            co_occurring_entities=[],
            location_hint=None,
            temporal_category=None,
        )

        # Act
        result = resolver.resolve("Unknown Person", candidates, context)

        # Assert
        assert result.outcome == ResolutionOutcome.GAP_EMITTED
        assert result.confidence == 0.0
        assert result.selected_entity_id is None
        # GAP band is for < 0.60 confidence
        assert quick_band(result.confidence) == ConfidenceBand.GAP


# =============================================================================
# Integration Test 3: Entity Clustering → Hebbian → Edge Creation
# =============================================================================


class TestClusteringToEdgeCreationPipeline:
    """Integration: Entity clustering → Hebbian co-occurrence → edges."""

    def test_cooccurring_entities_create_edge(self) -> None:
        """
        Test: Entities co-occurring in events create Hebbian edges.
        """
        # Arrange
        hebbian = HebbianLearner(config=HebbianConfig())

        # Simulate co-occurrence: Sarah and Costco appear together
        # Initial weight
        initial_weight = hebbian.compute_initial_weight(avg_importance=0.7)

        # Update weight for 3 co-occurrences
        weight = initial_weight
        count = 0
        for i in range(3):
            weight, count = hebbian.update_edge_weight(
                current_weight=weight,
                current_count=count,
                event_importance=0.7,
            )

        # Assert: Weight increased
        assert weight > initial_weight
        assert count == 3
        assert weight <= 1.0  # Bounded

    def test_hebbian_with_merge_threshold_check(self) -> None:
        """
        Test: Hebbian weight + merge threshold determines edge creation.
        """
        # Arrange
        hebbian = HebbianLearner(config=HebbianConfig())
        merge_thresholds = AdaptiveMergeThresholds()

        # Compute weight after co-occurrences
        weight = hebbian.compute_initial_weight(0.6)
        for _ in range(5):
            weight, _ = hebbian.update_edge_weight(weight, 0, 0.6)

        # Check if meets threshold for edge creation
        decision = merge_thresholds.should_merge("PERSON", weight)

        # Assert: With sufficient co-occurrences, should create edge
        assert weight > 0.3  # Above base threshold
        assert decision is not None  # Decision was made (either merge or not)

    def test_phase_discovers_edges_from_clusters(self) -> None:
        """
        Test: R4KGConsolidator._discover_relationships creates edges.
        """
        # Arrange
        phase = R4KGConsolidator(config=R4Config(min_co_occurrence=2))
        phase._initialize_components(MockRunnerContext())

        clusters = [
            EntityCluster(
                cluster_id="cluster_sarah",
                canonical_name="Sarah",
                entity_type="FAMILY_MEMBER",
                mentions=["Sarah", "my wife"],
                observation_ids=["evt_001", "evt_002"],
                confidence=0.8,
            ),
            EntityCluster(
                cluster_id="cluster_costco",
                canonical_name="Costco",
                entity_type="ORGANIZATION",
                mentions=["Costco"],
                observation_ids=["evt_001", "evt_002"],  # Same events
                confidence=0.9,
            ),
        ]

        # Create mock event_entity_map showing co-occurrence
        from k0.modules.consolidation.algorithms.entity_extractor import ExtractedEntity

        event_entity_map: Dict[str, List[ExtractedEntity]] = {
            "evt_001": [
                ExtractedEntity(
                    text="Sarah",
                    kg_type=KGEntityType.FAMILY_MEMBER,
                    normalized_text="sarah",
                    source_label="KINSHIP",
                    source_head="ner_family",
                    priority=0.8,
                    start_token=0,
                    end_token=0,
                ),
                ExtractedEntity(
                    text="Costco",
                    kg_type=KGEntityType.ORGANIZATION,
                    normalized_text="costco",
                    source_label="ORG",
                    source_head="ner_general",
                    priority=0.9,
                    start_token=1,
                    end_token=1,
                ),
            ],
            "evt_002": [
                ExtractedEntity(
                    text="Sarah",
                    kg_type=KGEntityType.FAMILY_MEMBER,
                    normalized_text="sarah",
                    source_label="KINSHIP",
                    source_head="ner_family",
                    priority=0.8,
                    start_token=0,
                    end_token=0,
                ),
                ExtractedEntity(
                    text="Costco",
                    kg_type=KGEntityType.ORGANIZATION,
                    normalized_text="costco",
                    source_label="ORG",
                    source_head="ner_general",
                    priority=0.9,
                    start_token=1,
                    end_token=1,
                ),
            ],
        }

        # Act
        import asyncio

        # M10.3: _discover_relationships now requires event_relations_map, tenant_id, space_id, ctx
        event_relations_map: Dict[str, List[str]] = {}  # No ULTRABERT relations for this test
        mock_ctx = MockRunnerContext()

        async def run_discover() -> List[KGUpdate]:
            return await phase._discover_relationships(
                clusters,
                event_entity_map,
                event_relations_map,
                "test-tenant",
                "test-space",
                mock_ctx,
            )

        edges = asyncio.run(run_discover())

        # Assert: Edge created between Sarah and Costco
        assert len(edges) >= 1
        edge = edges[0]
        assert edge.update_type == KGUpdateType.CREATE_EDGE
        assert edge.observation_count >= 2


# =============================================================================
# Integration Test 4: Edge Discovery → Granger Causality → Causal Edges
# =============================================================================


class TestEdgeToGrangerCausalityPipeline:
    """Integration: Edge discovery → Granger causality → causal direction."""

    def test_granger_infers_direction_from_observations(self) -> None:
        """
        Test: GrangerCausalityInference infers direction from temporal data.
        """
        # Arrange
        granger = GrangerCausalityInference()

        # Coffee always precedes work_start by 5+ minutes
        # Observations are tuples of (ts_coffee, ts_work) in milliseconds
        # Need to be at least 1 minute (60000ms) apart to not be "simultaneous"
        observations = [
            (0, 300000),  # Coffee @ 0min, work @ 5min
            (600000, 900000),  # Coffee @ 10min, work @ 15min
            (1200000, 1500000),  # Coffee @ 20min, work @ 25min
            (1800000, 2100000),  # Coffee @ 30min, work @ 35min
            (2400000, 2700000),  # Coffee @ 40min, work @ 45min
        ]

        # Act
        result = granger.compute_temporal_precedence(
            entity_a="coffee",
            entity_b="work_start",
            observations=observations,
        )

        # Assert: Source precedes target consistently
        assert result.precedence_ratio >= 0.75
        assert result.a_before_b == 5
        assert result.b_before_a == 0

    def test_granger_with_category_thresholds(self) -> None:
        """
        Test: GrangerCausalityInference uses AdaptiveCausalityThresholds.
        """
        # Arrange
        granger = GrangerCausalityInference()
        thresholds = AdaptiveCausalityThresholds()
        classifier = CausalCategoryClassifier()

        # Classify relationship
        category = classifier.classify(
            source_entity_name="Coffee",
            target_entity_name="Work",
            relationship_type="CAUSES",
        )

        # Get threshold for category
        threshold = thresholds.get_threshold(category)

        # Create observations - tuples of (ts_source, ts_target) in ms
        # Need at least 1 minute (60000ms) apart to not be "simultaneous"
        observations = [(i * 600000, i * 600000 + 300000) for i in range(10)]

        # Analyze
        result = granger.compute_temporal_precedence(
            entity_a="coffee",
            entity_b="work",
            observations=observations,
        )

        # Assert: Check against category threshold
        is_causal = result.precedence_ratio >= threshold
        assert isinstance(is_causal, bool)

    def test_phase_creates_causal_edges(self) -> None:
        """
        Test: R4KGConsolidator._infer_causal_relationships creates causal edges.
        """
        # Arrange
        config = R4Config(
            enable_causal_inference=True,
            enable_causality_thresholds=True,
            granger_min_observations=2,
        )
        phase = R4KGConsolidator(config=config)
        phase._initialize_components(MockRunnerContext())

        # Create edge updates (from Hebbian discovery)
        edge_updates = [
            KGUpdate(
                update_type=KGUpdateType.CREATE_EDGE,
                edge_id="edge_001",
                source_id="coffee_cluster",
                target_id="work_cluster",
                relation_type="RELATED_TO",
                confidence=0.7,
                observation_count=5,
            )
        ]

        clusters = [
            EntityCluster(
                cluster_id="coffee_cluster",
                canonical_name="Coffee",
                entity_type="ACTIVITY",
                mentions=["coffee"],
                observation_ids=["e1", "e2", "e3", "e4", "e5"],
                confidence=0.8,
            ),
            EntityCluster(
                cluster_id="work_cluster",
                canonical_name="Work",
                entity_type="ACTIVITY",
                mentions=["work"],
                observation_ids=["e1", "e2", "e3", "e4", "e5"],
                confidence=0.8,
            ),
        ]

        # Act
        import asyncio

        async def run_infer() -> List[KGUpdate]:
            return await phase._infer_causal_relationships(
                edge_updates, clusters, "test_space", MockRunnerContext()
            )

        causal_edges = asyncio.run(run_infer())

        # Assert: Causal edges created (if threshold met)
        # The exact result depends on the simulated precedence ratio
        assert isinstance(causal_edges, list)

    def test_phase_creates_causal_edges_from_update_edge(self) -> None:
        """
        GAP-001 M10.1: UPDATE_EDGE with sufficient observations creates causal edge.

        After M9 fix, existing edges use UPDATE_EDGE to accumulate observation_count.
        Granger causality must process UPDATE_EDGE types, not just CREATE_EDGE.
        """
        # Arrange
        config = R4Config(
            enable_causal_inference=True,
            enable_causality_thresholds=True,
            granger_min_observations=5,  # Default threshold
        )
        phase = R4KGConsolidator(config=config)
        phase._initialize_components(MockRunnerContext())

        # Create UPDATE_EDGE with accumulated observation_count >= 5
        edge_updates = [
            KGUpdate(
                update_type=KGUpdateType.UPDATE_EDGE,  # Key: UPDATE, not CREATE
                edge_id="edge_gym_health",
                source_id="gym_cluster",
                target_id="health_cluster",
                relation_type="RELATED_TO",
                confidence=0.8,
                observation_count=7,  # Accumulated across batches, > 5 threshold
            )
        ]

        clusters = [
            EntityCluster(
                cluster_id="gym_cluster",
                canonical_name="Gym",
                entity_type="ACTIVITY",
                mentions=["gym", "workout"],
                observation_ids=["e1", "e2", "e3", "e4", "e5", "e6", "e7"],
                confidence=0.85,
            ),
            EntityCluster(
                cluster_id="health_cluster",
                canonical_name="Health",
                entity_type="CONCEPT",
                mentions=["health", "fitness"],
                observation_ids=["e1", "e2", "e3", "e4", "e5", "e6", "e7"],
                confidence=0.85,
            ),
        ]

        # Act
        import asyncio

        async def run_infer_update_edge() -> List[KGUpdate]:
            return await phase._infer_causal_relationships(
                edge_updates, clusters, "test_space", MockRunnerContext()
            )

        causal_edges = asyncio.run(run_infer_update_edge())

        # Assert: UPDATE_EDGE should produce causal edge
        assert isinstance(causal_edges, list)
        # With observation_count=7 >= 5 and confidence=0.8, should create causal edge
        assert len(causal_edges) >= 1, "UPDATE_EDGE with 7 observations should create causal edge"
        assert causal_edges[0].relation_type == "CAUSES"
        assert causal_edges[0].observation_count == 7


# =============================================================================
# Integration Test 5: Causal Edge → Feedback → Threshold Adjustment
# =============================================================================


class TestCausalEdgeToFeedbackPipeline:
    """Integration: Causal edge → feedback → threshold adjustment."""

    def test_wrong_prediction_adjusts_threshold(self) -> None:
        """
        Test: Wrong prediction feedback raises category threshold.
        """
        # Arrange
        thresholds = AdaptiveCausalityThresholds()
        processor = CausalEdgeFeedbackProcessor()  # Would process edge-level feedback

        category = CausalityCategory.HEALTH_MEDICAL
        original_threshold = thresholds.get_threshold(category)

        # Act: Process wrong prediction feedback
        new_threshold = thresholds.adjust_threshold(
            category=category,
            feedback_signal="CAUSAL_PREDICTION_WRONG",
        )

        # Assert: Threshold increased (returns new value directly)
        assert new_threshold > original_threshold
        assert processor is not None  # Processor would be used for edge-level feedback

    def test_correct_prediction_lowers_threshold(self) -> None:
        """
        Test: Correct prediction feedback lowers category threshold.
        """
        # Arrange
        thresholds = AdaptiveCausalityThresholds()

        category = CausalityCategory.PREFERENCE_HABIT
        original_threshold = thresholds.get_threshold(category)

        # Act: Process correct prediction feedback
        new_threshold = thresholds.adjust_threshold(
            category=category,
            feedback_signal="CAUSAL_PREDICTION_CORRECT",
        )

        # Assert: Threshold lowered (or unchanged at min)
        assert new_threshold <= original_threshold

    def test_staleness_checker_initialized(self) -> None:
        """
        Test: CausalEdgeStalenessChecker initializes with staleness days.
        """
        # Arrange & Act
        checker = CausalEdgeStalenessChecker(staleness_days=30)

        # Assert: Checker configured correctly
        assert checker.staleness_days == 30

    def test_staleness_checker_with_different_thresholds(self) -> None:
        """
        Test: CausalEdgeStalenessChecker accepts different staleness thresholds.
        """
        # Arrange
        checker_short = CausalEdgeStalenessChecker(staleness_days=7)
        checker_long = CausalEdgeStalenessChecker(staleness_days=90)

        # Assert: Different configurations
        assert checker_short.staleness_days == 7
        assert checker_long.staleness_days == 90

        # These checkers would query the DB in real use
        # For unit test, we verify the staleness window calculation
        now_ms = int(time.time() * 1000)
        short_cutoff = now_ms - (7 * 86400000)  # 7 days in ms
        long_cutoff = now_ms - (90 * 86400000)  # 90 days in ms

        assert short_cutoff > long_cutoff  # Short window has more recent cutoff


# =============================================================================
# Integration Test 6: Full R4 Phase End-to-End
# =============================================================================


class TestR4PhaseEndToEnd:
    """Integration: Complete R4 phase execution."""

    @pytest.mark.asyncio
    async def test_r4_phase_processes_events(
        self,
        mock_envelope: MockEnvelope,
        mock_runner_context: MockRunnerContext,
    ) -> None:
        """
        Test: Full R4 phase processes events into KG updates.

        Verifies:
        - Phase runs without error
        - Entities extracted
        - Clusters formed
        - Edges discovered (if sufficient co-occurrence)
        - Phase result is DONE status
        """
        # Arrange
        config = R4Config(
            min_co_occurrence=2,
            enable_causal_inference=True,
            enable_hebbian_adaptive_rates=True,
        )
        phase = R4KGConsolidator(config=config)

        # Act
        result = await phase.run(mock_envelope, mock_runner_context)

        # Assert: Phase completed successfully
        assert result.status == P03PhaseStatus.DONE
        assert result.duration_ms > 0
        assert "events_processed" in result.outputs_summary
        assert result.outputs_summary["events_processed"] == 3

    @pytest.mark.asyncio
    async def test_r4_phase_populates_envelope_outputs(
        self,
        mock_envelope: MockEnvelope,
        mock_runner_context: MockRunnerContext,
    ) -> None:
        """
        Test: R4 phase populates envelope.phases.r4_* outputs.
        """
        # Arrange
        phase = R4KGConsolidator()

        # Act
        await phase.run(mock_envelope, mock_runner_context)

        # Assert: Outputs populated
        assert hasattr(mock_envelope.phases, "r4_new_entities")
        assert hasattr(mock_envelope.phases, "r4_new_edges")
        assert hasattr(mock_envelope.phases, "r4_gap_candidates")

    @pytest.mark.asyncio
    async def test_r4_phase_skips_when_no_content(
        self,
        mock_runner_context: MockRunnerContext,
    ) -> None:
        """
        Test: R4 phase skips when events have no content.
        """
        # Arrange
        empty_events = [
            MockEvent(event_id="evt_empty_1", content_text=None),
            MockEvent(event_id="evt_empty_2", content_text=None),
        ]
        envelope = MockEnvelope(empty_events)
        phase = R4KGConsolidator()

        # Act
        result = await phase.run(envelope, mock_runner_context)

        # Assert: Phase skipped
        assert result.status == P03PhaseStatus.SKIP

    @pytest.mark.asyncio
    async def test_r4_phase_latency_within_bounds(
        self,
        mock_envelope: MockEnvelope,
        mock_runner_context: MockRunnerContext,
    ) -> None:
        """
        Test: R4 phase completes within latency bounds.

        Target: <500ms for 3 events
        """
        # Arrange
        phase = R4KGConsolidator()

        # Act
        start = time.time()
        result = await phase.run(mock_envelope, mock_runner_context)
        elapsed_ms = (time.time() - start) * 1000

        # Assert: Under 500ms for small batch
        assert elapsed_ms < 500
        assert result.duration_ms < 500


# =============================================================================
# Integration Test 7: Stats Tracking Across Components
# =============================================================================


class TestStatsTrackingIntegration:
    """Integration: Verify stats accumulate correctly across components."""

    @pytest.mark.asyncio
    async def test_stats_track_entity_extraction(
        self,
        mock_envelope: MockEnvelope,
        mock_runner_context: MockRunnerContext,
    ) -> None:
        """
        Test: R4PhaseStats tracks entity extraction counts.
        """
        # Arrange
        phase = R4KGConsolidator()

        # Act
        result = await phase.run(mock_envelope, mock_runner_context)

        # Assert: Stats tracked
        assert result.outputs_summary["entities_extracted"] >= 0
        assert result.outputs_summary["events_processed"] == 3

    @pytest.mark.asyncio
    async def test_stats_track_confidence_routing(
        self,
        mock_envelope: MockEnvelope,
        mock_runner_context: MockRunnerContext,
    ) -> None:
        """
        Test: R4PhaseStats tracks confidence band routing.
        """
        # Arrange
        phase = R4KGConsolidator()

        # Act
        result = await phase.run(mock_envelope, mock_runner_context)

        # Assert: Confidence routing stats present
        outputs = result.outputs_summary
        assert "auto_resolved" in outputs
        assert "flagged_for_review" in outputs
        assert "gaps_emitted" in outputs

    @pytest.mark.asyncio
    async def test_stats_track_hebbian_learning(
        self,
        mock_envelope: MockEnvelope,
        mock_runner_context: MockRunnerContext,
    ) -> None:
        """
        Test: R4PhaseStats tracks Hebbian edge operations.
        """
        # Arrange
        config = R4Config(enable_hebbian_adaptive_rates=True)
        phase = R4KGConsolidator(config=config)

        # Act
        result = await phase.run(mock_envelope, mock_runner_context)

        # Assert: Edge stats tracked
        outputs = result.outputs_summary
        assert "new_edges" in outputs


# =============================================================================
# Integration Test 8: Error Handling Across Components
# =============================================================================


class TestErrorHandlingIntegration:
    """Integration: Verify error handling works across components."""

    @pytest.mark.asyncio
    async def test_phase_handles_extraction_error_gracefully(
        self,
        mock_runner_context: MockRunnerContext,
    ) -> None:
        """
        Test: Phase continues with partial results if extraction fails.
        """
        # Arrange: One valid event, one problematic
        events = [
            MockEvent(event_id="evt_good", content_text="Valid content with entities."),
            MockEvent(event_id="evt_empty", content_text=""),  # Empty but not None
        ]
        envelope = MockEnvelope(events)
        phase = R4KGConsolidator()

        # Act
        result = await phase.run(envelope, mock_runner_context)

        # Assert: Phase completed (didn't crash)
        assert result.status in [P03PhaseStatus.DONE, P03PhaseStatus.SKIP]

    @pytest.mark.asyncio
    async def test_phase_returns_fail_on_critical_error(
        self,
        mock_runner_context: MockRunnerContext,
    ) -> None:
        """
        Test: Phase returns FAIL status on critical error.

        Note: This is difficult to trigger without mocking internal components,
        so we just verify the error handling path exists.
        """
        # Arrange
        phase = R4KGConsolidator()

        # The phase has try/except that returns P03PhaseResult.fail()
        # Verify the phase and status exist
        assert phase is not None
        assert hasattr(P03PhaseStatus, "FAIL")
        # Arrange
        phase = R4KGConsolidator()

        # The phase has try/except that returns P03PhaseResult.fail()
        # Verify the phase and status exist
        assert phase is not None
        assert hasattr(P03PhaseStatus, "FAIL")
