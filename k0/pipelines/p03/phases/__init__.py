"""
P03 Phase Implementations — M3 Issue 3.1.1+

This package contains the concrete implementations of R0-R8 phases
for the P03 consolidation pipeline.

Phases:
    R0: Batch Selection (3.2.1)
    R1: Importance Scoring (4.1.1-4.1.2)
    R2: Episodic Integration (4.2.1-4.2.8)
    R3: Deduplication & Decay (4.3.1-4.3.12)
    R4: Knowledge Graph Consolidation (4.4.1-4.4.12)
    R5: Dream Exploration (8.1.1-8.1.20) - M8 Implementation
    R6: Staging Table Updates (5.1.1-5.1.13)
    R7: Truth Writer (3.1.1)
    R8: Event Emitter (3.1.2)
"""

from __future__ import annotations

from k0.pipelines.p03.phase_interface import P03PhaseResult
from k0.pipelines.p03.phases.r0_batch_selector import R0BatchSelector, R0Config
from k0.pipelines.p03.phases.r1_importance_scorer import (
    R1Config,
    R1ImportanceScorer,
    create_r1_phase,
)
from k0.pipelines.p03.phases.r2_episodic_integrator import (
    R2Config,
    R2EpisodicIntegrator,
    create_r2_phase,
)
from k0.pipelines.p03.phases.r3_dedup_decay import (
    R3Config,
    R3DedupDecay,
    R3PhaseStats,
    R3Stores,
    create_r3_phase,
)
from k0.pipelines.p03.phases.r4_kg_consolidator import (
    EntityCluster,
    KGUpdate,
    KGUpdateType,
    R4Config,
    R4KGConsolidator,
    R4PhaseStats,
    create_r4_phase,
)
from k0.pipelines.p03.phases.r5_dream_explorer import R5DreamExplorer
from k0.pipelines.p03.phases.r6_staging import R6Staging, create_r6_phase
from k0.pipelines.p03.phases.r7_truth_writer import OptimisticLockError, R7TruthWriter
from k0.pipelines.p03.phases.r8_event_emitter import R8EventEmitter
from k0.pipelines.p03.r5_config import R5Config, R5Mode, get_default_r5_config
from k0.pipelines.p03.runner_contract import P03PhaseId

# =============================================================================
# PHASE ADAPTERS - Wrappers for phases with non-standard signatures
# =============================================================================


class R0PhaseAdapter:
    """
    Adapter that wraps R0BatchSelector to conform to P03PhaseProtocol.

    R0BatchSelector.run(tenant_id, space_id, ctx) -> (envelope, result)
    P03PhaseProtocol.run(envelope, ctx) -> result

    This adapter extracts tenant_id/space_id from the envelope context
    and delegates to R0BatchSelector, then updates the envelope with
    the result.

    Note: R0 is special because it CREATES the envelope. When the sequential
    runner calls R0, it passes a "seed" envelope that only has tenant/space
    identifiers. R0 populates it with actual events from the database.
    """

    phase_id = P03PhaseId.R0_INIT

    def __init__(self) -> None:
        self._r0 = R0BatchSelector()

    async def run(self, envelope, ctx) -> P03PhaseResult:
        """
        Adapt R0BatchSelector.run() to P03PhaseProtocol interface.

        The envelope passed here should have context.tenant_id and
        context.space_id set (or we extract from config/ctx).
        """
        # Extract tenant_id/space_id from envelope context or ctx
        tenant_id = getattr(envelope.context, "tenant_id", None)
        space_id = getattr(envelope.context, "space_id", None)

        if not tenant_id:
            tenant_id = ctx.get_config("tenant_id", "default")
        if not space_id:
            space_id = ctx.get_config("space_id", "default")

        # Call the actual R0 implementation
        new_envelope, result = await self._r0.run(tenant_id, space_id, ctx)

        if new_envelope is not None:
            # R0 created a new envelope with events - copy data to our envelope
            envelope.events = new_envelope.events
            envelope.context = new_envelope.context
            envelope.phases = new_envelope.phases

        return result

    def should_skip(self, envelope, ctx) -> tuple[bool, str]:
        """R0 never skips - it's the entry point."""
        return (False, "")

    def idempotency_key(self, envelope, ctx) -> str:
        """Return idempotency key for R0."""
        tenant_id = getattr(envelope.context, "tenant_id", "unknown")
        space_id = getattr(envelope.context, "space_id", "unknown")
        return f"r0_{tenant_id}_{space_id}"


# =============================================================================
# PHASE_REGISTRY - Mapping of phase IDs to phase instances
# =============================================================================
#
# This registry is used by SequentialRunnerAdapter to load phases for
# P03SequentialRunner. Each phase is instantiated with default configuration.
#
# R5 (Dream Exploration) is implemented in M8 with mode control (Issue 8.1.1).
# Default mode is DISABLED for MVP safety.


def create_r5_phase(config: R5Config | None = None) -> R5DreamExplorer:
    """
    Create R5 Dream Exploration phase with configuration.

    Args:
        config: R5 configuration (uses get_default_r5_config() if None,
                which respects P03_FF_R5_MODE global flag)

    Returns:
        R5DreamExplorer instance
    """
    return R5DreamExplorer(config=config or get_default_r5_config())


# Registry mapping P03PhaseId -> phase instance
# Note: P03SequentialRunner expects Dict[P03PhaseId, P03PhaseProtocol]
PHASE_REGISTRY: dict[P03PhaseId, object] = {
    P03PhaseId.R0_INIT: R0PhaseAdapter(),  # Adapter for R0's special signature
    P03PhaseId.R1_SCORE: R1ImportanceScorer(),
    P03PhaseId.R2_CLUSTER: R2EpisodicIntegrator(),
    P03PhaseId.R3_PRUNE: create_r3_phase(),  # Reconciliation enabled by default (Issue 4.3.13)
    P03PhaseId.R4_KG: R4KGConsolidator(),
    P03PhaseId.R5_DREAM: create_r5_phase(),  # M8 Issue 8.1.1: mode=DISABLED by default
    P03PhaseId.R6_STAGE: R6Staging(),
    P03PhaseId.R7_WRITE: R7TruthWriter(),
    P03PhaseId.R8_EMIT: R8EventEmitter(),
}


__all__: list[str] = [
    # Registry and Adapters
    "PHASE_REGISTRY",
    "R0PhaseAdapter",
    # R0
    "R0BatchSelector",
    "R0Config",
    # R1
    "R1ImportanceScorer",
    "R1Config",
    "create_r1_phase",
    # R2
    "R2EpisodicIntegrator",
    "R2Config",
    "create_r2_phase",
    # R3
    "R3DedupDecay",
    "R3Config",
    "R3PhaseStats",
    "R3Stores",
    "create_r3_phase",
    # R4
    "R4KGConsolidator",
    "R4Config",
    "R4PhaseStats",
    "KGUpdate",
    "KGUpdateType",
    "EntityCluster",
    "create_r4_phase",
    # R5 (M8 Issue 8.1.1)
    "R5DreamExplorer",
    "R5Config",
    "R5Mode",
    "create_r5_phase",
    # R6
    "R6Staging",
    "create_r6_phase",
    # R7
    "R7TruthWriter",
    "OptimisticLockError",
    # R8
    "R8EventEmitter",
]
