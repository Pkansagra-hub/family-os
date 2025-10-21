"""Performance testing and load scenario orchestration.

This module provides the infrastructure for running performance and load tests
against the k0 kernel. It includes:

- Scenario definition and validation via JSON schema
- YAML-based scenario configuration
- Prometheus Pushgateway integration for metrics collection
- Timeline and artifact generation for post-mortem analysis

Usage:
    python -m k0.perf.runner --scenario scenarios/command_burst.yaml
    python -m k0.perf.runner --scenario scenarios/sse_fanout.yaml --dry-run

See Also:
    - perf/README.md - Comprehensive usage documentation
    - perf/schema/scenario.schema.json - Scenario JSON schema
    - tests/performance/ - Ward-based validation tests
"""

from __future__ import annotations

__all__ = [
    "ScenarioRunner",
    "ScenarioConfig",
    "PushgatewayClient",
]

# Performance testing components will be imported here as they're implemented
