"""
EpisodicCoherenceScore - Per-episode semantic coherence metric.

Replaces broken silhouette as the primary quality signal.
Computes coherence across 5 dimensions from ObservationContext members.

Research: M4-RSCH-04 equal_weight coherence rho=0.4556 post-correction.
Silhouette breaks post-correction (mean=-0.0329).

Coherence Dimensions:
    - narrative: fraction sharing dominant narrative_thread_id
    - social: fraction sharing dominant social_context
    - spatial: fraction sharing dominant location (geohash_6 or location_name)
    - temporal: 1 - normalized_temporal_spread (tighter = more coherent)
    - affective: 1 - normalized affect_valence stddev (similar affect = more coherent)

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# Default for dimensions with no data (uncertain)
NEUTRAL_FALLBACK = 0.5

# Maximum temporal spread to consider (24 hours in ms)
MAX_TEMPORAL_SPREAD_MS = 24 * 60 * 60 * 1000


@dataclass
class CoherenceDimensions:
    """Per-dimension coherence scores for an episode."""

    narrative: Optional[float] = None
    """Fraction sharing dominant narrative_thread_id. None if no thread data."""

    social: Optional[float] = None
    """Fraction sharing dominant social_context. None if no social data."""

    spatial: Optional[float] = None
    """Fraction sharing dominant location. None if no location data."""

    temporal: Optional[float] = None
    """1 - normalized_temporal_spread. None if < 2 events."""

    affective: Optional[float] = None
    """1 - normalized affect_valence stddev. None if no affect data."""

    def populated_dimensions(self) -> Dict[str, float]:
        """Return only dimensions that have data (not None)."""
        result = {}
        for name in ("narrative", "social", "spatial", "temporal", "affective"):
            value = getattr(self, name)
            if value is not None:
                result[name] = value
        return result

    def to_dict(self) -> Dict[str, Optional[float]]:
        """Convert to dictionary for serialization."""
        return {
            "narrative": round(self.narrative, 4) if self.narrative is not None else None,
            "social": round(self.social, 4) if self.social is not None else None,
            "spatial": round(self.spatial, 4) if self.spatial is not None else None,
            "temporal": round(self.temporal, 4) if self.temporal is not None else None,
            "affective": round(self.affective, 4) if self.affective is not None else None,
        }


@dataclass
class EpisodicCoherenceResult:
    """Coherence score for a single episode."""

    composite: float = NEUTRAL_FALLBACK
    """Equal-weight mean of populated dimensions."""

    dimensions: CoherenceDimensions = field(default_factory=CoherenceDimensions)
    """Per-dimension scores."""

    populated_count: int = 0
    """Number of dimensions with real data (not fallback)."""

    member_count: int = 0
    """Number of member events used for computation."""


class EpisodicCoherenceScorer:
    """
    Computes semantic coherence for an episode cluster.

    Input: List of member event contexts (ObservationContext or any
    object with the required attribute fields).

    Output: EpisodicCoherenceResult with per-dimension and composite scores.

    Research: M4-RSCH-04 equal_weight coherence rho=0.4556.
    """

    def compute(self, members: Sequence[Any]) -> EpisodicCoherenceResult:
        """
        Compute coherence from member event contexts.

        Args:
            members: ObservationContext objects or any objects with
                narrative_thread_id, social_context, location_name,
                geohash_6, observed_at, affect_valence attributes.

        Returns:
            EpisodicCoherenceResult with composite and per-dimension scores.
        """
        if not members:
            return EpisodicCoherenceResult()

        dims = CoherenceDimensions(
            narrative=self._narrative_coherence(members),
            social=self._social_coherence(members),
            spatial=self._spatial_coherence(members),
            temporal=self._temporal_coherence(members),
            affective=self._affective_coherence(members),
        )

        populated = dims.populated_dimensions()
        populated_count = len(populated)

        if populated_count == 0:
            composite = NEUTRAL_FALLBACK
        else:
            composite = sum(populated.values()) / populated_count

        return EpisodicCoherenceResult(
            composite=composite,
            dimensions=dims,
            populated_count=populated_count,
            member_count=len(members),
        )

    def _narrative_coherence(self, members: Sequence[Any]) -> Optional[float]:
        """Fraction of members sharing the dominant narrative_thread_id."""
        thread_counts: Dict[str, int] = {}
        total = 0

        for m in members:
            thread_id = getattr(m, "narrative_thread_id", None)
            if not thread_id:
                # Try source_event_id path for ObservationContext
                thread_id = getattr(m, "narrative_thread_id", None)
            if thread_id:
                thread_counts[thread_id] = thread_counts.get(thread_id, 0) + 1
                total += 1

        if total == 0:
            return None

        dominant_count = max(thread_counts.values())
        return dominant_count / total

    def _social_coherence(self, members: Sequence[Any]) -> Optional[float]:
        """Fraction of members sharing the dominant social_context."""
        context_counts: Dict[str, int] = {}
        total = 0

        for m in members:
            ctx = getattr(m, "social_context", None)
            if ctx:
                context_counts[ctx] = context_counts.get(ctx, 0) + 1
                total += 1

        if total == 0:
            return None

        dominant_count = max(context_counts.values())
        return dominant_count / total

    def _spatial_coherence(self, members: Sequence[Any]) -> Optional[float]:
        """Fraction of members sharing the dominant location.

        Uses geohash_6 first (more precise), falls back to location_name.
        """
        location_counts: Dict[str, int] = {}
        total = 0

        for m in members:
            loc = getattr(m, "geohash_6", None) or getattr(m, "location_name", None)
            if loc:
                location_counts[loc] = location_counts.get(loc, 0) + 1
                total += 1

        if total == 0:
            return None

        dominant_count = max(location_counts.values())
        return dominant_count / total

    def _temporal_coherence(self, members: Sequence[Any]) -> Optional[float]:
        """1 - normalized temporal spread. Tighter clusters = more coherent."""
        timestamps = []
        for m in members:
            ts = getattr(m, "observed_at", None)
            if ts is not None and ts > 0:
                timestamps.append(ts)

        if len(timestamps) < 2:
            return None

        spread = max(timestamps) - min(timestamps)
        normalized = min(1.0, spread / MAX_TEMPORAL_SPREAD_MS)
        return 1.0 - normalized

    def _affective_coherence(self, members: Sequence[Any]) -> Optional[float]:
        """1 - normalized stddev of affect_valence. Similar affect = more coherent."""
        valences = []
        for m in members:
            val = getattr(m, "affect_valence", None)
            if val is not None:
                valences.append(float(val))

        if len(valences) < 2:
            return None

        mean = sum(valences) / len(valences)
        variance = sum((v - mean) ** 2 for v in valences) / len(valences)
        stddev = math.sqrt(variance)

        # affect_valence is in [-1, 1], max possible stddev = 1.0
        normalized_stddev = min(1.0, stddev)
        return 1.0 - normalized_stddev


@dataclass
class BatchCoherenceSummary:
    """Batch-level aggregation of per-episode coherence."""

    mean_coherence: float = NEUTRAL_FALLBACK
    min_coherence: float = NEUTRAL_FALLBACK
    max_coherence: float = NEUTRAL_FALLBACK
    std_coherence: float = 0.0
    episode_count: int = 0
    per_dimension_means: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "mean_coherence": round(self.mean_coherence, 4),
            "min_coherence": round(self.min_coherence, 4),
            "max_coherence": round(self.max_coherence, 4),
            "std_coherence": round(self.std_coherence, 4),
            "episode_count": self.episode_count,
            "per_dimension_means": {k: round(v, 4) for k, v in self.per_dimension_means.items()},
        }


def compute_batch_coherence(
    episode_results: List[EpisodicCoherenceResult],
) -> BatchCoherenceSummary:
    """
    Aggregate per-episode coherence into batch summary.

    Args:
        episode_results: List of per-episode coherence results.

    Returns:
        BatchCoherenceSummary with mean, min, max, std, and per-dimension means.
    """
    if not episode_results:
        return BatchCoherenceSummary()

    composites = [r.composite for r in episode_results]
    n = len(composites)
    mean = sum(composites) / n
    variance = sum((c - mean) ** 2 for c in composites) / n if n > 1 else 0.0

    # Per-dimension means
    dim_sums: Dict[str, float] = {}
    dim_counts: Dict[str, int] = {}
    for r in episode_results:
        populated = r.dimensions.populated_dimensions()
        for name, value in populated.items():
            dim_sums[name] = dim_sums.get(name, 0.0) + value
            dim_counts[name] = dim_counts.get(name, 0) + 1

    per_dimension_means = {name: dim_sums[name] / dim_counts[name] for name in dim_sums}

    return BatchCoherenceSummary(
        mean_coherence=mean,
        min_coherence=min(composites),
        max_coherence=max(composites),
        std_coherence=math.sqrt(variance),
        episode_count=n,
        per_dimension_means=per_dimension_means,
    )
