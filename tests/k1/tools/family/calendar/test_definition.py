"""Tests for ``CALENDAR_DEFINITION`` declarative shape."""

from __future__ import annotations

from k1.tools.family.calendar.definition import CALENDAR_DEFINITION

_EXPECTED_ACTIONS = {
    "create_event",
    "update_event",
    "delete_event",
    "list_events",
    "get_event",
    "respond_to_invite",
    "set_visibility",
    "connect_feed",
    "disconnect_feed",
    "list_feeds",
}


def test_definition_basics() -> None:
    d = CALENDAR_DEFINITION
    assert d.adapter_id == "calendar"
    assert d.category == "coordination"
    assert d.entity_type == "calendar_event"
    assert d.version == "1.0.0"
    assert d.activity_profile == "calendar.v1"
    assert set(d.domain_tags) >= {"scheduling", "availability", "external_calendar"}
    assert d.summary  # non-empty


def test_definition_declares_all_ten_actions() -> None:
    names = {a.name for a in CALENDAR_DEFINITION.actions}
    assert names == _EXPECTED_ACTIONS


def test_tables_sql_contains_schema_version_marker() -> None:
    # P7 invariant: tables_sql validator already enforces this, but we
    # double-check at the API level too.
    assert "calendar_schema_version" in CALENDAR_DEFINITION.tables_sql
    assert "calendar_events" in CALENDAR_DEFINITION.tables_sql
    assert "calendar_feeds" in CALENDAR_DEFINITION.tables_sql


def test_parent_only_actions_have_min_role() -> None:
    parent_only = {"set_visibility", "connect_feed", "disconnect_feed"}
    for name in parent_only:
        spec = CALENDAR_DEFINITION.find_action(name)
        assert spec is not None, name
        assert spec.min_role == "parent", name


def test_idempotent_actions_declared() -> None:
    idem_names = {a.name for a in CALENDAR_DEFINITION.actions if a.idempotent}
    assert idem_names == {"create_event", "connect_feed"}


def test_calendar_write_actions_expose_generic_metadata() -> None:
    for name in ("create_event", "update_event"):
        spec = CALENDAR_DEFINITION.find_action(name)
        assert spec is not None
        params = {param.name: param for param in spec.params}
        assert params["metadata"].type == "object"
        assert "_semantic" in params["metadata"].description


def test_core_calendar_actions_reference_activity_prompt_template() -> None:
    for name in _EXPECTED_ACTIONS:
        spec = CALENDAR_DEFINITION.find_action(name)
        assert spec is not None
        assert spec.prompt_template == "calendar_activity_v1"


def test_action_kinds_partition_correctly() -> None:
    by_kind: dict[str, set[str]] = {}
    for a in CALENDAR_DEFINITION.actions:
        by_kind.setdefault(a.kind, set()).add(a.name)
    assert by_kind["read"] == {"list_events", "get_event", "list_feeds"}
    assert by_kind["delete"] == {"delete_event"}
    assert "create_event" in by_kind["write"]
    assert "respond_to_invite" in by_kind["write"]


def test_sse_topics_follow_canonical_format() -> None:
    for a in CALENDAR_DEFINITION.actions:
        if not a.sse.emits:
            continue
        for topic in a.sse.emits:
            assert topic.startswith("family.calendar.")
            assert topic.endswith(".v1")
