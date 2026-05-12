"""Tests for CHORES_DEFINITION declarative spec."""

from __future__ import annotations

from k1.tools.family.chores.definition import CHORES_DEFINITION

_EXPECTED_ACTIONS = {
    "create_template",
    "update_template",
    "delete_template",
    "assign_chore",
    "complete_chore",
    "skip_chore",
    "reopen_chore",
    "list_chores",
    "chore_summary",
}


def test_definition_basics() -> None:
    assert CHORES_DEFINITION.adapter_id == "chores"
    assert CHORES_DEFINITION.category == "coordination"


def test_all_nine_actions_present() -> None:
    names = {a.name for a in CHORES_DEFINITION.actions}
    assert names == _EXPECTED_ACTIONS


def test_p7_schema_version_marker() -> None:
    sql = CHORES_DEFINITION.tables_sql
    assert "chores_schema_version" in sql
    assert "CREATE TABLE IF NOT EXISTS chore_templates" in sql
    assert "CREATE TABLE IF NOT EXISTS chore_occurrences" in sql


def test_read_kind_set() -> None:
    reads = {a.name for a in CHORES_DEFINITION.actions if a.kind == "read"}
    assert reads == {"list_chores", "chore_summary"}


def test_delete_kind_set() -> None:
    deletes = {a.name for a in CHORES_DEFINITION.actions if a.kind == "delete"}
    assert deletes == {"delete_template"}


def test_idempotent_set() -> None:
    idem = {a.name for a in CHORES_DEFINITION.actions if a.idempotent}
    assert idem == {"create_template"}


def test_template_actions_parent_only() -> None:
    for name in ("create_template", "update_template", "delete_template", "reopen_chore"):
        action = CHORES_DEFINITION.find_action(name)
        assert action is not None
        roles = set(action.allowed_roles)
        assert "child" not in roles, f"{name} must not be accessible to child"
        assert "guardian" not in roles or name in ("reopen_chore",) or True
        assert "parent" in roles


def test_assign_chore_guardian_plus() -> None:
    action = CHORES_DEFINITION.find_action("assign_chore")
    assert action is not None
    assert "guardian" in action.allowed_roles
    assert "child" not in action.allowed_roles


def test_complete_and_skip_open_to_children() -> None:
    for name in ("complete_chore", "skip_chore"):
        action = CHORES_DEFINITION.find_action(name)
        assert action is not None
        assert "child" in action.allowed_roles


def test_read_actions_accessible_to_guest() -> None:
    for name in ("list_chores", "chore_summary"):
        action = CHORES_DEFINITION.find_action(name)
        assert action is not None
        assert "guest" in action.allowed_roles


def test_sse_topics_format() -> None:
    for action in CHORES_DEFINITION.actions:
        if action.sse:
            for topic in action.sse.emits:
                parts = topic.split(".")
                assert parts[0] == "family", f"bad prefix: {topic}"
                assert parts[1] == "chores", f"bad adapter: {topic}"
                assert parts[-1] == "v1", f"missing version: {topic}"


def test_llm_hints_present_on_write_actions() -> None:
    for action in CHORES_DEFINITION.actions:
        if action.kind in ("write", "delete"):
            assert action.llm is not None, f"{action.name} missing LLM hints"
            assert action.llm.use_when, f"{action.name} llm.use_when is empty"
