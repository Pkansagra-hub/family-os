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

import logging
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from k1.l5_infrastructure.config.schema_validator import (SchemaValidator,
                                                          ValidationError)

logger = logging.getLogger(__name__)


@dataclass
class ConfigLoadResult:
    """Result of config loading operation"""
    success: bool
    config_data: Optional[Dict[str, Any]] = None
    errors: List[ValidationError] = field(default_factory=list)
    latency_ms: float = 0.0


class ConfigLoader:
    """Load and manage K1 YAML configuration files

    Responsibilities:
    - Load YAML config files with environment variable substitution
    - Validate configs against JSON schemas
    - Support config merging (defaults + environment + local)
    - Thread-safe config access with atomic swaps
    - Hot reload support (via watchdog, see ADR-0080)

    Performance: <50ms load P95, <100ms hot reload P95

    Example:
        loader = ConfigLoader(config_dir="k1/config")
        result = loader.load_config("kernel")
        if result.success:
            config = result.config_data
            print(f"Loaded kernel config in {result.latency_ms:.2f}ms")
    """

    def __init__(
        self,
        config_dir: Optional[str] = None,
        schema_validator: Optional[SchemaValidator] = None
    ):
        """Initialize config loader

        Args:
            config_dir: Directory containing YAML configs (default: k1/config)
            schema_validator: Schema validator instance (default: create new)
        """
        if config_dir is None:
            # Default to k1/config
            repo_root = Path(__file__).resolve().parents[3]
            self.config_dir = repo_root / "k1" / "config"
        else:
            self.config_dir = Path(config_dir)

        # Schema validator
        self.validator = schema_validator or SchemaValidator()

        # Config cache (config_name -> config_data)
        self._configs: Dict[str, Dict[str, Any]] = {}
        self._config_lock = threading.RLock()

        # Callbacks for config changes
        self._callbacks: List[Callable[[str, Dict[str, Any]], None]] = []

        logger.info(
            "[ConfigLoader] Initialized",
            extra={'config_dir': str(self.config_dir)}
        )

    def load_config(self, config_name: str) -> ConfigLoadResult:
        """Load configuration from YAML file

        Args:
            config_name: Config name (kernel, logging, circuit_breaker, thermal, metrics)

        Returns:
            ConfigLoadResult with success status, config_data, errors, latency

        Performance: <50ms P95 (<30ms typical)
        """
        import time
        start_time = time.perf_counter()

        try:
            # Find config file (try .yaml, then .yml)
            config_file = self._find_config_file(config_name)
            if config_file is None:
                return ConfigLoadResult(
                    success=False,
                    errors=[ValidationError(
                        path="",
                        message=f"Config file not found: {config_name}.yaml or {config_name}.yml",
                        expected="YAML file in config directory",
                        actual=f"{self.config_dir}/{config_name}.yaml"
                    )]
                )

            # Read and parse YAML
            raw_yaml = self._read_yaml_file(config_file)
            if raw_yaml is None:
                return ConfigLoadResult(
                    success=False,
                    errors=[ValidationError(
                        path="",
                        message=f"Failed to read YAML file: {config_file}",
                        expected="Valid YAML file",
                        actual=str(config_file)
                    )]
                )

            # Environment variable substitution
            config_data = self._substitute_env_vars(raw_yaml)

            # Schema validation
            validation_errors = self.validator.validate(config_name, config_data)
            if validation_errors:
                return ConfigLoadResult(
                    success=False,
                    config_data=config_data,  # Return data even on validation failure for debugging
                    errors=validation_errors,
                    latency_ms=(time.perf_counter() - start_time) * 1000
                )

            # Cache config (thread-safe)
            with self._config_lock:
                self._configs[config_name] = config_data

            latency_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "[ConfigLoader] Config loaded",
                extra={'config_name': config_name, 'latency_ms': f"{latency_ms:.2f}"}
            )

            return ConfigLoadResult(
                success=True,
                config_data=config_data,
                latency_ms=latency_ms
            )

        except Exception as e:
            logger.error(
                "[ConfigLoader] Config load failed",
                extra={'config_name': config_name, 'error': str(e)}
            )
            return ConfigLoadResult(
                success=False,
                errors=[ValidationError(
                    path="",
                    message=f"Unexpected error loading config: {str(e)}",
                    expected="Valid config file",
                    actual=str(e)
                )],
                latency_ms=(time.perf_counter() - start_time) * 1000
            )

    def get_config(self, config_name: str) -> Optional[Dict[str, Any]]:
        """Get cached config (thread-safe)

        Args:
            config_name: Config name

        Returns:
            Config data dict or None if not loaded
        """
        with self._config_lock:
            return self._configs.get(config_name)

    def reload_config(self, config_name: str) -> ConfigLoadResult:
        """Reload configuration from disk (hot reload)

        Args:
            config_name: Config name to reload

        Returns:
            ConfigLoadResult with success status

        Performance: <100ms P95 (<80ms typical)
        """
        import time
        start_time = time.perf_counter()

        logger.info(
            "[ConfigLoader] Reloading config",
            extra={'config_name': config_name}
        )

        # Load new config
        result = self.load_config(config_name)

        if result.success:
            # Notify callbacks
            config_data = result.config_data
            if config_data is not None:  # Type guard for mypy
                for callback in self._callbacks:
                    try:
                        callback(config_name, config_data)
                    except Exception as e:
                        logger.error(
                            "[ConfigLoader] Callback failed",
                            extra={'config_name': config_name, 'error': str(e)}
                        )

            result.latency_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "[ConfigLoader] Config reloaded",
                extra={'config_name': config_name, 'latency_ms': f"{result.latency_ms:.2f}"}
            )
        else:
            logger.warning(
                "[ConfigLoader] Config reload failed (rollback to cached)",
                extra={'config_name': config_name, 'num_errors': len(result.errors)}
            )

        return result

    def register_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """Register callback for config changes

        Args:
            callback: Function(config_name, config_data) -> None
        """
        self._callbacks.append(callback)
        logger.debug(
            "[ConfigLoader] Callback registered",
            extra={'num_callbacks': len(self._callbacks)}
        )

    def _find_config_file(self, config_name: str) -> Optional[Path]:
        """Find config file (.yaml or .yml)"""
        yaml_path = self.config_dir / f"{config_name}.yaml"
        yml_path = self.config_dir / f"{config_name}.yml"

        if yaml_path.exists():
            return yaml_path
        elif yml_path.exists():
            return yml_path
        else:
            return None

    def _read_yaml_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Read and parse YAML file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not isinstance(data, dict):
                logger.error(
                    "[ConfigLoader] YAML file must contain dictionary",
                    extra={'file_path': str(file_path), 'type': type(data).__name__}
                )
                return None

            return data

        except yaml.YAMLError as e:
            logger.error(
                "[ConfigLoader] YAML parse error",
                extra={'file_path': str(file_path), 'error': str(e)}
            )
            return None
        except Exception as e:
            logger.error(
                "[ConfigLoader] File read error",
                extra={'file_path': str(file_path), 'error': str(e)}
            )
            return None

    def _substitute_env_vars(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively substitute environment variables in config

        Syntax: ${ENV_VAR} or ${ENV_VAR:default_value}

        Args:
            config_data: Config dictionary

        Returns:
            Config with environment variables substituted
        """
        if isinstance(config_data, dict):
            return {
                key: self._substitute_env_vars(value)
                for key, value in config_data.items()
            }
        elif isinstance(config_data, list):
            return [self._substitute_env_vars(item) for item in config_data]
        elif isinstance(config_data, str):
            # Pattern: ${ENV_VAR} or ${ENV_VAR:default}
            pattern = r'\$\{([A-Z_][A-Z0-9_]*)(?::([^}]*))?\}'

            def replace_env_var(match):
                env_var = match.group(1)
                default_value = match.group(2)

                value = os.environ.get(env_var)

                if value is not None:
                    return value
                elif default_value is not None:
                    return default_value
                else:
                    logger.warning(
                        "[ConfigLoader] Environment variable not set (no default)",
                        extra={'env_var': env_var}
                    )
                    return match.group(0)  # Keep original ${ENV_VAR}

            return re.sub(pattern, replace_env_var, config_data)
        else:
            return config_data
            return config_data
            return re.sub(pattern, replace_env_var, config_data)
        else:
            return config_data
