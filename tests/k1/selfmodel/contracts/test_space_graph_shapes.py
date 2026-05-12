"""M0.E1.I2 — family_model contract dataclasses are frozen and minimal-construct."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from k1.selfmodel.contracts.family_model import (
    FamilyMemberRef,
    FamilySelfModelSnapshot,
    RelationshipEdge,
    RoutineRef,
)


def test_family_member_ref_min_construct() -> None:
    m = FamilyMemberRef(member_id="alice")
    assert m.member_id == "alice"
    assert m.display_name == ""
    assert m.role == ""
    assert m.age_band == ""


def test_relationship_edge_min_construct() -> None:
    e = RelationshipEdge(from_member="alice", to_member="bob", kind="parent_of")
    assert e.from_member == "alice"
    assert e.to_member == "bob"
    assert e.kind == "parent_of"
    assert e.weight == 1.0


def test_routine_ref_min_construct() -> None:
    r = RoutineRef(routine_id="r-bedtime")
    assert r.routine_id == "r-bedtime"
    assert r.name == ""
    assert r.schedule == ""


def test_family_self_model_snapshot_min_construct() -> None:
    snap = FamilySelfModelSnapshot(family_space_id="fs-1")
    assert snap.family_space_id == "fs-1"
    assert snap.members == ()
    assert snap.relations == ()
    assert snap.routines == ()


@pytest.mark.parametrize(
    "instance,field_name",
    [
        (FamilyMemberRef(member_id="alice"), "member_id"),
        (RelationshipEdge(from_member="a", to_member="b", kind="x"), "from_member"),
        (RoutineRef(routine_id="r-1"), "routine_id"),
        (FamilySelfModelSnapshot(family_space_id="fs-1"), "family_space_id"),
    ],
)
def test_family_dataclasses_are_frozen(instance: object, field_name: str) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(instance, field_name, "tampered")
