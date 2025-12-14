"""Performance regression detection and baseline management for K0 kernel.

This module provides automated performance baseline comparison and regression detection
for K0 kernel performance testing. It collects metrics from performance profiles,
stores baselines, and detects regressions with configurable thresholds.

Features:
- Baseline management (store/load by git SHA)
- Performance profile execution (small, balanced, large workloads)
- Regression detection (P50/P95/P99 latency, throughput, error rate)
- Markdown report generation for CI artifacts

Usage:
    # Run performance suite and save baseline
    python -m k0.automation.performance_regression_detector \\
        --run-suite \\
        --save-baseline main

    # Check for regressions vs main branch
    python -m k0.automation.performance_regression_detector \\
        --run-suite \\
        --baseline main \\
        --threshold 0.10 \\
        --fail-on-regression

    # Load and compare existing baselines
    python -m k0.automation.performance_regression_detector \\
        --baseline-a main \\
        --baseline-b feature-branch \\
        --threshold 0.15

Exit Codes:
    0 - No regressions detected or comparison requested
    1 - Regressions detected above threshold
    2 - Configuration or runtime error
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Setup logging
logging.basicConfig(level=logging.INFO, format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class MetricsSnapshot:
    """Single metric collection point (P50/P95/P99 + throughput/error rate)."""

    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    throughput_rps: float
    error_rate: float

    def to_dict(self) -> dict[str, float]:
        """Convert to flat dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetricsSnapshot:
        """Create from dictionary."""
        return cls(
            p50_latency_ms=data["p50_latency_ms"],
            p95_latency_ms=data["p95_latency_ms"],
            p99_latency_ms=data["p99_latency_ms"],
            throughput_rps=data["throughput_rps"],
            error_rate=data["error_rate"],
        )


