"""
YAML Configuration Loader

Purpose: Load and hot-reload YAML configuration files for K1
Location: k1/l5_infrastructure/config/loader.py
Performance: <50ms config load, <100ms hot reload

Primary ADRs:
- ADR-0009b: Hot Reload (config file monitoring)
- ADR-0080: Config Hot-Reload (change detection, validator, rollback)

Related ADRs:
- ADR-0024b: Component-Level Budgets (config reload <100ms)

Key Responsibilities:

1. Config Loading:
   - Load YAML config files (kernel.yaml, logging.yaml, circuit_breaker.yaml, thermal.yaml, metrics.yaml)
   - Validate schema (JSON Schema Draft 7 validation)
   - Merge configs (defaults + environment-specific overrides)
   - Environment variable substitution (${ENV_VAR} syntax)

2. Hot Reload (ADR-0080):
   - Detect config file changes (file watcher: inotify/FSEvents/ReadDirectoryChangesW)
   - Reload without restart (<100ms)
   - Zero-downtime config apply (atomic swap)
   - Atomic updates (all-or-nothing: validate all configs before applying)
   - Rollback on validation failure (revert to last known good config)

3. Config Files:
   - kernel.yaml: Core K1 configuration (agent limits, performance budgets)
   - logging.yaml: Logging configuration (levels, rotation, targets)
   - circuit_breaker.yaml: Circuit breaker settings (thresholds, cooldowns)
   - thermal.yaml: Thermal management settings (zones, hysteresis)
   - metrics.yaml: Metrics configuration (scrape interval, exporters)

4. Config Merging:
   - Defaults: Base configuration (hardcoded defaults)
   - Environment overrides: Environment-specific configs (dev/staging/prod)
   - Local overrides: Local config file (kernel.local.yaml, not in Git)
   - Merge order: Defaults < Environment < Local (later overrides earlier)

5. Environment Variable Substitution:
   - Syntax: ${ENV_VAR} or ${ENV_VAR:default_value}
   - Example: log_level: ${LOG_LEVEL:INFO}
   - Substitution at load time (before validation)

Performance Metrics:
- Config load: <50ms P95 (<30ms typical, startup)
- Hot reload: <100ms P95 (<80ms typical)
- Schema validation: <10ms P95
- File watch latency: <50ms (change detection to reload start)

Implementation Notes:
- Use PyYAML library for YAML parsing
- Use watchdog library for file watching (cross-platform)
- Use jsonschema library for schema validation
- Atomic config swap: Load new config → Validate → Swap pointer (lock-free)
- Config immutability: Configs are immutable after load (prevent race conditions)
- Thread-safe: Config access is thread-safe (read-write lock)

Example Usage:
    from k1.l5_infrastructure.config import ConfigLoader

    # Load config
    loader = ConfigLoader(config_dir="/etc/k1/config")
    config = loader.load()  # Returns: KernelConfig object

    # Access config
    max_agents = config.agent_fabric.max_agents_per_session  # 3
    log_level = config.logging.level  # "INFO"

    # Hot reload callback
    def on_config_change(new_config):
        print(f"Config reloaded: {new_config}")

    loader.register_callback(on_config_change)
    loader.start_watching()  # Start file watcher

Research Foundation:
- YAML configuration (human-readable, widely supported)
- File watching (inotify Linux, FSEvents macOS, ReadDirectoryChangesW Windows)
- Zero-downtime updates (blue-green config, atomic swaps)
- Config merging (layered configuration, override patterns)

TODO:
- [ ] Implement ConfigLoader class with PyYAML
- [ ] Implement YAML parsing with error handling
- [ ] Implement schema validation (delegate to SchemaValidator)
- [ ] Implement config merging (defaults + environment + local)
- [ ] Implement environment variable substitution (${ENV_VAR} syntax)
- [ ] Implement hot reload with watchdog file watcher
- [ ] Implement atomic config swap (validate → swap pointer)
- [ ] Implement rollback on validation failure
- [ ] Add callback registration for config change notifications
- [ ] Add thread-safe config access (read-write lock)
- [ ] Add unit tests for config loading and merging
- [ ] Add integration tests for hot reload
"""

# TODO: Implement ConfigLoader with hot-reload and schema validation
