"""
ConsolidationStatusMarker — Status assignment logic for R6.

Determines and assigns consolidation_status to each processed event
based on R1-R5 outcomes (ReconciliationAction, is_duplicate, PruneDecision).

Issue: 5.1.2
Spec Reference:
    - Dossier §4.7.1 (Consolidation Status Marking)
    - M5_EXECUTION.md Issue 5.1.2

Status Values:
    - CONSOLIDATED: Event successfully reconciled (REINFORCE, EXTEND, CREATE, EVOLVE)
    - DUPLICATE: Event is exact/near duplicate (is_duplicate=True or SKIP with dup reason)
    - PRUNED: Event decayed below threshold (PRUNE action or ARCHIVE/TOMBSTONE decision)
    - PENDING_REVIEW: Event flagged for P06 (CONTRADICT action or gap emitted)

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from k0.pipelines.p03.event_state import (
    P03EventState,
    PruneDecision,
    ReconciliationAction,
)

# Status constants (matching r6_output.py)
STATUS_CONSOLIDATED = "CONSOLIDATED"
STATUS_DUPLICATE = "DUPLICATE"
STATUS_PRUNED = "PRUNED"
STATUS_PENDING_REVIEW = "PENDING_REVIEW"


# =============================================================================
# Status Result Dataclass
# =============================================================================


@dataclass
class StatusResult:
    """
    Result of status determination for an event.

    Includes the status value and a reasoning trace for debugging/audit.

    Attributes:
        event_id: The event ID
        status: One of CONSOLIDATED, DUPLICATE, PRUNED, PENDING_REVIEW
        reason: Human-readable explanation of why this status was assigned
        source_decision: The primary decision that drove this status
        contributing_factors: Additional factors that influenced the decision
    """

    event_id: str
    status: str
    reason: str
    source_decision: str
    contributing_factors: Dict[str, str]

    def __post_init__(self) -> None:
        """Validate status value."""
        valid = {STATUS_CONSOLIDATED, STATUS_DUPLICATE, STATUS_PRUNED, STATUS_PENDING_REVIEW}
        if self.status not in valid:
            raise ValueError(f"Invalid status: {self.status}. Must be one of: {valid}")


# =============================================================================
# Reason Templates
# =============================================================================

# Templates for generating human-readable reasons
_REASON_TEMPLATES = {
    # Duplicate reasons
    "duplicate_explicit": "Event marked as duplicate of {canonical_id} (hamming={hamming})",
    "duplicate_skip": "Event skipped as duplicate via ReconciliationAction.SKIP",
    # Pruned reasons
    "pruned_action": "Event pruned via ReconciliationAction.PRUNE",
    "pruned_archive": "Event marked for archival due to decay (PruneDecision.ARCHIVE)",
    "pruned_tombstone": "Event marked for deletion due to decay (PruneDecision.TOMBSTONE)",
    "pruned_skip_decay": "Event skipped due to decay below threshold",
    # Pending review reasons
    "pending_contradict": "Event contradicts existing truth; flagged for P06 review",
    "pending_gap": "Event triggered gap emission; pending P06 resolution",
    "pending_low_confidence": "Low confidence decision ({confidence:.2f}); flagged for review",
    # Consolidated reasons
    "consolidated_reinforce": "Event reinforces existing record {match_id} in {layer} (sim={similarity:.2f})",
    "consolidated_extend": "Event extends existing record {match_id} in {layer} (sim={similarity:.2f})",
    "consolidated_create": "Event creates new truth record (novelty={novelty:.2f})",
    "consolidated_evolve": "Event evolves existing record {match_id} with new schema/semantics",
    "consolidated_default": "Event successfully consolidated via {action}",
}


# =============================================================================
# ConsolidationStatusMarker Class
# =============================================================================


class ConsolidationStatusMarker:
    """
    Determines consolidation_status from P03EventState.

    Implements the status marking rules from Dossier §4.7.1:
    1. Check is_duplicate first → DUPLICATE
    2. Check reconciliation_action == CONTRADICT → PENDING_REVIEW
    3. Check reconciliation_action == PRUNE or PruneDecision != KEEP → PRUNED
    4. Check reconciliation_action == SKIP → determine DUPLICATE or PRUNED based on reason
    5. Otherwise → CONSOLIDATED

    Usage:
        marker = ConsolidationStatusMarker()
        result = marker.mark_status(event_state)
        print(result.status, result.reason)

        # Batch processing
        results = marker.mark_batch(event_states)
        for event_id, result in results.items():
            print(f"{event_id}: {result.status}")
    """

    # Confidence threshold below which events are flagged for review
    LOW_CONFIDENCE_THRESHOLD = 0.5

    # ReconciliationActions that result in CONSOLIDATED status
    CONSOLIDATED_ACTIONS = frozenset(
        {
            ReconciliationAction.REINFORCE,
            ReconciliationAction.EXTEND,
            ReconciliationAction.CREATE,
            ReconciliationAction.EVOLVE,
        }
    )

    def __init__(
        self,
        low_confidence_threshold: float = 0.5,
        flag_low_confidence: bool = False,
    ) -> None:
        """
        Initialize the status marker.

        Args:
            low_confidence_threshold: Confidence below which to flag for review
            flag_low_confidence: If True, low confidence decisions → PENDING_REVIEW
        """
        self.low_confidence_threshold = low_confidence_threshold
        self.flag_low_confidence = flag_low_confidence

    def mark_status(self, event_state: P03EventState) -> StatusResult:
        """
        Determine consolidation_status from event state.

        Implements the decision tree from Dossier §4.7.1.

        Args:
            event_state: P03EventState with R1-R5 enrichment

        Returns:
            StatusResult with status and reasoning trace
        """
        event_id = event_state.event_id
        action = event_state.reconciliation_action
        prune_decision = event_state.prune_decision

        # Build contributing factors
        factors: Dict[str, str] = {
            "reconciliation_action": action.value,
            "is_duplicate": str(event_state.is_duplicate),
            "prune_decision": prune_decision.value,
        }

        # Rule 1: Check is_duplicate first → DUPLICATE
        if event_state.is_duplicate:
            return StatusResult(
                event_id=event_id,
                status=STATUS_DUPLICATE,
                reason=_REASON_TEMPLATES["duplicate_explicit"].format(
                    canonical_id=event_state.duplicate_of_id or "unknown",
                    hamming=event_state.hamming_distance,
                ),
                source_decision="is_duplicate=True",
                contributing_factors=factors,
            )

        # Rule 2: Check CONTRADICT → PENDING_REVIEW
        if action == ReconciliationAction.CONTRADICT:
            return StatusResult(
                event_id=event_id,
                status=STATUS_PENDING_REVIEW,
                reason=_REASON_TEMPLATES["pending_contradict"],
                source_decision="ReconciliationAction.CONTRADICT",
                contributing_factors=factors,
            )

        # Rule 3: Check PRUNE action → PRUNED
        if action == ReconciliationAction.PRUNE:
            return StatusResult(
                event_id=event_id,
                status=STATUS_PRUNED,
                reason=_REASON_TEMPLATES["pruned_action"],
                source_decision="ReconciliationAction.PRUNE",
                contributing_factors=factors,
            )

        # Rule 3b: Check PruneDecision is ARCHIVE or TOMBSTONE → PRUNED
        if prune_decision in (PruneDecision.ARCHIVE, PruneDecision.TOMBSTONE):
            template_key = (
                "pruned_archive" if prune_decision == PruneDecision.ARCHIVE else "pruned_tombstone"
            )
            return StatusResult(
                event_id=event_id,
                status=STATUS_PRUNED,
                reason=_REASON_TEMPLATES[template_key],
                source_decision=f"PruneDecision.{prune_decision.value}",
                contributing_factors=factors,
            )

        # Rule 4: Check SKIP → determine if DUPLICATE or PRUNED based on reason
        if action == ReconciliationAction.SKIP:
            return self._handle_skip_action(event_state, factors)

        # Rule 5: Check PENDING → could be incomplete processing
        if action == ReconciliationAction.PENDING:
            # PENDING means no decision was made - treat as error/incomplete
            # but we still need to assign a status for safety
            return StatusResult(
                event_id=event_id,
                status=STATUS_PENDING_REVIEW,
                reason="Event still in PENDING state; incomplete processing",
                source_decision="ReconciliationAction.PENDING",
                contributing_factors=factors,
            )

        # Rule 6: Optional low confidence check → PENDING_REVIEW
        if self.flag_low_confidence and event_state.confidence < self.low_confidence_threshold:
            return StatusResult(
                event_id=event_id,
                status=STATUS_PENDING_REVIEW,
                reason=_REASON_TEMPLATES["pending_low_confidence"].format(
                    confidence=event_state.confidence,
                ),
                source_decision=f"low_confidence ({event_state.confidence:.2f})",
                contributing_factors=factors,
            )

        # Rule 7: Consolidated actions → CONSOLIDATED
        if action in self.CONSOLIDATED_ACTIONS:
            return self._handle_consolidated_action(event_state, action, factors)

        # Fallback: Unknown action - treat as consolidated with warning
        return StatusResult(
            event_id=event_id,
            status=STATUS_CONSOLIDATED,
            reason=_REASON_TEMPLATES["consolidated_default"].format(action=action.value),
            source_decision=f"ReconciliationAction.{action.value} (fallback)",
            contributing_factors=factors,
        )

    def _handle_skip_action(
        self,
        event_state: P03EventState,
        factors: Dict[str, str],
    ) -> StatusResult:
        """
        Handle SKIP action - determine if DUPLICATE or PRUNED.

        SKIP is used for multiple scenarios:
        - Duplicate detected (most common)
        - Already processed in previous cycle
        - Filtered by pre-condition

        We check the reconciliation_reason to determine the correct status.
        """
        event_id = event_state.event_id
        reason_lower = event_state.reconciliation_reason.lower()

        # Check if reason indicates duplicate
        if any(kw in reason_lower for kw in ["duplicate", "dup ", "hamming", "merged"]):
            return StatusResult(
                event_id=event_id,
                status=STATUS_DUPLICATE,
                reason=_REASON_TEMPLATES["duplicate_skip"],
                source_decision="ReconciliationAction.SKIP (duplicate)",
                contributing_factors=factors,
            )

        # Check if reason indicates decay/pruning
        if any(kw in reason_lower for kw in ["decay", "prune", "expired", "stale"]):
            return StatusResult(
                event_id=event_id,
                status=STATUS_PRUNED,
                reason=_REASON_TEMPLATES["pruned_skip_decay"],
                source_decision="ReconciliationAction.SKIP (decay)",
                contributing_factors=factors,
            )

        # Default SKIP → DUPLICATE (most common case)
        return StatusResult(
            event_id=event_id,
            status=STATUS_DUPLICATE,
            reason=f"Event skipped: {event_state.reconciliation_reason or 'no reason provided'}",
            source_decision="ReconciliationAction.SKIP (default→duplicate)",
            contributing_factors=factors,
        )

    def _handle_consolidated_action(
        self,
        event_state: P03EventState,
        action: ReconciliationAction,
        factors: Dict[str, str],
    ) -> StatusResult:
        """
        Handle consolidation actions (REINFORCE, EXTEND, CREATE, EVOLVE).

        Generates a descriptive reason based on the specific action.
        """
        event_id = event_state.event_id

        if action == ReconciliationAction.REINFORCE:
            reason = _REASON_TEMPLATES["consolidated_reinforce"].format(
                match_id=event_state.best_match_id or "unknown",
                layer=event_state.best_match_layer or "unknown",
                similarity=event_state.similarity_score,
            )
        elif action == ReconciliationAction.EXTEND:
            reason = _REASON_TEMPLATES["consolidated_extend"].format(
                match_id=event_state.best_match_id or "unknown",
                layer=event_state.best_match_layer or "unknown",
                similarity=event_state.similarity_score,
            )
        elif action == ReconciliationAction.CREATE:
            reason = _REASON_TEMPLATES["consolidated_create"].format(
                novelty=event_state.novelty_factor,
            )
        elif action == ReconciliationAction.EVOLVE:
            reason = _REASON_TEMPLATES["consolidated_evolve"].format(
                match_id=event_state.best_match_id or "unknown",
            )
        else:
            reason = _REASON_TEMPLATES["consolidated_default"].format(action=action.value)

        return StatusResult(
            event_id=event_id,
            status=STATUS_CONSOLIDATED,
            reason=reason,
            source_decision=f"ReconciliationAction.{action.value}",
            contributing_factors=factors,
        )

    def mark_batch(
        self,
        event_states: List[P03EventState],
    ) -> Dict[str, StatusResult]:
        """
        Mark status for a batch of events.

        Args:
            event_states: List of P03EventState objects

        Returns:
            Dict mapping event_id to StatusResult
        """
        return {event.event_id: self.mark_status(event) for event in event_states}

    def get_status_counts(
        self,
        results: Dict[str, StatusResult],
    ) -> Dict[str, int]:
        """
        Count events by status.

        Args:
            results: Dict of event_id to StatusResult

        Returns:
            Dict mapping status to count
        """
        counts = {
            STATUS_CONSOLIDATED: 0,
            STATUS_DUPLICATE: 0,
            STATUS_PRUNED: 0,
            STATUS_PENDING_REVIEW: 0,
        }
        for result in results.values():
            if result.status in counts:
                counts[result.status] += 1
        return counts
