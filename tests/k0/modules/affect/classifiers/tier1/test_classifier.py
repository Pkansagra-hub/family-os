"""Tests for Tier-1 Enhanced Classifier (ADR-0012c)."""

import importlib.util
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from k0.modules.affect.classifiers.tier1.classifier import Tier1Classifier

MODEL_PATH = Path("k0/modules/affect/resources/models/distilbert_affect_int8.onnx")
TOKENIZER_DIR = Path("k0/modules/affect/resources/tokenizers/distilbert_base_uncased")

ONNXRUNTIME_AVAILABLE = importlib.util.find_spec("onnxruntime") is not None

HAS_FULL_ONNX = ONNXRUNTIME_AVAILABLE and MODEL_PATH.exists() and TOKENIZER_DIR.exists()


@pytest.fixture
def classifier_no_onnx():
    """Tier-1 classifier with ONNX disabled for faster unit tests."""
    return Tier1Classifier(enable_onnx=False)


class TestTier1Classifier:
    """Test Tier-1 classifier functionality."""

    def test_init_default(self, classifier_no_onnx):
        """Test default initialization."""
        classifier = classifier_no_onnx
        assert hasattr(classifier, "vader_available")
        assert hasattr(classifier, "textblob_available")
        assert hasattr(classifier, "onnx_available")

    def test_init_with_model_path(self):
        """Test initialization with custom model path."""
        classifier = Tier1Classifier(
            model_path="/custom/path/model.onnx",
            enable_onnx=False,
        )
        assert classifier.model_path == Path("/custom/path/model.onnx")

    def test_init_disable_onnx(self):
        """Test initialization with ONNX disabled."""
        classifier = Tier1Classifier(enable_onnx=False)
        assert not classifier.enable_onnx
        assert not classifier.onnx_available

    def test_vader_available(self):
        """Real VADER should be available when dependency is installed."""
        classifier = Tier1Classifier(enable_onnx=False)
        assert classifier.vader_available
        assert classifier.vader is not None

    def test_vader_unavailable(self):
        """Test VADER initialization when unavailable."""
        with patch.dict(
            "sys.modules", {"vaderSentiment": None, "vaderSentiment.vaderSentiment": None}
        ):
            classifier = Tier1Classifier()
            assert not classifier.vader_available
            assert classifier.vader is None

    def test_textblob_available(self, classifier_no_onnx):
        """Test TextBlob availability flag."""
        assert isinstance(classifier_no_onnx.textblob_available, bool)

    @pytest.mark.skipif(
        not HAS_FULL_ONNX,
        reason="Quantized DistilBERT ONNX assets not available",
    )
    def test_onnx_inference_positive_text(self):
        """End-to-end ONNX inference should yield positive valence for positive text."""
        classifier = Tier1Classifier()

        valence, arousal, tags, confidence = classifier.classify("I absolutely love this!")

        assert classifier.onnx_available
        assert valence > 0.2
        assert arousal >= 0.35
        assert confidence > 0.4
        assert "positive" in tags

    @pytest.mark.skipif(
        not HAS_FULL_ONNX,
        reason="Quantized DistilBERT ONNX assets not available",
    )
    def test_onnx_inference_negative_text(self):
        """Negative text should yield negative valence when ONNX is active."""
        classifier = Tier1Classifier()

        valence, arousal, tags, confidence = classifier.classify("This is absolutely horrible")

        assert classifier.onnx_available
        assert valence < -0.2
        assert confidence > 0.4
        assert "negative" in tags

    def test_classify_empty_text(self, classifier_no_onnx):
        """Test classification of empty text."""
        valence, arousal, tags, confidence = classifier_no_onnx.classify("")

        assert valence == 0.0
        assert arousal == 0.0
        assert tags == ["neutral", "low_arousal"]
        assert confidence == 0.0

    def test_classify_whitespace_text(self, classifier_no_onnx):
        """Test classification of whitespace-only text."""
        valence, arousal, tags, confidence = classifier_no_onnx.classify("   ")

        assert valence == 0.0
        assert arousal == 0.0
        assert tags == ["neutral", "low_arousal"]
        assert confidence == 0.0

    def test_classify_with_vader_only(self):
        """Test classification with only VADER available."""
        classifier = Tier1Classifier(enable_onnx=False)
        mock_vader = Mock()
        mock_vader.polarity_scores.return_value = {
            "neg": 0.1,
            "neu": 0.2,
            "pos": 0.7,
            "compound": 0.8,
        }
        classifier.vader = mock_vader
        classifier.vader_available = True
        classifier.textblob_available = False
        classifier.tokenizer_available = False
        classifier.onnx_available = False

        valence, arousal, tags, confidence = classifier.classify("I love this!")

        assert valence > 0
        assert arousal > 0
        assert "positive" in tags
        assert confidence > 0

    def test_classify_no_components_available(self):
        """Test classification when no components are available."""
        # Mock all components as unavailable
        with patch.dict(
            "sys.modules",
            {"vaderSentiment": None, "vaderSentiment.vaderSentiment": None, "textblob": None},
        ):
            with patch(
                "k0.modules.affect.classifiers.tier1.classifier.Tier1Classifier._init_onnx"
            ) as mock_onnx:
                mock_onnx.return_value = None
                classifier = Tier1Classifier(enable_onnx=False)

                valence, arousal, tags, confidence = classifier.classify("Some text")

                # Should return neutral when no components available
                assert valence == 0.0
                assert arousal == 0.0
                assert tags == ["neutral", "low_arousal"]
                assert confidence == 0.0

    def test_aggregate_predictions_single(self, classifier_no_onnx):
        """Test prediction aggregation with single prediction."""
        predictions = [(0.5, 0.6, 0.8)]  # valence, arousal, confidence

        valence, arousal, confidence = classifier_no_onnx._aggregate_predictions(predictions)

        assert valence == 0.5
        assert arousal == 0.6
        assert confidence > 0

    def test_aggregate_predictions_multiple(self, classifier_no_onnx):
        """Test prediction aggregation with multiple predictions."""
        predictions = [
            (0.5, 0.6, 0.8),  # High confidence positive
            (0.3, 0.4, 0.6),  # Medium confidence positive
        ]

        valence, arousal, confidence = classifier_no_onnx._aggregate_predictions(predictions)

        # Should be weighted average
        expected_valence = (0.5 * 0.8 + 0.3 * 0.6) / (0.8 + 0.6)
        expected_arousal = (0.6 * 0.8 + 0.4 * 0.6) / (0.8 + 0.6)

        assert abs(valence - expected_valence) < 0.01
        assert abs(arousal - expected_arousal) < 0.01
        assert confidence > 0

    def test_calculate_disagreement(self, classifier_no_onnx):
        """Test disagreement calculation."""

        # Perfect agreement
        predictions = [(0.5, 0.6, 0.8), (0.5, 0.6, 0.8)]
        disagreement = classifier_no_onnx._calculate_disagreement(predictions)
        assert disagreement == 0.0

        # Maximum disagreement
        predictions = [(1.0, 0.6, 0.8), (-1.0, 0.6, 0.8)]
        disagreement = classifier_no_onnx._calculate_disagreement(predictions)
        assert disagreement == 1.0

    def test_generate_tags_positive_high_arousal(self, classifier_no_onnx):
        """Test tag generation for positive high arousal."""
        tags = classifier_no_onnx._generate_tags(0.8, 0.8)

        assert "positive" in tags
        assert "high_arousal" in tags
        assert "excited" in tags

    def test_generate_tags_negative_low_arousal(self, classifier_no_onnx):
        """Test tag generation for negative low arousal."""
        tags = classifier_no_onnx._generate_tags(-0.8, 0.2)

        assert "negative" in tags
        assert "low_arousal" in tags
        assert "sad" in tags

    def test_generate_tags_neutral(self, classifier_no_onnx):
        """Test tag generation for neutral affect."""
        tags = classifier_no_onnx._generate_tags(0.0, 0.4)

        assert "neutral" in tags
        assert "medium_arousal" in tags


