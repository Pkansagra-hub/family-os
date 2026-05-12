"""Bootstrap / capability-registration tests for the Chores adapter."""

from __future__ import annotations

from k1.tools.family.chores import CHORES_DEFINITION

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


def test_offline_bootstrap_registers_all_capabilities() -> None:
    assert len(CHORES_DEFINITION.actions) == 9
    names = {a.name for a in CHORES_DEFINITION.actions}
    assert names == _EXPECTED_ACTIONS


def test_create_template_idempotent_flag() -> None:
    a = CHORES_DEFINITION.find_action("create_template")
    assert a is not None
    assert a.idempotent is True


def test_list_chores_accessible_to_guest() -> None:
    a = CHORES_DEFINITION.find_action("list_chores")
    assert a is not None
    assert "guest" in a.allowed_roles


def test_chore_summary_accessible_to_guest() -> None:
    a = CHORES_DEFINITION.find_action("chore_summary")
    assert a is not None
    assert "guest" in a.allowed_roles


def test_action_safety_bands_present() -> None:
    for action in CHORES_DEFINITION.actions:
        assert action.min_band is not None, f"{action.name} missing min_band"


def test_complete_skip_accessible_to_child() -> None:
    for name in ("complete_chore", "skip_chore"):
        a = CHORES_DEFINITION.find_action(name)
        assert "child" in a.allowed_roles


def test_template_management_parent_only() -> None:
    for name in ("create_template", "update_template", "delete_template"):
        a = CHORES_DEFINITION.find_action(name)
        assert "child" not in a.allowed_roles
        assert "guardian" not in a.allowed_roles
        assert "parent" in a.allowed_roles
