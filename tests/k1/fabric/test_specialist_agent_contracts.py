"""M19.E2 — Specialist agent YAML contracts are auto-discovered.

These tests pin the production resolution path:

    Fabric bootstrap (production contracts_dir = k1/contracts/)
      → ModuleLoader (`_CONTRACT_SUBDIRS` includes "agents")
      → discovers k1/contracts/agents/*.yaml
      → AgentContractParser → CapabilityRegistry
      → _auto_register_providers → ProviderRegistry

After this milestone the registry must contain:
    * agent.execute.health_specialist
    * agent.execute.finance_specialist
    * agent.execute.travel_specialist

with provider_type=AGENT and a dedicated provider_id per specialist.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k1.fabric.factory import FabricFactory
from k1.fabric.types import AgentContract, ProviderType

# Use the production contracts dir explicitly so this test catches any
# drift in the YAMLs themselves.
PRODUCTION_CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "k1" / "contracts"


SPECIALIST_NAMES = (
    "agent.execute.health_specialist",
    "agent.execute.finance_specialist",
    "agent.execute.travel_specialist",
)


@pytest.fixture(scope="module")
def production_fabric() -> object:
    return FabricFactory.create_for_testing(
        capture_events=False,
        contracts_dir=str(PRODUCTION_CONTRACTS_DIR),
    )


@pytest.mark.parametrize("name", SPECIALIST_NAMES)
def test_specialist_contract_loaded(production_fabric: object, name: str) -> None:
    contract = production_fabric.lookup(name)
    assert contract is not None, (
        f"{name!r} not loaded; check that ModuleLoader scans "
        f"k1/contracts/agents/ and the YAML is well-formed."
    )
    assert isinstance(
        contract, AgentContract
    ), f"{name!r} loaded as {type(contract).__name__!r}; expected AgentContract"
    assert contract.provider_type == ProviderType.AGENT.value
    assert contract.provider_id, f"{name!r} must declare a provider_id"
    assert contract.prompt_template, f"{name!r} must declare a prompt_template"
    assert contract.llm_budget_tokens > 0


def test_specialists_have_distinct_provider_ids(production_fabric: object) -> None:
    ids = {production_fabric.lookup(n).provider_id for n in SPECIALIST_NAMES}
    assert len(ids) == len(SPECIALIST_NAMES), (
        f"Each specialist must have a distinct provider_id so they get "
        f"independent AgentProvider instances; saw {ids!r}"
    )


def test_specialist_provider_ids_registered_in_provider_registry(
    production_fabric: object,
) -> None:
    """``_auto_register_providers`` must have created a ProviderConfig
    for each specialist's provider_id."""

    provider_registry = production_fabric.facade._resolver._provider_matcher._provider_registry
    for name in SPECIALIST_NAMES:
        contract = production_fabric.lookup(name)
        assert provider_registry.contains(contract.provider_id), (
            f"provider_id {contract.provider_id!r} (for {name!r}) was not "
            f"auto-registered into the ProviderRegistry."
        )
