"""
R2 Phase - Episodic Integration (DBSCAN Clustering).

M4 Epic 4.2: Implement R2 Phase for Episodic Clustering with Composite Distance.

This phase performs episodic clustering on events from R1:
1. Split events into sequences by time gaps / geohash / entity boundaries (Issue 4.2.2)
2. Cluster each sequence using EpisodicDBSCAN with composite distance (Issues 4.2.1, 4.2.3)
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
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Union

import numpy as np

from k0.modules.consolidation.algorithms import (
    CentroidCalculator,
    CentroidResult,
    ClusteringResult,
    ClusterQualityMetrics,
    ClusterQualityTracker,
    DBSCANParams,
    EpisodeCandidate,
    EpisodeSplitter,
    EpisodicDBSCAN,
    EpisodicHDBSCAN,
    EpsAdjuster,
    EpsAdjustmentConfig,
    HDBSCANClusteringResult,
    HDBSCANParams,
    MinSamplesAdjuster,
    MinSamplesConfig,
    SplitConfig,
    WeightingStrategy,
)
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
# R2 CONFIGURATION
# =============================================================================


@dataclass
class R2Config:
    """
    R2 phase configuration.

    Attributes:
        min_batch_size: Minimum events required for clustering (skip if less)
        eps: DBSCAN eps parameter (0.0 = use adaptive learning)
        min_samples: DBSCAN min_samples parameter (0 = use adaptive learning)
        semantic_weight: Weight for semantic (embedding) distance [0,1]
        temporal_weight: Weight for temporal distance [0,1]
        enable_splitting: Whether to split events before clustering
        time_gap_minutes: Time gap threshold for sequence splitting
        enable_adaptive_eps: Whether to use adaptive eps learning
        enable_adaptive_min_samples: Whether to use adaptive min_samples learning
        enable_quality_tracking: Whether to track cluster quality metrics
        weighting_strategy: Strategy for centroid weighting
        use_hdbscan: Use HDBSCAN instead of DBSCAN for better noise handling
        noise_rescue_threshold: Outlier score below which noise is rescued (HDBSCAN)
        cluster_selection_method: HDBSCAN cluster selection ('eom' or 'leaf')
    """

    min_batch_size: int = 2
    eps: float = 0.0  # 0.0 = use adaptive or default
    min_samples: int = 0  # 0 = use adaptive or default
    semantic_weight: float = 0.7
    temporal_weight: float = 0.3
    enable_splitting: bool = True
    time_gap_minutes: int = 60
    enable_adaptive_eps: bool = True
    enable_adaptive_min_samples: bool = True
    enable_quality_tracking: bool = True
    weighting_strategy: WeightingStrategy = WeightingStrategy.IMPORTANCE
    use_hdbscan: bool = True  # Use HDBSCAN by default for noise rescue
    noise_rescue_threshold: float = 0.5  # Rescue noise with outlier_score < this
    cluster_selection_method: str = "leaf"  # 'leaf' preserves small clusters
    enable_canonicalization: bool = False  # Disabled: HDBSCAN clusters are already good
    canonicalization_time_bucket_hours: int = 1  # Time bucket for signature grouping (if enabled)

    # === ISSUE 2 FIX: Episode Matching ===
    # Query st_epi for existing episodes before clustering to avoid duplicates
    enable_episode_matching: bool = True  # Enable matching to existing episodes
    episode_reinforce_threshold: float = 0.85  # Cosine similarity threshold for REINFORCE
    episode_extend_threshold: float = 0.60  # Threshold for EXTEND (future use)
    episode_query_limit: int = 50  # Max episodes to query per batch


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
        # Extract from event if available (may be in content or metadata)
        # For now, return None - location handling is phase-specific
        return None

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


# =============================================================================
# R2 EPISODIC INTEGRATOR PHASE
# =============================================================================


class R2EpisodicIntegrator:
    """
    R2 Phase: Episodic Integration (DBSCAN Clustering).

    Responsibilities:
        1. Check if batch size >= min_batch_size (skip otherwise)
        2. Split events into sequences (by time gap, location, entity)
        3. Cluster each sequence using EpisodicDBSCAN
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
        self._clusterer: Optional[Union[EpisodicDBSCAN, EpisodicHDBSCAN]] = None
        self._centroid_calculator: Optional[CentroidCalculator] = None
        self._quality_tracker: Optional[ClusterQualityTracker] = None
        self._eps_adjuster: Optional[EpsAdjuster] = None
        self._min_samples_adjuster: Optional[MinSamplesAdjuster] = None

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
            4. Cluster each sequence with DBSCAN
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
            dbscan_params = await self._get_dbscan_params(ctx, space_id)

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
            # =================================================================
            matched_events: List["P03EventState"] = []
            novel_events = events_with_embeddings  # Default: all events are novel

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
                    # Match events to existing episodes
                    matched_events, novel_events = self._match_events_to_existing_episodes(
                        events=events_with_embeddings,
                        existing_episodes=existing_episodes,
                    )

            # Track matched events count for output
            matched_event_count = len(matched_events)

            # Only cluster novel events (those not matching existing episodes)
            # Adapt events to EventLike protocol
            adapted_events = [EventAdapter(e) for e in novel_events]

            # Step 1: Split events into sequences
            sequences = self._split_events(adapted_events)

            # Step 2: Cluster each sequence
            all_results: List[Union[ClusteringResult, HDBSCANClusteringResult]] = []
            all_noise_ids: List[str] = []

            for sequence in sequences:
                if len(sequence) < self.config.min_batch_size:
                    # Too small to cluster - mark as noise
                    all_noise_ids.extend(e.event_id for e in sequence)
                    continue

                # Params already set in _initialize_components via EpisodicDBSCAN(params=...)
                clustering_result = self._clusterer.cluster(sequence)
                all_results.append(clustering_result)

                # Extract noise event IDs (label=-1 in DBSCAN)
                for idx, label in enumerate(clustering_result.labels):
                    if label == -1:
                        all_noise_ids.append(sequence[idx].event_id)

            # Step 3: Compute centroids and build episode candidates
            episode_candidates: List[EpisodeCandidate] = []
            episode_clusters: List[EpisodeCluster] = []

            # Build event lookup for centroid calculation
            event_lookup = {e.event_id: e for e in adapted_events}

            for clustering_result in all_results:
                # clusters is List[EpisodeCluster] from DBSCAN
                for cluster in clustering_result.clusters:
                    # Skip noise clusters (single events with label -1)
                    member_ids = cluster.member_event_ids
                    if not member_ids:
                        continue

                    # Skip single-member clusters (likely noise)
                    # HDBSCAN already handles noise rescue, so single-member clusters
                    # that made it here are legitimate small clusters
                    if len(member_ids) == 1:
                        # Single events are not episodes - skip them
                        continue

                    # Get events for this cluster
                    cluster_events = [
                        event_lookup[eid] for eid in member_ids if eid in event_lookup
                    ]

                    if not cluster_events:
                        continue

                    # Compute centroid
                    centroid_result = self._centroid_calculator.compute(
                        cluster_events, strategy=self.config.weighting_strategy
                    )

                    # Build episode candidate
                    # Cohesion = 1/(1+variance) - lower variance means higher cohesion
                    cohesion = 1.0 / (1.0 + centroid_result.variance)
                    candidate = EpisodeCandidate(
                        cluster_id=cluster.cluster_id,
                        space_id=envelope.context.space_id,
                        event_ids=member_ids,
                        event_count=len(member_ids),
                        centroid_embedding=centroid_result.centroid,
                        temporal_start=min(e.timestamp for e in cluster_events),
                        temporal_end=max(e.timestamp for e in cluster_events),
                        cohesion_score=cohesion,
                        variance=centroid_result.variance,
                    )
                    episode_candidates.append(candidate)

                    # Build EpisodeCluster for envelope outputs
                    episode_cluster = self._build_episode_cluster(
                        cluster.cluster_id, member_ids, cluster_events, centroid_result
                    )
                    episode_clusters.append(episode_cluster)

            # Step 3.5: Canonicalize episodes (merge by signature)
            if self.config.enable_canonicalization and len(episode_clusters) > 1:
                episode_clusters, merge_count = self._canonicalize_episodes(episode_clusters)
                if merge_count > 0:
                    logger.info(
                        "R2: Canonicalized episodes",
                        extra={
                            "merged_count": merge_count,
                            "canonical_count": len(episode_clusters),
                        },
                    )

            # Step 4: Update event states with cluster assignments
            self._update_event_states(envelope.events, all_results, all_noise_ids)

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
                "eps": dbscan_params.eps,
                "min_samples": dbscan_params.min_samples,
                "semantic_weight": self.config.semantic_weight,
                "temporal_weight": self.config.temporal_weight,
                "episode_matching_enabled": self.config.enable_episode_matching,
                "matched_to_existing": matched_event_count,  # Issue 2 fix
            }

            # Step 6: Track quality metrics and adaptive learning
            quality_metrics = None
            if self.config.enable_quality_tracking and episode_candidates:
                quality_metrics = await self._track_quality_and_adapt(
                    ctx, space_id, episode_candidates, all_noise_ids, dbscan_params
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
                    "eps": dbscan_params.eps,
                    "min_samples": dbscan_params.min_samples,
                    "silhouette": quality_metrics.silhouette_score if quality_metrics else None,
                    "duration_ms": duration_ms,
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
                    "eps": dbscan_params.eps,
                    "min_samples": dbscan_params.min_samples,
                    "silhouette": (
                        round(quality_metrics.silhouette_score, 3) if quality_metrics else None
                    ),
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
        # Splitter - only using time_gap_minutes (geohash/entity split not implemented)
        split_config = SplitConfig(
            time_gap_minutes=self.config.time_gap_minutes,
        )
        self._splitter = EpisodeSplitter(config=split_config)

        # Choose clustering algorithm based on config
        if self.config.use_hdbscan:
            # HDBSCAN with noise rescue capability
            hdbscan_params = HDBSCANParams(
                min_cluster_size=2,  # Smallest episode size
                min_samples=1,  # Allow more inclusive clustering
                cluster_selection_epsilon=self.config.eps if self.config.eps > 0 else 0.0,
                noise_rescue_threshold=self.config.noise_rescue_threshold,
                temporal_weight=self.config.temporal_weight,
                cluster_selection_method=self.config.cluster_selection_method,
            )
            self._clusterer = EpisodicHDBSCAN(params=hdbscan_params)
            logger.info(
                "R2 using HDBSCAN with noise_rescue_threshold=%.2f, cluster_selection=%s",
                self.config.noise_rescue_threshold,
                self.config.cluster_selection_method,
            )
        else:
            # Legacy DBSCAN (includes temporal_weight, eps, min_samples)
            dbscan_params = DBSCANParams(
                eps=(
                    self.config.eps if self.config.eps > 0 else 0.07
                ),  # 0.07 for tight UltraBERT clustering (was 0.10)
                min_samples=self.config.min_samples if self.config.min_samples > 0 else 2,
                temporal_weight=self.config.temporal_weight,
            )
            self._clusterer = EpisodicDBSCAN(params=dbscan_params)
            logger.info(
                "R2 using DBSCAN with eps=%.2f, min_samples=%d",
                dbscan_params.eps,
                dbscan_params.min_samples,
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

    async def _get_dbscan_params(self, ctx: "P03RunnerContext", space_id: str) -> DBSCANParams:
        """
        Get DBSCAN parameters from config or adaptive learning.

        Args:
            ctx: Runner context with syscalls
            space_id: Space ID for per-space params

        Returns:
            DBSCANParams with eps and min_samples
        """
        # Start with config values or defaults (0.07 eps for tight UltraBERT clustering)
        eps = self.config.eps if self.config.eps > 0 else 0.07
        min_samples = self.config.min_samples if self.config.min_samples > 0 else 2

        # Try to get learned params from syscalls (st_learned_weights)
        try:
            if hasattr(ctx.syscalls, "get_learned_param"):
                learned_eps = await ctx.syscalls.get_learned_param(
                    space_id=space_id, param_key="dbscan_eps"
                )
                if learned_eps is not None:
                    eps = learned_eps

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

        return DBSCANParams(eps=eps, min_samples=min_samples)

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

    def _canonicalize_episodes(
        self, episodes: List[EpisodeCluster]
    ) -> tuple[List[EpisodeCluster], int]:
        """
        Merge episodes with the same signature into canonical episodes.

        Signature = (episode_type, primary_location, time_bucket)
        Episodes with the same signature are merged:
        - member_event_ids: union
        - participants: union
        - temporal bounds: min/max
        - sentiment/emotion: weighted average
        - cohesion: recomputed as average
        - summary: regenerated

        Args:
            episodes: List of episode clusters to canonicalize

        Returns:
            Tuple of (canonical_episodes, merge_count)
        """
        from collections import defaultdict

        bucket_hours = self.config.canonicalization_time_bucket_hours
        bucket_ms = bucket_hours * 3600 * 1000

        # Group by signature
        signature_groups: Dict[tuple, List[EpisodeCluster]] = defaultdict(list)
        for ep in episodes:
            # Compute time bucket from temporal_start
            time_bucket = ep.temporal_start // bucket_ms if ep.temporal_start > 0 else 0
            # Normalize activity_type to episode_type mapping
            episode_type = self._infer_episode_type(ep)
            # Fix 2: More specific signature includes participant count and event count bucket
            participant_count = len(ep.participants_json.split(",")) if ep.participants_json else 0
            event_count_bucket = ep.event_count // 3  # Group by event count (0-2, 3-5, 6-8, etc.)
            # Semantic hash from first few event IDs to prevent unrelated merging
            semantic_hint = ep.member_event_ids[0][:8] if ep.member_event_ids else ""
            signature = (
                episode_type,
                ep.location_hint or "",
                time_bucket,
                participant_count,
                event_count_bucket,
                semantic_hint,
            )
            signature_groups[signature].append(ep)

        # Merge groups with more than 1 episode
        canonical: List[EpisodeCluster] = []
        merge_count = 0

        for signature, group in signature_groups.items():
            if len(group) == 1:
                # No merge needed - compute better confidence
                ep = group[0]
                ep = self._recompute_confidence(ep)
                canonical.append(ep)
            else:
                # Merge multiple episodes into one canonical
                merged = self._merge_episodes(group, signature)
                canonical.append(merged)
                merge_count += len(group) - 1  # Count how many were merged away

        return canonical, merge_count

    def _infer_episode_type(self, ep: EpisodeCluster) -> str:
        """Infer episode type from activity_type_ultrabert or activity_type or location.

        Priority order (Issue 0060):
        1. activity_type_ultrabert (UltraBERT 12-type INGRESS) - most granular
        2. activity_type (legacy 7-type) - backward compatibility
        3. Location-based inference - fallback
        """
        # Priority 1: UltraBERT 12-type INGRESS classification (Issue 0060)
        # These map directly to episode types with full granularity
        ultrabert_type = ep.activity_type_ultrabert.upper() if ep.activity_type_ultrabert else ""
        ultrabert_mapping = {
            "DIARY": "reflection",  # Personal journaling/logging
            "TASK": "task",  # To-do items, action items
            "HEALTH": "health",  # Medical, exercise, wellness
            "FINANCE": "financial",  # Money, budget, transactions
            "RELATIONSHIP": "social",  # Interpersonal connections
            "WORK": "work",  # Professional activities
            "META": "system",  # System/meta operations
            "MEMORY": "memory",  # Memory recall/queries
            "PLANNING": "planning",  # Future planning
            "CELEBRATION": "milestone",  # Celebrations, achievements
            "CONCERN": "concern",  # Worries, problems
            "GRATITUDE": "gratitude",  # Thankfulness, appreciation
        }
        if ultrabert_type in ultrabert_mapping:
            return ultrabert_mapping[ultrabert_type]

        # Priority 2: Legacy activity_type (backward compatibility)
        activity = ep.activity_type.lower() if ep.activity_type else ""
        location = (ep.location_hint or "").lower()

        # Fix 3: Direct mapping for uppercase activity types from input data
        # These come from submit_diverse_events.py activity_type field
        activity_upper = ep.activity_type.upper() if ep.activity_type else ""
        direct_mapping = {
            "FAMILY": "family",
            "WORK": "work",
            "HEALTH": "health",
            "SOCIAL": "social",
            "LEARNING": "learning",
            "MILESTONE": "milestone",
            "TRAVEL": "travel",
            "FINANCIAL": "financial",
            "REMINDER": "reminder",
            "DECISION": "decision",
            "REFLECTION": "reflection",
            "EMOTIONAL": "emotional",
            "NEWS": "news",
            "QUERY": "query",
        }
        if activity_upper in direct_mapping:
            return direct_mapping[activity_upper]

        # Map activity types to episode types (pattern matching)
        if any(w in activity for w in ["work", "meeting", "standup", "review", "presentation"]):
            return "work"
        if any(w in activity for w in ["family", "dinner", "birthday", "party"]):
            return "family"
        if any(w in activity for w in ["coffee", "lunch", "social", "movie"]):
            return "social"
        if any(w in activity for w in ["exercise", "run", "yoga", "gym", "health"]):
            return "health"
        if any(w in activity for w in ["travel", "flight", "trip", "visit"]):
            return "travel"
        if any(w in activity for w in ["learn", "read", "course", "webinar", "study"]):
            return "learning"
        if any(w in activity for w in ["remind", "reminder", "forget"]):
            return "reminder"
        if any(w in activity for w in ["decide", "decision", "advice", "should"]):
            return "decision"
        if any(w in activity for w in ["reflect", "realize", "learn", "insight"]):
            return "reflection"
        if any(w in activity for w in ["feel", "emotion", "anxious", "happy", "sad"]):
            return "emotional"

        # Priority 3: Fallback to location-based inference
        if any(w in location for w in ["office", "conference", "boardroom"]):
            return "work"
        if any(w in location for w in ["starbucks", "cafe", "restaurant", "chipotle"]):
            return "social"
        if any(w in location for w in ["park", "gym", "yoga", "clinic", "medical", "dental"]):
            return "health"
        if any(w in location for w in ["school", "elementary", "university"]):
            return "education"
        if any(w in location for w in ["airport", "hotel", "bridge", "trail"]):
            return "travel"
        # Home is last fallback - don't use it as primary signal
        if any(w in location for w in ["home", "apartment"]):
            return "home"  # Changed from 'routine' to be more specific

        return "miscellaneous"  # Changed from 'unknown' for clarity

    def _merge_episodes(self, episodes: List[EpisodeCluster], signature: tuple) -> EpisodeCluster:
        """Merge multiple episodes into one canonical episode."""
        import json
        import uuid

        # Collect all member events
        all_member_ids: List[str] = []
        for ep in episodes:
            all_member_ids.extend(ep.member_event_ids)
        all_member_ids = list(set(all_member_ids))  # Dedupe

        # Aggregate participants
        all_participants: set = set()
        for ep in episodes:
            try:
                participants = json.loads(ep.participants_json or "[]")
                all_participants.update(participants)
            except json.JSONDecodeError:
                pass

        # Temporal bounds - min/max across all episodes
        temporal_start = min(ep.temporal_start for ep in episodes)
        temporal_end = max(ep.temporal_end for ep in episodes)

        # Weighted average sentiment (by event count)
        total_events = sum(ep.event_count for ep in episodes)
        avg_sentiment = (
            sum(ep.dominant_sentiment * ep.event_count for ep in episodes) / total_events
            if total_events > 0
            else 0.0
        )

        # Most common emotion
        emotion_counts: Dict[str, int] = {}
        for ep in episodes:
            if ep.dominant_emotion:
                emotion_counts[ep.dominant_emotion] = (
                    emotion_counts.get(ep.dominant_emotion, 0) + ep.event_count
                )
        dominant_emotion = max(emotion_counts, key=emotion_counts.get) if emotion_counts else ""

        # Average cohesion
        avg_cohesion = sum(ep.cohesion_score for ep in episodes) / len(episodes)

        # Use signature for type/location
        episode_type, location, _ = signature

        # Generate merged title
        title = f"{episode_type.title()} at {location}" if location else episode_type.title()

        # Generate merged summary
        summaries = [ep.summary for ep in episodes if ep.summary]
        summary = " | ".join(summaries[:3])
        if len(summaries) > 3:
            summary += f" ... ({len(summaries)} episodes merged)"

        # Compute confidence score
        confidence = self._compute_confidence(
            event_count=len(all_member_ids),
            temporal_start=temporal_start,
            temporal_end=temporal_end,
            participant_count=len(all_participants),
            cohesion=avg_cohesion,
            location_purity=1.0,  # All same location by signature
        )

        # Aggregate UltraBERT activity types from merged episodes (Issue 0060)
        ultrabert_counts: Dict[str, int] = {}
        for ep in episodes:
            if ep.activity_type_ultrabert:
                ultrabert_counts[ep.activity_type_ultrabert] = (
                    ultrabert_counts.get(ep.activity_type_ultrabert, 0) + ep.event_count
                )
        activity_type_ultrabert = (
            max(ultrabert_counts, key=ultrabert_counts.get) if ultrabert_counts else ""
        )

        # GAP-002: Aggregate location_type from merged episodes
        location_type_counts: Dict[str, int] = {}
        for ep in episodes:
            if ep.location_type:
                location_type_counts[ep.location_type] = (
                    location_type_counts.get(ep.location_type, 0) + ep.event_count
                )
        merged_location_type = (
            max(location_type_counts, key=location_type_counts.get)
            if location_type_counts
            else None
        )

        # Issue 7.6: Aggregate member_contexts from merged episodes
        all_member_contexts = []
        for ep in episodes:
            all_member_contexts.extend(ep.member_contexts)

        (
            aggregated_sentiment,
            aggregated_salience,
            dominant_location,
            dominant_social_context,
        ) = self._aggregate_context_fields(all_member_contexts)

        return EpisodeCluster(
            cluster_id=f"canonical-{uuid.uuid4().hex[:16]}",
            member_event_ids=all_member_ids,
            member_contexts=all_member_contexts,  # Issue 7.6
            centroid_embedding_id=None,
            dominant_sentiment=avg_sentiment,
            dominant_emotion=dominant_emotion,
            aggregated_sentiment=aggregated_sentiment,
            aggregated_salience=aggregated_salience,
            dominant_location=dominant_location,
            dominant_social_context=dominant_social_context,
            temporal_start=temporal_start,
            temporal_end=temporal_end,
            location_hint=location or None,
            location_type=merged_location_type,  # GAP-002: location category
            participants_json=json.dumps(sorted(all_participants)),
            activity_type=episode_type,
            activity_type_ultrabert=activity_type_ultrabert,  # Issue 0060
            cohesion_score=confidence,  # Use confidence as cohesion display
            title=title,
            summary=summary,
        )

    def _recompute_confidence(self, ep: EpisodeCluster) -> EpisodeCluster:
        """Recompute confidence score for a single episode."""
        import json

        try:
            participants = json.loads(ep.participants_json or "[]")
            participant_count = len(participants)
        except json.JSONDecodeError:
            participant_count = 0

        confidence = self._compute_confidence(
            event_count=ep.event_count,
            temporal_start=ep.temporal_start,
            temporal_end=ep.temporal_end,
            participant_count=participant_count,
            cohesion=ep.cohesion_score,
            location_purity=1.0 if ep.location_hint else 0.5,
        )

        # Update cohesion_score to reflect confidence
        return EpisodeCluster(
            cluster_id=ep.cluster_id,
            member_event_ids=ep.member_event_ids,
            member_contexts=ep.member_contexts,  # Issue 7.6: preserve contexts
            centroid_embedding_id=ep.centroid_embedding_id,
            dominant_sentiment=ep.dominant_sentiment,
            dominant_emotion=ep.dominant_emotion,
            aggregated_sentiment=ep.aggregated_sentiment,
            aggregated_salience=ep.aggregated_salience,
            dominant_location=ep.dominant_location,
            dominant_social_context=ep.dominant_social_context,
            temporal_start=ep.temporal_start,
            temporal_end=ep.temporal_end,
            location_hint=ep.location_hint,
            location_type=ep.location_type,  # GAP-002: preserve location category
            participants_json=ep.participants_json,
            activity_type=ep.activity_type,
            cohesion_score=confidence,
            title=ep.title,
            summary=ep.summary,
        )

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

        # Extract dominant emotion from most common across events
        emotion_counts: Dict[str, int] = {}
        for e in cluster_events:
            try:
                emotions = json.loads(e.event.emotions_json or "[]")
                for emotion in emotions:
                    if isinstance(emotion, str):
                        emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
                    elif isinstance(emotion, dict):
                        label = emotion.get("label", emotion.get("emotion", ""))
                        if label:
                            emotion_counts[label] = emotion_counts.get(label, 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass
        dominant_emotion = max(emotion_counts, key=emotion_counts.get) if emotion_counts else ""

        # Extract most common location
        location_counts: Dict[str, int] = {}
        for e in cluster_events:
            loc = e.event.location_name
            if loc:
                location_counts[loc] = location_counts.get(loc, 0) + 1
        location_hint = max(location_counts, key=location_counts.get) if location_counts else None

        # GAP-002: Extract most common location type
        location_type_counts: Dict[str, int] = {}
        for e in cluster_events:
            loc_type = e.event.location_type
            if loc_type:
                location_type_counts[loc_type] = location_type_counts.get(loc_type, 0) + 1
        location_type = (
            max(location_type_counts, key=location_type_counts.get)
            if location_type_counts
            else None
        )

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

        # Extract most common activity type
        activity_counts: Dict[str, int] = {}
        for e in cluster_events:
            act = e.event.activity_type
            if act:
                activity_counts[act] = activity_counts.get(act, 0) + 1
        activity_type = max(activity_counts, key=activity_counts.get) if activity_counts else ""

        # Extract most common UltraBERT activity type (Issue 0060)
        # This gives us better granularity (12 types vs 7 legacy types)
        ultrabert_counts: Dict[str, int] = {}
        for e in cluster_events:
            act_ultra = e.event.activity_type_ultrabert
            if act_ultra:
                ultrabert_counts[act_ultra] = ultrabert_counts.get(act_ultra, 0) + 1
        activity_type_ultrabert = (
            max(ultrabert_counts, key=ultrabert_counts.get) if ultrabert_counts else ""
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

        return EpisodeCluster(
            cluster_id=cluster_id,
            member_event_ids=list(member_ids),
            member_contexts=member_contexts,  # Issue 7.6
            centroid_embedding_id=None,  # Will be set by R6/R7 when persisted
            dominant_sentiment=dominant_sentiment,
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
        """Generate a summary from event texts."""
        # Collect all event texts
        texts = []
        for e in cluster_events:
            text = getattr(e.event, "text", "") or ""
            if text:
                texts.append(text.strip())

        if not texts:
            return ""

        # For now, concatenate first few events (proper LLM summarization TODO)
        if len(texts) == 1:
            return texts[0]
        elif len(texts) <= 3:
            return " | ".join(texts)
        else:
            # Show first 2 and last 1 with count
            return f"{texts[0]} | {texts[1]} | ... ({len(texts)} events) | {texts[-1]}"

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

        location_counts: Dict[str, int] = {}
        for c in contexts:
            loc = c.location_type or c.location_name
            if loc:
                location_counts[loc] = location_counts.get(loc, 0) + 1
        dominant_location = (
            max(location_counts, key=location_counts.get) if location_counts else None
        )

        social_counts: Dict[str, int] = {}
        for c in contexts:
            if c.social_context:
                social_counts[c.social_context] = social_counts.get(c.social_context, 0) + 1
        dominant_social_context = (
            max(social_counts, key=social_counts.get) if social_counts else None
        )

        return aggregated_sentiment, aggregated_salience, dominant_location, dominant_social_context

    def _update_event_states(
        self,
        events: List["P03EventState"],
        clustering_results: List[Union[ClusteringResult, HDBSCANClusteringResult]],
        noise_ids: List[str],
    ) -> None:
        """
        Update P03EventState with cluster assignments.

        Args:
            events: Original event states to update
            clustering_results: Results from DBSCAN or HDBSCAN
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

    async def _track_quality_and_adapt(
        self,
        ctx: "P03RunnerContext",
        space_id: str,
        candidates: List[EpisodeCandidate],
        noise_ids: List[str],
        params: DBSCANParams,
    ) -> Optional[ClusterQualityMetrics]:
        """
        Track cluster quality and trigger adaptive parameter learning.

        Args:
            ctx: Runner context
            space_id: Space ID for per-space learning
            candidates: Episode candidates from clustering
            noise_ids: Event IDs marked as noise
            params: Current DBSCAN parameters

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

        # Calculate batch silhouette score (average of cohesion scores as approximation)
        batch_silhouette = (
            sum(c.cohesion_score for c in candidates) / cluster_count if cluster_count > 0 else 0.0
        )

        # Create a simple object that matches R2OutputProtocol
        class R2OutputSimple:
            def __init__(self, sil: float, clusters: int, noise: int):
                self.batch_silhouette_score = sil
                self.cluster_count = clusters
                self.noise_count = noise

        r2_output = R2OutputSimple(batch_silhouette, cluster_count, noise_count)
        metrics = self._quality_tracker.compute_from_r2_output(
            space_id=space_id,
            r2_output=r2_output,
        )

        # Compute avg_cluster_size from candidates (not in ClusterQualityMetrics)
        avg_cluster_size = (
            sum(len(c.event_ids) for c in candidates) / cluster_count if cluster_count > 0 else 0.0
        )

        # Trigger adaptive eps learning
        if self._eps_adjuster and self.config.enable_adaptive_eps:
            eps_result = self._eps_adjuster.adjust(
                current_eps=params.eps,
                silhouette_score=metrics.silhouette_score,
                avg_cluster_size=avg_cluster_size,
                singleton_rate=metrics.singleton_rate,
                total_clusters_formed=metrics.total_clusters,
            )

            if eps_result.adjusted and hasattr(ctx.syscalls, "set_learned_param"):
                try:
                    await ctx.syscalls.set_learned_param(
                        space_id=space_id,
                        param_key="dbscan_eps",
                        param_value=eps_result.new_eps,
                    )
                    logger.info(
                        "R2: Adjusted eps",
                        extra={
                            "space_id": space_id,
                            "old_eps": params.eps,
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
                        param_key="dbscan_min_samples",
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
