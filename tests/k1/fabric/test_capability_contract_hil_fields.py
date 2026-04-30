"""E2.2 -- HIL fields on CapabilityContract / AgentContract dataclasses.

Verifies the two new optional fields are present with safe defaults,
round-trip via to_dict/from_dict, and are populated from YAML by the
tool-contract loader (`_build_contract`).
"""

from __future__ import annotations

from typing import Any, Dict

from k1.fabric.contracts.tool_contract import ToolContractParser
from k1.fabric.types import AgentContract, CapabilityContract

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_default_requires_human_confirmation_is_none(self) -> None:
        c = CapabilityContract()
        assert c.requires_human_confirmation is None

    def test_default_side_effects_empty_list(self) -> None:
        c = CapabilityContract()
        assert c.side_effects == []

    def test_agent_contract_inherits_hil_fields(self) -> None:
        a = AgentContract()
        assert a.requires_human_confirmation is None
        assert a.side_effects == []


# ---------------------------------------------------------------------------
# Round-trip via to_dict/from_dict
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_to_dict_round_trip_with_explicit_true(self) -> None:
        c = CapabilityContract(name="tool.write.x", requires_human_confirmation=True)
        c2 = CapabilityContract.from_dict(c.to_dict())
        assert c2.requires_human_confirmation is True

    def test_to_dict_round_trip_with_explicit_false(self) -> None:
        c = CapabilityContract(name="tool.write.x", requires_human_confirmation=False)
        c2 = CapabilityContract.from_dict(c.to_dict())
        assert c2.requires_human_confirmation is False

    def test_to_dict_round_trip_with_none_explicit(self) -> None:
        c = CapabilityContract(name="tool.write.x")
        d = c.to_dict()
        assert "requires_human_confirmation" in d
        assert d["requires_human_confirmation"] is None
        c2 = CapabilityContract.from_dict(d)
        assert c2.requires_human_confirmation is None

    def test_to_dict_round_trip_with_side_effects(self) -> None:
        side = [
            {"kind": "data_delete", "target": "calendar.event", "reversible": False},
            {"kind": "notification_send", "target": "user", "reversible": True},
        ]
        c = CapabilityContract(name="tool.write.x", side_effects=side)
        c2 = CapabilityContract.from_dict(c.to_dict())
        assert c2.side_effects == side
        # Defensive copy: mutating round-tripped list does not mutate original
        assert c2.side_effects is not c.side_effects

    def test_agent_contract_round_trip_preserves_hil_fields(self) -> None:
        a = AgentContract(
            name="agent.execute.invitation_drafter",
            requires_human_confirmation=True,
            side_effects=[{"kind": "notification_send", "target": "user"}],
        )
        a2 = AgentContract.from_dict(a.to_dict())
        assert a2.requires_human_confirmation is True
        assert a2.side_effects == [{"kind": "notification_send", "target": "user"}]


# ---------------------------------------------------------------------------
# YAML loader populates new fields
# ---------------------------------------------------------------------------


def _yaml_body(extra: Dict[str, Any]) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "name": "tool.write.calendar_delete_event",
        "version": "1.0.0",
        "domain": ["CALENDAR"],
        "description": "Delete an event",
        "required_inputs": [
            {"name": "event_id", "type": "STRING", "description": "Event id"},
        ],
        "output": {"type": "object", "properties": {"status": {"type": "string"}}},
        "provider_type": "MCP",
        "provider_id": "calendar_mcp_stdio",
        "safety_band_min": "AMBER",
        "availability": "ONLINE",
    }
    body.update(extra)
    return body


class TestLoaderPopulatesHILFields:
    def test_legacy_body_yields_defaults(self) -> None:
        contract = ToolContractParser._build_contract(_yaml_body({}))
        assert contract.requires_human_confirmation is None
        assert contract.side_effects == []

    def test_body_with_requires_human_confirmation_true(self) -> None:
        contract = ToolContractParser._build_contract(
            _yaml_body({"requires_human_confirmation": True})
        )
        assert contract.requires_human_confirmation is True

    def test_body_with_requires_human_confirmation_false(self) -> None:
        contract = ToolContractParser._build_contract(
            _yaml_body({"requires_human_confirmation": False})
        )
        assert contract.requires_human_confirmation is False

    def test_body_with_side_effects_loaded(self) -> None:
        side = [{"kind": "data_delete", "target": "calendar.event", "reversible": False}]
        contract = ToolContractParser._build_contract(_yaml_body({"side_effects": side}))
        assert contract.side_effects == side


# ---------------------------------------------------------------------------
# CapabilityContractView adapter sees the new fields
# ---------------------------------------------------------------------------


class TestViewSeesHILFields:
    def test_view_from_real_capability_contract(self) -> None:
        from k1.hil.types import view_from_capability_contract

        c = CapabilityContract(
            name="tool.write.x",
            safety_band_min="AMBER",
            requires_human_confirmation=True,
            side_effects=[{"kind": "data_write", "target": "x"}],
            description="hello",
        )
        view = view_from_capability_contract(c)
        assert view.name == "tool.write.x"
        assert view.safety_band_min == "AMBER"
        assert view.requires_human_confirmation is True
        assert view.side_effects == [{"kind": "data_write", "target": "x"}]
        assert view.description == "hello"

    def test_view_from_legacy_capability_contract(self) -> None:
        from k1.hil.types import view_from_capability_contract

        c = CapabilityContract(name="tool.read.x", safety_band_min="GREEN")
        view = view_from_capability_contract(c)
        assert view.requires_human_confirmation is None
        assert view.side_effects == []
