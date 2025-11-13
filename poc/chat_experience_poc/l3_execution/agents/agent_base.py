"""
Agent Base Class — Common functionality for all K1 agents.

All agents (Concierge, Specialists, Planner, Writers) inherit from AgentBase.
Provides shared capabilities:
  - Mailbox access (send/receive messages)
  - Lifecycle management (PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED)
  - Tool calling via Tool Registry
  - SessionState updates
  - User KG queries
  - Tracing with cognitive_trace_id

Subclasses must implement:
  - async process_message(message) - Handle incoming message

Optional lifecycle hooks (subclasses can override):
  - async on_warming() - Custom WARMING behavior
  - async on_active() - Custom ACTIVE behavior
  - async on_idle() - Custom IDLE behavior
  - async on_draining() - Custom DRAINING behavior
  - async on_terminated() - Cleanup

References:
  - docs/whiteboard/chat_experience.md - Agent architecture
  - ADR-0005 - Agent base capabilities
  - Epic 4.1.1 - Concierge implementation
"""

import asyncio
import time
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog
from l5_infrastructure.registries.prompt_registry import get_prompt_registry
from l5_infrastructure.registries.prompt_template_engine import get_prompt_template_engine
from l5_infrastructure.tool_call_handler import get_tool_call_handler


class AgentState(Enum):
    """Agent lifecycle states."""

    PENDING = "pending"  # Created, not yet ready
    WARMING = "warming"  # Resource validation, model loading
    ACTIVE = "active"  # Processing tasks, accepting work
    IDLE = "idle"  # No tasks, waiting (pooled for reuse)
    DRAINING = "draining"  # Finishing tasks, no new work
    TERMINATED = "terminated"  # Shut down, resources freed


