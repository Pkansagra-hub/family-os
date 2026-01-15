"""
Tests for P03 context helper integration.

Related Issues: 6.3.5 Application context setup helper

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from k0.db.context_helper import (
    isolated_read_scope,
    p03_isolation_scope,
    set_local_full_context,
    set_local_space_context,
    set_local_tenant_context,
)


def make_context(
    tenant_id: str = "tenant-001",
    space_id: str = "family-test",
) -> MagicMock:
    """Create mock P03CycleContext with specified fields."""
    ctx = MagicMock()
    ctx.tenant_id = tenant_id
    ctx.space_id = space_id
    return ctx


class TestSetLocalSpaceContext:
    """Tests for set_local_space_context function."""

    @pytest.mark.asyncio
    async def test_sets_local_space_id(self) -> None:
        """Verify SET LOCAL is used for space_id."""
        mock_conn = AsyncMock()
        await set_local_space_context(mock_conn, "test-space")

        mock_conn.execute.assert_called_once_with(
            "SET LOCAL app.current_space_id = $1",
            "test-space",
        )

    @pytest.mark.asyncio
    async def test_uses_set_local_not_set_config(self) -> None:
        """Verify SET LOCAL is used, not set_config."""
        mock_conn = AsyncMock()
        await set_local_space_context(mock_conn, "any-space")

        call_args = mock_conn.execute.call_args[0][0]
        assert "SET LOCAL" in call_args
        assert "set_config" not in call_args.lower()


class TestSetLocalTenantContext:
    """Tests for set_local_tenant_context function."""

    @pytest.mark.asyncio
    async def test_sets_local_tenant_id(self) -> None:
        """Verify SET LOCAL is used for tenant_id."""
        mock_conn = AsyncMock()
        await set_local_tenant_context(mock_conn, "test-tenant")

        mock_conn.execute.assert_called_once_with(
            "SET LOCAL app.current_tenant_id = $1",
            "test-tenant",
        )


class TestSetLocalFullContext:
    """Tests for set_local_full_context function."""

    @pytest.mark.asyncio
    async def test_sets_both_space_and_tenant(self) -> None:
        """Verify both space and tenant are set."""
        mock_conn = AsyncMock()
        await set_local_full_context(mock_conn, "space-123", "tenant-456")

        calls = mock_conn.execute.call_args_list
        assert len(calls) == 2
        assert "app.current_space_id" in calls[0][0][0]
        assert "app.current_tenant_id" in calls[1][0][0]


class TestP03IsolationScope:
    """Tests for p03_isolation_scope context manager."""

    @pytest.mark.asyncio
    async def test_acquires_pool_connection(self) -> None:
        """Verify connection is acquired from pool."""
        ctx = make_context()
        mock_conn = AsyncMock()
        mock_tx = MagicMock()
        mock_pool = MagicMock()

        # Create proper async context manager for transaction
        mock_tx_cm = MagicMock()
        mock_tx_cm.__aenter__ = AsyncMock(return_value=mock_tx)
        mock_tx_cm.__aexit__ = AsyncMock(return_value=None)
        mock_conn.transaction = MagicMock(return_value=mock_tx_cm)

        # Create proper async context manager for pool acquire
        mock_acquire_cm = MagicMock()
        mock_acquire_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_cm.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_cm)

        with patch("k0.db.pool.get_pool", return_value=mock_pool):
            async with p03_isolation_scope(ctx) as (conn, tx):
                assert conn is mock_conn
                assert tx is mock_tx

            mock_pool.acquire.assert_called_once()

    @pytest.mark.asyncio
    async def test_starts_transaction(self) -> None:
        """Verify transaction is started."""
        ctx = make_context()
        mock_conn = AsyncMock()
        mock_tx = MagicMock()
        mock_pool = MagicMock()

        mock_tx_cm = MagicMock()
        mock_tx_cm.__aenter__ = AsyncMock(return_value=mock_tx)
        mock_tx_cm.__aexit__ = AsyncMock(return_value=None)
        mock_conn.transaction = MagicMock(return_value=mock_tx_cm)

        mock_acquire_cm = MagicMock()
        mock_acquire_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_cm.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_cm)

        with patch("k0.db.pool.get_pool", return_value=mock_pool):
            async with p03_isolation_scope(ctx) as (conn, tx):
                pass

            mock_conn.transaction.assert_called_once()

    @pytest.mark.asyncio
    async def test_sets_space_context_from_p03_context(self) -> None:
        """Verify space_id is set from P03CycleContext."""
        ctx = make_context(space_id="family-abc")
        mock_conn = AsyncMock()
        mock_tx = MagicMock()
        mock_pool = MagicMock()

        mock_tx_cm = MagicMock()
        mock_tx_cm.__aenter__ = AsyncMock(return_value=mock_tx)
        mock_tx_cm.__aexit__ = AsyncMock(return_value=None)
        mock_conn.transaction = MagicMock(return_value=mock_tx_cm)

        mock_acquire_cm = MagicMock()
        mock_acquire_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_cm.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_cm)

        with patch("k0.db.pool.get_pool", return_value=mock_pool):
            async with p03_isolation_scope(ctx) as (conn, tx):
                pass

            calls = mock_conn.execute.call_args_list
            space_call = calls[0]
            assert space_call[0][0] == "SET LOCAL app.current_space_id = $1"
            assert space_call[0][1] == "family-abc"

    @pytest.mark.asyncio
    async def test_sets_tenant_context_from_p03_context(self) -> None:
        """Verify tenant_id is set from P03CycleContext."""
        ctx = make_context(tenant_id="tenant-xyz")
        mock_conn = AsyncMock()
        mock_tx = MagicMock()
        mock_pool = MagicMock()

        mock_tx_cm = MagicMock()
        mock_tx_cm.__aenter__ = AsyncMock(return_value=mock_tx)
        mock_tx_cm.__aexit__ = AsyncMock(return_value=None)
        mock_conn.transaction = MagicMock(return_value=mock_tx_cm)

        mock_acquire_cm = MagicMock()
        mock_acquire_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_cm.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_cm)

        with patch("k0.db.pool.get_pool", return_value=mock_pool):
            async with p03_isolation_scope(ctx) as (conn, tx):
                pass

            calls = mock_conn.execute.call_args_list
            tenant_call = calls[1]
            assert tenant_call[0][0] == "SET LOCAL app.current_tenant_id = $1"
            assert tenant_call[0][1] == "tenant-xyz"


class TestIsolatedReadScope:
    """Tests for isolated_read_scope context manager."""

    @pytest.mark.asyncio
    async def test_uses_readonly_transaction(self) -> None:
        """Verify transaction is started in readonly mode."""
        ctx = make_context()
        mock_conn = AsyncMock()
        mock_pool = MagicMock()

        mock_tx_cm = MagicMock()
        mock_tx_cm.__aenter__ = AsyncMock(return_value=None)
        mock_tx_cm.__aexit__ = AsyncMock(return_value=None)
        mock_conn.transaction = MagicMock(return_value=mock_tx_cm)

        mock_acquire_cm = MagicMock()
        mock_acquire_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_cm.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_cm)

        with patch("k0.db.pool.get_pool", return_value=mock_pool):
            async with isolated_read_scope(ctx) as _conn:
                pass

            mock_conn.transaction.assert_called_once_with(readonly=True)

    @pytest.mark.asyncio
    async def test_yields_connection_only(self) -> None:
        """Verify only connection is yielded, not transaction."""
        ctx = make_context()
        mock_conn = AsyncMock()
        mock_pool = MagicMock()

        mock_tx_cm = MagicMock()
        mock_tx_cm.__aenter__ = AsyncMock(return_value=None)
        mock_tx_cm.__aexit__ = AsyncMock(return_value=None)
        mock_conn.transaction = MagicMock(return_value=mock_tx_cm)

        mock_acquire_cm = MagicMock()
        mock_acquire_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_cm.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_cm)

        with patch("k0.db.pool.get_pool", return_value=mock_pool):
            async with isolated_read_scope(ctx) as conn:
                assert conn is mock_conn

    @pytest.mark.asyncio
    async def test_sets_context_in_readonly_scope(self) -> None:
        """Verify context is set even in readonly scope."""
        ctx = make_context(space_id="read-space", tenant_id="read-tenant")
        mock_conn = AsyncMock()
        mock_pool = MagicMock()

        mock_tx_cm = MagicMock()
        mock_tx_cm.__aenter__ = AsyncMock(return_value=None)
        mock_tx_cm.__aexit__ = AsyncMock(return_value=None)
        mock_conn.transaction = MagicMock(return_value=mock_tx_cm)

        mock_acquire_cm = MagicMock()
        mock_acquire_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_cm.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_cm)

        with patch("k0.db.pool.get_pool", return_value=mock_pool):
            async with isolated_read_scope(ctx) as _conn:
                pass

            calls = mock_conn.execute.call_args_list
            assert len(calls) == 2
            assert "app.current_space_id" in calls[0][0][0]
            assert "app.current_tenant_id" in calls[1][0][0]
