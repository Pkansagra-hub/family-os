"""
Tests for P03 Edge Case Handler.

Issue 6.2.18: Edge case handling implementation
"""

from __future__ import annotations

import time
from typing import Any, List, Optional
from unittest.mock import MagicMock

import pytest

from k0.pipelines.p03.ops.edge_case_handler import (
    EdgeCaseResult,
    EdgeCaseType,
    P03EdgeCaseHandler,
    P03HealthCheck,
    create_edge_case_handler,
    create_health_check,
)

# ============================================================================
# Mock database connection
# ============================================================================


class MockRow:
    """Mock database row."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)


class MockConnection:
    """Mock asyncpg connection for testing."""

    def __init__(self) -> None:
        self.executed: List[tuple] = []
        self._fetchrow_results: List[Optional[MockRow]] = []
        self._fetch_results: List[List[MockRow]] = []

    def set_fetchrow_results(self, results: List[Optional[dict]]) -> None:
        """Set results for fetchrow() calls."""
        self._fetchrow_results = [MockRow(r) if r else None for r in results]

    def set_fetch_results(self, results: List[List[dict]]) -> None:
        """Set results for fetch() calls."""
        self._fetch_results = [[MockRow(r) for r in batch] for batch in results]

    async def fetchrow(self, query: str, *args: Any) -> Optional[MockRow]:
        if self._fetchrow_results:
            return self._fetchrow_results.pop(0)
        return None

    async def fetch(self, query: str, *args: Any) -> List[MockRow]:
        if self._fetch_results:
            return self._fetch_results.pop(0)
        return []

    async def execute(self, query: str, *args: Any) -> str:
        self.executed.append((query, args))
        return "UPDATE 1"


# ============================================================================
# Factory tests
# ============================================================================


class TestFactory:
    """Tests for factory functions."""

    def test_create_edge_case_handler_default(self) -> None:
        """Test factory with defaults."""
        handler = create_edge_case_handler()
        assert handler is not None
        assert handler._idle_threshold_hours == 24
        assert handler._backlog_warning_threshold == 10_000
        assert handler._backlog_critical_threshold == 50_000
        assert handler._memory_pressure_threshold == 0.80
        assert handler._kg_node_threshold == 1_000_000

    def test_create_edge_case_handler_custom(self) -> None:
        """Test factory with custom thresholds."""
        handler = create_edge_case_handler(
            idle_threshold_hours=12,
            backlog_warning_threshold=5000,
        )
        assert handler._idle_threshold_hours == 12
        assert handler._backlog_warning_threshold == 5000

    def test_create_edge_case_handler_with_metrics(self) -> None:
        """Test factory with metrics exporter."""
        metrics = MagicMock()
        handler = create_edge_case_handler(metrics=metrics)
        assert handler._metrics is metrics

    def test_create_health_check(self) -> None:
        """Test health check factory."""
        check = create_health_check()
        assert check is not None
        assert check._handler is not None

    def test_create_health_check_with_handler(self) -> None:
        """Test health check factory with custom handler."""
        handler = create_edge_case_handler()
        check = create_health_check(handler)
        assert check._handler is handler


# ============================================================================
# EdgeCaseType tests
# ============================================================================


class TestEdgeCaseType:
    """Tests for EdgeCaseType enum."""

    def test_all_types_exist(self) -> None:
        """Test all expected types are defined."""
        expected = [
            "IDLE_CYCLE",
            "CORRUPTED_EMBEDDING",
            "PARTIAL_WRITE_FAILURE",
            "BACKLOG_OVERFLOW",
            "P08_CIRCUIT_OPEN",
            "FAISS_UNAVAILABLE",
            "DUPLICATE_TRIGGER",
            "MEMORY_PRESSURE",
            "KG_EXPLOSION",
        ]
        for name in expected:
            assert hasattr(EdgeCaseType, name)


# ============================================================================
# EdgeCaseResult tests
# ============================================================================


class TestEdgeCaseResult:
    """Tests for EdgeCaseResult dataclass."""

    def test_not_detected(self) -> None:
        """Test non-detected result."""
        result = EdgeCaseResult(detected=False)
        assert result.detected is False
        assert result.edge_case_type is None
        assert result.severity == "info"

    def test_critical_severity(self) -> None:
        """Test critical severity types."""
        result = EdgeCaseResult(
            detected=True,
            edge_case_type=EdgeCaseType.KG_EXPLOSION,
        )
        assert result.severity == "critical"

    def test_warning_severity(self) -> None:
        """Test warning severity types."""
        result = EdgeCaseResult(
            detected=True,
            edge_case_type=EdgeCaseType.BACKLOG_OVERFLOW,
        )
        assert result.severity == "warning"


# ============================================================================
# check_idle_cycle tests
# ============================================================================


class TestCheckIdleCycle:
    """Tests for check_idle_cycle method."""

    @pytest.mark.asyncio
    async def test_no_events_idle(self) -> None:
        """Test idle detected when no events exist."""
        handler = P03EdgeCaseHandler(idle_threshold_hours=24)
        conn = MockConnection()
        conn.set_fetchrow_results([{"last_event": None}])

        result = await handler.check_idle_cycle("space1", connection=conn)

        assert result.detected is True
        assert result.edge_case_type == EdgeCaseType.IDLE_CYCLE
        assert result.action_taken == "EMIT_IDLE_EVENT"

    @pytest.mark.asyncio
    async def test_old_events_idle(self) -> None:
        """Test idle detected when events are too old."""
        handler = P03EdgeCaseHandler(idle_threshold_hours=24)
        conn = MockConnection()
        # Event from 25 hours ago
        old_time = int(time.time() - 25 * 3600) * 1000
        conn.set_fetchrow_results([{"last_event": old_time}])

        result = await handler.check_idle_cycle("space1", connection=conn)

        assert result.detected is True

    @pytest.mark.asyncio
    async def test_recent_events_not_idle(self) -> None:
        """Test not idle when recent events exist."""
        handler = P03EdgeCaseHandler(idle_threshold_hours=24)
        conn = MockConnection()
        # Event from 1 hour ago
        recent_time = int(time.time() - 1 * 3600) * 1000
        conn.set_fetchrow_results([{"last_event": recent_time}])

        result = await handler.check_idle_cycle("space1", connection=conn)

        assert result.detected is False


# ============================================================================
# check_corrupted_embedding tests
# ============================================================================


class TestCheckCorruptedEmbedding:
    """Tests for check_corrupted_embedding method."""

    def test_valid_embedding(self) -> None:
        """Test valid embedding passes check."""
        handler = P03EdgeCaseHandler(embedding_dimension=3)
        embedding = [0.1, 0.2, 0.3]

        result = handler.check_corrupted_embedding("e1", embedding, 3)

        assert result.detected is False

    def test_dimension_mismatch(self) -> None:
        """Test dimension mismatch detection."""
        handler = P03EdgeCaseHandler(embedding_dimension=1536)
        embedding = [0.1, 0.2, 0.3]  # Only 3 dimensions

        result = handler.check_corrupted_embedding("e1", embedding, 1536)

        assert result.detected is True
        assert result.edge_case_type == EdgeCaseType.CORRUPTED_EMBEDDING
        assert result.details["reason"] == "dimension_mismatch"

    def test_nan_detection(self) -> None:
        """Test NaN value detection."""
        handler = P03EdgeCaseHandler(embedding_dimension=3)
        embedding = [0.1, float("nan"), 0.3]

        result = handler.check_corrupted_embedding("e1", embedding, 3)

        assert result.detected is True
        assert result.details["reason"] == "nan_detected"

    def test_inf_detection(self) -> None:
        """Test infinity value detection."""
        handler = P03EdgeCaseHandler(embedding_dimension=3)
        embedding = [0.1, float("inf"), 0.3]

        result = handler.check_corrupted_embedding("e1", embedding, 3)

        assert result.detected is True
        assert result.details["reason"] == "inf_detected"


# ============================================================================
# check_backlog_overflow tests
# ============================================================================


class TestCheckBacklogOverflow:
    """Tests for check_backlog_overflow method."""

    @pytest.mark.asyncio
    async def test_no_overflow(self) -> None:
        """Test no overflow with low count."""
        handler = P03EdgeCaseHandler(
            backlog_warning_threshold=10000,
            backlog_critical_threshold=50000,
        )
        conn = MockConnection()
        conn.set_fetchrow_results([{"pending_count": 5000}])

        result = await handler.check_backlog_overflow("space1", connection=conn)

        assert result.detected is False

    @pytest.mark.asyncio
    async def test_warning_overflow(self) -> None:
        """Test warning level overflow."""
        handler = P03EdgeCaseHandler(
            backlog_warning_threshold=10000,
            backlog_critical_threshold=50000,
        )
        conn = MockConnection()
        conn.set_fetchrow_results([{"pending_count": 15000}])

        result = await handler.check_backlog_overflow("space1", connection=conn)

        assert result.detected is True
        assert result.details["severity"] == "warning"
        assert result.action_taken == "ADAPTIVE_BATCHING_WARNING"

    @pytest.mark.asyncio
    async def test_critical_overflow(self) -> None:
        """Test critical level overflow."""
        handler = P03EdgeCaseHandler(
            backlog_warning_threshold=10000,
            backlog_critical_threshold=50000,
        )
        conn = MockConnection()
        conn.set_fetchrow_results([{"pending_count": 60000}])

        result = await handler.check_backlog_overflow("space1", connection=conn)

        assert result.detected is True
        assert result.details["severity"] == "critical"
        assert result.action_taken == "ADAPTIVE_BATCHING_CRITICAL"


# ============================================================================
# check_duplicate_trigger tests
# ============================================================================


class TestCheckDuplicateTrigger:
    """Tests for check_duplicate_trigger method."""

    def test_first_trigger_not_duplicate(self) -> None:
        """Test first trigger is not duplicate."""
        handler = P03EdgeCaseHandler()

        result = handler.check_duplicate_trigger("hash1", "cycle1")

        assert result.detected is False

    def test_same_hash_is_duplicate(self) -> None:
        """Test same hash is detected as duplicate."""
        handler = P03EdgeCaseHandler()

        # First call
        handler.check_duplicate_trigger("hash1", "cycle1")

        # Second call with same hash
        result = handler.check_duplicate_trigger("hash1", "cycle2")

        assert result.detected is True
        assert result.edge_case_type == EdgeCaseType.DUPLICATE_TRIGGER
        assert result.action_taken == "IDEMPOTENT_SKIP"

    def test_different_hash_not_duplicate(self) -> None:
        """Test different hash is not duplicate."""
        handler = P03EdgeCaseHandler()

        handler.check_duplicate_trigger("hash1", "cycle1")
        result = handler.check_duplicate_trigger("hash2", "cycle2")

        assert result.detected is False

    def test_cache_cleared(self) -> None:
        """Test cache can be cleared."""
        handler = P03EdgeCaseHandler()

        handler.check_duplicate_trigger("hash1", "cycle1")
        assert handler.get_batch_hash_cache_size() == 1

        handler.clear_batch_hash_cache()
        assert handler.get_batch_hash_cache_size() == 0


# ============================================================================
# check_memory_pressure tests
# ============================================================================


class TestCheckMemoryPressure:
    """Tests for check_memory_pressure method."""

    def test_memory_check_runs(self) -> None:
        """Test memory check runs without error."""
        handler = P03EdgeCaseHandler()

        result = handler.check_memory_pressure()

        # Result depends on system state, just verify it returns
        assert isinstance(result, EdgeCaseResult)

    def test_can_skip_dream_phase(self) -> None:
        """Test can_skip_dream_phase helper."""
        handler = P03EdgeCaseHandler()

        # Should return bool
        can_skip = handler.can_skip_dream_phase()
        assert isinstance(can_skip, bool)


# ============================================================================
# check_kg_explosion tests
# ============================================================================


class TestCheckKGExplosion:
    """Tests for check_kg_explosion method."""

    @pytest.mark.asyncio
    async def test_no_explosion(self) -> None:
        """Test no explosion with low node count."""
        handler = P03EdgeCaseHandler(kg_node_threshold=1_000_000)
        conn = MockConnection()
        conn.set_fetchrow_results([{"node_count": 100_000}])

        result = await handler.check_kg_explosion("space1", connection=conn)

        assert result.detected is False

    @pytest.mark.asyncio
    async def test_explosion_detected(self) -> None:
        """Test explosion detected at threshold."""
        handler = P03EdgeCaseHandler(kg_node_threshold=1_000_000)
        conn = MockConnection()
        conn.set_fetchrow_results([{"node_count": 1_500_000}])

        result = await handler.check_kg_explosion("space1", connection=conn)

        assert result.detected is True
        assert result.edge_case_type == EdgeCaseType.KG_EXPLOSION
        assert result.action_taken == "ENABLE_KG_SHARDING"


# ============================================================================
# check_p08_circuit_open_duration tests
# ============================================================================


class TestCheckP08CircuitOpenDuration:
    """Tests for check_p08_circuit_open_duration method."""

    def test_circuit_closed(self) -> None:
        """Test no detection when circuit is closed."""
        handler = P03EdgeCaseHandler()

        result = handler.check_p08_circuit_open_duration(None)

        assert result.detected is False

    def test_circuit_open_short(self) -> None:
        """Test no detection when circuit open for short time."""
        handler = P03EdgeCaseHandler()
        recent_open = time.time() - 60  # 1 minute ago

        result = handler.check_p08_circuit_open_duration(recent_open, 300)

        assert result.detected is False

    def test_circuit_open_too_long(self) -> None:
        """Test detection when circuit open too long."""
        handler = P03EdgeCaseHandler()
        old_open = time.time() - 400  # 6+ minutes ago

        result = handler.check_p08_circuit_open_duration(old_open, 300)

        assert result.detected is True
        assert result.edge_case_type == EdgeCaseType.P08_CIRCUIT_OPEN


# ============================================================================
# flag_embedding_for_recompute tests
# ============================================================================


class TestFlagEmbeddingForRecompute:
    """Tests for flag_embedding_for_recompute method."""

    @pytest.mark.asyncio
    async def test_flag_updates_status(self) -> None:
        """Test flagging updates st_vec status."""
        handler = P03EdgeCaseHandler()
        conn = MockConnection()

        await handler.flag_embedding_for_recompute("entity1", connection=conn)

        assert len(conn.executed) == 1
        query, args = conn.executed[0]
        assert "RECOMPUTE_REQUIRED" in query
        assert "entity1" in args


# ============================================================================
# P03HealthCheck tests
# ============================================================================


class TestP03HealthCheck:
    """Tests for P03HealthCheck class."""

    @pytest.mark.asyncio
    async def test_run_all_checks_healthy(self) -> None:
        """Test health check when all is healthy."""
        handler = P03EdgeCaseHandler()
        check = P03HealthCheck(handler)
        conn = MockConnection()

        # Recent event, low backlog, low KG
        recent_time = int(time.time() - 1 * 3600) * 1000
        conn.set_fetchrow_results(
            [
                {"last_event": recent_time},  # idle check
                {"pending_count": 100},  # backlog check
                {"node_count": 1000},  # KG check
            ]
        )

        results = await check.run_all_checks("space1", connection=conn)

        # No issues means empty results
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_run_all_checks_with_issues(self) -> None:
        """Test health check with issues detected."""
        handler = P03EdgeCaseHandler(
            idle_threshold_hours=24,
            backlog_critical_threshold=50000,
        )
        check = P03HealthCheck(handler)
        conn = MockConnection()

        # No events (idle) and high backlog
        conn.set_fetchrow_results(
            [
                {"last_event": None},  # idle check - will trigger
                {"pending_count": 60000},  # backlog check - critical
                {"node_count": 1000},  # KG check - ok
            ]
        )

        results = await check.run_all_checks("space1", connection=conn)

        assert len(results) >= 2
        check_names = [r.check_name for r in results]
        assert "idle_cycle" in check_names
        assert "backlog_overflow" in check_names

    @pytest.mark.asyncio
    async def test_get_health_summary(self) -> None:
        """Test health summary generation."""
        handler = P03EdgeCaseHandler()
        check = P03HealthCheck(handler)
        conn = MockConnection()

        # All healthy
        recent_time = int(time.time() - 1 * 3600) * 1000
        conn.set_fetchrow_results(
            [
                {"last_event": recent_time},
                {"pending_count": 100},
                {"node_count": 1000},
            ]
        )

        summary = await check.get_health_summary("space1", connection=conn)

        assert "overall_status" in summary
        assert "checks_run" in summary
        assert "issues_found" in summary


# ============================================================================
# Metrics emission tests
# ============================================================================


class TestMetricsEmission:
    """Tests for metrics emission."""

    @pytest.mark.asyncio
    async def test_idle_cycle_emits_metric(self) -> None:
        """Test idle cycle detection emits metric."""
        metrics = MagicMock()
        handler = P03EdgeCaseHandler(metrics=metrics)
        conn = MockConnection()
        conn.set_fetchrow_results([{"last_event": None}])

        await handler.check_idle_cycle("space1", connection=conn)

        metrics.emit.assert_called()
        call_args = metrics.emit.call_args
        assert "p03_idle_cycles_total" in str(call_args)

    def test_corrupted_embedding_emits_metric(self) -> None:
        """Test corrupted embedding detection emits metric."""
        metrics = MagicMock()
        handler = P03EdgeCaseHandler(metrics=metrics, embedding_dimension=10)

        handler.check_corrupted_embedding("e1", [0.1], 10)

        metrics.emit.assert_called()

    def test_duplicate_trigger_emits_metric(self) -> None:
        """Test duplicate trigger detection emits metric."""
        metrics = MagicMock()
        handler = P03EdgeCaseHandler(metrics=metrics)

        handler.check_duplicate_trigger("hash1", "cycle1")
        handler.check_duplicate_trigger("hash1", "cycle2")  # Duplicate

        metrics.emit.assert_called()
