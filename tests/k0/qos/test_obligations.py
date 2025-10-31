"""QoS Obligations and policy integration tests."""

from __future__ import annotations

from typing import Any

import pytest

from k0.qos import QoSContext, Scheduler, apply_qos_obligations, coerce_positive_int


class TestCoercePositiveInt:
    """Test suite for coerce_positive_int() utility."""

    def test_coerce_positive_int_from_int(self) -> None:
        """Coercing positive int returns same value."""
        assert coerce_positive_int(10) == 10
        assert coerce_positive_int(1) == 1

    def test_coerce_positive_int_from_float(self) -> None:
        """Coercing float truncates to int."""
        assert coerce_positive_int(10.7) == 10
        assert coerce_positive_int(1.1) == 1

    def test_coerce_positive_int_from_string(self) -> None:
        """Coercing string parses as number."""
        assert coerce_positive_int("25") == 25
        assert coerce_positive_int("3.7") == 3

    def test_coerce_positive_int_zero_returns_none(self) -> None:
        """Zero is not positive, returns None."""
        assert coerce_positive_int(0) is None
        assert coerce_positive_int(0.0) is None
        assert coerce_positive_int("0") is None

    def test_coerce_positive_int_negative_returns_none(self) -> None:
        """Negative values return None."""
        assert coerce_positive_int(-5) is None
        assert coerce_positive_int(-1.5) is None
        assert coerce_positive_int("-10") is None

    def test_coerce_positive_int_from_dict_key_priority(self) -> None:
        """Coercing dict tries keys in order: requested, value, current, max, limit."""
        assert coerce_positive_int({"requested": 10}) == 10
        assert coerce_positive_int({"value": 5}) == 5
        assert coerce_positive_int({"current": 3}) == 3
        assert coerce_positive_int({"max": 8}) == 8
        assert coerce_positive_int({"limit": 2}) == 2

    def test_coerce_positive_int_from_dict_first_valid_wins(self) -> None:
        """From dict, first valid key wins."""
        result = coerce_positive_int({"requested": 10, "max": 5})
        assert result == 10  # requested comes first

    def test_coerce_positive_int_from_sequence(self) -> None:
        """Coercing sequence returns first positive int."""
        assert coerce_positive_int([None, 5, 10]) == 5
        assert coerce_positive_int(["invalid", 3]) == 3

    def test_coerce_positive_int_from_bool_returns_none(self) -> None:
        """Boolean values (even True) return None."""
        assert coerce_positive_int(True) is None
        assert coerce_positive_int(False) is None

    def test_coerce_positive_int_from_none_returns_none(self) -> None:
        """None returns None."""
        assert coerce_positive_int(None) is None

    def test_coerce_positive_int_empty_string_returns_none(self) -> None:
        """Empty string returns None."""
        assert coerce_positive_int("") is None
        assert coerce_positive_int("   ") is None

    def test_coerce_positive_int_invalid_string_returns_none(self) -> None:
        """Non-numeric string returns None."""
        assert coerce_positive_int("abc") is None


class MockObligation:
    """Mock obligation object for testing."""

    def __init__(self, name: str, details: dict[str, Any] | None = None) -> None:
        self.name = name
        self.details = details or {}


