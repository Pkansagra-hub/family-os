"""
DedupMetadataPopulator — Deduplication metadata population for R6.

Populates deduplication-related metadata fields on staged event updates
from DuplicateDetector results (M19).

Issue: 5.1.3
Spec Reference:
    - Dossier §4.7.2 (Deduplication Metadata)
    - Dossier §7.4.2 (M19 DuplicateDetector)
    - M5_EXECUTION.md Issue 5.1.3

Metadata Fields:
    - near_duplicates_json: JSON array of near-duplicate entries
    - novelty_score: Computed novelty score [0, 1]
    - episode_cluster_id: Cluster assignment from R2
    - novelty_bonuses_json: Breakdown of novelty bonuses/penalties

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from k0.modules.consolidation.algorithms.duplicate_detector import (
    DuplicationResult,
    NoveltyBonuses,
)
from k0.pipelines.p03.event_state import P03EventState
from k0.pipelines.p03.phase_outputs import DedupMerge

# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class NearDuplicateEntry:
    """
    Single entry in the near_duplicates_json array.

    Captures all relevant information about a near-duplicate detection.

    Attributes:
        event_id: ID of the near-duplicate event
        hamming_distance: SimHash hamming distance (0-64, None if embedding-only)
        embedding_similarity: Cosine similarity between embeddings [0, 1]
        detection_stage: How the duplicate was detected ("SIMHASH", "EMBEDDING", "TWO_STAGE")
    """

    event_id: str
    hamming_distance: Optional[int]
    embedding_similarity: float
    detection_stage: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "event_id": self.event_id,
            "hamming_distance": self.hamming_distance,
            "embedding_similarity": round(self.embedding_similarity, 4),
            "detection_stage": self.detection_stage,
        }


@dataclass
class DedupMetadata:
    """
    Complete deduplication metadata for an event.

    This is the output from DedupMetadataPopulator that contains
    all dedup-related fields for staging.

    Attributes:
        event_id: The event this metadata belongs to
        near_duplicates_json: JSON array of NearDuplicateEntry dicts
        novelty_score: Final novelty score [0, 1]
        episode_cluster_id: Cluster assignment from R2 (None for noise/singleton)
        novelty_bonuses_json: JSON object with bonus breakdown
        is_duplicate: Whether this event is a duplicate
        duplicate_of: Canonical event ID if this is a duplicate
    """

    event_id: str
    near_duplicates_json: str = "[]"
    novelty_score: float = 1.0
    episode_cluster_id: Optional[str] = None
    novelty_bonuses_json: str = "{}"
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate JSON fields."""
        # Ensure valid JSON
        try:
            json.loads(self.near_duplicates_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid near_duplicates_json: {e}")

        try:
            json.loads(self.novelty_bonuses_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid novelty_bonuses_json: {e}")

        # Clamp novelty score
        self.novelty_score = max(0.0, min(1.0, self.novelty_score))


# =============================================================================
# DedupMetadataPopulator Class
# =============================================================================


class DedupMetadataPopulator:
    """
    Populates deduplication metadata from DuplicateDetector results.

    Combines data from:
    - DuplicationResult (from M19 DuplicateDetector)
    - P03EventState (clustering, dedup fields)
    - DedupMerge (from phase_outputs if available)

    Usage:
        populator = DedupMetadataPopulator()

        # From DuplicationResult
        metadata = populator.from_duplication_result(event_state, dedup_result)

        # From event state only (when result not available)
        metadata = populator.from_event_state(event_state)

        # Build near_duplicates_json manually
        json_str = populator.build_near_duplicates_json(entries)
    """

    # Default novelty score when no dedup result available
    DEFAULT_NOVELTY_SCORE = 1.0

    def from_duplication_result(
        self,
        event_state: P03EventState,
        dedup_result: DuplicationResult,
        near_duplicate_details: Optional[List[NearDuplicateEntry]] = None,
    ) -> DedupMetadata:
        """
        Create DedupMetadata from a DuplicationResult.

        Args:
            event_state: P03EventState with R2 clustering info
            dedup_result: DuplicationResult from M19 DuplicateDetector
            near_duplicate_details: Optional pre-built entries with full details

        Returns:
            DedupMetadata with all fields populated
        """
        # Build near duplicates JSON
        if near_duplicate_details:
            near_duplicates_json = self.build_near_duplicates_json(near_duplicate_details)
        else:
            # Build from dedup_result.near_duplicates (event IDs only)
            near_duplicates_json = self._build_near_duplicates_from_ids(
                near_duplicate_ids=dedup_result.near_duplicates,
                match_method=dedup_result.match_method,
                max_similarity=dedup_result.max_similarity,
            )

        # Build bonuses JSON
        novelty_bonuses_json = self._build_bonuses_json(dedup_result.bonuses)

        return DedupMetadata(
            event_id=event_state.event_id,
            near_duplicates_json=near_duplicates_json,
            novelty_score=dedup_result.novelty_score,
            episode_cluster_id=event_state.cluster_id,
            novelty_bonuses_json=novelty_bonuses_json,
            is_duplicate=dedup_result.is_duplicate,
            duplicate_of=dedup_result.duplicate_of,
        )

    def from_event_state(
        self,
        event_state: P03EventState,
        dedup_merges: Optional[List[DedupMerge]] = None,
    ) -> DedupMetadata:
        """
        Create DedupMetadata from P03EventState only.

        Use this when DuplicationResult is not available (e.g., first occurrence
        or processing resumed from checkpoint).

        Args:
            event_state: P03EventState with dedup fields populated
            dedup_merges: Optional list of DedupMerge from phase_outputs

        Returns:
            DedupMetadata with fields from event state
        """
        near_duplicates_json = "[]"
        novelty_bonuses_json = "{}"

        # If we have dedup_merges, find any that reference this event
        if dedup_merges:
            related_merges = [
                m
                for m in dedup_merges
                if m.duplicate_id == event_state.event_id or m.canonical_id == event_state.event_id
            ]

            if related_merges:
                entries = [
                    NearDuplicateEntry(
                        event_id=(
                            m.canonical_id
                            if m.duplicate_id == event_state.event_id
                            else m.duplicate_id
                        ),
                        hamming_distance=m.hamming_distance,
                        embedding_similarity=m.merge_confidence,
                        detection_stage="SIMHASH" if m.hamming_distance <= 3 else "TWO_STAGE",
                    )
                    for m in related_merges
                ]
                near_duplicates_json = self.build_near_duplicates_json(entries)

        # Use novelty_factor from event state as novelty_score
        novelty_score = (
            event_state.novelty_factor
            if event_state.novelty_factor > 0
            else self.DEFAULT_NOVELTY_SCORE
        )

        return DedupMetadata(
            event_id=event_state.event_id,
            near_duplicates_json=near_duplicates_json,
            novelty_score=novelty_score,
            episode_cluster_id=event_state.cluster_id,
            novelty_bonuses_json=novelty_bonuses_json,
            is_duplicate=event_state.is_duplicate,
            duplicate_of=event_state.duplicate_of_id,
        )

    def build_near_duplicates_json(
        self,
        entries: List[NearDuplicateEntry],
    ) -> str:
        """
        Build JSON array from NearDuplicateEntry list.

        Args:
            entries: List of NearDuplicateEntry objects

        Returns:
            JSON array string
        """
        return json.dumps([e.to_dict() for e in entries], separators=(",", ":"))

    def _build_near_duplicates_from_ids(
        self,
        near_duplicate_ids: List[str],
        match_method: str,
        max_similarity: float,
    ) -> str:
        """
        Build near_duplicates_json from event IDs only.

        When we only have event IDs without full details, we use the match_method
        and max_similarity from the overall result.

        Args:
            near_duplicate_ids: List of near-duplicate event IDs
            match_method: Detection method from DuplicationResult
            max_similarity: Maximum similarity from DuplicationResult

        Returns:
            JSON array string
        """
        if not near_duplicate_ids:
            return "[]"

        # Map match_method to detection_stage
        detection_stage = self._normalize_detection_stage(match_method)

        entries = []
        for event_id in near_duplicate_ids:
            entries.append(
                {
                    "event_id": event_id,
                    "hamming_distance": None,  # Unknown for individual matches
                    "embedding_similarity": round(max_similarity, 4),
                    "detection_stage": detection_stage,
                }
            )

        return json.dumps(entries, separators=(",", ":"))

    def _build_bonuses_json(self, bonuses: NoveltyBonuses) -> str:
        """
        Build JSON object from NoveltyBonuses.

        Args:
            bonuses: NoveltyBonuses from DuplicationResult

        Returns:
            JSON object string with bonus breakdown
        """
        return json.dumps(
            {
                "first_occurrence": round(bonuses.first_occurrence, 4),
                "milestone": round(bonuses.milestone, 4),
                "rare_pattern": round(bonuses.rare_pattern, 4),
                "temporal_anomaly": round(bonuses.temporal_anomaly, 4),
                "routine_penalty": round(bonuses.routine_penalty, 4),
                "total_bonus": round(bonuses.total_bonus, 4),
            },
            separators=(",", ":"),
        )

    def _normalize_detection_stage(self, match_method: str) -> str:
        """
        Normalize match_method to detection_stage enum.

        Args:
            match_method: Raw match method from DuplicationResult

        Returns:
            One of "SIMHASH", "EMBEDDING", "TWO_STAGE"
        """
        method_upper = match_method.upper()

        if "SIMHASH" in method_upper:
            return "SIMHASH"
        elif "EMBEDDING" in method_upper:
            return "EMBEDDING"
        elif "TWO_STAGE" in method_upper or "TWOSTAGE" in method_upper:
            return "TWO_STAGE"
        elif method_upper == "":
            return "UNKNOWN"
        else:
            return "TWO_STAGE"  # Default to two-stage for unknown methods


# =============================================================================
# Utility Functions
# =============================================================================


def create_near_duplicate_entry(
    event_id: str,
    hamming_distance: Optional[int] = None,
    embedding_similarity: float = 0.0,
    detection_stage: str = "TWO_STAGE",
) -> NearDuplicateEntry:
    """
    Factory function to create a NearDuplicateEntry.

    Args:
        event_id: ID of the near-duplicate event
        hamming_distance: SimHash hamming distance (optional)
        embedding_similarity: Cosine similarity
        detection_stage: Detection method

    Returns:
        NearDuplicateEntry instance
    """
    return NearDuplicateEntry(
        event_id=event_id,
        hamming_distance=hamming_distance,
        embedding_similarity=embedding_similarity,
        detection_stage=detection_stage,
    )


def parse_near_duplicates_json(json_str: str) -> List[NearDuplicateEntry]:
    """
    Parse near_duplicates_json into NearDuplicateEntry list.

    Args:
        json_str: JSON array string

    Returns:
        List of NearDuplicateEntry objects
    """
    data = json.loads(json_str)
    return [
        NearDuplicateEntry(
            event_id=item["event_id"],
            hamming_distance=item.get("hamming_distance"),
            embedding_similarity=item.get("embedding_similarity", 0.0),
            detection_stage=item.get("detection_stage", "UNKNOWN"),
        )
        for item in data
    ]


def parse_novelty_bonuses_json(json_str: str) -> Dict[str, float]:
    """
    Parse novelty_bonuses_json into dict.

    Args:
        json_str: JSON object string

    Returns:
        Dict with bonus values
    """
    return json.loads(json_str)
