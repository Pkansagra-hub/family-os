"""Tests for SHOPPING_DEFINITION declarative spec."""

from __future__ import annotations

from k1.fabric.manifest_translator import build_contract
from k1.tools.family.shopping.definition import SHOPPING_DEFINITION

_EXPECTED_ACTIONS = {
    "create_list",
    "delete_list",
    "list_lists",
    "add_item",
    "update_item",
    "approve_item",
    "reject_item",
    "check_off_item",
    "delete_item",
    "list_items",
    "get_item",
}


def test_definition_basics() -> None:
    assert SHOPPING_DEFINITION.adapter_id == "shopping"
    assert SHOPPING_DEFINITION.category == "coordination"
    assert SHOPPING_DEFINITION.activity_profile == "shopping.v1"
    assert set(SHOPPING_DEFINITION.domain_tags) >= {"shopping", "groceries", "clothes"}


def test_all_actions_present() -> None:
    names = {a.name for a in SHOPPING_DEFINITION.actions}
    assert names == _EXPECTED_ACTIONS


def test_p7_schema_version_marker() -> None:
    sql = SHOPPING_DEFINITION.tables_sql
    assert "shopping_schema_version" in sql
    assert "CREATE TABLE IF NOT EXISTS shopping_lists" in sql
    assert "CREATE TABLE IF NOT EXISTS shopping_items" in sql


def test_kind_sets() -> None:
    reads = {a.name for a in SHOPPING_DEFINITION.actions if a.kind == "read"}
    deletes = {a.name for a in SHOPPING_DEFINITION.actions if a.kind == "delete"}
    idempotent = {a.name for a in SHOPPING_DEFINITION.actions if a.idempotent}

    assert reads == {"list_lists", "list_items", "get_item"}
    assert deletes == {"delete_list", "delete_item"}
    assert idempotent == {"create_list", "add_item"}


def test_all_actions_are_green() -> None:
    for action in SHOPPING_DEFINITION.actions:
        assert action.min_band == "GREEN", action.name


def test_child_can_request_but_not_approve_or_check_off() -> None:
    add = SHOPPING_DEFINITION.find_action("add_item")
    assert add is not None
    assert "child" in add.allowed_roles

    for name in ("approve_item", "reject_item", "check_off_item", "delete_item"):
        action = SHOPPING_DEFINITION.find_action(name)
        assert action is not None
        assert "child" not in action.allowed_roles
        assert "parent" in action.allowed_roles


def test_all_actions_reference_activity_prompt_template() -> None:
    for action in SHOPPING_DEFINITION.actions:
        assert action.prompt_template == "shopping_activity_v1", action.name


def test_contracts_expose_profile_and_instructions() -> None:
    for action in SHOPPING_DEFINITION.actions:
        contract = build_contract(SHOPPING_DEFINITION, action)
        assert contract.activity_profile == "shopping.v1"
        assert contract.prompt_template == "shopping_activity_v1"
        assert contract.tool_instructions
        assert "shopping" in contract.domain
