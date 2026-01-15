"""
P03 Decision Audit Logger - Write path for consolidation decisions.

This module implements the audit logging for P03 consolidation decisions,
writing structured records to st_consolidation_audit for explainability,
debugging, and learning analysis.

Spec Reference: Dossier §6.20, §14.10

DESIGN DECISIONS:
    - Writes all audit fields from st_consolidation_audit schema
    - Accepts structured inputs/outputs and serializes to JSON text
    - Never logs raw PII (IDs only); applies K0 redaction
    - Idempotent per audit_id (ULID-based)

TIMESTAMP CONVENTION (LOCKED):
    All `*_at` and `*_ts` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .context import generate_ulid

# =============================================================================
# AUDIT ACTION ENUM
# =============================================================================


class AuditAction(Enum):
    """
    Valid consolidation actions for audit records.

    These map to the CHECK constraint on st_consolidation_audit.action.
    """

    REINFORCE = "REINFORCE"
    DECAY = "DECAY"
    ARCHIVE = "ARCHIVE"
    MERGE = "MERGE"
    CREATE = "CREATE"
    EXTEND = "EXTEND"
    PRUNE = "PRUNE"
    SKIP = "SKIP"
    CONTRADICT = "CONTRADICT"
    SCORE = "SCORE"  # Issue 4.1.2: Importance scoring audit action


# =============================================================================
# EXPLANATION TEMPLATES (Section 14.10)
# =============================================================================


EXPLANATION_TEMPLATES: Dict[AuditAction, str] = {
    AuditAction.REINFORCE: (
        "Memory reinforced based on {formula_used} with confidence {confidence:.2f}. "
        "Strength increased from {old_strength:.2f} to {new_strength:.2f}."
    ),
    AuditAction.DECAY: (
        "Memory decayed due to time elapsed since last access. "
        "Strength reduced from {old_strength:.2f} to {new_strength:.2f}."
    ),
    AuditAction.ARCHIVE: (
        "Memory archived after reaching minimum strength threshold. "
        "Final strength: {final_strength:.2f}."
    ),
    AuditAction.MERGE: (
        "Memory merged with similar existing memory (similarity: {similarity:.2f}). "
        "Merged into memory_id: {merged_into}."
    ),
    AuditAction.CREATE: (
        "New memory created from hippocampus event. " "Initial strength: {initial_strength:.2f}."
    ),
    AuditAction.EXTEND: (
        "Memory extended with new associations. " "Added {association_count} new links."
    ),
    AuditAction.PRUNE: (
        "Memory pruned due to low relevance score ({relevance:.2f}). "
        "Below threshold: {threshold:.2f}."
    ),
    AuditAction.SKIP: ("Event skipped - no consolidation action required. Reason: {skip_reason}."),
    AuditAction.CONTRADICT: (
        "Contradicting evidence detected (confidence: {contradiction_confidence:.2f}). "
        "Existing memory strength reduced."
    ),
    AuditAction.SCORE: (
        "Importance score computed: {importance_score:.3f} (priority: {priority_tier}). "
        "Components: emotional={emotional:.3f}, novelty={novelty:.3f}, social={social:.3f}, "
        "multiplier={multiplier:.2f}. Weights source: {weights_source}."
    ),
}


# =============================================================================
# PII REDACTION FIELDS
# =============================================================================


# Fields that must NEVER appear in audit records (RED-band forbidden)
RED_BAND_FIELDS: frozenset[str] = frozenset(
    {
        "raw_content",
        "message_body",
        "user_input",
        "personal_name",
        "email",
        "phone",
        "address",
        "ssn",
        "credit_card",
        "password",
        "api_key",
        "secret",
        "token",
        "biometric",
        "health_data",
        "financial_data",
        "location_precise",
    }
)


def redact_pii_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove RED-band forbidden fields from a dictionary.

    Args:
        data: Dictionary that may contain PII fields

    Returns:
        New dictionary with RED-band fields removed
    """
    return {k: v for k, v in data.items() if k.lower() not in RED_BAND_FIELDS}


