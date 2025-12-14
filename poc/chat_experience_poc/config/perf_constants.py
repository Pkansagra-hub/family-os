"""
Performance Budget Constants

Importable constants derived from config/perf.yml for use throughout the codebase.
Provides type-safe access to performance budgets with fail-fast validation.

Usage:
    from config.perf_constants import WARMING_P95_MS, NEGOTIATION_DEADLINE_MS

    if latency_ms > WARMING_P95_MS:
        logger.error("budget_violation", budget="warming", latency=latency_ms)
        raise PerformanceBudgetViolation(f"WARMING exceeded: {latency_ms}ms > {WARMING_P95_MS}ms")

References:
- config/perf.yml - Performance budget definitions
- .github/copilot-instructions.md - Performance standards
"""

from pathlib import Path
from typing import Any, Dict

import yaml

# Load performance budgets from YAML
_PERF_CONFIG_PATH = Path(__file__).parent / "perf.yml"


def _load_perf_config() -> Dict[str, Any]:
    """Load performance configuration from YAML file."""
    if not _PERF_CONFIG_PATH.exists():
        raise FileNotFoundError(f"Performance config not found: {_PERF_CONFIG_PATH}")

    with open(_PERF_CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


# Load config once at module import
_PERF = _load_perf_config()

# ============================================================================
# ORCHESTRATOR BUDGETS (3-Phase Coordination)
# ============================================================================
NEGOTIATION_DEADLINE_MS: int = _PERF["orchestrator"]["negotiation_deadline_ms"]
SELECTION_DEADLINE_MS: int = _PERF["orchestrator"]["selection_deadline_ms"]
EXECUTION_DEADLINE_MS: int = _PERF["orchestrator"]["execution_deadline_ms"]

# ============================================================================
# AGENT LIFECYCLE BUDGETS
# ============================================================================
WARMING_P95_MS: int = _PERF["agent"]["warming_p95_ms"]
IDLE_TTL_MS: int = _PERF["agent"]["idle_ttl_ms"]
DRAINING_TIMEOUT_MS: int = _PERF["agent"]["draining_timeout_ms"]
SPAWN_LATENCY_P95_MS: int = _PERF["agent"]["spawn_latency_p95_ms"]
POOL_REUSE_LATENCY_MS: int = _PERF["agent"]["pool_reuse_latency_ms"]

# ============================================================================
# LLM BUDGETS
# ============================================================================
TTFT_MS: int = _PERF["llm"]["ttft_ms"]
TOKENS_PER_SECOND: int = _PERF["llm"]["tokens_per_second"]
MAX_COMPLETION_TIME_MS: int = _PERF["llm"]["max_completion_time_ms"]
RATE_LIMIT_BUDGET: int = _PERF["llm"]["rate_limit_budget"]

# ============================================================================
# RUNTIME COMPONENT BUDGETS
# ============================================================================
STATE_ACCESS_P95_MS: float = _PERF["runtime"]["state_access_p95_ms"]
STATE_WRITE_P95_MS: float = _PERF["runtime"]["state_write_p95_ms"]
MAILBOX_OP_P95_MS: float = _PERF["runtime"]["mailbox_op_p95_ms"]
DELTA_COMPUTATION_P95_MS: float = _PERF["runtime"]["delta_computation_p95_ms"]
DELTABUS_DELIVERY_P95_MS: float = _PERF["runtime"]["deltabus_delivery_p95_ms"]

# ============================================================================
# END-TO-END BUDGETS
# ============================================================================
E2E_LATENCY_P95_MS: int = _PERF["e2e"]["latency_p95_ms"]
E2E_LATENCY_PLANNING_P95_MS: int = _PERF["e2e"]["latency_planning_p95_ms"]
META_INTENT_LATENCY_MS: int = _PERF["e2e"]["meta_intent_latency_ms"]
PROACTIVE_TICK_LATENCY_MS: int = _PERF["e2e"]["proactive_tick_latency_ms"]

# ============================================================================
# K0 BRIDGE BUDGETS
# ============================================================================
K0_QUERY_P95_MS: int = _PERF["k0_bridge"]["query_p95_ms"]
K0_BATCH_SEND_P95_MS: int = _PERF["k0_bridge"]["batch_send_p95_ms"]
SSE_HEARTBEAT_INTERVAL_MS: int = _PERF["k0_bridge"]["sse_heartbeat_interval_ms"]
SSE_RECONNECT_JITTER_MS: int = _PERF["k0_bridge"]["sse_reconnect_jitter_ms"]

# ============================================================================
# MAILBOX CONFIGURATION
# ============================================================================
MAILBOX_CAPACITY: int = _PERF["mailbox"]["capacity"]
WFQ_WEIGHTS: list = _PERF["mailbox"]["wfq_weights"]
BACKPRESSURE_THRESHOLD: float = _PERF["mailbox"]["backpressure_threshold"]

# ============================================================================
# CIRCUIT BREAKER CONFIGURATION
# ============================================================================
CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = _PERF["circuit_breaker"]["failure_threshold"]
CIRCUIT_BREAKER_TIMEOUT_SECONDS: int = _PERF["circuit_breaker"]["timeout_seconds"]
CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS: int = _PERF["circuit_breaker"]["half_open_max_calls"]

# ============================================================================
# MONITORING CONFIGURATION
# ============================================================================
METRICS_EXPORT_INTERVAL_MS: int = _PERF["monitoring"]["metrics_export_interval_ms"]
LOG_SAMPLE_RATE: float = _PERF["monitoring"]["log_sample_rate"]
TRACE_SAMPLE_RATE: float = _PERF["monitoring"]["trace_sample_rate"]

# ============================================================================
# ENFORCEMENT CONFIGURATION
# ============================================================================
FAIL_FAST: bool = _PERF["enforcement"]["fail_fast"]
EMIT_METRIC: bool = _PERF["enforcement"]["emit_metric"]
LOG_VIOLATIONS: bool = _PERF["enforcement"]["log_violations"]


class PerformanceBudgetViolation(Exception):
    """Raised when a performance budget is exceeded."""

    def __init__(self, message: str, budget_name: str, actual_value: float, budget_value: float):
        super().__init__(message)
        self.budget_name = budget_name
        self.actual_value = actual_value
        self.budget_value = budget_value


def check_budget(
    actual_ms: float,
    budget_ms: float,
    budget_name: str,
    logger=None,
) -> bool:
    """
    Check if actual latency exceeds budget.

    Args:
        actual_ms: Actual latency in milliseconds
        budget_ms: Budget limit in milliseconds
        budget_name: Name of the budget (for logging/errors)
        logger: Optional structured logger

    Returns:
        True if within budget, False if exceeded

    Raises:
        PerformanceBudgetViolation: If fail_fast=True and budget exceeded
    """
    if actual_ms <= budget_ms:
        return True

    # Budget exceeded
    violation_msg = f"{budget_name} budget exceeded: {actual_ms}ms > {budget_ms}ms"

    if LOG_VIOLATIONS and logger:
        logger.warning(
            "performance_budget_violation",
            budget=budget_name,
            actual_ms=actual_ms,
            budget_ms=budget_ms,
            overage_ms=actual_ms - budget_ms,
        )

    if EMIT_METRIC and logger:
        # Emit metric for monitoring (would integrate with Prometheus)
        logger.info(
            "budget_violation_metric",
            metric_name=f"budget.{budget_name}.violations",
            value=1,
        )

    if FAIL_FAST:
        raise PerformanceBudgetViolation(
            violation_msg,
            budget_name=budget_name,
            actual_value=actual_ms,
            budget_value=budget_ms,
        )

    return False


# Export all constants for easy import
__all__ = [
    # Orchestrator
    "NEGOTIATION_DEADLINE_MS",
    "SELECTION_DEADLINE_MS",
    "EXECUTION_DEADLINE_MS",
    # Agent
    "WARMING_P95_MS",
    "IDLE_TTL_MS",
    "DRAINING_TIMEOUT_MS",
    "SPAWN_LATENCY_P95_MS",
    "POOL_REUSE_LATENCY_MS",
    # LLM
    "TTFT_MS",
    "TOKENS_PER_SECOND",
    "MAX_COMPLETION_TIME_MS",
    "RATE_LIMIT_BUDGET",
    # Runtime
    "STATE_ACCESS_P95_MS",
    "STATE_WRITE_P95_MS",
    "MAILBOX_OP_P95_MS",
    "DELTA_COMPUTATION_P95_MS",
    "DELTABUS_DELIVERY_P95_MS",
    # E2E
    "E2E_LATENCY_P95_MS",
    "E2E_LATENCY_PLANNING_P95_MS",
    "META_INTENT_LATENCY_MS",
    "PROACTIVE_TICK_LATENCY_MS",
    # K0 Bridge
    "K0_QUERY_P95_MS",
    "K0_BATCH_SEND_P95_MS",
    "SSE_HEARTBEAT_INTERVAL_MS",
    "SSE_RECONNECT_JITTER_MS",
    # Mailbox
    "MAILBOX_CAPACITY",
    "WFQ_WEIGHTS",
    "BACKPRESSURE_THRESHOLD",
    # Circuit Breaker
    "CIRCUIT_BREAKER_FAILURE_THRESHOLD",
    "CIRCUIT_BREAKER_TIMEOUT_SECONDS",
    "CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS",
    # Monitoring
    "METRICS_EXPORT_INTERVAL_MS",
    "LOG_SAMPLE_RATE",
    "TRACE_SAMPLE_RATE",
    # Enforcement
    "FAIL_FAST",
    "EMIT_METRIC",
    "LOG_VIOLATIONS",
    # Utilities
    "PerformanceBudgetViolation",
    "check_budget",
]
