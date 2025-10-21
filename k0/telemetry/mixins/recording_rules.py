"""Recording rules for pre-aggregating SLI metrics.

Recording rules reduce query latency by pre-calculating expensive histogram
quantiles and rate calculations. These rules run in Prometheus at regular
intervals and store the results as new time series.

FAANG-level Practice:
- Pre-aggregate p50/p95/p99 latencies
- Calculate availability ratios
- Compute throughput rates
- All dashboards query recording rules instead of raw metrics
"""

from __future__ import annotations

from typing import Any

from k0.telemetry.mixins._config import SLO_TARGETS


def generate_recording_rules() -> dict[str, Any]:
    """Generate Prometheus recording rules for SLI pre-aggregation.

    Recording rules follow naming convention:
    - <metric_type>:<name>:<aggregation>:<time_window>

    Examples:
    - job:http_request_duration_seconds:p95:5m
    - job:http_requests:rate5m
    - job:http_availability:ratio5m
    """

    rules = {
        "groups": [
            # HTTP Latency Recording Rules (p50, p95, p99)
            {
                "name": "k0-sli-latency-recording",
                "interval": "15s",
                "rules": [
                    # Command latency quantiles
                    {
                        "record": "job:k0_command_latency_seconds:p50:5m",
                        "expr": (
                            "histogram_quantile(0.50, "
                            "sum(rate(k0_kernel_http_request_latency_seconds_bucket{"
                            'route="/k0/command.submit"}[5m])) by (le))'
                        ),
                    },
                    {
                        "record": "job:k0_command_latency_seconds:p95:5m",
                        "expr": (
                            "histogram_quantile(0.95, "
                            "sum(rate(k0_kernel_http_request_latency_seconds_bucket{"
                            'route="/k0/command.submit"}[5m])) by (le))'
                        ),
                    },
                    {
                        "record": "job:k0_command_latency_seconds:p99:5m",
                        "expr": (
                            "histogram_quantile(0.99, "
                            "sum(rate(k0_kernel_http_request_latency_seconds_bucket{"
                            'route="/k0/command.submit"}[5m])) by (le))'
                        ),
                    },
                    # Query latency quantiles
                    {
                        "record": "job:k0_query_latency_seconds:p50:5m",
                        "expr": (
                            "histogram_quantile(0.50, "
                            "sum(rate(k0_kernel_http_request_latency_seconds_bucket{"
                            'route="/k0/query.execute"}[5m])) by (le))'
                        ),
                    },
                    {
                        "record": "job:k0_query_latency_seconds:p95:5m",
                        "expr": (
                            "histogram_quantile(0.95, "
                            "sum(rate(k0_kernel_http_request_latency_seconds_bucket{"
                            'route="/k0/query.execute"}[5m])) by (le))'
                        ),
                    },
                    {
                        "record": "job:k0_query_latency_seconds:p99:5m",
                        "expr": (
                            "histogram_quantile(0.99, "
                            "sum(rate(k0_kernel_http_request_latency_seconds_bucket{"
                            'route="/k0/query.execute"}[5m])) by (le))'
                        ),
                    },
                    # Generic HTTP latency by route
                    {
                        "record": "job:k0_http_request_latency_seconds:p95:5m",
                        "expr": (
                            "histogram_quantile(0.95, "
                            "sum by (route, le) (rate(k0_kernel_http_request_latency_seconds_bucket[5m])))"
                        ),
                    },
                ],
            },
            # HTTP Availability Recording Rules
            {
                "name": "k0-sli-availability-recording",
                "interval": "15s",
                "rules": [
                    # Overall API availability (non-5xx rate)
                    {
                        "record": "job:k0_api_availability:ratio5m",
                        "expr": (
                            "1 - ("
                            'sum(rate(k0_kernel_http_requests_total{status=~"5.."}[5m])) '
                            "/ "
                            "sum(rate(k0_kernel_http_requests_total[5m]))"
                            ")"
                        ),
                    },
                    # Availability by route
                    {
                        "record": "job:k0_api_availability_by_route:ratio5m",
                        "expr": (
                            "1 - ("
                            'sum by (route) (rate(k0_kernel_http_requests_total{status=~"5.."}[5m])) '
                            "/ "
                            "sum by (route) (rate(k0_kernel_http_requests_total[5m]))"
                            ")"
                        ),
                    },
                    # Success rate (2xx+3xx) by route
                    {
                        "record": "job:k0_http_success_rate_by_route:ratio5m",
                        "expr": (
                            'sum by (route) (rate(k0_kernel_http_requests_total{status=~"[23].."}[5m])) '
                            "/ "
                            "sum by (route) (rate(k0_kernel_http_requests_total[5m]))"
                        ),
                    },
                ],
            },
            # Throughput Recording Rules (RED: Rate)
            {
                "name": "k0-sli-throughput-recording",
                "interval": "15s",
                "rules": [
                    # Request rate by route
                    {
                        "record": "job:k0_http_requests:rate5m",
                        "expr": "sum by (route, method, status) (rate(k0_kernel_http_requests_total[5m]))",
                    },
                    # Command submission rate
                    {
                        "record": "job:k0_command_submissions:rate5m",
                        "expr": 'sum(rate(k0_kernel_http_requests_total{route="/k0/command.submit"}[5m]))',
                    },
                    # Query execution rate
                    {
                        "record": "job:k0_query_executions:rate5m",
                        "expr": 'sum(rate(k0_kernel_http_requests_total{route="/k0/query.execute"}[5m]))',
                    },
                    # Replay throughput (events/sec)
                    {
                        "record": "job:k0_replay_throughput:rate5m",
                        "expr": "rate(k0_kernel_replay_processed_total[5m])",
                    },
                ],
            },
            # Error Budget Recording Rules
            {
                "name": "k0-sli-error-budget-recording",
                "interval": "60s",
                "rules": [
                    # Error budget remaining (1h window)
                    {
                        "record": "job:k0_error_budget_remaining:ratio1h",
                        "expr": (
                            f"1 - ("
                            f"(1 - job:k0_api_availability:ratio5m) "
                            f"/ "
                            f'(1 - {SLO_TARGETS["api_availability_percent"] / 100})'
                            f")"
                        ),
                    },
                    # Error budget burn rate (1h window)
                    {
                        "record": "job:k0_error_budget_burn_rate:ratio1h",
                        "expr": (
                            f"((1 - job:k0_api_availability:ratio5m) "
                            f"/ "
                            f'(1 - {SLO_TARGETS["api_availability_percent"] / 100}))'
                        ),
                    },
                    # Latency budget compliance (command p95)
                    {
                        "record": "job:k0_command_latency_budget_compliance:ratio5m",
                        "expr": (
                            f"clamp_max("
                            f"job:k0_command_latency_seconds:p95:5m * 1000 "
                            f'/ {SLO_TARGETS["command_latency_p95_ms"]}, '
                            f"10)"  # Cap at 10x over budget
                        ),
                    },
                ],
            },
            # Storage & Durability Recording Rules
            {
                "name": "k0-sli-storage-recording",
                "interval": "30s",
                "rules": [
                    # WAL commit rate
                    {
                        "record": "job:k0_wal_commits:rate5m",
                        "expr": "rate(k0_kernel_k0_uow_commit_total{outcome='success'}[5m])",
                    },
                    # WAL fsync duration p95
                    {
                        "record": "job:k0_wal_fsync_duration_seconds:p95:5m",
                        "expr": (
                            "rate(k0_kernel_k0_uow_wal_fsync_seconds_total{outcome='success'}[5m]) "
                            "/ "
                            "rate(k0_kernel_k0_uow_wal_fsync_total{outcome='success'}[5m])"
                        ),
                    },
                    # Outbox pending ratio
                    {
                        "record": "job:k0_outbox_pending:ratio",
                        "expr": "sum(k0_kernel_outbox_pending_total) by (driver)",
                    },
                ],
            },
        ],
    }

    return rules


