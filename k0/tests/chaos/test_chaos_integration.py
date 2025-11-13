"""Ward integration tests for multi-subsystem chaos (Issue 9.1.4 Phase 3)."""

from __future__ import annotations

import errno
import random
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st
from ward import test

from k0.chaos.toggles import apply_scheduler_starvation, should_drop_telemetry
from k0.kernel.config import ChaosSettings
from k0.obs.metrics import MetricsExporter
from k0.qos.scheduler import Scheduler, SchedulerCapacityError, SchedulerProfile
from k0.storage.wal import WalEntry, WriteAheadLog
from k0.tests.chaos.fixtures import (
    chaos_test_db,
    metric_value,
    metrics_exporter,
    sample_entry,
)


@test("integration: system survives multi-subsystem chaos injection")
def _(
    exporter: MetricsExporter = metrics_exporter,
    entry: WalEntry = sample_entry,
    db_path: Path = chaos_test_db,
) -> None:
    # Use moderate failure rates for integration test to ensure mix of success/failure
    config = ChaosSettings(
        enabled=True,
        wal_fsync_fail_rate=0.3,  # 30% failure allows both successes and failures
        scheduler_starvation_multiplier=0.5,  # 50% capacity reduction
        network_latency_ms=100,
        telemetry_outage_rate=0.3,
        random_seed=54321,
    )
    random.seed(54321)  # Set global random seed

    # Initialize all subsystems with chaos enabled
    wal = WriteAheadLog()

    base_profile = SchedulerProfile(
        name="integration-chaos",
        description="Multi-subsystem chaos test",
        port_limits={"command": 20},
        default_port_limit=10,
    )
    starved_profile = apply_scheduler_starvation(base_profile, config, exporter)
    scheduler = Scheduler(starved_profile)

    # Execute operations with chaos across all subsystems
    wal_successes = 0
    wal_failures = 0
    scheduler_successes = 0
    scheduler_failures = 0
    telemetry_drops = 0
    active_tokens = []

    for _ in range(100):
        # WAL operations with fsync chaos
        try:
            wal.append(entry)
            wal.fsync(chaos_config=config, metrics_exporter=exporter)
            wal_successes += 1
        except OSError as e:
            if e.errno == errno.EIO:
                wal_failures += 1
            else:
                raise

        # Scheduler operations with capacity chaos
        # Accumulate tokens without releasing to trigger capacity errors
        try:
            token = scheduler.acquire(band="GREEN", port="command", cost=1)
            scheduler_successes += 1
            active_tokens.append(token)
        except SchedulerCapacityError:
            scheduler_failures += 1

        # Telemetry chaos
        if should_drop_telemetry(config):
            telemetry_drops += 1

    # Clean up scheduler tokens
    for token in active_tokens:
        token.release()

    # Verify system survived and processed some operations
    assert wal_successes > 0, "WAL must process some operations despite chaos"
    assert (
        scheduler_successes > 0
    ), "Scheduler must process some operations despite chaos"

    # Verify chaos actually injected faults
    assert wal_failures > 0, "Expected WAL fsync failures with high fail_rate"
    assert (
        scheduler_failures > 0
    ), "Expected scheduler capacity errors with high starvation"
    assert telemetry_drops > 0, "Expected telemetry drops with high outage_rate"

    # Verify telemetry captured chaos events
    fsync_injected = metric_value(exporter, "k0_kernel_chaos_fsync_injected_total")
    scheduler_throttled = metric_value(
        exporter, "k0_kernel_scheduler_throttled_multiplier"
    )

    assert fsync_injected is not None and fsync_injected > 0
    assert scheduler_throttled == config.scheduler_starvation_multiplier


@test("hypothesis: system maintains integrity under varied chaos conditions")
def _(
    exporter: MetricsExporter = metrics_exporter,
    db_path: Path = chaos_test_db,
) -> None:
    @settings(max_examples=25, deadline=1000)
    @given(
        fsync_fail_rate=st.floats(min_value=0.0, max_value=0.3),
        starvation_multiplier=st.floats(min_value=0.3, max_value=1.0),
        outage_rate=st.floats(min_value=0.0, max_value=0.2),
        num_ops=st.integers(min_value=10, max_value=50),
    )
    def runner(
        fsync_fail_rate: float,
        starvation_multiplier: float,
        outage_rate: float,
        num_ops: int,
    ) -> None:
        config = ChaosSettings(
            enabled=True,
            wal_fsync_fail_rate=fsync_fail_rate,
            scheduler_starvation_multiplier=starvation_multiplier,
            telemetry_outage_rate=outage_rate,
            random_seed=42,
        )

        wal = WriteAheadLog()

        base_profile = SchedulerProfile(
            name="hypothesis-integration",
            description="Property-based chaos integration",
            port_limits={"command": 30},
            default_port_limit=15,
        )
        starved_profile = apply_scheduler_starvation(base_profile, config, exporter)
        scheduler = Scheduler(starved_profile)

        entry = WalEntry(
            tenant_id="tenant-integration",
            space_id="space-integration",
            device_id="device-integration",
            idem_key=f"idem-integration-{fsync_fail_rate}",
            topic="memory.delta",
            schema_uri="schema://memory.delta",
            schema_version="1.0",
            body=b'{"integration": "chaos"}',
            envelope_json="{}",
            commit_ts="2025-10-05T14:00:00Z",
            payload_sha256="0" * 64,
        )

        total_successes = 0
        total_failures = 0

        for _ in range(num_ops):
            wal_success = False
            try:
                wal.append(entry)
                wal.fsync(chaos_config=config, metrics_exporter=exporter)
                wal_success = True
            except OSError as e:
                if e.errno == errno.EIO:
                    pass  # Expected chaos failure
                else:
                    raise

            scheduler_success = False
            try:
                token = scheduler.acquire(band="GREEN", port="command", cost=1)
                scheduler_success = True
                token.release()
            except SchedulerCapacityError:
                pass  # Expected capacity error

            if wal_success and scheduler_success:
                total_successes += 1
            else:
                total_failures += 1

        # System must process at least some operations
        assert total_successes > 0, (
            f"Expected some successes with fsync_fail_rate={fsync_fail_rate}, "
            f"starvation={starvation_multiplier}, outage_rate={outage_rate}"
        )

        # Verify operations completed
        assert total_successes + total_failures == num_ops

    runner()

