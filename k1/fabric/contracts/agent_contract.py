"""
Agent Contract Parser -- Loads and parses agent contract YAML into AgentContract.

Responsibilities:
  1. Load YAML from file path or accept raw dict
  2. Extract agent_contract root key
  3. Validate via ContractValidator (schema + 12 semantic rules)
  4. Parse into AgentContract frozen dataclass

Design decisions:
  - FAB-12: All contracts validated against schema before registration
  - FAB-11: Capability names follow type conventions (agent.<verb>.<name>)
  - FAB-07: tools_granted[] scoped per plan step
  - Parser is stateless: no side effects, no caching, no I/O beyond YAML loading
  - Validation is delegated to ContractValidator (single responsibility)

References:
  - fabric_discussion.md Section 6 (Contract system, agent contract example)
  - agent_contract.schema.json (JSON Schema definition)
  - FAB-006 (Agent Lifecycle specialization)
  - Epic 2.1.3 in fabric-implementation-plan.md

Consumed by:
  - Contract facade parse_contract() (2.1.6)
  - ModuleLoader.scan_directory() (2.3.1)
  - CapabilityRegistry.register() (2.2.2)
  - AgentFactory (4.3.1)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

import yaml

from k1.fabric.contracts.context_precision import parse_context_precision
from k1.fabric.core.contract_validator import ContractValidator
from k1.fabric.types import AgentContract, InputSpec

logger = logging.getLogger(__name__)

_CONTRACT_TYPE = "agent_contract"


class AgentContractParseError(Exception):
    """
    Raised when an agent contract cannot be parsed.

    This covers:
      - YAML syntax errors
      - Missing root key
      - File I/O failures

    Validation failures raise ContractValidationError instead.
    """


class AgentContractParser:
    """
    Parses agent contract YAML into validated AgentContract instances.

    Thread-safe: stateless, all methods are pure functions (except file I/O).
    No shared mutable state between calls.

    Usage:
        parser = AgentContractParser()

        # From file:
        contract = parser.parse("k1/contracts/agents/invitation_sender.yaml")

        # From dict:
        contract = parser.parse({"agent_contract": {...}})

        # With custom validator:
        validator = ContractValidator()
        parser = AgentContractParser(validator=validator)
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
    ) -> AgentContract:
        """
        Parse an agent contract from a file path or raw dict.

        Args:
            source: One of:
                - str / Path: file path to a YAML contract file
                - dict: pre-parsed YAML with root key 'agent_contract'
            skip_validation: If True, skip ContractValidator validation.
                Only use for performance-critical hot paths where the
                contract has already been validated.

        Returns:
            AgentContract frozen dataclass.

        Raises:
            AgentContractParseError: YAML syntax, missing root key, or I/O error.
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
    ) -> AgentContract:
        """
        Parse from an already-extracted body dict (no root key wrapper).

        Convenience for callers that have already unwrapped the YAML structure.

        Args:
            body: Inner dict with agent contract fields.
            skip_validation: If True, skip validation.

        Returns:
            AgentContract frozen dataclass.

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
            raise FileNotFoundError(f"Agent contract file not found: {path}")
        if path.suffix not in (".yaml", ".yml"):
            raise AgentContractParseError(f"Expected .yaml or .yml file, got: {path.suffix}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise AgentContractParseError(f"Invalid YAML in {path}: {exc}") from exc

        if not isinstance(data, dict):
            raise AgentContractParseError(
                f"Expected YAML mapping at root level, " f"got {type(data).__name__} in {path}"
            )
        return data

    @staticmethod
    def _extract_body(data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract the agent_contract body from the root-keyed structure."""
        if _CONTRACT_TYPE not in data:
            available_keys = list(data.keys())
            raise AgentContractParseError(
                f"Missing root key '{_CONTRACT_TYPE}'. " f"Found keys: {available_keys}"
            )

        body = data[_CONTRACT_TYPE]
        if not isinstance(body, dict):
            raise AgentContractParseError(
                f"Root key '{_CONTRACT_TYPE}' must contain a mapping, " f"got {type(body).__name__}"
            )
        return body

    # -------------------------------------------------------------------
    # Private: Building
    # -------------------------------------------------------------------

    @staticmethod
    def _build_contract(body: Dict[str, Any]) -> AgentContract:
        """
        Construct an AgentContract from a validated body dict.

        Maps all agent_contract.schema.json fields to AgentContract fields.
        Includes base CapabilityContract fields + 6 agent-specific fields.
        Uses InputSpec.from_dict for nested input parsing.
        """
        required_inputs = [
            InputSpec.from_dict(inp)
            for inp in body.get("required_inputs", [])
            if isinstance(inp, dict)
        ]
        optional_inputs = [
            InputSpec.from_dict(inp)
            for inp in body.get("optional_inputs", [])
            if isinstance(inp, dict)
        ]

        return AgentContract(
            # ---- Base CapabilityContract: Identity ----
            name=body.get("name", ""),
            version=body.get("version", ""),
            domain=list(body.get("domain", [])),
            description=body.get("description", ""),
            # ---- Base: Capabilities & Limitations ----
            capabilities=list(body.get("capabilities", [])),
            limitations=list(body.get("limitations", [])),
            # ---- Base: Input Requirements ----
            required_inputs=required_inputs,
            optional_inputs=optional_inputs,
            # ---- Base: Context Requirements ----
            required_context=list(body.get("required_context", [])),
            optional_context=list(body.get("optional_context", [])),
            # ---- Base: Output Schema ----
            output=dict(body.get("output", {})),
            # ---- Base: Provider Metadata ----
            provider_type=body.get("provider_type", "AGENT"),
            provider_id=body.get("provider_id", ""),
            provider_endpoint=body.get("provider_endpoint", ""),
            context_precision=parse_context_precision(body.get("context_precision")),
            lease=dict(body["lease"]) if isinstance(body.get("lease"), dict) else body.get("lease"),
            # ---- Base: Policy Metadata ----
            safety_band_min=body.get("safety_band_min", "GREEN"),
            cost_per_call=float(body.get("cost_per_call", 0.0)),
            avg_latency_ms=int(body.get("avg_latency_ms", 0)),
            max_latency_ms=int(body.get("max_latency_ms", 0)),
            availability=body.get("availability", "ONLINE"),
            # ---- Base: Audit Fields ----
            registered_at=body.get("registered_at", ""),
            last_updated=body.get("last_updated", ""),
            success_rate_30d=float(body.get("success_rate_30d", 0.0)),
            total_invocations_30d=int(body.get("total_invocations_30d", 0)),
            # ---- Agent-Specific Fields ----
            prompt_template=body.get("prompt_template", ""),
            tools_granted=list(body.get("tools_granted", [])),
            llm_budget_tokens=int(body.get("llm_budget_tokens", 0)),
            max_tool_calls=int(body.get("max_tool_calls", 0)),
            max_execution_time_ms=int(body.get("max_execution_time_ms", 30000)),
            template_file=body.get("template_file", ""),
        )
