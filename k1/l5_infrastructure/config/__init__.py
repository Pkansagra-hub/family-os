"""
Layer 5 - Configuration Module

This module provides YAML configuration loading, validation, and hot-reload
capabilities for K1 with zero-downtime updates.

Components:
- loader: YAML config loader with hot-reload
- schema_validator: JSON schema validation for config files

Configuration Files:
- kernel.yaml: Core K1 configuration
- logging.yaml: Logging configuration
- circuit_breaker.yaml: Circuit breaker settings
- thermal.yaml: Thermal management settings
- metrics.yaml: Metrics configuration

Hot Reload (ADR-0009b, ADR-0080):
- Detect config file changes (file watcher)
- Reload without restart (<100ms)
- Zero-downtime config apply
- Atomic updates (all-or-nothing)
- Rollback on validation failure

Configuration Loading:
- Load YAML config files
- Validate schema (JSON Schema Draft 7)
- Merge configs (defaults + overrides)
- Environment variable substitution

Performance (ADR-0024b):
- Config load: <50ms P95 (startup)
- Hot reload: <100ms P95
- Schema validation: <10ms P95

Primary ADRs:
- ADR-0009b: Hot Reload (config file monitoring)
- ADR-0080: Config Hot-Reload (change detection, validator, rollback)
- ADR-0024b: Component-Level Budgets (config reload <100ms)

Research Foundation:
- YAML configuration (human-readable, widely supported)
- JSON Schema validation (Draft 7, constraint validation)
- File watching (inotify, FSEvents, ReadDirectoryChangesW)
- Zero-downtime updates (blue-green config, atomic swaps)
"""

# __all__ = [
#     "ConfigLoader",
#     "SchemaValidator",
# ]
