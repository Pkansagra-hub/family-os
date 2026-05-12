"""Unit tests for ``SituationFrameComposer`` (M1.E2.I1).

Covers the happy path for several of the 13 situations + freshness +
empty-constitution edge cases. Adversarial / leak attempts live in the
``invariants/`` test files.
"""

from __future__ import annotations

import pytest

from k1.selfmodel.contracts.space_graph import RelationshipEdge
from k1.selfmodel.contracts.situations import SITUATION_KINDS
from k1.selfmodel.service.errors import (
    UnknownActorError,
    UnknownSituationError,
)
from tests.k1.selfmodel.service._helpers import (
    T0_MS,
    build_bundle,
    make_actor,
    make_constitution,
    make_family,
    make_member,
    v0_body,
)


# ---------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------
def test_unknown_situation_kind_rejected() -> None:
    bundle = build_bundle(
        actors=(make_actor("g1"),),
        family=make_family(members=(make_member("g1", role="guardian"),)),
        constitution=make_constitution(body=v0_body()),
    )
    with pytest.raises(UnknownSituationError):
        bundle.composer.compose("g1", T0_MS, "d1", "no_such_kind")


def test_empty_actor_id_rejected() -> None:
    bundle = build_bundle()
    with pytest.raises(ValueError):
        bundle.composer.compose("", T0_MS, "d1", "child_daily_read")


def test_unknown_actor_raises() -> None:
    bundle = build_bundle(constitution=make_constitution(body=v0_body()))
    with pytest.raises(UnknownActorError):
        bundle.composer.compose("ghost", T0_MS, "d1", "child_daily_read")


# ---------------------------------------------------------------------
# Single-actor household
# ---------------------------------------------------------------------
def test_single_actor_compose_emits_self_block() -> None:
    bundle = build_bundle(
        actors=(make_actor("g1", role="guardian", name="Aanya"),),
        family=make_family(members=(make_member("g1", role="guardian"),)),
        constitution=make_constitution(body=v0_body()),
    )
    frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_context_briefing")

    assert frame.actor_id == "g1"
    assert frame.situation_kind == "caregiver_context_briefing"
    assert frame.composed_at_ms == T0_MS
    assert frame.device_id == "d1"
    assert frame.projected_self["name"] == "Aanya"
    assert frame.projected_self["role_in_family"] == "guardian"
    assert frame.relations.edges == ()
    assert frame.relations.projected_others == ()


# ---------------------------------------------------------------------
# Multi-actor household
# ---------------------------------------------------------------------
def _household_bundle():
    actors = (
        make_actor("g1", role="guardian", name="Aanya",
                   consent_family=("name", "role_in_family", "schedule")),
        make_actor("c1", role="child", name="Liam", age_band="child",
                   consent_family=("name", "role_in_family", "age_band", "schedule")),
        make_actor("c2", role="child", name="Maya", age_band="child",
                   consent_family=("name",)),
    )
    family = make_family(
        members=(
            make_member("g1", role="guardian", name="Aanya"),
            make_member("c1", role="child", name="Liam"),
            make_member("c2", role="child", name="Maya"),
        ),
        edges=(
            RelationshipEdge("g1", "c1", "parent_of"),
            RelationshipEdge("g1", "c2", "parent_of"),
            RelationshipEdge("c1", "c2", "sibling_of"),
        ),
    )
    return build_bundle(
        actors=actors,
        family=family,
        constitution=make_constitution(body=v0_body()),
    )


def test_guardian_sees_children_through_consent_intersection() -> None:
    bundle = _household_bundle()
    frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_child_read")
    others = {p.member_id: p for p in frame.relations.projected_others}
    assert set(others) == {"c1", "c2"}
    # c1 consented to schedule; visibility allows it for guardian→child.
    assert others["c1"].visible_attributes.get("name") == "Liam"
    # c2 consented only to "name", so age_band/schedule must be omitted.
    assert "age_band" not in others["c2"].visible_attributes
    assert "schedule" not in others["c2"].visible_attributes
    assert others["c2"].visible_attributes.get("name") == "Maya"


def test_visibility_block_lists_per_member_keys() -> None:
    bundle = _household_bundle()
    frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_pattern_analysis")
    assert frame.visibility.can_see_members == ("c1", "c2")
    # Visibility reflects the rule, not the consent intersection (it is
    # the *upper bound* of what could be visible if consent permitted).
    assert "schedule" in frame.visibility.can_see_attributes["c1"]


