"""
Contract Validator -- Validates capability contracts against structural rules.

This is the GATE that every contract must pass before entering the
CapabilityRegistry. It enforces the 12 validation rules from
fabric_discussion.md Section 6 and the 4 JSON Schema files from Epic 1.2.

Design decisions:
  - FAB-12: All contracts validated against schema before registration
  - FAB-11: Capability names follow type conventions
  - Two-phase validation: (1) JSON Schema structural, (2) semantic rules

References:
  - fabric_discussion.md Section 6 (Contract system, 12 validation rules)
  - tool_contract.schema.json, agent_contract.schema.json,
    prompt_contract.schema.json, workflow_contract.schema.json
  - Epic 2.1.1 in fabric-implementation-plan.md

Consumed by:
  - CapabilityRegistry.register() (2.2.2)
  - ModuleLoader.scan_directory() (2.3.1)
  - All 4 contract parsers (2.1.2 - 2.1.5)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from jsonschema import Draft7Validator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema cache -- loaded once per process, keyed by contract type
# ---------------------------------------------------------------------------

_SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "contracts" / "schemas"

_CONTRACT_TYPE_TO_SCHEMA_FILE = {
    "tool_contract": "tool_contract.schema.json",
    "agent_contract": "agent_contract.schema.json",
    "prompt_contract": "prompt_contract.schema.json",
    "workflow_contract": "workflow_contract.schema.json",
}

_CONTRACT_TYPE_TO_ROOT_KEY = {
    "tool_contract": "tool_contract",
    "agent_contract": "agent_contract",
    "prompt_contract": "prompt_contract",
    "workflow_contract": "workflow_contract",
}

# Name patterns per contract type (FAB-11)
# Tool names allow 3+ segments to support:
#   Native:  tool.execute.send_message          (3 segments)
#   IFL:     tool.execute.home.hue.set_brightness (5 segments)
#   MCP:     tool.execute.mcp.get_weather         (4 segments)
_NAME_PATTERNS = {
    "tool_contract": re.compile(r"^tool\.(execute|read|write|delete)(\.[a-z][a-z0-9_]+)+$"),
    "agent_contract": re.compile(r"^agent\.(execute|spawn)\.[a-z][a-z0-9_]+$"),
    "prompt_contract": re.compile(r"^[a-z][a-z0-9_]+(_v[0-9]+)?$"),
    "workflow_contract": re.compile(r"^workflow\.run\.[a-z][a-z0-9_]+$"),
}

_SEMVER_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

_VALID_PROVIDER_TYPES = {"MCP", "WASM", "BRIDGE", "AGENT", "WORKFLOW", "CONCIERGE"}
_VALID_SAFETY_BANDS = {"GREEN", "AMBER", "RED", "CRISIS"}
_VALID_AVAILABILITY = {"ONLINE", "DEGRADED", "OFFLINE"}
_VALID_OUTPUT_FORMATS = {"TEXT", "JSON", "STRUCTURED"}
_VALID_TRIGGER_TYPES = {"cron", "event", "manual"}

_TOOL_PROVIDER_TYPES = {"MCP", "WASM", "BRIDGE"}

# Cache for loaded JSON schemas
_schema_cache: Dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ContractValidationError(Exception):
    """
    Raised when a contract fails validation.

    Attributes:
        errors: List of individual validation error messages.
        contract_type: The type of contract that failed validation.
        contract_name: The name field from the contract, if available.
    """

    def __init__(
        self,
        errors: List[str],
        contract_type: str = "",
        contract_name: str = "",
    ):
        self.errors = errors
        self.contract_type = contract_type
        self.contract_name = contract_name
        summary = "; ".join(errors[:5])
        if len(errors) > 5:
            summary += f" ... and {len(errors) - 5} more"
        super().__init__(
            f"Contract validation failed for {contract_type}"
            f"{f' ({contract_name})' if contract_name else ''}: {summary}"
        )


# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------


def _load_schema(contract_type: str) -> dict:
    """Load and cache a JSON Schema file for the given contract type."""
    if contract_type in _schema_cache:
        return _schema_cache[contract_type]

    filename = _CONTRACT_TYPE_TO_SCHEMA_FILE.get(contract_type)
    if not filename:
        raise ValueError(f"Unknown contract type: {contract_type}")

    schema_path = _SCHEMA_DIR / filename
    if not schema_path.exists():
        raise FileNotFoundError(
            f"Schema file not found: {schema_path}. " f"Ensure Epic 1.2 schemas are registered."
        )

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    # Validate the schema itself is valid Draft-07
    Draft7Validator.check_schema(schema)
    _schema_cache[contract_type] = schema
    return schema


# ---------------------------------------------------------------------------
# Contract type detection
# ---------------------------------------------------------------------------


def detect_contract_type(data: Dict[str, Any]) -> Optional[str]:
    """
    Detect the contract type from a parsed YAML/dict structure.

    Returns one of: 'tool_contract', 'agent_contract', 'prompt_contract',
    'workflow_contract', or None if unrecognized.
    """
    for key in _CONTRACT_TYPE_TO_ROOT_KEY:
        if key in data:
            return key
    return None


# ---------------------------------------------------------------------------
# Phase 1: JSON Schema validation
# ---------------------------------------------------------------------------


def _validate_json_schema(
    data: Dict[str, Any],
    contract_type: str,
) -> List[str]:
    """
    Validate contract data against its JSON Schema (Draft-07).

    Returns list of error messages. Empty list = valid.
    """
    errors: List[str] = []
    try:
        schema = _load_schema(contract_type)
    except (FileNotFoundError, ValueError) as exc:
        errors.append(str(exc))
        return errors

    validator = Draft7Validator(schema)
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"[schema] {path}: {error.message}")

    return errors


# ---------------------------------------------------------------------------
# Phase 2: Semantic validation rules (12 rules from Section 6)
# ---------------------------------------------------------------------------


def _validate_name_convention(
    body: Dict[str, Any],
    contract_type: str,
    errors: List[str],
) -> None:
    """Rule 1: name follows type convention (FAB-11)."""
    name = body.get("name", "")
    if not name:
        errors.append("[rule-01] name is empty")
        return

    pattern = _NAME_PATTERNS.get(contract_type)
    if pattern and not pattern.match(name):
        errors.append(
            f"[rule-01] name '{name}' does not match "
            f"pattern for {contract_type}: {pattern.pattern}"
        )


def _validate_semver(
    body: Dict[str, Any],
    errors: List[str],
) -> None:
    """Rule 2: version is valid semver."""
    version = body.get("version", "")
    if not version:
        errors.append("[rule-02] version is empty")
        return
    if not _SEMVER_PATTERN.match(version):
        errors.append(
            f"[rule-02] version '{version}' is not valid semver " f"(expected major.minor.patch)"
        )


def _validate_domain(
    body: Dict[str, Any],
    errors: List[str],
) -> None:
    """Rule 3: domain[] has >= 1 tag."""
    domain = body.get("domain")
    if not domain or not isinstance(domain, list) or len(domain) == 0:
        errors.append("[rule-03] domain must have at least 1 tag")
        return
    for i, tag in enumerate(domain):
        if not isinstance(tag, str) or not tag.strip():
            errors.append(f"[rule-03] domain[{i}] is empty or not a string")


def _validate_description(
    body: Dict[str, Any],
    errors: List[str],
) -> None:
    """Rule 4: description non-empty."""
    desc = body.get("description", "")
    if not desc or not isinstance(desc, str) or not desc.strip():
        errors.append("[rule-04] description must be non-empty")
    elif len(desc) > 512:
        errors.append(f"[rule-04] description exceeds 512 characters (got {len(desc)})")


def _validate_required_inputs(
    body: Dict[str, Any],
    errors: List[str],
) -> None:
    """Rule 5: required_inputs have name/type/description."""
    inputs = body.get("required_inputs")
    if inputs is None:
        return  # Some contract types don't require inputs
    if not isinstance(inputs, list):
        errors.append("[rule-05] required_inputs must be a list")
        return
    for i, inp in enumerate(inputs):
        if not isinstance(inp, dict):
            errors.append(f"[rule-05] required_inputs[{i}] must be an object")
            continue
        for field_name in ("name", "type", "description"):
            val = inp.get(field_name, "")
            if not val or not isinstance(val, str) or not val.strip():
                errors.append(
                    f"[rule-05] required_inputs[{i}].{field_name} " f"is missing or empty"
                )


def _validate_output_schema(
    body: Dict[str, Any],
    contract_type: str,
    errors: List[str],
) -> None:
    """Rule 6: output has valid JSON Schema (for tool/agent contracts)."""
    if contract_type not in ("tool_contract", "agent_contract"):
        return
    output = body.get("output")
    if output is None:
        return  # JSON Schema will catch required field
    if not isinstance(output, dict):
        errors.append("[rule-06] output must be an object (JSON Schema)")
        return
    if "type" not in output:
        errors.append("[rule-06] output must have a 'type' property")


def _validate_provider_type(
    body: Dict[str, Any],
    contract_type: str,
    errors: List[str],
) -> None:
    """Rule 7: provider_type is valid enum."""
    provider_type = body.get("provider_type")
    if provider_type is None:
        return  # Not all contract types have provider_type
    if provider_type not in _VALID_PROVIDER_TYPES:
        errors.append(
            f"[rule-07] provider_type '{provider_type}' is not valid; "
            f"expected one of {sorted(_VALID_PROVIDER_TYPES)}"
        )

    # Tool contracts must have MCP/WASM/BRIDGE only
    if contract_type == "tool_contract" and provider_type not in _TOOL_PROVIDER_TYPES:
        errors.append(
            f"[rule-07] tool_contract provider_type must be one of "
            f"{sorted(_TOOL_PROVIDER_TYPES)}, got '{provider_type}'"
        )

    # Agent contracts must have AGENT
    if contract_type == "agent_contract" and provider_type != "AGENT":
        errors.append(
            f"[rule-07] agent_contract provider_type must be 'AGENT', " f"got '{provider_type}'"
        )


def _validate_safety_band(
    body: Dict[str, Any],
    errors: List[str],
) -> None:
    """Rule 8: safety_band_min is valid."""
    band = body.get("safety_band_min")
    if band is None:
        return
    if band not in _VALID_SAFETY_BANDS:
        errors.append(
            f"[rule-08] safety_band_min '{band}' is not valid; "
            f"expected one of {sorted(_VALID_SAFETY_BANDS)}"
        )


def _validate_availability(
    body: Dict[str, Any],
    errors: List[str],
) -> None:
    """Rule 9: availability is valid."""
    avail = body.get("availability")
    if avail is None:
        return
    if avail not in _VALID_AVAILABILITY:
        errors.append(
            f"[rule-09] availability '{avail}' is not valid; "
            f"expected one of {sorted(_VALID_AVAILABILITY)}"
        )


def _validate_agent_tools_granted(
    body: Dict[str, Any],
    contract_type: str,
    errors: List[str],
) -> None:
    """Rule 10: agent tools_granted reference valid capability names."""
    if contract_type != "agent_contract":
        return
    tools = body.get("tools_granted")
    if tools is None:
        return
    if not isinstance(tools, list):
        errors.append("[rule-10] tools_granted must be a list")
        return
    # Allow 3+ segments: native (tool.verb.name), IFL (tool.verb.cat.adapter.action),
    # MCP dynamic (tool.verb.mcp.name)
    tool_name_pattern = re.compile(r"^tool\.(execute|read|write|delete)(\.[a-z][a-z0-9_]+)+$")
    for i, tool_name in enumerate(tools):
        if not isinstance(tool_name, str) or not tool_name.strip():
            errors.append(f"[rule-10] tools_granted[{i}] is empty or not a string")
        elif not tool_name_pattern.match(tool_name):
            errors.append(
                f"[rule-10] tools_granted[{i}] '{tool_name}' does not follow "
                f"tool naming convention (tool.<verb>.<name>[.<segments>...])"
            )


def _validate_prompt_variables(
    body: Dict[str, Any],
    contract_type: str,
    errors: List[str],
) -> None:
    """Rule 11: prompt variables are satisfiable (name, type, description present)."""
    if contract_type != "prompt_contract":
        return
    variables = body.get("variables")
    if variables is None:
        return
    if not isinstance(variables, list):
        errors.append("[rule-11] variables must be a list")
        return
    valid_var_types = {"STRING", "NUMBER", "BOOLEAN", "DATE", "OBJECT", "ARRAY"}
    seen_names: Set[str] = set()
    for i, var in enumerate(variables):
        if not isinstance(var, dict):
            errors.append(f"[rule-11] variables[{i}] must be an object")
            continue
        var_name = var.get("name", "")
        if not var_name:
            errors.append(f"[rule-11] variables[{i}].name is missing or empty")
        elif var_name in seen_names:
            errors.append(f"[rule-11] variables[{i}].name '{var_name}' is duplicate")
        else:
            seen_names.add(var_name)

        var_type = var.get("type", "")
        if var_type and var_type not in valid_var_types:
            errors.append(
                f"[rule-11] variables[{i}].type '{var_type}' is not valid; "
                f"expected one of {sorted(valid_var_types)}"
            )

        if "required" not in var:
            errors.append(
                f"[rule-11] variables[{i}].required is missing " f"(must be true or false)"
            )
        elif not isinstance(var.get("required"), bool):
            errors.append(f"[rule-11] variables[{i}].required must be a boolean")

        # Default is only valid when required=false
        if var.get("default") is not None and var.get("required") is True:
            errors.append(
                f"[rule-11] variables[{i}] has default but required=true "
                f"(default is only valid when required=false)"
            )


def _validate_workflow_dag(
    body: Dict[str, Any],
    contract_type: str,
    errors: List[str],
) -> None:
    """Rule 12: workflow deps are acyclic DAG."""
    if contract_type != "workflow_contract":
        return

    steps = body.get("steps")
    if not steps or not isinstance(steps, list):
        return

    # Build step ID set
    step_ids: Set[str] = set()
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"[rule-12] steps[{i}] must be an object")
            continue
        step_id = step.get("id", "")
        if not step_id:
            errors.append(f"[rule-12] steps[{i}].id is missing or empty")
            continue
        if step_id in step_ids:
            errors.append(f"[rule-12] steps[{i}].id '{step_id}' is duplicate")
        step_ids.add(step_id)

    # Validate deps reference existing step IDs
    deps_map: Dict[str, List[str]] = {}
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_id = step.get("id", "")
        if not step_id:
            continue
        deps = step.get("deps", [])
        if not isinstance(deps, list):
            errors.append(f"[rule-12] steps['{step_id}'].deps must be a list")
            deps = []
        for dep_id in deps:
            if dep_id not in step_ids:
                errors.append(
                    f"[rule-12] steps['{step_id}'] depends on '{dep_id}' "
                    f"which does not exist in steps"
                )
        deps_map[step_id] = deps

    # Also validate the top-level dependencies map if present
    top_deps = body.get("dependencies")
    if top_deps and isinstance(top_deps, dict):
        for step_id, dep_list in top_deps.items():
            if step_id not in step_ids:
                errors.append(f"[rule-12] dependencies key '{step_id}' " f"does not exist in steps")
            if isinstance(dep_list, list):
                for dep_id in dep_list:
                    if dep_id not in step_ids:
                        errors.append(
                            f"[rule-12] dependencies['{step_id}'] references "
                            f"'{dep_id}' which does not exist in steps"
                        )
                # Use top-level deps as authoritative for cycle check
                deps_map[step_id] = dep_list

    # Topological sort cycle detection (Kahn's algorithm)
    if step_ids and deps_map:
        in_degree: Dict[str, int] = {sid: 0 for sid in step_ids}
        for sid, deps in deps_map.items():
            in_degree.setdefault(sid, 0)
            for dep in deps:
                if dep in step_ids:
                    in_degree[sid] = in_degree.get(sid, 0) + 1

        # Reverse map: build adjacency list (dep -> [dependents])
        adjacency: Dict[str, List[str]] = {sid: [] for sid in step_ids}
        for sid, deps in deps_map.items():
            for dep in deps:
                if dep in step_ids:
                    adjacency.setdefault(dep, []).append(sid)

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        visited_count = 0
        while queue:
            node = queue.pop(0)
            visited_count += 1
            for neighbor in adjacency.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(step_ids):
            cycle_nodes = [sid for sid, deg in in_degree.items() if deg > 0]
            errors.append(
                f"[rule-12] workflow dependencies contain a cycle "
                f"involving steps: {sorted(cycle_nodes)}"
            )


# ---------------------------------------------------------------------------
# Main validation API
# ---------------------------------------------------------------------------


class ContractValidator:
    """
    Validates capability contracts against JSON Schema and semantic rules.

    Two-phase validation:
      Phase 1: JSON Schema (Draft-07) structural validation
      Phase 2: 12 semantic business rules from fabric_discussion.md Section 6

    Thread-safe: stateless, all methods are pure functions.
    No I/O dependencies. No ports. Pure computation.

    Usage:
        validator = ContractValidator()
        errors = validator.validate(data, contract_type="tool_contract")
        if errors:
            raise ContractValidationError(errors, contract_type=...)

        # Or use the convenience method:
        validator.validate_or_raise(data, contract_type="tool_contract")
    """

    def validate(
        self,
        data: Dict[str, Any],
        contract_type: Optional[str] = None,
    ) -> List[str]:
        """
        Validate a contract data structure.

        Args:
            data: Parsed YAML/dict with root key (e.g. {"tool_contract": {...}})
            contract_type: Explicit contract type. Auto-detected if None.

        Returns:
            List of error strings. Empty list = valid.
        """
        errors: List[str] = []

        # Auto-detect contract type if not provided
        if contract_type is None:
            contract_type = detect_contract_type(data)
            if contract_type is None:
                errors.append(
                    "Cannot detect contract type. Expected root key: "
                    "tool_contract, agent_contract, prompt_contract, "
                    "or workflow_contract"
                )
                return errors

        root_key = _CONTRACT_TYPE_TO_ROOT_KEY.get(contract_type)
        if root_key is None:
            errors.append(f"Unknown contract type: {contract_type}")
            return errors

        # Phase 1: JSON Schema validation
        schema_errors = _validate_json_schema(data, contract_type)
        errors.extend(schema_errors)

        # Extract the body (inner dict under root key)
        body = data.get(root_key)
        if not isinstance(body, dict):
            errors.append(
                f"Root key '{root_key}' must contain an object, " f"got {type(body).__name__}"
            )
            return errors

        # Phase 2: Semantic validation (12 rules)
        _validate_name_convention(body, contract_type, errors)
        _validate_semver(body, errors)
        _validate_domain(body, errors)
        _validate_description(body, errors)
        _validate_required_inputs(body, errors)
        _validate_output_schema(body, contract_type, errors)
        _validate_provider_type(body, contract_type, errors)
        _validate_safety_band(body, errors)
        _validate_availability(body, errors)
        _validate_agent_tools_granted(body, contract_type, errors)
        _validate_prompt_variables(body, contract_type, errors)
        _validate_workflow_dag(body, contract_type, errors)

        return errors

    def validate_or_raise(
        self,
        data: Dict[str, Any],
        contract_type: Optional[str] = None,
    ) -> None:
        """
        Validate a contract and raise ContractValidationError if invalid.

        Args:
            data: Parsed YAML/dict with root key
            contract_type: Explicit contract type. Auto-detected if None.

        Raises:
            ContractValidationError: If any validation rule fails.
        """
        ct = contract_type or detect_contract_type(data) or ""
        errors = self.validate(data, contract_type)
        if errors:
            # Extract name for error context
            root_key = _CONTRACT_TYPE_TO_ROOT_KEY.get(ct, "")
            body = data.get(root_key, {})
            name = body.get("name", "") if isinstance(body, dict) else ""
            raise ContractValidationError(
                errors=errors,
                contract_type=ct,
                contract_name=name,
            )

    def validate_body(
        self,
        body: Dict[str, Any],
        contract_type: str,
    ) -> List[str]:
        """
        Validate just the inner body (without root key wrapper).

        Wraps the body in the expected root key and delegates to validate().
        Convenience for callers that already extracted the body.

        Args:
            body: Inner contract dict (e.g. {"name": "tool.execute.x", ...})
            contract_type: Contract type string.

        Returns:
            List of error strings. Empty list = valid.
        """
        root_key = _CONTRACT_TYPE_TO_ROOT_KEY.get(contract_type)
        if root_key is None:
            return [f"Unknown contract type: {contract_type}"]
        return self.validate({root_key: body}, contract_type)
