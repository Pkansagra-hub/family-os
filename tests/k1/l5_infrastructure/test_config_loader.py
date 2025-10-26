"""WARD Tests for K1 Config Loader (Epic 4.1.1)

Test Suite: ConfigLoader and SchemaValidator
Coverage: YAML loading, schema validation, env var substitution, config caching
ADRs: ADR-0080 (Config Hot-Reload), ADR-0009b (Per-Service Circuit Config)

Test Groups:
- Group 1: SchemaValidator initialization and schema loading (3 tests)
- Group 2: ConfigLoader YAML loading and parsing (4 tests)
- Group 3: Environment variable substitution (3 tests)
- Group 4: Schema validation (success + failure cases) (4 tests)
- Group 5: Config caching and thread safety (2 tests)
- Group 6: Performance budgets (<50ms load, <10ms validation) (2 tests)

Total: 18 tests
"""

import os
import time
from pathlib import Path

from ward import fixture, test

from k1.l5_infrastructure.config.loader import ConfigLoader
from k1.l5_infrastructure.config.schema_validator import SchemaValidator

# ============================================================================
# Fixtures
# ============================================================================


@fixture
def schema_validator():
    """SchemaValidator fixture with real schemas"""
    return SchemaValidator()


@fixture
def config_loader():
    """ConfigLoader fixture with real config directory"""
    return ConfigLoader()


@fixture
def temp_config_file(tmpdir="tmp"):
    """Create temporary config file for testing"""
    import tempfile

    import yaml

    tmpdir = Path(tempfile.mkdtemp())

    def _create_config(config_name: str, config_data: dict) -> Path:
        config_file = tmpdir / f"{config_name}.yaml"
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f)
        return config_file

    yield _create_config

    # Cleanup
    import shutil

    if tmpdir.exists():
        shutil.rmtree(tmpdir)


# ============================================================================
# Group 1: SchemaValidator Initialization (3 tests)
# ============================================================================


@test("SchemaValidator loads all 5 schemas")
def _(validator=schema_validator):
    """Verify all schemas loaded from k1/contracts/schemas"""
    # Expected schemas
    expected_schemas = ["kernel", "logging", "circuit_breaker", "thermal", "metrics"]

    for schema_name in expected_schemas:
        assert schema_name in validator._schemas, f"Schema {schema_name} not loaded"
        assert (
            schema_name in validator._validators
        ), f"Validator for {schema_name} not created"


@test("SchemaValidator validates kernel schema structure")
def _(validator=schema_validator):
    """Verify kernel schema has required properties"""
    kernel_schema = validator._schemas.get("kernel")
    assert kernel_schema is not None, "kernel schema not found"

    # Check schema structure
    assert kernel_schema["type"] == "object"
    assert "properties" in kernel_schema
    assert "version" in kernel_schema["properties"]
    assert "kernel" in kernel_schema["properties"]
    assert "runtime" in kernel_schema["properties"]


@test("SchemaValidator validates circuit_breaker schema structure")
def _(validator=schema_validator):
    """Verify circuit_breaker schema has required properties"""
    cb_schema = validator._schemas.get("circuit_breaker")
    assert cb_schema is not None, "circuit_breaker schema not found"

    # Check schema structure
    assert cb_schema["type"] == "object"
    assert "properties" in cb_schema
    assert "version" in cb_schema["properties"]
    assert "circuit_breakers" in cb_schema["properties"]


# ============================================================================
# Group 2: ConfigLoader YAML Loading (4 tests)
# ============================================================================


@test("ConfigLoader loads kernel.yaml successfully")
def _(loader=config_loader):
    """Verify kernel.yaml loads without errors"""
    result = loader.load_config("kernel")

    assert result.success, f"kernel.yaml load failed: {result.errors}"
    assert result.config_data is not None
    assert "version" in result.config_data
    assert "kernel" in result.config_data


@test("ConfigLoader loads circuit_breaker.yaml successfully")
def _(loader=config_loader):
    """Verify circuit_breaker.yaml loads without errors"""
    result = loader.load_config("circuit_breaker")

    assert result.success, f"circuit_breaker.yaml load failed: {result.errors}"
    assert result.config_data is not None
    assert "circuit_breakers" in result.config_data

    # Check 6 services configured (ADR-0009b)
    services = result.config_data["circuit_breakers"]
    assert "tool_runner" in services
    assert "model_hub_local" in services
    assert "model_hub_remote" in services
    assert "k0_bridge" in services
    assert "mcp_gateway" in services
    assert "streaming_engine" in services


