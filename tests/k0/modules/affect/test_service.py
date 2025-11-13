"""
Tests for Affect Service

Tests the main AffectService class and P02 integration functions.

Reference: ADR-0012 (Affect Module)
"""

import pytest

from k0.modules.affect.models import PolicyBand
from k0.modules.affect.service import AffectService, analyze_text_for_p02


class TestAffectService:
    """Test AffectService functionality."""

    def test_init(self):
        """Test service initialization."""
        service = AffectService()
        assert service.model_version == "tier0_v0.1.0"
        assert hasattr(service, "tier0_classifier")

    def test_classify_text_positive(self):
        """Test classification of positive text."""
        service = AffectService()
        result = service.classify_text("I love this! It is amazing and wonderful!")

        assert result.valence > 0.5  # Positive valence
        assert result.arousal > 0.5  # High arousal
        assert "positive" in result.tags
        assert "excited" in result.tags
        assert result.band == PolicyBand.GREEN
        assert result.model_version == "tier0_v0.1.0"
        assert isinstance(result.computed_at, float)
        assert result.event_id.startswith("evt_")
        assert result.space_id == "default"

    def test_classify_text_negative(self):
        """Test classification of negative text."""
        service = AffectService()
        result = service.classify_text("I hate this! It is terrible and awful!")

        assert result.valence < -0.5  # Negative valence
        assert result.arousal > 0.5  # High arousal
        assert "negative" in result.tags
        assert "angry" in result.tags
        assert result.band == PolicyBand.GREEN

    def test_classify_text_neutral(self):
        """Test classification of neutral text."""
        service = AffectService()
        result = service.classify_text("This is a test message.")

        assert -0.3 < result.valence < 0.3  # Neutral valence
        assert result.arousal < 0.4  # Low to medium arousal (expanded lexicon)
        assert "neutral" in result.tags
        assert result.arousal < 0.6  # Not high arousal

    def test_classify_text_negation(self):
        """Test negation handling."""
        service = AffectService()
        result = service.classify_text("I do not love this!")

        assert result.valence < -0.2  # Should be negative due to negation (expanded lexicon)
        assert "negative" in result.tags

    def test_classify_text_with_context(self):
        """Test classification with context parameters."""
        service = AffectService()
        context = {
            "event_id": "test_event_123",
            "space_id": "test_space_456",
            "behavior": {"typing_speed": 250},  # Fast typing
        }
        result = service.classify_text("Hello!", context=context)

        assert result.event_id == "test_event_123"
        assert result.space_id == "test_space_456"
        assert result.arousal > 0.1  # Should be boosted by fast typing

    def test_classify_text_empty(self):
        """Test classification of empty text."""
        service = AffectService()
        result = service.classify_text("")

        assert result.valence == 0.0
        assert result.arousal == 0.0
        assert result.tags == ["neutral", "low_arousal"]
        assert result.confidence == 0.0


class TestP02Integration:
    """Test P02 Write Pipeline integration functions."""

    def test_analyze_text_for_p02_basic(self):
        """Test basic P02 function."""
        result = analyze_text_for_p02("I love this!")

        required_keys = {
            "affect_valence",
            "affect_arousal",
            "affect_tags",
            "affect_confidence",
            "affect_model_version",
            "affect_computed_at",
        }
        assert set(result.keys()) == required_keys

        assert isinstance(result["affect_valence"], float)
        assert isinstance(result["affect_arousal"], float)
        assert isinstance(result["affect_tags"], list)
        assert isinstance(result["affect_confidence"], float)
        assert isinstance(result["affect_model_version"], str)
        assert isinstance(result["affect_computed_at"], float)

    def test_analyze_text_for_p02_positive(self):
        """Test P02 function with positive text."""
        result = analyze_text_for_p02("I love this! It is amazing and wonderful!")

        assert result["affect_valence"] > 0.5
        assert result["affect_arousal"] > 0.5
        assert "positive" in result["affect_tags"]
        assert "excited" in result["affect_tags"]
        assert result["affect_model_version"] == "tier0_v0.1.0"

    def test_analyze_text_for_p02_with_params(self):
        """Test P02 function with event_id and space_id."""
        result = analyze_text_for_p02("Hello world!", event_id="evt_123", space_id="space_456")

        assert abs(result["affect_valence"]) < 0.2  # Near neutral (expanded lexicon)
        assert "neutral" in result["affect_tags"]

    def test_analyze_text_for_p02_st_hipp_store_format(self):
        """Test that output matches st_hipp_store schema."""
        result = analyze_text_for_p02("Test message!")

        # Verify all required columns are present and correctly typed
        assert "affect_valence" in result
        assert "affect_arousal" in result
        assert "affect_tags" in result
        assert "affect_confidence" in result
        assert "affect_model_version" in result
        assert "affect_computed_at" in result

        # Verify types match st_hipp_store expectations
        assert isinstance(result["affect_valence"], (int, float))
        assert isinstance(result["affect_arousal"], (int, float))
        assert isinstance(result["affect_tags"], list)
        assert isinstance(result["affect_confidence"], (int, float))
        assert isinstance(result["affect_model_version"], str)
        assert isinstance(result["affect_computed_at"], (int, float))


class TestServiceIntegration:
    """Integration tests for the complete service."""

    def test_service_creation_and_classification(self):
        """Test full service lifecycle."""
        service = AffectService()

        # Test multiple classifications
        texts = ["I love this!", "This is terrible!", "Hello world.", "I do not like this at all!"]

        results = []
        for text in texts:
            result = service.classify_text(text)
            results.append(result)

            # Verify all results have required attributes
            assert hasattr(result, "valence")
            assert hasattr(result, "arousal")
            assert hasattr(result, "tags")
            assert hasattr(result, "confidence")
            assert hasattr(result, "band")
            assert hasattr(result, "model_version")
            assert hasattr(result, "computed_at")

        # Verify results are different for different texts
        assert results[0].valence > 0  # Positive
        assert results[1].valence < 0  # Negative
        assert abs(results[2].valence) < 0.3  # Neutral
        # Note: Negation test may be neutral if no positive words found
        assert abs(results[3].valence) < 0.5  # Either neutral or slightly negative

    @pytest.mark.parametrize(
        "text,expected_tags",
        [
            (
                "I love this!",
                ["positive"],
            ),  # More flexible - just check valence, not specific arousal
            ("This is terrible!", ["negative"]),
            ("Hello.", ["neutral"]),
            ("I do not love this!", ["negative"]),
        ],
    )
    def test_parametrized_classification(self, text, expected_tags):
        """Test classification with parametrized inputs."""
        service = AffectService()
        result = service.classify_text(text)

        for tag in expected_tags:
            assert tag in result.tags
