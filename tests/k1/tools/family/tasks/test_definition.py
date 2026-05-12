"""Tests for ``TASKS_DEFINITION`` declarative spec."""

from __future__ import annotations

from k1.tools.family.tasks.definition import TASKS_DEFINITION

_EXPECTED_ACTIONS = {
    "create_task",
    "update_task",
    "complete_task",
    "reopen_task",
    "reassign_task",
    "delete_task",
    "list_tasks",
    "get_task",
    "create_list",
    "list_lists",
}


def test_definition_basics() -> None:
    assert TASKS_DEFINITION.adapter_id == "tasks"
    assert TASKS_DEFINITION.category == "coordination"


def test_all_ten_actions_present() -> None:
    names = {a.name for a in TASKS_DEFINITION.actions}
    assert names == _EXPECTED_ACTIONS


def test_p7_schema_version_marker() -> None:
    sql = TASKS_DEFINITION.tables_sql
    assert "tasks_schema_version" in sql
    assert "task_items" in sql
    assert "task_lists" in sql


def test_idempotent_set() -> None:
    idem = {a.name for a in TASKS_DEFINITION.actions if a.idempotent}
    assert idem == {"create_task", "create_list"}


def test_read_kind_set() -> None:
    reads = {a.name for a in TASKS_DEFINITION.actions if a.kind == "read"}
    assert reads == {"list_tasks", "get_task", "list_lists"}


def test_delete_kind_set() -> None:
    deletes = {a.name for a in TASKS_DEFINITION.actions if a.kind == "delete"}
    assert deletes == {"delete_task"}


def test_sse_topics_format() -> None:
    for action in TASKS_DEFINITION.actions:
        if action.sse:
            for topic in action.sse.emits:
                parts = topic.split(".")
                assert parts[0] == "family", f"bad topic prefix: {topic}"
                assert parts[1] == "tasks", f"bad adapter in topic: {topic}"
                assert parts[-1] == "v1", f"missing version suffix: {topic}"
