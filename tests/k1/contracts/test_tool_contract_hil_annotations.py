"""E2.4 -- HIL annotations on sensitive tool contracts.

Loads the annotated YAML contracts and asserts the expected
`requires_human_confirmation` + `side_effects` content. Read-only
contracts (weather, search, list, discover) must keep the default
None / [] (i.e. no explicit override).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from k1.fabric.contracts.tool_contract import ToolContractParser

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "k1" / "contracts" / "tools"


def _load_body(name: str) -> Dict[str, Any]:
    with (CONTRACTS_DIR / name).open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    return doc["tool_contract"]


# ---------------------------------------------------------------------------
# Sensitive contracts: must explicitly require HIL
# ---------------------------------------------------------------------------


class TestSensitiveContractsRequireHIL:
    def test_calendar_delete_requires_confirmation(self) -> None:
        c = ToolContractParser._build_contract(_load_body("calendar_delete_event.yaml"))
        assert c.requires_human_confirmation is True
        kinds = {se["kind"] for se in c.side_effects}
        assert "data_delete" in kinds
        assert any(se["target"] == "calendar.event" for se in c.side_effects)

    def test_calendar_create_requires_confirmation(self) -> None:
        c = ToolContractParser._build_contract(_load_body("calendar_create_event.yaml"))
        assert c.requires_human_confirmation is True
        assert any(se["kind"] == "data_write" for se in c.side_effects)

    def test_recipe_meal_plan_requires_confirmation(self) -> None:
        c = ToolContractParser._build_contract(_load_body("recipe_meal_plan.yaml"))
        assert c.requires_human_confirmation is True
        assert c.side_effects, "expected at least one declared side effect"

    def test_build_agent_requires_confirmation(self) -> None:
        c = ToolContractParser._build_contract(_load_body("build_agent.yaml"))
        assert c.requires_human_confirmation is True
        assert any(se["target"].startswith("capability_registry") for se in c.side_effects)


# ---------------------------------------------------------------------------
# Read-only / low-stakes contracts: no explicit override
# ---------------------------------------------------------------------------


READ_ONLY_CONTRACTS = [
    "weather_current.yaml",
    "weather_forecast.yaml",
    "recipe_search.yaml",
    "notes_search.yaml",
    "notes_list.yaml",
    "calendar_list_events.yaml",
    "discover_capabilities.yaml",
    "find_prompts.yaml",
    "date_calc.yaml",
    "unit_convert.yaml",
]


@pytest.mark.parametrize("yaml_name", READ_ONLY_CONTRACTS)
def test_read_only_contracts_no_explicit_hil(yaml_name: str) -> None:
    c = ToolContractParser._build_contract(_load_body(yaml_name))
    assert c.requires_human_confirmation is None, (
        f"{yaml_name} should leave requires_human_confirmation unset (None) "
        "so HIL is inferred from safety_band_min."
    )
    assert c.side_effects == [], f"{yaml_name} should declare no side effects"


# ---------------------------------------------------------------------------
# notes_create: AMBER, default policy (still inferable, no override yet)
# ---------------------------------------------------------------------------


def test_notes_create_uses_default_policy() -> None:
    """notes_create is AMBER but intentionally NOT explicitly annotated --
    we let SafetyBandPolicy infer ASK from the band. This documents the
    decision so a future audit doesn't accidentally add an override."""
    c = ToolContractParser._build_contract(_load_body("notes_create.yaml"))
    assert c.safety_band_min == "AMBER"
    assert c.requires_human_confirmation is None
    assert c.side_effects == []
