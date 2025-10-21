"""SLO dashboard builder using Grafana dashboard JSON format."""

from __future__ import annotations

from typing import Any

from ._config import (
    ALERT_THRESHOLDS,
    COLORS,
    DASHBOARD_VARIABLES,
    RUNBOOK_URL_BASE,
    SLO_TARGETS,
    get_dashboard_template,
    get_panel_defaults,
    get_stat_panel_defaults,
)

__all__ = [
    "build_kernel_overview_dashboard",
    "build_command_latency_dashboard",
    "build_query_latency_dashboard",
    "build_sse_health_dashboard",
    "build_replay_throughput_dashboard",
]


def _add_grid_pos(panel: dict[str, Any], x: int, y: int, w: int, h: int) -> None:
    """Add grid position to panel."""
    panel["gridPos"] = {"x": x, "y": y, "w": w, "h": h}


def _add_target(
    panel: dict[str, Any],
    expr: str,
    legend: str = "",
    ref_id: str = "A",
) -> None:
    """Add Prometheus query target to panel."""
    panel["targets"].append(
        {
            "datasource": {"type": "prometheus", "uid": "prometheus"},
            "expr": expr,
            "legendFormat": legend,
            "refId": ref_id,
        }
    )


def _apply_dashboard_links(
    dashboard: dict[str, Any],
    entries: list[tuple[str, str]],
) -> None:
    """Attach runbook links to a dashboard for quick operator access."""

    dashboard["links"] = [
        {
            "title": title,
            "url": RUNBOOK_URL_BASE.format(path=path),
            "type": "link",
            "targetBlank": True,
            "tooltip": f"Open {title}",
        }
        for title, path in entries
    ]

    if "description" not in dashboard:
        dashboard["description"] = (
            "Includes quick links to related runbooks for rapid incident response."
        )


