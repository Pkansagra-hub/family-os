"""Tests for performance suite package initialization."""

from __future__ import annotations

from ward import test  # type: ignore[attr-defined]


@test("k0.perf package imports successfully")
def _() -> None:
    """Verify performance package can be imported."""
    import k0.perf

    # Package should define expected exports (when implemented)
    assert hasattr(k0.perf, "__all__")
    assert "ScenarioRunner" in k0.perf.__all__
    assert "ScenarioConfig" in k0.perf.__all__
    assert "PushgatewayClient" in k0.perf.__all__
