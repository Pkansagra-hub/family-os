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
  CreatedAgentRecord -- Lifecycle metadata for created agents (4.5.6)
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
  AgentSpecValidator -- Agent spec validation (4.5.1)
  AgentSpecValidationResult -- Validation result dataclass (4.5.1)
  AgentSpecValidationError -- Validation exception (4.5.1)
  AGENT_NAME_PATTERN -- Regex for agent name validation
  ALLOWED_CONTEXT_SECTIONS -- Valid required_context sections
  AgentComposer -- Builder pattern agent composition (4.5.4)
  AgentCompositionError -- Composition build failure (4.5.4)
  BuildAgentHandler -- 8-step agent creation handler (4.5.2)
  BuildAgentError -- Unrecoverable build error (4.5.2)
  BUILD_AGENT_CAPABILITY_NAME -- Tool capability name constant
  BUILD_AGENT_PROVIDER_ID -- Provider ID for build_agent handler
  DEFAULT_LLM_BUDGET_TOKENS -- Default LLM token budget (8192)
  DEFAULT_MAX_TOOL_CALLS -- Default max tool calls (10)
  DEFAULT_MAX_EXECUTION_TIME_MS -- Default max execution time (30000)
  DEFAULT_SAFETY_BAND -- Default safety band (GREEN)
  DiscoverCapabilitiesHandler -- Discover capabilities tool handler (4.5.3)
  FindPromptsHandler -- Find prompts tool handler (4.5.3)
  DiscoveryToolError -- Discovery tool input validation error (4.5.3)
  DISCOVER_CAPABILITIES_NAME -- Tool capability name constant (4.5.3)
  DISCOVER_CAPABILITIES_PROVIDER_ID -- Provider ID constant (4.5.3)
  FIND_PROMPTS_NAME -- Tool capability name constant (4.5.3)
  FIND_PROMPTS_PROVIDER_ID -- Provider ID constant (4.5.3)
  DEFAULT_DISCOVER_TOP_K -- Default top_k for discover (4.5.3)
  DEFAULT_FIND_PROMPTS_TOP_K -- Default top_k for find_prompts (4.5.3)
"""

from k1.fabric.core.agent_builder import (
    AGENT_NAME_PATTERN,
    ALLOWED_CONTEXT_SECTIONS,
    BUILD_AGENT_CAPABILITY_NAME,
    BUILD_AGENT_PROVIDER_ID,
    DEFAULT_LLM_BUDGET_TOKENS,
    DEFAULT_MAX_EXECUTION_TIME_MS,
    DEFAULT_MAX_TOOL_CALLS,
    DEFAULT_SAFETY_BAND,
    AgentComposer,
    AgentCompositionError,
    AgentSpecValidationError,
    AgentSpecValidationResult,
    AgentSpecValidator,
    BuildAgentError,
    BuildAgentHandler,
)
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
    clear_schema_cache,
    detect_contract_type,
)
from k1.fabric.core.discovery_tools import (
    DEFAULT_DISCOVER_TOP_K,
    DEFAULT_FIND_PROMPTS_TOP_K,
    DISCOVER_CAPABILITIES_NAME,
    DISCOVER_CAPABILITIES_PROVIDER_ID,
    FIND_PROMPTS_NAME,
    FIND_PROMPTS_PROVIDER_ID,
    DiscoverCapabilitiesHandler,
    DiscoveryToolError,
    FindPromptsHandler,
)
from k1.fabric.core.module_loader import ModuleLoader, ModuleLoaderError, ScanResult
from k1.fabric.core.registry import (
    CapabilityNotFoundError,
    CapabilityRegistry,
    CapabilityRegistryError,
    ContractMetadata,
    CreatedAgentRecord,
    DuplicateCapabilityError,
    RegistryHealth,
    VersionConflictError,
    VersionRegressionError,
)

__all__ = [
    # --- Validation (M2) ---
    "ContractValidationError",
    "ContractValidator",
    "clear_schema_cache",
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
    # --- CreatedAgentRecord (4.5.6) ---
    "CreatedAgentRecord",
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
    # --- AgentSpecValidator (4.5.1) ---
    "AgentSpecValidator",
    "AgentSpecValidationResult",
    "AgentSpecValidationError",
    "AGENT_NAME_PATTERN",
    "ALLOWED_CONTEXT_SECTIONS",
    # --- AgentComposer (4.5.4) ---
    "AgentComposer",
    "AgentCompositionError",
    # --- BuildAgentHandler (4.5.2) ---
    "BuildAgentHandler",
    "BuildAgentError",
    "BUILD_AGENT_CAPABILITY_NAME",
    "BUILD_AGENT_PROVIDER_ID",
    "DEFAULT_LLM_BUDGET_TOKENS",
    "DEFAULT_MAX_TOOL_CALLS",
    "DEFAULT_MAX_EXECUTION_TIME_MS",
    "DEFAULT_SAFETY_BAND",
    # --- Discovery Tools (4.5.3) ---
    "DiscoverCapabilitiesHandler",
    "FindPromptsHandler",
    "DiscoveryToolError",
    "DISCOVER_CAPABILITIES_NAME",
    "DISCOVER_CAPABILITIES_PROVIDER_ID",
    "FIND_PROMPTS_NAME",
    "FIND_PROMPTS_PROVIDER_ID",
    "DEFAULT_DISCOVER_TOP_K",
    "DEFAULT_FIND_PROMPTS_TOP_K",
]
