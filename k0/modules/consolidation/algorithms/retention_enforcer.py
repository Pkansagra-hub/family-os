"""
RetentionEnforcer — Decay-based retention policy enforcement.

Evaluates records for archival/tombstoning based on decay factor.
Supports resurrection for re-accessed archived records.

Scientific Basis:
- Ebbinghaus (1885): Forgetting curve — memory strength decays exponentially
- Bjork & Bjork (1992): Retrieval strengthens memories (resurrection)

Spec Reference:
- Dossier 4.4.1.2: Retention Policy Enforcement
- M4_EXECUTION.md Issue 4.3.4

Resurrection Formula:
    new_decay = max(0.70, 0.50 + old_decay * 0.50)

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .decay_engine import DecayClassification, DecayConfig, UnifiedDecayEngine

# =============================================================================
# Constants
# =============================================================================

# Time constants
MS_PER_DAY = 24 * 60 * 60 * 1000  # 86,400,000 ms

# Resurrection constants (from Dossier 4.4.1.2)
RESURRECTION_FLOOR = 0.70  # Minimum decay after resurrection
RESURRECTION_BASE = 0.50  # Base decay boost
RESURRECTION_CARRY = 0.50  # Fraction of old decay preserved
RESURRECTION_ALERT_THRESHOLD = 3  # Log warning after this many resurrections


# =============================================================================
# Retention Decision
# =============================================================================


class RetentionDecision(Enum):
    """
    Retention policy decision for a record.

    Maps to archival_status column in database:
    - KEEP: Stay active, no action needed
    - ARCHIVE: Move to archive tier (cold storage, no index)
    - TOMBSTONE: Mark for deletion, will be pruned
    """

    KEEP = "KEEP"  # Record is healthy, keep active
    ARCHIVE = "ARCHIVE"  # Move to archive tier
    TOMBSTONE = "TOMBSTONE"  # Mark for deletion


class ResurrectionTrigger(Enum):
    """
    What caused a record to be resurrected.

    From Dossier 4.4.1.2:
    - EXPLICIT_ACCESS: User explicitly accessed/recalled the memory
    - ASSOCIATION_HIT: Memory was activated via associated memory
    - SEARCH_RESULT: Memory appeared in search results
    - CONSOLIDATION_RESCUE: P03 consolidation rescued during merge
    """

    EXPLICIT_ACCESS = "EXPLICIT_ACCESS"
    ASSOCIATION_HIT = "ASSOCIATION_HIT"
    SEARCH_RESULT = "SEARCH_RESULT"
    CONSOLIDATION_RESCUE = "CONSOLIDATION_RESCUE"


# =============================================================================
# Result Dataclasses
# =============================================================================


@dataclass
class RetentionResult:
    """
    Result of evaluating retention policy for a single record.

    Attributes:
        entity_id: Unique identifier of the record
        table_name: Source table (st_epi, st_sem, etc.)
        current_decay: Current decay factor [0, 1]
        classification: Decay classification (ACTIVE, ARCHIVE_CANDIDATE, etc.)
        decision: Retention decision (KEEP, ARCHIVE, TOMBSTONE)
        reason: Human-readable explanation
        days_since_access: Days since last observation
        importance_score: Record importance score
    """

    entity_id: str
    table_name: str
    current_decay: float
    classification: DecayClassification
    decision: RetentionDecision
    reason: str
    days_since_access: float = 0.0
    importance_score: float = 0.0


@dataclass
class ResurrectionResult:
    """
    Result of resurrecting an archived/tombstoned record.

    Attributes:
        entity_id: Unique identifier of the record
        table_name: Source table
        trigger: What caused the resurrection
        old_decay: Decay factor before resurrection
        new_decay: Decay factor after resurrection (boosted)
        old_status: Previous archival status
        new_status: New archival status (ACTIVE)
        resurrected_at: Timestamp of resurrection (ms)
        resurrection_count: Total times this record was resurrected
    """

    entity_id: str
    table_name: str
    trigger: ResurrectionTrigger
    old_decay: float
    new_decay: float
    old_status: str
    new_status: str = "ACTIVE"
    resurrected_at: int = 0
    resurrection_count: int = 1


@dataclass
class BatchRetentionResult:
    """
    Result of batch retention evaluation.

    Attributes:
        total_evaluated: Number of records evaluated
        keep_count: Records to keep active
        archive_count: Records to archive
        tombstone_count: Records to tombstone
        results: Individual retention results
        evaluation_time_ms: Time taken for evaluation (ms)
    """

    total_evaluated: int = 0
    keep_count: int = 0
    archive_count: int = 0
    tombstone_count: int = 0
    results: List[RetentionResult] = field(default_factory=list)
    evaluation_time_ms: float = 0.0

    def summary(self) -> Dict[str, Any]:
        """Return summary statistics."""
        return {
            "total": self.total_evaluated,
            "keep": self.keep_count,
            "archive": self.archive_count,
            "tombstone": self.tombstone_count,
            "evaluation_time_ms": self.evaluation_time_ms,
        }


# =============================================================================
# RetentionEnforcer Class
# =============================================================================


class RetentionEnforcer:
    """
    Decay-based retention policy enforcer.

    Evaluates records for archival/tombstoning and handles resurrection
    of re-accessed memories.

    Usage:
        enforcer = RetentionEnforcer()

        # Evaluate single record
        result = enforcer.evaluate(
            entity_id='mem_123',
            table_name='st_epi',
            last_observed_at=1700000000000,
            current_time=1705000000000,
        )
        # → RetentionResult(decision=RetentionDecision.ARCHIVE, ...)

        # Resurrect archived record
        res_result = enforcer.resurrect(
            entity_id='mem_123',
            table_name='st_epi',
            current_decay=0.05,
            current_status='ARCHIVED',
            trigger=ResurrectionTrigger.EXPLICIT_ACCESS,
        )
        # → ResurrectionResult(new_decay=0.70, ...)

    Spec: Dossier 4.4.1.2, M4_EXECUTION.md Issue 4.3.4
    """

    def __init__(
        self,
        decay_engine: Optional[UnifiedDecayEngine] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize retention enforcer.

        Args:
            decay_engine: Custom decay engine. Uses default if None.
            logger: Logger instance. Creates default if None.
        """
        self.decay_engine = decay_engine or UnifiedDecayEngine()
        self.logger = logger or logging.getLogger(__name__)

        # Track resurrection counts per entity (in-memory for now)
        self._resurrection_counts: Dict[str, int] = {}

    def evaluate(
        self,
        entity_id: str,
        table_name: str,
        last_observed_at: int,
        current_time: int,
        current_status: str = "ACTIVE",
        importance_score: float = 0.0,
        confidence_score: float = 0.0,
        observation_count: int = 1,
    ) -> RetentionResult:
        """
        Evaluate retention policy for a single record.

        Args:
            entity_id: Unique identifier of the record
            table_name: Source table (st_epi, st_sem, etc.)
            last_observed_at: Timestamp of last observation (ms)
            current_time: Current timestamp (ms)
            current_status: Current archival status (ACTIVE, ARCHIVED, TOMBSTONE)
            importance_score: Record importance [0, 1]
            confidence_score: Record confidence [0, 1]
            observation_count: Number of observations

        Returns:
            RetentionResult with decision and explanation
        """
        # Compute decay factor
        decay_factor = self.decay_engine.compute_decay_factor(
            table_name=table_name,
            last_observed_at=last_observed_at,
            current_time=current_time,
            importance_score=importance_score,
            confidence_score=confidence_score,
            observation_count=observation_count,
        )

        # Classify
        classification = self.decay_engine.classify_record(decay_factor)

        # Calculate days since access
        days_since_access = (current_time - last_observed_at) / MS_PER_DAY

        # Determine decision based on classification
        decision, reason = self._decide(
            classification=classification,
            decay_factor=decay_factor,
            current_status=current_status,
            importance_score=importance_score,
            days_since_access=days_since_access,
        )

        return RetentionResult(
            entity_id=entity_id,
            table_name=table_name,
            current_decay=decay_factor,
            classification=classification,
            decision=decision,
            reason=reason,
            days_since_access=days_since_access,
            importance_score=importance_score,
        )

    def _decide(
        self,
        classification: DecayClassification,
        decay_factor: float,
        current_status: str,
        importance_score: float,
        days_since_access: float,
    ) -> Tuple[RetentionDecision, str]:
        """
        Determine retention decision and reason.

        Decision logic (from Dossier 4.4.1.2):
        1. ACTIVE classification → KEEP
        2. ARCHIVE_CANDIDATE → ARCHIVE (unless already archived)
        3. PRUNE_CANDIDATE → TOMBSTONE

        Returns:
            Tuple of (decision, reason)
        """
        if classification == DecayClassification.ACTIVE:
            return (
                RetentionDecision.KEEP,
                f"Record is active (decay={decay_factor:.4f} >= 0.10)",
            )

        elif classification == DecayClassification.ARCHIVE_CANDIDATE:
            if current_status == "ARCHIVED":
                # Already archived, no action needed
                return (
                    RetentionDecision.KEEP,
                    f"Already archived (decay={decay_factor:.4f})",
                )
            return (
                RetentionDecision.ARCHIVE,
                f"Decay below threshold (decay={decay_factor:.4f}, "
                f"days_inactive={days_since_access:.1f})",
            )

        else:  # PRUNE_CANDIDATE
            if current_status == "TOMBSTONE":
                return (
                    RetentionDecision.KEEP,
                    f"Already tombstoned (decay={decay_factor:.4f})",
                )
            return (
                RetentionDecision.TOMBSTONE,
                f"Critically decayed (decay={decay_factor:.4f}, "
                f"days_inactive={days_since_access:.1f})",
            )

    def compute_resurrection_decay(self, old_decay: float) -> float:
        """
        Compute new decay factor after resurrection.

        Formula (from Dossier 4.4.1.2):
            new_decay = max(0.70, 0.50 + old_decay * 0.50)

        This ensures:
        - Minimum decay of 0.70 after resurrection (floor)
        - Preserves 50% of whatever decay remained
        - Caps at 1.0

        Args:
            old_decay: Current decay factor before resurrection [0, 1]

        Returns:
            New decay factor after resurrection [0.70, 1.0]
        """
        new_decay = RESURRECTION_BASE + old_decay * RESURRECTION_CARRY
        return max(RESURRECTION_FLOOR, min(1.0, new_decay))

    def resurrect(
        self,
        entity_id: str,
        table_name: str,
        current_decay: float,
        current_status: str,
        trigger: ResurrectionTrigger,
        current_time: Optional[int] = None,
    ) -> ResurrectionResult:
        """
        Resurrect an archived/tombstoned record.

        Called when a decayed record is re-accessed. Boosts decay factor
        and resets status to ACTIVE.

        Args:
            entity_id: Unique identifier of the record
            table_name: Source table
            current_decay: Current decay factor [0, 1]
            current_status: Current status (ARCHIVED, TOMBSTONE)
            trigger: What caused the resurrection
            current_time: Current timestamp (ms). Uses now if None.

        Returns:
            ResurrectionResult with old/new decay and status
        """
        if current_time is None:
            current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # Compute boosted decay
        new_decay = self.compute_resurrection_decay(current_decay)

        # Track resurrection count
        key = f"{table_name}:{entity_id}"
        count = self._resurrection_counts.get(key, 0) + 1
        self._resurrection_counts[key] = count

        # Log if threshold exceeded
        if count >= RESURRECTION_ALERT_THRESHOLD:
            self.logger.warning(
                f"High resurrection count: entity={entity_id} table={table_name} "
                f"count={count} trigger={trigger.value}"
            )

        result = ResurrectionResult(
            entity_id=entity_id,
            table_name=table_name,
            trigger=trigger,
            old_decay=current_decay,
            new_decay=new_decay,
            old_status=current_status,
            new_status="ACTIVE",
            resurrected_at=current_time,
            resurrection_count=count,
        )

        self.logger.info(
            f"Resurrected: entity={entity_id} table={table_name} "
            f"decay={current_decay:.4f}→{new_decay:.4f} trigger={trigger.value}"
        )

        return result

    def log_resurrection(self, result: ResurrectionResult) -> None:
        """
        Log resurrection event for audit trail.

        Args:
            result: Resurrection result to log
        """
        self.logger.info(
            f"RESURRECTION_AUDIT: entity_id={result.entity_id} "
            f"table={result.table_name} trigger={result.trigger.value} "
            f"old_decay={result.old_decay:.4f} new_decay={result.new_decay:.4f} "
            f"old_status={result.old_status} count={result.resurrection_count} "
            f"timestamp={result.resurrected_at}"
        )

    def evaluate_batch(
        self,
        records: List[Dict[str, Any]],
        current_time: int,
    ) -> BatchRetentionResult:
        """
        Evaluate retention policy for a batch of records.

        Args:
            records: List of records with keys:
                - entity_id: str
                - table_name: str
                - last_observed_at: int
                - current_status: str (optional)
                - importance_score: float (optional)
                - confidence_score: float (optional)
                - observation_count: int (optional)
            current_time: Current timestamp (ms)

        Returns:
            BatchRetentionResult with all decisions
        """
        import time

        start = time.monotonic()

        results: List[RetentionResult] = []
        keep_count = 0
        archive_count = 0
        tombstone_count = 0

        for record in records:
            result = self.evaluate(
                entity_id=record["entity_id"],
                table_name=record["table_name"],
                last_observed_at=record["last_observed_at"],
                current_time=current_time,
                current_status=record.get("current_status", "ACTIVE"),
                importance_score=record.get("importance_score", 0.0),
                confidence_score=record.get("confidence_score", 0.0),
                observation_count=record.get("observation_count", 1),
            )

            results.append(result)

            if result.decision == RetentionDecision.KEEP:
                keep_count += 1
            elif result.decision == RetentionDecision.ARCHIVE:
                archive_count += 1
            else:
                tombstone_count += 1

        elapsed = (time.monotonic() - start) * 1000

        return BatchRetentionResult(
            total_evaluated=len(records),
            keep_count=keep_count,
            archive_count=archive_count,
            tombstone_count=tombstone_count,
            results=results,
            evaluation_time_ms=elapsed,
        )

    def get_resurrection_count(self, entity_id: str, table_name: str) -> int:
        """
        Get resurrection count for an entity.

        Args:
            entity_id: Entity identifier
            table_name: Source table

        Returns:
            Number of times entity was resurrected
        """
        key = f"{table_name}:{entity_id}"
        return self._resurrection_counts.get(key, 0)

    def reset_resurrection_count(self, entity_id: str, table_name: str) -> None:
        """
        Reset resurrection count for an entity.

        Used when entity is permanently archived or deleted.

        Args:
            entity_id: Entity identifier
            table_name: Source table
        """
        key = f"{table_name}:{entity_id}"
        self._resurrection_counts.pop(key, None)

    def get_config(self) -> DecayConfig:
        """Get the decay engine configuration."""
        return self.decay_engine.config
