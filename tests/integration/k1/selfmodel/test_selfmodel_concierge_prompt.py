"""M5.E2.I2 — selfmodel <-> k1.concierge (prompt) seam.

Per IMPLEMENTATION_PLAN_SELF_MODEL.md M5.E2.I2:

    Validate: DynamicPromptBuilder.build() includes capsule for
    every PromptMode; capsule reflects current SituationFrame;
    OPP-7 IdentitySnapshot overlay does not mutate K1SelfModel
    (Invariant I7).
    Acceptance: prompt-injection test green; OPP-7 isolation test green.

Wires the real ``SituationFrameComposer`` -> real
``GroundingCapsuleBuilder`` -> real ``GroundingCapsuleRenderer`` ->
real ``DynamicPromptBuilder.build(grounding_capsule=...)``.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from k1.concierge.prompt.affect import AffectBand
from k1.concierge.prompt.builder import DynamicPromptBuilder
from k1.concierge.prompt.mode import PromptMode
from k1.selfmodel.adapters.grounding_capsule_renderer import (
    GroundingCapsuleRenderer,
)
from k1.selfmodel.service.capsule_builder import GroundingCapsuleBuilder
from tests.k1.selfmodel.service._helpers import (
    T0_MS,
    build_bundle,
    make_actor,
    make_constitution,
    make_family,
    make_member,
    v0_body,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _bundle():
    return build_bundle(
        actors=(make_actor("g1", role="guardian", name="Aanya"),),
        family=make_family(members=(make_member("g1", role="guardian"),)),
        constitution=make_constitution(body=v0_body()),
    )


def _renderer(bundle):
    return GroundingCapsuleRenderer(
        builder=GroundingCapsuleBuilder(clock_ms=lambda: T0_MS),
        frame_provider=lambda: bundle.composer.compose(
            "g1", T0_MS, "d1", "caregiver_context_briefing"
        ),
    )


def _build_for(
    builder: DynamicPromptBuilder,
    mode: PromptMode,
    *,
    grounding_capsule,
):
    """Invoke DynamicPromptBuilder.build for a single mode with no SS."""
    return builder.build(
        mode=mode,
        affect_band=AffectBand(band="neutral"),
        history_messages=[],
        all_tool_schemas=[],
        scenario_data={},
        grounding_capsule=grounding_capsule,
    )


# ---------------------------------------------------------------------
# Capsule appears in every PromptMode
# ---------------------------------------------------------------------
@pytest.mark.parametrize("mode", list(PromptMode))
def test_capsule_appended_to_every_prompt_mode(mode: PromptMode) -> None:
    bundle = _bundle()
    renderer = _renderer(bundle)
    builder = DynamicPromptBuilder()

    capsule = renderer.render()
    assert capsule is not None

    built = _build_for(builder, mode, grounding_capsule=capsule)
    # The capsule's actor block uses a stable [actor]-prefixed line.
    assert (
        "[actor]" in built.system_prompt
    ), f"capsule actor block missing in PromptMode={mode.value}"
    # And one of the capsule's other blocks should also leak into the prompt.
    capsule_text = capsule.as_prompt_text()
    assert capsule_text in built.system_prompt


# ---------------------------------------------------------------------
# Flag-off (capsule=None) leaves the pre-M4 baseline untouched
# ---------------------------------------------------------------------
def test_no_capsule_yields_baseline_prompt() -> None:
    builder = DynamicPromptBuilder()
    base = _build_for(builder, PromptMode.STANDARD, grounding_capsule=None)
    assert "[actor]" not in base.system_prompt


# ---------------------------------------------------------------------
# Capsule reflects current SituationFrame (re-render after mutation)
# ---------------------------------------------------------------------
def test_capsule_reflects_updated_self_model_after_recompose() -> None:
    bundle = _bundle()
    renderer = _renderer(bundle)
    builder = DynamicPromptBuilder()

    first = _build_for(builder, PromptMode.STANDARD, grounding_capsule=renderer.render())
    assert "Aanya" in first.system_prompt

    # Mutate the underlying self snapshot through the canonical writer
    # path; the next render must reflect the new display name.
    old_snap, _ = bundle.store.read_self("g1")
    new_l2 = dict(old_snap.L2_identity)
    new_l2["display_name"] = "Aanya-Updated"
    bundle.store.write_self(
        replace(old_snap, L2_identity=new_l2),
        writer_id="test:fixture",
    )

    second = _build_for(builder, PromptMode.STANDARD, grounding_capsule=renderer.render())
    assert "Aanya-Updated" in second.system_prompt


# ---------------------------------------------------------------------
# OPP-7 isolation: the capsule rendering pipeline never writes back to
# the K1SelfModel projection store. We assert the snapshot's revision
# string is unchanged across many render cycles.
# ---------------------------------------------------------------------
def test_capsule_rendering_does_not_mutate_self_model() -> None:
    bundle = _bundle()
    renderer = _renderer(bundle)
    builder = DynamicPromptBuilder()

    pre_snap, pre_meta = bundle.store.read_self("g1")
    pre_rev = pre_meta.revision.revision

    for _ in range(5):
        _build_for(
            builder,
            PromptMode.STANDARD,
            grounding_capsule=renderer.render(),
        )

    post_snap, post_meta = bundle.store.read_self("g1")
    assert post_meta.revision.revision == pre_rev
    assert post_snap == pre_snap


# ---------------------------------------------------------------------
# Renderer fail-soft: composer down -> capsule None -> baseline prompt
# ---------------------------------------------------------------------
def test_renderer_fail_soft_does_not_break_prompt_build() -> None:
    builder = DynamicPromptBuilder()

    def boom():
        raise RuntimeError("composer down")

    renderer = GroundingCapsuleRenderer(
        builder=GroundingCapsuleBuilder(clock_ms=lambda: T0_MS),
        frame_provider=boom,
    )
    capsule = renderer.render()
    assert capsule is None

    built = _build_for(builder, PromptMode.STANDARD, grounding_capsule=capsule)
    # Baseline assembly succeeded; no exception, no [actor] block.
    assert "[actor]" not in built.system_prompt
    assert isinstance(built.system_prompt, str)
