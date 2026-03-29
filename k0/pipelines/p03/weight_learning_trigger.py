"""
Weight Learning Trigger -- Train importance weights after R3 reconciliation.

Implements ADR-K025 training flow:
    After R3 reconciliation, build TrainingBatch from grounding signals
    and train ImportanceWeightLearner if sufficient data is available.

Issue 5.W.2.4: Training trigger in P03
Issue 5.W.2.5: Weight persistence flow

This module is called as a post-R3 side-effect, NOT as a full P03 phase.
It operates on the envelope after R3 has set reconciliation actions on
all events, using those actions as grounding labels.

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, Optional

from k0.modules.consolidation.algorithms.grounding_signal_collector import GroundingSignalCollector
from k0.modules.consolidation.algorithms.importance_weight_learner import (
    ImportanceWeightLearner,
    TrainingResult,
    WeightLearnerConfig,
)

if TYPE_CHECKING:
    from k0.pipelines.p03.envelope import P03BatchEnvelope
    from k0.pipelines.p03.phase_interface import P03RunnerContext

logger = logging.getLogger(__name__)


# =============================================================================
# Training Trigger Configuration
# =============================================================================


@dataclass
class WeightTrainingConfig:
    """
    Configuration for the weight learning trigger.

    Attributes:
        enabled: Whether weight learning is enabled
        min_batch_size: Minimum events needed to trigger training
        persist_after_training: Whether to persist weights after each training step
        log_training_result: Whether to log full training result details
        hebbian_activation_threshold: Cumulative sample_count at which Hebbian
            learning auto-activates. The trigger reports hebbian_activated=True
            on the result once this threshold is reached. Set to 0 to disable.
    """

    enabled: bool = True
    min_batch_size: int = 50
    persist_after_training: bool = True
    log_training_result: bool = True
    hebbian_activation_threshold: int = 500


# =============================================================================
# Training Trigger Result
# =============================================================================


@dataclass
class WeightTrainingTriggerResult:
    """
    Result from the weight training trigger.

    Attributes:
        triggered: Whether training was actually executed
        skipped: Whether training was skipped (with reason)
        skip_reason: Why training was skipped (if applicable)
        training_result: Result from learner.train_step() if executed
        batch_size: Number of events in the training batch
        grounded_count: Number of grounded events in batch
        persisted: Whether weights were persisted to storage
        duration_ms: Total time spent in trigger
        hebbian_activated: Whether cumulative sample_count has crossed
            the hebbian_activation_threshold. Downstream consumers
            (e.g. R1Config, R4 runner) use this to flip Hebbian on.
        cumulative_sample_count: Total samples processed by the learner
    """

    triggered: bool = False
    skipped: bool = False
    skip_reason: str = ""
    training_result: Optional[TrainingResult] = None
    batch_size: int = 0
    grounded_count: int = 0
    persisted: bool = False
    duration_ms: int = 0
    hebbian_activated: bool = False
    cumulative_sample_count: int = 0


# =============================================================================
# Weight Learning Trigger
# =============================================================================


class WeightLearningTrigger:
    """
    Triggers ImportanceWeightLearner training after R3 reconciliation.

    Called as a post-R3 side-effect during P03 cycle execution.
    Builds a TrainingBatch from R3 grounding signals and trains the
    learner if sufficient data is available.

    The trigger manages:
    1. Grounding signal collection from R3 reconciliation actions
    2. TrainingBatch construction with 8 CONFIG_B features
    3. Training step execution with batch protection
    4. Weight persistence to st_learned_weights

    Usage:
        trigger = WeightLearningTrigger(space_id="sp_123")
        result = await trigger.execute(envelope, ctx)
        if result.triggered:
            print(f"Trained on {result.batch_size} events, loss={result.training_result.loss}")
    """

    def __init__(
        self,
        space_id: str,
        config: Optional[WeightTrainingConfig] = None,
        learner_config: Optional[WeightLearnerConfig] = None,
    ) -> None:
        """
        Initialize weight learning trigger.

        Args:
            space_id: User/family space ID
            config: Training trigger configuration
            learner_config: Learner-specific configuration
        """
        self.space_id = space_id
        self.config = config or WeightTrainingConfig()
        self._learner = ImportanceWeightLearner(
            space_id=space_id,
            config=learner_config,
        )
        self._collector = GroundingSignalCollector()

    @property
    def learner(self) -> ImportanceWeightLearner:
        """Access the underlying weight learner."""
        return self._learner

    async def execute(
        self,
        envelope: "P03BatchEnvelope",
        ctx: "P03RunnerContext",
    ) -> WeightTrainingTriggerResult:
        """
        Execute weight learning trigger after R3 reconciliation.

        Flow:
        1. Check if training is enabled
        2. Build TrainingBatch from R3 grounding signals
        3. Check minimum batch size
        4. Execute learner.train_step()
        5. Persist weights if configured
        6. Return result

        Args:
            envelope: P03 batch envelope (after R3 has run)
            ctx: Runner context with syscalls

        Returns:
            WeightTrainingTriggerResult with training outcome
        """
        start_ms = int(time.time() * 1000)

        # Check if training is enabled
        if not self.config.enabled:
            return WeightTrainingTriggerResult(
                skipped=True,
                skip_reason="TRAINING_DISABLED",
                duration_ms=int(time.time() * 1000) - start_ms,
            )

        # Check if learner is enabled
        if not self._learner.is_learning_enabled:
            return WeightTrainingTriggerResult(
                skipped=True,
                skip_reason="LEARNER_DISABLED",
                duration_ms=int(time.time() * 1000) - start_ms,
            )

        # Build training batch from grounding signals
        now_ms = int(time.time() * 1000)
        event_states = envelope.events
        batch = self._collector.build_training_batch(event_states, now_ms=now_ms)

        # Check minimum batch size
        if len(batch) < self.config.min_batch_size:
            duration_ms = int(time.time() * 1000) - start_ms
            logger.debug(
                "Weight training skipped: insufficient batch size",
                extra={
                    "space_id": self.space_id,
                    "batch_size": len(batch),
                    "min_batch_size": self.config.min_batch_size,
                    "cycle_id": envelope.context.cycle_id,
                },
            )
            return WeightTrainingTriggerResult(
                skipped=True,
                skip_reason="BATCH_TOO_SMALL",
                batch_size=len(batch),
                duration_ms=duration_ms,
            )

        # Count grounded vs not-grounded
        grounded_count = sum(1 for s in batch.samples if s.was_grounded)

        # Try to load existing weights from storage before training
        try:
            await self._load_existing_weights(ctx)
        except Exception as e:
            logger.warning(
                "Failed to load existing weights, training with priors",
                extra={
                    "space_id": self.space_id,
                    "error": str(e),
                },
            )

        # Execute training step
        try:
            result = self._learner.train_step(batch)
        except Exception as e:
            duration_ms = int(time.time() * 1000) - start_ms
            logger.exception(
                "Weight training failed",
                extra={
                    "space_id": self.space_id,
                    "batch_size": len(batch),
                    "cycle_id": envelope.context.cycle_id,
                    "error": str(e),
                },
            )
            return WeightTrainingTriggerResult(
                triggered=True,
                batch_size=len(batch),
                grounded_count=grounded_count,
                duration_ms=duration_ms,
            )

        # Log training result
        if self.config.log_training_result:
            logger.info(
                "Weight training step completed",
                extra={
                    "space_id": self.space_id,
                    "cycle_id": envelope.context.cycle_id,
                    "batch_size": len(batch),
                    "grounded_count": grounded_count,
                    "loss": round(result.loss, 6),
                    "sample_count": result.sample_count,
                    "converged": result.converged,
                    "skipped": result.skipped,
                    "drift": round(result.drift, 4) if result.drift is not None else None,
                    "weights": {k: round(v, 4) for k, v in result.weights.items()},
                },
            )

        # Persist weights if configured and training succeeded
        persisted = False
        if self.config.persist_after_training and not result.skipped:
            try:
                await self._persist_weights(ctx)
                persisted = True
            except Exception as e:
                logger.warning(
                    "Failed to persist learned weights",
                    extra={
                        "space_id": self.space_id,
                        "error": str(e),
                    },
                )

        duration_ms = int(time.time() * 1000) - start_ms

        # Check Hebbian activation threshold (Decision D-R1-001)
        cumulative = self._learner.sample_count
        threshold = self.config.hebbian_activation_threshold
        hebbian_activated = threshold > 0 and cumulative >= threshold

        if hebbian_activated:
            logger.info(
                "Hebbian activation threshold reached",
                extra={
                    "space_id": self.space_id,
                    "cumulative_sample_count": cumulative,
                    "hebbian_activation_threshold": threshold,
                },
            )

        return WeightTrainingTriggerResult(
            triggered=True,
            training_result=result,
            batch_size=len(batch),
            grounded_count=grounded_count,
            persisted=persisted,
            duration_ms=duration_ms,
            hebbian_activated=hebbian_activated,
            cumulative_sample_count=cumulative,
        )

    async def _load_existing_weights(self, ctx: "P03RunnerContext") -> None:
        """
        Load existing learned weights from storage via syscalls.

        Uses the SyscallLearnedWeightsStore to load weights that were
        persisted in previous P03 cycles.

        Args:
            ctx: Runner context with syscalls
        """
        from k0.pipelines.p03.stores import SyscallLearnedWeightsStore

        store = SyscallLearnedWeightsStore(syscalls=ctx.syscalls)
        weights: Dict[str, float] = {}

        for component in self._learner.COMPONENTS:
            param_key = f"importance_{component}"
            try:
                value = await store.get_weight(
                    space_id=self.space_id,
                    param_key=param_key,
                )
                if value is not None:
                    weights[component] = value
            except Exception:
                pass  # Missing key is fine, will use priors

        if weights:
            self._learner.set_weights(weights)
            logger.debug(
                "Loaded existing weights for training",
                extra={
                    "space_id": self.space_id,
                    "loaded_components": list(weights.keys()),
                },
            )

    async def _persist_weights(self, ctx: "P03RunnerContext") -> None:
        """
        Persist learned weights to st_learned_weights via syscalls.

        Uses the SyscallLearnedWeightsStore to write each component weight.

        Args:
            ctx: Runner context with syscalls
        """
        from k0.pipelines.p03.stores import SyscallLearnedWeightsStore

        store = SyscallLearnedWeightsStore(syscalls=ctx.syscalls)
        weights = self._learner.get_weights()
        priors = self._learner.config.get_priors()

        for component, value in weights.items():
            param_key = f"importance_{component}"
            prior_value = priors.get(component, 0.125)
            await store.upsert_weight(
                param_key=param_key,
                space_id=self.space_id,
                value=value,
                prior_value=prior_value,
            )

        logger.info(
            "Persisted learned weights to storage",
            extra={
                "space_id": self.space_id,
                "sample_count": self._learner.sample_count,
                "components_written": len(weights),
            },
        )
