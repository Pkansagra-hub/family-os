"""
Consolidation Algorithms — Core cognitive algorithms for P03.

This package contains all reusable algorithms for memory consolidation:

R1 Algorithms (Epic 4.1):
    - ImportanceScorer: Weighted importance score computation (Issue 4.1.1)
    - HebbianUpdater (to be implemented in phases/r1)

R2 Algorithms (Epic 4.2 — Episodic Clustering):
    - CompositeDistance: Semantic + temporal distance metric (Issue 4.2.1)
    - EpisodeSplitter: Pre-clustering sequence splitting (Issue 4.2.2)
    - EpisodicHDBSCAN: HDBSCAN with composite distance and noise rescue (Issue 4.2.3)
    - CentroidCalculator: Weighted centroid computation (Issue 4.2.4)
    - EpsAdjuster: Adaptive eps learning (Issue 4.2.5)
    - MinSamplesAdjuster: Adaptive min_samples learning (Issue 4.2.6)
    - ClusterQualityTracker: Closed-loop quality metrics (Issue 4.2.7)

R3 Algorithms (Epic 4.3 — Dedup + Decay):
    - SimHasher: 64-bit locality-sensitive hashing (Issue 4.3.1)
    - TwoStageDeduplicator: SimHash + embedding verification (Issue 4.3.2)
    - UnifiedDecayEngine: Exponential decay for 8 memory layers (Issue 4.3.3)
    - RetentionEnforcer: Archive/tombstone decisioning (Issue 4.3.4)
    - AccessTracker: Per-entity access tracking (Issue 4.3.5)
    - PruneRegretDetector: Detect pruning regret (Issue 4.3.6)
    - NoveltyScorer: Calculate novelty scores (Issue 4.3.7)

R4 Algorithms (Epic 4.4 — Knowledge Graph):
    - EntityResolver: Entity deduplication and linking
    - RelationshipExtractor: Extract semantic relationships
    - ConceptHierarchyBuilder: Build concept taxonomies

Usage:
    from k0.modules.consolidation.algorithms import SimHasher, UnifiedDecayEngine

    hasher = SimHasher()
    simhash = hasher.compute_simhash("Wake up at 7am")

    decay_engine = UnifiedDecayEngine()
    decay_factor = decay_engine.compute_decay_factor(...)

Spec Reference:
    - Dossier Appendix C (Algorithm Specifications)
    - M4_EXECUTION.md (Implementation Details)
"""

# R3 Access Tracker (Epic 4.3.5)
from k0.modules.consolidation.algorithms.access_tracker import (
    AccessStats,
    AccessTracker,
    AccessTrackerConfig,
    BayesianLambdaEstimator,
    LambdaEstimate,
)

# R4 Ambiguous Entity Resolution (Epic 4.4.4)
from k0.modules.consolidation.algorithms.ambiguous_resolver import (
    P03_RESOLUTION_THRESHOLD_AUTO,
    P03_RESOLUTION_THRESHOLD_FLAG,
    AmbiguousEntityResolver,
    AmbiguousResolverConfig,
    CandidateEntity,
    EventContext,
    ResolutionBreakdown,
    ResolutionOutcome,
    ResolutionResult,
    get_ambiguous_resolver,
)

# R2 Centroid Calculator (Epic 4.2.4)
from k0.modules.consolidation.algorithms.centroid_calculator import (
    CentroidCalculator,
    CentroidResult,
    EpisodeCandidate,
    SecondaryCentroidSelector,
    WeightingStrategy,
)

# R2 Cluster Quality Tracker (Epic 4.2.7)
from k0.modules.consolidation.algorithms.cluster_quality import (
    ClusterQualityMetrics,
    ClusterQualityTracker,
)

# R2 Episodic Clustering (Epic 4.2)
from k0.modules.consolidation.algorithms.composite_distance import (
    ClusteringDistanceParams,
    CompositeDistance,
    DBSCANParams,
    EnsembleDistance,
    EnsembleDistanceConfig,
    FallbackPolicy,
)

# R4 Confidence Router (Epic 4.4.5)
from k0.modules.consolidation.algorithms.confidence_router import (
    P03_CONFIDENCE_THRESHOLD_AUTO,
    P03_CONFIDENCE_THRESHOLD_FLAG,
    ConfidenceBand,
    ConfidenceRouter,
    ConfidenceRouterConfig,
    GapPayload,
    GapType,
    OutboxEntry,
    RoutingResult,
    get_confidence_router,
    quick_band,
)

