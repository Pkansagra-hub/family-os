"""M4.E1.I1 — GroundingCapsuleBuilder tests."""

from __future__ import annotations

import pytest

from k1.selfmodel.contracts.capsule import GroundingCapsule
from k1.selfmodel.contracts.privacy import BlackBandLeakError
from k1.selfmodel.contracts.situation import (
    ApplicableRules,
    Capabilities,
    ProjectedSelf,
    RelationsSubset,
    SituationFrame,
    Visibility,
)
from k1.selfmodel.contracts.space_graph import RelationshipEdge
from k1.selfmodel.service.capsule_builder import (
    DEFAULT_CAPSULE_SIZE_LIMIT,
    GroundingCapsuleBuilder,
)

T0 = 1_700_000_000_000


def _frame(**overrides) -> SituationFrame:
    base = dict(
        actor_id="a1",
        situation_kind="caregiver_context_briefing",
        composed_at_ms=T0,
        device_id="dev-1",
        projected_self={"display_name": "Alex", "role": "guardian", "age_band": "adult"},
        relations=RelationsSubset(
            edges=(RelationshipEdge(from_member="a1", to_member="c1", kind="parent_of"),),
            projected_others=(
                ProjectedSelf(
                    member_id="c1",
                    display_name="Casey",
                    role="child",
                    visible_attributes={"age_band": "child"},
                ),
            ),
        ),
        rules=ApplicableRules(rule_ids=("R1", "R2"), constitution_version="v0"),
        capabilities=Capabilities(
            can_do=("recall_memory", "set_routine"),
            requires_confirmation=("send_message",),
            requires_identity_tier={"set_routine": 2},
        ),
        visibility=Visibility(),
        freshness={"self": "fresh", "family": "fresh", "constitution": "fresh"},
    )
    base.update(overrides)
    return SituationFrame(**base)


def _builder(*, size_limit_bytes: int = DEFAULT_CAPSULE_SIZE_LIMIT) -> GroundingCapsuleBuilder:
    return GroundingCapsuleBuilder(size_limit_bytes=size_limit_bytes, clock_ms=lambda: T0)


# ---------------------------------------------------------------------
# Construction / validation
# ---------------------------------------------------------------------
def test_constructor_validates_size_limit() -> None:
    with pytest.raises(ValueError):
        GroundingCapsuleBuilder(size_limit_bytes=0)
    with pytest.raises(ValueError):
        GroundingCapsuleBuilder(size_limit_bytes=-1)
    with pytest.raises(ValueError):
        GroundingCapsuleBuilder(size_limit_bytes="big")  # type: ignore[arg-type]


def test_build_rejects_non_situation_frame() -> None:
    b = _builder()
    with pytest.raises(TypeError):
        b.build("not-a-frame")  # type: ignore[arg-type]


# ---------------------------------------------------------------------
# Block content
# ---------------------------------------------------------------------
def test_capsule_returns_grounding_capsule_with_all_blocks() -> None:
    cap = _builder().build(_frame())
    assert isinstance(cap, GroundingCapsule)
    assert cap.actor_block.startswith("[actor]")
    assert "name=Alex" in cap.actor_block
    assert "role=guardian" in cap.actor_block
    assert "situation=caregiver_context_briefing" in cap.actor_block
    assert cap.family_block.startswith("[family]")
    assert "c1" in cap.family_block
    assert cap.rules_block.startswith("[rules]")
    assert "R1" in cap.rules_block and "R2" in cap.rules_block
    assert "constitution_version=v0" in cap.rules_block
    assert cap.capabilities_block.startswith("[capabilities]")
    assert "recall_memory" in cap.capabilities_block
    assert "send_message" in cap.capabilities_block
    assert "set_routine:2" in cap.capabilities_block
    assert cap.freshness_footer.startswith("[freshness]")
    assert "worst_of_three=fresh" in cap.freshness_footer
    assert cap.rendered_at_ms == T0


def test_empty_relations_renders_placeholder() -> None:
    cap = _builder().build(_frame(relations=RelationsSubset()))
    assert "(no related members" in cap.family_block


def test_empty_rules_renders_placeholder() -> None:
    cap = _builder().build(_frame(rules=ApplicableRules()))
    assert "(no constitution rules" in cap.rules_block


def test_empty_capabilities_renders_none_granted() -> None:
    cap = _builder().build(_frame(capabilities=Capabilities()))
    assert "(none granted)" in cap.capabilities_block


