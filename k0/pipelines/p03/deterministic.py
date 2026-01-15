"""
P03 Deterministic Cycle Seeding and Skip Rule Policy — Issue 1.2.7

This module provides deterministic behavior for P03 consolidation cycles:
1. Cycle seed derivation for reproducible random operations
2. Skip rule policy checks for conditional phase execution
3. Seeded RNG context for phase operations

References:
- Spec: docs/pipelines/P03_consolidation_dossier_v2.md §4.0, Appendix G.1-G.2
- Issue: docs/TEMP_EXECUTION_DOCS/M1_EXECUTION.md Issue 1.2.7
- Dossier §4.6.7: R5 complexity and skip conditions
- Dossier §18.5.5: r5_skip_on_backlog, r5_backlog_threshold

Design Principles:
- Determinism: Same cycle_id + batch_id = same seed = same random choices
- Policy-first: Skip rules are explicit policy checks, not implicit behavior
- Observability: All skip decisions are recorded with reasons
- Testability: All functions are pure where possible, no hidden state
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Protocol, Tuple, runtime_checkable

from k0.pipelines.p03.runner_contract import P03PhaseId

# =============================================================================
# CONSTANTS
# =============================================================================

# Default thresholds from dossier §18.5.5 and Appendix F.5
DEFAULT_R5_BACKLOG_THRESHOLD: int = 5000  # Skip R5 if pending > threshold
DEFAULT_MINIMAL_WORK_THRESHOLD: int = 2  # Skip R3-R5 if batch_size < threshold

# Phase groups for skip rules
R5_SKIP_PHASES: FrozenSet[P03PhaseId] = frozenset({P03PhaseId.R5_DREAM})
MINIMAL_WORK_SKIP_PHASES: FrozenSet[P03PhaseId] = frozenset(
    {
        P03PhaseId.R3_PRUNE,
        P03PhaseId.R4_KG,
        P03PhaseId.R5_DREAM,
    }
)

# Seed derivation constants
SEED_HASH_PREFIX: str = "p03:cycle:seed"
SEED_HASH_BYTES: int = 8  # 64 bits = 16 hex chars


# =============================================================================
# SEED DERIVATION
# =============================================================================


def derive_cycle_seed(cycle_id: str, batch_id: str) -> int:
    """
    Derive a deterministic seed from cycle identifiers.

    This seed ensures all randomized/heuristic behavior within a cycle is
    reproducible. Two runs with the same cycle_id and batch_id will produce
    identical random sequences when using this seed.

    Algorithm:
        1. Concatenate identifiers with separator: "{prefix}:{cycle_id}:{batch_id}"
        2. Compute SHA-256 hash
        3. Take first 16 hex characters (64 bits)
        4. Convert to integer

    Args:
        cycle_id: ULID uniquely identifying the consolidation cycle
        batch_id: Deterministic hash of sorted unique event IDs (SHA256[:16])

    Returns:
        64-bit integer seed for random number generation

    Example:
        >>> seed = derive_cycle_seed("01JFXYZ123ABC", "a1b2c3d4e5f67890")
        >>> seed  # Deterministic for same inputs
        12345678901234567890
        >>> rng = random.Random(seed)
        >>> rng.random()  # Always same value for same seed
        0.123456789...

    Spec Reference:
        docs/TEMP_EXECUTION_DOCS/M1_EXECUTION.md Issue 1.2.7:
        - cycle_id is ULID
        - batch_id is SHA256[:16] of sorted event IDs
    """
    if not cycle_id:
        raise ValueError("cycle_id cannot be empty")
    if not batch_id:
        raise ValueError("batch_id cannot be empty")

    # Create deterministic input string
    seed_input = f"{SEED_HASH_PREFIX}:{cycle_id}:{batch_id}"

    # Compute SHA-256 hash
    hash_bytes = hashlib.sha256(seed_input.encode("utf-8")).digest()

    # Take first 8 bytes (64 bits) and convert to integer
    seed_value = int.from_bytes(hash_bytes[:SEED_HASH_BYTES], byteorder="big")

    return seed_value


def derive_phase_seed(cycle_seed: int, phase_id: P03PhaseId) -> int:
    """
    Derive a phase-specific seed from cycle seed.

    Each phase gets its own seed derived from the cycle seed to ensure:
    - Phase independence: One phase's random choices don't affect another
    - Reproducibility: Same cycle seed + phase = same phase seed

    Algorithm:
        hash("{cycle_seed}:{phase_id.value}")[:8] → int

    Args:
        cycle_seed: Master seed from derive_cycle_seed()
        phase_id: Phase identifier (R0-R8)

    Returns:
        64-bit integer seed specific to this phase

    Example:
        >>> cycle_seed = derive_cycle_seed("01JFXYZ123ABC", "a1b2c3d4e5f67890")
        >>> r5_seed = derive_phase_seed(cycle_seed, P03PhaseId.R5_DREAM)
        >>> rng = random.Random(r5_seed)
    """
    seed_input = f"{cycle_seed}:{phase_id.value}"
    hash_bytes = hashlib.sha256(seed_input.encode("utf-8")).digest()
    return int.from_bytes(hash_bytes[:SEED_HASH_BYTES], byteorder="big")


# =============================================================================
# SEEDED RNG CONTEXT
# =============================================================================


@dataclass
class P03SeededRNG:
    """
    Seeded random number generator for P03 cycle operations.

    Provides a deterministic RNG that can be passed to phases for any
    operations requiring randomness (sampling, MCTS rollouts, random walks).

    The RNG is initialized with the cycle seed and can provide phase-specific
    generators for isolation.

    Attributes:
        cycle_seed: Master seed derived from cycle_id + batch_id
        cycle_id: ULID of the cycle (for tracing)
        batch_id: Batch hash (for tracing)
        _rng: Internal random.Random instance
        _phase_rngs: Cached phase-specific RNGs
    """

    cycle_seed: int
    cycle_id: str
    batch_id: str
    _rng: random.Random = field(default_factory=random.Random, repr=False)
    _phase_rngs: Dict[P03PhaseId, random.Random] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        """Initialize the master RNG with cycle seed."""
        self._rng.seed(self.cycle_seed)

    @classmethod
    def create(cls, cycle_id: str, batch_id: str) -> "P03SeededRNG":
        """
        Factory method to create seeded RNG from cycle identifiers.

        Args:
            cycle_id: ULID of the cycle
            batch_id: Deterministic batch hash

        Returns:
            Initialized P03SeededRNG instance
        """
        seed = derive_cycle_seed(cycle_id, batch_id)
        rng = cls(
            cycle_seed=seed,
            cycle_id=cycle_id,
            batch_id=batch_id,
        )
        return rng

    def get_phase_rng(self, phase_id: P03PhaseId) -> random.Random:
        """
        Get a phase-specific RNG.

        Each phase gets its own isolated RNG to ensure phase independence.
        The phase RNG is cached for the lifetime of this context.

        Args:
            phase_id: Phase identifier

        Returns:
            Seeded random.Random instance for the phase
        """
        if phase_id not in self._phase_rngs:
            phase_seed = derive_phase_seed(self.cycle_seed, phase_id)
            phase_rng = random.Random(phase_seed)
            self._phase_rngs[phase_id] = phase_rng
        return self._phase_rngs[phase_id]

    def random(self) -> float:
        """Get a random float in [0.0, 1.0) from master RNG."""
        return self._rng.random()

    def randint(self, a: int, b: int) -> int:
        """Get a random integer N such that a <= N <= b from master RNG."""
        return self._rng.randint(a, b)

    def choice(self, seq: List) -> object:
        """Choose a random element from a non-empty sequence."""
        return self._rng.choice(seq)

    def sample(self, population: List, k: int) -> List:
        """Return k unique random elements from population."""
        return self._rng.sample(population, k)

    def shuffle(self, x: List) -> None:
        """Shuffle list x in place."""
        self._rng.shuffle(x)

    def to_dict(self) -> Dict:
        """Serialize RNG context for logging/checkpointing."""
        return {
            "cycle_seed": self.cycle_seed,
            "cycle_id": self.cycle_id,
            "batch_id": self.batch_id,
            "phase_seeds": {
                phase.value: derive_phase_seed(self.cycle_seed, phase) for phase in self._phase_rngs
            },
        }


# =============================================================================
# SKIP RULE POLICIES
# =============================================================================


class SkipReason(Enum):
    """
    Enumeration of skip reasons for policy decisions.

    Each skip reason maps to a specific policy condition documented in
    the dossier Appendix G.2.
    """

    # R5 skip reasons
    R5_BACKLOG_EXCEEDED = "r5_backlog_exceeded"
    R5_DISABLED = "r5_disabled"

    # Minimal work skip reasons (R2→R6 fast-path)
    BATCH_TOO_SMALL = "batch_too_small"
    SINGLE_EVENT_MICRO_EPISODE = "single_event_micro_episode"

    # Generic skip
    PHASE_DISABLED = "phase_disabled"
    SKIP_CONDITION_MET = "skip_condition_met"


@dataclass(frozen=True)
class SkipDecision:
    """
    Immutable skip decision result from policy evaluation.

    Captures whether a phase should be skipped and why.

    Attributes:
        should_skip: True if the phase should be skipped
        phase_id: Phase being evaluated
        reason: SkipReason enum value if skipping
        reason_detail: Human-readable explanation
        threshold_value: Threshold that was evaluated (if applicable)
        actual_value: Actual value compared against threshold (if applicable)
    """

    should_skip: bool
    phase_id: P03PhaseId
    reason: Optional[SkipReason] = None
    reason_detail: Optional[str] = None
    threshold_value: Optional[int] = None
    actual_value: Optional[int] = None

    def to_dict(self) -> Dict:
        """Serialize for logging/observability."""
        result = {
            "should_skip": self.should_skip,
            "phase": self.phase_id.value,
        }
        if self.reason:
            result["reason"] = self.reason.value
        if self.reason_detail:
            result["reason_detail"] = self.reason_detail
        if self.threshold_value is not None:
            result["threshold_value"] = self.threshold_value
        if self.actual_value is not None:
            result["actual_value"] = self.actual_value
        return result


@dataclass(frozen=True)
class SkipPolicyConfig:
    """
    Configuration for skip rule policies.

    Attributes:
        r5_enabled: Whether R5 Dream phase is enabled
        r5_skip_on_backlog: Whether to skip R5 when backlog exceeds threshold
        r5_backlog_threshold: Pending event threshold for R5 skip
        minimal_work_threshold: Batch size threshold for fast-path skip
    """

    r5_enabled: bool = True
    r5_skip_on_backlog: bool = True
    r5_backlog_threshold: int = DEFAULT_R5_BACKLOG_THRESHOLD
    minimal_work_threshold: int = DEFAULT_MINIMAL_WORK_THRESHOLD

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.r5_backlog_threshold < 0:
            raise ValueError("r5_backlog_threshold must be non-negative")
        if self.minimal_work_threshold < 1:
            raise ValueError("minimal_work_threshold must be >= 1")

    @classmethod
    def from_dict(cls, config: Dict) -> "SkipPolicyConfig":
        """Create from dictionary (e.g., from P03Settings)."""
        return cls(
            r5_enabled=config.get("r5_dream_enabled", True),
            r5_skip_on_backlog=config.get("r5_skip_on_backlog", True),
            r5_backlog_threshold=config.get("r5_backlog_threshold", DEFAULT_R5_BACKLOG_THRESHOLD),
            minimal_work_threshold=config.get(
                "minimal_work_threshold", DEFAULT_MINIMAL_WORK_THRESHOLD
            ),
        )


# =============================================================================
# SKIP POLICY EVALUATION
# =============================================================================


def evaluate_r5_skip(
    pending_count: int,
    config: Optional[SkipPolicyConfig] = None,
) -> SkipDecision:
    """
    Evaluate whether R5 Dream phase should be skipped.

    Skip conditions (from dossier §4.6.7, G.2):
        1. R5 is globally disabled (r5_enabled=False)
        2. Backlog skip enabled AND pending > threshold

    Args:
        pending_count: Current count of pending events in st_hipp_events
        config: Skip policy configuration (uses defaults if None)

    Returns:
        SkipDecision with skip determination and reason

    Example:
        >>> decision = evaluate_r5_skip(pending_count=6000)
        >>> decision.should_skip
        True
        >>> decision.reason
        SkipReason.R5_BACKLOG_EXCEEDED
    """
    config = config or SkipPolicyConfig()

    # Check if R5 is globally disabled
    if not config.r5_enabled:
        return SkipDecision(
            should_skip=True,
            phase_id=P03PhaseId.R5_DREAM,
            reason=SkipReason.R5_DISABLED,
            reason_detail="R5 Dream phase is globally disabled",
        )

    # Check backlog condition
    if config.r5_skip_on_backlog and pending_count > config.r5_backlog_threshold:
        return SkipDecision(
            should_skip=True,
            phase_id=P03PhaseId.R5_DREAM,
            reason=SkipReason.R5_BACKLOG_EXCEEDED,
            reason_detail=(
                f"Pending count ({pending_count}) exceeds "
                f"backlog threshold ({config.r5_backlog_threshold})"
            ),
            threshold_value=config.r5_backlog_threshold,
            actual_value=pending_count,
        )

    # R5 should execute normally
    return SkipDecision(
        should_skip=False,
        phase_id=P03PhaseId.R5_DREAM,
    )


def evaluate_minimal_work_skip(
    batch_size: int,
    config: Optional[SkipPolicyConfig] = None,
) -> SkipDecision:
    """
    Evaluate whether R2 clustering should skip to R6 (fast-path).

    The minimal work fast-path (R2→R6) is triggered when batch is too small
    for meaningful clustering/analysis:
        - batch_size < minimal_work_threshold → skip R3-R5, go to R6

    From dossier G.2 (R2_CLUSTER):
        "Skip Condition: batch_size < 2 (single event = micro-episode)"

    Args:
        batch_size: Number of events in the current batch
        config: Skip policy configuration (uses defaults if None)

    Returns:
        SkipDecision with skip determination for R2→R6 fast-path

    Example:
        >>> decision = evaluate_minimal_work_skip(batch_size=1)
        >>> decision.should_skip
        True
        >>> decision.reason
        SkipReason.SINGLE_EVENT_MICRO_EPISODE
    """
    config = config or SkipPolicyConfig()

    if batch_size < config.minimal_work_threshold:
        # Special case: single event
        if batch_size == 1:
            return SkipDecision(
                should_skip=True,
                phase_id=P03PhaseId.R2_CLUSTER,
                reason=SkipReason.SINGLE_EVENT_MICRO_EPISODE,
                reason_detail="Single event batch treated as micro-episode",
                threshold_value=config.minimal_work_threshold,
                actual_value=batch_size,
            )
        # General case: batch too small
        return SkipDecision(
            should_skip=True,
            phase_id=P03PhaseId.R2_CLUSTER,
            reason=SkipReason.BATCH_TOO_SMALL,
            reason_detail=(
                f"Batch size ({batch_size}) below minimal work threshold "
                f"({config.minimal_work_threshold})"
            ),
            threshold_value=config.minimal_work_threshold,
            actual_value=batch_size,
        )

    # Normal processing path
    return SkipDecision(
        should_skip=False,
        phase_id=P03PhaseId.R2_CLUSTER,
    )


# =============================================================================
# SKIP POLICY MANAGER
# =============================================================================


@runtime_checkable
class SkipPolicyProtocol(Protocol):
    """Protocol for skip policy implementations."""

    def should_skip_phase(self, phase_id: P03PhaseId) -> SkipDecision:
        """Evaluate whether a phase should be skipped."""
        ...

    def get_skip_transition(self, phase_id: P03PhaseId) -> Optional[P03PhaseId]:
        """Get the target phase if skipping, or None if no skip."""
        ...


@dataclass
class P03SkipPolicy:
    """
    Skip policy manager for P03 cycle execution.

    Centralizes all skip rule evaluations and tracks skip decisions
    made during the cycle for observability.

    Attributes:
        config: Skip policy configuration
        pending_count: Current pending event count (for R5 evaluation)
        batch_size: Current batch size (for minimal work evaluation)
        _decisions: Cache of skip decisions made
    """

    config: SkipPolicyConfig
    pending_count: int
    batch_size: int
    _decisions: Dict[P03PhaseId, SkipDecision] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        pending_count: int,
        batch_size: int,
        config: Optional[SkipPolicyConfig] = None,
    ) -> "P03SkipPolicy":
        """
        Factory method for creating skip policy manager.

        Args:
            pending_count: Current pending events in st_hipp_events
            batch_size: Number of events in current batch
            config: Policy configuration (uses defaults if None)

        Returns:
            Initialized P03SkipPolicy
        """
        return cls(
            config=config or SkipPolicyConfig(),
            pending_count=pending_count,
            batch_size=batch_size,
        )

    def should_skip_phase(self, phase_id: P03PhaseId) -> SkipDecision:
        """
        Evaluate whether a phase should be skipped.

        Results are cached for consistency within the cycle.

        Args:
            phase_id: Phase to evaluate

        Returns:
            SkipDecision with skip determination
        """
        # Return cached decision if already evaluated
        if phase_id in self._decisions:
            return self._decisions[phase_id]

        # Evaluate based on phase
        if phase_id == P03PhaseId.R5_DREAM:
            decision = evaluate_r5_skip(self.pending_count, self.config)
        elif phase_id == P03PhaseId.R2_CLUSTER:
            decision = evaluate_minimal_work_skip(self.batch_size, self.config)
        else:
            # Phase has no skip rules - always execute
            decision = SkipDecision(
                should_skip=False,
                phase_id=phase_id,
            )

        # Cache and return
        self._decisions[phase_id] = decision
        return decision

    def get_skip_transition(self, phase_id: P03PhaseId) -> Optional[P03PhaseId]:
        """
        Get the target phase if current phase should be skipped.

        Skip transitions from dossier Appendix G.3:
            - R2 → R6: Minimal work fast-path (batch_size < 2)
            - R4 → R6: Skip R5 on backlog
            - R5 → R6: R5 skipped (already at R5)

        Args:
            phase_id: Current phase being evaluated

        Returns:
            Target phase to skip to, or None if no skip
        """
        decision = self.should_skip_phase(phase_id)

        if not decision.should_skip:
            return None

        # Define skip targets
        skip_targets: Dict[P03PhaseId, P03PhaseId] = {
            P03PhaseId.R2_CLUSTER: P03PhaseId.R6_STAGE,
            P03PhaseId.R5_DREAM: P03PhaseId.R6_STAGE,
        }

        return skip_targets.get(phase_id)

    def get_all_decisions(self) -> Dict[P03PhaseId, SkipDecision]:
        """Get all skip decisions made during this cycle."""
        return dict(self._decisions)

    def get_skip_summary(self) -> Dict:
        """Get summary of skip decisions for observability."""
        skipped = [
            phase.value for phase, decision in self._decisions.items() if decision.should_skip
        ]
        return {
            "pending_count": self.pending_count,
            "batch_size": self.batch_size,
            "phases_skipped": skipped,
            "decisions": {
                phase.value: decision.to_dict() for phase, decision in self._decisions.items()
            },
        }

    def to_dict(self) -> Dict:
        """Serialize for logging/checkpointing."""
        return {
            "config": {
                "r5_enabled": self.config.r5_enabled,
                "r5_skip_on_backlog": self.config.r5_skip_on_backlog,
                "r5_backlog_threshold": self.config.r5_backlog_threshold,
                "minimal_work_threshold": self.config.minimal_work_threshold,
            },
            "pending_count": self.pending_count,
            "batch_size": self.batch_size,
            "decisions": {
                phase.value: decision.to_dict() for phase, decision in self._decisions.items()
            },
        }


# =============================================================================
# DETERMINISTIC CYCLE CONTEXT
# =============================================================================


@dataclass
class P03DeterministicContext:
    """
    Combined context for deterministic cycle execution.

    Bundles the seeded RNG and skip policy for convenient passing to phases.

    Attributes:
        rng: Seeded random number generator
        skip_policy: Skip rule policy manager
        cycle_id: ULID of the cycle
        batch_id: Deterministic batch hash
    """

    rng: P03SeededRNG
    skip_policy: P03SkipPolicy
    cycle_id: str
    batch_id: str

    @classmethod
    def create(
        cls,
        cycle_id: str,
        batch_id: str,
        pending_count: int,
        batch_size: int,
        skip_config: Optional[SkipPolicyConfig] = None,
    ) -> "P03DeterministicContext":
        """
        Factory method for creating deterministic context.

        Args:
            cycle_id: ULID of the cycle
            batch_id: Deterministic batch hash
            pending_count: Current pending events
            batch_size: Current batch size
            skip_config: Optional skip policy configuration

        Returns:
            Initialized P03DeterministicContext
        """
        return cls(
            rng=P03SeededRNG.create(cycle_id, batch_id),
            skip_policy=P03SkipPolicy.create(pending_count, batch_size, skip_config),
            cycle_id=cycle_id,
            batch_id=batch_id,
        )

    def get_phase_rng(self, phase_id: P03PhaseId) -> random.Random:
        """Get phase-specific RNG for isolated random operations."""
        return self.rng.get_phase_rng(phase_id)

    def should_skip_phase(self, phase_id: P03PhaseId) -> SkipDecision:
        """Check if a phase should be skipped."""
        return self.skip_policy.should_skip_phase(phase_id)

    def to_dict(self) -> Dict:
        """Serialize for logging/checkpointing."""
        return {
            "cycle_id": self.cycle_id,
            "batch_id": self.batch_id,
            "rng": self.rng.to_dict(),
            "skip_policy": self.skip_policy.to_dict(),
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_phases_to_skip_for_fast_path(
    from_phase: P03PhaseId,
    to_phase: P03PhaseId,
) -> Tuple[P03PhaseId, ...]:
    """
    Calculate which phases are skipped in a fast-path transition.

    Args:
        from_phase: Starting phase (e.g., R2)
        to_phase: Target phase (e.g., R6)

    Returns:
        Tuple of phases that will be skipped

    Example:
        >>> get_phases_to_skip_for_fast_path(P03PhaseId.R2_CLUSTER, P03PhaseId.R6_STAGE)
        (P03PhaseId.R3_PRUNE, P03PhaseId.R4_KG, P03PhaseId.R5_DREAM)
    """
    order = P03PhaseId.execution_order()
    from_idx = order.index(from_phase)
    to_idx = order.index(to_phase)

    if from_idx >= to_idx:
        return ()

    # Phases between from_phase and to_phase (exclusive of both)
    return order[from_idx + 1 : to_idx]


def validate_skip_transition(
    from_phase: P03PhaseId,
    to_phase: P03PhaseId,
) -> bool:
    """
    Validate that a skip transition is legal.

    Legal skip transitions from Appendix G.3:
        - R2 → R6 (minimal work fast-path)
        - R4 → R6 (skip R5 on backlog)
        - R5 → R6 (R5 itself skipped)

    Args:
        from_phase: Current phase
        to_phase: Proposed skip target

    Returns:
        True if transition is valid
    """
    from k0.pipelines.p03.runner_contract import SKIP_TRANSITIONS

    skip_info = SKIP_TRANSITIONS.get(from_phase)
    if skip_info and skip_info[0] == to_phase:
        return True
    return False


def record_skip_in_envelope(
    envelope: "P03BatchEnvelope",
    phase_id: P03PhaseId,
    skip_decision: SkipDecision,
) -> None:
    """
    Record a skip decision in the envelope's observability context.

    Updates:
        - Phase status to SKIP
        - R5 skip fields if R5
        - Observability counters

    Args:
        envelope: P03BatchEnvelope to update
        phase_id: Phase that was skipped
        skip_decision: Skip decision with reason
    """
    # Import here to avoid circular dependency

    # Mark phase as skipped
    envelope.mark_phase_skipped(phase_id, skip_decision.reason_detail or "Skip condition met")

    # Update R5-specific fields if R5 was skipped
    if phase_id == P03PhaseId.R5_DREAM:
        envelope.phases.r5_skipped = True
        envelope.phases.r5_skip_reason = skip_decision.reason_detail

    # Record in observability
    envelope.observability.set_tag(f"skip.{phase_id.value}", True)
    if skip_decision.reason:
        envelope.observability.set_tag(f"skip.{phase_id.value}.reason", skip_decision.reason.value)


# =============================================================================
# ERROR CLASSES
# =============================================================================


class DeterministicError(Exception):
    """Base exception for deterministic module errors."""

    pass


class SeedDerivationError(DeterministicError):
    """Error during seed derivation."""

    pass


class SkipPolicyError(DeterministicError):
    """Error during skip policy evaluation."""

    pass


# =============================================================================
# TYPE ALIASES
# =============================================================================

# Type alias for phase-specific RNG getter
PhaseRNGGetter = callable  # Callable[[P03PhaseId], random.Random]
