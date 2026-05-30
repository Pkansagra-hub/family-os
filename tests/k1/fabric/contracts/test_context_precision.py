"""M4-E1 context_precision contract coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from k1.fabric.contracts.agent_contract import AgentContractParser
from k1.fabric.contracts.context_precision import ContextPrecision
from k1.fabric.contracts.tool_contract import ToolContractParser
from k1.fabric.core.contract_validator import ContractValidator


def _tool_body() -> dict[str, object]:
    return {
        "name": "tool.execute.weather",
        "version": "1.0.0",
        "domain": ["WEATHER"],
        "description": "Get weather for a place.",
        "required_inputs": [],
        "output": {"type": "object"},
        "provider_type": "MCP",
        "provider_id": "weather",
        "safety_band_min": "GREEN",
        "availability": "ONLINE",
    }


def _agent_body() -> dict[str, object]:
    return {
        "name": "agent.execute.planner",
        "version": "1.0.0",
        "domain": ["PLANNING"],
        "description": "Plan a short task.",
        "required_inputs": [],
        "prompt_template": "planner_v1",
        "tools_granted": ["tool.execute.weather"],
        "llm_budget_tokens": 1024,
        "max_tool_calls": 3,
        "max_execution_time_ms": 30000,
        "output": {"type": "object"},
        "provider_type": "AGENT",
        "safety_band_min": "GREEN",
        "availability": "ONLINE",
    }


def test_tool_parser_preserves_context_precision() -> None:
    body = _tool_body()
    body["context_precision"] = {"temporal": "execution", "spatial": "approximate"}

    contract = ToolContractParser().parse_body(body)

    assert isinstance(contract.context_precision, ContextPrecision)
    assert contract.context_precision.temporal == "execution"
    assert contract.context_precision.spatial == "approximate"
    assert contract.to_dict()["context_precision"] == {
        "temporal": "execution",
        "spatial": "approximate",
    }


def test_agent_parser_preserves_context_precision() -> None:
    body = _agent_body()
    body["context_precision"] = {"temporal": "windows", "spatial": "semantic"}

    contract = AgentContractParser().parse_body(body)

    assert isinstance(contract.context_precision, ContextPrecision)
    assert contract.context_precision.temporal == "windows"
    assert contract.context_precision.spatial == "semantic"


def test_schema_rejects_invalid_context_precision() -> None:
    body = _tool_body()
    body["context_precision"] = {"temporal": "utc", "spatial": "raw"}

    errors = ContractValidator().validate(
        {"tool_contract": body},
        contract_type="tool_contract",
    )

    assert any("context_precision" in error for error in errors)


def test_context_precision_value_object_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        ContextPrecision.from_dict({"temporal": "anchor", "spatial": "coordinates"})


def test_grounding_invocation_schema_accepts_baseline_block() -> None:
    schema_path = Path("k1/contracts/schemas/grounding.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft7Validator.check_schema(schema)
    validator = Draft7Validator(schema)

    errors = list(
        validator.iter_errors(
            {
                "invoked_at_utc": "2026-05-24T21:20:00+00:00",
                "grounding_envelope_id": "env-1",
                "grounding_projection_id": "proj-1",
                "temporal_anchor_id": "anchor-1",
                "spatial_context_id": "spatial-1",
                "resolved_temporal_refs": [],
                "resolved_spatial_refs": [],
            }
        )
    )

    assert errors == []
