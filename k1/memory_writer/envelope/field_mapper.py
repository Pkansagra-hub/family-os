"""
FieldMapper -- Map MemoryAtom → K0 envelope body dict.

34 direct field mappings + 7 derived observation fields.
All transformations are deterministic. No LLM, no I/O.

K0 gap fixes (§5.9):
  G1: sentiment_score from sentiment_label (SENTIMENT_TO_SCORE)
  G2: dominant_emotion from emotion_tags[0]
  G3: dominant_emotions_json from emotion_tags with confidence
  G4: affect_valence from affect.valence (flattened)
  G5: geohash_6 from PlaceResolver.resolve_with_geohash()
  G6: place_id from PlaceResolver.resolve_with_geohash()
  G8: num_participants from len(participants)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from k1.memory_writer.config import MWConfig
from k1.memory_writer.place_resolver import PlaceResolver
from k1.memory_writer.types import Affect, ExtractionContext, MemoryAtom, Narrative


class FieldMapper:
    """Map MemoryAtom → K0 envelope body dict.

    34 direct field mappings + 7 derived observation fields.
    All transformations are deterministic. No LLM, no I/O.
    """

    # G1: Same mapping as k0/runtime/ultrabert_adapter.py SENTIMENT_TO_VALENCE
    SENTIMENT_TO_SCORE: Dict[str, float] = {
        "very_negative": -0.9,
        "negative": -0.5,
        "neutral": 0.0,
        "positive": 0.5,
        "very_positive": 0.9,
    }

    __slots__ = ("_place_resolver", "_config")

    def __init__(self, place_resolver: PlaceResolver, config: MWConfig) -> None:
        self._place_resolver = place_resolver
        self._config = config

    def map_atom_to_body(
        self,
        atom: MemoryAtom,
        context: ExtractionContext,
        trace_id: str,
    ) -> dict:
        """Convert MemoryAtom → K0-compatible body dict.

        Returns a plain dict ready for JSON serialization.
        All frozen dataclass fields are unpacked to plain dicts.
        """
        # Resolve place_id and geohash_6 (G5/G6)
        place_id, geohash_6 = self._place_resolver.resolve_with_geohash(
            atom.location_name,
            self._config.known_location_geohashes,
        )

        body: dict = {
            # --- Core content ---
            "text": atom.text,
            "operation": "UPSERT",
            "topics": list(atom.topics),
            "categories": list(atom.categories) if atom.categories else [],
            "activity_type": atom.activity_type.value if atom.activity_type else None,
            # --- Participants (already resolved to person_ids) ---
            "participants": list(atom.participants) if atom.participants else [],
            "participant_relationships": [],  # Phase 2 does not extract relationships
            # --- Location ---
            "location_name": atom.location_name,
            "location_type": atom.location_type.value if atom.location_type else None,
            "place_id": place_id,  # G6
            # --- Emotion ---
            "sentiment_label": atom.sentiment_label.value if atom.sentiment_label else "neutral",
            "emotion_tags": list(atom.emotion_tags) if atom.emotion_tags else [],
            "affect": self._serialize_affect(atom.affect),
            # --- Narrative ---
            "narrative": self._serialize_narrative(atom.narrative),
            # --- Temporal ---
            "temporal": self._build_temporal(context),
            "temporal_links": self._serialize_temporal_links(atom.temporal_links),
            "temporal_orientation": (
                atom.temporal_orientation.value if atom.temporal_orientation else "PAST"
            ),
            "conversation_anchor_ms": atom.conversation_anchor_ms,
            # --- Social ---
            "social_context": atom.social_context.value if atom.social_context else None,
            "social_intimacy": atom.social_intimacy.value if atom.social_intimacy else None,
            # --- Cognitive dimensions ---
            "source_type": atom.source_type.value if atom.source_type else "user_stated",
            "novelty": atom.novelty.value if atom.novelty else "EXPECTED",
            "elaboration_depth": (
                atom.elaboration_depth.value if atom.elaboration_depth else "MENTION"
            ),
            "intent_type": atom.intent_type.value if atom.intent_type else None,
            "identity_domains": list(atom.identity_domains) if atom.identity_domains else [],
            # --- Confidence + metadata ---
            "confidence": atom.confidence,
            "session_id": atom.session_id,
            "conversation_turn": atom.conversation_turn,
            "language": atom.language or "en",
            "cognitive_trace_id": trace_id,
            "embedding_text": None,  # K0 P02 computes embeddings, not K1
            # --- v2.2 correction signals ---
            "correction_signal": atom.correction_signal,
            "contradiction_signal": atom.contradiction_signal,
            "supersedes_concept": atom.supersedes_concept,
            "correction_source": atom.correction_source,
            "session_context_id": atom.session_context_id,
            # --- K0-required derived fields (gaps G1-G8) ---
            "sentiment_score": self.SENTIMENT_TO_SCORE.get(
                atom.sentiment_label.value if atom.sentiment_label else "neutral",
                0.0,
            ),  # G1
            "dominant_emotion": (atom.emotion_tags[0] if atom.emotion_tags else "neutral"),  # G2
            "dominant_emotions_json": [
                {"emotion": e, "confidence": 0.8} for e in (atom.emotion_tags or [])[:5]
            ],  # G3
            "affect_valence": atom.affect.valence if atom.affect else 0.0,  # G4
            "geohash_6": geohash_6,  # G5
            "num_participants": len(atom.participants) if atom.participants else 0,  # G8
            # --- Event time ---
            "event_time_utc": self._resolve_event_time(context),
        }

        return body

    @staticmethod
    def _serialize_affect(affect: Optional[Affect]) -> Optional[dict]:
        if affect is None:
            return None
        return {
            "valence": affect.valence,
            "arousal": affect.arousal,
            "dominance": affect.dominance,
        }

    @staticmethod
    def _serialize_narrative(narrative: Optional[Narrative]) -> Optional[dict]:
        if narrative is None:
            return None
        return {
            "arc_label": narrative.thread_id,
            "arc_position": (
                narrative.arc_position.value if narrative.arc_position else "EXPOSITION"
            ),
            "arc_salience": 0.5,  # Default; LLM does not score salience
        }

    @staticmethod
    def _serialize_temporal_links(links: tuple) -> list:
        return [
            {
                "mentioned_time": link.mentioned_time,
                "resolved_epoch_ms": link.resolved_epoch_ms,
                "uncertainty_window_ms": link.uncertainty_window_ms,
                "link_type": link.link_type,
                "confidence": link.confidence,
            }
            for link in (links or ())
        ]

    def _build_temporal(self, context: ExtractionContext) -> Optional[dict]:
        """Build temporal object from ExtractionContext.

        day_of_week and time_of_day derived from turn_timestamp_ms.
        """
        ts = context.turn_timestamp_ms
        if not ts or ts <= 0:
            return None
        dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
        return {
            "day_of_week": dt.strftime("%A"),
            "time_of_day": self._time_of_day(dt.hour),
            "is_recurring": False,  # MW does not detect recurrence
        }

    @staticmethod
    def _time_of_day(hour: int) -> str:
        if hour < 6:
            return "night"
        if hour < 12:
            return "morning"
        if hour < 18:
            return "afternoon"
        return "evening"

    @staticmethod
    def _resolve_event_time(context: ExtractionContext) -> str:
        """ISO 8601 UTC from turn_timestamp_ms. Fallback: now_utc()."""
        ts = context.turn_timestamp_ms
        if ts and ts > 0:
            dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
        else:
            dt = datetime.now(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
