"""
UnifiedDecayEngine — Exponential decay for all 8 memory tables.

Scientific Basis:
- Ebbinghaus (1885): Forgetting curve — memory strength decays exponentially
- Tononi & Cirelli (2006): Synaptic homeostasis hypothesis

Formula: decay_factor = exp(-λ_effective × days_since_last_observed)

Spec Reference:
- Dossier §4.4.1.1: Unified Decay Architecture
- Dossier Appendix C.4.2: Exponential Decay Memory Fading
- M4_EXECUTION.md Issue 4.3.3

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

# =============================================================================
# Constants
# =============================================================================

# Time constants
MS_PER_DAY = 24 * 60 * 60 * 1000  # 86,400,000 ms


# =============================================================================
# Per-Layer λ Values (from Dossier §4.4.1.1)
# =============================================================================

LAYER_LAMBDAS: Dict[str, float] = {
    # Table Name -> Default λ (decay rate per day)
    # Higher λ = faster decay (shorter half-life)
    # Lower λ = slower decay (longer half-life)
    "st_hipp_events": 0.100,  # Short-term buffer, half-life ~7 days
    "st_prospective": 0.020,  # Plans/Goals, half-life ~35 days
    "st_procedural": 0.010,  # Habits/Routines, half-life ~69 days
    "st_kg_edges": 0.008,  # Associations, half-life ~87 days
    "st_epi": 0.005,  # Episodic Memory, half-life ~139 days
    "st_sem": 0.003,  # Semantic Memory, half-life ~231 days
    "st_social": 0.002,  # Social Memory, half-life ~347 days
    "st_kg_dom": 0.001,  # Concepts, half-life ~693 days
}

# Half-life approximation: t_half = ln(2) / λ ≈ 0.693 / λ


# =============================================================================
# Decay Classification
# =============================================================================


class DecayClassification(Enum):
    """
    Decay-based lifecycle state.

    From Dossier §4.4.1.1:
    - ACTIVE: decay_factor >= 0.10 (healthy, actively used)
    - ARCHIVE_CANDIDATE: 0.01 <= decay_factor < 0.10 (weakening, may archive)
    - PRUNE_CANDIDATE: decay_factor < 0.01 (very weak, may tombstone)
    """

    ACTIVE = "ACTIVE"  # decay_factor >= 0.10
    ARCHIVE_CANDIDATE = "ARCHIVE_CANDIDATE"  # 0.01 <= decay_factor < 0.10
    PRUNE_CANDIDATE = "PRUNE_CANDIDATE"  # decay_factor < 0.01


# =============================================================================
# Configuration
# =============================================================================


@dataclass(frozen=True)
class DecayConfig:
    """
    Configuration for decay computation.

    Attributes:
        base_lambda: Default decay rate if table not in LAYER_LAMBDAS
        importance_modifier: How much importance reduces decay (0-1)
        confidence_modifier: How much confidence reduces decay (0-1)
        archive_threshold: Decay factor below which → ARCHIVE_CANDIDATE
        tombstone_threshold: Decay factor below which → PRUNE_CANDIDATE

    From Dossier §4.4.1.1 Configuration:
        P03_DECAY_ARCHIVE_THRESHOLD: 0.10
        P03_DECAY_TOMBSTONE_THRESHOLD: 0.01
        P03_DECAY_IMPORTANCE_MODIFIER: 0.5
        P03_DECAY_CONFIDENCE_MODIFIER: 0.3
    """

    base_lambda: float = 0.01
    importance_modifier: float = 0.5  # High importance decays slower
    confidence_modifier: float = 0.3  # High confidence decays slower
    archive_threshold: float = 0.10  # ACTIVE → ARCHIVE_CANDIDATE
    tombstone_threshold: float = 0.01  # ARCHIVE_CANDIDATE → PRUNE_CANDIDATE

    def validate(self) -> None:
        """Validate configuration."""
        if self.base_lambda <= 0:
            raise ValueError(f"base_lambda must be > 0, got {self.base_lambda}")
        if not 0 <= self.importance_modifier <= 1:
            raise ValueError(
                f"importance_modifier must be in [0, 1], got {self.importance_modifier}"
            )
        if not 0 <= self.confidence_modifier <= 1:
            raise ValueError(
                f"confidence_modifier must be in [0, 1], got {self.confidence_modifier}"
            )
        if self.tombstone_threshold >= self.archive_threshold:
            raise ValueError(
                f"tombstone_threshold ({self.tombstone_threshold}) must be < "
                f"archive_threshold ({self.archive_threshold})"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "base_lambda": self.base_lambda,
            "importance_modifier": self.importance_modifier,
            "confidence_modifier": self.confidence_modifier,
            "archive_threshold": self.archive_threshold,
            "tombstone_threshold": self.tombstone_threshold,
        }


# =============================================================================
# UnifiedDecayEngine Class
# =============================================================================


class UnifiedDecayEngine:
    """
    Unified decay engine for all 8 memory tables.

    Scientific Basis:
    - Ebbinghaus (1885): Forgetting curve — memory strength decays exponentially
    - Tononi & Cirelli (2006): Synaptic homeostasis hypothesis — sleep clears
      weak synapses, strengthens important ones

    Formula:
        decay_factor = exp(-λ_effective × days_since_last_observed)

    Where λ_effective is adjusted by:
        - importance_score (high importance → slower decay)
        - confidence_score (high confidence → slower decay)
        - observation_count (more reinforcement → slower decay)
        - space_modifier (per-space adjustment)
        - entity_type_modifier (per-entity-type adjustment)

    Usage:
        engine = UnifiedDecayEngine()

        # Compute decay factor
        decay = engine.compute_decay_factor(
            table_name='st_epi',
            last_observed_at=1700000000000,  # ms timestamp
            current_time=1705000000000,
            importance_score=0.8,
        )

        # Classify record
        classification = engine.classify_record(decay)
        # → DecayClassification.ACTIVE

    Spec: Dossier §4.4.1.1, Appendix C.4.2
    """

    def __init__(self, config: Optional[DecayConfig] = None):
        """
        Initialize decay engine.

        Args:
            config: Decay configuration. Uses defaults if None.
        """
        self.config = config or DecayConfig()
        self.config.validate()

    def get_base_lambda(self, table_name: str) -> float:
        """
        Get default λ for table.

        From Dossier §4.4.1.1 Per-Layer λ Values:
        - st_hipp_events: 0.100 (fastest decay, short-term buffer)
        - st_kg_dom: 0.001 (slowest decay, core concepts)

        Args:
            table_name: Database table name (e.g., 'st_epi', 'st_sem')

        Returns:
            Base λ value for the table
        """
        return LAYER_LAMBDAS.get(table_name, self.config.base_lambda)

    def get_half_life_days(self, table_name: str) -> float:
        """
        Get approximate half-life in days for a table.

        Half-life = ln(2) / λ ≈ 0.693 / λ

        Args:
            table_name: Database table name

        Returns:
            Half-life in days
        """
        lambda_val = self.get_base_lambda(table_name)
        if lambda_val <= 0:
            return float("inf")
        return 0.693 / lambda_val

    def compute_effective_lambda(
        self,
        table_name: str,
        importance_score: float = 0.0,
        confidence_score: float = 0.0,
        observation_count: int = 1,
        space_modifier: float = 1.0,
        entity_type_modifier: float = 1.0,
    ) -> float:
        """
        Compute decay rate adjusted for importance and reinforcement.

        Formula (from Dossier §4.4.1.1):
            λ_effective = λ_base × space_modifier × entity_type_modifier
                          × importance_factor × confidence_factor × reinforcement_factor

        Where:
            - importance_factor = 1.0 - (importance_score × importance_modifier)
            - confidence_factor = 1.0 - (confidence_score × confidence_modifier)
            - reinforcement_factor = 1.0 / (1.0 + 0.1 × observation_count)

        Args:
            table_name: Database table name for base λ lookup
            importance_score: Importance score [0, 1], higher = slower decay
            confidence_score: Confidence score [0, 1], higher = slower decay
            observation_count: Number of times entity was observed/accessed
            space_modifier: Per-space adjustment factor (default 1.0)
            entity_type_modifier: Per-entity-type adjustment (default 1.0)

        Returns:
            Effective λ value (decay rate per day)
        """
        base = self.get_base_lambda(table_name)

        # Clamp input scores to [0, 1]
        importance_score = max(0.0, min(1.0, importance_score))
        confidence_score = max(0.0, min(1.0, confidence_score))
        observation_count = max(1, observation_count)

        # Importance reduces decay (important memories persist longer)
        # importance_score=1.0 → factor=0.5 (halves λ)
        importance_factor = 1.0 - (importance_score * self.config.importance_modifier)

        # Confidence reduces decay (trusted memories persist longer)
        # confidence_score=1.0 → factor=0.7 (30% reduction)
        confidence_factor = 1.0 - (confidence_score * self.config.confidence_modifier)

        # Observation count reduces decay (reinforced memories persist longer)
        # observation_count=10 → factor=0.5 (halves λ)
        reinforcement_factor = 1.0 / (1.0 + 0.1 * observation_count)

        return (
            base
            * space_modifier
            * entity_type_modifier
            * importance_factor
            * confidence_factor
            * reinforcement_factor
        )

    def compute_decay_factor(
        self,
        table_name: str,
        last_observed_at: int,
        current_time: int,
        importance_score: float = 0.0,
        confidence_score: float = 0.0,
        observation_count: int = 1,
        space_modifier: float = 1.0,
        entity_type_modifier: float = 1.0,
    ) -> float:
        """
        Compute current decay factor.

        Formula:
            decay_factor = exp(-λ_effective × days_since_last_observed)

        Args:
            table_name: Database table name for base λ lookup
            last_observed_at: Timestamp of last observation (ms since epoch)
            current_time: Current timestamp (ms since epoch)
            importance_score: Importance score [0, 1]
            confidence_score: Confidence score [0, 1]
            observation_count: Number of observations/accesses
            space_modifier: Per-space adjustment factor
            entity_type_modifier: Per-entity-type adjustment

        Returns:
            Decay factor in [0.0, 1.0]:
            - 1.0 = freshly observed, no decay
            - 0.0 = completely forgotten
        """
        # Calculate days since last observed
        elapsed_ms = current_time - last_observed_at
        days_since_observed = elapsed_ms / MS_PER_DAY

        # If no time has passed or negative (clock skew), return 1.0
        if days_since_observed <= 0:
            return 1.0

        # Compute effective λ
        effective_lambda = self.compute_effective_lambda(
            table_name=table_name,
            importance_score=importance_score,
            confidence_score=confidence_score,
            observation_count=observation_count,
            space_modifier=space_modifier,
            entity_type_modifier=entity_type_modifier,
        )

        # Apply exponential decay formula
        decay_factor = math.exp(-effective_lambda * days_since_observed)

        # Clamp to [0.0, 1.0]
        return max(0.0, min(1.0, decay_factor))

    def classify_record(self, decay_factor: float) -> DecayClassification:
        """
        Classify record based on decay factor.

        From Dossier §4.4.1.1:
        - ACTIVE: decay_factor >= 0.10
        - ARCHIVE_CANDIDATE: 0.01 <= decay_factor < 0.10
        - PRUNE_CANDIDATE: decay_factor < 0.01

        Args:
            decay_factor: Current decay factor [0, 1]

        Returns:
            DecayClassification enum value
        """
        if decay_factor >= self.config.archive_threshold:
            return DecayClassification.ACTIVE
        elif decay_factor >= self.config.tombstone_threshold:
            return DecayClassification.ARCHIVE_CANDIDATE
        else:
            return DecayClassification.PRUNE_CANDIDATE

    def compute_and_classify(
        self,
        table_name: str,
        last_observed_at: int,
        current_time: int,
        **kwargs: Any,
    ) -> Tuple[float, DecayClassification]:
        """
        Convenience method: compute decay factor and classify.

        Args:
            table_name: Database table name
            last_observed_at: Last observation timestamp (ms)
            current_time: Current timestamp (ms)
            **kwargs: Additional arguments for compute_decay_factor

        Returns:
            Tuple of (decay_factor, classification)
        """
        decay_factor = self.compute_decay_factor(
            table_name=table_name,
            last_observed_at=last_observed_at,
            current_time=current_time,
            **kwargs,
        )
        classification = self.classify_record(decay_factor)
        return (decay_factor, classification)

    def days_until_archive(
        self,
        table_name: str,
        current_decay: float = 1.0,
        importance_score: float = 0.0,
        confidence_score: float = 0.0,
        observation_count: int = 1,
    ) -> float:
        """
        Estimate days until record becomes ARCHIVE_CANDIDATE.

        Useful for UI display: "This memory will fade in ~45 days"

        Args:
            table_name: Database table name
            current_decay: Current decay factor
            importance_score: Importance score
            confidence_score: Confidence score
            observation_count: Observation count

        Returns:
            Estimated days until decay_factor < archive_threshold
        """
        if current_decay < self.config.archive_threshold:
            return 0.0

        effective_lambda = self.compute_effective_lambda(
            table_name=table_name,
            importance_score=importance_score,
            confidence_score=confidence_score,
            observation_count=observation_count,
        )

        if effective_lambda <= 0:
            return float("inf")

        # Solve: archive_threshold = current_decay × exp(-λ × days)
        # days = -ln(archive_threshold / current_decay) / λ
        ratio = self.config.archive_threshold / current_decay
        if ratio >= 1.0:
            return 0.0

        return -math.log(ratio) / effective_lambda

    def get_layer_info(self, table_name: str) -> Dict[str, Any]:
        """
        Get decay information for a table layer.

        Args:
            table_name: Database table name

        Returns:
            Dictionary with layer decay information
        """
        base_lambda = self.get_base_lambda(table_name)
        half_life = self.get_half_life_days(table_name)

        return {
            "table_name": table_name,
            "base_lambda": base_lambda,
            "half_life_days": half_life,
            "archive_threshold": self.config.archive_threshold,
            "tombstone_threshold": self.config.tombstone_threshold,
        }

    def get_all_layers_info(self) -> Dict[str, Dict[str, Any]]:
        """Get decay information for all 8 memory tables."""
        return {table: self.get_layer_info(table) for table in LAYER_LAMBDAS}
