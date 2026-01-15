"""P03 Phase Logger — Issue 6.1.13.

This module implements phase-appropriate logging levels based on the
dossier specification. Each phase has specific events that should be
logged at INFO vs DEBUG level.

Issue Reference: M6_EXECUTION.md Issue 6.1.13
Dossier Reference: docs/pipelines/P03_consolidation_dossier_v2.md Section 8.4.2

Key Features:
    - Phase-specific log level matrix (INFO vs DEBUG events)
    - PhaseLogger wrapper enforcing correct levels
    - Structured event types per phase
    - Integration with P03LogContextManager

Usage:
    from k0.pipelines.p03.ops.phase_logger import PhaseLogger

    phase_logger = PhaseLogger("R1", logger)

    # These are logged at INFO (defined in PHASE_INFO_EVENTS)
    phase_logger.log_event("batch_size", "Selected batch", batch_size=100)

    # These are logged at DEBUG (defined in PHASE_DEBUG_EVENTS)
    phase_logger.log_event("event_importance_score", "Scored event", score=0.75)
"""

from __future__ import annotations

import logging
from typing import Any

__all__ = [
    "PhaseLogger",
    "PHASE_INFO_EVENTS",
    "PHASE_DEBUG_EVENTS",
    "PHASE_WARN_EVENTS",
    "PHASE_ERROR_EVENTS",
]

LOGGER = logging.getLogger(__name__)


# =============================================================================
# PHASE LOG LEVEL MATRIX (from Dossier 8.4.2)
# =============================================================================

# Events that should be logged at INFO level per phase
PHASE_INFO_EVENTS: dict[str, frozenset[str]] = {
    "R0": frozenset(
        {
            "cycle_start",
            "trigger_type",
            "lock_acquired",
            "cycle_context_initialized",
        }
    ),
    "R1": frozenset(
        {
            "batch_size",
            "importance_range",
            "batch_selected",
            "scoring_complete",
        }
    ),
    "R2": frozenset(
        {
            "cluster_count",
            "avg_cluster_size",
            "clustering_complete",
            "episode_groups_formed",
        }
    ),
    "R3": frozenset(
        {
            "duplicates_found",
            "records_pruned",
            "dedup_complete",
            "novelty_assessment_complete",
        }
    ),
    "R4": frozenset(
        {
            "entities_created",
            "edges_created",
            "kg_update_complete",
            "entity_resolutions",
        }
    ),
    "R5": frozenset(
        {
            "insights_generated",
            "exploration_complete",
            "counterfactuals_evaluated",
        }
    ),
    "R6": frozenset(
        {
            "events_updated",
            "staging_complete",
            "status_transitions",
        }
    ),
    "R7": frozenset(
        {
            "records_written",
            "layer_counts",
            "truth_write_complete",
            "uow_committed",
        }
    ),
    "R8": frozenset(
        {
            "events_emitted",
            "gaps_detected",
            "emission_complete",
            "cycle_complete",
        }
    ),
}

# Events that should be logged at DEBUG level per phase
PHASE_DEBUG_EVENTS: dict[str, frozenset[str]] = {
    "R0": frozenset(
        {
            "lock_acquisition_attempt",
            "lock_wait_ms",
            "context_field_set",
        }
    ),
    "R1": frozenset(
        {
            "event_importance_score",
            "scoring_formula_used",
            "feature_extraction",
            "weight_applied",
        }
    ),
    "R2": frozenset(
        {
            "cluster_membership",
            "dbscan_params",
            "embedding_fetch",
            "similarity_calculated",
        }
    ),
    "R3": frozenset(
        {
            "dedup_decision",
            "novelty_score",
            "hamming_distance",
            "fingerprint_match",
        }
    ),
    "R4": frozenset(
        {
            "entity_resolution",
            "edge_discovery",
            "confidence_update",
            "alias_mapping",
        }
    ),
    "R5": frozenset(
        {
            "counterfactual_detail",
            "simulation_step",
            "exploration_path",
        }
    ),
    "R6": frozenset(
        {
            "event_status_update",
            "staging_row",
            "transition_reason",
        }
    ),
    "R7": frozenset(
        {
            "layer_write_detail",
            "uow_transaction",
            "row_modified",
            "constraint_check",
        }
    ),
    "R8": frozenset(
        {
            "event_emission_detail",
            "gap_emission",
            "bus_publish",
            "outbox_insert",
        }
    ),
}

# Events that should be logged at WARNING level per phase
PHASE_WARN_EVENTS: dict[str, frozenset[str]] = {
    "R0": frozenset(
        {
            "lock_contention",
            "lock_retry",
        }
    ),
    "R1": frozenset(
        {
            "low_importance_batch",
            "sparse_features",
        }
    ),
    "R2": frozenset(
        {
            "oversized_clusters",
            "clustering_timeout",
        }
    ),
    "R3": frozenset(
        {
            "high_novelty_conflicts",
            "dedup_ambiguity",
        }
    ),
    "R4": frozenset(
        {
            "ambiguous_entities",
            "edge_conflict",
        }
    ),
    "R5": frozenset(
        {
            "no_insights_found",
            "exploration_limited",
        }
    ),
    "R6": frozenset(
        {
            "update_conflicts",
            "stale_event",
        }
    ),
    "R7": frozenset(
        {
            "retry_scenarios",
            "constraint_warning",
        }
    ),
    "R8": frozenset(
        {
            "bus_unavailable",
            "emission_retry",
        }
    ),
}

