"""M4.E2.I1 — CitationPackBuilder tests."""

from __future__ import annotations

import pytest

from k1.selfmodel.contracts.citation import Citation, CitationPack
from k1.selfmodel.service.citation_builder import (
    CONFLICT_CONFIDENCE_FACTOR,
    DEFAULT_EXCERPT_BYTES,
    OFFLINE_CONFIDENCE_FACTOR,
    STALE_CONFIDENCE_FACTOR,
    CitationPackBuilder,
)

T0 = 1_700_000_000_000


def _b(**kw) -> CitationPackBuilder:
    kw.setdefault("clock_ms", lambda: T0)
    return CitationPackBuilder(**kw)


# ---------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------
def test_constructor_validates_excerpt_bytes() -> None:
    with pytest.raises(ValueError):
        CitationPackBuilder(excerpt_bytes=0)
    with pytest.raises(ValueError):
        CitationPackBuilder(excerpt_bytes="big")  # type: ignore[arg-type]


def test_wrap_validates_actor_id() -> None:
    with pytest.raises(ValueError):
        _b().wrap("", [])
    with pytest.raises(ValueError):
        _b().wrap(None, [])  # type: ignore[arg-type]


def test_wrap_rejects_non_mapping_row() -> None:
    with pytest.raises(TypeError):
        _b().wrap("a1", ["not-a-dict"])  # type: ignore[list-item]


# ---------------------------------------------------------------------
# Empty path
# ---------------------------------------------------------------------
def test_empty_input_returns_empty_pack() -> None:
    pack = _b().wrap("a1", [])
    assert isinstance(pack, CitationPack)
    assert pack.actor_id == "a1"
    assert pack.citations == ()
    assert pack.composed_at_ms == T0


def test_none_input_returns_empty_pack() -> None:
    pack = _b().wrap("a1", None)
    assert pack.citations == ()


# ---------------------------------------------------------------------
# Layer normalisation
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("L1", "L1"),
        ("L5", "L5"),
        ("F", "F"),
        ("episodic", "L1"),
        ("semantic", "L2"),
        ("procedural", "L3"),
        ("affective", "L4"),
        ("metacognitive", "L5"),
        ("family", "F"),
        ("constitution", "C"),
        ("garbage", "L1"),
        ("", "L1"),
    ],
)
def test_layer_normalisation(raw: str, expected: str) -> None:
    pack = _b().wrap("a1", [{"id": "x", "source_layer": raw}])
    assert pack.citations[0].source_layer == expected


# ---------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------
def test_citations_sorted_by_layer_then_id() -> None:
    rows = [
        {"id": "z", "source_layer": "L3"},
        {"id": "a", "source_layer": "L1"},
        {"id": "b", "source_layer": "L1"},
        {"id": "c", "source_layer": "C"},
    ]
    pack = _b().wrap("a1", rows)
    ids = [c.citation_id for c in pack.citations]
    assert ids == ["a", "b", "z", "c"]


# ---------------------------------------------------------------------
# Confidence scaling
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    ("freshness", "factor"),
    [
        ("fresh", 1.0),
        ("stale", STALE_CONFIDENCE_FACTOR),
        ("offline_local_only", OFFLINE_CONFIDENCE_FACTOR),
        ("conflict_pending", CONFLICT_CONFIDENCE_FACTOR),
    ],
)
def test_confidence_scaling_per_freshness(freshness: str, factor: float) -> None:
    pack = _b().wrap(
        "a1",
        [{"id": "x", "freshness": freshness, "confidence": 1.0}],
    )
    assert abs(pack.citations[0].confidence - factor) < 1e-9


def test_unknown_freshness_treated_as_fresh() -> None:
    pack = _b().wrap("a1", [{"id": "x", "freshness": "weird", "confidence": 0.5}])
    assert pack.citations[0].freshness == "fresh"
    assert pack.citations[0].confidence == 0.5


def test_confidence_clipped_to_unit_interval() -> None:
    pack = _b().wrap(
        "a1",
        [
            {"id": "low", "confidence": -1.0},
            {"id": "high", "confidence": 5.0},
            {"id": "junk", "confidence": "nope"},
        ],
    )
    by_id = {c.citation_id: c for c in pack.citations}
    assert by_id["low"].confidence == 0.0
    assert by_id["high"].confidence == 1.0
    assert by_id["junk"].confidence == 1.0  # unparseable -> default


# ---------------------------------------------------------------------
# Excerpt truncation
# ---------------------------------------------------------------------
def test_excerpt_uses_first_available_field() -> None:
    pack = _b().wrap("a1", [{"id": "x", "text": "hello world"}])
    assert pack.citations[0].content_excerpt == "hello world"


def test_excerpt_truncated_to_byte_cap() -> None:
    long_text = "abc " * 1_000  # 4_000 bytes
    pack = _b(excerpt_bytes=64).wrap("a1", [{"id": "x", "content": long_text}])
    excerpt = pack.citations[0].content_excerpt
    assert excerpt.endswith("…")
    assert len(excerpt.encode("utf-8")) <= 64 + 4  # ellipsis tolerance


def test_default_excerpt_cap() -> None:
    text = "x" * (DEFAULT_EXCERPT_BYTES * 2)
    pack = _b().wrap("a1", [{"id": "x", "content": text}])
    assert len(pack.citations[0].content_excerpt.encode("utf-8")) <= DEFAULT_EXCERPT_BYTES + 4


# ---------------------------------------------------------------------
# Payload preservation
# ---------------------------------------------------------------------
def test_unknown_fields_preserved_in_payload() -> None:
    pack = _b().wrap(
        "a1",
        [{"id": "x", "custom_attr": 42, "tags": ["a", "b"]}],
    )
    payload = pack.citations[0].payload
    assert payload["custom_attr"] == 42
    assert payload["tags"] == ["a", "b"]


def test_reserved_fields_not_duplicated_in_payload() -> None:
    pack = _b().wrap(
        "a1",
        [{"id": "x", "source_layer": "L2", "content": "hi", "confidence": 0.9}],
    )
    payload = pack.citations[0].payload
    for k in ("id", "source_layer", "content", "confidence"):
        assert k not in payload


# ---------------------------------------------------------------------
# Identity / determinism
# ---------------------------------------------------------------------
def test_missing_id_gets_synthetic_id() -> None:
    pack = _b().wrap("a1", [{}])
    assert isinstance(pack.citations[0], Citation)
    assert pack.citations[0].citation_id.startswith("cit_")


def test_revision_propagation() -> None:
    pack = _b().wrap(
        "a1",
        [{"id": "x", "projection_revision": "rev_42"}],
    )
    assert pack.citations[0].projection_revision == "rev_42"
