"""
Tests for TransactionCoordinator — Issue 5.2.10

Tests for atomic multi-table writes with retry logic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from k0.modules.consolidation.truth_writer.result import WriteResult
from k0.modules.consolidation.truth_writer.transaction import (
    LAYER_PK_MAP,
    OptimisticLockError,
    TransactionConfig,
    TransactionCoordinator,
    TransactionResult,
    create_transaction_coordinator,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_write_result():
    """Create a mock WriteResult."""
    return WriteResult(
        total_attempted=3,
        total_succeeded=3,
        total_failed=0,
    )


@pytest.fixture
def mock_router(mock_write_result):
    """Create mock DecisionRouter."""
    router = MagicMock()
    router.route = AsyncMock(return_value=mock_write_result)
    return router


@pytest.fixture
def mock_uow():
    """Create mock UnitOfWork."""
    uow = MagicMock()
    uow.connection = AsyncMock()
    uow.connection.fetchrow = AsyncMock(return_value={"version": 1})
    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()
    return uow


@pytest.fixture
def mock_staged():
    """Create mock P03StagedWrites."""
    staged = MagicMock()
    staged.st_epi_writes = []
    staged.st_sem_writes = []
    staged.st_vec_writes = []
    return staged


@pytest.fixture
def default_config():
    """Create default TransactionConfig."""
    return TransactionConfig()


@pytest.fixture
def coordinator(mock_router, default_config):
    """Create TransactionCoordinator with mock router."""
    return TransactionCoordinator(router=mock_router, config=default_config)


# ============================================================================
# Factory Tests
# ============================================================================


class TestFactory:
    """Tests for factory function."""

    def test_create_transaction_coordinator_returns_instance(self, mock_router):
        """Factory should return a TransactionCoordinator instance."""
        coordinator = create_transaction_coordinator(mock_router)
        assert isinstance(coordinator, TransactionCoordinator)

    def test_create_with_custom_config(self, mock_router):
        """Factory should accept custom config."""
        from k0.modules.consolidation.truth_writer.router import WriteMode

        config = TransactionConfig(max_retries=5, retry_delay_ms=200, mode=WriteMode.PARTIAL)
        coordinator = create_transaction_coordinator(mock_router, config=config)
        assert coordinator.config.max_retries == 5
        assert coordinator.config.retry_delay_ms == 200


# ============================================================================
# TransactionConfig Tests
# ============================================================================


class TestTransactionConfig:
    """Tests for TransactionConfig dataclass."""

    def test_default_values(self):
        """Should have correct defaults."""
        from k0.modules.consolidation.truth_writer.router import WriteMode

        config = TransactionConfig()
        assert config.max_retries == 3
        assert config.retry_delay_ms == 100
        assert config.mode == WriteMode.ATOMIC
        assert config.require_capabilities is True

    def test_custom_values(self):
        """Should accept custom values."""
        from k0.modules.consolidation.truth_writer.router import WriteMode

        config = TransactionConfig(
            max_retries=5,
            retry_delay_ms=50,
            mode=WriteMode.PARTIAL,
            require_capabilities=False,
        )
        assert config.max_retries == 5
        assert config.retry_delay_ms == 50
        assert config.mode == WriteMode.PARTIAL
        assert config.require_capabilities is False


# ============================================================================
# TransactionResult Tests
# ============================================================================


class TestTransactionResult:
    """Tests for TransactionResult dataclass."""

    def test_success_result(self, mock_write_result):
        """Should create a success result."""
        result = TransactionResult(
            write_result=mock_write_result,
            attempts=1,
            total_duration_ms=50,
            version_conflicts=0,
        )
        assert result.success is True
        assert result.attempts == 1
        assert result.version_conflicts == 0

    def test_partial_failure_result(self):
        """Should track partial failures."""
        write_result = WriteResult(
            total_attempted=5,
            total_succeeded=3,
            total_failed=2,
        )
        result = TransactionResult(
            write_result=write_result,
            attempts=3,
            total_duration_ms=300,
            version_conflicts=2,
        )
        assert result.success is False
        assert result.version_conflicts == 2

    def test_success_property(self):
        """Should report success when no failures."""
        write_result = WriteResult(
            total_attempted=5,
            total_succeeded=5,
            total_failed=0,
        )
        result = TransactionResult(write_result=write_result)
        assert result.success is True


# ============================================================================
# OptimisticLockError Tests
# ============================================================================


class TestOptimisticLockError:
    """Tests for OptimisticLockError exception."""

    def test_error_message(self):
        """Should format error message correctly."""
        error = OptimisticLockError("st_epi", "entity_001", expected_version=1)
        assert "st_epi" in str(error)
        assert "entity_001" in str(error)
        assert "expected version 1" in str(error)

    def test_error_attributes(self):
        """Should store record details."""
        error = OptimisticLockError("st_sem", "pattern_001", expected_version=2)
        assert error.layer == "st_sem"
        assert error.record_id == "pattern_001"
        assert error.expected_version == 2

    def test_error_without_version(self):
        """Should work without expected version."""
        error = OptimisticLockError("st_vec", "emb_001")
        assert "st_vec" in str(error)
        assert "emb_001" in str(error)
        assert error.expected_version is None


# ============================================================================
# LAYER_PK_MAP Tests
# ============================================================================


class TestLayerPKMap:
    """Tests for LAYER_PK_MAP constant."""

    def test_expected_layers_have_pk(self):
        """Expected layers should have PK mapping."""
        expected_layers = {
            "st_epi",
            "st_sem",
            "st_procedural",
            "st_social",
            "st_prospective",
            "st_kg_dom",
            "st_kg_edges",
            "st_vec",
            "st_hipp_events",
            "st_learning_queue",
        }
        assert set(LAYER_PK_MAP.keys()) == expected_layers

    def test_pk_column_format(self):
        """PK columns should have _id suffix."""
        for layer, pk_col in LAYER_PK_MAP.items():
            assert pk_col.endswith("_id"), f"{layer} PK should end with _id"


# ============================================================================
# Execute Tests
# ============================================================================


class TestExecute:
    """Tests for execute() method with retry logic."""

    @pytest.mark.asyncio
    async def test_execute_success_no_retry(self, coordinator, mock_uow, mock_staged):
        """Should succeed on first attempt."""
        result = await coordinator.execute(mock_staged, mock_uow)

        assert result.success is True
        assert result.attempts == 1
        assert result.write_result.total_succeeded == 3

    @pytest.mark.asyncio
    async def test_execute_retry_on_version_conflict(
        self, mock_router, mock_uow, mock_staged, mock_write_result
    ):
        """Should retry on version conflict."""
        # First call raises OptimisticLockError, second succeeds
        mock_router.route.side_effect = [
            OptimisticLockError("st_epi", "entity_001", expected_version=1),
            mock_write_result,
        ]

        coordinator = TransactionCoordinator(
            router=mock_router,
            config=TransactionConfig(retry_delay_ms=1),  # Fast backoff for test
        )

        result = await coordinator.execute(mock_staged, mock_uow)

        assert result.success is True
        assert result.attempts == 2
        assert result.version_conflicts == 1

    @pytest.mark.asyncio
    async def test_execute_max_retries_exceeded(self, mock_router, mock_uow, mock_staged):
        """Should fail after max retries."""
        mock_router.route.side_effect = OptimisticLockError(
            "st_epi", "entity_001", expected_version=1
        )

        coordinator = TransactionCoordinator(
            router=mock_router,
            config=TransactionConfig(max_retries=2, retry_delay_ms=1),
        )

        with pytest.raises(OptimisticLockError) as exc_info:
            await coordinator.execute(mock_staged, mock_uow)

        assert exc_info.value.layer == "st_epi"
        assert exc_info.value.record_id == "entity_001"

    @pytest.mark.asyncio
    async def test_execute_exponential_backoff(
        self, mock_router, mock_uow, mock_staged, mock_write_result
    ):
        """Should use backoff between retries."""
        mock_router.route.side_effect = [
            OptimisticLockError("st_epi", "entity_001"),
            OptimisticLockError("st_epi", "entity_001"),
            mock_write_result,
        ]

        coordinator = TransactionCoordinator(
            router=mock_router,
            config=TransactionConfig(max_retries=3, retry_delay_ms=1),
        )

        with patch.object(coordinator, "_backoff", new_callable=AsyncMock) as mock_backoff:
            result = await coordinator.execute(mock_staged, mock_uow)

            assert result.success is True
            assert result.attempts == 3
            # Should have called backoff twice
            assert mock_backoff.call_count == 2


# ============================================================================
# Execute Simple Tests
# ============================================================================


class TestExecuteSimple:
    """Tests for execute_simple() method without retry."""

    @pytest.mark.asyncio
    async def test_execute_simple_success(self, coordinator, mock_uow, mock_staged):
        """Should succeed on first attempt."""
        result = await coordinator.execute_simple(mock_staged, mock_uow)

        assert isinstance(result, WriteResult)
        assert result.total_succeeded == 3

    @pytest.mark.asyncio
    async def test_execute_simple_no_retry_on_error(self, mock_router, mock_uow, mock_staged):
        """Should not retry on version conflict."""
        mock_router.route.side_effect = OptimisticLockError(
            "st_epi", "entity_001", expected_version=1
        )

        coordinator = TransactionCoordinator(
            router=mock_router,
            config=TransactionConfig(),
        )

        with pytest.raises(OptimisticLockError):
            await coordinator.execute_simple(mock_staged, mock_uow)

        # Should only call route once
        mock_router.route.assert_called_once()


# ============================================================================
# Capability Validation Tests
# ============================================================================


class TestCapabilityValidation:
    """Tests for capability validation."""

    @pytest.mark.asyncio
    async def test_validates_capabilities_when_enabled(
        self, mock_router, mock_uow, mock_staged, mock_write_result
    ):
        """Should validate capabilities when enabled and required caps provided."""
        mock_router.route.return_value = mock_write_result

        coordinator = TransactionCoordinator(
            router=mock_router,
            config=TransactionConfig(require_capabilities=True),
        )

        with patch.object(
            coordinator, "_validate_capabilities", new_callable=AsyncMock
        ) as mock_validate:
            await coordinator.execute(mock_staged, mock_uow, required_caps=["storage.write"])
            mock_validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_validation_when_disabled(
        self, mock_router, mock_uow, mock_staged, mock_write_result
    ):
        """Should skip validation when disabled."""
        mock_router.route.return_value = mock_write_result

        coordinator = TransactionCoordinator(
            router=mock_router,
            config=TransactionConfig(require_capabilities=False),
        )

        with patch.object(
            coordinator, "_validate_capabilities", new_callable=AsyncMock
        ) as mock_validate:
            await coordinator.execute(mock_staged, mock_uow, required_caps=["storage.write"])
            mock_validate.assert_not_called()


# ============================================================================
# Router Property Tests
# ============================================================================


class TestProperties:
    """Tests for coordinator properties."""

    def test_router_property(self, mock_router):
        """Should expose router property."""
        coordinator = TransactionCoordinator(router=mock_router)
        assert coordinator.router is mock_router

    def test_config_property(self, mock_router):
        """Should expose config property."""
        config = TransactionConfig(max_retries=5)
        coordinator = TransactionCoordinator(router=mock_router, config=config)
        assert coordinator.config is config

    def test_default_config(self, mock_router):
        """Should use default config when not provided."""
        coordinator = TransactionCoordinator(router=mock_router)
        assert coordinator.config is not None
        assert coordinator.config.max_retries == 3


# ============================================================================
# Integration-Style Tests
# ============================================================================


class TestIntegration:
    """Integration-style tests with more realistic scenarios."""

    @pytest.mark.asyncio
    async def test_multiple_layer_transaction(self, mock_router, mock_uow):
        """Should handle writes across multiple layers."""
        mock_staged = MagicMock()
        mock_staged.st_epi_writes = [MagicMock()]
        mock_staged.st_sem_writes = [MagicMock()]
        mock_staged.st_vec_writes = [MagicMock()]

        mock_router.route.return_value = WriteResult(
            total_attempted=3,
            total_succeeded=3,
            total_failed=0,
        )

        coordinator = TransactionCoordinator(router=mock_router)
        result = await coordinator.execute(mock_staged, mock_uow)

        assert result.success is True
        assert result.write_result.total_succeeded == 3
