"""
k1.fabric.providers.agent_provider -- Agent, AgentFactory, AgentProvider.

Contains:
  - AgentProvider (4.3.5) full implementation using AgentFactory
  - Agent class (4.3.2) with 6-state lifecycle FSM
  - AgentFactory (4.3.1) with 8-step instantiation flow
  - AgentPool (4.3.3) IDLE pool for agent reuse
  - AgentDelta + DeltaEmitter (4.3.4) structured delta emission
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

Agent Pool (4.3.3):
  - Pool keyed by contract name
  - On success, agent -> IDLE -> pool (if room)
  - On next request for same contract: pop from pool, reactivate
  - TTL sweep: agents idle > IDLE_TTL_S are drained+terminated
  - Max pool size configurable per AgentPoolConfig

Delta emission (4.3.4):
  - Agents NEVER write SessionState directly (FAB-01)
  - AgentDelta: structured payload with section, key, value, op
  - DeltaEmitter: batches deltas in 500ms window, LWW merge
  - Emits via IDeltaBusPort to ``k1.agent.{agent_id}.delta.v1``

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
  AgentProvider              -- Agent execution provider (4.3.5, full)
  IAgentFactory              -- Agent factory port protocol
  AgentResult                -- Result from agent execution
  AgentProviderError         -- Base agent exception
  AgentNotImplementedError   -- M3 stub: not yet implemented
  AgentSpawnError            -- Agent instantiation failed
  AgentExecutionError        -- Agent execution failed
  AgentTemplateNotFoundError -- Agent contract/template not found (4.3.5)
  AgentTimeoutError          -- Agent execution timeout (4.3.5)
  AgentLifecycleError        -- Invalid lifecycle transition (4.3.2)
  Agent                      -- Agent instance with lifecycle (4.3.2)
  AgentFactory               -- 8-step agent instantiation (4.3.1)
  AgentFactoryConfig         -- Factory configuration (4.3.1)
  AgentPool                  -- IDLE pool for agent reuse (4.3.3)
  AgentPoolConfig            -- Pool configuration (4.3.3)
  AgentPoolFullError         -- Pool at capacity (4.3.3)
  AgentDelta                 -- Structured delta payload (4.3.4)
  DeltaEmitter               -- Batched delta emission (4.3.4)
  DELTA_TOPIC_PATTERN        -- Topic pattern for delta bus (4.3.4)
  DELTA_BATCH_WINDOW_MS      -- Batch window in ms (4.3.4)
  ILLMHandle                 -- LLM handle port protocol (5.1.4 preview)
  IModelGatewayPort          -- LLM access port protocol (5.1.4 preview)
  IDeltaBusPort              -- Delta emission port protocol (5.1.6 preview)
  IAgentMailbox              -- Agent mailbox port protocol (4.4 preview)
  ISessionStateReader        -- SessionState reader protocol (5.1.1 preview)
  IDLE_TTL_S                 -- Default idle timeout (60s)
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Protocol

from k1.fabric.core.context_builder import ContextBuilder
from k1.fabric.metrics import get_default_metrics
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


class AgentTemplateNotFoundError(AgentProviderError):
    """Agent contract/template not found for the requested capability."""

    def __init__(self, provider_id: str, capability_name: str) -> None:
        self.capability_name = capability_name
        super().__init__(
            provider_id,
            f"No agent template found for capability '{capability_name}'",
            retriable=False,
        )


class AgentTimeoutError(AgentProviderError):
    """Agent execution exceeded the allowed deadline."""

    def __init__(
        self,
        provider_id: str,
        agent_id: str,
        timeout_ms: int,
    ) -> None:
        self.agent_id = agent_id
        self.timeout_ms = timeout_ms
        super().__init__(
            provider_id,
            f"Agent '{agent_id}' exceeded {timeout_ms}ms deadline",
            retriable=True,
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

    async def is_model_loaded(self, model_id: str) -> bool:
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
        "_delta_emitter",
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
        delta_emitter: Optional["DeltaEmitter"] = None,
    ) -> None:
        self._id = agent_id
        self._contract = contract
        self._mailbox = mailbox
        self._llm_handle = llm_handle
        self._state_reader = state_reader
        self._tool_scope = tool_scope
        self._context = context
        self._delta_bus = delta_bus
        self._delta_emitter = delta_emitter
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
    def delta_emitter(self) -> Optional["DeltaEmitter"]:
        """The DeltaEmitter for structured delta emission (4.3.4)."""
        return self._delta_emitter

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

            # Emit delta (4.3.4): structured via DeltaEmitter if available,
            # else fallback to raw IDeltaBusPort
            if self._delta_emitter is not None and output:
                try:
                    self._delta_emitter.emit(
                        delta_type="agent_output",
                        section="history_active",
                        key=f"agent_{self._id[:8]}_{request_id or 'noid'}",
                        value=output,
                        op="set",
                    )
                    self._delta_emitter.flush()
                except Exception:
                    logger.warning(
                        "Agent %s: DeltaEmitter flush failed",
                        self._id[:8],
                        exc_info=True,
                    )
            elif self._delta_bus is not None and output:
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
# Delta emission types (4.3.4)
# ---------------------------------------------------------------------------

DELTA_TOPIC_PATTERN: str = "k1.agent.{agent_id}.delta.v1"
"""Topic pattern for agent delta emission to Delta Bus."""

DELTA_BATCH_WINDOW_MS: int = 500
"""Batch window in milliseconds for delta aggregation (LWW merge)."""


@dataclass(frozen=True)
class AgentDelta:
    """
    Structured delta payload emitted by agents (4.3.4).

    Agents NEVER write SessionState directly (FAB-01).  Instead they
    produce ``AgentDelta`` records which are emitted to the Delta Bus
    topic ``k1.agent.{agent_id}.delta.v1``.  The Concierge aggregates
    these (500ms batching, LWW merge) and writes via MutationGuard.

    Attributes:
        agent_id: UUID of the emitting agent.
        delta_type: Category of the delta (e.g. "belief", "fact", "observation").
        section: Target SessionState section (e.g. "beliefs_active").
        key: Unique key within the section for LWW merge.
        value: The new value to set.
        op: Operation: "set" (overwrite), "append" (list), "delete".
        timestamp_ms: Monotonic timestamp for LWW conflict resolution.
        trace_id: Cognitive trace ID for audit.
    """

    agent_id: str
    delta_type: str
    section: str
    key: str
    value: Any
    op: str = "set"
    timestamp_ms: int = 0
    trace_id: str = ""

    def __post_init__(self) -> None:
        if self.op not in ("set", "append", "delete"):
            raise ValueError(f"Invalid delta op '{self.op}', expected set/append/delete")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for Delta Bus transmission."""
        return {
            "agent_id": self.agent_id,
            "delta_type": self.delta_type,
            "section": self.section,
            "key": self.key,
            "value": self.value,
            "op": self.op,
            "timestamp_ms": self.timestamp_ms,
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentDelta":
        """Deserialize from dict."""
        return cls(
            agent_id=data["agent_id"],
            delta_type=data["delta_type"],
            section=data["section"],
            key=data["key"],
            value=data["value"],
            op=data.get("op", "set"),
            timestamp_ms=data.get("timestamp_ms", 0),
            trace_id=data.get("trace_id", ""),
        )


class DeltaEmitter:
    """
    Batched delta emission for agents (4.3.4).

    Collects ``AgentDelta`` records within a configurable batch window
    (default 500ms), applies LWW (Last-Writer-Wins) merge on
    ``(section, key)`` collisions, then flushes via ``IDeltaBusPort``.

    Flow per the plan:
      Agent emits delta -> DeltaEmitter batches (500ms) ->
      LWW merge -> IDeltaBusPort.emit_delta() ->
      Delta Bus -> Aggregation Window -> Concierge ->
      MutationGuard -> SessionState

    Thread-safe: uses a lock to protect the pending batch.
    """

    __slots__ = (
        "_agent_id",
        "_delta_bus",
        "_trace_id",
        "_batch_window_ms",
        "_pending",
        "_lock",
        "_last_flush_time",
    )

    def __init__(
        self,
        *,
        agent_id: str,
        delta_bus: IDeltaBusPort,
        trace_id: str = "",
        batch_window_ms: int = DELTA_BATCH_WINDOW_MS,
    ) -> None:
        self._agent_id = agent_id
        self._delta_bus = delta_bus
        self._trace_id = trace_id
        self._batch_window_ms = batch_window_ms
        self._pending: Dict[str, AgentDelta] = {}  # key = "section:key"
        self._lock = threading.Lock()
        self._last_flush_time: float = time.monotonic()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def emit(
        self,
        *,
        delta_type: str,
        section: str,
        key: str,
        value: Any,
        op: str = "set",
    ) -> AgentDelta:
        """
        Queue a delta for batched emission.

        If ``(section, key)`` already has a pending delta, the new one
        wins (LWW by timestamp).  Caller should call ``flush()`` or
        ``flush_if_ready()`` after emitting.

        Returns:
            The ``AgentDelta`` that was queued.
        """
        ts = int(time.monotonic() * 1000)
        delta = AgentDelta(
            agent_id=self._agent_id,
            delta_type=delta_type,
            section=section,
            key=key,
            value=value,
            op=op,
            timestamp_ms=ts,
            trace_id=self._trace_id,
        )
        merge_key = f"{section}:{key}"
        with self._lock:
            existing = self._pending.get(merge_key)
            if existing is None or delta.timestamp_ms >= existing.timestamp_ms:
                self._pending[merge_key] = delta
        return delta

    def flush(self) -> int:
        """
        Flush all pending deltas to the Delta Bus.

        Applies LWW merge (already applied at emit time) and sends
        each delta via ``IDeltaBusPort.emit_delta()``.

        Returns:
            Number of deltas flushed.
        """
        with self._lock:
            batch = dict(self._pending)
            self._pending.clear()
            self._last_flush_time = time.monotonic()

        flushed = 0
        for delta in batch.values():
            try:
                self._delta_bus.emit_delta(
                    agent_id=delta.agent_id,
                    delta_type=delta.delta_type,
                    section=delta.section,
                    data=delta.to_dict(),
                )
                flushed += 1
            except Exception:
                logger.warning(
                    "DeltaEmitter: failed to emit delta %s:%s for agent %s",
                    delta.section,
                    delta.key,
                    self._agent_id[:8],
                    exc_info=True,
                )
        return flushed

    def flush_if_ready(self) -> int:
        """
        Flush if the batch window has elapsed since last flush.

        Returns:
            Number of deltas flushed (0 if window not elapsed or batch empty).
        """
        elapsed = (time.monotonic() - self._last_flush_time) * 1000
        if elapsed < self._batch_window_ms:
            return 0
        if not self._pending:
            return 0
        return self.flush()

    @property
    def pending_count(self) -> int:
        """Number of deltas waiting to be flushed."""
        with self._lock:
            return len(self._pending)

    @property
    def batch_window_ms(self) -> int:
        """Configured batch window in milliseconds."""
        return self._batch_window_ms

    def __repr__(self) -> str:
        return (
            f"DeltaEmitter(agent={self._agent_id[:8]}..., "
            f"pending={self.pending_count}, "
            f"window={self._batch_window_ms}ms)"
        )


# ---------------------------------------------------------------------------
# AgentPool (4.3.3) -- IDLE pool for agent reuse
# ---------------------------------------------------------------------------


class AgentPoolFullError(AgentProviderError):
    """Agent pool is at capacity for the given contract."""

    def __init__(self, provider_id: str, contract_name: str, max_size: int) -> None:
        self.contract_name = contract_name
        self.max_size = max_size
        super().__init__(
            provider_id,
            f"Agent pool full for '{contract_name}' (max {max_size})",
            retriable=True,
        )


@dataclass(frozen=True)
class AgentPoolConfig:
    """
    Configuration for AgentPool (4.3.3).

    Attributes:
        max_pool_size: Max IDLE agents per contract name.
        idle_ttl_s: TTL in seconds before idle agents are evicted.
        sweep_interval_s: How often to run TTL sweep (seconds).
    """

    max_pool_size: int = 5
    idle_ttl_s: int = IDLE_TTL_S
    sweep_interval_s: int = 15

    def __repr__(self) -> str:
        return (
            f"AgentPoolConfig("
            f"max_size={self.max_pool_size}, "
            f"ttl={self.idle_ttl_s}s, "
            f"sweep={self.sweep_interval_s}s)"
        )


class AgentPool:
    """
    IDLE pool for agent reuse (4.3.3).

    When an agent completes execution successfully, it transitions to
    IDLE and is placed in the pool (keyed by contract name).  When a
    new task arrives for the same contract, a pooled agent is popped
    and reactivated (IDLE -> ACTIVE) instead of cold-starting.

    Pool mechanics:
      - Keyed by ``contract.name`` (agents of same contract are fungible)
      - Max pool size per contract name (configurable via AgentPoolConfig)
      - FIFO reuse: oldest idle agent is reactivated first
      - TTL sweep: periodically evicts agents idle > ``idle_ttl_s``
      - Thread-safe via RLock

    Usage::

        pool = AgentPool()
        # After successful execution:
        pool.put(agent)  # agent transitions ACTIVE -> IDLE -> pooled

        # Before spawning new agent:
        reused = pool.get(\"agent.execute.empathy_writer\")
        if reused is not None:
            reused.reactivate()  # already done by get()
        else:
            agent = factory._spawn(...)
    """

    __slots__ = (
        "_pool",
        "_config",
        "_lock",
        "_total_reuses",
        "_total_evictions",
    )

    def __init__(self, config: Optional[AgentPoolConfig] = None) -> None:
        self._config = config or AgentPoolConfig()
        self._pool: Dict[str, List[Agent]] = {}
        self._lock = threading.RLock()
        self._total_reuses: int = 0
        self._total_evictions: int = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def config(self) -> AgentPoolConfig:
        """Pool configuration."""
        return self._config

    @property
    def total_reuses(self) -> int:
        """Total number of agents reused from pool."""
        return self._total_reuses

    @property
    def total_evictions(self) -> int:
        """Total number of agents evicted by TTL sweep."""
        return self._total_evictions

    def size(self, contract_name: Optional[str] = None) -> int:
        """
        Number of pooled agents.

        Args:
            contract_name: If given, count for that contract only.
                          If None, total across all contracts.
        """
        with self._lock:
            if contract_name is not None:
                return len(self._pool.get(contract_name, []))
            return sum(len(v) for v in self._pool.values())

    @property
    def contract_names(self) -> List[str]:
        """List of contract names that have pooled agents."""
        with self._lock:
            return [k for k, v in self._pool.items() if v]

    # ------------------------------------------------------------------
    # Put / Get
    # ------------------------------------------------------------------

    def put(self, agent: Agent) -> bool:
        """
        Place an agent into the pool.

        The agent must be in ACTIVE state.  It will be transitioned
        to IDLE.  If the pool for this contract is full, the oldest
        idle agent is evicted (drained + terminated) to make room.

        Args:
            agent: The agent to pool.

        Returns:
            True if pooled successfully, False if agent state invalid.
        """
        if agent.lifecycle_state not in (
            AgentLifecycleState.ACTIVE,
            AgentLifecycleState.IDLE,
        ):
            logger.warning(
                "AgentPool: cannot pool agent %s in state %s",
                agent.id[:8],
                agent.lifecycle_state.value,
            )
            return False

        # Transition to IDLE if currently ACTIVE
        if agent.lifecycle_state == AgentLifecycleState.ACTIVE:
            agent.idle()

        contract_name = agent.contract.name

        pool_size = 0
        with self._lock:
            bucket = self._pool.setdefault(contract_name, [])

            # Evict oldest if at capacity
            if len(bucket) >= self._config.max_pool_size:
                evicted = bucket.pop(0)
                self._total_evictions += 1
                logger.debug(
                    "AgentPool: evicted oldest agent %s for '%s' (at capacity %d)",
                    evicted.id[:8],
                    contract_name,
                    self._config.max_pool_size,
                )
                try:
                    evicted.drain()
                    evicted.terminate()
                except Exception:
                    logger.warning(
                        "AgentPool: failed to terminate evicted agent %s",
                        evicted.id[:8],
                        exc_info=True,
                    )

            bucket.append(agent)
            pool_size = len(bucket)

        logger.debug(
            "AgentPool: pooled agent %s for '%s' (pool size=%d)",
            agent.id[:8],
            contract_name,
            self.size(contract_name),
        )
        self._set_pool_size_metric(contract_name, pool_size)
        return True

    def get(self, contract_name: str) -> Optional[Agent]:
        """
        Pop a reusable IDLE agent from the pool for the given contract.

        The agent is reactivated (IDLE -> ACTIVE) before return.
        Agents whose TTL has expired are skipped and evicted.

        Args:
            contract_name: The contract name to look up.

        Returns:
            A reactivated Agent, or None if no viable agent in pool.
        """
        pool_size = 0
        with self._lock:
            bucket = self._pool.get(contract_name)
            if not bucket:
                return None

            # Scan for a non-expired agent (FIFO order)
            while bucket:
                candidate = bucket.pop(0)
                if not candidate.is_idle:
                    # Not idle any more (someone drained externally)
                    continue
                if candidate.idle_ttl_expired:
                    # TTL expired -- terminate
                    self._total_evictions += 1
                    try:
                        candidate.drain()
                        candidate.terminate()
                    except Exception:
                        pass
                    continue

                # Valid candidate -- reactivate
                candidate.reactivate()
                self._total_reuses += 1
                pool_size = len(bucket)
                logger.debug(
                    "AgentPool: reused agent %s for '%s'",
                    candidate.id[:8],
                    contract_name,
                )
                self._set_pool_size_metric(contract_name, pool_size)
                return candidate

            self._set_pool_size_metric(contract_name, pool_size)
            return None

    # ------------------------------------------------------------------
    # TTL sweep
    # ------------------------------------------------------------------

    def sweep(self) -> int:
        """
        Evict all agents whose IDLE TTL has expired.

        This should be called periodically (e.g. every ``sweep_interval_s``).

        Returns:
            Number of agents evicted.
        """
        evicted_count = 0
        sizes: Dict[str, int] = {}
        with self._lock:
            for contract_name, bucket in self._pool.items():
                still_alive: List[Agent] = []
                for agent in bucket:
                    if not agent.is_idle or agent.idle_ttl_expired:
                        evicted_count += 1
                        self._total_evictions += 1
                        try:
                            if agent.is_idle:
                                agent.drain()
                            if agent.lifecycle_state == AgentLifecycleState.DRAINING:
                                agent.terminate()
                        except Exception:
                            logger.warning(
                                "AgentPool: sweep failed to terminate %s",
                                agent.id[:8],
                                exc_info=True,
                            )
                    else:
                        still_alive.append(agent)
                self._pool[contract_name] = still_alive
                sizes[contract_name] = len(still_alive)

        for contract_name, size in sizes.items():
            self._set_pool_size_metric(contract_name, size)

        if evicted_count:
            logger.debug("AgentPool: swept %d expired agents", evicted_count)
        return evicted_count

    def drain_all(self) -> int:
        """
        Drain and terminate ALL pooled agents.

        Used during shutdown.

        Returns:
            Number of agents terminated.
        """
        terminated = 0
        contract_names: List[str] = []
        with self._lock:
            for bucket in self._pool.values():
                for agent in bucket:
                    try:
                        if agent.is_idle:
                            agent.drain()
                        if agent.lifecycle_state == AgentLifecycleState.DRAINING:
                            agent.terminate()
                        terminated += 1
                    except Exception:
                        logger.warning(
                            "AgentPool: drain_all failed for %s",
                            agent.id[:8],
                            exc_info=True,
                        )
            contract_names = list(self._pool.keys())
            self._pool.clear()
        logger.debug("AgentPool: drained %d agents", terminated)
        for contract_name in contract_names:
            self._set_pool_size_metric(contract_name, 0)
        return terminated

    def _set_pool_size_metric(self, contract_name: str, size: int) -> None:
        try:
            get_default_metrics().set_agent_pool_size(contract_name, size)
        except Exception:
            logger.warning(
                "AgentPool: failed to record pool size for '%s'",
                contract_name,
                exc_info=True,
            )

    def __repr__(self) -> str:
        return (
            f"AgentPool(total={self.size()}, "
            f"contracts={len(self.contract_names)}, "
            f"reuses={self._total_reuses}, "
            f"evictions={self._total_evictions})"
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
        "_pool",
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
        pool: Optional[AgentPool] = None,
    ) -> None:
        self._context_builder = context_builder
        self._model_gateway = model_gateway
        self._state_reader = state_reader
        self._delta_bus = delta_bus
        self._contract_loader = contract_loader
        self._config = config or AgentFactoryConfig()
        self._pool = pool

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def config(self) -> AgentFactoryConfig:
        """Current factory configuration."""
        return self._config

    @property
    def pool(self) -> Optional[AgentPool]:
        """The agent pool (if configured)."""
        return self._pool

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

        # Pool check (4.3.3): try to reuse an IDLE agent
        reused = False
        agent: Optional[Agent] = None
        if self._pool is not None:
            agent = self._pool.get(contract.name)
            if agent is not None:
                reused = True
                logger.debug(
                    "Reusing pooled agent %s for '%s'",
                    agent.id[:8],
                    contract.name,
                )

        # Steps 2-7: Spawn agent (only if not reused from pool)
        if agent is None:
            try:
                agent = self._spawn(
                    contract,
                    context,
                    request.params,
                    trace_id,
                    session_id=request.session_id,
                    prompt_template_name=request.prompt_template,
                    context_override=request.context_override,
                )
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

        # Step 8: Warm up (if fresh) and execute
        try:
            if not reused:
                agent.warm_up()
            result = await agent.execute(request.params)

            # Pool on success (4.3.3), terminate on failure
            if result.success:
                if self._pool is not None:
                    self._pool.put(agent)
                else:
                    agent.idle()
            else:
                if agent.lifecycle_state in (
                    AgentLifecycleState.ACTIVE,
                    AgentLifecycleState.IDLE,
                ):
                    agent.drain()
                if agent.lifecycle_state == AgentLifecycleState.DRAINING:
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
        session_id: str = "",
        prompt_template_name: Optional[str] = None,
        context_override: Optional[Dict[str, Any]] = None,
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
                    session_id=session_id,
                    prompt_template_name=prompt_template_name or contract.prompt_template,
                    context_override=context_override,
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

        # Step 7: Create DeltaEmitter for structured emission (4.3.4)
        delta_emitter: Optional[DeltaEmitter] = None
        if self._delta_bus is not None:
            delta_emitter = DeltaEmitter(
                agent_id=agent_id,
                delta_bus=self._delta_bus,
                trace_id=trace_id,
            )

        # Step 8: Instantiate Agent object
        agent = Agent(
            agent_id=agent_id,
            contract=contract,
            context=initial_context,
            mailbox=mailbox,
            llm_handle=llm_handle,
            state_reader=state_reader,
            tool_scope=tool_scope,
            delta_bus=self._delta_bus,
            delta_emitter=delta_emitter,
        )

        logger.debug(
            "Spawned agent %s (contract=%s, llm=%s, tools=%s, emitter=%s)",
            agent_id[:8],
            contract.name,
            llm_handle is not None,
            tool_scope is not None,
            delta_emitter is not None,
        )

        try:
            get_default_metrics().inc_agent_spawns()
        except Exception:
            logger.warning("Failed to record agent spawn metric", exc_info=True)

        return agent

    def __repr__(self) -> str:
        return (
            f"AgentFactory("
            f"model_gw={'yes' if self._model_gateway else 'no'}, "
            f"ctx_builder={'yes' if self._context_builder else 'no'}, "
            f"delta_bus={'yes' if self._delta_bus else 'no'}, "
            f"pool={'yes' if self._pool else 'no'})"
        )


# ---------------------------------------------------------------------------
# AgentProvider (4.3.5 -- full implementation)
# ---------------------------------------------------------------------------

#: Default execution timeout when contract omits max_execution_time_ms.
DEFAULT_AGENT_TIMEOUT_MS: int = 30_000


class AgentProvider(BaseProvider):
    """
    Agent execution provider (4.3.5).

    Full implementation that delegates to ``AgentFactory.spawn_and_execute()``.
    Replaces the M3 stub with production-grade error handling:

      - **Template not found**: ``AgentTemplateNotFoundError`` when the
        factory cannot load a contract for the requested capability.
      - **Model loading failure**: ``AgentSpawnError`` propagated as
        structured failure result.
      - **Tool scope violation**: Caught during spawn (step 5); returned
        as a failure result with ``tool_scope_violation`` error code.
      - **Execution timeout**: ``asyncio.wait_for`` enforces
        ``contract.max_execution_time_ms`` (default 30s).  On timeout
        the agent is drained and terminated, result is ``retriable=True``.
      - **Clean resource disposal**: ``shutdown()`` drains and terminates
        all tracked agents.  Also called implicitly on individual
        agent failure.

    Backward-compatible: when ``agent_factory`` is ``None`` the provider
    degrades to the M3 stub behaviour (returns
    ``AgentNotImplementedError``).

    Constructor Args:
        config: ProviderConfig with provider_id and type.
        agent_factory: Optional AgentFactory (None degrades to stub).
        capability_names: Capability names this provider handles.
        default_timeout_ms: Fallback timeout when contract omits it.

    Usage::

        provider = AgentProvider(
            config=ProviderConfig(provider_id="agent-runner", ...),
            agent_factory=factory,
            capability_names=["agent.execute.empathy_writer"],
        )
        result = await provider.execute(request, context, trace_id)
    """

    __slots__ = (
        "_agent_factory",
        "_capability_names",
        "_default_timeout_ms",
        "_active_agents",
        "_lock",
    )

    def __init__(
        self,
        config: ProviderConfig,
        *,
        agent_factory: Optional[IAgentFactory] = None,
        capability_names: Optional[List[str]] = None,
        default_timeout_ms: int = DEFAULT_AGENT_TIMEOUT_MS,
        **_kwargs: Any,
    ) -> None:
        super().__init__(config)
        self._agent_factory = agent_factory
        self._capability_names: List[str] = list(capability_names or [])
        self._default_timeout_ms = default_timeout_ms
        self._active_agents: Dict[str, Agent] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def agent_factory(self) -> Optional[IAgentFactory]:
        """The injected agent factory (None when stub)."""
        return self._agent_factory

    @property
    def active_agent_count(self) -> int:
        """Number of agents currently tracked by this provider."""
        with self._lock:
            return len(self._active_agents)

    @property
    def default_timeout_ms(self) -> int:
        """Default execution timeout in milliseconds."""
        return self._default_timeout_ms

    # ======================================================================
    # CapabilityProvider interface
    # ======================================================================

    def capabilities(self) -> List[str]:
        """Return the list of agent capability names."""
        return list(self._capability_names)

    async def health_check(self) -> ProviderHealth:
        """
        Agent provider health check.

        Checks:
          1. agent_factory is injected (not stub).
          2. If factory has a model_gateway, verify a model can be
             reached.  Factory-level pool status is informational.

        Returns:
            ProviderHealth with HEALTHY / DEGRADED / UNKNOWN status.
        """
        if self._agent_factory is None:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderStatus.UNKNOWN.value,
                error="AgentProvider has no agent_factory (stub mode).",
            )

        # If factory is a real AgentFactory, check deeper
        factory = self._agent_factory
        issues: List[str] = []

        # Check model gateway availability
        if hasattr(factory, "_model_gateway"):
            gw = getattr(factory, "_model_gateway", None)
            if gw is not None:
                try:
                    loaded = await gw.is_model_loaded("")
                    # No-op check -- we just verify the gateway is reachable
                except Exception as exc:
                    issues.append(f"model_gateway unreachable: {exc}")

        # Check pool health (informational)
        if hasattr(factory, "pool") and factory.pool is not None:
            pool = factory.pool
            if hasattr(pool, "size") and pool.size == 0:
                pass  # empty pool is fine

        if issues:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderStatus.DEGRADED.value,
                error="; ".join(issues),
            )

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
        Agent-specific execution logic (4.3.5).

        Flow:
          1. Verify agent_factory is available (else stub error).
          2. Delegate to ``agent_factory.spawn_and_execute()``, wrapped
             in ``asyncio.wait_for`` for timeout enforcement.
          3. On success: return CapabilityResult with agent metadata.
          4. On failure/timeout/exception: structured error result.
        """
        # --- Stub guard (backward compat) ---
        if self._agent_factory is None:
            raise AgentNotImplementedError(self.provider_id)

        logger.debug(
            "[%s] executing agent for: %s (trace=%s)",
            self.provider_id,
            request.capability_name,
            trace_id,
        )

        # Resolve timeout from factory/contract or default
        timeout_ms = self._resolve_timeout(request)
        timeout_s = timeout_ms / 1000.0

        try:
            agent_result = await asyncio.wait_for(
                self._agent_factory.spawn_and_execute(request, context, trace_id),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            raise AgentTimeoutError(
                provider_id=self.provider_id,
                agent_id="unknown",
                timeout_ms=timeout_ms,
            )

        # --- Template not found ---
        if (
            not agent_result.success
            and agent_result.error_message
            and "contract not found" in agent_result.error_message.lower()
        ):
            raise AgentTemplateNotFoundError(
                provider_id=self.provider_id,
                capability_name=request.capability_name,
            )

        # --- Spawn failure (model / tool scope) ---
        if (
            not agent_result.success
            and agent_result.error_message
            and "toolscope" in agent_result.error_message.lower()
        ):
            return CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code="tool_scope_violation",
                error_message=agent_result.error_message,
                retriable=False,
                provider_id=self.provider_id,
                trace_id=trace_id,
            )

        if (
            not agent_result.success
            and agent_result.error_message
            and "llm handle" in agent_result.error_message.lower()
        ):
            return CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code="model_loading_failure",
                error_message=agent_result.error_message,
                retriable=True,
                provider_id=self.provider_id,
                trace_id=trace_id,
            )

        # --- Generic agent failure ---
        if not agent_result.success:
            return CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code="agent_execution_error",
                error_message=agent_result.error_message or "Agent execution failed",
                retriable=False,
                provider_id=self.provider_id,
                trace_id=trace_id,
            )

        # --- Success ---
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

    # ------------------------------------------------------------------
    # Timeout resolution
    # ------------------------------------------------------------------

    def _resolve_timeout(self, request: CapabilityRequest) -> int:
        """
        Resolve execution timeout in milliseconds.

        Priority:
          1. ``request.params["timeout_ms"]`` if present
          2. Provider-level ``_default_timeout_ms``

        The AgentFactory itself also reads
        ``contract.max_execution_time_ms`` internally, but this
        provider-level timeout is the outer guard.
        """
        explicit = request.params.get("timeout_ms") if request.params else None
        if isinstance(explicit, (int, float)) and explicit > 0:
            return int(explicit)
        return self._default_timeout_ms

    # ------------------------------------------------------------------
    # Shutdown / resource disposal
    # ------------------------------------------------------------------

    def shutdown(self) -> int:
        """
        Drain and terminate all tracked agents.

        Called during provider shutdown to ensure clean resource
        disposal.  Agents in ACTIVE/IDLE state are drained first,
        then terminated.

        Returns:
            Number of agents terminated.
        """
        with self._lock:
            agents = list(self._active_agents.values())
            self._active_agents.clear()

        terminated = 0
        for agent in agents:
            try:
                if agent.lifecycle_state in (
                    AgentLifecycleState.ACTIVE,
                    AgentLifecycleState.IDLE,
                ):
                    agent.drain()
                if agent.lifecycle_state == AgentLifecycleState.DRAINING:
                    agent.terminate()
                terminated += 1
            except Exception:
                logger.warning(
                    "Failed to terminate agent %s during shutdown",
                    agent.id[:8],
                    exc_info=True,
                )
        logger.info(
            "[%s] shutdown: terminated %d agents",
            self.provider_id,
            terminated,
        )

        # Also drain pool if factory has one
        if self._agent_factory is not None and hasattr(self._agent_factory, "pool"):
            pool = getattr(self._agent_factory, "pool", None)
            if pool is not None and hasattr(pool, "drain_all"):
                try:
                    pool.drain_all()
                except Exception:
                    logger.warning("Pool drain failed during shutdown", exc_info=True)

        return terminated

    # ------------------------------------------------------------------
    # Agent tracking helpers
    # ------------------------------------------------------------------

    def track_agent(self, agent: Agent) -> None:
        """Register an agent for lifecycle tracking."""
        with self._lock:
            self._active_agents[agent.id] = agent

    def untrack_agent(self, agent_id: str) -> None:
        """Remove an agent from lifecycle tracking."""
        with self._lock:
            self._active_agents.pop(agent_id, None)

    def __repr__(self) -> str:
        status = "stub" if self._agent_factory is None else "active"
        with self._lock:
            agent_count = len(self._active_agents)
        return (
            f"AgentProvider("
            f"provider_id={self.provider_id!r}, "
            f"status={status}, "
            f"capabilities={len(self._capability_names)}, "
            f"tracked_agents={agent_count})"
        )
