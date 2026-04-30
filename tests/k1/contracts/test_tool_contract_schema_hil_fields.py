"""E2.1 -- HIL fields on contract JSON schemas.

Verifies the new optional fields `requires_human_confirmation` and
`side_effects` validate correctly across the four contract schemas, and
that the inconsistency rule (GREEN + requires_human_confirmation=false +
non-empty side_effects -> error) is enforced on the three schemas that
carry safety_band_min.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml

from k1.fabric.core.contract_validator import ContractValidator

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "k1" / "contracts" / "tools"


VALID_TOOL_BODY: Dict[str, Any] = {
    "name": "tool.write.calendar_delete_event",
    "version": "1.0.0",
    "domain": ["CALENDAR"],
    "description": "Delete a calendar event by id",
    "required_inputs": [
        {"name": "event_id", "type": "STRING", "description": "Event id"},
    ],
    "output": {"type": "object", "properties": {"status": {"type": "string"}}},
    "provider_type": "MCP",
    "provider_id": "calendar_mcp_stdio",
    "safety_band_min": "AMBER",
    "availability": "ONLINE",
}


@pytest.fixture
def validator() -> ContractValidator:
    return ContractValidator()


def _wrap(body: Dict[str, Any]) -> Dict[str, Any]:
    return {"tool_contract": body}


# ---------------------------------------------------------------------------
# Backwards-compat: every existing tool YAML still validates
# ---------------------------------------------------------------------------


class TestExistingContractsStillValidate:
    def test_existing_tool_contracts_still_validate(self, validator: ContractValidator) -> None:
        yaml_files: List[Path] = sorted(CONTRACTS_DIR.glob("*.yaml"))
        assert yaml_files, "expected k1/contracts/tools/*.yaml fixtures"
        for path in yaml_files:
            with path.open(encoding="utf-8") as fh:
                doc = yaml.safe_load(fh)
            errors = validator.validate(doc, "tool_contract")
            assert errors == [], f"{path.name} now fails validation: {errors}"


# ---------------------------------------------------------------------------
# requires_human_confirmation field
# ---------------------------------------------------------------------------


class TestRequiresHumanConfirmation:
    def test_requires_human_confirmation_true_validates(self, validator: ContractValidator) -> None:
        body = copy.deepcopy(VALID_TOOL_BODY)
        body["requires_human_confirmation"] = True
        assert validator.validate(_wrap(body), "tool_contract") == []

    def test_requires_human_confirmation_false_validates(
        self, validator: ContractValidator
    ) -> None:
        body = copy.deepcopy(VALID_TOOL_BODY)
        body["requires_human_confirmation"] = False
        assert validator.validate(_wrap(body), "tool_contract") == []

    def test_requires_human_confirmation_null_validates(self, validator: ContractValidator) -> None:
        body = copy.deepcopy(VALID_TOOL_BODY)
        body["requires_human_confirmation"] = None
        assert validator.validate(_wrap(body), "tool_contract") == []

    def test_requires_human_confirmation_string_rejected(
        self, validator: ContractValidator
    ) -> None:
        body = copy.deepcopy(VALID_TOOL_BODY)
        body["requires_human_confirmation"] = "yes"
        errors = validator.validate(_wrap(body), "tool_contract")
        assert errors, "expected schema error for non-boolean override"


# ---------------------------------------------------------------------------
# side_effects array
# ---------------------------------------------------------------------------


class TestSideEffects:
    def test_side_effects_array_validates(self, validator: ContractValidator) -> None:
        body = copy.deepcopy(VALID_TOOL_BODY)
        body["side_effects"] = [
            {"kind": "data_delete", "target": "calendar.event", "reversible": False},
        ]
        assert validator.validate(_wrap(body), "tool_contract") == []

    def test_side_effects_kind_enum_enforced(self, validator: ContractValidator) -> None:
        body = copy.deepcopy(VALID_TOOL_BODY)
        body["side_effects"] = [{"kind": "bogus", "target": "x"}]
        errors = validator.validate(_wrap(body), "tool_contract")
        assert errors, "expected schema error for unknown kind"

    def test_side_effects_requires_kind_and_target(self, validator: ContractValidator) -> None:
        body = copy.deepcopy(VALID_TOOL_BODY)
        body["side_effects"] = [{"kind": "data_write"}]  # missing target
        errors = validator.validate(_wrap(body), "tool_contract")
        assert errors, "expected schema error for missing target"

    def test_cost_estimate_optional(self, validator: ContractValidator) -> None:
        body = copy.deepcopy(VALID_TOOL_BODY)
        body["side_effects"] = [{"kind": "data_write", "target": "notes.note"}]
        assert validator.validate(_wrap(body), "tool_contract") == []

    def test_payment_side_effect_with_cost(self, validator: ContractValidator) -> None:
        body = copy.deepcopy(VALID_TOOL_BODY)
        body["side_effects"] = [
            {
                "kind": "payment",
                "target": "payment.card.ending_4242",
                "reversible": False,
                "cost_estimate": {"currency": "USD", "amount": 12.5},
                "description": "Order checkout",
            },
        ]
        assert validator.validate(_wrap(body), "tool_contract") == []


# ---------------------------------------------------------------------------
# Inconsistency rule: GREEN + false + side_effects -> reject
# ---------------------------------------------------------------------------


class TestGreenFalseWithSideEffectsRejected:
    def test_inconsistent_combo_rejected_on_tool(self, validator: ContractValidator) -> None:
        body = copy.deepcopy(VALID_TOOL_BODY)
        body["safety_band_min"] = "GREEN"
        body["requires_human_confirmation"] = False
        body["side_effects"] = [{"kind": "data_write", "target": "calendar.event"}]
        errors = validator.validate(_wrap(body), "tool_contract")
        assert errors, "GREEN + false + side_effects must fail"

    def test_amber_false_with_side_effects_allowed(self, validator: ContractValidator) -> None:
        body = copy.deepcopy(VALID_TOOL_BODY)
        body["safety_band_min"] = "AMBER"
        body["requires_human_confirmation"] = False
        body["side_effects"] = [{"kind": "data_write", "target": "calendar.event"}]
        assert validator.validate(_wrap(body), "tool_contract") == []

    def test_green_true_with_side_effects_allowed(self, validator: ContractValidator) -> None:
        body = copy.deepcopy(VALID_TOOL_BODY)
        body["safety_band_min"] = "GREEN"
        body["requires_human_confirmation"] = True
        body["side_effects"] = [{"kind": "data_write", "target": "calendar.event"}]
        assert validator.validate(_wrap(body), "tool_contract") == []

    def test_green_no_override_no_side_effects_allowed(self, validator: ContractValidator) -> None:
        body = copy.deepcopy(VALID_TOOL_BODY)
        body["safety_band_min"] = "GREEN"
        # default behaviour
        assert validator.validate(_wrap(body), "tool_contract") == []
