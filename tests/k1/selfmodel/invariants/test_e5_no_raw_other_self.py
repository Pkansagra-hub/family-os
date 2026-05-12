"""Empty-Set Invariant E5 — ``raw_S(other) ∩ ProjectedSelf(actor) = ∅``.

Whiteboard: "SituationFrame never carries another person's raw S. Only
projections."
"""

from __future__ import annotations

import json

import pytest

from k1.selfmodel.contracts.space_graph import RelationshipEdge
from k1.selfmodel.contracts.self_model import LayerObservation
from k1.selfmodel.contracts.situation import ProjectedSelf

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


def _build_two_actor_household():
    g = make_actor(
        "g1", role="guardian", name="Aanya",
        consent_family=("name", "role_in_family"),
    )
    c = make_actor(
        "c1", role="child", name="Liam", age_band="child",
        consent_family=("name", "role_in_family", "age_band", "schedule"),
        extra_l3={"schedule": {"after_school": "soccer"}},
        extra_l4={"copresence": {"in_bedroom": True}},
        extra_l5={"mood": {"frustrated": True}},
    )
    fam = make_family(
        members=(make_member("g1", role="guardian"), make_member("c1", role="child")),
        edges=(RelationshipEdge("g1", "c1", "parent_of"),),
    )
    return build_bundle(
        actors=(g, c),
        family=fam,
        constitution=make_constitution(body=v0_body()),
    )


def test_e5_relations_contains_only_projected_self_instances() -> None:
    bundle = _build_two_actor_household()
    frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_child_read")
    for entry in frame.relations.projected_others:
        assert isinstance(entry, ProjectedSelf), (
            f"E5 violation: relations contains {type(entry).__name__}"
        )


def test_e5_raw_l3_keys_in_blocklist_are_never_projected() -> None:
    """Even if visibility + consent allowlist the key, raw_dialogue/etc never project."""
    g = make_actor("g1", role="guardian",
                   consent_family=("name", "role_in_family"))
    c = make_actor(
        "c1", role="child",
        consent_family=("name", "raw_dialogue", "raw_audio_features"),
        extra_l3={
            "raw_dialogue": "secret transcript",
            "raw_audio_features": [0.1, 0.2],
        },
    )
    body = v0_body(
        extra_visibility={
            "guardian": {"child": ["name", "raw_dialogue", "raw_audio_features"]},
        }
    )
    fam = make_family(
        members=(make_member("g1", role="guardian"), make_member("c1", role="child")),
        edges=(RelationshipEdge("g1", "c1", "parent_of"),),
    )
    bundle = build_bundle(
        actors=(g, c),
        family=fam,
        constitution=make_constitution(body=body),
    )
    frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_child_read")
    others = {p.member_id: p for p in frame.relations.projected_others}
    assert "raw_dialogue" not in others["c1"].visible_attributes
    assert "raw_audio_features" not in others["c1"].visible_attributes


def test_e5_other_actors_l4_l5_never_in_frame_transient() -> None:
    """Adversary: c1 has L4/L5 RAM data; g1's frame must not surface it."""
    bundle = _build_two_actor_household()
    bundle.self_model.update_layer(
        "L4",
        LayerObservation(
            actor_id="c1", layer="L4", kind="copresence",
            payload={"in_bedroom": True}, observed_at_ms=T0_MS,
        ),
    )
    bundle.self_model.update_layer(
        "L5",
        LayerObservation(
            actor_id="c1", layer="L5", kind="mood",
            payload={"frustrated": True}, observed_at_ms=T0_MS,
        ),
    )
    frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_context_briefing")
    # transient must only carry g1's own data.
    serialized = json.dumps(frame.transient, default=str)
    assert "in_bedroom" not in serialized
    assert "frustrated" not in serialized


def test_e5_full_frame_serialised_contains_no_raw_other_layers() -> None:
    """Brutal sweep: serialise the whole frame, assert no leak strings appear."""
    g = make_actor(
        "g1", role="guardian", name="Aanya",
        consent_family=("name", "role_in_family"),
    )
    leak_marker = "DO_NOT_LEAK_THIS_TOKEN_4729AB"
    c = make_actor(
        "c1", role="child", name="Liam",
        consent_family=("name", "role_in_family", "age_band"),
        extra_l3={"private_pattern": leak_marker},  # no visibility rule for this key
        extra_l4={"deep_secret": leak_marker},
        extra_l5={"deeper_secret": leak_marker},
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
    bundle.self_model.update_layer(
        "L4",
        LayerObservation(
            actor_id="c1", layer="L4", kind="deep_secret",
            payload={"value": leak_marker}, observed_at_ms=T0_MS,
        ),
    )
    frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_pattern_analysis")
    blob = json.dumps(
        {
            "projected_self": frame.projected_self,
            "relations_attrs": [
                {"id": p.member_id, "attrs": p.visible_attributes}
                for p in frame.relations.projected_others
            ],
            "transient": frame.transient,
            "freshness": frame.freshness,
        },
        default=str,
    )
    assert leak_marker not in blob, "E5 leak: raw private value reached SituationFrame"


def test_e5_dangling_edge_to_unknown_member_does_not_fabricate_projection() -> None:
    """Adversary: family has an edge pointing at a member with no S row."""
    g = make_actor("g1", role="guardian",
                   consent_family=("name", "role_in_family"))
    fam = make_family(
        members=(
            make_member("g1", role="guardian"),
            make_member("c_phantom", role="child"),
        ),
        edges=(RelationshipEdge("g1", "c_phantom", "parent_of"),),
    )
    bundle = build_bundle(
        actors=(g,),  # no c_phantom snapshot
        family=fam,
        constitution=make_constitution(body=v0_body()),
    )
    frame = bundle.composer.compose("g1", T0_MS, "d1", "caregiver_child_read")
    # Default-deny: phantom not in projected_others.
    assert all(p.member_id != "c_phantom" for p in frame.relations.projected_others)
