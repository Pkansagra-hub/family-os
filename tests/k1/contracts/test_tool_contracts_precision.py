"""M4-E2 tool contract grounding precision declarations."""

from __future__ import annotations

from pathlib import Path

import pytest

from k1.fabric.contracts import parse_contract
from k1.fabric.core.contract_validator import ContractValidator

CONTRACTS_DIR = Path("k1/contracts/tools")

EXPECTED_PRECISION = {
    "build_agent.yaml": ("execution", "semantic"),
    "date_calc.yaml": ("anchor", "hidden"),
    "discover_capabilities.yaml": ("anchor", "hidden"),
    "find_prompts.yaml": ("anchor", "hidden"),
    "unit_convert.yaml": ("anchor", "hidden"),
}


@pytest.mark.parametrize("filename,expected", EXPECTED_PRECISION.items())
def test_tool_contract_declares_context_precision(
    filename: str,
    expected: tuple[str, str],
) -> None:
    contract = parse_contract(CONTRACTS_DIR / filename, validator=ContractValidator())

    assert contract.context_precision is not None
    assert contract.context_precision.temporal == expected[0]
    assert contract.context_precision.spatial == expected[1]


def test_all_tool_contracts_are_covered_by_precision_inventory() -> None:
    actual = {path.name for path in CONTRACTS_DIR.glob("*.yaml")}
    assert actual == set(EXPECTED_PRECISION)


def test_build_agent_contract_declares_agent_lease_policy() -> None:
    contract = parse_contract(CONTRACTS_DIR / "build_agent.yaml", validator=ContractValidator())

    assert contract.required_context == [
        "temporal",
        "spatial",
        "beliefs_active",
        "interaction_history",
        "task_context",
    ]
    assert contract.optional_context == ["active_plans", "pending_clarifications"]
    assert contract.lease == {"ttl_seconds": 900, "allow_refresh": True}