# =============================================================================
# AUDIT RECORD DATACLASS
# =============================================================================


@dataclass
class AuditRecord:
    """
    A single audit record for a consolidation decision.

    All fields match st_consolidation_audit schema from Dossier §6.20.
    """

    # Primary key - generated automatically if not provided
    audit_id: str = field(default_factory=generate_ulid)

    # Core reference columns
    memory_id: str = ""
    source_table: str = ""
    action: AuditAction = AuditAction.SKIP

    # Formula tracking
    formula_used: Optional[str] = None
    formula_version: Optional[str] = None

    # Input/output JSON for debugging (will be redacted and serialized)
    inputs: Optional[Dict[str, Any]] = None
    outputs: Optional[Dict[str, Any]] = None

    # Explainability
    explanation: Optional[str] = None
    decision_id: Optional[str] = None

    # Context columns
    space_id: str = ""
    tenant_id: str = ""
    cycle_id: Optional[str] = None
    confidence: Optional[float] = None
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))

    # Outcome tracking columns (from Section 1.4.7)
    threshold_used: Optional[float] = None
    threshold_name: Optional[str] = None
    outcome_evaluated: bool = False
    outcome_success: Optional[bool] = None
    evaluated_at: Optional[int] = None

    def generate_explanation(self, template_params: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate user-friendly explanation from template.

        Args:
            template_params: Parameters to fill in template placeholders

        Returns:
            Formatted explanation string
        """
        template = EXPLANATION_TEMPLATES.get(self.action, "Decision made: {action}")
        params = template_params or {}

        # Add default params
        params.setdefault("action", self.action.value)
        params.setdefault("confidence", self.confidence or 0.0)
        params.setdefault("formula_used", self.formula_used or "unknown")

        try:
            return template.format(**params)
        except KeyError:
            # If template params are missing, return basic explanation
            return f"Action {self.action.value} taken on memory {self.memory_id}"

    def to_db_row(self) -> Dict[str, Any]:
        """
        Convert to database row dictionary for insertion.

        Handles:
        - Redaction of PII fields from inputs/outputs
        - JSON serialization of dict fields
        - Enum to string conversion

        Returns:
            Dictionary matching st_consolidation_audit columns
        """
        # Redact and serialize inputs
        inputs_json = None
        if self.inputs:
            redacted_inputs = redact_pii_fields(self.inputs)
            inputs_json = json.dumps(redacted_inputs, default=str)

        # Redact and serialize outputs
        outputs_json = None
        if self.outputs:
            redacted_outputs = redact_pii_fields(self.outputs)
            outputs_json = json.dumps(redacted_outputs, default=str)

        return {
            "audit_id": self.audit_id,
            "memory_id": self.memory_id,
            "source_table": self.source_table,
            "action": self.action.value,
            "formula_used": self.formula_used,
            "formula_version": self.formula_version,
            "inputs_json": inputs_json,
            "outputs_json": outputs_json,
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


# =============================================================================
# AUDIT LOGGER CLASS
# =============================================================================


class P03AuditLogger:
    """
    Audit logger for P03 consolidation decisions.

    Accumulates audit records during a consolidation cycle and provides
    methods for batch writing to st_consolidation_audit.

    Thread Safety:
        NOT thread-safe. Use one logger per cycle/context.

    Usage:
        logger = P03AuditLogger(space_id="sp_123", tenant_id="t_1", cycle_id="cyc_abc")
        logger.log_decision(
            memory_id="mem_xyz",
            source_table="st_epi",
            action=AuditAction.REINFORCE,
            formula_used="hebbian_v2",
            inputs={"strength": 0.5},
            outputs={"new_strength": 0.7},
            confidence=0.85,
        )
        rows = logger.get_pending_records()  # For batch insert
    """

    def __init__(
        self,
        space_id: str,
        tenant_id: str,
        cycle_id: Optional[str] = None,
    ):
        """
        Initialize audit logger for a consolidation context.

        Args:
            space_id: User/family space ID
            tenant_id: Tenant ID for multi-tenant isolation
            cycle_id: Optional consolidation cycle ID for correlation
        """
        self.space_id = space_id
        self.tenant_id = tenant_id
        self.cycle_id = cycle_id
        self._pending_records: List[AuditRecord] = []
        self._logged_audit_ids: set[str] = set()

    def log_decision(
        self,
        memory_id: str,
        source_table: str,
        action: AuditAction,
        formula_used: Optional[str] = None,
        formula_version: Optional[str] = None,
        inputs: Optional[Dict[str, Any]] = None,
        outputs: Optional[Dict[str, Any]] = None,
        decision_id: Optional[str] = None,
        confidence: Optional[float] = None,
        threshold_used: Optional[float] = None,
        threshold_name: Optional[str] = None,
        template_params: Optional[Dict[str, Any]] = None,
        audit_id: Optional[str] = None,
    ) -> AuditRecord:
        """
        Log a consolidation decision.

        Args:
            memory_id: ID of the affected memory
            source_table: Target table (st_epi, st_kg_dom, etc.)
            action: The consolidation action taken
            formula_used: Algorithm/formula name
            formula_version: Version for rollback tracking
            inputs: Input parameters to formula (will be redacted)
            outputs: Output values from formula (will be redacted)
            decision_id: Links to decision outcome tracking
            confidence: Decision confidence [0-1]
            threshold_used: Threshold value that triggered decision
            threshold_name: Name of threshold parameter
            template_params: Additional params for explanation template
            audit_id: Optional explicit audit ID (for idempotency)

        Returns:
            The created AuditRecord
        """
        # Generate or use provided audit_id
        record_id = audit_id or generate_ulid()

        # Idempotency check
        if record_id in self._logged_audit_ids:
            # Return existing record (find and return)
            for record in self._pending_records:
                if record.audit_id == record_id:
                    return record
            # Should not happen, but create new if not found
            pass

        # Create record
        record = AuditRecord(
            audit_id=record_id,
            memory_id=memory_id,
            source_table=source_table,
            action=action,
            formula_used=formula_used,
            formula_version=formula_version,
            inputs=inputs,
            outputs=outputs,
            decision_id=decision_id,
            space_id=self.space_id,
            tenant_id=self.tenant_id,
            cycle_id=self.cycle_id,
            confidence=confidence,
            threshold_used=threshold_used,
            threshold_name=threshold_name,
        )

        # Generate explanation from template
        record.explanation = record.generate_explanation(template_params)

        # Track for idempotency
        self._logged_audit_ids.add(record_id)
        self._pending_records.append(record)

        return record

    def get_pending_records(self) -> List[AuditRecord]:
        """
        Get all pending audit records for batch writing.

        Returns:
            List of AuditRecord objects
        """
        return list(self._pending_records)

    def get_pending_db_rows(self) -> List[Dict[str, Any]]:
        """
        Get all pending records as database row dictionaries.

        Returns:
            List of dictionaries ready for database insertion
        """
        return [record.to_db_row() for record in self._pending_records]

    def clear_pending(self) -> int:
        """
        Clear all pending records after successful commit.

        Returns:
            Number of records cleared
        """
        count = len(self._pending_records)
        self._pending_records.clear()
        self._logged_audit_ids.clear()
        return count

    def record_count(self) -> int:
        """Return count of pending records."""
        return len(self._pending_records)

    def has_records(self) -> bool:
        """Check if there are pending records."""
        return len(self._pending_records) > 0


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def create_audit_logger(
    space_id: str,
    tenant_id: str,
    cycle_id: Optional[str] = None,
) -> P03AuditLogger:
    """
    Factory function to create an audit logger.

    Args:
        space_id: User/family space ID
        tenant_id: Tenant ID for multi-tenant isolation
        cycle_id: Optional consolidation cycle ID

    Returns:
        Configured P03AuditLogger instance
    """
    return P03AuditLogger(space_id=space_id, tenant_id=tenant_id, cycle_id=cycle_id)
