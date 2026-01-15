"""
OutboxEventAssembler — Issue 5.1.8

Assembles outbox events for R8 emission based on reconciliation decisions.

Spec Reference:
    - Dossier §4.8 (R8 — Outbox Emission)
    - M5_EXECUTION.md Issue 5.1.8

Event Topics:
    - p03.consolidation.complete.v1: Cycle completion (priority 10)
    - p03.truth.created.v1: New truth record created
    - p03.truth.reinforced.v1: Existing truth reinforced
    - p03.truth.evolved.v1: Truth evolved/extended
    - p03.memory.pruned.v1: Memory archived/pruned
    - p03.pattern.detected.v1: New semantic pattern
    - p03.gap.detected.v1: Gap for P06 (priority 30)

Priority Levels:
    - 10: Completion (highest)
    - 30: Gaps (for P06)
    - 50: Decision events (normal)

TIMESTAMP CONVENTION: All *_ms fields use MILLISECONDS since epoch.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from k0.modules.consolidation.staging.r6_output import ReconciliationSummary
from k0.pipelines.p03.event_state import P03EventState, ReconciliationAction
from k0.pipelines.p03.phase_outputs import GapCandidate, Insight
from k0.pipelines.p03.staged_writes import StagedOutboxEvent

# =============================================================================
# CONSTANTS
# =============================================================================


# Event topics
TOPIC_CONSOLIDATION_COMPLETE = "p03.consolidation.complete.v1"
TOPIC_TRUTH_CREATED = "p03.truth.created.v1"
TOPIC_TRUTH_REINFORCED = "p03.truth.reinforced.v1"
TOPIC_TRUTH_EVOLVED = "p03.truth.evolved.v1"
TOPIC_MEMORY_PRUNED = "p03.memory.pruned.v1"
TOPIC_PATTERN_DETECTED = "p03.pattern.detected.v1"
TOPIC_GAP_DETECTED = "p03.gap.detected.v1"
# Issue 8.1.12: R5 insight events
TOPIC_INSIGHT_GENERATED = "p03.insight.generated.v1"

# Priority levels
PRIORITY_COMPLETION = 10
PRIORITY_GAP = 30
PRIORITY_INSIGHT = 40  # Issue 8.1.12: Insights between gaps and decisions
PRIORITY_DECISION = 50

# Source phase for all assembled outbox events
SOURCE_PHASE_R6 = "R6"


# =============================================================================
# HELPER
# =============================================================================


def _now_ms() -> int:
    """Return current time in milliseconds since epoch."""
    import time

    return int(time.time() * 1000)


# =============================================================================
# ASSEMBLED OUTBOX RESULT
# =============================================================================


@dataclass
class AssembledOutbox:
    """
    Result of outbox assembly.

    Issue 8.1.12: Added insight_events for R5 insight routing.

    Attributes:
        events: List of staged outbox events
        completion_event: The completion event (if assembled)
        decision_events: Events from reconciliation decisions
        gap_events: Events for P06 gaps
        insight_events: Events for R5 insights (Issue 8.1.12)
        event_count_by_topic: Count of events per topic
    """

    events: List[StagedOutboxEvent]
    completion_event: Optional[StagedOutboxEvent]
    decision_events: List[StagedOutboxEvent]
    gap_events: List[StagedOutboxEvent]
    insight_events: List[StagedOutboxEvent] = None  # Issue 8.1.12
    event_count_by_topic: Dict[str, int] = None

    def __post_init__(self) -> None:
        """Set defaults for optional fields."""
        if self.insight_events is None:
            self.insight_events = []
        if self.event_count_by_topic is None:
            self.event_count_by_topic = {}


# =============================================================================
# OUTBOX EVENT ASSEMBLER
# =============================================================================


class OutboxEventAssembler:
    """
    Assembles outbox events for R8 emission.

    Creates events based on reconciliation decisions and cycle completion.

    Example:
        >>> assembler = OutboxEventAssembler(
        ...     cycle_ulid="01ABC",
        ...     tenant_id="tenant1",
        ...     space_id="space1",
        ... )
        >>> events = assembler.assemble_all(summary, event_states, gaps, durations)
    """

    def __init__(
        self,
        cycle_ulid: str,
        tenant_id: str,
        space_id: str,
    ) -> None:
        """
        Initialize OutboxEventAssembler.

        Args:
            cycle_ulid: Cycle identifier for envelope
            tenant_id: Tenant identifier for envelope
            space_id: Space identifier for envelope
        """
        self.cycle_ulid = cycle_ulid
        self.tenant_id = tenant_id
        self.space_id = space_id

    def _build_envelope(self) -> Dict[str, Any]:
        """Build standard envelope fields for all events."""
        return {
            "cycle_id": self.cycle_ulid,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
            "timestamp_ms": _now_ms(),
        }

    def assemble_completion_event(
        self,
        summary: ReconciliationSummary,
        phase_durations: Dict[str, int],
    ) -> StagedOutboxEvent:
        """
        Build p03.consolidation.complete.v1 event.

        Args:
            summary: Cycle reconciliation summary
            phase_durations: Duration per phase in ms (e.g., {"R0": 100, "R1": 200})

        Returns:
            StagedOutboxEvent for completion
        """
        payload = {
            **self._build_envelope(),
            "summary": summary.to_dict(),
            "phase_durations": phase_durations,
            "total_events": summary.total_events,
            "total_writes": summary.total_writes,
            "consolidated_count": summary.consolidated_count,
            "duplicate_count": summary.duplicate_count,
            "pruned_count": summary.pruned_count,
            "gap_count": summary.gap_count,
        }

        # Issue 8.1.13: Deterministic idempotency key
        idempotency_key = f"{self.cycle_ulid}:complete"

        return StagedOutboxEvent.create(
            topic=TOPIC_CONSOLIDATION_COMPLETE,
            payload=payload,
            phase=SOURCE_PHASE_R6,
            priority=PRIORITY_COMPLETION,
            idempotency_key=idempotency_key,
        )

    def assemble_decision_events(
        self,
        event_states: Dict[str, P03EventState],
    ) -> List[StagedOutboxEvent]:
        """
        Build per-decision events based on reconciliation_action.

        Mappings:
            - REINFORCE → p03.truth.reinforced.v1
            - CREATE → p03.truth.created.v1, p03.pattern.detected.v1
            - EVOLVE/EXTEND → p03.truth.evolved.v1
            - PRUNE → p03.memory.pruned.v1

        Args:
            event_states: Map of event_id to P03EventState

        Returns:
            List of decision events
        """
        events: List[StagedOutboxEvent] = []

        for event_id, state in event_states.items():
            action = state.reconciliation_action

            if action == ReconciliationAction.REINFORCE:
                events.append(self._create_reinforced_event(event_id, state))

            elif action == ReconciliationAction.CREATE:
                # CREATE produces two events: truth.created and pattern.detected
                events.append(self._create_created_event(event_id, state))
                events.append(self._create_pattern_event(event_id, state))

            elif action in (ReconciliationAction.EVOLVE, ReconciliationAction.EXTEND):
                events.append(self._create_evolved_event(event_id, state))

            elif action == ReconciliationAction.PRUNE:
                events.append(self._create_pruned_event(event_id, state))

            # PENDING, SKIP, CONTRADICT do not emit decision events

        return events

    def _create_reinforced_event(
        self,
        event_id: str,
        state: P03EventState,
    ) -> StagedOutboxEvent:
        """Create p03.truth.reinforced.v1 event."""
        payload = {
            **self._build_envelope(),
            "event_id": event_id,
            "matched_record_id": state.best_match_id,
            "matched_layer": state.best_match_layer,
            "similarity_score": state.similarity_score,
            "confidence": state.confidence,
            "reason": state.reconciliation_reason,
        }

        # Issue 8.1.13: Deterministic idempotency key
        idempotency_key = f"{self.cycle_ulid}:reinforce:{event_id}"

        return StagedOutboxEvent.create(
            topic=TOPIC_TRUTH_REINFORCED,
            payload=payload,
            phase=SOURCE_PHASE_R6,
            priority=PRIORITY_DECISION,
            idempotency_key=idempotency_key,
        )

    def _create_created_event(
        self,
        event_id: str,
        state: P03EventState,
    ) -> StagedOutboxEvent:
        """Create p03.truth.created.v1 event."""
        payload = {
            **self._build_envelope(),
            "event_id": event_id,
            "content_type": getattr(state, "content_type", ""),
            "importance_score": state.importance_score,
            "cluster_id": state.cluster_id,
            "reason": state.reconciliation_reason,
        }

        # Issue 8.1.13: Deterministic idempotency key
        idempotency_key = f"{self.cycle_ulid}:create:{event_id}"

        return StagedOutboxEvent.create(
            topic=TOPIC_TRUTH_CREATED,
            payload=payload,
            phase=SOURCE_PHASE_R6,
            priority=PRIORITY_DECISION,
            idempotency_key=idempotency_key,
        )

    def _create_pattern_event(
        self,
        event_id: str,
        state: P03EventState,
    ) -> StagedOutboxEvent:
        """Create p03.pattern.detected.v1 event for CREATE action."""
        payload = {
            **self._build_envelope(),
            "event_id": event_id,
            "pattern_id": f"sem_{event_id}",
            "content_type": getattr(state, "content_type", ""),
            "confidence": state.confidence,
        }

        # Issue 8.1.13: Deterministic idempotency key
        idempotency_key = f"{self.cycle_ulid}:pattern:{event_id}"

        return StagedOutboxEvent.create(
            topic=TOPIC_PATTERN_DETECTED,
            payload=payload,
            phase=SOURCE_PHASE_R6,
            priority=PRIORITY_DECISION,
            idempotency_key=idempotency_key,
        )

    def _create_evolved_event(
        self,
        event_id: str,
        state: P03EventState,
    ) -> StagedOutboxEvent:
        """Create p03.truth.evolved.v1 event for EVOLVE/EXTEND actions."""
        payload = {
            **self._build_envelope(),
            "event_id": event_id,
            "action": state.reconciliation_action.value,
            "matched_record_id": state.best_match_id,
            "matched_layer": state.best_match_layer,
            "similarity_score": state.similarity_score,
            "reason": state.reconciliation_reason,
        }

        # Issue 8.1.13: Deterministic idempotency key
        idempotency_key = f"{self.cycle_ulid}:evolve:{event_id}"

        return StagedOutboxEvent.create(
            topic=TOPIC_TRUTH_EVOLVED,
            payload=payload,
            phase=SOURCE_PHASE_R6,
            priority=PRIORITY_DECISION,
            idempotency_key=idempotency_key,
        )

    def _create_pruned_event(
        self,
        event_id: str,
        state: P03EventState,
    ) -> StagedOutboxEvent:
        """Create p03.memory.pruned.v1 event for PRUNE action."""
        payload = {
            **self._build_envelope(),
            "event_id": event_id,
            "prune_decision": state.prune_decision.value,
            "decay_score": state.decay_score,
            "days_since_access": state.days_since_access,
            "reason": state.reconciliation_reason,
        }

        # Issue 8.1.13: Deterministic idempotency key
        idempotency_key = f"{self.cycle_ulid}:prune:{event_id}"

        return StagedOutboxEvent.create(
            topic=TOPIC_MEMORY_PRUNED,
            payload=payload,
            phase=SOURCE_PHASE_R6,
            priority=PRIORITY_DECISION,
            idempotency_key=idempotency_key,
        )

    def assemble_gap_events(
        self,
        gaps: List[GapCandidate],
    ) -> List[StagedOutboxEvent]:
        """
        Build p03.gap.detected.v1 events for P06.

        Deduplicates by gap_id to avoid redundant events.

        Args:
            gaps: List of gap candidates from R5

        Returns:
            List of gap events (deduplicated by gap_id)
        """
        events: List[StagedOutboxEvent] = []
        seen_gap_ids: Set[str] = set()

        for gap in gaps:
            if gap.gap_id in seen_gap_ids:
                continue
            seen_gap_ids.add(gap.gap_id)

            payload = {
                **self._build_envelope(),
                "gap_id": gap.gap_id,
                "gap_type": gap.gap_type,
                "related_entity_id": gap.related_entity_id,
                "entropy_score": gap.entropy_score,
                "priority": gap.priority,
                "context_json": gap.context_json,
                "candidate_values": gap.candidate_values,
            }

            # Issue 8.1.13: Deterministic idempotency key for gaps
            idempotency_key = f"{self.cycle_ulid}:gap:{gap.gap_id}"

            events.append(
                StagedOutboxEvent.create(
                    topic=TOPIC_GAP_DETECTED,
                    payload=payload,
                    phase=SOURCE_PHASE_R6,
                    priority=PRIORITY_GAP,
                    idempotency_key=idempotency_key,
                )
            )

        return events

    def assemble_insight_events(
        self,
        insights: List[Insight],
    ) -> List[StagedOutboxEvent]:
        """
        Build p03.insight.generated.v1 events for R5 insights.

        Issue 8.1.12: Routes R5 insight outputs through staged writes.
        Issue 8.1.13: Added deterministic idempotency_key per A.0.5 invariant.

        Deduplicates by insight_id to avoid redundant events.

        Args:
            insights: List of insights from R5 DreamExplorer

        Returns:
            List of insight events (deduplicated by insight_id)
        """
        events: List[StagedOutboxEvent] = []
        seen_insight_ids: Set[str] = set()

        for insight in insights:
            if insight.insight_id in seen_insight_ids:
                continue
            seen_insight_ids.add(insight.insight_id)

            payload = {
                **self._build_envelope(),
                "insight_id": insight.insight_id,
                "insight_type": insight.insight_type,
                "concept_a_id": insight.concept_a_id,
                "concept_b_id": insight.concept_b_id,
                "pmi_score": insight.pmi_score,
                "novelty_score": insight.novelty_score,
                "relevance_score": insight.relevance_score,
                "confidence": insight.relevance_score,  # Issue 8.1.13: schema field
                "description": insight.natural_language,
                "evidence_ids": insight.evidence_ids,
                "supporting_evidence": insight.evidence_ids,  # Issue 8.1.13: schema alias
                "generated_at": _now_ms(),  # Issue 8.1.13: required schema field
            }

            # Issue 8.1.13: Deterministic idempotency key per A.0.5 invariant
            # Pattern: {cycle_id}:insight:{insight_id}
            idempotency_key = f"{self.cycle_ulid}:insight:{insight.insight_id}"

            events.append(
                StagedOutboxEvent.create(
                    topic=TOPIC_INSIGHT_GENERATED,
                    payload=payload,
                    phase=SOURCE_PHASE_R6,
                    priority=PRIORITY_INSIGHT,
                    idempotency_key=idempotency_key,
                )
            )

        return events

    def assemble_all(
        self,
        summary: ReconciliationSummary,
        event_states: Dict[str, P03EventState],
        gaps: List[GapCandidate],
        phase_durations: Dict[str, int],
        insights: Optional[List[Insight]] = None,
    ) -> AssembledOutbox:
        """
        Assemble all outbox events for the cycle.

        Issue 8.1.12: Added insights parameter for R5 routing.

        Args:
            summary: Reconciliation summary for completion event
            event_states: Map of event_id to P03EventState
            gaps: List of gap candidates for P06
            phase_durations: Duration per phase in ms
            insights: List of R5 insights (Issue 8.1.12)

        Returns:
            AssembledOutbox containing all events and breakdown
        """
        # Assemble each category
        completion = self.assemble_completion_event(summary, phase_durations)
        decision_events = self.assemble_decision_events(event_states)
        gap_events = self.assemble_gap_events(gaps)
        insight_events = self.assemble_insight_events(insights or [])

        # Combine all events
        all_events = [completion] + decision_events + gap_events + insight_events

        # Count by topic
        count_by_topic: Dict[str, int] = {}
        for event in all_events:
            count_by_topic[event.topic] = count_by_topic.get(event.topic, 0) + 1

        return AssembledOutbox(
            events=all_events,
            completion_event=completion,
            decision_events=decision_events,
            gap_events=gap_events,
            insight_events=insight_events,
            event_count_by_topic=count_by_topic,
        )

    def count_events(self, result: AssembledOutbox) -> int:
        """Return total event count from assembled result."""
        return len(result.events)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def count_outbox_events(result: AssembledOutbox) -> int:
    """Return total event count from assembled result."""
    return len(result.events)


def summarize_outbox(result: AssembledOutbox) -> Dict[str, Any]:
    """
    Create summary of assembled outbox events.

    Args:
        result: AssembledOutbox from assembly

    Returns:
        Summary dict with counts and breakdown
    """
    return {
        "total_events": len(result.events),
        "completion_event": result.completion_event is not None,
        "decision_event_count": len(result.decision_events),
        "gap_event_count": len(result.gap_events),
        "events_by_topic": result.event_count_by_topic,
    }


def get_events_by_priority(
    result: AssembledOutbox,
) -> Dict[int, List[StagedOutboxEvent]]:
    """
    Group events by priority level.

    Args:
        result: AssembledOutbox from assembly

    Returns:
        Dict mapping priority -> list of events
    """
    by_priority: Dict[int, List[StagedOutboxEvent]] = {}
    for event in result.events:
        if event.priority not in by_priority:
            by_priority[event.priority] = []
        by_priority[event.priority].append(event)
    return by_priority
