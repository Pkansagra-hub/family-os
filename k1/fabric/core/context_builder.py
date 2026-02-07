"""
k1.fabric.core.context_builder -- Execution context assembly (4.2.1).

6-step flow:
  1. Read contract ``required_context`` + ``optional_context`` section lists.
  2. Fetch each section from SessionState via ``ISessionStateReader``
     (multi-reader, lock-free).
  3. Inject request params.
  4. Resolve prompt template (if applicable) via ``IPromptSystemPort``.
  5. Apply token budget (128K ceiling) via ``ContextBudget``.
  6. Package into ``ExecutionContext`` (frozen dataclass from types.py).

Graceful degradation:
  - Optional section missing -> skip silently.
  - Required section missing -> log warning, continue with partial context.
  - IPromptSystemPort is None -> skip prompt resolution (prompt=None).
  - ISessionStateReader is None -> session_sections={}.

Thread safety: All public methods are stateless per call.  Internal
``ContextBudget`` and port calls are also thread-safe.

References:
  - fabric_discussion.md Section 12 (Context Assembly Flow)
  - Epic 4.2.1 in fabric-implementation-plan.md
  - FAB-008 (Single Writer -- Fabric reads SessionState, never writes)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from k1.fabric.core.context_budget import BudgetResult, ContextBudget, ContextBudgetConfig
from k1.fabric.types import CapabilityContract, ExecutionContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Port protocols (declared locally to avoid circular imports)
# ---------------------------------------------------------------------------


class ISessionStateReader(Protocol):
    """
    Read-only access to SessionState sections.

    Matches ``k1.fabric.policy.ports.ISessionStateReader`` structurally.
    Re-declared here to avoid cross-package import coupling.
    """

    def read_section(
        self,
        session_id: str,
        section: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a named section, or None if unavailable."""
        ...  # pragma: no cover


