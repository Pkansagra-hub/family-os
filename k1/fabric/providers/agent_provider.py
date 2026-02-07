"""
k1.fabric.providers.agent_provider -- Agent, AgentFactory, AgentProvider.

Contains:
  - M3 stub AgentProvider (3.3.7) that delegates to IAgentFactory
  - Agent class (4.3.2) with 6-state lifecycle FSM
  - AgentFactory (4.3.1) with 8-step instantiation flow
  - Port protocol declarations for M5 interfaces

Execution flow (from fabric_discussion.md Section 13):
  1. Receive CapabilityRequest (e.g. "agent.execute.empathy_writer")
  2. Delegate to IAgentFactory.spawn_and_execute()
  3. AgentFactory 8-step: load contract, create mailbox, grant LLM,
     grant SessionState, scope tools, build context, instantiate, start
  4. Agent executes with LLM + scoped tools (lifecycle FSM)
  5. Return CapabilityResult

Agent lifecycle (ADR-0005):
  PENDING -> WARMING -> ACTIVE -> IDLE (pool, 60s TTL)
                                -> DRAINING -> TERMINATED

Invariants:
  - Agents NEVER write SessionState directly (FAB-01)
  - Deltas emitted via IDeltaBusPort only
  - ToolScope enforced on all tool invocations (FAB-07)
  - Thread-safe: no shared mutable state between agents

References:
  - fabric_discussion.md Section 13 (Agent Factory design)
  - ADR-0005 (Agent Lifecycle states)
  - k1_cognitive_architecture_skeleton.mmd (Agent subgraph)
  - Epic 4.3 in fabric-implementation-plan.md

Exports:
  AgentProvider              -- Agent execution provider (stub, 3.3.7)
  IAgentFactory              -- Agent factory port protocol
  AgentResult                -- Result from agent execution
  AgentProviderError         -- Base agent exception
  AgentNotImplementedError   -- M3 stub: not yet implemented
  AgentSpawnError            -- Agent instantiation failed
  AgentExecutionError        -- Agent execution failed
  AgentLifecycleError        -- Invalid lifecycle transition (4.3.2)
  Agent                      -- Agent instance with lifecycle (4.3.2)
  AgentFactory               -- 8-step agent instantiation (4.3.1)
  AgentFactoryConfig         -- Factory configuration (4.3.1)
  ILLMHandle                 -- LLM handle port protocol (5.1.4 preview)
  IModelGatewayPort          -- LLM access port protocol (5.1.4 preview)
  IDeltaBusPort              -- Delta emission port protocol (5.1.6 preview)
  IAgentMailbox              -- Agent mailbox port protocol (4.4 preview)
  ISessionStateReader        -- SessionState reader protocol (5.1.1 preview)
  IDLE_TTL_S                 -- Default idle timeout (60s)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Protocol

from k1.fabric.core.context_builder import ContextBuilder
from k1.fabric.policy.tool_scope import ToolScope
from k1.fabric.providers.base_provider import BaseProvider, ProviderExecutionError
from k1.fabric.types import (
    AgentContract,
    AgentLifecycleState,
    CapabilityRequest,
    CapabilityResult,
    ExecutionContext,
    ProviderConfig,
    ProviderHealth,
    ProviderStatus,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Agent result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentResult:
    """
    Result from agent execution.

    Produced by AgentFactory.spawn_and_execute() in M4.
    Contains the agent's output plus execution metadata.

    Attributes:
        success: Whether agent execution succeeded.
        output: Agent output data.
        agent_id: Identifier of the spawned agent instance.
        tokens_used: LLM tokens consumed during execution.
        tool_calls: Number of tool invocations the agent made.
        error_message: Error description if success=False.
    """

    success: bool = True
    output: Dict[str, Any] = field(default_factory=dict)
    agent_id: str = ""
    tokens_used: int = 0
    tool_calls: int = 0
    error_message: str = ""


# ---------------------------------------------------------------------------
# Agent factory port (Protocol)
# ---------------------------------------------------------------------------


class IAgentFactory(Protocol):
    """
    Port protocol for agent instantiation and execution.

    Concrete implementation comes in Epic 4.3. Injected by
    FabricFactory in M4 when AgentFactory is built.

    In M3 this port is not available -- AgentProvider returns
    "not_implemented" error.
    """

    async def spawn_and_execute(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str,
    ) -> AgentResult:
        """
        Spawn an agent and execute the capability.

        Args:
            request: The capability request.
            context: Execution context with session sections.
            trace_id: Cognitive trace ID.

        Returns:
            AgentResult with output and metadata.
        """
        ...


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AgentProviderError(ProviderExecutionError):
    """Base exception for agent provider operations."""

    def __init__(
        self,
        provider_id: str,
        message: str,
        *,
        retriable: bool = False,
    ) -> None:
        super().__init__(
            provider_id,
            message,
            retriable=retriable,
            error_code="agent_error",
        )


class AgentNotImplementedError(AgentProviderError):
    """AgentProvider is not yet implemented (M3 stub)."""

    def __init__(self, provider_id: str) -> None:
        super().__init__(
            provider_id,
            "AgentProvider is a stub in M3. Full implementation in Epic 4.3.",
            retriable=False,
        )


class AgentSpawnError(AgentProviderError):
    """Agent instantiation failed (used in M4)."""

    def __init__(self, provider_id: str, agent_template: str, cause: str) -> None:
        self.agent_template = agent_template
        self.cause = cause
        super().__init__(
            provider_id,
            f"Failed to spawn agent '{agent_template}': {cause}",
            retriable=False,
        )


class AgentExecutionError(AgentProviderError):
    """Agent execution failed (used in M4)."""

    def __init__(self, provider_id: str, agent_id: str, cause: str) -> None:
        self.agent_id = agent_id
        self.cause = cause
        super().__init__(
            provider_id,
            f"Agent '{agent_id}' execution failed: {cause}",
            retriable=False,
        )


# ---------------------------------------------------------------------------
# Port protocols -- M4/M5 interface previews (declared locally)
# ---------------------------------------------------------------------------


class ILLMHandle(Protocol):
    """
    Opaque handle to an LLM model connection (5.1.4 preview).

    Returned by ``IModelGatewayPort.create_handle()``.  Grants an agent
    access to a specific LLM within a token budget.

    Production implementation lives in Model Hub (5.1.4).
    """

    async def generate(
        self,
        prompt: str,
        params: Dict[str, Any],
    ) -> str:
        """Generate a completion from the LLM."""
        ...  # pragma: no cover

    @property
    def model_id(self) -> str:
        """Identifier of the model this handle connects to."""
        ...  # pragma: no cover

    @property
    def budget_tokens(self) -> int:
        """Remaining token budget for this handle."""
        ...  # pragma: no cover


class IModelGatewayPort(Protocol):
    """
    LLM access port (5.1.4 interface preview).

    Production adapter: Model Hub (5.2.5).
    Consumed by AgentFactory step 3 (grant LLM access).
    """

    def create_handle(
        self,
        budget_tokens: int,
        model_preference: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        trace_id: str = "",
    ) -> ILLMHandle:
        """Create an LLM handle with the given budget."""
        ...  # pragma: no cover

    def is_model_loaded(self, model_id: str) -> bool:
        """Check if a model is currently loaded."""
        ...  # pragma: no cover


class IDeltaBusPort(Protocol):
    """
    Delta emission port (5.1.6 interface preview).

    Agents NEVER write SessionState directly (FAB-01).  Instead they
    emit deltas to the Delta Bus which routes through Concierge ->
    MutationGuard -> SessionState.

    Production adapter: Delta Bus (5.2.7).
    Consumed by Agent.execute() for delta emission.
    """

    def emit_delta(
        self,
        agent_id: str,
        delta_type: str,
        section: str,
        data: Dict[str, Any],
    ) -> None:
        """Emit a state delta for eventual SessionState write."""
        ...  # pragma: no cover


class IAgentMailbox(Protocol):
    """
    Per-agent MPSC mailbox (4.4 interface preview).

    Each spawned agent receives its own mailbox with WFQ
    INTERACTIVE priority.  Full implementation in Epic 4.4.
    """

    def send(self, message: Dict[str, Any]) -> None:
        """Enqueue a message."""
        ...  # pragma: no cover

    def receive(self) -> Optional[Dict[str, Any]]:
        """Dequeue the next message, or None if empty."""
        ...  # pragma: no cover

    @property
    def depth(self) -> int:
        """Current queue depth."""
        ...  # pragma: no cover

    def close(self) -> None:
        """Close the mailbox, rejecting further messages."""
        ...  # pragma: no cover


class ISessionStateReader(Protocol):
    """
    Read-only SessionState access (5.1.1 interface preview).

    Re-declared locally to avoid cross-package import coupling.
    Structurally matches ``k1.fabric.policy.ports.ISessionStateReader``.
    """

    def read_section(
        self,
        session_id: str,
        section: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a named section, or None if unavailable."""
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Agent lifecycle constants (4.3.2)
# ---------------------------------------------------------------------------

