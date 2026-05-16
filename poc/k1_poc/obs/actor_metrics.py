"""
poc.k1_poc.obs.actor_metrics -- Front/Back actor telemetry instrumentation.

M11 E11.2.2 (Front per-mode) and E11.2.3 (Back per-tier)

Front metrics (per PromptMode):
    - Invocation count per mode
    - Iteration utilization per mode
    - Tool call count per mode
    - Degenerate rate per mode
    - HITL_RELAY tool call alert (should be 0)

Back metrics (per ComplexityTier):
    - Invocation count per tier
    - Budget utilization per tier (iterations_used / budget_limit)
    - Suspension count per tier
    - Cancel-to-exit latency per tier

All functions accept a MetricsCollector and structured outcome data.
They are decoupled from the actor modules and can be composed freely.

Metric naming convention:
    front.mode.{metric_name}  -- labels: mode
    back.tier.{metric_name}   -- labels: tier
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from poc.k1_poc.obs.metrics import MetricsCollector

logger = logging.getLogger(__name__)


# =====================================================================
# Front actor outcome (11.2.2)
# =====================================================================


@dataclass
class FrontOutcome:
    """Structured extraction from front_handler for metrics emission.

    Built by front_handler after react_loop returns.
    """

    mode: str = ""  # PromptMode value (STANDARD, PRESENT, WEAVE, etc.)
    status: str = ""  # ReactResult.status
    iterations_used: int = 0
    iterations_budget: int = 0
    tool_call_count: int = 0
    degenerate_count: int = 0
    dispatched_tasks: int = 0
    has_text: bool = False
    duration_ms: float = 0.0


# Mode-specific expected behavior (for alert evaluation)
# mode -> (expected_max_tool_calls, expected_max_iterations, alert_description)
MODE_EXPECTATIONS: dict[str, tuple[int, int, str]] = {
    "HITL_RELAY": (0, 1, "HITL_RELAY should have 0 tool calls"),
    "HITL_RESOLVE": (1, 3, "HITL_RESOLVE should use <= 3 iterations"),
    "WEAVE": (2, 3, "WEAVE should be quick, <= 3 iterations"),
    "PRESENT": (2, 3, "PRESENT should be quick, <= 3 iterations"),
    "STANDARD": (6, 6, "STANDARD normal range"),
    "INTERRUPT": (0, 1, "INTERRUPT should be immediate"),
    "ERROR": (0, 1, "ERROR should be immediate"),
    "CANCEL": (0, 1, "CANCEL should be immediate"),
}


def record_front_metrics(
    collector: MetricsCollector,
    outcome: FrontOutcome,
) -> list[dict[str, Any]]:
    """Record per-mode quality metrics for Front actor.

    Emits:
        - front.mode.invocation_count (counter, by mode)
        - front.mode.iterations_used (histogram, by mode)
        - front.mode.tool_calls (histogram, by mode)
        - front.mode.degenerate_count (counter, by mode)
        - front.mode.dispatched_tasks (histogram, by mode)
        - front.mode.duration_ms (histogram, by mode)
        - front.mode.iteration_utilization (histogram, by mode)

    Returns list of alert dicts for any mode-specific violations.
    """
    if not collector or not collector.enabled:
        return []

    mode_labels = {"mode": outcome.mode}
    alerts: list[dict[str, Any]] = []

    # --- Invocation count ---
    collector.increment("front.mode.invocation_count", mode_labels)

    # --- Iteration utilization ---
    collector.observe(
        "front.mode.iterations_used",
        mode_labels,
        value=float(outcome.iterations_used),
    )
    if outcome.iterations_budget > 0:
        utilization = outcome.iterations_used / outcome.iterations_budget
        collector.observe(
            "front.mode.iteration_utilization",
            mode_labels,
            value=round(utilization, 3),
        )

    # --- Tool calls ---
    collector.observe(
        "front.mode.tool_calls",
        mode_labels,
        value=float(outcome.tool_call_count),
    )

    # --- Degenerate count ---
    if outcome.degenerate_count > 0:
        collector.increment(
            "front.mode.degenerate_count",
            mode_labels,
            value=float(outcome.degenerate_count),
        )

    # --- Dispatched tasks ---
    if outcome.dispatched_tasks > 0:
        collector.observe(
            "front.mode.dispatched_tasks",
            mode_labels,
            value=float(outcome.dispatched_tasks),
        )

    # --- Duration ---
    if outcome.duration_ms > 0:
        collector.observe(
            "front.mode.duration_ms",
            mode_labels,
            value=outcome.duration_ms,
        )

    # --- Mode-specific alerts ---
    expectations = MODE_EXPECTATIONS.get(outcome.mode)
    if expectations:
        max_tools, max_iters, desc = expectations
        if outcome.tool_call_count > max_tools:
            alert = {
                "rule": f"front.mode.{outcome.mode.lower()}.excess_tool_calls",
                "mode": outcome.mode,
                "expected_max_tools": max_tools,
                "actual_tools": outcome.tool_call_count,
                "description": desc,
            }
            alerts.append(alert)
            collector.increment(
                "front.mode.alert_triggered",
                {**mode_labels, "alert": "excess_tool_calls"},
            )
        if outcome.iterations_used > max_iters:
            alert = {
                "rule": f"front.mode.{outcome.mode.lower()}.excess_iterations",
                "mode": outcome.mode,
                "expected_max_iters": max_iters,
                "actual_iters": outcome.iterations_used,
                "description": desc,
            }
            alerts.append(alert)
            collector.increment(
                "front.mode.alert_triggered",
                {**mode_labels, "alert": "excess_iterations"},
            )

    logger.debug(
        "actor_metrics: front mode=%s status=%s iters=%d tools=%d alerts=%d",
        outcome.mode,
        outcome.status,
        outcome.iterations_used,
        outcome.tool_call_count,
        len(alerts),
    )

    return alerts


# =====================================================================
# Back actor outcome (11.2.3)
# =====================================================================


@dataclass
class BackOutcome:
    """Structured extraction from back_handler for metrics emission.

    Built by back_handler after react_loop returns.
    """

    tier: str = ""  # ComplexityTier value (LOW, MEDIUM, HIGH)
    status: str = ""  # ReactResult.status
    iterations_used: int = 0
    budget_limit: int = 0  # max_iterations for this tier
    tool_call_count: int = 0
    degenerate_count: int = 0
    duration_ms: float = 0.0
    cancel_to_exit_ms: float = 0.0  # ms from cancel signal to loop exit
    task_id: str = ""


# Tier budget limits (P3.2: collapsed to simple/plan; legacy aliases kept)
TIER_BUDGET_LIMITS: dict[str, int] = {
    "simple": 400,
    "plan": 400,
    "crisis": 400,
    # Legacy aliases
    "LOW": 400,
    "MEDIUM": 400,
    "HIGH": 400,
}

# Budget utilization thresholds
UTILIZATION_UNDER = 0.3  # under-utilized
UTILIZATION_HEALTHY_LOW = 0.3
UTILIZATION_HEALTHY_HIGH = 0.8
UTILIZATION_NEAR_EXHAUSTION = 0.8
UTILIZATION_EXHAUSTED = 1.0


def record_back_metrics(
    collector: MetricsCollector,
    outcome: BackOutcome,
) -> list[dict[str, Any]]:
    """Record per-tier quality metrics for Back actor.

    Emits:
        - back.tier.invocation_count (counter, by tier)
        - back.tier.iterations_used (histogram, by tier)
        - back.tier.budget_utilization (histogram, by tier)
        - back.tier.tool_calls (histogram, by tier)
        - back.tier.suspension_count (counter, by tier, if suspended)
        - back.tier.cancel_to_exit_latency_ms (histogram, by tier, if cancelled)
        - back.tier.duration_ms (histogram, by tier)

    Returns list of alert dicts for tier-specific violations.
    """
    if not collector or not collector.enabled:
        return []

    tier_labels = {"tier": outcome.tier}
    alerts: list[dict[str, Any]] = []

    # --- Invocation count ---
    collector.increment("back.tier.invocation_count", tier_labels)

    # --- Iteration utilization ---
    collector.observe(
        "back.tier.iterations_used",
        tier_labels,
        value=float(outcome.iterations_used),
    )

    budget = outcome.budget_limit or TIER_BUDGET_LIMITS.get(outcome.tier, 4)
    if budget > 0:
        utilization = outcome.iterations_used / budget
        collector.observe(
            "back.tier.budget_utilization",
            tier_labels,
            value=round(utilization, 3),
        )

        # Budget exhaustion alert
        if utilization >= UTILIZATION_EXHAUSTED:
            alert = {
                "rule": "back.tier.budget_exhaustion",
                "tier": outcome.tier,
                "utilization": round(utilization, 3),
                "iterations_used": outcome.iterations_used,
                "budget_limit": budget,
                "description": "Task complexity exceeds tier budget",
            }
            alerts.append(alert)
            collector.increment(
                "back.tier.alert_triggered",
                {**tier_labels, "alert": "budget_exhaustion"},
            )

    # --- Tool calls ---
    collector.observe(
        "back.tier.tool_calls",
        tier_labels,
        value=float(outcome.tool_call_count),
    )

    # --- Suspension ---
    if outcome.status == "suspended":
        collector.increment("back.tier.suspension_count", tier_labels)

    # --- Cancel-to-exit latency ---
    if outcome.status == "cancelled" and outcome.cancel_to_exit_ms > 0:
        collector.observe(
            "back.tier.cancel_to_exit_latency_ms",
            tier_labels,
            value=outcome.cancel_to_exit_ms,
        )

    # --- Duration ---
    if outcome.duration_ms > 0:
        collector.observe(
            "back.tier.duration_ms",
            tier_labels,
            value=outcome.duration_ms,
        )

    logger.debug(
        "actor_metrics: back tier=%s status=%s iters=%d/%d util=%.2f alerts=%d",
        outcome.tier,
        outcome.status,
        outcome.iterations_used,
        budget,
        outcome.iterations_used / budget if budget > 0 else 0,
        len(alerts),
    )

    return alerts


def classify_budget_utilization(utilization: float) -> str:
    """Classify budget utilization into categories.

    Returns one of: "under", "healthy", "near_exhaustion", "exhausted".
    """
    if utilization >= UTILIZATION_EXHAUSTED:
        return "exhausted"
    if utilization >= UTILIZATION_NEAR_EXHAUSTION:
        return "near_exhaustion"
    if utilization >= UTILIZATION_HEALTHY_LOW:
        return "healthy"
    return "under"
