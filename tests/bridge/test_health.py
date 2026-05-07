"""Tests for bridge/core/health.py — K0HealthChecker + DegradedModeManager.

Verifies:
  1. K0HealthChecker state transitions (ONLINE↔DEGRADED↔OFFLINE).
  2. DegradedModeManager policy decisions per status.
  3. Force-offline and snapshot isolation.

Milestone: MS-2 Epic 2.6
"""

from __future__ import annotations

import pytest

from bridge.core.health import (
    DegradedModeManager,
    K0AvailabilityStatus,
    K0HealthChecker,
    K0HealthSnapshot,
)

# ---------------------------------------------------------------------------
# K0HealthSnapshot
# ---------------------------------------------------------------------------


class TestK0HealthSnapshot:
    def test_defaults(self):
        snap = K0HealthSnapshot()
        assert snap.status == K0AvailabilityStatus.OFFLINE
        assert snap.consecutive_failures == 0
        assert snap.error_message == ""

    def test_custom_values(self):
        snap = K0HealthSnapshot(
            status=K0AvailabilityStatus.ONLINE,
            latency_ms=42,
            consecutive_failures=0,
        )
        assert snap.status == K0AvailabilityStatus.ONLINE
        assert snap.latency_ms == 42


# ---------------------------------------------------------------------------
# K0HealthChecker — state transitions
# ---------------------------------------------------------------------------


class TestK0HealthChecker:
    def test_initial_state_is_offline(self):
        hc = K0HealthChecker()
        assert hc.status == K0AvailabilityStatus.OFFLINE

    def test_success_transitions_to_online(self):
        hc = K0HealthChecker()
        result = hc.record_success(latency_ms=50)
        assert result == K0AvailabilityStatus.ONLINE
        assert hc.status == K0AvailabilityStatus.ONLINE

    def test_high_latency_transitions_to_degraded(self):
        hc = K0HealthChecker(degraded_threshold_ms=100)
        hc.record_success(latency_ms=50)  # ONLINE first
        result = hc.record_success(latency_ms=200)
        assert result == K0AvailabilityStatus.DEGRADED

    def test_online_to_degraded_on_single_failure(self):
        hc = K0HealthChecker(failure_threshold=3)
        hc.record_success(latency_ms=10)
        assert hc.status == K0AvailabilityStatus.ONLINE

        result = hc.record_failure("timeout")
        assert result == K0AvailabilityStatus.DEGRADED

    def test_consecutive_failures_go_offline(self):
        hc = K0HealthChecker(failure_threshold=3)
        hc.record_success(latency_ms=10)  # start ONLINE

        hc.record_failure("err1")
        assert hc.status == K0AvailabilityStatus.DEGRADED

        hc.record_failure("err2")
        assert hc.status == K0AvailabilityStatus.DEGRADED

        hc.record_failure("err3")
        assert hc.status == K0AvailabilityStatus.OFFLINE

    def test_offline_recovery_on_single_success(self):
        hc = K0HealthChecker(failure_threshold=2)
        hc.record_failure("err1")
        hc.record_failure("err2")
        assert hc.status == K0AvailabilityStatus.OFFLINE

        result = hc.record_success(latency_ms=30)
        assert result == K0AvailabilityStatus.ONLINE

    def test_degraded_recovery_on_low_latency(self):
        hc = K0HealthChecker(degraded_threshold_ms=100)
        hc.record_success(latency_ms=200)  # DEGRADED
        assert hc.status == K0AvailabilityStatus.DEGRADED

        result = hc.record_success(latency_ms=50)
        assert result == K0AvailabilityStatus.ONLINE

    def test_force_offline(self):
        hc = K0HealthChecker()
        hc.record_success(latency_ms=10)
        assert hc.status == K0AvailabilityStatus.ONLINE

        hc.force_offline("shutdown")
        assert hc.status == K0AvailabilityStatus.OFFLINE

    def test_snapshot_is_isolated_copy(self):
        hc = K0HealthChecker()
        hc.record_success(latency_ms=10)

        snap = hc.snapshot
        assert snap.status == K0AvailabilityStatus.ONLINE

        # Mutate internal state — snapshot should be unaffected
        hc.record_failure("oops")
        assert snap.status == K0AvailabilityStatus.ONLINE
        assert hc.status != snap.status

    def test_consecutive_failures_reset_on_success(self):
        hc = K0HealthChecker(failure_threshold=5)
        hc.record_failure("e1")
        hc.record_failure("e2")
        assert hc.snapshot.consecutive_failures == 2

        hc.record_success(latency_ms=10)
        assert hc.snapshot.consecutive_failures == 0

    def test_snapshot_captures_error_message(self):
        hc = K0HealthChecker()
        hc.record_failure("connection refused")
        assert hc.snapshot.error_message == "connection refused"

    def test_snapshot_clears_error_on_success(self):
        hc = K0HealthChecker()
        hc.record_failure("err")
        hc.record_success(latency_ms=10)
        assert hc.snapshot.error_message == ""


