"""
Prune Decision Audit Logger.

Issue: 4.3.10
Spec Reference: Dossier §1.4.7 (lines 1800-2060), §6.20

Purpose: Record all prune/archive/tombstone decisions for:
- GDPR Article 22 compliance ("meaningful information about logic involved")
- Debugging and explainability
- Thompson Sampling feedback loop

Existing Table: st_consolidation_audit (0036_st_consolidation_audit.py)
"""

from __future__ import annotations

import json
import random
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol

# =============================================================================
# Enums
# =============================================================================


class PruneAction(Enum):
    """Prune decision action types.

    From spec §1.4.7:
    - ARCHIVE: decay_factor < 0.10, reversible via resurrection
    - TOMBSTONE: decay_factor < 0.01, permanent deletion
    - PRUNE: Explicit prune decision
    - SKIP: Decision to NOT prune (retained)
    """

    ARCHIVE = "ARCHIVE"
    TOMBSTONE = "TOMBSTONE"
    PRUNE = "PRUNE"
    SKIP = "SKIP"


# =============================================================================
# Protocols
# =============================================================================


class AuditStoreProtocol(Protocol):
    """Protocol for audit record storage."""

    async def insert_audit_record(
        self,
        record: "PruneAuditRecord",
    ) -> None:
        """Insert audit record to storage."""
        ...

    async def get_decision_history(
        self,
        memory_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get audit history for a memory."""
        ...


# =============================================================================
# Data Classes
# =============================================================================


@dataclass(frozen=True)
class PruneDecisionContext:
    """Context for a prune decision.

    All inputs that contributed to the decision.

    Attributes:
        memory_id: ID of the memory being evaluated.
        source_table: Table containing the memory (st_epi, st_sem, etc.).
        decay_factor: Current decay factor value.
        effective_lambda: Lambda value used for decay.
        days_since_access: Days since last access.
        access_count: Total access count.
        is_immune: Whether entity is decay_immune.
        threshold_used: Threshold that triggered decision.
        threshold_name: Name of threshold (archive, tombstone).
    """

    memory_id: str
    source_table: str
    decay_factor: float
    effective_lambda: float
    days_since_access: int
    access_count: int
    is_immune: bool
    threshold_used: float
    threshold_name: str

    def to_inputs_dict(self) -> Dict[str, Any]:
        """Convert to inputs dictionary for JSON serialization."""
        return {
            "decay_factor": self.decay_factor,
            "effective_lambda": self.effective_lambda,
            "days_since_access": self.days_since_access,
            "access_count": self.access_count,
            "is_immune": self.is_immune,
        }

    def to_outputs_dict(self, action: PruneAction) -> Dict[str, Any]:
        """Convert to outputs dictionary for JSON serialization."""
        return {
            "action": action.value,
            "threshold_used": self.threshold_used,
            "threshold_name": self.threshold_name,
        }


@dataclass
class PruneAuditRecord:
    """Audit record for a prune decision.

    Matches st_consolidation_audit schema from 0036.

    Attributes:
        audit_id: Unique identifier for this audit record.
        memory_id: ID of the memory being evaluated.
        source_table: Table containing the memory.
        action: The prune action taken.
        formula_used: Name of formula used.
        formula_version: Version of formula.
        inputs_json: JSON string of decision inputs.
        outputs_json: JSON string of decision outputs.
        explanation: Human-readable explanation.
        decision_id: Links related decisions.
        space_id: Space containing the memory.
        tenant_id: Tenant owning the space.
        cycle_id: Consolidation cycle ID.
        confidence: Confidence score (decay_factor).
        created_at: Timestamp in milliseconds.
        threshold_used: Threshold that triggered decision.
        threshold_name: Name of threshold.
        outcome_evaluated: Whether outcome has been evaluated.
        outcome_success: Whether decision was successful.
        evaluated_at: When outcome was evaluated.
    """

    audit_id: str
    memory_id: str
    source_table: str
    action: PruneAction
    formula_used: str
    formula_version: str
    inputs_json: str
    outputs_json: str
    explanation: str
    decision_id: str
    space_id: str
    tenant_id: str
    cycle_id: str
    confidence: float
    created_at: int
    threshold_used: float
    threshold_name: str
    outcome_evaluated: bool = False
    outcome_success: Optional[bool] = None
    evaluated_at: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "audit_id": self.audit_id,
            "memory_id": self.memory_id,
            "source_table": self.source_table,
            "action": self.action.value,
            "formula_used": self.formula_used,
            "formula_version": self.formula_version,
            "inputs_json": self.inputs_json,
            "outputs_json": self.outputs_json,
            "explanation": self.explanation,
            "decision_id": self.decision_id,
            "space_id": self.space_id,
            "tenant_id": self.tenant_id,
            "cycle_id": self.cycle_id,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "threshold_used": self.threshold_used,
            "threshold_name": self.threshold_name,
            "outcome_evaluated": self.outcome_evaluated,
            "outcome_success": self.outcome_success,
            "evaluated_at": self.evaluated_at,
        }


@dataclass
class PruneAuditLoggerConfig:
    """Configuration for PruneAuditLogger.

    Attributes:
        enabled: Master switch for audit logging.
        sample_rate_production: Sampling rate in production (default 10%).
        sample_rate_debug: Sampling rate in debug (default 100%).
        is_debug: Whether debug mode is enabled.
        retention_days: Days to retain audit records.
        formula_name: Name of decay formula used.
        formula_version: Version of decay formula.
    """

    enabled: bool = True
    sample_rate_production: float = 0.10
    sample_rate_debug: float = 1.0
    is_debug: bool = False
    retention_days: int = 90
    formula_name: str = "UnifiedDecayFormula"
    formula_version: str = "1.0"

    def validate(self) -> None:
        """Validate configuration."""
        if not (0.0 <= self.sample_rate_production <= 1.0):
            raise ValueError(
                f"sample_rate_production must be in [0, 1]: {self.sample_rate_production}"
            )
        if not (0.0 <= self.sample_rate_debug <= 1.0):
            raise ValueError(f"sample_rate_debug must be in [0, 1]: {self.sample_rate_debug}")
        if self.retention_days < 1:
            raise ValueError(f"retention_days must be >= 1: {self.retention_days}")

    @property
    def sample_rate(self) -> float:
        """Get effective sample rate based on debug mode."""
        return self.sample_rate_debug if self.is_debug else self.sample_rate_production


# =============================================================================
# In-Memory Store for Testing
# =============================================================================


class InMemoryAuditStore:
    """In-memory audit store for testing.

    Implements AuditStoreProtocol.
    """

    def __init__(self) -> None:
        """Initialize store."""
        self._records: List[PruneAuditRecord] = []

    async def insert_audit_record(
        self,
        record: PruneAuditRecord,
    ) -> None:
        """Insert audit record."""
        self._records.append(record)

    async def get_decision_history(
        self,
        memory_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get audit history for a memory."""
        matching = [r.to_dict() for r in self._records if r.memory_id == memory_id]
        # Sort by created_at descending
        matching.sort(key=lambda x: x["created_at"], reverse=True)
        return matching[:limit]

    def get_all_records(self) -> List[PruneAuditRecord]:
        """Get all records (for testing)."""
        return list(self._records)

    def count_by_action(self, action: PruneAction) -> int:
        """Count records by action type."""
        return sum(1 for r in self._records if r.action == action)

    def clear(self) -> None:
        """Clear all records."""
        self._records.clear()


# =============================================================================
# PruneAuditLogger Class
# =============================================================================


class PruneAuditLogger:
    """
    Log all prune/archive/tombstone decisions to st_consolidation_audit.

    Spec: Dossier §1.4.7, §6.20

    Features:
    - Full decision context captured
    - Sampling for production (10%) vs debug (100%)
    - TOMBSTONE always logged (100%)
    - Links to Thompson Sampling outcome tracking

    Usage:
        logger = PruneAuditLogger(config=PruneAuditLoggerConfig(is_debug=True))
        audit_id = await logger.log_prune_decision(
            action=PruneAction.ARCHIVE,
            context=context,
            space_id="space_1",
            tenant_id="tenant_1",
            cycle_id="cycle_123",
            store=audit_store,
        )
    """

    def __init__(
        self,
        config: Optional[PruneAuditLoggerConfig] = None,
    ) -> None:
        """
        Initialize PruneAuditLogger.

        Args:
            config: Configuration for logging behavior.
        """
        self.config = config or PruneAuditLoggerConfig()
        self.config.validate()

        # Metrics tracking
        self._logged_count: Dict[str, int] = {}
        self._sampled_out_count: Dict[str, int] = {}

    def should_log(self, action: PruneAction) -> bool:
        """
        Determine if this decision should be logged.

        Always log:
        - TOMBSTONE (permanent deletion) - 100%

        Sample log:
        - ARCHIVE (per sample rate)
        - PRUNE (per sample rate)
        - SKIP (per sample rate)

        Args:
            action: The prune action.

        Returns:
            True if decision should be logged.
        """
        if not self.config.enabled:
            return False

        # TOMBSTONE always logged - permanent deletion requires audit
        if action == PruneAction.TOMBSTONE:
            return True

        # Other actions sampled
        return random.random() < self.config.sample_rate

    async def log_prune_decision(
        self,
        action: PruneAction,
        context: PruneDecisionContext,
        space_id: str,
        tenant_id: str,
        cycle_id: str,
        store: AuditStoreProtocol,
    ) -> Optional[str]:
        """
        Log a prune decision to st_consolidation_audit.

        Args:
            action: The prune action taken.
            context: Decision context with all inputs.
            space_id: Space containing the memory.
            tenant_id: Tenant owning the space.
            cycle_id: Consolidation cycle ID.
            store: Audit store for persistence.

        Returns:
            audit_id if logged, None if sampled out or disabled.
        """
        if not self.should_log(action):
            # Track sampled out
            self._sampled_out_count[action.value] = self._sampled_out_count.get(action.value, 0) + 1
            return None

        # Generate audit ID
        audit_id = str(uuid.uuid4())

        # Generate explanation
        explanation = self._generate_explanation(action, context)

        # Build JSON strings
        inputs_json = json.dumps(context.to_inputs_dict())
        outputs_json = json.dumps(context.to_outputs_dict(action))

        # Create audit record
        record = PruneAuditRecord(
            audit_id=audit_id,
            memory_id=context.memory_id,
            source_table=context.source_table,
            action=action,
            formula_used=self.config.formula_name,
            formula_version=self.config.formula_version,
            inputs_json=inputs_json,
            outputs_json=outputs_json,
            explanation=explanation,
            decision_id=audit_id,  # decision_id = audit_id for prune decisions
            space_id=space_id,
            tenant_id=tenant_id,
            cycle_id=cycle_id,
            confidence=context.decay_factor,  # confidence = decay_factor
            created_at=_now_ms(),
            threshold_used=context.threshold_used,
            threshold_name=context.threshold_name,
            outcome_evaluated=False,
        )

        # Persist record
        await store.insert_audit_record(record)

        # Track logged count
        self._logged_count[action.value] = self._logged_count.get(action.value, 0) + 1

        return audit_id

    def _generate_explanation(
        self,
        action: PruneAction,
        context: PruneDecisionContext,
    ) -> str:
        """Generate human-readable explanation for decision.

        Args:
            action: The prune action.
            context: Decision context.

        Returns:
            Human-readable explanation string.
        """
        if context.is_immune:
            return "SKIP: Entity is decay_immune (never prune)"

        if action == PruneAction.ARCHIVE:
            return (
                f"ARCHIVE: decay_factor={context.decay_factor:.3f} < "
                f"threshold={context.threshold_used:.2f}. "
                f"Not accessed in {context.days_since_access} days. "
                f"Total accesses: {context.access_count}. "
                f"Can be resurrected if queried."
            )

        if action == PruneAction.TOMBSTONE:
            return (
                f"TOMBSTONE: decay_factor={context.decay_factor:.4f} < 0.01. "
                f"Entity has {context.access_count} lifetime accesses over "
                f"{context.days_since_access} days. "
                f"PERMANENT deletion per retention policy."
            )

        if action == PruneAction.PRUNE:
            return (
                f"PRUNE: Explicit prune decision. "
                f"decay_factor={context.decay_factor:.3f}. "
                f"Entity has {context.access_count} lifetime accesses."
            )

        if action == PruneAction.SKIP:
            return (
                f"SKIP: decay_factor={context.decay_factor:.3f} >= "
                f"threshold={context.threshold_used:.2f}. "
                f"Entity retained."
            )

        return f"{action.value}: No explanation available"

    async def get_decision_history(
        self,
        memory_id: str,
        store: AuditStoreProtocol,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get audit history for a specific memory.

        Args:
            memory_id: Memory ID to query.
            store: Audit store to query.
            limit: Maximum records to return.

        Returns:
            List of audit records as dictionaries.
        """
        return await store.get_decision_history(memory_id, limit)

    def get_logged_count(self, action: PruneAction) -> int:
        """Get count of logged decisions for action type."""
        return self._logged_count.get(action.value, 0)

    def get_sampled_out_count(self, action: PruneAction) -> int:
        """Get count of sampled-out decisions for action type."""
        return self._sampled_out_count.get(action.value, 0)

    def reset_counts(self) -> None:
        """Reset all counters."""
        self._logged_count.clear()
        self._sampled_out_count.clear()


# =============================================================================
# Integration Helpers
# =============================================================================


def determine_prune_action(
    decay_factor: float,
    is_immune: bool,
    archive_threshold: float = 0.10,
    tombstone_threshold: float = 0.01,
) -> tuple[PruneAction, float, str]:
    """
    Determine prune action based on decay factor.

    Args:
        decay_factor: Current decay factor value.
        is_immune: Whether entity is decay_immune.
        archive_threshold: Threshold for ARCHIVE action.
        tombstone_threshold: Threshold for TOMBSTONE action.

    Returns:
        Tuple of (action, threshold_used, threshold_name).
    """
    if is_immune:
        return (PruneAction.SKIP, 0.0, "immune")

    if decay_factor < tombstone_threshold:
        return (PruneAction.TOMBSTONE, tombstone_threshold, "tombstone")

    if decay_factor < archive_threshold:
        return (PruneAction.ARCHIVE, archive_threshold, "archive")

    return (PruneAction.SKIP, archive_threshold, "archive")


def build_prune_context(
    memory_id: str,
    source_table: str,
    decay_factor: float,
    effective_lambda: float,
    days_since_access: int,
    access_count: int,
    is_immune: bool,
    archive_threshold: float = 0.10,
    tombstone_threshold: float = 0.01,
) -> tuple[PruneAction, PruneDecisionContext]:
    """
    Build prune context and determine action.

    Helper for integration with UnifiedDecayEngine.

    Args:
        memory_id: ID of memory.
        source_table: Table containing memory.
        decay_factor: Current decay factor.
        effective_lambda: Lambda used for decay.
        days_since_access: Days since last access.
        access_count: Total access count.
        is_immune: Whether entity is immune.
        archive_threshold: Threshold for ARCHIVE.
        tombstone_threshold: Threshold for TOMBSTONE.

    Returns:
        Tuple of (action, context).
    """
    action, threshold_used, threshold_name = determine_prune_action(
        decay_factor=decay_factor,
        is_immune=is_immune,
        archive_threshold=archive_threshold,
        tombstone_threshold=tombstone_threshold,
    )

    context = PruneDecisionContext(
        memory_id=memory_id,
        source_table=source_table,
        decay_factor=decay_factor,
        effective_lambda=effective_lambda,
        days_since_access=days_since_access,
        access_count=access_count,
        is_immune=is_immune,
        threshold_used=threshold_used,
        threshold_name=threshold_name,
    )

    return action, context


# =============================================================================
# Utility Functions
# =============================================================================


def _now_ms() -> int:
    """Get current time in milliseconds."""
    return int(time.time() * 1000)


def parse_inputs_json(inputs_json: str) -> Dict[str, Any]:
    """Parse inputs JSON from audit record."""
    return json.loads(inputs_json)


def parse_outputs_json(outputs_json: str) -> Dict[str, Any]:
    """Parse outputs JSON from audit record."""
    return json.loads(outputs_json)
