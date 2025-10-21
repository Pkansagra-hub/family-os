#!/usr/bin/env python3
"""
Generate chaos engineering test reports from test runs.

Usage:
    # Single profile report
    python generate_chaos_report.py \
        --profile moderate \
        --fsync-fail-rate 0.05 \
        --scheduler-multiplier 0.5 \
        --output chaos_report.json

    # Consolidated report from multiple runs
    python generate_chaos_report.py \
        --consolidate \
        --input-dir chaos-artifacts \
        --output chaos_summary.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_ward_output(output_path: Path) -> dict[str, Any]:
    """Parse Ward test output file to extract results."""
    if not output_path.exists():
        return {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "duration_seconds": 0.0,
            "failures": [],
        }

    content = output_path.read_text()

    # Extract test counts
    # Example: "298 Tests Passing (99.3%), 2 Failures (0.7%)"
    test_summary_match = re.search(
        r"(\d+)\s+Tests?\s+Passing.*?,\s*(\d+)\s+Failures?", content, re.IGNORECASE
    )
    if test_summary_match:
        passed = int(test_summary_match.group(1))
        failed = int(test_summary_match.group(2))
        total = passed + failed
    else:
        # Fallback: count PASS/FAIL markers
        passed = len(re.findall(r"PASS", content))
        failed = len(re.findall(r"FAIL", content))
        total = passed + failed

    # Extract duration
    # Example: "in 44.26 seconds"
    duration_match = re.search(r"in\s+([\d.]+)\s+seconds?", content, re.IGNORECASE)
    duration = float(duration_match.group(1)) if duration_match else 0.0

    # Extract failure details
    failures = []
    # Example: "FAIL test_chaos_integration:114 "hypothesis: system maintains integrity""
    failure_matches = re.finditer(
        r"FAIL\s+([\w_:]+)\s+[\"']([^\"']+)[\"']", content, re.MULTILINE
    )
    for match in failure_matches:
        failures.append({"test_id": match.group(1), "description": match.group(2)})

    return {
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "skipped": 0,  # Ward doesn't report skipped separately in summary
        "duration_seconds": duration,
        "failures": failures,
    }


def generate_single_profile_report(
    profile: str,
    fsync_fail_rate: float,
    scheduler_multiplier: float,
    network_latency_ms: int,
    telemetry_outage_rate: float,
    test_output_path: Path | None = None,
) -> dict[str, Any]:
    """Generate report for a single chaos profile."""
    timestamp = datetime.now(timezone.utc).isoformat()

    # Parse test results if available
    test_results = {}
    if test_output_path and test_output_path.exists():
        test_results = parse_ward_output(test_output_path)

    report = {
        "timestamp": timestamp,
        "profile": profile,
        "chaos_settings": {
            "fsync_fail_rate": fsync_fail_rate,
            "scheduler_starvation_multiplier": scheduler_multiplier,
            "network_latency_ms": network_latency_ms,
            "telemetry_outage_rate": telemetry_outage_rate,
        },
        "test_results": test_results,
        "status": "passed" if test_results.get("failed", 1) == 0 else "failed",
        "summary": {
            "total_tests": test_results.get("total_tests", 0),
            "passed": test_results.get("passed", 0),
            "failed": test_results.get("failed", 0),
            "success_rate": (
                round(test_results["passed"] / test_results["total_tests"] * 100, 2)
                if test_results.get("total_tests", 0) > 0
                else 0.0
            ),
            "duration_seconds": test_results.get("duration_seconds", 0.0),
        },
    }

    # Add failure details if any
    if test_results.get("failures"):
        report["failures"] = test_results["failures"]

    return report


def consolidate_reports(input_dir: Path) -> dict[str, Any]:
    """Consolidate multiple chaos profile reports into a summary."""
    timestamp = datetime.now(timezone.utc).isoformat()

    profiles = []
    total_tests = 0
    total_passed = 0
    total_failed = 0
    total_duration = 0.0

    # Find all JSON reports in input directory
    for report_file in input_dir.rglob("chaos_report_*.json"):
        try:
            report = json.loads(report_file.read_text())
            profiles.append(report)

            total_tests += report.get("summary", {}).get("total_tests", 0)
            total_passed += report.get("summary", {}).get("passed", 0)
            total_failed += report.get("summary", {}).get("failed", 0)
            total_duration += report.get("summary", {}).get("duration_seconds", 0.0)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Warning: Failed to parse {report_file}: {e}", file=sys.stderr)
            continue

    consolidated = {
        "timestamp": timestamp,
        "total_tests": total_tests,
        "passed": total_passed,
        "failed": total_failed,
        "success_rate": (
            round(total_passed / total_tests * 100, 2) if total_tests > 0 else 0.0
        ),
        "duration_seconds": round(total_duration, 2),
        "profiles": profiles,
        "status": "passed" if total_failed == 0 else "failed",
    }

    return consolidated


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate chaos engineering test reports"
    )

    # Single profile mode
    parser.add_argument(
        "--profile", help="Chaos profile name (mild/moderate/aggressive)"
    )
    parser.add_argument("--fsync-fail-rate", type=float, help="WAL fsync failure rate")
    parser.add_argument(
        "--scheduler-multiplier", type=float, help="Scheduler capacity multiplier"
    )
    parser.add_argument(
        "--network-latency", type=int, help="Network latency injection (ms)"
    )
    parser.add_argument("--telemetry-outage", type=float, help="Telemetry drop rate")
    parser.add_argument(
        "--test-output", type=Path, help="Path to Ward test output file"
    )

    # Consolidate mode
    parser.add_argument(
        "--consolidate", action="store_true", help="Consolidate multiple reports"
    )
    parser.add_argument(
        "--input-dir", type=Path, help="Directory containing chaos report JSONs"
    )

    # Common
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output JSON file path",
    )

    args = parser.parse_args()

    try:
        if args.consolidate:
            if not args.input_dir:
                print(
                    "Error: --input-dir required for consolidate mode", file=sys.stderr
                )
                return 1

            report = consolidate_reports(args.input_dir)
        else:
            if not all(
                [
                    args.profile,
                    args.fsync_fail_rate is not None,
                    args.scheduler_multiplier is not None,
                    args.network_latency is not None,
                    args.telemetry_outage is not None,
                ]
            ):
                print(
                    "Error: --profile, --fsync-fail-rate, --scheduler-multiplier, "
                    "--network-latency, and --telemetry-outage required",
                    file=sys.stderr,
                )
                return 1

            report = generate_single_profile_report(
                profile=args.profile,
                fsync_fail_rate=args.fsync_fail_rate,
                scheduler_multiplier=args.scheduler_multiplier,
                network_latency_ms=args.network_latency,
                telemetry_outage_rate=args.telemetry_outage,
                test_output_path=args.test_output,
            )

        # Write report
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2))

        print(f"✅ Chaos report generated: {args.output}")
        print(f"Status: {report['status'].upper()}")
        print(
            f"Tests: {report.get('passed', report.get('summary', {}).get('passed', 0))}"
            f"/{report.get('total_tests', report.get('summary', {}).get('total_tests', 0))} passed"
        )

        return 0 if report["status"] == "passed" else 1

    except Exception as e:
        print(f"Error generating chaos report: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