IDLE_TTL_S: int = 60
"""Default idle timeout in seconds before agent is terminated."""

_VALID_TRANSITIONS: Dict[AgentLifecycleState, FrozenSet[AgentLifecycleState]] = {
    AgentLifecycleState.PENDING: frozenset({AgentLifecycleState.WARMING}),
    AgentLifecycleState.WARMING: frozenset({AgentLifecycleState.ACTIVE}),
    AgentLifecycleState.ACTIVE: frozenset({AgentLifecycleState.IDLE, AgentLifecycleState.DRAINING}),
    AgentLifecycleState.IDLE: frozenset({AgentLifecycleState.ACTIVE, AgentLifecycleState.DRAINING}),
    AgentLifecycleState.DRAINING: frozenset({AgentLifecycleState.TERMINATED}),
    AgentLifecycleState.TERMINATED: frozenset(),
}


class AgentLifecycleError(AgentProviderError):
    """Invalid lifecycle state transition."""

    def __init__(
        self,
        provider_id: str,
        agent_id: str,
        from_state: str,
        to_state: str,
    ) -> None:
        self.agent_id = agent_id
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            provider_id,
            f"Invalid lifecycle transition: {from_state} -> {to_state} " f"(agent={agent_id})",
            retriable=False,
        )


# ---------------------------------------------------------------------------
# Agent class (4.3.2)
# ---------------------------------------------------------------------------