class TestTier1ClassifierIntegration:
    """Integration tests for Tier-1 classifier."""

    def test_classifier_creation_and_basic_classification(self):
        """Test full classifier lifecycle."""
        classifier = Tier1Classifier(enable_onnx=False)  # Disable ONNX for testing

        # Test multiple classifications
        texts = ["I love this!", "This is terrible!", "Hello world.", "I am so excited!"]

        for text in texts:
            valence, arousal, tags, confidence = classifier.classify(text)

            # Basic validation
            assert isinstance(valence, float)
            assert isinstance(arousal, float)
            assert isinstance(tags, list)
            assert isinstance(confidence, float)

            # Range checks
            assert -1.0 <= valence <= 1.0
            assert 0.0 <= arousal <= 1.0
            assert 0.0 <= confidence <= 1.0

            # Tag validation
            assert len(tags) >= 2  # At least valence and arousal tags

    @pytest.mark.parametrize(
        "text,expected_valence_range",
        [
            ("I love this!", (0.5, 1.0)),  # Should be positive
            ("This is terrible!", (-1.0, -0.3)),  # Should be negative
            ("Hello world.", (-0.2, 0.2)),  # Should be neutral
        ],
    )
    def test_parametrized_classification(self, text, expected_valence_range):
        """Test classification with parametrized inputs."""
        classifier = Tier1Classifier(enable_onnx=False)

        valence, arousal, tags, confidence = classifier.classify(text)

        min_val, max_val = expected_valence_range
        assert min_val <= valence <= max_val


@pytest.mark.skipif(
    not HAS_FULL_ONNX,
    reason="Quantized DistilBERT ONNX assets not available",
)
class TestTier1ClassifierOnnxIntegration:
    """Integration tests that require the real ONNX runtime pipeline."""

    def test_positive_vs_negative_split(self):
        classifier = Tier1Classifier()

        positive = classifier.classify("We had a wonderful celebration tonight!")
        negative = classifier.classify("I am devastated and extremely upset.")

        assert positive[0] > negative[0]
        assert positive[1] >= 0.35
        assert negative[0] < 0
        assert negative[3] > 0.3
