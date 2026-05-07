"""
Tests for M10 E10.1 -- UltraBERTPhase1Pipeline.

Covers:
  - Mapping from adapter dict to Phase1Result (all 13 fields)
  - Multi-factor complexity classifier
  - Confidence thresholding for intents
  - Graceful degradation (fallback to StubPhase1Pipeline)
  - Sentiment-to-valence mapping
  - Arousal heuristic
  - Entity merging (family + general NER)
  - Temporal expressions and relations (E10.5)
  - Embedding retention (last_embedding property)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from poc.k1_poc.config.loader import Phase1Config
from poc.k1_poc.fsm.phase1 import Phase1Result
from poc.k1_poc.fsm.ultrabert_adapter import SENTIMENT_TO_VALENCE, StubUltraBERTAdapter
from poc.k1_poc.fsm.ultrabert_phase1 import UltraBERTPhase1Pipeline

# =========================================================================
# Fixtures / Helpers
# =========================================================================


def _analysis(**overrides: Any) -> dict[str, Any]:
    """Build a standard UltraBERT analysis dict for testing."""
    defaults: dict[str, Any] = {
        "sentiment": "positive",
        "sentiment_confidence": 0.85,
        "emotions": ["joy", "love"],
        "emotion_scores": {"joy": 0.9, "love": 0.6, "neutral": 0.1},
        "safety": "GREEN",
        "safety_confidence": 0.95,
        "entities": [{"text": "Mom", "label": "KINSHIP", "start": 0, "end": 3}],
        "general_entities": [{"text": "Saturday", "label": "DATE", "start": 10, "end": 18}],
        "temporal": [{"text": "next Saturday", "label": "DATE_REL", "start": 5, "end": 18}],
        "intent": "log_memory",
        "ingress": "FAMILY",
        "relations": ["parent_of"],
        "embedding": [0.1] * 768,
        "latency_ms": 18.5,
    }
    defaults.update(overrides)
    return defaults


class _MockAdapter:
    """Configurable adapter that returns a fixed analysis dict."""

    def __init__(self, analysis: dict[str, Any] | None = None):
        self._analysis = analysis
        self._available = analysis is not None

    def analyze(self, text: str) -> dict[str, Any] | None:
        return self._analysis

    def is_available(self) -> bool:
        return self._available

    def get_metrics(self) -> dict[str, Any]:
        return {"mock": True}


def _pipeline(
    analysis: dict[str, Any] | None = None,
    config: Phase1Config | None = None,
) -> UltraBERTPhase1Pipeline:
    """Build a pipeline with a mock adapter."""
    adapter = _MockAdapter(analysis)
    return UltraBERTPhase1Pipeline(
        adapter=adapter,
        config=config or Phase1Config(),
    )


# =========================================================================
# E10.1.1 -- Mapping: adapter dict -> Phase1Result
# =========================================================================


class TestMapping:
    """classify() correctly maps all 12-head outputs to Phase1Result."""

    def test_intent_classification(self):
        p = _pipeline(_analysis(intent="scheduling"))
        r = p.classify("book appointment")
        assert r.intent_classification == "scheduling"

    def test_domain_context(self):
        p = _pipeline(_analysis(ingress="HEALTH"))
        r = p.classify("see doctor")
        assert r.domain_context == "HEALTH"

    def test_safety_band(self):
        p = _pipeline(_analysis(safety="AMBER"))
        r = p.classify("something")
        assert r.safety_band == "AMBER"

    def test_primary_emotion(self):
        p = _pipeline(_analysis(emotions=["worry", "fear"]))
        r = p.classify("concerned")
        assert r.primary_emotion == "worry"

    def test_primary_emotion_fallback(self):
        p = _pipeline(_analysis(emotions=[]))
        r = p.classify("hello")
        assert r.primary_emotion == "neutral"

    def test_emotion_confidence_from_max_score(self):
        p = _pipeline(_analysis(emotion_scores={"joy": 0.9, "love": 0.6}))
        r = p.classify("great")
        assert r.emotion_confidence == pytest.approx(0.9)

    def test_emotion_confidence_default(self):
        p = _pipeline(_analysis(emotion_scores={}))
        r = p.classify("hello")
        assert r.emotion_confidence == pytest.approx(0.5)

    def test_valence_from_sentiment(self):
        for sent, expected_val in SENTIMENT_TO_VALENCE.items():
            p = _pipeline(_analysis(sentiment=sent))
            r = p.classify("test")
            assert r.valence == pytest.approx(expected_val), f"Failed for {sent}"

    def test_valence_unknown_sentiment_defaults_to_neutral(self):
        p = _pipeline(_analysis(sentiment="unknown_value"))
        r = p.classify("test")
        assert r.valence == pytest.approx(0.5)

    def test_entities_merged(self):
        p = _pipeline(
            _analysis(
                entities=[{"text": "Mom", "label": "KINSHIP", "start": 0, "end": 3}],
                general_entities=[{"text": "NYC", "label": "LOC", "start": 5, "end": 8}],
            )
        )
        r = p.classify("Mom in NYC")
        assert len(r.entities) == 2
        texts = {e["text"] for e in r.entities}
        assert "Mom" in texts
        assert "NYC" in texts

    def test_entities_deduplicated_by_span(self):
        """Overlapping spans: family entity wins."""
        p = _pipeline(
            _analysis(
                entities=[{"text": "Mom", "label": "KINSHIP", "start": 0, "end": 3}],
                general_entities=[{"text": "Mom", "label": "PERSON", "start": 0, "end": 3}],
            )
        )
        r = p.classify("Mom")
        assert len(r.entities) == 1
        assert r.entities[0]["label"] == "KINSHIP"

    def test_salience_map_created(self):
        p = _pipeline(
            _analysis(
                entities=[{"text": "A", "label": "X", "start": 0, "end": 1}],
                general_entities=[{"text": "B", "label": "Y", "start": 2, "end": 3}],
            )
        )
        r = p.classify("A B")
        assert len(r.salience_map) == 2
        assert all(v == pytest.approx(0.8) for v in r.salience_map.values())

    def test_intents_includes_primary(self):
        p = _pipeline(_analysis(intent="greeting"))
        r = p.classify("hi")
        assert "greeting" in r.intents

    def test_complexity_tier_present(self):
        """P3.1: complexity_tier removed from Phase1Result."""
        p = _pipeline(_analysis())
        r = p.classify("test")
        assert not hasattr(r, "complexity_tier")


# =========================================================================
# E10.5 -- Temporal, relations, embedding
# =========================================================================


class TestExtraHeads:
    """Temporal expressions, relations, embedding integration."""

    def test_temporal_expressions(self):
        temporal = [{"text": "next Saturday", "label": "DATE_REL", "start": 5, "end": 18}]
        p = _pipeline(_analysis(temporal=temporal))
        r = p.classify("meet next Saturday")
        assert len(r.temporal_expressions) == 1
        assert r.temporal_expressions[0]["label"] == "DATE_REL"

    def test_relations(self):
        p = _pipeline(_analysis(relations=["parent_of", "spouse_of"]))
        r = p.classify("Mom and Dad")
        assert "parent_of" in r.relations
        assert "spouse_of" in r.relations

    def test_relations_in_metadata(self):
        p = _pipeline(_analysis(relations=["parent_of"]))
        r = p.classify("Mom")
        md = r.to_metadata()
        assert "parent_of" in md["relations"]

    def test_temporal_in_metadata(self):
        temporal = [{"text": "tomorrow", "label": "DATE_REL", "start": 0, "end": 8}]
        p = _pipeline(_analysis(temporal=temporal))
        r = p.classify("tomorrow")
        md = r.to_metadata()
        assert len(md["temporal_expressions"]) == 1

    def test_embedding_retained(self):
        embedding = [0.5] * 768
        p = _pipeline(_analysis(embedding=embedding))
        p.classify("test")
        assert p.last_embedding is not None
        assert len(p.last_embedding) == 768

    def test_embedding_none_when_not_list(self):
        p = _pipeline(_analysis(embedding=None))
        p.classify("test")
        assert p.last_embedding is None

    def test_embedding_not_in_metadata(self):
        """Embedding should NOT be in to_metadata() (too large)."""
        p = _pipeline(_analysis(embedding=[0.1] * 768))
        r = p.classify("test")
        md = r.to_metadata()
        assert "embedding" not in md


# =========================================================================
# E10.1.2 -- Multi-factor complexity classifier
# P3.1: REMOVED -- complexity_tier no longer produced by Phase 1.
# Routing tier now decided downstream by dispatch_task / actor logic.
# =========================================================================


class TestComplexityClassifier:
    """P3.1: complexity_tier classification removed from UltraBERT pipeline."""

    def test_complexity_classifier_removed(self):
        from poc.k1_poc.fsm.ultrabert_phase1 import UltraBERTPhase1Pipeline

        # _compute_complexity helper deleted in P3.1
        assert not hasattr(UltraBERTPhase1Pipeline, "_compute_complexity")


# =========================================================================
# E10.1.3 -- Confidence thresholding
# =========================================================================


class TestConfidenceThresholding:
    """Intent filtering by confidence threshold."""

    def test_only_primary_when_no_scores(self):
        p = _pipeline(_analysis(intent="greeting"))
        r = p.classify("hi")
        assert r.intents == ["greeting"]

    def test_filters_below_threshold(self):
        cfg = Phase1Config(intent_confidence_threshold=0.3)
        p = _pipeline(
            _analysis(
                intent="booking",
                intent_scores={"booking": 0.8, "scheduling": 0.35, "query": 0.1},
            ),
            config=cfg,
        )
        r = p.classify("book hotel near doctor")
        assert "booking" in r.intents
        assert "scheduling" in r.intents
        assert "query" not in r.intents

    def test_primary_always_included(self):
        cfg = Phase1Config(intent_confidence_threshold=0.9)
        p = _pipeline(
            _analysis(
                intent="booking",
                intent_scores={"booking": 0.5},  # Below threshold
            ),
            config=cfg,
        )
        r = p.classify("book")
        assert "booking" in r.intents


# =========================================================================
# E10.1.4 -- Graceful degradation
# =========================================================================


class TestGracefulDegradation:
    """Fallback to StubPhase1Pipeline when adapter is unavailable."""

    def test_fallback_when_adapter_returns_none(self):
        adapter = StubUltraBERTAdapter()
        p = UltraBERTPhase1Pipeline(adapter=adapter)
        r = p.classify("hello")
        # Should get a valid Phase1Result from the stub
        assert isinstance(r, Phase1Result)

    def test_degraded_count_increments(self):
        adapter = StubUltraBERTAdapter()
        p = UltraBERTPhase1Pipeline(adapter=adapter)
        p.classify("one")
        p.classify("two")
        assert p.degraded_count == 2

    def test_degraded_flag_on_result(self):
        adapter = StubUltraBERTAdapter()
        p = UltraBERTPhase1Pipeline(adapter=adapter)
        r = p.classify("hello")
        assert getattr(r, "_degraded", False) is True

    def test_fallback_when_adapter_raises(self):
        adapter = MagicMock()
        adapter.analyze.side_effect = RuntimeError("GPU OOM")
        adapter.is_available.return_value = True
        p = UltraBERTPhase1Pipeline(adapter=adapter)
        r = p.classify("boom")
        assert isinstance(r, Phase1Result)
        assert p.degraded_count == 1

    def test_call_count_always_increments(self):
        adapter = StubUltraBERTAdapter()
        p = UltraBERTPhase1Pipeline(adapter=adapter)
        p.classify("a")
        p.classify("b")
        assert p.call_count == 2


# =========================================================================
# Arousal heuristic
# =========================================================================


class TestArousalHeuristic:
    """_infer_arousal() heuristic mapping."""

    def test_high_arousal_emotion(self):
        p = _pipeline(_analysis(emotions=["anger"], emotion_scores={"anger": 0.9}))
        r = p.classify("furious")
        assert r.arousal >= 0.7

    def test_low_arousal_emotion(self):
        p = _pipeline(_analysis(emotions=["sadness"], emotion_scores={"sadness": 0.8}))
        r = p.classify("sad")
        assert r.arousal <= 0.3

    def test_neutral_arousal(self):
        p = _pipeline(_analysis(emotions=["neutral"], emotion_scores={"neutral": 0.5}))
        r = p.classify("ok")
        assert r.arousal == pytest.approx(0.5)
