"""Performance scenario runner for k0 kernel load testing.

This module orchestrates performance and load test scenarios, handling:
- YAML scenario loading and validation
- Workload execution across multiple phases
- Metrics collection via Prometheus Pushgateway
- Artifact generation (timeline, traces, metrics snapshots)

Usage:
    # Run a scenario
    python -m k0.perf.runner --scenario scenarios/command_burst.yaml

    # Dry-run validation only
    python -m k0.perf.runner --scenario scenarios/sse_fanout.yaml --dry-run

    # Override Pushgateway endpoint
    python -m k0.perf.runner \\
        --scenario scenarios/replay_surge.yaml \\
        --pushgateway http://localhost:9091

Exit Codes:
    0 - Scenario passed all assertions
    1 - Scenario failed assertions or validation
    2 - Runtime error (configuration, network, etc.)
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import yaml


@dataclass
class ScenarioConfig:
    """Parsed and validated scenario configuration."""

    name: str
    description: str | None
    type: str
    duration: int
    tags: list[str]
    environment: dict[str, Any]
    phases: list[dict[str, Any]]
    global_assertions: dict[str, Any] | None
    artifacts: dict[str, bool]

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> ScenarioConfig:
        """Load and parse a scenario YAML file.

        Args:
            yaml_path: Path to scenario YAML file

        Returns:
            Parsed ScenarioConfig instance

        Raises:
            FileNotFoundError: If YAML file doesn't exist
            yaml.YAMLError: If YAML is malformed
            ValueError: If scenario doesn't match schema
        """
        if not yaml_path.exists():
            raise FileNotFoundError(f"Scenario file not found: {yaml_path}")

        with yaml_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # TODO: Validate against JSON schema
        return cls(
            name=data["name"],
            description=data.get("description"),
            type=data["type"],
            duration=data["duration"],
            tags=data.get("tags", []),
            environment=data["environment"],
            phases=data["phases"],
            global_assertions=data.get("global_assertions"),
            artifacts=data.get("artifacts", {}),
        )


@dataclass
class ScenarioResult:
    """Results from scenario execution."""

    scenario_name: str
    start_time: datetime
    end_time: datetime
    success: bool
    phases_executed: int
    total_requests: int
    success_rate: float
    p99_latency_ms: float
    errors: list[str]
    artifacts_dir: Path | None


class PushgatewayClient:
    """Client for pushing metrics to Prometheus Pushgateway."""

    def __init__(self, endpoint: str, job_name: str = "k0-perf"):
        """Initialize Pushgateway client.

        Args:
            endpoint: Pushgateway base URL (e.g., http://localhost:9091)
            job_name: Job name for metric grouping
        """
        self.endpoint = endpoint.rstrip("/")
        self.job_name = job_name

    def _build_push_url(self, labels: dict[str, str] | None = None) -> str:
        """Build Pushgateway push URL with job and labels.

        Args:
            labels: Additional labels for metrics grouping

        Returns:
            Full push URL with job and label path segments
        """
        url = f"{self.endpoint}/metrics/job/{self.job_name}"

        if labels:
            for key, value in sorted(labels.items()):
                # URL-encode label values
                encoded_value = quote(value, safe="")
                url += f"/{key}/{encoded_value}"

        return url

    def _format_metrics(self, metrics: dict[str, float]) -> str:
        """Format metrics in Prometheus exposition format.

        Args:
            metrics: Metric name -> value mapping

        Returns:
            Metrics in Prometheus text format
        """
        lines: list[str] = []

        for metric_name, value in metrics.items():
            # Validate metric name (alphanumeric + underscore/colon)
            if not all(c.isalnum() or c in ("_", ":") for c in metric_name):
                raise ValueError(f"Invalid metric name: {metric_name}")

            # Format value (handle NaN/Inf)
            if value != value:  # NaN check
                value_str = "NaN"
            elif value == float("inf"):
                value_str = "+Inf"
            elif value == float("-inf"):
                value_str = "-Inf"
            else:
                value_str = str(value)

            lines.append(f"{metric_name} {value_str}")

        return "\n".join(lines) + "\n"

    def push_metrics(
        self, metrics: dict[str, float], labels: dict[str, str] | None = None
    ) -> None:
        """Push metrics to Pushgateway.

        Args:
            metrics: Metric name -> value mapping
            labels: Additional labels for metrics (scenario, git_sha, etc.)

        Raises:
            httpx.HTTPError: If push fails
            ValueError: If metric names are invalid
        """
        url = self._build_push_url(labels)
        payload = self._format_metrics(metrics)

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    url,
                    content=payload,
                    headers={"Content-Type": "text/plain; charset=utf-8"},
                )
                response.raise_for_status()
        except httpx.HTTPError as e:
            raise httpx.HTTPError(f"Failed to push metrics to {url}: {e}") from e

    def delete_metrics(self, labels: dict[str, str] | None = None) -> None:
        """Delete metrics from Pushgateway.

        Args:
            labels: Label filters for deletion

        Raises:
            httpx.HTTPError: If deletion fails
        """
        url = self._build_push_url(labels)

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.delete(url)
                response.raise_for_status()
        except httpx.HTTPError as e:
            raise httpx.HTTPError(f"Failed to delete metrics from {url}: {e}") from e


class ScenarioRunner:
    """Orchestrates performance scenario execution."""

    def __init__(
        self,
        config: ScenarioConfig,
        pushgateway_endpoint: str | None = None,
        artifacts_dir: Path | None = None,
        dry_run: bool = False,
    ):
        """Initialize scenario runner.

        Args:
            config: Validated scenario configuration
            pushgateway_endpoint: Optional Pushgateway URL override
            artifacts_dir: Directory for artifact output
            dry_run: If True, validate only without execution
        """
        self.config = config
        self.dry_run = dry_run
        self.artifacts_dir = artifacts_dir or Path("perf-artifacts")

        # Determine Pushgateway endpoint
        pg_endpoint = pushgateway_endpoint or config.environment.get(
            "prometheus_pushgateway"
        )
        self.pushgateway = PushgatewayClient(pg_endpoint) if pg_endpoint else None

    def validate(self) -> list[str]:
        """Validate scenario configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors: list[str] = []

        # Validate phases
        if not self.config.phases:
            errors.append("Scenario must have at least one phase")

        total_phase_duration = sum(phase["duration"] for phase in self.config.phases)
        if total_phase_duration != self.config.duration:
            errors.append(
                f"Phase durations ({total_phase_duration}s) don't match "
                f"scenario duration ({self.config.duration}s)"
            )

        # Validate environment
        if not self.config.environment.get("kernel_endpoint"):
            errors.append("Environment must specify kernel_endpoint")

        return errors

    def execute(self) -> ScenarioResult:
        """Execute the performance scenario.

        Returns:
            ScenarioResult with execution summary and metrics

        Raises:
            RuntimeError: If scenario validation fails
        """
        validation_errors = self.validate()
        if validation_errors:
            raise RuntimeError(
                "Scenario validation failed:\n" + "\n".join(validation_errors)
            )

        if self.dry_run:
            print(f"✓ Scenario '{self.config.name}' validated successfully (dry-run)")
            return ScenarioResult(
                scenario_name=self.config.name,
                start_time=datetime.now(tz=timezone.utc),
                end_time=datetime.now(tz=timezone.utc),
                success=True,
                phases_executed=0,
                total_requests=0,
                success_rate=1.0,
                p99_latency_ms=0.0,
                errors=[],
                artifacts_dir=None,
            )

        # TODO: Implement scenario execution
        # - Phase-by-phase workload generation
        # - Metrics collection and Pushgateway push
        # - Timeline/trace artifact capture
        # - Assertion evaluation

        start_time = datetime.now(tz=timezone.utc)
        print(f"🚀 Starting scenario: {self.config.name}")
        print(f"   Duration: {self.config.duration}s")
        print(f"   Phases: {len(self.config.phases)}")
        print(f"   Type: {self.config.type}")

        # Placeholder result
        end_time = datetime.now(tz=timezone.utc)
        return ScenarioResult(
            scenario_name=self.config.name,
            start_time=start_time,
            end_time=end_time,
            success=False,
            phases_executed=0,
            total_requests=0,
            success_rate=0.0,
            p99_latency_ms=0.0,
            errors=["Scenario execution not yet implemented"],
            artifacts_dir=self.artifacts_dir,
        )


def main() -> int:
    """CLI entry point for scenario runner."""
    parser = argparse.ArgumentParser(
        description="Run k0 kernel performance scenarios",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--scenario",
        type=Path,
        required=True,
        help="Path to scenario YAML file",
    )
    parser.add_argument(
        "--pushgateway",
        type=str,
        help="Prometheus Pushgateway endpoint (overrides scenario config)",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("perf-artifacts"),
        help="Directory for artifact output (default: perf-artifacts)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate scenario without execution",
    )

    args = parser.parse_args()

    try:
        # Load and validate scenario
        config = ScenarioConfig.from_yaml(args.scenario)

        # Create runner
        runner = ScenarioRunner(
            config=config,
            pushgateway_endpoint=args.pushgateway,
            artifacts_dir=args.artifacts_dir,
            dry_run=args.dry_run,
        )

        # Execute scenario
        result = runner.execute()

        # Print summary
        print("\n" + "=" * 60)
        print(f"Scenario: {result.scenario_name}")
        print(f"Status: {'✓ PASS' if result.success else '✗ FAIL'}")
        print(f"Duration: {(result.end_time - result.start_time).total_seconds():.2f}s")
        print(f"Phases: {result.phases_executed}")
        print(f"Requests: {result.total_requests}")
        print(f"Success Rate: {result.success_rate:.2%}")
        print(f"P99 Latency: {result.p99_latency_ms:.2f}ms")

        if result.errors:
            print("\nErrors:")
            for error in result.errors:
                print(f"  - {error}")

        if result.artifacts_dir:
            print(f"\nArtifacts: {result.artifacts_dir}")

        print("=" * 60)

        return 0 if result.success else 1

    except FileNotFoundError as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        return 2
    except (yaml.YAMLError, ValueError) as e:
        print(f"✗ Scenario validation failed: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"✗ Execution error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n✗ Scenario interrupted by user", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
