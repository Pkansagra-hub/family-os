"""
Prompt Contract Parser -- Loads and parses prompt contract YAML into PromptContract.

Responsibilities:
  1. Load YAML from file path or accept raw dict
  2. Extract prompt_contract root key
  3. Validate via ContractValidator (schema + 12 semantic rules)
  4. Parse into PromptContract frozen dataclass

Design decisions:
  - FAB-12: All contracts validated against schema before registration
  - FAB-11: Capability names follow type conventions (lowercase alphanumeric)
  - Parser is stateless: no side effects, no caching, no I/O beyond YAML loading
  - Validation is delegated to ContractValidator (single responsibility)

References:
  - fabric_discussion.md Section 6 (Contract system, prompt contract example)
  - prompt_contract.schema.json (JSON Schema definition)
  - Epic 2.1.4 in fabric-implementation-plan.md

Consumed by:
  - Contract facade parse_contract() (2.1.6)
  - ModuleLoader.scan_directory() (2.3.1)
  - CapabilityRegistry.register() (2.2.2)
  - RetrievalEngine.find_relevant_prompts() (4.1.5)
  - ContextBuilder (4.2.1)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

import yaml

from k1.fabric.core.contract_validator import ContractValidator
from k1.fabric.types import PromptContract, VariableSpec

logger = logging.getLogger(__name__)

_CONTRACT_TYPE = "prompt_contract"


class PromptContractParseError(Exception):
    """
    Raised when a prompt contract cannot be parsed.

    This covers:
      - YAML syntax errors
      - Missing root key
      - File I/O failures

    Validation failures raise ContractValidationError instead.
    """


class PromptContractParser:
    """
    Parses prompt contract YAML into validated PromptContract instances.

    Thread-safe: stateless, all methods are pure functions (except file I/O).
    No shared mutable state between calls.

    Usage:
        parser = PromptContractParser()

        # From file:
        contract = parser.parse("k1/contracts/prompts/invitation_drafter_v1.yaml")

        # From dict:
        contract = parser.parse({"prompt_contract": {...}})

        # With custom validator:
        validator = ContractValidator()
        parser = PromptContractParser(validator=validator)
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
    ) -> PromptContract:
        """
        Parse a prompt contract from a file path or raw dict.

        Args:
            source: One of:
                - str / Path: file path to a YAML contract file
                - dict: pre-parsed YAML with root key 'prompt_contract'
            skip_validation: If True, skip ContractValidator validation.
                Only use for performance-critical hot paths where the
                contract has already been validated.

        Returns:
            PromptContract frozen dataclass.

        Raises:
            PromptContractParseError: YAML syntax, missing root key, or I/O error.
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
    ) -> PromptContract:
        """
        Parse from an already-extracted body dict (no root key wrapper).

        Convenience for callers that have already unwrapped the YAML structure.

        Args:
            body: Inner dict with prompt contract fields.
            skip_validation: If True, skip validation.

        Returns:
            PromptContract frozen dataclass.

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
            raise FileNotFoundError(f"Prompt contract file not found: {path}")
        if path.suffix not in (".yaml", ".yml"):
            raise PromptContractParseError(f"Expected .yaml or .yml file, got: {path.suffix}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise PromptContractParseError(f"Invalid YAML in {path}: {exc}") from exc

        if not isinstance(data, dict):
            raise PromptContractParseError(
                f"Expected YAML mapping at root level, " f"got {type(data).__name__} in {path}"
            )
        return data

    @staticmethod
    def _extract_body(data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract the prompt_contract body from the root-keyed structure."""
        if _CONTRACT_TYPE not in data:
            available_keys = list(data.keys())
            raise PromptContractParseError(
                f"Missing root key '{_CONTRACT_TYPE}'. " f"Found keys: {available_keys}"
            )

        body = data[_CONTRACT_TYPE]
        if not isinstance(body, dict):
            raise PromptContractParseError(
                f"Root key '{_CONTRACT_TYPE}' must contain a mapping, " f"got {type(body).__name__}"
            )
        return body

    # -------------------------------------------------------------------
    # Private: Building
    # -------------------------------------------------------------------

    @staticmethod
    def _build_contract(body: Dict[str, Any]) -> PromptContract:
        """
        Construct a PromptContract from a validated body dict.

        Maps all prompt_contract.schema.json fields to PromptContract fields.
        Uses VariableSpec.from_dict for nested variable parsing.
        """
        variables = [
            VariableSpec.from_dict(v) for v in body.get("variables", []) if isinstance(v, dict)
        ]

        return PromptContract(
            # ---- Identity ----
            name=body.get("name", ""),
            version=body.get("version", ""),
            domain=list(body.get("domain", [])),
            description=body.get("description", ""),
            activity_profile=body.get("activity_profile", ""),
            # ---- Retrieval Matching ----
            intent_match=list(body.get("intent_match", [])),
            # ---- Template Variables ----
            variables=variables,
            # ---- Template Configuration ----
            template_file=body.get("template_file", ""),
            max_tokens=int(body.get("max_tokens", 0)),
            output_format=body.get("output_format", "TEXT"),
            # ---- Compatibility ----
            compatible_agents=list(body.get("compatible_agents", [])),
            compatible_tools=list(body.get("compatible_tools", [])),
            # ---- Audit Fields ----
            registered_at=body.get("registered_at", ""),
            last_updated=body.get("last_updated", ""),
        )
