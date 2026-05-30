"""
k1.fabric.contracts -- Contract parser implementations for all 4 contract types.

This package provides:
  1. Four type-specific parsers (tool, agent, prompt, workflow)
  2. A unified parse_contract() facade that auto-detects contract type
     from the YAML root key and routes to the correct parser

The parse_contract() facade is the single entry point called by
ModuleLoader.scan_directory() (2.3.3) and programmatic registration (2.3.4).

Design decisions:
  - FAB-12: All contracts validated against schema before registration
  - FAB-11: Capability names follow type conventions
  - Auto-detection via root key (tool_contract, agent_contract, etc.)
  - Shared ContractValidator instance across all parsers for schema caching

References:
  - Epic 2.1.6 in fabric-implementation-plan.md
  - fabric_discussion.md Section 6 (Contract system)

Exports:
  parse_contract -- Auto-detect and parse any contract YAML
  ContractParseError -- Raised when auto-detection or routing fails
  ToolContractParser / ToolContractParseError
  AgentContractParser / AgentContractParseError
  PromptContractParser / PromptContractParseError
  WorkflowContractParser / WorkflowContractParseError
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

import yaml

from k1.fabric.contracts.agent_contract import (
    AgentContractParseError,
    AgentContractParser,
)
from k1.fabric.contracts.context_precision import (
    ContextPrecision,
    parse_context_precision,
)
from k1.fabric.contracts.prompt_contract import (
    PromptContractParseError,
    PromptContractParser,
)
from k1.fabric.contracts.tool_contract import ToolContractParseError, ToolContractParser
from k1.fabric.contracts.workflow_contract import (
    WorkflowContractParseError,
    WorkflowContractParser,
)
from k1.fabric.core.contract_validator import ContractValidator, detect_contract_type
from k1.fabric.types import (
    AgentContract,
    CapabilityContract,
    PromptContract,
    WorkflowContract,
)

logger = logging.getLogger(__name__)

# Union of all contract return types
ContractUnion = Union[CapabilityContract, AgentContract, PromptContract, WorkflowContract]


class ContractParseError(Exception):
    """
    Raised when parse_contract() cannot detect or route a contract.

    This covers:
      - Unknown root key (not one of the 4 contract types)
      - YAML syntax errors during loading
      - File I/O failures

    Type-specific parse errors (ToolContractParseError, etc.) are raised
    by the individual parsers for root-key extraction failures.
    """


def parse_contract(
    source: Union[str, Path, Dict[str, Any]],
    *,
    validator: Optional[ContractValidator] = None,
    skip_validation: bool = False,
) -> ContractUnion:
    """
    Auto-detect contract type and parse into the appropriate dataclass.

    This is the single entry point for contract loading. It:
      1. Loads YAML from file path or accepts a raw dict
      2. Detects the contract type from the root key
      3. Routes to the correct type-specific parser
      4. Returns the parsed frozen dataclass

    Args:
        source: One of:
            - str / Path: file path to a YAML contract file
            - dict: pre-parsed YAML with a recognized root key
        validator: Optional shared ContractValidator. If None, creates one.
            Pass a shared instance for schema caching across multiple parses.
        skip_validation: If True, skip ContractValidator validation.
            Only use for performance-critical hot paths.

    Returns:
        One of: CapabilityContract, AgentContract, PromptContract, WorkflowContract

    Raises:
        ContractParseError: Unknown contract type, YAML error, or I/O failure.
        ContractValidationError: Schema or semantic rule violation.
        FileNotFoundError: File does not exist.
    """
    data = _load_source(source)

    contract_type = detect_contract_type(data)
    if contract_type is None:
        available_keys = [k for k in data.keys() if isinstance(k, str)]
        raise ContractParseError(
            f"Cannot detect contract type. Expected one of: "
            f"tool_contract, agent_contract, prompt_contract, workflow_contract. "
            f"Found root keys: {available_keys}"
        )

    shared_validator = validator or ContractValidator()

    parser = _PARSERS[contract_type](validator=shared_validator)
    return parser.parse(data, skip_validation=skip_validation)


def parse_contract_body(
    body: Dict[str, Any],
    contract_type: str,
    *,
    validator: Optional[ContractValidator] = None,
    skip_validation: bool = False,
) -> ContractUnion:
    """
    Parse from an already-extracted body dict with an explicit contract type.

    Convenience for callers that have already unwrapped the YAML structure
    and know the contract type.

    Args:
        body: Inner contract dict (without root key wrapper).
        contract_type: One of 'tool_contract', 'agent_contract',
            'prompt_contract', 'workflow_contract'.
        validator: Optional shared ContractValidator.
        skip_validation: If True, skip validation.

    Returns:
        One of: CapabilityContract, AgentContract, PromptContract, WorkflowContract

    Raises:
        ContractParseError: Unknown contract_type.
        ContractValidationError: Schema or semantic rule violation.
    """
    if contract_type not in _PARSERS:
        raise ContractParseError(
            f"Unknown contract type: '{contract_type}'. "
            f"Expected one of: {sorted(_PARSERS.keys())}"
        )

    shared_validator = validator or ContractValidator()
    parser = _PARSERS[contract_type](validator=shared_validator)
    return parser.parse_body(body, skip_validation=skip_validation)


# ---------------------------------------------------------------------------
# Private: Loading + Router map
# ---------------------------------------------------------------------------

_PARSERS = {
    "tool_contract": ToolContractParser,
    "agent_contract": AgentContractParser,
    "prompt_contract": PromptContractParser,
    "workflow_contract": WorkflowContractParser,
}


def _load_source(source: Union[str, Path, Dict[str, Any]]) -> Dict[str, Any]:
    """Load raw data from file path or passthrough dict."""
    if isinstance(source, dict):
        return source

    path = Path(source)
    if path.suffix not in (".yaml", ".yml"):
        raise ContractParseError(f"Expected .yaml or .yml file, got: {path.suffix}")
    if not path.exists():
        raise FileNotFoundError(f"Contract file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ContractParseError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ContractParseError(
            f"Expected YAML mapping at root level, " f"got {type(data).__name__} in {path}"
        )
    return data


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    # Facade
    "parse_contract",
    "parse_contract_body",
    "ContractParseError",
    "ContractUnion",
    # Tool
    "ToolContractParser",
    "ToolContractParseError",
    # Agent
    "AgentContractParser",
    "AgentContractParseError",
    # Grounding precision
    "ContextPrecision",
    "parse_context_precision",
    # Prompt
    "PromptContractParser",
    "PromptContractParseError",
    # Workflow
    "WorkflowContractParser",
    "WorkflowContractParseError",
]