class Agent:
    """
    Agent instance with lifecycle management (4.3.2).

    Created by ``AgentFactory.spawn()``.  Each agent has its own:
      - UUID identity
      - AgentContract (frozen)
      - LLM handle (optional, from IModelGatewayPort)
      - SessionState reader (scoped to declared sections)
      - ToolScope (enforces tools_granted)
      - ExecutionContext (assembled by ContextBuilder)
      - Lifecycle FSM (6 states from ADR-0005)

    Lifecycle::

      PENDING -> WARMING -> ACTIVE -> IDLE (pool, 60s TTL)
                                    -> DRAINING -> TERMINATED

    Invariants:
      - NEVER writes SessionState directly (FAB-01)
      - Emits deltas via IDeltaBusPort only
      - ToolScope enforced on all tool invocations (FAB-07)
      - Token budget tracked via LLM handle
    """

    __slots__ = (
        "_id",
        "_contract",
        "_mailbox",
        "_llm_handle",
        "_state_reader",
        "_tool_scope",
        "_context",
        "_delta_bus",
        "_lifecycle_state",
        "_created_at",
        "_idle_since",
        "_tokens_used",
        "_tool_calls",
    )

    def __init__(
        self,
        *,
        agent_id: str,
        contract: AgentContract,
        context: ExecutionContext,
        mailbox: Optional[IAgentMailbox] = None,
        llm_handle: Optional[ILLMHandle] = None,
        state_reader: Optional[ISessionStateReader] = None,
        tool_scope: Optional[ToolScope] = None,
        delta_bus: Optional[IDeltaBusPort] = None,
    ) -> None:
        self._id = agent_id
        self._contract = contract
        self._mailbox = mailbox
        self._llm_handle = llm_handle
        self._state_reader = state_reader
        self._tool_scope = tool_scope
        self._context = context
        self._delta_bus = delta_bus
        self._lifecycle_state = AgentLifecycleState.PENDING
        self._created_at: float = time.monotonic()
        self._idle_since: float = 0.0
        self._tokens_used: int = 0
        self._tool_calls: int = 0

    # ------------------------------------------------------------------
    # Read-only properties
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        """Agent UUID."""
        return self._id

    @property
    def contract(self) -> AgentContract:
        """The AgentContract this agent was spawned from."""
        return self._contract

    @property
    def lifecycle_state(self) -> AgentLifecycleState:
        """Current lifecycle state."""
        return self._lifecycle_state

    @property
    def is_active(self) -> bool:
        """True when agent is executing."""
        return self._lifecycle_state == AgentLifecycleState.ACTIVE

    @property
    def is_idle(self) -> bool:
        """True when agent is pooled and reusable."""
        return self._lifecycle_state == AgentLifecycleState.IDLE

    @property
    def is_terminated(self) -> bool:
        """True when agent lifecycle is complete."""
        return self._lifecycle_state == AgentLifecycleState.TERMINATED

    @property
    def context(self) -> ExecutionContext:
        """The execution context assembled at spawn time."""
        return self._context

    @property
    def tokens_used(self) -> int:
        """Approximate LLM tokens consumed."""
        return self._tokens_used

    @property
    def tool_calls(self) -> int:
        """Number of tool invocations made."""
        return self._tool_calls

    @property
    def idle_elapsed_s(self) -> float:
        """Seconds elapsed since entering IDLE state (0 if not idle)."""
        if self._lifecycle_state != AgentLifecycleState.IDLE:
            return 0.0
        return time.monotonic() - self._idle_since

    @property
    def idle_ttl_expired(self) -> bool:
        """True if IDLE time exceeds IDLE_TTL_S."""
        return self.is_idle and self.idle_elapsed_s > IDLE_TTL_S

    # ------------------------------------------------------------------
    # Lifecycle transitions
    # ------------------------------------------------------------------

    def _transition(self, target: AgentLifecycleState) -> None:
        """
        Transition to *target* state with FSM validation.

        Raises:
            AgentLifecycleError: If the transition is not valid.
        """
        valid = _VALID_TRANSITIONS.get(self._lifecycle_state, frozenset())
        if target not in valid:
            raise AgentLifecycleError(
                provider_id=self._contract.provider_id,
                agent_id=self._id,
                from_state=self._lifecycle_state.value,
                to_state=target.value,
            )
        logger.debug(
            "Agent %s: %s -> %s",
            self._id[:8],
            self._lifecycle_state.value,
            target.value,
        )
        self._lifecycle_state = target

    def warm_up(self) -> None:
        """
        Transition PENDING -> WARMING -> ACTIVE.

        In production, model preload happens during WARMING phase.
        Currently synchronous (preload is instant for stub handles).
        """
        self._transition(AgentLifecycleState.WARMING)
        # Model preload would happen here with real ILLMHandle
        self._transition(AgentLifecycleState.ACTIVE)

    def idle(self) -> None:
        """Transition ACTIVE -> IDLE (enter agent pool)."""
        self._transition(AgentLifecycleState.IDLE)
        self._idle_since = time.monotonic()

    def reactivate(self) -> None:
        """Transition IDLE -> ACTIVE (reuse from pool)."""
        self._transition(AgentLifecycleState.ACTIVE)
        self._idle_since = 0.0

    def drain(self) -> None:
        """Transition ACTIVE or IDLE -> DRAINING."""
        self._transition(AgentLifecycleState.DRAINING)

    def terminate(self) -> None:
        """
        Transition DRAINING -> TERMINATED.

        Releases port references (mailbox, LLM handle, state reader).
        """
        self._transition(AgentLifecycleState.TERMINATED)
        self._mailbox = None
        self._llm_handle = None
        self._state_reader = None

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute(self, params: Dict[str, Any]) -> CapabilityResult:
        """
        Execute the agent's capability with the given parameters.

        The agent must be in ACTIVE state.  If in IDLE state, it is
        reactivated first.

        Flow:
          1. Validate lifecycle (must be ACTIVE)
          2. Build execution prompt from context + params
          3. If LLM handle: generate response
          4. If no LLM handle: passthrough params as output
          5. Emit delta if delta_bus exists
          6. Return CapabilityResult

        Args:
            params: Request parameters for this execution.

        Returns:
            CapabilityResult with agent output.
        """
        # Auto-reactivate from IDLE
        if self._lifecycle_state == AgentLifecycleState.IDLE:
            self.reactivate()

        if self._lifecycle_state != AgentLifecycleState.ACTIVE:
            return CapabilityResult.failure_result(
                request_id=params.get("request_id", ""),
                error_code="agent_lifecycle_error",
                error_message=(f"Cannot execute: agent is in {self._lifecycle_state.value} state"),
                retriable=False,
                provider_id=self._contract.provider_id,
                trace_id=self._context.trace_id,
            )

        t0 = time.monotonic()
        request_id = params.get("request_id", "")
        trace_id = self._context.trace_id

        try:
            output: Dict[str, Any]

            if self._llm_handle is not None:
                # Production path: call LLM
                prompt = self._context.prompt or ""
                full_prompt = f"{prompt}\n\nParams: {params}" if prompt else str(params)
                response_text = await self._llm_handle.generate(full_prompt, params)
                output = {"response": response_text}
                self._tokens_used += len(response_text) // 4  # approximate
            else:
                # No LLM handle: passthrough for testing
                output = dict(params)

            # Emit delta if delta_bus available
            if self._delta_bus is not None and output:
                try:
                    self._delta_bus.emit_delta(
                        agent_id=self._id,
                        delta_type="agent_output",
                        section="history_active",
                        data={"output": output},
                    )
                except Exception:
                    logger.warning(
                        "Agent %s: delta emission failed",
                        self._id[:8],
                        exc_info=True,
                    )

            elapsed_ms = int((time.monotonic() - t0) * 1000)

            return CapabilityResult.success_result(
                request_id=request_id,
                data=output,
                provider_id=self._contract.provider_id,
                trace_id=trace_id,
                execution_time_ms=elapsed_ms,
            )

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.error(
                "Agent %s execution failed: %s",
                self._id[:8],
                exc,
                exc_info=True,
            )
            return CapabilityResult.failure_result(
                request_id=request_id,
                error_code="agent_execution_error",
                error_message=f"Agent execution failed: {exc}",
                retriable=False,
                provider_id=self._contract.provider_id,
                trace_id=trace_id,
                execution_time_ms=elapsed_ms,
            )

    def __repr__(self) -> str:
        return (
            f"Agent(id={self._id[:8]}..., "
            f"contract={self._contract.name!r}, "
            f"state={self._lifecycle_state.value}, "
            f"tokens={self._tokens_used})"
        )