def build_kernel_overview_dashboard() -> dict[str, Any]:
    """Build high-level kernel overview dashboard with SLO stat panels."""
    dashboard = get_dashboard_template()
    dashboard["title"] = "K0 Kernel Overview"
    dashboard["uid"] = "k0-kernel-overview"
    dashboard["templating"]["list"] = DASHBOARD_VARIABLES
    _apply_dashboard_links(
        dashboard,
        [
            ("SLO Dashboard Runbook", "slo-dashboard.md"),
            ("API Availability Runbook", "alerts/api-availability.md"),
            ("Command Latency Runbook", "alerts/command-latency.md"),
            ("Query Latency Runbook", "alerts/query-latency.md"),
            ("WAL Lag Runbook", "alerts/wal-lag.md"),
            ("Outbox Backlog Runbook", "alerts/outbox-backlog.md"),
        ],
    )

    panel_id = 1
    y_pos = 0

    # Row 1: SLO stat panels (6 panels, each 4 grid units wide)
    # NOTE: Using pre-aggregated recording rules for 50%+ query speedup
    slo_panels = [
        {
            "title": "API Availability",
            "expr": "100 * job:k0_api_availability:ratio5m",
            "unit": "percent",
            "decimals": 2,
            "thresholds": [
                {"value": 0, "color": COLORS["critical"]},
                {
                    "value": ALERT_THRESHOLDS["api_availability_percent"]["warning"],
                    "color": COLORS["warning"],
                },
                {
                    "value": SLO_TARGETS["api_availability_percent"],
                    "color": COLORS["success"],
                },
            ],
        },
        {
            "title": "Command Latency (p95)",
            "expr": "job:k0_command_latency_seconds:p95:5m * 1000",
            "unit": "ms",
            "decimals": 1,
            "thresholds": [
                {"value": 0, "color": COLORS["success"]},
                {
                    "value": ALERT_THRESHOLDS["command_latency_p95_ms"]["warning"],
                    "color": COLORS["warning"],
                },
                {
                    "value": ALERT_THRESHOLDS["command_latency_p95_ms"]["critical"],
                    "color": COLORS["critical"],
                },
            ],
        },
        {
            "title": "Query Latency (p95)",
            "expr": "job:k0_query_latency_seconds:p95:5m * 1000",
            "unit": "ms",
            "decimals": 1,
            "thresholds": [
                {"value": 0, "color": COLORS["success"]},
                {
                    "value": ALERT_THRESHOLDS["query_latency_p95_ms"]["warning"],
                    "color": COLORS["warning"],
                },
                {
                    "value": ALERT_THRESHOLDS["query_latency_p95_ms"]["critical"],
                    "color": COLORS["critical"],
                },
            ],
        },
        {
            "title": "Replay Throughput",
            "expr": "rate(k0_kernel_replay_watermark[$interval])",
            "unit": "evtps",
            "decimals": 0,
            "thresholds": [
                {"value": 0, "color": COLORS["critical"]},
                {
                    "value": ALERT_THRESHOLDS["replay_throughput_eps"]["critical"],
                    "color": COLORS["warning"],
                },
                {
                    "value": SLO_TARGETS["replay_throughput_eps"],
                    "color": COLORS["success"],
                },
            ],
        },
        {
            "title": "WAL Lag",
            "expr": "time() - k0_kernel_snapshot_watermark",
            "unit": "s",
            "decimals": 0,
            "thresholds": [
                {"value": 0, "color": COLORS["success"]},
                {
                    "value": ALERT_THRESHOLDS["wal_lag_seconds"]["warning"],
                    "color": COLORS["warning"],
                },
                {
                    "value": ALERT_THRESHOLDS["wal_lag_seconds"]["critical"],
                    "color": COLORS["critical"],
                },
            ],
        },
        {
            "title": "Outbox Backlog",
            "expr": 'sum(k0_outbox_pending_total{state="pending"})',
            "unit": "short",
            "decimals": 0,
            "thresholds": [
                {"value": 0, "color": COLORS["success"]},
                {
                    "value": ALERT_THRESHOLDS["outbox_backlog_count"]["warning"],
                    "color": COLORS["warning"],
                },
                {
                    "value": ALERT_THRESHOLDS["outbox_backlog_count"]["critical"],
                    "color": COLORS["critical"],
                },
            ],
        },
    ]

    for idx, slo in enumerate(slo_panels):
        panel = get_stat_panel_defaults()
        panel["id"] = panel_id
        panel["title"] = slo["title"]
        panel["fieldConfig"]["defaults"]["unit"] = slo["unit"]
        panel["fieldConfig"]["defaults"]["decimals"] = slo["decimals"]
        panel["fieldConfig"]["defaults"]["thresholds"]["steps"] = slo["thresholds"]
        _add_target(panel, slo["expr"])
        _add_grid_pos(panel, (idx % 6) * 4, y_pos, 4, 4)
        dashboard["panels"].append(panel)
        panel_id += 1

    y_pos += 4

    # Row 2: HTTP Request Rate and Error Rate
    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "HTTP Request Rate"
    panel["fieldConfig"]["defaults"]["unit"] = "reqps"
    _add_target(
        panel,
        "sum(rate(k0_kernel_http_requests_total[$interval])) by (method, route)",
        "{{method}} {{route}}",
    )
    _add_grid_pos(panel, 0, y_pos, 12, 6)
    dashboard["panels"].append(panel)
    panel_id += 1

    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "HTTP Error Rate"
    panel["fieldConfig"]["defaults"]["unit"] = "percentunit"
    _add_target(
        panel,
        'rate(k0_kernel_http_requests_total{status=~"5.."}[$interval]) / rate(k0_kernel_http_requests_total[$interval])',
        "Error Rate",
    )
    _add_grid_pos(panel, 12, y_pos, 12, 6)
    dashboard["panels"].append(panel)
    panel_id += 1

    y_pos += 6

    # Row 3: UoW Commit Latency and Outbox Apply Rate
    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "UoW Commit Latency (p95)"
    panel["fieldConfig"]["defaults"]["unit"] = "s"
    _add_target(
        panel,
        "histogram_quantile(0.95, sum(rate(k0_uow_commit_seconds_bucket[$interval])) by (le, outcome))",
        "{{outcome}}",
    )
    _add_grid_pos(panel, 0, y_pos, 12, 6)
    dashboard["panels"].append(panel)
    panel_id += 1

    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "Outbox Apply Rate by Outcome"
    panel["fieldConfig"]["defaults"]["unit"] = "ops"
    _add_target(
        panel, "sum(rate(k0_outbox_apply_total[$interval])) by (outcome)", "{{outcome}}"
    )
    _add_grid_pos(panel, 12, y_pos, 12, 6)
    dashboard["panels"].append(panel)
    panel_id += 1

    y_pos += 6

    # Row 4: Active Connections and SSE Subscriptions
    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "Active HTTP Connections"
    panel["fieldConfig"]["defaults"]["unit"] = "short"
    _add_target(panel, "k0_kernel_active_connections", "Connections")
    _add_grid_pos(panel, 0, y_pos, 12, 6)
    dashboard["panels"].append(panel)
    panel_id += 1

    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "Active SSE Subscriptions"
    panel["fieldConfig"]["defaults"]["unit"] = "short"
    _add_target(panel, "k0_sse_active_subscriptions", "Subscriptions")
    _add_grid_pos(panel, 12, y_pos, 12, 6)
    dashboard["panels"].append(panel)
    panel_id += 1

    return dashboard


