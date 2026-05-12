"""Direct tests for ``situation_composer`` module-level helpers.

These cover the defensive branches that are awkward to exercise via the
full ``compose()`` path.
"""

from __future__ import annotations

from k1.selfmodel.contracts.self_model import K1SelfModelSnapshot
from k1.selfmodel.service.situation_composer import (
    _build_applicable_rules,
    _build_capabilities,
    _build_visibility,
    _extract_consent_for_family,
    _extract_role,
    _project_visible_attributes,
)
from k1.selfmodel.contracts.space_graph import FamilyMemberRef


def _snap(*, l1=None, l2=None, l3=None) -> K1SelfModelSnapshot:
    return K1SelfModelSnapshot(
        actor_id="x",
        L1_core=dict(l1 or {}),
        L2_identity=dict(l2 or {}),
        L3_pattern=dict(l3 or {}),
    )


# ---------------------------------------------------------------------
# _extract_role
# ---------------------------------------------------------------------
def test_extract_role_falls_back_to_l1() -> None:
    s = _snap(l1={"role": "guardian"}, l2={})
    assert _extract_role(s) == "guardian"


def test_extract_role_returns_empty_when_missing() -> None:
    assert _extract_role(_snap()) == ""


def test_extract_role_rejects_non_string() -> None:
    s = _snap(l1={"role": 123}, l2={"role_in_family": ""})
    assert _extract_role(s) == ""


# ---------------------------------------------------------------------
# _extract_consent_for_family
# ---------------------------------------------------------------------
def test_consent_missing_returns_empty() -> None:
    assert _extract_consent_for_family(_snap()) == ()


def test_consent_wrong_shape_returns_empty() -> None:
    s = _snap(l1={"consent_posture": "all"})
    assert _extract_consent_for_family(s) == ()


def test_consent_family_value_must_be_iterable() -> None:
    s = _snap(l1={"consent_posture": {"family": 42}})
    assert _extract_consent_for_family(s) == ()


def test_consent_accepts_set_and_frozenset() -> None:
    s = _snap(l1={"consent_posture": {"family": frozenset({"name", "age_band"})}})
    out = sorted(_extract_consent_for_family(s))
    assert out == ["age_band", "name"]


# ---------------------------------------------------------------------
# _project_visible_attributes
# ---------------------------------------------------------------------
def test_project_drops_blocked_l3_keys() -> None:
    s = _snap(l3={"raw_dialogue": "secret", "wake_pattern": "early"})
    out = _project_visible_attributes(s, ("raw_dialogue", "wake_pattern"))
    assert "raw_dialogue" not in out
    assert out["wake_pattern"] == "early"


def test_project_skips_unknown_keys() -> None:
    s = _snap(l1={"name": "Aanya"})
    out = _project_visible_attributes(s, ("name", "no_such_key"))
    assert out == {"name": "Aanya"}


# ---------------------------------------------------------------------
# _build_applicable_rules / _build_capabilities / _build_visibility
# ---------------------------------------------------------------------
def test_build_applicable_rules_handles_empty_body() -> None:
    rules = _build_applicable_rules(
        constitution_body={},
        constitution_version="v0",
        actor_role="guardian",
        situation_kind="caregiver_child_read",
    )
    assert rules.rule_ids == ()
    assert rules.constitution_version == "v0"


def test_build_capabilities_handles_empty_body() -> None:
    caps = _build_capabilities(constitution_body={}, actor_role="guardian")
    assert caps.can_do == ()
    assert caps.requires_confirmation == ()
    assert caps.requires_identity_tier == {}


def test_build_visibility_skips_actor_self() -> None:
    body = {"visibility_rules": {"guardian": {"child": ["name"]}}}
    members = (
        FamilyMemberRef("g1", display_name="A", role="guardian", age_band="adult"),
        FamilyMemberRef("c1", display_name="L", role="child", age_band="child"),
    )
    vis = _build_visibility(
        constitution_body=body, actor_role="guardian",
        members=members, actor_id="g1",
    )
    assert vis.can_see_members == ("c1",)
    assert vis.can_see_attributes == {"c1": ("name",)}


def test_build_visibility_default_deny_for_unmapped_role() -> None:
    body = {"visibility_rules": {"guardian": {"child": ["name"]}}}
    members = (
        FamilyMemberRef("g1", display_name="A", role="guardian", age_band="adult"),
        FamilyMemberRef("t1", display_name="M", role="teen", age_band="teen"),
    )
    vis = _build_visibility(
        constitution_body=body, actor_role="guardian",
        members=members, actor_id="g1",
    )
    assert vis.can_see_members == ()
    assert vis.can_see_attributes == {}
