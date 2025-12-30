"""Tests for k0.kernel.config - Runtime configuration models and loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from k0.kernel.config import (
    CONFIG_ENV_VAR,
    ENV_PREFIX,
    BusMiddlewareSettings,
    BusSettings,
    ChaosSettings,
    DatabaseSettings,
    KernelSettings,
    PolicySettings,
    PostgreSQLSettings,
    QoSSettings,
    RetentionPolicy,
    RetentionSettings,
    SecuritySettings,
    ServerSettings,
    TelemetrySettings,
    _assign_nested,
    _coerce_env_value,
    _deep_merge,
    _extract_env_overrides,
    _resolve_config_path,
)


class TestTelemetrySettings:
    """Tests for TelemetrySettings model."""

    def test_default_values(self) -> None:
        """TelemetrySettings should have sensible defaults."""
        settings = TelemetrySettings()
        assert settings.otlp_endpoint is None
        assert settings.otlp_headers == {}
        assert settings.trace_sample_ratio == 1.0
        assert settings.prometheus_enabled is True
        assert settings.metrics_namespace == "k0_kernel"
        assert settings.log_sensitive_keys == []
        assert settings.log_mask == "[REDACTED]"

    def test_otlp_endpoint_normalization(self) -> None:
        """otlp_endpoint should be normalized (stripped)."""
        settings = TelemetrySettings(otlp_endpoint="  http://otlp.local  ")
        assert settings.otlp_endpoint == "http://otlp.local"

    def test_otlp_endpoint_empty_string_becomes_none(self) -> None:
        """Empty otlp_endpoint string should become None."""
        settings = TelemetrySettings(otlp_endpoint="   ")
        assert settings.otlp_endpoint is None

    def test_metrics_namespace_cannot_be_empty(self) -> None:
        """metrics_namespace must not be empty."""
        with pytest.raises(ValueError, match="metrics_namespace"):
            TelemetrySettings(metrics_namespace="   ")

    def test_log_sensitive_keys_normalized(self) -> None:
        """log_sensitive_keys should be stripped and lowercased."""
        settings = TelemetrySettings(log_sensitive_keys=["  PASSWORD  ", " API_KEY "])
        assert settings.log_sensitive_keys == ["password", "api_key"]

    def test_log_mask_cannot_be_empty(self) -> None:
        """log_mask must not be empty."""
        with pytest.raises(ValueError, match="log_mask"):
            TelemetrySettings(log_mask="   ")

    def test_trace_sample_ratio_bounds(self) -> None:
        """trace_sample_ratio must be between 0 and 1."""
        TelemetrySettings(trace_sample_ratio=0.0)  # Valid
        TelemetrySettings(trace_sample_ratio=1.0)  # Valid
        with pytest.raises(ValueError):
            TelemetrySettings(trace_sample_ratio=-0.1)
        with pytest.raises(ValueError):
            TelemetrySettings(trace_sample_ratio=1.1)


class TestQoSSettings:
    """Tests for QoSSettings model."""

    def test_default_values(self) -> None:
        """QoSSettings should have sensible defaults."""
        settings = QoSSettings()
        assert settings.fanout_max == 3
        assert settings.top_k_max == 8
        assert settings.scheduler_profile == "balanced"

    def test_fanout_max_bounds(self) -> None:
        """fanout_max must be between 1 and 16."""
        QoSSettings(fanout_max=1)  # Valid
        QoSSettings(fanout_max=16)  # Valid
        with pytest.raises(ValueError):
            QoSSettings(fanout_max=0)
        with pytest.raises(ValueError):
            QoSSettings(fanout_max=17)

    def test_top_k_max_bounds(self) -> None:
        """top_k_max must be between 1 and 128."""
        QoSSettings(top_k_max=1)  # Valid
        QoSSettings(top_k_max=128)  # Valid
        with pytest.raises(ValueError):
            QoSSettings(top_k_max=0)
        with pytest.raises(ValueError):
            QoSSettings(top_k_max=129)

    def test_scheduler_profile_stripped(self) -> None:
        """scheduler_profile should be stripped."""
        settings = QoSSettings(scheduler_profile="  balanced  ")
        assert settings.scheduler_profile == "balanced"

    def test_scheduler_profile_cannot_be_empty(self) -> None:
        """scheduler_profile must not be empty."""
        with pytest.raises(ValueError, match="scheduler_profile"):
            QoSSettings(scheduler_profile="   ")


class TestRetentionPolicy:
    """Tests for RetentionPolicy model."""

    def test_default_values(self) -> None:
        """RetentionPolicy should have sensible defaults."""
        policy = RetentionPolicy()
        assert policy.wal_days == 7
        assert policy.wal_max_events == 10_000_000

    def test_wal_days_bounds(self) -> None:
        """wal_days must be between 1 and 365."""
        RetentionPolicy(wal_days=1)  # Valid
        RetentionPolicy(wal_days=365)  # Valid
        with pytest.raises(ValueError):
            RetentionPolicy(wal_days=0)
        with pytest.raises(ValueError):
            RetentionPolicy(wal_days=366)

    def test_wal_max_events_minimum(self) -> None:
        """wal_max_events must be at least 1."""
        RetentionPolicy(wal_max_events=1)  # Valid
        with pytest.raises(ValueError):
            RetentionPolicy(wal_max_events=0)


class TestRetentionSettings:
    """Tests for RetentionSettings model."""

    def test_default_values(self) -> None:
        """RetentionSettings should have default policy."""
        settings = RetentionSettings()
        assert isinstance(settings.default, RetentionPolicy)
        assert settings.topics == {}
        assert settings.spaces == {}

    def test_custom_topic_policy(self) -> None:
        """RetentionSettings should support topic-specific policies."""
        settings = RetentionSettings(topics={"events": RetentionPolicy(wal_days=30)})
        assert settings.topics["events"].wal_days == 30


class TestPostgreSQLSettings:
    """Tests for PostgreSQLSettings model."""

    def test_default_values(self) -> None:
        """PostgreSQLSettings should have sensible defaults."""
        settings = PostgreSQLSettings()
        assert settings.host == "localhost"
        assert settings.port == 5432
        assert settings.database == "k0_kernel"
        assert settings.user == "k0user"
        assert settings.password == "changeme"

    def test_port_bounds(self) -> None:
        """port must be between 1 and 65535."""
        PostgreSQLSettings(port=1)  # Valid
        PostgreSQLSettings(port=65535)  # Valid
        with pytest.raises(ValueError):
            PostgreSQLSettings(port=0)
        with pytest.raises(ValueError):
            PostgreSQLSettings(port=65536)


class TestDatabaseSettings:
    """Tests for DatabaseSettings model."""

    def test_default_values(self) -> None:
        """DatabaseSettings should use SQLite by default."""
        settings = DatabaseSettings()
        assert settings.backend == "sqlite"
        assert settings.path == Path("k0_runtime.sqlite3")
        assert settings.fsync_mode == "wal_only"
        assert settings.postgresql is None

    def test_backend_must_be_valid(self) -> None:
        """backend must be either 'sqlite' or 'postgresql'."""
        DatabaseSettings(backend="sqlite")  # Valid
        DatabaseSettings(backend="postgresql")  # Valid
        with pytest.raises(ValueError):
            DatabaseSettings(backend="mysql")  # type: ignore

    def test_fsync_mode_values(self) -> None:
        """fsync_mode must be one of allowed literal values."""
        DatabaseSettings(fsync_mode="strict")  # Valid
        DatabaseSettings(fsync_mode="wal_only")  # Valid
        DatabaseSettings(fsync_mode="disabled")  # Valid

    def test_fsync_mode_invalid(self) -> None:
        """fsync_mode must be one of allowed values."""
        with pytest.raises(ValueError):
            DatabaseSettings(fsync_mode="invalid")  # type: ignore


class TestServerSettings:
    """Tests for ServerSettings model."""

    def test_default_values(self) -> None:
        """ServerSettings should have sensible defaults."""
        settings = ServerSettings()
        assert settings.host == "0.0.0.0"
        assert settings.port == 8080
        assert settings.log_level == "info"
        assert settings.timeout_graceful_shutdown == 30.0

    def test_port_bounds(self) -> None:
        """port must be between 1 and 65535."""
        ServerSettings(port=1)  # Valid
        ServerSettings(port=65535)  # Valid
        with pytest.raises(ValueError):
            ServerSettings(port=0)
        with pytest.raises(ValueError):
            ServerSettings(port=65536)

    def test_host_cannot_be_empty(self) -> None:
        """host must not be empty."""
        with pytest.raises(ValueError, match="host"):
            ServerSettings(host="   ")

    def test_log_level_normalized(self) -> None:
        """log_level should be normalized to lowercase."""
        settings = ServerSettings(log_level="  INFO  ")
        assert settings.log_level == "info"

    def test_log_level_must_be_valid(self) -> None:
        """log_level must be one of allowed values."""
        for level in ["critical", "error", "warning", "info", "debug", "trace"]:
            ServerSettings(log_level=level)  # All valid
        with pytest.raises(ValueError, match="log_level"):
            ServerSettings(log_level="invalid")

    def test_timeout_graceful_shutdown_bounds(self) -> None:
        """timeout_graceful_shutdown must be between 0 and 300."""
        ServerSettings(timeout_graceful_shutdown=0.0)  # Valid
        ServerSettings(timeout_graceful_shutdown=300.0)  # Valid
        with pytest.raises(ValueError):
            ServerSettings(timeout_graceful_shutdown=-1.0)
        with pytest.raises(ValueError):
            ServerSettings(timeout_graceful_shutdown=301.0)


class TestSecuritySettings:
    """Tests for SecuritySettings model."""

    def test_default_values(self) -> None:
        """SecuritySettings should have sensible defaults."""
        settings = SecuritySettings()
        assert settings.key_rotation_grace_window_hours == 24
        assert settings.key_rotation_max_grace_hours == 168

    def test_grace_window_bounds(self) -> None:
        """key_rotation_grace_window_hours must be between 1 and 168."""
        SecuritySettings(key_rotation_grace_window_hours=1)  # Valid
        SecuritySettings(key_rotation_grace_window_hours=168)  # Valid
        with pytest.raises(ValueError):
            SecuritySettings(key_rotation_grace_window_hours=0)
        with pytest.raises(ValueError):
            SecuritySettings(key_rotation_grace_window_hours=169)

    def test_max_grace_bounds(self) -> None:
        """key_rotation_max_grace_hours must be between 1 and 720."""
        SecuritySettings(key_rotation_max_grace_hours=1)  # Valid
        SecuritySettings(key_rotation_max_grace_hours=720)  # Valid
        with pytest.raises(ValueError):
            SecuritySettings(key_rotation_max_grace_hours=0)
        with pytest.raises(ValueError):
            SecuritySettings(key_rotation_max_grace_hours=721)


class TestChaosSettings:
    """Tests for ChaosSettings model."""

    def test_default_values(self) -> None:
        """ChaosSettings should be disabled by default."""
        settings = ChaosSettings()
        assert settings.enabled is False
        assert settings.wal_fsync_fail_rate == 0.0
        assert settings.scheduler_starvation_multiplier == 1.0
        assert settings.network_latency_ms == 0
        assert settings.telemetry_outage_rate == 0.0
        assert settings.random_seed is None

    def test_wal_fsync_fail_rate_bounds(self) -> None:
        """wal_fsync_fail_rate must be between 0 and 1."""
        ChaosSettings(wal_fsync_fail_rate=0.0)  # Valid
        ChaosSettings(wal_fsync_fail_rate=1.0)  # Valid
        with pytest.raises(ValueError):
            ChaosSettings(wal_fsync_fail_rate=-0.1)
        with pytest.raises(ValueError):
            ChaosSettings(wal_fsync_fail_rate=1.1)

    def test_scheduler_starvation_bounds(self) -> None:
        """scheduler_starvation_multiplier must be between 0 and 1."""
        ChaosSettings(scheduler_starvation_multiplier=0.0)  # Valid
        ChaosSettings(scheduler_starvation_multiplier=1.0)  # Valid
        with pytest.raises(ValueError):
            ChaosSettings(scheduler_starvation_multiplier=-0.1)
        with pytest.raises(ValueError):
            ChaosSettings(scheduler_starvation_multiplier=1.1)

    def test_telemetry_outage_rate_bounds(self) -> None:
        """telemetry_outage_rate must be between 0 and 1."""
        ChaosSettings(telemetry_outage_rate=0.0)  # Valid
        ChaosSettings(telemetry_outage_rate=1.0)  # Valid
        with pytest.raises(ValueError):
            ChaosSettings(telemetry_outage_rate=-0.1)
        with pytest.raises(ValueError):
            ChaosSettings(telemetry_outage_rate=1.1)


class TestBusMiddlewareSettings:
    """Tests for BusMiddlewareSettings model."""

    def test_default_values(self) -> None:
        """BusMiddlewareSettings should enable all middleware by default."""
        settings = BusMiddlewareSettings()
        assert settings.timestamps_enabled is True
        assert settings.tracing_enabled is True
        assert settings.metrics_enabled is True

    def test_can_disable_middleware(self) -> None:
        """Individual middleware can be disabled."""
        settings = BusMiddlewareSettings(
            timestamps_enabled=False,
            tracing_enabled=False,
            metrics_enabled=False,
        )
        assert settings.timestamps_enabled is False
        assert settings.tracing_enabled is False
        assert settings.metrics_enabled is False


class TestBusSettings:
    """Tests for BusSettings model."""

    def test_default_values(self) -> None:
        """BusSettings should have middleware defaults."""
        settings = BusSettings()
        assert isinstance(settings.middleware, BusMiddlewareSettings)


class TestPolicySettings:
    """Tests for PolicySettings model."""

    def test_default_values(self) -> None:
        """PolicySettings should have None paths by default."""
        settings = PolicySettings()
        assert settings.manifest_path is None
        assert settings.bridge_policy_contract_path is None

    def test_with_paths(self) -> None:
        """PolicySettings should accept Path values."""
        settings = PolicySettings(
            manifest_path=Path("/etc/policy/manifest.yaml"),
            bridge_policy_contract_path=Path("/etc/policy/contract.yaml"),
        )
        assert settings.manifest_path == Path("/etc/policy/manifest.yaml")
        assert settings.bridge_policy_contract_path == Path("/etc/policy/contract.yaml")


class TestKernelSettings:
    """Tests for KernelSettings aggregate model."""

    def test_default_values(self) -> None:
        """KernelSettings should have sensible defaults."""
        settings = KernelSettings()
        assert settings.version == "0.0.0-dev"
        assert settings.environment == "development"
        assert settings.config_file is None
        assert isinstance(settings.telemetry, TelemetrySettings)
        assert isinstance(settings.qos, QoSSettings)
        assert isinstance(settings.database, DatabaseSettings)
        assert isinstance(settings.server, ServerSettings)
        assert isinstance(settings.security, SecuritySettings)
        assert isinstance(settings.chaos, ChaosSettings)
        assert isinstance(settings.bus, BusSettings)
        assert isinstance(settings.policy, PolicySettings)

    def test_environment_normalized(self) -> None:
        """environment should be stripped."""
        settings = KernelSettings(environment="  production  ")
        assert settings.environment == "production"

    def test_environment_cannot_be_empty(self) -> None:
        """environment must not be empty."""
        with pytest.raises(ValueError, match="environment"):
            KernelSettings(environment="   ")

    def test_default_method(self) -> None:
        """KernelSettings.default() should return settings instance."""
        settings = KernelSettings.default()
        assert isinstance(settings, KernelSettings)


class TestDeepMerge:
    """Tests for _deep_merge helper function."""

    def test_simple_merge(self) -> None:
        """Simple key-value pairs should be merged."""
        base = {"a": 1, "b": 2}
        update = {"b": 3, "c": 4}
        result = _deep_merge(base, update)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self) -> None:
        """Nested dicts should be recursively merged."""
        base: dict[str, Any] = {"server": {"host": "localhost", "port": 8080}}
        update: dict[str, Any] = {"server": {"port": 9090}}
        result = _deep_merge(base, update)
        assert result == {"server": {"host": "localhost", "port": 9090}}

    def test_non_dict_overrides_dict(self) -> None:
        """Non-dict value should replace dict value."""
        base: dict[str, Any] = {"server": {"host": "localhost"}}
        update: dict[str, Any] = {"server": "string_value"}
        result = _deep_merge(base, update)
        assert result == {"server": "string_value"}

    def test_dict_overrides_non_dict(self) -> None:
        """Dict value should replace non-dict value."""
        base: dict[str, Any] = {"server": "string_value"}
        update: dict[str, Any] = {"server": {"host": "localhost"}}
        result = _deep_merge(base, update)
        assert result == {"server": {"host": "localhost"}}


class TestAssignNested:
    """Tests for _assign_nested helper function."""

    def test_single_level(self) -> None:
        """Single-level path should set value directly."""
        target: dict[str, Any] = {}
        _assign_nested(target, ["key"], "value")
        assert target == {"key": "value"}

    def test_multi_level(self) -> None:
        """Multi-level path should create nested structure."""
        target: dict[str, Any] = {}
        _assign_nested(target, ["server", "port"], 8080)
        assert target == {"server": {"port": 8080}}

    def test_deep_nested(self) -> None:
        """Deep nesting should work correctly."""
        target: dict[str, Any] = {}
        _assign_nested(target, ["a", "b", "c", "d"], "value")
        assert target == {"a": {"b": {"c": {"d": "value"}}}}


class TestCoerceEnvValue:
    """Tests for _coerce_env_value helper function."""

    def test_empty_string(self) -> None:
        """Empty string should return empty string."""
        assert _coerce_env_value("   ") == ""

    def test_integer(self) -> None:
        """Integer strings should be coerced to int."""
        assert _coerce_env_value("42") == 42

    def test_float(self) -> None:
        """Float strings should be coerced to float."""
        assert _coerce_env_value("3.14") == 3.14

    def test_boolean_true(self) -> None:
        """'true' should be coerced to True."""
        assert _coerce_env_value("true") is True

    def test_boolean_false(self) -> None:
        """'false' should be coerced to False."""
        assert _coerce_env_value("false") is False

    def test_comma_separated_list(self) -> None:
        """Comma-separated values should become a list."""
        result = _coerce_env_value("a, b, c")
        assert result == ["a", "b", "c"]

    def test_plain_string(self) -> None:
        """Plain strings should remain strings."""
        assert _coerce_env_value("hello_world") == "hello_world"


class TestExtractEnvOverrides:
    """Tests for _extract_env_overrides helper function."""

    def test_single_level_override(self) -> None:
        """K0_KERNEL_VERSION should set version."""
        env = {f"{ENV_PREFIX}VERSION": "1.0.0"}
        result = _extract_env_overrides(env)
        assert result == {"version": "1.0.0"}

    def test_nested_override(self) -> None:
        """K0_KERNEL_SERVER__PORT should set server.port."""
        env = {f"{ENV_PREFIX}SERVER__PORT": "9090"}
        result = _extract_env_overrides(env)
        assert result == {"server": {"port": 9090}}

    def test_ignores_config_file_var(self) -> None:
        """CONFIG_ENV_VAR should be ignored."""
        env = {CONFIG_ENV_VAR: "/path/to/config.yaml"}
        result = _extract_env_overrides(env)
        assert result == {}

    def test_ignores_non_prefix_vars(self) -> None:
        """Non-K0_KERNEL_ vars should be ignored."""
        env = {"PATH": "/usr/bin", "HOME": "/home/user"}
        result = _extract_env_overrides(env)
        assert result == {}


class TestResolveConfigPath:
    """Tests for _resolve_config_path helper function."""

    def test_explicit_path_exists(self, tmp_path: Path) -> None:
        """Explicit path should be returned if it exists."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("version: '1.0.0'")

        result = _resolve_config_path(config_file, {})
        assert result == config_file

    def test_explicit_path_not_exists(self, tmp_path: Path) -> None:
        """FileNotFoundError should be raised if explicit path doesn't exist."""
        config_file = tmp_path / "nonexistent.yaml"

        with pytest.raises(FileNotFoundError):
            _resolve_config_path(config_file, {})

    def test_env_var_path_exists(self, tmp_path: Path) -> None:
        """Env var path should be used when no explicit path given."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("version: '1.0.0'")

        env = {CONFIG_ENV_VAR: str(config_file)}
        result = _resolve_config_path(None, env)
        assert result == config_file

    def test_env_var_path_not_exists(self, tmp_path: Path) -> None:
        """FileNotFoundError should be raised if env var path doesn't exist."""
        env = {CONFIG_ENV_VAR: str(tmp_path / "nonexistent.yaml")}

        with pytest.raises(FileNotFoundError):
            _resolve_config_path(None, env)