def build_command_latency_dashboard() -> dict[str, Any]:
    """Build detailed command path latency dashboard."""
    dashboard = get_dashboard_template()
    dashboard["title"] = "K0 Command Latency"
    dashboard["uid"] = "k0-command-latency"
    dashboard["templating"]["list"] = DASHBOARD_VARIABLES
    _apply_dashboard_links(
        dashboard,
        [
            ("Command Latency Runbook", "alerts/command-latency.md"),
            ("Scheduler Starvation Runbook", "alerts/scheduler-starvation.md"),
        ],
    )

    panel_id = 1
    y_pos = 0

    # Command submission latency percentiles (using recording rules for speed)
    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "Command Submit Latency Percentiles"
    panel["fieldConfig"]["defaults"]["unit"] = "ms"
    # Use pre-aggregated recording rules instead of raw histogram_quantile
    _add_target(panel, "job:k0_command_latency_seconds:p50:5m * 1000", "p50", "P50")
    _add_target(panel, "job:k0_command_latency_seconds:p95:5m * 1000", "p95", "P95")
    _add_target(panel, "job:k0_command_latency_seconds:p99:5m * 1000", "p99", "P99")
    _add_grid_pos(panel, 0, y_pos, 24, 8)
    dashboard["panels"].append(panel)
    panel_id += 1
    y_pos += 8

    # UoW commit breakdown
    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "UoW Commit Latency Distribution"
    panel["fieldConfig"]["defaults"]["unit"] = "s"
    _add_target(
        panel,
        "histogram_quantile(0.5, sum(rate(k0_uow_commit_seconds_bucket[$interval])) by (le))",
        "p50",
        "A",
    )
    _add_target(
        panel,
        "histogram_quantile(0.95, sum(rate(k0_uow_commit_seconds_bucket[$interval])) by (le))",
        "p95",
        "B",
    )
    _add_target(
        panel,
        "histogram_quantile(0.99, sum(rate(k0_uow_commit_seconds_bucket[$interval])) by (le))",
        "p99",
        "C",
    )
    _add_grid_pos(panel, 0, y_pos, 12, 6)
    dashboard["panels"].append(panel)
    panel_id += 1

    # WAL fsync latency
    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "WAL Fsync Latency (p95)"
    panel["fieldConfig"]["defaults"]["unit"] = "s"
    _add_target(
        panel,
        "histogram_quantile(0.95, sum(rate(k0_uow_wal_fsync_seconds_bucket[$interval])) by (le))",
        "p95",
    )
    _add_grid_pos(panel, 12, y_pos, 12, 6)
    dashboard["panels"].append(panel)
    panel_id += 1
    y_pos += 6

    # Commit/Rollback counters
    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "UoW Commit Rate by Outcome"
    panel["fieldConfig"]["defaults"]["unit"] = "ops"
    _add_target(
        panel, "sum(rate(k0_uow_commit_total[$interval])) by (outcome)", "{{outcome}}"
    )
    _add_grid_pos(panel, 0, y_pos, 12, 6)
    dashboard["panels"].append(panel)
    panel_id += 1

    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "UoW Rollback Rate"
    panel["fieldConfig"]["defaults"]["unit"] = "ops"
    _add_target(panel, "sum(rate(k0_uow_rollback_total[$interval]))", "Rollbacks")
    _add_grid_pos(panel, 12, y_pos, 12, 6)
    dashboard["panels"].append(panel)
    panel_id += 1

    return dashboard


def build_query_latency_dashboard() -> dict[str, Any]:
    """Build detailed query path latency dashboard."""
    dashboard = get_dashboard_template()
    dashboard["title"] = "K0 Query Latency"
    dashboard["uid"] = "k0-query-latency"
    dashboard["templating"]["list"] = DASHBOARD_VARIABLES
    _apply_dashboard_links(
        dashboard,
        [
            ("Query Latency Runbook", "alerts/query-latency.md"),
        ],
    )

    panel_id = 1
    y_pos = 0

    # Query execution latency percentiles (using recording rules for speed)
    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "Query Execute Latency Percentiles"
    panel["fieldConfig"]["defaults"]["unit"] = "ms"
    # Use pre-aggregated recording rules instead of raw histogram_quantile
    _add_target(panel, "job:k0_query_latency_seconds:p50:5m * 1000", "p50", "P50")
    _add_target(panel, "job:k0_query_latency_seconds:p95:5m * 1000", "p95", "P95")
    _add_target(panel, "job:k0_query_latency_seconds:p99:5m * 1000", "p99", "P99")
    _add_grid_pos(panel, 0, y_pos, 24, 8)
    dashboard["panels"].append(panel)
    panel_id += 1
    y_pos += 8

    # Query rate by status
    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "Query Rate by Status"
    panel["fieldConfig"]["defaults"]["unit"] = "reqps"
    _add_target(
        panel,
        'sum(rate(k0_kernel_http_requests_total{route="/k0/query.execute"}[$interval])) by (status)',
        "{{status}}",
    )
    _add_grid_pos(panel, 0, y_pos, 24, 6)
    dashboard["panels"].append(panel)
    panel_id += 1

    return dashboard


