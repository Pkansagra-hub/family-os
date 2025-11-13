"""Tier-1 Enhanced Classifier Implementation.

Ensemble: VADER + TextBlob + ONNX DistilBERT (int8 quantized).

Reference: ADR-0012c (Tier-1 Enhanced Classifier & ONNX)
"""

import logging
from pathlib import Path
from typing import List, Optional, Tuple

try:
    import numpy as np

    numpy_available = True
except ImportError:  # pragma: no cover - numpy is expected in production
    np = None  # type: ignore
    numpy_available = False

try:
    from tokenizers import Tokenizer as HFTokenizer

    tokenizers_available = True
except ImportError:  # pragma: no cover - tokenizer dependency handled via requirements
    HFTokenizer = None  # type: ignore
    tokenizers_available = False

logger = logging.getLogger(__name__)


class Tier1Classifier:
    """
    Tier-1 ensemble classifier with VADER, TextBlob, and ONNX.

    Performance: <60ms P95 latency

    Features:
    - VADER: Rule-based sentiment analysis
    - TextBlob: Pattern-based polarity detection
    - ONNX: Transformer-based affect classification
    - Confidence-weighted ensemble
    - Graceful degradation (8 fallback scenarios)

    Usage:
        classifier = Tier1Classifier()
        valence, arousal, tags, confidence = classifier.classify("I'm really stressed out")
    """

    DEFAULT_MODEL_PATH = Path("k0/modules/affect/resources/models/distilbert_affect_int8.onnx")
    DEFAULT_TOKENIZER_DIR = Path("k0/modules/affect/resources/tokenizers/distilbert_base_uncased")

    def __init__(
        self,
        model_path: Optional[str] = None,
        *,
        tokenizer_dir: Optional[str] = None,
        enable_onnx: bool = True,
        max_length: int = 128,
    ):
        """
        Initialize Tier-1 classifier.

        Args:
            model_path: Optional path to ONNX model (default: distilbert_affect_int8.onnx)
            tokenizer_dir: Optional directory containing DistilBERT tokenizer assets
            enable_onnx: Whether to enable ONNX inference (default: True)
            max_length: Sequence length for tokenizer padding/truncation
        """
        self.model_path = Path(model_path) if model_path else self.DEFAULT_MODEL_PATH
        self.tokenizer_dir = Path(tokenizer_dir) if tokenizer_dir else self.DEFAULT_TOKENIZER_DIR
        self.enable_onnx = enable_onnx
        self.max_length = max_length

        # Component availability flags
        self.vader_available = False
        self.textblob_available = False
        self.onnx_available = False
        self.tokenizer_available = False

        # Lazily initialized component handles
        self.vader = None
        self._textblob_cls = None
        self.tokenizer = None  # type: Optional[object]
        self.onnx_session = None
        self.onnx_output_name = None  # type: Optional[str]

        # Initialize components
        self._init_vader()
        self._init_textblob()
        self._init_tokenizer()
        if enable_onnx:
            self._init_onnx()

        # Model warmup
        self._warmup()

        logger.info(
            f"Tier1Classifier initialized: VADER={self.vader_available}, TextBlob={self.textblob_available}, ONNX={self.onnx_available}"
        )

    def _init_vader(self) -> None:
        """Initialize VADER sentiment analyzer."""
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

            self.vader = SentimentIntensityAnalyzer()
            self.vader_available = True
        except ImportError:
            logger.warning("VADER not available - install vaderSentiment")
            self.vader = None

    def _init_textblob(self) -> None:
        """Initialize TextBlob."""
        try:
            from textblob import TextBlob

            self._textblob_cls = TextBlob
            self.textblob_available = True
        except ImportError:
            logger.warning("TextBlob not available - install textblob")
            self.textblob_available = False

    def _init_tokenizer(self) -> None:
        """Initialize DistilBERT tokenizer for ONNX preprocessing."""
        if not tokenizers_available or HFTokenizer is None:
            logger.warning("tokenizers library not available - install tokenizers")
            self.tokenizer = None
            self.tokenizer_available = False
            return

        tokenizer_path = self.tokenizer_dir / "tokenizer.json"
        if not tokenizer_path.exists():
            logger.warning("Tokenizer file not found at %s", tokenizer_path)
            self.tokenizer = None
            self.tokenizer_available = False
            return

        try:
            tokenizer = HFTokenizer.from_file(str(tokenizer_path))
            tokenizer.enable_truncation(max_length=self.max_length)
            tokenizer.enable_padding(length=self.max_length)
            self.tokenizer = tokenizer
            self.tokenizer_available = True
        except Exception as exc:  # pragma: no cover - depends on external file integrity
            logger.warning("Failed to initialize tokenizer: %s", exc)
            self.tokenizer = None
            self.tokenizer_available = False

    def _init_onnx(self) -> None:
        """Initialize ONNX model."""
        try:
            import onnxruntime as ort

            providers = ort.get_available_providers()
            self.onnx_session = ort.InferenceSession(
                str(self.model_path),
                providers=providers,
            )
            self.onnx_output_name = self.onnx_session.get_outputs()[0].name
            self.onnx_available = True
            logger.info(f"ONNX model loaded from {self.model_path}")
        except ImportError:
            logger.warning("ONNX Runtime not available - install onnxruntime")
            self.onnx_available = False
        except Exception as e:
            logger.warning(f"Failed to load ONNX model: {e}")
            self.onnx_available = False

    def _warmup(self) -> None:
        """Warm up models with dummy inference."""
        try:
            # Warm up VADER
            if self.vader_available and self.vader:
                self.vader.polarity_scores("test")

            # Warm up TextBlob
            if self.textblob_available and self._textblob_cls:
                self._textblob_cls("test").sentiment

            # Warm up ONNX (if available)
            if (
                self.onnx_available
                and self.tokenizer_available
                and numpy_available
                and self.onnx_session
                and self.onnx_output_name
            ):
                dummy_input = {
                    "input_ids": np.zeros((1, self.max_length), dtype=np.int64),
                    "attention_mask": np.zeros((1, self.max_length), dtype=np.int64),
                }
                self.onnx_session.run([self.onnx_output_name], dummy_input)

        except Exception as e:
            logger.warning(f"Model warmup failed: {e}")

    def classify(self, text: str) -> Tuple[float, float, List[str], float]:
        """
        Classify text affect with ensemble.

        Args:
            text: Input text

        Returns:
            (valence, arousal, tags, confidence)
        """
        if not text.strip():
            return 0.0, 0.0, ["neutral", "low_arousal"], 0.0

        # Get predictions from each component
        predictions = []

        # 1. VADER prediction
        vader_result = self._classify_vader(text)
        if vader_result:
            predictions.append(vader_result)

        # 2. TextBlob prediction
        textblob_result = self._classify_textblob(text)
        if textblob_result:
            predictions.append(textblob_result)

        # 3. ONNX prediction
        onnx_result = self._classify_onnx(text)
        if onnx_result:
            predictions.append(onnx_result)

        if not predictions:
            # No components available - fallback to neutral
            logger.warning("No Tier-1 components available, falling back to neutral")
            return 0.0, 0.0, ["neutral", "low_arousal"], 0.0

        # Aggregate predictions with confidence weighting
        valence, arousal, confidence = self._aggregate_predictions(predictions)

        # Generate tags
        tags = self._generate_tags(valence, arousal)

        return valence, arousal, tags, confidence

    def _classify_vader(self, text: str) -> Optional[Tuple[float, float, float]]:
        """
        Classify with VADER.

        Returns:
            (valence, arousal, confidence) or None if unavailable
        """
        if not self.vader_available or not self.vader:
            return None

        try:
            scores = self.vader.polarity_scores(text)
            # VADER compound score → valence (-1 to 1)
            valence = scores["compound"]
            # Estimate arousal from compound + pos/neg difference
            arousal = min(1.0, abs(valence) + 0.2)
            confidence = 0.8  # VADER is generally reliable

            return valence, arousal, confidence
        except Exception as e:
            logger.warning(f"VADER classification failed: {e}")
            return None

    def _classify_textblob(self, text: str) -> Optional[Tuple[float, float, float]]:
        """
        Classify with TextBlob.

        Returns:
            (valence, arousal, confidence) or None if unavailable
        """
        if not (self.textblob_available and self._textblob_cls):
            return None

        try:
            blob = self._textblob_cls(text)
            # TextBlob polarity → valence (-1 to 1)
            valence = blob.sentiment.polarity
            # Subjectivity → arousal estimate
            arousal = min(1.0, blob.sentiment.subjectivity + 0.3)
            confidence = 0.6  # TextBlob is less reliable than VADER

            return valence, arousal, confidence
        except Exception as e:
            logger.warning(f"TextBlob classification failed: {e}")
            return None

    def _classify_onnx(self, text: str) -> Optional[Tuple[float, float, float]]:
        """
        Classify with ONNX model.

        Returns:
            (valence, arousal, confidence) or None if unavailable
        """
        if not (
            self.onnx_available
            and self.tokenizer_available
            and numpy_available
            and self.tokenizer
            and self.onnx_session
            and self.onnx_output_name
        ):
            return None

        try:
            encoding = self.tokenizer.encode(text)
            input_ids = np.array([encoding.ids], dtype=np.int64)
            attention_mask = np.array([encoding.attention_mask], dtype=np.int64)

            inputs = {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
            }

            outputs = self.onnx_session.run([self.onnx_output_name], inputs)
            logits = np.array(outputs[0], dtype=np.float32)
            probs = self._softmax(logits[0])  # type: ignore[arg-type]

            negative_prob = float(probs[0])
            positive_prob = float(probs[1])

            # Map probability difference into [-1, 1]
            valence = max(-1.0, min(1.0, positive_prob - negative_prob))
            # Use confidence-driven arousal heuristic
            arousal = min(1.0, 0.35 + 0.55 * max(positive_prob, negative_prob))
            confidence = max(positive_prob, negative_prob)

            return valence, arousal, confidence
        except Exception as e:
            logger.warning(f"ONNX classification failed: {e}")
            return None

    def _aggregate_predictions(
        self, predictions: List[Tuple[float, float, float]]
    ) -> Tuple[float, float, float]:
        """
        Aggregate predictions with confidence weighting.

        Args:
            predictions: List of (valence, arousal, confidence)

        Returns:
            (valence, arousal, overall_confidence)
        """
        if not predictions:
            return 0.0, 0.0, 0.0

        # Weight predictions by confidence
        total_weight = sum(conf for _, _, conf in predictions)
        if total_weight == 0:
            return 0.0, 0.0, 0.0

        weighted_valence = sum(v * c for v, _, c in predictions) / total_weight
        weighted_arousal = sum(a * c for _, a, c in predictions) / total_weight

        # Overall confidence based on number of components and agreement
        num_components = len(predictions)
        base_confidence = min(1.0, num_components * 0.3)
        agreement_factor = 1.0 - self._calculate_disagreement(predictions)
        overall_confidence = base_confidence * agreement_factor

        return weighted_valence, weighted_arousal, overall_confidence

    def _calculate_disagreement(self, predictions: List[Tuple[float, float, float]]) -> float:
        """
        Calculate disagreement between predictions (0 = perfect agreement, 1 = max disagreement).
        """
        if len(predictions) < 2:
            return 0.0

        valences = [v for v, _, _ in predictions]
        valence_range = max(valences) - min(valences)
        return min(1.0, valence_range / 2.0)  # Normalize to [0, 1]

    @staticmethod
    def _softmax(logits):
        """Numerically stable softmax helper."""
        if not numpy_available:
            raise RuntimeError("NumPy required for softmax computation")

        shifted = logits - np.max(logits)
        exp_scores = np.exp(shifted)
        return exp_scores / np.sum(exp_scores)

    def _generate_tags(self, valence: float, arousal: float) -> List[str]:
        """
        Generate affect tags based on valence and arousal.
        """
        tags = []

        # Valence tags
        if valence > 0.3:
            tags.append("positive")
        elif valence < -0.3:
            tags.append("negative")
        else:
            tags.append("neutral")

        # Arousal tags
        if arousal > 0.6:
            tags.append("high_arousal")
        elif arousal > 0.3:
            tags.append("medium_arousal")
        else:
            tags.append("low_arousal")

        # Specific emotion tags
        if valence > 0.5 and arousal > 0.6:
            tags.append("excited")
        elif valence > 0.5 and arousal < 0.3:
            tags.append("calm")
        elif valence < -0.5 and arousal > 0.6:
            tags.append("angry")
        elif valence < -0.5 and arousal < 0.3:
            tags.append("sad")

        return tags
