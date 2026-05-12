"""Empty-Set Invariant E2 — ``(S \\ C.visibility_rules) ∩ F = ∅``.

Whiteboard: "No self-data reaches family without a visibility rule
applying. Default-deny."
"""

from __future__ import annotations

import pytest

from k1.selfmodel.contracts.space_graph import RelationshipEdge

from tests.k1.selfmodel.service._helpers import (
    T0_MS,
    build_bundle,
    make_actor,
    make_constitution,
    make_family,
    make_member,
    v0_body,
)

pytestmark = pytest.mark.invariant


def test_e2_unrecognised_attribute_key_not_projected() -> None:
    """Adversary: child has a new L2 key (``pronouns``) with no visibility rule."""
    g = make_actor("g1", role="guardian",
                   consent_family=("name", "role_in_family"))
    c = make_actor(
        "c1", role="child", name="Liam",
        consent_family=("name", "role_in_family", "pronouns"),
        extra_l2={"pronouns": "they/them"},
    )
    fam = make_family(
        members=(make_member("g1", role="guardian"), make_member("c1", role="child")),
        edges=(RelationshipEdge("g1", "c1", "parent_of"),),
    )
    bundle = build_bundle(
        actors=(g, c),
        family=fam,
        constitution=make_constitution(body=v0_body()),
    )
    frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_child_read")
    others = {p.member_id: p for p in frame.relations.projected_others}
    # pronouns is consented BUT has no visibility rule → omitted.
    assert "pronouns" not in others["c1"].visible_attributes


def test_e2_empty_constitution_blocks_all_projection() -> None:
    """Adversary: constitution has empty body → no rule applies → no F leak."""
    g = make_actor("g1", role="guardian",
                   consent_family=("name", "role_in_family"))
    c = make_actor("c1", role="child", consent_family=("name", "role_in_family"))
    fam = make_family(
        members=(make_member("g1", role="guardian"), make_member("c1", role="child")),
        edges=(RelationshipEdge("g1", "c1", "parent_of"),),
    )
    bundle = build_bundle(
        actors=(g, c),
        family=fam,
        constitution=make_constitution(body={}),
    )
    frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_child_read")
    assert frame.relations.projected_others == ()


def test_e2_role_with_no_visibility_rule_defaults_deny() -> None:
    """Adversary: ``teen`` role is added but no visibility rules exist for it."""
    body = v0_body()
    # Ensure no "teen" visibility rule.
    g = make_actor("g1", role="guardian",
                   consent_family=("name", "role_in_family"))
    teen = make_actor(
        "t1", role="teen", name="Maya",
        consent_family=("name", "role_in_family", "schedule"),
        extra_l3={"schedule": {"after_school": "soccer"}},
    )
    fam = make_family(
        members=(
            make_member("g1", role="guardian"),
            make_member("t1", role="teen"),
        ),
        edges=(RelationshipEdge("g1", "t1", "parent_of"),),
    )
    bundle = build_bundle(
        actors=(g, teen),
        family=fam,
        constitution=make_constitution(body=body),
    )
    frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_child_read")
    # No guardian->teen rule in v0_body() → projected_others must omit t1.
    others_ids = {p.member_id for p in frame.relations.projected_others}
    assert "t1" not in others_ids


def test_e2_visibility_block_is_default_deny_for_unknown_member_role() -> None:
    """Adversary: Visibility output should not list a teen target either."""
    g = make_actor("g1", role="guardian",
                   consent_family=("name", "role_in_family"))
    teen = make_actor("t1", role="teen", consent_family=("name",))
    fam = make_family(
        members=(make_member("g1", role="guardian"), make_member("t1", role="teen")),
        edges=(RelationshipEdge("g1", "t1", "parent_of"),),
    )
    bundle = build_bundle(
        actors=(g, teen),
        family=fam,
        constitution=make_constitution(body=v0_body()),
    )
    frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_pattern_analysis")
    assert "t1" not in frame.visibility.can_see_members
    assert "t1" not in frame.visibility.can_see_attributes
