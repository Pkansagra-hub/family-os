"""
ReconciliationRecorder — Reconciliation decision audit trail for R6.

Records complete reconciliation decision history per event, including
matched truth record, similarity scores, and decision reasoning.

Issue: 5.1.4
Spec Reference:
    - Dossier §4.7.3 (Reconciliation Decision Recording)
    - Dossier §4.3.2 (Decision Engine)
    - M5_EXECUTION.md Issue 5.1.4

Decision Fields Recorded:
    - reconciliation_action: PENDING, REINFORCE, EXTEND, CREATE, EVOLVE, CONTRADICT, PRUNE, SKIP
    - best_match_id: Matched truth record ID
    - best_match_layer: Truth layer (st_epi, st_sem, etc.)
    - similarity_score: Cosine similarity [0, 1]
    - confidence: Decision confidence [0, 1]
    - reconciliation_reason: Human-readable explanation
    - decision_timestamp_ms: When decision was made

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from k0.pipelines.p03.event_state import P03EventState, ReconciliationAction

# =============================================================================
# ReconciliationRecord Dataclass
# =============================================================================


@dataclass
class ReconciliationRecord:
    """
    Complete reconciliation decision record for an event.

    Captures all decision-relevant fields for audit trail and debugging.

    Attributes:
        event_id: The event this record belongs to
        reconciliation_action: Action taken (REINFORCE, CREATE, etc.)
        best_match_id: Matched truth record ID (None for CREATE/SKIP)
        best_match_layer: Truth layer of match (st_epi, st_sem, etc.)
        similarity_score: Cosine similarity to best match [0, 1]
        confidence: Decision confidence [0, 1]
        reconciliation_reason: Human-readable explanation
        decision_timestamp_ms: Timestamp when decision was recorded (ms epoch)
    """

    event_id: str
    reconciliation_action: str
    best_match_id: Optional[str]
    best_match_layer: Optional[str]
    similarity_score: float
    confidence: float
    reconciliation_reason: str
    decision_timestamp_ms: int

    def __post_init__(self) -> None:
        """Validate record fields."""
        # Validate action is a known value
        valid_actions = {a.value for a in ReconciliationAction}
        if self.reconciliation_action not in valid_actions:
            raise ValueError(
                f"Invalid reconciliation_action: {self.reconciliation_action}. "
                f"Must be one of: {valid_actions}"
            )

        # Clamp scores to [0, 1]
        self.similarity_score = max(0.0, min(1.0, self.similarity_score))
        self.confidence = max(0.0, min(1.0, self.confidence))

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dict for JSON serialization.

        Uses compact field names for storage efficiency.
        """
        return {
            "action": self.reconciliation_action,
            "match_id": self.best_match_id,
            "match_layer": self.best_match_layer,
            "similarity": round(self.similarity_score, 4),
            "confidence": round(self.confidence, 4),
            "reason": self.reconciliation_reason,
            "decided_at_ms": self.decision_timestamp_ms,
        }

    def to_json(self) -> str:
        """Serialize to compact JSON string."""
        return json.dumps(self.to_dict(), separators=(",", ":"))


# =============================================================================
# ReconciliationRecorder Class
# =============================================================================


