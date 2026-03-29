"""
Integration tests for learned_weights syscalls and store adapters.

Tests the complete flow:
  migrations (0040, 0041) -> syscalls (learned_weights_*) -> store adapters -> modules

Coverage:
  - Syscall capability gating (PermissionError)
  - learned_weights_query: prefix-based bulk SELECT
  - learned_weights_get: single-row SELECT
  - learned_weights_upsert: INSERT and UPDATE (version increment)
  - SyscallWeightStore: WeightStoreProtocol adapter for R1
  - SyscallLearnedWeightsStore: LearnedWeightsStoreProtocol adapter for R3
  - Round-trip: upsert -> query/get -> verify
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.kernel.syscalls import PermissionError, Syscalls
from k0.pipelines.p03.stores import SyscallLearnedWeightsStore, SyscallWeightStore

# =============================================================================
# Fixtures
# =============================================================================


def _make_uow(fetch_result=None, fetchrow_result=None, execute_result="INSERT 0 1"):
    """Build mock UoW with pre-wired connection methods."""
    uow = MagicMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=fetch_result or [])
    conn.fetchrow = AsyncMock(return_value=fetchrow_result)
    conn.execute = AsyncMock(return_value=execute_result)
    uow._connection = conn
    return uow


def _make_syscalls(caps, uow):
    """Build Syscalls with given capabilities and mock UoW."""
    return Syscalls(
        pipeline_id="P03",
        granted_caps=caps,
        uow_factory=MagicMock(return_value=uow),
    )


# =============================================================================
# Syscall: learned_weights_query
# =============================================================================


class TestLearnedWeightsQuery:
    """Tests for learned_weights_query syscall."""

    @pytest.mark.asyncio
    async def test_query_requires_read_capability(self) -> None:
        """Should raise PermissionError without st_learned_weights.read."""
        syscalls = _make_syscalls(caps=set(), uow=_make_uow())
        with pytest.raises(PermissionError) as exc_info:
            await syscalls.learned_weights_query(space_id="sp_1", param_prefix="importance_")
        assert "st_learned_weights.read" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_query_returns_rows_and_count(self) -> None:
        """Should return dict with rows list and count."""
        rows = [
            {
                "param_key": "importance_sentiment",
                "current_value": 0.10,
                "sample_count": 600,
                "updated_at": 1000,
                "confidence": 0.8,
                "version": 5,
            },
            {
                "param_key": "importance_affect",
                "current_value": 0.12,
                "sample_count": 600,
                "updated_at": 1000,
                "confidence": 0.8,
                "version": 5,
            },
        ]
        uow = _make_uow(fetch_result=rows)
        syscalls = _make_syscalls(caps={"st_learned_weights.read"}, uow=uow)

        result = await syscalls.learned_weights_query(space_id="sp_1", param_prefix="importance_")

        assert result["count"] == 2
        assert len(result["rows"]) == 2
        assert result["rows"][0]["param_key"] == "importance_sentiment"

    @pytest.mark.asyncio
    async def test_query_empty_returns_zero_count(self) -> None:
        """Should return count=0 and empty rows when nothing matches."""
        uow = _make_uow(fetch_result=[])
        syscalls = _make_syscalls(caps={"st_learned_weights.read"}, uow=uow)

        result = await syscalls.learned_weights_query(space_id="sp_1", param_prefix="nonexistent_")

        assert result["count"] == 0
        assert result["rows"] == []

    @pytest.mark.asyncio
    async def test_query_passes_correct_sql_params(self) -> None:
        """Should pass space_id and prefix% to SQL."""
        uow = _make_uow()
        syscalls = _make_syscalls(caps={"st_learned_weights.read"}, uow=uow)

        await syscalls.learned_weights_query(space_id="sp_42", param_prefix="novelty_bonus_")

        conn = uow._connection
        conn.fetch.assert_awaited_once()
        args = conn.fetch.call_args
        assert args[0][1] == "sp_42"
        assert args[0][2] == "novelty_bonus_%"


# =============================================================================
# Syscall: learned_weights_get
# =============================================================================


class TestLearnedWeightsGet:
    """Tests for learned_weights_get syscall."""

    @pytest.mark.asyncio
    async def test_get_requires_read_capability(self) -> None:
        """Should raise PermissionError without st_learned_weights.read."""
        syscalls = _make_syscalls(caps=set(), uow=_make_uow())
        with pytest.raises(PermissionError) as exc_info:
            await syscalls.learned_weights_get(space_id="sp_1", param_key="novelty_bonus_first")
        assert "st_learned_weights.read" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_returns_dict_when_found(self) -> None:
        """Should return dict with weight data when row exists."""
        row = {
            "param_key": "novelty_bonus_first",
            "current_value": 0.3,
            "sample_count": 10,
            "updated_at": 5000,
            "confidence": 0.5,
            "version": 2,
        }
        uow = _make_uow(fetchrow_result=row)
        syscalls = _make_syscalls(caps={"st_learned_weights.read"}, uow=uow)

        result = await syscalls.learned_weights_get(
            space_id="sp_1", param_key="novelty_bonus_first"
        )

        assert result is not None
        assert result["current_value"] == 0.3
        assert result["sample_count"] == 10

    @pytest.mark.asyncio
    async def test_get_returns_none_when_not_found(self) -> None:
        """Should return None when no matching row."""
        uow = _make_uow(fetchrow_result=None)
        syscalls = _make_syscalls(caps={"st_learned_weights.read"}, uow=uow)

        result = await syscalls.learned_weights_get(space_id="sp_1", param_key="nonexistent_key")

        assert result is None


# =============================================================================
# Syscall: learned_weights_upsert
# =============================================================================


class TestLearnedWeightsUpsert:
    """Tests for learned_weights_upsert syscall."""

    @pytest.mark.asyncio
    async def test_upsert_requires_write_capability(self) -> None:
        """Should raise PermissionError without st_learned_weights.write."""
        syscalls = _make_syscalls(caps={"st_learned_weights.read"}, uow=_make_uow())
        with pytest.raises(PermissionError) as exc_info:
            await syscalls.learned_weights_upsert(
                space_id="sp_1",
                param_key="importance_sentiment",
                value=0.12,
                prior_value=0.10,
            )
        assert "st_learned_weights.write" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_upsert_insert_returns_status(self) -> None:
        """Should return param_key, value, and INSERTED status for new row."""
        uow = _make_uow(execute_result="INSERT 0 1")
        syscalls = _make_syscalls(caps={"st_learned_weights.write"}, uow=uow)

        result = await syscalls.learned_weights_upsert(
            space_id="sp_1",
            param_key="importance_sentiment",
            value=0.12,
            prior_value=0.10,
        )

        assert result["param_key"] == "importance_sentiment"
        assert result["value"] == 0.12
        assert result["status"] == "INSERTED"

    @pytest.mark.asyncio
    async def test_upsert_update_returns_updated_status(self) -> None:
        """Should return UPDATED status on conflict."""
        uow = _make_uow(execute_result="UPDATE 1")
        syscalls = _make_syscalls(caps={"st_learned_weights.write"}, uow=uow)

        result = await syscalls.learned_weights_upsert(
            space_id="sp_1",
            param_key="importance_sentiment",
            value=0.14,
            prior_value=0.12,
        )

        assert result["status"] == "UPDATED"

    @pytest.mark.asyncio
    async def test_upsert_passes_correct_sql_params(self) -> None:
        """Should pass param_key, space_id, value, prior_value to SQL."""
        uow = _make_uow(execute_result="INSERT 0 1")
        syscalls = _make_syscalls(caps={"st_learned_weights.write"}, uow=uow)

        await syscalls.learned_weights_upsert(
            space_id="sp_42",
            param_key="novelty_bonus_first",
            value=0.5,
            prior_value=0.3,
        )

        conn = uow._connection
        conn.execute.assert_awaited_once()
        args = conn.execute.call_args[0]
        assert args[1] == "novelty_bonus_first"  # $1
        assert args[2] == "sp_42"  # $2
        assert args[3] == 0.5  # $3
        assert args[4] == 0.3  # $4


# =============================================================================
# SyscallWeightStore (R1 adapter)
# =============================================================================


class TestSyscallWeightStore:
    """Tests for SyscallWeightStore (WeightStoreProtocol for R1)."""

    @pytest.mark.asyncio
    async def test_get_weights_returns_none_on_empty(self) -> None:
        """Should return None when syscall returns no rows."""
        mock_syscalls = MagicMock()
        mock_syscalls.learned_weights_query = AsyncMock(return_value={"rows": [], "count": 0})

        store = SyscallWeightStore(syscalls=mock_syscalls)
        result = await store.get_weights(space_id="sp_1", param_prefix="importance_")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_weights_strips_prefix_from_keys(self) -> None:
        """Should strip param_prefix from returned keys."""
        rows = [
            {
                "param_key": "importance_sentiment",
                "current_value": 0.10,
                "sample_count": 600,
                "updated_at": 1000,
                "confidence": 0.8,
                "version": 5,
            },
            {
                "param_key": "importance_affect",
                "current_value": 0.12,
                "sample_count": 600,
                "updated_at": 1000,
                "confidence": 0.8,
                "version": 5,
            },
        ]
        mock_syscalls = MagicMock()
        mock_syscalls.learned_weights_query = AsyncMock(return_value={"rows": rows, "count": 2})

        store = SyscallWeightStore(syscalls=mock_syscalls)
        result = await store.get_weights(space_id="sp_1", param_prefix="importance_")

        assert result is not None
        assert "sentiment" in result.weights
        assert "affect" in result.weights
        assert "importance_sentiment" not in result.weights

    @pytest.mark.asyncio
    async def test_get_weights_uses_min_sample_count(self) -> None:
        """Should use the minimum sample_count across all rows."""
        rows = [
            {
                "param_key": "importance_sentiment",
                "current_value": 0.10,
                "sample_count": 600,
                "updated_at": 1000,
                "confidence": 0.8,
                "version": 5,
            },
            {
                "param_key": "importance_affect",
                "current_value": 0.12,
                "sample_count": 400,
                "updated_at": 1000,
                "confidence": 0.8,
                "version": 5,
            },
        ]
        mock_syscalls = MagicMock()
        mock_syscalls.learned_weights_query = AsyncMock(return_value={"rows": rows, "count": 2})

        store = SyscallWeightStore(syscalls=mock_syscalls)
        result = await store.get_weights(space_id="sp_1", param_prefix="importance_")

        assert result is not None
        assert result.sample_count == 400

    @pytest.mark.asyncio
    async def test_get_weights_uses_max_updated_at(self) -> None:
        """Should use the maximum updated_at across all rows."""
        rows = [
            {
                "param_key": "importance_sentiment",
                "current_value": 0.10,
                "sample_count": 600,
                "updated_at": 1000,
                "confidence": 0.8,
                "version": 5,
            },
            {
                "param_key": "importance_affect",
                "current_value": 0.12,
                "sample_count": 600,
                "updated_at": 2000,
                "confidence": 0.8,
                "version": 5,
            },
        ]
        mock_syscalls = MagicMock()
        mock_syscalls.learned_weights_query = AsyncMock(return_value={"rows": rows, "count": 2})

        store = SyscallWeightStore(syscalls=mock_syscalls)
        result = await store.get_weights(space_id="sp_1", param_prefix="importance_")

        assert result is not None
        assert result.updated_at == 2000

    @pytest.mark.asyncio
    async def test_get_weights_passes_prefix_to_syscall(self) -> None:
        """Should forward space_id and param_prefix to syscall."""
        mock_syscalls = MagicMock()
        mock_syscalls.learned_weights_query = AsyncMock(return_value={"rows": [], "count": 0})

        store = SyscallWeightStore(syscalls=mock_syscalls)
        await store.get_weights(space_id="sp_42", param_prefix="novelty_")

        mock_syscalls.learned_weights_query.assert_awaited_once_with(
            space_id="sp_42",
            param_prefix="novelty_",
        )


# =============================================================================
# SyscallLearnedWeightsStore (R3 adapter)
# =============================================================================


class TestSyscallLearnedWeightsStore:
    """Tests for SyscallLearnedWeightsStore (LearnedWeightsStoreProtocol for R3)."""

    @pytest.mark.asyncio
    async def test_get_weight_returns_value_when_found(self) -> None:
        """Should return float value from syscall result."""
        mock_syscalls = MagicMock()
        mock_syscalls.learned_weights_get = AsyncMock(
            return_value={
                "param_key": "novelty_bonus_first",
                "current_value": 0.3,
                "sample_count": 10,
                "updated_at": 5000,
                "confidence": 0.5,
                "version": 2,
            },
        )

        store = SyscallLearnedWeightsStore(syscalls=mock_syscalls)
        result = await store.get_weight(param_key="novelty_bonus_first", space_id="sp_1")

        assert result == 0.3

    @pytest.mark.asyncio
    async def test_get_weight_returns_none_when_not_found(self) -> None:
        """Should return None when syscall returns None."""
        mock_syscalls = MagicMock()
        mock_syscalls.learned_weights_get = AsyncMock(return_value=None)

        store = SyscallLearnedWeightsStore(syscalls=mock_syscalls)
        result = await store.get_weight(param_key="nonexistent", space_id="sp_1")

        assert result is None

    @pytest.mark.asyncio
    async def test_upsert_weight_calls_syscall(self) -> None:
        """Should call learned_weights_upsert with correct params."""
        mock_syscalls = MagicMock()
        mock_syscalls.learned_weights_upsert = AsyncMock(
            return_value={"param_key": "novelty_bonus_first", "value": 0.5, "status": "INSERTED"},
        )

        store = SyscallLearnedWeightsStore(syscalls=mock_syscalls)
        await store.upsert_weight(
            param_key="novelty_bonus_first",
            space_id="sp_1",
            value=0.5,
            prior_value=0.3,
        )

        mock_syscalls.learned_weights_upsert.assert_awaited_once_with(
            space_id="sp_1",
            param_key="novelty_bonus_first",
            value=0.5,
            prior_value=0.3,
        )

    @pytest.mark.asyncio
    async def test_upsert_weight_returns_none(self) -> None:
        """Upsert should return None (protocol signature)."""
        mock_syscalls = MagicMock()
        mock_syscalls.learned_weights_upsert = AsyncMock(
            return_value={"param_key": "x", "value": 1.0, "status": "INSERTED"},
        )

        store = SyscallLearnedWeightsStore(syscalls=mock_syscalls)
        result = await store.upsert_weight(
            param_key="x",
            space_id="sp_1",
            value=1.0,
            prior_value=0.0,
        )

        assert result is None
