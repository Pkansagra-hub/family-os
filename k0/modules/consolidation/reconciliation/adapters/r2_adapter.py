"""R2Adapter -- translate R2 phase objects to/from engine types (M9.8).

Bridges the gap between R2 EpisodicIntegrator's domain objects
(P03EventState, EpisodeCandidate, existing-episode dicts) and the
universal reconciliation engine's types (ReconciliationCandidate,
TruthRecord).

Two conversion paths:
  1. event_to_candidate  -- P03EventState -> ReconciliationCandidate  (Seam 1: REINFORCE)
  2. episode_to_candidate -- EpisodeCandidate -> ReconciliationCandidate (Seam 2: EXTEND)

Plus:
  existing_to_truth_record -- st_epi query dict -> TruthRecord
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from k0.modules.consolidation.types import K1SignalBundle, ReconciliationCandidate, TruthRecord

if TYPE_CHECKING:
    from k0.modules.consolidation.algorithms import EpisodeCandidate
    from k0.pipelines.p03.event_state import P03EventState

logger = logging.getLogger(__name__)

LAYER_ST_EPI = "st_epi"


def _safe_json_parse(raw: str, fallback: Any = None) -> Any:
    """Parse JSON string, returning fallback on failure."""
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return fallback


def _to_set(raw: Any) -> set:
    """Coerce list/set/string to a set."""
    if isinstance(raw, set):
        return raw
    if isinstance(raw, (list, tuple)):
        return set(raw)
    return set()


class R2Adapter:
    """Stateless adapter between R2 domain objects and engine types."""

    # -----------------------------------------------------------------
    # Seam 1: event -> candidate (pre-clustering REINFORCE path)
    # -----------------------------------------------------------------

    @staticmethod
    def event_to_candidate(
        event: P03EventState,
        cycle_id: str,
        space_id: str = "",
        tenant_id: str = "",
    ) -> ReconciliationCandidate:
        """Convert a P03EventState into a ReconciliationCandidate.

        Extracts structural metadata for the 11-feature identity scorer:
        topics, participants, focal, social_context, location,
        source_type, correction/contradiction signals.
        """
        topics = set()
        topic_raw = _safe_json_parse(getattr(event, "topics_json", "[]"), [])
        if isinstance(topic_raw, list):
            topics = {str(t) for t in topic_raw if t}

        participants = set()
        part_raw = _safe_json_parse(getattr(event, "participants_json", "[]"), [])
        if isinstance(part_raw, list):
            participants = {str(p) for p in part_raw if p}

        metadata: dict[str, Any] = {
            "topics": topics,
            "participants": participants,
            "focal": getattr(event, "focal_entity", "") or "",
            "social_context": getattr(event, "social_context", "") or "",
            "location": getattr(event, "location_name", "") or "",
            "source_type": getattr(event, "source_type", "") or "",
            "narrative_thread_id": getattr(event, "narrative_thread_id", "") or "",
        }

        return ReconciliationCandidate(
            candidate_id=event.event_id,
            layer=LAYER_ST_EPI,
            source_phase="R2",
            embedding=list(event.embedding_768) if event.embedding_768 is not None else None,
            metadata=metadata,
            k1_signals=K1SignalBundle(
                correction_signal=getattr(event, "correction_signal", False),
                contradiction_signal=getattr(event, "contradiction_signal", False),
            ),
            source_event_ids=(event.event_id,),
            cycle_id=cycle_id,
            tenant_id=tenant_id,
            space_id=space_id,
        )

    # -----------------------------------------------------------------
    # Seam 2: episode candidate -> candidate (post-clustering EXTEND path)
    # -----------------------------------------------------------------

    @staticmethod
    def episode_to_candidate(
        episode: EpisodeCandidate,
        cycle_id: str,
        space_id: str = "",
        tenant_id: str = "",
        event_lookup: dict[str, Any] | None = None,
    ) -> ReconciliationCandidate:
        """Convert an EpisodeCandidate into a ReconciliationCandidate.

        Aggregates metadata from member events when event_lookup is provided.
        """
        topics: set[str] = set()
        participants: set[str] = set()
        focal = ""
        social_context = ""
        location = ""
        narrative_thread_id = ""

        if event_lookup:
            thread_counts: dict[str, int] = {}
            for eid in episode.event_ids:
                ev = event_lookup.get(eid)
                if ev is None:
                    continue
                t_raw = _safe_json_parse(getattr(ev, "topics_json", "[]"), [])
                if isinstance(t_raw, list):
                    topics.update(str(t) for t in t_raw if t)
                p_raw = _safe_json_parse(getattr(ev, "participants_json", "[]"), [])
                if isinstance(p_raw, list):
                    participants.update(str(p) for p in p_raw if p)
                if not focal:
                    focal = getattr(ev, "focal_entity", "") or ""
                if not social_context:
                    social_context = getattr(ev, "social_context", "") or ""
                if not location:
                    location = getattr(ev, "location_name", "") or ""
                tid = getattr(ev, "narrative_thread_id", "") or ""
                if tid:
                    thread_counts[tid] = thread_counts.get(tid, 0) + 1
            if thread_counts:
                narrative_thread_id = max(thread_counts, key=lambda k: thread_counts[k])

        metadata: dict[str, Any] = {
            "topics": topics,
            "participants": participants,
            "focal": focal,
            "social_context": social_context,
            "location": location,
            "source_type": "",
            "narrative_thread_id": narrative_thread_id,
            "temporal_start": episode.temporal_start,
            "temporal_end": episode.temporal_end,
            "cluster_id": episode.cluster_id,
        }

        return ReconciliationCandidate(
            candidate_id=episode.cluster_id,
            layer=LAYER_ST_EPI,
            source_phase="R2",
            embedding=(
                list(episode.centroid_embedding) if episode.centroid_embedding is not None else None
            ),
            metadata=metadata,
            k1_signals=K1SignalBundle(),
            source_event_ids=tuple(episode.event_ids),
            cycle_id=cycle_id,
            tenant_id=tenant_id,
            space_id=space_id,
        )

    # -----------------------------------------------------------------
    # Existing episode dict -> TruthRecord (shared by both seams)
    # -----------------------------------------------------------------

    @staticmethod
    def existing_to_truth_record(episode_dict: dict[str, Any]) -> TruthRecord:
        """Convert a raw st_epi query dict to a TruthRecord.

        The dict is expected to have keys: episode_id, embedding (ndarray or list),
        version, narrative_thread_id, start_time_utc, end_time_utc, etc.
        """
        embedding = episode_dict.get("embedding")
        if embedding is not None:
            # numpy array -> list
            try:
                embedding = list(embedding)
            except (TypeError, ValueError):
                embedding = None

        metadata: dict[str, Any] = {
            "narrative_thread_id": episode_dict.get("narrative_thread_id", ""),
            "topics": set(),
            "participants": set(),
            "focal": "",
            "social_context": "",
            "location": episode_dict.get("primary_location", "") or "",
            "source_type": "",
            "start_time_utc": episode_dict.get("start_time_utc", 0),
            "end_time_utc": episode_dict.get("end_time_utc", 0),
        }

        return TruthRecord(
            record_id=episode_dict["episode_id"],
            layer=LAYER_ST_EPI,
            embedding=embedding,
            confidence=episode_dict.get("cluster_confidence", 0.5),
            version=episode_dict.get("version", 1),
            observation_count=episode_dict.get("source_event_count", 0),
            last_observed_ms=episode_dict.get("end_time_utc", 0),
            metadata=metadata,
        )
