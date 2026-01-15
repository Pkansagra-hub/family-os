"""Unit tests for k0.db.pool module.

These tests verify the pool interface without requiring a running PostgreSQL.
Integration tests that require PostgreSQL are in tests/integration/db/.
"""

from __future__ import annotations

import pytest

from k0.db.pool import AsyncPgPool, PoolStats


class TestPoolStats:
    """Tests for PoolStats dataclass."""

    def test_frozen(self):
        """PoolStats is immutable."""
        stats = PoolStats(size=5, free_size=3, used_size=2, min_size=1, max_size=10)
        with pytest.raises(Exception):
            stats.size = 10  # type: ignore

    def test_values(self):
        """PoolStats stores values correctly."""
        stats = PoolStats(size=5, free_size=3, used_size=2, min_size=1, max_size=10)
        assert stats.size == 5
        assert stats.free_size == 3
        assert stats.used_size == 2
        assert stats.min_size == 1
        assert stats.max_size == 10


class TestAsyncPgPoolInterface:
    """Tests for AsyncPgPool interface without database.

    These tests verify the pool raises appropriate errors when
    not initialized, without requiring a running PostgreSQL.
    """

    def test_stats_uninitialized(self):
        """Uninitialized pool returns zero stats."""
        from k0.config.postgres import PostgresSettings

        settings = PostgresSettings()
        pool = AsyncPgPool(settings)

        stats = pool.stats()
        assert stats.size == 0
        assert stats.free_size == 0
        assert stats.used_size == 0

    @pytest.mark.asyncio
    async def test_acquire_uninitialized_raises(self):
        """Acquire on uninitialized pool raises RuntimeError."""
        from k0.config.postgres import PostgresSettings

        settings = PostgresSettings()
        pool = AsyncPgPool(settings)

        with pytest.raises(RuntimeError, match="not initialized"):
            async with pool.acquire():
                pass

    @pytest.mark.asyncio
    async def test_execute_uninitialized_raises(self):
        """Execute on uninitialized pool raises RuntimeError."""
        from k0.config.postgres import PostgresSettings

        settings = PostgresSettings()
        pool = AsyncPgPool(settings)

        with pytest.raises(RuntimeError):
            await pool.execute("SELECT 1")

    @pytest.mark.asyncio
    async def test_close_uninitialized_safe(self):
        """Close on uninitialized pool is safe."""
        from k0.config.postgres import PostgresSettings

        settings = PostgresSettings()
        pool = AsyncPgPool(settings)

        # Should not raise
        await pool.close()


class TestGlobalPoolFunctions:
    """Tests for global pool singleton functions."""

    def test_get_pool_unconfigured_raises(self):
        """get_pool raises when not configured."""
        # Ensure pool is None
        import k0.db.pool as pool_module
        from k0.db.pool import get_pool

        original = pool_module._pool
        pool_module._pool = None

        try:
            with pytest.raises(RuntimeError, match="not been configured"):
                get_pool()
        finally:
            pool_module._pool = original