# Events that should be logged at ERROR level per phase
PHASE_ERROR_EVENTS: dict[str, frozenset[str]] = {
    "R0": frozenset(
        {
            "lock_timeout",
            "initialization_failed",
        }
    ),
    "R1": frozenset(
        {
            "batch_selection_failed",
            "scoring_error",
        }
    ),
    "R2": frozenset(
        {
            "clustering_failed",
            "embedding_error",
        }
    ),
    "R3": frozenset(
        {
            "dedup_index_error",
            "novelty_calculation_failed",
        }
    ),
    "R4": frozenset(
        {
            "kg_update_failed",
            "entity_resolution_error",
        }
    ),
    "R5": frozenset(
        {
            "exploration_error",
            "simulation_failed",
        }
    ),
    "R6": frozenset(
        {
            "staging_update_failed",
            "status_transition_error",
        }
    ),
    "R7": frozenset(
        {
            "write_transaction_failed",
            "constraint_violation",
            "uow_rollback",
        }
    ),
    "R8": frozenset(
        {
            "emission_failed",
            "gap_emission_error",
            "outbox_error",
        }
    ),
}


# =============================================================================
# PHASE LOGGER
# =============================================================================


class PhaseLogger:
    """Phase-aware logger that enforces log level matrix.

    This logger automatically routes events to the appropriate log level
    based on the phase and event type. Unknown events default to DEBUG.

    Thread Safety:
        Thread-safe (wraps standard logging.Logger).

    Usage:
        phase_logger = PhaseLogger("R1", logging.getLogger(__name__))
        phase_logger.log_event("batch_size", "Selected batch", batch_size=100)
    """

    def __init__(self, phase: str, logger: logging.Logger) -> None:
        """Initialize phase logger.

        Args:
            phase: Phase identifier (R0-R8).
            logger: Underlying Python logger.
        """
        self._phase = phase
        self._logger = logger
        self._info_events = PHASE_INFO_EVENTS.get(phase, frozenset())
        self._debug_events = PHASE_DEBUG_EVENTS.get(phase, frozenset())
        self._warn_events = PHASE_WARN_EVENTS.get(phase, frozenset())
        self._error_events = PHASE_ERROR_EVENTS.get(phase, frozenset())

    @property
    def phase(self) -> str:
        """Return current phase."""
        return self._phase

    def log_event(
        self,
        event_type: str,
        message: str,
        **kwargs: Any,
    ) -> None:
        """Log event at appropriate level based on matrix.

        Args:
            event_type: Event type identifier (e.g., "batch_size").
            message: Log message.
            **kwargs: Additional structured context fields.
        """
        extra = {"event_type": event_type, "phase": self._phase, **kwargs}

        if event_type in self._error_events:
            self._logger.error(message, extra=extra)
        elif event_type in self._warn_events:
            self._logger.warning(message, extra=extra)
        elif event_type in self._info_events:
            self._logger.info(message, extra=extra)
        elif event_type in self._debug_events:
            self._logger.debug(message, extra=extra)
        else:
            # Default to DEBUG for unlisted events
            self._logger.debug(message, extra=extra)

    def info(self, event_type: str, message: str, **kwargs: Any) -> None:
        """Log at INFO level with event type."""
        self._logger.info(
            message,
            extra={"event_type": event_type, "phase": self._phase, **kwargs},
        )

    def debug(self, event_type: str, message: str, **kwargs: Any) -> None:
        """Log at DEBUG level with event type."""
        self._logger.debug(
            message,
            extra={"event_type": event_type, "phase": self._phase, **kwargs},
        )

    def warning(self, event_type: str, message: str, **kwargs: Any) -> None:
        """Log at WARNING level with event type."""
        self._logger.warning(
            message,
            extra={"event_type": event_type, "phase": self._phase, **kwargs},
        )

    def error(self, event_type: str, message: str, **kwargs: Any) -> None:
        """Log at ERROR level with event type."""
        self._logger.error(
            message,
            extra={"event_type": event_type, "phase": self._phase, **kwargs},
        )

    def get_expected_level(self, event_type: str) -> str:
        """Get expected log level for an event type.

        Useful for testing and validation.

        Args:
            event_type: Event type to check.

        Returns:
            Expected log level: "ERROR", "WARNING", "INFO", or "DEBUG".
        """
        if event_type in self._error_events:
            return "ERROR"
        if event_type in self._warn_events:
            return "WARNING"
        if event_type in self._info_events:
            return "INFO"
        return "DEBUG"


def create_phase_logger(phase: str, name: str | None = None) -> PhaseLogger:
    """Create a PhaseLogger for the specified phase.

    Args:
        phase: Phase identifier (R0-R8).
        name: Logger name (defaults to "k0.pipelines.p03.phases.{phase}").

    Returns:
        Configured PhaseLogger instance.
    """
    logger_name = name or f"k0.pipelines.p03.phases.{phase.lower()}"
    return PhaseLogger(phase, logging.getLogger(logger_name))
