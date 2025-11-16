"""Salience Module Types"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class SalienceBand(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class SalienceScore:
    score: float  # 0.0-1.0
    band: SalienceBand
    reasons: List[str]
    social_component: float = 0.0
    affect_component: float = 0.0
    recency_component: float = 0.0
    model_version: str = "salience_v0.1.0"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SalienceConfig:
    social_weight: float = 0.50
    affect_weight: float = 0.40
    recency_weight: float = 0.10
    high_threshold: float = 0.7
    medium_threshold: float = 0.4
    target_latency_ms: int = 5
    emit_metrics: bool = True
    custom_config: Dict[str, Any] = field(default_factory=dict)
    custom_config: Dict[str, Any] = field(default_factory=dict)
    custom_config: Dict[str, Any] = field(default_factory=dict)