# ---------------------------------------------------------------------------
# DegradedModeManager — policy decisions
# ---------------------------------------------------------------------------


class TestDegradedModeManager:
    def _make_online(self):
        hc = K0HealthChecker()
        hc.record_success(latency_ms=10)
        return DegradedModeManager(hc), hc

    def _make_degraded(self):
        hc = K0HealthChecker(degraded_threshold_ms=100)
        hc.record_success(latency_ms=200)
        return DegradedModeManager(hc), hc

    def _make_offline(self):
        hc = K0HealthChecker(failure_threshold=1)
        hc.record_failure("gone")
        return DegradedModeManager(hc), hc

    # -- should_queue_command

    def test_online_does_not_queue(self):
        dm, _ = self._make_online()
        assert dm.should_queue_command() is False

    def test_degraded_does_not_queue(self):
        dm, _ = self._make_degraded()
        assert dm.should_queue_command() is False

    def test_offline_queues_command(self):
        dm, _ = self._make_offline()
        assert dm.should_queue_command() is True

    # -- should_drop_obs

    def test_online_keeps_all_obs(self):
        dm, _ = self._make_online()
        assert dm.should_drop_obs("LOW") is False
        assert dm.should_drop_obs("NORMAL") is False
        assert dm.should_drop_obs("HIGH") is False

    def test_degraded_drops_low_obs(self):
        dm, _ = self._make_degraded()
        assert dm.should_drop_obs("LOW") is True
        assert dm.should_drop_obs("NORMAL") is False

    def test_offline_drops_low_obs(self):
        dm, _ = self._make_offline()
        assert dm.should_drop_obs("LOW") is True
        assert dm.should_drop_obs("NORMAL") is False

    # -- should_use_cache

    def test_online_no_cache(self):
        dm, _ = self._make_online()
        assert dm.should_use_cache() is False

    def test_degraded_no_cache(self):
        dm, _ = self._make_degraded()
        assert dm.should_use_cache() is False

    def test_offline_uses_cache(self):
        dm, _ = self._make_offline()
        assert dm.should_use_cache() is True

    # -- query_timeout_ms

    def test_online_default_timeout(self):
        dm, _ = self._make_online()
        assert dm.query_timeout_ms() == 5000

    def test_degraded_extended_timeout(self):
        dm, _ = self._make_degraded()
        assert dm.query_timeout_ms() == 10000  # 5000 * 2.0

    def test_custom_timeout_factor(self):
        hc = K0HealthChecker(degraded_threshold_ms=100)
        hc.record_success(latency_ms=200)
        dm = DegradedModeManager(
            hc, default_query_timeout_ms=3000, degraded_query_timeout_factor=3.0
        )
        assert dm.query_timeout_ms() == 9000

    # -- is_online

    def test_is_online_true(self):
        dm, _ = self._make_online()
        assert dm.is_online() is True

    def test_is_online_false_degraded(self):
        dm, _ = self._make_degraded()
        assert dm.is_online() is False

    def test_is_online_false_offline(self):
        dm, _ = self._make_offline()
        assert dm.is_online() is False

    # -- status property

    def test_status_reflects_health(self):
        hc = K0HealthChecker()
        dm = DegradedModeManager(hc)
        assert dm.status == K0AvailabilityStatus.OFFLINE

        hc.record_success(latency_ms=10)
        assert dm.status == K0AvailabilityStatus.ONLINE
