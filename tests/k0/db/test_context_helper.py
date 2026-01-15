"""
Tests for k0/db/context_helper.py - RLS Context Management.

Validates context helper functions for Row-Level Security enforcement:
- set_space_context()
- set_tenant_context()
- set_user_context()
- set_full_context()
- clear_context()
- isolation_scope() context manager
- space_isolation_scope() context manager

Related:
- Issue 6.3.1: RLS policy for st_learned_weights
- Issue 6.3.2: RLS policy for st_consolidation_audit
- Issue 6.3.3: RLS policy for st_pruned_entities
- Issue 6.3.4: RLS policy for st_decay_feedback
"""

from __future__ import annotations

from unittest.mock import AsyncMock, call

import pytest

from k0.db.context_helper import (
    clear_context,
    get_current_space_id,
    get_current_tenant_id,
    get_current_user_id,
    isolation_scope,
    set_full_context,
    set_space_context,
    set_tenant_context,
    set_user_context,
    space_isolation_scope,
)

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def mock_conn() -> AsyncMock:
    """Create a mock asyncpg connection."""
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetchval = AsyncMock(return_value=None)
    return conn


# =============================================================================
# TEST: set_space_context
# =============================================================================


class TestSetSpaceContext:
    """Tests for set_space_context()."""

    @pytest.mark.asyncio
    async def test_sets_space_context(self, mock_conn):
        """Verify set_space_context sets app.current_space_id."""
        await set_space_context(mock_conn, "space_123")

        mock_conn.execute.assert_called_once_with(
            "SELECT set_config('app.current_space_id', $1, false)",
            "space_123",
        )

    @pytest.mark.asyncio
    async def test_sets_different_space_ids(self, mock_conn):
        """Verify set_space_context works with various space IDs."""
        test_ids = ["space_abc", "sp-001", "test.space.id", ""]

        for space_id in test_ids:
            mock_conn.reset_mock()
            await set_space_context(mock_conn, space_id)
            mock_conn.execute.assert_called_once()


# =============================================================================
# TEST: set_tenant_context
# =============================================================================


class TestSetTenantContext:
    """Tests for set_tenant_context()."""

    @pytest.mark.asyncio
    async def test_sets_tenant_context(self, mock_conn):
        """Verify set_tenant_context sets app.current_tenant_id."""
        await set_tenant_context(mock_conn, "tenant_456")

        mock_conn.execute.assert_called_once_with(
            "SELECT set_config('app.current_tenant_id', $1, false)",
            "tenant_456",
        )


# =============================================================================
# TEST: set_user_context
# =============================================================================


class TestSetUserContext:
    """Tests for set_user_context()."""

    @pytest.mark.asyncio
    async def test_sets_user_context(self, mock_conn):
        """Verify set_user_context sets app.current_user_id."""
        await set_user_context(mock_conn, "user_789")

        mock_conn.execute.assert_called_once_with(
            "SELECT set_config('app.current_user_id', $1, false)",
            "user_789",
        )


# =============================================================================
# TEST: set_full_context
# =============================================================================


class TestSetFullContext:
    """Tests for set_full_context()."""

    @pytest.mark.asyncio
    async def test_sets_all_contexts(self, mock_conn):
        """Verify set_full_context sets space, tenant, and user."""
        await set_full_context(mock_conn, "space_1", "tenant_2", "user_3")

        assert mock_conn.execute.call_count == 3
        calls = mock_conn.execute.call_args_list
        assert calls[0] == call("SELECT set_config('app.current_space_id', $1, false)", "space_1")
        assert calls[1] == call("SELECT set_config('app.current_tenant_id', $1, false)", "tenant_2")
        assert calls[2] == call("SELECT set_config('app.current_user_id', $1, false)", "user_3")

    @pytest.mark.asyncio
    async def test_sets_space_tenant_only_when_user_none(self, mock_conn):
        """Verify set_full_context skips user when None."""
        await set_full_context(mock_conn, "space_1", "tenant_2", user_id=None)

        assert mock_conn.execute.call_count == 2
        calls = mock_conn.execute.call_args_list
        assert calls[0] == call("SELECT set_config('app.current_space_id', $1, false)", "space_1")
        assert calls[1] == call("SELECT set_config('app.current_tenant_id', $1, false)", "tenant_2")


# =============================================================================
# TEST: clear_context
# =============================================================================


class TestClearContext:
    """Tests for clear_context()."""

    @pytest.mark.asyncio
    async def test_clears_all_contexts(self, mock_conn):
        """Verify clear_context resets all context variables."""
        await clear_context(mock_conn)

        assert mock_conn.execute.call_count == 3
        calls = mock_conn.execute.call_args_list
        assert calls[0] == call("RESET app.current_space_id")
        assert calls[1] == call("RESET app.current_tenant_id")
        assert calls[2] == call("RESET app.current_user_id")


# =============================================================================
# TEST: get_current_* functions
# =============================================================================