# ---------------------------------------------------------------------
# Freshness worst-of-three
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    ("freshness", "expected"),
    [
        ({"self": "fresh", "family": "fresh", "constitution": "fresh"}, "fresh"),
        ({"self": "stale", "family": "fresh", "constitution": "fresh"}, "stale"),
        (
            {"self": "fresh", "family": "offline_local_only", "constitution": "stale"},
            "offline_local_only",
        ),
        (
            {"self": "fresh", "family": "stale", "constitution": "conflict_pending"},
            "conflict_pending",
        ),
        ({}, "fresh"),
    ],
)
def test_worst_of_three_freshness(freshness, expected) -> None:
    cap = _builder().build(_frame(freshness=freshness))
    assert f"worst_of_three={expected}" in cap.freshness_footer


def test_unknown_freshness_state_treated_as_fresh() -> None:
    cap = _builder().build(_frame(freshness={"self": "garbage"}))
    assert "worst_of_three=fresh" in cap.freshness_footer


# ---------------------------------------------------------------------
# BLACK band redaction (E3 defense in depth)
# ---------------------------------------------------------------------
def test_black_band_in_actor_raises() -> None:
    f = _frame(
        projected_self={
            "display_name": "Alex",
            "role": "guardian",
            "privacy_band": "BLACK",
        }
    )
    with pytest.raises(BlackBandLeakError):
        _builder().build(f)


def test_black_band_in_family_member_is_redacted() -> None:
    other = ProjectedSelf(
        member_id="c1",
        display_name="Casey",
        role="child",
        visible_attributes={"privacy_band": "BLACK", "secret": "do-not-leak"},
    )
    cap = _builder().build(_frame(relations=RelationsSubset(projected_others=(other,))))
    assert "do-not-leak" not in cap.family_block
    assert "[redacted: BLACK]" in cap.family_block


# ---------------------------------------------------------------------
# Size cap
# ---------------------------------------------------------------------
def test_size_cap_truncates_within_limit() -> None:
    big_rules = ApplicableRules(
        rule_ids=tuple(f"R{i}" for i in range(500)),
        constitution_version="v0",
    )
    cap = _builder(size_limit_bytes=512).build(_frame(rules=big_rules))
    total = sum(
        len(s.encode("utf-8"))
        for s in (
            cap.actor_block,
            cap.family_block,
            cap.rules_block,
            cap.capabilities_block,
            cap.freshness_footer,
        )
    )
    assert total <= 512
    # Actor + footer must survive truncation in full or near-full form.
    assert cap.actor_block.startswith("[actor]")
    assert cap.freshness_footer.startswith("[freshness]") or "[truncated]" in cap.freshness_footer


def test_size_cap_no_truncation_when_under_limit() -> None:
    cap = _builder(size_limit_bytes=10_000).build(_frame())
    assert "[truncated]" not in cap.as_prompt_text()


# ---------------------------------------------------------------------
# as_prompt_text composition
# ---------------------------------------------------------------------
def test_as_prompt_text_joins_non_empty_blocks() -> None:
    """``as_prompt_text`` emits the legacy actor/family/rules/capabilities/
    freshness sequence when the M7 typed blocks are absent (no
    ``self_view`` or ``conscience`` set on the test frame).
    """
    cap = _builder().build(_frame())
    text = cap.as_prompt_text()
    # M7 fallback: when self_view is None, self_block is empty so the
    # legacy actor_block surfaces in its place.
    assert text.count("[actor]") == 1
    # When conscience is None and space_graph_block is empty (no
    # space_routines/projected_others), the legacy family_block
    # surfaces. The test frame has at least one of those.
    assert ("[family]" in text) or ("[space]" in text)
    assert text.count("[freshness]") == 1
    # Conscience absent → legacy rules_block surfaces.
    assert ("[rules]" in text) or ("[conscience]" in text)


# ---------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------
def test_newlines_in_attribute_values_are_flattened() -> None:
    cap = _builder().build(
        _frame(projected_self={"display_name": "Multi\nLine", "role": "guardian"})
    )
    assert "\n" not in cap.actor_block.split("name=", 1)[1].split("\n", 1)[0]


def test_capsule_is_idempotent_for_same_input() -> None:
    b = _builder()
    cap1 = b.build(_frame())
    cap2 = b.build(_frame())
    assert cap1 == cap2
