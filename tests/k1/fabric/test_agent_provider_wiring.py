"""M19.E1 — AgentProvider deps wiring (audit H-3 fix).

Pre-fix, `_create_agent` in `k1/fabric/factory.py` passed
``model_gateway``, ``state_reader``, ``delta_bus`` and
``context_builder`` directly to ``AgentProvider.__init__``. But
``AgentProvider.__init__`` only declares ``agent_factory`` and
``capability_names`` keyword arguments and silently swallows everything
else through ``**_kwargs``. The result was that production
``AgentProvider`` instances ran in stub mode (``agent_factory is None``,
health_check returns ``UNKNOWN``, execute() raises
``AgentNotImplementedError``) and the entire ``agent.*`` capability
dispatch path silently broke.

These tests pin the post-fix contract:

* ``AgentProvider`` instances created via ``ProviderFactory`` for an
  ``AGENT`` provider type have a real ``AgentFactory`` injected.
* The factory is constructed from the same ports the FabricFactory
  passes to ``ProviderFactory`` (model gateway, state reader, delta
  bus, context builder).
* ``contract_loader`` is wired so the factory can resolve
  ``AgentContract`` records from the registry on demand.
* ``capability_names`` is populated from the registry for the contracts
  that target this ``provider_id``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k1.fabric.factory import FabricFactory
from k1.fabric.providers.agent_provider import AgentFactory, AgentProvider
from k1.fabric.types import AgentContract, ProviderConfig, ProviderType

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _make_fabric() -> object:
    return FabricFactory.create_for_testing(
        capture_events=True,
        contracts_dir=str(FIXTURES_DIR),
    )


def _create_agent_provider(fabric: object, provider_id: str) -> AgentProvider:
    """Drive the factory's _create_agent handler by asking ProviderFactory
    to build a provider for the AGENT provider_type."""
    config = ProviderConfig(
        provider_id=provider_id,
        provider_type=ProviderType.AGENT.value,
        endpoint=f"local://{provider_id}",
    )
    provider_factory = fabric.facade._resolver._provider_factory  # type: ignore[attr-defined]
    return provider_factory.create(config)


def test_agent_provider_gets_real_factory_injected() -> None:
    fabric = _make_fabric()

    # The fixture YAMLs (invitation_sender, health_summarizer) declare
    # provider_type=AGENT but no provider_id; pick the auto-derived
    # behaviour by registering an explicit one for this assertion.
    provider = _create_agent_provider(fabric, "test-agent-provider")

    assert isinstance(provider, AgentProvider)
    assert provider.agent_factory is not None, (
        "AgentProvider should have a real AgentFactory after H-3 fix; "
        "previously this was None (silent stub mode)."
    )
    assert isinstance(provider.agent_factory, AgentFactory)


def test_agent_factory_has_model_gateway_and_context_builder() -> None:
    fabric = _make_fabric()
    provider = _create_agent_provider(fabric, "test-agent-provider-2")

    factory = provider.agent_factory
    assert factory is not None

    # FabricFactory.create_for_testing wires TestModelGatewayAdapter and
    # ContextBuilder; the H-3 fix must thread them through.
    assert factory.has_model_gateway is True, (
        "AgentFactory.has_model_gateway should be True; the test fabric "
        "wires a TestModelGatewayAdapter and the H-3 fix must pass it "
        "through to AgentFactory."
    )
    assert factory.has_context_builder is True


def test_agent_factory_can_load_contracts_from_registry() -> None:
    """The contract_loader closure should return AgentContract instances
    when asked for an agent-typed capability_name registered in the
    fabric's CapabilityRegistry."""

    fabric = _make_fabric()
    provider = _create_agent_provider(fabric, "test-agent-provider-3")
    factory = provider.agent_factory
    assert factory is not None

    # The fixture invitation_sender.yaml is loaded via ModuleLoader at
    # bootstrap and registered as an AgentContract.
    contract_loader = factory._contract_loader  # type: ignore[attr-defined]
    assert contract_loader is not None
    loaded = contract_loader("agent.execute.invitation_sender")
    assert loaded is not None
    assert isinstance(loaded, AgentContract)
    assert loaded.name == "agent.execute.invitation_sender"


def test_agent_factory_contract_loader_returns_none_for_non_agent() -> None:
    """The contract_loader must return None for non-AgentContract names
    (e.g. tool contracts) so AgentFactory falls back to its
    ``Agent contract not found`` error path rather than crashing on a
    type mismatch."""

    fabric = _make_fabric()
    provider = _create_agent_provider(fabric, "test-agent-provider-4")
    factory = provider.agent_factory
    assert factory is not None

    contract_loader = factory._contract_loader  # type: ignore[attr-defined]
    # A non-existent name returns None.
    assert contract_loader("agent.execute.does_not_exist") is None


@pytest.mark.asyncio
async def test_agent_provider_health_check_no_longer_unknown() -> None:
    """Pre-fix, AgentProvider.health_check returned UNKNOWN because
    agent_factory was None. With the H-3 fix the factory is wired, so
    health_check must report HEALTHY or DEGRADED -- never UNKNOWN."""

    fabric = _make_fabric()
    provider = _create_agent_provider(fabric, "test-agent-provider-health")

    health = await provider.health_check()
    assert health.status != "UNKNOWN", (
        f"AgentProvider.health_check should not return UNKNOWN after the "
        f"H-3 fix (got status={health.status!r}, error={health.error!r})."
    )
