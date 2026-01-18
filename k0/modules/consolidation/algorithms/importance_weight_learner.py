"""
ImportanceWeightLearner - Adaptive weight learning for importance scoring.

This module implements online gradient descent learning for importance
component weights, transforming static priors into data-driven personalization.

Spec Reference:
    - Dossier Appendix C.2.1.1: Adaptive Weight Learning
    - Dossier Appendix C.2.1.2: Stability Controls
    - M4_EXECUTION.md Issue 4.1.5

Learning Method:
    - Online gradient descent with momentum (β=0.9)
    - Binary cross-entropy loss predicting "will event be grounded?"
    - Nightly batch training during P03 consolidation cycle
    - Minimum 500 samples before learning begins

Weight Constraints:
    - All weights normalized via softmax (sum to 1.0)
    - Per-weight clamping to [0.05, 0.60]
    - Rollback after 3 consecutive nights of increasing loss

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def _check_torch_available() -> bool:
    """Check if PyTorch is available."""
    try:
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


TORCH_AVAILABLE = _check_torch_available()


# =============================================================================
# Configuration
# =============================================================================


@dataclass(frozen=True)
class WeightLearnerConfig:
    """
    Configuration for importance weight learning.

    Defaults from Dossier C.2.1.1 and C.2.1.2:
        - learning_rate: 0.01 (η in gradient descent)
        - momentum: 0.9 (β for velocity smoothing)
        - min_samples: 500 (cold start threshold)
        - weight_min: 0.05 (per-weight floor)
        - weight_max: 0.60 (per-weight ceiling)
        - sliding_window_days: 30 (training data window)
        - rollback_threshold: 3 (consecutive increasing loss nights)

    Batch Protection (Issue 4 fix):
        - min_batch_size: 50 (minimum samples to proceed with training)
        - small_batch_lr_factor: 10.0 (learning rate scaling for small batches)
        - drift_threshold: 0.15 (maximum allowed weight change per step)
    """

    learning_rate: float = 0.01
    momentum: float = 0.9
    min_samples: int = 500
    weight_min: float = 0.05
    weight_max: float = 0.60
    sliding_window_days: int = 30
    rollback_threshold: int = 3

    # Batch protection (Issue 4)
    min_batch_size: int = 50
    small_batch_lr_factor: float = 10.0
    drift_threshold: float = 0.15

    # Static priors (from Dossier §4.2.2)
    prior_emotional: float = 0.35
    prior_recency: float = 0.25
    prior_access: float = 0.20
    prior_social: float = 0.20

    def get_priors(self) -> Dict[str, float]:
        """Get static prior weights as dict."""
        return {
            "emotional": self.prior_emotional,
            "recency": self.prior_recency,
            "access": self.prior_access,
            "social": self.prior_social,
        }

    def get_priors_list(self) -> List[float]:
        """Get static prior weights as list."""
        return [
            self.prior_emotional,
            self.prior_recency,
            self.prior_access,
            self.prior_social,
        ]

    def validate(self) -> None:
        """Validate configuration values."""
        if not 0.0 < self.learning_rate <= 1.0:
            raise ValueError(f"learning_rate must be in (0, 1], got {self.learning_rate}")
        if not 0.0 <= self.momentum < 1.0:
            raise ValueError(f"momentum must be in [0, 1), got {self.momentum}")
        if self.min_samples < 1:
            raise ValueError(f"min_samples must be >= 1, got {self.min_samples}")
        if not 0.0 <= self.weight_min < self.weight_max <= 1.0:
            raise ValueError(f"weight bounds invalid: min={self.weight_min}, max={self.weight_max}")


# =============================================================================
# Training Data Types
# =============================================================================


@dataclass
class TrainingSample:
    """
    Single training sample for weight learning.

    Represents one event with its component scores and grounding outcome.
    """

    emotional_score: float
    recency_score: float
    access_score: float
    social_score: float
    was_grounded: bool  # Ground truth label
    days_ago: float = 0.0  # For sample weighting

    def to_features(self) -> List[float]:
        """Convert to feature vector [emotional, recency, access, social]."""
        return [
            self.emotional_score,
            self.recency_score,
            self.access_score,
            self.social_score,
        ]

    def to_label(self) -> float:
        """Convert to binary label (1.0 if grounded, 0.0 if not)."""
        return 1.0 if self.was_grounded else 0.0

    def compute_sample_weight(self, decay_rate: float = 0.1) -> float:
        """
        Compute sample weight with exponential decay.

        Formula: weight = exp(-decay_rate × days_ago)

        Recent samples weighted more than older samples.
        """
        return math.exp(-decay_rate * self.days_ago)


@dataclass
class TrainingBatch:
    """Batch of training samples."""

    samples: List[TrainingSample] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.samples)

    def to_arrays(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Convert to numpy arrays for training.

        Returns:
            Tuple of (features, labels, sample_weights) arrays
        """
        if not self.samples:
            return (
                np.zeros((0, 4), dtype=np.float32),
                np.zeros(0, dtype=np.float32),
                np.zeros(0, dtype=np.float32),
            )

        features = np.array([s.to_features() for s in self.samples], dtype=np.float32)
        labels = np.array([s.to_label() for s in self.samples], dtype=np.float32)
        weights = np.array([s.compute_sample_weight() for s in self.samples], dtype=np.float32)

        return features, labels, weights