class TestApplyQoSObligations:
    """Test suite for apply_qos_obligations() flow."""

    def test_apply_no_obligations_returns_empty_tightening(self) -> None:
        """No obligations means no tightening."""
        scheduler = Scheduler()
        qos = QoSContext(scheduler=scheduler, fanout_budget=5, top_k_budget=8)

        tightening = apply_qos_obligations(qos, [])

        assert tightening.fanout is None
        assert tightening.top_k is None
        assert tightening.time_slice_ms is None
        # QoS context unchanged
        assert qos.fanout_budget == 5
        assert qos.top_k_budget == 8

    def test_apply_non_qos_obligations_ignored(self) -> None:
        """Non-QoS obligations are ignored."""
        scheduler = Scheduler()
        qos = QoSContext(scheduler=scheduler, fanout_budget=5, top_k_budget=8)

        obligations = [
            MockObligation("kernel.audit.log", {"level": "info"}),
            MockObligation("kernel.redact.field", {"fields": ["email"]}),
        ]

        tightening = apply_qos_obligations(qos, obligations)

        assert tightening.fanout is None
        assert tightening.top_k is None
        # QoS context unchanged
        assert qos.fanout_budget == 5
        assert qos.top_k_budget == 8

    def test_apply_tighten_fanout_obligation(self) -> None:
        """kernel.qos.tighten obligation with fanout tightens budget."""
        scheduler = Scheduler()
        qos = QoSContext(scheduler=scheduler, fanout_budget=5, top_k_budget=8)

        obligations = [MockObligation("kernel.qos.tighten", {"fanout": 2})]

        tightening = apply_qos_obligations(qos, obligations)

        assert qos.fanout_budget == 2  # Tightened
        assert qos.top_k_budget == 8  # Unchanged
        assert tightening.fanout == 2
        assert tightening.top_k is None

    def test_apply_tighten_top_k_obligation(self) -> None:
        """kernel.qos.tighten obligation with top_k tightens budget."""
        scheduler = Scheduler()
        qos = QoSContext(scheduler=scheduler, fanout_budget=5, top_k_budget=8)

        obligations = [MockObligation("kernel.qos.tighten", {"top_k": 4})]

        tightening = apply_qos_obligations(qos, obligations)

        assert qos.fanout_budget == 5  # Unchanged
        assert qos.top_k_budget == 4  # Tightened
        assert tightening.fanout is None
        assert tightening.top_k == 4

    def test_apply_tighten_time_slice_obligation(self) -> None:
        """kernel.qos.tighten obligation with time_slice_ms sets time budget."""
        scheduler = Scheduler()
        qos = QoSContext(scheduler=scheduler, fanout_budget=5, top_k_budget=8)

        obligations = [MockObligation("kernel.qos.tighten", {"time_slice_ms": 50})]

        tightening = apply_qos_obligations(qos, obligations)

        # Fanout and top_k unchanged (no fanout/top_k keys)
        assert qos.fanout_budget == 5
        assert qos.top_k_budget == 8
        # Time slice set
        assert tightening.time_slice_ms == 50

    def test_apply_multiple_obligations_all_keys(self) -> None:
        """Single obligation with all tightening keys."""
        scheduler = Scheduler()
        qos = QoSContext(scheduler=scheduler, fanout_budget=5, top_k_budget=8)

        obligations = [
            MockObligation(
                "kernel.qos.tighten",
                {"fanout": 2, "top_k": 4, "time_slice_ms": 100},
            )
        ]

        tightening = apply_qos_obligations(qos, obligations)

        assert qos.fanout_budget == 2
        assert qos.top_k_budget == 4
        assert tightening.fanout == 2
        assert tightening.top_k == 4
        assert tightening.time_slice_ms == 100

    def test_apply_multiple_tighten_obligations_min_wins(self) -> None:
        """Multiple tighten obligations, smallest limit wins."""
        scheduler = Scheduler()
        qos = QoSContext(scheduler=scheduler, fanout_budget=10, top_k_budget=10)

        obligations = [
            MockObligation("kernel.qos.tighten", {"fanout": 5, "top_k": 6}),
            MockObligation("kernel.qos.tighten", {"fanout": 3, "top_k": 8}),
        ]

        tightening = apply_qos_obligations(qos, obligations)

        assert qos.fanout_budget == 3  # min(5, 3)
        assert qos.top_k_budget == 6  # min(6, 8)
        assert tightening.fanout == 3
        assert tightening.top_k == 6

    def test_apply_tighten_with_alternative_key_names(self) -> None:
        """Tighten obligation tries alternative key names."""
        scheduler = Scheduler()
        qos = QoSContext(scheduler=scheduler, fanout_budget=10, top_k_budget=10)

        # Use alternative names: fanout_max, top_k_max, latency_ms
        obligations = [
            MockObligation(
                "kernel.qos.tighten",
                {"fanout_max": 4, "top_k_max": 5, "latency_ms": 75},
            )
        ]

        tightening = apply_qos_obligations(qos, obligations)

        assert qos.fanout_budget == 4
        assert qos.top_k_budget == 5
        assert tightening.time_slice_ms == 75

    def test_apply_mixed_qos_and_non_qos_obligations(self) -> None:
        """Mix of QoS and non-QoS obligations processes correctly."""
        scheduler = Scheduler()
        qos = QoSContext(scheduler=scheduler, fanout_budget=8, top_k_budget=10)

        obligations = [
            MockObligation("kernel.audit.log", {"level": "warning"}),
            MockObligation("kernel.qos.tighten", {"fanout": 3}),
            MockObligation("kernel.redact.field", {"fields": ["email"]}),
            MockObligation("kernel.qos.tighten", {"top_k": 5}),
        ]

        tightening = apply_qos_obligations(qos, obligations)

        # Only QoS obligations processed
        assert qos.fanout_budget == 3
        assert qos.top_k_budget == 5
        assert tightening.fanout == 3
        assert tightening.top_k == 5

    def test_apply_tighten_upward_attempt_ignored(self) -> None:
        """Attempt to increase budget via tighten is ignored."""
        scheduler = Scheduler()
        qos = QoSContext(scheduler=scheduler, fanout_budget=2, top_k_budget=2)

        # Try to increase (should be ignored by tighten logic)
        obligations = [MockObligation("kernel.qos.tighten", {"fanout": 10})]

        tightening = apply_qos_obligations(qos, obligations)

        # Budget not increased
        assert qos.fanout_budget == 2
        # Tightening still records attempted limit
        assert tightening.fanout == 10

    def test_apply_obligation_with_dict_value(self) -> None:
        """Tighten obligation with dict value (coercion)."""
        scheduler = Scheduler()
        qos = QoSContext(scheduler=scheduler, fanout_budget=10, top_k_budget=10)

        obligations = [
            MockObligation(
                "kernel.qos.tighten",
                {"fanout": {"requested": 4}, "top_k": {"max": 5}},
            )
        ]

        tightening = apply_qos_obligations(qos, obligations)

        assert qos.fanout_budget == 4
        assert qos.top_k_budget == 5

    def test_apply_obligation_with_string_value(self) -> None:
        """Tighten obligation with string value (coercion)."""
        scheduler = Scheduler()
        qos = QoSContext(scheduler=scheduler, fanout_budget=10, top_k_budget=10)

        obligations = [
            MockObligation(
                "kernel.qos.tighten",
                {"fanout": "3", "top_k": "6"},
            )
        ]

        tightening = apply_qos_obligations(qos, obligations)

        assert qos.fanout_budget == 3
        assert qos.top_k_budget == 6

    def test_apply_obligation_with_list_value(self) -> None:
        """Tighten obligation with list value (first positive wins)."""
        scheduler = Scheduler()
        qos = QoSContext(scheduler=scheduler, fanout_budget=10, top_k_budget=10)

        obligations = [
            MockObligation(
                "kernel.qos.tighten",
                {"fanout": [None, 4], "top_k": [1, 2, 6]},
            )
        ]

        tightening = apply_qos_obligations(qos, obligations)

        assert qos.fanout_budget == 4
        assert qos.top_k_budget == 1  # First positive in [1, 2, 6]

    def test_apply_obligation_invalid_values_skipped(self) -> None:
        """Invalid coercible values skipped, still processes valid ones."""
        scheduler = Scheduler()
        qos = QoSContext(scheduler=scheduler, fanout_budget=10, top_k_budget=10)

        obligations = [
            MockObligation(
                "kernel.qos.tighten",
                {"fanout": "invalid", "top_k": 5},  # fanout invalid
            )
        ]

        tightening = apply_qos_obligations(qos, obligations)

        assert qos.fanout_budget == 10  # Unchanged (invalid)
        assert qos.top_k_budget == 5  # Tightened
        assert tightening.fanout is None  # Invalid skipped
        assert tightening.top_k == 5


