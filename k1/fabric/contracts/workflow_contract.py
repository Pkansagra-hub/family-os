"""
Workflow Contract Parser -- Loads and parses workflow contract YAML into WorkflowContract.

Responsibilities:
  1. Load YAML from file path or accept raw dict
  2. Extract workflow_contract root key
  3. Validate via ContractValidator (schema + 12 semantic rules incl. DAG acyclicity)
  4. Parse into WorkflowContract frozen dataclass

Design decisions:
  - FAB-12: All contracts validated against schema before registration
  - FAB-11: Capability names follow type conventions (workflow.run.<name>)
  - Rule-12 (DAG acyclicity) enforced by ContractValidator
  - Parser is stateless: no side effects, no caching, no I/O beyond YAML loading
  - Validation is delegated to ContractValidator (single responsibility)

References:
  - fabric_discussion.md Section 6 (Contract system, workflow contract example)
  - workflow_contract.schema.json (JSON Schema definition)
  - FAB-001 (CommittedPlan, PlanStep types)
  - Epic 2.1.5 in fabric-implementation-plan.md

Consumed by:
  - Contract facade parse_contract() (2.1.6)
  - ModuleLoader.scan_directory() (2.3.1)
  - CapabilityRegistry.register() (2.2.2)
  - WorkflowProvider (3.3.5)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

import yaml

from k1.fabric.core.contract_validator import ContractValidator
from k1.fabric.types import PlanStep, TriggerSpec, WorkflowContract

logger = logging.getLogger(__name__)

_CONTRACT_TYPE = "workflow_contract"


class WorkflowContractParseError(Exception):
    """
    Raised when a workflow contract cannot be parsed.

    This covers:
      - YAML syntax errors
      - Missing root key
      - File I/O failures

    Validation failures raise ContractValidationError instead.
    """


class WorkflowContractParser:
    """
    Parses workflow contract YAML into validated WorkflowContract instances.

    Thread-safe: stateless, all methods are pure functions (except file I/O).
    No shared mutable state between calls.

    Usage:
        parser = WorkflowContractParser()

        # From file:
        contract = parser.parse("k1/contracts/workflows/weekly_health_check.yaml")

        # From dict:
        contract = parser.parse({"workflow_contract": {...}})

        # With custom validator:
        validator = ContractValidator()
        parser = WorkflowContractParser(validator=validator)
    """

    def __init__(
        self,
        validator: Optional[ContractValidator] = None,
    ) -> None:
        """
        Args:
            validator: Optional ContractValidator instance. If None, creates
                       a default one. Allows dependency injection for testing.
        """
        self._validator = validator or ContractValidator()

    def parse(
        self,
        source: Union[str, Path, Dict[str, Any]],
        *,
        skip_validation: bool = False,
    ) -> WorkflowContract:
        """
        Parse a workflow contract from a file path or raw dict.

        Args:
            source: One of:
                - str / Path: file path to a YAML contract file
                - dict: pre-parsed YAML with root key 'workflow_contract'
            skip_validation: If True, skip ContractValidator validation.
                Only use for performance-critical hot paths where the
                contract has already been validated.

        Returns:
            WorkflowContract frozen dataclass.

        Raises:
            WorkflowContractParseError: YAML syntax, missing root key, or I/O error.
            ContractValidationError: Schema or semantic rule violation.
            FileNotFoundError: File does not exist.
        """
        data = self._load(source)
        body = self._extract_body(data)

        if not skip_validation:
            self._validator.validate_or_raise(data, contract_type=_CONTRACT_TYPE)

        return self._build_contract(body)

    def parse_body(
        self,
        body: Dict[str, Any],
        *,
        skip_validation: bool = False,
    ) -> WorkflowContract:
        """
        Parse from an already-extracted body dict (no root key wrapper).

        Convenience for callers that have already unwrapped the YAML structure.

        Args:
            body: Inner dict with workflow contract fields.
            skip_validation: If True, skip validation.

        Returns:
            WorkflowContract frozen dataclass.

        Raises:
            ContractValidationError: Schema or semantic rule violation.
        """
        if not skip_validation:
            wrapped = {_CONTRACT_TYPE: body}
            self._validator.validate_or_raise(wrapped, contract_type=_CONTRACT_TYPE)

        return self._build_contract(body)

    # -------------------------------------------------------------------
    # Private: Loading
    # -------------------------------------------------------------------

    @staticmethod
    def _load(source: Union[str, Path, Dict[str, Any]]) -> Dict[str, Any]:
        """Load raw data from file or passthrough dict."""
        if isinstance(source, dict):
            return source

        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Workflow contract file not found: {path}")
        if path.suffix not in (".yaml", ".yml"):
            raise WorkflowContractParseError(f"Expected .yaml or .yml file, got: {path.suffix}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise WorkflowContractParseError(f"Invalid YAML in {path}: {exc}") from exc

        if not isinstance(data, dict):
            raise WorkflowContractParseError(
                f"Expected YAML mapping at root level, " f"got {type(data).__name__} in {path}"
            )
        return data

    @staticmethod
    def _extract_body(data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract the workflow_contract body from the root-keyed structure."""
        if _CONTRACT_TYPE not in data:
            available_keys = list(data.keys())
            raise WorkflowContractParseError(
                f"Missing root key '{_CONTRACT_TYPE}'. " f"Found keys: {available_keys}"
            )

        body = data[_CONTRACT_TYPE]
        if not isinstance(body, dict):
            raise WorkflowContractParseError(
                f"Root key '{_CONTRACT_TYPE}' must contain a mapping, " f"got {type(body).__name__}"
            )
        return body

    # -------------------------------------------------------------------
    # Private: Building
    # -------------------------------------------------------------------

    @staticmethod
    def _build_contract(body: Dict[str, Any]) -> WorkflowContract:
        """
        Construct a WorkflowContract from a validated body dict.

        Maps all workflow_contract.schema.json fields to WorkflowContract fields.
        Uses TriggerSpec.from_dict and PlanStep.from_dict for nested parsing.
        """
        trigger_data = body.get("trigger")
        trigger = TriggerSpec.from_dict(trigger_data) if isinstance(trigger_data, dict) else None

        steps = [PlanStep.from_dict(s) for s in body.get("steps", []) if isinstance(s, dict)]

        # Normalize dependencies: ensure all values are lists
        raw_deps = body.get("dependencies", {})
        dependencies: Dict[str, list] = {}
        if isinstance(raw_deps, dict):
            for step_id, dep_list in raw_deps.items():
                if isinstance(dep_list, list):
                    dependencies[step_id] = list(dep_list)

        return WorkflowContract(
            # ---- Identity ----
            name=body.get("name", ""),
            version=body.get("version", ""),
            domain=list(body.get("domain", [])),
            description=body.get("description", ""),
            # ---- Plan Origin ----
            source_plan_id=body.get("source_plan_id", ""),
            # ---- Trigger Configuration ----
            trigger=trigger,
            # ---- Execution Steps (DAG) ----
            steps=steps,
            dependencies=dependencies,
            # ---- Recursion & Sub-Workflow Control ----
            max_depth=int(body.get("max_depth", 3)),
            allows_sub_workflows=bool(body.get("allows_sub_workflows", True)),
            # ---- Policy Metadata ----
            safety_band_min=body.get("safety_band_min", "GREEN"),
            avg_latency_ms=int(body.get("avg_latency_ms", 0)),
            active=bool(body.get("active", True)),
            # ---- Audit Fields ----
            created_at=body.get("created_at", ""),
            last_run=body.get("last_run", ""),
            run_count=int(body.get("run_count", 0)),
            success_rate=float(body.get("success_rate", 0.0)),
        )
