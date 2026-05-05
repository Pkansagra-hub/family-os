"""M4.E2.I2 — RecallCitationWrapper tests."""

from __future__ import annotations

import asyncio

import pytest

from k1.selfmodel.adapters.recall_citation_wrapper import RecallCitationWrapper


def _sync_inner(query, memory_types, max_results):
    return [
        {"id": "m1", "source_layer": "L1", "content": "first", "confidence": 0.9},
        {"id": "m2", "source_layer": "L2", "content": "second"},
    ]


async def _async_inner(query, memory_types, max_results):
    return [{"id": "m1", "source_layer": "L1", "content": "x"}]


# ---------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------
def test_constructor_requires_callable_inner() -> None:
    with pytest.raises(ValueError):
        RecallCitationWrapper(inner=None, actor_id="a1")  # type: ignore[arg-type]


def test_constructor_requires_actor_id() -> None:
    with pytest.raises(ValueError):
        RecallCitationWrapper(inner=_sync_inner, actor_id="")


def test_constructor_validates_mode() -> None:
    with pytest.raises(ValueError):
        RecallCitationWrapper(inner=_sync_inner, actor_id="a1", mode="weird")  # type: ignore[arg-type]


# ---------------------------------------------------------------------
# Sync inner — pack mode
# ---------------------------------------------------------------------
def test_sync_inner_returns_pack_envelope() -> None:
    w = RecallCitationWrapper(inner=_sync_inner, actor_id="a1")
    out = w("q", ["episodic"], 5)
    assert isinstance(out, list)
    assert len(out) == 1
    envelope = out[0]
    assert "citation_pack" in envelope and "memories" in envelope
    pack_dict = envelope["citation_pack"]
    assert pack_dict["actor_id"] == "a1"
    assert {c["citation_id"] for c in pack_dict["citations"]} == {"m1", "m2"}
    # Raw rows preserved verbatim for back-compat consumers.
    assert envelope["memories"] == [
        {"id": "m1", "source_layer": "L1", "content": "first", "confidence": 0.9},
        {"id": "m2", "source_layer": "L2", "content": "second"},
    ]


# ---------------------------------------------------------------------
# Sync inner — passthrough mode
# ---------------------------------------------------------------------
def test_passthrough_mode_returns_raw_rows() -> None:
    w = RecallCitationWrapper(inner=_sync_inner, actor_id="a1", mode="passthrough")
    out = w("q", ["episodic"], 5)
    assert out == _sync_inner("", [], 0)


# ---------------------------------------------------------------------
# Async inner
# ---------------------------------------------------------------------
def test_async_inner_returns_awaitable() -> None:
    w = RecallCitationWrapper(inner=_async_inner, actor_id="a1")
    coro = w("q", ["episodic"], 5)
    out = asyncio.run(coro)
    assert "citation_pack" in out[0]
    assert out[0]["citation_pack"]["actor_id"] == "a1"


# ---------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------
def test_empty_inner_returns_empty_pack_envelope() -> None:
    w = RecallCitationWrapper(inner=lambda *a: [], actor_id="a1")
    out = w("q", [], 5)
    assert out[0]["citation_pack"]["citations"] == []
    assert out[0]["memories"] == []


def test_non_iterable_inner_falls_back_safely(caplog) -> None:
    w = RecallCitationWrapper(inner=lambda *a: 42, actor_id="a1")  # type: ignore[arg-type]
    out = w("q", [], 5)
    # Coerced to empty list, then wrapped.
    assert out[0]["citation_pack"]["citations"] == []


def test_builder_failure_falls_back_to_passthrough() -> None:
    class _BadBuilder:
        def wrap(self, actor_id, rows):
            raise RuntimeError("builder boom")

    w = RecallCitationWrapper(
        inner=_sync_inner,
        actor_id="a1",
        builder=_BadBuilder(),  # type: ignore[arg-type]
    )
    out = w("q", [], 5)
    # Falls back to raw rows.
    assert out == _sync_inner("", [], 0)


def test_signature_preserved() -> None:
    captured = {}

    def inner(query, memory_types, max_results):
        captured["q"] = query
        captured["mt"] = list(memory_types)
        captured["max"] = max_results
        return []

    w = RecallCitationWrapper(inner=inner, actor_id="a1")
    w("hello", ("episodic", "semantic"), 7)
    assert captured == {"q": "hello", "mt": ["episodic", "semantic"], "max": 7}
