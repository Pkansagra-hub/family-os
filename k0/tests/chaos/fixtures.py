"""Chaos test fixtures for Ward."""

from __future__ import annotations

import random
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

from ward import fixture

from k0.automation.migrate import apply_migrations
from k0.kernel.config import ChaosSettings
from k0.obs.metrics import MetricsExporter
from k0.qos.scheduler import SchedulerProfile
from k0.storage.wal import WalEntry
from k0.uow.connection_pool import configure_pool, shutdown_pool


@fixture
def chaos_enabled_config() -> ChaosSettings:
    """Chaos config with deterministic seed for reproducible tests."""
    # Set global random seed for deterministic testing
    random.seed(42)
    return ChaosSettings(
        enabled=True,
        wal_fsync_fail_rate=0.1,
        scheduler_starvation_multiplier=0.3,
        network_latency_ms=100,
        telemetry_outage_rate=0.05,
        random_seed=42,  # Keep for documentation
    )


@fixture
def chaos_disabled_config() -> ChaosSettings:
    """Chaos config with all toggles disabled."""
    return ChaosSettings(
        enabled=False,
        wal_fsync_fail_rate=0.0,
        scheduler_starvation_multiplier=1.0,
        network_latency_ms=0,
        telemetry_outage_rate=0.0,
        random_seed=None,
    )


@fixture
def high_failure_config() -> ChaosSettings:
    """Chaos config with high failure rates for deterministic testing."""
    # Set global random seed for deterministic testing
    random.seed(12345)
    return ChaosSettings(
        enabled=True,
        wal_fsync_fail_rate=0.9,
        scheduler_starvation_multiplier=0.1,
        network_latency_ms=500,
        telemetry_outage_rate=0.5,
        random_seed=12345,  # Keep for documentation
    )


@fixture
def metrics_exporter() -> MetricsExporter:
    """Fresh metrics exporter for each test."""
    return MetricsExporter()


@fixture
def chaos_test_db() -> Iterator[Path]:
    """Temporary database with schema migrations applied."""
    with TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "chaos_test.sqlite3"
        apply_migrations(db_path)
        configure_pool(db_path, max_size=2)
        try:
            yield db_path
        finally:
            shutdown_pool()


@fixture
def base_scheduler_profile() -> SchedulerProfile:
    """Base scheduler profile for chaos testing."""
    return SchedulerProfile(
        name="chaos-test-profile",
        description="Scheduler profile for chaos validation",
        port_limits={"command": 10, "query": 5, "sse": 3},
        default_port_limit=4,
    )


@fixture
def sample_entry() -> WalEntry:
    """Sample WAL entry for testing."""
    return WalEntry(
        tenant_id="tenant-chaos-test",
        space_id="space-chaos-test",
        device_id="device-chaos-test",
        idem_key="idem-chaos-test",
        topic="memory.delta",
        schema_uri="schema://memory.delta",
        schema_version="1.0",
        body=b'{"data": "chaos test payload"}',
        envelope_json='{"test": "envelope"}',
        commit_ts="2025-10-05T12:00:00Z",
        payload_sha256="0" * 64,
    )


def metric_value(
    exporter: MetricsExporter, metric_name: str, **labels: str
) -> float | None:
    """Helper to retrieve metric value from exporter registry."""
    sample = exporter.registry.get_sample_value(metric_name, labels=labels)
    return sample if sample is not None else None
