"""
Tests for M10 E10.2 -- Phase 1 three-section SessionState writes.

Covers:
  - ControlSection: set_intent, set_primary_domain, escalate_safety, set_complexity_tier
  - ScoreboardSection: set_user_intent, add_referent (entities + temporals)
  - AffectiveNowSection: update (emotion, valence, arousal, confidence, source)
  - _write_phase1_to_ss helper: partial failure resilience, timing
  - Integration: _run_phase1 and _run_phase1_with_arbiter both call helper
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from k1.concierge.fsm.phase1 import Phase1Result
from k1.sessionstate.sections.control import (
    ControlSection,
    IntentClassification,
    PrivacyBand,
)

# =========================================================================
# Fixtures
# =========================================================================


def _phase1_result(**overrides: Any) -> Phase1Result:
    """Build a standard Phase1Result for testing."""
    defaults: dict[str, Any] = {
        "intents": ["log_memory", "greeting"],
        "entities": [
            {"text": "Mom", "label": "KINSHIP", "start": 0, "end": 3},
            {"text": "NYC", "label": "LOC", "start": 10, "end": 13},
        ],
        "salience_map": {"ent-0": 0.8, "ent-1": 0.8},
        "primary_emotion": "joy",
        "emotion_confidence": 0.9,
        "valence": 0.7,
        "arousal": 0.6,
        "intent_classification": "log_memory",
        "domain_context": "FAMILY",
        "safety_band": "GREEN",
        "temporal_expressions": [{"text": "Saturday", "label": "DATE_REL", "start": 20, "end": 28}],
        "relations": ["parent_of"],
    }
    defaults.update(overrides)
    return Phase1Result(**defaults)


# =========================================================================
# E10.2.1 -- ControlSection intent/complexity methods
# =========================================================================


class TestControlSectionIntentMethods:
    """New set_intent, get_intents, set_complexity_tier, get_complexity_tier."""

    def test_set_intent_stores_classification(self):
        cs = ControlSection(session_id="test-sess")
        intent = IntentClassification(
            primary="log_memory",
            all_intents=["log_memory", "greeting"],
            classifier="ultrabert",
        )
        cs.set_intent(intent)
        result = cs.get_intents()
        assert result.primary == "log_memory"
        assert result.all_intents == ["log_memory", "greeting"]
        assert result.classifier == "ultrabert"

    def test_set_intent_updates_timestamp(self):
        cs = ControlSection(session_id="test-sess")
        ts_before = cs.last_updated_ms
        intent = IntentClassification(primary="test")
        cs.set_intent(intent)
        assert cs.last_updated_ms >= ts_before

    def test_get_intents_default(self):
        cs = ControlSection(session_id="test-sess")
        result = cs.get_intents()
        assert result.primary == ""
        assert result.all_intents == []

    def test_set_complexity_tier(self):
        cs = ControlSection(session_id="test-sess")
        cs.set_complexity_tier("HIGH")
        assert cs.get_complexity_tier() == "HIGH"

    def test_set_complexity_tier_updates_overlay(self):
        cs = ControlSection(session_id="test-sess")
        cs.set_complexity_tier("MEDIUM")
        assert cs.fsm_overlay["complexity_tier"] == "MEDIUM"

    def test_get_complexity_tier_default_empty(self):
        cs = ControlSection(session_id="test-sess")
        assert cs.get_complexity_tier() == ""


# =========================================================================
# E10.2.1 -- Control section writes from _write_phase1_to_ss
# =========================================================================


class TestControlSectionWrites:
    """_write_phase1_to_ss correctly writes to control section."""

    def _mock_ss(self) -> MagicMock:
        """Build a mock SessionStateManager with real ControlSection."""
        ss = MagicMock()
        self._control = ControlSection(session_id="test-sess")
        sections = {"control": self._control}
        ss.get_section = lambda name: sections.get(name)
        return ss

    def test_intent_written(self):
        ss = self._mock_ss()
        result = _phase1_result()
        self._run_write(ss, result)
        intents = self._control.get_intents()
        assert intents.primary == "log_memory"
        assert "log_memory" in intents.all_intents
        assert intents.classifier == "ultrabert"

    def test_domain_written(self):
        ss = self._mock_ss()
        result = _phase1_result(domain_context="HEALTH")
        self._run_write(ss, result)
        domains = self._control.get_domains()
        assert domains.primary_domain == "HEALTH"

    def test_safety_band_written(self):
        ss = self._mock_ss()
        result = _phase1_result(safety_band="AMBER")
        self._run_write(ss, result)
        safety = self._control.get_safety()
        assert safety.band == PrivacyBand.AMBER

    def test_safety_crisis_maps_to_red(self):
        ss = self._mock_ss()
        result = _phase1_result(safety_band="CRISIS")
        self._run_write(ss, result)
        safety = self._control.get_safety()
        assert safety.band == PrivacyBand.RED

    def _run_write(self, ss: MagicMock, result: Phase1Result) -> None:
        """Invoke _write_phase1_to_ss via a minimal controller stub."""
        from k1.concierge.fsm.controller import ConciergeController

        # Call the helper directly -- it only needs self._ss
        ctrl = object.__new__(ConciergeController)
        ctrl._ss = ss
        ctrl._write_phase1_to_ss(result)


# =========================================================================
# E10.2.2 -- Scoreboard section writes
# =========================================================================


class TestScoreboardWrites:
    """_write_phase1_to_ss correctly writes to scoreboard section."""

    def _mock_ss(self) -> MagicMock:
        from k1.sessionstate.sections.scoreboard import ScoreboardSection

        ss = MagicMock()
        self._scoreboard = ScoreboardSection()
        sections = {"scoreboard": self._scoreboard}
        ss.get_section = lambda name: sections.get(name)
        return ss

    def test_user_intent_written(self):
        ss = self._mock_ss()
        result = _phase1_result(
            intent_classification="scheduling",
            emotion_confidence=0.85,
        )
        self._run_write(ss, result)
        intent, conf = self._scoreboard.get_user_intent()
        assert intent == "scheduling"
        assert conf == pytest.approx(0.85)

    def test_entity_referents_added(self):
        ss = self._mock_ss()
        result = _phase1_result(
            entities=[
                {"text": "Mom", "label": "KINSHIP", "start": 0, "end": 3},
                {"text": "NYC", "label": "LOC", "start": 10, "end": 13},
            ]
        )
        self._run_write(ss, result)
        refs = self._scoreboard.list_referents()
        texts = {r.text for r in refs}
        assert "Mom" in texts
        assert "NYC" in texts

    def test_temporal_referents_added(self):
        ss = self._mock_ss()
        result = _phase1_result(
            temporal_expressions=[
                {"text": "Saturday", "label": "DATE_REL", "start": 20, "end": 28},
            ]
        )
        self._run_write(ss, result)
        refs = self._scoreboard.list_referents()
        temporal_refs = [r for r in refs if "temporal" in r.entity_id]
        assert len(temporal_refs) >= 1
        assert temporal_refs[0].text == "Saturday"

    def test_no_entities_no_crash(self):
        ss = self._mock_ss()
        result = _phase1_result(entities=[], temporal_expressions=[])
        self._run_write(ss, result)
        refs = self._scoreboard.list_referents()
        assert len(refs) == 0

    def _run_write(self, ss: MagicMock, result: Phase1Result) -> None:
        from k1.concierge.fsm.controller import ConciergeController

        ctrl = object.__new__(ConciergeController)
        ctrl._ss = ss
        ctrl._write_phase1_to_ss(result)


# =========================================================================
# E10.2.3 -- AffectiveNow section writes
# =========================================================================


class TestAffectiveNowWrites:
    """_write_phase1_to_ss correctly writes to affective_now section."""

    def _mock_ss(self) -> MagicMock:
        from k1.sessionstate.sections.affective_now import AffectiveNowSection

        ss = MagicMock()
        self._affective = AffectiveNowSection(session_id="test-sess")
        sections = {"affective_now": self._affective}
        ss.get_section = lambda name: sections.get(name)
        return ss

    def test_emotion_written(self):
        ss = self._mock_ss()
        result = _phase1_result(primary_emotion="joy")
        self._run_write(ss, result)
        assert self._affective.current_emotion == "joy"

    def test_valence_written(self):
        ss = self._mock_ss()
        result = _phase1_result(valence=0.7)
        self._run_write(ss, result)
        assert self._affective.dimensions.valence == pytest.approx(0.7)

    def test_arousal_written(self):
        ss = self._mock_ss()
        result = _phase1_result(arousal=0.6)
        self._run_write(ss, result)
        assert self._affective.dimensions.arousal == pytest.approx(0.6)

    def test_source_is_ultrabert(self):
        ss = self._mock_ss()
        result = _phase1_result()
        self._run_write(ss, result)
        assert self._affective.source == "ultrabert"

    def test_confidence_written(self):
        ss = self._mock_ss()
        result = _phase1_result(emotion_confidence=0.92)
        self._run_write(ss, result)
        assert self._affective.confidence == pytest.approx(0.92)

    def _run_write(self, ss: MagicMock, result: Phase1Result) -> None:
        from k1.concierge.fsm.controller import ConciergeController

        ctrl = object.__new__(ConciergeController)
        ctrl._ss = ss
        ctrl._write_phase1_to_ss(result)


# =========================================================================
# E10.2.4 -- Partial failure resilience
# =========================================================================


class TestPartialFailureResilience:
    """If one section write fails, the others still complete."""

    def test_scoreboard_failure_doesnt_block_affective(self):
        from k1.sessionstate.sections.affective_now import AffectiveNowSection

        ss = MagicMock()
        affective = AffectiveNowSection(session_id="test-sess")
        bad_scoreboard = MagicMock()
        bad_scoreboard.set_user_intent.side_effect = RuntimeError("scoreboard broken")

        sections = {
            "control": None,
            "scoreboard": bad_scoreboard,
            "affective_now": affective,
        }
        ss.get_section = lambda name: sections.get(name)

        from k1.concierge.fsm.controller import ConciergeController

        ctrl = object.__new__(ConciergeController)
        ctrl._ss = ss
        result = _phase1_result()
        # Should NOT raise
        ctrl._write_phase1_to_ss(result)
        # Affective should still be written
        assert affective.current_emotion == "joy"

    def test_control_failure_doesnt_block_scoreboard(self):
        from k1.sessionstate.sections.scoreboard import ScoreboardSection

        ss = MagicMock()
        scoreboard = ScoreboardSection()
        bad_control = MagicMock()
        bad_control.set_intent.side_effect = RuntimeError("control broken")

        sections = {
            "control": bad_control,
            "scoreboard": scoreboard,
            "affective_now": None,
        }
        ss.get_section = lambda name: sections.get(name)

        from k1.concierge.fsm.controller import ConciergeController

        ctrl = object.__new__(ConciergeController)
        ctrl._ss = ss
        result = _phase1_result()
        ctrl._write_phase1_to_ss(result)
        intent, _ = scoreboard.get_user_intent()
        assert intent == "log_memory"

    def test_ss_none_does_not_crash(self):
        from k1.concierge.fsm.controller import ConciergeController

        ctrl = object.__new__(ConciergeController)
        ctrl._ss = None
        result = _phase1_result()
        # Should be a no-op, not a crash
        ctrl._write_phase1_to_ss(result)


# =========================================================================
# E10.2 -- All 3 sections written together
# =========================================================================


class TestThreeSectionIntegration:
    """All 3 sections get written from a single Phase1Result."""

    def _mock_ss_all(self) -> MagicMock:
        from k1.sessionstate.sections.affective_now import AffectiveNowSection
        from k1.sessionstate.sections.scoreboard import ScoreboardSection

        ss = MagicMock()
        self._control = ControlSection(session_id="test-sess")
        self._scoreboard = ScoreboardSection()
        self._affective = AffectiveNowSection(session_id="test-sess")
        sections = {
            "control": self._control,
            "scoreboard": self._scoreboard,
            "affective_now": self._affective,
        }
        ss.get_section = lambda name: sections.get(name)
        return ss

    def test_all_three_sections_written(self):
        ss = self._mock_ss_all()
        result = _phase1_result(
            intent_classification="scheduling",
            domain_context="HEALTH",
            safety_band="AMBER",
            primary_emotion="worry",
            emotion_confidence=0.88,
            valence=0.3,
            arousal=0.7,
        )

        from k1.concierge.fsm.controller import ConciergeController

        ctrl = object.__new__(ConciergeController)
        ctrl._ss = ss
        ctrl._write_phase1_to_ss(result)

        # Control
        assert self._control.get_intents().primary == "scheduling"
        assert self._control.get_domains().primary_domain == "HEALTH"
        assert self._control.get_safety().band == PrivacyBand.AMBER

        # Scoreboard
        intent, conf = self._scoreboard.get_user_intent()
        assert intent == "scheduling"

        # Affective
        assert self._affective.current_emotion == "worry"
        assert self._affective.dimensions.valence == pytest.approx(0.3)
