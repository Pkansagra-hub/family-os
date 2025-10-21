"""Telemetry module for SLO dashboards, Prometheus rules, and Grafana preview stack.

This module provides:
- Jsonnet mixins for SLO dashboards (command/query/SSE latency, replay throughput, availability)
- Deterministic Grafana dashboard and Prometheus rule generation
- Preview stack orchestration for local development and validation
- Integration with the existing k0/obs/metrics.py exporter

Directory structure:
    k0/telemetry/
        __init__.py          - Package entry point
        render.py            - CLI for rendering dashboards and rules
        mixins/              - Jsonnet source files for dashboards and alerts
        generated/           - Rendered artifacts (dashboards/*.json, rules/*.yaml)
        preview/             - Docker Compose stack for Grafana + Prometheus
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
