"""
R4 Configuration — KG Edge Enrichment

Defines configuration dataclasses for GAP-007 edge enrichment algorithms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, cast


@dataclass
class ContextualEdgeConfig:
    """Config for contextual edge algorithm."""

    enabled: bool = True
    similarity_threshold: float = 0.5
    max_edges_per_entity: int = 5
    context_weights: dict[str, float] = field(default_factory=dict)
    relation_type: str = "CONTEXTUALLY_RELATED"

    def __post_init__(self) -> None:
        if not self.context_weights:
            self.context_weights = {
                "location_type": 1.0,
                "social_context": 1.0,
                "time_of_day_bucket": 0.5,
                "sentiment_label": 0.5,
                "ingress_category": 0.8,  # Meaningful UltraBERT 12-class categories
            }


@dataclass
class SemanticSimilarityConfig:
    """Config for semantic similarity edge algorithm."""

    enabled: bool = True
    k_neighbors: int = 10
    similarity_threshold: float = 0.75
    max_edges_per_entity: int = 5
    relation_type: str = "SIMILAR_TO"


@dataclass
class IntentSimilarityConfig:
    """Config for intent similarity edge algorithm."""

    enabled: bool = True
    similarity_threshold: float = 0.5
    max_edges_per_entity: int = 5
    relation_type: str = "INTENT_RELATED"


@dataclass
class EmotionSimilarityConfig:
    """Config for emotion similarity edge algorithm."""

    enabled: bool = True
    similarity_threshold: float = 0.6
    max_edges_per_entity: int = 5
    arousal_weight: float = 0.3  # How much to weight affect_arousal in similarity
    relation_type: str = "EMOTIONALLY_RELATED"


@dataclass
class TemporalProximityConfig:
    """Config for temporal proximity edge algorithm."""

    enabled: bool = True
    window_ms: int = 300_000  # 5 minutes
    tau_ms: int = 60_000  # 1 minute decay constant
    min_weight: float = 0.1
    max_edges_per_entity: int = 10
    relation_type: str = "TEMPORALLY_ASSOCIATED"


@dataclass
class TransitiveClosureConfig:
    """Config for transitive closure edge algorithm."""

    enabled: bool = True
    max_hops: int = 2
    attenuation_factor: float = 0.7
    min_confidence: float = 0.3
    max_edges_per_entity: int = 3
    relation_type: str = "INFERRED_RELATED"


@dataclass
class BayesianCausalConfig:
    """Config for Bayesian causal inference algorithm."""

    enabled: bool = True
    prior_strength: float = 0.1
    min_evidence_count: int = 3
    posterior_threshold: float = 0.6
    relation_type: str = "CAUSES"


@dataclass
class WeightNormalizationConfig:
    """Config for edge weight normalization."""

    enabled: bool = True
    strategy: str = "softmax"  # softmax, sum_to_one, cap
    max_weight: float = 1.0
    min_weight: float = 0.01


@dataclass
class EdgeFusionConfig:
    """Configuration for fusing multiple algorithm signals."""

    weight_fusion: str = "weighted_sum"  # weighted_sum | mean
    confidence_fusion: str = "noisy_or"  # noisy_or | mean
    algorithm_weights: dict[str, float] = field(default_factory=dict)
    min_weight: float = 0.0
    max_weight: float = 1.0
    min_confidence: float = 0.0
    max_confidence: float = 1.0


@dataclass
class EdgeEnrichmentConfig:
    """Master config for all R4 edge enrichment algorithms."""

    semantic_similarity: SemanticSimilarityConfig | None = None
    temporal_proximity: TemporalProximityConfig | None = None
    contextual: ContextualEdgeConfig | None = None
    emotion_similarity: EmotionSimilarityConfig | None = None
    intent_similarity: IntentSimilarityConfig | None = None
    transitive_closure: TransitiveClosureConfig | None = None
    bayesian_causal: BayesianCausalConfig | None = None
    weight_normalization: WeightNormalizationConfig | None = None
    fusion: EdgeFusionConfig | None = None

    # Global settings
    max_total_new_edges_per_cycle: int = 100
    max_total_updates_per_cycle: int = 500

    def __post_init__(self) -> None:
        self.semantic_similarity = self.semantic_similarity or SemanticSimilarityConfig()
        self.temporal_proximity = self.temporal_proximity or TemporalProximityConfig()
        self.contextual = self.contextual or ContextualEdgeConfig()
        self.emotion_similarity = self.emotion_similarity or EmotionSimilarityConfig()
        self.intent_similarity = self.intent_similarity or IntentSimilarityConfig()
        self.transitive_closure = self.transitive_closure or TransitiveClosureConfig()
        self.bayesian_causal = self.bayesian_causal or BayesianCausalConfig()
        self.weight_normalization = self.weight_normalization or WeightNormalizationConfig()
        self.fusion = self.fusion or EdgeFusionConfig()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EdgeEnrichmentConfig":
        """Create config from a dict (e.g., YAML/env-parsed config)."""
        semantic_similarity_data = cast(Mapping[str, Any], data.get("semantic_similarity", {}))
        temporal_proximity_data = cast(Mapping[str, Any], data.get("temporal_proximity", {}))
        contextual_data = cast(Mapping[str, Any], data.get("contextual", {}))
        emotion_similarity_data = cast(Mapping[str, Any], data.get("emotion_similarity", {}))
        intent_similarity_data = cast(Mapping[str, Any], data.get("intent_similarity", {}))
        transitive_closure_data = cast(Mapping[str, Any], data.get("transitive_closure", {}))
        bayesian_causal_data = cast(Mapping[str, Any], data.get("bayesian_causal", {}))
        weight_normalization_data = cast(Mapping[str, Any], data.get("weight_normalization", {}))
        fusion_data = cast(Mapping[str, Any], data.get("fusion", {}))

        return cls(
            semantic_similarity=(
                SemanticSimilarityConfig(**semantic_similarity_data)
                if data.get("semantic_similarity") is not None
                else None
            ),
            temporal_proximity=(
                TemporalProximityConfig(**temporal_proximity_data)
                if data.get("temporal_proximity") is not None
                else None
            ),
            contextual=(
                ContextualEdgeConfig(**contextual_data)
                if data.get("contextual") is not None
                else None
            ),
            emotion_similarity=(
                EmotionSimilarityConfig(**emotion_similarity_data)
                if data.get("emotion_similarity") is not None
                else None
            ),
            intent_similarity=(
                IntentSimilarityConfig(**intent_similarity_data)
                if data.get("intent_similarity") is not None
                else None
            ),
            transitive_closure=(
                TransitiveClosureConfig(**transitive_closure_data)
                if data.get("transitive_closure") is not None
                else None
            ),
            bayesian_causal=(
                BayesianCausalConfig(**bayesian_causal_data)
                if data.get("bayesian_causal") is not None
                else None
            ),
            weight_normalization=(
                WeightNormalizationConfig(**weight_normalization_data)
                if data.get("weight_normalization") is not None
                else None
            ),
            fusion=(EdgeFusionConfig(**fusion_data) if data.get("fusion") is not None else None),
            max_total_new_edges_per_cycle=int(data.get("max_total_new_edges_per_cycle", 100)),
            max_total_updates_per_cycle=int(data.get("max_total_updates_per_cycle", 500)),
        )


__all__ = [
    "SemanticSimilarityConfig",
    "TemporalProximityConfig",
    "ContextualEdgeConfig",
    "EmotionSimilarityConfig",
    "TransitiveClosureConfig",
    "BayesianCausalConfig",
    "WeightNormalizationConfig",
    "EdgeFusionConfig",
    "EdgeEnrichmentConfig",
]
