"""
R3 Deduplication & Decay Phase Orchestrator.

Issue: 4.3.12
Spec Reference: Dossier §4.3, M4_EXECUTION.md

Purpose: Wire together all R3 algorithms (4.3.1-4.3.11) into a cohesive
phase that handles duplicate detection, decay computation, retention
decisions, and audit logging.

R3 Sub-phases:
    R3.1: Duplicate Detection (SimHasher, TwoStageDeduplicator, DuplicateDetector)
    R3.2: Novelty Scoring (DuplicateDetector, AdaptiveNoveltyBonusLearner)
    R3.3: Decay Computation (UnifiedDecayEngine)
    R3.4: Retention Evaluation (RetentionEnforcer, ImmunityChecker)
    R3.5: Audit Logging (PruneAuditLogger)
    R3.6: Access Tracking (AccessTracker, BayesianLambdaEstimator)
    R3.7: Regret Detection (PruneRegretDetector, PrunedEntityTracker)
    R3.8: Scale Optimization (MinHashLSH, AdaptiveDeduplicationStrategy)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

if TYPE_CHECKING:
    pass

# AccessTracker (4.3.5)
from k0.modules.consolidation.algorithms.access_tracker import (
    AccessStats,
    AccessStoreProtocol,
    AccessTracker,
    AccessTrackerConfig,
    BayesianLambdaEstimator,
    InMemoryAccessStore,
    LambdaEstimate,
)

# UnifiedDecayEngine (4.3.3)
from k0.modules.consolidation.algorithms.decay_engine import (
    DecayClassification,
    DecayConfig,
    UnifiedDecayEngine,
)

# DuplicateDetector (4.3.7)
from k0.modules.consolidation.algorithms.duplicate_detector import (
    DuplicateDetector,
    DuplicateDetectorConfig,
    DuplicationResult,
    InMemoryActivityHistory,
)

# ImmunityChecker (4.3.9)
from k0.modules.consolidation.algorithms.immunity_checker import (
    ImmunityChecker,
    ImmunityCheckerConfig,
    ImmunityLevel,
    ImmunityResult,
)

# MinHashLSH (4.3.11)
from k0.modules.consolidation.algorithms.minhash_lsh import (
    AdaptiveDeduplicationStrategy,
    AdaptiveStrategyConfig,
    DeduplicationStrategy,
    MinHashConfig,
    MinHashLSH,
)

# AdaptiveNoveltyBonusLearner (4.3.8)
from k0.modules.consolidation.algorithms.novelty_bonus_learner import (
    AdaptiveNoveltyBonusLearner,
    BonusAdjustment,
    InMemoryLearnedWeightsStore,
    LearnedWeightsStoreProtocol,
    NoveltyBonusConfig,
)

# PruneAuditLogger (4.3.10)
from k0.modules.consolidation.algorithms.prune_audit_logger import (
    AuditStoreProtocol,
    InMemoryAuditStore,
    PruneAction,
    PruneAuditLogger,
    PruneAuditLoggerConfig,
    PruneDecisionContext,
    build_prune_context,
)

# PruneRegretDetector (4.3.6)
from k0.modules.consolidation.algorithms.prune_regret_detector import (
    InMemoryPrunedEntityStore,
    PrunedEntityStoreProtocol,
    PrunedEntityTracker,
    PruneRegretConfig,
    PruneRegretDetector,
    RegretMatch,
)

# ReconciliationEngine (4.3.13 - Truth Layer Reconciliation)
from k0.modules.consolidation.algorithms.reconciliation_engine import (
    ReconciliationConfig,
    ReconciliationDecision,
    ReconciliationEngine,
)

# RetentionEnforcer (4.3.4)
from k0.modules.consolidation.algorithms.retention_enforcer import (
    BatchRetentionResult,
    ResurrectionResult,
    ResurrectionTrigger,
    RetentionDecision,
    RetentionEnforcer,
    RetentionResult,
)

# R3 Component Imports (4.3.1-4.3.11) - using documented APIs
# SimHasher (4.3.1)
from k0.modules.consolidation.algorithms.simhasher import SimHasher

# TwoStageDeduplicator (4.3.2)
from k0.modules.consolidation.algorithms.two_stage_dedup import TwoStageDeduplicator
from k0.modules.consolidation.staging.truth_query_service import TruthQueryService

# P03 Phase Interface
from k0.pipelines.p03.phase_interface import P03PhaseId, P03PhaseResult

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class R3Config:
    """
    Configuration for R3 Deduplication & Decay phase.

    Aggregates configuration for all R3 sub-components.
    """

    # Decay configuration
    decay_config: Optional[DecayConfig] = None

    # Access tracking configuration
    access_config: Optional[AccessTrackerConfig] = None

    # Novelty bonus configuration
    novelty_config: Optional[NoveltyBonusConfig] = None

    # Prune regret configuration
    regret_config: Optional[PruneRegretConfig] = None

    # Duplicate detector configuration
    dedup_config: Optional[DuplicateDetectorConfig] = None

    # Immunity configuration
    immunity_config: Optional[ImmunityCheckerConfig] = None

    # Audit logger configuration
    audit_config: Optional[PruneAuditLoggerConfig] = None

    # MinHash LSH configuration
    minhash_config: Optional[MinHashConfig] = None

    # Adaptive strategy configuration
    adaptive_config: Optional[AdaptiveStrategyConfig] = None

    # Reconciliation configuration (Issue 4.3.13)
    reconciliation_config: Optional[ReconciliationConfig] = None

    # Enable reconciliation (feature flag for safe rollout)
    # Enabled by default as of Issue 4.3.13 completion
    enable_reconciliation: bool = True

    # Debug mode
    is_debug: bool = False

    def __post_init__(self) -> None:
        """Set up debug mode for audit logger if enabled."""
        if self.is_debug and self.audit_config is None:
            self.audit_config = PruneAuditLoggerConfig(is_debug=True)


# =============================================================================
# Statistics
# =============================================================================


@dataclass
class R3PhaseStats:
    """
    Statistics from R3 phase execution.

    Tracks metrics across all R3 sub-phases.
    """

    # Duplicate detection stats
    events_processed: int = 0
    duplicates_found: int = 0
    near_duplicates_found: int = 0
    distinct_events: int = 0

    # Dedup results by event_id (for populating envelope)
    dedup_results: Dict[str, DuplicationResult] = field(default_factory=dict)

    # Novelty scoring stats
    avg_novelty_score: float = 0.0
    high_novelty_count: int = 0  # novelty >= 0.7
    low_novelty_count: int = 0  # novelty < 0.3

    # Decay stats
    entities_evaluated: int = 0
    active_count: int = 0
    archive_candidate_count: int = 0
    prune_candidate_count: int = 0

    # Retention stats
    keep_count: int = 0
    archive_count: int = 0
    tombstone_count: int = 0

    # Immunity stats
    immune_count: int = 0
    immune_by_entity: int = 0
    immune_by_attribute: int = 0

    # Audit stats
    decisions_logged: int = 0
    decisions_sampled_out: int = 0

    # Access tracking stats
    accesses_recorded: int = 0
    lambda_estimates_created: int = 0

    # Regret detection stats
    regrets_detected: int = 0
    strong_matches: int = 0
    likely_matches: int = 0

    # Scale optimization stats
    current_strategy: str = "simhash_pairwise"
    strategy_switches: int = 0
    lsh_queries: int = 0

    # Reconciliation stats (Issue 4.3.13)
    reconciliation_enabled: bool = False
    reconciliation_count: int = 0
    reinforce_count: int = 0
    extend_count: int = 0
    create_count: int = 0
    evolve_count: int = 0
    contradict_count: int = 0
    skip_count: int = 0
    prune_count: int = 0

    # Timing
    total_duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "events_processed": self.events_processed,
            "duplicates_found": self.duplicates_found,
            "near_duplicates_found": self.near_duplicates_found,
            "distinct_events": self.distinct_events,
            "avg_novelty_score": self.avg_novelty_score,
            "high_novelty_count": self.high_novelty_count,
            "low_novelty_count": self.low_novelty_count,
            "entities_evaluated": self.entities_evaluated,
            "active_count": self.active_count,
            "archive_candidate_count": self.archive_candidate_count,
            "prune_candidate_count": self.prune_candidate_count,
            "keep_count": self.keep_count,
            "archive_count": self.archive_count,
            "tombstone_count": self.tombstone_count,
            "immune_count": self.immune_count,
            "immune_by_entity": self.immune_by_entity,
            "immune_by_attribute": self.immune_by_attribute,
            "decisions_logged": self.decisions_logged,
            "decisions_sampled_out": self.decisions_sampled_out,
            "accesses_recorded": self.accesses_recorded,
            "lambda_estimates_created": self.lambda_estimates_created,
            "regrets_detected": self.regrets_detected,
            "strong_matches": self.strong_matches,
            "likely_matches": self.likely_matches,
            "current_strategy": self.current_strategy,
            "strategy_switches": self.strategy_switches,
            "lsh_queries": self.lsh_queries,
            "reconciliation_enabled": self.reconciliation_enabled,
            "reconciliation_count": self.reconciliation_count,
            "reinforce_count": self.reinforce_count,
            "extend_count": self.extend_count,
            "create_count": self.create_count,
            "evolve_count": self.evolve_count,
            "contradict_count": self.contradict_count,
            "skip_count": self.skip_count,
            "prune_count": self.prune_count,
            "total_duration_ms": self.total_duration_ms,
        }


# =============================================================================
# Store Container
# =============================================================================


@dataclass
class R3Stores:
    """
    Container for all R3 storage backends.

    Allows injection of production or test stores.
    """

    access_store: AccessStoreProtocol
    pruned_entity_store: PrunedEntityStoreProtocol
    learned_weights_store: LearnedWeightsStoreProtocol
    audit_store: AuditStoreProtocol

    @classmethod
    def create_in_memory(cls) -> "R3Stores":
        """Create in-memory stores for testing."""
        return cls(
            access_store=InMemoryAccessStore(),
            pruned_entity_store=InMemoryPrunedEntityStore(),
            learned_weights_store=InMemoryLearnedWeightsStore(),
            audit_store=InMemoryAuditStore(),
        )


# =============================================================================
# R3DedupDecay Phase Orchestrator
# =============================================================================


class R3DedupDecay:
    """
    R3 Deduplication & Decay Phase Orchestrator.

    Coordinates all R3 algorithms (4.3.1-4.3.11) to:
    - Detect duplicates using SimHash + embeddings
    - Compute novelty scores with adaptive bonuses
    - Calculate decay factors per entity
    - Make retention decisions (KEEP/ARCHIVE/TOMBSTONE)
    - Check immunity before pruning
    - Log audit records for GDPR compliance
    - Track access patterns for λ learning
    - Detect prune regret when queries match pruned entities
    - Auto-switch deduplication strategy at scale

    Usage:
        config = R3Config(is_debug=True)
        stores = R3Stores.create_in_memory()
        r3 = R3DedupDecay(config=config)

        # Process events for deduplication
        results = await r3.process_events(events, existing_events, space_id, stores)

        # Evaluate entities for decay/retention
        retention = await r3.evaluate_retention(entities, current_time, stores)

        # Check query for regret
        regrets = await r3.check_query_regret(query_embedding, space_id, query_id, stores)

    Spec: Dossier §4.3, M4_EXECUTION.md Issue 4.3.12
    """

    def __init__(
        self,
        config: Optional[R3Config] = None,
    ) -> None:
        """
        Initialize R3DedupDecay orchestrator.

        Args:
            config: R3 phase configuration.
        """
        self.config = config or R3Config()

        # Initialize all R3 components using documented APIs

        # 4.3.1: SimHasher
        self._simhasher = SimHasher()

        # 4.3.2: TwoStageDeduplicator - takes simhasher, NOT thresholds
        self._two_stage_dedup = TwoStageDeduplicator(simhasher=self._simhasher)

        # 4.3.3: UnifiedDecayEngine - takes config, NOT raw thresholds
        self._decay_engine = UnifiedDecayEngine(config=self.config.decay_config)

        # 4.3.4: RetentionEnforcer - takes decay_engine, NOT thresholds
        self._retention_enforcer = RetentionEnforcer(decay_engine=self._decay_engine)

        # 4.3.5: AccessTracker
        self._access_tracker = AccessTracker(config=self.config.access_config)
        self._lambda_estimator = BayesianLambdaEstimator(config=self.config.access_config)

        # 4.3.6: PruneRegretDetector
        self._regret_detector = PruneRegretDetector(config=self.config.regret_config)
        self._pruned_entity_tracker = PrunedEntityTracker(config=self.config.regret_config)

        # 4.3.7: DuplicateDetector - requires simhasher AND two_stage_dedup
        self._duplicate_detector = DuplicateDetector(
            simhasher=self._simhasher,
            two_stage_dedup=self._two_stage_dedup,
            config=self.config.dedup_config,
        )

        # 4.3.8: AdaptiveNoveltyBonusLearner
        self._novelty_learner = AdaptiveNoveltyBonusLearner(config=self.config.novelty_config)

        # 4.3.9: ImmunityChecker
        self._immunity_checker = ImmunityChecker(config=self.config.immunity_config)

        # 4.3.10: PruneAuditLogger
        self._audit_logger = PruneAuditLogger(config=self.config.audit_config)

        # 4.3.11: MinHashLSH
        self._minhash_lsh = MinHashLSH(config=self.config.minhash_config)
        self._adaptive_strategy = AdaptiveDeduplicationStrategy(
            minhash_lsh=self._minhash_lsh,
            config=self.config.adaptive_config,
        )

        # 4.3.13: ReconciliationEngine (optional, behind feature flag)
        self._reconciliation_engine: Optional[ReconciliationEngine] = None
        self._truth_query_service: Optional[TruthQueryService] = None

        if self.config.enable_reconciliation:
            recon_config = self.config.reconciliation_config or ReconciliationConfig()
            self._reconciliation_engine = ReconciliationEngine(config=recon_config)
            logger.info("ReconciliationEngine initialized (enabled)")

        # Tracking
        self._seen_categories: Set[str] = set()
        self._routine_patterns: Set[str] = set()
        self._activity_history = InMemoryActivityHistory()

        logger.info("R3DedupDecay orchestrator initialized")

    # -------------------------------------------------------------------------
    # Pipeline Phase Interface
    # -------------------------------------------------------------------------

    def phase_id(self) -> P03PhaseId:
        """Return the phase ID for this phase."""
        return P03PhaseId.R3_PRUNE

    def should_skip(self, envelope: "P03BatchEnvelope") -> bool:
        """Check if this phase should be skipped."""
        # R3 can be skipped if no events or no clusters
        if not envelope.events:
            return True
        if not envelope.phases.r2_clusters:
            return True
        return False

    def determinism_key(self, envelope: "P03BatchEnvelope") -> str:
        """Generate deterministic key for this phase execution."""
        return f"p03:r3:{envelope.context.cycle_id}"

    async def run(
        self,
        envelope: "P03BatchEnvelope",
        ctx: "P03RunnerContext",
    ) -> P03PhaseResult:
        """
        Execute R3 phase: Deduplication & Decay.

        Steps:
            1. Process events for duplicate detection
            2. Compute novelty scores
            3. Evaluate retention decisions
            4. Log audit records
            5. Update envelope with R3 outputs

        Args:
            envelope: Batch envelope with events from R2
            ctx: Runner context with syscalls, logger, config

        Returns:
            P03PhaseResult with status, duration, outputs summary
        """
        start_ms = int(time.time() * 1000)
        cycle_id = envelope.context.cycle_id
        space_id = envelope.context.space_id
        tenant_id = envelope.context.tenant_id

        logger.info(
            "R3: Starting deduplication & decay phase",
            extra={
                "cycle_id": cycle_id,
                "tenant_id": tenant_id,
                "space_id": space_id,
                "event_count": len(envelope.events),
                "cluster_count": len(envelope.phases.r2_clusters),
            },
        )

        # Skip check
        if self.should_skip(envelope):
            duration_ms = int(time.time() * 1000) - start_ms
            logger.info(
                "R3: Skipping phase - no events or clusters",
                extra={"cycle_id": cycle_id, "duration_ms": duration_ms},
            )
            return P03PhaseResult.skip(
                phase_id=P03PhaseId.R3_PRUNE,
                duration_ms=duration_ms,
                skip_reason="No events or clusters to process",
            )

        # Create in-memory stores for this cycle
        stores = R3Stores.create_in_memory()

        # Lazy initialization of TruthQueryService for reconciliation (Issue 4.3.13)
        if self.config.enable_reconciliation and self._truth_query_service is None:
            try:
                from k0.db.pool import get_pool

                pool = get_pool()

                # Pass pool directly - TruthQueryService will use pool.acquire()
                self._truth_query_service = TruthQueryService(pool=pool)
                if self._reconciliation_engine is not None:
                    self._reconciliation_engine.set_truth_service(self._truth_query_service)
                    logger.info("R3: TruthQueryService lazily initialized for reconciliation")
            except (RuntimeError, ImportError) as e:
                logger.warning(
                    f"R3: Could not initialize TruthQueryService: {e}. "
                    "Reconciliation will be skipped this cycle."
                )

        # Gather existing events for deduplication comparison
        # P03EventState uses embedding_id (not embedding) - filter those with embeddings
        existing_events = [e for e in envelope.events if e.embedding_id is not None]

        # Execute the full R3 phase
        current_time = int(time.time() * 1000)

        # Query truth layer entities needing decay evaluation
        # Uses TruthQueryService to fetch ACTIVE entities with decay_factor < 1.0
        entities_for_decay: List[Dict[str, Any]] = []
        if self._truth_query_service is not None:
            try:
                decay_candidates = await self._truth_query_service.query_entities_for_decay(
                    space_id=space_id,
                    tenant_id=tenant_id,
                    max_decay_factor=0.99,  # Any entity that has started decaying
                    limit_per_layer=100,  # Limit per layer to avoid overload
                )
                # Convert DecayCandidate to dict for execute()
                entities_for_decay = [c.to_dict() for c in decay_candidates]
                logger.debug(
                    f"R3: Queried {len(entities_for_decay)} entities for decay evaluation",
                    extra={
                        "cycle_id": cycle_id,
                        "entity_count": len(entities_for_decay),
                    },
                )
            except Exception as e:
                logger.warning(
                    f"R3: Failed to query entities for decay: {e}. "
                    "Decay evaluation will run on empty set."
                )
                entities_for_decay = []

        stats = await self.execute(
            events=envelope.events,
            existing_events=existing_events,
            entities_for_decay=entities_for_decay,
            space_id=space_id,
            tenant_id=tenant_id,
            cycle_id=cycle_id,
            current_time=current_time,
            stores=stores,
        )

        # Store dedup results in envelope for R6 consumption
        envelope.phases.r3_dedup_results = stats.dedup_results

        # Update each event's P03EventState with R3 results
        import json

        for event in envelope.events:
            result = stats.dedup_results.get(event.event_id)
            if result:
                event.novelty_score = result.novelty_score
                event.is_duplicate = result.is_duplicate
                event.duplicate_of_id = result.duplicate_of
                if result.near_duplicates:
                    event.near_duplicates_json = json.dumps(result.near_duplicates)
                # hamming_distance may not exist on all DuplicationResult objects
                if hasattr(result, "hamming_distance") and result.hamming_distance is not None:
                    event.hamming_distance = result.hamming_distance

        duration_ms = int(time.time() * 1000) - start_ms

        logger.info(
            "R3: Deduplication & decay phase complete",
            extra={
                "cycle_id": cycle_id,
                "duplicates_found": stats.duplicates_found,
                "near_duplicates_found": stats.near_duplicates_found,
                "distinct_events": stats.distinct_events,
                "avg_novelty": stats.avg_novelty_score,
                "duration_ms": duration_ms,
            },
        )

        return P03PhaseResult.done(
            phase_id=P03PhaseId.R3_PRUNE,
            duration_ms=duration_ms,
            outputs_summary={
                "duplicates_found": stats.duplicates_found,
                "near_duplicates_found": stats.near_duplicates_found,
                "distinct_events": stats.distinct_events,
                "avg_novelty": stats.avg_novelty_score,
            },
        )

    # -------------------------------------------------------------------------
    # R3.1: Duplicate Detection
    # -------------------------------------------------------------------------

    async def detect_duplicate(
        self,
        event: Any,
        existing_events: List[Any],
        space_id: str = "",
        event_hour: Optional[int] = None,
        activity_type: Optional[str] = None,
    ) -> DuplicationResult:
        """
        Detect if event is duplicate and compute novelty score.

        Uses DuplicateDetector which internally uses SimHasher and TwoStageDeduplicator.

        Args:
            event: Event to check (must match EventStateProtocol).
            existing_events: Events to compare against.
            space_id: Space ID for activity history.
            event_hour: Hour of day (0-23) for temporal anomaly.
            activity_type: Activity type for pattern detection.

        Returns:
            DuplicationResult with duplicate status and novelty score.
        """
        result = await self._duplicate_detector.detect(
            event=event,
            existing_events=existing_events,
            seen_categories=self._seen_categories,
            routine_patterns=self._routine_patterns,
            activity_history=self._activity_history,
            space_id=space_id,
            event_hour=event_hour,
            activity_type=activity_type,
        )

        # Track category if seen
        if activity_type and not result.is_duplicate:
            self._seen_categories.add(activity_type)

        return result

    async def process_events(
        self,
        events: List[Any],
        existing_events: List[Any],
        space_id: str,
        stores: R3Stores,
    ) -> List[DuplicationResult]:
        """
        Process batch of events for deduplication and novelty scoring.

        Args:
            events: New events to process.
            existing_events: Existing events in window.
            space_id: Space ID.
            stores: R3 storage backends.

        Returns:
            List of DuplicationResult for each event.
        """
        results: List[DuplicationResult] = []

        # Update strategy based on event count
        total_events = len(existing_events) + len(events)
        self._adaptive_strategy.update_event_count(total_events)

        for event in events:
            # Prefer UltraBERT 12-type over legacy 7-type for category tracking (Issue 0060)
            activity_type = getattr(event, "activity_type_ultrabert", None) or getattr(
                event, "activity_type", None
            )
            result = await self.detect_duplicate(
                event=event,
                existing_events=existing_events,
                space_id=space_id,
                activity_type=activity_type,
            )
            results.append(result)

            # Index in LSH if using that strategy
            if self._adaptive_strategy.get_strategy() == DeduplicationStrategy.MINHASH_LSH:
                if hasattr(event, "content_text"):
                    signature = self._minhash_lsh.compute_minhash(event.content_text)
                    self._minhash_lsh.index_event(event.event_id, signature)

        return results

    # -------------------------------------------------------------------------
    # R3.2: Novelty Scoring with Adaptive Learning
    # -------------------------------------------------------------------------

    async def process_novelty_feedback(
        self,
        signal_type: str,
        space_id: str,
        stores: R3Stores,
    ) -> Optional[BonusAdjustment]:
        """
        Process novelty feedback signal to adjust bonuses.

        Args:
            signal_type: Feedback signal type string.
            space_id: Space ID.
            stores: R3 storage backends.

        Returns:
            BonusAdjustment if processed, None otherwise.
        """
        return await self._novelty_learner.process_feedback_signal(
            signal_type=signal_type,
            space_id=space_id,
            store=stores.learned_weights_store,
        )

    async def get_learned_bonuses(
        self,
        space_id: str,
        stores: R3Stores,
    ) -> Dict[str, float]:
        """
        Get learned novelty bonus values for a space.

        Args:
            space_id: Space ID.
            stores: R3 storage backends.

        Returns:
            Dict mapping bonus name to value.
        """
        return await self._novelty_learner.get_bonuses_as_dict(
            space_id=space_id,
            store=stores.learned_weights_store,
        )

    # -------------------------------------------------------------------------
    # R3.3: Decay Computation
    # -------------------------------------------------------------------------

    def compute_decay(
        self,
        table_name: str,
        last_observed_at: int,
        current_time: int,
        importance_score: float = 0.0,
        confidence_score: float = 0.0,
        observation_count: int = 1,
    ) -> tuple[float, DecayClassification]:
        """
        Compute decay factor and classification for an entity.

        Args:
            table_name: Source table (st_epi, st_sem, etc.).
            last_observed_at: Last access timestamp (epoch ms).
            current_time: Current timestamp (epoch ms).
            importance_score: Importance score [0, 1].
            confidence_score: Confidence score [0, 1].
            observation_count: Number of observations.

        Returns:
            Tuple of (decay_factor, classification).
        """
        return self._decay_engine.compute_and_classify(
            table_name=table_name,
            last_observed_at=last_observed_at,
            current_time=current_time,
            importance_score=importance_score,
            confidence_score=confidence_score,
            observation_count=observation_count,
        )

    # -------------------------------------------------------------------------
    # R3.4: Retention Evaluation with Immunity
    # -------------------------------------------------------------------------

    def check_immunity(
        self,
        entity_type: str,
        entity_attributes: Dict[str, Any],
    ) -> ImmunityResult:
        """
        Check if entity should be immune to decay.

        Args:
            entity_type: Type of entity (PERSON, FAMILY_MEMBER, etc.).
            entity_attributes: Entity attributes dict.

        Returns:
            ImmunityResult with immunity status and reason.
        """
        return self._immunity_checker.should_mark_immune(
            entity_type=entity_type,
            entity_attributes=entity_attributes,
        )

    def evaluate_retention(
        self,
        entity_id: str,
        table_name: str,
        last_observed_at: int,
        current_time: int,
        current_status: str = "ACTIVE",
        importance_score: float = 0.0,
        confidence_score: float = 0.0,
        observation_count: int = 1,
    ) -> RetentionResult:
        """
        Evaluate single entity for retention decision.

        Args:
            entity_id: Entity identifier.
            table_name: Source table.
            last_observed_at: Last access timestamp (epoch ms).
            current_time: Current timestamp (epoch ms).
            current_status: Current entity status.
            importance_score: Importance score.
            confidence_score: Confidence score.
            observation_count: Observation count.

        Returns:
            RetentionResult with decision.
        """
        return self._retention_enforcer.evaluate(
            entity_id=entity_id,
            table_name=table_name,
            last_observed_at=last_observed_at,
            current_time=current_time,
            current_status=current_status,
            importance_score=importance_score,
            confidence_score=confidence_score,
            observation_count=observation_count,
        )

    def evaluate_retention_batch(
        self,
        records: List[Dict[str, Any]],
        current_time: int,
    ) -> BatchRetentionResult:
        """
        Evaluate batch of entities for retention decisions.

        Args:
            records: List of entity records with keys:
                - entity_id, table_name, last_observed_at
                - Optional: importance_score, confidence_score, observation_count
            current_time: Current timestamp (epoch ms).

        Returns:
            BatchRetentionResult with all results.
        """
        return self._retention_enforcer.evaluate_batch(
            records=records,
            current_time=current_time,
        )

    def resurrect_entity(
        self,
        entity_id: str,
        table_name: str,
        current_decay: float,
        current_status: str,
        trigger: ResurrectionTrigger,
        current_time: Optional[int] = None,
    ) -> ResurrectionResult:
        """
        Resurrect an archived/tombstoned entity.

        Args:
            entity_id: Entity identifier.
            table_name: Source table.
            current_decay: Current decay factor.
            current_status: Current status (ARCHIVED, TOMBSTONE).
            trigger: What triggered resurrection.
            current_time: Current timestamp (optional).

        Returns:
            ResurrectionResult with new decay and status.
        """
        return self._retention_enforcer.resurrect(
            entity_id=entity_id,
            table_name=table_name,
            current_decay=current_decay,
            current_status=current_status,
            trigger=trigger,
            current_time=current_time,
        )

    # -------------------------------------------------------------------------
    # R3.5: Audit Logging
    # -------------------------------------------------------------------------

    async def log_prune_decision(
        self,
        action: PruneAction,
        context: PruneDecisionContext,
        space_id: str,
        tenant_id: str,
        cycle_id: str,
        stores: R3Stores,
    ) -> Optional[str]:
        """
        Log a prune/archive/tombstone decision.

        Args:
            action: The prune action taken.
            context: Decision context.
            space_id: Space ID.
            tenant_id: Tenant ID.
            cycle_id: Consolidation cycle ID.
            stores: R3 storage backends.

        Returns:
            audit_id if logged, None if sampled out.
        """
        return await self._audit_logger.log_prune_decision(
            action=action,
            context=context,
            space_id=space_id,
            tenant_id=tenant_id,
            cycle_id=cycle_id,
            store=stores.audit_store,
        )

    async def log_retention_decision(
        self,
        result: RetentionResult,
        effective_lambda: float,
        is_immune: bool,
        space_id: str,
        tenant_id: str,
        cycle_id: str,
        stores: R3Stores,
    ) -> Optional[str]:
        """
        Log a retention decision with full context.

        Args:
            result: RetentionResult from evaluate_retention.
            effective_lambda: Lambda used for decay.
            is_immune: Whether entity is immune.
            space_id: Space ID.
            tenant_id: Tenant ID.
            cycle_id: Consolidation cycle ID.
            stores: R3 storage backends.

        Returns:
            audit_id if logged, None if sampled out.
        """
        # Map retention decision to prune action
        action_map = {
            RetentionDecision.KEEP: PruneAction.SKIP,
            RetentionDecision.ARCHIVE: PruneAction.ARCHIVE,
            RetentionDecision.TOMBSTONE: PruneAction.TOMBSTONE,
        }
        action = action_map.get(result.decision, PruneAction.SKIP)

        # Build context using helper
        _, context = build_prune_context(
            memory_id=result.entity_id,
            source_table=result.table_name,
            decay_factor=result.current_decay,
            effective_lambda=effective_lambda,
            days_since_access=int(result.days_since_access),
            access_count=1,  # Would need to track this
            is_immune=is_immune,
        )

        return await self.log_prune_decision(
            action=action,
            context=context,
            space_id=space_id,
            tenant_id=tenant_id,
            cycle_id=cycle_id,
            stores=stores,
        )

    # -------------------------------------------------------------------------
    # R3.6: Access Tracking
    # -------------------------------------------------------------------------

    async def record_access(
        self,
        entity_id: str,
        entity_table: str,
        accessed_at_ms: int,
        stores: R3Stores,
    ) -> AccessStats:
        """
        Record entity access for λ learning.

        Args:
            entity_id: Entity identifier.
            entity_table: Source table.
            accessed_at_ms: Access timestamp (epoch ms).
            stores: R3 storage backends.

        Returns:
            Updated AccessStats.
        """
        return await self._access_tracker.record_access(
            entity_id=entity_id,
            entity_table=entity_table,
            accessed_at_ms=accessed_at_ms,
            store=stores.access_store,
        )

    async def estimate_and_persist_lambda(
        self,
        stats: AccessStats,
        space_id: str,
        stores: R3Stores,
    ) -> Optional[LambdaEstimate]:
        """
        Estimate λ from access stats and persist if eligible.

        Args:
            stats: Access statistics.
            space_id: Space ID.
            stores: R3 storage backends.

        Returns:
            LambdaEstimate if created, None otherwise.
        """
        if not stats.eligible_for_learning:
            return None

        intervals = self._access_tracker.get_inter_access_intervals_days(stats)
        estimate = self._lambda_estimator.estimate_lambda(
            entity_id=stats.entity_id,
            entity_table=stats.entity_table,
            intervals_days=intervals,
        )

        if estimate:
            await self._lambda_estimator.persist_lambda(
                estimate=estimate,
                space_id=space_id,
                store=stores.access_store,
            )

        return estimate

    # -------------------------------------------------------------------------
    # R3.7: Regret Detection
    # -------------------------------------------------------------------------

    async def track_pruned_entity(
        self,
        entity_id: str,
        entity_type: str,
        canonical_name: str,
        embedding: Any,  # np.ndarray
        space_id: str,
        layer_table: str,
        decay_factor: float,
        lambda_value: float,
        pruned_at: int,
        stores: R3Stores,
    ) -> str:
        """
        Track a pruned entity for regret detection.

        Args:
            entity_id: Entity identifier.
            entity_type: Entity type (PERSON, PLACE, etc.).
            canonical_name: Normalized name.
            embedding: Entity embedding.
            space_id: Space ID.
            layer_table: Source table.
            decay_factor: Decay factor at prune.
            lambda_value: Lambda used.
            pruned_at: Prune timestamp (epoch ms).
            stores: R3 storage backends.

        Returns:
            prune_id for tracking.
        """
        return await self._pruned_entity_tracker.track_pruned_entity(
            entity_id=entity_id,
            entity_type=entity_type,
            canonical_name=canonical_name,
            embedding=embedding,
            space_id=space_id,
            layer_table=layer_table,
            decay_factor=decay_factor,
            lambda_value=lambda_value,
            pruned_at=pruned_at,
            store=stores.pruned_entity_store,
        )

    async def check_query_regret(
        self,
        query_embedding: Any,  # np.ndarray
        space_id: str,
        query_id: str,
        stores: R3Stores,
    ) -> List[RegretMatch]:
        """
        Check if query matches recently pruned entities.

        Args:
            query_embedding: Query embedding vector.
            space_id: Space ID.
            query_id: Query identifier.
            stores: R3 storage backends.

        Returns:
            List of RegretMatch for matches.
        """
        current_time_ms = int(time.time() * 1000)
        matches = await self._regret_detector.check_query(
            query_embedding=query_embedding,
            space_id=space_id,
            query_id=query_id,
            current_time_ms=current_time_ms,
            store=stores.pruned_entity_store,
        )

        # Emit regret signals for each match
        for match in matches:
            await self._regret_detector.emit_regret_signal(
                match=match,
                space_id=space_id,
                store=stores.pruned_entity_store,
            )

        return matches

    # -------------------------------------------------------------------------
    # R3.9: Reconciliation Engine (Issue 4.3.13)
    # -------------------------------------------------------------------------

    def set_truth_query_service(self, service: TruthQueryService) -> None:
        """
        Set the TruthQueryService for reconciliation.

        Must be called before reconciliation if enable_reconciliation is True.
        Typically set by the runner with a database connection factory.

        Args:
            service: TruthQueryService instance with database connection.
        """
        self._truth_query_service = service
        if self._reconciliation_engine is not None:
            self._reconciliation_engine.set_truth_service(service)
            logger.info("TruthQueryService connected to ReconciliationEngine")

    async def reconcile_event(
        self,
        event: Any,  # P03EventState
        space_id: str,
        tenant_id: str,
    ) -> Optional[ReconciliationDecision]:
        """
        Make reconciliation decision for a single event.

        Queries truth layers, computes similarity, applies thresholds,
        and sets the reconciliation fields on the event.

        Args:
            event: P03EventState to reconcile.
            space_id: Space context for truth queries.
            tenant_id: Tenant context for truth queries.

        Returns:
            ReconciliationDecision if reconciliation enabled, None otherwise.
        """
        if self._reconciliation_engine is None:
            return None

        decision = await self._reconciliation_engine.decide(
            event=event,
            space_id=space_id,
            tenant_id=tenant_id,
        )

        # Apply decision to event state
        event.set_reconciliation(
            action=decision.action,
            match_id=decision.best_match_id,
            match_layer=decision.best_match_layer,
            similarity=decision.similarity_score,
            confidence=decision.confidence,
            reason=decision.reason,
        )

        return decision

    async def reconcile_batch(
        self,
        events: List[Any],  # List[P03EventState]
        space_id: str,
        tenant_id: str,
    ) -> Dict[str, ReconciliationDecision]:
        """
        Make reconciliation decisions for a batch of events.

        Args:
            events: List of P03EventState to reconcile.
            space_id: Space context for truth queries.
            tenant_id: Tenant context for truth queries.

        Returns:
            Dict mapping event_id to ReconciliationDecision.
        """
        results: Dict[str, ReconciliationDecision] = {}

        if self._reconciliation_engine is None:
            return results

        for event in events:
            decision = await self.reconcile_event(
                event=event,
                space_id=space_id,
                tenant_id=tenant_id,
            )
            if decision is not None:
                results[event.event_id] = decision

        return results

    def get_reconciliation_metrics(self) -> Dict[str, Any]:
        """Get reconciliation engine metrics."""
        if self._reconciliation_engine is None:
            return {"enabled": False}

        metrics = self._reconciliation_engine.get_metrics()
        metrics["enabled"] = True
        return metrics

    # -------------------------------------------------------------------------
    # R3.8: Scale Optimization
    # -------------------------------------------------------------------------

    def get_current_strategy(self) -> DeduplicationStrategy:
        """Get current deduplication strategy."""
        return self._adaptive_strategy.get_strategy()

    def update_event_count(self, count: int) -> Optional[tuple[str, str]]:
        """
        Update event count and check for strategy switch.

        Args:
            count: New event count.

        Returns:
            Tuple of (old_strategy, new_strategy) if switch occurred.
        """
        return self._adaptive_strategy.update_event_count(count)

    def get_lsh_stats(self) -> Dict[str, Any]:
        """Get MinHash LSH index statistics."""
        stats = self._minhash_lsh.get_stats()
        return {
            "event_count": stats.event_count,
            "bucket_count": stats.bucket_count,
            "avg_bucket_size": stats.avg_bucket_size,
            "strategy": stats.strategy.value,
        }

    # -------------------------------------------------------------------------
    # Full R3 Phase Execution
    # -------------------------------------------------------------------------

    async def execute(
        self,
        events: List[Any],
        existing_events: List[Any],
        entities_for_decay: List[Dict[str, Any]],
        space_id: str,
        tenant_id: str,
        cycle_id: str,
        current_time: int,
        stores: R3Stores,
    ) -> R3PhaseStats:
        """
        Execute full R3 phase: deduplication, decay, and retention.

        Args:
            events: New events to process.
            existing_events: Existing events in window.
            entities_for_decay: Entities to evaluate for decay.
            space_id: Space ID.
            tenant_id: Tenant ID.
            cycle_id: Consolidation cycle ID.
            current_time: Current timestamp (epoch ms).
            stores: R3 storage backends.

        Returns:
            R3PhaseStats with execution statistics.
        """
        start_time = time.time()
        stats = R3PhaseStats()

        # R3.1: Process events for deduplication
        dedup_results = await self.process_events(
            events=events,
            existing_events=existing_events,
            space_id=space_id,
            stores=stores,
        )

        stats.events_processed = len(dedup_results)
        novelty_sum = 0.0

        for i, result in enumerate(dedup_results):
            # Store result keyed by event_id for envelope population
            if i < len(events):
                event_id = getattr(events[i], "event_id", None)
                if event_id:
                    stats.dedup_results[event_id] = result

            if result.is_duplicate:
                stats.duplicates_found += 1
            elif result.near_duplicates:
                stats.near_duplicates_found += 1
            else:
                stats.distinct_events += 1

            novelty_sum += result.novelty_score
            if result.novelty_score >= 0.7:
                stats.high_novelty_count += 1
            elif result.novelty_score < 0.3:
                stats.low_novelty_count += 1

        if stats.events_processed > 0:
            stats.avg_novelty_score = novelty_sum / stats.events_processed

        # R3.4: Evaluate entities for retention
        batch_result = self.evaluate_retention_batch(
            records=entities_for_decay,
            current_time=current_time,
        )

        stats.entities_evaluated = batch_result.total_evaluated
        stats.keep_count = batch_result.keep_count
        stats.archive_count = batch_result.archive_count
        stats.tombstone_count = batch_result.tombstone_count

        # Count classifications and check immunity
        for result in batch_result.results:
            # Get entity attributes for immunity check
            entity_record = next(
                (e for e in entities_for_decay if e.get("entity_id") == result.entity_id),
                {},
            )
            entity_type = entity_record.get("entity_type", "")
            entity_attrs = entity_record.get("attributes", {})

            # Check immunity
            immunity = self.check_immunity(entity_type, entity_attrs)
            if immunity.is_immune:
                stats.immune_count += 1
                if immunity.level == ImmunityLevel.ENTITY:
                    stats.immune_by_entity += 1
                elif immunity.level == ImmunityLevel.ATTRIBUTE:
                    stats.immune_by_attribute += 1

            # Count by classification
            if result.classification == DecayClassification.ACTIVE:
                stats.active_count += 1
            elif result.classification == DecayClassification.ARCHIVE_CANDIDATE:
                stats.archive_candidate_count += 1
            elif result.classification == DecayClassification.PRUNE_CANDIDATE:
                stats.prune_candidate_count += 1

            # R3.5: Log audit record
            effective_lambda = self._decay_engine.compute_effective_lambda(
                table_name=result.table_name,
                importance_score=result.importance_score,
            )
            audit_id = await self.log_retention_decision(
                result=result,
                effective_lambda=effective_lambda,
                is_immune=immunity.is_immune,
                space_id=space_id,
                tenant_id=tenant_id,
                cycle_id=cycle_id,
                stores=stores,
            )
            if audit_id:
                stats.decisions_logged += 1
            else:
                stats.decisions_sampled_out += 1

        # R3.8: Update strategy stats
        stats.current_strategy = self.get_current_strategy().value
        stats.strategy_switches = len(self._adaptive_strategy.strategy_switches)
        stats.lsh_queries = self._minhash_lsh.query_count

        # R3.9: Reconciliation (Issue 4.3.13)
        stats.reconciliation_enabled = self.config.enable_reconciliation
        if self.config.enable_reconciliation and self._reconciliation_engine is not None:
            recon_decisions = await self.reconcile_batch(
                events=events,
                space_id=space_id,
                tenant_id=tenant_id,
            )

            # Update stats from reconciliation decisions
            stats.reconciliation_count = len(recon_decisions)
            from k0.pipelines.p03.event_state import ReconciliationAction

            for decision in recon_decisions.values():
                if decision.action == ReconciliationAction.REINFORCE:
                    stats.reinforce_count += 1
                elif decision.action == ReconciliationAction.EXTEND:
                    stats.extend_count += 1
                elif decision.action == ReconciliationAction.CREATE:
                    stats.create_count += 1
                elif decision.action == ReconciliationAction.EVOLVE:
                    stats.evolve_count += 1
                elif decision.action == ReconciliationAction.CONTRADICT:
                    stats.contradict_count += 1
                elif decision.action == ReconciliationAction.SKIP:
                    stats.skip_count += 1
                elif decision.action == ReconciliationAction.PRUNE:
                    stats.prune_count += 1

            logger.info(
                f"R3.9 reconciliation: {stats.reconciliation_count} events, "
                f"REINFORCE={stats.reinforce_count}, EXTEND={stats.extend_count}, "
                f"CREATE={stats.create_count}, EVOLVE={stats.evolve_count}"
            )

        stats.total_duration_ms = (time.time() - start_time) * 1000

        logger.info(
            f"R3 phase complete: {stats.events_processed} events, "
            f"{stats.entities_evaluated} entities, "
            f"{stats.decisions_logged} decisions logged, "
            f"{stats.total_duration_ms:.2f}ms"
        )

        return stats

    # -------------------------------------------------------------------------
    # Component Access (for testing)
    # -------------------------------------------------------------------------

    @property
    def simhasher(self) -> SimHasher:
        """Get SimHasher instance."""
        return self._simhasher

    @property
    def two_stage_dedup(self) -> TwoStageDeduplicator:
        """Get TwoStageDeduplicator instance."""
        return self._two_stage_dedup

    @property
    def decay_engine(self) -> UnifiedDecayEngine:
        """Get UnifiedDecayEngine instance."""
        return self._decay_engine

    @property
    def retention_enforcer(self) -> RetentionEnforcer:
        """Get RetentionEnforcer instance."""
        return self._retention_enforcer

    @property
    def access_tracker(self) -> AccessTracker:
        """Get AccessTracker instance."""
        return self._access_tracker

    @property
    def regret_detector(self) -> PruneRegretDetector:
        """Get PruneRegretDetector instance."""
        return self._regret_detector

    @property
    def duplicate_detector(self) -> DuplicateDetector:
        """Get DuplicateDetector instance."""
        return self._duplicate_detector

    @property
    def novelty_learner(self) -> AdaptiveNoveltyBonusLearner:
        """Get AdaptiveNoveltyBonusLearner instance."""
        return self._novelty_learner

    @property
    def immunity_checker(self) -> ImmunityChecker:
        """Get ImmunityChecker instance."""
        return self._immunity_checker

    @property
    def audit_logger(self) -> PruneAuditLogger:
        """Get PruneAuditLogger instance."""
        return self._audit_logger

    @property
    def minhash_lsh(self) -> MinHashLSH:
        """Get MinHashLSH instance."""
        return self._minhash_lsh

    @property
    def adaptive_strategy(self) -> AdaptiveDeduplicationStrategy:
        """Get AdaptiveDeduplicationStrategy instance."""
        return self._adaptive_strategy

    @property
    def reconciliation_engine(self) -> Optional[ReconciliationEngine]:
        """Get ReconciliationEngine instance (if enabled)."""
        return self._reconciliation_engine

    @property
    def truth_query_service(self) -> Optional[TruthQueryService]:
        """Get TruthQueryService instance (if configured)."""
        return self._truth_query_service


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def create_r3_phase(config: Optional[R3Config] = None) -> R3DedupDecay:
    """
    Factory function to create R3 phase.

    By default, creates R3 with reconciliation enabled (Issue 4.3.13).

    Args:
        config: Optional configuration. If None, uses defaults with
                reconciliation enabled.

    Returns:
        Configured R3DedupDecay instance
    """
    return R3DedupDecay(config=config)
