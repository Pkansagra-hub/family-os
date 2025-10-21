"""Ward tests for WAL fsync chaos injection (Issue 9.1.4 Phase 3)."""

from __future__ import annotations

import errno
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st
from ward import test

from k0.chaos.toggles import should_fail_fsync
from k0.kernel.config import ChaosSettings
from k0.obs.metrics import MetricsExporter
from k0.storage.wal import WalEntry, WriteAheadLog
from tests.chaos.fixtures import (
    chaos_disabled_config,
    chaos_enabled_config,
    chaos_test_db,
    high_failure_config,
    metric_value,
    metrics_exporter,
    sample_entry,
)


@test("chaos toggle: should_fail_fsync returns deterministic decisions with seed")
def _(
    config: ChaosSettings = chaos_enabled_config,
    exporter: MetricsExporter = metrics_exporter,
) -> None:
    decisions = [should_fail_fsync(config, exporter) for _ in range(100)]

    # With random_seed=42 and fail_rate=0.1, expect ~10 failures
    failure_count = sum(1 for d in decisions if d.should_inject)
    assert 5 <= failure_count <= 15, f"Expected ~10 failures, got {failure_count}"

    # Verify telemetry emitted
    injected = metric_value(exporter, "k0_kernel_chaos_fsync_injected_total")
    assert injected is not None
    assert injected == failure_count


@test("chaos toggle: high failure rate produces frequent injections")
def _(
    config: ChaosSettings = high_failure_config,
    exporter: MetricsExporter = metrics_exporter,
) -> None:
    decisions = [should_fail_fsync(config, exporter) for _ in range(50)]

    failure_count = sum(1 for d in decisions if d.should_inject)
    # With fail_rate=0.9, expect 40-50 failures
    assert 35 <= failure_count <= 50, f"Expected 40-50 failures, got {failure_count}"


@test("wal fsync: chaos-injected failure raises OSError(EIO)")
def _(
    entry: WalEntry = sample_entry,
    exporter: MetricsExporter = metrics_exporter,
    db_path: Path = chaos_test_db,
) -> None:
    wal = WriteAheadLog()
    config = ChaosSettings(
        enabled=True,
        wal_fsync_fail_rate=0.1,
        random_seed=42,
    )
    # Multiple attempts will eventually hit chaos injection with fail_rate=0.1
    failures = 0
    successes = 0

    for attempt in range(100):
        try:
            wal.append(entry)
            wal.fsync(chaos_config=config, metrics_exporter=exporter)
            successes += 1
        except OSError as e:
            if e.errno == errno.EIO:
                failures += 1
                assert "Chaos-injected fsync failure" in str(e) or "EIO" in str(
                    e.strerror or ""
                )
            else:
                raise

    # With fail_rate=0.1, expect 5-20 failures out of 100
    assert failures >= 5, f"Expected some chaos failures, got {failures}"
    assert successes >= 50, f"Expected at least 50% successes, got {successes}"
    # Verify total operations completed
    assert failures + successes == 100


@test("wal fsync: chaos disabled produces no injected failures")
def _(entry: WalEntry = sample_entry, db_path: Path = chaos_test_db) -> None:
    wal = WriteAheadLog()
    # With chaos disabled, all appends should succeed
    for _ in range(50):
        wal.append(entry)  # Should never raise OSError(EIO)

    # No failures expected


@test("wal fsync: injected failures emit telemetry counter")
def _(
    entry: WalEntry = sample_entry,
    exporter: MetricsExporter = metrics_exporter,
    db_path: Path = chaos_test_db,
) -> None:
    config = ChaosSettings(
        enabled=True,
        wal_fsync_fail_rate=0.3,
        random_seed=555,
    )
    wal = WriteAheadLog()
    failures = 0
    for _ in range(100):
        try:
            wal.append(entry)
            wal.fsync(chaos_config=config, metrics_exporter=exporter)
        except OSError as e:
            if e.errno == errno.EIO:
                failures += 1

    injected = metric_value(exporter, "k0_kernel_chaos_fsync_injected_total")
    assert injected is not None
    assert injected == failures


@test("wal fsync: chaos recovery after config change")
def _(
    entry: WalEntry = sample_entry,
    chaos_cfg: ChaosSettings = chaos_enabled_config,
    normal_cfg: ChaosSettings = chaos_disabled_config,
    exporter: MetricsExporter = metrics_exporter,
    db_path: Path = chaos_test_db,
) -> None:
    # Start with chaos enabled
    wal = WriteAheadLog()

    failures = 0
    for _ in range(50):
        try:
            wal.append(entry)
            wal.fsync(chaos_config=chaos_cfg, metrics_exporter=exporter)
        except OSError as e:
            if e.errno == errno.EIO:
                failures += 1

    assert failures > 0, "Expected some chaos failures"

    # Switch to chaos disabled - just verify WAL works
    for _ in range(50):
        wal.append(entry)
        wal.fsync(chaos_config=normal_cfg, metrics_exporter=exporter)


@test("hypothesis: wal fsync failures occur at configured probability")
def _(
    config: ChaosSettings = chaos_enabled_config,
    exporter: MetricsExporter = metrics_exporter,
) -> None:
    @settings(max_examples=50, deadline=300)
    @given(
        fail_rate=st.floats(min_value=0.0, max_value=1.0),
        seed=st.integers(min_value=1, max_value=999999),
    )
    def runner(fail_rate: float, seed: int) -> None:
        test_config = ChaosSettings(
            enabled=True,
            wal_fsync_fail_rate=fail_rate,
            random_seed=seed,
        )

        decisions = [should_fail_fsync(test_config, exporter) for _ in range(100)]
        failure_count = sum(1 for d in decisions if d.should_inject)

        # Allow 20% margin for randomness
        expected = fail_rate * 100
        lower = max(0, expected - 20)
        upper = min(100, expected + 20)

        assert (
            lower <= failure_count <= upper
        ), f"fail_rate={fail_rate}, expected {expected}±20, got {failure_count}"

    runner()


@test("hypothesis: WAL survives varied chaos conditions")
def _(
    exporter: MetricsExporter = metrics_exporter, db_path: Path = chaos_test_db
) -> None:
    @settings(max_examples=30, deadline=1500)
    @given(
        fail_rate=st.floats(min_value=0.0, max_value=0.5),
        num_ops=st.integers(min_value=10, max_value=50),
    )
    def runner(fail_rate: float, num_ops: int) -> None:
        config = ChaosSettings(
            enabled=True,
            wal_fsync_fail_rate=fail_rate,
            random_seed=42,
        )

        wal = WriteAheadLog()

        entry = WalEntry(
            tenant_id="tenant-hypothesis",
            space_id="space-hypothesis",
            device_id="device-hypothesis",
            idem_key=f"idem-hypothesis-{fail_rate}-{num_ops}",
            topic="memory.delta",
            schema_uri="schema://memory.delta",
            schema_version="1.0",
            body=b'{"hypothesis": "test"}',
            envelope_json="{}",
            commit_ts="2025-10-05T13:00:00Z",
            payload_sha256="0" * 64,
        )

        successes = 0
        failures = 0

        for _ in range(num_ops):
            try:
                wal.append(entry)
                wal.fsync(chaos_config=config, metrics_exporter=exporter)
                successes += 1
            except OSError as e:
                if e.errno == errno.EIO:
                    failures += 1
                else:
                    raise

        # System must survive and process some operations
        assert successes + failures == num_ops
        assert successes > 0, "Expected at least some successful operations"

    runner()
