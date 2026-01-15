"""Unit tests for k0.db.advisory_lock module.

Part of Milestone 1.3 - Issue 1.3.4: Single-writer-per-space guard.

These tests verify the advisory lock interface and utilities without
requiring a running PostgreSQL. Integration tests that require PostgreSQL
are in tests/integration/db/.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from k0.db.advisory_lock import (
    AdvisoryLockService,
    AdvisoryLockServiceProtocol,
    LockInfo,
    LockResult,
    hash_lock_key,
    make_p03_lock_key,
)


class TestLockResult:
    """Tests for LockResult dataclass."""

    def test_frozen(self):
        """LockResult is immutable."""
        result = LockResult(
            acquired=True,
            lock_key="test",
            lock_id=12345,
            holder_id="node_1",
        )
        with pytest.raises(Exception):
            result.acquired = False  # type: ignore

    def test_acquired_result(self):
        """LockResult with acquired=True has holder info."""
        now = datetime.now(UTC)
        result = LockResult(
            acquired=True,
            lock_key="P03:t1:s1",
            lock_id=-123456789,
            holder_id="node_1",
            acquired_at=now,
        )
        assert result.acquired is True
        assert result.lock_key == "P03:t1:s1"
        assert result.lock_id == -123456789
        assert result.holder_id == "node_1"
        assert result.error is None
        assert result.acquired_at == now

    def test_failed_result(self):
        """LockResult with acquired=False has error info."""
        result = LockResult(
            acquired=False,
            lock_key="P03:t1:s1",
            lock_id=-123456789,
            holder_id=None,
            error="lock_held",
        )
        assert result.acquired is False
        assert result.lock_key == "P03:t1:s1"
        assert result.holder_id is None
        assert result.error == "lock_held"
        assert result.acquired_at is None


class TestLockInfo:
    """Tests for LockInfo dataclass."""

    def test_frozen(self):
        """LockInfo is immutable."""
        info = LockInfo(
            lock_key="test",
            lock_id=12345,
            holder_id="node_1",
            acquired_at=datetime.now(UTC),
        )
        with pytest.raises(Exception):
            info.holder_id = "node_2"  # type: ignore

    def test_values(self):
        """LockInfo stores values correctly."""
        now = datetime.now(UTC)
        info = LockInfo(
            lock_key="P03:t1:s1",
            lock_id=-123456789,
            holder_id="node_1",
            acquired_at=now,
        )
        assert info.lock_key == "P03:t1:s1"
        assert info.lock_id == -123456789
        assert info.holder_id == "node_1"
        assert info.acquired_at == now


class TestHashLockKey:
    """Tests for hash_lock_key utility."""

    def test_returns_int(self):
        """hash_lock_key returns an integer."""
        result = hash_lock_key("P03:tenant_1:space_1")
        assert isinstance(result, int)

    def test_consistent_hash(self):
        """Same input always produces same hash."""
        key = "P03:tenant_1:space_abc"
        hash1 = hash_lock_key(key)
        hash2 = hash_lock_key(key)
        assert hash1 == hash2

    def test_different_keys_different_hashes(self):
        """Different inputs produce different hashes."""
        hash1 = hash_lock_key("P03:tenant_1:space_1")
        hash2 = hash_lock_key("P03:tenant_1:space_2")
        hash3 = hash_lock_key("P03:tenant_2:space_1")
        assert hash1 != hash2
        assert hash1 != hash3
        assert hash2 != hash3

    def test_signed_64bit(self):
        """Hash is within signed 64-bit range."""
        # Test with various inputs
        for key in [
            "P03:t1:s1",
            "P03:tenant_very_long_name:space_very_long_name",
            "",
            "a" * 1000,
        ]:
            result = hash_lock_key(key)
            assert -(2**63) <= result < 2**63

    def test_empty_key(self):
        """Empty key produces valid hash."""
        result = hash_lock_key("")
        assert isinstance(result, int)

    def test_unicode_key(self):
        """Unicode keys produce valid hashes."""
        result = hash_lock_key("P03:テナント:スペース")
        assert isinstance(result, int)


class TestMakeP03LockKey:
    """Tests for make_p03_lock_key utility."""

    def test_format(self):
        """Lock key follows expected format."""
        key = make_p03_lock_key("tenant_1", "space_abc")
        assert key == "P03:tenant_1:space_abc"

    def test_empty_values(self):
        """Empty tenant/space produce valid key."""
        key = make_p03_lock_key("", "")
        assert key == "P03::"

    def test_special_characters(self):
        """Special characters in values are preserved."""
        key = make_p03_lock_key("tenant-1", "space_2.3")
        assert key == "P03:tenant-1:space_2.3"


class TestAdvisoryLockServiceProtocol:
    """Tests for AdvisoryLockServiceProtocol."""

    def test_protocol_is_runtime_checkable(self):
        """Protocol can be used with isinstance."""
        service = AdvisoryLockService()
        assert isinstance(service, AdvisoryLockServiceProtocol)

    def test_service_has_required_methods(self):
        """Service implements all protocol methods."""
        service = AdvisoryLockService()
        assert hasattr(service, "acquire")
        assert hasattr(service, "release")
        assert hasattr(service, "is_held_globally")
        assert callable(service.acquire)
        assert callable(service.release)
        assert callable(service.is_held_globally)


class TestAdvisoryLockServiceInterface:
    """Tests for AdvisoryLockService interface without database.

    These tests verify the service raises appropriate errors when
    pool is not initialized, without requiring a running PostgreSQL.
    """

    def test_init_no_held_locks(self):
        """New service has no held locks."""
        service = AdvisoryLockService()
        assert service.get_held_locks() == {}

    @pytest.mark.asyncio
    async def test_acquire_without_pool_raises(self):
        """Acquire without pool raises RuntimeError."""
        import k0.db.pool as pool_module

        original = pool_module._pool
        pool_module._pool = None

        try:
            service = AdvisoryLockService()
            with pytest.raises(RuntimeError, match="not been configured"):
                await service.acquire("test", "node_1")
        finally:
            pool_module._pool = original

    @pytest.mark.asyncio
    async def test_release_not_held_returns_false(self):
        """Release of non-held lock returns False."""
        service = AdvisoryLockService()
        # Lock not in _held_locks, so returns False without DB call
        result = await service.release("not_held", "node_1")
        assert result is False

    @pytest.mark.asyncio
    async def test_release_wrong_holder_returns_false(self):
        """Release by wrong holder returns False."""
        from datetime import UTC, datetime

        from k0.db.advisory_lock import LockState

        service = AdvisoryLockService()
        # Manually add a lock state
        service._held_locks["P03:t1:s1"] = LockState(
            lock_key="P03:t1:s1",
            lock_id=12345,
            holder_id="node_1",
            acquired_at=datetime.now(UTC),
        )

        # Try to release with wrong holder
        result = await service.release("P03:t1:s1", "node_2")
        assert result is False

        # Lock should still be held
        assert "P03:t1:s1" in service._held_locks

    @pytest.mark.asyncio
    async def test_release_all_empty(self):
        """Release all with no locks returns 0."""
        service = AdvisoryLockService()
        count = await service.release_all()
        assert count == 0


class TestGlobalLockServiceFunctions:
    """Tests for global lock service singleton functions."""

    def test_get_service_unconfigured_raises(self):
        """get_advisory_lock_service raises when not configured."""
        import k0.db.advisory_lock as lock_module
        from k0.db.advisory_lock import get_advisory_lock_service

        original = lock_module._lock_service
        lock_module._lock_service = None

        try:
            with pytest.raises(RuntimeError, match="not been configured"):
                get_advisory_lock_service()
        finally:
            lock_module._lock_service = original

    @pytest.mark.asyncio
    async def test_configure_creates_service(self):
        """configure_lock_service creates the singleton."""
        import k0.db.advisory_lock as lock_module
        from k0.db.advisory_lock import (
            configure_lock_service,
            get_advisory_lock_service,
            reset_lock_service,
        )

        original = lock_module._lock_service
        lock_module._lock_service = None

        try:
            await configure_lock_service()
            service = get_advisory_lock_service()
            assert service is not None
            assert isinstance(service, AdvisoryLockService)
        finally:
            await reset_lock_service()
            lock_module._lock_service = original

    @pytest.mark.asyncio
    async def test_configure_idempotent(self):
        """configure_lock_service is safe to call multiple times."""
        import k0.db.advisory_lock as lock_module
        from k0.db.advisory_lock import configure_lock_service, reset_lock_service

        original = lock_module._lock_service
        lock_module._lock_service = None

        try:
            await configure_lock_service()
            service1 = lock_module._lock_service
            await configure_lock_service()
            service2 = lock_module._lock_service
            # Should be same instance
            assert service1 is service2
        finally:
            await reset_lock_service()
            lock_module._lock_service = original

    @pytest.mark.asyncio
    async def test_reset_clears_service(self):
        """reset_lock_service clears the singleton."""
        import k0.db.advisory_lock as lock_module
        from k0.db.advisory_lock import configure_lock_service, reset_lock_service

        original = lock_module._lock_service
        lock_module._lock_service = None

        try:
            await configure_lock_service()
            assert lock_module._lock_service is not None
            await reset_lock_service()
            assert lock_module._lock_service is None
        finally:
            lock_module._lock_service = original


class TestP03LockKeyIntegration:
    """Tests for P03-specific lock key patterns."""

    def test_p03_lock_key_format(self):
        """P03 lock keys follow dossier pattern."""
        key = make_p03_lock_key("tenant_abc", "space_123")
        assert key == "P03:tenant_abc:space_123"
        # Should be hashable
        lock_id = hash_lock_key(key)
        assert isinstance(lock_id, int)

    def test_different_spaces_different_locks(self):
        """Different spaces have different lock IDs."""
        key1 = make_p03_lock_key("t1", "s1")
        key2 = make_p03_lock_key("t1", "s2")
        assert hash_lock_key(key1) != hash_lock_key(key2)

    def test_different_tenants_different_locks(self):
        """Different tenants have different lock IDs."""
        key1 = make_p03_lock_key("t1", "s1")
        key2 = make_p03_lock_key("t2", "s1")
        assert hash_lock_key(key1) != hash_lock_key(key2)


class TestLockKeyCollisionResistance:
    """Tests for hash collision resistance."""

    def test_no_collisions_in_sample(self):
        """No hash collisions in a reasonable sample size."""
        keys = [
            make_p03_lock_key(f"tenant_{i}", f"space_{j}") for i in range(100) for j in range(100)
        ]
        hashes = [hash_lock_key(k) for k in keys]
        # All hashes should be unique
        assert len(set(hashes)) == len(hashes)