def test_capabilities_for_guardian() -> None:
    bundle = _household_bundle()
    frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_high_impact_write")
    assert "recall_memory" in frame.capabilities.can_do
    assert "pickup_change" in frame.capabilities.requires_confirmation
    assert frame.capabilities.requires_identity_tier.get("set_routine") == 2


def test_capabilities_for_child() -> None:
    bundle = _household_bundle()
    frame = bundle.composer.compose("c1", T0_MS, "d1", "child_own_action_write")
    assert frame.capabilities.can_do == ("complete_chore",)
    assert frame.capabilities.requires_confirmation == ("leave_house",)


def test_applicable_rules_includes_protection_for_situation() -> None:
    bundle = _household_bundle()
    frame = bundle.composer.compose("c1", T0_MS, "d1", "child_explicit_privacy")
    assert "redact_from_siblings" in frame.rules.rule_ids
    assert "alert_caregiver_safety" in frame.rules.rule_ids
    # Plus the autonomy-derived rule_ids.
    assert any(r.startswith("autonomy:can:") for r in frame.rules.rule_ids)


def test_freshness_block_present() -> None:
    bundle = _household_bundle()
    bundle.store.mark_stale("self:g1")
    frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_child_read")
    assert frame.freshness["self"] == "stale"
    assert frame.freshness["family"] == "fresh"
    assert frame.freshness["constitution"] == "fresh"


# ---------------------------------------------------------------------
# Empty constitution edge case
# ---------------------------------------------------------------------
def test_empty_constitution_yields_default_deny_frame() -> None:
    bundle = _household_bundle()
    # Replace with empty body.
    bundle.store.write_constitution(
        make_constitution(body={}), writer_id="test:fixture"
    )
    frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_child_read")
    assert frame.relations.projected_others == ()  # no visibility rule applies
    assert frame.capabilities.can_do == ()
    assert frame.visibility.can_see_members == ()


def test_unavailable_constitution_still_produces_frame() -> None:
    # Build a bundle where get_active raises (no row).
    actor = make_actor("g1", role="guardian")
    fam = make_family(members=(make_member("g1", role="guardian"),))
    bundle = build_bundle(actors=(actor,), family=fam)  # no constitution!
    frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_context_briefing")
    assert frame.rules.constitution_version == ""
    assert frame.capabilities.can_do == ()


# ---------------------------------------------------------------------
# Transient block (L4/L5)
# ---------------------------------------------------------------------
def test_transient_block_carries_actor_l4_l5_only() -> None:
    bundle = _household_bundle()
    from k1.selfmodel.contracts.self_model import LayerObservation

    bundle.self_model.update_layer(
        "L4",
        LayerObservation(
            actor_id="g1", layer="L4", kind="copresence",
            payload={"in_kitchen": True}, observed_at_ms=T0_MS,
        ),
    )
    # Add L4 to *another* actor — must NOT bleed.
    bundle.self_model.update_layer(
        "L4",
        LayerObservation(
            actor_id="c1", layer="L4", kind="copresence",
            payload={"in_bedroom": True}, observed_at_ms=T0_MS,
        ),
    )
    frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_context_briefing")
    assert frame.transient.get("L4") == {"copresence": {"in_kitchen": True}}
    # E5 partial: c1's L4 must NOT appear anywhere in the frame.
    rendered = repr(frame)
    assert "in_bedroom" not in rendered


# ---------------------------------------------------------------------
# Walk all 13 situations end-to-end
# ---------------------------------------------------------------------
def test_compose_walks_every_v0_situation() -> None:
    bundle = _household_bundle()
    for kind in sorted(SITUATION_KINDS):
        frame = bundle.composer.compose("g1", T0_MS, "d1", kind)
        assert frame.situation_kind == kind
        assert frame.actor_id == "g1"
        # Frame is a dataclass, freshness always populated.
        assert set(frame.freshness) == {"self", "family", "constitution"}


# ---------------------------------------------------------------------
# Composer constructor validation
# ---------------------------------------------------------------------
def test_composer_requires_family_space_id() -> None:
    from k1.selfmodel.service.situation_composer import SituationFrameComposer

    bundle = build_bundle()
    with pytest.raises(ValueError):
        SituationFrameComposer(
            self_model=bundle.self_model,
            space_graph=bundle.space_graph,
            constitution=bundle.constitution,
            space_id="",
        )
