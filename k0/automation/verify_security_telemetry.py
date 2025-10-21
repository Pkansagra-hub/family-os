"""CI guard that validates security telemetry snapshots for Issue 8.2.3.

This script parses the Prometheus snapshot files written by the Ward security
fuzz suite and asserts that every threat scenario covered by the plan emits the
expected counters and labels. The check fails if any metric is missing or if its
value never increments, enforcing the 100% scenario coverage acceptance
threshold tracked in `k0/plan.md`.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from prometheus_client.parser import text_string_to_metric_families

SNAPSHOT_FILENAMES = (
    "security-gate.prom",
    "security-ledger.prom",
)


@dataclass(frozen=True)
class MetricExpectation:
    name: str
    labels: Mapping[str, str]


REQUIRED_EXPECTATIONS: tuple[MetricExpectation, ...] = (
    # Gate enforcement signals
    MetricExpectation(
        name="k0_kernel_k0_signature_verified_total",
        labels={"key_state": "ACTIVE", "key_version": "v1-active"},
    ),
    MetricExpectation(
        name="k0_kernel_k0_signature_verification_failed_total",
        labels={"reason": "INVALID_SIGNATURE"},
    ),
    MetricExpectation(
        name="k0_kernel_k0_provisioning_denial_total",
        labels={"reason": "DEVICE_NOT_PROVISIONED"},
    ),
    MetricExpectation(
        name="k0_kernel_k0_schema_denial_total",
        labels={
            "reason": "SCHEMA_BLOCKED",
            "schema_uri": "schema://memory.blocked",
            "schema_version": "1.0",
        },
    ),
    # Ledger enforcement signals
    MetricExpectation(
        name="k0_kernel_k0_idem_commit_recorded_total",
        labels={"state": "COMMITTED"},
    ),
    MetricExpectation(
        name="k0_kernel_k0_idem_lookup_total",
        labels={"outcome": "hit", "state": "COMMITTED"},
    ),
    MetricExpectation(
        name="k0_kernel_k0_idem_duplicate_detected_total",
        labels={"state": "COMMITTED"},
    ),
)


def _load_samples(paths: Iterable[Path]) -> Mapping[str, list[object]]:
    from collections import defaultdict

    samples: dict[str, list[object]] = defaultdict(list)
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"Missing telemetry snapshot: {path}")
        content = path.read_text(encoding="utf-8")
        for family in text_string_to_metric_families(content):
            for sample in family.samples:
                samples[sample.name].append(sample)
    return samples


def _matches(sample: object, labels: Mapping[str, str]) -> bool:
    sample_labels = getattr(sample, "labels", {})
    return all(sample_labels.get(key) == value for key, value in labels.items())


def _value(sample: object) -> float:
    return float(getattr(sample, "value", 0.0))


def verify(directory: Path) -> None:
    snapshot_paths = [directory / filename for filename in SNAPSHOT_FILENAMES]
    samples = _load_samples(snapshot_paths)

    missing: list[str] = []
    zero_valued: list[str] = []

    for expectation in REQUIRED_EXPECTATIONS:
        sample_candidates = samples.get(expectation.name, [])
        filtered = [
            sample
            for sample in sample_candidates
            if _matches(sample, expectation.labels)
        ]
        if not filtered:
            missing.append(f"{expectation.name} {dict(expectation.labels)}")
            continue
        if not any(_value(sample) > 0.0 for sample in filtered):
            zero_valued.append(f"{expectation.name} {dict(expectation.labels)}")

    if missing or zero_valued:
        message_lines = [
            "Security telemetry verification failed:",
        ]
        if missing:
            message_lines.append("  Missing metrics:")
            message_lines.extend(f"    - {entry}" for entry in missing)
        if zero_valued:
            message_lines.append("  Zero-valued metrics:")
            message_lines.extend(f"    - {entry}" for entry in zero_valued)
        raise SystemExit("\n".join(message_lines))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Ward security telemetry snapshots",
    )
    parser.add_argument(
        "--directory",
        "-d",
        type=Path,
        default=None,
        help=(
            "Directory containing security telemetry snapshots. "
            "Defaults to $WARD_SECURITY_SNAPSHOT_DIR or "
            "artifacts/security-telemetry."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.directory is not None:
        directory = args.directory
    else:
        env_dir = os.environ.get("WARD_SECURITY_SNAPSHOT_DIR")
        directory = Path(env_dir) if env_dir else Path("artifacts/security-telemetry")

    if not directory.exists():
        raise SystemExit(f"Telemetry directory not found: {directory}")

    verify(directory)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
