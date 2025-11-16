"""
Affect Module - Type Definitions

Shared types for affect classification.
Extensible dataclasses allow adding fields without breaking existing code.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AffectBand(str, Enum):
    """Affect intensity band classification"""

    GREEN = "GREEN"  # Low emotional intensity
    AMBER = "AMBER"  # Moderate emotional content
    RED = "RED"  # High emotional intensity
    MIXED = "MIXED"  # Mixed emotions


class EmotionTag(str, Enum):
    """Primary emotion tags (Plutchik's wheel)"""

    JOY = "joy"
    CONTENTMENT = "contentment"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    ANTICIPATION = "anticipation"
    TRUST = "trust"
    NEUTRAL = "neutral"


@dataclass
class AffectAnnotation:
    """
    Affect Classification Output

    Extensible: Add new affect dimensions without breaking existing code.
    """

    valence: float  # -1.0 (negative) to +1.0 (positive)
    arousal: float  # 0.0 (calm) to 1.0 (excited)
    tags: List[str]
    band: AffectBand
    band_reasons: List[str]

    # Extensibility fields
    model_version: str = "affect_v0.1.0"
    confidence: float = 0.0
    computation_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Future fields (examples):
    # dominance: Optional[float] = None  # Control dimension
    # discrete_emotions: Optional[Dict[str, float]] = None  # Multi-label scores
    # cultural_context: Optional[str] = None
    # personalized_delta: Optional[float] = None  # Deviation from user baseline


@dataclass
class AffectConfig:
    """
    Runtime configuration for affect module.

    Loaded from config.yml, can be overridden per-tenant or per-pipeline.
    """

    # Model config
    model_name: str = "distilbert-affect-v1"
    model_path: Optional[str] = None
    quantization: str = "int8"
    device: str = "cpu"

    # Performance config
    target_latency_ms: int = 70
    batch_size: int = 16
    max_memory_mb: int = 20

    # Thresholds
    neutral_threshold: float = 0.1
    high_arousal_threshold: float = 0.7
    emotion_confidence_threshold: float = 0.3

    # Feature flags
    enable_multimodal: bool = False
    enable_personalization: bool = False
    enable_learning_loop: bool = False
    enable_cultural_adaptation: bool = False

    # Fallback
    use_lexicon_fallback: bool = True

    # Observability
    emit_metrics: bool = True
    emit_traces: bool = True
    log_classifications: bool = False

    # Extensibility
    custom_config: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "AffectConfig":
        """Create config from dictionary (loaded from YAML)."""
        return cls(**{k: v for k, v in config.items() if k in cls.__annotations__})