class TestKernelSettingsLoad:
    """Tests for KernelSettings.load() method."""

    def test_load_default(self) -> None:
        """load() with no args should return defaults."""
        # Temporarily ensure no config file exists
        with patch.object(Path, "exists", return_value=False):
            settings = KernelSettings.load()
        assert isinstance(settings, KernelSettings)

    def test_load_from_yaml(self, tmp_path: Path) -> None:
        """load() should parse YAML config file."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
version: "1.2.3"
environment: production
server:
  port: 9090
"""
        )

        settings = KernelSettings.load(config_path=config_file)
        assert settings.version == "1.2.3"
        assert settings.environment == "production"
        assert settings.server.port == 9090

    def test_load_with_env_overrides(self, tmp_path: Path) -> None:
        """load() should apply environment variable overrides."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
version: "1.0.0"
server:
  port: 8080
"""
        )

        env = {
            f"{ENV_PREFIX}SERVER__PORT": "9999",
        }

        settings = KernelSettings.load(config_path=config_file, env=env)
        assert settings.server.port == 9999  # Env override wins

    def test_load_with_programmatic_overrides(self, tmp_path: Path) -> None:
        """load() should apply programmatic overrides."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
version: "1.0.0"
"""
        )

        overrides = {"environment": "staging", "version": "2.0.0"}

        settings = KernelSettings.load(config_path=config_file, overrides=overrides)
        assert settings.environment == "staging"
        assert settings.version == "2.0.0"

    def test_from_yaml_convenience_method(self, tmp_path: Path) -> None:
        """from_yaml() should load from YAML file."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
version: "3.0.0"
"""
        )

        settings = KernelSettings.from_yaml(config_file)
        assert settings.version == "3.0.0"


class TestKernelSettingsExtraFieldsForbidden:
    """Tests for extra fields being forbidden (strict mode)."""

    def test_telemetry_forbids_extra(self) -> None:
        """TelemetrySettings should reject unknown fields."""
        with pytest.raises(ValueError):
            TelemetrySettings(unknown_field="value")  # type: ignore

    def test_qos_forbids_extra(self) -> None:
        """QoSSettings should reject unknown fields."""
        with pytest.raises(ValueError):
            QoSSettings(unknown_field="value")  # type: ignore

    def test_server_forbids_extra(self) -> None:
        """ServerSettings should reject unknown fields."""
        with pytest.raises(ValueError):
            ServerSettings(unknown_field="value")  # type: ignore

    def test_kernel_forbids_extra(self) -> None:
        """KernelSettings should reject unknown fields."""
        with pytest.raises(ValueError):
            KernelSettings(unknown_field="value")  # type: ignore