def get_recording_rule_usage_guide() -> dict[str, str]:
    """Return mapping of recording rules to their dashboard usage.

    This helps dashboard authors know which recording rules to use.
    """
    return {
        # Latency dashboards
        "job:k0_command_latency_seconds:p95:5m": "Command Latency dashboard, Command SLO panel",
        "job:k0_query_latency_seconds:p95:5m": "Query Latency dashboard, Query SLO panel",
        "job:k0_http_request_latency_seconds:p95:5m": "Kernel Overview dashboard, Latency heatmap",
        # Availability dashboards
        "job:k0_api_availability:ratio5m": "Kernel Overview dashboard, Availability SLO panel",
        "job:k0_api_availability_by_route:ratio5m": "Kernel Overview dashboard, Availability by route",
        "job:k0_http_success_rate_by_route:ratio5m": "Kernel Overview dashboard, Success rate gauge",
        # Throughput dashboards
        "job:k0_http_requests:rate5m": "Kernel Overview dashboard, Request rate panel",
        "job:k0_command_submissions:rate5m": "Command Latency dashboard, Submission rate stat",
        "job:k0_query_executions:rate5m": "Query Latency dashboard, Query rate stat",
        "job:k0_replay_throughput:rate5m": "Replay Throughput dashboard, Throughput timeseries",
        # Error budget dashboards
        "job:k0_error_budget_remaining:ratio1h": "Kernel Overview dashboard, Error budget gauge",
        "job:k0_error_budget_burn_rate:ratio1h": "Kernel Overview dashboard, Burn rate alert panel",
        "job:k0_command_latency_budget_compliance:ratio5m": "Command Latency dashboard, Budget compliance",
        # Storage dashboards
        "job:k0_wal_commits:rate5m": "Storage dashboard, WAL commit rate",
        "job:k0_wal_fsync_duration_seconds:p95:5m": "Storage dashboard, Fsync latency",
        "job:k0_outbox_pending:ratio": "Outbox dashboard, Pending messages",
    }
