"""Tests for chaos module initialization and exports."""

from __future__ import annotations

from k0.chaos import (
    ChaosDecision,
    ChaosTransport,
    apply_scheduler_starvation,
    get_network_delay_ms,
    should_drop_telemetry,
    should_fail_fsync,
)


class TestChaosModuleExports:
    """Test that chaos module exports are properly available."""

    def test_chaos_decision_dataclass(self):
        """Test ChaosDecision dataclass can be instantiated."""
        decision = ChaosDecision(should_inject=True, reason="test", metadata={"key": "value"})

        assert decision.should_inject is True
        assert decision.reason == "test"
        assert decision.metadata == {"key": "value"}

    def test_chaos_decision_defaults(self):
        """Test ChaosDecision default values."""
        decision = ChaosDecision(should_inject=False)

        assert decision.should_inject is False
        assert decision.reason is None
        assert decision.metadata is None

    def test_exports_available(self):
        """Test that all expected exports are available."""
        # These should not raise ImportError
        assert ChaosDecision is not None
        assert ChaosTransport is not None
        assert should_fail_fsync is not None
        assert apply_scheduler_starvation is not None
        assert get_network_delay_ms is not None
        assert should_drop_telemetry is not None

    def test_all_exports_in___all__(self):
        """Test that __all__ contains expected exports."""
        import k0.chaos as chaos_module

        expected_exports = [
            "ChaosDecision",
            "should_fail_fsync",
            "apply_scheduler_starvation",
            "get_network_delay_ms",
            "should_drop_telemetry",
            "ChaosTransport",
        ]

        assert hasattr(chaos_module, "__all__")
        assert chaos_module.__all__ == expected_exports
