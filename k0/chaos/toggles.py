"""
Chaos toggle decision functions with    if should_inject and metrics_exporter:
        metrics_exporter.counter(
            "chaos_fsync_injected",
            "Total WAL fsync failures injected by chaos",
        ).inc()metry emission.

All toggles emit metrics for observability and must operate deterministically
when random_seed is configured.
"""

import random
from typing import TYPE_CHECKING

from k0.chaos import ChaosDecision

if TYPE_CHECKING:
    from k0.kernel.config import ChaosSettings
    from k0.obs.metrics import MetricsExporter
    from k0.qos.scheduler import SchedulerProfile


def should_fail_fsync(
    chaos_config: "ChaosSettings",
    metrics_exporter: "MetricsExporter | None" = None,
) -> ChaosDecision:
    """
    Decide whether to inject WAL fsync failure.

    Args:
        chaos_config: Chaos configuration with fail_rate
        metrics_exporter: Optional metrics exporter for telemetry

    Returns:
        ChaosDecision with should_inject=True if failure should occur

    Raises:
        None - decision only, caller raises OSError(errno.EIO)
    """
    if not chaos_config.enabled or chaos_config.wal_fsync_fail_rate <= 0.0:
        return ChaosDecision(should_inject=False, reason="chaos_disabled_or_zero_rate")

    # Use global random (caller should set seed if deterministic behavior needed)
    should_inject = random.random() < chaos_config.wal_fsync_fail_rate

    if should_inject and metrics_exporter:
        metrics_exporter.counter(
            "chaos_fsync_injected_total",
            "Total WAL fsync failures injected by chaos",
        ).inc()

    return ChaosDecision(
        should_inject=should_inject,
        reason="probabilistic_injection" if should_inject else "probability_not_met",
        metadata={"fail_rate": chaos_config.wal_fsync_fail_rate},
    )


def apply_scheduler_starvation(
    profile: "SchedulerProfile",
    chaos_config: "ChaosSettings",
    metrics_exporter: "MetricsExporter | None" = None,
) -> "SchedulerProfile":
    """
    Apply scheduler capacity reduction for starvation testing.

    Args:
        profile: Original scheduler profile with port_limits
        chaos_config: Chaos configuration with starvation_multiplier
        metrics_exporter: Optional metrics exporter for telemetry

    Returns:
        Modified SchedulerProfile with reduced port_limits

    Example:
        multiplier=0.3 means 30% of original capacity (70% starvation)
    """
    if not chaos_config.enabled or chaos_config.scheduler_starvation_multiplier >= 1.0:
        return profile  # No modification

    multiplier = chaos_config.scheduler_starvation_multiplier

    # Create new profile with reduced limits (actual capacity reduction)
    from k0.qos.scheduler import SchedulerProfile

    reduced_limits = {
        port: max(1, int(limit * multiplier))  # At least 1 to avoid zero
        for port, limit in profile.port_limits.items()
    }

    if metrics_exporter:
        metrics_exporter.gauge(
            "scheduler_throttled_multiplier",
            "Current scheduler capacity multiplier (1.0=normal, <1.0=starved)",
        ).set(multiplier)

    return SchedulerProfile(
        name=profile.name,
        description=profile.description,
        port_limits=reduced_limits,
        default_port_limit=profile.default_port_limit,
    )


def get_network_delay_ms(chaos_config: "ChaosSettings") -> int:
    """
    Get configured network latency injection in milliseconds.

    Args:
        chaos_config: Chaos configuration with network_latency_ms

    Returns:
        Delay in milliseconds (0 if disabled)

    Note:
        Delay applied via ChaosTransport using time.sleep() -
        acceptable for intentional chaos injection.
    """
    if not chaos_config.enabled:
        return 0

    return max(0, chaos_config.network_latency_ms)


def should_drop_telemetry(
    chaos_config: "ChaosSettings",
    metrics_exporter: "MetricsExporter | None" = None,
) -> bool:
    """
    Decide whether to drop telemetry emission (simulate outage).

    Args:
        chaos_config: Chaos configuration with telemetry_outage_rate
        metrics_exporter: Optional metrics exporter for telemetry

    Returns:
        True if telemetry should be dropped this invocation

    Note:
        This creates partial observability to test alert resilience.
    """
    if not chaos_config.enabled or chaos_config.telemetry_outage_rate <= 0.0:
        return False

    # Use global random (caller should set seed if deterministic behavior needed)
    should_drop = random.random() < chaos_config.telemetry_outage_rate

    if should_drop and metrics_exporter:
        # Ironic: emit metric about dropping metrics
        # This validates that _some_ telemetry still flows
        try:
            metrics_exporter.counter(
                "chaos_telemetry_dropped",
                "Total telemetry emissions dropped by chaos",
            ).inc()
        except Exception:
            # If metrics exporter itself is broken, fail silently
            pass

    return should_drop
