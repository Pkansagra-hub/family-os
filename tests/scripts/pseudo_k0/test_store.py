"""tests/scripts/pseudo_k0/test_store.py — SQLiteK0Store tests.

Run: python -m pytest tests/scripts/pseudo_k0/test_store.py -q --no-cov
"""

from __future__ import annotations

import pytest

from scripts.pseudo_k0.models import (
    K0Envelope,
    RecallRequestBody,
    RecallSelectorBody,
)
from scripts.pseudo_k0.store import (
    SQLiteK0Store,
    _extract_content,
    _infer_memory_type,
)


@pytest.fixture
def store():
    s = SQLiteK0Store(":memory:")
    yield s
    s.close()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _env(
    *,
    topic: str = "memory.write.v1",
    body: dict | None = None,
    space_id: str = "family:smith",
    actor: str | None = "alex",
    tenant_id: str | None = None,
) -> K0Envelope:
    return K0Envelope(
        topic=topic,
        body=body or {"content": "hello"},
        space_id=space_id,
        actor=actor,
        tenant_id=tenant_id,
    )


# ---------------------------------------------------------------------------
# Pure helper tests
# ---------------------------------------------------------------------------


class TestInferMemoryType:
    def test_explicit_body_field(self):
        assert _infer_memory_type("anything", {"type": "Semantic"}) == "semantic"

    def test_memory_write_defaults_episodic(self):
        assert _infer_memory_type("memory.write.v1", {}) == "episodic"

    def test_unknown_topic_returns_none(self):
        assert _infer_memory_type("foo.bar.v1", {}) is None


class TestExtractContent:
    def test_content_field_wins(self):
        assert _extract_content({"content": "hello"}) == "hello"

    def test_text_field(self):
        assert _extract_content({"text": "world"}) == "world"

    def test_nested_summary(self):
        assert _extract_content({"description": {"text": "deep"}}) == "deep"

    def test_fallback_is_json_truncated(self):
        out = _extract_content({"k": "v"})
        assert out.startswith("{")
        assert '"k":"v"' in out


# ---------------------------------------------------------------------------
# Store behaviour
# ---------------------------------------------------------------------------


class TestWriteEnvelope:
    def test_returns_row_id(self, store):
        rid = store.write_envelope(_env())
        assert rid >= 1

    def test_counts_increment(self, store):
        store.write_envelope(_env())
        store.write_envelope(_env())
        wal, obs = store.counts()
        assert wal == 2 and obs == 0

    def test_memory_type_inferred_for_memory_write(self, store):
        store.write_envelope(_env(topic="memory.write.v1", body={"content": "x"}))
        # Inferred memory_type=episodic — verifiable via recall(type=episodic)
        req = RecallRequestBody(
            selectors=[RecallSelectorBody(type="episodic", query="x")],
            space_id="family:smith",
        )
        resp = store.recall(req)
        assert resp.total == 1
        assert resp.hits[0].selector_type == "episodic"


class TestWriteObs:
    def test_obs_count(self, store):
        store.write_obs("feedback", {"score": 0.9})
        store.write_obs("feedback", {"score": 0.7})
        _, obs = store.counts()
        assert obs == 2


class TestRecall:
    def test_empty_store_returns_zero_hits(self, store):
        req = RecallRequestBody(
            selectors=[RecallSelectorBody(type="episodic")],
            space_id="family:smith",
        )
        resp = store.recall(req)
        assert resp.total == 0
        assert resp.hits == []
        assert resp.truncated is False

    def test_filters_by_space_id(self, store):
        store.write_envelope(_env(space_id="family:smith", body={"content": "smith hi"}))
        store.write_envelope(_env(space_id="family:other", body={"content": "other hi"}))
        req = RecallRequestBody(
            selectors=[RecallSelectorBody(type="episodic")],
            space_id="family:smith",
        )
        resp = store.recall(req)
        assert resp.total == 1
        assert "smith" in resp.hits[0].content.get("content", "")

    def test_query_like_filter(self, store):
        store.write_envelope(_env(body={"content": "Riley swim bag"}))
        store.write_envelope(_env(body={"content": "Jordan night shift"}))
        req = RecallRequestBody(
            selectors=[RecallSelectorBody(type="episodic", query="Riley")],
            space_id="family:smith",
        )
        resp = store.recall(req)
        assert resp.total == 1
        assert "Riley" in resp.hits[0].content.get("content", "")

    def test_vector_query_fallback(self, store):
        store.write_envelope(_env(body={"content": "Riley swim bag"}))
        # No per-selector query, but body-level vector_query — should still match.
        req = RecallRequestBody(
            selectors=[RecallSelectorBody(type="episodic")],
            space_id="family:smith",
            vector_query="Riley",
        )
        resp = store.recall(req)
        assert resp.total == 1

    def test_max_results_truncates(self, store):
        for i in range(5):
            store.write_envelope(_env(body={"content": f"msg-{i}"}))
        req = RecallRequestBody(
            selectors=[RecallSelectorBody(type="episodic", limit=10)],
            space_id="family:smith",
            max_results=2,
        )
        resp = store.recall(req)
        assert resp.total == 5
        assert len(resp.hits) == 2
        assert resp.truncated is True

    def test_per_selector_limit_caps(self, store):
        for i in range(5):
            store.write_envelope(_env(body={"content": f"msg-{i}"}))
        req = RecallRequestBody(
            selectors=[RecallSelectorBody(type="episodic", limit=3)],
            space_id="family:smith",
        )
        resp = store.recall(req)
        assert resp.total == 3  # selector cap is the SQL LIMIT

    def test_selector_belief_returns_empty(self, store):
        store.write_envelope(_env(body={"content": "x"}))
        req = RecallRequestBody(
            selectors=[RecallSelectorBody(type="belief")],
            space_id="family:smith",
        )
        resp = store.recall(req)
        assert resp.total == 0  # pseudo-K0 has no belief store

    def test_topic_filter_in_selector(self, store):
        store.write_envelope(
            _env(topic="memory.write.v1", body={"type": "episodic", "content": "a"})
        )
        store.write_envelope(
            _env(topic="custom.topic.v1", body={"type": "episodic", "content": "b"})
        )
        req = RecallRequestBody(
            selectors=[RecallSelectorBody(type="episodic", topic="memory.write.v1")],
            space_id="family:smith",
        )
        resp = store.recall(req)
        assert resp.total == 1
        assert resp.hits[0].content.get("content") == "a"

    def test_trace_id_echoed(self, store):
        req = RecallRequestBody(
            selectors=[RecallSelectorBody(type="episodic")],
            space_id="family:smith",
            trace_id="trace-42",
        )
        resp = store.recall(req)
        assert resp.trace_id == "trace-42"

    def test_hit_source_is_pseudo_k0(self, store):
        store.write_envelope(_env(body={"content": "x"}))
        req = RecallRequestBody(
            selectors=[RecallSelectorBody(type="episodic")],
            space_id="family:smith",
        )
        resp = store.recall(req)
        assert resp.hits[0].source == "pseudo_k0.wal"


class TestPersistence:
    def test_round_trip_via_disk(self, tmp_path):
        db = tmp_path / "k0.db"
        s1 = SQLiteK0Store(db)
        s1.write_envelope(_env(body={"content": "persist me"}))
        s1.close()

        s2 = SQLiteK0Store(db)
        try:
            wal, _ = s2.counts()
            assert wal == 1
            req = RecallRequestBody(
                selectors=[RecallSelectorBody(type="episodic", query="persist")],
                space_id="family:smith",
            )
            resp = s2.recall(req)
            assert resp.total == 1
        finally:
            s2.close()