# R2 Cross-Batch Extend (Epic 6.4)
from k0.modules.consolidation.algorithms.cross_batch_extend import (
    CrossBatchExtendConfig,
    CrossBatchExtendMatcher,
    CrossBatchExtendStats,
    ExtendMatch,
)

# R3 Decay Engine (Epic 4.3.3)
from k0.modules.consolidation.algorithms.decay_engine import (
    LAYER_LAMBDAS,
    DecayClassification,
    DecayConfig,
    UnifiedDecayEngine,
)

# R3 Duplicate Detector (Epic 4.3.7)
from k0.modules.consolidation.algorithms.duplicate_detector import (
    DuplicateDetector,
    DuplicateDetectorConfig,
    DuplicationResult,
    InMemoryActivityHistory,
    NoveltyBonuses,
)

# R4 Entity Disambiguation (Epic 4.4.2)
from k0.modules.consolidation.algorithms.entity_disambiguator import (
    P03_DISAMBIGUATION_THRESHOLD,
    DisambiguationBreakdown,
    DisambiguationWeights,
    EntityDisambiguator,
    get_entity_disambiguator,
)

# R4 Entity Extraction (Epic 4.4.1)
from k0.modules.consolidation.algorithms.entity_extractor import (
    ExtractedEntity,
    KGEntityType,
    UltraBERTEntityExtractor,
    get_entity_extractor,
)

# R4 Entity Merger (Epic 4.4.7)
from k0.modules.consolidation.algorithms.entity_merger import (
    CascadeCounts,
    EntityMerger,
    EntitySnapshot,
    MergeResult,
    MergerMetrics,
    MergeStatus,
    get_entity_merger,
)
from k0.modules.consolidation.algorithms.episode_splitter import (
    BoundaryDecision,
    EpisodeSplitter,
    SplitConfig,
    SplitReason,
    SplitResult,
    WeakBoundary,
)

# R2 Episodic Coherence (M4-RSCH-04: replaces silhouette as primary quality signal)
from k0.modules.consolidation.algorithms.episodic_coherence import (
    BatchCoherenceSummary,
    CoherenceDimensions,
    EpisodicCoherenceResult,
    EpisodicCoherenceScorer,
    compute_batch_coherence,
)

# R2 Episodic HDBSCAN Clustering with Noise Rescue (Epic 4.2.3)
from k0.modules.consolidation.algorithms.episodic_hdbscan import (
    EpisodicHDBSCAN,
    HDBSCANClusteringResult,
    HDBSCANParams,
)

# Uncomment as implemented:
# from k0.modules.consolidation.algorithms.eps_adjuster import EpsAdjuster
# R2 Adaptive Learning (Epic 4.2.5-4.2.6)
from k0.modules.consolidation.algorithms.eps_adjuster import (
    EpsAdjuster,
    EpsAdjustmentConfig,
    EpsAdjustmentResult,
)

# R2 Hebbian Co-occurrence Distance Boost (Epic 5.1)
from k0.modules.consolidation.algorithms.hebbian_boost import (
    CoOccurrenceEdge,
    HebbinaBoostConfig,
    apply_hebbian_boost,
    build_cooccurrence_graph,
    compute_pairwise_affinity,
)

# R1 Hebbian Learning (Epic 4.1)
from k0.modules.consolidation.algorithms.hebbian_learner import (
    AntiHebbianSignal,
    CoOccurrence,
    EdgeUpdate,
    HebbianConfig,
    HebbianLearner,
    KGEdge,
    RelationType,
)

# R3 Immunity Checker (Epic 4.3.9)
from k0.modules.consolidation.algorithms.immunity_checker import (
    ATTRIBUTE_LEVEL_IMMUNITY,
    ENTITY_LEVEL_IMMUNE_TYPES,
    IMMUNITY_ONTOLOGY,
    ImmunityChecker,
    ImmunityCheckerConfig,
    ImmunityLevel,
    ImmunityMetricsCollector,
    ImmunityOntologyEntry,
    ImmunityResult,
    auto_mark_immunity,
)

# R1 Importance Scoring (Epic 4.1)
from k0.modules.consolidation.algorithms.importance_scorer import (
    ImportanceBreakdown,
    ImportanceScorer,
    ImportanceWeights,
    LearnedWeights,
    WeightStoreProtocol,
)

