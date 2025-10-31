from __future__ import annotations

import logging
import math
import os
import time
from statistics import median

import pytest

import k0.policy.pep_syscall as pep_syscall
from tests.scripts import test_k0_bootstrap_harness as harness_tests

# ADR-0089: PEM latency budget enforcement for command port decisions.
ALLOW_MANIFEST = harness_tests.POLICY_FIXTURES_DIR / "allow_all.json"
ITER_ENV_VAR = "K0_PEM_BENCH_ITERATIONS"
DEFAULT_ITERATIONS = 200
WARMUP_REQUESTS = 40
BUDGET_TARGET_US = 50.0
BUDGET_SLACK_US = 1.0


def _parse_metric_value(metrics_blob: str, metric: str, labels: dict[str, str]) -> float:
    label_text = ",".join(f'{key}="{value}"' for key, value in sorted(labels.items()))
    token = f"{metric}{{{label_text}}}"
    for line in metrics_blob.splitlines():
        if not line.startswith(token):
            continue
        try:
            return float(line.split(" ", 1)[1])
        except (IndexError, ValueError):
            return 0.0
    return 0.0


@pytest.mark.performance
@pytest.mark.parametrize("manifest_path", [ALLOW_MANIFEST])
def test_pem_evaluation_latency_budget(
    tmp_path, monkeypatch, manifest_path: os.PathLike[str]
) -> None:
    iterations = int(os.getenv(ITER_ENV_VAR, str(DEFAULT_ITERATIONS)))
    warmup = min(WARMUP_REQUESTS, max(10, iterations // 5))

    with harness_tests.run_with_manifest(
        tmp_path,
        monkeypatch,
        manifest_path=manifest_path,
    ) as (app, client, contract, signing_key):
        # Fresh app start ensures clean cache state.
        # No need to clear caches - the app was just created.
        # Manifest will be loaded on first evaluate_envelope call below.

        prototype_envelope = harness_tests._make_signed_envelope(contract, signing_key)

        # Warm up the manifest cache to stabilize measurements (single file I/O cost).
        # Without this, first few calls pay the cost of reading/parsing JSON from disk.
        _warmup_input = {key: value for key, value in prototype_envelope.items() if key != "sig"}
        for _ in range(warmup):
            pep_syscall.evaluate_envelope(_warmup_input)

        # Measure raw PEM evaluation latency (no HTTP overhead) with warm cache.
        evaluation_input = {key: value for key, value in prototype_envelope.items() if key != "sig"}
        durations_us: list[float] = []

        # Suppress logging during measurements to avoid I/O overhead affecting latency measurements.
        pep_logger = logging.getLogger("k0.policy.pep_syscall")
        old_level = pep_logger.level
        pep_logger.setLevel(logging.WARNING)

        try:
            for _ in range(iterations):
                start_ns = time.perf_counter_ns()
                decision = pep_syscall.evaluate_envelope(evaluation_input)
                end_ns = time.perf_counter_ns()
                durations_us.append((end_ns - start_ns) / 1_000.0)
                assert decision.admit, "ALLOW manifest should admit the envelope"
        finally:
            pep_logger.setLevel(old_level)

        trim_evaluations = min(len(durations_us) - 1, max(5, len(durations_us) // 10))
        if trim_evaluations > 0:
            durations_us = durations_us[trim_evaluations:]

        durations_us.sort()
        index = max(0, math.ceil(0.95 * len(durations_us)) - 1)
        p95_latency_us = durations_us[index]
        budget_with_slack = BUDGET_TARGET_US + BUDGET_SLACK_US
        assert p95_latency_us <= budget_with_slack, (
            f"Expected PEM p95 latency <= {budget_with_slack:.1f}µs (target {BUDGET_TARGET_US}µs), "
            f"observed {p95_latency_us:.2f}µs"
        )
        # Provide additional visibility for diagnostics if budgets are tight.
        median_latency_us = median(durations_us) if durations_us else 0.0
        print(
            f"PEM latency - p95: {p95_latency_us:.2f}µs, median: {median_latency_us:.2f}µs, samples: {len(durations_us)}"
        )
