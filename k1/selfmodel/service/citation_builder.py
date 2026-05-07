"""CitationPackBuilder — wrap raw recall hits into a ``CitationPack``.

The wrapper makes provenance first-class: every memory reference an
actor sees carries (source_layer, projection_revision, freshness,
confidence). Pure function over an iterable of dicts.

Input shape (matches ``ToolContext.recall_fn`` contract from
``k1/concierge/tools/implementations.py`` — ``list[dict]``)::

    {
        # Required
        "id": "mem_123" | "doc_42" | ...,
        # Optional — defaults below if missing
        "source_layer": "L1" | "L2" | "L3" | "L4" | "L5" | "F" | "C" | "episodic" | ...,
        "projection_revision": "rev_42" | "",
        "freshness": "fresh" | "stale" | "offline_local_only" | "conflict_pending",
        "content": "..." | "text": "..." | "excerpt": "...",
        "confidence": 0.0 .. 1.0,
        # everything else is preserved verbatim under ``payload``.
    }

Output: a ``CitationPack`` with one :class:`Citation` per input row,
grouped/sorted by ``source_layer`` for stable downstream rendering.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from k1.selfmodel.contracts.citation import Citation, CitationPack

__all__ = [
    "CitationPackBuilder",
    "DEFAULT_EXCERPT_BYTES",
    "STALE_CONFIDENCE_FACTOR",
    "OFFLINE_CONFIDENCE_FACTOR",
    "CONFLICT_CONFIDENCE_FACTOR",
]

logger = logging.getLogger(__name__)

# Public constants — also used by tests so they stay in lockstep.
DEFAULT_EXCERPT_BYTES: int = 240
STALE_CONFIDENCE_FACTOR: float = 0.8
OFFLINE_CONFIDENCE_FACTOR: float = 0.6
CONFLICT_CONFIDENCE_FACTOR: float = 0.4

_VALID_SOURCE_LAYERS = frozenset(("L1", "L2", "L3", "L4", "L5", "F", "C"))
_LEGACY_LAYER_MAP = {
    "episodic": "L1",
    "semantic": "L2",
    "procedural": "L3",
    "affective": "L4",
    "metacognitive": "L5",
    "family": "F",
    "constitution": "C",
}
_VALID_FRESHNESS = frozenset(("fresh", "stale", "offline_local_only", "conflict_pending"))
_FRESHNESS_FACTOR: dict[str, float] = {
    "fresh": 1.0,
    "stale": STALE_CONFIDENCE_FACTOR,
    "offline_local_only": OFFLINE_CONFIDENCE_FACTOR,
    "conflict_pending": CONFLICT_CONFIDENCE_FACTOR,
}


@dataclass(frozen=True)
class _Normalised:
    citation_id: str
    source_layer: str
    projection_revision: str
    freshness: str
    content_excerpt: str
    base_confidence: float
    payload: dict[str, object]


class CitationPackBuilder:
    """Wrap recall results into a :class:`CitationPack`."""

    __slots__ = ("_excerpt_bytes", "_clock_ms")

    def __init__(
        self,
        *,
        excerpt_bytes: int = DEFAULT_EXCERPT_BYTES,
        clock_ms=None,
    ) -> None:
        if not isinstance(excerpt_bytes, int) or excerpt_bytes <= 0:
            raise ValueError("excerpt_bytes must be a positive int")
        self._excerpt_bytes = excerpt_bytes
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def wrap(
        self,
        actor_id: str,
        raw_results: Iterable[Mapping[str, object]] | None,
    ) -> CitationPack:
        """Build a :class:`CitationPack` from raw recall rows.

        Args:
            actor_id: The actor whose recall this is (provenance scope).
            raw_results: Sequence of dict-like rows; ``None`` is treated
                as empty.

        Returns:
            A :class:`CitationPack`. If ``raw_results`` is empty/None,
            ``citations`` is an empty tuple.

        Raises:
            ValueError: if ``actor_id`` is empty.
            TypeError: if a row is not a Mapping.
        """
        if not actor_id or not isinstance(actor_id, str):
            raise ValueError("actor_id must be a non-empty string")

        rows = list(raw_results or ())
        normalised: list[_Normalised] = []
        for idx, row in enumerate(rows):
            if not isinstance(row, Mapping):
                raise TypeError(f"recall row {idx} must be Mapping, got {type(row).__name__}")
            normalised.append(self._normalise(row, idx))

        # Stable order: source_layer (L1<L2<L3<L4<L5<F<C), then citation_id.
        normalised.sort(key=lambda n: (_LAYER_RANK.get(n.source_layer, 99), n.citation_id))

        citations = tuple(
            Citation(
                citation_id=n.citation_id,
                source_layer=n.source_layer,
                projection_revision=n.projection_revision,
                freshness=n.freshness,
                content_excerpt=n.content_excerpt,
                confidence=_scaled_confidence(n.base_confidence, n.freshness),
                payload=n.payload,
            )
            for n in normalised
        )

        return CitationPack(
            actor_id=actor_id,
            citations=citations,
            composed_at_ms=self._clock_ms(),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _normalise(self, row: Mapping[str, object], idx: int) -> _Normalised:
        cid_obj = row.get("id") or row.get("citation_id") or row.get("doc_id")
        cid = str(cid_obj) if cid_obj is not None else f"cit_{idx}"

        raw_layer = row.get("source_layer") or row.get("layer") or ""
        layer = _coerce_layer(str(raw_layer))

        rev_obj = row.get("projection_revision") or row.get("revision") or ""
        rev = str(rev_obj)

        raw_fresh = str(row.get("freshness") or "fresh").lower()
        freshness = raw_fresh if raw_fresh in _VALID_FRESHNESS else "fresh"

        excerpt_src = (
            row.get("content_excerpt")
            or row.get("excerpt")
            or row.get("content")
            or row.get("text")
            or ""
        )
        excerpt = self._truncate(str(excerpt_src))

        confidence = _coerce_confidence(row.get("confidence", 1.0))

        payload = {k: v for k, v in row.items() if k not in _RESERVED_KEYS}

        return _Normalised(
            citation_id=cid,
            source_layer=layer,
            projection_revision=rev,
            freshness=freshness,
            content_excerpt=excerpt,
            base_confidence=confidence,
            payload=payload,
        )

    def _truncate(self, text: str) -> str:
        if not text:
            return ""
        encoded = text.encode("utf-8")
        if len(encoded) <= self._excerpt_bytes:
            return text.strip()
        # Truncate on byte boundary then sanitise utf-8.
        cut = encoded[: self._excerpt_bytes].decode("utf-8", errors="ignore")
        return cut.rstrip() + "…"


# ----------------------------------------------------------------------
# Module-level helpers
# ----------------------------------------------------------------------
_RESERVED_KEYS = frozenset(
    (
        "id",
        "citation_id",
        "doc_id",
        "source_layer",
        "layer",
        "projection_revision",
        "revision",
        "freshness",
        "content_excerpt",
        "excerpt",
        "content",
        "text",
        "confidence",
    )
)

_LAYER_RANK: dict[str, int] = {
    "L1": 1,
    "L2": 2,
    "L3": 3,
    "L4": 4,
    "L5": 5,
    "F": 6,
    "C": 7,
}


def _coerce_layer(raw: str) -> str:
    raw = (raw or "").strip()
    if raw in _VALID_SOURCE_LAYERS:
        return raw
    mapped = _LEGACY_LAYER_MAP.get(raw.lower())
    if mapped:
        return mapped
    return "L1"  # default-safe: unknown source treated as episodic.


def _coerce_confidence(value: object) -> float:
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1.0
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return f


def _scaled_confidence(base: float, freshness: str) -> float:
    factor = _FRESHNESS_FACTOR.get(freshness, 1.0)
    scaled = base * factor
    if scaled < 0.0:
        return 0.0
    if scaled > 1.0:
        return 1.0
    return scaled