# R1 Weight Learning (Epic 4.1.5-4.1.6)
from k0.modules.consolidation.algorithms.importance_weight_learner import (
    ImportanceWeightLearner,
    TrainingBatch,
    TrainingResult,
    TrainingSample,
    WeightLearnerConfig,
    WeightPersistenceProtocol,
)

# R5 MCTS Shadow Validation (Epic 4.5)
from k0.modules.consolidation.algorithms.mcts_shadow import (
    CycleShadowTracker,
    PromotionAnalysis,
    PromotionRecommendation,
    ShadowDecisionRecord,
    ShadowDecisionType,
    ShadowOutcomeTracker,
    ShadowValidationStats,
)

# R4 Merge Threshold Learner (Epic 4.4.6)
from k0.modules.consolidation.algorithms.merge_threshold_learner import (
    AdaptiveMergeThresholds,
    MergeDecision,
    ThresholdAdjustment,
    ThresholdBounds,
    ThresholdMetrics,
    get_adaptive_merge_thresholds,
)
from k0.modules.consolidation.algorithms.min_samples_adjuster import (
    MinSamplesAdjuster,
    MinSamplesAdjustmentResult,
    MinSamplesConfig,
)

# R3 MinHash LSH (Epic 4.3.11)
from k0.modules.consolidation.algorithms.minhash_lsh import (
    DEFAULT_MINHASH_LSH_ENABLED,
    DEFAULT_NUM_BANDS,
    DEFAULT_NUM_HASHES,
    DEFAULT_SIMILARITY_THRESHOLD,
    THRESHOLD_BUCKETING,
    THRESHOLD_PAIRWISE,
    AdaptiveDeduplicationStrategy,
    AdaptiveStrategyConfig,
    DeduplicationStrategy,
    LSHCandidate,
    LSHIndexStats,
    MinHashConfig,
    MinHashLSH,
    MinHashMetricsCollector,
    compute_jaccard_similarity,
    estimate_lsh_threshold,
)

# R3 Novelty Bonus Learner (Epic 4.3.8)
from k0.modules.consolidation.algorithms.novelty_bonus_learner import (
    BONUS_MAX,
    BONUS_MIN,
    DEFAULT_FIRST_OCCURRENCE_BONUS,
    DEFAULT_MILESTONE_BONUS,
    DEFAULT_RARE_PATTERN_BONUS,
    DEFAULT_TEMPORAL_ANOMALY_BONUS,
    AdaptiveNoveltyBonusLearner,
    BonusAdjustment,
    InMemoryLearnedWeightsStore,
    NoveltyBonusConfig,
    NoveltyBonusType,
    NoveltyFeedbackSignal,
    clamp_bonus,
    get_default_bonus,
)

# Observation Context (Issue 7.2)
from k0.modules.consolidation.algorithms.observation_context import ObservationContext

# R3 Prune Audit Logger (Epic 4.3.10)
from k0.modules.consolidation.algorithms.prune_audit_logger import (
    InMemoryAuditStore,
    PruneAction,
    PruneAuditLogger,
    PruneAuditLoggerConfig,
    PruneAuditRecord,
    PruneDecisionContext,
    build_prune_context,
    determine_prune_action,
    parse_inputs_json,
    parse_outputs_json,
)

# R3 Prune Regret Detector (Epic 4.3.6)
from k0.modules.consolidation.algorithms.prune_regret_detector import (
    InMemoryPrunedEntityStore,
    MatchType,
    PrunedEntitiesCleanup,
    PrunedEntity,
    PrunedEntityTracker,
    PruneRegretConfig,
    PruneRegretDetector,
    RegretMatch,
)

# R3 Reconciliation Engine (Issue 4.3.13)
from k0.modules.consolidation.algorithms.reconciliation_engine import (
    ReconciliationConfig,
    ReconciliationDecision,
    ReconciliationEngine,
)

# R3 Retention Enforcer (Epic 4.3.4)
from k0.modules.consolidation.algorithms.retention_enforcer import (
    BatchRetentionResult,
    ResurrectionResult,
    ResurrectionTrigger,
    RetentionDecision,
    RetentionEnforcer,
    RetentionResult,
)

# R2 Same-Thread Merge (Epic 6.3)
from k0.modules.consolidation.algorithms.same_thread_merge import (
    SameThreadMergeConfig,
    SameThreadMerger,
    SameThreadMergeStats,
)

# R3 Dedup + Decay (Epic 4.3)
from k0.modules.consolidation.algorithms.simhasher import SimHasher

