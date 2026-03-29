"""
k1.fabric.core.agent_builder -- Agent Spec Validation and Composition (Epic 4.5).

AgentSpecValidator (4.5.1):
  Validates programmatic agent specs before contract creation.
  7 validation rules, stateless, pure functions over inputs.

BuildAgentHandler (4.5.2):
  Handler for tool.write.build_agent MCP Tool. 8-step execute()
  orchestrates dynamic agent creation from discovered capabilities.
  Orchestrator-executed DAG step (NOT a Planner tool, PLAN-06).

AgentComposer (4.5.4):
  Builder pattern for composing agent CapabilityContract instances.
  Validates incrementally: add_tool checks Registry.contains(),
  set_prompt checks IPromptSystemPort.resolve(). Terminal build()
  runs cross-field validation and returns frozen CapabilityContract.
  Factory from_discovery_result() auto-selects tools from ScoredCapability.

Design:
  - Constructor injection: CapabilityRegistry (2.2.1), IPromptSystemPort (5.1.5)
  - Thread-safe: stateless validator and handler, no mutable state
  - Builder instances are per-call (no shared mutable state)
  - Returns AgentSpecValidationResult (frozen dataclass) or raises
    AgentSpecValidationError
  - BuildAgentHandler uses Protocol-based dependency injection for
    AgentComposer (4.5.4), SecurityContext (4.5.5), EventEmitter (4.5.7),
    and extended CapabilityRegistry (4.5.6)

Consumers:
  - BuildAgentHandler (4.5.2) step 2 uses AgentSpecValidator
  - BuildAgentHandler (4.5.2) step 4 uses AgentComposer
  - MCPProvider (3.3.1) handler_registry registers BuildAgentHandler

References:
  - fabric-implementation-plan.md Epic 4.5, Issues 4.5.1, 4.5.2, 4.5.4
  - meta-agent-creation-integration-proposal.md PART 1 (Option A)
  - k1/contracts/tools/build_agent.yaml (MCP tool contract)

Exports:
  AgentSpecValidator
  AgentSpecValidationResult
  AgentSpecValidationError
  AgentComposer
  AgentCompositionError
  BuildAgentHandler
  BuildAgentError
  BUILD_AGENT_CAPABILITY_NAME
  BUILD_AGENT_PROVIDER_ID
  DEFAULT_LLM_BUDGET_TOKENS
  DEFAULT_MAX_TOOL_CALLS
  DEFAULT_MAX_EXECUTION_TIME_MS
  DEFAULT_SAFETY_BAND
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from k1.fabric.types import (
    AgentContract,
    CapabilityContract,
    CapabilityRequest,
    CapabilityResult,
    SafetyBand,
    ScoredCapability,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Valid name pattern: agent.execute.<lowercase_alpha_start><lowercase_alphanum_underscore>
AGENT_NAME_PATTERN = re.compile(r"^agent\.execute\.[a-z][a-z0-9_]+$")

# Allowed required_context section names (from SessionState)
ALLOWED_CONTEXT_SECTIONS = frozenset(
    {
        "beliefs_active",
        "interaction_history",
        "task_context",
        "rhythm_state",
        "active_plans",
        "pending_clarifications",
    }
)

# Budget range constraints
MIN_LLM_BUDGET_TOKENS = 512
MAX_LLM_BUDGET_TOKENS = 32768
MIN_TOOL_CALLS = 1
MAX_TOOL_CALLS = 50
MIN_EXECUTION_TIME_MS = 1000
MAX_EXECUTION_TIME_MS = 60000

# Valid SafetyBand values (string form)
VALID_SAFETY_BANDS = frozenset({band.value for band in SafetyBand})


# ---------------------------------------------------------------------------
# Port protocols (structural subtyping to avoid hard imports)
# ---------------------------------------------------------------------------


@runtime_checkable
class RegistryLike(Protocol):
    """Minimal protocol for registry dependency (2.2.1 / 2.2.3)."""

    def contains(self, name: str) -> bool:
        """Check if a capability name is registered."""
        ...  # pragma: no cover


@runtime_checkable
class PromptSystemLike(Protocol):
    """Minimal protocol for prompt system dependency (5.1.5)."""

    def resolve(self, template_name: str) -> Optional[Any]:
        """Look up a prompt template by name. Returns None if unknown."""
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# 4.5.1 -- AgentSpecValidationResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentSpecValidationResult:
    """
    Result of agent spec validation.

    Attributes:
        valid: True if spec passes all validation rules.
        errors: List of validation error messages (empty if valid).
        warnings: List of non-fatal warning messages.
    """

    valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 4.5.1 -- AgentSpecValidationError
# ---------------------------------------------------------------------------


class AgentSpecValidationError(Exception):
    """Raised when an agent spec fails validation (validate_or_raise)."""

    def __init__(self, errors: List[str]) -> None:
        self.errors = errors
        super().__init__(
            f"Agent spec validation failed with {len(errors)} error(s): " f"{'; '.join(errors)}"
        )


# ---------------------------------------------------------------------------
# 4.5.1 -- AgentSpecValidator
# ---------------------------------------------------------------------------


class AgentSpecValidator:
    """
    Validates programmatic agent specs before contract creation.

    7 validation rules:
      1. Name follows ``agent.execute.<identifier>`` pattern
      2. tools_granted[] all exist in registry
      3. required_context sections from allowed set
      4. prompt_template resolves via IPromptSystemPort (if specified)
      5. Domain tags non-empty and no duplicates
      6. safety_band is a valid SafetyBand enum value
      7. Budget ranges within constraints

    Constructor injection:
      registry: CapabilityRegistry (2.2.1) -- for tools_granted validation
      prompt_system: IPromptSystemPort (5.1.5) -- for prompt_template validation

    Thread-safe: stateless validator, no mutable state. All methods are
    pure functions over inputs + registry lookups + prompt resolution.
    """

    def __init__(
        self,
        registry: RegistryLike,
        prompt_system: Optional[PromptSystemLike] = None,
    ) -> None:
        self._registry = registry
        self._prompt_system = prompt_system

    # -- Public API --------------------------------------------------------

    def validate(self, spec: Dict[str, Any]) -> AgentSpecValidationResult:
        """
        Validate an agent spec dict.

        Args:
            spec: Agent specification dictionary with keys:
                - name (str): Agent capability name
                - tools_granted (list[str]): Tools the agent may use
                - required_context (list[str]): SessionState sections needed
                - prompt_template (str, optional): Prompt template name
                - domain (list[str]): Domain tags
                - safety_band (str): Safety band classification
                - llm_budget_tokens (int, optional): LLM token budget
                - max_tool_calls (int, optional): Max tool invocations
                - max_execution_time_ms (int, optional): Max execution time

        Returns:
            AgentSpecValidationResult with valid flag, errors, and warnings.
        """
        errors: List[str] = []
        warnings: List[str] = []

        # Rule 1: Name pattern
        self._validate_name(spec, errors)

        # Rule 2: Tools granted exist in registry
        self._validate_tools_granted(spec, errors, warnings)

        # Rule 3: Required context sections
        self._validate_required_context(spec, errors)

        # Rule 4: Prompt template resolution
        self._validate_prompt_template(spec, errors, warnings)

        # Rule 5: Domain tags
        self._validate_domain(spec, errors)

        # Rule 6: Safety band
        self._validate_safety_band(spec, errors)

        # Rule 7: Budget ranges
        self._validate_budgets(spec, errors, warnings)

        valid = len(errors) == 0
        return AgentSpecValidationResult(
            valid=valid,
            errors=errors,
            warnings=warnings,
        )

    def validate_or_raise(self, spec: Dict[str, Any]) -> None:
        """
        Validate an agent spec dict, raising on failure.

        Args:
            spec: Agent specification dictionary (same as validate()).

        Raises:
            AgentSpecValidationError: If any validation rule fails.
        """
        result = self.validate(spec)
        if not result.valid:
            raise AgentSpecValidationError(result.errors)

    # -- Validation rules (private) ----------------------------------------

    def _validate_name(self, spec: Dict[str, Any], errors: List[str]) -> None:
        """Rule 1: Name follows agent.execute.<identifier> pattern."""
        name = spec.get("name")
        if name is None:
            errors.append("Missing required field: 'name'")
            return
        if not isinstance(name, str):
            errors.append(f"'name' must be a string, got {type(name).__name__}")
            return
        if not AGENT_NAME_PATTERN.match(name):
            errors.append(
                f"'name' must match pattern agent.execute.<identifier> "
                f"(lowercase alphanumeric + underscore, starting with letter), "
                f"got '{name}'"
            )

    def _validate_tools_granted(
        self,
        spec: Dict[str, Any],
        errors: List[str],
        warnings: List[str],
    ) -> None:
        """Rule 2: All tools_granted exist in registry."""
        tools = spec.get("tools_granted")
        if tools is None:
            # tools_granted is optional -- agent may have no tools
            warnings.append("No 'tools_granted' specified; agent will have no tools")
            return
        if not isinstance(tools, list):
            errors.append(f"'tools_granted' must be a list, got {type(tools).__name__}")
            return

        unknown_tools: List[str] = []
        for tool in tools:
            if not isinstance(tool, str):
                errors.append(
                    f"Each tool in 'tools_granted' must be a string, "
                    f"got {type(tool).__name__}: {tool!r}"
                )
                continue
            if not self._registry.contains(tool):
                unknown_tools.append(tool)

        if unknown_tools:
            errors.append(
                f"Unknown tools in 'tools_granted' (not in registry): " f"{unknown_tools}"
            )

    def _validate_required_context(
        self,
        spec: Dict[str, Any],
        errors: List[str],
    ) -> None:
        """Rule 3: Required context sections from allowed set."""
        sections = spec.get("required_context")
        if sections is None:
            # No required context is valid (some agents need no state)
            return
        if not isinstance(sections, list):
            errors.append(f"'required_context' must be a list, got {type(sections).__name__}")
            return

        invalid_sections: List[str] = []
        for section in sections:
            if not isinstance(section, str):
                errors.append(
                    f"Each section in 'required_context' must be a string, "
                    f"got {type(section).__name__}: {section!r}"
                )
                continue
            if section not in ALLOWED_CONTEXT_SECTIONS:
                invalid_sections.append(section)

        if invalid_sections:
            errors.append(
                f"Invalid required_context sections: {invalid_sections}. "
                f"Allowed: {sorted(ALLOWED_CONTEXT_SECTIONS)}"
            )

    def _validate_prompt_template(
        self,
        spec: Dict[str, Any],
        errors: List[str],
        warnings: List[str],
    ) -> None:
        """Rule 4: Prompt template resolves via IPromptSystemPort."""
        template = spec.get("prompt_template")
        if template is None or template == "":
            # Prompt template is optional
            return
        if not isinstance(template, str):
            errors.append(f"'prompt_template' must be a string, got {type(template).__name__}")
            return

        if self._prompt_system is None:
            warnings.append(
                f"Cannot validate prompt_template '{template}': " f"no IPromptSystemPort configured"
            )
            return

        resolved = self._prompt_system.resolve(template)
        if resolved is None:
            errors.append(f"Prompt template '{template}' not found via IPromptSystemPort")

    def _validate_domain(self, spec: Dict[str, Any], errors: List[str]) -> None:
        """Rule 5: Domain tags non-empty and no duplicates."""
        domain = spec.get("domain")
        if domain is None:
            errors.append("Missing required field: 'domain'")
            return
        if not isinstance(domain, list):
            errors.append(f"'domain' must be a list, got {type(domain).__name__}")
            return
        if len(domain) == 0:
            errors.append("'domain' must contain at least one tag")
            return

        # Check for non-string entries
        for tag in domain:
            if not isinstance(tag, str):
                errors.append(
                    f"Each domain tag must be a string, " f"got {type(tag).__name__}: {tag!r}"
                )
                return

        # Check for duplicates
        seen = set()
        duplicates = []
        for tag in domain:
            if tag in seen:
                duplicates.append(tag)
            seen.add(tag)
        if duplicates:
            errors.append(f"Duplicate domain tags: {duplicates}")

    def _validate_safety_band(
        self,
        spec: Dict[str, Any],
        errors: List[str],
    ) -> None:
        """Rule 6: Safety band is a valid SafetyBand enum value."""
        band = spec.get("safety_band")
        if band is None:
            # Also accept safety_band_min as alias
            band = spec.get("safety_band_min")
        if band is None:
            # Default to GREEN if not specified -- not an error
            return
        if not isinstance(band, str):
            errors.append(f"'safety_band' must be a string, got {type(band).__name__}")
            return
        if band not in VALID_SAFETY_BANDS:
            errors.append(
                f"Invalid safety_band '{band}'. " f"Valid values: {sorted(VALID_SAFETY_BANDS)}"
            )

    def _validate_budgets(
        self,
        spec: Dict[str, Any],
        errors: List[str],
        warnings: List[str],
    ) -> None:
        """Rule 7: Budget ranges within constraints."""
        # llm_budget_tokens
        tokens = spec.get("llm_budget_tokens")
        if tokens is not None:
            if not isinstance(tokens, int):
                errors.append(
                    f"'llm_budget_tokens' must be an int, " f"got {type(tokens).__name__}"
                )
            elif tokens < MIN_LLM_BUDGET_TOKENS or tokens > MAX_LLM_BUDGET_TOKENS:
                errors.append(
                    f"'llm_budget_tokens' must be in range "
                    f"[{MIN_LLM_BUDGET_TOKENS}..{MAX_LLM_BUDGET_TOKENS}], "
                    f"got {tokens}"
                )

        # max_tool_calls
        calls = spec.get("max_tool_calls")
        if calls is not None:
            if not isinstance(calls, int):
                errors.append(f"'max_tool_calls' must be an int, " f"got {type(calls).__name__}")
            elif calls < MIN_TOOL_CALLS or calls > MAX_TOOL_CALLS:
                errors.append(
                    f"'max_tool_calls' must be in range "
                    f"[{MIN_TOOL_CALLS}..{MAX_TOOL_CALLS}], got {calls}"
                )

        # max_execution_time_ms
        exec_time = spec.get("max_execution_time_ms")
        if exec_time is not None:
            if not isinstance(exec_time, int):
                errors.append(
                    f"'max_execution_time_ms' must be an int, " f"got {type(exec_time).__name__}"
                )
            elif exec_time < MIN_EXECUTION_TIME_MS or exec_time > MAX_EXECUTION_TIME_MS:
                errors.append(
                    f"'max_execution_time_ms' must be in range "
                    f"[{MIN_EXECUTION_TIME_MS}..{MAX_EXECUTION_TIME_MS}], "
                    f"got {exec_time}"
                )

    # -- Repr --------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"AgentSpecValidator("
            f"registry={self._registry!r}, "
            f"prompt_system={self._prompt_system!r})"
        )


# ---------------------------------------------------------------------------
# 4.5.2 -- Build agent constants
# ---------------------------------------------------------------------------

DEFAULT_LLM_BUDGET_TOKENS = 8192
DEFAULT_MAX_TOOL_CALLS = 10
DEFAULT_MAX_EXECUTION_TIME_MS = 30000
DEFAULT_SAFETY_BAND = "GREEN"

BUILD_AGENT_CAPABILITY_NAME = "tool.write.build_agent"
BUILD_AGENT_PROVIDER_ID = "build_agent_handler"


# ---------------------------------------------------------------------------
# 4.5.2 -- Protocols for BuildAgentHandler dependencies
# ---------------------------------------------------------------------------


class AgentBuilderInstanceLike(Protocol):
    """
    Protocol for the builder returned by compose_agent (4.5.4).

    Builder pattern: each setter returns self for chaining.
    Terminal method build() returns a CapabilityContract.
    """

    def add_tool(self, tool_name: str) -> AgentBuilderInstanceLike: ...

    def set_prompt(self, template_name: str) -> AgentBuilderInstanceLike: ...

    def set_context(
        self, required: List[str], optional: Optional[List[str]] = None
    ) -> AgentBuilderInstanceLike: ...

    def set_budget(
        self,
        llm_tokens: int = 8192,
        max_tool_calls: int = 10,
        max_execution_ms: int = 30000,
    ) -> AgentBuilderInstanceLike: ...

    def set_safety_band(self, band: str = "GREEN") -> AgentBuilderInstanceLike: ...

    def set_lifecycle(
        self, ephemeral: bool = True, session_scoped: bool = True
    ) -> AgentBuilderInstanceLike: ...

    def build(self) -> Any: ...


@runtime_checkable
class ComposerLike(Protocol):
    """Protocol for agent composition factory (4.5.4)."""

    def compose_agent(
        self, name: str, description: str, domain: List[str]
    ) -> AgentBuilderInstanceLike: ...


@runtime_checkable
class SecurityGateLike(Protocol):
    """
    Protocol for meta-operation security validation (4.5.5).

    Returns an object with ``allowed: bool`` and ``reasons: list[str]``.
    Satisfied by SecurityContext.validate_meta_operation() (4.5.5).
    """

    def validate_meta_operation(self, request_band: str, agent_spec: Dict[str, Any]) -> Any: ...


@runtime_checkable
class RegistryForBuildLike(Protocol):
    """
    Extended registry protocol for build_agent (2.2.1 + 4.5.6).

    Extends RegistryLike with register() and register_created_agent().
    Satisfied by CapabilityRegistry after 4.5.6 extends it.
    """

    def contains(self, name: str) -> bool: ...

    def register(self, contract: Any, *, skip_validation: bool = False) -> None: ...

    def register_created_agent(
        self,
        contract: Any,
        ephemeral: bool,
        created_by: str,
        session_scoped: bool,
    ) -> None: ...


@runtime_checkable
class EmitterForBuildLike(Protocol):
    """
    Protocol for event emission in build_agent (4.5.7).

    Satisfied by EventEmitter after 4.5.7 extends it.
    """

    def emit_agent_created(
        self,
        agent_name: str,
        created_by: str,
        tools_granted: List[str],
        domain: List[str],
        prompt_template: str,
        ephemeral: bool,
        session_id: str,
        trace_id: str,
    ) -> None: ...


# ---------------------------------------------------------------------------
# 4.5.4 -- AgentCompositionError
# ---------------------------------------------------------------------------


class AgentCompositionError(Exception):
    """
    Build-time validation failure during agent composition (4.5.4).

    Raised by AgentComposer.build() when cross-field validation fails
    (missing required fields, no tools added, incompatible tool+band
    combinations).

    Distinct from:
      - AgentSpecValidationError: semantic rule violations (4.5.1)
      - BuildAgentError: input parsing failures (4.5.2)
    """

    def __init__(self, errors: List[str]) -> None:
        self.errors = errors
        super().__init__(
            f"Agent composition failed with {len(errors)} error(s): " f"{'; '.join(errors)}"
        )


# ---------------------------------------------------------------------------
# 4.5.4 -- AgentComposer (builder pattern)
# ---------------------------------------------------------------------------

# Safety band ordering for max() computation in from_discovery_result
_SAFETY_BAND_ORDER: Dict[str, int] = {
    SafetyBand.GREEN.value: 0,
    SafetyBand.AMBER.value: 1,
    SafetyBand.RED.value: 2,
    SafetyBand.CRISIS.value: 3,
}


class AgentComposer:
    """
    Builder pattern for composing agent CapabilityContract instances (4.5.4).

    Validates incrementally: add_tool() checks Registry.contains(),
    set_prompt() checks IPromptSystemPort.resolve(). Terminal build()
    runs cross-field validation and returns frozen CapabilityContract
    with provider_type=AGENT.

    Factory method from_discovery_result() auto-selects tools from
    ScoredCapability list, auto-unions domains, auto-computes
    safety_band as max() of individual tool bands.

    Constructor injection:
      registry: CapabilityRegistry (2.2.1) for tool existence checks
      prompt_system: IPromptSystemPort (5.1.5) for prompt resolution

    Thread safety: builder instances are per-call, no shared mutable state.

    Satisfies:
      ComposerLike -- compose_agent(name, description, domain)
      AgentBuilderInstanceLike -- add_tool, set_prompt, set_context,
        set_budget, set_safety_band, set_lifecycle, build

    Consumed by:
      BuildAgentHandler (4.5.2) step 4 via ComposerLike protocol.

    References:
      - fabric-implementation-plan.md Issue 4.5.4
      - meta-agent-creation-integration-proposal.md (auto-union of required_context)
    """

    __slots__ = (
        "_registry",
        "_prompt_system",
        "_name",
        "_description",
        "_domain",
        "_tools",
        "_prompt_template",
        "_context_required",
        "_context_optional",
        "_llm_tokens",
        "_max_tool_calls",
        "_max_execution_ms",
        "_safety_band",
        "_ephemeral",
        "_session_scoped",
        "_initialized",
    )

    def __init__(
        self,
        registry: RegistryLike,
        prompt_system: Optional[PromptSystemLike] = None,
    ) -> None:
        """
        Args:
            registry: CapabilityRegistry (2.2.1) for tool existence validation.
            prompt_system: IPromptSystemPort (5.1.5) for prompt template resolution.
                Optional -- if None, set_prompt() skips resolution validation.
        """
        self._registry = registry
        self._prompt_system = prompt_system

        # Builder state -- initialized by compose_agent()
        self._name: str = ""
        self._description: str = ""
        self._domain: List[str] = []
        self._tools: List[str] = []
        self._prompt_template: str = ""
        self._context_required: List[str] = []
        self._context_optional: Optional[List[str]] = None
        self._llm_tokens: int = DEFAULT_LLM_BUDGET_TOKENS
        self._max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS
        self._max_execution_ms: int = DEFAULT_MAX_EXECUTION_TIME_MS
        self._safety_band: str = DEFAULT_SAFETY_BAND
        self._ephemeral: bool = True
        self._session_scoped: bool = True
        self._initialized: bool = False

    # -- Static Factory (ComposerLike) ------------------------------------

    def compose_agent(
        self,
        name: str,
        description: str,
        domain: List[str],
    ) -> "AgentComposer":
        """
        Initialize a new builder instance for agent composition.

        Satisfies ComposerLike protocol. Returns a new AgentComposer
        with the same registry/prompt_system deps but fresh builder state.

        Args:
            name: Agent capability name (e.g., "agent.execute.summarizer").
            description: Human-readable description of the agent.
            domain: Domain tags (e.g., ["memory", "recall"]).

        Returns:
            New AgentComposer instance with builder state initialized.
        """
        builder = AgentComposer(
            registry=self._registry,
            prompt_system=self._prompt_system,
        )
        builder._name = name
        builder._description = description
        builder._domain = list(domain)
        builder._initialized = True
        return builder

    # -- Builder Methods (AgentBuilderInstanceLike) ------------------------

    def add_tool(self, tool_name: str) -> "AgentComposer":
        """
        Add a tool to the agent's granted tool list.

        Validates tool existence via Registry.contains() (2.2.3).

        Args:
            tool_name: Capability name of the tool to grant.

        Returns:
            self for chaining.

        Raises:
            ValueError: If tool_name is not registered in the registry.
        """
        if not self._registry.contains(tool_name):
            raise ValueError(f"Tool not found in registry: {tool_name!r}")
        self._tools.append(tool_name)
        return self

    def set_prompt(self, template_name: str) -> "AgentComposer":
        """
        Set the prompt template for the agent.

        Validates template existence via IPromptSystemPort.resolve() (5.1.5)
        if prompt_system is available.

        Args:
            template_name: Name of the prompt template to use.

        Returns:
            self for chaining.

        Raises:
            ValueError: If prompt_system is set and template cannot be resolved.
        """
        if self._prompt_system is not None:
            result = self._prompt_system.resolve(template_name)
            if result is None:
                raise ValueError(f"Prompt template not found: {template_name!r}")
        self._prompt_template = template_name
        return self

    def set_context(
        self,
        required: List[str],
        optional: Optional[List[str]] = None,
    ) -> "AgentComposer":
        """
        Set context requirements (SessionState sections).

        Args:
            required: Required context section names.
            optional: Optional context section names.

        Returns:
            self for chaining.
        """
        self._context_required = list(required)
        self._context_optional = list(optional) if optional else None
        return self

    def set_budget(
        self,
        llm_tokens: int = DEFAULT_LLM_BUDGET_TOKENS,
        max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
        max_execution_ms: int = DEFAULT_MAX_EXECUTION_TIME_MS,
    ) -> "AgentComposer":
        """
        Set budget constraints for the agent.

        Args:
            llm_tokens: LLM token budget.
            max_tool_calls: Maximum tool invocations.
            max_execution_ms: Maximum execution time in milliseconds.

        Returns:
            self for chaining.
        """
        self._llm_tokens = llm_tokens
        self._max_tool_calls = max_tool_calls
        self._max_execution_ms = max_execution_ms
        return self

    def set_safety_band(self, band: str = DEFAULT_SAFETY_BAND) -> "AgentComposer":
        """
        Set the minimum safety band for the agent.

        Args:
            band: Safety band string (GREEN, AMBER, RED, CRISIS).

        Returns:
            self for chaining.
        """
        self._safety_band = band
        return self

    def set_lifecycle(
        self,
        ephemeral: bool = True,
        session_scoped: bool = True,
    ) -> "AgentComposer":
        """
        Set lifecycle attributes for the agent.

        Args:
            ephemeral: Whether the agent is ephemeral (auto-cleanup).
            session_scoped: Whether the agent is scoped to a session.

        Returns:
            self for chaining.
        """
        self._ephemeral = ephemeral
        self._session_scoped = session_scoped
        return self

    # -- Terminal Method ---------------------------------------------------

    def build(self) -> CapabilityContract:
        """
        Build the agent CapabilityContract (terminal operation).

        Runs cross-field validation before constructing the frozen
        CapabilityContract with provider_type=AGENT.

        Returns:
            Frozen CapabilityContract (1.3.3) with provider_type=AGENT.

        Raises:
            AgentCompositionError: If cross-field validation fails.
        """
        errors: List[str] = []

        if not self._name:
            errors.append("Agent name is required")
        if not self._description:
            errors.append("Agent description is required")
        if not self._domain:
            errors.append("At least one domain tag is required")
        if not self._tools:
            errors.append("At least one tool must be added via add_tool()")

        if errors:
            raise AgentCompositionError(errors)

        return AgentContract(
            name=self._name,
            version="1.0.0",
            domain=self._domain,
            description=self._description,
            required_context=self._context_required,
            optional_context=self._context_optional or [],
            output={"type": "object"},
            provider_type="AGENT",
            safety_band_min=self._safety_band,
            prompt_template=self._prompt_template,
            tools_granted=list(self._tools),
            llm_budget_tokens=self._llm_tokens,
            max_tool_calls=self._max_tool_calls,
            max_execution_time_ms=self._max_execution_ms,
            ephemeral=self._ephemeral,
            session_scoped=self._session_scoped,
        )

    # -- Factory Method ----------------------------------------------------

    @classmethod
    def from_discovery_result(
        cls,
        capabilities: List[ScoredCapability],
        intent: str,
        prompt_template: str,
        *,
        registry: RegistryLike,
        prompt_system: Optional[PromptSystemLike] = None,
    ) -> "AgentComposer":
        """
        Auto-compose an agent from discovery results.

        Extracts tool names from ScoredCapability.contract.name, auto-unions
        domains across all capability contracts, and computes safety_band
        as max() of individual tool safety bands.

        Args:
            capabilities: List of ScoredCapability from discover_capabilities.
            intent: Description/intent string for the agent.
            prompt_template: Prompt template name to set.
            registry: CapabilityRegistry for the new composer instance.
            prompt_system: Optional IPromptSystemPort for prompt validation.

        Returns:
            AgentComposer with tools, domains, and safety_band pre-configured.
            Caller can further customize before calling build().
        """
        composer = cls(registry=registry, prompt_system=prompt_system)

        # Derive agent name from intent (sanitized)
        sanitized = re.sub(r"[^a-z0-9_]", "_", intent.lower().strip())
        sanitized = re.sub(r"_+", "_", sanitized).strip("_")
        if not sanitized:
            sanitized = "composed_agent"
        agent_name = f"agent.execute.{sanitized}"

        # Collect tools, domains, and compute max safety band
        tools: List[str] = []
        all_domains: List[str] = []
        all_context: List[str] = []
        max_band_order = 0

        for sc in capabilities:
            if sc.contract is None:
                continue
            tools.append(sc.contract.name)
            all_domains.extend(sc.contract.domain)
            all_context.extend(sc.contract.required_context)
            band_order = _SAFETY_BAND_ORDER.get(sc.contract.safety_band_min, 0)
            if band_order > max_band_order:
                max_band_order = band_order

        # Deduplicate domains and context preserving order
        seen_domains: set[str] = set()
        unique_domains: List[str] = []
        for d in all_domains:
            if d not in seen_domains:
                seen_domains.add(d)
                unique_domains.append(d)

        seen_context: set[str] = set()
        unique_context: List[str] = []
        for c in all_context:
            if c not in seen_context:
                seen_context.add(c)
                unique_context.append(c)

        # Reverse-lookup max safety band string
        max_band = DEFAULT_SAFETY_BAND
        for band_str, order in _SAFETY_BAND_ORDER.items():
            if order == max_band_order:
                max_band = band_str
                break

        # Initialize builder state
        composer._name = agent_name
        composer._description = intent
        composer._domain = unique_domains if unique_domains else ["general"]
        composer._tools = tools
        composer._prompt_template = prompt_template
        composer._context_required = unique_context
        composer._safety_band = max_band
        composer._initialized = True

        return composer

    # -- Repr --------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"AgentComposer("
            f"name={self._name!r}, "
            f"tools={len(self._tools)}, "
            f"initialized={self._initialized})"
        )


# ---------------------------------------------------------------------------
# 4.5.2 -- BuildAgentError
# ---------------------------------------------------------------------------


class BuildAgentError(Exception):
    """
    Unrecoverable error during agent build process (4.5.2).

    Raised by BuildAgentHandler Step 1 (input parsing) when required
    inputs are missing or have invalid types. Distinct from
    AgentSpecValidationError (semantic rule violations in Step 2).
    """

    def __init__(self, errors: List[str]) -> None:
        self.errors = errors
        super().__init__(f"Agent build failed with {len(errors)} error(s): " f"{'; '.join(errors)}")


# ---------------------------------------------------------------------------
# 4.5.2 -- BuildAgentHandler
# ---------------------------------------------------------------------------


class BuildAgentHandler:
    """
    Handler for tool.write.build_agent MCP Tool (4.5.2).

    8-step execute() orchestrates dynamic agent creation:
      1. Parse+validate inputs against contract schema
      2. AgentSpecValidator.validate_or_raise(spec) (4.5.1)
      3. SecurityContext.validate_meta_operation(band, spec) (4.5.5)
      4. AgentComposer.compose_agent()...build() -> contract (4.5.4)
      5. Registry.register(contract, skip_validation=False) (2.2.2)
      6. Registry.register_created_agent(contract, ...) (4.5.6)
      7. EventEmitter.emit_agent_created(...) (4.5.7)
      8. Return CapabilityResult.success() or failure()

    Constructor injection (5 deps):
      validator: AgentSpecValidator (4.5.1)
      composer:  ComposerLike (4.5.4)
      registry:  RegistryForBuildLike (2.2.1 + 4.5.6)
      security:  SecurityGateLike (4.5.5)
      emitter:   EmitterForBuildLike (4.5.7)

    Registered in MCPProvider (3.3.1) handler_registry as local handler
    for ``tool.write.build_agent``. Resolved via standard Resolver
    pipeline (3.1.5) -- appears as normal AMBER-band MCP capability.

    NOTE: Orchestrator-executed DAG step, NOT a Planner tool (PLAN-06).

    Thread safety: stateless handler, safe for concurrent calls.
    All mutable state is in the injected dependencies.
    """

    __slots__ = ("_validator", "_composer", "_registry", "_security", "_emitter")

    def __init__(
        self,
        validator: AgentSpecValidator,
        composer: ComposerLike,
        registry: RegistryForBuildLike,
        security: SecurityGateLike,
        emitter: EmitterForBuildLike,
    ) -> None:
        """
        Args:
            validator: AgentSpecValidator (4.5.1) for semantic spec validation.
            composer: AgentComposer (4.5.4) for building CapabilityContract.
            registry: CapabilityRegistry (2.2.1 + 4.5.6) for registration.
            security: SecurityContext (4.5.5) for meta-operation policy.
            emitter: EventEmitter (4.5.7) for lifecycle event emission.
        """
        self._validator = validator
        self._composer = composer
        self._registry = registry
        self._security = security
        self._emitter = emitter

    # -- Public API --------------------------------------------------------

    def execute(self, request: CapabilityRequest) -> CapabilityResult:
        """
        Execute the build_agent tool (8-step pipeline).

        Args:
            request: CapabilityRequest with params containing agent spec inputs.
                Required params: agent_name, description, tools_granted,
                    prompt_template, domain.
                Optional params: required_context, llm_budget_tokens,
                    safety_band_min, max_tool_calls, max_execution_time_ms,
                    ephemeral, session_scoped.

        Returns:
            CapabilityResult with:
              - success: data={agent_name, status:"registered", errors:[]}
              - failure: error with code and message
        """
        trace_id = request.trace_id
        request_id = request.request_id
        session_id = request.session_id
        safety_band = request.safety_band
        params = request.params
        start_ms = _now_ms()

        try:
            # Step 1: Parse + validate inputs (structural)
            spec = self._parse_inputs(params)

            # Step 2: Semantic validation (7 rules)
            self._validator.validate_or_raise(spec)

            # Step 3: Security gate (5 hard gates)
            security_result = self._security.validate_meta_operation(safety_band, spec)
            if not getattr(security_result, "allowed", False):
                reasons = getattr(security_result, "reasons", [])
                return CapabilityResult.failure_result(
                    request_id=request_id,
                    error_code="security_denied",
                    error_message=(f"Meta-operation blocked: {'; '.join(reasons)}"),
                    trace_id=trace_id,
                    duration_ms=_now_ms() - start_ms,
                )

            # Step 4: Compose agent contract via builder pattern
            contract = self._compose_contract(spec)

            # Step 5: Register in main registry
            self._registry.register(contract, skip_validation=False)

            # Step 6: Register as created agent (lifecycle tracking)
            self._registry.register_created_agent(
                contract=contract,
                ephemeral=spec.get("ephemeral", True),
                created_by="orchestrator",
                session_scoped=spec.get("session_scoped", True),
            )

            # Step 7: Emit creation event
            self._emitter.emit_agent_created(
                agent_name=spec["name"],
                created_by="orchestrator",
                tools_granted=spec.get("tools_granted", []),
                domain=spec["domain"],
                prompt_template=spec.get("prompt_template", ""),
                ephemeral=spec.get("ephemeral", True),
                session_id=session_id,
                trace_id=trace_id,
            )

            # Step 8: Return success
            return CapabilityResult.success_result(
                request_id=request_id,
                data={
                    "agent_name": spec["name"],
                    "status": "registered",
                    "errors": [],
                },
                provider_id=BUILD_AGENT_PROVIDER_ID,
                trace_id=trace_id,
                duration_ms=_now_ms() - start_ms,
            )

        except AgentSpecValidationError as exc:
            return CapabilityResult.failure_result(
                request_id=request_id,
                error_code="validation_failed",
                error_message=str(exc),
                trace_id=trace_id,
                duration_ms=_now_ms() - start_ms,
            )

        except BuildAgentError as exc:
            return CapabilityResult.failure_result(
                request_id=request_id,
                error_code="build_failed",
                error_message=str(exc),
                trace_id=trace_id,
                duration_ms=_now_ms() - start_ms,
            )

        except Exception as exc:
            logger.error("BuildAgentHandler unexpected error: %s", exc, exc_info=True)
            return CapabilityResult.failure_result(
                request_id=request_id,
                error_code="internal_error",
                error_message=(f"Unexpected error: {type(exc).__name__}: {exc}"),
                trace_id=trace_id,
                duration_ms=_now_ms() - start_ms,
            )

    # -- Step 1: Input parsing ---------------------------------------------

    def _parse_inputs(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse raw request params into agent spec dict.

        Validates required fields are present and have correct types.
        Applies defaults for optional fields.

        Args:
            params: Raw request parameters from CapabilityRequest.params.

        Returns:
            Normalized agent spec dict ready for AgentSpecValidator.

        Raises:
            BuildAgentError: If required inputs are missing or invalid.
        """
        errors: List[str] = []

        # Required fields -- presence and type check
        agent_name = params.get("agent_name")
        if not isinstance(agent_name, str) or not agent_name.strip():
            errors.append("Missing or invalid required input: 'agent_name' (str)")

        description = params.get("description")
        if not isinstance(description, str) or not description.strip():
            errors.append("Missing or invalid required input: 'description' (str)")

        tools_granted = params.get("tools_granted")
        if not isinstance(tools_granted, list):
            errors.append("Missing or invalid required input: 'tools_granted' (list[str])")

        prompt_template = params.get("prompt_template")
        if not isinstance(prompt_template, str) or not prompt_template.strip():
            errors.append("Missing or invalid required input: 'prompt_template' (str)")

        domain = params.get("domain")
        if not isinstance(domain, list):
            errors.append("Missing or invalid required input: 'domain' (list[str])")

        if errors:
            raise BuildAgentError(errors)

        # Construct full capability name (add prefix if missing)
        name = (
            agent_name if agent_name.startswith("agent.execute.") else f"agent.execute.{agent_name}"
        )

        # Build spec with defaults for optional fields
        return {
            "name": name,
            "description": description,
            "tools_granted": tools_granted,
            "prompt_template": prompt_template,
            "domain": domain,
            "required_context": params.get("required_context", list(ALLOWED_CONTEXT_SECTIONS)),
            "llm_budget_tokens": params.get("llm_budget_tokens", DEFAULT_LLM_BUDGET_TOKENS),
            "safety_band_min": params.get("safety_band_min", DEFAULT_SAFETY_BAND),
            "max_tool_calls": params.get("max_tool_calls", DEFAULT_MAX_TOOL_CALLS),
            "max_execution_time_ms": params.get(
                "max_execution_time_ms", DEFAULT_MAX_EXECUTION_TIME_MS
            ),
            "ephemeral": params.get("ephemeral", True),
            "session_scoped": params.get("session_scoped", True),
        }

    # -- Step 4: Contract composition --------------------------------------

    def _compose_contract(self, spec: Dict[str, Any]) -> Any:
        """
        Build agent contract via AgentComposer builder pattern (Step 4).

        Args:
            spec: Validated agent spec dict from _parse_inputs + validator.

        Returns:
            CapabilityContract (frozen dataclass) with provider_type=AGENT.
        """
        builder = self._composer.compose_agent(
            name=spec["name"],
            description=spec["description"],
            domain=spec["domain"],
        )

        for tool in spec.get("tools_granted", []):
            builder = builder.add_tool(tool)

        if spec.get("prompt_template"):
            builder = builder.set_prompt(spec["prompt_template"])

        builder = builder.set_context(spec.get("required_context", list(ALLOWED_CONTEXT_SECTIONS)))

        builder = builder.set_budget(
            llm_tokens=spec.get("llm_budget_tokens", DEFAULT_LLM_BUDGET_TOKENS),
            max_tool_calls=spec.get("max_tool_calls", DEFAULT_MAX_TOOL_CALLS),
            max_execution_ms=spec.get("max_execution_time_ms", DEFAULT_MAX_EXECUTION_TIME_MS),
        )

        builder = builder.set_safety_band(spec.get("safety_band_min", DEFAULT_SAFETY_BAND))

        builder = builder.set_lifecycle(
            ephemeral=spec.get("ephemeral", True),
            session_scoped=spec.get("session_scoped", True),
        )

        return builder.build()

    # -- Repr --------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"BuildAgentHandler("
            f"validator={self._validator!r}, "
            f"composer={self._composer!r}, "
            f"registry={self._registry!r})"
        )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _now_ms() -> int:
    """Current epoch time in milliseconds."""
    return int(time.time() * 1000)
