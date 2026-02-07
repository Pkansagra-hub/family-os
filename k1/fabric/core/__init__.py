"""
k1.fabric.core -- Core validation, registry, orchestration, and context components.

Exports:
  ContractValidator -- Two-phase contract validation (schema + 12 rules)
  ContractValidationError -- Raised on validation failure
  detect_contract_type -- Auto-detect contract type from parsed YAML
  CapabilityRegistry -- In-memory indexed catalog of all contracts
  CapabilityRegistryError -- Base exception for registry operations
  DuplicateCapabilityError -- Raised on duplicate registration
  CapabilityNotFoundError -- Raised when capability not in registry
  VersionConflictError -- Same name + same version (2.4.2)
  VersionRegressionError -- Older compatible version rejected (2.4.2)
  ContractMetadata -- Hot-cache metadata per contract
  RegistryHealth -- Health snapshot returned by health()
  ModuleLoader -- Contract lifecycle manager (scan, watch, register)
  ModuleLoaderError -- Base exception for loader operations
  ScanResult -- Frozen result of scan_directory()
  ContextBuilder -- 6-step execution context assembly (4.2.1)
  ContextBuilderConfig -- Configuration for ContextBuilder
  ContextBuildResult -- Full assembly result with metadata
  ContextBuilderError -- Base exception for context assembly
  ContextAssemblyError -- Fatal context assembly failure
  ContextBudget -- Token budget manager (4.2.2)
  ContextBudgetConfig -- Configuration for ContextBudget
  BudgetAllocation -- Soft allocation targets
  BudgetResult -- Budget application result
  CompressionLevel -- Compression level enum
  count_tokens -- Token counting utility (4.2.3)
  count_tokens_dict -- Token counting for dicts
  TOKEN_CEILING -- Hard token ceiling constant (128K)
  DEFAULT_RESPONSE_HEADROOM -- Reserved response headroom
  MIN_BELIEF_CONFIDENCE -- Belief confidence threshold (L3)
  MAX_HISTORY_TURNS_COMPRESSED -- History turn limit (L2)
  HOT_SECTION_NAMES -- HOT tier section names for budget
  WARM_SECTION_NAMES -- WARM tier section names for budget
  ALL_SECTION_NAMES -- All section names for budget
"""

from k1.fabric.core.context_budget import (
    ALL_SECTION_NAMES,
    DEFAULT_RESPONSE_HEADROOM,
    HOT_SECTION_NAMES,
    MAX_HISTORY_TURNS_COMPRESSED,
    MIN_BELIEF_CONFIDENCE,
    TOKEN_CEILING,
    WARM_SECTION_NAMES,
    BudgetAllocation,
    BudgetResult,
    CompressionLevel,
    ContextBudget,
    ContextBudgetConfig,
    count_tokens,
    count_tokens_dict,
)
from k1.fabric.core.context_builder import (
    ContextAssemblyError,
    ContextBuilder,
    ContextBuilderConfig,
    ContextBuilderError,
    ContextBuildResult,
)
from k1.fabric.core.contract_validator import (
    ContractValidationError,
    ContractValidator,
    detect_contract_type,
)
from k1.fabric.core.module_loader import ModuleLoader, ModuleLoaderError, ScanResult
from k1.fabric.core.registry import (
    CapabilityNotFoundError,
    CapabilityRegistry,
    CapabilityRegistryError,
    ContractMetadata,
    DuplicateCapabilityError,
    RegistryHealth,
    VersionConflictError,
    VersionRegressionError,
)

__all__ = [
    # --- Validation (M2) ---
    "ContractValidationError",
    "ContractValidator",
    "detect_contract_type",
    # --- Registry (M2) ---
    "CapabilityRegistry",
    "CapabilityRegistryError",
    "DuplicateCapabilityError",
    "CapabilityNotFoundError",
    "VersionConflictError",
    "VersionRegressionError",
    "ContractMetadata",
    "RegistryHealth",
    # --- ModuleLoader (M2) ---
    "ModuleLoader",
    "ModuleLoaderError",
    "ScanResult",
    # --- ContextBuilder (4.2.1) ---
    "ContextBuilder",
    "ContextBuilderConfig",
    "ContextBuildResult",
    "ContextBuilderError",
    "ContextAssemblyError",
    # --- ContextBudget (4.2.2 + 4.2.3) ---
    "ContextBudget",
    "ContextBudgetConfig",
    "BudgetAllocation",
    "BudgetResult",
    "CompressionLevel",
    "count_tokens",
    "count_tokens_dict",
    "TOKEN_CEILING",
    "DEFAULT_RESPONSE_HEADROOM",
    "MIN_BELIEF_CONFIDENCE",
    "MAX_HISTORY_TURNS_COMPRESSED",
    "HOT_SECTION_NAMES",
    "WARM_SECTION_NAMES",
    "ALL_SECTION_NAMES",
]
