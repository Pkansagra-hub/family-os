"""M0.E1.I2 — situation frame contract dataclasses are frozen and minimal-construct."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from k1.selfmodel.contracts.situation import (
    ApplicableRules,
    Capabilities,
    ProjectedSelf,
    RelationsSubset,
    SituationFrame,
    Visibility,
)


def test_projected_self_min_construct() -> None:
    p = ProjectedSelf(member_id="bob")
    assert p.member_id == "bob"
    assert p.visible_attributes == {}


def test_relations_subset_min_construct() -> None:
    r = RelationsSubset()
    assert r.edges == ()
    assert r.projected_others == ()


def test_applicable_rules_min_construct() -> None:
    r = ApplicableRules()
    assert r.rule_ids == ()
    assert r.constitution_version == ""


def test_capabilities_min_construct() -> None:
    c = Capabilities()
    assert c.can_do == ()
    assert c.requires_confirmation == ()
    assert c.requires_identity_tier == {}


def test_visibility_min_construct() -> None:
    v = Visibility()
    assert v.can_see_members == ()
    assert v.can_see_attributes == {}


def test_situation_frame_min_construct() -> None:
    f = SituationFrame(actor_id="alice", situation_kind="S1")
    assert f.actor_id == "alice"
    assert f.situation_kind == "S1"
    assert isinstance(f.relations, RelationsSubset)
    assert isinstance(f.rules, ApplicableRules)
    assert isinstance(f.capabilities, Capabilities)
    assert isinstance(f.visibility, Visibility)


@pytest.mark.parametrize(
    "instance,field_name",
    [
        (ProjectedSelf(member_id="x"), "member_id"),
        (RelationsSubset(), "edges"),
        (ApplicableRules(), "rule_ids"),
        (Capabilities(), "can_do"),
        (Visibility(), "can_see_members"),
        (SituationFrame(actor_id="a", situation_kind="S1"), "actor_id"),
    ],
)
def test_situation_dataclasses_are_frozen(instance: object, field_name: str) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(instance, field_name, "tampered")
