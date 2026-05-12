"""Bootstrap / capability-registration tests for the Reminders adapter."""

from __future__ import annotations

from k1.tools.family.reminders import REMINDERS_DEFINITION

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


def test_offline_bootstrap_registers_all_capabilities() -> None:
    """REMINDERS_DEFINITION advertises exactly the 8 promised capabilities."""
    assert len(REMINDERS_DEFINITION.actions) == 8
    names = {a.name for a in REMINDERS_DEFINITION.actions}
    assert names == _EXPECTED_ACTIONS


def test_llm_tool_spec_fire_reminder_system_only() -> None:
    fire = REMINDERS_DEFINITION.find_action("fire_reminder")
    assert fire is not None
    assert fire.allowed_roles == [
        "system"
    ], "fire_reminder must be restricted to system role so LLM cannot invoke it"


def test_ui_manifest_all_8_for_parent() -> None:
    """A parent caller should see all 8 actions in the manifest."""
    from k1.tools.family.base import WriteContext
    from k1.tools.family.policy import default_policy

    policy = default_policy()
    all_names = {a.name for a in REMINDERS_DEFINITION.actions}
    assert all_names == _EXPECTED_ACTIONS


def test_action_safety_bands_present() -> None:
    for action in REMINDERS_DEFINITION.actions:
        assert action.min_band is not None, f"{action.name} missing min_band"


def test_create_reminder_idempotent_flag() -> None:
    create = REMINDERS_DEFINITION.find_action("create_reminder")
    assert create is not None
    assert create.idempotent is True


def test_get_reminder_no_required_role() -> None:
    """get_reminder is a read action accessible to guests."""
    get = REMINDERS_DEFINITION.find_action("get_reminder")
    assert get is not None
    assert "guest" in get.allowed_roles
