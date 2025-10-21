"""Layer 5: Infrastructure

Scheduling, backpressure, observability, configuration, K0 bridge.

Performance Budget: Config reload <100ms P95, Scheduler <1% CPU overhead

Module Categories:
- infrastructure/: Core infrastructure (7 modules) - Scheduler, backpressure, thermal, budgets, cache, rate limiting, storage
- safety/: Safety & policy (3 modules) - Policy enforcement, PII detection, arbiter
- observability/: Observability (4 modules) - Tracing, metrics, receipts, perf harness
- config/: Configuration (3 modules) - Global defaults, schemas, hot reload manager
- connectors/: Connectors (2 modules) - K0 bridge, Model Hub client
"""