class TestQoSObligationsIntegration:
    """Integration tests for full obligation + QoS flow."""

    def test_full_flow_amber_band_tightening(self) -> None:
        """Full flow: AMBER policy obligation → QoS tightening → rejection."""
        scheduler = Scheduler()
        qos = QoSContext(scheduler=scheduler, fanout_budget=8, top_k_budget=10)

        # Simulate AMBER policy obligations
        obligations = [
            MockObligation("kernel.qos.tighten", {"fanout": 2, "top_k": 4}),
            MockObligation("kernel.audit.log", {"level": "warning"}),
        ]

        # Apply obligations
        tightening = apply_qos_obligations(qos, obligations)

        # Verify tightening
        assert tightening.fanout == 2
        assert tightening.top_k == 4

        # Attempt to consume resources
        qos.consume_fanout(2)  # OK: exactly at limit
        assert qos.fanout_budget == 0

        # Next fanout request should fail
        with pytest.raises(Exception):  # QoSBudgetError
            qos.consume_fanout(1)

    def test_cascade_multiple_policy_decisions(self) -> None:
        """Cascade through multiple policy decision evaluations."""
        scheduler = Scheduler()
        qos = QoSContext(scheduler=scheduler, fanout_budget=16, top_k_budget=32)

        # First policy pass (device band check)
        obligations1 = [MockObligation("kernel.qos.tighten", {"fanout": 8, "top_k": 16})]
        apply_qos_obligations(qos, obligations1)
        assert qos.fanout_budget == 8

        # Second policy pass (role check, further tightening)
        obligations2 = [MockObligation("kernel.qos.tighten", {"fanout": 4, "top_k": 8})]
        apply_qos_obligations(qos, obligations2)
        assert qos.fanout_budget == 4  # Further tightened

        # Third policy pass (no additional tightening)
        obligations3 = [MockObligation("kernel.audit.log", {"level": "info"})]
        apply_qos_obligations(qos, obligations3)
        assert qos.fanout_budget == 4  # Unchanged
        assert qos.fanout_budget == 4  # Unchanged