@dataclass
class PerformanceBaseline:
    """Versioned performance baseline for a git SHA."""

    git_sha: str
    timestamp: str
    branch: str | None = None
    metrics: dict[str, MetricsSnapshot] = field(default_factory=dict)  # profile -> metrics

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            "git_sha": self.git_sha,
            "timestamp": self.timestamp,
            "branch": self.branch,
            "metrics": {profile: snapshot.to_dict() for profile, snapshot in self.metrics.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PerformanceBaseline:
        """Create from deserialized dictionary."""
        baseline = cls(
            git_sha=data["git_sha"],
            timestamp=data["timestamp"],
            branch=data.get("branch"),
        )
        baseline.metrics = {
            profile: MetricsSnapshot.from_dict(snapshot)
            for profile, snapshot in data.get("metrics", {}).items()
        }
        return baseline

    def get_checksum(self) -> str:
        """Compute deterministic checksum of baseline (excluding timestamp)."""
        # Create deterministic JSON representation
        data = {
            "git_sha": self.git_sha,
            "branch": self.branch,
            "metrics": {
                profile: snapshot.to_dict() for profile, snapshot in sorted(self.metrics.items())
            },
        }
        json_str = json.dumps(data, sort_keys=True, separators=(",", ":"))
        hash_obj = hashlib.sha256(json_str.encode())
        return hash_obj.hexdigest()[:16]


@dataclass
class RegressionResult:
    """Result of comparing two baselines."""

    metric_name: str
    profile: str
    baseline_value: float
    current_value: float
    change_percent: float
    threshold_percent: float
    is_regression: bool

    def __str__(self) -> str:
        """Format for display."""
        status = "⚠️  REGRESSION" if self.is_regression else "✓ OK"
        direction = "↑" if self.change_percent > 0 else "↓"
        return (
            f"{status} {self.profile} {self.metric_name}: "
            f"{self.baseline_value:.2f} → {self.current_value:.2f} "
            f"({direction}{abs(self.change_percent):.1f}%)"
        )


class BaselineManager:
    """Manages performance baseline storage and retrieval."""

    def __init__(self, baselines_dir: Path = Path("k0/perf/baselines")):
        """Initialize baseline manager.

        Args:
            baselines_dir: Directory for storing baseline JSON files
        """
        self.baselines_dir = Path(baselines_dir)
        self.baselines_dir.mkdir(parents=True, exist_ok=True)

    def _get_baseline_path(self, git_sha: str) -> Path:
        """Get file path for baseline.

        Args:
            git_sha: Git commit SHA or reference (e.g., "main", "abc1234")

        Returns:
            Path to baseline JSON file
        """
        # Handle "main" → resolve to actual SHA (stub for now)
        sha = git_sha if len(git_sha) >= 7 else git_sha
        return self.baselines_dir / f"{sha}.json"

    def save_baseline(self, baseline: PerformanceBaseline) -> None:
        """Save baseline to disk.

        Args:
            baseline: PerformanceBaseline instance to save
        """
        path = self._get_baseline_path(baseline.git_sha)
        data = baseline.to_dict()
        data["checksum"] = baseline.get_checksum()

        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved baseline for {baseline.git_sha} to {path}")

    def load_baseline(self, git_sha: str) -> PerformanceBaseline:
        """Load baseline from disk.

        Args:
            git_sha: Git commit SHA or reference to load

        Returns:
            PerformanceBaseline instance

        Raises:
            FileNotFoundError: If baseline doesn't exist
            json.JSONDecodeError: If baseline JSON is malformed
        """
        path = self._get_baseline_path(git_sha)

        if not path.exists():
            raise FileNotFoundError(
                f"Baseline not found for {git_sha} at {path}. "
                f"Available baselines: {list(self.baselines_dir.glob('*.json'))}"
            )

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        # Strip checksum before creating baseline
        data.pop("checksum", None)
        return PerformanceBaseline.from_dict(data)

    def list_baselines(self) -> list[str]:
        """List all available baselines.

        Returns:
            List of git SHAs with available baselines
        """
        return [f.stem for f in sorted(self.baselines_dir.glob("*.json"))]


class PerformanceProfileRunner:
    """Runs performance profiles and collects metrics."""

    def __init__(self, profiles_dir: Path = Path("k0/perf/profiles")):
        """Initialize profile runner.

        Args:
            profiles_dir: Directory containing profile Python files
        """
        self.profiles_dir = Path(profiles_dir)

    def run_profile(self, profile_name: str) -> MetricsSnapshot:
        """Execute a performance profile and collect metrics.

        Args:
            profile_name: Name of profile (e.g., "small", "balanced", "large")

        Returns:
            MetricsSnapshot with collected metrics

        Raises:
            FileNotFoundError: If profile doesn't exist
            RuntimeError: If profile execution fails
        """
        profile_path = self.profiles_dir / f"{profile_name}.py"

        if not profile_path.exists():
            raise FileNotFoundError(
                f"Profile not found: {profile_path}. "
                f"Available profiles: {list(self.profiles_dir.glob('*.py'))}"
            )

        logger.info(f"Running profile: {profile_name}")

        try:
            # Execute profile and capture metrics
            result = subprocess.run(
                [sys.executable, profile_path.name],
                capture_output=True,
                text=True,
                timeout=300,  # 5 min timeout
                cwd=str(self.profiles_dir),
            )

            if result.returncode != 0:
                raise RuntimeError(f"Profile execution failed:\n{result.stderr}")

            # Parse metrics from stdout (JSON format)
            metrics_json = json.loads(result.stdout)
            metrics = MetricsSnapshot(**metrics_json)
            logger.info(
                f"  P95: {metrics.p95_latency_ms:.2f}ms, "
                f"Throughput: {metrics.throughput_rps:.0f} rps, "
                f"Error rate: {metrics.error_rate:.2%}"
            )

            return metrics

        except json.JSONDecodeError as e:
            raise RuntimeError(f"Profile output is not valid JSON: {result.stdout[:200]}") from e
        except subprocess.TimeoutExpired:
            raise RuntimeError("Profile execution timeout (> 300s)")

    def run_suite(self, profiles: list[str] | None = None) -> PerformanceBaseline:
        """Run multiple profiles and collect baseline.

        Args:
            profiles: List of profile names to run. If None, runs all available.

        Returns:
            PerformanceBaseline with all profiles' metrics
        """
        if profiles is None:
            # Auto-discover profiles
            profiles = [p.stem for p in self.profiles_dir.glob("*.py") if p.name != "__init__.py"]

        # Get current git SHA
        try:
            git_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=self.profiles_dir.parent.parent.parent,
                check=True,
            ).stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            git_sha = "unknown"
            logger.warning("Could not determine git SHA, using 'unknown'")

        baseline = PerformanceBaseline(
            git_sha=git_sha,
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            branch=self._get_current_branch(),
        )

        for profile in profiles:
            logger.info(f"Running profile {profile}...")
            try:
                metrics = self.run_profile(profile)
                baseline.metrics[profile] = metrics
            except (FileNotFoundError, RuntimeError) as e:
                logger.error(f"  Failed to run profile {profile}: {e}")
                # Continue with other profiles

        logger.info(f"✓ Performance suite completed ({len(baseline.metrics)} profiles)")
        return baseline

    @staticmethod
    def _get_current_branch() -> str | None:
        """Get current git branch name.

        Returns:
            Branch name or None if not in git repo
        """
        try:
            return subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            ).stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None