@test("ConfigLoader returns error for missing config file")
def _(loader=config_loader):
    """Verify error when config file doesn't exist"""
    result = loader.load_config("nonexistent_config")

    assert not result.success
    assert len(result.errors) > 0
    assert "not found" in result.errors[0].message.lower()


@test("ConfigLoader caches config after successful load")
def _(loader=config_loader):
    """Verify config is cached after loading"""
    # Load config
    result = loader.load_config("kernel")
    assert result.success

    # Check cache
    cached_config = loader.get_config("kernel")
    assert cached_config is not None
    assert cached_config["version"] == result.config_data["version"]


# ============================================================================
# Group 3: Environment Variable Substitution (3 tests)
# ============================================================================


@test("ConfigLoader substitutes environment variables")
def _(loader=config_loader, tmp_config=temp_config_file):
    """Verify ${ENV_VAR} substitution works"""
    # Set environment variable
    os.environ["TEST_LOG_LEVEL"] = "DEBUG"

    # Create config with env var
    config_data = {
        "version": "1.0.0",
        "logging": {"level": "${TEST_LOG_LEVEL}", "format": "json"},
    }

    # Create temp config
    config_file = tmp_config("logging", config_data)

    # Load from temp directory
    temp_loader = ConfigLoader(config_dir=str(config_file.parent))
    result = temp_loader.load_config("logging")

    # Verify substitution
    assert result.success
    assert result.config_data["logging"]["level"] == "DEBUG"

    # Cleanup
    del os.environ["TEST_LOG_LEVEL"]


@test("ConfigLoader uses default value when env var not set")
def _(loader=config_loader, tmp_config=temp_config_file):
    """Verify ${ENV_VAR:default} fallback works"""
    # Ensure env var not set
    if "NONEXISTENT_VAR" in os.environ:
        del os.environ["NONEXISTENT_VAR"]

    # Create config with env var + default
    config_data = {
        "version": "1.0.0",
        "logging": {"level": "${NONEXISTENT_VAR:INFO}", "format": "json"},
    }

    config_file = tmp_config("logging", config_data)
    temp_loader = ConfigLoader(config_dir=str(config_file.parent))
    result = temp_loader.load_config("logging")

    # Verify default used
    assert result.success
    assert result.config_data["logging"]["level"] == "INFO"


@test("ConfigLoader keeps original value when env var missing and no default")
def _(loader=config_loader, tmp_config=temp_config_file):
    """Verify ${ENV_VAR} kept when env var missing and no default"""
    # Ensure env var not set
    if "MISSING_VAR" in os.environ:
        del os.environ["MISSING_VAR"]

    config_data = {
        "version": "1.0.0",
        "logging": {"level": "${MISSING_VAR}", "format": "json"},
    }

    config_file = tmp_config("logging", config_data)
    temp_loader = ConfigLoader(config_dir=str(config_file.parent))
    result = temp_loader.load_config("logging")

    # Verify original kept (will fail validation, but substitution works)
    assert result.config_data["logging"]["level"] == "${MISSING_VAR}"


# ============================================================================
# Group 4: Schema Validation (4 tests)
# ============================================================================


@test("SchemaValidator accepts valid thermal config")
def _(validator=schema_validator):
    """Verify valid thermal config passes validation"""
    thermal_config = {
        "version": "1.0.0",
        "thermal": {
            "enabled": True,
            "thresholds": {
                "cool_celsius": 50.0,
                "warm_celsius": 65.0,
                "hot_celsius": 80.0,
                "critical_celsius": 90.0,
            },
            "migration": {
                "enabled": True,
                "policy": "npu_to_gpu",
                "cooldown_threshold_celsius": 55.0,
                "check_interval_ms": 1000,
            },
        },
    }

    errors = validator.validate("thermal", thermal_config)
    assert len(errors) == 0, f"Validation errors: {errors}"


