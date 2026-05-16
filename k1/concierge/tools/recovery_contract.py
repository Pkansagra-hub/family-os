"""Structured recovery contracts for Concierge tool execution.

The ReAct loop consumes this module as kernel control data. Tool failures that
need a human are represented as explicit contracts, not inferred from model
text or error strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

ASK_HUMAN_ACTION = "ask_human"
CLARIFICATION_HIL_TYPE = "clarification"
RECOVERY_SCHEMA_VERSION = "k1.concierge.tool_recovery.v1"


@dataclass(frozen=True)
class CapabilityParamContract:
    """Minimal input contract needed by Concierge before capability dispatch."""

    capability_name: str
    required_fields: tuple[str, ...]
    field_questions: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_contract(cls, contract: Any) -> "CapabilityParamContract":
        capability_name = str(getattr(contract, "name", "") or "")
        required_inputs = getattr(contract, "required_inputs", ()) or ()
        required_fields: list[str] = []
        field_questions: dict[str, str] = {}
        for field in required_inputs:
            name = str(getattr(field, "name", "") or "")
            if not name:
                continue
            required_fields.append(name)
            description = str(getattr(field, "description", "") or "").strip()
            label = description.rstrip(".") if description else name.replace("_", " ")
            field_questions[name] = f"I need {label} to keep going. What should I use?"
        return cls(
            capability_name=capability_name,
            required_fields=tuple(required_fields),
            field_questions=field_questions,
        )

    def missing_fields(self, params: Mapping[str, Any]) -> tuple[str, ...]:
        return tuple(
            field for field in self.required_fields if _is_missing_param(params.get(field, None))
        )

    def question_for(self, missing_fields: tuple[str, ...]) -> str:
        if not missing_fields:
            return "I need one more detail before I can keep going. What should I use?"
        first = missing_fields[0]
        configured = self.field_questions.get(first)
        if configured:
            return configured
        label = first.replace("_", " ")
        return f"What should I use for {label}?"


@dataclass(frozen=True)
class ToolRecoveryContract:
    """Machine-readable control contract emitted by tools for kernel recovery."""

    action: str
    hil_type: str
    question: str
    capability_name: str
    missing_fields: tuple[str, ...] = ()
    retry_tool: str = ""
    retry_args: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = RECOVERY_SCHEMA_VERSION
    field_contracts: Sequence[Mapping[str, Any]] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "action": self.action,
            "hil_type": self.hil_type,
            "question": self.question,
            "capability_name": self.capability_name,
            "missing_fields": list(self.missing_fields),
            "field_contracts": [dict(item) for item in self.field_contracts],
            "retry_tool": self.retry_tool,
            "retry_args": dict(self.retry_args),
        }


def _input_spec_to_dict(field: Any) -> dict[str, Any]:
    to_dict = getattr(field, "to_dict", None)
    if callable(to_dict):
        return dict(to_dict())
    return {
        "name": str(getattr(field, "name", "") or ""),
        "type": str(getattr(field, "type", "") or ""),
        "description": str(getattr(field, "description", "") or ""),
    }


def _is_missing_param(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return not value
    return False


def recovery_for_unsatisfied_contract(
    *,
    contract: Any,
    params: Mapping[str, Any],
    retry_tool: str,
    retry_args: Mapping[str, Any],
) -> ToolRecoveryContract | None:
    """Return an ask-human recovery contract when capability params are incomplete."""

    param_contract = CapabilityParamContract.from_contract(contract)
    if not param_contract.capability_name or not param_contract.required_fields:
        return None
    missing = param_contract.missing_fields(params)
    if not missing:
        return None
    missing_set = set(missing)
    return ToolRecoveryContract(
        action=ASK_HUMAN_ACTION,
        hil_type=CLARIFICATION_HIL_TYPE,
        question=param_contract.question_for(missing),
        capability_name=param_contract.capability_name,
        missing_fields=missing,
        field_contracts=[
            _input_spec_to_dict(field)
            for field in (getattr(contract, "required_inputs", ()) or ())
            if str(getattr(field, "name", "") or "") in missing_set
        ],
        retry_tool=retry_tool,
        retry_args=retry_args,
    )


def ask_human_recovery_from_tool_data(data: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Extract an ask-human recovery contract from ToolResult.data."""

    if not isinstance(data, Mapping):
        return None
    recovery = data.get("recovery")
    if not isinstance(recovery, Mapping):
        return None
    if recovery.get("schema_version") != RECOVERY_SCHEMA_VERSION:
        return None
    if recovery.get("action") != ASK_HUMAN_ACTION:
        return None
    return dict(recovery)
