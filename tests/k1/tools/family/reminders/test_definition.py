"""Tests for ``REMINDERS_DEFINITION`` declarative spec."""

from __future__ import annotations

from k1.fabric.manifest_translator import build_contract
from k1.tools.family.reminders.definition import REMINDERS_DEFINITION

_EXPECTED_ACTIONS = {
    "create_reminder",
    "update_reminder",
    "snooze_reminder",
    "dismiss_reminder",
    "fire_reminder",
    "delete_reminder",
    "list_reminders",
    "get_reminder",
}


def test_definition_basics() -> None:
    assert REMINDERS_DEFINITION.adapter_id == "reminders"
    assert REMINDERS_DEFINITION.category == "coordination"
    assert REMINDERS_DEFINITION.activity_profile == "reminders.v1"
    assert set(REMINDERS_DEFINITION.domain_tags) >= {"alerting", "notification", "scheduler"}


def test_all_eight_actions_present() -> None:
    names = {a.name for a in REMINDERS_DEFINITION.actions}
    assert names == _EXPECTED_ACTIONS


def test_p7_schema_version_marker() -> None:
    sql = REMINDERS_DEFINITION.tables_sql
    assert "reminders_schema_version" in sql
    assert "CREATE TABLE IF NOT EXISTS reminders" in sql


def test_idempotent_set() -> None:
    idem = {a.name for a in REMINDERS_DEFINITION.actions if a.idempotent}
    assert idem == {"create_reminder"}


def test_read_kind_set() -> None:
    reads = {a.name for a in REMINDERS_DEFINITION.actions if a.kind == "read"}
    assert reads == {"list_reminders", "get_reminder"}


def test_delete_kind_set() -> None:
    deletes = {a.name for a in REMINDERS_DEFINITION.actions if a.kind == "delete"}
    assert deletes == {"delete_reminder"}


def test_fire_reminder_system_only() -> None:
    fire = REMINDERS_DEFINITION.find_action("fire_reminder")
    assert fire is not None
    assert fire.allowed_roles == ["system"]
    assert fire.prompt_template is None
    assert fire.tool_instructions is not None
    assert "Scheduler-only" in fire.tool_instructions


def test_sse_topics_format() -> None:
    for action in REMINDERS_DEFINITION.actions:
        if action.sse:
            for topic in action.sse.emits:
                parts = topic.split(".")
                assert parts[0] == "family", f"bad topic prefix: {topic}"
                assert parts[1] == "reminders", f"bad adapter in topic: {topic}"
                assert parts[-1] == "v1", f"missing version suffix: {topic}"


def test_llm_hints_present_on_write_actions() -> None:
    for action in REMINDERS_DEFINITION.actions:
        if action.kind in ("write", "delete"):
            assert action.llm is not None, f"{action.name} missing LLM hints"


def test_no_user_invokable_reminder_action_carries_legacy_prompt_template() -> None:
    for action in REMINDERS_DEFINITION.actions:
        if action.name == "fire_reminder":
            continue
        assert action.prompt_template is None, action.name


def test_reminder_contracts_inherit_activity_profile_metadata() -> None:
    action = REMINDERS_DEFINITION.find_action("create_reminder")
    assert action is not None

    contract = build_contract(REMINDERS_DEFINITION, action)

    assert contract.activity_profile == "reminders.v1"
    assert contract.prompt_template is None
    assert "alerting" in contract.domain
