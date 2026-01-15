"""Tests for device retention policy."""

from __future__ import annotations

import time

from k0.pipelines.p03.security.device_retention import (
    RETENTION_DAYS,
    DeviceRetentionPolicy,
    RetentionAction,
)


class TestRetentionDays:
    """Tests for RETENTION_DAYS configuration."""

    def test_green_longest_retention(self) -> None:
        """GREEN band has longest retention."""
        assert RETENTION_DAYS["GREEN"] == 365

    def test_amber_medium_retention(self) -> None:
        """AMBER band has medium retention."""
        assert RETENTION_DAYS["AMBER"] == 180

    def test_red_shorter_retention(self) -> None:
        """RED band has shorter retention."""
        assert RETENTION_DAYS["RED"] == 90

    def test_tombstone_shortest(self) -> None:
        """Tombstones have shortest retention."""
        assert RETENTION_DAYS["TOMBSTONE"] == 7


class TestGetRetentionDays:
    """Tests for get_retention_days()."""

    def test_normal_data(self) -> None:
        """Normal data uses band retention."""
        assert DeviceRetentionPolicy.get_retention_days("GREEN") == 365
        assert DeviceRetentionPolicy.get_retention_days("AMBER") == 180
        assert DeviceRetentionPolicy.get_retention_days("RED") == 90

    def test_archived_data(self) -> None:
        """Archived data uses archive retention."""
        assert DeviceRetentionPolicy.get_retention_days("GREEN", is_archived=True) == 30

    def test_tombstoned_data(self) -> None:
        """Tombstoned data uses tombstone retention."""
        assert DeviceRetentionPolicy.get_retention_days("GREEN", is_tombstone=True) == 7


class TestEvaluateRetention:
    """Tests for evaluate_retention()."""

    def test_recent_data_kept(self) -> None:
        """Recent data is kept."""
        now_ms = int(time.time() * 1000)
        created_at = now_ms - (1 * 24 * 60 * 60 * 1000)  # 1 day ago

        decision = DeviceRetentionPolicy.evaluate_retention(
            created_at_ms=created_at,
            last_accessed_at_ms=None,
            band="GREEN",
        )

        assert decision.action == RetentionAction.KEEP
        assert decision.days_until_action is not None
        assert decision.days_until_action > 300

    def test_old_data_deleted(self) -> None:
        """Old data past retention is deleted."""
        now_ms = int(time.time() * 1000)
        created_at = now_ms - (400 * 24 * 60 * 60 * 1000)  # 400 days ago

        decision = DeviceRetentionPolicy.evaluate_retention(
            created_at_ms=created_at,
            last_accessed_at_ms=None,
            band="GREEN",  # 365 day retention
        )

        assert decision.action == RetentionAction.DELETE

    def test_last_access_extends_retention(self) -> None:
        """Recent access extends retention."""
        now_ms = int(time.time() * 1000)
        created_at = now_ms - (200 * 24 * 60 * 60 * 1000)  # 200 days ago
        last_accessed = now_ms - (1 * 24 * 60 * 60 * 1000)  # 1 day ago

        decision = DeviceRetentionPolicy.evaluate_retention(
            created_at_ms=created_at,
            last_accessed_at_ms=last_accessed,
            band="AMBER",  # 180 day retention
        )

        # Would be deleted based on created_at, but kept due to recent access
        assert decision.action == RetentionAction.KEEP

    def test_tombstone_short_retention(self) -> None:
        """Tombstoned items deleted after 7 days."""
        now_ms = int(time.time() * 1000)
        created_at = now_ms - (10 * 24 * 60 * 60 * 1000)  # 10 days ago

        decision = DeviceRetentionPolicy.evaluate_retention(
            created_at_ms=created_at,
            last_accessed_at_ms=None,
            band="GREEN",
            is_tombstone=True,
        )

        assert decision.action == RetentionAction.DELETE