class IPromptSystemPort(Protocol):
    """
    Prompt resolution and compilation port (5.1.5 interface preview).

    Production implementation lives in the K1 Prompt Management System.
    Fabric only defines this port interface.
    """

    def resolve(self, template_name: str) -> Optional[Dict[str, Any]]:
        """
        Resolve a prompt template by name.

        Returns:
            Template dict with at least ``{"text": str}`` key, or None.
        """
        ...  # pragma: no cover

    def compile(
        self,
        template: Dict[str, Any],
        variables: Dict[str, Any],
    ) -> str:
        """
        Compile a template with variables, returning the final prompt string.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ContextBuilderError(Exception):
    """Base exception for ContextBuilder operations."""

    def __repr__(self) -> str:
        return f"ContextBuilderError({self.args})"


class ContextAssemblyError(ContextBuilderError):
    """Raised when context assembly fails in a non-recoverable way."""

    def __repr__(self) -> str:
        return f"ContextAssemblyError({self.args})"


# ---------------------------------------------------------------------------
# Build result (richer than just ExecutionContext)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextBuildResult:
    """
    Full result of context assembly, including the ``ExecutionContext``
    and assembly metadata.
    """

    #: The packaged execution context (frozen).
    context: ExecutionContext = field(default_factory=ExecutionContext)

    #: Budget details (compression level, sections dropped, etc.).
    budget: BudgetResult = field(default_factory=BudgetResult)

    #: Sections that were requested but could not be fetched.
    missing_required: List[str] = field(default_factory=list)
    missing_optional: List[str] = field(default_factory=list)

    #: Assembly wall-clock time in milliseconds.
    assembly_ms: float = 0.0

    #: Whether a prompt was resolved and compiled.
    prompt_resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "context": self.context.to_dict(),
            "budget": self.budget.to_dict(),
            "missing_required": list(self.missing_required),
            "missing_optional": list(self.missing_optional),
            "assembly_ms": round(self.assembly_ms, 3),
            "prompt_resolved": self.prompt_resolved,
        }

    def __repr__(self) -> str:
        return (
            f"ContextBuildResult(tokens={self.budget.total_tokens}, "
            f"compression={self.budget.compression_applied.value}, "
            f"missing_req={len(self.missing_required)}, "
            f"assembly_ms={self.assembly_ms:.1f})"
        )


# ---------------------------------------------------------------------------
# ContextBuilder configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextBuilderConfig:
    """Configuration for ContextBuilder."""

    #: Default session_id when none provided.
    default_session_id: str = ""

    #: Budget config forwarded to ContextBudget.
    budget_config: ContextBudgetConfig = field(default_factory=ContextBudgetConfig)

    def __repr__(self) -> str:
        return (
            f"ContextBuilderConfig(ceiling={self.budget_config.ceiling}, "
            f"headroom={self.budget_config.response_headroom})"
        )


# ---------------------------------------------------------------------------
# ContextBuilder -- main class
# ---------------------------------------------------------------------------


class ContextBuilder:
    """
    Assembles ``ExecutionContext`` for capability execution.

    Six-step pipeline:
      1. Read contract required_context + optional_context lists.
      2. Fetch from SessionState via ``ISessionStateReader``.
      3. Inject request params.
      4. Resolve prompt template via ``IPromptSystemPort`` (optional).
      5. Apply token budget via ``ContextBudget``.
      6. Package ``ExecutionContext``.

    Ports are injected at construction time and can be ``None`` for
    graceful degradation (no SessionState reads, no prompt resolution).

    Usage::

        builder = ContextBuilder(state_reader=reader, prompt_system=prompt_sys)
        result = builder.build(
            contract=contract,
            params={"query": "lights on"},
            session_id="sess-123",
            trace_id="tr-abc",
        )
        context = result.context  # ExecutionContext (frozen)
    """

    __slots__ = ("_state_reader", "_prompt_system", "_budget", "_config")

    def __init__(
        self,
        state_reader: Optional[ISessionStateReader] = None,
        prompt_system: Optional[IPromptSystemPort] = None,
        config: Optional[ContextBuilderConfig] = None,
    ) -> None:
        self._state_reader = state_reader
        self._prompt_system = prompt_system
        self._config: ContextBuilderConfig = config or ContextBuilderConfig()
        self._budget = ContextBudget(self._config.budget_config)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def config(self) -> ContextBuilderConfig:
        """Current configuration (frozen)."""
        return self._config

    @property
    def has_state_reader(self) -> bool:
        """Whether a SessionState reader port is connected."""
        return self._state_reader is not None

    @property
    def has_prompt_system(self) -> bool:
        """Whether a prompt system port is connected."""
        return self._prompt_system is not None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        contract: CapabilityContract,
        params: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        trace_id: str = "",
        prompt_template_name: Optional[str] = None,
        prompt_variables: Optional[Dict[str, Any]] = None,
    ) -> ContextBuildResult:
        """
        Assemble an ``ExecutionContext`` for the given contract.

        Args:
            contract: The capability contract declaring context requirements.
            params: Request parameters to inject.
            session_id: Session identifier for SessionState reads.
            trace_id: Tracing identifier from the originating request.
            prompt_template_name: Optional prompt template to resolve.
            prompt_variables: Variables for prompt compilation.

        Returns:
            ContextBuildResult with the packaged ExecutionContext and
            assembly metadata.

        Raises:
            ContextAssemblyError: If a fatal error prevents assembly.
        """
        t0 = time.perf_counter()
        params = params or {}
        session_id = session_id or self._config.default_session_id
        prompt_variables = prompt_variables or {}

        # ----- Step 1: Read contract context requirements -----
        required_sections: List[str] = list(contract.required_context)
        optional_sections: List[str] = list(contract.optional_context)
        all_sections = required_sections + optional_sections

        # ----- Step 2: Fetch from SessionState -----
        session_data: Dict[str, Any] = {}
        missing_required: List[str] = []
        missing_optional: List[str] = []

        if self._state_reader is not None and all_sections:
            for section_name in all_sections:
                try:
                    data = self._state_reader.read_section(session_id, section_name)
                except Exception:
                    logger.warning(
                        "SessionState read failed for section '%s'",
                        section_name,
                        exc_info=True,
                    )
                    data = None

                if data is not None:
                    session_data[section_name] = data
                elif section_name in required_sections:
                    missing_required.append(section_name)
                    logger.warning(
                        "Required context section '%s' unavailable (session=%s)",
                        section_name,
                        session_id,
                    )
                else:
                    missing_optional.append(section_name)
        elif self._state_reader is None and required_sections:
            # No reader -- all required sections are missing
            missing_required = list(required_sections)
            missing_optional = list(optional_sections)
            logger.warning(
                "No ISessionStateReader -- %d required sections unavailable",
                len(missing_required),
            )

        # ----- Step 3: Inject request params -----
        # params are passed through directly; no transformation needed.

        # ----- Step 4: Resolve prompt template (if applicable) -----
        compiled_prompt: Optional[str] = None
        prompt_resolved = False

        if prompt_template_name and self._prompt_system is not None:
            try:
                template = self._prompt_system.resolve(prompt_template_name)
                if template is not None:
                    compiled_prompt = self._prompt_system.compile(template, prompt_variables)
                    prompt_resolved = True
                else:
                    logger.warning("Prompt template '%s' not found", prompt_template_name)
            except Exception:
                logger.warning(
                    "Prompt resolution failed for '%s'",
                    prompt_template_name,
                    exc_info=True,
                )

        # ----- Step 5: Apply token budget -----
        budget_result = self._budget.apply(
            session_sections=session_data,
            prompt=compiled_prompt,
            params=params,
            optional_sections=optional_sections,
        )

        # ----- Step 6: Package ExecutionContext -----
        context = ExecutionContext(
            session_sections=budget_result.session_sections,
            params=budget_result.params,
            prompt=budget_result.prompt,
            token_count=budget_result.total_tokens,
            trace_id=trace_id,
        )

        assembly_ms = (time.perf_counter() - t0) * 1000.0

        return ContextBuildResult(
            context=context,
            budget=budget_result,
            missing_required=missing_required,
            missing_optional=missing_optional,
            assembly_ms=assembly_ms,
            prompt_resolved=prompt_resolved,
        )

    def build_minimal(
        self,
        params: Optional[Dict[str, Any]] = None,
        trace_id: str = "",
    ) -> ExecutionContext:
        """
        Build a minimal context with no contract requirements.

        Useful for simple tool calls that don't need SessionState or prompts.

        Args:
            params: Request parameters.
            trace_id: Tracing identifier.

        Returns:
            Minimal ExecutionContext with only params and trace_id.
        """
        from k1.fabric.core.context_budget import count_tokens_dict

        params = params or {}
        return ExecutionContext(
            session_sections={},
            params=params,
            prompt=None,
            token_count=count_tokens_dict(params),
            trace_id=trace_id,
        )
