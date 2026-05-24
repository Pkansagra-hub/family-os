"""Resolve typed place candidates against registry and fallback sources."""

from __future__ import annotations

from collections.abc import Sequence

from k1.spatial.service.place_alias_catalog import (
    expanded_aliases,
    normalize_place_label,
)
from k1.spatial.types import PlaceCandidate, PlaceRef


def resolve_place_candidate(
    candidate: PlaceCandidate | None,
    places: Sequence[PlaceRef],
    *,
    unknown_place_label: str = "unknown",
) -> PlaceRef | None:
    """Resolve one candidate into a PlaceRef with explicit unknown fallback."""
    if candidate is None or not candidate.normalized_text:
        return None
    normalized = normalize_place_label(candidate.normalized_text)
    for place in places:
        aliases = expanded_aliases(place.label, place.aliases + (place.place_kind,))
        if normalized in aliases:
            return PlaceRef(
                place_id=place.place_id,
                label=place.label,
                place_kind=place.place_kind,
                confidence=max(place.confidence, candidate.confidence),
                source=place.source,
                aliases=place.aliases,
                timezone=place.timezone,
                parent_place_id=place.parent_place_id,
                geofence_ids=place.geofence_ids,
                metadata={**dict(place.metadata), "matched_candidate_source": candidate.source},
            )
    return PlaceRef(
        place_id="unknown",
        label=unknown_place_label,
        place_kind="unknown",
        confidence=max(0.1, min(candidate.confidence, 0.45)),
        source=candidate.source,
        aliases=(normalized,),
        metadata={"unresolved_text": candidate.raw_text},
    )


__all__ = ["resolve_place_candidate"]
