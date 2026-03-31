"""
k1.concierge.obs.react_metrics -- ReAct loop telemetry instrumentation.

M11 E11.2.1

Captures structured metrics from ReAct loop execution results:
    - Exit path classification (degenerate, budget_exhausted, forced_text,
      cancelled, normal, suspended)
    - Iteration utilization (used vs budget)
    - Tool call counts (parallel vs sequential)
    - Per-loop duration
    - Degenerate fallback frequency

All functions accept a MetricsCollector and a ReactResult-like dict
or dataclass. They do NOT modify loop.py; they are called after the
loop returns. Designed for composability: front.py and back.py call
record_react_loop_metrics() to emit standardized metrics.

Metric naming convention:
    react_loop.{actor}.{metric_name}
    Labels: actor, mode (front only), tier (back only), exit_path
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from k1.concierge.obs.metrics import MetricsCollector

logger = logging.getLogger(__name__)


# =====================================================================
# ReactLoopOutcome -- structured extraction from ReactResult
# =====================================================================


@dataclass
class ReactLoopOutcome:
    """Structured extraction from a ReactResult for metrics emission.

    Callers build this from the actual ReactResult returned by react_loop.
    This decouples obs from the react module's internal types.
    """

    actor: str = ""  # "front" or "back"
    status: str = ""  # "complete", "suspended", "cancelled", "budget_exhausted"
    exit_path: str = ""  # classified exit path (see classify_exit_path)
    iterations_used: int = 0
    iterations_budget: int = 0
    tool_calls_total: int = 0
    parallel_tool_calls: int = 0
    sequential_tool_calls: int = 0
    degenerate_count: int = 0
    forced_text: bool = False
    duration_ms: float = 0.0
    mode: str = ""  # Front: PromptMode value
    tier: str = ""  # Back: ComplexityTier value
    dispatched_tasks: int = 0
    has_text: bool = False
    validator_rejections: int = 0


# =====================================================================
# Exit path classification
# =====================================================================

# Canonical exit paths (one per loop termination)
EXIT_NORMAL = "normal"
EXIT_DEGENERATE = "degenerate"
EXIT_BUDGET_EXHAUSTED = "budget_exhausted"
EXIT_FORCED_TEXT = "forced_text"
EXIT_CANCELLED = "cancelled"
EXIT_SUSPENDED = "suspended"

ALL_EXIT_PATHS = frozenset(
    {
        EXIT_NORMAL,
        EXIT_DEGENERATE,
        EXIT_BUDGET_EXHAUSTED,
        EXIT_FORCED_TEXT,
        EXIT_CANCELLED,
        EXIT_SUSPENDED,
    }
)


def classify_exit_path(
    status: str,
    degenerate_count: int = 0,
    forced_text: bool = False,
    iterations_used: int = 0,
    iterations_budget: int = 0,
) -> str:
    """Classify the ReAct loop exit path from result attributes.

    Priority (highest to lowest):
        1. cancelled -> EXIT_CANCELLED
        2. suspended -> EXIT_SUSPENDED
        3. budget_exhausted -> EXIT_BUDGET_EXHAUSTED
        4. forced_text flag -> EXIT_FORCED_TEXT
        5. degenerate_count > 0 -> EXIT_DEGENERATE
        6. else -> EXIT_NORMAL

    Returns one of the EXIT_* constants.
    """
    if status == "cancelled":
        return EXIT_CANCELLED
    if status == "suspended":
        return EXIT_SUSPENDED
    if status == "budget_exhausted":
        return EXIT_BUDGET_EXHAUSTED
    if forced_text:
        return EXIT_FORCED_TEXT
    if degenerate_count > 0:
        return EXIT_DEGENERATE
    return EXIT_NORMAL


# =====================================================================
# Core metrics emission
# =====================================================================


def record_react_loop_metrics(
    collector: MetricsCollector,
    outcome: ReactLoopOutcome,
) -> None:
    """Record all metrics for a completed ReAct loop execution.

    Emits:
        - react_loop.{actor}.completion_count (counter, by exit_path)
        - react_loop.{actor}.degenerate_count (counter)
        - react_loop.{actor}.budget_exhausted_count (counter)
        - react_loop.{actor}.forced_text_count (counter)
        - react_loop.{actor}.cancel_exit_count (counter)
        - react_loop.{actor}.normal_completion_count (counter)
        - react_loop.{actor}.suspended_count (counter, back only)
        - react_loop.{actor}.validator_rejection_count (counter)
        - react_loop.{actor}.iteration_count (histogram)
        - react_loop.{actor}.iteration_utilization (histogram, used/budget)
        - react_loop.{actor}.tool_call_count (histogram)
        - react_loop.{actor}.parallel_tool_calls (histogram)
        - react_loop.{actor}.sequential_tool_calls (histogram)
        - react_loop.{actor}.duration_ms (histogram)
        - react_loop.{actor}.dispatched_task_count (histogram, front only)

    Args:
        collector: MetricsCollector instance for this session.
        outcome: ReactLoopOutcome with loop execution data.
    """
    if not collector or not collector.enabled:
        return

    actor = outcome.actor
    base_labels: dict[str, str] = {"actor": actor}
    if outcome.mode:
        base_labels["mode"] = outcome.mode
    if outcome.tier:
        base_labels["tier"] = outcome.tier

    exit_path = outcome.exit_path or classify_exit_path(
        status=outcome.status,
        degenerate_count=outcome.degenerate_count,
        forced_text=outcome.forced_text,
        iterations_used=outcome.iterations_used,
        iterations_budget=outcome.iterations_budget,
    )

    # --- Exit path counter (unified) ---
    exit_labels = {**base_labels, "exit_path": exit_path}
    collector.increment(f"react_loop.{actor}.completion_count", exit_labels)

    # --- Per-exit-path counters ---
    if exit_path == EXIT_DEGENERATE:
        collector.increment(f"react_loop.{actor}.degenerate_count", base_labels)
    elif exit_path == EXIT_BUDGET_EXHAUSTED:
        collector.increment(f"react_loop.{actor}.budget_exhausted_count", base_labels)
    elif exit_path == EXIT_FORCED_TEXT:
        collector.increment(f"react_loop.{actor}.forced_text_count", base_labels)
    elif exit_path == EXIT_CANCELLED:
        collector.increment(f"react_loop.{actor}.cancel_exit_count", base_labels)
    elif exit_path == EXIT_SUSPENDED:
        collector.increment(f"react_loop.{actor}.suspended_count", base_labels)
    elif exit_path == EXIT_NORMAL:
        collector.increment(f"react_loop.{actor}.normal_completion_count", base_labels)

    # --- Degenerate count (cumulative per session) ---
    if outcome.degenerate_count > 0:
        collector.increment(
            f"react_loop.{actor}.degenerate_count",
            base_labels,
            value=float(outcome.degenerate_count),
        )

    # --- Validator rejections ---
    if outcome.validator_rejections > 0:
        collector.increment(
            f"react_loop.{actor}.validator_rejection_count",
            base_labels,
            value=float(outcome.validator_rejections),
        )

    # --- Iteration histograms ---
    collector.observe(
        f"react_loop.{actor}.iteration_count",
        base_labels,
        value=float(outcome.iterations_used),
    )
    if outcome.iterations_budget > 0:
        utilization = outcome.iterations_used / outcome.iterations_budget
        collector.observe(
            f"react_loop.{actor}.iteration_utilization",
            base_labels,
            value=round(utilization, 3),
        )

    # --- Tool call histograms ---
    collector.observe(
        f"react_loop.{actor}.tool_call_count",
        base_labels,
        value=float(outcome.tool_calls_total),
    )
    collector.observe(
        f"react_loop.{actor}.parallel_tool_calls",
        base_labels,
        value=float(outcome.parallel_tool_calls),
    )
    collector.observe(
        f"react_loop.{actor}.sequential_tool_calls",
        base_labels,
        value=float(outcome.sequential_tool_calls),
    )

    # --- Duration ---
    if outcome.duration_ms > 0:
        collector.observe(
            f"react_loop.{actor}.duration_ms",
            base_labels,
            value=outcome.duration_ms,
        )

    # --- Dispatched tasks (front only) ---
    if actor == "front" and outcome.dispatched_tasks > 0:
        collector.observe(
            f"react_loop.{actor}.dispatched_task_count",
            base_labels,
            value=float(outcome.dispatched_tasks),
        )

    logger.debug(
        "react_metrics: recorded actor=%s exit=%s iters=%d/%d tools=%d dur=%.1fms",
        actor,
        exit_path,
        outcome.iterations_used,
        outcome.iterations_budget,
        outcome.tool_calls_total,
        outcome.duration_ms,
    )


def build_react_loop_summary(outcome: ReactLoopOutcome) -> dict[str, Any]:
    """Build a structured summary dict for bus emission.

    Suitable as payload for build_metric_emitted().
    """
    return {
        "metric_name": "react_loop.summary",
        "actor": outcome.actor,
        "mode": outcome.mode,
        "tier": outcome.tier,
        "iterations_used": outcome.iterations_used,
        "iterations_budget": outcome.iterations_budget,
        "tool_calls": outcome.tool_calls_total,
        "parallel_tool_calls": outcome.parallel_tool_calls,
        "sequential_tool_calls": outcome.sequential_tool_calls,
        "exit_path": outcome.exit_path
        or classify_exit_path(
            outcome.status,
            outcome.degenerate_count,
            outcome.forced_text,
            outcome.iterations_used,
            outcome.iterations_budget,
        ),
        "degenerate_count": outcome.degenerate_count,
        "duration_ms": round(outcome.duration_ms, 1),
        "dispatched_tasks": outcome.dispatched_tasks,
        "validator_rejections": outcome.validator_rejections,
    }