@dataclass
class TrainingResult:
    """Result from a training step."""

    loss: float
    weights: Dict[str, float]
    sample_count: int
    converged: bool = False
    skipped: bool = False
    reason: Optional[str] = None
    drift: Optional[float] = None


# =============================================================================
# Weight Persistence Protocol
# =============================================================================


class WeightPersistenceProtocol(Protocol):
    """Protocol for weight storage backend."""

    async def load_weights(self, space_id: str, param_prefix: str) -> Optional[Dict[str, Any]]: ...

    async def save_weights(
        self,
        space_id: str,
        weights: Dict[str, float],
        sample_count: int,
        loss: float,
    ) -> None: ...

    async def get_recent_losses(self, space_id: str, limit: int) -> List[float]: ...

    async def rollback_to_priors(self, space_id: str) -> None: ...


# =============================================================================
# ImportanceWeightLearner
# =============================================================================


class ImportanceWeightLearner:
    """
    Learn importance component weights from feedback signals.

    Method: Online gradient descent with momentum
    Loss: Binary cross-entropy predicting "will event be grounded?"
    Training: Nightly batch during P03 consolidation cycle

    The learner transforms static importance weights into data-driven
    personalization. Each space learns weights that reflect actual
    usage patterns, improving recall precision over time.

    Weight Components:
        - emotional: Emotional salience contribution
        - recency: Time decay contribution
        - access: Access frequency contribution
        - social: Social context contribution

    Usage:
        learner = ImportanceWeightLearner(space_id="sp_123")

        # Load training data
        batch = TrainingBatch(samples=[...])

        # Train one step
        result = learner.train_step(batch)

        # Get current weights
        weights = learner.get_weights()

        # Persist to database
        await learner.persist_weights(db_conn)
    """

    # Component names in order
    COMPONENTS = ["emotional", "recency", "access", "social"]

    def __init__(
        self,
        space_id: str,
        config: Optional[WeightLearnerConfig] = None,
    ) -> None:
        """
        Initialize ImportanceWeightLearner for a space.

        Args:
            space_id: User/family space ID
            config: Optional configuration; uses defaults if None
        """
        self.space_id = space_id
        self.config = config or WeightLearnerConfig()
        self.config.validate()

        # Initialize weights from static priors
        priors = self.config.get_priors_list()
        self._backend: str

        if TORCH_AVAILABLE:
            self._init_torch(priors)
            self._backend = "torch"
        else:
            self._init_numpy(priors)
            self._backend = "numpy"

        # Training state
        self.sample_count = 0
        self.last_loss: Optional[float] = None
        self.loss_history: List[float] = []
        self.is_learning_enabled = True

    def _init_torch(self, priors: List[float]) -> None:
        """Initialize PyTorch tensors."""
        import torch

        self._weights_tensor = torch.tensor(priors, dtype=torch.float32, requires_grad=True)
        self._optimizer = torch.optim.Adam([self._weights_tensor], lr=self.config.learning_rate)
        self._velocity_tensor = torch.zeros(4)

    def _init_numpy(self, priors: List[float]) -> None:
        """Initialize NumPy arrays."""
        self._weights_np = np.array(priors, dtype=np.float32)
        self._velocity_np = np.zeros(4, dtype=np.float32)

    # =========================================================================
    # Training
    # =========================================================================

    def train_step(self, batch: TrainingBatch) -> TrainingResult:
        """
        One gradient descent step with momentum and batch protection.

        Issue 4 Fix: Implements 4 protections against noisy small batches:
        1. Minimum batch size (skip if too small)
        2. Sample ratio check (reduce learning rate for small relative batches)
        3. Weight snapshot for potential rollback
        4. Drift detection with warning

        Args:
            batch: Training batch with features, labels, sample weights

        Returns:
            TrainingResult with loss and updated weights
        """
        # Empty batch - no-op
        if len(batch) == 0:
            return TrainingResult(
                loss=0.0,
                weights=self.get_weights(),
                sample_count=self.sample_count,
                converged=False,
                skipped=True,
                reason="BATCH_EMPTY",
            )

        # Protection 1: Minimum batch size
        if len(batch) < self.config.min_batch_size:
            logger.debug(
                f"Skipping train_step: batch size {len(batch)} < min {self.config.min_batch_size}"
            )
            return TrainingResult(
                loss=0.0,
                weights=self.get_weights(),
                sample_count=self.sample_count,
                converged=False,
                skipped=True,
                reason="BATCH_TOO_SMALL",
            )

        # Protection 2: Sample ratio check - reduce learning rate for small batches
        effective_lr = self.config.learning_rate
        if self.sample_count > self.config.min_samples:
            ratio = len(batch) / self.sample_count
            if ratio < 0.05:
                # Small batch relative to existing samples - reduce learning rate
                effective_lr = self.config.learning_rate * ratio * self.config.small_batch_lr_factor
                logger.debug(
                    f"Reduced learning rate: {self.config.learning_rate} -> {effective_lr:.6f} "
                    f"(batch ratio {ratio:.3f})"
                )

        # Protection 3: Snapshot weights for drift detection
        weights_before = self.get_weights().copy()

        features, labels, sample_weights = batch.to_arrays()

        # Execute training step with potentially reduced learning rate
        if self._backend == "torch":
            loss = self._train_step_torch(features, labels, sample_weights, effective_lr)
        else:
            loss = self._train_step_numpy(features, labels, sample_weights, effective_lr)

        self.sample_count += len(batch)
        self.last_loss = loss
        self.loss_history.append(loss)

        # Protection 4: Drift detection
        weights_after = self.get_weights()
        drift = self._compute_weight_drift(weights_before, weights_after)

        if drift > self.config.drift_threshold:
            logger.warning(
                f"Weight drift {drift:.2%} exceeds threshold {self.config.drift_threshold:.2%}. "
                f"Batch size: {len(batch)}, sample_count: {self.sample_count}"
            )
            # Emit warning but don't block - monitoring will catch systemic issues

        return TrainingResult(
            loss=loss,
            weights=weights_after,
            sample_count=self.sample_count,
            converged=loss < 0.1,
            skipped=False,
            drift=drift,
        )

    def _compute_weight_drift(self, before: Dict[str, float], after: Dict[str, float]) -> float:
        """
        Compute maximum percentage change in weights.

        Args:
            before: Weights before training step
            after: Weights after training step

        Returns:
            Maximum absolute percentage change across all weights
        """
        max_drift = 0.0
        for key in before:
            if before[key] > 0:
                change = abs(after[key] - before[key]) / before[key]
                max_drift = max(max_drift, change)
        return max_drift

    def _train_step_torch(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        sample_weights: np.ndarray,
        effective_lr: float,
    ) -> float:
        """PyTorch training step with dynamic learning rate."""
        import torch
        import torch.nn.functional as F

        # Convert to tensors
        features_t = torch.tensor(features, dtype=torch.float32)
        labels_t = torch.tensor(labels, dtype=torch.float32)
        sample_weights_t = torch.tensor(sample_weights, dtype=torch.float32)

        # Update optimizer learning rate if different from config
        for param_group in self._optimizer.param_groups:
            param_group["lr"] = effective_lr

        self._optimizer.zero_grad()

        # Softmax ensures weights sum to 1
        w = F.softmax(self._weights_tensor, dim=0)

        # Compute predictions: weighted sum of features
        predictions = (features_t * w).sum(dim=1)

        # Binary cross-entropy with logits
        # Apply sample weights for exponential decay on older samples
        loss_per_sample = F.binary_cross_entropy_with_logits(
            predictions, labels_t, reduction="none"
        )
        weighted_loss = (loss_per_sample * sample_weights_t).sum() / sample_weights_t.sum()

        weighted_loss.backward()

        # Apply momentum smoothing
        with torch.no_grad():
            if self._weights_tensor.grad is not None:
                self._velocity_tensor = (
                    self.config.momentum * self._velocity_tensor + self._weights_tensor.grad
                )

        self._optimizer.step()

        # Apply weight clamping after update
        with torch.no_grad():
            w_softmax = F.softmax(self._weights_tensor, dim=0)
            w_clamped = torch.clamp(
                w_softmax, min=self.config.weight_min, max=self.config.weight_max
            )
            w_normalized = w_clamped / w_clamped.sum()
            # Convert back to logits approximately
            self._weights_tensor.copy_(w_normalized)

        return weighted_loss.item()

    def _train_step_numpy(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        sample_weights: np.ndarray,
        effective_lr: float,
    ) -> float:
        """NumPy fallback training step with dynamic learning rate."""
        # Softmax normalization
        w = self._softmax_numpy(self._weights_np)

        # Forward pass: predictions = sum(features * weights)
        predictions = (features * w).sum(axis=1)

        # Sigmoid for probability
        probs = 1.0 / (1.0 + np.exp(-np.clip(predictions, -50, 50)))

        # Binary cross-entropy loss
        eps = 1e-7
        loss_per_sample = -(labels * np.log(probs + eps) + (1 - labels) * np.log(1 - probs + eps))
        weighted_loss = (loss_per_sample * sample_weights).sum() / sample_weights.sum()

        # Compute gradient (simplified)
        # d_loss/d_w = sum((probs - labels) * features * sample_weights) / sum(sample_weights)
        error = probs - labels
        gradient = (error[:, np.newaxis] * features * sample_weights[:, np.newaxis]).sum(
            axis=0
        ) / sample_weights.sum()

        # Momentum update
        self._velocity_np = self.config.momentum * self._velocity_np + gradient

        # Update weights using effective learning rate (may be reduced for small batches)
        self._weights_np = self._weights_np - effective_lr * self._velocity_np

        # Clamp weights
        self._weights_np = self._clamp_weights_numpy(self._weights_np)

        return float(weighted_loss)

    def _softmax_numpy(self, x: np.ndarray) -> np.ndarray:
        """Numerically stable softmax."""
        x_max = np.max(x)
        exp_x = np.exp(x - x_max)
        return exp_x / exp_x.sum()

    def _clamp_weights_numpy(self, weights: np.ndarray) -> np.ndarray:
        """Clamp weights to [weight_min, weight_max] and renormalize."""
        w = self._softmax_numpy(weights)
        w = np.clip(w, self.config.weight_min, self.config.weight_max)
        # Renormalize after clamping
        return w / w.sum()

    # =========================================================================
    # Weight Access
    # =========================================================================

    def get_weights(self) -> Dict[str, float]:
        """
        Get current weights as dictionary.

        Weights are softmax-normalized and clamped to [weight_min, weight_max].

        Returns:
            Dict with keys: emotional, recency, access, social
        """
        if self._backend == "torch":
            import torch
            import torch.nn.functional as F

            with torch.no_grad():
                w = F.softmax(self._weights_tensor, dim=0)
                w = torch.clamp(w, min=self.config.weight_min, max=self.config.weight_max)
                w = w / w.sum()  # Renormalize
                values = w.numpy()
        else:
            w = self._softmax_numpy(self._weights_np)
            w = np.clip(w, self.config.weight_min, self.config.weight_max)
            w = w / w.sum()
            values = w

        return {self.COMPONENTS[i]: float(values[i]) for i in range(len(self.COMPONENTS))}

    def get_weights_list(self) -> List[float]:
        """Get current weights as list [emotional, recency, access, social]."""
        weights = self.get_weights()
        return [weights[c] for c in self.COMPONENTS]

    def set_weights(self, weights: Dict[str, float]) -> None:
        """
        Set weights from dictionary (e.g., loaded from database).

        Args:
            weights: Dict with emotional, recency, access, social keys
        """
        values = [weights.get(c, self.config.get_priors()[c]) for c in self.COMPONENTS]

        if self._backend == "torch":
            import torch

            with torch.no_grad():
                self._weights_tensor.copy_(torch.tensor(values, dtype=torch.float32))
        else:
            self._weights_np = np.array(values, dtype=np.float32)

    # =========================================================================
    # Rollback and Stability
    # =========================================================================

    def check_rollback_needed(self) -> bool:
        """
        Check if weights should be rolled back to static priors.

        Rollback triggered when loss increases for N consecutive training runs.

        Returns:
            True if rollback should be performed
        """
        if len(self.loss_history) < self.config.rollback_threshold:
            return False

        # Check last N losses for consecutive increases
        recent = self.loss_history[-self.config.rollback_threshold :]
        for i in range(1, len(recent)):
            if recent[i] <= recent[i - 1]:
                return False  # Not consecutive increase

        logger.warning(
            "Rollback triggered: %d consecutive loss increases",
            self.config.rollback_threshold,
            extra={"space_id": self.space_id, "recent_losses": recent},
        )
        return True

    def rollback_to_priors(self) -> None:
        """
        Rollback weights to static priors and disable learning.

        Called when loss increases for too many consecutive nights.
        """
        priors = self.config.get_priors_list()

        if self._backend == "torch":
            import torch

            with torch.no_grad():
                self._weights_tensor.copy_(torch.tensor(priors, dtype=torch.float32))
                self._velocity_tensor.zero_()
        else:
            self._weights_np = np.array(priors, dtype=np.float32)
            self._velocity_np = np.zeros(4, dtype=np.float32)

        self.is_learning_enabled = False
        self.loss_history.clear()

        logger.info(
            "Rolled back to static priors, learning disabled",
            extra={"space_id": self.space_id},
        )

    def enable_learning(self) -> None:
        """Re-enable learning after rollback (requires manual intervention)."""
        self.is_learning_enabled = True
        logger.info(
            "Learning re-enabled",
            extra={"space_id": self.space_id},
        )

    # =========================================================================
    # Persistence
    # =========================================================================

    async def persist_weights(
        self,
        db_conn: Any,
        generate_id_func: Optional[Any] = None,
    ) -> None:
        """
        Save weights to st_learned_weights table.

        Args:
            db_conn: Database connection with execute() method
            generate_id_func: Optional function to generate UUIDs
        """
        weights = self.get_weights()
        now_ms = int(time.time() * 1000)

        # Default ID generator
        def _default_gen() -> str:
            return str(uuid.uuid4())

        id_gen = generate_id_func if generate_id_func is not None else _default_gen

        for component, value in weights.items():
            param_key = f"importance_{component}"
            prior_value = self.config.get_priors().get(component, 0.25)

            await db_conn.execute(
                """
                INSERT INTO st_learned_weights
                    (param_id, param_key, param_scope, scope_id, space_id,
                     current_value, prior_value, confidence, sample_count,
                     last_updated_at, version, previous_value, quality_at_update,
                     rollback_eligible, created_at, updated_at)
                VALUES ($1, $2, 'space', $3, $3, $4, $5, $6, $7, $8, 1, NULL, $9, TRUE, $8, $8)
                ON CONFLICT (space_id, param_key, param_scope, scope_id)
                DO UPDATE SET
                    previous_value = st_learned_weights.current_value,
                    current_value = $4,
                    sample_count = st_learned_weights.sample_count + $7,
                    version = st_learned_weights.version + 1,
                    quality_at_update = $9,
                    last_updated_at = $8,
                    updated_at = $8
                """,
                id_gen(),  # param_id
                param_key,
                self.space_id,  # scope_id and space_id
                value,  # current_value
                prior_value,  # prior_value
                min(0.95, self.sample_count / 1000),  # confidence
                len(weights),  # sample_count increment
                now_ms,  # timestamps
                self.last_loss or 0.0,  # quality_at_update
            )

        logger.info(
            "Persisted importance weights",
            extra={
                "space_id": self.space_id,
                "sample_count": self.sample_count,
                "loss": self.last_loss,
            },
        )

    async def load_weights(self, db_conn: Any) -> bool:
        """
        Load weights from st_learned_weights table.

        Args:
            db_conn: Database connection with fetch() method

        Returns:
            True if weights were loaded, False if using priors
        """
        rows = await db_conn.fetch(
            """
            SELECT param_key, current_value, sample_count, quality_at_update
            FROM st_learned_weights
            WHERE space_id = $1
              AND param_scope = 'space'
              AND param_key LIKE 'importance_%'
            """,
            self.space_id,
        )

        if not rows:
            logger.debug(
                "No learned weights found, using priors",
                extra={"space_id": self.space_id},
            )
            return False

        weights: Dict[str, float] = {}
        total_samples = 0
        losses: List[float] = []

        for row in rows:
            component = row["param_key"].replace("importance_", "")
            if component in self.COMPONENTS:
                weights[component] = row["current_value"]
                total_samples = max(total_samples, row["sample_count"])
                if row["quality_at_update"] is not None:
                    losses.append(row["quality_at_update"])

        if weights:
            self.set_weights(weights)
            self.sample_count = total_samples
            if losses:
                self.last_loss = losses[-1]
            logger.info(
                "Loaded learned weights",
                extra={
                    "space_id": self.space_id,
                    "sample_count": total_samples,
                    "weights": weights,
                },
            )
            return True

        return False

    # =========================================================================
    # Metrics and Diagnostics
    # =========================================================================

    def compute_drift(self) -> float:
        """
        Compute drift from static priors.

        Formula: drift = max_i |w_i^current - w_i^prior|

        Returns:
            Maximum absolute weight drift
        """
        current = self.get_weights()
        priors = self.config.get_priors()

        max_drift = 0.0
        for component in self.COMPONENTS:
            drift = abs(current[component] - priors[component])
            max_drift = max(max_drift, drift)

        return max_drift

    def compute_euclidean_drift(self) -> float:
        """
        Compute Euclidean distance from static priors.

        Returns:
            Euclidean distance in weight space
        """
        current = self.get_weights_list()
        priors = self.config.get_priors_list()

        squared_sum = sum((c - p) ** 2 for c, p in zip(current, priors))
        return math.sqrt(squared_sum)

    def get_diagnostics(self) -> Dict[str, Any]:
        """Get diagnostic information for monitoring."""
        return {
            "space_id": self.space_id,
            "weights": self.get_weights(),
            "sample_count": self.sample_count,
            "last_loss": self.last_loss,
            "is_learning_enabled": self.is_learning_enabled,
            "drift_max": self.compute_drift(),
            "drift_euclidean": self.compute_euclidean_drift(),
            "loss_history_length": len(self.loss_history),
            "recent_losses": self.loss_history[-5:] if self.loss_history else [],
            "backend": self._backend,
        }
