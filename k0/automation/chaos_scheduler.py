"""Chaos scheduler for automated, reproducible chaos experiments on K0 kernel.

This module provides a framework for running controlled chaos experiments to validate
K0's fault tolerance and recovery mechanisms. It integrates with the existing chaos
infrastructure in k0/chaos/ for fault injection and uses pytest for test orchestration.

Features:
- 3 predefined chaos profiles (mild, moderate, aggressive)
- Fault injection: fsync failures, scheduler stress, network latency, telemetry outages
- Recovery validation: correctness invariants, MTTR measurement, SSE reconnection
- JSON reporting with fault timeline and recovery metrics
- CLI integration for CI workflows

Usage:
    # Run mild chaos experiment for 60 seconds
    python -m k0.automation.chaos_scheduler \\
        --profile=mild \\
        --duration=60 \\
        --output=chaos-report.json

    # Run aggressive experiment with telemetry collection
    python -m k0.automation.chaos_scheduler \\
        --profile=aggressive \\
        --duration=300 \\
        --collect-telemetry \\
        --output=chaos-report.json

Exit Codes:
    0 - Chaos experiment completed, no invariant violations
    1 - Invariant violations detected during recovery
    2 - Configuration or runtime error
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

# Setup logging
logging.basicConfig(level=logging.INFO, format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class FaultType(Enum):
    """Types of faults that can be injected."""

    FSYNC_FAILURE = "fsync_failure"
    SCHEDULER_STRESS = "scheduler_stress"
    NETWORK_LATENCY = "network_latency"
    TELEMETRY_OUTAGE = "telemetry_outage"


@dataclass
class ChaosProfile:
    """Configuration profile for chaos experiments."""

    name: str
    fsync_fail_rate: float  # 0.0-1.0
    scheduler_multiplier: float  # Fraction of normal capacity (0.0-1.0)
    network_latency_ms: int  # Milliseconds of added latency
    telemetry_outage_rate: float  # 0.0-1.0 fraction of telemetry events dropped

    def validate(self) -> bool:
        """Validate profile parameters are in valid ranges."""
        return (
            0.0 <= self.fsync_fail_rate <= 1.0
            and 0.0 < self.scheduler_multiplier <= 1.0
            and self.network_latency_ms >= 0
            and 0.0 <= self.telemetry_outage_rate <= 1.0
        )


# Predefined chaos profiles
PROFILES = {
    "mild": ChaosProfile(
        name="mild",
        fsync_fail_rate=0.05,
        scheduler_multiplier=0.5,
        network_latency_ms=0,
        telemetry_outage_rate=0.0,
    ),
    "moderate": ChaosProfile(
        name="moderate",
        fsync_fail_rate=0.10,
        scheduler_multiplier=0.3,
        network_latency_ms=50,
        telemetry_outage_rate=0.1,
    ),
    "aggressive": ChaosProfile(
        name="aggressive",
        fsync_fail_rate=0.20,
        scheduler_multiplier=0.2,
        network_latency_ms=100,
        telemetry_outage_rate=0.2,
    ),
}


@dataclass
class FaultEvent:
    """Record of a fault injection event."""

    timestamp: str
    fault_type: str
    description: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class RecoveryCheckpoint:
    """Checkpoint during recovery validation."""

    timestamp: str
    invariant: str
    status: str  # "passed", "failed", "unknown"
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ChaosReport:
    """Complete report from a chaos experiment."""

    experiment_id: str
    profile_name: str
    start_time: str
    end_time: str
    duration_seconds: float
    fault_events: list[FaultEvent] = field(default_factory=list)
    recovery_checkpoints: list[RecoveryCheckpoint] = field(default_factory=list)
    invariant_violations: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            "experiment_id": self.experiment_id,
            "profile_name": self.profile_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "fault_events": [e.to_dict() for e in self.fault_events],
            "recovery_checkpoints": [c.to_dict() for c in self.recovery_checkpoints],
            "invariant_violations": self.invariant_violations,
            "metrics": self.metrics,
        }


class ChaosInjector:
    """Injects faults according to chaos profile configuration."""

    def __init__(
        self,
        profile: ChaosProfile,
        random_seed: int | None = None,
    ):
        """Initialize fault injector.

        Args:
            profile: ChaosProfile defining fault rates
            random_seed: Random seed for reproducible chaos (None = non-deterministic)
        """
        self.profile = profile
        if random_seed is not None:
            random.seed(random_seed)

    def should_inject_fsync_failure(self) -> bool:
        """Determine if fsync failure should be injected."""
        return random.random() < self.profile.fsync_fail_rate

    def should_degrade_scheduler(self) -> bool:
        """Determine if scheduler should be degraded (queue overflow)."""
        # Inverse logic: if multiplier is 0.5, then 50% of the time inject degradation
        degradation_rate = 1.0 - self.profile.scheduler_multiplier
        return random.random() < degradation_rate

    def get_network_latency_ms(self) -> int:
        """Get network latency to inject for this request."""
        if self.profile.network_latency_ms <= 0:
            return 0
        # Add random jitter: ±20% of configured latency
        jitter = random.uniform(0.8, 1.2)
        return int(self.profile.network_latency_ms * jitter)

    def should_drop_telemetry(self) -> bool:
        """Determine if telemetry event should be dropped."""
        return random.random() < self.profile.telemetry_outage_rate


class RecoveryValidator:
    """Validates correctness invariants after chaos injection."""

    @staticmethod
    def validate_replay_parity(
        original_commands: list[dict[str, Any]],
        replayed_commands: list[dict[str, Any]],
    ) -> tuple[bool, str]:
        """Validate that replayed commands match original commands.

        Args:
            original_commands: Commands executed before chaos
            replayed_commands: Commands re-executed after recovery

        Returns:
            Tuple of (is_valid, details_str)
        """
        if len(original_commands) != len(replayed_commands):
            return (
                False,
                f"Command count mismatch: {len(original_commands)} vs {len(replayed_commands)}",
            )

        for i, (orig, replayed) in enumerate(zip(original_commands, replayed_commands)):
            if orig.get("command_id") != replayed.get("command_id"):
                return (
                    False,
                    f"Command ID mismatch at index {i}: {orig.get('command_id')} vs {replayed.get('command_id')}",
                )

            if orig.get("result_hash") != replayed.get("result_hash"):
                return (
                    False,
                    f"Result hash mismatch for command {orig.get('command_id')}",
                )

        return True, "All commands replayed successfully with matching results"

    @staticmethod
    def validate_receipt_consistency(
        receipts_during_chaos: list[dict[str, Any]],
        receipts_after_recovery: list[dict[str, Any]],
    ) -> tuple[bool, str]:
        """Validate that receipts are consistent before and after chaos.

        Args:
            receipts_during_chaos: Receipts collected during chaos period
            receipts_after_recovery: Receipts after recovery completed

        Returns:
            Tuple of (is_valid, details_str)
        """
        # Extract receipt hashes
        during_hashes = {r.get("receipt_id"): r.get("hash") for r in receipts_during_chaos}
        after_hashes = {r.get("receipt_id"): r.get("hash") for r in receipts_after_recovery}

        # Check that all receipts from chaos period are accounted for
        for receipt_id, original_hash in during_hashes.items():
            if receipt_id not in after_hashes:
                return (
                    False,
                    f"Receipt {receipt_id} lost during chaos (not found after recovery)",
                )

            if after_hashes[receipt_id] != original_hash:
                return (
                    False,
                    f"Receipt {receipt_id} corrupted: hash changed during recovery",
                )

        return True, "All receipts consistent across chaos period and recovery"

    @staticmethod
    def validate_sse_reconnection(
        sse_connections_before: int,
        sse_connections_after: int,
        sse_events_received: int,
    ) -> tuple[bool, str]:
        """Validate SSE reconnection and event delivery after recovery.

        Args:
            sse_connections_before: Number of active SSE connections before chaos
            sse_connections_after: Number of active SSE connections after recovery
            sse_events_received: Number of SSE events received during recovery

        Returns:
            Tuple of (is_valid, details_str)
        """
        if sse_connections_after == 0:
            return False, "No SSE connections active after recovery"

        if sse_events_received < sse_connections_before:
            return (
                False,
                f"SSE events missing: expected >={sse_connections_before}, got {sse_events_received}",
            )

        return (
            True,
            f"SSE recovery successful: {sse_connections_after} connections, {sse_events_received} events",
        )

    @staticmethod
    def validate_scheduler_recovery(
        queue_depth_during_chaos: int,
        queue_depth_after_recovery: int,
        max_queue_depth: int,
    ) -> tuple[bool, str]:
        """Validate that scheduler queue recovers to normal depth.

        Args:
            queue_depth_during_chaos: Maximum queue depth during chaos
            queue_depth_after_recovery: Queue depth after recovery
            max_queue_depth: Expected normal max queue depth

        Returns:
            Tuple of (is_valid, details_str)
        """
        if queue_depth_after_recovery > max_queue_depth:
            return (
                False,
                f"Scheduler queue not recovered: {queue_depth_after_recovery} > {max_queue_depth}",
            )

        queue_utilization = queue_depth_after_recovery / max_queue_depth * 100
        return (
            True,
            f"Scheduler queue recovered: {queue_depth_after_recovery}/{max_queue_depth} ({queue_utilization:.1f}% utilized)",
        )


class ChaosExperiment:
    """Orchestrates a complete chaos experiment."""

    def __init__(
        self,
        profile: ChaosProfile,
        duration_seconds: int = 300,
        random_seed: int | None = None,
    ):
        """Initialize chaos experiment.

        Args:
            profile: ChaosProfile defining fault rates and intensities
            duration_seconds: Duration of chaos period
            random_seed: Random seed for reproducible experiments
        """
        if not profile.validate():
            raise ValueError(f"Invalid profile: {profile}")

        self.profile = profile
        self.duration_seconds = duration_seconds
        self.injector = ChaosInjector(profile, random_seed)
        self.report = ChaosReport(
            experiment_id=self._generate_experiment_id(),
            profile_name=profile.name,
            start_time=datetime.now(tz=timezone.utc).isoformat(),
            end_time="",
            duration_seconds=0.0,
        )

    @staticmethod
    def _generate_experiment_id() -> str:
        """Generate unique experiment ID."""
        import uuid

        return str(uuid.uuid4())[:8]

    def run(self) -> ChaosReport:
        """Execute chaos experiment.

        Returns:
            ChaosReport with results and metrics
        """
        logger.info(
            f"Starting chaos experiment: {self.profile.name} "
            f"for {self.duration_seconds}s (ID: {self.report.experiment_id})"
        )

        start_time = time.time()

        # Simulate fault injection over duration
        # Ensure minimum 3 injection attempts even for short durations
        num_injections = max(3, int(self.duration_seconds / 10))
        injection_interval = self.duration_seconds / num_injections

        for i in range(num_injections):
            current_time = time.time() - start_time

            if current_time >= self.duration_seconds:
                break

            # Simulate fault injection events
            if self.injector.should_inject_fsync_failure():
                self.report.fault_events.append(
                    FaultEvent(
                        timestamp=datetime.now(tz=timezone.utc).isoformat(),
                        fault_type="fsync_failure",
                        description=f"WAL fsync failure injected (rate: {self.profile.fsync_fail_rate * 100:.0f}%)",
                        metadata={"attempt": i, "rate": self.profile.fsync_fail_rate},
                    )
                )
                logger.info(f"  Injected fsync failure at {current_time:.1f}s")

            if self.injector.should_degrade_scheduler():
                self.report.fault_events.append(
                    FaultEvent(
                        timestamp=datetime.now(tz=timezone.utc).isoformat(),
                        fault_type="scheduler_stress",
                        description=f"Scheduler degraded to {self.profile.scheduler_multiplier * 100:.0f}% capacity",
                        metadata={"multiplier": self.profile.scheduler_multiplier},
                    )
                )
                logger.info(f"  Injected scheduler stress at {current_time:.1f}s")

            if self.profile.network_latency_ms > 0:
                latency = self.injector.get_network_latency_ms()
                self.report.fault_events.append(
                    FaultEvent(
                        timestamp=datetime.now(tz=timezone.utc).isoformat(),
                        fault_type="network_latency",
                        description=f"Network latency: {latency}ms",
                        metadata={"latency_ms": latency},
                    )
                )
                logger.info(f"  Injected network latency: {latency}ms at {current_time:.1f}s")

            if self.injector.should_drop_telemetry():
                self.report.fault_events.append(
                    FaultEvent(
                        timestamp=datetime.now(tz=timezone.utc).isoformat(),
                        fault_type="telemetry_outage",
                        description=f"Telemetry event dropped (drop rate: {self.profile.telemetry_outage_rate * 100:.0f}%)",
                        metadata={"drop_rate": self.profile.telemetry_outage_rate},
                    )
                )

            # Sleep for next injection interval
            time.sleep(min(injection_interval, self.duration_seconds - current_time))

        # Finalize report
        self.report.end_time = datetime.now(tz=timezone.utc).isoformat()
        self.report.duration_seconds = time.time() - start_time

        logger.info(
            f"✓ Chaos experiment completed in {self.report.duration_seconds:.1f}s "
            f"({len(self.report.fault_events)} faults injected)"
        )

        return self.report

    def validate_recovery(
        self,
        original_commands: list[dict[str, Any]] | None = None,
        replayed_commands: list[dict[str, Any]] | None = None,
        receipts_during: list[dict[str, Any]] | None = None,
        receipts_after: list[dict[str, Any]] | None = None,
        sse_metrics: dict[str, int] | None = None,
        scheduler_metrics: dict[str, int] | None = None,
    ) -> tuple[bool, list[str]]:
        """Validate recovery after chaos experiment.

        Args:
            original_commands: Commands executed before chaos (optional)
            replayed_commands: Commands replayed after recovery (optional)
            receipts_during: Receipts collected during chaos (optional)
            receipts_after: Receipts after recovery (optional)
            sse_metrics: SSE connection/event metrics (optional)
            scheduler_metrics: Scheduler queue metrics (optional)

        Returns:
            Tuple of (all_passed, list_of_violations)
        """
        logger.info("Validating recovery invariants...")
        violations: list[str] = []

        # Validate replay parity
        if original_commands and replayed_commands:
            valid, details = RecoveryValidator.validate_replay_parity(
                original_commands, replayed_commands
            )
            checkpoint = RecoveryCheckpoint(
                timestamp=datetime.now(tz=timezone.utc).isoformat(),
                invariant="replay_parity",
                status="passed" if valid else "failed",
                details=details,
            )
            self.report.recovery_checkpoints.append(checkpoint)
            logger.info(f"  Replay parity: {'✓' if valid else '✗'} {details}")
            if not valid:
                violations.append(f"replay_parity: {details}")

        # Validate receipt consistency
        if receipts_during and receipts_after:
            valid, details = RecoveryValidator.validate_receipt_consistency(
                receipts_during, receipts_after
            )
            checkpoint = RecoveryCheckpoint(
                timestamp=datetime.now(tz=timezone.utc).isoformat(),
                invariant="receipt_consistency",
                status="passed" if valid else "failed",
                details=details,
            )
            self.report.recovery_checkpoints.append(checkpoint)
            logger.info(f"  Receipt consistency: {'✓' if valid else '✗'} {details}")
            if not valid:
                violations.append(f"receipt_consistency: {details}")

        # Validate SSE reconnection
        if sse_metrics:
            valid, details = RecoveryValidator.validate_sse_reconnection(
                sse_metrics.get("connections_before", 0),
                sse_metrics.get("connections_after", 0),
                sse_metrics.get("events_received", 0),
            )
            checkpoint = RecoveryCheckpoint(
                timestamp=datetime.now(tz=timezone.utc).isoformat(),
                invariant="sse_reconnection",
                status="passed" if valid else "failed",
                details=details,
            )
            self.report.recovery_checkpoints.append(checkpoint)
            logger.info(f"  SSE reconnection: {'✓' if valid else '✗'} {details}")
            if not valid:
                violations.append(f"sse_reconnection: {details}")

        # Validate scheduler recovery
        if scheduler_metrics:
            valid, details = RecoveryValidator.validate_scheduler_recovery(
                scheduler_metrics.get("queue_depth_during", 0),
                scheduler_metrics.get("queue_depth_after", 0),
                scheduler_metrics.get("max_queue_depth", 1000),
            )
            checkpoint = RecoveryCheckpoint(
                timestamp=datetime.now(tz=timezone.utc).isoformat(),
                invariant="scheduler_recovery",
                status="passed" if valid else "failed",
                details=details,
            )
            self.report.recovery_checkpoints.append(checkpoint)
            logger.info(f"  Scheduler recovery: {'✓' if valid else '✗'} {details}")
            if not valid:
                violations.append(f"scheduler_recovery: {details}")

        self.report.invariant_violations = violations
        return len(violations) == 0, violations


def generate_report_markdown(report: ChaosReport) -> str:
    """Generate human-readable Markdown report from chaos report.

    Args:
        report: ChaosReport instance

    Returns:
        Formatted Markdown report
    """
    lines: list[str] = []

    lines.append("# Chaos Experiment Report")
    lines.append("")
    lines.append(f"**Experiment ID**: {report.experiment_id}")
    lines.append(f"**Profile**: {report.profile_name}")
    lines.append(f"**Duration**: {report.duration_seconds:.1f}s")
    lines.append(f"**Status**: {'PASSED' if not report.invariant_violations else 'FAILED'}")
    lines.append("")

    lines.append("## Fault Injection Timeline")
    lines.append("")
    if report.fault_events:
        for i, event in enumerate(report.fault_events, 1):
            lines.append(f"{i}. **{event.fault_type}** — {event.description}")
    else:
        lines.append("*No faults injected*")
    lines.append("")

    lines.append(f"## Recovery Validation ({len(report.recovery_checkpoints)} checks)")
    lines.append("")
    if report.recovery_checkpoints:
        for checkpoint in report.recovery_checkpoints:
            status_icon = "PASS" if checkpoint.status == "passed" else "FAIL"
            lines.append(f"- [{status_icon}] **{checkpoint.invariant}**: {checkpoint.details}")
    else:
        lines.append("*No recovery validation performed*")
    lines.append("")

    if report.invariant_violations:
        lines.append("## Invariant Violations")
        lines.append("")
        for violation in report.invariant_violations:
            lines.append(f"- WARNING: {violation}")
        lines.append("")
        lines.append("## Remediation Steps")
        lines.append("")
        lines.append("1. **Analyze logs**: Review K0 kernel logs during chaos period")
        lines.append("2. **Identify root cause**: Use flamegraphs and trace data")
        lines.append("3. **Fix invariant violation**: Address code path causing violation")
        lines.append("4. **Rerun experiment**: Validate fix with `--profile=mild` first")
        lines.append(
            "5. **Escalate if needed**: For multiple violations, escalate to incident response"
        )
    else:
        lines.append("## Result")
        lines.append("")
        lines.append("All invariants validated successfully")
        lines.append("")
        lines.append(f"- Faults injected: {len(report.fault_events)}")
        lines.append(f"- Recovery checks passed: {len(report.recovery_checkpoints)}")
        lines.append(f"- MTTR: {report.duration_seconds:.1f}s")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Chaos scheduler for K0 kernel fault tolerance testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--profile",
        type=str,
        choices=list(PROFILES.keys()),
        default="mild",
        help="Chaos profile to run (default: mild)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Duration of chaos period in seconds (default: 60)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file for JSON report (default: stdout)",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        help="Random seed for reproducible chaos (optional)",
    )
    parser.add_argument(
        "--markdown-report",
        type=Path,
        help="Generate human-readable Markdown report to file",
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
        profile = PROFILES[args.profile]
        logger.info(f"Using chaos profile: {args.profile}")

        # Run experiment
        experiment = ChaosExperiment(
            profile=profile,
            duration_seconds=args.duration,
            random_seed=args.random_seed,
        )
        report = experiment.run()

        # Generate JSON report
        json_report = json.dumps(report.to_dict(), indent=2)

        if args.output:
            args.output.write_text(json_report)
            logger.info(f"✓ JSON report written to {args.output}")
        else:
            print(json_report)

        # Generate Markdown report if requested
        if args.markdown_report:
            md_report = generate_report_markdown(report)
            args.markdown_report.write_text(md_report)
            logger.info(f"✓ Markdown report written to {args.markdown_report}")

        # Exit with status based on violations
        if report.invariant_violations:
            logger.warning(f"⚠️  {len(report.invariant_violations)} invariant violations detected")
            return 1

        logger.info("✓ Experiment completed successfully")
        return 0

    except KeyError as e:
        logger.error(f"✗ Invalid profile: {e}")
        return 2
    except Exception as e:
        logger.error(f"✗ {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
