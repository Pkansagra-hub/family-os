"""
R2 Phase - Episodic Integration (HDBSCAN Clustering).

M4 Epic 4.2: Implement R2 Phase for Episodic Clustering with Composite Distance.

This phase performs episodic clustering on events from R1:
1. Split events into sequences by time gaps / geohash / entity boundaries (Issue 4.2.2)
2. Cluster each sequence using EpisodicHDBSCAN with composite distance (Issues 4.2.1, 4.2.3)
3. Compute centroids for each cluster (Issue 4.2.4)
4. Track cluster quality metrics (Issue 4.2.7)
5. Adaptive eps/min_samples learning (Issues 4.2.5, 4.2.6)

References:
    - Dossier 4.3: R2 - Neocortical Integration (NREM2)
    - Dossier Appendix C.3: R2 Episodic Integration Algorithms
    - M4 Execution: docs/TEMP_EXECUTION_DOCS/M4_EXECUTION.md Epic 4.2
    - Phase Interface: k0/pipelines/p03/phase_interface.py

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import numpy as np
from sklearn.metrics import silhouette_score as sklearn_silhouette_score

from k0.modules.consolidation.algorithms import (
    CentroidCalculator,
    CentroidResult,
    ClusterQualityMetrics,
    ClusterQualityTracker,
    EnsembleDistanceConfig,
    EpisodeCandidate,
    EpisodeSplitter,
    EpisodicCoherenceScorer,
    EpisodicHDBSCAN,
    EpsAdjuster,
    EpsAdjustmentConfig,
    HDBSCANClusteringResult,
    HDBSCANParams,
    MinSamplesAdjuster,
    MinSamplesConfig,
    SecondaryCentroidSelector,
    SplitConfig,
    WeightingStrategy,
    compute_batch_coherence,
)
from k0.modules.consolidation.algorithms.cross_batch_extend import (
    CrossBatchExtendConfig,
    CrossBatchExtendMatcher,
)

# === M9.10: Scene segmentation imports ===
from k0.modules.consolidation.algorithms.fragment_absorber import (
    FragmentAbsorptionConfig,
    absorb_fragments,
)
from k0.modules.consolidation.algorithms.hebbian_boost import (
    HebbinaBoostConfig,
    build_cooccurrence_graph,
)
from k0.modules.consolidation.algorithms.same_thread_merge import (
    SameThreadMergeConfig,
    SameThreadMerger,
    SameThreadMergeStats,
)
from k0.modules.consolidation.algorithms.scene_segmenter import (
    SceneSegmentationConfig,
    segment_episodes,
)
from k0.modules.consolidation.algorithms.text_generators.episode_summarizer import (
    generate_episode_summary,
)
from k0.modules.consolidation.algorithms.thread_purity import (
    PurityCorrectionStats,
    ThreadPurityCorrector,
)

# === M9.8: Engine reconciliation imports ===
from k0.modules.consolidation.identity.episodic import EpisodicIdentity
from k0.modules.consolidation.reconciliation.adapters.r2_adapter import R2Adapter
from k0.modules.consolidation.reconciliation.engine import ReconciliationFramework
from k0.modules.consolidation.truth_layer_registry import TruthLayerRegistry
from k0.pipelines.p03.event_state import ReconciliationAction
from k0.pipelines.p03.observability import P03Error
from k0.pipelines.p03.phase_interface import P03PhaseResult
from k0.pipelines.p03.phase_outputs import EpisodeCluster
from k0.pipelines.p03.runner_contract import P03PhaseId

if TYPE_CHECKING:
    from k0.pipelines.p03.envelope import P03BatchEnvelope
    from k0.pipelines.p03.event_state import P03EventState
    from k0.pipelines.p03.phase_interface import P03RunnerContext

logger = logging.getLogger(__name__)


# =============================================================================
# HELPERS
# =============================================================================


def _vote_winner(items: List[str], default: str = "") -> str:
    """Return the most frequent non-empty value, or default."""
    counts: Dict[str, int] = {}
    for item in items:
        if item:
            counts[item] = counts.get(item, 0) + 1
    if not counts:
        return default
    return max(counts, key=lambda k: counts[k])


# =============================================================================
# R2 CONFIGURATION
# =============================================================================


@dataclass
class R2Config:
    """
    R2 phase configuration.

    Attributes:
        min_batch_size: Minimum events required for clustering (skip if less)
        eps: Clustering eps parameter (0.0 = use adaptive learning)
        min_samples: Clustering min_samples parameter (0 = use adaptive learning)
        semantic_weight: Weight for semantic (embedding) distance [0,1]
        temporal_weight: Weight for temporal distance [0,1]
        enable_splitting: Whether to split events before clustering
        time_gap_minutes: Time gap threshold for sequence splitting
        enable_adaptive_eps: Whether to use adaptive eps learning
        enable_adaptive_min_samples: Whether to use adaptive min_samples learning
        enable_quality_tracking: Whether to track cluster quality metrics
        weighting_strategy: Strategy for centroid weighting
        noise_rescue_threshold: Outlier score below which noise is rescued (HDBSCAN)
        cluster_selection_method: HDBSCAN cluster selection ('eom' or 'leaf')
    """

    min_batch_size: int = 2
    eps: float = 0.0  # 0.0 = use adaptive or default
    min_samples: int = 0  # 0 = use adaptive or default
    semantic_weight: float = 0.7
    temporal_weight: float = 0.3
    enable_splitting: bool = True
    time_gap_minutes: int = 360  # 6 hours: groups events within same half-day
    enable_adaptive_eps: bool = True
    enable_adaptive_min_samples: bool = True
    enable_quality_tracking: bool = True
    weighting_strategy: WeightingStrategy = WeightingStrategy.IMPORTANCE
    noise_rescue_threshold: float = 0.5  # Rescue noise with outlier_score < this
    rescue_all_noise: bool = True  # Force-assign ALL remaining noise to nearest cluster
    cluster_selection_method: str = "leaf"  # 'leaf' preserves small clusters

    # === Epic 6.1: Ensemble distance (3D: semantic 0.45, temporal 0.25, narrative 0.30) ===
    enable_ensemble_distance: bool = True
    ensemble_distance_config: Optional[EnsembleDistanceConfig] = None  # None = proven defaults

    # === Epic 6.2: Thread purity correction ===
    enable_thread_purity_correction: bool = True

    # === Epic 6.3: Same-thread merge (post-purity correction) ===
    enable_same_thread_merge: bool = True
    same_thread_merge_config: Optional[SameThreadMergeConfig] = None  # None = proven defaults

    # === Epic 6.4: Cross-batch episode extension ===
    enable_cross_batch_extend: bool = True
    cross_batch_extend_config: Optional[CrossBatchExtendConfig] = None  # None = proven defaults

    # === Epic 5.1: Hebbian co-occurrence distance boost ===
    enable_hebbian_boost: bool = True
    hebbian_boost_config: Optional[HebbinaBoostConfig] = None  # None = use defaults

    # === ISSUE 2 FIX: Episode Matching ===
    # Query st_epi for existing episodes before clustering to avoid duplicates
    enable_episode_matching: bool = True  # Enable matching to existing episodes
    episode_reinforce_threshold: float = 0.85  # Cosine similarity threshold for REINFORCE
    episode_extend_threshold: float = 0.60  # Threshold for EXTEND (future use)
    episode_query_limit: int = 50  # Max episodes to query per batch

    # === M9.8: Engine Reconciliation (Phase Migration) ===
    enable_engine_reinforce: bool = True  # Seam 1: use engine for pre-clustering REINFORCE
    enable_engine_extend: bool = True  # Seam 2: use engine for post-clustering EXTEND
    engine_dual_path_enabled: bool = False  # Run both legacy + engine, compare
    engine_dual_path_log_divergences: bool = True  # Log divergences in dual-path mode

    # === M9.10: Scene Segmentation (Mega-Episode Splitting) ===
    enable_scene_segmentation: bool = True  # Split mega-episodes into human-scale scenes
    scene_segmentation_config: Optional[SceneSegmentationConfig] = None  # None = POC defaults
    enable_fragment_absorption: bool = True  # Absorb micro-fragments into nearby scenes
    fragment_absorption_config: Optional[FragmentAbsorptionConfig] = None  # None = POC defaults


# =============================================================================
# EVENT ADAPTER (P03EventState -> EventLike)
# =============================================================================


@dataclass
class EventAdapter:
    """
    Adapter to make P03EventState compatible with R2 algorithm protocols.

    The R2 algorithms expect EventLike protocol:
        - event_id: str
        - timestamp: int (milliseconds)
        - embedding_768: Optional[List[float]]
        - geohash: Optional[str]
        - ner_entities: Optional[List[str]]
        - importance_score: Optional[float]

    Epic 1.1 additions (signal activation):
        - geohash_6: Optional[str]           (1.1.1 -- EpisodeSplitter Signal 1)
        - activity_type: Optional[str]       (1.1.2 -- EpisodeSplitter Signal 2)
        - activity_type_ultrabert: Optional[str] (1.1.2 -- 12-type INGRESS)
        - social_context: Optional[str]      (1.1.3 -- Epic 3.1 social distance)
        - social_intimacy: Optional[str]     (1.1.3 -- Epic 3.3 boundary scoring)
        - participants_json: Optional[str]   (1.1.3 -- Epic 3.1 Jaccard similarity)
        - narrative_thread_id: Optional[str] (1.1.4 -- Epic 3.1 narrative distance)
        - narrative_arc_position: Optional[str] (1.1.4 -- Epic 3.3 boundary scoring)
        - affect_valence: float              (1.1.5 -- Epic 3.1 affective distance)
        - affect_arousal: float              (1.1.5 -- Epic 3.1 affective distance)
        - affect_dominance: float            (1.1.5 -- MW v2 affective signal)
        - sentiment_score: float             (1.1.5 -- ClusterableEvent protocol)
        - salience_score: float              (1.1.5 -- Epic 4.1 centroid weighting)
        - temporal_orientation: Optional[str] (1.1.6 -- future temporal enhancements)
        - temporal_resolved_epoch_ms: float  (1.1.6 -- Epic 1.2 timestamp chain)
        - temporal_anchor_json: Optional[str] (1.1.6 -- MW v2 temporal context)

    Epic 3.6 additions (temporal context binding):
        - temporal_links_json: Optional[str]  (3.6.0 -- MW v2 temporal links)
        - time_of_day_bucket: Optional[str]   (3.6.0 -- circadian context)
        - circadian_slot: Optional[str]       (3.6.0 -- circadian phase)
        - is_weekend: Optional[bool]          (3.6.0 -- day type context)
        - extraction_sequence: int            (3.6.0 -- same-turn ordering)

    P03EventState has these fields directly, but we wrap for safety.
    """

    event: "P03EventState"

    @property
    def event_id(self) -> str:
        return self.event.event_id

    @property
    def timestamp(self) -> int:
        return self.event.timestamp

    @property
    def embedding_768(self) -> Optional[List[float]]:
        return self.event.embedding_768

    @property
    def geohash(self) -> Optional[str]:
        # Issue 1.1.1: Was hardcoded None. Now returns geohash_6 from P03EventState.
        return self.event.geohash_6 or None

    @property
    def geohash_6(self) -> Optional[str]:
        """Expose geohash_6 for EpisodeSplitter._detect_break Signal 1.

        EpisodeSplitter uses getattr(prev, "geohash_6", None) at episode_splitter.py L340.
        """
        return self.event.geohash_6 or None

    @property
    def ner_entities(self) -> Optional[List[str]]:
        # Parse from ner_entities_json if needed
        import json

        try:
            entities = json.loads(self.event.ner_entities_json or "[]")
            return [e.get("text", "") for e in entities if isinstance(e, dict)]
        except (json.JSONDecodeError, TypeError):
            return None

    @property
    def importance_score(self) -> Optional[float]:
        return self.event.importance_score if self.event.importance_computed else None

    # --- Issue 1.1.2: Activity signals (EpisodeSplitter Signal 2) ---

    @property
    def activity_type(self) -> Optional[str]:
        """Legacy 7-type activity classification.

        Used by EpisodeSplitter._detect_break Signal 2 (episode_splitter.py L354).
        Types: meal/conversation/routine/milestone/social/work/unknown
        """
        return self.event.activity_type or None

    @property
    def activity_type_ultrabert(self) -> Optional[str]:
        """UltraBERT 12-type INGRESS classification.

        Preferred over legacy activity_type for finer granularity.
        Types: DIARY/TASK/HEALTH/FINANCE/RELATIONSHIP/WORK/META/MEMORY/
               PLANNING/CELEBRATION/CONCERN/GRATITUDE
        """
        return self.event.activity_type_ultrabert or None

    # --- Issue 1.1.3: Social context signals (Epic 3.1 social distance) ---

    @property
    def social_context(self) -> Optional[str]:
        """Social context type (nuclear_family/solo/work/friends/extended_family).

        Used by Epic 3.1 social distance dimension and Epic 3.3 boundary scoring.
        """
        return self.event.social_context or None

    @property
    def social_intimacy(self) -> Optional[str]:
        """Social intimacy level (HIGH/LOW)."""
        return self.event.social_intimacy or None

    @property
    def participants_json(self) -> Optional[str]:
        """JSON array of participant IDs for Jaccard similarity (Epic 3.1)."""
        return self.event.participants_json if self.event.participants_json != "[]" else None

    # --- Issue 1.1.4: Narrative signals (Epic 3.1 narrative distance) ---

    @property
    def narrative_thread_id(self) -> Optional[str]:
        """MW v2 narrative thread ID.

        Used by Epic 3.1 narrative distance dimension.
        Used by Epic 3.3 boundary scoring (highest-weight signal).
        """
        return self.event.narrative_thread_id or None

    @property
    def narrative_arc_position(self) -> Optional[str]:
        """Position within narrative arc (BEGINNING/MIDDLE/END/CLIMAX)."""
        return self.event.narrative_arc_position or None

    # --- Epic 3.3: Additional signals for accumulated boundary scoring ---

    @property
    def place_id(self) -> Optional[str]:
        """Stable place identity from K1 PlaceResolver.

        Used by Epic 3.3 spatial channel (place_change_penalty)
        and Tier 1 hard_context_jump detection.
        """
        return self.event.place_id or None

    @property
    def goal_context(self) -> Optional[str]:
        """Goal/intent context for same_goal_bonus in Epic 3.3 boundary scoring."""
        return self.event.goal_context or None

    # --- Issue 1.1.5: Affective signals (Epic 3.1 affective distance) ---

    @property
    def affect_valence(self) -> float:
        """Emotional valence [-1, 1]. From P02 UltraBERT."""
        return self.event.affect_valence

    @property
    def affect_arousal(self) -> float:
        """Emotional arousal [0, 1]. From P02 UltraBERT."""
        return self.event.affect_arousal

    @property
    def affect_dominance(self) -> float:
        """Emotional dominance [0, 1]. From MW v2."""
        return self.event.affect_dominance

    @property
    def sentiment_score(self) -> float:
        """Sentiment score [-1, 1].

        Required by ClusterableEvent protocol (episodic_hdbscan.py L155).
        """
        return self.event.sentiment_score

    @property
    def salience_score(self) -> float:
        """P02 computed salience [0, 1]."""
        return self.event.salience_score

    # --- Issue 1.1.6: Temporal signals (Epic 1.2 timestamp chain) ---

    @property
    def temporal_orientation(self) -> Optional[str]:
        """Temporal orientation: PAST/PRESENT/FUTURE."""
        return self.event.temporal_orientation or None

    @property
    def temporal_resolved_epoch_ms(self) -> float:
        """MW v2 resolved epoch timestamp in ms.

        Preferred over event.timestamp for accuracy. Used by Epic 1.2 timestamp chain.
        """
        return self.event.temporal_resolved_epoch_ms

    @property
    def temporal_anchor_json(self) -> Optional[str]:
        """JSON temporal anchor context from MW v2."""
        return self.event.temporal_anchor_json if self.event.temporal_anchor_json != "{}" else None

    # --- Epic 3.2.2: Temporal quality provenance ---

    @property
    def temporal_source(self) -> Optional[str]:
        """Timestamp provenance for temporal confidence attenuation.

        Returns the source of the event's primary timestamp:
            mw_resolved, conversation_anchor_ms, event_time_utc,
            created_at, envelope_ts, now, or None if unknown.

        Used by _cd_temporal() to attenuate temporal dimension confidence
        when timestamps are low-quality.
        """
        return self.event.temporal_source or None

    # --- Epic 3.6.0: Remaining temporal support fields ---

    @property
    def temporal_links_json(self) -> Optional[str]:
        """JSON array of TemporalLink dicts from MW v2 multi-link model.

        Returns None when empty/default ("[]" or "").
        """
        v = self.event.temporal_links_json
        return v if v and v != "[]" else None

    @property
    def time_of_day_bucket(self) -> Optional[str]:
        """Coarse time-of-day: MORNING/AFTERNOON/EVENING/NIGHT."""
        return self.event.time_of_day_bucket or None

    @property
    def circadian_slot(self) -> Optional[str]:
        """Circadian phase: WAKE/ACTIVE/WIND_DOWN/SLEEP."""
        return self.event.circadian_slot or None

    @property
    def is_weekend(self) -> Optional[bool]:
        """True if event occurred on weekend, False for weekday, None if unknown."""
        return self.event.is_weekend

    @property
    def extraction_sequence(self) -> int:
        """Position within same-turn multi-event extraction (0 = default/only)."""
        return self.event.extraction_sequence


# =============================================================================
# R2 EPISODIC INTEGRATOR PHASE
# =============================================================================


class R2EpisodicIntegrator:
    """
    R2 Phase: Episodic Integration (HDBSCAN Clustering).

    Responsibilities:
        1. Check if batch size >= min_batch_size (skip otherwise)
        2. Split events into sequences (by time gap, location, entity)
        3. Cluster each sequence using EpisodicHDBSCAN
        4. Compute centroids for each cluster
        5. Update P03EventState with cluster assignments
        6. Populate envelope.phases.r2_* fields
        7. Track quality metrics and trigger adaptive learning

    Data Flow:
        R1 events (with importance) -> Split -> Cluster -> Centroids -> R3

    Idempotency:
        - Clustering is deterministic given same input order
        - Cluster IDs are generated from event content (reproducible)
        - Same batch produces same clusters on retry
    """

    PHASE_ID = P03PhaseId.R2_CLUSTER

    def __init__(self, config: Optional[R2Config] = None):
        """
        Initialize R2 phase.

        Args:
            config: Optional configuration (defaults used if not provided)
        """
        self.config = config or R2Config()

        # Initialize algorithm components
        self._splitter: Optional[EpisodeSplitter] = None
        self._clusterer: Optional[EpisodicHDBSCAN] = None
        self._centroid_calculator: Optional[CentroidCalculator] = None
        self._quality_tracker: Optional[ClusterQualityTracker] = None
        self._eps_adjuster: Optional[EpsAdjuster] = None
        self._min_samples_adjuster: Optional[MinSamplesAdjuster] = None

        # M9.8: Engine components (lazy-initialized on first engine-path call)
        self._engine_registry: Optional[TruthLayerRegistry] = None
        self._engine_identity: Optional[EpisodicIdentity] = None

    @property
    def phase_id(self) -> P03PhaseId:
        """Return the phase identifier."""
        return self.PHASE_ID

    def should_skip(self, envelope: "P03BatchEnvelope") -> bool:
        """
        Check if R2 should be skipped.

        Skip Conditions:
            - Fewer than min_batch_size events
            - All events missing embeddings

        Args:
            envelope: Current batch envelope

        Returns:
            True if phase should be skipped
        """
        if len(envelope.events) < self.config.min_batch_size:
            return True

        # Check if at least one event has embedding
        has_embedding = any(e.embedding_768 is not None for e in envelope.events)
        return not has_embedding

    def idempotency_key(self, envelope: "P03BatchEnvelope") -> str:
        """
        Compute idempotency key for retry safety.

        Args:
            envelope: Current batch envelope

        Returns:
            Deterministic key for this phase execution
        """
        return f"p03:r2:{envelope.context.cycle_id}"

    async def run(
        self,
        envelope: "P03BatchEnvelope",
        ctx: "P03RunnerContext",
    ) -> P03PhaseResult:
        """
        Execute R2 phase: Episodic Integration (Clustering).

        Steps:
            1. Check skip conditions (batch size, embeddings)
            2. Get clustering parameters (adaptive or configured)
            3. Split events into sequences
            4. Cluster each sequence with HDBSCAN
            5. Compute centroids for clusters
            6. Update event states with cluster assignments
            7. Populate envelope.phases.r2_* outputs
            8. Track quality metrics and trigger adaptive learning

        Args:
            envelope: Batch envelope with events from R1
            ctx: Runner context with syscalls, logger, config

        Returns:
            P03PhaseResult with status, duration, outputs summary
        """
        start_ms = int(time.time() * 1000)
        cycle_id = envelope.context.cycle_id
        space_id = envelope.context.space_id
        tenant_id = envelope.context.tenant_id

        logger.info(
            "R2: Starting episodic integration phase",
            extra={
                "cycle_id": cycle_id,
                "tenant_id": tenant_id,
                "space_id": space_id,
                "event_count": len(envelope.events),
            },
        )

        # Skip check
        if self.should_skip(envelope):
            duration_ms = int(time.time() * 1000) - start_ms
            skip_reason = self._get_skip_reason(envelope)
            logger.info(
                "R2: Skipping phase",
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
            # Initialize algorithm components
            self._initialize_components(ctx)

            # Get clustering parameters (from config or adaptive learning)
            distance_params = await self._get_distance_params(ctx, space_id)

            # B1 FIX: Apply learned params back to the clusterer
            self._clusterer.params = distance_params

            # Filter to events that have embeddings (required for clustering)
            events_with_embeddings = [e for e in envelope.events if e.embedding_768 is not None]
            events_without_embeddings = len(envelope.events) - len(events_with_embeddings)
            if events_without_embeddings > 0:
                logger.warning(
                    "R2: Excluding events without embeddings",
                    extra={
                        "context": {
                            "total_events": len(envelope.events),
                            "events_with_embeddings": len(events_with_embeddings),
                            "events_without_embeddings": events_without_embeddings,
                        }
                    },
                )

            if not events_with_embeddings:
                # No events with embeddings - skip clustering
                return envelope.with_skip(
                    phase_id=self.PHASE_ID,
                    reason="No events with embeddings for clustering",
                    duration_ms=0,
                    idempotency_key=self.idempotency_key(envelope),
                )

            # =================================================================
            # ISSUE 2 FIX: Match events to existing episodes BEFORE clustering
            # M9.8: Engine path via DualPathRunner when enabled
            # =================================================================
            matched_events: List["P03EventState"] = []
            novel_events = events_with_embeddings  # Default: all events are novel
            existing_episodes: List[Dict] = []

            if self.config.enable_episode_matching:
                # Query existing episodes from st_epi
                time_start = min(e.timestamp for e in events_with_embeddings)
                time_end = max(e.timestamp for e in events_with_embeddings)

                existing_episodes = await self._query_existing_episodes(
                    ctx=ctx,
                    space_id=space_id,
                    tenant_id=tenant_id,
                    time_start_ms=time_start,
                    time_end_ms=time_end,
                )

                if existing_episodes:
                    use_engine = self.config.enable_engine_reinforce
                    dual_path = self.config.engine_dual_path_enabled

                    if use_engine and not dual_path:
                        # Engine-only path
                        matched_events, novel_events = self._engine_match_events(
                            events=events_with_embeddings,
                            existing_episodes=existing_episodes,
                            cycle_id=cycle_id,
                            space_id=space_id,
                            tenant_id=tenant_id,
                        )
                    elif dual_path:
                        # Dual-path: run both, use legacy as authoritative
                        legacy_matched, legacy_novel = self._match_events_to_existing_episodes(
                            events=events_with_embeddings,
                            existing_episodes=existing_episodes,
                        )
                        engine_matched, _ = self._engine_match_events(
                            events=events_with_embeddings,
                            existing_episodes=existing_episodes,
                            cycle_id=cycle_id,
                            space_id=space_id,
                            tenant_id=tenant_id,
                        )
                        # Log divergences
                        legacy_ids = {e.event_id for e in legacy_matched}
                        engine_ids = {e.event_id for e in engine_matched}
                        if (
                            legacy_ids != engine_ids
                            and self.config.engine_dual_path_log_divergences
                        ):
                            logger.warning(
                                "R2: REINFORCE dual-path divergence",
                                extra={
                                    "cycle_id": cycle_id,
                                    "legacy_matched": len(legacy_ids),
                                    "engine_matched": len(engine_ids),
                                    "only_legacy": list(legacy_ids - engine_ids)[:5],
                                    "only_engine": list(engine_ids - legacy_ids)[:5],
                                },
                            )
                        # Legacy is authoritative in dual-path
                        matched_events, novel_events = legacy_matched, legacy_novel
                    else:
                        # Legacy-only path (default)
                        matched_events, novel_events = self._match_events_to_existing_episodes(
                            events=events_with_embeddings,
                            existing_episodes=existing_episodes,
                        )

            # Track matched events count for output
            matched_event_count = len(matched_events)

            # Only cluster novel events (those not matching existing episodes)
            # Adapt events to EventLike protocol
            adapted_events = [EventAdapter(e) for e in novel_events]

            # Sort by timestamp for EpisodeSplitter ordering invariant.
            # R0 selects by wal_pos which may not match temporal order,
            # especially when reset events mix with newer ingestion.
            adapted_events.sort(key=lambda e: e.timestamp)

            # =================================================================
            # Issue 1.2.4: Timestamp quality observability
            # =================================================================
            ts_quality, _degraded_ratio = self._compute_timestamp_quality(novel_events, cycle_id)

            # Step 1: Split events into sequences
            sequences = self._split_events(adapted_events)

            # Step 1b: Build co-occurrence graph from batch events (Epic 5.1)
            cooccurrence_graph = None
            if self.config.enable_hebbian_boost:
                cooccurrence_graph = build_cooccurrence_graph(adapted_events)
                if cooccurrence_graph:
                    logger.info(
                        "R2: Built co-occurrence graph",
                        extra={
                            "cycle_id": cycle_id,
                            "edge_count": len(cooccurrence_graph),
                        },
                    )

            # Step 2: Cluster each sequence
            all_results, all_noise_ids = self._cluster_sequences(sequences, cooccurrence_graph)

            # Step 2.5: Thread purity correction (Epic 6.2)
            if self.config.enable_thread_purity_correction:
                event_lookup_purity = {e.event_id: e for e in adapted_events}
                corrector = ThreadPurityCorrector()
                accumulated_purity = PurityCorrectionStats()
                for cr in all_results:
                    cr.clusters, cr_stats = corrector.correct(cr.clusters, event_lookup_purity)
                    cr.cluster_count = sum(1 for c in cr.clusters if len(c.member_event_ids) > 1)
                    accumulated_purity.clusters_before += cr_stats.clusters_before
                    accumulated_purity.clusters_after += cr_stats.clusters_after
                    accumulated_purity.clusters_split += cr_stats.clusters_split
                    accumulated_purity.clusters_pure += cr_stats.clusters_pure
                    accumulated_purity.events_reassigned += cr_stats.events_reassigned
                    accumulated_purity.noise_clusters_skipped += cr_stats.noise_clusters_skipped

                # Rescue events dropped by purity correction
                if accumulated_purity.noise_clusters_skipped > 0 and self.config.rescue_all_noise:
                    self._rescue_purity_orphans(all_results, event_lookup_purity)

                if accumulated_purity.clusters_split > 0:
                    logger.info(
                        "R2: Thread purity correction applied",
                        extra={
                            "cycle_id": cycle_id,
                            **accumulated_purity.to_dict(),
                        },
                    )

            # Step 2.6: Same-thread merge (Epic 6.3)
            if self.config.enable_same_thread_merge:
                if not self.config.enable_thread_purity_correction:
                    event_lookup_purity = {e.event_id: e for e in adapted_events}
                merger = SameThreadMerger(
                    config=self.config.same_thread_merge_config or SameThreadMergeConfig(),
                )
                merge_stats = SameThreadMergeStats()
                for cr in all_results:
                    cr.clusters, merge_stats = merger.merge(cr.clusters, event_lookup_purity)
                    cr.cluster_count = sum(1 for c in cr.clusters if len(c.member_event_ids) > 1)
                if merge_stats.clusters_merged > 0:
                    logger.info(
                        "R2: Same-thread merge applied",
                        extra={
                            "cycle_id": cycle_id,
                            **merge_stats.to_dict(),
                        },
                    )

            # Step 3: Compute centroids and build episode candidates
            episode_candidates, episode_clusters = self._build_episodes_from_clusters(
                all_results, adapted_events, envelope.context.space_id
            )

            # Step 3.5: Cross-batch extend matching (Epic 6.4)
            # M9.8: Engine path via feature flag when enabled
            if self.config.enable_cross_batch_extend and existing_episodes and episode_candidates:
                if (
                    not self.config.enable_thread_purity_correction
                    and not self.config.enable_same_thread_merge
                ):
                    event_lookup_purity = {e.event_id: e for e in adapted_events}

                use_engine_ext = self.config.enable_engine_extend
                dual_path_ext = self.config.engine_dual_path_enabled

                if use_engine_ext and not dual_path_ext:
                    # Engine-only EXTEND path
                    # Build event lookup from P03EventState for metadata extraction
                    p03_event_lookup = {e.event_id: e for e in novel_events}
                    self._engine_extend_episodes(
                        episode_candidates=episode_candidates,
                        existing_episodes=existing_episodes,
                        event_lookup=p03_event_lookup,
                        cycle_id=cycle_id,
                        space_id=space_id,
                        tenant_id=tenant_id,
                    )
                elif dual_path_ext:
                    # Dual-path: run both, legacy is authoritative
                    extend_matcher = CrossBatchExtendMatcher(
                        config=self.config.cross_batch_extend_config or CrossBatchExtendConfig(),
                    )
                    extend_matches, extend_stats = extend_matcher.match(
                        episode_candidates,
                        existing_episodes,
                        event_lookup_purity,
                    )
                    # Apply legacy results
                    legacy_extended = set()
                    for cand, ext_match in zip(episode_candidates, extend_matches):
                        if ext_match is not None:
                            cand.reconciliation_action = "EXTEND"
                            cand.extend_target_episode_id = ext_match.target_episode_id
                            cand.extend_similarity = ext_match.similarity
                            legacy_extended.add(cand.cluster_id)

                    # Run engine for comparison logging only
                    p03_event_lookup = {e.event_id: e for e in novel_events}
                    # Use copies to avoid clobbering legacy annotations
                    engine_ext_count = self._engine_extend_episodes(
                        episode_candidates=episode_candidates,
                        existing_episodes=existing_episodes,
                        event_lookup=p03_event_lookup,
                        cycle_id=cycle_id,
                        space_id=space_id,
                        tenant_id=tenant_id,
                    )
                    if self.config.engine_dual_path_log_divergences:
                        logger.info(
                            "R2: EXTEND dual-path comparison",
                            extra={
                                "cycle_id": cycle_id,
                                "legacy_extended": len(legacy_extended),
                                "engine_extended": engine_ext_count,
                            },
                        )
                    if extend_stats.candidates_extended > 0:
                        logger.info(
                            "R2: Cross-batch extend matching applied",
                            extra={
                                "cycle_id": cycle_id,
                                **extend_stats.to_dict(),
                            },
                        )
                else:
                    # Legacy-only EXTEND path (default)
                    extend_matcher = CrossBatchExtendMatcher(
                        config=self.config.cross_batch_extend_config or CrossBatchExtendConfig(),
                    )
                    extend_matches, extend_stats = extend_matcher.match(
                        episode_candidates,
                        existing_episodes,
                        event_lookup_purity,
                    )
                    for cand, ext_match in zip(episode_candidates, extend_matches):
                        if ext_match is not None:
                            cand.reconciliation_action = "EXTEND"
                            cand.extend_target_episode_id = ext_match.target_episode_id
                            cand.extend_similarity = ext_match.similarity
                    if extend_stats.candidates_extended > 0:
                        logger.info(
                            "R2: Cross-batch extend matching applied",
                            extra={
                                "cycle_id": cycle_id,
                                **extend_stats.to_dict(),
                            },
                        )

            # Step 3b: Scene segmentation (M9.10)
            # Splits mega-episodes (> max_scene_events) into human-scale scenes.
            # Fragment absorption merges micro-fragments (<= absorb_max_events)
            # into nearby compatible scenes.
            scene_seg_stats = None
            frag_abs_stats = None
            if self.config.enable_scene_segmentation and episode_candidates:
                seg_config = self.config.scene_segmentation_config or SceneSegmentationConfig()
                episode_candidates, episode_clusters, scene_seg_stats = segment_episodes(
                    episode_candidates,
                    episode_clusters,
                    event_lookup_purity,
                    seg_config,
                )
                logger.info(
                    "R2: Scene segmentation applied",
                    extra={
                        "cycle_id": cycle_id,
                        **scene_seg_stats.to_dict(),
                    },
                )

                # Fragment absorption runs only after scene segmentation
                if self.config.enable_fragment_absorption:
                    abs_config = (
                        self.config.fragment_absorption_config or FragmentAbsorptionConfig()
                    )
                    episode_candidates, episode_clusters, frag_abs_stats = absorb_fragments(
                        episode_candidates,
                        episode_clusters,
                        event_lookup_purity,
                        abs_config,
                    )
                    if frag_abs_stats.fragments_absorbed > 0:
                        logger.info(
                            "R2: Fragment absorption applied",
                            extra={
                                "cycle_id": cycle_id,
                                **frag_abs_stats.to_dict(),
                            },
                        )

            # Step 4: Update event states with cluster assignments
            # Use episode_candidates (post-merge/split/absorb) as authoritative source.
            # all_results contains pre-merge HDBSCAN IDs that become phantoms in st_epi.
            self._update_event_states_from_candidates(
                envelope.events, episode_candidates, all_noise_ids
            )

            # Step 5: Populate envelope outputs
            envelope.phases.r2_clusters = episode_clusters
            envelope.phases.r2_noise_event_ids = all_noise_ids
            envelope.phases.r2_cluster_count = len(episode_clusters)
            envelope.phases.r2_avg_cluster_size = (
                sum(len(c.member_event_ids) for c in episode_clusters) / len(episode_clusters)
                if episode_clusters
                else 0.0
            )
            envelope.phases.r2_clustering_params = {
                "eps": distance_params.cluster_selection_epsilon,
                "min_samples": distance_params.min_samples,
                "semantic_weight": self.config.semantic_weight,
                "temporal_weight": self.config.temporal_weight,
                "episode_matching_enabled": self.config.enable_episode_matching,
                "matched_to_existing": matched_event_count,  # Issue 2 fix
            }
            if scene_seg_stats is not None:
                envelope.phases.r2_clustering_params["scene_segmentation"] = (
                    scene_seg_stats.to_dict()
                )
            if frag_abs_stats is not None:
                envelope.phases.r2_clustering_params["fragment_absorption"] = (
                    frag_abs_stats.to_dict()
                )

            # Step 6: Track quality metrics and adaptive learning
            quality_metrics = None
            if self.config.enable_quality_tracking and episode_candidates:
                quality_metrics = await self._track_quality_and_adapt(
                    ctx,
                    space_id,
                    episode_candidates,
                    all_noise_ids,
                    distance_params,
                    all_results,
                    episode_clusters=episode_clusters,
                )

            duration_ms = int(time.time() * 1000) - start_ms

            logger.info(
                "R2: Episodic integration complete",
                extra={
                    "cycle_id": cycle_id,
                    "clusters_formed": len(episode_clusters),
                    "matched_to_existing": matched_event_count,  # Issue 2 fix
                    "noise_events": len(all_noise_ids),
                    "avg_cluster_size": envelope.phases.r2_avg_cluster_size,
                    "eps": distance_params.cluster_selection_epsilon,
                    "min_samples": distance_params.min_samples,
                    "silhouette": quality_metrics.silhouette_score if quality_metrics else None,
                    "duration_ms": duration_ms,
                    "scenes_split": scene_seg_stats.episodes_split if scene_seg_stats else 0,
                    "fragments_absorbed": (
                        frag_abs_stats.fragments_absorbed if frag_abs_stats else 0
                    ),
                },
            )

            return P03PhaseResult.done(
                phase_id=self.PHASE_ID,
                duration_ms=duration_ms,
                outputs_summary={
                    "clusters_formed": len(episode_clusters),
                    "matched_to_existing": matched_event_count,  # Issue 2 fix
                    "noise_events": len(all_noise_ids),
                    "avg_cluster_size": round(envelope.phases.r2_avg_cluster_size, 2),
                    "eps": distance_params.cluster_selection_epsilon,
                    "min_samples": distance_params.min_samples,
                    "silhouette": (
                        round(quality_metrics.silhouette_score, 3) if quality_metrics else None
                    ),
                    # Issue 1.2.4: Timestamp quality in phase result
                    "ts_quality": ts_quality,
                    "ts_degraded_ratio": round(_degraded_ratio, 3),
                },
                idempotency_key=self.idempotency_key(envelope),
            )

        except Exception as e:
            duration_ms = int(time.time() * 1000) - start_ms
            logger.exception(
                "R2: Episodic integration failed",
                extra={
                    "cycle_id": cycle_id,
                    "error": str(e),
                    "duration_ms": duration_ms,
                },
            )

            error = P03Error.create(
                phase="R2",
                stage_id="episodic_integrator",
                error_type="R2_CLUSTERING_ERROR",
                error_message=str(e),
                recoverable=True,  # R2 failures are retriable
            )

            return P03PhaseResult.fail(
                phase_id=self.PHASE_ID,
                error=error,
                duration_ms=duration_ms,
            )

    # =========================================================================
    # PRIVATE METHODS
    # =========================================================================

    def _get_skip_reason(self, envelope: "P03BatchEnvelope") -> str:
        """Get human-readable skip reason."""
        if len(envelope.events) < self.config.min_batch_size:
            return (
                f"Batch size {len(envelope.events)} < min_batch_size {self.config.min_batch_size}"
            )
        if not any(e.embedding_768 is not None for e in envelope.events):
            return "No events with embeddings"
        return "Unknown skip condition"

    def _initialize_components(self, ctx: "P03RunnerContext") -> None:
        """Initialize algorithm components."""
        # Splitter - accumulated boundary scoring (Epic 3.3)
        split_config = SplitConfig(
            hard_time_gap_minutes=self.config.time_gap_minutes,
        )
        self._splitter = EpisodeSplitter(config=split_config)

        # Choose clustering algorithm based on config
        # HDBSCAN with noise rescue capability
        hdbscan_params = HDBSCANParams(
            min_cluster_size=2,  # Smallest episode size
            min_samples=1,  # Allow more inclusive clustering
            cluster_selection_epsilon=self.config.eps if self.config.eps > 0 else 0.0,
            noise_rescue_threshold=self.config.noise_rescue_threshold,
            rescue_all_noise=self.config.rescue_all_noise,
            temporal_weight=self.config.temporal_weight,
            cluster_selection_method=self.config.cluster_selection_method,
        )
        # Resolve ensemble distance config (Epic 6.1)
        ensemble_config = None
        if self.config.enable_ensemble_distance:
            ensemble_config = self.config.ensemble_distance_config or EnsembleDistanceConfig()

        # Resolve Hebbian boost config
        hebbian_config = None
        if self.config.enable_hebbian_boost:
            hebbian_config = self.config.hebbian_boost_config or HebbinaBoostConfig()

        self._clusterer = EpisodicHDBSCAN(
            params=hdbscan_params,
            ensemble_config=ensemble_config,
            hebbian_config=hebbian_config,
        )
        logger.info(
            "R2 using HDBSCAN with noise_rescue=%.2f, selection=%s, ensemble=%s, hebbian=%s",
            self.config.noise_rescue_threshold,
            self.config.cluster_selection_method,
            self.config.enable_ensemble_distance,
            self.config.enable_hebbian_boost,
        )

        # Centroid calculator
        self._centroid_calculator = CentroidCalculator()

        # Quality tracker
        if self.config.enable_quality_tracking:
            self._quality_tracker = ClusterQualityTracker()

        # Adaptive adjusters
        if self.config.enable_adaptive_eps:
            self._eps_adjuster = EpsAdjuster(config=EpsAdjustmentConfig())

        if self.config.enable_adaptive_min_samples:
            self._min_samples_adjuster = MinSamplesAdjuster(config=MinSamplesConfig())

    async def _get_distance_params(self, ctx: "P03RunnerContext", space_id: str) -> HDBSCANParams:
        """
        Get clustering distance parameters from config or adaptive learning.

        Args:
            ctx: Runner context with syscalls
            space_id: Space ID for per-space params

        Returns:
            HDBSCANParams with learned or default values
        """
        # Start with config values or defaults (0.07 eps for tight UltraBERT clustering)
        eps = self.config.eps if self.config.eps > 0 else 0.07
        min_samples = self.config.min_samples if self.config.min_samples > 0 else 2

        # Try to get learned params from syscalls (st_learned_weights)
        try:
            if hasattr(ctx.syscalls, "get_learned_param"):
                # Try new key first, fall back to legacy key for backward compatibility
                learned_eps = await ctx.syscalls.get_learned_param(
                    space_id=space_id, param_key="clustering_eps"
                )
                if learned_eps is None:
                    learned_eps = await ctx.syscalls.get_learned_param(
                        space_id=space_id, param_key="dbscan_eps"
                    )
                if learned_eps is not None:
                    eps = learned_eps

                learned_min_samples = await ctx.syscalls.get_learned_param(
                    space_id=space_id, param_key="clustering_min_samples"
                )
                if learned_min_samples is None:
                    learned_min_samples = await ctx.syscalls.get_learned_param(
                        space_id=space_id, param_key="dbscan_min_samples"
                    )
                if learned_min_samples is not None:
                    min_samples = int(learned_min_samples)
        except Exception as e:
            logger.warning(
                "R2: Failed to get learned params, using defaults",
                extra={"error": str(e)},
            )

        return HDBSCANParams(
            min_cluster_size=2,
            min_samples=min_samples,
            cluster_selection_epsilon=eps,
            noise_rescue_threshold=self.config.noise_rescue_threshold,
            rescue_all_noise=self.config.rescue_all_noise,
            temporal_weight=self.config.temporal_weight,
            cluster_selection_method=self.config.cluster_selection_method,
        )

    def _split_events(self, events: List[EventAdapter]) -> List[List[EventAdapter]]:
        """
        Split events into sequences using EpisodeSplitter.

        Args:
            events: Adapted events to split

        Returns:
            List of event sequences
        """
        if not self.config.enable_splitting or self._splitter is None:
            return [events]  # No splitting - single sequence

        split_result = self._splitter.split(events)
        return split_result.episodes

    def _compute_timestamp_quality(
        self,
        events: List["P03EventState"],
        cycle_id: str,
    ) -> Tuple[Dict[str, int], float]:
        """Compute timestamp quality stats and degraded ratio."""
        ts_quality: Dict[str, int] = {
            "mw_resolved": 0,
            "ner_temporal": 0,
            "event_time": 0,
            "envelope_ts": 0,
            "now": 0,
            "unknown": 0,
        }
        for evt in events:
            src = getattr(evt, "temporal_source", "") or "unknown"
            ts_quality[src] = ts_quality.get(src, 0) + 1

        total = len(events) or 1
        degraded = (
            ts_quality["event_time"]
            + ts_quality["envelope_ts"]
            + ts_quality["now"]
            + ts_quality["unknown"]
        )
        degraded_ratio = degraded / total

        logger.info(
            "R2: Timestamp quality stats",
            extra={
                "cycle_id": cycle_id,
                "ts_quality": ts_quality,
                "degraded_ratio": round(degraded_ratio, 3),
                "total_events": len(events),
            },
        )
        if degraded_ratio > 0.5:
            logger.warning(
                "R2: >50%% events have degraded timestamps "
                "-- episode boundaries may be unreliable",
                extra={
                    "cycle_id": cycle_id,
                    "degraded_ratio": round(degraded_ratio, 3),
                },
            )
        return ts_quality, degraded_ratio

    def _cluster_sequences(
        self,
        sequences: List[List["EventAdapter"]],
        cooccurrence_graph: Optional[Dict] = None,
    ) -> Tuple[List["HDBSCANClusteringResult"], List[str]]:
        """Cluster each event sequence via HDBSCAN, returning results and noise IDs."""
        all_results: List[HDBSCANClusteringResult] = []
        all_noise_ids: List[str] = []
        sub_batch_events: List["EventAdapter"] = []

        for sequence in sequences:
            if len(sequence) < self.config.min_batch_size:
                # Collect sub-batch events for cross-sequence rescue later
                sub_batch_events.extend(sequence)
                continue

            clustering_result = self._clusterer.cluster(
                sequence, cooccurrence_graph=cooccurrence_graph
            )
            all_results.append(clustering_result)

            for idx, label in enumerate(clustering_result.labels):
                if label == -1:
                    all_noise_ids.append(sequence[idx].event_id)

        # Cross-sequence rescue: assign sub-batch events to nearest cluster
        if sub_batch_events and self.config.rescue_all_noise and all_results:
            rescued_ids = self._rescue_sub_batch_events(sub_batch_events, all_results)
            # Only noise those that couldn't be rescued
            for evt in sub_batch_events:
                if evt.event_id not in rescued_ids:
                    all_noise_ids.append(evt.event_id)
        elif sub_batch_events:
            # No clusters to assign to — mark as noise
            all_noise_ids.extend(e.event_id for e in sub_batch_events)

        return all_results, all_noise_ids

    def _rescue_sub_batch_events(
        self,
        orphan_events: List["EventAdapter"],
        clustering_results: List["HDBSCANClusteringResult"],
    ) -> set:
        """Assign sub-batch orphan events to the nearest existing cluster.

        Prefers same-thread clusters by temporal proximity, falling back
        to any cluster when no same-thread match exists.  This reduces
        cross-thread impurity that purity correction would later discard.

        Returns:
            Set of event IDs that were successfully rescued.
        """
        rescued: set = set()
        # Build candidate list with thread hint from orphan events
        candidates: list = []
        for result in clustering_results:
            for cluster in result.clusters:
                if (
                    cluster.member_event_ids
                    and len(cluster.member_event_ids) >= 2
                    and cluster.temporal_start > 0
                    and not cluster.cluster_id.startswith("noise-")
                ):
                    candidates.append(cluster)

        if not candidates:
            return rescued

        # Build thread lookup from all available events
        # (orphan_events won't overlap with cluster members, but we have
        #  no lookup for cluster members here; thread matching happens
        #  in _rescue_purity_orphans as a safety net)
        for evt in orphan_events:
            ts = evt.timestamp
            evt_thread = getattr(evt, "narrative_thread_id", None)

            best_cluster = None
            best_dist = float("inf")
            best_same_thread = None
            best_same_dist = float("inf")

            for cluster in candidates:
                mid = (cluster.temporal_start + cluster.temporal_end) / 2
                dist = abs(ts - mid)
                if dist < best_dist:
                    best_dist = dist
                    best_cluster = cluster
                # Check if cluster_id hints at thread (after purity split)
                if evt_thread and evt_thread in cluster.cluster_id and dist < best_same_dist:
                    best_same_dist = dist
                    best_same_thread = cluster

            target = best_same_thread if best_same_thread is not None else best_cluster
            if target is not None:
                target.member_event_ids.append(evt.event_id)
                rescued.add(evt.event_id)

        if rescued:
            logger.info(
                "R2: Sub-batch rescue assigned %d/%d orphan events to nearest clusters",
                len(rescued),
                len(orphan_events),
            )

        return rescued

    def _rescue_purity_orphans(
        self,
        all_results: List["HDBSCANClusteringResult"],
        event_lookup: Dict[str, "EventAdapter"],
    ) -> int:
        """Rescue events dropped by thread purity correction.

        After purity correction splits impure clusters, sub-groups smaller
        than min_split_size are discarded.  Their events lose cluster
        membership.  This sweep finds those orphans and assigns each one
        to the nearest cluster that shares the same narrative thread,
        falling back to temporal proximity when no same-thread cluster
        exists.

        Returns:
            Number of events rescued.
        """
        from k0.modules.consolidation.algorithms.thread_purity import _get_thread_group

        # Collect all event_ids currently in clusters
        clustered_ids: set = set()
        for result in all_results:
            for cluster in result.clusters:
                clustered_ids.update(cluster.member_event_ids)

        # Orphans = events in lookup but not in any cluster
        orphan_ids = set(event_lookup.keys()) - clustered_ids
        if not orphan_ids:
            return 0

        # Build candidate clusters (≥2 members, have temporal bounds)
        candidate_clusters = []
        for result in all_results:
            for cluster in result.clusters:
                if len(cluster.member_event_ids) >= 2 and cluster.temporal_start > 0:
                    # Determine dominant thread of this cluster
                    thread_counts: Dict[str, int] = {}
                    for eid in cluster.member_event_ids:
                        ev = event_lookup.get(eid)
                        if ev:
                            tg = _get_thread_group(ev)
                            thread_counts[tg] = thread_counts.get(tg, 0) + 1
                    dominant = (
                        max(thread_counts, key=lambda t: thread_counts[t])
                        if thread_counts
                        else "__no_thread__"
                    )
                    candidate_clusters.append((cluster, dominant))

        if not candidate_clusters:
            return 0

        rescued = 0
        for oid in orphan_ids:
            evt = event_lookup.get(oid)
            if evt is None:
                continue
            evt_thread = _get_thread_group(evt)
            ts = evt.timestamp

            # Prefer same-thread cluster, fall back to any cluster
            best_cluster = None
            best_dist = float("inf")
            best_same_thread = None
            best_same_dist = float("inf")

            for cluster, dominant_thread in candidate_clusters:
                mid = (cluster.temporal_start + cluster.temporal_end) / 2
                dist = abs(ts - mid)
                if dist < best_dist:
                    best_dist = dist
                    best_cluster = cluster
                if dominant_thread == evt_thread and dist < best_same_dist:
                    best_same_dist = dist
                    best_same_thread = cluster

            target = best_same_thread if best_same_thread is not None else best_cluster
            if target is not None:
                target.member_event_ids.append(oid)
                rescued += 1

        if rescued:
            logger.info(
                "R2: Post-purity rescue assigned %d/%d orphan events",
                rescued,
                len(orphan_ids),
            )

        return rescued

    def _build_episodes_from_clusters(
        self,
        all_results: List["HDBSCANClusteringResult"],
        adapted_events: List["EventAdapter"],
        space_id: str,
    ) -> Tuple[List["EpisodeCandidate"], List["EpisodeCluster"]]:
        """Build episode candidates and clusters from HDBSCAN results."""
        episode_candidates: List[EpisodeCandidate] = []
        episode_clusters: List[EpisodeCluster] = []
        event_lookup = {e.event_id: e for e in adapted_events}

        for clustering_result in all_results:
            for cluster in clustering_result.clusters:
                member_ids = cluster.member_event_ids
                if not member_ids or len(member_ids) == 1:
                    continue

                cluster_events = [event_lookup[eid] for eid in member_ids if eid in event_lookup]
                if not cluster_events:
                    continue

                centroid_result = self._centroid_calculator.compute(
                    cluster_events, strategy=self.config.weighting_strategy
                )

                cohesion = 1.0 / (1.0 + centroid_result.variance)
                candidate = EpisodeCandidate(
                    cluster_id=cluster.cluster_id,
                    space_id=space_id,
                    event_ids=member_ids,
                    event_count=len(member_ids),
                    centroid_embedding=centroid_result.centroid,
                    temporal_start=min(e.timestamp for e in cluster_events),
                    temporal_end=max(e.timestamp for e in cluster_events),
                    cohesion_score=cohesion,
                    variance=centroid_result.variance,
                )
                episode_candidates.append(candidate)

                episode_cluster = self._build_episode_cluster(
                    cluster.cluster_id, member_ids, cluster_events, centroid_result
                )
                episode_clusters.append(episode_cluster)

        return episode_candidates, episode_clusters

    def _compute_confidence(
        self,
        event_count: int,
        temporal_start: int,
        temporal_end: int,
        participant_count: int,
        cohesion: float,
        location_purity: float,
    ) -> float:
        """
        Compute episode confidence score.

        Based on:
        - Event count (more = higher, with saturation)
        - Temporal compactness (tighter = higher)
        - Participant stability (having participants = higher)
        - Cohesion (semantic similarity)
        - Location purity (consistent location)

        Returns:
            Confidence score in [0.0, 1.0]
        """
        # Event count score (saturates at 10 events)
        event_score = min(1.0, event_count / 10.0)

        # Temporal compactness (score higher for shorter duration)
        duration_ms = temporal_end - temporal_start if temporal_end > temporal_start else 0
        duration_hours = duration_ms / 3600000.0
        # 1 hour = 1.0, 4 hours = 0.5, 8+ hours = 0.25
        if duration_hours <= 1:
            temporal_score = 1.0
        elif duration_hours <= 4:
            temporal_score = 1.0 - (duration_hours - 1) * 0.167  # 0.5 at 4h
        else:
            temporal_score = max(0.25, 0.5 - (duration_hours - 4) * 0.03)

        # Participant score (having participants is better)
        participant_score = min(1.0, 0.5 + participant_count * 0.1)

        # Cohesion already in [0, 1]
        cohesion_score = min(1.0, cohesion)

        # Combine with weights
        confidence = (
            0.25 * event_score
            + 0.20 * temporal_score
            + 0.15 * participant_score
            + 0.25 * cohesion_score
            + 0.15 * location_purity
        )

        return round(min(1.0, max(0.0, confidence)), 3)

    def _build_episode_cluster(
        self,
        cluster_id: str,
        member_ids: List[str],
        cluster_events: List[EventAdapter],
        centroid_result: CentroidResult,
    ) -> EpisodeCluster:
        """
        Build EpisodeCluster for envelope outputs.

        Args:
            cluster_id: Cluster ID
            member_ids: Member event IDs
            cluster_events: Events in the cluster
            centroid_result: Centroid computation result

        Returns:
            EpisodeCluster dataclass
        """
        import json

        # Calculate temporal bounds
        timestamps = [e.timestamp for e in cluster_events]
        temporal_start = min(timestamps) if timestamps else 0
        temporal_end = max(timestamps) if timestamps else 0

        # Calculate dominant sentiment (average)
        sentiments = [e.event.sentiment_score for e in cluster_events]
        dominant_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0

        # Derive label from score (same thresholds as HDBSCAN + st_hipp_events)
        if dominant_sentiment > 0.6:
            dominant_sentiment_label = "positive"
        elif dominant_sentiment < 0.4:
            dominant_sentiment_label = "negative"
        else:
            dominant_sentiment_label = "neutral"

        # Extract dominant emotion from most common across events
        emotion_labels: List[str] = []
        for e in cluster_events:
            try:
                emotions = json.loads(e.event.emotions_json or "[]")
                for emotion in emotions:
                    if isinstance(emotion, str):
                        emotion_labels.append(emotion)
                    elif isinstance(emotion, dict):
                        label = emotion.get("label", emotion.get("emotion", ""))
                        if label:
                            emotion_labels.append(label)
            except (json.JSONDecodeError, TypeError):
                pass
        dominant_emotion = _vote_winner(emotion_labels)

        # Extract most common location
        location_hint = _vote_winner([e.event.location_name for e in cluster_events]) or None

        # GAP-002: Extract most common location type
        location_type = _vote_winner([e.event.location_type for e in cluster_events]) or None

        # Aggregate participants across all events
        all_participants: set = set()
        for e in cluster_events:
            try:
                participants = json.loads(e.event.participants_json or "[]")
                for p in participants:
                    if isinstance(p, str):
                        all_participants.add(p)
                    elif isinstance(p, dict):
                        name = p.get("name", p.get("id", ""))
                        if name:
                            all_participants.add(name)
            except (json.JSONDecodeError, TypeError):
                pass
        participants_json = json.dumps(sorted(all_participants))

        # Extract entity IDs from NER data across all member events
        entity_ids: set = set()
        for e in cluster_events:
            try:
                ner_json = getattr(e.event, "ner_entities_json", "{}") or "{}"
                ner_data = json.loads(ner_json) if ner_json else {}
                if isinstance(ner_data, dict):
                    for source in ["ner_family", "ner_general"]:
                        if source in ner_data and isinstance(ner_data[source], dict):
                            entities = ner_data[source].get("entities", [])
                            for ent in entities:
                                if isinstance(ent, dict):
                                    ent_id = ent.get("id")
                                    if ent_id:
                                        entity_ids.add(ent_id)
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass

        # Extract most common activity type
        activity_type = _vote_winner([e.event.activity_type for e in cluster_events])

        # Extract most common UltraBERT activity type (Issue 0060)
        activity_type_ultrabert = _vote_winner(
            [e.event.activity_type_ultrabert for e in cluster_events]
        )

        # Generate a basic title from location + activity or first event text
        title = self._generate_episode_title(cluster_events, location_hint, activity_type)

        # Generate summary from event texts
        summary = self._generate_episode_summary(cluster_events)

        # Issue 7.6: Build ObservationContext for each member event
        from k0.modules.consolidation.algorithms.observation_context import ObservationContext

        member_contexts = []
        for e in cluster_events:
            ctx = ObservationContext.from_event(e.event)
            member_contexts.append(ctx)

        (
            aggregated_sentiment,
            aggregated_salience,
            dominant_location,
            dominant_social_context,
        ) = self._aggregate_context_fields(member_contexts)

        # M0-E2-I5: Compute ambiguity_score based on missing critical fields
        # Higher score = more ambiguous (more missing information)
        ambiguity_score = self._compute_ambiguity_score(
            location_hint=location_hint,
            participants_json=participants_json,
            activity_type=activity_type,
            activity_type_ultrabert=activity_type_ultrabert,
            entity_ids=entity_ids,
            cluster_events=cluster_events,
        )

        # M4-RSCH-02: Select secondary centroids (best_of_all MRR=0.9627)
        centroid_metadata = None
        if len(cluster_events) >= 2:
            selector = SecondaryCentroidSelector()
            secondary = selector.select_all(cluster_events)
            if secondary:
                centroid_metadata = {
                    "version": 1,
                    "centroids": {
                        role: {"event_id": data["event_id"]} for role, data in secondary.items()
                    },
                }

        return EpisodeCluster(
            cluster_id=cluster_id,
            member_event_ids=list(member_ids),
            member_contexts=member_contexts,  # Issue 7.6
            entity_ids=list(entity_ids),  # M0-E2-I3: Extracted from NER data
            ambiguity_score=ambiguity_score,  # M0-E2-I5: Uncertainty quantification
            centroid_embedding_id=None,  # Will be set by R6/R7 when persisted
            centroid_metadata=centroid_metadata,  # M4-RSCH-02: secondary centroids
            dominant_sentiment=dominant_sentiment,
            dominant_sentiment_label=dominant_sentiment_label,
            dominant_emotion=dominant_emotion,
            aggregated_sentiment=aggregated_sentiment,
            aggregated_salience=aggregated_salience,
            dominant_location=dominant_location,
            dominant_social_context=dominant_social_context,
            temporal_start=temporal_start,
            temporal_end=temporal_end,
            location_hint=location_hint,
            location_type=location_type,  # GAP-002: location category
            participants_json=participants_json,
            activity_type=activity_type,
            activity_type_ultrabert=activity_type_ultrabert,  # Issue 0060
            cohesion_score=1.0 / (1.0 + centroid_result.variance),
            title=title,
            summary=summary,
        )

    def _generate_episode_title(
        self,
        cluster_events: List[EventAdapter],
        location: Optional[str],
        activity: str,
    ) -> str:
        """
        Generate a descriptive title for the episode.

        Priority: Activity + Participants + Location
        Examples:
        - "Family Dinner with Emma, Jake at Home"
        - "Work Meeting with John, Lisa at Office"
        - "Coffee with Rachel at Starbucks"
        """
        import json

        # Extract participants from events
        participants = set()
        for e in cluster_events:
            p_json = getattr(e.event, "participants_json", "[]") or "[]"
            try:
                p_list = json.loads(p_json) if p_json else []
                for p in p_list:
                    if isinstance(p, str) and p:
                        participants.add(p)
            except (json.JSONDecodeError, TypeError):
                pass

        # Also try to extract person entities from NER
        for e in cluster_events:
            ner_json = getattr(e.event, "ner_entities_json", "{}") or "{}"
            try:
                ner_data = json.loads(ner_json) if ner_json else {}
                if isinstance(ner_data, dict):
                    for source in ["ner_family", "ner_general"]:
                        if source in ner_data and isinstance(ner_data[source], dict):
                            entities = ner_data[source].get("entities", [])
                            for ent in entities:
                                if isinstance(ent, dict):
                                    label = ent.get("label", "")
                                    text = ent.get("text", "").strip()
                                    # Include PERSON, PER, KINSHIP labels
                                    if label in ("PERSON", "PER", "KINSHIP") and text:
                                        # Clean up possessives
                                        if text.endswith("'s"):
                                            text = text[:-2]
                                        # Clean up "and Jake" -> "Jake"
                                        if text.lower().startswith(("and ", "with ")):
                                            text = text.split(" ", 1)[1] if " " in text else text
                                        if len(text) > 1:
                                            participants.add(text)
            except (json.JSONDecodeError, TypeError):
                pass

        # Build title parts
        parts = []

        # Activity type (cleaned up)
        if activity:
            activity_clean = activity.replace("_", " ").title()
            parts.append(activity_clean)

        # Participants (max 3)
        if participants:
            participant_list = sorted(participants)[:3]
            parts.append(f"with {', '.join(participant_list)}")

        # Location
        if location:
            parts.append(f"at {location}")

        if parts:
            return " ".join(parts)

        # Fallback: use first event's text snippet
        if cluster_events:
            first_text = getattr(cluster_events[0].event, "text", "") or ""
            if first_text:
                # Take first 50 chars as title
                title = first_text[:50].strip()
                if len(first_text) > 50:
                    title += "..."
                return title

        return f"Episode ({len(cluster_events)} events)"

    def _generate_episode_summary(self, cluster_events: List[EventAdapter]) -> str:
        """Generate a structured-semantic summary from event texts.

        Uses WHO -- WHAT at WHERE: MMR-selected detail sentence.
        Winner of 9-technique benchmark (composite 0.930, semantic 0.810).
        """
        return generate_episode_summary(
            events=[e.event for e in cluster_events],
            episode_location="",
            episode_participants_json="[]",
        )

    def _aggregate_context_fields(
        self, contexts: List["ObservationContext"]
    ) -> tuple[Optional[float], Optional[float], Optional[str], Optional[str]]:
        """Aggregate context fields from member ObservationContext entries."""
        if not contexts:
            return None, None, None, None

        sentiments = [c.sentiment_score for c in contexts if c.sentiment_score is not None]
        aggregated_sentiment = sum(sentiments) / len(sentiments) if sentiments else None

        saliences = [c.salience_score for c in contexts if c.salience_score is not None]
        aggregated_salience = max(saliences) if saliences else None

        dominant_location = (
            _vote_winner([c.location_type or c.location_name for c in contexts]) or None
        )

        dominant_social_context = _vote_winner([c.social_context for c in contexts]) or None

        return aggregated_sentiment, aggregated_salience, dominant_location, dominant_social_context

    def _update_event_states_from_candidates(
        self,
        events: List["P03EventState"],
        episode_candidates: List[EpisodeCandidate],
        noise_ids: List[str],
    ) -> None:
        """
        Update P03EventState with FINAL post-merge/split cluster assignments.

        Uses episode_candidates (which reflect thread-purity, same-thread merge,
        scene segmentation, and fragment absorption) instead of raw HDBSCAN results.
        This ensures st_hipp_events.episode_cluster_id matches st_epi.episode_id.

        Args:
            events: Original event states to update
            episode_candidates: Final episode candidates after all merges/splits
            noise_ids: Event IDs marked as noise
        """
        assignments: Dict[str, tuple] = {}

        for cand in episode_candidates:
            cluster_id = cand.cluster_id
            try:
                label = int(cluster_id.split("_")[-1]) if "_" in cluster_id else 0
            except ValueError:
                label = 0
            for event_id in cand.event_ids:
                assignments[event_id] = (cluster_id, label)

        for event in events:
            if event.event_id in assignments:
                cluster_id, label = assignments[event.event_id]
                event.cluster_id = cluster_id
                event.cluster_label = label
                event.is_noise = False
            elif event.event_id in noise_ids:
                event.cluster_id = None
                event.cluster_label = -1
                event.is_noise = True

    def _update_event_states(
        self,
        events: List["P03EventState"],
        clustering_results: List[HDBSCANClusteringResult],
        noise_ids: List[str],
    ) -> None:
        """
        Update P03EventState with cluster assignments.

        DEPRECATED: Use _update_event_states_from_candidates instead.
        Kept for backward compatibility with tests.

        Args:
            events: Original event states to update
            clustering_results: Results from HDBSCAN
            noise_ids: Event IDs marked as noise
        """
        # Build lookup: event_id -> (cluster_id, label)
        assignments: Dict[str, tuple] = {}

        for result in clustering_results:
            for cluster in result.clusters:
                cluster_id = cluster.cluster_id
                member_ids = cluster.member_event_ids
                # Extract numeric label from cluster_id if possible
                try:
                    label = int(cluster_id.split("_")[-1]) if "_" in cluster_id else 0
                except ValueError:
                    label = 0

                for event_id in member_ids:
                    assignments[event_id] = (cluster_id, label)

        # Update each event
        for event in events:
            if event.event_id in assignments:
                cluster_id, label = assignments[event.event_id]
                event.cluster_id = cluster_id
                event.cluster_label = label
                event.is_noise = False
            elif event.event_id in noise_ids:
                event.cluster_id = None
                event.cluster_label = -1
                event.is_noise = True
            # Events not in any result keep default values

    def _compute_batch_silhouette(
        self,
        clustering_results: Optional[List[HDBSCANClusteringResult]],
    ) -> Optional[float]:
        """
        Compute true silhouette score from HDBSCAN clustering results.

        Uses sklearn.metrics.silhouette_score on the precomputed distance
        matrix and label assignment from clustering. Returns None when
        silhouette is mathematically undefined (fewer than 2 distinct
        non-noise labels, or no distance matrix available).

        Args:
            clustering_results: HDBSCAN results with distance_matrix and labels

        Returns:
            True silhouette score in [-1, 1], or None if undefined
        """
        if not clustering_results:
            return None

        # Aggregate silhouette across all sequences (weighted by event count)
        total_weight = 0
        weighted_sum = 0.0

        for result in clustering_results:
            if result.distance_matrix is None:
                continue

            labels_array = np.array(result.labels)

            # Need at least 2 distinct non-noise labels for silhouette
            non_noise_labels = set(labels_array[labels_array >= 0].tolist())
            if len(non_noise_labels) < 2:
                continue

            # Filter to non-noise events only (silhouette is undefined for noise)
            non_noise_mask = labels_array >= 0
            if non_noise_mask.sum() < 2:
                continue

            non_noise_indices = np.where(non_noise_mask)[0]
            dm_subset = result.distance_matrix[np.ix_(non_noise_indices, non_noise_indices)]
            labels_subset = labels_array[non_noise_indices]

            try:
                sil = sklearn_silhouette_score(dm_subset, labels_subset, metric="precomputed")
                n_events = len(labels_subset)
                weighted_sum += sil * n_events
                total_weight += n_events
            except Exception as e:
                logger.debug(
                    "R2: Silhouette computation failed for sequence",
                    extra={"error": str(e)},
                )
                continue

        if total_weight == 0:
            return None

        return weighted_sum / total_weight

    async def _track_quality_and_adapt(
        self,
        ctx: "P03RunnerContext",
        space_id: str,
        candidates: List[EpisodeCandidate],
        noise_ids: List[str],
        params: HDBSCANParams,
        clustering_results: Optional[List[HDBSCANClusteringResult]] = None,
        episode_clusters: Optional[List] = None,
    ) -> Optional[ClusterQualityMetrics]:
        """
        Track cluster quality and trigger adaptive parameter learning.

        Args:
            ctx: Runner context
            space_id: Space ID for per-space learning
            candidates: Episode candidates from clustering
            noise_ids: Event IDs marked as noise
            params: Current clustering parameters
            clustering_results: HDBSCAN results carrying distance matrices and labels
            episode_clusters: EpisodeCluster list with member_contexts for coherence

        Returns:
            ClusterQualityMetrics if computed, None otherwise
        """
        if not self._quality_tracker:
            return None

        # Compute quality metrics using sync method
        # Build minimal R2 output-like object for compute_from_r2_output
        total_events = sum(len(c.event_ids) for c in candidates) + len(noise_ids)
        cluster_count = len(candidates)
        noise_count = len(noise_ids)

        # Compute true silhouette from precomputed distance matrices and labels
        batch_silhouette = self._compute_batch_silhouette(clustering_results)

        # Create a simple object that matches R2OutputProtocol
        class R2OutputSimple:
            def __init__(self, sil: float, clusters: int, noise: int, sil_valid: bool):
                self.batch_silhouette_score = sil
                self.cluster_count = clusters
                self.noise_count = noise
                self.silhouette_valid = sil_valid

        silhouette_valid = batch_silhouette is not None
        sil_value = batch_silhouette if silhouette_valid else 0.0
        r2_output = R2OutputSimple(sil_value, cluster_count, noise_count, silhouette_valid)
        metrics = self._quality_tracker.compute_from_r2_output(
            space_id=space_id,
            r2_output=r2_output,
        )

        # M4-RSCH-04: Compute batch coherence from episode member contexts
        if episode_clusters:
            scorer = EpisodicCoherenceScorer()
            episode_results = [
                scorer.compute(ep.member_contexts)
                for ep in episode_clusters
                if ep.member_contexts and len(ep.member_contexts) >= 2
            ]
            if episode_results:
                batch_coh = compute_batch_coherence(episode_results)
                metrics.coherence_score = batch_coh.mean_coherence
                metrics.coherence_valid = batch_coh.episode_count > 0
                metrics.compute_composite()

        # Compute avg_cluster_size from candidates (not in ClusterQualityMetrics)
        avg_cluster_size = (
            sum(len(c.event_ids) for c in candidates) / cluster_count if cluster_count > 0 else 0.0
        )

        # Trigger adaptive eps learning (skip when silhouette is invalid —
        # a score of 0.0 from fewer than 2 clusters would cause false adjustments)
        if self._eps_adjuster and self.config.enable_adaptive_eps and silhouette_valid:
            eps_result = self._eps_adjuster.adjust(
                current_eps=params.cluster_selection_epsilon,
                silhouette_score=metrics.silhouette_score,
                avg_cluster_size=avg_cluster_size,
                singleton_rate=metrics.singleton_rate,
                total_clusters_formed=metrics.total_clusters,
            )

            if eps_result.adjusted and hasattr(ctx.syscalls, "set_learned_param"):
                try:
                    await ctx.syscalls.set_learned_param(
                        space_id=space_id,
                        param_key="clustering_eps",
                        param_value=eps_result.new_eps,
                    )
                    logger.info(
                        "R2: Adjusted eps",
                        extra={
                            "space_id": space_id,
                            "old_eps": params.cluster_selection_epsilon,
                            "new_eps": eps_result.new_eps,
                            "reason": eps_result.reason,
                        },
                    )
                except Exception as e:
                    logger.warning(
                        "R2: Failed to persist eps adjustment",
                        extra={"error": str(e)},
                    )

        # Trigger adaptive min_samples learning
        if self._min_samples_adjuster and self.config.enable_adaptive_min_samples:
            min_samples_result = self._min_samples_adjuster.adjust(
                current_min_samples=params.min_samples,
                singleton_rate=metrics.singleton_rate,
            )

            if min_samples_result.adjusted and hasattr(ctx.syscalls, "set_learned_param"):
                try:
                    await ctx.syscalls.set_learned_param(
                        space_id=space_id,
                        param_key="clustering_min_samples",
                        param_value=min_samples_result.new_min_samples,
                    )
                    logger.info(
                        "R2: Adjusted min_samples",
                        extra={
                            "space_id": space_id,
                            "old_min_samples": params.min_samples,
                            "new_min_samples": min_samples_result.new_min_samples,
                            "reason": min_samples_result.reason,
                        },
                    )
                except Exception as e:
                    logger.warning(
                        "R2: Failed to persist min_samples adjustment",
                        extra={"error": str(e)},
                    )

        return metrics

    # =========================================================================
    # EPISODE MATCHING (Issue 2 Fix - Query st_epi before clustering)
    # =========================================================================

    async def _query_existing_episodes(
        self,
        ctx: "P03RunnerContext",
        space_id: str,
        tenant_id: str,
        time_start_ms: int,
        time_end_ms: int,
    ) -> List[Dict]:
        """
        Query st_epi for existing episodes in the time window.

        Uses syscalls to query episodes that could match incoming events.
        Fetches embeddings for similarity comparison.

        Args:
            ctx: Runner context with syscalls
            space_id: Space context
            tenant_id: Tenant context
            time_start_ms: Start of time window (milliseconds)
            time_end_ms: End of time window (milliseconds)

        Returns:
            List of episode records with embeddings
        """
        # Extend time window by 7 days to catch recurring episodes
        SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000
        extended_start = time_start_ms - SEVEN_DAYS_MS

        # Build query for episodes that might match
        query = """
            SELECT
                e.episode_id,
                e.episode_type,
                e.primary_location,
                e.location_type,
                e.narrative_thread_id,
                e.start_time_utc,
                e.end_time_utc,
                e.source_event_count,
                e.cluster_confidence,
                e.version,
                v.vector,
                v.vector_dim
            FROM st_epi e
            LEFT JOIN st_vec v ON e.embedding_id = v.embedding_id
            WHERE e.tenant_id = $1
              AND e.space_id = $2
              AND e.archival_status = 'ACTIVE'
              AND e.start_time_utc >= $3
              AND v.vector IS NOT NULL
            ORDER BY e.start_time_utc DESC
            LIMIT $4
        """

        episodes: List[Dict] = []

        try:
            if hasattr(ctx.syscalls, "execute_query"):
                rows = await ctx.syscalls.execute_query(
                    query,
                    tenant_id,
                    space_id,
                    extended_start,
                    self.config.episode_query_limit,
                )
                for row in rows:
                    episode = {
                        "episode_id": row["episode_id"],
                        "episode_type": row.get("episode_type", ""),
                        "primary_location": row.get("primary_location"),
                        "location_type": row.get("location_type"),
                        "narrative_thread_id": row.get("narrative_thread_id"),
                        "start_time_utc": row.get("start_time_utc", 0),
                        "end_time_utc": row.get("end_time_utc", 0),
                        "source_event_count": row.get("source_event_count", 0),
                        "cluster_confidence": row.get("cluster_confidence", 0.5),
                        "version": row.get("version", 1),
                        "embedding": self._decode_vector(
                            row.get("vector"), row.get("vector_dim", 768)
                        ),
                    }
                    if episode["embedding"] is not None:
                        episodes.append(episode)
        except Exception as e:
            logger.warning(
                "R2: Failed to query existing episodes, will cluster all as new",
                extra={"error": str(e)},
            )

        return episodes

    def _decode_vector(
        self, vector_bytes: Optional[bytes], vector_dim: int
    ) -> Optional[np.ndarray]:
        """Decode BYTEA vector to numpy array."""
        if vector_bytes is None:
            return None
        try:
            import struct

            expected_size = vector_dim * 4  # float32 = 4 bytes
            if len(vector_bytes) != expected_size:
                return None
            floats = struct.unpack(f"<{vector_dim}f", vector_bytes)
            return np.array(floats, dtype=np.float64)
        except Exception:
            return None

    def _match_events_to_existing_episodes(
        self,
        events: List["P03EventState"],
        existing_episodes: List[Dict],
    ) -> Tuple[List["P03EventState"], List["P03EventState"]]:
        """
        Match incoming events to existing episodes by embedding similarity.

        Events matching an existing episode (similarity >= reinforce_threshold)
        get their episode_match_id set and reconciliation_action = REINFORCE.
        These events should UPDATE the existing episode, not create duplicates.

        Args:
            events: Events with embeddings to match
            existing_episodes: Episodes from st_epi with embeddings

        Returns:
            Tuple of (matched_events, novel_events)
            matched_events: Events that match existing episodes (REINFORCE)
            novel_events: Events that need clustering (new episodes)
        """
        if not existing_episodes:
            return [], events

        matched_events: List["P03EventState"] = []
        novel_events: List["P03EventState"] = []

        for event in events:
            # Skip events without embeddings
            if event.embedding_768 is None:
                novel_events.append(event)
                continue

            event_embedding = np.asarray(event.embedding_768, dtype=np.float64)

            # Find best matching episode
            best_match = None
            best_similarity = 0.0

            for episode in existing_episodes:
                ep_embedding = episode.get("embedding")
                if ep_embedding is None:
                    continue

                similarity = self._cosine_similarity(event_embedding, ep_embedding)

                # Check if this is a better match
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = episode

            # Apply threshold logic
            if best_match and best_similarity >= self.config.episode_reinforce_threshold:
                # Mark event as matching existing episode
                event.episode_match_id = best_match["episode_id"]
                event.episode_match_similarity = best_similarity
                event.episode_match_version = best_match.get("version", 1)
                event.reconciliation_action = ReconciliationAction.REINFORCE
                event.reconciliation_reason = (
                    f"Matches existing episode {best_match['episode_id'][:8]}... "
                    f"with similarity {best_similarity:.3f}"
                )
                matched_events.append(event)

                logger.debug(
                    "R2: Event matched to existing episode",
                    extra={
                        "event_id": event.event_id,
                        "episode_id": best_match["episode_id"],
                        "similarity": round(best_similarity, 3),
                    },
                )
            else:
                # No match - needs clustering
                novel_events.append(event)

        if matched_events:
            logger.info(
                "R2: Matched events to existing episodes",
                extra={
                    "matched_count": len(matched_events),
                    "novel_count": len(novel_events),
                    "threshold": self.config.episode_reinforce_threshold,
                },
            )

        return matched_events, novel_events

    # =========================================================================
    # M9.8: ENGINE-BASED RECONCILIATION
    # =========================================================================

    def _ensure_engine_components(self) -> None:
        """Lazy-initialize engine components on first use."""
        if self._engine_registry is None:
            self._engine_registry = TruthLayerRegistry.from_contracts()
        if self._engine_identity is None:
            self._engine_identity = EpisodicIdentity()

    def _engine_match_events(
        self,
        events: List["P03EventState"],
        existing_episodes: List[Dict],
        cycle_id: str,
        space_id: str,
        tenant_id: str,
    ) -> Tuple[List["P03EventState"], List["P03EventState"]]:
        """Engine-based pre-clustering REINFORCE matching (Seam 1).

        Replaces _match_events_to_existing_episodes when
        enable_engine_reinforce=True.

        For each event, converts to ReconciliationCandidate, runs
        framework.decide() against TruthRecords built from existing
        episodes.  Events where action=REINFORCE are matched; others
        go to the clustering pool.
        """
        self._ensure_engine_components()

        if not existing_episodes:
            return [], events

        # Convert existing episodes to TruthRecords (once for the batch)
        truth_records = [R2Adapter.existing_to_truth_record(ep) for ep in existing_episodes]

        matched: List["P03EventState"] = []
        novel: List["P03EventState"] = []

        for event in events:
            if event.embedding_768 is None:
                novel.append(event)
                continue

            candidate = R2Adapter.event_to_candidate(
                event,
                cycle_id,
                space_id,
                tenant_id,
            )

            result = ReconciliationFramework.decide(
                candidate=candidate,
                layer="st_epi",
                registry=self._engine_registry,
                existing_records=truth_records,
                # identity_strategy=None: existing episodes from st_epi lack
                # structural metadata (topics, participants, focal) needed
                # by EpisodicIdentity.  Pure cosine-sim + thresholds suffices
                # for R2 pre-clustering matching.
                identity_strategy=None,
            )

            if result.action == ReconciliationAction.REINFORCE and result.match_id:
                # Find the version from the matching episode
                match_version = 1
                for ep in existing_episodes:
                    if ep["episode_id"] == result.match_id:
                        match_version = ep.get("version", 1)
                        break

                event.episode_match_id = result.match_id
                event.episode_match_similarity = result.similarity
                event.episode_match_version = match_version
                event.reconciliation_action = ReconciliationAction.REINFORCE
                event.reconciliation_reason = result.reason
                matched.append(event)
            else:
                novel.append(event)

        if matched:
            logger.info(
                "R2: Engine matched events to existing episodes",
                extra={
                    "matched_count": len(matched),
                    "novel_count": len(novel),
                    "path": "engine",
                },
            )

        return matched, novel

    def _engine_extend_episodes(
        self,
        episode_candidates: List,
        existing_episodes: List[Dict],
        event_lookup: Dict,
        cycle_id: str,
        space_id: str,
        tenant_id: str,
    ) -> int:
        """Engine-based post-clustering EXTEND matching (Seam 2).

        Replaces CrossBatchExtendMatcher when enable_engine_extend=True.

        For each EpisodeCandidate, converts to ReconciliationCandidate,
        runs framework.decide() against TruthRecords. If action=EXTEND,
        annotates the candidate.

        Returns the count of extended candidates.
        """
        self._ensure_engine_components()

        if not existing_episodes or not episode_candidates:
            return 0

        truth_records = [R2Adapter.existing_to_truth_record(ep) for ep in existing_episodes]

        extended_count = 0

        for cand in episode_candidates:
            if cand.centroid_embedding is None:
                continue

            rc = R2Adapter.episode_to_candidate(
                cand,
                cycle_id,
                space_id,
                tenant_id,
                event_lookup,
            )

            result = ReconciliationFramework.decide(
                candidate=rc,
                layer="st_epi",
                registry=self._engine_registry,
                existing_records=truth_records,
                # identity_strategy=None: same rationale as Seam 1 —
                # st_epi rows have no structural metadata for the identity
                # model. Cosine-sim thresholds are sufficient for cross-batch
                # episode extension.
                identity_strategy=None,
            )

            if (
                result.action
                in (
                    ReconciliationAction.EXTEND,
                    ReconciliationAction.REINFORCE,
                )
                and result.match_id
            ):
                cand.reconciliation_action = "EXTEND"
                cand.extend_target_episode_id = result.match_id
                cand.extend_similarity = result.similarity
                extended_count += 1

        if extended_count > 0:
            logger.info(
                "R2: Engine cross-batch extend applied",
                extra={
                    "candidates_extended": extended_count,
                    "candidates_total": len(episode_candidates),
                    "path": "engine",
                },
            )

        return extended_count

    def _compute_ambiguity_score(
        self,
        location_hint: Optional[str],
        participants_json: str,
        activity_type: str,
        activity_type_ultrabert: str,
        entity_ids: set,
        cluster_events: List,
    ) -> float:
        """
        Compute ambiguity score based on missing critical fields.

        Higher score = more ambiguous (more missing information).
        Used by SPC-UQ algorithm for uncertainty quantification.

        Critical fields for episode clarity:
        - Location (where it happened)
        - Participants (who was involved)
        - Activity type (what type of activity)
        - Entity IDs (named entities mentioned)

        Returns:
            Float between 0.0 (fully specified) and 1.0 (highly ambiguous)
        """
        import json

        missing_fields = 0
        total_fields = 4  # location, participants, activity, entities

        # Check location
        if not location_hint:
            missing_fields += 1

        # Check participants
        try:
            participants = json.loads(participants_json or "[]")
            if not participants:
                missing_fields += 1
        except (json.JSONDecodeError, TypeError):
            missing_fields += 1

        # Check activity type (prefer UltraBERT, fallback to legacy)
        has_activity = bool(activity_type_ultrabert or activity_type)
        if not has_activity:
            missing_fields += 1

        # Check entity IDs
        if not entity_ids:
            missing_fields += 1

        # Additional ambiguity factors
        ambiguity_penalty = 0.0

        # Small clusters are more ambiguous
        if len(cluster_events) < 3:
            ambiguity_penalty += 0.1

        # No sentiment/emotion data makes it more ambiguous
        has_sentiment_data = any(
            getattr(e.event, "sentiment_score", None) is not None
            or getattr(e.event, "emotion_label", None)
            for e in cluster_events
        )
        if not has_sentiment_data:
            ambiguity_penalty += 0.1

        # Calculate base score from missing fields
        base_score = missing_fields / total_fields

        # Apply penalty and clamp to [0, 1]
        final_score = min(1.0, base_score + ambiguity_penalty)

        return final_score

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(vec1, vec2) / (norm1 * norm2))


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def create_r2_phase(config: Optional[R2Config] = None) -> R2EpisodicIntegrator:
    """
    Factory function to create R2 phase.

    Args:
        config: Optional configuration (defaults used if not provided)

    Returns:
        Configured R2EpisodicIntegrator instance
    """
    return R2EpisodicIntegrator(config=config)


# =============================================================================
# CROSS-EPISODE THREAD MATCHING (Epic 5.1, Issue 5.1.3)
# =============================================================================


def detect_arc_completion(
    current_arc_position: str,
    prior_episodes: List[dict],
) -> bool:
    """Detect if this episode completes a narrative goal arc.

    A thread is complete when the current episode reaches CLIMAX or RESOLUTION
    and at least one prior episode had EXPOSITION or RISING_ACTION (buildup).

    Args:
        current_arc_position: Arc position of current episode.
        prior_episodes: Prior episodes from find_thread_continuations.

    Returns:
        True if the narrative goal arc is complete.
    """
    if not prior_episodes:
        return False
    if current_arc_position not in ("CLIMAX", "RESOLUTION"):
        return False
    prior_arcs = {ep.get("narrative_arc_position") for ep in prior_episodes}
    return bool(prior_arcs & {"EXPOSITION", "RISING_ACTION"})


def log_thread_completion(
    thread_id: str,
    tenant_id: str,
    completed_episode_id: str,
    current_arc_position: str,
    current_start_time: int,
    prior_episodes: List[dict],
) -> None:
    """Emit structured observability event for narrative thread completion.

    Args:
        thread_id: Completed narrative thread_id.
        tenant_id: Tenant isolation.
        completed_episode_id: Episode that completed the arc.
        current_arc_position: CLIMAX or RESOLUTION.
        current_start_time: Start time of completing episode (ms).
        prior_episodes: Prior episodes in the thread chain.
    """
    sorted_chain = sorted(prior_episodes, key=lambda e: e.get("start_time_utc", 0))
    episode_chain = [
        {
            "episode_id": ep["episode_id"],
            "arc_position": ep.get("narrative_arc_position"),
            "start_time_utc": ep.get("start_time_utc"),
        }
        for ep in sorted_chain
    ] + [
        {
            "episode_id": completed_episode_id,
            "arc_position": current_arc_position,
            "start_time_utc": current_start_time,
        },
    ]

    first_start = sorted_chain[0].get("start_time_utc", 0) if sorted_chain else current_start_time
    span_ms = current_start_time - first_start if first_start else 0
    span_days = span_ms / 86_400_000 if span_ms > 0 else 0

    logger.info(
        "NARRATIVE_THREAD_COMPLETED",
        extra={
            "topic": "narrative.thread.completed.v1",
            "thread_id": thread_id,
            "tenant_id": tenant_id,
            "completed_episode_id": completed_episode_id,
            "episode_chain": episode_chain,
            "total_episodes": len(episode_chain),
            "span_days": round(span_days, 1),
            "completed_at_utc": int(time.time()),
        },
    )


async def find_thread_continuations(
    conn,
    tenant_id: str,
    thread_id: str,
    exclude_episode_id: str,
) -> List[dict]:
    """
    Find existing episodes sharing the same narrative thread.

    Queries st_epi for ACTIVE episodes with matching narrative_thread_id,
    excluding the current episode. Uses ix_st_epi_narrative_thread partial index.

    Args:
        conn: asyncpg connection
        tenant_id: Tenant isolation
        thread_id: Narrative thread_id to match
        exclude_episode_id: Episode to exclude (self)

    Returns:
        List of dicts with episode_id, narrative_arc_position, start_time_utc,
        end_time_utc, episode_summary. Ordered most-recent first.
    """
    if not thread_id:
        return []
    rows = await conn.fetch(
        """
        SELECT episode_id, narrative_arc_position, start_time_utc, end_time_utc,
               episode_summary
        FROM st_epi
        WHERE tenant_id = $1
          AND narrative_thread_id = $2
          AND episode_id != $3
          AND archival_status = 'ACTIVE'
        ORDER BY start_time_utc DESC
        LIMIT 10
        """,
        tenant_id,
        thread_id,
        exclude_episode_id,
    )
    return [dict(r) for r in rows]