def build_sse_health_dashboard() -> dict[str, Any]:
    """Build SSE subscription health dashboard."""
    dashboard = get_dashboard_template()
    dashboard["title"] = "K0 SSE Health"
    dashboard["uid"] = "k0-sse-health"
    dashboard["templating"]["list"] = DASHBOARD_VARIABLES
    _apply_dashboard_links(
        dashboard,
        [
            ("SSE Disconnect Runbook", "alerts/sse-disconnect.md"),
            ("Driver Handshake Runbook", "alerts/driver-handshake.md"),
        ],
    )

    panel_id = 1
    y_pos = 0

    # Active subscriptions
    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "Active SSE Subscriptions"
    panel["fieldConfig"]["defaults"]["unit"] = "short"
    _add_target(panel, "k0_sse_active_subscriptions", "Active")
    _add_grid_pos(panel, 0, y_pos, 12, 6)
    dashboard["panels"].append(panel)
    panel_id += 1

    # Subscription churn rate
    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "SSE Subscribe/Disconnect Rate"
    panel["fieldConfig"]["defaults"]["unit"] = "ops"
    _add_target(
        panel,
        'rate(k0_kernel_http_requests_total{route="/k0/sse.subscribe"}[$interval])',
        "Subscribe",
        "A",
    )
    _add_target(
        panel,
        'rate(k0_kernel_http_requests_total{route="/k0/sse.subscribe", status=~"499|5.."}[$interval])',
        "Disconnect/Error",
        "B",
    )
    _add_grid_pos(panel, 12, y_pos, 12, 6)
    dashboard["panels"].append(panel)
    panel_id += 1
    y_pos += 6

    # Bus dispatch latency
    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "Bus Dispatch Latency (p95)"
    panel["fieldConfig"]["defaults"]["unit"] = "s"
    _add_target(
        panel,
        "histogram_quantile(0.95, sum(rate(k0_bus_dispatch_latency_bucket[$interval])) by (le, driver))",
        "{{driver}}",
    )
    _add_grid_pos(panel, 0, y_pos, 24, 6)
    dashboard["panels"].append(panel)
    panel_id += 1

    return dashboard


def build_replay_throughput_dashboard() -> dict[str, Any]:
    """Build replay throughput and snapshot health dashboard."""
    dashboard = get_dashboard_template()
    dashboard["title"] = "K0 Replay & Snapshots"
    dashboard["uid"] = "k0-replay-throughput"
    dashboard["templating"]["list"] = DASHBOARD_VARIABLES
    _apply_dashboard_links(
        dashboard,
        [
            ("Replay Throughput Runbook", "alerts/replay-throughput.md"),
            ("Replay Failure Runbook", "alerts/replay-failure.md"),
            ("WAL Lag Runbook", "alerts/wal-lag.md"),
            ("Outbox Backlog Runbook", "alerts/outbox-backlog.md"),
        ],
    )

    panel_id = 1
    y_pos = 0

    # Replay throughput
    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "Replay Throughput"
    panel["fieldConfig"]["defaults"]["unit"] = "evtps"
    _add_target(panel, "rate(k0_kernel_replay_watermark[$interval])", "Events/sec")
    _add_grid_pos(panel, 0, y_pos, 12, 6)
    dashboard["panels"].append(panel)
    panel_id += 1

    # Snapshot watermark age
    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "Snapshot Age (WAL Lag)"
    panel["fieldConfig"]["defaults"]["unit"] = "s"
    _add_target(panel, "time() - k0_kernel_snapshot_watermark", "Age")
    _add_grid_pos(panel, 12, y_pos, 12, 6)
    dashboard["panels"].append(panel)
    panel_id += 1
    y_pos += 6

    # Outbox state breakdown
    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "Outbox Entries by State"
    panel["fieldConfig"]["defaults"]["unit"] = "short"
    _add_target(panel, "sum(k0_outbox_pending_total) by (state)", "{{state}}")
    _add_grid_pos(panel, 0, y_pos, 12, 6)
    dashboard["panels"].append(panel)
    panel_id += 1

    # Outbox apply outcomes
    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "Outbox Apply Rate by Outcome"
    panel["fieldConfig"]["defaults"]["unit"] = "ops"
    _add_target(
        panel,
        "sum(rate(k0_outbox_apply_total[$interval])) by (outcome, driver)",
        "{{outcome}}/{{driver}}",
    )
    _add_grid_pos(panel, 12, y_pos, 12, 6)
    dashboard["panels"].append(panel)
    panel_id += 1

    return dashboard
