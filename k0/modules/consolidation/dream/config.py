"""
DreamConfig — Configuration for DreamExplorer module.

This module defines the configuration dataclass for M22 DreamExplorer,
controlling depth, creativity, and limits for dream exploration.

References:
- M8_EXECUTION.md Issue 8.1.3: M22 DreamExplorer scaffold
- Dossier §4.6: R5 — Dream-Like Exploration (REM)
- Dossier §7.4.5: M22 — DreamExplorer
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional


@dataclass
class DreamConfig:
    """
    Configuration for DreamExplorer.

    Controls exploration depth, creativity level, and output limits.
    Seed enables deterministic behavior for testing.

    Attributes:
        depth: Maximum hops in knowledge graph traversal (default: 3)
        creativity: Exploration aggressiveness 0=conservative, 1=wild (default: 0.5)
        max_insights: Maximum insights per cycle (default: 10)
        max_counterfactuals: Maximum counterfactual scenarios (default: 5)
        max_prospective_memories: Maximum prospective memories (default: 5)
        max_routine_optimizations: Maximum routine optimizations (default: 5)
        seed: Seed for deterministic randomness (cycle_id for reproducibility)
        min_novelty_score: Minimum novelty threshold for insights (default: 0.3)
        min_confidence: Minimum confidence for outputs (default: 0.5)
        coherence_threshold: Minimum coherence for BGT-SM paths (default: 0.4)
        semantic_distance_threshold: Min distance for novel connections (default: 0.3)
        pmi_threshold: Minimum PMI for significant associations (default: 3.0)
        serendipity_threshold: Min serendipity for surfacing (default: 0.6)
    """

    # Exploration parameters
    depth: int = 3
    creativity: float = 0.5
    seed: Optional[str] = None

    # Output limits
    max_insights: int = 10
    max_counterfactuals: int = 5
    max_prospective_memories: int = 5
    max_routine_optimizations: int = 5

    # Quality thresholds (Issue 8.1.10, M3-E2 cold-start tuning)
    # Cold-start thresholds: novelty 0.5->0.3, semantic 0.7->0.5, PMI 3.0->1.5
    min_novelty_score: float = 0.3  # M3-E2-I3: lowered for cold-start (was 0.5)
    min_confidence: float = 0.5
    coherence_threshold: float = 0.4
    serendipity_threshold: float = 0.6  # Per Issue 8.1.10: serendipity > 0.6

    # BGT-SM parameters (Issue 8.1.9, 8.1.10, GAP-001 M9.1, M3-E2)
    semantic_distance_threshold: float = 0.5  # M3-E2-I1: lowered for cold-start (was 0.7)
    pmi_threshold: float = 1.5  # M3-E2-I2: lowered for cold-start (was 3.0)
    corpus_size_n: int = 10000
    cold_start_threshold: int = 100  # Min corpus for BGT-SM (lowered from 10K)

    # CPN parameters (GAP-001 M9.3)
    cpn_perturbation_std: float = 0.1
    cpn_counterfactual_types: tuple = ("UPWARD", "DOWNWARD", "SEMIFACTUAL")
    cpn_emotional_threshold: float = 0.3  # Min |sentiment| for regret selection

    # MCTS parameters (Issue 8.1.5, 8.1.6)
    mcts_exploration_constant: float = 1.414  # UCT c = sqrt(2)
    mcts_max_rollout_depth: int = 30  # Days of simulation horizon
    mcts_discount_factor: float = 0.9  # Discount for future rewards
    mcts_max_total_rollouts: int = 1000  # Per-cycle budget

    # SPC-UQ parameters
    spc_simulation_count: int = 100
    spc_uncertainty_alpha: float = 1.0
    spc_uncertainty_beta: float = 1.0

    # TDL-HCO parameters
    tdl_learning_rate: float = 0.01
    tdl_discount_factor: float = 0.95

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.depth < 1:
            raise ValueError("depth must be at least 1")
        if not 0.0 <= self.creativity <= 1.0:
            raise ValueError("creativity must be between 0 and 1")
        if self.max_insights < 0:
            raise ValueError("max_insights must be non-negative")
        if self.max_counterfactuals < 0:
            raise ValueError("max_counterfactuals must be non-negative")
        if self.min_novelty_score < 0 or self.min_novelty_score > 1:
            raise ValueError("min_novelty_score must be between 0 and 1")
        if self.min_confidence < 0 or self.min_confidence > 1:
            raise ValueError("min_confidence must be between 0 and 1")

    def derive_seed(self, cycle_id: str, algorithm: str) -> int:
        """
        Derive deterministic seed for a specific algorithm.

        Uses cycle_id + algorithm name to create reproducible seeds
        that differ per algorithm within the same cycle.

        Args:
            cycle_id: Unique cycle identifier (ULID)
            algorithm: Algorithm name (e.g., "cpn", "bgt_sm", "mcts")

        Returns:
            Integer seed for random number generator
        """
        base_seed = self.seed or cycle_id
        combined = f"{base_seed}:{algorithm}"
        hash_bytes = hashlib.sha256(combined.encode()).digest()
        return int.from_bytes(hash_bytes[:8], "big")

    @classmethod
    def from_r5_config(cls, r5_config: "R5Config") -> "DreamConfig":
        """
        Create DreamConfig from R5Config.

        Maps R5 pipeline configuration to DreamExplorer configuration.

        Args:
            r5_config: R5 phase configuration

        Returns:
            DreamConfig instance
        """

        return cls(
            depth=3,  # Default depth
            creativity=0.5,  # Default creativity
            seed=None,  # Set from cycle_id at runtime
            max_insights=r5_config.max_insights_per_batch,
            max_counterfactuals=r5_config.max_counterfactuals_per_event,
            min_novelty_score=0.3,
            min_confidence=0.5,
            coherence_threshold=0.4,
            semantic_distance_threshold=r5_config.bgt_sm_semantic_distance_threshold,
            pmi_threshold=r5_config.bgt_sm_pmi_threshold,
            corpus_size_n=r5_config.bgt_sm_corpus_size_n,
            cold_start_threshold=r5_config.bgt_sm_cold_start_threshold,
            cpn_perturbation_std=r5_config.cpn_perturbation_std,
            cpn_counterfactual_types=r5_config.cpn_counterfactual_types,
            cpn_emotional_threshold=r5_config.cpn_emotional_threshold,
            mcts_exploration_constant=r5_config.mcts_exploration_constant,
            mcts_max_rollout_depth=r5_config.mcts_max_depth,
            mcts_discount_factor=0.9,  # Default
            mcts_max_total_rollouts=1000,  # Per-cycle budget
            spc_simulation_count=r5_config.spc_uq_simulation_count,
            spc_uncertainty_alpha=r5_config.spc_uq_uncertainty_alpha,
            spc_uncertainty_beta=r5_config.spc_uq_uncertainty_beta,
            tdl_learning_rate=r5_config.tdl_hco_learning_rate,
            tdl_discount_factor=r5_config.tdl_hco_discount_factor,
        )