class ReconciliationRecorder:
    """
    Records reconciliation decisions from P03EventState for audit trail.

    Extracts decision fields from event state and creates ReconciliationRecord
    objects for storage in st_hipp_events.reconciliation_json.

    Usage:
        recorder = ReconciliationRecorder()

        # Single event
        record = recorder.record(event_state)
        json_str = record.to_json()

        # Batch of events
        records = recorder.record_batch(event_states)

        # Get JSON for st_hipp_events update
        json_str = recorder.to_json(record)
    """

    # Actions that should have a truth match recorded
    MATCH_REQUIRED_ACTIONS = frozenset(
        {
            ReconciliationAction.REINFORCE,
            ReconciliationAction.EXTEND,
            ReconciliationAction.EVOLVE,
        }
    )

    # Actions that create new records (no match expected)
    NO_MATCH_ACTIONS = frozenset(
        {
            ReconciliationAction.CREATE,
            ReconciliationAction.PRUNE,
            ReconciliationAction.SKIP,
            ReconciliationAction.PENDING,
        }
    )

    def __init__(self, timestamp_provider: Optional[Callable[[], int]] = None) -> None:
        """
        Initialize the recorder.

        Args:
            timestamp_provider: Optional function that returns current time in ms.
                               Defaults to time.time() * 1000
        """
        self._get_timestamp = timestamp_provider or (lambda: int(time.time() * 1000))

    def record(
        self,
        event_state: P03EventState,
        timestamp_ms: Optional[int] = None,
    ) -> ReconciliationRecord:
        """
        Extract reconciliation decision from event state.

        Args:
            event_state: P03EventState with R3 reconciliation fields populated
            timestamp_ms: Optional explicit timestamp (for testing/replay)

        Returns:
            ReconciliationRecord with all decision fields
        """
        return ReconciliationRecord(
            event_id=event_state.event_id,
            reconciliation_action=event_state.reconciliation_action.value,
            best_match_id=event_state.best_match_id,
            best_match_layer=event_state.best_match_layer,
            similarity_score=event_state.similarity_score,
            confidence=event_state.confidence,
            reconciliation_reason=event_state.reconciliation_reason,
            decision_timestamp_ms=timestamp_ms or self._get_timestamp(),
        )

    def record_batch(
        self,
        event_states: List[P03EventState],
        timestamp_ms: Optional[int] = None,
    ) -> Dict[str, ReconciliationRecord]:
        """
        Record decisions for batch of events.

        All events in batch get the same timestamp for consistency.

        Args:
            event_states: List of P03EventState objects
            timestamp_ms: Optional explicit timestamp for all records

        Returns:
            Dict mapping event_id to ReconciliationRecord
        """
        ts = timestamp_ms or self._get_timestamp()
        return {event.event_id: self.record(event, timestamp_ms=ts) for event in event_states}

    def to_json(self, record: ReconciliationRecord) -> str:
        """
        Serialize record to JSON for st_hipp_events.reconciliation_json.

        Args:
            record: ReconciliationRecord to serialize

        Returns:
            Compact JSON string
        """
        return record.to_json()

    def batch_to_json(
        self,
        records: Dict[str, ReconciliationRecord],
    ) -> Dict[str, str]:
        """
        Serialize batch of records to JSON strings.

        Args:
            records: Dict mapping event_id to ReconciliationRecord

        Returns:
            Dict mapping event_id to JSON string
        """
        return {event_id: record.to_json() for event_id, record in records.items()}

    def validate_record(self, record: ReconciliationRecord) -> List[str]:
        """
        Validate record for completeness and consistency.

        Args:
            record: ReconciliationRecord to validate

        Returns:
            List of validation warnings (empty if valid)
        """
        warnings = []

        action = ReconciliationAction(record.reconciliation_action)

        # Check match presence for actions that require it
        if action in self.MATCH_REQUIRED_ACTIONS:
            if not record.best_match_id:
                warnings.append(f"Action {action.value} should have best_match_id")
            if not record.best_match_layer:
                warnings.append(f"Action {action.value} should have best_match_layer")
            if record.similarity_score == 0.0:
                warnings.append(f"Action {action.value} has zero similarity_score")

        # Check that no-match actions don't have spurious matches
        if action in self.NO_MATCH_ACTIONS and action != ReconciliationAction.CONTRADICT:
            if record.best_match_id and action == ReconciliationAction.CREATE:
                warnings.append("Action CREATE should not have best_match_id")

        # Check for empty reason
        if not record.reconciliation_reason:
            warnings.append("Missing reconciliation_reason")

        # Check confidence is reasonable for the action
        if action not in {ReconciliationAction.PENDING, ReconciliationAction.SKIP}:
            if record.confidence == 0.0:
                warnings.append("Zero confidence for non-trivial action")

        return warnings


# =============================================================================
# Utility Functions
# =============================================================================


def parse_reconciliation_json(json_str: str) -> ReconciliationRecord:
    """
    Parse reconciliation_json from st_hipp_events back to ReconciliationRecord.

    Args:
        json_str: JSON string from st_hipp_events.reconciliation_json

    Returns:
        ReconciliationRecord instance
    """
    data = json.loads(json_str)
    return ReconciliationRecord(
        event_id="",  # Not stored in JSON, must be set by caller
        reconciliation_action=data["action"],
        best_match_id=data.get("match_id"),
        best_match_layer=data.get("match_layer"),
        similarity_score=data.get("similarity", 0.0),
        confidence=data.get("confidence", 0.0),
        reconciliation_reason=data.get("reason", ""),
        decision_timestamp_ms=data.get("decided_at_ms", 0),
    )


def summarize_decisions(
    records: Dict[str, ReconciliationRecord],
) -> Dict[str, int]:
    """
    Count records by reconciliation action.

    Args:
        records: Dict mapping event_id to ReconciliationRecord

    Returns:
        Dict mapping action name to count
    """
    counts: Dict[str, int] = {}
    for record in records.values():
        action = record.reconciliation_action
        counts[action] = counts.get(action, 0) + 1
    return counts
