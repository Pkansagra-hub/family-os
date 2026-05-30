"""Bootstrap / offline-manifest tests for the Shopping adapter."""

from __future__ import annotations

from k1.tools.family.shopping.definition import SHOPPING_DEFINITION


def test_offline_bootstrap_registers_all_capabilities(svc) -> None:
    service, _, _ = svc
    assert service.adapter_id == "shopping"
    assert len(SHOPPING_DEFINITION.actions) == 11


def test_parent_actions_and_child_request_action() -> None:
    parent_only = {
        "create_list",
        "delete_list",
        "update_item",
        "approve_item",
        "reject_item",
        "check_off_item",
        "delete_item",
    }
    for action in SHOPPING_DEFINITION.actions:
        if action.name in parent_only:
            assert "parent" in action.allowed_roles
            assert "child" not in action.allowed_roles

    add = SHOPPING_DEFINITION.find_action("add_item")
    assert add is not None
    assert "child" in add.allowed_roles