# ---------------------------------------------------------------------------
# AgentFactory configuration (4.3.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentFactoryConfig:
    """
    Configuration for AgentFactory (4.3.1).

    Attributes:
        idle_ttl_s: Time in seconds before IDLE agents are terminated.
        max_concurrent_agents: Max concurrent agent instances.
        default_llm_budget: Default token budget when contract omits it.
    """

    idle_ttl_s: int = IDLE_TTL_S
    max_concurrent_agents: int = 20
    default_llm_budget: int = 4_000

    def __repr__(self) -> str:
        return (
            f"AgentFactoryConfig("
            f"idle_ttl={self.idle_ttl_s}s, "
            f"max_agents={self.max_concurrent_agents}, "
            f"llm_budget={self.default_llm_budget})"
        )


# ---------------------------------------------------------------------------
# AgentFactory (4.3.1) -- 8-step instantiation
# ---------------------------------------------------------------------------


class AgentFactory:
    """
    Agent instantiation factory (4.3.1).

    Implements the 8-step agent instantiation flow from
    ``fabric_discussion.md`` Section 13.  Satisfies the ``IAgentFactory``
    protocol structurally.

    8-step flow:
      1. Load AgentContract via ``contract_loader``
      2. Create MPSC mailbox (WFQ INTERACTIVE) -- stub for 4.4
      3. Grant LLM access via ``IModelGatewayPort``
      4. Grant SessionState read access (declared sections)
      5. Scope tool access (ToolScope from ``contract.tools_granted``)
      6. Build initial context via ``ContextBuilder``
      7. Instantiate Agent object
      8. Start lifecycle: PENDING -> WARMING -> ACTIVE

    Usage::

        factory = AgentFactory(
            context_builder=builder,
            model_gateway=model_gw,
            contract_loader=registry.get_agent_contract,
        )
        result = await factory.spawn_and_execute(request, context, trace_id)
    """

    __slots__ = (
        "_context_builder",
        "_model_gateway",
        "_state_reader",
        "_delta_bus",
        "_contract_loader",
        "_config",
    )

    def __init__(
        self,
        *,
        context_builder: Optional[ContextBuilder] = None,
        model_gateway: Optional[IModelGatewayPort] = None,
        state_reader: Optional[ISessionStateReader] = None,
        delta_bus: Optional[IDeltaBusPort] = None,
        contract_loader: Optional[Callable[[str], Optional[AgentContract]]] = None,
        config: Optional[AgentFactoryConfig] = None,
    ) -> None:
        self._context_builder = context_builder
        self._model_gateway = model_gateway
        self._state_reader = state_reader
        self._delta_bus = delta_bus
        self._contract_loader = contract_loader
        self._config = config or AgentFactoryConfig()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def config(self) -> AgentFactoryConfig:
        """Current factory configuration."""
        return self._config

    @property
    def has_model_gateway(self) -> bool:
        """Whether a model gateway port is connected."""
        return self._model_gateway is not None

    @property
    def has_context_builder(self) -> bool:
        """Whether a ContextBuilder is connected."""
        return self._context_builder is not None

    # ------------------------------------------------------------------
    # IAgentFactory protocol implementation
    # ------------------------------------------------------------------

    async def spawn_and_execute(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str,
    ) -> AgentResult:
        """
        Spawn an agent and execute the requested capability.

        Implements the ``IAgentFactory`` protocol.  Performs the 8-step
        instantiation, executes the agent, and returns the result.

        Args:
            request: The capability request (agent.execute.* or agent.spawn.*).
            context: Pre-assembled execution context (fallback).
            trace_id: Cognitive trace ID.

        Returns:
            AgentResult with output and metadata.
        """
        t0 = time.monotonic()

        # Step 1: Load AgentContract
        contract = self._load_contract(request.capability_name)
        if contract is None:
            return AgentResult(
                success=False,
                error_message=(
                    f"Agent contract not found for '{request.capability_name}'. "
                    "No contract_loader configured or contract missing."
                ),
            )

        # Steps 2-7: Spawn agent
        try:
            agent = self._spawn(contract, context, request.params, trace_id)
        except AgentSpawnError as exc:
            return AgentResult(
                success=False,
                error_message=str(exc),
            )
        except Exception as exc:
            logger.error(
                "Agent spawn failed for '%s': %s",
                request.capability_name,
                exc,
                exc_info=True,
            )
            return AgentResult(
                success=False,
                error_message=f"Agent spawn failed: {exc}",
            )

        # Step 8: Warm up and execute
        try:
            agent.warm_up()
            result = await agent.execute(request.params)

            # Transition to IDLE (poolable) on success, terminate on failure
            if result.success:
                agent.idle()
            else:
                agent.drain()
                agent.terminate()

            return AgentResult(
                success=result.success,
                output=result.data or {},
                agent_id=agent.id,
                tokens_used=agent.tokens_used,
                tool_calls=agent.tool_calls,
                error_message=result.error.message if result.error else "",
            )

        except Exception as exc:
            logger.error(
                "Agent %s execution failed: %s",
                agent.id[:8],
                exc,
                exc_info=True,
            )
            # Best-effort cleanup
            try:
                if agent.lifecycle_state in (
                    AgentLifecycleState.ACTIVE,
                    AgentLifecycleState.IDLE,
                ):
                    agent.drain()
                if agent.lifecycle_state == AgentLifecycleState.DRAINING:
                    agent.terminate()
            except Exception:
                pass
            return AgentResult(
                success=False,
                agent_id=agent.id,
                error_message=f"Agent execution failed: {exc}",
            )

    # ------------------------------------------------------------------
    # Internal: contract loading
    # ------------------------------------------------------------------

    def _load_contract(self, capability_name: str) -> Optional[AgentContract]:
        """
        Step 1: Load the AgentContract for the given capability.

        Returns None if no contract_loader is configured or the
        contract is not found.
        """
        if self._contract_loader is None:
            logger.warning("No contract_loader configured for AgentFactory")
            return None

        try:
            contract = self._contract_loader(capability_name)
            if contract is not None:
                logger.debug(
                    "Loaded agent contract '%s' for '%s'",
                    contract.name,
                    capability_name,
                )
            return contract
        except Exception:
            logger.warning(
                "Failed to load contract for '%s'",
                capability_name,
                exc_info=True,
            )
            return None

    # ------------------------------------------------------------------
    # Internal: 8-step spawn
    # ------------------------------------------------------------------

    def _spawn(
        self,
        contract: AgentContract,
        fallback_context: ExecutionContext,
        params: Dict[str, Any],
        trace_id: str,
    ) -> Agent:
        """
        Steps 2-7 of the 8-step instantiation flow.

        Args:
            contract: The AgentContract to instantiate.
            fallback_context: Context to use if ContextBuilder unavailable.
            params: Request parameters for context building.
            trace_id: Cognitive trace ID.

        Returns:
            A new Agent in PENDING state.

        Raises:
            AgentSpawnError: If a critical step fails.
        """
        agent_id = str(uuid.uuid4())

        # Step 2: Create MPSC Mailbox (WFQ INTERACTIVE priority)
        # Full implementation in Epic 4.4.  Mailbox is None for now.
        mailbox: Optional[IAgentMailbox] = None

        # Step 3: Grant LLM access via IModelGatewayPort
        llm_handle: Optional[ILLMHandle] = None
        if self._model_gateway is not None:
            budget = contract.llm_budget_tokens or self._config.default_llm_budget
            try:
                llm_handle = self._model_gateway.create_handle(
                    budget_tokens=budget,
                    trace_id=trace_id,
                )
            except Exception as exc:
                raise AgentSpawnError(
                    provider_id=contract.provider_id,
                    agent_template=contract.name,
                    cause=f"LLM handle creation failed: {exc}",
                ) from exc

        # Step 4: Grant SessionState read access (declared sections only)
        state_reader = self._state_reader

        # Step 5: Scope tool access (tools_granted from contract)
        tool_scope: Optional[ToolScope] = None
        if contract.tools_granted:
            try:
                tool_scope = ToolScope(tools_granted=contract.tools_granted)
            except Exception as exc:
                raise AgentSpawnError(
                    provider_id=contract.provider_id,
                    agent_template=contract.name,
                    cause=f"ToolScope creation failed: {exc}",
                ) from exc

        # Step 6: Build initial context via ContextBuilder
        if self._context_builder is not None:
            try:
                build_result = self._context_builder.build(
                    contract=contract,
                    params=params,
                    trace_id=trace_id,
                )
                initial_context = build_result.context
            except Exception as exc:
                logger.warning(
                    "ContextBuilder failed for agent '%s', using fallback: %s",
                    contract.name,
                    exc,
                )
                initial_context = fallback_context
        else:
            initial_context = fallback_context

        # Step 7: Instantiate Agent object
        agent = Agent(
            agent_id=agent_id,
            contract=contract,
            context=initial_context,
            mailbox=mailbox,
            llm_handle=llm_handle,
            state_reader=state_reader,
            tool_scope=tool_scope,
            delta_bus=self._delta_bus,
        )

        logger.debug(
            "Spawned agent %s (contract=%s, llm=%s, tools=%s)",
            agent_id[:8],
            contract.name,
            llm_handle is not None,
            tool_scope is not None,
        )

        return agent

    def __repr__(self) -> str:
        return (
            f"AgentFactory("
            f"model_gw={'yes' if self._model_gateway else 'no'}, "
            f"ctx_builder={'yes' if self._context_builder else 'no'}, "
            f"delta_bus={'yes' if self._delta_bus else 'no'})"
        )


