"""M4.E1.I2 — GroundingCapsuleRenderer + DynamicPromptBuilder injection tests."""

from __future__ import annotations

import pytest

from k1.selfmodel.adapters.grounding_capsule_renderer import GroundingCapsuleRenderer
from k1.selfmodel.contracts.capsule import GroundingCapsule
from k1.selfmodel.contracts.situation import SituationFrame
from k1.selfmodel.service.capsule_builder import GroundingCapsuleBuilder

T0 = 1_700_000_000_000


def _frame() -> SituationFrame:
    return SituationFrame(
        actor_id="a1",
        situation_kind="caregiver_context_briefing",
        composed_at_ms=T0,
    )


# ---------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------
def test_constructor_requires_builder() -> None:
    with pytest.raises(ValueError):
        GroundingCapsuleRenderer(builder=None, frame_provider=lambda: _frame())  # type: ignore[arg-type]


def test_constructor_requires_callable_provider() -> None:
    b = GroundingCapsuleBuilder()
    with pytest.raises(ValueError):
        GroundingCapsuleRenderer(builder=b, frame_provider=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------
def test_render_returns_capsule() -> None:
    r = GroundingCapsuleRenderer(
        builder=GroundingCapsuleBuilder(clock_ms=lambda: T0),
        frame_provider=_frame,
    )
    cap = r.render()
    assert isinstance(cap, GroundingCapsule)
    assert cap.actor_block.startswith("[actor]")


# ---------------------------------------------------------------------
# Fail-soft
# ---------------------------------------------------------------------
def test_render_returns_none_on_provider_exception() -> None:
    def boom() -> SituationFrame:
        raise RuntimeError("composer down")

    r = GroundingCapsuleRenderer(
        builder=GroundingCapsuleBuilder(),
        frame_provider=boom,
    )
    assert r.render() is None


def test_render_returns_none_on_builder_exception() -> None:
    class _BrokenBuilder:
        def build(self, frame):
            raise RuntimeError("rendering exploded")

    r = GroundingCapsuleRenderer(
        builder=_BrokenBuilder(),  # type: ignore[arg-type]
        frame_provider=_frame,
    )
    assert r.render() is None
