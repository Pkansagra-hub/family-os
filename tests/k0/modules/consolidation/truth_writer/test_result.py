"""
Test Result Dataclasses — Issue 5.2.1

Tests for LayerWriteResult and WriteResult dataclasses.
"""

from __future__ import annotations

import pytest

from k0.modules.consolidation.truth_writer.result import LayerWriteResult, WriteResult

# =============================================================================
# 1. LAYER WRITE RESULT TESTS
# =============================================================================


class TestLayerWriteResultConstruction:
    """Test LayerWriteResult creation and factories."""

    def test_success_factory(self) -> None:
        """success() factory creates all-succeeded result."""
        result = LayerWriteResult.success(layer="st_epi", count=5, duration_ms=100)

        assert result.layer == "st_epi"
        assert result.writes_attempted == 5
        assert result.writes_succeeded == 5
        assert result.writes_failed == 0
        assert result.failed_ids == []
        assert result.error_message is None
        assert result.duration_ms == 100

    def test_failure_factory(self) -> None:
        """failure() factory creates all-failed result."""
        result = LayerWriteResult.failure(
            layer="st_sem",
            error="Connection timeout",
            failed_ids=["id1", "id2"],
        )

        assert result.layer == "st_sem"
        assert result.writes_attempted == 2
        assert result.writes_succeeded == 0
        assert result.writes_failed == 2
        assert result.failed_ids == ["id1", "id2"]
        assert result.error_message == "Connection timeout"

    def test_failure_factory_no_ids(self) -> None:
        """failure() with no IDs creates single-failure result."""
        result = LayerWriteResult.failure(layer="st_kg_dom", error="Unknown error")

        assert result.writes_attempted == 1
        assert result.writes_failed == 1
        assert result.failed_ids == []

    def test_partial_factory(self) -> None:
        """partial() factory creates mixed-success result."""
        result = LayerWriteResult.partial(
            layer="st_procedural",
            succeeded=3,
            failed_ids=["id4", "id5"],
            error="Partial failure",
        )

        assert result.layer == "st_procedural"
        assert result.writes_attempted == 5
        assert result.writes_succeeded == 3
        assert result.writes_failed == 2
        assert result.is_partial


class TestLayerWriteResultProperties:
    """Test LayerWriteResult computed properties."""

    def test_is_success_true(self) -> None:
        """is_success True when no failures."""
        result = LayerWriteResult.success("st_epi", 10)
        assert result.is_success is True

    def test_is_success_false(self) -> None:
        """is_success False when any failures."""
        result = LayerWriteResult.partial("st_epi", succeeded=5, failed_ids=["id1"])
        assert result.is_success is False

    def test_is_partial_true(self) -> None:
        """is_partial True when some but not all succeeded."""
        result = LayerWriteResult.partial("st_sem", succeeded=3, failed_ids=["x", "y"])
        assert result.is_partial is True

    def test_is_partial_false_all_success(self) -> None:
        """is_partial False when all succeeded."""
        result = LayerWriteResult.success("st_sem", 5)
        assert result.is_partial is False

    def test_is_partial_false_all_failed(self) -> None:
        """is_partial False when all failed."""
        result = LayerWriteResult.failure("st_sem", "error", ["a", "b", "c"])
        assert result.is_partial is False


class TestLayerWriteResultSerialization:
    """Test LayerWriteResult serialization."""

    def test_to_dict(self) -> None:
        """to_dict produces expected structure."""
        result = LayerWriteResult.partial(
            layer="st_epi",
            succeeded=8,
            failed_ids=["id9", "id10"],
            error="timeout",
        )
        result.duration_ms = 250

        data = result.to_dict()

        assert data["layer"] == "st_epi"
        assert data["writes_attempted"] == 10
        assert data["writes_succeeded"] == 8
        assert data["writes_failed"] == 2
        assert data["failed_ids"] == ["id9", "id10"]
        assert data["error_message"] == "timeout"
        assert data["duration_ms"] == 250


# =============================================================================
# 2. WRITE RESULT TESTS
# =============================================================================


