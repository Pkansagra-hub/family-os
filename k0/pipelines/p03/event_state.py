"""
P03EventState - Per-event state that accumulates enrichment through phases R0-R6.

This module implements the mutable dataclass that tracks each event's journey
through the consolidation pipeline. Unlike P03CycleContext (frozen), event
state is mutated as each phase adds enrichment data.

Spec Reference: docs/pipelines/P03_envelope_fields_discovery.md section 16.1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ReconciliationAction(Enum):
    """
    Possible reconciliation decisions for an event (R3).

    These determine what happens to the event in R6/R7:
    - PENDING: Not yet decided (initial state)
    - REINFORCE: Strengthen existing truth record (sim >= 0.85)
    - EXTEND: Add detail to existing record (0.60 <= sim < 0.85)
    - CREATE: Create new truth record (sim < 0.60, novelty >= 0.70)
    - EVOLVE: Version existing truth (schema/semantic change)
    - CONTRADICT: Conflicts with existing truth (flagged for P06 review)
    - PRUNE: Decay score below threshold, archive/tombstone
    - SKIP: Already processed, duplicate, or filtered out
    """

    PENDING = "PENDING"
    REINFORCE = "REINFORCE"
    EXTEND = "EXTEND"
    CREATE = "CREATE"
    EVOLVE = "EVOLVE"
    CONTRADICT = "CONTRADICT"
    PRUNE = "PRUNE"
    SKIP = "SKIP"


class PruneDecision(Enum):
    """
    Decay-based pruning decision (R3).

    - KEEP: Retain in active truth store
    - ARCHIVE: Move to cold storage (recoverable)
    - TOMBSTONE: Mark for deletion (soft delete)
    """

    KEEP = "KEEP"
    ARCHIVE = "ARCHIVE"
    TOMBSTONE = "TOMBSTONE"


@dataclass
class P03EventState:
    """
    Per-event state that is enriched as event flows through phases.

    Each event in the batch has one P03EventState instance.
    Fields are populated incrementally by different phases:
    - R0: event_id, hipp_event_id, content fields (from st_hipp_events)
    - R1: importance_score, factors, hebbian_updates
    - R2: cluster_id, cluster assignment
    - R3: reconciliation_action, similarity, dedup, decay
    - R6: staged write references
    - R7: write results

    Note: This is NOT frozen - it accumulates state through the pipeline.
    Use P03CycleContext for immutable batch-level metadata.

    Attributes:
        event_id: ULID identifying the event
        hipp_event_id: st_hipp_events primary key (may differ from event_id)
        content_text: Raw text content from P02
        content_type: Event type (CHAT/VOICE/CALENDAR/TRANSACTION)
        content_hash: SHA256 of content for exact dedup
        simhash_hex: 64-bit SimHash for fuzzy dedup
        timestamp: Event occurrence time (unix ms)
        channel_id: Source channel identifier
        embedding_id: Reference to st_vec (lazy load - no vector until needed)
        embedding_768: Materialized 768-dim embedding (None until loaded)
        sentiment_score: Sentiment analysis score [-1, 1]
        sentiment_label: Sentiment classification (positive/negative/neutral)
        emotions_json: JSON array of detected emotions
        intent_label: Detected intent classification
        ner_entities_json: JSON array of named entities
        temporal_expressions_json: JSON array of temporal expressions
        importance_score: Computed importance [0, 1] (R1)
        recency_factor: Recency contribution to importance
        affect_factor: Emotional intensity contribution
        social_factor: Social relevance contribution
        novelty_factor: Information novelty contribution
        importance_computed: Whether R1 has computed importance
        hebbian_updates: List of Hebbian edge updates from R1
        cluster_id: Episode cluster assignment (R2)
        cluster_label: DBSCAN label (-1 = noise)
        is_noise: Whether event is clustering noise
        centroid_distance: Distance to cluster centroid
        reconciliation_action: Decision for this event (R3)
        best_match_id: Matched truth record ID
        best_match_layer: Truth layer (st_epi, st_sem, etc.)
        similarity_score: Cosine similarity to best match
        confidence: Confidence in reconciliation decision
        reconciliation_reason: Human-readable explanation
        is_duplicate: Whether event is a duplicate
        duplicate_of_id: ID of canonical event if duplicate
        hamming_distance: SimHash hamming distance (0-64)
        decay_score: Current decay score [0, 1]
        lambda_decay: Decay rate parameter
        days_since_access: Days since last access
        access_count: Number of times accessed
        prune_decision: KEEP/ARCHIVE/TOMBSTONE
        expected_version: For optimistic locking (R6)
        version_conflict: Whether version conflict detected
        write_success: Whether R7 write succeeded
        write_error: Error message if write failed
        written_to_layer: Which truth layer was written
        written_record_id: ID of written record
    """

    # === IDENTIFICATION (R0 - from st_hipp_events) ===
    event_id: str
    hipp_event_id: str = ""

    # === CONTENT (R0 - from P02 pre-computation) ===
    content_text: str = ""
    content_type: str = ""
    content_hash: str = ""
    simhash_hex: str = ""
    timestamp: int = 0
    channel_id: str = ""

    # === PRE-COMPUTED NLP (R0 - from P02/UltraBERT) ===
    embedding_id: str = ""
    embedding_768: Optional[List[float]] = None
    sentiment_score: float = 0.0
    sentiment_label: str = "neutral"
    emotions_json: str = "[]"  # JSON array, not object
    intent_label: str = ""
    ner_entities_json: str = "[]"
    temporal_expressions_json: str = "[]"

    # === AFFECT & SALIENCE (R0 - from P02/UltraBERT) ===
    # Issue 1 Fix: These fields were missing, causing 55% of importance formula to be dead
    affect_valence: float = 0.0  # Emotional valence [-1, 1]
    affect_arousal: float = 0.0  # Emotional arousal [0, 1]
    salience_score: float = (
        0.0  # P02 computed salience [0, 1] (0.50×social + 0.40×affect + 0.10×recency)
    )

    # === SOCIAL CONTEXT (R0 - from st_hipp_events) ===
    # Used by R4 for social relationship extraction
    participants_json: str = "[]"  # JSON array of participant IDs
    num_participants: int = 0
    social_context: str = ""  # nuclear_family, solo, work, etc.
    social_intimacy: str = ""  # HIGH, LOW, etc.
    location_name: str = ""
    location_type: str = ""
    activity_type: str = (
        ""  # Legacy 7-type (meal/conversation/routine/milestone/social/work/unknown)
    )
    actor_id: str = ""  # SELF actor ID for relationship extraction

    # === TEMPORAL CONTEXT (R0 - Issue 7.6) ===
    # Time-of-day and circadian context for st_observations
    time_of_day_bucket: str = ""  # MORNING, AFTERNOON, EVENING, NIGHT
    circadian_slot: str = ""  # WAKE, ACTIVE, WIND_DOWN, SLEEP
    is_weekend: Optional[bool] = None
    day_of_week: str = ""  # Monday, Tuesday, etc.

    # === MODALITY CONTEXT (R0 - Issue 7.6) ===
    # How user communicated - for st_observations
    ingress_channel: str = ""  # voice, chat, api
    ingress_source: str = ""  # Concrete origin app
    device_kind: str = ""  # phone, desktop, tablet, speaker

    # === UltraBERT CLASSIFICATION (R0 - Issue 0060) ===
    # Full 12-type INGRESS classification for better episode inference
    # DIARY/TASK/HEALTH/FINANCE/RELATIONSHIP/WORK/META/MEMORY/PLANNING/CELEBRATION/CONCERN/GRATITUDE
    activity_type_ultrabert: str = ""
    activity_type_confidence: float = 0.0
    # Full 8-type INTENT classification
    # log_memory/query_memory/set_reminder/express_feeling/seek_advice/share_news/reflect/other
    intent_ultrabert: str = ""
    intent_confidence: float = 0.0
    # UltraBERT extracted relationship types (parent_of, spouse_of, friend_of, etc.)
    # Used by R4 for relationship type inference
    extracted_relations_json: str = "[]"

    # === IMPORTANCE SCORING (R1) ===
    importance_score: float = 0.0
    recency_factor: float = 0.0
    affect_factor: float = 0.0
    social_factor: float = 0.0
    novelty_factor: float = 0.0
    importance_computed: bool = False

    # === HEBBIAN UPDATES (R1) ===
    hebbian_updates: List[Dict[str, Any]] = field(default_factory=list)

    # === CLUSTERING (R2) ===
    cluster_id: Optional[str] = None
    cluster_label: int = -1
    is_noise: bool = False
    centroid_distance: float = 0.0

    # === EPISODE MATCHING (R2) - Issue 2 Fix ===
    # R2 now queries st_epi for existing episodes before clustering.
    # Events matching existing episodes get REINFORCE action instead of creating duplicates.
    episode_match_id: Optional[str] = None  # Matched existing episode ID from st_epi
    episode_match_similarity: float = 0.0  # Cosine similarity to matched episode [0, 1]
    episode_match_version: int = 0  # Version of matched episode (for optimistic locking)

    # === RECONCILIATION DECISION (R3) ===
    reconciliation_action: ReconciliationAction = ReconciliationAction.PENDING
    best_match_id: Optional[str] = None
    best_match_layer: Optional[str] = None
    similarity_score: float = 0.0
    confidence: float = 0.0
    reconciliation_reason: str = ""

    # === DEDUPLICATION (R3) ===
    is_duplicate: bool = False
    duplicate_of_id: Optional[str] = None
    hamming_distance: int = 64  # Max = 64 (no match)

    # === DECAY (R3) ===
    decay_score: float = 1.0
    lambda_decay: float = 0.01
    days_since_access: int = 0
    access_count: int = 0
    prune_decision: PruneDecision = PruneDecision.KEEP

    # === VERSION CONTROL (R6) ===
    expected_version: int = 0
    version_conflict: bool = False

    # === WRITE TRACKING (R7) ===
    write_success: bool = False
    write_error: Optional[str] = None
    written_to_layer: Optional[str] = None
    written_record_id: Optional[str] = None

    # === PHASE TRACKING (for checkpoint/resume) ===
    last_completed_phase: str = ""  # R0, R1, R2, R3, R6, R7

    # =========================================================================
    # Helper Methods (Phase Updates)
    # =========================================================================

    # Expected embedding dimension (UltraBERT 768-dim)
    EMBEDDING_DIM: int = 768

    def materialize_embedding(self, embedding: List[float]) -> None:
        """
        Load embedding vector when needed for similarity computation.

        Called lazily during R2/R3 when actual vector comparison is needed.
        Avoids loading all embeddings upfront for batch efficiency.

        Args:
            embedding: 768-dimensional embedding vector

        Raises:
            ValueError: If embedding dimension doesn't match expected (768)
        """
        if len(embedding) != self.EMBEDDING_DIM:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self.EMBEDDING_DIM}, "
                f"got {len(embedding)} for event {self.event_id}"
            )
        self.embedding_768 = embedding

    def clear_embedding(self) -> None:
        """
        Clear materialized embedding to free memory.

        Called after R3 completes to reduce envelope memory footprint.
        The embedding_id is retained for reference.
        """
        self.embedding_768 = None

    def set_importance(
        self,
        score: float,
        recency: float,
        affect: float,
        social: float,
        novelty: float,
    ) -> None:
        """
        Set importance score and contributing factors (R1).

        Args:
            score: Computed importance score [0, 1]
            recency: Recency factor contribution
            affect: Emotional intensity contribution
            social: Social relevance contribution
            novelty: Information novelty contribution
        """
        self.importance_score = score
        self.recency_factor = recency
        self.affect_factor = affect
        self.social_factor = social
        self.novelty_factor = novelty
        self.importance_computed = True

    def add_hebbian_update(
        self,
        source_entity_id: str,
        target_entity_id: str,
        old_weight: float,
        new_weight: float,
        update_type: str = "STRENGTHEN",
    ) -> None:
        """
        Record a Hebbian edge update (R1).

        Args:
            source_entity_id: Source KG entity
            target_entity_id: Target KG entity
            old_weight: Previous edge weight
            new_weight: Updated edge weight
            update_type: STRENGTHEN, WEAKEN, or CREATE
        """
        self.hebbian_updates.append(
            {
                "source_entity_id": source_entity_id,
                "target_entity_id": target_entity_id,
                "old_weight": old_weight,
                "new_weight": new_weight,
                "update_type": update_type,
            }
        )

    def assign_cluster(
        self,
        cluster_id: str,
        label: int,
        distance: float,
    ) -> None:
        """
        Assign event to episode cluster (R2).

        Args:
            cluster_id: ULID of the cluster
            label: DBSCAN cluster label (-1 = noise)
            distance: Distance to cluster centroid
        """
        self.cluster_id = cluster_id
        self.cluster_label = label
        self.is_noise = label == -1
        self.centroid_distance = distance

    def mark_as_noise(self) -> None:
        """Mark event as clustering noise (R2)."""
        self.cluster_id = None
        self.cluster_label = -1
        self.is_noise = True
        self.centroid_distance = 0.0

    def set_reconciliation(
        self,
        action: ReconciliationAction,
        match_id: Optional[str] = None,
        match_layer: Optional[str] = None,
        similarity: float = 0.0,
        confidence: float = 0.0,
        reason: str = "",
    ) -> None:
        """
        Set reconciliation decision (R3).

        Args:
            action: ReconciliationAction enum value
            match_id: ID of matched truth record (if applicable)
            match_layer: Truth layer of match (st_epi, st_sem, etc.)
            similarity: Cosine similarity to matched record
            confidence: Confidence score for decision
            reason: Human-readable explanation
        """
        self.reconciliation_action = action
        self.best_match_id = match_id
        self.best_match_layer = match_layer
        self.similarity_score = similarity
        self.confidence = confidence
        self.reconciliation_reason = reason

    def mark_duplicate(
        self,
        canonical_id: str,
        hamming_dist: int,
    ) -> None:
        """
        Mark event as duplicate of another event (R3).

        Args:
            canonical_id: ID of the canonical (kept) event
            hamming_dist: SimHash hamming distance (0-64)
        """
        self.is_duplicate = True
        self.duplicate_of_id = canonical_id
        self.hamming_distance = hamming_dist
        self.reconciliation_action = ReconciliationAction.SKIP
        self.reconciliation_reason = f"Duplicate of {canonical_id} (hamming={hamming_dist})"

    def set_decay(
        self,
        decay_score: float,
        lambda_decay: float,
        days_since: int,
        access_count: int,
        decision: PruneDecision,
    ) -> None:
        """
        Set decay state and pruning decision (R3).

        NOTE: This does NOT automatically set reconciliation_action.
        Decay/prune decisions are orthogonal to reconciliation.
        Call set_reconciliation() separately if needed.

        Args:
            decay_score: Current decay score [0, 1]
            lambda_decay: Decay rate parameter used in calculation
            days_since: Days since last access
            access_count: Total access count
            decision: PruneDecision (KEEP/ARCHIVE/TOMBSTONE)
        """
        self.decay_score = decay_score
        self.lambda_decay = lambda_decay
        self.days_since_access = days_since
        self.access_count = access_count
        self.prune_decision = decision
        # NOTE: reconciliation_action is NOT set here.
        # Decay decision is orthogonal - caller must explicitly
        # call set_reconciliation(PRUNE, ...) if decay triggers pruning.

    def set_version_conflict(self, expected: int) -> None:
        """
        Record version conflict for optimistic locking (R6).

        Args:
            expected: The expected version that was stale
        """
        self.expected_version = expected
        self.version_conflict = True

    def set_write_result(
        self,
        success: bool,
        layer: Optional[str] = None,
        record_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Record R7 write result.

        Args:
            success: Whether write succeeded
            layer: Target truth layer
            record_id: ID of written record
            error: Error message if failed
        """
        self.write_success = success
        self.written_to_layer = layer
        self.written_record_id = record_id
        self.write_error = error

    # =========================================================================
    # Utility Methods
    # =========================================================================

    # Actions that require processing in R6/R7
    _ACTIONABLE_STATES: frozenset = frozenset(
        {
            ReconciliationAction.REINFORCE,
            ReconciliationAction.EXTEND,
            ReconciliationAction.CREATE,
            ReconciliationAction.EVOLVE,
            ReconciliationAction.CONTRADICT,
            ReconciliationAction.PRUNE,
        }
    )

    def is_actionable(self) -> bool:
        """
        Check if event requires action in R6/R7.

        Actionable states: REINFORCE, EXTEND, CREATE, EVOLVE, CONTRADICT, PRUNE
        Non-actionable: PENDING, SKIP, or version_conflict=True
        """
        return self.reconciliation_action in self._ACTIONABLE_STATES and not self.version_conflict

    def needs_truth_write(self) -> bool:
        """Check if event needs a truth layer write."""
        return self.reconciliation_action in (
            ReconciliationAction.CREATE,
            ReconciliationAction.EXTEND,
            ReconciliationAction.EVOLVE,
        )

    def needs_reinforcement(self) -> bool:
        """Check if event reinforces existing truth."""
        return self.reconciliation_action == ReconciliationAction.REINFORCE

    def to_summary_dict(self) -> Dict[str, Any]:
        """
        Convert to summary dict for serialization.

        Returns minimal fields for checkpoint/logging (not full state).
        """
        return {
            "event_id": self.event_id,
            "reconciliation_action": self.reconciliation_action.value,
            "importance_score": self.importance_score,
            "cluster_id": self.cluster_id,
            "is_duplicate": self.is_duplicate,
            "write_success": self.write_success,
        }

    @classmethod
    def from_hipp_event(
        cls,
        event_id: str,
        hipp_event_id: str,
        content_text: str,
        content_type: str,
        content_hash: str,
        simhash_hex: str,
        timestamp: int,
        channel_id: str,
        embedding_id: str,
        sentiment_score: float = 0.0,
        sentiment_label: str = "neutral",
        emotions_json: str = "{}",
        intent_label: str = "",
        ner_entities_json: str = "[]",
        temporal_expressions_json: str = "[]",
    ) -> P03EventState:
        """
        Factory method to create event state from st_hipp_events row.

        Called during R0 to initialize event state from database.

        Args:
            event_id: ULID for the event
            hipp_event_id: Primary key in st_hipp_events
            content_text: Raw text content
            content_type: Event type classification
            content_hash: SHA256 hash of content
            simhash_hex: 64-bit SimHash hex string
            timestamp: Event occurrence time (unix ms)
            channel_id: Source channel
            embedding_id: Reference to st_vec record
            sentiment_score: Pre-computed sentiment [-1, 1]
            sentiment_label: Sentiment classification
            emotions_json: JSON array of emotions
            intent_label: Intent classification
            ner_entities_json: JSON array of NER entities
            temporal_expressions_json: JSON array of temporal expressions

        Returns:
            Initialized P03EventState
        """
        return cls(
            event_id=event_id,
            hipp_event_id=hipp_event_id,
            content_text=content_text,
            content_type=content_type,
            content_hash=content_hash,
            simhash_hex=simhash_hex,
            timestamp=timestamp,
            channel_id=channel_id,
            embedding_id=embedding_id,
            sentiment_score=sentiment_score,
            sentiment_label=sentiment_label,
            emotions_json=emotions_json,
            intent_label=intent_label,
            ner_entities_json=ner_entities_json,
            temporal_expressions_json=temporal_expressions_json,
        )
