"""
SummaryGenerator — Issue 5.1.10

Generates ReconciliationSummary from event states.

Spec Reference:
    - Dossier §4.9.3 (Metrics Aggregation)
    - Dossier Appendix G R6 (R6Output.reconciliation_summary)
    - M5_EXECUTION.md Issue 5.1.10

Aggregation:
    - Count each ReconciliationAction type
    - Compute status breakdown (CONSOLIDATED, DUPLICATE, PRUNED, PENDING_REVIEW)
    - Aggregate layer write counts
    - Track KG entity/edge counts, gap counts

TIMESTAMP CONVENTION: All *_ms fields use MILLISECONDS since epoch.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from k0.modules.consolidation.staging.r6_output import ReconciliationSummary
from k0.pipelines.p03.event_state import P03EventState, ReconciliationAction
from k0.pipelines.p03.staged_writes import StagedWrite

# =============================================================================
# GENERATOR RESULT
# =============================================================================


@dataclass
class GeneratorResult:
    """
    Result from SummaryGenerator.compute().

    Attributes:
        summary: The generated ReconciliationSummary
        warnings: Any warnings encountered during generation
        pending_count: Count of events still in PENDING state
    """

    summary: ReconciliationSummary
    warnings: List[str] = field(default_factory=list)
    pending_count: int = 0


# =============================================================================
# SUMMARY GENERATOR
# =============================================================================


class SummaryGenerator:
    """
    Generates ReconciliationSummary from event states.

    Aggregates counts of all ReconciliationAction values and
    consolidation status breakdowns.

    Example:
        >>> generator = SummaryGenerator()
        >>> result = generator.compute(event_states)
        >>> print(result.summary.to_dict())
    """

    # Map ReconciliationAction to status
    ACTION_TO_STATUS = {
        ReconciliationAction.REINFORCE: "CONSOLIDATED",
        ReconciliationAction.EXTEND: "CONSOLIDATED",
        ReconciliationAction.CREATE: "CONSOLIDATED",
        ReconciliationAction.EVOLVE: "CONSOLIDATED",
        ReconciliationAction.CONTRADICT: "PENDING_REVIEW",
        ReconciliationAction.PRUNE: "PRUNED",
        ReconciliationAction.SKIP: "DUPLICATE",  # Usually skip is for duplicates
        ReconciliationAction.PENDING: "PENDING_REVIEW",
    }

    def compute(
        self,
        event_states: Dict[str, P03EventState],
        layer_write_counts: Optional[Dict[str, int]] = None,
        kg_entity_count: int = 0,
        kg_edge_count: int = 0,
        gap_count: int = 0,
        insight_count: int = 0,
        counterfactual_count: int = 0,
        routine_optimization_count: int = 0,
        total_writes: int = 0,
        cycle_duration_ms: int = 0,
    ) -> GeneratorResult:
        """
        Aggregate ReconciliationSummary from all event states.

        Issue 8.1.12: Added insight_count parameter for R5 outputs.
        Issue 8.1.17: Added counterfactual_count, routine_optimization_count.

        Args:
            event_states: Map of event_id → P03EventState
            layer_write_counts: Optional pre-computed write counts by layer
            kg_entity_count: Number of KG entities written
            kg_edge_count: Number of KG edges written
            gap_count: Number of gaps for P06
            insight_count: Number of R5 insights generated (Issue 8.1.12)
            counterfactual_count: Number of counterfactual scenarios (Issue 8.1.17)
            routine_optimization_count: Number of routine optimizations (Issue 8.1.17)
            total_writes: Total database writes staged
            cycle_duration_ms: R0-R6 processing time in MILLISECONDS

        Returns:
            GeneratorResult with summary and any warnings
        """
        warnings: List[str] = []

        # Count actions
        action_counter: Counter = Counter()
        status_counter: Counter = Counter()

        for event_id, state in event_states.items():
            action = state.reconciliation_action
            action_counter[action.value] += 1

            status = self.ACTION_TO_STATUS.get(action, "PENDING_REVIEW")
            status_counter[status] += 1

        # Check for pending events
        pending_count = action_counter.get(ReconciliationAction.PENDING.value, 0)
        if pending_count > 0:
            warnings.append(f"{pending_count} events still have PENDING reconciliation action")

        # Build action breakdown as tuple of tuples (frozen)
        action_breakdown = tuple(sorted(action_counter.items()))

        # Build layer write counts as tuple of tuples
        if layer_write_counts:
            layer_counts_tuple = tuple(sorted(layer_write_counts.items()))
        else:
            layer_counts_tuple = ()

        # Create summary
        summary = ReconciliationSummary(
            total_events=len(event_states),
            consolidated_count=status_counter.get("CONSOLIDATED", 0),
            duplicate_count=status_counter.get("DUPLICATE", 0),
            pruned_count=status_counter.get("PRUNED", 0),
            pending_review_count=status_counter.get("PENDING_REVIEW", 0),
            action_breakdown=action_breakdown,
            layer_write_counts=layer_counts_tuple,
            kg_entity_count=kg_entity_count,
            kg_edge_count=kg_edge_count,
            gap_count=gap_count,
            insight_count=insight_count,
            counterfactual_count=counterfactual_count,
            routine_optimization_count=routine_optimization_count,
            total_writes=total_writes,
            cycle_duration_ms=cycle_duration_ms,
        )

        return GeneratorResult(
            summary=summary,
            warnings=warnings,
            pending_count=pending_count,
        )

    def compute_from_actions(
        self,
        actions: List[ReconciliationAction],
    ) -> ReconciliationSummary:
        """
        Compute summary from list of actions (for testing).

        Args:
            actions: List of ReconciliationAction values

        Returns:
            ReconciliationSummary with counts
        """
        # Build minimal event states
        event_states: Dict[str, P03EventState] = {}
        for i, action in enumerate(actions):
            state = P03EventState(event_id=f"event_{i}")
            state.reconciliation_action = action
            event_states[f"event_{i}"] = state

        result = self.compute(event_states)
        return result.summary

    def merge(
        self,
        summaries: List[ReconciliationSummary],
    ) -> ReconciliationSummary:
        """
        Merge multiple summaries (for batch parallelism).

        Args:
            summaries: List of summaries to merge

        Returns:
            Combined ReconciliationSummary
        """
        if not summaries:
            return ReconciliationSummary()

        if len(summaries) == 1:
            return summaries[0]

        # Aggregate counts
        total_events = sum(s.total_events for s in summaries)
        consolidated_count = sum(s.consolidated_count for s in summaries)
        duplicate_count = sum(s.duplicate_count for s in summaries)
        pruned_count = sum(s.pruned_count for s in summaries)
        pending_review_count = sum(s.pending_review_count for s in summaries)
        kg_entity_count = sum(s.kg_entity_count for s in summaries)
        kg_edge_count = sum(s.kg_edge_count for s in summaries)
        gap_count = sum(s.gap_count for s in summaries)
        insight_count = sum(s.insight_count for s in summaries)
        counterfactual_count = sum(s.counterfactual_count for s in summaries)
        routine_optimization_count = sum(s.routine_optimization_count for s in summaries)
        total_writes = sum(s.total_writes for s in summaries)
        # For duration, take max (parallel execution)
        cycle_duration_ms = max(s.cycle_duration_ms for s in summaries)

        # Merge action breakdowns
        action_counter: Counter = Counter()
        for summary in summaries:
            for action, count in summary.action_breakdown:
                action_counter[action] += count
        action_breakdown = tuple(sorted(action_counter.items()))

        # Merge layer write counts
        layer_counter: Counter = Counter()
        for summary in summaries:
            for layer, count in summary.layer_write_counts:
                layer_counter[layer] += count
        layer_write_counts = tuple(sorted(layer_counter.items()))

        return ReconciliationSummary(
            total_events=total_events,
            consolidated_count=consolidated_count,
            duplicate_count=duplicate_count,
            pruned_count=pruned_count,
            pending_review_count=pending_review_count,
            action_breakdown=action_breakdown,
            layer_write_counts=layer_write_counts,
            kg_entity_count=kg_entity_count,
            kg_edge_count=kg_edge_count,
            gap_count=gap_count,
            insight_count=insight_count,
            counterfactual_count=counterfactual_count,
            routine_optimization_count=routine_optimization_count,
            total_writes=total_writes,
            cycle_duration_ms=cycle_duration_ms,
        )

    def compute_with_writes(
        self,
        event_states: Dict[str, P03EventState],
        truth_writes: List[StagedWrite],
        kg_writes: List[StagedWrite],
        gap_count: int = 0,
        insight_count: int = 0,
        counterfactual_count: int = 0,
        routine_optimization_count: int = 0,
        cycle_duration_ms: int = 0,
    ) -> GeneratorResult:
        """
        Compute summary with write counting.

        Convenience method that counts writes by layer automatically.

        Issue 8.1.12: Added insight_count parameter for R5 outputs.
        Issue 8.1.17: Added counterfactual_count, routine_optimization_count.

        Args:
            event_states: Map of event_id → P03EventState
            truth_writes: List of truth layer writes
            kg_writes: List of KG writes
            gap_count: Number of gaps
            insight_count: Number of R5 insights (Issue 8.1.12)
            counterfactual_count: Number of counterfactual scenarios (Issue 8.1.17)
            routine_optimization_count: Number of routine optimizations (Issue 8.1.17)
            cycle_duration_ms: Cycle duration

        Returns:
            GeneratorResult with computed summary
        """
        # Count writes by layer
        layer_counter: Counter = Counter()
        for write in truth_writes:
            layer_counter[write.layer] += 1
        for write in kg_writes:
            layer_counter[write.layer] += 1

        # Count KG entities and edges
        kg_entity_count = sum(1 for w in kg_writes if w.layer == "st_kg_dom")
        kg_edge_count = sum(1 for w in kg_writes if w.layer == "st_kg_edges")

        return self.compute(
            event_states=event_states,
            layer_write_counts=dict(layer_counter),
            kg_entity_count=kg_entity_count,
            kg_edge_count=kg_edge_count,
            gap_count=gap_count,
            insight_count=insight_count,
            counterfactual_count=counterfactual_count,
            routine_optimization_count=routine_optimization_count,
            total_writes=len(truth_writes) + len(kg_writes),
            cycle_duration_ms=cycle_duration_ms,
        )


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def generate_summary(
    event_states: Dict[str, P03EventState],
    **kwargs,
) -> ReconciliationSummary:
    """
    Convenience function to generate a summary.

    Args:
        event_states: Map of event_id → P03EventState
        **kwargs: Additional arguments for SummaryGenerator.compute()

    Returns:
        ReconciliationSummary
    """
    generator = SummaryGenerator()
    result = generator.compute(event_states, **kwargs)
    return result.summary


def count_actions(
    event_states: Dict[str, P03EventState],
) -> Dict[str, int]:
    """
    Count reconciliation actions in event states.

    Args:
        event_states: Map of event_id → P03EventState

    Returns:
        Dict mapping action name to count
    """
    counter: Counter = Counter()
    for state in event_states.values():
        counter[state.reconciliation_action.value] += 1
    return dict(counter)


def validate_total(
    summary: ReconciliationSummary,
) -> bool:
    """
    Validate that summary totals are consistent.

    Args:
        summary: Summary to validate

    Returns:
        True if totals are consistent
    """
    status_total = (
        summary.consolidated_count
        + summary.duplicate_count
        + summary.pruned_count
        + summary.pending_review_count
    )
    return status_total == summary.total_events
