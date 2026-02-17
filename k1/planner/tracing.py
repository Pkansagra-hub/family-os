"""Tracing/context helpers for Planner pipeline orchestration.

This module provides reusable constructors for runtime tracing context
objects used by PipelineController and stage services.
"""

from __future__ import annotations

from typing import Any, Callable

from k1.planner.config import PlannerConfig
from k1.planner.types import StageContext


def create_stage_context(
    request: Any,
    config: PlannerConfig,
    elapsed_ms: int,
    tokens_used: int,
    cancel_check: Callable[[], bool],
) -> StageContext:
    """Create StageContext with shrinking timeout/token envelopes.

    Parameters
    ----------
    request : Any
        Plan-like request object exposing ``request_id`` and ``trace_id``.
    config : PlannerConfig
        Planner runtime configuration.
    elapsed_ms : int
        Elapsed milliseconds since plan start.
    tokens_used : int
        Total tokens already consumed in the current plan.
    cancel_check : Callable[[], bool]
        Cooperative cancellation closure for this request.

    Returns
    -------
    StageContext
        Base stage context populated with dynamic remaining budgets.
    """
    remaining_ms = max(1, config.pipeline_timeout_ms - max(0, elapsed_ms))
    remaining_tokens = max(0, config.total_token_budget - max(0, tokens_used))

    request_id = "unknown"
    trace_id = "unknown"
    if request is not None:
        request_id = getattr(request, "request_id", "") or "unknown"
        trace_id = getattr(request, "trace_id", "") or "unknown"

    return StageContext(
        request_id=request_id,
        trace_id=trace_id,
        timeout_remaining_ms=remaining_ms,
        token_budget_remaining=remaining_tokens,
        cancel_check=cancel_check,
    )


__all__ = ["create_stage_context"]