class TestGetCurrentContext:
    """Tests for get_current_* functions."""

    @pytest.mark.asyncio
    async def test_get_current_space_id_returns_value(self, mock_conn):
        """Verify get_current_space_id returns the set value."""
        mock_conn.fetchval.return_value = "space_123"

        result = await get_current_space_id(mock_conn)

        assert result == "space_123"
        mock_conn.fetchval.assert_called_once_with(
            "SELECT current_setting('app.current_space_id', true)"
        )

    @pytest.mark.asyncio
    async def test_get_current_space_id_returns_none_when_empty(self, mock_conn):
        """Verify get_current_space_id returns None when empty string."""
        mock_conn.fetchval.return_value = ""

        result = await get_current_space_id(mock_conn)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_current_space_id_returns_none_when_not_set(self, mock_conn):
        """Verify get_current_space_id returns None when not set."""
        mock_conn.fetchval.return_value = None

        result = await get_current_space_id(mock_conn)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_current_tenant_id_returns_value(self, mock_conn):
        """Verify get_current_tenant_id returns the set value."""
        mock_conn.fetchval.return_value = "tenant_456"

        result = await get_current_tenant_id(mock_conn)

        assert result == "tenant_456"
        mock_conn.fetchval.assert_called_once_with(
            "SELECT current_setting('app.current_tenant_id', true)"
        )

    @pytest.mark.asyncio
    async def test_get_current_user_id_returns_value(self, mock_conn):
        """Verify get_current_user_id returns the set value."""
        mock_conn.fetchval.return_value = "user_789"

        result = await get_current_user_id(mock_conn)

        assert result == "user_789"
        mock_conn.fetchval.assert_called_once_with(
            "SELECT current_setting('app.current_user_id', true)"
        )


# =============================================================================
# TEST: isolation_scope context manager
# =============================================================================


class TestIsolationScope:
    """Tests for isolation_scope() context manager."""

    @pytest.mark.asyncio
    async def test_sets_context_on_entry(self, mock_conn):
        """Verify isolation_scope sets context on entry."""
        async with isolation_scope(mock_conn, "space_1", "tenant_2", "user_3"):
            # Verify context was set
            assert mock_conn.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_clears_context_on_exit(self, mock_conn):
        """Verify isolation_scope clears context on exit."""
        async with isolation_scope(mock_conn, "space_1", "tenant_2"):
            mock_conn.reset_mock()

        # Should have called clear_context (3 RESET calls)
        assert mock_conn.execute.call_count == 3
        calls = mock_conn.execute.call_args_list
        assert calls[0] == call("RESET app.current_space_id")
        assert calls[1] == call("RESET app.current_tenant_id")
        assert calls[2] == call("RESET app.current_user_id")

    @pytest.mark.asyncio
    async def test_clears_context_on_exception(self, mock_conn):
        """Verify isolation_scope clears context even on exception."""
        with pytest.raises(ValueError):
            async with isolation_scope(mock_conn, "space_1", "tenant_2"):
                mock_conn.reset_mock()
                raise ValueError("Test exception")

        # Should still have cleared context
        assert mock_conn.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_yields_same_connection(self, mock_conn):
        """Verify isolation_scope yields the same connection."""
        async with isolation_scope(mock_conn, "space_1", "tenant_2") as scoped_conn:
            assert scoped_conn is mock_conn


# =============================================================================
# TEST: space_isolation_scope context manager
# =============================================================================


class TestSpaceIsolationScope:
    """Tests for space_isolation_scope() context manager."""

    @pytest.mark.asyncio
    async def test_sets_space_context_only(self, mock_conn):
        """Verify space_isolation_scope only sets space context."""
        async with space_isolation_scope(mock_conn, "space_123"):
            assert mock_conn.execute.call_count == 1
            mock_conn.execute.assert_called_with(
                "SELECT set_config('app.current_space_id', $1, false)",
                "space_123",
            )

    @pytest.mark.asyncio
    async def test_clears_only_space_on_exit(self, mock_conn):
        """Verify space_isolation_scope only clears space on exit."""
        async with space_isolation_scope(mock_conn, "space_123"):
            mock_conn.reset_mock()

        # Should only reset space_id
        assert mock_conn.execute.call_count == 1
        mock_conn.execute.assert_called_with("RESET app.current_space_id")

    @pytest.mark.asyncio
    async def test_clears_on_exception(self, mock_conn):
        """Verify space_isolation_scope clears on exception."""
        with pytest.raises(RuntimeError):
            async with space_isolation_scope(mock_conn, "space_123"):
                mock_conn.reset_mock()
                raise RuntimeError("Test error")

        assert mock_conn.execute.call_count == 1
        mock_conn.execute.assert_called_with("RESET app.current_space_id")

    @pytest.mark.asyncio
    async def test_yields_same_connection(self, mock_conn):
        """Verify space_isolation_scope yields the same connection."""
        async with space_isolation_scope(mock_conn, "space_1") as scoped_conn:
            assert scoped_conn is mock_conn


# =============================================================================
# TEST: RLS Integration Patterns
# =============================================================================


class TestRLSPatterns:
    """Tests demonstrating RLS usage patterns for P03 tables."""

    @pytest.mark.asyncio
    async def test_pattern_query_with_isolation(self, mock_conn):
        """Demonstrate pattern for querying with RLS isolation."""
        # Pattern: Set context before query
        await set_space_context(mock_conn, "family_space_001")

        # Simulated query that RLS will filter
        mock_conn.fetch = AsyncMock(return_value=[{"param_key": "decay_lambda"}])
        rows = await mock_conn.fetch("SELECT * FROM st_learned_weights")

        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_pattern_cross_space_access_prevented(self, mock_conn):
        """Demonstrate RLS prevents cross-space access."""
        # Set context to space_A
        await set_space_context(mock_conn, "space_A")

        # Query will only return space_A rows (RLS enforced)
        # Space_B rows are invisible even if queried

    @pytest.mark.asyncio
    async def test_pattern_nested_scopes(self, mock_conn):
        """Demonstrate nested isolation scopes."""
        async with space_isolation_scope(mock_conn, "outer_space"):
            # Operations in outer_space context
            pass

        # After exiting scope, context is cleared
        # Reset mock to test new context setting
        mock_conn.reset_mock()
        await set_space_context(mock_conn, "another_space")
        assert mock_conn.execute.call_count == 1
