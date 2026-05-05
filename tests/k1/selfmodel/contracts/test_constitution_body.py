"""Tests for ``constitution_body`` helpers (default-deny everywhere)."""

from __future__ import annotations

from k1.selfmodel.contracts import constitution_body as body


def test_visibility_default_deny() -> None:
    assert body.get_visibility_keys({}, viewer_role="g", target_role="c") == ()
    assert (
        body.get_visibility_keys(
            {"visibility_rules": "not_a_dict"}, viewer_role="g", target_role="c"
        )
        == ()
    )
    assert (
        body.get_visibility_keys(
            {"visibility_rules": {"g": "not_a_dict"}}, viewer_role="g", target_role="c"
        )
        == ()
    )
    assert (
        body.get_visibility_keys(
            {"visibility_rules": {"g": {"c": "not_iterable"}}},
            viewer_role="g",
            target_role="c",
        )
        == ()
    )


def test_visibility_happy_path() -> None:
    body_dict = {
        "visibility_rules": {
            "guardian": {"child": ["name", "age_band", "schedule"]},
        }
    }
    keys = body.get_visibility_keys(body_dict, viewer_role="guardian", target_role="child")
    assert keys == ("name", "age_band", "schedule")


def test_autonomy_default_empty() -> None:
    assert body.get_autonomy_bucket({}, role="guardian", bucket="can") == ()
    assert (
        body.get_autonomy_bucket(
            {"autonomy_rules": {"guardian": {}}}, role="guardian", bucket="can"
        )
        == ()
    )


def test_autonomy_happy_path() -> None:
    body_dict = {
        "autonomy_rules": {
            "guardian": {
                "can": ["recall_memory", "set_routine"],
                "must_ask": ["pickup_change"],
                "cannot": [],
            }
        }
    }
    assert body.get_autonomy_bucket(body_dict, role="guardian", bucket="can") == (
        "recall_memory",
        "set_routine",
    )
    assert body.get_autonomy_bucket(body_dict, role="guardian", bucket="must_ask") == (
        "pickup_change",
    )
    assert body.get_autonomy_bucket(body_dict, role="guardian", bucket="cannot") == ()


def test_authority_clamps_and_defaults() -> None:
    body_dict = {
        "authority_rules": {
            "approve_amendment": 3,
            "set_pickup": 2,
            "weird_negative": -7,
            "weird_high": 99,
            "weird_bool": True,
        }
    }
    assert body.get_authority_tier(body_dict, tool_id="approve_amendment") == 3
    assert body.get_authority_tier(body_dict, tool_id="set_pickup") == 2
    assert body.get_authority_tier(body_dict, tool_id="missing") == 0
    assert body.get_authority_tier(body_dict, tool_id="weird_negative") == 0
    assert body.get_authority_tier(body_dict, tool_id="weird_high") == 3
    # bool is rejected (treated as not-int).
    assert body.get_authority_tier(body_dict, tool_id="weird_bool") == 0


def test_protection_rules_default_empty() -> None:
    assert body.get_protection_rules({}, situation_kind="x") == ()
    body_dict = {
        "protection_rules": {
            "child_explicit_privacy": ["redact_from_siblings"],
        }
    }
    assert body.get_protection_rules(body_dict, situation_kind="child_explicit_privacy") == (
        "redact_from_siblings",
    )
    assert body.get_protection_rules(body_dict, situation_kind="other") == ()