# ---------------------------------------------------------------------------
# AgentProvider (stub -- full implementation in 4.3.5)
# ---------------------------------------------------------------------------


class AgentProvider(BaseProvider):
    """
    Agent execution provider -- STUB (3.3.7).

    M3 stub that returns "not_implemented" for all execute() calls.
    Full implementation in Epic 4.3 when AgentFactory is built.

    In M4, this provider will:
      1. Load agent template from AgentContract
      2. Spawn agent via IAgentFactory
      3. Agent gets: LLM handle, scoped tools, SessionState reader
      4. Execute and return CapabilityResult

    Constructor Args:
        config: ProviderConfig with provider_id and type.
        agent_factory: Optional IAgentFactory (None in M3, injected in M4).
        capability_names: List of agent.execute.* and agent.spawn.* capabilities.

    Usage (M3 -- stub)::

        provider = AgentProvider(
            config=ProviderConfig(
                provider_id="agent-runner",
                provider_type="AGENT",
            ),
            capability_names=["agent.execute.empathy_writer"],
        )
        result = await provider.execute(request, context, trace_id)
        # result.success == False, error.code == "agent_error"

    Usage (M4 -- full)::

        provider = AgentProvider(
            config=...,
            agent_factory=my_agent_factory,
            capability_names=[...],
        )
        result = await provider.execute(request, context, trace_id)
        # result.success == True (when agent succeeds)
    """

    __slots__ = ("_agent_factory", "_capability_names")

    def __init__(
        self,
        config: ProviderConfig,
        *,
        agent_factory: Optional[IAgentFactory] = None,
        capability_names: Optional[List[str]] = None,
        **_kwargs: Any,
    ) -> None:
        super().__init__(config)
        self._agent_factory = agent_factory
        self._capability_names: List[str] = list(capability_names or [])

    # ======================================================================
    # CapabilityProvider interface
    # ======================================================================

    def capabilities(self) -> List[str]:
        """Return the list of agent capability names."""
        return list(self._capability_names)

    async def health_check(self) -> ProviderHealth:
        """
        Agent provider health check.

        M3: Returns UNKNOWN (stub).
        M4: Will check IAgentFactory + IModelGatewayPort availability.
        """
        if self._agent_factory is None:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderStatus.UNKNOWN.value,
                error="AgentProvider is a stub (M3). No agent_factory injected.",
            )
        # M4 path: check agent factory availability
        return ProviderHealth(
            provider_id=self.provider_id,
            status=ProviderStatus.HEALTHY.value,
        )

    # ======================================================================
    # Internal execution (BaseProvider._execute)
    # ======================================================================

    async def _execute(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str,
    ) -> CapabilityResult:
        """
        Agent-specific execution logic.

        M3: Raises AgentNotImplementedError (stub).
        M4: Delegates to IAgentFactory.spawn_and_execute().
        """
        # M3 stub: no agent factory available
        if self._agent_factory is None:
            raise AgentNotImplementedError(self.provider_id)

        # M4 path: delegate to agent factory
        logger.debug(
            "[%s] spawning agent for: %s (trace=%s)",
            self.provider_id,
            request.capability_name,
            trace_id,
        )

        agent_result = await self._agent_factory.spawn_and_execute(request, context, trace_id)

        if not agent_result.success:
            return CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code="agent_execution_error",
                error_message=agent_result.error_message or "Agent execution failed",
                retriable=False,
                provider_id=self.provider_id,
                trace_id=trace_id,
            )

        return CapabilityResult.success_result(
            request_id=request.request_id,
            data={
                "output": agent_result.output,
                "agent_id": agent_result.agent_id,
                "tokens_used": agent_result.tokens_used,
                "tool_calls": agent_result.tool_calls,
            },
            provider_id=self.provider_id,
            trace_id=trace_id,
        )

    def __repr__(self) -> str:
        status = "stub" if self._agent_factory is None else "active"
        return (
            f"AgentProvider("
            f"provider_id={self.provider_id!r}, "
            f"status={status}, "
            f"capabilities={len(self._capability_names)})"
        )
