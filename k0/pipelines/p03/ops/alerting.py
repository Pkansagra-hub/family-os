"""Prometheus alert rules for P03 Consolidation Cycle observability.

Issue 6.1.18 - Alerting Rules
Provides alert rule definitions organized by category:
- Cycle alerts (failure rate, duration)
- Queue alerts (pending queue depth, staleness)
- Learning alerts (divergence, regret rate)
- Security alerts (cross-space leakage)
- Performance alerts (latency, budget)
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

__all__ = [
    "build_p03_alert_rules",
    "P03_ALERT_THRESHOLDS",
    "P03_SLO_TARGETS",
]

# -----------------------------------------------------------------------------
# P03-Specific SLO Targets
# -----------------------------------------------------------------------------

P03_SLO_TARGETS: dict[str, float] = {
    # Cycle SLOs
    "cycle_success_rate_percent": 99.5,
    "cycle_duration_seconds_p95": 30.0,
    "cycle_duration_seconds_p99": 60.0,
    # Queue SLOs
    "pending_queue_max_size": 50,
    "pending_queue_age_hours": 24,
    # Learning SLOs
    "divergence_rate_percent": 5.0,
    "regret_rate_percent": 2.0,
    "gap_resolution_rate_percent": 95.0,
    # Security SLOs
    "cross_space_leakage_rate": 0.0,
    # Performance SLOs
    "phase_latency_p95_ms": 100.0,
    "budget_utilization_max_percent": 95.0,
}

# -----------------------------------------------------------------------------
# P03-Specific Alert Thresholds
# -----------------------------------------------------------------------------

P03_ALERT_THRESHOLDS: dict[str, dict[str, float]] = {
    # Cycle thresholds
    "cycle_failure_rate_percent": {
        "warning": 1.0,  # >1% failure rate
        "critical": 5.0,  # >5% failure rate
    },
    "cycle_duration_seconds": {
        "warning": 45.0,  # P95 > 45s
        "critical": 90.0,  # P95 > 90s
    },
    # Queue thresholds
    "pending_queue_size": {
        "warning": 25,
        "critical": 50,
    },
    "pending_queue_age_hours": {
        "warning": 12,
        "critical": 24,
    },
    # Learning thresholds
    "divergence_rate_percent": {
        "warning": 10.0,
        "critical": 25.0,
    },
    "regret_rate_percent": {
        "warning": 3.0,
        "critical": 5.0,
    },
    "gap_resolution_rate_percent": {
        "warning": 90.0,  # <90% resolution
        "critical": 80.0,  # <80% resolution
    },
    # Security thresholds
    "cross_space_leakage": {
        "warning": 1,  # Any leakage is warning
        "critical": 5,  # 5+ is critical
    },
    # Performance thresholds
    "phase_latency_ms_p95": {
        "warning": 150.0,
        "critical": 300.0,
    },
    "budget_utilization_percent": {
        "warning": 85.0,
        "critical": 95.0,
    },
    # Learning budget thresholds (Issue 6.4.13)
    "learning_time_pct": {
        "warning": 4.0,  # >4% of cycle time
        "critical": 5.0,  # >5% of cycle time
    },
    "learning_queue_depth": {
        "warning": 500,
        "critical": 1000,
    },
    "learning_skip_rate_per_hour": {
        "warning": 1,
        "critical": 10,
    },
    "learning_queue_overflow_per_min": {
        "warning": 10,
        "critical": 50,
    },
    "audit_drops_per_min": {
        "warning": 1,
        "critical": 10,
    },
}

# Runbook base URL for P03 alerts
P03_RUNBOOK_URL_BASE = "https://docs.familyos.io/runbooks/p03/{path}"


# -----------------------------------------------------------------------------
# Type Definitions
# -----------------------------------------------------------------------------


class RuleLabels(TypedDict, total=False):
    severity: Literal["info", "warning", "critical"]
    component: str
    subsystem: str
    slo: str
    pipeline: str
    contact: str
    runbook: str


class RuleAnnotations(TypedDict):
    summary: str
    description: str
    runbook_url: str


RuleDefinition = TypedDict(
    "RuleDefinition",
    {
        "alert": str,
        "expr": str,
        "for": str,
        "labels": RuleLabels,
        "annotations": RuleAnnotations,
    },
    total=False,
)


# -----------------------------------------------------------------------------
# Rule Builder Helper
# -----------------------------------------------------------------------------


def _rule(
    *,
    alert: str,
    expr: str,
    duration: str,
    severity: Literal["info", "warning", "critical"],
    subsystem: str,
    slo: str,
    runbook_slug: str,
    summary: str,
    description: str,
    contact: str = "p03-oncall",
) -> RuleDefinition:
    """Build a single alert rule definition.

    Args:
        alert: Alert name (e.g., P03CycleFailureRateWarning)
        expr: PromQL expression that triggers alert
        duration: Duration before firing (e.g., "5m")
        severity: Alert severity level
        subsystem: P03 subsystem (cycle, queue, learning, security, performance)
        slo: SLO category this alert monitors
        runbook_slug: Runbook filename without extension
        summary: Short alert summary
        description: Detailed alert description with template variables
        contact: Alert contact override

    Returns:
        RuleDefinition dict for Prometheus alert rules
    """
    runbook_path = f"{runbook_slug}.md"

    labels: RuleLabels = {
        "severity": severity,
        "component": "consolidation",
        "subsystem": subsystem,
        "slo": slo,
        "pipeline": "p03",
        "contact": contact,
        "runbook": runbook_path,
    }

    annotations: RuleAnnotations = {
        "summary": summary,
        "description": description,
        "runbook_url": P03_RUNBOOK_URL_BASE.format(path=runbook_path),
    }

    return {
        "alert": alert,
        "expr": expr,
        "for": duration,
        "labels": labels,
        "annotations": annotations,
    }


# -----------------------------------------------------------------------------
# Alert Rule Groups
# -----------------------------------------------------------------------------


def _build_cycle_alerts() -> dict[str, Any]:
    """Build P03 cycle-related alert rules."""
    return {
        "name": "p03-cycle",
        "interval": "30s",
        "rules": [
            # Cycle failure rate
            _rule(
                alert="P03CycleFailureRateWarning",
                expr=(
                    '100 * (sum(rate(p03_cycle_total{status="failure"}[15m])) '
                    "/ sum(rate(p03_cycle_total[15m]))) > "
                    f"{P03_ALERT_THRESHOLDS['cycle_failure_rate_percent']['warning']}"
                ),
                duration="10m",
                severity="warning",
                subsystem="cycle",
                slo="reliability",
                runbook_slug="p03-cycle-failures",
                summary="P03 consolidation cycle failure rate elevated",
                description=(
                    "Consolidation cycle failure rate is {{ $value | humanizePercentage }} "
                    f"(> {P03_ALERT_THRESHOLDS['cycle_failure_rate_percent']['warning']}%), "
                    f"target is < {100 - P03_SLO_TARGETS['cycle_success_rate_percent']}%"
                ),
            ),
            _rule(
                alert="P03CycleFailureRateCritical",
                expr=(
                    '100 * (sum(rate(p03_cycle_total{status="failure"}[15m])) '
                    "/ sum(rate(p03_cycle_total[15m]))) > "
                    f"{P03_ALERT_THRESHOLDS['cycle_failure_rate_percent']['critical']}"
                ),
                duration="5m",
                severity="critical",
                subsystem="cycle",
                slo="reliability",
                runbook_slug="p03-cycle-failures",
                summary="P03 consolidation cycle failure rate CRITICAL",
                description=(
                    "Consolidation cycle failure rate is {{ $value | humanizePercentage }} "
                    f"(> {P03_ALERT_THRESHOLDS['cycle_failure_rate_percent']['critical']}%), "
                    "immediate investigation required"
                ),
            ),
            # Cycle duration
            _rule(
                alert="P03CycleDurationWarning",
                expr=(
                    "histogram_quantile(0.95, sum(rate(p03_cycle_duration_seconds_bucket[15m])) by (le)) > "
                    f"{P03_ALERT_THRESHOLDS['cycle_duration_seconds']['warning']}"
                ),
                duration="15m",
                severity="warning",
                subsystem="cycle",
                slo="latency",
                runbook_slug="p03-cycle-duration",
                summary="P03 consolidation cycle P95 duration elevated",
                description=(
                    "Consolidation cycle P95 duration is {{ $value | humanizeDuration }} "
                    f"(> {P03_ALERT_THRESHOLDS['cycle_duration_seconds']['warning']}s), "
                    f"target is < {P03_SLO_TARGETS['cycle_duration_seconds_p95']}s"
                ),
            ),
            _rule(
                alert="P03CycleDurationCritical",
                expr=(
                    "histogram_quantile(0.95, sum(rate(p03_cycle_duration_seconds_bucket[15m])) by (le)) > "
                    f"{P03_ALERT_THRESHOLDS['cycle_duration_seconds']['critical']}"
                ),
                duration="5m",
                severity="critical",
                subsystem="cycle",
                slo="latency",
                runbook_slug="p03-cycle-duration",
                summary="P03 consolidation cycle P95 duration CRITICAL",
                description=(
                    "Consolidation cycle P95 duration is {{ $value | humanizeDuration }} "
                    f"(> {P03_ALERT_THRESHOLDS['cycle_duration_seconds']['critical']}s), "
                    "cycles are severely delayed"
                ),
            ),
            # No cycles running
            _rule(
                alert="P03NoCyclesRunning",
                expr="sum(increase(p03_cycle_total[1h])) == 0",
                duration="1h",
                severity="warning",
                subsystem="cycle",
                slo="liveness",
                runbook_slug="p03-no-cycles",
                summary="No P03 consolidation cycles running",
                description=(
                    "No consolidation cycles have completed in the last hour. "
                    "Check if the consolidation scheduler is running."
                ),
            ),
        ],
    }


def _build_queue_alerts() -> dict[str, Any]:
    """Build P03 queue-related alert rules."""
    return {
        "name": "p03-queue",
        "interval": "30s",
        "rules": [
            # Pending queue size
            _rule(
                alert="P03PendingQueueHighWarning",
                expr=(
                    f"sum(p03_pending_queue_size) > "
                    f"{P03_ALERT_THRESHOLDS['pending_queue_size']['warning']}"
                ),
                duration="15m",
                severity="warning",
                subsystem="queue",
                slo="throughput",
                runbook_slug="p03-pending-queue",
                summary="P03 pending queue size elevated",
                description=(
                    "Pending queue has {{ $value }} items "
                    f"(> {P03_ALERT_THRESHOLDS['pending_queue_size']['warning']}), "
                    "consolidation may be falling behind"
                ),
            ),
            _rule(
                alert="P03PendingQueueHighCritical",
                expr=(
                    f"sum(p03_pending_queue_size) > "
                    f"{P03_ALERT_THRESHOLDS['pending_queue_size']['critical']}"
                ),
                duration="10m",
                severity="critical",
                subsystem="queue",
                slo="throughput",
                runbook_slug="p03-pending-queue",
                summary="P03 pending queue size CRITICAL",
                description=(
                    "Pending queue has {{ $value }} items "
                    f"(> {P03_ALERT_THRESHOLDS['pending_queue_size']['critical']}), "
                    "consolidation is severely backlogged"
                ),
            ),
            # Stale pending items
            _rule(
                alert="P03PendingQueueStaleWarning",
                expr=(
                    "max(p03_pending_oldest_age_hours) > "
                    f"{P03_ALERT_THRESHOLDS['pending_queue_age_hours']['warning']}"
                ),
                duration="30m",
                severity="warning",
                subsystem="queue",
                slo="freshness",
                runbook_slug="p03-stale-pending",
                summary="P03 pending items are stale",
                description=(
                    "Oldest pending item is {{ $value | humanize }} hours old "
                    f"(> {P03_ALERT_THRESHOLDS['pending_queue_age_hours']['warning']}h), "
                    "items may be stuck"
                ),
            ),
            _rule(
                alert="P03PendingQueueStaleCritical",
                expr=(
                    "max(p03_pending_oldest_age_hours) > "
                    f"{P03_ALERT_THRESHOLDS['pending_queue_age_hours']['critical']}"
                ),
                duration="15m",
                severity="critical",
                subsystem="queue",
                slo="freshness",
                runbook_slug="p03-stale-pending",
                summary="P03 pending items are very stale",
                description=(
                    "Oldest pending item is {{ $value | humanize }} hours old "
                    f"(> {P03_ALERT_THRESHOLDS['pending_queue_age_hours']['critical']}h), "
                    "check for processing failures"
                ),
            ),
        ],
    }


def _build_learning_alerts() -> dict[str, Any]:
    """Build P03 learning/formula comparison alert rules."""
    return {
        "name": "p03-learning",
        "interval": "1m",
        "rules": [
            # Formula divergence rate
            _rule(
                alert="P03FormulaDivergenceWarning",
                expr=(
                    "100 * (sum(rate(p03_formula_comparison_divergence[1h])) "
                    "/ sum(rate(p03_formula_decisions_total[1h]))) > "
                    f"{P03_ALERT_THRESHOLDS['divergence_rate_percent']['warning']}"
                ),
                duration="30m",
                severity="warning",
                subsystem="learning",
                slo="consistency",
                runbook_slug="p03-formula-divergence",
                summary="P03 formula divergence rate elevated",
                description=(
                    "Formula divergence rate is {{ $value | humanizePercentage }} "
                    f"(> {P03_ALERT_THRESHOLDS['divergence_rate_percent']['warning']}%), "
                    "candidate formula may have different behavior"
                ),
            ),
            _rule(
                alert="P03FormulaDivergenceCritical",
                expr=(
                    "100 * (sum(rate(p03_formula_comparison_divergence[1h])) "
                    "/ sum(rate(p03_formula_decisions_total[1h]))) > "
                    f"{P03_ALERT_THRESHOLDS['divergence_rate_percent']['critical']}"
                ),
                duration="15m",
                severity="critical",
                subsystem="learning",
                slo="consistency",
                runbook_slug="p03-formula-divergence",
                summary="P03 formula divergence rate CRITICAL",
                description=(
                    "Formula divergence rate is {{ $value | humanizePercentage }} "
                    f"(> {P03_ALERT_THRESHOLDS['divergence_rate_percent']['critical']}%), "
                    "candidate formula significantly differs - do not promote"
                ),
            ),
            # Prune regret rate
            _rule(
                alert="P03PruneRegretRateWarning",
                expr=(
                    "100 * (sum(rate(p03_prune_regrets_total[6h])) "
                    '/ sum(rate(p03_decisions_total{decision="prune"}[6h]))) > '
                    f"{P03_ALERT_THRESHOLDS['regret_rate_percent']['warning']}"
                ),
                duration="1h",
                severity="warning",
                subsystem="learning",
                slo="quality",
                runbook_slug="p03-prune-regrets",
                summary="P03 prune regret rate elevated",
                description=(
                    "Prune regret rate is {{ $value | humanizePercentage }} "
                    f"(> {P03_ALERT_THRESHOLDS['regret_rate_percent']['warning']}%), "
                    "pruning decisions may need review"
                ),
            ),
            _rule(
                alert="P03PruneRegretRateCritical",
                expr=(
                    "100 * (sum(rate(p03_prune_regrets_total[6h])) "
                    '/ sum(rate(p03_decisions_total{decision="prune"}[6h]))) > '
                    f"{P03_ALERT_THRESHOLDS['regret_rate_percent']['critical']}"
                ),
                duration="30m",
                severity="critical",
                subsystem="learning",
                slo="quality",
                runbook_slug="p03-prune-regrets",
                summary="P03 prune regret rate CRITICAL",
                description=(
                    "Prune regret rate is {{ $value | humanizePercentage }} "
                    f"(> {P03_ALERT_THRESHOLDS['regret_rate_percent']['critical']}%), "
                    "pruning formula may be too aggressive"
                ),
            ),
            # Gap resolution rate
            _rule(
                alert="P03GapResolutionLow",
                expr=(
                    "100 * (sum(rate(p03_gaps_resolved_total[1h])) "
                    "/ sum(rate(p03_gaps_detected_total[1h]))) < "
                    f"{P03_ALERT_THRESHOLDS['gap_resolution_rate_percent']['warning']}"
                ),
                duration="2h",
                severity="warning",
                subsystem="learning",
                slo="gap-resolution",
                runbook_slug="p03-gap-resolution",
                summary="P03 gap resolution rate low",
                description=(
                    "Gap resolution rate is {{ $value | humanizePercentage }} "
                    f"(< {P03_ALERT_THRESHOLDS['gap_resolution_rate_percent']['warning']}%), "
                    "gaps are accumulating"
                ),
            ),
            # Issue 6.4.13: Learning budget alerts
            _rule(
                alert="P03LearningBudgetExceeded",
                expr=(
                    f"p03_learning_time_pct > "
                    f"{P03_ALERT_THRESHOLDS['learning_time_pct']['critical']}"
                ),
                duration="5m",
                severity="warning",
                subsystem="learning",
                slo="budget",
                runbook_slug="p03-learning-budget",
                summary="Learning operations exceed 5% budget",
                description=(
                    "Space {{ $labels.space_id }} learning at {{ $value }}% of cycle time "
                    f"(> {P03_ALERT_THRESHOLDS['learning_time_pct']['critical']}%), "
                    "investigate slow operations"
                ),
            ),
            _rule(
                alert="P03LearningSkipRateHigh",
                expr=(
                    f"rate(p03_learning_skip_count[1h]) * 3600 > "
                    f"{P03_ALERT_THRESHOLDS['learning_skip_rate_per_hour']['critical']}"
                ),
                duration="15m",
                severity="warning",
                subsystem="learning",
                slo="throughput",
                runbook_slug="p03-learning-skips",
                summary="High learning operation skip rate",
                description=("{{ $value }} operations/hour skipped due to budget constraints"),
            ),
            _rule(
                alert="P03LearningQueueHigh",
                expr=(
                    f"p03_learning_queue_depth > "
                    f"{P03_ALERT_THRESHOLDS['learning_queue_depth']['warning']}"
                ),
                duration="5m",
                severity="warning",
                subsystem="learning",
                slo="queue",
                runbook_slug="p03-learning-queue",
                summary="Learning feedback queue above 500 signals",
                description=("Queue depth at {{ $value }} signals, approaching capacity"),
            ),
            _rule(
                alert="P03LearningQueueCritical",
                expr=(
                    f"p03_learning_queue_depth > "
                    f"{P03_ALERT_THRESHOLDS['learning_queue_depth']['critical']}"
                ),
                duration="1m",
                severity="critical",
                subsystem="learning",
                slo="queue",
                runbook_slug="p03-learning-queue",
                summary="Learning feedback queue at capacity (1000 signals)",
                description=("Queue depth at {{ $value }} signals - at risk of overflow"),
            ),
            _rule(
                alert="P03LearningQueueOverflow",
                expr=(
                    f"rate(p03_learning_queue_overflow[5m]) * 60 > "
                    f"{P03_ALERT_THRESHOLDS['learning_queue_overflow_per_min']['critical']}"
                ),
                duration="5m",
                severity="critical",
                subsystem="learning",
                slo="queue",
                runbook_slug="p03-learning-overflow",
                summary="Learning queue overflowing",
                description=("{{ $value }} signals/min discarded, increase queue size"),
            ),
            _rule(
                alert="P03AuditDropsElevated",
                expr=(
                    f"rate(p03_audit_drops[5m]) * 60 > "
                    f"{P03_ALERT_THRESHOLDS['audit_drops_per_min']['critical']}"
                ),
                duration="5m",
                severity="warning",
                subsystem="learning",
                slo="audit",
                runbook_slug="p03-audit-drops",
                summary="Async audit logger dropping records",
                description=("{{ $value }} audit records/min dropped, async writer overloaded"),
            ),
        ],
    }


def _build_security_alerts() -> dict[str, Any]:
    """Build P03 security-related alert rules."""
    return {
        "name": "p03-security",
        "interval": "30s",
        "rules": [
            # Cross-space leakage detection
            _rule(
                alert="P03CrossSpaceLeakageDetected",
                expr=(
                    "sum(increase(p03_cross_space_access_denied_total[15m])) > "
                    f"{P03_ALERT_THRESHOLDS['cross_space_leakage']['warning']}"
                ),
                duration="1m",
                severity="warning",
                subsystem="security",
                slo="isolation",
                runbook_slug="p03-cross-space-leakage",
                summary="P03 cross-space access attempts detected",
                description=(
                    "{{ $value }} cross-space access attempts denied in last 15m, "
                    "possible isolation boundary violation"
                ),
                contact="security-oncall",
            ),
            _rule(
                alert="P03CrossSpaceLeakageCritical",
                expr=(
                    "sum(increase(p03_cross_space_access_denied_total[15m])) > "
                    f"{P03_ALERT_THRESHOLDS['cross_space_leakage']['critical']}"
                ),
                duration="1m",
                severity="critical",
                subsystem="security",
                slo="isolation",
                runbook_slug="p03-cross-space-leakage",
                summary="P03 cross-space leakage CRITICAL",
                description=(
                    "{{ $value }} cross-space access attempts denied - "
                    "potential security incident, investigate immediately"
                ),
                contact="security-oncall",
            ),
            # Shadow mode mismatch (security-relevant divergence)
            _rule(
                alert="P03ShadowSecurityDivergence",
                expr=(
                    'sum(rate(p03_formula_comparison_divergence{old_decision="keep",new_decision="prune"}[1h])) > 0 '
                    'or sum(rate(p03_formula_comparison_divergence{old_decision="prune",new_decision="keep"}[1h])) > 0'
                ),
                duration="15m",
                severity="info",
                subsystem="security",
                slo="consistency",
                runbook_slug="p03-shadow-divergence",
                summary="P03 shadow mode shows retention/prune divergence",
                description=(
                    "Shadow mode comparison shows different keep/prune decisions "
                    "between formula versions - review before promotion"
                ),
            ),
        ],
    }


def _build_performance_alerts() -> dict[str, Any]:
    """Build P03 performance-related alert rules."""
    return {
        "name": "p03-performance",
        "interval": "30s",
        "rules": [
            # Phase latency
            _rule(
                alert="P03PhaseLatencyWarning",
                expr=(
                    "histogram_quantile(0.95, sum(rate(p03_phase_duration_ms_bucket[5m])) by (le, phase)) > "
                    f"{P03_ALERT_THRESHOLDS['phase_latency_ms_p95']['warning']}"
                ),
                duration="10m",
                severity="warning",
                subsystem="performance",
                slo="latency",
                runbook_slug="p03-phase-latency",
                summary="P03 phase latency elevated",
                description=(
                    "Phase {{ $labels.phase }} P95 latency is {{ $value }}ms "
                    f"(> {P03_ALERT_THRESHOLDS['phase_latency_ms_p95']['warning']}ms)"
                ),
            ),
            _rule(
                alert="P03PhaseLatencyCritical",
                expr=(
                    "histogram_quantile(0.95, sum(rate(p03_phase_duration_ms_bucket[5m])) by (le, phase)) > "
                    f"{P03_ALERT_THRESHOLDS['phase_latency_ms_p95']['critical']}"
                ),
                duration="5m",
                severity="critical",
                subsystem="performance",
                slo="latency",
                runbook_slug="p03-phase-latency",
                summary="P03 phase latency CRITICAL",
                description=(
                    "Phase {{ $labels.phase }} P95 latency is {{ $value }}ms "
                    f"(> {P03_ALERT_THRESHOLDS['phase_latency_ms_p95']['critical']}ms), "
                    "investigate bottleneck"
                ),
            ),
            # Budget utilization
            _rule(
                alert="P03BudgetUtilizationWarning",
                expr=(
                    "100 * (p03_budget_utilized / p03_budget_total) > "
                    f"{P03_ALERT_THRESHOLDS['budget_utilization_percent']['warning']}"
                ),
                duration="15m",
                severity="warning",
                subsystem="performance",
                slo="capacity",
                runbook_slug="p03-budget-utilization",
                summary="P03 budget utilization high",
                description=(
                    "Budget utilization is {{ $value | humanizePercentage }} "
                    f"(> {P03_ALERT_THRESHOLDS['budget_utilization_percent']['warning']}%), "
                    "approaching capacity limits"
                ),
            ),
            _rule(
                alert="P03BudgetUtilizationCritical",
                expr=(
                    "100 * (p03_budget_utilized / p03_budget_total) > "
                    f"{P03_ALERT_THRESHOLDS['budget_utilization_percent']['critical']}"
                ),
                duration="5m",
                severity="critical",
                subsystem="performance",
                slo="capacity",
                runbook_slug="p03-budget-utilization",
                summary="P03 budget utilization CRITICAL",
                description=(
                    "Budget utilization is {{ $value | humanizePercentage }} "
                    f"(> {P03_ALERT_THRESHOLDS['budget_utilization_percent']['critical']}%), "
                    "consolidation may be throttled"
                ),
            ),
            # Formula execution errors
            _rule(
                alert="P03FormulaErrorsElevated",
                expr="sum(rate(p03_formula_errors_total[15m])) * 60 > 1",
                duration="10m",
                severity="warning",
                subsystem="performance",
                slo="reliability",
                runbook_slug="p03-formula-errors",
                summary="P03 formula execution errors detected",
                description=(
                    "Formula execution errors are {{ $value | humanize }} per minute, "
                    "check formula implementation"
                ),
            ),
        ],
    }


# -----------------------------------------------------------------------------
# Main Builder Function
# -----------------------------------------------------------------------------


def build_p03_alert_rules() -> dict[str, Any]:
    """Build complete Prometheus alert rules YAML structure for P03.

    Returns:
        Dictionary structure suitable for YAML serialization as Prometheus
        alerting rules file.

    Example output structure:
        {
            "groups": [
                {"name": "p03-cycle", "rules": [...]},
                {"name": "p03-queue", "rules": [...]},
                ...
            ]
        }
    """
    return {
        "groups": [
            _build_cycle_alerts(),
            _build_queue_alerts(),
            _build_learning_alerts(),
            _build_security_alerts(),
            _build_performance_alerts(),
        ]
    }


# Convenience function to get rules as YAML string
def get_p03_alerts_yaml() -> str:
    """Get P03 alert rules as YAML string.

    Requires PyYAML to be installed.

    Returns:
        YAML-formatted alert rules string
    """
    import yaml

    return yaml.safe_dump(build_p03_alert_rules(), default_flow_style=False, sort_keys=False)