class TestWriteResultConstruction:
    """Test WriteResult creation."""

    def test_from_layer_results_single(self) -> None:
        """from_layer_results with single layer."""
        layer_result = LayerWriteResult.success("st_epi", 5)
        result = WriteResult.from_layer_results([layer_result])

        assert result.total_attempted == 5
        assert result.total_succeeded == 5
        assert result.total_failed == 0
        assert "st_epi" in result.by_layer

    def test_from_layer_results_multiple(self) -> None:
        """from_layer_results aggregates multiple layers."""
        results = [
            LayerWriteResult.success("st_epi", 3),
            LayerWriteResult.success("st_sem", 5),
            LayerWriteResult.partial("st_kg_dom", succeeded=2, failed_ids=["kg1"]),
        ]
        result = WriteResult.from_layer_results(results)

        assert result.total_attempted == 11
        assert result.total_succeeded == 10
        assert result.total_failed == 1
        assert len(result.by_layer) == 3
        assert result.failed_decision_ids == ["kg1"]

    def test_empty_factory(self) -> None:
        """empty() creates zero-count result."""
        result = WriteResult.empty()

        assert result.total_attempted == 0
        assert result.total_succeeded == 0
        assert result.total_failed == 0
        assert result.by_layer == {}


class TestWriteResultProperties:
    """Test WriteResult computed properties."""

    def test_is_success(self) -> None:
        """is_success when all writes succeeded."""
        results = [
            LayerWriteResult.success("st_epi", 3),
            LayerWriteResult.success("st_sem", 5),
        ]
        result = WriteResult.from_layer_results(results)

        assert result.is_success is True

    def test_is_not_success_with_failures(self) -> None:
        """is_success False when any failures."""
        results = [
            LayerWriteResult.success("st_epi", 3),
            LayerWriteResult.failure("st_sem", "error"),
        ]
        result = WriteResult.from_layer_results(results)

        assert result.is_success is False

    def test_is_partial(self) -> None:
        """is_partial when some but not all succeeded."""
        results = [
            LayerWriteResult.success("st_epi", 3),
            LayerWriteResult.partial("st_sem", succeeded=2, failed_ids=["x"]),
        ]
        result = WriteResult.from_layer_results(results)

        assert result.is_partial is True

    def test_success_rate(self) -> None:
        """success_rate calculates correctly."""
        results = [
            LayerWriteResult.success("st_epi", 3),
            LayerWriteResult.partial("st_sem", succeeded=2, failed_ids=["x"]),
        ]
        result = WriteResult.from_layer_results(results)

        assert result.success_rate == pytest.approx(5 / 6)

    def test_success_rate_empty(self) -> None:
        """success_rate is 1.0 for empty result."""
        result = WriteResult.empty()
        assert result.success_rate == 1.0

    def test_layers_written(self) -> None:
        """layers_written lists all layers."""
        results = [
            LayerWriteResult.success("st_epi", 3),
            LayerWriteResult.success("st_sem", 5),
        ]
        result = WriteResult.from_layer_results(results)

        assert set(result.layers_written) == {"st_epi", "st_sem"}

    def test_failed_layers(self) -> None:
        """failed_layers lists layers with failures."""
        results = [
            LayerWriteResult.success("st_epi", 3),
            LayerWriteResult.failure("st_sem", "error"),
            LayerWriteResult.partial("st_kg_dom", succeeded=1, failed_ids=["x"]),
        ]
        result = WriteResult.from_layer_results(results)

        assert set(result.failed_layers) == {"st_sem", "st_kg_dom"}


class TestWriteResultMethods:
    """Test WriteResult methods."""

    def test_get_layer_result_exists(self) -> None:
        """get_layer_result returns result for known layer."""
        layer_result = LayerWriteResult.success("st_epi", 5)
        result = WriteResult.from_layer_results([layer_result])

        assert result.get_layer_result("st_epi") is layer_result

    def test_get_layer_result_not_exists(self) -> None:
        """get_layer_result returns None for unknown layer."""
        result = WriteResult.empty()
        assert result.get_layer_result("unknown") is None

    def test_to_dict(self) -> None:
        """to_dict produces expected structure."""
        results = [LayerWriteResult.success("st_epi", 3)]
        result = WriteResult.from_layer_results(results)

        data = result.to_dict()

        assert "total_attempted" in data
        assert "total_succeeded" in data
        assert "total_failed" in data
        assert "by_layer" in data
        assert "success_rate" in data
        assert data["success_rate"] == 1.0

    def test_to_summary_success(self) -> None:
        """to_summary for successful result."""
        results = [
            LayerWriteResult.success("st_epi", 3),
            LayerWriteResult.success("st_sem", 5),
        ]
        result = WriteResult.from_layer_results(results)

        summary = result.to_summary()

        assert "8/8" in summary
        assert "succeeded" in summary
        assert "2 layers" in summary

    def test_to_summary_with_failures(self) -> None:
        """to_summary for result with failures."""
        results = [
            LayerWriteResult.success("st_epi", 3),
            LayerWriteResult.failure("st_sem", "error", ["x", "y"]),
        ]
        result = WriteResult.from_layer_results(results)

        summary = result.to_summary()

        assert "3/5" in summary
        assert "2 failed" in summary
        assert "st_sem" in summary