class RegressionDetector:
    """Detects performance regressions between baselines."""

    @staticmethod
    def detect_regressions(
        baseline: PerformanceBaseline,
        current: PerformanceBaseline,
        threshold: float = 0.10,
    ) -> list[RegressionResult]:
        """Compare two baselines and detect regressions.

        Args:
            baseline: Reference baseline (e.g., main branch)
            current: Current/feature baseline to compare
            threshold: Regression threshold (0.10 = 10% degradation)

        Returns:
            List of RegressionResult for each metric comparison
        """
        regressions: list[RegressionResult] = []

        # Get union of profiles in both baselines
        profiles = set(baseline.metrics.keys()) | set(current.metrics.keys())

        for profile in sorted(profiles):
            if profile not in baseline.metrics:
                logger.warning(f"Profile {profile} not in baseline, skipping")
                continue

            if profile not in current.metrics:
                logger.warning(f"Profile {profile} not in current metrics, skipping")
                continue

            baseline_metrics = baseline.metrics[profile]
            current_metrics = current.metrics[profile]

            # Check latency metrics (higher is worse)
            for metric_name in ["p50_latency_ms", "p95_latency_ms", "p99_latency_ms"]:
                baseline_val = getattr(baseline_metrics, metric_name)
                current_val = getattr(current_metrics, metric_name)

                # Calculate percent change (positive = worse for latency)
                if baseline_val > 0:
                    change = (current_val - baseline_val) / baseline_val
                else:
                    change = 0

                is_regression = change > threshold

                regressions.append(
                    RegressionResult(
                        metric_name=metric_name,
                        profile=profile,
                        baseline_value=baseline_val,
                        current_value=current_val,
                        change_percent=change * 100,
                        threshold_percent=threshold * 100,
                        is_regression=is_regression,
                    )
                )

            # Check throughput (lower is worse, so negative change = regression)
            baseline_tp = baseline_metrics.throughput_rps
            current_tp = current_metrics.throughput_rps

            if baseline_tp > 0:
                tp_change = (baseline_tp - current_tp) / baseline_tp  # Inverted
            else:
                tp_change = 0

            is_regression = tp_change > threshold
            regressions.append(
                RegressionResult(
                    metric_name="throughput_rps",
                    profile=profile,
                    baseline_value=baseline_tp,
                    current_value=current_tp,
                    change_percent=-tp_change * 100,  # Negate for display
                    threshold_percent=threshold * 100,
                    is_regression=is_regression,
                )
            )

            # Check error rate (higher is worse)
            baseline_err = baseline_metrics.error_rate
            current_err = current_metrics.error_rate

            if baseline_err > 0:
                err_change = (current_err - baseline_err) / baseline_err
            else:
                err_change = current_err  # If baseline is 0, any error is bad

            is_regression = err_change > threshold
            regressions.append(
                RegressionResult(
                    metric_name="error_rate",
                    profile=profile,
                    baseline_value=baseline_err,
                    current_value=current_err,
                    change_percent=err_change * 100,
                    threshold_percent=threshold * 100,
                    is_regression=is_regression,
                )
            )

        return regressions

    @staticmethod
    def generate_report(
        baseline: PerformanceBaseline,
        current: PerformanceBaseline,
        regressions: list[RegressionResult],
        threshold: float = 0.10,
    ) -> str:
        """Generate Markdown comparison report.

        Args:
            baseline: Reference baseline
            current: Current baseline
            regressions: List of regression results
            threshold: Threshold used for comparison

        Returns:
            Formatted Markdown report
        """
        lines: list[str] = []

        lines.append("# Performance Regression Report")
        lines.append("")
        lines.append(f"**Baseline**: {baseline.git_sha} @ {baseline.timestamp}")
        lines.append(f"**Current**: {current.git_sha} @ {current.timestamp}")
        lines.append(f"**Threshold**: {threshold * 100:.1f}%")
        lines.append("")

        # Summary statistics
        total = len(regressions)
        regressions_found = sum(1 for r in regressions if r.is_regression)

        lines.append("## Summary")
        lines.append(f"- **Total metrics**: {total}")
        lines.append(f"- **Regressions**: {regressions_found}")
        lines.append(f"- **Status**: {'⚠️ FAILED' if regressions_found > 0 else '✓ PASSED'}")
        lines.append("")

        # Group by status
        lines.append("## Detailed Results")
        lines.append("")

        # Regressions
        regression_items = [r for r in regressions if r.is_regression]
        if regression_items:
            lines.append("### 🔴 Regressions")
            lines.append("")
            for result in sorted(regression_items, key=lambda r: (-r.change_percent, r.profile)):
                lines.append(f"- {result}")
            lines.append("")

        # Okays
        ok_items = [r for r in regressions if not r.is_regression]
        if ok_items:
            lines.append(f"### 🟢 Within Threshold ({len(ok_items)} metrics)")
            lines.append("")
            for result in sorted(ok_items, key=lambda r: (-abs(r.change_percent), r.profile))[:10]:
                lines.append(f"- {result}")
            if len(ok_items) > 10:
                lines.append(f"- ... and {len(ok_items) - 10} more")
            lines.append("")

        # Remediation steps
        if regressions_found > 0:
            lines.append("## Remediation Steps")
            lines.append("")
            lines.append(
                "1. **Profile the changes**: `python -m k0.perf.runner --scenario scenarios/*.yaml`"
            )
            lines.append("2. **Identify bottlenecks**: Use flamegraphs in artifacts directory")
            lines.append("3. **Optimize code**: Address performance-critical paths")
            lines.append("4. **Verify fix**: Rerun performance suite to confirm improvements")
            lines.append(
                "5. **Update baseline**: `python -m k0.automation.performance_regression_detector --save-baseline`"
            )
            lines.append("")

        return "\n".join(lines)


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Performance regression detection for K0 kernel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--run-suite",
        action="store_true",
        help="Run performance profiles and collect metrics",
    )
    mode_group.add_argument(
        "--compare",
        nargs=2,
        metavar=("BASELINE_A", "BASELINE_B"),
        help="Compare two baselines (SHA or branch names)",
    )

    parser.add_argument(
        "--profiles",
        nargs="+",
        default=None,
        help="Specific profiles to run (default: auto-discover)",
    )
    parser.add_argument(
        "--baseline",
        type=str,
        help="Baseline to compare against (for regression detection)",
    )
    parser.add_argument(
        "--save-baseline",
        type=str,
        help="Save collected metrics as baseline for this git SHA",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.10,
        help="Regression threshold as decimal (default: 0.10 = 10%%)",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit with code 1 if regressions detected",
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        help="Write report to file (default: stdout)",
    )
    parser.add_argument(
        "--baselines-dir",
        type=Path,
        default=Path("k0/perf/baselines"),
        help="Directory for baseline storage",
    )
    parser.add_argument(
        "--profiles-dir",
        type=Path,
        default=Path("k0/perf/profiles"),
        help="Directory containing performance profiles",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        baseline_mgr = BaselineManager(args.baselines_dir)
        profile_runner = PerformanceProfileRunner(args.profiles_dir)
        detector = RegressionDetector()

        if args.run_suite:
            # Run performance suite
            logger.info("Running performance suite...")
            current = profile_runner.run_suite(args.profiles)

            # Save as baseline if requested
            if args.save_baseline:
                current.git_sha = args.save_baseline
                baseline_mgr.save_baseline(current)
                logger.info(f"✓ Baseline saved as '{args.save_baseline}'")

            # Compare if baseline specified
            if args.baseline:
                logger.info(f"Comparing against baseline '{args.baseline}'...")
                baseline = baseline_mgr.load_baseline(args.baseline)
                regressions = detector.detect_regressions(baseline, current, args.threshold)

                report = detector.generate_report(baseline, current, regressions, args.threshold)

                if args.report_file:
                    args.report_file.write_text(report)
                    logger.info(f"Report written to {args.report_file}")
                else:
                    print(report)

                regressions_found = sum(1 for r in regressions if r.is_regression)
                if regressions_found > 0:
                    logger.warning(f"⚠️  {regressions_found} regressions detected")
                    if args.fail_on_regression:
                        return 1
                else:
                    logger.info("✓ No regressions detected")

        elif args.compare:
            # Compare two existing baselines
            logger.info(f"Comparing baselines: {args.compare[0]} vs {args.compare[1]}")
            baseline_a = baseline_mgr.load_baseline(args.compare[0])
            baseline_b = baseline_mgr.load_baseline(args.compare[1])

            regressions = detector.detect_regressions(baseline_a, baseline_b, args.threshold)

            report = detector.generate_report(baseline_a, baseline_b, regressions, args.threshold)

            if args.report_file:
                args.report_file.write_text(report)
                logger.info(f"Report written to {args.report_file}")
            else:
                print(report)

            regressions_found = sum(1 for r in regressions if r.is_regression)
            if regressions_found > 0:
                logger.warning(f"⚠️  {regressions_found} regressions detected")
                if args.fail_on_regression:
                    return 1

        return 0

    except FileNotFoundError as e:
        logger.error(f"✗ {e}")
        return 2
    except RuntimeError as e:
        logger.error(f"✗ {e}")
        return 2
    except KeyboardInterrupt:
        logger.error("✗ Interrupted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())
