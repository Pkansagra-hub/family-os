"""Empty-Set Invariant E1 — ``(S \\ consent) ∩ F = ∅``.

Whiteboard: "No self-data reaches family without consent. Ever."

These tests construct adversarial fixtures and assert the composer
filters them. Marked ``@pytest.mark.invariant`` so CI can gate on this
class of test specifically.
"""

from __future__ import annotations

import pytest

from k1.selfmodel.contracts.family_model import RelationshipEdge
from k1.selfmodel.contracts.self_model import K1SelfModelSnapshot

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


def test_e1_empty_consent_blocks_all_attribute_leak() -> None:
    """Adversary: child's consent_posture is empty → guardian sees zero attrs."""
    g = make_actor("g1", role="guardian", name="Aanya",
                   consent_family=("name", "role_in_family"))
    # c1's consent posture is missing entirely — should default-deny.
    c = K1SelfModelSnapshot(
        actor_id="c1",
        L1_core={"actor_id": "c1", "name": "Liam", "age_band": "child"},
        L2_identity={"role_in_family": "child"},
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
    # E1: no projected_others entry (empty consent → fully filtered out).
    assert frame.relations.projected_others == ()


def test_e1_consent_narrowing_takes_effect_immediately() -> None:
    """Adversary: a previously-consented attribute is removed from consent.

    The composer must reflect the current consent on the next compose
    call — not a cached prior posture.
    """
    g = make_actor("g1", role="guardian",
                   consent_family=("name", "role_in_family"))
    c = make_actor("c1", role="child", name="Liam",
                   consent_family=("name", "role_in_family", "age_band"))
    fam = make_family(
        members=(make_member("g1", role="guardian"), make_member("c1", role="child")),
        edges=(RelationshipEdge("g1", "c1", "parent_of"),),
    )
    bundle = build_bundle(
        actors=(g, c),
        family=fam,
        constitution=make_constitution(body=v0_body()),
    )

    frame_before = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_child_read")
    others_before = {p.member_id: p for p in frame_before.relations.projected_others}
    assert "age_band" in others_before["c1"].visible_attributes

    # Narrow c1's consent: drop age_band.
    narrowed = make_actor(
        "c1", role="child", name="Liam",
        consent_family=("name", "role_in_family"),
    )
    bundle.store.write_self(narrowed, writer_id="test:fixture")

    frame_after = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_child_read")
    others_after = {p.member_id: p for p in frame_after.relations.projected_others}
    assert "age_band" not in others_after["c1"].visible_attributes


def test_e1_guest_with_no_consent_yields_empty_projection() -> None:
    """Adversary: a guest joins; their consent has not been declared."""
    g = make_actor("g1", role="guardian",
                   consent_family=("name", "role_in_family"))
    guest = K1SelfModelSnapshot(
        actor_id="x1",
        L1_core={"actor_id": "x1", "name": "Visitor"},
        L2_identity={"role_in_family": "guest"},
    )
    fam = make_family(
        members=(make_member("g1", role="guardian"), make_member("x1", role="guest")),
        edges=(RelationshipEdge("g1", "x1", "hosts"),),
    )
    bundle = build_bundle(
        actors=(g, guest),
        family=fam,
        constitution=make_constitution(body=v0_body()),
    )
    frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_context_briefing")
    assert frame.relations.projected_others == ()


def test_e1_consent_field_present_but_malformed_defaults_deny() -> None:
    """Adversary: consent_posture is the wrong shape (string instead of dict)."""
    g = make_actor("g1", role="guardian",
                   consent_family=("name", "role_in_family"))
    c = K1SelfModelSnapshot(
        actor_id="c1",
        L1_core={
            "actor_id": "c1",
            "name": "Liam",
            "consent_posture": "all_fields",  # NOT a dict
        },
        L2_identity={"role_in_family": "child"},
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
    assert frame.relations.projected_others == ()
