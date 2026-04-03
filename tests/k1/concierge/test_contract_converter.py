"""
E6.7.1 — Unit tests for contract_converter.py.

Validates POC capability dict → K1 CapabilityContract conversion.
"""

from __future__ import annotations

from k1.concierge.fabric.contract_converter import (
    convert_all_poc_capabilities,
    poc_dict_to_contract,
)
from k1.fabric.types import CapabilityContract, InputSpec

# =====================================================================
# poc_dict_to_contract — field mapping
# =====================================================================


class TestPocDictToContract:
    """Verify individual field mappings."""

    SAMPLE: dict = {
        "name": "tool.execute.hotel_search",
        "description": "Search for hotels by location",
        "required_inputs": ["location"],
        "optional_inputs": ["check_in", "check_out"],
        "has_side_effects": False,
        "estimated_cost": "free",
        "domain": "travel",
    }

    def test_returns_capability_contract(self) -> None:
        contract = poc_dict_to_contract(self.SAMPLE)
        assert isinstance(contract, CapabilityContract)

    def test_name_maps_directly(self) -> None:
        contract = poc_dict_to_contract(self.SAMPLE)
        assert contract.name == "tool.execute.hotel_search"

    def test_description_maps_directly(self) -> None:
        contract = poc_dict_to_contract(self.SAMPLE)
        assert contract.description == "Search for hotels by location"

    def test_domain_is_list(self) -> None:
        contract = poc_dict_to_contract(self.SAMPLE)
        assert isinstance(contract.domain, list)
        assert contract.domain == ["travel"]

    def test_version_defaults_to_1_0_0(self) -> None:
        contract = poc_dict_to_contract(self.SAMPLE)
        assert contract.version == "1.0.0"

    def test_required_inputs_are_input_spec(self) -> None:
        contract = poc_dict_to_contract(self.SAMPLE)
        assert len(contract.required_inputs) == 1
        assert isinstance(contract.required_inputs[0], InputSpec)
        assert contract.required_inputs[0].name == "location"
        assert contract.required_inputs[0].type == "STRING"

    def test_optional_inputs_are_input_spec(self) -> None:
        contract = poc_dict_to_contract(self.SAMPLE)
        assert len(contract.optional_inputs) == 2
        assert contract.optional_inputs[0].name == "check_in"
        assert contract.optional_inputs[1].name == "check_out"

    def test_provider_type_is_bridge(self) -> None:
        contract = poc_dict_to_contract(self.SAMPLE)
        assert contract.provider_type == "BRIDGE"

    def test_provider_id_is_poc_mock_bridge(self) -> None:
        contract = poc_dict_to_contract(self.SAMPLE)
        assert contract.provider_id == "poc-mock-bridge"

    def test_provider_endpoint(self) -> None:
        contract = poc_dict_to_contract(self.SAMPLE)
        assert contract.provider_endpoint == "local://poc-mock-bridge"

    def test_no_side_effects_empty_limitations(self) -> None:
        contract = poc_dict_to_contract(self.SAMPLE)
        assert contract.limitations == []

    def test_side_effects_in_limitations(self) -> None:
        cap = {**self.SAMPLE, "has_side_effects": True}
        contract = poc_dict_to_contract(cap)
        assert "has_side_effects" in contract.limitations

    def test_free_cost_is_zero(self) -> None:
        contract = poc_dict_to_contract(self.SAMPLE)
        assert contract.cost_per_call == 0.0

    def test_dollar_cost_parsed(self) -> None:
        cap = {**self.SAMPLE, "estimated_cost": "$1.50"}
        contract = poc_dict_to_contract(cap)
        assert contract.cost_per_call == 1.50

    def test_varies_cost_is_zero(self) -> None:
        cap = {**self.SAMPLE, "estimated_cost": "varies"}
        contract = poc_dict_to_contract(cap)
        assert contract.cost_per_call == 0.0

    def test_safety_band_min_green(self) -> None:
        contract = poc_dict_to_contract(self.SAMPLE)
        assert contract.safety_band_min == "GREEN"

    def test_availability_online(self) -> None:
        contract = poc_dict_to_contract(self.SAMPLE)
        assert contract.availability == "ONLINE"

    def test_ephemeral_true(self) -> None:
        contract = poc_dict_to_contract(self.SAMPLE)
        assert contract.ephemeral is True

    def test_session_scoped_true(self) -> None:
        contract = poc_dict_to_contract(self.SAMPLE)
        assert contract.session_scoped is True

    def test_capabilities_list(self) -> None:
        contract = poc_dict_to_contract(self.SAMPLE)
        assert contract.capabilities == ["tool_execution"]

    def test_empty_domain_produces_empty_list(self) -> None:
        cap = {**self.SAMPLE, "domain": ""}
        contract = poc_dict_to_contract(cap)
        assert contract.domain == []


# =====================================================================
# convert_all_poc_capabilities — aggregate conversion
# =====================================================================


class TestConvertAllPocCapabilities:
    """Verify bulk conversion of all 40 POC capabilities."""

    def test_returns_list(self) -> None:
        contracts = convert_all_poc_capabilities()
        assert isinstance(contracts, list)

    def test_returns_40_contracts(self) -> None:
        contracts = convert_all_poc_capabilities()
        assert len(contracts) == 40

    def test_all_are_capability_contracts(self) -> None:
        contracts = convert_all_poc_capabilities()
        for c in contracts:
            assert isinstance(c, CapabilityContract)

    def test_all_have_bridge_provider_type(self) -> None:
        contracts = convert_all_poc_capabilities()
        for c in contracts:
            assert c.provider_type == "BRIDGE"

    def test_all_have_poc_mock_bridge_provider_id(self) -> None:
        contracts = convert_all_poc_capabilities()
        for c in contracts:
            assert c.provider_id == "poc-mock-bridge"

    def test_all_names_are_unique(self) -> None:
        contracts = convert_all_poc_capabilities()
        names = [c.name for c in contracts]
        assert len(names) == len(set(names))

    def test_all_names_start_with_tool_execute(self) -> None:
        contracts = convert_all_poc_capabilities()
        for c in contracts:
            assert c.name.startswith("tool.execute.")

    def test_all_domains_are_lists(self) -> None:
        contracts = convert_all_poc_capabilities()
        for c in contracts:
            assert isinstance(c.domain, list)

    def test_all_required_inputs_are_input_spec(self) -> None:
        contracts = convert_all_poc_capabilities()
        for c in contracts:
            for inp in c.required_inputs:
                assert isinstance(inp, InputSpec)
