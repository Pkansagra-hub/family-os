"""Prometheus alert rule builder for K0 kernel SLOs."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from ._config import ALERT_CONTACTS, ALERT_THRESHOLDS, RUNBOOK_URL_BASE, SLO_TARGETS

__all__ = ["build_slo_alert_rules"]


class RuleLabels(TypedDict, total=False):
    severity: Literal["info", "warning", "critical"]
    component: str
    subsystem: str
    slo: str
    tenant: str
    space: str
    maintenance: Literal["true", "false"]
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


def _rule(
    *,
    alert: str,
    expr: str,
    duration: str,
    severity: Literal["info", "warning", "critical"],
    component: str,
    subsystem: str,
    slo: str,
    runbook_slug: str,
    runbook_directory: str = "alerts",
    summary: str,
    description: str,
    contact_override: str | None = None,
) -> RuleDefinition:
    contact = contact_override or ALERT_CONTACTS.get(subsystem, "sre")

    if runbook_directory:
        directory = runbook_directory.rstrip("/")
        runbook_rel = f"{directory}/{runbook_slug}.md"
    else:
        runbook_rel = f"{runbook_slug}.md"

    labels: RuleLabels = {
        "severity": severity,
        "component": component,
        "subsystem": subsystem,
        "slo": slo,
        "tenant": "all",
        "space": "all",
        "maintenance": "false",
        "contact": contact,
        "runbook": runbook_rel,
    }

    annotations: RuleAnnotations = {
        "summary": summary,
        "description": description,
        "runbook_url": RUNBOOK_URL_BASE.format(path=runbook_rel),
    }

    return {
        "alert": alert,
        "expr": expr,
        "for": duration,
        "labels": labels,
        "annotations": annotations,
    }


def build_slo_alert_rules() -> dict[str, Any]:
    """Build Prometheus alert rules YAML structure for SLO monitoring."""

    groups: list[dict[str, Any]] = []

    # Availability-focused alerts
    groups.append(
        {
            "name": "k0-availability",
            "interval": "30s",
            "rules": [
                _rule(
                    alert="K0ApiAvailabilityWarning",
                    expr=(
                        '100 * (1 - (rate(k0_kernel_http_requests_total{status=~"5.."}[5m]) '
                        "/ rate(k0_kernel_http_requests_total[5m]))) < "
                        f"{ALERT_THRESHOLDS['api_availability_percent']['warning']}"
                    ),
                    duration="5m",
                    severity="warning",
                    component="kernel",
                    subsystem="availability",
                    slo="availability",
                    runbook_slug="api-availability",
                    summary="K0 API availability below warning threshold",
                    description=(
                        "API availability is {{ $value | humanizePercentage }} (< "
                        f"{ALERT_THRESHOLDS['api_availability_percent']['warning']}%), "
                        f"target is {SLO_TARGETS['api_availability_percent']}%"
                    ),
                ),
                _rule(
                    alert="K0ApiAvailabilityCritical",
                    expr=(
                        '100 * (1 - (rate(k0_kernel_http_requests_total{status=~"5.."}[5m]) '
                        "/ rate(k0_kernel_http_requests_total[5m]))) < "
                        f"{ALERT_THRESHOLDS['api_availability_percent']['critical']}"
                    ),
                    duration="2m",
                    severity="critical",
                    component="kernel",
                    subsystem="availability",
                    slo="availability",
                    runbook_slug="api-availability",
                    summary="K0 API availability CRITICAL",
                    description=(
                        "API availability is {{ $value | humanizePercentage }} (< "
                        f"{ALERT_THRESHOLDS['api_availability_percent']['critical']}%), "
                        f"target is {SLO_TARGETS['api_availability_percent']}%"
                    ),
                ),
                _rule(
                    alert="K0DriverHandshakeFailureWarning",
                    expr=(
                        'rate(k0_driver_handshakes_total{outcome="failure"}[5m]) * 60 > '
                        f"{ALERT_THRESHOLDS['driver_handshake_failures_per_minute']['warning']}"
                    ),
                    duration="10m",
                    severity="warning",
                    component="drivers",
                    subsystem="drivers",
                    slo="availability",
                    runbook_slug="driver-handshake",
                    summary="K0 driver handshake failures above warning threshold",
                    description=(
                        "Driver handshake failures are {{ $value | humanize }} per minute (> "
                        f"{ALERT_THRESHOLDS['driver_handshake_failures_per_minute']['warning']}), "
                        "investigate driver availability"
                    ),
                ),
                _rule(
                    alert="K0DriverHandshakeFailureCritical",
                    expr=(
                        'rate(k0_driver_handshakes_total{outcome="failure"}[5m]) * 60 > '
                        f"{ALERT_THRESHOLDS['driver_handshake_failures_per_minute']['critical']}"
                    ),
                    duration="5m",
                    severity="critical",
                    component="drivers",
                    subsystem="drivers",
                    slo="availability",
                    runbook_slug="driver-handshake",
                    summary="K0 driver handshake failures CRITICAL",
                    description=(
                        "Driver handshake failures are {{ $value | humanize }} per minute (> "
                        f"{ALERT_THRESHOLDS['driver_handshake_failures_per_minute']['critical']}), "
                        "drivers likely offline"
                    ),
                ),
            ],
        }
    )

    # Topology and multi-zone health alerts
    groups.append(
        {
            "name": "k0-topology",
            "interval": "30s",
            "rules": [
                _rule(
                    alert="K0SchedulerQuorumWarning",
                    expr=(
                        "min without(zone)(k0_scheduler_quorum_members) < "
                        f"{ALERT_THRESHOLDS['scheduler_quorum_members']['warning']}"
                    ),
                    duration="5m",
                    severity="warning",
                    component="cluster",
                    subsystem="topology",
                    slo="topology",
                    runbook_slug="control-plane-failover",
                    runbook_directory="",
                    summary="Scheduler quorum below warning threshold",
                    description=(
                        "Scheduler quorum minimum is {{ $value | humanize }} (< "
                        f"{ALERT_THRESHOLDS['scheduler_quorum_members']['warning']}), target is "
                        f"{SLO_TARGETS['scheduler_quorum_members']}"
                    ),
                ),
                _rule(
                    alert="K0SchedulerQuorumCritical",
                    expr=(
                        "min without(zone)(k0_scheduler_quorum_members) < "
                        f"{ALERT_THRESHOLDS['scheduler_quorum_members']['critical']}"
                    ),
                    duration="2m",
                    severity="critical",
                    component="cluster",
                    subsystem="topology",
                    slo="topology",
                    runbook_slug="control-plane-failover",
                    runbook_directory="",
                    summary="Scheduler quorum CRITICAL",
                    description=(
                        "Scheduler quorum minimum is {{ $value | humanize }} (< "
                        f"{ALERT_THRESHOLDS['scheduler_quorum_members']['critical']}), target is "
                        f"{SLO_TARGETS['scheduler_quorum_members']}"
                    ),
                ),
                _rule(
                    alert="K0WalReplicaLagWarning",
                    expr=(
                        "max without(instance, pod)(k0_wal_replica_lag_seconds) > "
                        f"{ALERT_THRESHOLDS['wal_replica_lag_seconds']['warning']}"
                    ),
                    duration="10m",
                    severity="warning",
                    component="storage",
                    subsystem="topology",
                    slo="freshness",
                    runbook_slug="data-plane-promotion",
                    runbook_directory="",
                    summary="Replica WAL lag above warning threshold",
                    description=(
                        "Replica WAL lag is {{ $value | humanizeDuration }} (> "
                        f"{ALERT_THRESHOLDS['wal_replica_lag_seconds']['warning']}s), target is < "
                        f"{SLO_TARGETS['wal_replica_lag_seconds']}s"
                    ),
                ),
                _rule(
                    alert="K0WalReplicaLagCritical",
                    expr=(
                        "max without(instance, pod)(k0_wal_replica_lag_seconds) > "
                        f"{ALERT_THRESHOLDS['wal_replica_lag_seconds']['critical']}"
                    ),
                    duration="5m",
                    severity="critical",
                    component="storage",
                    subsystem="topology",
                    slo="freshness",
                    runbook_slug="data-plane-promotion",
                    runbook_directory="",
                    summary="Replica WAL lag CRITICAL",
                    description=(
                        "Replica WAL lag is {{ $value | humanizeDuration }} (> "
                        f"{ALERT_THRESHOLDS['wal_replica_lag_seconds']['critical']}s), target is < "
                        f"{SLO_TARGETS['wal_replica_lag_seconds']}s"
                    ),
                ),
                _rule(
                    alert="K0ZoneHealthWarning",
                    expr=(
                        "sum(k0_cluster_zone_health) / clamp_min(count(k0_cluster_zone_health), 1) < "
                        f"{ALERT_THRESHOLDS['cluster_zone_health_ratio']['warning']}"
                    ),
                    duration="10m",
                    severity="warning",
                    component="cluster",
                    subsystem="topology",
                    slo="availability",
                    runbook_slug="control-plane-failover",
                    runbook_directory="",
                    summary="Cluster zone health below warning threshold",
                    description=(
                        "Average cluster zone health is {{ $value | humanize }} (< "
                        f"{ALERT_THRESHOLDS['cluster_zone_health_ratio']['warning']}), target is "
                        f"{SLO_TARGETS['cluster_zone_health_ratio']}"
                    ),
                ),
                _rule(
                    alert="K0ZoneHealthCritical",
                    expr=(
                        "sum(k0_cluster_zone_health) / clamp_min(count(k0_cluster_zone_health), 1) <= "
                        f"{ALERT_THRESHOLDS['cluster_zone_health_ratio']['critical']}"
                    ),
                    duration="2m",
                    severity="critical",
                    component="cluster",
                    subsystem="topology",
                    slo="availability",
                    runbook_slug="control-plane-failover",
                    runbook_directory="",
                    summary="Cluster zone health CRITICAL",
                    description=(
                        "Average cluster zone health is {{ $value | humanize }} (<= "
                        f"{ALERT_THRESHOLDS['cluster_zone_health_ratio']['critical']}), target is "
                        f"{SLO_TARGETS['cluster_zone_health_ratio']}"
                    ),
                ),
            ],
        }
    )

    # Latency-centric alerts
    groups.append(
        {
            "name": "k0-slo-latency",
            "interval": "30s",
            "rules": [
                _rule(
                    alert="K0CommandLatencyWarning",
                    expr=(
                        "histogram_quantile(0.95, sum(rate(k0_kernel_http_request_latency_seconds_bucket"
                        '{route="/k0/command.submit"}[5m])) by (le)) * 1000 > '
                        f"{ALERT_THRESHOLDS['command_latency_p95_ms']['warning']}"
                    ),
                    duration="5m",
                    severity="warning",
                    component="kernel",
                    subsystem="command",
                    slo="latency",
                    runbook_slug="command-latency",
                    summary="K0 command latency (p95) above warning threshold",
                    description=(
                        "Command p95 latency is {{ $value | humanize }}ms (> "
                        f"{ALERT_THRESHOLDS['command_latency_p95_ms']['warning']}ms), target is < "
                        f"{SLO_TARGETS['command_latency_p95_ms']}ms"
                    ),
                ),
                _rule(
                    alert="K0CommandLatencyCritical",
                    expr=(
                        "histogram_quantile(0.95, sum(rate(k0_kernel_http_request_latency_seconds_bucket"
                        '{route="/k0/command.submit"}[5m])) by (le)) * 1000 > '
                        f"{ALERT_THRESHOLDS['command_latency_p95_ms']['critical']}"
                    ),
                    duration="2m",
                    severity="critical",
                    component="kernel",
                    subsystem="command",
                    slo="latency",
                    runbook_slug="command-latency",
                    summary="K0 command latency (p95) CRITICAL",
                    description=(
                        "Command p95 latency is {{ $value | humanize }}ms (> "
                        f"{ALERT_THRESHOLDS['command_latency_p95_ms']['critical']}ms), target is < "
                        f"{SLO_TARGETS['command_latency_p95_ms']}ms"
                    ),
                ),
                _rule(
                    alert="K0QueryLatencyWarning",
                    expr=(
                        "histogram_quantile(0.95, sum(rate(k0_kernel_http_request_latency_seconds_bucket"
                        '{route="/k0/query.execute"}[5m])) by (le)) * 1000 > '
                        f"{ALERT_THRESHOLDS['query_latency_p95_ms']['warning']}"
                    ),
                    duration="5m",
                    severity="warning",
                    component="kernel",
                    subsystem="query",
                    slo="latency",
                    runbook_slug="query-latency",
                    summary="K0 query latency (p95) above warning threshold",
                    description=(
                        "Query p95 latency is {{ $value | humanize }}ms (> "
                        f"{ALERT_THRESHOLDS['query_latency_p95_ms']['warning']}ms), target is < "
                        f"{SLO_TARGETS['query_latency_p95_ms']}ms"
                    ),
                ),
                _rule(
                    alert="K0QueryLatencyCritical",
                    expr=(
                        "histogram_quantile(0.95, sum(rate(k0_kernel_http_request_latency_seconds_bucket"
                        '{route="/k0/query.execute"}[5m])) by (le)) * 1000 > '
                        f"{ALERT_THRESHOLDS['query_latency_p95_ms']['critical']}"
                    ),
                    duration="2m",
                    severity="critical",
                    component="kernel",
                    subsystem="query",
                    slo="latency",
                    runbook_slug="query-latency",
                    summary="K0 query latency (p95) CRITICAL",
                    description=(
                        "Query p95 latency is {{ $value | humanize }}ms (> "
                        f"{ALERT_THRESHOLDS['query_latency_p95_ms']['critical']}ms), target is < "
                        f"{SLO_TARGETS['query_latency_p95_ms']}ms"
                    ),
                ),
            ],
        }
    )

    # Durability, backlogs, and replay alerts
    groups.append(
        {
            "name": "k0-durability",
            "interval": "60s",
            "rules": [
                _rule(
                    alert="K0WalLagWarning",
                    expr=(
                        "time() - k0_kernel_snapshot_watermark > "
                        f"{ALERT_THRESHOLDS['wal_lag_seconds']['warning']}"
                    ),
                    duration="5m",
                    severity="warning",
                    component="storage",
                    subsystem="storage",
                    slo="freshness",
                    runbook_slug="wal-lag",
                    summary="K0 WAL lag above warning threshold",
                    description=(
                        "WAL lag is {{ $value | humanizeDuration }} (> "
                        f"{ALERT_THRESHOLDS['wal_lag_seconds']['warning']}s), target is < "
                        f"{SLO_TARGETS['wal_lag_seconds']}s"
                    ),
                ),
                _rule(
                    alert="K0WalLagCritical",
                    expr=(
                        "time() - k0_kernel_snapshot_watermark > "
                        f"{ALERT_THRESHOLDS['wal_lag_seconds']['critical']}"
                    ),
                    duration="2m",
                    severity="critical",
                    component="storage",
                    subsystem="storage",
                    slo="freshness",
                    runbook_slug="wal-lag",
                    summary="K0 WAL lag CRITICAL",
                    description=(
                        "WAL lag is {{ $value | humanizeDuration }} (> "
                        f"{ALERT_THRESHOLDS['wal_lag_seconds']['critical']}s), target is < "
                        f"{SLO_TARGETS['wal_lag_seconds']}s"
                    ),
                ),
                _rule(
                    alert="K0OutboxBacklogWarning",
                    expr=(
                        'sum(k0_outbox_pending_total{state="pending"}) > '
                        f"{ALERT_THRESHOLDS['outbox_backlog_count']['warning']}"
                    ),
                    duration="10m",
                    severity="warning",
                    component="storage",
                    subsystem="outbox",
                    slo="saturation",
                    runbook_slug="outbox-backlog",
                    summary="K0 outbox backlog above warning threshold",
                    description=(
                        "Outbox pending count is {{ $value | humanize }} (> "
                        f"{ALERT_THRESHOLDS['outbox_backlog_count']['warning']}), target is < "
                        f"{SLO_TARGETS['outbox_backlog_count']}"
                    ),
                ),
                _rule(
                    alert="K0OutboxBacklogCritical",
                    expr=(
                        'sum(k0_outbox_pending_total{state="pending"}) > '
                        f"{ALERT_THRESHOLDS['outbox_backlog_count']['critical']}"
                    ),
                    duration="5m",
                    severity="critical",
                    component="storage",
                    subsystem="outbox",
                    slo="saturation",
                    runbook_slug="outbox-backlog",
                    summary="K0 outbox backlog CRITICAL",
                    description=(
                        "Outbox pending count is {{ $value | humanize }} (> "
                        f"{ALERT_THRESHOLDS['outbox_backlog_count']['critical']}), target is < "
                        f"{SLO_TARGETS['outbox_backlog_count']}"
                    ),
                ),
                _rule(
                    alert="K0ReplayThroughputWarning",
                    expr=(
                        "rate(k0_kernel_replay_watermark[5m]) < "
                        f"{ALERT_THRESHOLDS['replay_throughput_eps']['warning']}"
                    ),
                    duration="10m",
                    severity="warning",
                    component="replay",
                    subsystem="replay",
                    slo="throughput",
                    runbook_slug="replay-throughput",
                    summary="K0 replay throughput below warning threshold",
                    description=(
                        "Replay throughput is {{ $value | humanize }} evt/s (< "
                        f"{ALERT_THRESHOLDS['replay_throughput_eps']['warning']} evt/s), target is > "
                        f"{SLO_TARGETS['replay_throughput_eps']} evt/s"
                    ),
                ),
                _rule(
                    alert="K0ReplayThroughputCritical",
                    expr=(
                        "rate(k0_kernel_replay_watermark[5m]) < "
                        f"{ALERT_THRESHOLDS['replay_throughput_eps']['critical']}"
                    ),
                    duration="5m",
                    severity="critical",
                    component="replay",
                    subsystem="replay",
                    slo="throughput",
                    runbook_slug="replay-throughput",
                    summary="K0 replay throughput CRITICAL",
                    description=(
                        "Replay throughput is {{ $value | humanize }} evt/s (< "
                        f"{ALERT_THRESHOLDS['replay_throughput_eps']['critical']} evt/s), target is > "
                        f"{SLO_TARGETS['replay_throughput_eps']} evt/s"
                    ),
                ),
                _rule(
                    alert="K0ReplayFailureRateWarning",
                    expr=(
                        "(100 * rate(k0_replay_failures_total[5m]) / clamp_min(rate(k0_replay_attempts_total[5m]), 1)) > "
                        f"{ALERT_THRESHOLDS['replay_failure_percent']['warning']}"
                    ),
                    duration="15m",
                    severity="warning",
                    component="replay",
                    subsystem="replay",
                    slo="reliability",
                    runbook_slug="replay-failure",
                    summary="K0 replay failure rate above warning threshold",
                    description=(
                        "Replay failure ratio is {{ $value | humanizePercentage }} (> "
                        f"{ALERT_THRESHOLDS['replay_failure_percent']['warning']}%), "
                        "investigate downstream storage or payload integrity"
                    ),
                ),
                _rule(
                    alert="K0ReplayFailureRateCritical",
                    expr=(
                        "(100 * rate(k0_replay_failures_total[5m]) / clamp_min(rate(k0_replay_attempts_total[5m]), 1)) > "
                        f"{ALERT_THRESHOLDS['replay_failure_percent']['critical']}"
                    ),
                    duration="5m",
                    severity="critical",
                    component="replay",
                    subsystem="replay",
                    slo="reliability",
                    runbook_slug="replay-failure",
                    summary="K0 replay failure rate CRITICAL",
                    description=(
                        "Replay failure ratio is {{ $value | humanizePercentage }} (> "
                        f"{ALERT_THRESHOLDS['replay_failure_percent']['critical']}%), "
                        "replay pipeline compromised"
                    ),
                ),
            ],
        }
    )

    # QoS and subscriber health alerts
    groups.append(
        {
            "name": "k0-qos",
            "interval": "30s",
            "rules": [
                _rule(
                    alert="K0SchedulerStarvationWarning",
                    expr=(
                        "rate(k0_qos_scheduler_denials_total[5m]) * 60 > "
                        f"{ALERT_THRESHOLDS['scheduler_denials_per_minute']['warning']}"
                    ),
                    duration="10m",
                    severity="warning",
                    component="qos",
                    subsystem="qos",
                    slo="capacity",
                    runbook_slug="scheduler-starvation",
                    summary="K0 scheduler denials above warning threshold",
                    description=(
                        "Scheduler denials are {{ $value | humanize }} per minute (> "
                        f"{ALERT_THRESHOLDS['scheduler_denials_per_minute']['warning']}), check QoS budgets"
                    ),
                ),
                _rule(
                    alert="K0SchedulerStarvationCritical",
                    expr=(
                        "rate(k0_qos_scheduler_denials_total[5m]) * 60 > "
                        f"{ALERT_THRESHOLDS['scheduler_denials_per_minute']['critical']}"
                    ),
                    duration="5m",
                    severity="critical",
                    component="qos",
                    subsystem="qos",
                    slo="capacity",
                    runbook_slug="scheduler-starvation",
                    summary="K0 scheduler denials CRITICAL",
                    description=(
                        "Scheduler denials are {{ $value | humanize }} per minute (> "
                        f"{ALERT_THRESHOLDS['scheduler_denials_per_minute']['critical']}), workloads starved"
                    ),
                ),
                _rule(
                    alert="K0SseDisconnectSpikeWarning",
                    expr=(
                        "100 * avg_over_time(k0_sse_active_subscriptions[5m]) / "
                        "clamp_min(avg_over_time(k0_sse_active_subscriptions[30m]), 1) < "
                        f"{ALERT_THRESHOLDS['sse_active_ratio_percent']['warning']}"
                    ),
                    duration="10m",
                    severity="warning",
                    component="ports",
                    subsystem="sse",
                    slo="availability",
                    runbook_slug="sse-disconnect",
                    summary="K0 SSE active subscription ratio below warning threshold",
                    description=(
                        "SSE active subscriptions are {{ $value | humanizePercentage }} of baseline (< "
                        f"{ALERT_THRESHOLDS['sse_active_ratio_percent']['warning']}%), investigate disconnect causes"
                    ),
                ),
                _rule(
                    alert="K0SseDisconnectSpikeCritical",
                    expr=(
                        "100 * avg_over_time(k0_sse_active_subscriptions[5m]) / "
                        "clamp_min(avg_over_time(k0_sse_active_subscriptions[30m]), 1) < "
                        f"{ALERT_THRESHOLDS['sse_active_ratio_percent']['critical']}"
                    ),
                    duration="5m",
                    severity="critical",
                    component="ports",
                    subsystem="sse",
                    slo="availability",
                    runbook_slug="sse-disconnect",
                    summary="K0 SSE active subscription ratio CRITICAL",
                    description=(
                        "SSE active subscriptions are {{ $value | humanizePercentage }} of baseline (< "
                        f"{ALERT_THRESHOLDS['sse_active_ratio_percent']['critical']}%), widespread disconnect"
                    ),
                ),
            ],
        }
    )

    # Meta and guardrail alerts
    groups.append(
        {
            "name": "k0-meta",
            "interval": "120s",
            "rules": [
                _rule(
                    alert="K0AlertingDeadman",
                    expr="vector(1)",
                    duration="0m",
                    severity="info",
                    component="observability",
                    subsystem="meta",
                    slo="meta",
                    runbook_slug="alerting-deadman",
                    summary="K0 alerting dead-man switch",
                    description=(
                        "Alertmanager heartbeat should always be firing; silence only for maintenance. "
                        "If missing, alerting pipeline may be down."
                    ),
                    contact_override="sre",
                ),
            ],
        }
    )
    return {"groups": groups}
    return {"groups": groups}
    return {"groups": groups}
    return {"groups": groups}
