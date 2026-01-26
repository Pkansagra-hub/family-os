"""
Shared fusion rules for GAP-007 edge enrichment.

Provides canonical edge keys, weight/confidence fusion, and clamping utilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping


@dataclass
class EdgeSignal:
    """Signal contribution from a single algorithm."""

    algorithm: str
    weight: float
    confidence: float
    properties: dict[str, object] = field(default_factory=dict)


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


def canonical_edge_key(a: str, b: str, directed: bool = False) -> tuple[str, str]:
    """Return canonical edge key for undirected (sorted) or directed pairs."""
    if directed:
        return (a, b)
    return (a, b) if a <= b else (b, a)


def clamp(value: float, min_value: float, max_value: float) -> float:
    """Clamp value to inclusive bounds."""
    return max(min_value, min(max_value, value))


def weighted_sum(values: Iterable[float], weights: Iterable[float] | None = None) -> float:
    """Compute a weighted sum with normalized weights."""
    vals = list(values)
    if not vals:
        return 0.0
    if weights is None:
        return sum(vals) / len(vals)

    wts = list(weights)
    if len(wts) != len(vals):
        raise ValueError("weights must match values length")

    total = sum(wts)
    if total <= 0:
        return sum(vals) / len(vals)

    normalized = [w / total for w in wts]
    return sum(v * w for v, w in zip(vals, normalized))


def fuse_confidences_noisy_or(confidences: Iterable[float]) -> float:
    """Fuse independent confidences using noisy-or."""
    confs = list(confidences)
    if not confs:
        return 0.0

    product = 1.0
    for c in confs:
        product *= 1.0 - clamp(c, 0.0, 1.0)
    return 1.0 - product


def fuse_confidences_mean(confidences: Iterable[float]) -> float:
    """Fuse confidences by mean."""
    confs = list(confidences)
    if not confs:
        return 0.0
    return sum(confs) / len(confs)


def fuse_edge_signals(
    signals: Iterable[EdgeSignal],
    config: EdgeFusionConfig,
) -> tuple[float, float]:
    """Fuse multiple edge signals into a single weight and confidence."""
    sigs = list(signals)
    if not sigs:
        return 0.0, 0.0

    weights = [s.weight for s in sigs]
    confidences = [s.confidence for s in sigs]

    algo_weights = [config.algorithm_weights.get(s.algorithm, 1.0) for s in sigs]

    if config.weight_fusion == "mean":
        fused_weight = weighted_sum(weights)
    else:
        fused_weight = weighted_sum(weights, algo_weights)

    if config.confidence_fusion == "mean":
        fused_confidence = fuse_confidences_mean(confidences)
    else:
        fused_confidence = fuse_confidences_noisy_or(confidences)

    fused_weight = clamp(fused_weight, config.min_weight, config.max_weight)
    fused_confidence = clamp(fused_confidence, config.min_confidence, config.max_confidence)

    return fused_weight, fused_confidence


def algorithm_weight_map_from_config(
    config: EdgeFusionConfig,
) -> Mapping[str, float]:
    """Return algorithm weight map with defaults applied."""
    return dict(config.algorithm_weights)
