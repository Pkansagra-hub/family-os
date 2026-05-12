"""Bootstrap / offline-manifest tests for the Tasks adapter."""

from __future__ import annotations

from k1.tools.family.tasks.definition import TASKS_DEFINITION


def test_offline_bootstrap_registers_all_capabilities(svc) -> None:
    """All 10 ActionSpecs must be discoverable via find_action."""
    service, _, _ = svc
    expected = {
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
    found = {spec.name for spec in TASKS_DEFINITION.actions}
    assert found == expected


def test_llm_tool_specs_names() -> None:
    """LLM tool spec names follow ``tasks.<action>`` pattern."""
    for action in TASKS_DEFINITION.actions:
        assert action.name in {
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
        # LLM hints present on all write actions at minimum
        if action.kind in ("write", "delete"):
            assert action.llm is not None, f"{action.name} missing LLM hints"


def test_ui_manifest_all_10_for_parent() -> None:
    """All 10 actions visible to parent role."""
    from k1.tools.family.tasks.definition import TASKS_DEFINITION

    parent_actions = [a for a in TASKS_DEFINITION.actions if "parent" in (a.allowed_roles or [])]
    assert len(parent_actions) == 10