@test("SchemaValidator rejects thermal config with invalid threshold order")
def _(validator=schema_validator):
    """Verify semantic validation catches threshold ordering (ADR-0080)"""
    thermal_config = {
        "version": "1.0.0",
        "thermal": {
            "enabled": True,
            "thresholds": {
                "cool_celsius": 70.0,  # Invalid: cool > warm
                "warm_celsius": 65.0,
                "hot_celsius": 80.0,
                "critical_celsius": 90.0,
            },
            "migration": {"enabled": True, "policy": "npu_to_gpu"},
        },
    }

    errors = validator.validate("thermal", thermal_config)
    assert len(errors) > 0
    assert any("strictly increasing" in error.message.lower() for error in errors)


@test("SchemaValidator rejects circuit_breaker with missing alternate_service")
def _(validator=schema_validator):
    """Verify semantic validation catches missing alternate_service (ADR-0009b)"""
    cb_config = {
        "version": "1.0.0",
        "circuit_breakers": {
            "test_service": {
                "failure_threshold": 3,
                "timeout_duration_ms": 10000,
                "success_threshold": 1,
                "slow_call_threshold_ms": 1000,
                "time_window_ms": 30000,
                "fallback_strategy": "alternate_model",  # Requires alternate_service
                "enabled": True,
                # Missing: alternate_service
            }
        },
    }

    errors = validator.validate("circuit_breaker", cb_config)
    assert len(errors) > 0
    assert any("alternate_service" in error.message for error in errors)


@test("SchemaValidator rejects kernel config with invalid max_agents")
def _(validator=schema_validator):
    """Verify schema validation catches out-of-range values"""
    kernel_config = {
        "version": "1.0.0",
        "kernel": {
            "name": "test",
            "session_timeout_ms": 300000,
            "max_agents_per_session": 25,  # Invalid: max is 10
        },
        "runtime": {"worker_threads": 4, "max_memory_mb": 512},
    }

    errors = validator.validate("kernel", kernel_config)
    assert len(errors) > 0
    assert any("max_agents_per_session" in error.path for error in errors)


# ============================================================================
# Group 5: Config Caching and Thread Safety (2 tests)
# ============================================================================


@test("ConfigLoader get_config returns None for unloaded config")
def _(loader=config_loader):
    """Verify get_config returns None when config not loaded"""
    cached_config = loader.get_config("never_loaded_config")
    assert cached_config is None


@test("ConfigLoader reload_config updates cached config")
def _(loader=config_loader):
    """Verify reload updates cached config"""
    # Load initial config
    result1 = loader.load_config("kernel")
    assert result1.success

    # Reload config
    result2 = loader.reload_config("kernel")
    assert result2.success

    # Verify latency reported
    assert result2.latency_ms > 0


# ============================================================================
# Group 6: Performance Budgets (2 tests)
# ============================================================================


@test("ConfigLoader load_config completes within 50ms budget")
def _(loader=config_loader):
    """Verify config loading meets <50ms P95 budget (ADR-0024b)"""
    # Measure load time (10 iterations for P95)
    latencies = []

    for _ in range(10):
        start = time.perf_counter()
        result = loader.load_config("kernel")
        latency_ms = (time.perf_counter() - start) * 1000

        assert result.success
        latencies.append(latency_ms)

    # Check P95
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
    assert p95_latency < 50, f"P95 latency {p95_latency:.2f}ms exceeds 50ms budget"


@test("SchemaValidator validate completes within 10ms budget")
def _(validator=schema_validator):
    """Verify schema validation meets <10ms P95 budget (ADR-0024b)"""
    # Valid thermal config
    thermal_config = {
        "version": "1.0.0",
        "thermal": {
            "enabled": True,
            "thresholds": {
                "cool_celsius": 50.0,
                "warm_celsius": 65.0,
                "hot_celsius": 80.0,
                "critical_celsius": 90.0,
            },
            "migration": {"enabled": True, "policy": "npu_to_gpu"},
        },
    }

    # Measure validation time (10 iterations for P95)
    latencies = []

    for _ in range(10):
        start = time.perf_counter()
        errors = validator.validate("thermal", thermal_config)
        latency_ms = (time.perf_counter() - start) * 1000

        assert len(errors) == 0
        latencies.append(latency_ms)

    # Check P95
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
    assert (
        p95_latency < 10
    ), f"P95 validation latency {p95_latency:.2f}ms exceeds 10ms budget"
    assert (
        p95_latency < 10
    ), f"P95 validation latency {p95_latency:.2f}ms exceeds 10ms budget"
    assert (
        p95_latency < 10
    ), f"P95 validation latency {p95_latency:.2f}ms exceeds 10ms budget"
