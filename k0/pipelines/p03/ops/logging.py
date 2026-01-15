"""P03 Structured Logging — Issue 6.1.12.

This module implements P03-specific structured logging schema and context
management that integrates with K0's logging infrastructure.

Issue Reference: M6_EXECUTION.md Issue 6.1.12
Dossier Reference: docs/pipelines/P03_consolidation_dossier_v2.md Section 8.4.1

Key Features:
    - P03-specific log schema with required fields (cycle_id, phase, tenant_id, space_id)
    - Context managers for cycle and phase scopes
    - Integration with K0's bind_log_context/reset_log_context
    - PII redaction via K0's StructuredLogFormatter

Usage:
    from k0.pipelines.p03.ops.logging import P03LogContextManager

    log_mgr = P03LogContextManager()

    with log_mgr.cycle_context(cycle_id, tenant_id, space_id):
        logger.info("cycle_started", pending_events=1500)

        with log_mgr.phase_context("R1", batch_size=100):
            logger.debug("batch_selected", importance_range=[0.5, 0.9])
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Generator

from k0.obs.logging import bind_log_context, reset_log_context

__all__ = [
    "P03LogContextManager",
    "P03_REQUIRED_FIELDS",
    "P03_OPTIONAL_FIELDS",
    "P03_DECISION_TYPES",
    "P03_TARGET_LAYERS",
]

LOGGER = logging.getLogger(__name__)


# =============================================================================
# LOG SCHEMA CONSTANTS (from Dossier 8.4.1)
# =============================================================================

# Required fields - must be present in all P03 log messages
P03_REQUIRED_FIELDS = frozenset(
    {
        "cycle_id",
        "phase",
        "tenant_id",
        "space_id",
    }
)

# Optional fields - present based on context
P03_OPTIONAL_FIELDS = frozenset(
    {
        # Event context
        "event_id",
        "event_ids",
        "batch_size",
        # Decision context
        "decision_type",
        "target_layer",
        "similarity_score",
        "confidence_before",
        "confidence_after",
        # Timing
        "duration_ms",
        # Error context
        "error_code",
        "error_message",
        "affected_events",
        # Module context
        "module_id",
        "module_name",
        # Clustering (R2)
        "cluster_count",
        "avg_cluster_size",
        # Dedup (R3)
        "duplicates_found",
        "records_pruned",
        # KG (R4)
        "entities_created",
        "edges_created",
        # Gap (R8)
        "gaps_detected",
        "gap_type",
        "gap_importance",
    }
)

# Valid decision types for log validation
P03_DECISION_TYPES = frozenset(
    {
        "REINFORCE",
        "EXTEND",
        "CREATE",
        "EVOLVE",
        "PRUNE",
        "CONTRADICT",
        "SKIP",
    }
)

# Valid target layers for log validation
P03_TARGET_LAYERS = frozenset(
    {
        "st_epi",
        "st_sem",
        "st_procedural",
        "st_social",
        "st_prospective",
        "st_kg_dom",
        "st_kg_edges",
        "st_hipp_events",
    }
)


# =============================================================================
# P03 LOG CONTEXT MANAGER
# =============================================================================


class P03LogContextManager:
    """Manage P03 structured logging context.

    This class provides context managers for binding P03-specific fields
    to structured logs. It integrates with K0's logging infrastructure.

    Thread Safety:
        Context is managed via ContextVar, so thread-safe.

    Usage:
        log_mgr = P03LogContextManager()

        with log_mgr.cycle_context(cycle_id, tenant_id, space_id):
            # All logs in this scope have cycle_id, tenant_id, space_id
            logger.info("processing_started")

            with log_mgr.phase_context("R1"):
                # Phase context layered on top of cycle context
                logger.info("phase_started")
    """

    @contextmanager
    def cycle_context(
        self,
        cycle_id: str,
        tenant_id: str,
        space_id: str,
        **extra: Any,
    ) -> Generator[None, None, None]:
        """Bind P03 cycle context for all logs within scope.

        Args:
            cycle_id: P03 cycle identifier (ULID).
            tenant_id: Tenant isolation key.
            space_id: Space isolation key.
            **extra: Additional context fields.

        Yields:
            None. Context is bound for the duration of the with block.
        """
        token = bind_log_context(
            cycle_id=cycle_id,
            tenant_id=tenant_id,
            space_id=space_id,
            pipeline="P03",
            **extra,
        )
        try:
            yield
        finally:
            reset_log_context(token)

    @contextmanager
    def phase_context(
        self,
        phase: str,
        **extra: Any,
    ) -> Generator[None, None, None]:
        """Bind phase-specific context.

        Should be used within a cycle_context scope.

        Args:
            phase: Phase identifier (R0-R8).
            **extra: Additional phase-specific fields.

        Yields:
            None. Context is bound for the duration of the with block.
        """
        token = bind_log_context(phase=phase, **extra)
        try:
            yield
        finally:
            reset_log_context(token)

    @contextmanager
    def decision_context(
        self,
        decision_type: str,
        target_layer: str,
        **extra: Any,
    ) -> Generator[None, None, None]:
        """Bind decision-specific context.

        Should be used within a phase_context scope.

        Args:
            decision_type: Decision type (REINFORCE, EXTEND, etc.).
            target_layer: Target memory layer (st_epi, etc.).
            **extra: Additional decision-specific fields.

        Yields:
            None. Context is bound for the duration of the with block.
        """
        token = bind_log_context(
            decision_type=decision_type,
            target_layer=target_layer,
            **extra,
        )
        try:
            yield
        finally:
            reset_log_context(token)

    @contextmanager
    def module_context(
        self,
        module_id: str,
        module_name: str,
        **extra: Any,
    ) -> Generator[None, None, None]:
        """Bind module-specific context.

        Should be used within a phase_context scope.

        Args:
            module_id: Module identifier (M18-M25).
            module_name: Human-readable module name.
            **extra: Additional module-specific fields.

        Yields:
            None. Context is bound for the duration of the with block.
        """
        token = bind_log_context(
            module_id=module_id,
            module_name=module_name,
            **extra,
        )
        try:
            yield
        finally:
            reset_log_context(token)

    @contextmanager
    def error_context(
        self,
        error_code: str,
        error_message: str,
        **extra: Any,
    ) -> Generator[None, None, None]:
        """Bind error context for structured error logging.

        Args:
            error_code: Error code (e.g., CONSTRAINT_VIOLATION).
            error_message: Human-readable error message.
            **extra: Additional error context (affected_events, etc.).

        Yields:
            None. Context is bound for the duration of the with block.
        """
        token = bind_log_context(
            error_code=error_code,
            error_message=error_message,
            **extra,
        )
        try:
            yield
        finally:
            reset_log_context(token)


# Module-level singleton for convenience
_log_context_manager: P03LogContextManager | None = None


def get_log_context_manager() -> P03LogContextManager:
    """Get or create the module-level log context manager singleton."""
    global _log_context_manager
    if _log_context_manager is None:
        _log_context_manager = P03LogContextManager()
    return _log_context_manager
