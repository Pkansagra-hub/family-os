"""Unit tests for ``FamilyModelService`` (M1.E1.I2)."""

from __future__ import annotations

import pytest

from k1.selfmodel.contracts.family_model import (
    FamilySelfModelSnapshot,
    RelationshipEdge,
    RoutineRef,
)
from k1.selfmodel.service.family_model import _adjacent_member_ids
from tests.k1.selfmodel.service._helpers import (
    DEFAULT_FAMILY_SPACE,
    build_bundle,
    make_family,
    make_member,
)


def test_get_view_unknown_family_returns_empty_snapshot() -> None:
    bundle = build_bundle()
    res = bundle.family_model.get_view("a1", "fs:nonexistent")
    assert isinstance(res.snapshot, FamilySelfModelSnapshot)
    assert res.snapshot.members == ()
    assert res.snapshot.relations == ()


def test_single_actor_household_has_no_relations() -> None:
    fam = make_family(members=(make_member("a1", role="guardian"),))
    bundle = build_bundle(family=fam)
    res = bundle.family_model.get_view("a1", DEFAULT_FAMILY_SPACE)
    assert res.snapshot.relations == ()
    assert len(res.snapshot.members) == 1


def test_only_adjacent_edges_returned() -> None:
    fam = make_family(
        members=(
            make_member("g1", role="guardian"),
            make_member("g2", role="guardian"),
            make_member("c1", role="child"),
            make_member("c2", role="child"),
        ),
        edges=(
            RelationshipEdge("g1", "c1", "parent_of"),
            RelationshipEdge("g1", "c2", "parent_of"),
            RelationshipEdge("g2", "c1", "parent_of"),  # NOT adjacent to g1? — yes, not via g1
            RelationshipEdge("c1", "c2", "sibling_of"),
        ),
    )
    bundle = build_bundle(family=fam)
    res = bundle.family_model.get_view("g1", DEFAULT_FAMILY_SPACE)
    edge_kinds = sorted((e.from_member, e.to_member, e.kind) for e in res.snapshot.relations)
    assert edge_kinds == [
        ("g1", "c1", "parent_of"),
        ("g1", "c2", "parent_of"),
    ]


def test_routines_passed_through() -> None:
    fam = make_family(
        members=(make_member("a1", role="guardian"),),
        routines=(RoutineRef(routine_id="r1", name="bedtime"),),
    )
    bundle = build_bundle(family=fam)
    res = bundle.family_model.get_view("a1", DEFAULT_FAMILY_SPACE)
    assert res.snapshot.routines == (RoutineRef(routine_id="r1", name="bedtime"),)


def test_get_view_requires_actor_and_family() -> None:
    bundle = build_bundle()
    with pytest.raises(ValueError):
        bundle.family_model.get_view("", "fs1")
    with pytest.raises(ValueError):
        bundle.family_model.get_view("a1", "")


def test_get_member_lookup() -> None:
    fam = make_family(
        members=(make_member("g1", role="guardian"), make_member("c1", role="child")),
    )
    bundle = build_bundle(family=fam)
    g = bundle.family_model.get_member(DEFAULT_FAMILY_SPACE, "g1")
    assert g is not None and g.role == "guardian"
    assert bundle.family_model.get_member(DEFAULT_FAMILY_SPACE, "ghost") is None
    assert bundle.family_model.get_member("fs:nonexistent", "g1") is None


def test_freshness_helper() -> None:
    fam = make_family(members=(make_member("a1", role="guardian"),))
    bundle = build_bundle(family=fam)
    assert bundle.family_model.freshness(DEFAULT_FAMILY_SPACE).value == "fresh"
    bundle.store.mark_stale(f"family:{DEFAULT_FAMILY_SPACE}")
    assert bundle.family_model.freshness(DEFAULT_FAMILY_SPACE).value == "stale"


# ---------------------------------------------------------------------
# Adjacency helper exposed to the composer
# ---------------------------------------------------------------------
def test_adjacent_member_ids_dedupes_and_excludes_self() -> None:
    edges = (
        RelationshipEdge("g1", "c1", "parent_of"),
        RelationshipEdge("c1", "g1", "child_of"),  # reverse edge
        RelationshipEdge("g1", "c2", "parent_of"),
        RelationshipEdge("g1", "g1", "self_loop"),  # self-loop ignored
    )
    assert _adjacent_member_ids(edges, "g1") == ("c1", "c2")
    assert _adjacent_member_ids((), "g1") == ()
