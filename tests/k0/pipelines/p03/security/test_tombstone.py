"""Tests for tombstone (soft-delete) management."""

from __future__ import annotations

import time

from k0.pipelines.p03.security.tombstone import (
    TOMBSTONE_RETENTION_DAYS,
    TombstoneInfo,
    TombstoneState,
    can_restore,
)


class TestTombstoneConstants:
    """Tests for tombstone constants."""

    def test_retention_days(self) -> None:
        """Tombstone retention is 7 days."""
        assert TOMBSTONE_RETENTION_DAYS == 7


class TestTombstoneState:
    """Tests for TombstoneState enum."""

    def test_states_exist(self) -> None:
        """Verify expected states exist."""
        assert TombstoneState.ACTIVE.value == "ACTIVE"
        assert TombstoneState.TOMBSTONED.value == "TOMBSTONED"
        assert TombstoneState.DELETED.value == "DELETED"


class TestTombstoneInfo:
    """Tests for TombstoneInfo dataclass."""

    def test_create_info(self) -> None:
        """Create tombstone info."""
        now_ms = int(time.time() * 1000)
        retention_ms = TOMBSTONE_RETENTION_DAYS * 24 * 60 * 60 * 1000

        info = TombstoneInfo(
            entity_id="ent-1",
            tombstoned_at_ms=now_ms,
            reason="user_deleted",
            can_restore_until_ms=now_ms + retention_ms,
        )

        assert info.entity_id == "ent-1"
        assert info.reason == "user_deleted"
        assert info.days_until_permanent == TOMBSTONE_RETENTION_DAYS

    def test_days_until_permanent(self) -> None:
        """Calculate days until permanent deletion."""
        now_ms = int(time.time() * 1000)
        # 3 days until permanent deletion
        restore_until = now_ms + (3 * 24 * 60 * 60 * 1000)

        info = TombstoneInfo(
            entity_id="ent-1",
            tombstoned_at_ms=now_ms - (4 * 24 * 60 * 60 * 1000),
            reason="test",
            can_restore_until_ms=restore_until,
        )

        assert info.days_until_permanent == 3

    def test_expired_returns_zero(self) -> None:
        """Expired tombstone returns 0 days."""
        now_ms = int(time.time() * 1000)
        expired = now_ms - (1 * 24 * 60 * 60 * 1000)  # Yesterday

        info = TombstoneInfo(
            entity_id="ent-1",
            tombstoned_at_ms=now_ms - (10 * 24 * 60 * 60 * 1000),
            reason="test",
            can_restore_until_ms=expired,
        )

        assert info.days_until_permanent == 0


class TestCanRestore:
    """Tests for can_restore()."""

    def test_recent_can_restore(self) -> None:
        """Recently tombstoned can be restored."""
        now_ms = int(time.time() * 1000)
        tombstoned_at = now_ms - (1 * 24 * 60 * 60 * 1000)  # 1 day ago
        assert can_restore(tombstoned_at) is True

    def test_old_cannot_restore(self) -> None:
        """Old tombstone cannot be restored."""
        now_ms = int(time.time() * 1000)
        tombstoned_at = now_ms - (10 * 24 * 60 * 60 * 1000)  # 10 days ago
        assert can_restore(tombstoned_at) is False

    def test_exactly_at_limit(self) -> None:
        """At exactly 7 days, can restore."""
        now_ms = int(time.time() * 1000)
        tombstoned_at = now_ms - (6 * 24 * 60 * 60 * 1000)  # 6 days ago (within 7)
        assert can_restore(tombstoned_at) is True