class AgentBase(ABC):
    """
    Abstract base class for all K1 agents.

    Provides common functionality:
      - Mailbox communication (send/receive messages)
      - Lifecycle state management (6-state FSM)
      - Prompt Registry + Template Engine access
      - Groq client for LLM reasoning
      - Tool calling (placeholder for POC)
      - SessionState updates (placeholder for POC)
      - User KG queries (placeholder for POC)
      - Tracing with cognitive_trace_id

    Subclasses implement:
      - async process_message(message) - Main message handler

    Optional lifecycle hooks:
      - async on_warming() - Custom WARMING behavior
      - async on_active() - Custom ACTIVE behavior
      - async on_idle() - Custom IDLE behavior
      - async on_draining() - Custom DRAINING behavior
      - async on_terminated() - Cleanup
    """

    def __init__(
        self,
        agent_id: str,
        agent_type: str,
        session_id: str,
        groq_client: Any,
        mailbox: Optional[asyncio.Queue] = None,  # NEW: Accept mailbox from AgentFabric
        trace_id: Optional[str] = None,
    ):
        """
        Initialize agent.

        Args:
            agent_id: Unique agent identifier
            agent_type: Agent type (concierge, healthcare, finance, planner, memory_writer)
            session_id: Session ID for this conversation
            groq_client: Groq client for LLM calls
            mailbox: Optional mailbox from AgentFabric (if None, creates private queue for backward compatibility)
            trace_id: Optional trace ID (generated if not provided)
        """
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.session_id = session_id
        self.groq_client = groq_client
        self.trace_id = trace_id or self._generate_trace_id()

        # Lifecycle state (use private _state with property setter for enum coercion)
        self._state = AgentState.PENDING
        self.state_history: List[Dict[str, Any]] = [
            {"state": AgentState.PENDING, "timestamp": datetime.utcnow().isoformat()}
        ]

        # Infrastructure
        self.prompt_registry = get_prompt_registry()
        self.template_engine = get_prompt_template_engine()
        self.logger = structlog.get_logger(self.__class__.__name__)

        # Optional runtime references (set by coordinator or caller)
        # Used for resolving user_id from current SessionState when querying UserKG
        self.session_state_manager: Optional[Any] = None

        # Optional AgentFabric reference (for lifecycle notifications)
        self.agent_fabric: Optional[Any] = None

        # Mailbox (from AgentFabric or fallback to private queue for backward compatibility)
        if mailbox is not None:
            self.mailbox = mailbox
            self.logger.info(
                "Agent initialized with mailbox from AgentFabric",
                agent_id=self.agent_id,
                agent_type=self.agent_type,
            )
        else:
            # Backward compatibility: create private queue if no mailbox provided
            self.mailbox = asyncio.Queue()
            self.logger.info(
                "Agent initialized with private mailbox (backward compatibility)",
                agent_id=self.agent_id,
                agent_type=self.agent_type,
            )

        # Metrics
        self.metrics = {
            "messages_received": 0,
            "messages_sent": 0,
            "llm_calls": 0,
            "errors": 0,
            "total_latency_ms": 0.0,
        }

        self.logger.info(
            "Agent initialized",
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            session_id=self.session_id,
            trace_id=self.trace_id,
        )

    @staticmethod
    def _generate_trace_id() -> str:
        """Generate unique trace ID for request correlation."""
        return f"agent-{int(time.time() * 1000)}"

    # ========================================================================
    # STATE PROPERTY (with string → enum coercion)
    # ========================================================================

    @property
    def state(self) -> AgentState:
        """Get current agent state"""
        return self._state

    @state.setter
    def state(self, value: Any) -> None:
        """
        Set agent state with automatic coercion from string to AgentState enum.

        Args:
            value: AgentState enum, string ("pending", "active", etc.), or string value

        Raises:
            ValueError: If string value doesn't map to valid AgentState
        """
        if isinstance(value, AgentState):
            self._state = value
        elif isinstance(value, str):
            # Coerce string to enum
            try:
                # Try uppercase first (e.g., "PENDING")
                self._state = AgentState[value.upper()]
            except KeyError:
                # Try lowercase value matching (e.g., "pending" → AgentState.PENDING)
                try:
                    self._state = AgentState(value.lower())
                except ValueError:
                    raise ValueError(f"Invalid agent state string: {value}")
        else:
            raise TypeError(f"Agent state must be AgentState or str, got {type(value)}")

    # ========================================================================
    # LIFECYCLE STATE MANAGEMENT
    # ========================================================================

    async def transition_to(self, new_state: AgentState) -> None:
        """
        Transition to new lifecycle state.

        Validates transition, calls lifecycle hooks, logs change, notifies AgentFabric.

        Args:
            new_state: Target state

        Raises:
            ValueError: If transition not allowed
        """
        # Validate transition (simplified for POC - full validation in Milestone 2)
        if self.state == new_state:
            self.logger.debug(
                "State transition skipped (already in target state)",
                current_state=self.state.value,
            )
            return

        old_state = self.state
        self.state = new_state
        self.state_history.append({"state": new_state, "timestamp": datetime.utcnow().isoformat()})

        self.logger.info(
            "State transition",
            agent_id=self.agent_id,
            old_state=old_state.value,
            new_state=new_state.value,
        )

        # Notify AgentFabric of state transition (Issue 1.2.2 Step 3)
        if hasattr(self, "agent_fabric") and self.agent_fabric:
            try:
                await self.agent_fabric.transition_to(
                    agent_id=self.agent_id,
                    state=new_state.value,
                    trace_id=self.trace_id,
                )
                self.logger.debug(
                    "AgentFabric notified of state transition",
                    agent_id=self.agent_id,
                    new_state=new_state.value,
                )
            except Exception as e:
                self.logger.warning(
                    "Failed to notify AgentFabric of state transition",
                    agent_id=self.agent_id,
                    error=str(e),
                )

        # Call lifecycle hook
        if new_state == AgentState.WARMING:
            await self.on_warming()
        elif new_state == AgentState.ACTIVE:
            await self.on_active()
        elif new_state == AgentState.IDLE:
            await self.on_idle()
        elif new_state == AgentState.DRAINING:
            await self.on_draining()
        elif new_state == AgentState.TERMINATED:
            await self.on_terminated()

    # ========================================================================
    # LIFECYCLE HOOKS (Subclasses can override)
    # ========================================================================

    async def on_warming(self) -> None:
        """
        WARMING state hook - resource validation and model loading.

        Default: Log state entry.
        Subclasses: Override for custom WARMING behavior.
        """
        self.logger.info("Agent entering WARMING state", agent_id=self.agent_id)

    async def on_active(self) -> None:
        """
        ACTIVE state hook - agent ready for work.

        Default: Log state entry.
        Subclasses: Override for custom ACTIVE behavior (e.g., SSE connection).
        """
        self.logger.info("Agent entering ACTIVE state", agent_id=self.agent_id)

    async def on_idle(self) -> None:
        """
        IDLE state hook - agent waiting for reuse.

        Default: Log state entry.
        Subclasses: Override for custom IDLE behavior.
        """
        self.logger.info("Agent entering IDLE state", agent_id=self.agent_id)

    async def on_draining(self) -> None:
        """
        DRAINING state hook - finishing tasks, no new work.

        Default: Log state entry.
        Subclasses: Override for custom DRAINING behavior.
        """
        self.logger.info("Agent entering DRAINING state", agent_id=self.agent_id)

    async def on_terminated(self) -> None:
        """
        TERMINATED state hook - cleanup and shutdown.

        Default: Log state entry.
        Subclasses: Override for custom cleanup (close connections, etc.).
        """
        self.logger.info("Agent entering TERMINATED state", agent_id=self.agent_id)

    # ========================================================================
    # MESSAGE HANDLING (Abstract - Subclasses must implement)
    # ========================================================================

    @abstractmethod
    async def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming message (ABSTRACT METHOD).

        Subclasses must implement this to handle agent-specific logic.

        Args:
            message: Message dict with 'payload', 'sender_id', 'trace_id', etc.

        Returns:
            Response dict with 'content', 'status', etc.

        Raises:
            NotImplementedError: If subclass doesn't implement
        """
        raise NotImplementedError("Subclasses must implement process_message()")

    async def receive_message(self) -> Optional[Dict[str, Any]]:
        """
        Pull message from mailbox (simulated for POC).

        Returns:
            Message dict or None if mailbox empty

        Note: In full implementation, this would pull from actual mailbox queue.
        """
        try:
            message = await asyncio.wait_for(self.mailbox.get(), timeout=0.1)
            self.metrics["messages_received"] += 1
            self.logger.debug(
                "Message received",
                agent_id=self.agent_id,
                message_id=message.get("message_id"),
            )
            return message
        except asyncio.TimeoutError:
            return None

    async def send_message(
        self, receiver_id: str, payload: Dict[str, Any], priority: str = "STANDARD"
    ) -> None:
        """
        Send message to another agent (simulated for POC).

        Args:
            receiver_id: Target agent ID
            payload: Message payload
            priority: Message priority (URGENT, INTERACTIVE, STANDARD, BACKGROUND)

        Note: In full implementation, this would route via MailboxManager.
        """
        message = {
            "message_id": self._generate_trace_id(),
            "sender_id": self.agent_id,
            "receiver_id": receiver_id,
            "payload": payload,
            "priority": priority,
            "timestamp": datetime.utcnow().isoformat(),
            "trace_id": self.trace_id,
        }

        self.metrics["messages_sent"] += 1
        self.logger.info(
            "Message sent",
            agent_id=self.agent_id,
            receiver_id=receiver_id,
            message_id=message["message_id"],
        )

        # Simulated send (no actual routing in POC)
        # In full implementation: mailbox_manager.send(message)

    # ========================================================================
    # LLM INTERACTION (via Groq client + Prompt Registry)
    # ========================================================================

    async def call_llm(
        self,
        user_input: str,
        context_data: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Call LLM with agent's system prompt + user input.

        Fetches agent prompt from Prompt Registry, merges with context,
        sends to Groq client for LLM reasoning.

        Args:
            user_input: User message
            context_data: Optional context for template merging (tools, history, user_context)
            temperature: Optional temperature override
            max_tokens: Optional max_tokens override

        Returns:
            Dict with 'content', 'tokens_used', 'finish_reason', 'trace_id'

        Raises:
            GroqClientError: On LLM API failures
        """
        start_time = datetime.utcnow()

        try:
            # Fetch and render prompt
            if context_data is None:
                context_data = {}

            final_prompt = self.template_engine.render_prompt(
                agent_type=self.agent_type, context_data=context_data
            )

            # Get agent-specific temperature and max_tokens if not overridden
            prompt_template = self.prompt_registry.get_prompt(self.agent_type)
            temperature = temperature or prompt_template.temperature
            max_tokens = max_tokens or prompt_template.max_tokens

            # Build messages for LLM
            messages = [
                {"role": "system", "content": final_prompt},
                {"role": "user", "content": user_input},
            ]

            # Call Groq
            response = await self.groq_client.complete(
                messages=messages,
                agent_type=self.agent_type,
                temperature=temperature,
                max_tokens=max_tokens,
                trace_id=self.trace_id,
            )

            self.metrics["llm_calls"] += 1
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.metrics["total_latency_ms"] += latency_ms

            self.logger.info(
                "LLM call successful",
                agent_id=self.agent_id,
                agent_type=self.agent_type,
                tokens_used=response["tokens_used"],
                latency_ms=latency_ms,
            )

            return response

        except Exception as e:
            self.metrics["errors"] += 1
            self.logger.error(
                "LLM call failed",
                agent_id=self.agent_id,
                error=str(e),
            )
            raise

    # ========================================================================
    # TOOL CALLING (Real via ToolCallHandler → Mock MCP)
    # ========================================================================

    async def call_tool(self, tool_name: str, tool_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call an external tool via ToolCallHandler (routes to Mock MCP).

        Args:
            tool_name: Tool ID from Tool Registry (e.g., "web_search")
            tool_params: Tool parameters matching the tool schema

        Returns:
            Dict containing the tool server's response data. On success, returns the
            raw result payload from the mock MCP. On error, returns a dict with
            status="error" and error message.
        """
        try:
            handler = get_tool_call_handler()
            receipt, result = await handler.call_tool(
                tool_id=tool_name,
                parameters=tool_params,
                agent_id=self.agent_id,
                trace_id=self.trace_id,
            )

            if receipt.status == "success" and result is not None:
                self.logger.info(
                    "tool_call_success",
                    agent_id=self.agent_id,
                    tool_id=tool_name,
                    latency_ms=receipt.latency_ms,
                )
                return result

            # Error path
            self.logger.warning(
                "tool_call_failed",
                agent_id=self.agent_id,
                tool_id=tool_name,
                error=receipt.error,
            )
            return {"status": "error", "message": receipt.error or "Tool call failed"}
        except Exception as e:
            self.logger.error(
                "tool_call_exception",
                agent_id=self.agent_id,
                tool_id=tool_name,
                error=str(e),
            )
            return {"status": "error", "message": str(e)}

    # ========================================================================
    # SESSIONSTATE UPDATES (Placeholder for POC)
    # ========================================================================

    async def update_session_state(self, section: str, updates: Dict[str, Any]) -> None:
        """
        Update SessionState section (placeholder for POC).

        Args:
            section: SessionState section (Beliefs, Control, Scoreboard, Meta, etc.)
            updates: Field updates

        Note: In full implementation, this would update SessionStateManager.
        """
        self.logger.info(
            "SessionState update (simulated)",
            agent_id=self.agent_id,
            section=section,
            updates=updates,
        )

    # ========================================================================
    # USER KG QUERIES (Placeholder for POC)
    # ========================================================================

    async def query_user_kg(
        self, query_type: str, filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Query User KG for context.

        Supported query_type values:
        - get_profile
        - get_health_context (filters: {"days": int})
        - get_goals
        - get_preferences (filters: {"category": str | None})
        - get_routines
        - get_relationships
        - query_memories (filters: {"date_range": (start, end), "keywords": [str]})
        """
        from l5_infrastructure.user_kg import get_user_kg

        self.logger.info(
            "user_kg_query",
            agent_id=self.agent_id,
            query_type=query_type,
            filters=filters,
        )

        kg = get_user_kg()
        user_id = filters.get("user_id") if filters else None
        if not user_id:
            # Try to resolve user_id from active SessionState
            try:
                if hasattr(self, "session_state_manager") and self.session_state_manager:
                    session = self.session_state_manager.get_session(self.session_id)
                    if session and getattr(session, "user_id", None):
                        user_id = session.user_id
            except Exception as _e:
                # Fall through to default if resolution fails
                pass

        if not user_id:
            # Fallback to canonical POC user if still unresolved
            user_id = "user_001"

        try:
            if query_type == "get_profile":
                data = kg.get_user_profile(user_id)
            elif query_type == "get_health_context":
                days = (filters or {}).get("days", 30)
                data = kg.get_health_context(user_id, days=days)
            elif query_type == "get_goals":
                data = kg.get_active_goals(user_id)
            elif query_type == "get_preferences":
                category = (filters or {}).get("category")
                data = kg.get_preferences(user_id, category=category)
            elif query_type == "get_routines":
                data = kg.get_routines(user_id)
            elif query_type == "get_relationships":
                data = kg.get_relationships(user_id)
            elif query_type == "query_memories":
                date_range = (filters or {}).get("date_range")
                keywords = (filters or {}).get("keywords")
                data = kg.query_memories(user_id, date_range=date_range, keywords=keywords)
            else:
                return {
                    "status": "error",
                    "message": f"Unknown query_type: {query_type}",
                }

            return {
                "status": "success",
                "query_type": query_type,
                "data": data,
            }
        except Exception as e:
            self.logger.error(
                "user_kg_query_error",
                agent_id=self.agent_id,
                query_type=query_type,
                error=str(e),
            )
            return {"status": "error", "message": str(e)}

    # ========================================================================
    # METRICS & STATS
    # ========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """
        Get agent statistics.

        Returns:
            Dict with metrics: messages, LLM calls, errors, latency
        """
        avg_latency = (
            self.metrics["total_latency_ms"] / self.metrics["llm_calls"]
            if self.metrics["llm_calls"] > 0
            else 0.0
        )

        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "current_state": self.state.value,
            "messages_received": self.metrics["messages_received"],
            "messages_sent": self.metrics["messages_sent"],
            "llm_calls": self.metrics["llm_calls"],
            "errors": self.metrics["errors"],
            "avg_latency_ms": avg_latency,
            "state_history": self.state_history,
        }
