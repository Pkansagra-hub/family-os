"""Ward tests for performance scenario validation.

These tests validate:
- Scenario YAML parsing and schema compliance
- ScenarioRunner dry-run execution
- Artifact contract enforcement
- Pushgateway client behavior
"""

from __future__ import annotations

from pathlib import Path

from ward import test  # type: ignore[attr-defined]

from k0.perf.runner import ScenarioConfig

SCENARIOS_DIR = Path(__file__).parent.parent.parent / "k0" / "perf" / "scenarios"


@test("scenario YAML files exist in expected location")
def _() -> None:
    """Verify scenario directory structure exists."""
    assert SCENARIOS_DIR.exists(), f"Scenarios directory not found: {SCENARIOS_DIR}"
    assert SCENARIOS_DIR.is_dir(), f"Scenarios path is not a directory: {SCENARIOS_DIR}"


@test("command_burst.yaml loads and validates")
def _() -> None:
    """Validate command burst scenario parses correctly."""
    scenario_path = SCENARIOS_DIR / "command_burst.yaml"
    assert scenario_path.exists(), f"Scenario not found: {scenario_path}"

    config = ScenarioConfig.from_yaml(scenario_path)

    assert config.name == "Command Burst Load Test"
    assert config.type == "burst"
    assert config.duration == 300
    assert len(config.phases) == 4
    assert "command" in config.tags

    # Validate phase durations sum to total
    total_phase_duration = sum(phase["duration"] for phase in config.phases)
    assert total_phase_duration == config.duration


@test("sse_fanout.yaml loads and validates")
def _() -> None:
    """Validate SSE fan-out scenario parses correctly."""
    scenario_path = SCENARIOS_DIR / "sse_fanout.yaml"
    assert scenario_path.exists(), f"Scenario not found: {scenario_path}"

    config = ScenarioConfig.from_yaml(scenario_path)

    assert config.name == "SSE Fan-out Stress Test"
    assert config.type == "sustained"
    assert config.duration == 600
    assert len(config.phases) == 4
    assert "sse" in config.tags

    total_phase_duration = sum(phase["duration"] for phase in config.phases)
    assert total_phase_duration == config.duration


@test("scheduler_starvation.yaml loads and validates")
def _() -> None:
    """Validate scheduler starvation scenario parses correctly."""
    scenario_path = SCENARIOS_DIR / "scheduler_starvation.yaml"
    assert scenario_path.exists(), f"Scenario not found: {scenario_path}"

    config = ScenarioConfig.from_yaml(scenario_path)

    assert config.name == "QoS Scheduler Starvation Test"
    assert config.type == "stress"
    assert config.duration == 180
    assert len(config.phases) == 2
    assert "qos" in config.tags

    total_phase_duration = sum(phase["duration"] for phase in config.phases)
    assert total_phase_duration == config.duration


@test("scenario validation catches phase duration mismatch")
def _() -> None:
    """Verify ScenarioRunner detects invalid phase durations."""
    from k0.perf.runner import ScenarioRunner

    # Load valid scenario and modify it
    scenario_path = SCENARIOS_DIR / "command_burst.yaml"
    config = ScenarioConfig.from_yaml(scenario_path)

    # Break phase duration sum
    config.phases[0]["duration"] = 999

    runner = ScenarioRunner(config=config, dry_run=True)
    errors = runner.validate()

    assert len(errors) > 0
    assert any("duration" in error.lower() for error in errors)


@test("scenario validation requires kernel_endpoint")
def _() -> None:
    """Verify ScenarioRunner requires kernel endpoint."""
    from k0.perf.runner import ScenarioRunner

    scenario_path = SCENARIOS_DIR / "command_burst.yaml"
    config = ScenarioConfig.from_yaml(scenario_path)

    # Remove kernel endpoint
    config.environment.pop("kernel_endpoint", None)

    runner = ScenarioRunner(config=config, dry_run=True)
    errors = runner.validate()

    assert len(errors) > 0
    assert any("kernel_endpoint" in error for error in errors)


@test("dry-run execution succeeds for valid scenarios")
def _() -> None:
    """Verify dry-run mode validates without executing workload."""
    from k0.perf.runner import ScenarioRunner

    scenario_path = SCENARIOS_DIR / "command_burst.yaml"
    config = ScenarioConfig.from_yaml(scenario_path)

    runner = ScenarioRunner(config=config, dry_run=True)
    result = runner.execute()

    assert result.success is True
    assert result.phases_executed == 0
    assert result.total_requests == 0
    assert len(result.errors) == 0
