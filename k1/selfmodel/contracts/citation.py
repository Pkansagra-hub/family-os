"""Citation pack dataclasses.

A ``CitationPack`` wraps raw recall results so every memory reference
the actor sees carries provenance: source layer, projection revision,
freshness, confidence. Builder logic lives in
``k1.selfmodel.service.citation_builder`` (M4).
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "Citation",
    "CitationPack",
]


@dataclass(frozen=True)
class Citation:
    """A single memory reference with provenance."""

    citation_id: str
    source_layer: str  # "L1" | "L2" | "L3" | "L4" | "L5" | "F" | "C"
    projection_revision: str = ""
    freshness: str = "fresh"  # "fresh" | "stale" | "offline_local_only" | "conflict_pending"
    content_excerpt: str = ""
    confidence: float = 1.0
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CitationPack:
    """A grouped set of citations returned in place of raw recall hits."""

    actor_id: str
    citations: tuple[Citation, ...] = field(default_factory=tuple)
    composed_at_ms: int = 0
