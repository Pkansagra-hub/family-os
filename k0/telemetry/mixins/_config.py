"""Shared configuration and constants for telemetry dashboards and alerts."""

from __future__ import annotations

from typing import Any

# Color palette (macOS Big Sur inspired)
COLORS = {
    "success": "#34C759",
    "warning": "#FF9F0A",
    "critical": "#FF3B30",
    "info": "#007AFF",
    "background_dark": "#1C1C1E",
    "background_light": "#F2F2F7",
    "text": "#FFFFFF",
}

# Runbook URL base (used for dashboards and alert metadata)
RUNBOOK_URL_BASE = (
    "https://github.com/Pkansagra-hub/memory_kernel/blob/main/docs/"
    "development/runbooks/{path}"
)

# SLO targets
SLO_TARGETS: dict[str, float] = {
    "command_latency_p95_ms": 100,
    "query_latency_p95_ms": 50,
    "api_availability_percent": 99.9,
    "replay_throughput_eps": 1000,
    "wal_lag_seconds": 60,
    "outbox_backlog_count": 10000,
    "scheduler_denials_per_minute": 0,
    "replay_failure_percent": 0,
    "sse_active_ratio_percent": 100,
    "driver_handshake_failures_per_minute": 0,
    "scheduler_quorum_members": 3,
    "wal_replica_lag_seconds": 10,
    "cluster_zone_health_ratio": 1,
}

# Alert thresholds
ALERT_THRESHOLDS: dict[str, dict[str, float]] = {
    "command_latency_p95_ms": {"warning": 150, "critical": 250},
    "query_latency_p95_ms": {"warning": 75, "critical": 150},
    "api_availability_percent": {"warning": 99.5, "critical": 99.0},
    "replay_throughput_eps": {"warning": 500, "critical": 100},
    "wal_lag_seconds": {"warning": 120, "critical": 300},
    "outbox_backlog_count": {"warning": 50000, "critical": 100000},
    "scheduler_denials_per_minute": {"warning": 10, "critical": 25},
    "replay_failure_percent": {"warning": 2, "critical": 5},
    "sse_active_ratio_percent": {"warning": 95, "critical": 90},
    "driver_handshake_failures_per_minute": {"warning": 1, "critical": 3},
    "scheduler_quorum_members": {"warning": 3, "critical": 2},
    "wal_replica_lag_seconds": {"warning": 20, "critical": 30},
    "cluster_zone_health_ratio": {"warning": 1, "critical": 0},
}

# Alert routing contacts by subsystem
ALERT_CONTACTS: dict[str, str] = {
    "availability": "sre",
    "command": "runtime",
    "query": "runtime",
    "storage": "storage",
    "replay": "storage",
    "outbox": "storage",
    "qos": "qos",
    "sse": "ports",
    "drivers": "drivers",
    "meta": "sre",
    "topology": "sre",
}

# Dashboard variables
DASHBOARD_VARIABLES: list[dict[str, Any]] = [
    {
        "name": "route",
        "type": "query",
        "label": "Route",
        "query": "label_values(k0_kernel_http_requests_total, route)",
        "multi": True,
        "includeAll": True,
        "current": {"text": "All", "value": "$__all"},
    },
    {
        "name": "method",
        "type": "query",
        "label": "Method",
        "query": 'label_values(k0_kernel_http_requests_total{route=~"$route"}, method)',
        "multi": True,
        "includeAll": True,
        "current": {"text": "All", "value": "$__all"},
    },
    {
        "name": "interval",
        "type": "interval",
        "label": "Interval",
        "auto": True,
        "auto_count": 30,
        "options": [
            {"text": "1m", "value": "1m"},
            {"text": "5m", "value": "5m", "selected": True},
            {"text": "15m", "value": "15m"},
            {"text": "30m", "value": "30m"},
            {"text": "1h", "value": "1h"},
            {"text": "6h", "value": "6h"},
            {"text": "12h", "value": "12h"},
            {"text": "1d", "value": "1d"},
        ],
        "current": {"text": "5m", "value": "5m"},
    },
    {
        "name": "percentile",
        "type": "custom",
        "label": "Percentile",
        "options": [
            {"text": "p50", "value": "0.5"},
            {"text": "p95", "value": "0.95", "selected": True},
            {"text": "p99", "value": "0.99"},
        ],
        "current": {"text": "p95", "value": "0.95"},
    },
]

# Prometheus histogram buckets (must match k0/obs/metrics.py)
HISTOGRAM_BUCKETS: list[float] = [
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1,
    2.5,
    5,
    10,
]


def get_dashboard_template() -> dict[str, Any]:
    """Return base Grafana dashboard template."""
    return {
        "annotations": {"list": []},
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,  # Shared crosshair
        "links": [],
        "liveNow": False,
        "panels": [],
        "refresh": "30s",
        "schemaVersion": 39,
        "tags": ["k0", "slo", "kernel"],
        "templating": {"list": []},
        "time": {"from": "now-1h", "to": "now"},
        "timepicker": {},
        "timezone": "browser",
        "version": 0,
        "weekStart": "",
    }


def get_panel_defaults() -> dict[str, Any]:
    """Return default panel configuration."""
    return {
        "type": "timeseries",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "palette-classic"},
                "custom": {
                    "axisBorderShow": False,
                    "axisCenteredZero": False,
                    "axisColorMode": "text",
                    "axisLabel": "",
                    "axisPlacement": "auto",
                    "barAlignment": 0,
                    "drawStyle": "line",
                    "fillOpacity": 10,
                    "gradientMode": "none",
                    "hideFrom": {"tooltip": False, "viz": False, "legend": False},
                    "insertNulls": False,
                    "lineInterpolation": "linear",
                    "lineWidth": 1,
                    "pointSize": 5,
                    "scaleDistribution": {"type": "linear"},
                    "showPoints": "never",
                    "spanNulls": False,
                    "stacking": {"group": "A", "mode": "none"},
                    "thresholdsStyle": {"mode": "off"},
                },
                "mappings": [],
                "thresholds": {
                    "mode": "absolute",
                    "steps": [
                        {"color": "green", "value": None},
                    ],
                },
                "unit": "short",
            },
            "overrides": [],
        },
        "options": {
            "legend": {
                "calcs": ["mean", "lastNotNull", "max"],
                "displayMode": "table",
                "placement": "bottom",
                "showLegend": True,
            },
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
        "targets": [],
    }


def get_stat_panel_defaults() -> dict[str, Any]:
    """Return default stat panel configuration for single-value metrics."""
    return {
        "type": "stat",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "thresholds"},
                "mappings": [],
                "thresholds": {
                    "mode": "absolute",
                    "steps": [
                        {"color": "green", "value": None},
                    ],
                },
                "unit": "short",
            },
            "overrides": [],
        },
        "options": {
            "colorMode": "value",
            "graphMode": "area",
            "justifyMode": "auto",
            "orientation": "auto",
            "reduceOptions": {
                "values": False,
                "calcs": ["lastNotNull"],
                "fields": "",
            },
            "showPercentChange": False,
            "textMode": "auto",
            "wideLayout": True,
        },
        "targets": [],
    }