# R2 Thread Purity Correction (Epic 6.2)
from k0.modules.consolidation.algorithms.thread_purity import (
    PurityCorrectionStats,
    ThreadPurityCorrector,
)
from k0.modules.consolidation.algorithms.two_stage_dedup import (
    DuplicateDecision,
    DuplicateMatch,
    EventStateProtocol,
    Stage1SimHashFilter,
    Stage2EmbeddingVerifier,
    TwoStageDeduplicator,
    find_duplicates_async,
)

__all__ = [
    # R1 Importance
    "ImportanceScorer",
    "ImportanceWeights",
    "ImportanceBreakdown",
    "LearnedWeights",
    "WeightStoreProtocol",
    # R1 Weight Learning
    "ImportanceWeightLearner",
    "WeightLearnerConfig",
    "TrainingSample",
    "TrainingBatch",
    "TrainingResult",
    "WeightPersistenceProtocol",
    # R1 Hebbian
    "HebbianLearner",
    "HebbianConfig",
    "KGEdge",
    "EdgeUpdate",
    "CoOccurrence",
    "RelationType",
    "AntiHebbianSignal",
    # R2 Episodic Clustering
    "CompositeDistance",
    "EnsembleDistance",
    "EnsembleDistanceConfig",
    "FallbackPolicy",
    "ClusteringDistanceParams",
    "DBSCANParams",
    "EpisodeSplitter",
    "SplitConfig",
    "SplitReason",
    "SplitResult",
    "BoundaryDecision",
    "WeakBoundary",
    "CentroidCalculator",
    "CentroidResult",
    "EpisodeCandidate",
    "SecondaryCentroidSelector",
    "WeightingStrategy",
    # R2 Adaptive Learning
    "EpsAdjuster",
    "EpsAdjustmentConfig",
    "EpsAdjustmentResult",
    "MinSamplesAdjuster",
    "MinSamplesConfig",
    "MinSamplesAdjustmentResult",
    # R2 Cluster Quality
    "ClusterQualityMetrics",
    "ClusterQualityTracker",
    # R2 Episodic Coherence
    "BatchCoherenceSummary",
    "CoherenceDimensions",
    "EpisodicCoherenceResult",
    "EpisodicCoherenceScorer",
    "compute_batch_coherence",
    # R2 Thread Purity Correction (Epic 6.2)
    "ThreadPurityCorrector",
    "PurityCorrectionStats",
    # R2 Same-Thread Merge (Epic 6.3)
    "SameThreadMerger",
    "SameThreadMergeConfig",
    "SameThreadMergeStats",
    # R2 Cross-Batch Extend (Epic 6.4)
    "CrossBatchExtendMatcher",
    "CrossBatchExtendConfig",
    "CrossBatchExtendStats",
    "ExtendMatch",
    # R3 SimHash + Dedup
    "SimHasher",
    "TwoStageDeduplicator",
    "DuplicateDecision",
    "DuplicateMatch",
    "EventStateProtocol",
    "Stage1SimHashFilter",
    "Stage2EmbeddingVerifier",
    "find_duplicates_async",
    # R3 Decay Engine (4.3.3)
    "UnifiedDecayEngine",
    "DecayClassification",
    "DecayConfig",
    "LAYER_LAMBDAS",
    # R3 Retention Enforcer (4.3.4)
    "RetentionEnforcer",
    "RetentionDecision",
    "RetentionResult",
    "ResurrectionTrigger",
    "ResurrectionResult",
    "BatchRetentionResult",
    # R3 Access Tracker (4.3.5)
    "AccessTracker",
    "AccessTrackerConfig",
    "AccessStats",
    "LambdaEstimate",
    "BayesianLambdaEstimator",
    # R3 Prune Regret Detector (4.3.6)
    "PruneRegretDetector",
    "PruneRegretConfig",
    "PrunedEntityTracker",
    "PrunedEntitiesCleanup",
    "PrunedEntity",
    "RegretMatch",
    "MatchType",
    "InMemoryPrunedEntityStore",
    # R3 Duplicate Detector (4.3.7)
    "DuplicateDetector",
    "DuplicateDetectorConfig",
    "DuplicationResult",
    "NoveltyBonuses",
    "InMemoryActivityHistory",
    # R3 Novelty Bonus Learner (4.3.8)
    "AdaptiveNoveltyBonusLearner",
    "NoveltyBonusConfig",
    "NoveltyBonusType",
    "NoveltyFeedbackSignal",
    "BonusAdjustment",
    "InMemoryLearnedWeightsStore",
    "BONUS_MIN",
    "BONUS_MAX",
    "DEFAULT_FIRST_OCCURRENCE_BONUS",
    "DEFAULT_MILESTONE_BONUS",
    "DEFAULT_RARE_PATTERN_BONUS",
    "DEFAULT_TEMPORAL_ANOMALY_BONUS",
    "clamp_bonus",
    "get_default_bonus",
    # R3 Immunity Checker (4.3.9)
    "ImmunityChecker",
    "ImmunityCheckerConfig",
    "ImmunityLevel",
    "ImmunityResult",
    "ImmunityOntologyEntry",
    "ImmunityMetricsCollector",
    "IMMUNITY_ONTOLOGY",
    "ENTITY_LEVEL_IMMUNE_TYPES",
    "ATTRIBUTE_LEVEL_IMMUNITY",
    "auto_mark_immunity",
    # R3 Prune Audit Logger (4.3.10)
    "PruneAuditLogger",
    "PruneAuditLoggerConfig",
    "PruneAuditRecord",
    "PruneDecisionContext",
    "PruneAction",
    "InMemoryAuditStore",
    "determine_prune_action",
    "build_prune_context",
    "parse_inputs_json",
    "parse_outputs_json",
    # R3 MinHash LSH (4.3.11)
    "MinHashLSH",
    "MinHashConfig",
    "LSHCandidate",
    "LSHIndexStats",
    "AdaptiveDeduplicationStrategy",
    "AdaptiveStrategyConfig",
    "DeduplicationStrategy",
    "MinHashMetricsCollector",
    "DEFAULT_NUM_HASHES",
    "DEFAULT_NUM_BANDS",
    "DEFAULT_SIMILARITY_THRESHOLD",
    "DEFAULT_MINHASH_LSH_ENABLED",
    "THRESHOLD_PAIRWISE",
    "THRESHOLD_BUCKETING",
    "estimate_lsh_threshold",
    "compute_jaccard_similarity",
    # R4 Entity Extraction (4.4.1)
    "UltraBERTEntityExtractor",
    "KGEntityType",
    "ExtractedEntity",
    "get_entity_extractor",
    # R4 Entity Disambiguation (4.4.2)
    "EntityDisambiguator",
    "DisambiguationWeights",
    "DisambiguationBreakdown",
    "P03_DISAMBIGUATION_THRESHOLD",
    "get_entity_disambiguator",
    # R4 Ambiguous Entity Resolution (4.4.4)
    "AmbiguousEntityResolver",
    "AmbiguousResolverConfig",
    "CandidateEntity",
    "EventContext",
    "ResolutionBreakdown",
    "ResolutionResult",
    "ResolutionOutcome",
    "P03_RESOLUTION_THRESHOLD_AUTO",
    "P03_RESOLUTION_THRESHOLD_FLAG",
    "get_ambiguous_resolver",
    # R4 Confidence Router (4.4.5)
    "ConfidenceRouter",
    "ConfidenceRouterConfig",
    "ConfidenceBand",
    "GapType",
    "GapPayload",
    "OutboxEntry",
    "RoutingResult",
    "P03_CONFIDENCE_THRESHOLD_AUTO",
    "P03_CONFIDENCE_THRESHOLD_FLAG",
    "get_confidence_router",
    "quick_band",
    # R4 Merge Threshold Learner (4.4.6)
    "AdaptiveMergeThresholds",
    "ThresholdBounds",
    "ThresholdAdjustment",
    "ThresholdMetrics",
    "MergeDecision",
    "get_adaptive_merge_thresholds",
    # R4 Entity Merger (4.4.7)
    "EntityMerger",
    "EntitySnapshot",
    "CascadeCounts",
    "MergeResult",
    "MergerMetrics",
    "MergeStatus",
    "get_entity_merger",
    # R3 Reconciliation Engine (4.3.13)
    "ReconciliationEngine",
    "ReconciliationConfig",
    "ReconciliationDecision",
    # Observation Context (Issue 7.2)
    "ObservationContext",
    # R5 MCTS Shadow Validation (Epic 4.5)
    "ShadowDecisionType",
    "PromotionRecommendation",
    "ShadowDecisionRecord",
    "ShadowValidationStats",
    "PromotionAnalysis",
    "ShadowOutcomeTracker",
    "CycleShadowTracker",
]
