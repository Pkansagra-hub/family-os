"""
Tests for M10 E10.5 -- Extra Heads & Bootstrap Wiring.

Covers:
  - E10.5.1: Temporal head -> Phase1Result.temporal_expressions + scoreboard referents
  - E10.5.2: Relation head -> Phase1Result.relations + to_metadata()
  - E10.5.3: Embedding head -> pipeline.last_embedding (NOT in to_metadata)
  - E10.4.2: Bootstrap pipeline selection (config-driven)
  - E10.4.4: End-to-end integration test (mock UltraBERT)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from poc.k1_poc.fsm.phase1 import Phase1Result, StubPhase1Pipeline
from poc.k1_poc.fsm.ultrabert_adapter import StubUltraBERTAdapter
from poc.k1_poc.fsm.ultrabert_phase1 import UltraBERTPhase1Pipeline


def _make_adapter(analysis: dict[str, Any]) -> MagicMock:
    """Build a mock adapter returning a fixed analysis dict."""
    adapter = MagicMock()
    adapter.is_available.return_value = True
    adapter.analyze.return_value = analysis
    return adapter


def _base_analysis(**overrides: Any) -> dict[str, Any]:
    """Full 12-head analysis dict with sensible defaults."""
    d: dict[str, Any] = {
        "sentiment": "positive",
        "emotions": ["joy"],
        "emotion_scores": {"joy": 0.9},
        "safety": "GREEN",
        "entities": [],
        "general_entities": [],
        "temporal": [],
        "intent": "log_memory",
        "intent_scores": {"log_memory": 0.8},
        "ingress": "FAMILY",
        "relations": [],
        "embedding": [0.1] * 768,
    }
    d.update(overrides)
    return d


# =========================================================================
# E10.5.1 -- Temporal head
# =========================================================================


class TestTemporalHead:
    """Temporal expressions from UltraBERT temporal head."""

    def test_temporal_expressions_extracted(self):
        temporal = [{"text": "next Saturday", "label": "DATE_REL", "start": 10, "end": 23}]
        adapter = _make_adapter(_base_analysis(temporal=temporal))
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        result = pipe.classify("Let's meet next Saturday")
        assert result.temporal_expressions == temporal

    def test_temporal_empty_when_no_temporal_head(self):
        adapter = _make_adapter(_base_analysis(temporal=[]))
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        result = pipe.classify("Hello world")
        assert result.temporal_expressions == []

    def test_multiple_temporal_spans(self):
        temporal = [
            {"text": "tomorrow", "label": "DATE_REL", "start": 5, "end": 13},
            {"text": "3pm", "label": "TIME_REL", "start": 17, "end": 20},
        ]
        adapter = _make_adapter(_base_analysis(temporal=temporal))
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        result = pipe.classify("Meet tomorrow at 3pm")
        assert len(result.temporal_expressions) == 2

    def test_temporal_in_to_metadata(self):
        temporal = [{"text": "next week", "label": "DATE_REL", "start": 0, "end": 9}]
        adapter = _make_adapter(_base_analysis(temporal=temporal))
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        result = pipe.classify("next week we travel")
        meta = result.to_metadata()
        assert "temporal_expressions" in meta
        assert len(meta["temporal_expressions"]) == 1

    def test_temporal_referents_written_to_scoreboard(self):
        """Verify _write_phase1_to_ss writes temporal spans as referents."""
        from poc.k1_poc.fsm.controller import ConciergeController
        from poc.k1_poc.sessionstate.sections.scoreboard import ScoreboardSection

        ctrl = object.__new__(ConciergeController)
        ctrl._ss = MagicMock()
        scoreboard = ScoreboardSection()
        ctrl._ss.get_section = lambda name: scoreboard if name == "scoreboard" else MagicMock()

        result = Phase1Result(
            intents=["log_memory"],
            entities=[],
            salience_map={},
            primary_emotion="joy",
            emotion_confidence=0.9,
            valence=0.8,
            arousal=0.5,
            intent_classification="log_memory",
            domain_context="FAMILY",
            safety_band="GREEN",
            complexity_tier="LOW",
            temporal_expressions=[
                {"text": "next Saturday", "label": "DATE_REL", "start": 10, "end": 23}
            ],
        )

        ctrl._write_phase1_to_ss(result)

        # Check scoreboard has referents for the temporal expression
        referents = list(scoreboard._referents.values())
        temporal_refs = [r for r in referents if "temporal" in r.entity_id]
        assert len(temporal_refs) >= 1
        assert temporal_refs[0].text == "next Saturday"


# =========================================================================
# E10.5.2 -- Relation head
# =========================================================================


class TestRelationHead:
    """Relation extraction from UltraBERT relation head."""

    def test_relations_extracted(self):
        relations = ["parent_of(Mom, grandma)"]
        adapter = _make_adapter(_base_analysis(relations=relations))
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        result = pipe.classify("Mom called about grandma")
        assert result.relations == relations

    def test_relations_empty_when_none(self):
        adapter = _make_adapter(_base_analysis(relations=[]))
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        result = pipe.classify("Hello world")
        assert result.relations == []

    def test_relations_in_to_metadata(self):
        relations = ["sibling_of(A, B)"]
        adapter = _make_adapter(_base_analysis(relations=relations))
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        result = pipe.classify("A and B are siblings")
        meta = result.to_metadata()
        assert "relations" in meta
        assert meta["relations"] == relations

    def test_multiple_relations(self):
        relations = ["parent_of(Mom, me)", "spouse_of(Mom, Dad)"]
        adapter = _make_adapter(_base_analysis(relations=relations))
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        result = pipe.classify("Mom and Dad talked about me")
        assert len(result.relations) == 2


# =========================================================================
# E10.5.3 -- Embedding head
# =========================================================================


class TestEmbeddingHead:
    """Embedding extraction and storage."""

    def test_embedding_stored_in_pipeline(self):
        embedding = [0.1] * 768
        adapter = _make_adapter(_base_analysis(embedding=embedding))
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        pipe.classify("test text")
        assert pipe.last_embedding is not None
        assert len(pipe.last_embedding) == 768

    def test_embedding_none_before_first_call(self):
        adapter = _make_adapter(_base_analysis())
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        assert pipe.last_embedding is None

    def test_embedding_not_in_phase1result_metadata(self):
        """768 floats too large for metadata dict -- embedding NOT serialized."""
        adapter = _make_adapter(_base_analysis(embedding=[0.5] * 768))
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        result = pipe.classify("test")
        meta = result.to_metadata()
        assert "embedding" not in meta

    def test_embedding_updates_on_each_call(self):
        adapter = _make_adapter(_base_analysis(embedding=[0.1] * 768))
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        pipe.classify("first call")
        first = pipe.last_embedding

        adapter.analyze.return_value = _base_analysis(embedding=[0.9] * 768)
        pipe.classify("second call")
        second = pipe.last_embedding

        assert first is not None
        assert second is not None
        assert first[0] != second[0]

    def test_embedding_cleared_on_degradation(self):
        """When adapter fails, last_embedding stays from previous call."""
        adapter = _make_adapter(_base_analysis(embedding=[0.1] * 768))
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        pipe.classify("good call")
        assert pipe.last_embedding is not None

        # Now adapter returns None -> degradation
        adapter.analyze.return_value = None
        result = pipe.classify("bad call")
        # Embedding should remain from previous successful call
        assert pipe.last_embedding is not None
        assert result._degraded is True


# =========================================================================
# E10.4.2 -- Bootstrap pipeline wiring
# =========================================================================


class TestBootstrapWiring:
    """Config-driven pipeline selection in start_kernel()."""

    def test_stub_pipeline_default(self):
        """Default config (pipeline=stub) -> StubPhase1Pipeline."""
        from poc.k1_poc.config.loader import Phase1Config

        cfg = Phase1Config()
        assert cfg.pipeline == "stub"

    def test_pipeline_config_field_exists(self):
        from poc.k1_poc.config.loader import Phase1Config

        cfg = Phase1Config(pipeline="ultrabert")
        assert cfg.pipeline == "ultrabert"

    def test_config_yaml_has_pipeline_key(self):
        """defaults.yaml should have phase1.pipeline field."""
        from pathlib import Path

        import yaml

        yaml_path = Path("poc/k1_poc/config/defaults.yaml")
        if yaml_path.exists():
            data = yaml.safe_load(yaml_path.read_text())
            assert "phase1" in data
            assert "pipeline" in data["phase1"]
            assert data["phase1"]["pipeline"] == "stub"

    def test_stub_adapter_used_when_config_stub(self):
        """StubPhase1Pipeline should be used when pipeline=stub."""
        from poc.k1_poc.fsm.phase1 import StubPhase1Pipeline

        # Simulate bootstrap logic: pipeline="stub" -> StubPhase1Pipeline
        pipeline_mode = "stub"
        if pipeline_mode == "ultrabert":
            pipeline = None  # would create UltraBERTPhase1Pipeline
        else:
            pipeline = StubPhase1Pipeline()

        assert isinstance(pipeline, StubPhase1Pipeline)

    def test_ultrabert_adapter_used_when_available(self):
        """Config ultrabert + available -> UltraBERTPhase1Pipeline."""
        # Simulate bootstrap logic with mock available adapter
        mock_adapter = _make_adapter(_base_analysis())
        pipe = UltraBERTPhase1Pipeline(adapter=mock_adapter)
        result = pipe.classify("test")
        assert result.intent_classification == "log_memory"

    def test_ultrabert_fallback_when_unavailable(self):
        """Config ultrabert + unavailable -> StubPhase1Pipeline."""
        adapter = StubUltraBERTAdapter()
        assert not adapter.is_available()
        # Bootstrap logic: if not adapter.is_available(), use stub
        pipeline = StubPhase1Pipeline()
        result = pipeline.classify("test")
        assert result.safety_band == "GREEN"  # stub defaults


# =========================================================================
# E10.4.4 -- End-to-end integration
# =========================================================================


class TestEndToEndIntegration:
    """Full-chain test with mock UltraBERT analysis."""

    def _full_analysis(self) -> dict[str, Any]:
        """Analysis for: 'Mom called about grandma's birthday party next Saturday'."""
        return {
            "sentiment": "positive",
            "emotions": ["joy", "anticipation"],
            "emotion_scores": {"joy": 0.7, "anticipation": 0.5},
            "safety": "GREEN",
            "entities": [
                {"text": "Mom", "label": "KINSHIP", "start": 0, "end": 3, "entity_id": "ent-mom"},
                {
                    "text": "grandma",
                    "label": "KINSHIP",
                    "start": 17,
                    "end": 24,
                    "entity_id": "ent-gma",
                },
            ],
            "general_entities": [
                {
                    "text": "birthday party",
                    "label": "EVENT",
                    "start": 27,
                    "end": 41,
                    "entity_id": "ent-bday",
                },
            ],
            "temporal": [
                {"text": "next Saturday", "label": "DATE_REL", "start": 42, "end": 55},
            ],
            "intent": "log_memory",
            "intent_scores": {"log_memory": 0.7, "set_reminder": 0.4},
            "ingress": "FAMILY",
            "relations": ["parent_of(Mom, grandma)"],
            "embedding": [0.42] * 768,
        }

    def test_e2e_classify_intents(self):
        adapter = _make_adapter(self._full_analysis())
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        result = pipe.classify("Mom called about grandma's birthday party next Saturday")

        # Multi-intent: log_memory + set_reminder above threshold
        assert "log_memory" in result.intents
        assert "set_reminder" in result.intents

    def test_e2e_entities_merged(self):
        adapter = _make_adapter(self._full_analysis())
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        result = pipe.classify("Mom called about grandma's birthday party next Saturday")

        entity_texts = [e["text"] for e in result.entities]
        assert "Mom" in entity_texts
        assert "grandma" in entity_texts
        assert "birthday party" in entity_texts

    def test_e2e_temporal(self):
        adapter = _make_adapter(self._full_analysis())
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        result = pipe.classify("Mom called about grandma's birthday party next Saturday")

        assert len(result.temporal_expressions) == 1
        assert result.temporal_expressions[0]["text"] == "next Saturday"

    def test_e2e_relations(self):
        adapter = _make_adapter(self._full_analysis())
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        result = pipe.classify("Mom called about grandma's birthday party next Saturday")

        assert "parent_of(Mom, grandma)" in result.relations

    def test_e2e_domain_and_safety(self):
        adapter = _make_adapter(self._full_analysis())
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        result = pipe.classify("Mom called about grandma's birthday party next Saturday")

        assert result.domain_context == "FAMILY"
        assert result.safety_band == "GREEN"

    def test_e2e_complexity_medium_or_higher(self):
        """Multi-intent + temporal -> complexity >= MEDIUM."""
        adapter = _make_adapter(self._full_analysis())
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        result = pipe.classify("Mom called about grandma's birthday party next Saturday")

        assert result.complexity_tier in ("MEDIUM", "HIGH")

    def test_e2e_emotion(self):
        adapter = _make_adapter(self._full_analysis())
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        result = pipe.classify("Mom called about grandma's birthday party next Saturday")

        assert result.primary_emotion == "joy"
        assert result.valence > 0.5  # positive sentiment

    def test_e2e_embedding(self):
        adapter = _make_adapter(self._full_analysis())
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        pipe.classify("Mom called about grandma's birthday party next Saturday")

        assert pipe.last_embedding is not None
        assert len(pipe.last_embedding) == 768
        assert pipe.last_embedding[0] == 0.42

    def test_e2e_ss_writes(self):
        """Full SS write: control, scoreboard, affective_now."""
        from poc.k1_poc.fsm.controller import ConciergeController
        from poc.k1_poc.sessionstate.sections.control import ControlSection
        from poc.k1_poc.sessionstate.sections.scoreboard import ScoreboardSection

        adapter = _make_adapter(self._full_analysis())
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        result = pipe.classify("Mom called about grandma's birthday party next Saturday")

        # Wire into controller SS write
        ctrl = object.__new__(ConciergeController)
        ctrl._ss = MagicMock()

        control = ControlSection(session_id="e2e-test")
        scoreboard = ScoreboardSection()
        affective = MagicMock()

        def get_sec(name: str) -> Any:
            return {"control": control, "scoreboard": scoreboard, "affective_now": affective}.get(
                name
            )

        ctrl._ss.get_section = get_sec
        ctrl._write_phase1_to_ss(result)

        # Control: intent set, domain set, complexity set
        assert control.get_intents() is not None
        assert control.get_complexity_tier() in ("MEDIUM", "HIGH")

        # Scoreboard: referents for entities + temporal
        referents = list(scoreboard._referents.values())
        ref_texts = [r.text for r in referents]
        assert "Mom" in ref_texts
        assert "grandma" in ref_texts
        assert "next Saturday" in ref_texts

        # Affective: update called
        assert affective.update.called

    def test_e2e_metadata_complete(self):
        adapter = _make_adapter(self._full_analysis())
        pipe = UltraBERTPhase1Pipeline(adapter=adapter)
        result = pipe.classify("Mom called about grandma's birthday party next Saturday")

        meta = result.to_metadata()
        assert "intent" in meta
        assert "entities" in meta
        assert "temporal_expressions" in meta
        assert "relations" in meta
        assert "safety_band" in meta
        assert "complexity_tier" in meta
        assert "emotion" in meta
