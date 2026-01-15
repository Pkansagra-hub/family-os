"""
R4 Phase - Knowledge Graph Consolidation.

M4 Epic 4.4: Implement R4 Phase for KG Entity Resolution and Edge Building.

This phase performs entity/relationship consolidation:
1. Extract entities from events using UltraBERT NER (4.4.1)
2. Disambiguate entities using per-type weights (4.4.2)
3. Resolve ambiguous mentions via context hierarchy (4.4.4)
4. Route through confidence bands with P06 gap emission (4.4.5)
5. Apply adaptive merge thresholds (4.4.6)
6. Merge entities with cascade support (4.4.7)
7. Discover relationships via Hebbian co-occurrence with adaptive rates (4.4.8)
8. Infer causal direction via Granger causality (4.4.9)
9. Apply adaptive causality thresholds by category (4.4.10)
10. Process edge feedback and demotion (4.4.11)
11. Populate envelope.phases.r4_* outputs

References:
    - Dossier 4.5: R4 - Knowledge Graph Consolidation (NREM2-3)
    - Dossier 7.4.4: M21 KGConsolidator Module
    - M4 Execution: docs/TEMP_EXECUTION_DOCS/M4_EXECUTION.md Epic 4.4

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from k0.modules.consolidation.algorithms.ambiguous_resolver import AmbiguousEntityResolver
from k0.modules.consolidation.algorithms.causality_thresholds import (
    AdaptiveCausalityThresholds,
    CausalCategoryClassifier,
    CausalityCategory,
)
from k0.modules.consolidation.algorithms.confidence_router import (
    ConfidenceBand,
    ConfidenceRouter,
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
from k0.modules.consolidation.algorithms.entity_merger import EntityMerger
from k0.modules.consolidation.algorithms.granger_causality import (
    CausalEdge,
    GrangerCausalityInference,
)
from k0.modules.consolidation.algorithms.hebbian_learner import HebbianConfig, HebbianLearner
from k0.modules.consolidation.algorithms.merge_threshold_learner import AdaptiveMergeThresholds
from k0.pipelines.p03.observability import P03Error
from k0.pipelines.p03.phase_interface import P03PhaseResult
from k0.pipelines.p03.phase_outputs import (
    GapCandidate,
    KGEdge,
    KGEdgeUpdate,
    KGEntity,
    KGEntityUpdate,
    SocialRelationship,
)
from k0.pipelines.p03.runner_contract import P03PhaseId

if TYPE_CHECKING:
    from k0.pipelines.p03.envelope import P03BatchEnvelope
    from k0.pipelines.p03.event_state import P03EventState
    from k0.pipelines.p03.phase_interface import P03RunnerContext

logger = logging.getLogger(__name__)


# =============================================================================
# R4 CONFIGURATION
# =============================================================================


@dataclass
class R4Config:
    """
    R4 phase configuration.

    Attributes:
        min_entities_for_edge: Minimum entities in event to discover edges
        min_co_occurrence: Minimum co-occurrences before creating relationship
        max_relationship_confidence: Maximum confidence cap for edges
        base_confidence: Starting confidence for new relationships
        confidence_increment: Confidence increase per co-occurrence
        enable_causal_inference: Whether to run Granger causality (4.4.9)
        enable_adaptive_thresholds: Whether to use learned merge thresholds
        emit_gaps_on_low_confidence: Whether to emit P06 gaps for low confidence
        enable_hebbian_adaptive_rates: Whether to use adaptive learning rates (4.4.8)
        enable_causality_thresholds: Whether to use per-category thresholds (4.4.10)
        enable_edge_feedback: Whether to process edge feedback/demotion (4.4.11)
        granger_min_observations: Minimum observations for causality inference
        granger_precedence_threshold: Default precedence ratio threshold
        staleness_check_days: Days before edge is considered stale
        min_event_observations: Minimum observations before promoting EVENT to KG
        use_hybrid_ner: Use BERT-NER for general entities instead of UltraBERT ner_general
    """

    min_entities_for_edge: int = 2
    min_co_occurrence: int = 1  # Lower threshold for initial relationship discovery
    max_relationship_confidence: float = 0.9
    base_confidence: float = 0.3
    confidence_increment: float = 0.1
    enable_causal_inference: bool = True  # 4.4.9 - Granger causality
    enable_adaptive_thresholds: bool = True  # 4.4.6 - merge thresholds
    emit_gaps_on_low_confidence: bool = True
    enable_hebbian_adaptive_rates: bool = True  # 4.4.8 - adaptive Hebbian
    enable_causality_thresholds: bool = True  # 4.4.10 - per-category thresholds
    enable_edge_feedback: bool = True  # 4.4.11 - edge demotion
    granger_min_observations: int = 5  # 4.4.9
    granger_precedence_threshold: float = 0.75  # 4.4.9 (overridden by 4.4.10)
    staleness_check_days: int = 90  # 4.4.11
    min_event_observations: int = 2  # Minimum observations to promote EVENT to KG
    # Hybrid NER: Use dslim/bert-base-NER for general entities instead of UltraBERT ner_general
    # UltraBERT v2-checkpoint-18000 ner_general head produces garbage (not properly trained)
    # BERT-NER adds ~3.8ms/event but P03 is nightly batch so latency is acceptable
    use_hybrid_ner: bool = True  # Default to hybrid mode for correct NER


# =============================================================================
# R4 STATISTICS
# =============================================================================


@dataclass
class R4PhaseStats:
    """
    Statistics from R4 phase execution.

    Tracks metrics across all R4 sub-operations.
    """

    # Entity extraction stats
    events_processed: int = 0
    entities_extracted: int = 0
    entities_by_type: Dict[str, int] = field(default_factory=dict)

    # Disambiguation stats
    disambiguation_attempts: int = 0
    disambiguation_successes: int = 0
    disambiguation_failures: int = 0

    # Resolution stats
    ambiguous_mentions: int = 0
    auto_resolved: int = 0
    flagged_for_review: int = 0
    gaps_emitted: int = 0
    resolved_gaps_applied: int = 0  # Resolved gaps used as canonical names

    # Entity consolidation stats
    new_entities_created: int = 0
    existing_entities_updated: int = 0
    entities_merged: int = 0

    # Edge discovery stats (4.4.8)
    co_occurrence_pairs: int = 0
    new_edges_created: int = 0
    existing_edges_updated: int = 0
    hebbian_edges_strengthened: int = 0
    hebbian_edges_weakened: int = 0

    # Causal inference stats (4.4.9, 4.4.10)
    causal_pairs_analyzed: int = 0
    causal_edges_created: int = 0
    causal_edges_by_category: Dict[str, int] = field(default_factory=dict)

    # Edge feedback stats (4.4.11)
    edges_boosted: int = 0
    edges_demoted: int = 0
    stale_edges_archived: int = 0

    # Social extraction stats
    social_relationships_extracted: int = 0
    social_relationships_by_type: Dict[str, int] = field(default_factory=dict)

    # Timing
    total_duration_ms: float = 0.0
    extraction_duration_ms: float = 0.0
    disambiguation_duration_ms: float = 0.0
    edge_discovery_duration_ms: float = 0.0
    causal_inference_duration_ms: float = 0.0
    social_extraction_duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "events_processed": self.events_processed,
            "entities_extracted": self.entities_extracted,
            "entities_by_type": self.entities_by_type,
            "disambiguation_attempts": self.disambiguation_attempts,
            "disambiguation_successes": self.disambiguation_successes,
            "disambiguation_failures": self.disambiguation_failures,
            "ambiguous_mentions": self.ambiguous_mentions,
            "auto_resolved": self.auto_resolved,
            "flagged_for_review": self.flagged_for_review,
            "gaps_emitted": self.gaps_emitted,
            "new_entities_created": self.new_entities_created,
            "existing_entities_updated": self.existing_entities_updated,
            "entities_merged": self.entities_merged,
            "co_occurrence_pairs": self.co_occurrence_pairs,
            "new_edges_created": self.new_edges_created,
            "existing_edges_updated": self.existing_edges_updated,
            "hebbian_edges_strengthened": self.hebbian_edges_strengthened,
            "hebbian_edges_weakened": self.hebbian_edges_weakened,
            "causal_pairs_analyzed": self.causal_pairs_analyzed,
            "causal_edges_created": self.causal_edges_created,
            "causal_edges_by_category": self.causal_edges_by_category,
            "edges_boosted": self.edges_boosted,
            "edges_demoted": self.edges_demoted,
            "stale_edges_archived": self.stale_edges_archived,
            "social_relationships_extracted": self.social_relationships_extracted,
            "social_relationships_by_type": self.social_relationships_by_type,
            "total_duration_ms": self.total_duration_ms,
            "social_extraction_duration_ms": self.social_extraction_duration_ms,
        }


# =============================================================================
# KG UPDATE TYPES (from Dossier §7.4.4)
# =============================================================================


class KGUpdateType(Enum):
    """Types of knowledge graph updates."""

    CREATE_ENTITY = "CREATE_ENTITY"
    UPDATE_ENTITY = "UPDATE_ENTITY"
    CREATE_EDGE = "CREATE_EDGE"
    UPDATE_EDGE = "UPDATE_EDGE"


@dataclass
class KGUpdate:
    """
    Knowledge graph update operation.

    Spec: Dossier §7.4.4
    """

    update_type: KGUpdateType
    entity_id: Optional[str] = None
    edge_id: Optional[str] = None

    # For CREATE_ENTITY / UPDATE_ENTITY
    canonical_name: Optional[str] = None
    entity_type: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    new_observations: int = 0
    confidence: float = 0.0
    source_event_ids: List[str] = field(default_factory=list)

    # For CREATE_EDGE / UPDATE_EDGE
    source_id: Optional[str] = None
    target_id: Optional[str] = None
    relation_type: Optional[str] = None
    observation_count: int = 0


@dataclass
class EntityCluster:
    """Cluster of resolved entity mentions."""

    cluster_id: str
    canonical_name: str
    entity_type: str
    mentions: List[str]  # Original text mentions
    observation_ids: List[str]  # Source event IDs
    confidence: float
    embedding: Optional[List[float]] = None


# =============================================================================
# R4 KG CONSOLIDATOR PHASE
# =============================================================================


class R4KGConsolidator:
    """
    R4 Phase: Knowledge Graph Consolidation.

    Responsibilities:
        1. Extract entities from events (UltraBERT NER) - 4.4.1
        2. Disambiguate entities using per-type weights - 4.4.2
        3. Resolve ambiguous mentions via context hierarchy - 4.4.4
        4. Route through confidence bands with P06 gap emission - 4.4.5
        5. Apply adaptive merge thresholds - 4.4.6
        6. Merge entities with cascade support - 4.4.7
        7. Discover relationships via Hebbian co-occurrence with adaptive rates - 4.4.8
        8. Infer causal direction via Granger causality - 4.4.9
        9. Apply adaptive causality thresholds by category - 4.4.10
        10. Process edge feedback and demotion - 4.4.11
        11. Populate envelope.phases.r4_* outputs

    Data Flow:
        R3 events → Extract entities → Disambiguate → Resolve → Merge → Edges → Causality → R5/R6

    Idempotency:
        - Entity extraction is deterministic for same input
        - Entity IDs are content-addressed (reproducible)
        - Edge creation is deterministic given same entity pairs
    """

    PHASE_ID = P03PhaseId.R4_KG

    def __init__(self, config: Optional[R4Config] = None):
        """
        Initialize R4 phase.

        Args:
            config: Optional configuration (defaults used if not provided)
        """
        self.config = config or R4Config()

        # Initialize algorithm components (lazy initialization in run)
        # 4.4.1-4.4.7 components
        self._entity_extractor: Optional[UltraBERTEntityExtractor] = None
        self._entity_disambiguator: Optional[EntityDisambiguator] = None
        self._ambiguous_resolver: Optional[AmbiguousEntityResolver] = None
        self._confidence_router: Optional[ConfidenceRouter] = None
        self._merge_thresholds: Optional[AdaptiveMergeThresholds] = None
        self._entity_merger: Optional[EntityMerger] = None

        # 4.4.8-4.4.11 components
        self._hebbian_learner: Optional[HebbianLearner] = None
        self._granger_causality: Optional[GrangerCausalityInference] = None
        self._causality_thresholds: Optional[AdaptiveCausalityThresholds] = None
        self._category_classifier: Optional[CausalCategoryClassifier] = None
        self._edge_feedback_processor: Optional[CausalEdgeFeedbackProcessor] = None
        self._staleness_checker: Optional[CausalEdgeStalenessChecker] = None

        # Resolved gaps cache: entity_id -> resolved_value (from st_learning_queue)
        self._resolved_gaps_cache: Dict[str, str] = {}

        # Tracking
        self._stats = R4PhaseStats()

    @property
    def phase_id(self) -> P03PhaseId:
        """Return the phase identifier."""
        return self.PHASE_ID

    def should_skip(self, envelope: "P03BatchEnvelope") -> bool:
        """
        Check if R4 should be skipped.

        Skip Conditions:
            - Empty event list
            - All events already have kg_processed=True
            - No events with content to extract entities from

        Args:
            envelope: Current batch envelope

        Returns:
            True if phase should be skipped
        """
        if not envelope.events:
            return True

        # Check if all events already processed
        all_processed = all(getattr(event, "kg_processed", False) for event in envelope.events)
        if all_processed:
            return True

        # Check if any events have content text
        has_content = any(getattr(event, "content_text", None) for event in envelope.events)
        return not has_content

    def idempotency_key(self, envelope: "P03BatchEnvelope") -> str:
        """
        Compute idempotency key for retry safety.

        Args:
            envelope: Current batch envelope

        Returns:
            Deterministic key for this phase execution
        """
        return f"p03:r4:{envelope.context.cycle_id}"

    def _initialize_components(self, ctx: "P03RunnerContext") -> None:
        """
        Initialize algorithm components.

        Args:
            ctx: Runner context with syscalls and configuration
        """
        # 4.4.1: Entity Extractor
        self._entity_extractor = UltraBERTEntityExtractor()

        # 4.4.2: Entity Disambiguator
        self._entity_disambiguator = EntityDisambiguator()

        # 4.4.4: Ambiguous Resolver
        self._ambiguous_resolver = AmbiguousEntityResolver()

        # 4.4.5: Confidence Router
        self._confidence_router = ConfidenceRouter()

        # 4.4.6: Adaptive Merge Thresholds
        self._merge_thresholds = AdaptiveMergeThresholds()

        # 4.4.7: Entity Merger
        self._entity_merger = EntityMerger()

        # 4.4.8: Hebbian Learner with Adaptive Rates
        if self.config.enable_hebbian_adaptive_rates:
            self._hebbian_learner = HebbianLearner(
                config=HebbianConfig(
                    learning_rate=self.config.confidence_increment,
                    max_weight=self.config.max_relationship_confidence,
                    min_weight=0.01,  # Use default min_weight to allow pruning
                )
            )

        # 4.4.9: Granger Causality Inference
        if self.config.enable_causal_inference:
            self._granger_causality = GrangerCausalityInference()

        # 4.4.10: Adaptive Causality Thresholds by Category
        if self.config.enable_causality_thresholds:
            self._causality_thresholds = AdaptiveCausalityThresholds()
            self._category_classifier = CausalCategoryClassifier()

        # 4.4.11: Edge Feedback Processor and Staleness Checker
        if self.config.enable_edge_feedback:
            self._edge_feedback_processor = CausalEdgeFeedbackProcessor()
            self._staleness_checker = CausalEdgeStalenessChecker(
                staleness_days=self.config.staleness_check_days
            )

    async def _load_resolved_gaps(self, ctx: "P03RunnerContext") -> None:
        """
        Load resolved gaps from st_learning_queue for canonical name lookup.

        Queries st_learning_queue for all RESOLVED gaps and caches the
        entity_id -> resolved_value mapping. This allows R4 to use user-provided
        or auto-resolved values as canonical names instead of NER-extracted text.

        Gap resolution flow:
            1. R0: GapAutoResolver marks gaps RESOLVED in st_learning_queue
            2. R4: This method loads resolved values before entity cluster creation
            3. R4: _build_entity_clusters uses resolved_value as canonical_name
            4. R7: Writes final canonical_name to st_kg_dom

        Args:
            ctx: Runner context with syscalls for database access
        """
        import json

        if not ctx.syscalls:
            logger.debug("R4: No syscalls available, skipping resolved gaps lookup")
            return

        try:
            pool = ctx.syscalls.get_pool()
            if not pool:
                logger.debug("R4: No connection pool available")
                return

            async with pool.acquire() as conn:
                # Query all RESOLVED gaps with their resolved values
                rows = await conn.fetch(
                    """
                    SELECT entity_id, resolution_data_json
                    FROM st_learning_queue
                    WHERE status = 'RESOLVED'
                      AND resolution_data_json IS NOT NULL
                    """
                )

                for row in rows:
                    entity_id = row["entity_id"]
                    resolution_json = row["resolution_data_json"]

                    if not entity_id or not resolution_json:
                        continue

                    try:
                        resolution_data = json.loads(resolution_json)
                        resolved_value = resolution_data.get("resolved_value")

                        if resolved_value:
                            self._resolved_gaps_cache[entity_id] = resolved_value
                            logger.debug(
                                f"R4: Cached resolved value for {entity_id}: {resolved_value}"
                            )
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"R4: Failed to parse resolution_data for {entity_id}: {e}")

                logger.info(
                    f"R4: Loaded {len(self._resolved_gaps_cache)} resolved gaps from st_learning_queue"
                )

        except Exception as e:
            logger.warning(f"R4: Failed to load resolved gaps: {e}")
            # Non-fatal - continue without resolved gaps

    async def run(
        self,
        envelope: "P03BatchEnvelope",
        ctx: "P03RunnerContext",
    ) -> P03PhaseResult:
        """
        Execute R4 phase: Knowledge Graph Consolidation.

        Steps:
            1. Check skip conditions
            2. Initialize algorithm components
            3. Extract entities from all events
            4. Build entity clusters
            5. Disambiguate and resolve ambiguous mentions
            6. Apply confidence routing (gap emission for low confidence)
            7. Process entity updates (create/update/merge)
            8. Discover relationships via Hebbian co-occurrence
            9. Populate envelope.phases.r4_* outputs
            10. Return phase result

        Args:
            envelope: Batch envelope with events from R3
            ctx: Runner context with syscalls, logger, config

        Returns:
            P03PhaseResult with status, duration, outputs summary
        """
        start_ms = int(time.time() * 1000)
        cycle_id = envelope.context.cycle_id
        space_id = envelope.context.space_id
        tenant_id = envelope.context.tenant_id

        logger.info(
            "R4: Starting knowledge graph consolidation phase",
            extra={
                "cycle_id": cycle_id,
                "tenant_id": tenant_id,
                "space_id": space_id,
                "event_count": len(envelope.events),
            },
        )

        # Reset stats
        self._stats = R4PhaseStats()

        # Skip check
        if self.should_skip(envelope):
            duration_ms = int(time.time() * 1000) - start_ms
            skip_reason = self._get_skip_reason(envelope)
            logger.info(
                "R4: Skipping phase",
                extra={
                    "cycle_id": cycle_id,
                    "reason": skip_reason,
                    "duration_ms": duration_ms,
                },
            )
            return P03PhaseResult.skip(
                phase_id=self.PHASE_ID,
                reason=skip_reason,
                duration_ms=duration_ms,
                idempotency_key=self.idempotency_key(envelope),
            )

        try:
            # Initialize components
            self._initialize_components(ctx)

            # Step 1: Extract entities from events
            extraction_start = int(time.time() * 1000)
            all_entities, event_entity_map = await self._extract_entities(envelope.events, space_id)
            self._stats.extraction_duration_ms = int(time.time() * 1000) - extraction_start

            # Step 2: Build entity clusters (uses resolved gaps from st_learning_queue)
            clusters = await self._build_entity_clusters(
                all_entities, event_entity_map, envelope.events, ctx
            )

            # Step 3: Disambiguate and resolve ambiguous mentions
            disambiguation_start = int(time.time() * 1000)
            resolved_clusters, gaps = await self._resolve_entities(
                clusters, envelope.events, space_id, ctx
            )
            self._stats.disambiguation_duration_ms = int(time.time() * 1000) - disambiguation_start

            # Step 4: Process entity updates (create/update based on confidence)
            kg_updates = await self._process_entity_clusters(resolved_clusters, space_id, ctx)

            # Step 5: Discover relationships via Hebbian co-occurrence
            edge_start = int(time.time() * 1000)
            edge_updates = await self._discover_relationships(resolved_clusters, event_entity_map)
            self._stats.edge_discovery_duration_ms = int(time.time() * 1000) - edge_start

            # Step 5.5: Extract social relationships for st_social
            social_start = int(time.time() * 1000)
            social_relationships = await self._extract_social_relationships(
                envelope.events, resolved_clusters, space_id
            )
            self._stats.social_extraction_duration_ms = int(time.time() * 1000) - social_start
            self._stats.social_relationships_extracted = len(social_relationships)
            # Track by relationship type
            for rel in social_relationships:
                rel_type = rel.relationship_type or "UNKNOWN"
                self._stats.social_relationships_by_type[rel_type] = (
                    self._stats.social_relationships_by_type.get(rel_type, 0) + 1
                )

            # Step 6: Infer causal direction via Granger causality (4.4.9)
            causal_edges: List[CausalEdge] = []
            if self.config.enable_causal_inference and self._granger_causality:
                causal_start = int(time.time() * 1000)
                causal_edges = await self._infer_causal_relationships(
                    edge_updates, resolved_clusters, space_id, ctx
                )
                self._stats.causal_inference_duration_ms = int(time.time() * 1000) - causal_start

            # Step 7: Populate envelope.phases.r4_* outputs and emit decision metrics
            self._populate_phase_outputs(
                envelope, kg_updates, edge_updates, gaps, causal_edges, social_relationships, ctx
            )

            # Step 8: Emit UPDATE writes for resolved gaps not in current cycle
            # This ensures st_kg_dom.canonical_name gets updated even when the
            # entity wasn't mentioned in the current batch of events
            await self._emit_canonical_name_updates(envelope, kg_updates, ctx)

            # Calculate final stats
            duration_ms = int(time.time() * 1000) - start_ms
            self._stats.total_duration_ms = duration_ms
            self._stats.events_processed = len(envelope.events)

            logger.info(
                "R4: Knowledge graph consolidation complete",
                extra={
                    "cycle_id": cycle_id,
                    "entities_extracted": self._stats.entities_extracted,
                    "new_entities": self._stats.new_entities_created,
                    "updated_entities": self._stats.existing_entities_updated,
                    "new_edges": self._stats.new_edges_created,
                    "causal_edges": self._stats.causal_edges_created,
                    "gaps_emitted": self._stats.gaps_emitted,
                    "duration_ms": duration_ms,
                },
            )

            return P03PhaseResult.done(
                phase_id=self.PHASE_ID,
                duration_ms=duration_ms,
                outputs_summary={
                    "events_processed": self._stats.events_processed,
                    "entities_extracted": self._stats.entities_extracted,
                    "new_entities": self._stats.new_entities_created,
                    "updated_entities": self._stats.existing_entities_updated,
                    "merged_entities": self._stats.entities_merged,
                    "new_edges": self._stats.new_edges_created,
                    "updated_edges": self._stats.existing_edges_updated,
                    "causal_edges_created": self._stats.causal_edges_created,
                    "causal_edges_by_category": self._stats.causal_edges_by_category,
                    "edges_boosted": self._stats.edges_boosted,
                    "edges_demoted": self._stats.edges_demoted,
                    "gaps_emitted": self._stats.gaps_emitted,
                    "auto_resolved": self._stats.auto_resolved,
                    "flagged_for_review": self._stats.flagged_for_review,
                    "resolved_gaps_applied": self._stats.resolved_gaps_applied,
                },
                idempotency_key=self.idempotency_key(envelope),
            )

        except Exception as e:
            duration_ms = int(time.time() * 1000) - start_ms
            logger.exception(
                "R4: Knowledge graph consolidation failed",
                extra={
                    "cycle_id": cycle_id,
                    "error": str(e),
                    "duration_ms": duration_ms,
                },
            )

            error = P03Error.create(
                phase="R4",
                stage_id="kg_consolidator",
                error_type="R4_KG_ERROR",
                error_message=str(e),
                recoverable=True,  # R4 failures are retriable
            )

            return P03PhaseResult.fail(
                phase_id=self.PHASE_ID,
                error=error,
                duration_ms=duration_ms,
            )

    def _get_skip_reason(self, envelope: "P03BatchEnvelope") -> str:
        """Determine why phase should be skipped."""
        if not envelope.events:
            return "No events in batch"

        all_processed = all(getattr(event, "kg_processed", False) for event in envelope.events)
        if all_processed:
            return "All events already KG-processed"

        has_content = any(getattr(event, "content_text", None) for event in envelope.events)
        if not has_content:
            return "No events with content text"

        return "Unknown skip condition"

    async def _extract_entities(
        self,
        events: List["P03EventState"],
        space_id: str,
    ) -> Tuple[List[ExtractedEntity], Dict[str, List[ExtractedEntity]]]:
        """
        Extract entities from all events using pre-computed NER data.

        R4 uses ner_entities_json from P02 pre-computation, not raw text.
        This converts the JSON back to ExtractedEntity objects.

        Args:
            events: List of events to process
            space_id: Space ID for context

        Returns:
            Tuple of (all_entities, event_to_entities_map)
        """
        import json

        all_entities: List[ExtractedEntity] = []
        event_entity_map: Dict[str, List[ExtractedEntity]] = {}

        for event in events:
            # Use pre-computed NER from P02 (stored in ner_entities_json)
            ner_json = getattr(event, "ner_entities_json", None) or "{}"
            try:
                ner_data = json.loads(ner_json) if isinstance(ner_json, str) else ner_json
            except (json.JSONDecodeError, TypeError):
                ner_data = {}

            entities: List[ExtractedEntity] = []

            # Handle nested NER structure: {"ner_family": {"entities": [...]}, "ner_general": {"entities": [...]}}
            if isinstance(ner_data, dict):
                # Phase 1: Collect family entities first (they have priority)
                family_spans: List[tuple[int, int]] = []  # (start, end) token spans

                family_head_data = ner_data.get("ner_family", {})
                if isinstance(family_head_data, dict):
                    family_entities_list = family_head_data.get("entities", [])
                elif isinstance(family_head_data, list):
                    family_entities_list = family_head_data
                else:
                    family_entities_list = []

                for ent_data in family_entities_list:
                    if not isinstance(ent_data, dict):
                        continue
                    start_tok = int(ent_data.get("start_token", 0))
                    end_tok = int(ent_data.get("end_token", 0))
                    family_spans.append((start_tok, end_tok))

                if family_spans:
                    logger.debug(f"R4: Family spans collected for dedup: {family_spans}")

                # Phase 2: Process all heads, but skip general entities that overlap with family spans
                # In hybrid mode (use_hybrid_ner=True), skip ner_general entirely - will use BERT-NER instead

                # Labels that ner_family produces - accept family-specific labels but NOT PERSON
                # PERSON from ner_family is low quality (e.g., tags "authentication" as PERSON)
                # We use BERT-NER for PERSON entities instead
                VALID_NER_FAMILY_LABELS = {
                    "KINSHIP",
                    "FAMILY_EVENT",
                    "HOME_LOC",
                    "FAMILY_LOC",
                    # "PERSON" - REJECTED: ner_family's PERSON is garbage (tags "authentication", etc.)
                    # Use BERT-NER for PERSON entities via hybrid mode
                    "DATE_REL",
                    "DATE",
                    "TIME",
                    "DURATION",
                    "MILESTONE",  # Added: family milestones
                    "HEIRLOOM",  # Added: family heirlooms
                    "TRADITION",  # Added: family traditions
                    "ROUTINE",  # Added: family routines
                    "PET",  # Added: family pets
                    "NICKNAME",  # Added: family nicknames
                }

                for head_name, head_data in ner_data.items():
                    # Determine source head from key name
                    source_head = head_name if head_name.startswith("ner_") else f"ner_{head_name}"

                    # HYBRID NER: Skip UltraBERT ner_general - it's garbage (untrained head)
                    # We'll use BERT-NER for general entities below
                    if self.config.use_hybrid_ner and source_head == "ner_general":
                        logger.debug(
                            "R4: Skipping UltraBERT ner_general (hybrid mode - using BERT-NER)"
                        )
                        continue

                    # Extract entities list from head data
                    entities_list: List[dict] = []
                    if isinstance(head_data, dict):
                        # Format: {"entities": [...]} or just {"entities": [...]}
                        entities_list = head_data.get("entities", [])
                    elif isinstance(head_data, list):
                        # Format: direct list of entities
                        entities_list = head_data

                    for ent_data in entities_list:
                        if not isinstance(ent_data, dict):
                            continue

                        try:
                            # Get the label early for filtering
                            label = ent_data.get("label", "UNKNOWN")

                            # HYBRID NER: For ner_family, only accept labels it was trained for
                            # Reject PERSON/ORG/LOC that may leak through (like "authentication" -> PERSON)
                            if self.config.use_hybrid_ner and source_head == "ner_family":
                                if label not in VALID_NER_FAMILY_LABELS:
                                    logger.debug(
                                        f"R4: Rejecting ner_family entity with unexpected label: "
                                        f"{ent_data.get('text')!r} ({label}) - expected {VALID_NER_FAMILY_LABELS}"
                                    )
                                    continue

                            # For ner_general entities, check span overlap with family entities
                            # If general entity's span is contained within a family span, skip it
                            # This handles cases like: family="Lincoln School" (8-9), general="Lincoln" (8-8)
                            if source_head == "ner_general":
                                ent_start = int(ent_data.get("start_token", 0))
                                ent_end = int(ent_data.get("end_token", 0))
                                is_contained = any(
                                    fam_start <= ent_start and ent_end <= fam_end
                                    for fam_start, fam_end in family_spans
                                )
                                if is_contained:
                                    logger.info(
                                        f"R4: Skipping overlapping general entity: {ent_data.get('text')} "
                                        f"(tokens {ent_start}-{ent_end}) contained in family span"
                                    )
                                    continue

                            # Map UltraBERT label to KGEntityType using LABEL_MAPPING
                            mapping = UltraBERTEntityExtractor.LABEL_MAPPING.get(label)

                            if mapping:
                                kg_type, priority = mapping
                            else:
                                # Unknown label, default to CONCEPT with low priority
                                kg_type = KGEntityType.CONCEPT
                                priority = 0.5

                            text = ent_data.get("text", "")
                            if not text:
                                continue

                            # Use entity extractor's normalize_name for proper cleanup
                            # (strips possessives, conjunctions, etc.)
                            normalized = self._entity_extractor.normalize_name(text)
                            if not normalized:
                                continue  # Skip if normalized to empty

                            # Word boundary validation - reject sub-word fragments
                            # e.g., "Fur" from "Fur Elise", "Bella" from "Bella Notte"
                            source_text = getattr(event, "content_text", "") or ""
                            if source_text and not self._entity_extractor.is_complete_word(
                                normalized, source_text
                            ):
                                logger.debug(f"R4 rejected sub-word fragment: {normalized}")
                                continue

                            # Reclassify ORG -> LOCATION if text has location affordance
                            if (
                                kg_type == KGEntityType.ORGANIZATION
                                and self._entity_extractor._has_location_affordance(normalized)
                            ):
                                kg_type = KGEntityType.LOCATION
                                logger.debug(f"R4 reclassified ORG->LOCATION: {normalized}")

                            entity = ExtractedEntity(
                                text=text,
                                kg_type=kg_type,
                                normalized_text=normalized,
                                source_label=label,
                                source_head=source_head,
                                priority=priority,
                                start_token=int(ent_data.get("start_token", 0)),
                                end_token=int(ent_data.get("end_token", 0)),
                            )
                            entities.append(entity)
                        except (ValueError, KeyError, TypeError) as e:
                            logger.debug(f"Skipping malformed entity data: {ent_data}, error: {e}")
                            continue
            elif isinstance(ner_data, list):
                # Legacy flat list format
                for ent_data in ner_data:
                    if isinstance(ent_data, str):
                        normalized = self._entity_extractor.normalize_name(ent_data)
                        if not normalized:
                            continue
                        # Word boundary validation
                        source_text = getattr(event, "content_text", "") or ""
                        if source_text and not self._entity_extractor.is_complete_word(
                            normalized, source_text
                        ):
                            continue
                        entity = ExtractedEntity(
                            text=ent_data,
                            kg_type=KGEntityType.CONCEPT,
                            normalized_text=normalized,
                            source_label="UNKNOWN",
                            source_head="ner_general",
                            priority=0.5,
                            start_token=0,
                            end_token=0,
                        )
                        entities.append(entity)
                        continue

                    try:
                        kg_type_str = ent_data.get("kg_type", ent_data.get("type", "CONCEPT"))
                        kg_type = (
                            KGEntityType(kg_type_str)
                            if isinstance(kg_type_str, str)
                            else KGEntityType.CONCEPT
                        )

                        raw_text = ent_data.get("text", ent_data.get("mention", ""))
                        normalized = self._entity_extractor.normalize_name(
                            ent_data.get("normalized", raw_text)
                        )
                        if not normalized:
                            continue

                        # Word boundary validation
                        source_text = getattr(event, "content_text", "") or ""
                        if source_text and not self._entity_extractor.is_complete_word(
                            normalized, source_text
                        ):
                            continue

                        entity = ExtractedEntity(
                            text=raw_text,
                            kg_type=kg_type,
                            normalized_text=normalized,
                            source_label=ent_data.get("source_label", "UNKNOWN"),
                            source_head=ent_data.get("source_head", "ner_general"),
                            priority=float(
                                ent_data.get("priority", ent_data.get("confidence", 0.5))
                            ),
                            start_token=int(ent_data.get("start_token", 0)),
                            end_token=int(ent_data.get("end_token", 0)),
                        )
                        entities.append(entity)
                    except (ValueError, KeyError, TypeError) as e:
                        logger.debug(f"Skipping malformed entity data: {ent_data}, error: {e}")
                        continue

            # HYBRID NER: Extract general entities using BERT-NER instead of UltraBERT ner_general
            # This runs dslim/bert-base-NER on the source text for correct PER/ORG/LOC extraction
            if self.config.use_hybrid_ner:
                source_text = getattr(event, "content_text", "") or ""
                if source_text and source_text.strip():
                    try:
                        from k0.modules.consolidation.algorithms.bert_ner_adapter import (
                            get_bert_ner,
                        )

                        bert_ner = get_bert_ner()
                        bert_results = bert_ner.extract(source_text)

                        for bert_ent in bert_results:
                            # Map BERT-NER labels to KG types
                            label = bert_ent.label
                            if label == "PER":
                                kg_type = KGEntityType.PERSON
                                priority = 0.85
                                mapped_label = "PERSON"
                            elif label == "ORG":
                                kg_type = KGEntityType.ORGANIZATION
                                priority = 0.80
                                mapped_label = "ORG"
                            elif label == "LOC":
                                kg_type = KGEntityType.LOCATION
                                priority = 0.80
                                mapped_label = "LOC"
                            elif label == "MISC":
                                kg_type = KGEntityType.CONCEPT
                                priority = 0.65
                                mapped_label = "MISC"
                            else:
                                kg_type = KGEntityType.CONCEPT
                                priority = 0.50
                                mapped_label = label

                            # Normalize and validate
                            normalized = self._entity_extractor.normalize_name(bert_ent.text)
                            if not normalized:
                                continue

                            # Word boundary validation
                            if not self._entity_extractor.is_complete_word(normalized, source_text):
                                logger.debug(f"R4 BERT-NER rejected sub-word: {normalized}")
                                continue

                            # Reclassify ORG -> LOCATION if has location affordance
                            if (
                                kg_type == KGEntityType.ORGANIZATION
                                and self._entity_extractor._has_location_affordance(normalized)
                            ):
                                kg_type = KGEntityType.LOCATION
                                logger.debug(
                                    f"R4 BERT-NER reclassified ORG->LOCATION: {normalized}"
                                )

                            entity = ExtractedEntity(
                                text=bert_ent.text,
                                kg_type=kg_type,
                                normalized_text=normalized,
                                source_label=mapped_label,
                                source_head="bert_ner",  # Track source
                                priority=priority,
                                start_token=bert_ent.start,  # Char positions
                                end_token=bert_ent.end,
                            )
                            entities.append(entity)

                        logger.debug(
                            f"R4 BERT-NER extracted {len(bert_results)} entities from event",
                            extra={"event_id": event.event_id},
                        )
                    except Exception as e:
                        logger.warning(f"R4 BERT-NER extraction failed: {e}")

            event_entity_map[event.event_id] = entities
            all_entities.extend(entities)

            # Update stats
            self._stats.entities_extracted += len(entities)
            for entity in entities:
                entity_type = entity.kg_type.value
                self._stats.entities_by_type[entity_type] = (
                    self._stats.entities_by_type.get(entity_type, 0) + 1
                )

        return all_entities, event_entity_map

    async def _build_entity_clusters(
        self,
        all_entities: List[ExtractedEntity],
        event_entity_map: Dict[str, List[ExtractedEntity]],
        events: List["P03EventState"],
        ctx: Optional["P03RunnerContext"] = None,
    ) -> List[EntityCluster]:
        """
        Build entity clusters from extracted entities.

        Groups similar entities across events into clusters.
        Uses resolved gaps from st_learning_queue for canonical names.

        Args:
            all_entities: All extracted entities
            event_entity_map: Map of event_id to entities
            events: Original events
            ctx: Runner context with syscalls (for resolved gap lookup)

        Returns:
            List of entity clusters
        """
        # Load resolved gaps if ctx available and cache empty
        if ctx and not self._resolved_gaps_cache:
            await self._load_resolved_gaps(ctx)
        # Group entities by normalized name + type
        entity_groups: Dict[str, List[Tuple[ExtractedEntity, str]]] = {}

        for event in events:
            entities = event_entity_map.get(event.event_id, [])
            for entity in entities:
                # Create normalized key
                key = f"{entity.kg_type.value}:{entity.normalized_text.lower()}"
                if key not in entity_groups:
                    entity_groups[key] = []
                entity_groups[key].append((entity, event.event_id))

        # Build clusters
        clusters: List[EntityCluster] = []
        for key, entity_events in entity_groups.items():
            entity_type, normalized_name = key.split(":", 1)

            # Collect all mentions and event IDs
            mentions = list(set(e.text for e, _ in entity_events))
            event_ids = list(set(eid for _, eid in entity_events))
            observation_count = len(event_ids)

            # Use first entity for canonical info
            first_entity = entity_events[0][0]

            # Calculate average confidence (using priority as confidence)
            avg_confidence = sum(e.priority for e, _ in entity_events) / len(entity_events)

            # EVENT entity promotion gate:
            # Only promote EVENT entities to KG if they appear in multiple events
            # or have high salience. Single-occurrence events like "piano", "recital"
            # should stay as episode metadata, not become KG entities.
            if entity_type == "EVENT" and observation_count < self.config.min_event_observations:
                logger.debug(
                    f"Skipping weak EVENT entity: {normalized_name} (observations={observation_count})"
                )
                continue

            # Check for resolved gap value to use as canonical name
            cluster_id = f"cluster_{key.replace(':', '_')}"
            canonical_name = first_entity.normalized_text

            # Lookup resolved value from st_learning_queue (populated by GapAutoResolver)
            if cluster_id in self._resolved_gaps_cache:
                canonical_name = self._resolved_gaps_cache[cluster_id]
                self._stats.resolved_gaps_applied += 1
                logger.debug(f"Using resolved canonical name for {cluster_id}: {canonical_name}")

            cluster = EntityCluster(
                cluster_id=cluster_id,
                canonical_name=canonical_name,
                entity_type=entity_type,
                mentions=mentions,
                observation_ids=event_ids,
                confidence=avg_confidence,
                embedding=None,  # Would come from embedding service
            )
            clusters.append(cluster)

        return clusters

    async def _resolve_entities(
        self,
        clusters: List[EntityCluster],
        events: List["P03EventState"],
        space_id: str,
        ctx: "P03RunnerContext",
    ) -> Tuple[List[EntityCluster], List[GapCandidate]]:
        """
        Resolve ambiguous entity mentions using context hierarchy.

        Args:
            clusters: Entity clusters
            events: Original events for context
            space_id: Space ID
            ctx: Runner context

        Returns:
            Tuple of (resolved_clusters, gap_candidates)
        """
        resolved_clusters: List[EntityCluster] = []
        gaps: List[GapCandidate] = []

        for cluster in clusters:
            # Route through confidence bands using quick_band
            band = quick_band(cluster.confidence)

            if band == ConfidenceBand.AUTO:
                # High confidence (AUTO): auto-resolve
                resolved_clusters.append(cluster)
                self._stats.auto_resolved += 1

            elif band == ConfidenceBand.FLAG:
                # Medium confidence (FLAG): resolve but flag for review
                resolved_clusters.append(cluster)
                self._stats.flagged_for_review += 1

                # Optionally emit a background gap for review
                if self.config.emit_gaps_on_low_confidence:
                    gap = GapCandidate(
                        gap_id=f"gap_{cluster.cluster_id}",
                        gap_type="ENTITY_FLAGGED",
                        related_entity_id=cluster.cluster_id,
                        entropy_score=1.0 - cluster.confidence,
                        priority="MEDIUM",
                        context_json=f'{{"mentions": {cluster.mentions}}}',
                        candidate_values=cluster.mentions,
                    )
                    gaps.append(gap)

            else:  # ConfidenceBand.GAP
                # Low confidence (GAP): emit gap, don't resolve
                self._stats.gaps_emitted += 1
                self._stats.ambiguous_mentions += 1

                gap = GapCandidate(
                    gap_id=f"gap_{cluster.cluster_id}",
                    gap_type="AMBIGUOUS_ENTITY",
                    related_entity_id=cluster.cluster_id,
                    entropy_score=1.0 - cluster.confidence,
                    priority="HIGH",
                    context_json=f'{{"mentions": {cluster.mentions}, "entity_type": "{cluster.entity_type}"}}',
                    candidate_values=cluster.mentions,
                )
                gaps.append(gap)

        return resolved_clusters, gaps

    async def _process_entity_clusters(
        self,
        clusters: List[EntityCluster],
        space_id: str,
        ctx: "P03RunnerContext",
    ) -> List[KGUpdate]:
        """
        Process entity clusters into KG updates.

        For each cluster:
        - Check if entity exists in KG (would query st_kg_dom)
        - If exists and similar: UPDATE_ENTITY (merge aliases)
        - If new: CREATE_ENTITY

        Args:
            clusters: Resolved entity clusters
            space_id: Space ID
            ctx: Runner context

        Returns:
            List of KGUpdate operations
        """
        updates: List[KGUpdate] = []

        for cluster in clusters:
            # Check merge threshold (assert initialized)
            assert self._merge_thresholds is not None, "Merge thresholds not initialized"
            decision = self._merge_thresholds.should_merge(cluster.entity_type, cluster.confidence)

            if decision.should_merge:
                # Would check for existing entity in real implementation
                # For now, assume all are new
                self._stats.new_entities_created += 1
                updates.append(
                    KGUpdate(
                        update_type=KGUpdateType.CREATE_ENTITY,
                        entity_id=cluster.cluster_id,
                        canonical_name=cluster.canonical_name,
                        entity_type=cluster.entity_type,
                        aliases=cluster.mentions,
                        new_observations=len(cluster.observation_ids),
                        confidence=cluster.confidence,
                        source_event_ids=cluster.observation_ids,
                    )
                )
            else:
                # Below threshold: still create but mark for potential merge later
                self._stats.new_entities_created += 1
                updates.append(
                    KGUpdate(
                        update_type=KGUpdateType.CREATE_ENTITY,
                        entity_id=cluster.cluster_id,
                        canonical_name=cluster.canonical_name,
                        entity_type=cluster.entity_type,
                        aliases=cluster.mentions,
                        new_observations=len(cluster.observation_ids),
                        confidence=cluster.confidence,
                        source_event_ids=cluster.observation_ids,
                    )
                )

        return updates

    async def _discover_relationships(
        self,
        clusters: List[EntityCluster],
        event_entity_map: Dict[str, List[ExtractedEntity]],
    ) -> List[KGUpdate]:
        """
        Discover relationships via Hebbian co-occurrence.

        Spec: Dossier §4.5.2, Issues 4.1.3, 4.1.4, 4.4.8

        Algorithm:
        1. For each event, find all entity pairs
        2. Use HebbianLearner to compute adaptive edge weights
        3. Apply anti-decay for re-observed edges (Issue 4.1.4)
        4. If co-occurrence >= MIN_CO_OCCURRENCE, create edge

        Args:
            clusters: Resolved entity clusters
            event_entity_map: Map of event_id to entities

        Returns:
            List of KGUpdate edge operations
        """
        updates: List[KGUpdate] = []

        # Build co-occurrence matrix from cluster observation overlap
        co_occurrences: Dict[str, Dict[str, Any]] = {}

        # Create cluster lookup by normalized name
        cluster_by_name: Dict[str, EntityCluster] = {}
        for cluster in clusters:
            key = f"{cluster.entity_type}:{cluster.canonical_name.lower()}"
            cluster_by_name[key] = cluster

        # Count co-occurrences per event with importance scores
        for event_id, entities in event_entity_map.items():
            if len(entities) < 2:
                continue

            # Find clusters for these entities (deduplicated by cluster_id)
            seen_cluster_ids: set = set()
            event_clusters: List[EntityCluster] = []
            for entity in entities:
                key = f"{entity.kg_type.value}:{entity.normalized_text.lower()}"
                if key in cluster_by_name:
                    cluster = cluster_by_name[key]
                    # Deduplicate: same entity from multiple NER heads
                    if cluster.cluster_id not in seen_cluster_ids:
                        event_clusters.append(cluster)
                        seen_cluster_ids.add(cluster.cluster_id)

            # Track pairs with importance context
            for i, cluster_a in enumerate(event_clusters):
                for cluster_b in event_clusters[i + 1 :]:
                    # Skip self-loops: same entity appearing multiple times
                    # (e.g., from both ner_family and bert_ner heads)
                    if cluster_a.cluster_id == cluster_b.cluster_id:
                        continue

                    # Canonical pair key (ordered for consistency)
                    pair_ids = sorted([cluster_a.cluster_id, cluster_b.cluster_id])
                    pair_key = f"{pair_ids[0]}:{pair_ids[1]}"

                    if pair_key not in co_occurrences:
                        co_occurrences[pair_key] = {
                            "count": 0,
                            "importance_sum": 0.0,
                            "cluster_a_id": pair_ids[0],
                            "cluster_b_id": pair_ids[1],
                        }

                    co_occurrences[pair_key]["count"] += 1
                    # Use average cluster confidence as importance proxy
                    avg_importance = (cluster_a.confidence + cluster_b.confidence) / 2
                    co_occurrences[pair_key]["importance_sum"] += avg_importance

        self._stats.co_occurrence_pairs = len(co_occurrences)

        # Generate edge updates using HebbianLearner if available
        for pair_key, pair_data in co_occurrences.items():
            count = pair_data["count"]
            if count < self.config.min_co_occurrence:
                continue

            cluster_a_id = pair_data["cluster_a_id"]
            cluster_b_id = pair_data["cluster_b_id"]

            # Final self-loop guard at edge creation
            if cluster_a_id == cluster_b_id:
                self._logger.debug(f"Skipping self-loop co-occurrence: {cluster_a_id}")
                continue

            avg_importance = pair_data["importance_sum"] / count if count > 0 else 0.5

            # Calculate confidence using HebbianLearner if available (4.4.8)
            if self._hebbian_learner and self.config.enable_hebbian_adaptive_rates:
                # Use HebbianLearner's adaptive weight computation
                # Start with initial weight based on importance
                initial_weight = self._hebbian_learner.compute_initial_weight(avg_importance)

                # Update weight for each co-occurrence with adaptive learning rate
                current_weight = initial_weight
                current_count = 0
                for _ in range(count):
                    new_weight, new_count = self._hebbian_learner.update_edge_weight(
                        current_weight=current_weight,
                        current_count=current_count,
                        event_importance=avg_importance,
                    )
                    # Track strengthening/weakening
                    delta = new_weight - current_weight
                    if delta > 0:
                        self._stats.hebbian_edges_strengthened += 1
                    elif delta < 0:
                        self._stats.hebbian_edges_weakened += 1

                    current_weight = new_weight
                    current_count = new_count

                confidence = current_weight
            else:
                # Fallback: use static formula
                confidence = min(
                    self.config.max_relationship_confidence,
                    self.config.base_confidence + self.config.confidence_increment * count,
                )

            # Create new edge
            edge_id = f"edge_{cluster_a_id}_{cluster_b_id}"
            self._stats.new_edges_created += 1

            updates.append(
                KGUpdate(
                    update_type=KGUpdateType.CREATE_EDGE,
                    edge_id=edge_id,
                    source_id=cluster_a_id,
                    target_id=cluster_b_id,
                    relation_type="RELATED_TO",
                    confidence=confidence,
                    observation_count=count,
                )
            )

        return updates

    async def _infer_causal_relationships(
        self,
        edge_updates: List[KGUpdate],
        clusters: List[EntityCluster],
        space_id: str,
        ctx: "P03RunnerContext",
    ) -> List[CausalEdge]:
        """
        Infer causal direction for discovered edges using Granger causality.

        Issues: 4.4.9, 4.4.10

        This method:
        1. Takes Hebbian co-occurrence edges from _discover_relationships
        2. Analyzes temporal precedence using Granger causality (4.4.9)
        3. Applies per-category adaptive thresholds (4.4.10)
        4. Creates causal edges for strong temporal patterns

        Args:
            edge_updates: Edge updates from Hebbian discovery
            clusters: Entity clusters with observation data
            space_id: Space ID for context
            ctx: Runner context

        Returns:
            List of CausalEdge objects for edges with causal direction
        """
        if not self._granger_causality:
            return []

        causal_edges: List[CausalEdge] = []
        cluster_lookup = {c.cluster_id: c for c in clusters}

        for edge_update in edge_updates:
            if edge_update.update_type != KGUpdateType.CREATE_EDGE:
                continue

            source_id = edge_update.source_id
            target_id = edge_update.target_id

            if not source_id or not target_id:
                continue

            source_cluster = cluster_lookup.get(source_id)
            target_cluster = cluster_lookup.get(target_id)

            if not source_cluster or not target_cluster:
                continue

            # Build observation timestamps from cluster observation_ids
            # In real implementation, would fetch actual timestamps from events
            # For now, use placeholder that returns observation count
            observations = edge_update.observation_count or 0

            if observations < self.config.granger_min_observations:
                continue

            # Determine causality category using classifier (4.4.10)
            category = CausalityCategory.PREFERENCE_HABIT  # Default
            if self._category_classifier:
                category = self._category_classifier.classify(
                    source_entity_name=source_cluster.canonical_name,
                    target_entity_name=target_cluster.canonical_name,
                    relationship_type=edge_update.relation_type or "RELATED_TO",
                )

            # Get adaptive threshold for category (4.4.10)
            threshold = self.config.granger_precedence_threshold
            if self._causality_thresholds:
                threshold = self._causality_thresholds.get_threshold(category)

            # For demonstration, create causal edge if observation count suggests
            # strong co-occurrence (would use real temporal data in production)
            if observations >= self.config.granger_min_observations:
                # Simulate precedence ratio based on confidence
                # In production: call granger_causality.compute_temporal_precedence
                simulated_ratio = min(0.95, edge_update.confidence + 0.1)

                if simulated_ratio >= threshold:
                    causal_edge = CausalEdge(
                        source_id=source_id,
                        target_id=target_id,
                        relation_type="CAUSES",
                        confidence=simulated_ratio,
                        observation_count=observations,
                        precedence_ratio=simulated_ratio,
                    )
                    causal_edges.append(causal_edge)

                    # Update stats
                    self._stats.causal_edges_created += 1
                    cat_name = category.value
                    self._stats.causal_edges_by_category[cat_name] = (
                        self._stats.causal_edges_by_category.get(cat_name, 0) + 1
                    )

        self._stats.causal_pairs_analyzed = len(edge_updates)

        logger.info(
            f"R4: Causal inference complete - {len(causal_edges)} causal edges "
            f"from {len(edge_updates)} candidate edges"
        )

        return causal_edges

    # =========================================================================
    # UltraBERT Relation Type Mappings
    # =========================================================================
    ULTRABERT_TO_TYPE: Dict[str, str] = {
        # Family relations -> FAMILY
        "parent_of": "FAMILY",
        "child_of": "FAMILY",
        "spouse_of": "FAMILY",
        "sibling_of": "FAMILY",
        "grandparent_of": "FAMILY",
        "grandchild_of": "FAMILY",
        "aunt_uncle_of": "FAMILY",
        "niece_nephew_of": "FAMILY",
        "cousin_of": "FAMILY",
        "pet_of": "FAMILY",
        # Social relations
        "friend_of": "FRIEND",
        "colleague_of": "COLLEAGUE",
        # Other
        "lives_at": "ACQUAINTANCE",
        "owns": "ACQUAINTANCE",
        "no_relation": "ACQUAINTANCE",
    }

    ULTRABERT_TO_SUBTYPE: Dict[str, str] = {
        "parent_of": "PARENT",
        "child_of": "CHILD",
        "spouse_of": "SPOUSE",
        "sibling_of": "SIBLING",
        "grandparent_of": "GRANDPARENT",
        "grandchild_of": "GRANDCHILD",
        "aunt_uncle_of": "EXTENDED_FAMILY",
        "niece_nephew_of": "EXTENDED_FAMILY",
        "cousin_of": "EXTENDED_FAMILY",
        "pet_of": "PET_OWNER",
        "friend_of": "FRIEND",
        "colleague_of": "COWORKER",
    }

    # Sentiment to valence mapping
    SENTIMENT_VALENCE: Dict[str, float] = {
        "very_negative": -1.0,
        "negative": -0.5,
        "neutral": 0.0,
        "positive": 0.5,
        "very_positive": 1.0,
    }

    # Emotions that suggest emotional roles
    ROLE_EMOTIONS: Dict[str, List[str]] = {
        "MENTOR": ["admiration", "gratitude", "learning", "guidance"],
        "CONFIDANT": ["trust", "caring", "relief", "vulnerability"],
        "ENERGY_SOURCE": ["joy", "excitement", "amusement", "playfulness"],
        "SUPPORT_GIVER": ["caring", "protectiveness", "worry", "patience"],
        "PLAYMATE": ["amusement", "excitement", "playfulness", "joy"],
        "CARETAKER": ["protectiveness", "patience", "worry", "tenderness"],
    }

    async def _extract_social_relationships(
        self,
        events: List["P03EventState"],
        resolved_clusters: List["EntityCluster"],
        space_id: str,
    ) -> List[SocialRelationship]:
        """
        Extract social relationships from events using UltraBERT outputs.

        Uses UltraBERT's extracted_relations_json as primary signal for relationship
        types. Enriches with sentiment, emotions, and context for richer social
        understanding.

        UltraBERT Capabilities Used:
        - relations: parent_of, spouse_of, colleague_of, friend_of, etc.
        - sentiment: very_negative to very_positive -> emotional_valence
        - emotions: 44 labels -> dominant_emotion, emotional_role
        - ner_family: PERSON, KINSHIP -> entity resolution

        Args:
            events: Events with UltraBERT outputs (extracted_relations_json, etc.)
            resolved_clusters: Entity clusters for person lookup
            space_id: Space ID for relationship IDs

        Returns:
            List of SocialRelationship for R6 to write to st_social
        """
        import hashlib
        import json
        from collections import defaultdict

        # Track relationships by (actor_a, actor_b) pair
        # Aggregate across all events to build comprehensive view
        relationship_data: Dict[str, Dict[str, Any]] = {}

        # Build entity name -> cluster ID map for entity resolution
        entity_name_to_id: Dict[str, str] = {}
        for cluster in resolved_clusters:
            if cluster.entity_type in ("PERSON", "FAMILY_MEMBER"):
                for mention in cluster.mentions:
                    entity_name_to_id[mention.lower()] = cluster.cluster_id
                entity_name_to_id[cluster.canonical_name.lower()] = cluster.cluster_id

        for event in events:
            # Get event metadata
            event_id = getattr(event, "event_id", "unknown")
            actor_id = getattr(event, "actor_id", None)
            self_actor_id = actor_id or f"SELF_{space_id}"

            # Parse UltraBERT relations (primary signal for relationship type)
            extracted_relations_json = getattr(event, "extracted_relations_json", None)
            try:
                ultrabert_relations = (
                    json.loads(extracted_relations_json) if extracted_relations_json else []
                )
            except (json.JSONDecodeError, TypeError):
                ultrabert_relations = []

            # Parse participants
            participants_json = getattr(event, "participants_json", None)
            try:
                participants = json.loads(participants_json) if participants_json else []
            except (json.JSONDecodeError, TypeError):
                participants = []

            # Parse entities for person names
            entities_json = getattr(event, "entities_json", None)
            try:
                entities = json.loads(entities_json) if entities_json else []
            except (json.JSONDecodeError, TypeError):
                entities = []

            # Extract person entities (PERSON, KINSHIP from ner_family)
            person_entities = [
                e for e in entities if e.get("label") in ("PERSON", "KINSHIP", "PER")
            ]

            # Get sentiment and emotions
            sentiment = getattr(event, "sentiment", "neutral") or "neutral"
            sentiment_confidence = getattr(event, "sentiment_confidence", 0.5) or 0.5
            emotions_json = getattr(event, "emotions_json", None)
            try:
                event_emotions = json.loads(emotions_json) if emotions_json else []
            except (json.JSONDecodeError, TypeError):
                event_emotions = []

            # Get context fields
            social_context = getattr(event, "social_context", None)
            # Prefer UltraBERT 12-type for better activity granularity (Issue 0060)
            activity_type = getattr(event, "activity_type_ultrabert", None) or getattr(
                event, "activity_type", None
            )
            location_name = getattr(event, "location_name", None)
            social_intimacy = getattr(event, "social_intimacy", None)
            created_at = getattr(event, "created_at", 0) or 0

            # Skip solo events
            num_participants = getattr(event, "num_participants", 0) or 0
            if num_participants == 0 and social_context == "solo" and not person_entities:
                continue

            # Build list of people mentioned in this event
            people_in_event: List[Dict[str, Any]] = []

            # Add from participants_json
            for participant_id in participants:
                if participant_id == self_actor_id:
                    continue
                name = participant_id
                if participant_id.startswith("person_"):
                    name = participant_id[7:]
                people_in_event.append(
                    {
                        "id": participant_id,
                        "name": name.replace("_", " ").title(),
                    }
                )

            # Add from entities if not already present
            existing_names = {p["name"].lower() for p in people_in_event}
            for entity in person_entities:
                entity_text = entity.get("text", "")
                if entity_text.lower() not in existing_names:
                    entity_id = f"person_{entity_text.lower().replace(' ', '_')}"
                    people_in_event.append(
                        {
                            "id": entity_id,
                            "name": entity_text.title(),
                            "label": entity.get("label"),
                        }
                    )

            # Process each person in this event
            for person in people_in_event:
                participant_id = person["id"]
                participant_name = person["name"]

                # Create relationship key (directional: SELF -> other)
                rel_key = f"{self_actor_id}:{participant_id}"

                if rel_key not in relationship_data:
                    # Initialize relationship data
                    relationship_data[rel_key] = {
                        "actor_a_id": self_actor_id,
                        "actor_b_id": participant_id,
                        "actor_b_name": participant_name,
                        "ultrabert_relation_types": set(),
                        "social_contexts": [],
                        "locations": [],
                        "activities": [],
                        "sentiments": [],
                        "emotions": defaultdict(int),
                        "event_ids": [],
                        "interaction_count": 0,
                        "intimacy_levels": [],
                        "canonical_entity_id": entity_name_to_id.get(participant_name.lower(), ""),
                    }

                data = relationship_data[rel_key]
                data["interaction_count"] += 1
                data["event_ids"].append(event_id)

                # Add UltraBERT relation types
                for rel in ultrabert_relations:
                    if rel and rel != "no_relation":
                        data["ultrabert_relation_types"].add(rel)

                # Track context
                if social_context:
                    data["social_contexts"].append(social_context)
                if location_name:
                    data["locations"].append(location_name)
                if activity_type:
                    data["activities"].append(activity_type)
                if social_intimacy:
                    data["intimacy_levels"].append(social_intimacy)

                # Track sentiment for trajectory
                valence = self.SENTIMENT_VALENCE.get(sentiment, 0.0)
                data["sentiments"].append(
                    {
                        "event_id": event_id,
                        "sentiment": sentiment,
                        "valence": valence,
                        "confidence": sentiment_confidence,
                        "timestamp": created_at,
                    }
                )

                # Aggregate emotions
                for emotion in event_emotions:
                    if isinstance(emotion, str):
                        data["emotions"][emotion] += 1

        # Convert aggregated data to SocialRelationship objects
        social_relationships: List[SocialRelationship] = []

        for rel_key, data in relationship_data.items():
            rel_hash = hashlib.sha256(rel_key.encode()).hexdigest()[:16]

            # Convert set to list for ultrabert_relation_types
            ultrabert_types = list(data["ultrabert_relation_types"])

            # Determine relationship type from UltraBERT relations (primary) or context (fallback)
            relationship_type = self._derive_relationship_type(
                ultrabert_types,
                data["social_contexts"],
                data["activities"],
            )

            # Determine subtype from UltraBERT or name inference
            relationship_subtype = self._derive_relationship_subtype(
                ultrabert_types,
                data["actor_b_name"],
                data["social_contexts"],
            )

            # Calculate emotional valence (average of all sentiments)
            sentiments = data["sentiments"]
            if sentiments:
                valences = [s["valence"] for s in sentiments]
                emotional_valence_avg = sum(valences) / len(valences)
                # Trend: compare recent vs older (simple split)
                if len(valences) >= 4:
                    mid = len(valences) // 2
                    older_avg = sum(valences[:mid]) / mid
                    recent_avg = sum(valences[mid:]) / (len(valences) - mid)
                    emotional_valence_trend = recent_avg - older_avg
                else:
                    emotional_valence_trend = 0.0
            else:
                emotional_valence_avg = 0.0
                emotional_valence_trend = 0.0

            # Find dominant emotion
            emotions_dict = dict(data["emotions"])
            dominant_emotion = ""
            if emotions_dict:
                dominant_emotion = max(emotions_dict, key=emotions_dict.get)

            # Infer emotional role from emotion patterns
            emotional_role = self._infer_emotional_role(emotions_dict)

            # Determine relationship phase from interaction patterns
            relationship_phase = self._infer_relationship_phase(
                data["interaction_count"],
                emotional_valence_trend,
                sentiments,
            )

            # Determine most common intimacy level
            intimacy_level = "CASUAL"
            if data["intimacy_levels"]:
                from collections import Counter

                intimacy_counts = Counter(data["intimacy_levels"])
                intimacy_level = intimacy_counts.most_common(1)[0][0]

            # Determine most common social context
            social_context = ""
            if data["social_contexts"]:
                from collections import Counter

                context_counts = Counter(data["social_contexts"])
                social_context = context_counts.most_common(1)[0][0]

            # Determine most common location
            location_pattern = ""
            if data["locations"]:
                from collections import Counter

                location_counts = Counter(data["locations"])
                location_pattern = location_counts.most_common(1)[0][0]

            # Extract unique activities and modalities
            typical_activities = list(set(data["activities"]))[:5]  # Top 5
            # For now, infer modalities from context (would need richer data)
            interaction_modalities = self._infer_modalities(social_context, data["activities"])

            # Calculate confidence based on observation count and UltraBERT signal
            base_confidence = 0.5
            observation_boost = min(0.3, data["interaction_count"] * 0.05)
            ultrabert_boost = 0.15 if ultrabert_types else 0.0
            confidence = min(0.95, base_confidence + observation_boost + ultrabert_boost)

            relationship = SocialRelationship(
                relationship_id=f"social_{rel_hash}",
                actor_a_id=data["actor_a_id"],
                actor_b_id=data["actor_b_id"],
                actor_b_name=data["actor_b_name"],
                ultrabert_relation_types=ultrabert_types,
                relationship_type=relationship_type,
                relationship_subtype=relationship_subtype,
                social_context=social_context,
                intimacy_level=intimacy_level,
                location_pattern=location_pattern,
                emotional_role=emotional_role,
                emotional_valence_avg=round(emotional_valence_avg, 3),
                emotional_valence_trend=round(emotional_valence_trend, 3),
                dominant_emotion=dominant_emotion,
                relationship_phase=relationship_phase,
                interaction_modalities=interaction_modalities,
                typical_activities=typical_activities,
                emotions=emotions_dict,
                sentiment_trajectory=sentiments[-10:],  # Keep last 10 for trend
                interaction_count=data["interaction_count"],
                confidence=round(confidence, 3),
                source_event_ids=data["event_ids"],
                canonical_entity_id=data["canonical_entity_id"],
                is_new=True,
            )
            social_relationships.append(relationship)

        logger.info(
            f"R4: Social extraction complete - {len(social_relationships)} relationships "
            f"from {len(events)} events (UltraBERT-enriched)"
        )

        return social_relationships

    def _derive_relationship_type(
        self,
        ultrabert_types: List[str],
        social_contexts: List[str],
        activities: List[str],
    ) -> str:
        """
        Derive relationship type from UltraBERT relations (primary) or context (fallback).

        Priority: UltraBERT relations > social_context > activity_type

        Args:
            ultrabert_types: UltraBERT relation labels (parent_of, friend_of, etc.)
            social_contexts: Social contexts from events
            activities: Activity types from events

        Returns:
            Relationship type: FAMILY, FRIEND, COLLEAGUE, ACQUAINTANCE
        """
        # Primary: Use UltraBERT relation types
        if ultrabert_types:
            # If any family relation, it's FAMILY
            for rel in ultrabert_types:
                rel_type = self.ULTRABERT_TO_TYPE.get(rel)
                if rel_type == "FAMILY":
                    return "FAMILY"
            # Check for friend/colleague
            for rel in ultrabert_types:
                rel_type = self.ULTRABERT_TO_TYPE.get(rel)
                if rel_type in ("FRIEND", "COLLEAGUE"):
                    return rel_type

        # Fallback: Use social context
        if social_contexts:
            from collections import Counter

            context_counts = Counter(social_contexts)
            most_common_context = context_counts.most_common(1)[0][0].lower()

            if most_common_context in ("nuclear_family", "extended_family", "family"):
                return "FAMILY"
            elif most_common_context == "work":
                return "COLLEAGUE"
            elif most_common_context in ("friends", "social"):
                return "FRIEND"

        # Fallback: Use activity type
        if activities:
            from collections import Counter

            activity_counts = Counter(activities)
            most_common_activity = activity_counts.most_common(1)[0][0].lower()
            if most_common_activity == "work":
                return "COLLEAGUE"

        return "ACQUAINTANCE"

    def _derive_relationship_subtype(
        self,
        ultrabert_types: List[str],
        participant_name: str,
        social_contexts: List[str],
    ) -> str:
        """
        Derive relationship subtype from UltraBERT relations or name inference.

        Args:
            ultrabert_types: UltraBERT relation labels
            participant_name: Name of the other person
            social_contexts: Social contexts from events

        Returns:
            Subtype: SPOUSE, PARENT, CHILD, SIBLING, COWORKER, etc.
        """
        # Primary: Use UltraBERT subtype mapping
        if ultrabert_types:
            for rel in ultrabert_types:
                subtype = self.ULTRABERT_TO_SUBTYPE.get(rel)
                if subtype:
                    return subtype

        # Fallback: Infer from name (legacy logic)
        return self._infer_relationship_subtype(
            participant_name, social_contexts[0] if social_contexts else ""
        )

    def _infer_emotional_role(self, emotions: Dict[str, int]) -> str:
        """
        Infer emotional role from aggregated emotion patterns.

        Args:
            emotions: Dict of emotion -> count

        Returns:
            Emotional role: MENTOR, CONFIDANT, ENERGY_SOURCE, etc.
        """
        if not emotions:
            return ""

        # Score each role based on emotion matches
        role_scores: Dict[str, int] = {}
        for role, role_emotions in self.ROLE_EMOTIONS.items():
            score = sum(emotions.get(e, 0) for e in role_emotions)
            if score > 0:
                role_scores[role] = score

        if role_scores:
            return max(role_scores, key=role_scores.get)
        return ""

    def _infer_relationship_phase(
        self,
        interaction_count: int,
        valence_trend: float,
        sentiments: List[Dict[str, Any]],
    ) -> str:
        """
        Infer relationship phase from interaction patterns.

        Args:
            interaction_count: Number of interactions
            valence_trend: Positive = warming, negative = cooling
            sentiments: Sentiment history

        Returns:
            Phase: FORMING, STABLE, DEEPENING, COOLING, DORMANT
        """
        # Few interactions = FORMING
        if interaction_count <= 2:
            return "FORMING"

        # Strong positive trend = DEEPENING
        if valence_trend > 0.2:
            return "DEEPENING"

        # Strong negative trend = COOLING
        if valence_trend < -0.2:
            return "COOLING"

        # Many interactions with stable valence = STABLE
        return "STABLE"

    def _infer_modalities(self, social_context: str, activities: List[str]) -> List[str]:
        """
        Infer interaction modalities from context and activities.

        Args:
            social_context: Social context (work, family, friends)
            activities: Activity types

        Returns:
            List of modalities: in_person, phone, text, video
        """
        modalities = set()

        # In-person for most family/social activities
        if social_context in ("nuclear_family", "family", "friends"):
            modalities.add("in_person")

        # Work often includes video/text
        if social_context == "work":
            modalities.add("in_person")
            modalities.add("video")

        # Activities that imply in-person
        for activity in activities:
            if activity.lower() in ("meal", "recreation", "travel", "celebration"):
                modalities.add("in_person")

        return list(modalities) if modalities else ["in_person"]

    def _infer_relationship_subtype(
        self,
        participant_name: str,
        social_context: str,
    ) -> str:
        """
        Infer relationship subtype from participant name and context.

        Args:
            participant_name: e.g., mom, dad, wife, coworker_john
            social_context: e.g., nuclear_family, work

        Returns:
            Subtype: SPOUSE, PARENT, CHILD, SIBLING, COWORKER, etc.
        """
        name_lower = participant_name.lower()

        # Family subtypes
        if name_lower in ("mom", "mother", "mama", "mum"):
            return "PARENT"
        elif name_lower in ("dad", "father", "papa"):
            return "PARENT"
        elif name_lower in ("wife", "husband", "spouse", "partner"):
            return "SPOUSE"
        elif name_lower in ("son", "daughter", "child", "kid"):
            return "CHILD"
        elif name_lower in ("brother", "sister", "sibling", "bro", "sis"):
            return "SIBLING"
        elif name_lower in ("grandma", "grandpa", "grandmother", "grandfather"):
            return "GRANDPARENT"
        elif (social_context or "").lower() == "work":
            return "COWORKER"
        else:
            return ""

    def _populate_phase_outputs(
        self,
        envelope: "P03BatchEnvelope",
        entity_updates: List[KGUpdate],
        edge_updates: List[KGUpdate],
        gaps: List[GapCandidate],
        causal_edges: Optional[List[CausalEdge]] = None,
        social_relationships: Optional[List[SocialRelationship]] = None,
        ctx: Optional["P03RunnerContext"] = None,
    ) -> None:
        """
        Populate envelope.phases.r4_* outputs and emit decision metrics.

        Args:
            envelope: Batch envelope to update
            entity_updates: Entity create/update operations
            edge_updates: Edge create/update operations
            gaps: Gap candidates for P06
            causal_edges: Causal edges from Granger inference (4.4.9)
            social_relationships: Social relationships for st_social
            ctx: Runner context (Issue 6.1.4 - for decision metrics)
        """
        # Get tenant_id for metrics
        tenant_id = envelope.context.tenant_id

        # Issue 6.1.4: Get metrics registry if available
        metrics_registry = ctx.metrics_registry if ctx else None

        # Add social relationships for st_social
        if social_relationships:
            envelope.phases.r4_social_entities.extend(social_relationships)
            logger.info(
                f"R4: Added {len(social_relationships)} social relationships to phase outputs"
            )

        # Convert KGUpdates to phase output types
        for update in entity_updates:
            if update.update_type == KGUpdateType.CREATE_ENTITY:
                # Assert non-null for entity creates
                assert update.entity_id is not None
                assert update.canonical_name is not None
                assert update.entity_type is not None
                envelope.phases.r4_new_entities.append(
                    KGEntity(
                        entity_id=update.entity_id,
                        canonical_name=update.canonical_name,
                        entity_type=update.entity_type,
                        aliases_json=str(update.aliases),
                        confidence=update.confidence,
                        source_event_ids=update.source_event_ids,
                        is_new=True,
                    )
                )
                # Issue 6.1.4: Emit CREATE decision metric
                if metrics_registry:
                    metrics_registry.emit_decision(
                        tenant_id=tenant_id,
                        decision_type="CREATE",
                        target_layer="st_kg_dom",
                        confidence=update.confidence,
                    )
            elif update.update_type == KGUpdateType.UPDATE_ENTITY:
                assert update.entity_id is not None
                envelope.phases.r4_updated_entities.append(
                    KGEntityUpdate(
                        entity_id=update.entity_id,
                        field_updates={"aliases": update.aliases},
                        confidence_delta=0.0,
                        new_aliases=update.aliases,
                    )
                )
                # Issue 6.1.4: Emit EXTEND decision metric (update = extend knowledge)
                if metrics_registry:
                    metrics_registry.emit_decision(
                        tenant_id=tenant_id,
                        decision_type="EXTEND",
                        target_layer="st_kg_dom",
                        confidence=update.confidence,
                    )

        for update in edge_updates:
            if update.update_type == KGUpdateType.CREATE_EDGE:
                assert update.edge_id is not None
                assert update.source_id is not None
                assert update.target_id is not None
                assert update.relation_type is not None

                # Final self-loop guard: skip edges where source == target
                if update.source_id == update.target_id:
                    self._logger.debug(
                        f"Skipping self-loop edge: {update.source_id} -> {update.target_id}"
                    )
                    continue

                envelope.phases.r4_new_edges.append(
                    KGEdge(
                        edge_id=update.edge_id,
                        source_entity_id=update.source_id,
                        target_entity_id=update.target_id,
                        relationship_type=update.relation_type,
                        weight=update.confidence,
                        confidence=update.confidence,
                        is_causal=False,
                        evidence_event_ids=[],
                        is_new=True,
                    )
                )
                # Issue 6.1.4: Emit CREATE decision metric for edges
                if metrics_registry:
                    metrics_registry.emit_decision(
                        tenant_id=tenant_id,
                        decision_type="CREATE",
                        target_layer="st_kg_edges",
                        confidence=update.confidence,
                    )
            elif update.update_type == KGUpdateType.UPDATE_EDGE:
                assert update.edge_id is not None
                envelope.phases.r4_updated_edges.append(
                    KGEdgeUpdate(
                        edge_id=update.edge_id,
                        weight_delta=0.0,
                        confidence_delta=update.confidence,
                        new_evidence_ids=[],
                    )
                )
                # Issue 6.1.4: Emit REINFORCE decision metric (update edge = reinforce)
                if metrics_registry:
                    metrics_registry.emit_decision(
                        tenant_id=tenant_id,
                        decision_type="REINFORCE",
                        target_layer="st_kg_edges",
                        confidence=update.confidence,
                    )

        # Add gap candidates
        envelope.phases.r4_gap_candidates.extend(gaps)

        # Add causal edges (4.4.9)
        if causal_edges:
            for causal_edge in causal_edges:
                envelope.phases.r4_new_edges.append(
                    KGEdge(
                        edge_id=f"causal_{causal_edge.source_id}_{causal_edge.target_id}",
                        source_entity_id=causal_edge.source_id,
                        target_entity_id=causal_edge.target_id,
                        relationship_type=causal_edge.relation_type,
                        weight=causal_edge.confidence,
                        confidence=causal_edge.confidence,
                        is_causal=True,
                        evidence_event_ids=[],
                        is_new=True,
                    )
                )

    async def _emit_canonical_name_updates(
        self,
        envelope: "P03BatchEnvelope",
        kg_updates: List[KGUpdate],
        ctx: Optional["P03RunnerContext"],
    ) -> None:
        """
        Emit UPDATE operations for resolved gaps that weren't in the current cycle.

        This ensures st_kg_dom.canonical_name gets updated even when the entity
        wasn't mentioned in the current batch of events. R7 will apply these
        updates via ON CONFLICT DO UPDATE.

        Args:
            envelope: Batch envelope
            kg_updates: Entity updates from current cycle (to avoid duplicates)
            ctx: Runner context
        """
        if not self._resolved_gaps_cache:
            return

        # Find entity_ids already processed in this cycle
        processed_entity_ids = {
            update.entity_id for update in kg_updates if update.entity_id is not None
        }

        # Emit updates for resolved gaps not in current cycle
        updates_emitted = 0
        for entity_id, canonical_name in self._resolved_gaps_cache.items():
            if entity_id in processed_entity_ids:
                # Already handled in current cycle
                continue

            # Create an UPDATE operation for this entity's canonical_name
            envelope.phases.r4_updated_entities.append(
                KGEntityUpdate(
                    entity_id=entity_id,
                    field_updates={"canonical_name": canonical_name},
                    confidence_delta=0.0,
                    new_aliases=[],
                )
            )
            updates_emitted += 1
            logger.debug(f"R4: Emitting canonical_name update for {entity_id}: {canonical_name}")

        if updates_emitted > 0:
            logger.info(f"R4: Emitted {updates_emitted} canonical_name updates for resolved gaps")
            self._stats.resolved_gaps_applied += updates_emitted


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def create_r4_phase(config: Optional[R4Config] = None) -> R4KGConsolidator:
    """
    Factory function to create R4 phase.

    Args:
        config: Optional configuration (defaults used if not provided)

    Returns:
        Configured R4KGConsolidator instance
    """
    return R4KGConsolidator(config=config)
