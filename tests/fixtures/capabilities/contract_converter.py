"""
tests.fixtures.capabilities.contract_converter -- POC dict → K1 CapabilityContract.

Converts the 40 POC capability definition dicts (from demo_capabilities,
family_capabilities, web_capabilities) into K1 CapabilityContract objects
so they can be registered with the real K1 Fabric CapabilityRegistry.

M6 E6.1.1
"""

from __future__ import annotations

from typing import Any

from k1.fabric.types import CapabilityContract, InputSpec


def poc_dict_to_contract(cap_dict: dict[str, Any]) -> CapabilityContract:
    """Convert a single POC capability dict to a K1 CapabilityContract.

    POC dict shape::

        {
            "name": "tool.execute.hotel_search",
            "description": "Search for hotels ...",
            "required_inputs": ["location"],
            "optional_inputs": ["check_in", "check_out"],
            "has_side_effects": False,
            "estimated_cost": "free",
            "domain": "travel",
        }
    """
    name = cap_dict.get("name", "")
    description = cap_dict.get("description", "")
    domain_str = cap_dict.get("domain", "")

    required_inputs = [
        InputSpec(name=n, type="STRING", description=n.replace("_", " ").title())
        for n in cap_dict.get("required_inputs", [])
    ]
    optional_inputs = [
        InputSpec(name=n, type="STRING", description=n.replace("_", " ").title())
        for n in cap_dict.get("optional_inputs", [])
    ]

    limitations: list[str] = []
    if cap_dict.get("has_side_effects", False):
        limitations.append("has_side_effects")

    cost_str = cap_dict.get("estimated_cost", "free")
    cost_per_call = 0.0
    if cost_str not in ("free", "varies", "", None):
        try:
            cost_per_call = float(cost_str.replace("$", ""))
        except (ValueError, AttributeError):
            pass

    return CapabilityContract(
        name=name,
        version="1.0.0",
        domain=[domain_str] if domain_str else [],
        description=description,
        capabilities=["tool_execution"],
        limitations=limitations,
        required_inputs=required_inputs,
        optional_inputs=optional_inputs,
        required_context=[],
        optional_context=[],
        output={"type": "object", "properties": {"result": {"type": "object"}}},
        provider_type="BRIDGE",
        provider_id="poc-mock-bridge",
        provider_endpoint="local://poc-mock-bridge",
        safety_band_min="GREEN",
        cost_per_call=cost_per_call,
        avg_latency_ms=50,
        max_latency_ms=200,
        availability="ONLINE",
        ephemeral=True,
        session_scoped=True,
    )


def convert_all_poc_capabilities() -> list[CapabilityContract]:
    """Convert all 40 POC capabilities to K1 CapabilityContract objects."""
    from tests.fixtures.capabilities.demo_capabilities import DEMO_CAPABILITIES
    from tests.fixtures.capabilities.family_capabilities import FAMILY_CAPABILITIES
    from tests.fixtures.capabilities.web_capabilities import WEB_CAPABILITIES

    contracts: list[CapabilityContract] = []
    for cap_dict in DEMO_CAPABILITIES + FAMILY_CAPABILITIES + WEB_CAPABILITIES:
        contracts.append(poc_dict_to_contract(cap_dict))
    return contracts
