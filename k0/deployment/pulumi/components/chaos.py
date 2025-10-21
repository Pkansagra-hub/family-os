"""Pulumi component for chaos engineering settings (Issue 9.1.4 Phase 4)."""

from __future__ import annotations

from typing import Any

import pulumi


class ChaosComponent:
    """Pulumi component for chaos configuration management.

    Reads chaos settings from Pulumi config and converts them to
    environment variables for K0 kernel deployment.
    """

    def __init__(self, config: pulumi.Config | None = None) -> None:
        """Initialize chaos component from Pulumi config.

        Args:
            config: Pulumi config instance (defaults to "k0" project config)
        """
        self.config = config or pulumi.Config("k0")

        # Read chaos settings from config with sensible defaults
        self.enabled = self.config.get_bool("chaos:enabled") or False
        self.fsync_fail_rate = self.config.get_float("chaos:fsync_fail_rate") or 0.0
        self.scheduler_starvation_multiplier = (
            self.config.get_float("chaos:scheduler_starvation_multiplier") or 1.0
        )
        self.network_latency_ms = self.config.get_int("chaos:network_latency_ms") or 0
        self.telemetry_outage_rate = (
            self.config.get_float("chaos:telemetry_outage_rate") or 0.0
        )
        self.random_seed = self.config.get_int("chaos:random_seed")

    def to_env_vars(self) -> dict[str, str]:
        """Convert chaos settings to environment variables for kernel config.

        Returns:
            Dictionary of environment variables in K0_KERNEL_CHAOS__* format
        """
        env_vars = {
            "K0_KERNEL_CHAOS__ENABLED": str(self.enabled).lower(),
            "K0_KERNEL_CHAOS__WAL_FSYNC_FAIL_RATE": str(self.fsync_fail_rate),
            "K0_KERNEL_CHAOS__SCHEDULER_STARVATION_MULTIPLIER": str(
                self.scheduler_starvation_multiplier
            ),
            "K0_KERNEL_CHAOS__NETWORK_LATENCY_MS": str(self.network_latency_ms),
            "K0_KERNEL_CHAOS__TELEMETRY_OUTAGE_RATE": str(self.telemetry_outage_rate),
        }

        if self.random_seed is not None:
            env_vars["K0_KERNEL_CHAOS__RANDOM_SEED"] = str(self.random_seed)

        return env_vars

    def to_dict(self) -> dict[str, Any]:
        """Convert chaos settings to dictionary for Ansible extra vars.

        Returns:
            Dictionary with chaos_* keys for Ansible role
        """
        result: dict[str, Any] = {
            "chaos_enabled": self.enabled,
            "chaos_wal_fsync_fail_rate": self.fsync_fail_rate,
            "chaos_scheduler_starvation_multiplier": self.scheduler_starvation_multiplier,
            "chaos_network_latency_ms": self.network_latency_ms,
            "chaos_telemetry_outage_rate": self.telemetry_outage_rate,
        }

        if self.random_seed is not None:
            result["chaos_random_seed"] = self.random_seed

        return result

    def export_outputs(self) -> None:
        """Export chaos settings as Pulumi stack outputs for auditing."""
        pulumi.export("chaos_enabled", self.enabled)
        pulumi.export("chaos_fsync_fail_rate", self.fsync_fail_rate)
        pulumi.export(
            "chaos_scheduler_starvation_multiplier",
            self.scheduler_starvation_multiplier,
        )
        pulumi.export("chaos_network_latency_ms", self.network_latency_ms)
        pulumi.export("chaos_telemetry_outage_rate", self.telemetry_outage_rate)

        if self.random_seed is not None:
            pulumi.export("chaos_random_seed", self.random_seed)
