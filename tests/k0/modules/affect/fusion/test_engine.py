"""Tests for FusionEngine (ADR-0012d)."""

import time

import pytest

from k0.modules.affect.fusion import FusionEngine
from k0.modules.affect.models import CalibrationParams, ModalityScore, ModalitySource


@pytest.fixture
def fusion_engine():
    """Default fusion engine for tests."""
    engine = FusionEngine()
    engine.clear_cache()
    return engine


def _score(valence: float, arousal: float, confidence: float, source: str = "tier1"):
    return ModalityScore(
        valence=valence,
        arousal=arousal,
        confidence=confidence,
        source=ModalitySource(source),
    )


class TestFusionEngineFusion:
    def test_confidence_weighted_fusion(self, fusion_engine):
        scores = [_score(0.6, 0.5, 0.9, "tier1"), _score(0.2, 0.7, 0.4, "tier0")]

        valence, arousal, confidence, attribution = fusion_engine._fuse_modalities(scores)

        expected_valence = (0.6 * 0.9 + 0.2 * 0.4) / (0.9 + 0.4)
        expected_arousal = (0.5 * 0.9 + 0.7 * 0.4) / (0.9 + 0.4)

        assert pytest.approx(valence, rel=1e-4) == expected_valence
        assert pytest.approx(arousal, rel=1e-4) == expected_arousal
        assert pytest.approx(confidence, rel=1e-4) == (0.9 + 0.4) / 2
        assert "tier1_valence" in attribution
        assert "tier0_arousal" in attribution


class TestFusionEngineEMA:
    def test_fuse_and_smooth_updates_ema(self, fusion_engine):
        scores = [
            {"valence": 0.8, "arousal": 0.7, "confidence": 0.9, "source": "tier1"},
        ]

        v1, a1, _, _ = fusion_engine.fuse_and_smooth(
            person_id="person", space_id="space", modality_scores=scores
        )
        v2, a2, _, _ = fusion_engine.fuse_and_smooth(
            person_id="person", space_id="space", modality_scores=scores
        )

        assert v2 > v1
        assert a2 > a1
        state, _ = fusion_engine._ema_cache[("person", "space")]
        assert state.n_observations == 2

    def test_cache_expiration_creates_new_state(self):
        engine = FusionEngine(cache_ttl_seconds=0.01)
        scores = [
            {"valence": 0.3, "arousal": 0.4, "confidence": 1.0, "source": "tier0"},
        ]

        engine.fuse_and_smooth(person_id="p", space_id="s", modality_scores=scores)
        first_state, _ = engine._ema_cache[("p", "s")]

        time.sleep(0.02)
        engine.fuse_and_smooth(person_id="p", space_id="s", modality_scores=scores)
        second_state, _ = engine._ema_cache[("p", "s")]

        assert id(first_state) != id(second_state)
        assert second_state.n_observations == 1


class TestFusionEngineCalibration:
    def test_calibration_bias_and_temperature(self, fusion_engine):
        params = CalibrationParams(
            person_id="person",
            valence_bias=0.2,
            arousal_bias=0.1,
            valence_temp=1.1,
            arousal_temp=0.9,
            alpha_fast=0.6,
            n_feedback_samples=5,
            last_updated=time.time(),
        )
        fusion_engine.update_calibration_params(params)

        scores = [
            {"valence": 0.1, "arousal": 0.2, "confidence": 0.8, "source": "tier1"},
        ]

        valence, arousal, _, attribution = fusion_engine.fuse_and_smooth(
            person_id="person", space_id="space", modality_scores=scores
        )

        assert valence > 0.1  # Bias + temperature raise valence
        assert arousal > 0.2  # Bias raises arousal even with <1 temp
        assert attribution["calibration_valence_bias"] == pytest.approx(0.2)
        assert attribution["calibration_arousal_temp"] == pytest.approx(0.9)


class TestFusionEngineTrend:
    def test_trend_detection(self, fusion_engine):
        positive = [
            {"valence": 0.9, "arousal": 0.7, "confidence": 1.0, "source": "tier1"},
        ]
        negative = [
            {"valence": -0.9, "arousal": 0.2, "confidence": 1.0, "source": "tier1"},
        ]

        fusion_engine.fuse_and_smooth(person_id="p", space_id="s", modality_scores=positive)
        fusion_engine.fuse_and_smooth(person_id="p", space_id="s", modality_scores=negative)

        trend_label, magnitude = fusion_engine.get_trend("p", "s")

        assert "valence_declining" in trend_label
        assert magnitude > 0


class TestFusionEngineValidation:
    def test_invalid_modality_scores_are_ignored(self, fusion_engine):
        scores = [
            {"valence": 0.4, "arousal": 0.4, "confidence": 0.7, "source": "tier0"},
            {"invalid": True},
        ]

        valence, arousal, confidence, _ = fusion_engine.fuse_and_smooth(
            person_id="person", space_id="space", modality_scores=scores
        )

        assert valence != 0.0  # valid score processed
        assert confidence > 0.0
        assert arousal >= 0.0
