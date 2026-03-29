"""
R5 Configuration — Execution mode control for Dream Phase.

This module implements R5 execution mode control as specified in
docs/TEMP_EXECUTION_DOCS/M8_EXECUTION.md Issue 8.1.1.

Modes:
- DISABLED: R5 skipped completely (MVP default)
- SHADOW: R5 runs but outputs are discarded, metrics collected
- ENABLED_LOW: R5 runs with reduced rollouts (10 per decision)
- ENABLED: R5 runs with full rollouts (100 per decision)

References:
- M8_EXECUTION.md Issue 8.1.1: R5 execution mode control
- Dossier §4.6.0: MVP Strategy (mode control, rollout phases)
- Dossier §4.6.7: R5 Complexity Assessment

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class R5Mode(str, Enum):
    """
    R5 execution modes for gradual rollout.

    Modes map to numeric values for metrics gauge:
    - DISABLED = 0: Skip R5 entirely (MVP default)
    - SHADOW = 1: Execute but discard outputs, collect metrics
    - ENABLED_LOW = 2: Execute with reduced rollouts (10 per decision)
    - ENABLED = 3: Execute with full rollouts (100 per decision)
    """

    DISABLED = "disabled"
    SHADOW = "shadow"
    ENABLED_LOW = "enabled_low"
    ENABLED = "enabled"

    @property
    def mode_value(self) -> int:
        """Return numeric value for metrics gauge."""
        mode_map = {
            R5Mode.DISABLED: 0,
            R5Mode.SHADOW: 1,
            R5Mode.ENABLED_LOW: 2,
            R5Mode.ENABLED: 3,
        }
        return mode_map[self]

    @property
    def is_active(self) -> bool:
        """Return True if R5 should execute (not DISABLED)."""
        return self != R5Mode.DISABLED

    @property
    def is_shadow(self) -> bool:
        """Return True if running in shadow mode (outputs discarded)."""
        return self == R5Mode.SHADOW


# =============================================================================
# ROLLOUT CONFIGURATION
# =============================================================================

# MCTS rollout counts per mode (from dossier §4.6.0, §4.6.2.1)
ROLLOUTS_PER_MODE = {
    R5Mode.DISABLED: 0,
    R5Mode.SHADOW: 100,  # Full rollouts for shadow validation
    R5Mode.ENABLED_LOW: 10,  # Reduced rollouts for conservative rollout
    R5Mode.ENABLED: 100,  # Full rollouts for production
}

# Skip thresholds (from dossier §4.6.7, Issue 8.1.2)
DEFAULT_BACKLOG_THRESHOLD = 1000  # Skip R5 if pending > threshold
DEFAULT_REMAINING_WINDOW_SECONDS = 60  # Skip R5 if remaining < threshold


# =============================================================================
# R5 CONFIGURATION DATACLASS
# =============================================================================


@dataclass
class R5Config:
    """
    Configuration for R5 Dream Exploration phase.

    Attributes:
        mode: R5 execution mode (disabled/shadow/enabled_low/enabled)
        backlog_threshold: Skip R5 if pending events exceed this count
        min_remaining_window_seconds: Skip R5 if remaining window < this
        mcts_rollouts_override: Override MCTS rollouts (None uses mode default)
        max_counterfactuals_per_event: Max counterfactuals to generate per event
        max_insights_per_batch: Max insights per consolidation batch
        cpn_perturbation_std: Standard deviation for CPN perturbations
        bgt_sm_semantic_distance_threshold: Min semantic distance for insights
        bgt_sm_pmi_threshold: Min PMI for concept connections
        spc_uq_uncertainty_alpha: Alpha parameter for SPC-UQ Beta distribution
        spc_uq_uncertainty_beta: Beta parameter for SPC-UQ Beta distribution
        tdl_hco_learning_rate: TD learning rate for motor rehearsal
        tdl_hco_discount_factor: Discount factor for future rewards
        enable_shadow_validation: Enable heuristic vs MCTS comparison
    """

    # Execution mode
    mode: R5Mode = R5Mode.DISABLED  # MVP default: R5 disabled

    # Skip thresholds (Issue 8.1.2)
    backlog_threshold: int = DEFAULT_BACKLOG_THRESHOLD
    min_remaining_window_seconds: int = DEFAULT_REMAINING_WINDOW_SECONDS

    # MCTS configuration (Issue 8.1.5, 8.1.6)
    mcts_rollouts_override: Optional[int] = None
    mcts_exploration_constant: float = 1.414  # UCT c = sqrt(2)
    mcts_max_depth: int = 10
    mcts_early_termination_threshold: float = 0.95  # Converge if best action prob > 95%

    # CPN configuration (Issue 8.1.4, GAP-001 M9.3)
    max_counterfactuals_per_event: int = 5
    cpn_perturbation_std: float = 0.1
    cpn_counterfactual_types: tuple = ("UPWARD", "DOWNWARD", "SEMIFACTUAL")
    cpn_emotional_threshold: float = 0.3  # Min |sentiment| for regret selection (lowered from 0.6)

    # BGT-SM configuration (Issue 8.1.9, 8.1.10, GAP-001 M9.1)
    max_insights_per_batch: int = 10
    bgt_sm_semantic_distance_threshold: float = 0.3  # Min distance for novel connection
    bgt_sm_pmi_threshold: float = 2.0  # Min PMI for significant association
    bgt_sm_corpus_size_n: int = 10000  # Corpus size N for PMI calculation
    bgt_sm_cold_start_threshold: int = 100  # Min corpus for BGT-SM (lowered from 10K)

    # Accumulated KG limits (GAP-001 M9.2)
    # Limits for loading accumulated KG entities/edges for R5 dream algorithms
    accumulated_kg_entity_limit: int = 1000  # Max entities to load for BGT-SM
    accumulated_kg_edge_limit: int = 5000  # Max edges to load for graph traversal

    # Accumulated Episode/Routine limits (R5 Parity Resolution)
    # Limits for loading accumulated episodes/routines for R5 dream algorithms
    accumulated_episode_limit: int = 100  # Max episodes to load for RoutineDetector/CPN
    accumulated_routine_limit: int = 50  # Max routines to load for TDL-HCO

    # SPC-UQ configuration (Issue 8.1.8)
    spc_uq_uncertainty_alpha: float = 1.0  # Beta distribution alpha
    spc_uq_uncertainty_beta: float = 1.0  # Beta distribution beta (uniform prior)
    spc_uq_simulation_count: int = 100

    # TDL-HCO configuration (Issue 8.1.11)
    tdl_hco_learning_rate: float = 0.01
    tdl_hco_discount_factor: float = 0.95
    tdl_hco_eligibility_trace_decay: float = 0.9

    # Shadow validation (Issue 8.1.14)
    enable_shadow_validation: bool = True

    @property
    def effective_rollouts(self) -> int:
        """Get effective MCTS rollouts based on mode or override."""
        if self.mcts_rollouts_override is not None:
            return self.mcts_rollouts_override
        return ROLLOUTS_PER_MODE.get(self.mode, 0)

    @property
    def should_execute(self) -> bool:
        """Return True if R5 should execute based on mode."""
        return self.mode.is_active

    @property
    def should_persist_outputs(self) -> bool:
        """Return True if R5 outputs should be persisted (not shadow mode)."""
        return self.mode.is_active and not self.mode.is_shadow

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.backlog_threshold < 0:
            raise ValueError("backlog_threshold must be non-negative")
        if self.min_remaining_window_seconds < 0:
            raise ValueError("min_remaining_window_seconds must be non-negative")
        if self.mcts_rollouts_override is not None and self.mcts_rollouts_override < 0:
            raise ValueError("mcts_rollouts_override must be non-negative")
        if self.max_counterfactuals_per_event < 0:
            raise ValueError("max_counterfactuals_per_event must be non-negative")
        if self.max_insights_per_batch < 0:
            raise ValueError("max_insights_per_batch must be non-negative")

    @classmethod
    def from_dict(cls, config: dict) -> "R5Config":
        """Create R5Config from dictionary (e.g., from P03Settings)."""
        mode_str = config.get("r5_mode", "disabled")
        try:
            mode = R5Mode(mode_str)
        except ValueError:
            mode = R5Mode.DISABLED

        return cls(
            mode=mode,
            backlog_threshold=config.get("r5_backlog_threshold", DEFAULT_BACKLOG_THRESHOLD),
            min_remaining_window_seconds=config.get(
                "r5_min_remaining_window_seconds", DEFAULT_REMAINING_WINDOW_SECONDS
            ),
            mcts_rollouts_override=config.get("r5_mcts_rollouts_override"),
            mcts_exploration_constant=config.get("r5_mcts_exploration_constant", 1.414),
            mcts_max_depth=config.get("r5_mcts_max_depth", 10),
            mcts_early_termination_threshold=config.get(
                "r5_mcts_early_termination_threshold", 0.95
            ),
            max_counterfactuals_per_event=config.get("r5_max_counterfactuals_per_event", 5),
            cpn_perturbation_std=config.get("r5_cpn_perturbation_std", 0.1),
            max_insights_per_batch=config.get("r5_max_insights_per_batch", 10),
            bgt_sm_semantic_distance_threshold=config.get(
                "r5_bgt_sm_semantic_distance_threshold", 0.3
            ),
            bgt_sm_pmi_threshold=config.get("r5_bgt_sm_pmi_threshold", 2.0),
            bgt_sm_corpus_size_n=config.get("r5_bgt_sm_corpus_size_n", 10000),
            spc_uq_uncertainty_alpha=config.get("r5_spc_uq_uncertainty_alpha", 1.0),
            spc_uq_uncertainty_beta=config.get("r5_spc_uq_uncertainty_beta", 1.0),
            spc_uq_simulation_count=config.get("r5_spc_uq_simulation_count", 100),
            tdl_hco_learning_rate=config.get("r5_tdl_hco_learning_rate", 0.01),
            tdl_hco_discount_factor=config.get("r5_tdl_hco_discount_factor", 0.95),
            tdl_hco_eligibility_trace_decay=config.get("r5_tdl_hco_eligibility_trace_decay", 0.9),
            enable_shadow_validation=config.get("r5_enable_shadow_validation", True),
        )


# =============================================================================
# GLOBAL FEATURE FLAG
# =============================================================================

# MVP default: R5 disabled until validated
# This is the default mode when no configuration is provided
# NOTE: Set to ENABLED for testing R5 dream phase integration
P03_FF_R5_MODE: R5Mode = R5Mode.ENABLED


def get_default_r5_config() -> R5Config:
    """Get default R5 configuration using global feature flag."""
    return R5Config(mode=P03_FF_R5_MODE)
