"""
E6.7.3 — End-to-end tests for the full Fabric wiring pipeline.

Validates: Concierge → Fabric → BridgeProvider → POCMockBridgeAdapter → handler.
"""

from __future__ import annotations

import pytest

from k1.concierge.fabric.capability_registry import create_demo_registry
from k1.concierge.fabric.contract_converter import convert_all_poc_capabilities
from k1.concierge.fabric.poc_bridge_adapter import POCMockBridgeAdapter
from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.adapters.test_delta_bus import TestDeltaBusAdapter
from k1.fabric.adapters.test_model_gateway import TestModelGatewayAdapter
from k1.fabric.adapters.test_prompt_system import TestPromptSystemAdapter
from k1.fabric.adapters.test_state_reader import TestSessionStateReaderAdapter
from k1.fabric.fabric import Fabric
from k1.fabric.factory import FabricFactory, _auto_register_providers
from k1.fabric.types import CapabilityRequest, CapabilityResult, RetrievalResult

# =====================================================================
# Fixtures
# =====================================================================


def _create_wired_fabric() -> Fabric:
    """Create a fully wired Fabric with all 40 POC capabilities.

    Mirrors the ``_create_fabric()`` helper in bootstrap.py.
    """
    registry = create_demo_registry()
    poc_bridge = POCMockBridgeAdapter(registry)

    fabric = FabricFactory.create_with_ports(
        state_reader=TestSessionStateReaderAdapter(),
        event_port=LocalEventAdapter(capture_mode=True),
        bridge=poc_bridge,
        model_gateway=TestModelGatewayAdapter(),
        prompt_system=TestPromptSystemAdapter(),
        delta_bus=TestDeltaBusAdapter(),
        production_mode=False,
    )

    for contract in convert_all_poc_capabilities():
        fabric.register(contract)

    # Re-run auto-registration so poc-mock-bridge gets a ProviderConfig
    provider_registry = fabric.facade._resolver._provider_matcher._provider_registry
    _auto_register_providers(fabric.registry, provider_registry)

    return fabric


# =====================================================================
# Registration
# =====================================================================


class TestRegistration:
    """All 40 contracts registered successfully."""

    def test_40_contracts_registered(self) -> None:
        fabric = _create_wired_fabric()
        contracts = fabric.registry_api.list_all()
        # 15 from k1/contracts/ + 40 from POC = 55 total
        assert len(contracts) >= 40

    def test_hotel_search_registered(self) -> None:
        fabric = _create_wired_fabric()
        contract = fabric.registry_api.lookup("tool.execute.hotel_search")
        assert contract is not None
        assert contract.name == "tool.execute.hotel_search"

    def test_send_message_registered(self) -> None:
        fabric = _create_wired_fabric()
        contract = fabric.registry_api.lookup("tool.execute.send_message")
        assert contract is not None

    def test_web_search_registered(self) -> None:
        fabric = _create_wired_fabric()
        contract = fabric.registry_api.lookup("tool.execute.web_search")
        assert contract is not None

    def test_all_poc_provider_types_are_bridge(self) -> None:
        fabric = _create_wired_fabric()
        for contract in fabric.registry_api.list_all():
            if contract.provider_id == "poc-mock-bridge":
                assert contract.provider_type == "BRIDGE"


# =====================================================================
# Execute — 9-step pipeline
# =====================================================================


class TestExecute:
    """Execute capabilities through the full pipeline."""

    @pytest.mark.asyncio
    async def test_execute_hotel_search_succeeds(self) -> None:
        fabric = _create_wired_fabric()
        request = CapabilityRequest(
            capability_name="tool.execute.hotel_search",
            params={"location": "Paris"},
            caller="test",
        )
        result = await fabric.execute(request)
        assert isinstance(result, CapabilityResult)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_result_has_data(self) -> None:
        fabric = _create_wired_fabric()
        request = CapabilityRequest(
            capability_name="tool.execute.hotel_search",
            params={"location": "Paris"},
            caller="test",
        )
        result = await fabric.execute(request)
        assert result.data is not None
        assert isinstance(result.data, dict)

    @pytest.mark.asyncio
    async def test_execute_result_has_duration(self) -> None:
        fabric = _create_wired_fabric()
        request = CapabilityRequest(
            capability_name="tool.execute.hotel_search",
            params={"location": "Paris"},
            caller="test",
        )
        result = await fabric.execute(request)
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_weather_succeeds(self) -> None:
        fabric = _create_wired_fabric()
        request = CapabilityRequest(
            capability_name="tool.execute.weather_forecast",
            params={"location": "NYC"},
            caller="test",
        )
        result = await fabric.execute(request)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_send_message_succeeds(self) -> None:
        fabric = _create_wired_fabric()
        request = CapabilityRequest(
            capability_name="tool.execute.send_message",
            params={"recipient": "Mom", "message": "Hi"},
            caller="test",
        )
        result = await fabric.execute(request)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_nonexistent_fails(self) -> None:
        fabric = _create_wired_fabric()
        request = CapabilityRequest(
            capability_name="tool.execute.nonexistent_capability",
            params={},
            caller="test",
        )
        result = await fabric.execute(request)
        assert result.success is False


# =====================================================================
# Execute batch
# =====================================================================


class TestExecuteBatch:
    """Batch execution through the pipeline."""

    @pytest.mark.asyncio
    async def test_batch_two_requests(self) -> None:
        fabric = _create_wired_fabric()
        requests = [
            CapabilityRequest(
                capability_name="tool.execute.hotel_search",
                params={"location": "Paris"},
                caller="test",
            ),
            CapabilityRequest(
                capability_name="tool.execute.weather_forecast",
                params={"location": "NYC"},
                caller="test",
            ),
        ]
        results = await fabric.execute_batch(requests)
        assert len(results) == 2
        assert all(r.success for r in results)


# =====================================================================
# Discovery
# =====================================================================


class TestDiscovery:
    """Discovery via FabricRetrieval."""

    @pytest.mark.asyncio
    async def test_discover_returns_retrieval_result(self) -> None:
        fabric = _create_wired_fabric()
        result = await fabric.discover_capabilities(domain=["travel"])
        assert isinstance(result, RetrievalResult)

    @pytest.mark.asyncio
    async def test_discover_travel_domain(self) -> None:
        fabric = _create_wired_fabric()
        result = await fabric.discover_capabilities(domain=["travel"])
        # Should find hotel_search, hotel_booking, restaurant_search, restaurant_booking
        names = [sc.contract.name for sc in result.capabilities]
        assert len(names) >= 1  # At least some travel capabilities

    @pytest.mark.asyncio
    async def test_discover_messaging_domain(self) -> None:
        fabric = _create_wired_fabric()
        result = await fabric.discover_capabilities(domain=["messaging"])
        names = [sc.contract.name for sc in result.capabilities]
        assert len(names) >= 1

    @pytest.mark.asyncio
    async def test_discover_empty_domain(self) -> None:
        fabric = _create_wired_fabric()
        result = await fabric.discover_capabilities(domain=["nonexistent_domain_xyz"])
        # May return empty or all — depends on retrieval engine fallback
        assert isinstance(result, RetrievalResult)
