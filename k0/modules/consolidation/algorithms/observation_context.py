"""
ObservationContext - Holistic context snapshot for memory observations.

This dataclass captures the full context of a memory observation for
recording to st_observations. It flows through P03 pipeline and is
used by ObservationRecorder to persist observation records.

Context Categories:
- Temporal: When it happened, time-of-day patterns
- Emotional: Sentiment, affect, dominant emotion
- Salience: Importance, novelty scores
- Modality: How user communicated (voice/chat/etc)
- Physical: Location context
- Social: Who was present, social setting

Pipeline Scope: P03 Consolidation (WRITE)
Used by: ObservationRecorder, Truth Writers

Spec Reference: docs/plans/temporal_fix.md Issue 7.2
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from k0.pipelines.p03.event_state import P03EventState


@dataclass
class ObservationContext:
    """
    Full context snapshot for a memory observation.

    Captures WHEN and WITH WHAT CONTEXT a memory was observed.
    All fields except observed_at are optional to support graceful
    degradation when source event lacks context.

    Factory Methods:
        from_event(): Create from P03EventState (full context)
        from_timestamp(): Create from raw timestamp (minimal context)

    Usage:
        # From P03 event (full context)
        ctx = ObservationContext.from_event(event)

        # Minimal context (e.g., backfill)
        ctx = ObservationContext.from_timestamp(1704067200000)

        # With observation type
        ctx = ObservationContext.from_event(event)
        ctx.observation_type = "FIRST_SEEN"
    """

    # =========================================================================
    # Temporal Context (REQUIRED: observed_at)
    # =========================================================================

    observed_at: int  # REQUIRED: When observation happened (Unix ms)

    # Temporal metadata (optional)
    anchor_time_utc: Optional[int] = None  # For prospective: when user spoke
    original_temporal_expr: Optional[str] = None  # "next week", "tomorrow"
    time_of_day_bucket: Optional[str] = None  # MORNING, AFTERNOON, EVENING, NIGHT
    circadian_slot: Optional[str] = None  # WAKE, ACTIVE, WIND_DOWN, SLEEP
    is_weekend: Optional[bool] = None
    day_of_week: Optional[str] = None  # Monday, Tuesday, etc.

    # =========================================================================
    # Emotional Context
    # =========================================================================

    sentiment_score: Optional[float] = None  # 0.0 to 1.0
    sentiment_label: Optional[str] = None  # negative, neutral, positive
    affect_valence: Optional[float] = None  # -1.0 to +1.0
    affect_arousal: Optional[float] = None  # 0.0 to 1.0
    dominant_emotion: Optional[str] = None  # First from emotions array
    dominant_emotions_json: Optional[str] = None  # Full emotions array JSON

    # =========================================================================
    # Intent Context
    # =========================================================================

    intent_ultrabert: Optional[str] = None  # 8-type intent classification
    intent_confidence: Optional[float] = None  # Confidence in intent classification

    # =========================================================================
    # Salience Context
    # =========================================================================

    salience_score: Optional[float] = None  # 0.0 to 1.0
    salience_band: Optional[str] = None  # HIGH, MED, LOW
    novelty_score: Optional[float] = None  # 0.0 to 1.0

    # =========================================================================
    # Modality Context
    # =========================================================================

    ingress_channel: Optional[str] = None  # voice, chat, api
    ingress_category: Optional[str] = None  # UltraBERT 12-class: DIARY, TASK, HEALTH, etc.
    ingress_source: Optional[str] = None  # Concrete origin app
    device_kind: Optional[str] = None  # phone, desktop, tablet, speaker

    # =========================================================================
    # Physical Context
    # =========================================================================

    location_name: Optional[str] = None  # Human-readable location
    location_type: Optional[str] = None  # home, work, transit, etc.
    geohash_6: Optional[str] = None  # 6-char geohash for clustering

    # =========================================================================
    # Social Context
    # =========================================================================

    social_context: Optional[str] = None  # solo, family, work, friends
    social_intimacy: Optional[str] = None  # Intimacy level
    is_solo_event: Optional[bool] = None  # True if user was alone
    num_participants: Optional[int] = None  # Number of participants

    # =========================================================================
    # Classification
    # =========================================================================

    observation_type: str = "REINFORCEMENT"  # FIRST_SEEN or REINFORCEMENT
    confidence: float = 1.0  # Confidence in observation [0, 1]

    # =========================================================================
    # Provenance
    # =========================================================================

    source_event_id: Optional[str] = None  # st_hipp_events.event_id (optional)
    consolidation_cycle_id: Optional[str] = None  # P03 cycle ID

    # =========================================================================
    # Factory Methods
    # =========================================================================

    @classmethod
    def from_event(cls, event: "P03EventState") -> "ObservationContext":
        """
        Create context from P03EventState.

        Extracts all available context fields from the event.
        Uses getattr for optional fields that may not exist in older
        P03EventState versions (graceful degradation).

        Args:
            event: P03EventState with event data

        Returns:
            ObservationContext with all available context
        """
        return cls(
            # Temporal
            observed_at=event.timestamp,
            time_of_day_bucket=getattr(event, "time_of_day_bucket", None),
            circadian_slot=getattr(event, "circadian_slot", None),
            is_weekend=getattr(event, "is_weekend", None),
            day_of_week=getattr(event, "day_of_week", None),
            # Emotional
            sentiment_score=getattr(event, "sentiment_score", None),
            sentiment_label=getattr(event, "sentiment_label", None),
            affect_valence=getattr(event, "affect_valence", None),
            affect_arousal=getattr(event, "affect_arousal", None),
            dominant_emotion=cls._extract_first_emotion(getattr(event, "emotions_json", None)),
            dominant_emotions_json=getattr(event, "emotions_json", None),
            # Intent
            intent_ultrabert=getattr(event, "intent_ultrabert", None),
            intent_confidence=getattr(event, "intent_confidence", None),
            # Salience
            salience_score=getattr(event, "salience_score", None),
            salience_band=getattr(event, "salience_band", None),
            novelty_score=getattr(event, "novelty_score", None),
            # Modality
            ingress_channel=getattr(event, "ingress_channel", None),
            ingress_category=getattr(event, "activity_type_ultrabert", None),
            ingress_source=getattr(event, "ingress_source", None),
            device_kind=getattr(event, "device_kind", None),
            # Physical
            location_name=getattr(event, "location_name", None),
            location_type=getattr(event, "location_type", None),
            geohash_6=getattr(event, "geohash_6", None),
            # Social
            social_context=getattr(event, "social_context", None),
            social_intimacy=getattr(event, "social_intimacy", None),
            is_solo_event=getattr(event, "is_solo_event", None),
            num_participants=getattr(event, "num_participants", None),
            # Provenance
            source_event_id=event.event_id,
            observation_type="REINFORCEMENT",
            confidence=1.0,
        )

    @classmethod
    def from_timestamp(cls, timestamp_ms: int) -> "ObservationContext":
        """
        Create minimal context from raw timestamp.

        Used for backfill operations or when full event context
        is not available.

        Args:
            timestamp_ms: Observation timestamp in Unix milliseconds

        Returns:
            ObservationContext with only observed_at set
        """
        return cls(observed_at=timestamp_ms)

    @classmethod
    def from_episode_cluster(
        cls,
        cluster: Any,  # EpisodeCluster
        event_id: Optional[str] = None,
    ) -> "ObservationContext":
        """
        Create context from EpisodeCluster.

        Used when creating observations from aggregated episode data
        rather than individual events.

        Args:
            cluster: EpisodeCluster with aggregated data
            event_id: Optional source event ID

        Returns:
            ObservationContext with cluster-level context
        """
        return cls(
            observed_at=getattr(cluster, "temporal_start", 0),
            location_name=getattr(cluster, "location_hint", None),
            location_type=getattr(cluster, "location_type", None),
            sentiment_score=getattr(cluster, "dominant_sentiment", None),
            dominant_emotion=getattr(cluster, "dominant_emotion", None),
            source_event_id=event_id,
            observation_type="FIRST_SEEN",
            confidence=getattr(cluster, "cohesion_score", 1.0),
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    @staticmethod
    def _extract_first_emotion(emotions_json: Optional[str]) -> Optional[str]:
        """
        Extract first emotion from JSON array.

        Args:
            emotions_json: JSON array string like '["joy", "anticipation"]'

        Returns:
            First emotion string or None
        """
        if not emotions_json:
            return None
        try:
            emotions = json.loads(emotions_json)
            if isinstance(emotions, list) and emotions:
                return str(emotions[0])
            return None
        except (json.JSONDecodeError, IndexError, TypeError):
            return None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for debugging and serialization.

        Returns:
            Dictionary with all non-None fields
        """
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_db_row(self) -> Dict[str, Any]:
        """
        Convert to database row format for st_observations INSERT.

        Maps dataclass fields to database column names.
        Excludes None values for nullable columns.

        Returns:
            Dictionary ready for database INSERT
        """
        row: Dict[str, Any] = {
            "observed_at": self.observed_at,
            "observation_type": self.observation_type,
            "observation_weight": self.confidence,
        }

        # Add optional fields only if not None
        optional_mappings = {
            "anchor_time_utc": self.anchor_time_utc,
            "original_temporal_expr": self.original_temporal_expr,
            "time_of_day_bucket": self.time_of_day_bucket,
            "circadian_slot": self.circadian_slot,
            "is_weekend": self.is_weekend,
            "day_of_week": self.day_of_week,
            "sentiment_score": self.sentiment_score,
            "sentiment_label": self.sentiment_label,
            "affect_valence": self.affect_valence,
            "affect_arousal": self.affect_arousal,
            "dominant_emotion": self.dominant_emotion,
            "salience_score": self.salience_score,
            "salience_band": self.salience_band,
            "novelty_score": self.novelty_score,
            "ingress_channel": self.ingress_channel,
            "ingress_source": self.ingress_source,
            "device_kind": self.device_kind,
            "location_name": self.location_name,
            "location_type": self.location_type,
            "geohash_6": self.geohash_6,
            "social_context": self.social_context,
            "social_intimacy": self.social_intimacy,
            "is_solo_event": self.is_solo_event,
            "num_participants": self.num_participants,
            "source_event_id": self.source_event_id,
        }

        for col, val in optional_mappings.items():
            if val is not None:
                row[col] = val

        return row

    def with_type(self, observation_type: str) -> "ObservationContext":
        """
        Return copy with updated observation type.

        Args:
            observation_type: FIRST_SEEN or REINFORCEMENT

        Returns:
            New ObservationContext with updated type
        """
        from dataclasses import replace

        return replace(self, observation_type=observation_type)

    def with_provenance(
        self,
        source_event_id: Optional[str] = None,
        cycle_id: Optional[str] = None,
    ) -> "ObservationContext":
        """
        Return copy with updated provenance.

        Args:
            source_event_id: Source event ID
            cycle_id: Consolidation cycle ID

        Returns:
            New ObservationContext with updated provenance
        """
        from dataclasses import replace

        updates: Dict[str, Any] = {}
        if source_event_id is not None:
            updates["source_event_id"] = source_event_id
        if cycle_id is not None:
            updates["consolidation_cycle_id"] = cycle_id
        return replace(self, **updates)
