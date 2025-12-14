"""
Agent Fabric - Centralized Agent Lifecycle Orchestration

Implements Issue 1.2.1: Lifecycle orchestration for agent registration,
mailbox allocation, and state transitions.

Design:
- Wraps AgentFactory with metadata tracking and lifecycle event publishing
- Maintains agent registry with type, tools, prompt source, activity tracking
- Allocates mailboxes via MailboxManager singleton
- Publishes lifecycle events (agent.registered, agent.warming, agent.active, etc.) to DeltaBus
- Supports agent reuse pool (IDLE → ACTIVE transitions)
- Tracks metadata per agent for observability and reuse decisions

Architecture:
- agent_id → AgentMetadata (registry)
- Lifecycle transitions trigger DeltaBus events
- Metadata available for agent selection/reuse decisions
- Integrates with AgentFactory for actual spawn logic

References:
  - ADR-0005: Agent lifecycle and capabilities
  - chat_experience_poc_plan.md: Issue 1.2.1 (Lifecycle orchestration)
  - l3_execution/agents/agent_base.py: AgentBase FSM (PENDING→WARMING→ACTIVE→IDLE→DRAINING→TERMINATED)
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from l3_execution.agents.agent_base import AgentState

# Type definitions for circular imports
try:
    from l3_execution.agents.agent_base import AgentBase, AgentState
except ImportError:
    AgentBase = None  # type: ignore
    AgentState = None  # type: ignore

logger = structlog.get_logger(__name__)


# ========================================================================
# ERROR CLASSES
# ========================================================================


class FabricError(Exception):
    """Base exception for AgentFabric errors"""

    pass


class MailboxExhaustedError(FabricError):
    """Raised when all mailboxes are allocated"""

    pass


class AgentSpawnError(FabricError):
    """Raised when agent spawn fails"""

    pass


class AgentNotFoundError(FabricError):
    """Raised when agent_id not found in registry"""

    pass


class InvalidStateTransitionError(FabricError):
    """Raised when state transition is invalid"""

    pass


# ========================================================================
# DATA MODELS
# ========================================================================


@dataclass
class AgentMetadata:
    """Metadata for a registered agent"""

    agent_id: str
    agent_type: str
    state: Optional[str] = "PENDING"  # AgentState enum value
    session_id: Optional[str] = None
    tools: List[str] = field(default_factory=list)
    prompt_source: str = "system"  # "system" or "generated"
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    reuse_pool_key: Optional[str] = None  # For grouping reusable agents
    custom_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize metadata to dictionary"""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "state": self.state,
            "session_id": self.session_id,
            "tools": self.tools,
            "prompt_source": self.prompt_source,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "reuse_pool_key": self.reuse_pool_key,
            "custom_metadata": self.custom_metadata,
        }


# ========================================================================
# AGENT FABRIC
# ========================================================================


class AgentFabric:
    """
    Centralized Agent Lifecycle Orchestration

    Provides:
    1. Agent registration and discovery
    2. Mailbox allocation via MailboxManager
    3. Lifecycle state management with event publishing
    4. Agent metadata tracking for reuse decisions
    5. Integration with AgentFactory for spawning

    Usage:
        fabric = AgentFabric(mailbox_manager, deltabus, agent_factory, agent_registry, tool_registry)

        # Register existing agent
        metadata = await fabric.register_agent(
            agent_id="concierge_001",
            agent_type="concierge",
            agent_instance=concierge_agent,
            mailbox=mailbox
        )

        # Spawn new agent
        agent = await fabric.spawn_agent(agent_type="healthcare", session_id="session_123")

        # Transition state
        await fabric.transition_to(agent_id="healthcare_001", state="ACTIVE")

        # Discover agents
        healthcare_agents = fabric.get_agents_by_type("healthcare")
        active_agents = fabric.get_agents_by_state("ACTIVE")
    """

    def __init__(
        self,
        mailbox_manager: Any,
        deltabus: Any,
        agent_factory: Any,
        agent_registry: Optional[Dict[str, Any]] = None,
        tool_registry: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize Agent Fabric

        Args:
            mailbox_manager: MailboxManager singleton (Phase 2)
            deltabus: DeltaBus for event publishing (Phase 2)
            agent_factory: AgentFactory for agent spawning (Phase 6)
            agent_registry: Optional agent registry (default empty dict)
            tool_registry: Optional tool registry for metadata
            config: Optional configuration dict
                - max_agents_per_type: int (default 100)
                - idle_ttl_seconds: int (default 300)
                - mailbox_size: int (default 64)
                - enable_reuse_pool: bool (default True)
        """
        self.mailbox_manager = mailbox_manager
        self.deltabus = deltabus
        self.agent_factory = agent_factory
        self.agent_registry = agent_registry or {}
        self.tool_registry = tool_registry

        # Configuration
        self.config = config or {}
        self.max_agents_per_type = self.config.get("max_agents_per_type", 100)
        self.idle_ttl_seconds = self.config.get("idle_ttl_seconds", 300)
        self.mailbox_size = self.config.get("mailbox_size", 64)
        self.enable_reuse_pool = self.config.get("enable_reuse_pool", True)

        # Internal registry: agent_id → (agent_instance, AgentMetadata)
        self._agents: Dict[str, tuple] = {}  # agent_id → (agent, metadata)

        # Type index: agent_type → [agent_ids]
        self._agents_by_type: Dict[str, List[str]] = {}

        # State index: state → [agent_ids]
        self._agents_by_state: Dict[str, List[str]] = {}

        # Mailbox tracking: agent_id → mailbox
        self._mailboxes: Dict[str, Any] = {}

        # Reuse pool: agent_type → [agent_ids] (IDLE agents available for reuse)
        self._idle_pool: Dict[str, List[str]] = {}

        # Metrics
        self._metrics = {
            "total_registered": 0,
            "total_spawned": 0,
            "total_transitions": 0,
            "total_events_published": 0,
        }

        logger.info(
            "[AgentFabric] Initialized",
            max_agents_per_type=self.max_agents_per_type,
            idle_ttl_seconds=self.idle_ttl_seconds,
            reuse_pool_enabled=self.enable_reuse_pool,
        )

    # ========================================================================
    # REGISTRATION
    # ========================================================================

    async def register_agent(
        self,
        agent_id: str,
        agent_type: str,
        agent_instance: Any,
        mailbox: Any,
        session_id: Optional[str] = None,
        tools: Optional[List[str]] = None,
        prompt_source: str = "system",
        trace_id: Optional[str] = None,
    ) -> AgentMetadata:
        """
        Register an existing agent instance.

        Args:
            agent_id: Unique agent identifier
            agent_type: Agent type (concierge, healthcare, planner, etc.)
            agent_instance: Agent object (must have state attribute)
            mailbox: Mailbox for this agent
            session_id: Optional session ID
            tools: Optional list of tool names
            prompt_source: "system" or "generated"
            trace_id: Optional trace ID for logging

        Returns:
            AgentMetadata for the registered agent

        Raises:
            ValueError: If agent_id already registered
        """
        if agent_id in self._agents:
            raise ValueError(f"Agent already registered: {agent_id}")

        # Create metadata
        metadata = AgentMetadata(
            agent_id=agent_id,
            agent_type=agent_type,
            state=str(getattr(agent_instance, "state", "PENDING")),
            session_id=session_id,
            tools=tools or [],
            prompt_source=prompt_source,
        )

        # Store in registry
        self._agents[agent_id] = (agent_instance, metadata)
        self._mailboxes[agent_id] = mailbox

        # Update indexes
        if agent_type not in self._agents_by_type:
            self._agents_by_type[agent_type] = []
        self._agents_by_type[agent_type].append(agent_id)

        state = str(metadata.state)
        if state not in self._agents_by_state:
            self._agents_by_state[state] = []
        self._agents_by_state[state].append(agent_id)

        self._metrics["total_registered"] += 1

        logger.info(
            "[AgentFabric] Agent registered",
            agent_id=agent_id,
            agent_type=agent_type,
            session_id=session_id,
            trace_id=trace_id,
        )

        # Publish event
        await self._publish_lifecycle_event(
            agent_id=agent_id,
            event_type="agent.registered",
            payload={
                "agent_id": agent_id,
                "agent_type": agent_type,
                "session_id": session_id,
                "tools": tools or [],
            },
            trace_id=trace_id,
        )

        return metadata

    async def register_external_agent(
        self,
        agent_id: str,
        agent_type: str,
        agent_instance: Optional[Any] = None,
        trace_id: Optional[str] = None,
    ) -> None:
        """
        Register Tier-1 agent (Concierge/Proactive) that was created outside AgentFabric.

        This allows lifecycle tracking and state transitions for externally-managed agents.
        Does NOT take ownership of the agent's lifecycle.

        Args:
            agent_id: Agent's existing ID (e.g., "concierge_001")
            agent_type: Agent type ("concierge" or "proactive")
            agent_instance: Optional agent instance (for state queries)
            trace_id: Optional trace ID
        """
        if agent_id in self._agents:
            logger.warning(
                "[AgentFabric] External agent already registered",
                agent_id=agent_id,
                action="skipping",
            )
            return

        # Create read-only metadata
        metadata = AgentMetadata(
            agent_id=agent_id,
            agent_type=agent_type,
            state=str(getattr(agent_instance, "state", "PENDING")) if agent_instance else "PENDING",
            session_id="system_session",
            custom_metadata={"external": True, "read_only": True},
        )

        # Store in registry (with or without instance)
        self._agents[agent_id] = (agent_instance, metadata)

        # Update indexes
        if agent_type not in self._agents_by_type:
            self._agents_by_type[agent_type] = []
        self._agents_by_type[agent_type].append(agent_id)

        state = metadata.state or "PENDING"  # Ensure state is not None
        if state not in self._agents_by_state:
            self._agents_by_state[state] = []
        self._agents_by_state[state].append(agent_id)

        logger.info(
            "[AgentFabric] External agent registered (read-only)",
            agent_id=agent_id,
            agent_type=agent_type,
            trace_id=trace_id,
        )

    async def unregister_agent(self, agent_id: str, trace_id: Optional[str] = None) -> bool:
        """
        Unregister an agent.

        Args:
            agent_id: Agent to unregister
            trace_id: Optional trace ID

        Returns:
            True if successful, False if agent not found

        Raises:
            ValueError: If agent state is not TERMINATED or IDLE
        """
        if agent_id not in self._agents:
            logger.warning(f"[AgentFabric] Agent not found for unregistration: {agent_id}")
            return False

        agent_instance, metadata = self._agents[agent_id]

        # Verify agent is in valid state for unregistration
        state = str(getattr(agent_instance, "state", "TERMINATED"))
        if state not in ("TERMINATED", "IDLE"):
            logger.warning(
                f"[AgentFabric] Cannot unregister agent in state {state}: {agent_id}. "
                f"Must be TERMINATED or IDLE."
            )
            return False

        # Remove from registry
        del self._agents[agent_id]
        if agent_id in self._mailboxes:
            del self._mailboxes[agent_id]

        # Remove from indexes
        agent_type = metadata.agent_type
        if agent_id in self._agents_by_type.get(agent_type, []):
            self._agents_by_type[agent_type].remove(agent_id)

        if agent_id in self._agents_by_state.get(state, []):
            self._agents_by_state[state].remove(agent_id)

        # Remove from reuse pool if present
        if agent_type in self._idle_pool and agent_id in self._idle_pool[agent_type]:
            self._idle_pool[agent_type].remove(agent_id)

        logger.info(
            "[AgentFabric] Agent unregistered",
            agent_id=agent_id,
            agent_type=agent_type,
            trace_id=trace_id,
        )

        return True

    # ========================================================================
    # MAILBOX ALLOCATION
    # ========================================================================

    async def allocate_mailbox(self, agent_type: str, agent_id: str) -> Any:
        """
        Allocate a new mailbox for an agent.

        Args:
            agent_type: Type of agent (used for quota tracking)
            agent_id: Unique agent identifier (for mailbox assignment)

        Returns:
            Mailbox object from MailboxManager

        Raises:
            MailboxExhaustedError: If all mailboxes allocated for type
        """
        # Check quota for agent type
        active_count = len(self._agents_by_type.get(agent_type, []))
        if active_count >= self.max_agents_per_type:
            raise MailboxExhaustedError(
                f"Max agents of type {agent_type} reached: {active_count}/{self.max_agents_per_type}"
            )

        # Request mailbox from MailboxManager
        try:
            mailbox = await self.mailbox_manager.create_mailbox(
                agent_id=agent_id,
                capacity=self.mailbox_size,
            )
            logger.debug(
                "[AgentFabric] Mailbox allocated",
                agent_id=agent_id,
                agent_type=agent_type,
                mailbox_id=getattr(mailbox, "mailbox_id", "unknown"),
            )
            return mailbox
        except Exception as e:
            raise MailboxExhaustedError(f"Failed to allocate mailbox for {agent_type}: {str(e)}")

    # ========================================================================
    # AGENT SPAWNING
    # ========================================================================

    async def spawn_agent(
        self,
        agent_type: str,
        session_id: str,
        trace_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Spawn a new agent or reuse an idle one.

        Steps:
        1. Check reuse pool for idle agent (if enabled)
        2. If none, allocate mailbox
        3. Use AgentFactory.spawn_agent() to create new instance
        4. Register with metadata
        5. Publish lifecycle events

        Args:
            agent_type: Type of agent to spawn
            session_id: Session ID for agent
            trace_id: Optional trace ID
            **kwargs: Additional arguments for agent construction

        Returns:
            Spawned agent instance

        Raises:
            AgentSpawnError: If spawn fails
            MailboxExhaustedError: If mailbox allocation fails
        """
        try:
            # Step 1: Check reuse pool
            if self.enable_reuse_pool:
                idle_agent_id = await self._get_idle_agent_for_reuse(agent_type, session_id)
                if idle_agent_id:
                    # Reactivate idle agent
                    agent_instance, metadata = self._agents[idle_agent_id]
                    await self.transition_to(
                        agent_id=idle_agent_id,
                        state="ACTIVE",
                        trace_id=trace_id,
                    )
                    logger.info(
                        "[AgentFabric] Agent reused from pool",
                        agent_id=idle_agent_id,
                        agent_type=agent_type,
                        trace_id=trace_id,
                    )
                    self._metrics["total_spawned"] += 1
                    return agent_instance

            # Step 2: Generate agent_id (needed for mailbox creation)
            agent_id = f"{agent_type}_{uuid.uuid4().hex[:8]}"

            # Step 3: Allocate mailbox with agent_id
            mailbox = await self.allocate_mailbox(agent_type, agent_id)

            # Step 4: Use AgentFactory to spawn
            agent_instance = await self.agent_factory.spawn_agent(
                agent_type=agent_type,
                task_envelope=kwargs,
                session_id=session_id,
                trace_id=trace_id or "spawn_" + uuid.uuid4().hex[:8],
                mailbox=mailbox,  # Pass mailbox to AgentFactory
            )

            if not agent_instance:
                raise AgentSpawnError(f"AgentFactory failed to spawn {agent_type}")

            # Override agent_id on the instance to match mailbox
            agent_instance.agent_id = agent_id

            # Step 5: Register with fabric
            tools = kwargs.get("tools", [])
            await self.register_agent(
                agent_id=agent_id,
                agent_type=agent_type,
                agent_instance=agent_instance,
                mailbox=mailbox,
                session_id=session_id,
                tools=tools,
                trace_id=trace_id,
            )

            # Step 6: Start mailbox consumer loop (if agent has run() method)
            if hasattr(agent_instance, "run") and callable(agent_instance.run):
                consumer_task = asyncio.create_task(agent_instance.run())
                logger.info(
                    "[AgentFabric] Started mailbox consumer loop",
                    agent_id=agent_id,
                    agent_type=agent_type,
                )
                # Store task reference for cleanup
                if agent_id in self._agents:
                    _, metadata = self._agents[agent_id]
                    metadata.custom_metadata["consumer_task"] = consumer_task

            self._metrics["total_spawned"] += 1

            logger.info(
                "[AgentFabric] Agent spawned",
                agent_id=agent_id,
                agent_type=agent_type,
                session_id=session_id,
                trace_id=trace_id,
            )

            return agent_instance

        except Exception as e:
            logger.error(
                "[AgentFabric] Agent spawn failed",
                agent_type=agent_type,
                error=str(e),
                trace_id=trace_id,
            )
            raise AgentSpawnError(str(e))

    # ========================================================================
    # LIFECYCLE MANAGEMENT
    # ========================================================================

    async def transition_to(
        self,
        agent_id: str,
        state: str,
        trace_id: Optional[str] = None,
    ) -> None:
        """
        Transition agent to new state.

        Steps:
        1. Validate agent exists
        2. Call agent.transition_to(state)
        3. Update metadata and indexes
        4. Publish DeltaBus event

        Args:
            agent_id: Agent to transition
            state: New state (PENDING, WARMING, ACTIVE, IDLE, DRAINING, TERMINATED)
            trace_id: Optional trace ID

        Raises:
            AgentNotFoundError: If agent not found
        """
        if agent_id not in self._agents:
            raise AgentNotFoundError(f"Agent not found: {agent_id}")

        agent_instance, metadata = self._agents[agent_id]

        # Convert string to AgentState enum for agent transition
        try:
            state_enum = AgentState[state.upper()] if isinstance(state, str) else state
        except KeyError:
            raise InvalidStateTransitionError(f"Invalid state: {state}")

        # Call agent transition
        try:
            await agent_instance.transition_to(state_enum)
        except Exception as e:
            logger.error(
                "[AgentFabric] Transition failed",
                agent_id=agent_id,
                target_state=state,
                error=str(e),
            )
            raise InvalidStateTransitionError(str(e))

        # Update metadata
        old_state = metadata.state
        metadata.state = state
        metadata.last_activity = datetime.utcnow()

        # Update indexes
        if old_state and old_state in self._agents_by_state:
            if agent_id in self._agents_by_state[old_state]:
                self._agents_by_state[old_state].remove(agent_id)

        if state not in self._agents_by_state:
            self._agents_by_state[state] = []
        self._agents_by_state[state].append(agent_id)

        # Handle reuse pool transitions
        if state == "IDLE" and self.enable_reuse_pool:
            agent_type = metadata.agent_type
            if agent_type not in self._idle_pool:
                self._idle_pool[agent_type] = []
            if agent_id not in self._idle_pool[agent_type]:
                self._idle_pool[agent_type].append(agent_id)

        elif state in ("ACTIVE", "DRAINING", "TERMINATED"):
            # Remove from idle pool
            agent_type = metadata.agent_type
            if agent_type in self._idle_pool and agent_id in self._idle_pool[agent_type]:
                self._idle_pool[agent_type].remove(agent_id)

        self._metrics["total_transitions"] += 1

        logger.info(
            "[AgentFabric] Agent transitioned",
            agent_id=agent_id,
            old_state=old_state,
            new_state=state,
            trace_id=trace_id,
        )

        # Publish event
        event_type = f"agent.{state.lower()}"
        await self._publish_lifecycle_event(
            agent_id=agent_id,
            event_type=event_type,
            payload={
                "agent_id": agent_id,
                "old_state": old_state,
                "new_state": state,
                "agent_type": metadata.agent_type,
            },
            trace_id=trace_id,
        )

    # ========================================================================
    # DISCOVERY
    # ========================================================================

    def get_agent(self, agent_id: str) -> Optional[Any]:
        """Get agent by ID"""
        if agent_id in self._agents:
            return self._agents[agent_id][0]
        return None

    def get_agent_metadata(self, agent_id: str) -> Optional[AgentMetadata]:
        """Get agent metadata by ID"""
        if agent_id in self._agents:
            return self._agents[agent_id][1]
        return None

    def get_agents_by_type(self, agent_type: str) -> List[Any]:
        """Get all agents of given type"""
        agent_ids = self._agents_by_type.get(agent_type, [])
        return [self._agents[aid][0] for aid in agent_ids if aid in self._agents]

    def get_agents_by_state(self, state: str) -> List[Any]:
        """Get all agents in given state"""
        agent_ids = self._agents_by_state.get(state, [])
        return [self._agents[aid][0] for aid in agent_ids if aid in self._agents]

    async def _get_idle_agent_for_reuse(self, agent_type: str, session_id: str) -> Optional[str]:
        """Get idle agent for reuse (with TTL check)"""
        if agent_type not in self._idle_pool or not self._idle_pool[agent_type]:
            return None

        # Check TTL on oldest idle agent
        agent_id = self._idle_pool[agent_type][0]
        metadata = self.get_agent_metadata(agent_id)

        if not metadata:
            return None

        idle_duration = (datetime.utcnow() - metadata.last_activity).total_seconds()
        if idle_duration > self.idle_ttl_seconds:
            # Idle too long, return to pool
            await self.unregister_agent(agent_id)
            return None

        # Age is OK, return for reuse
        return agent_id

    # ========================================================================
    # METADATA MANAGEMENT
    # ========================================================================

    def set_metadata(self, agent_id: str, key: str, value: Any) -> None:
        """Set custom metadata on agent"""
        if agent_id not in self._agents:
            raise AgentNotFoundError(f"Agent not found: {agent_id}")

        _, metadata = self._agents[agent_id]
        metadata.custom_metadata[key] = value

    def get_metadata(self, agent_id: str) -> Dict[str, Any]:
        """Get all metadata for agent"""
        if agent_id not in self._agents:
            raise AgentNotFoundError(f"Agent not found: {agent_id}")

        _, metadata = self._agents[agent_id]
        return metadata.to_dict()

    # ========================================================================
    # EVENT PUBLISHING
    # ========================================================================

    async def _publish_lifecycle_event(
        self,
        agent_id: str,
        event_type: str,
        payload: Dict[str, Any],
        trace_id: Optional[str] = None,
    ) -> None:
        """Publish lifecycle event to DeltaBus"""
        if not self.deltabus:
            return

        try:
            # Import DeltaBusEvent to create proper event object
            from l4_runtime.deltabus.deltabus import DeltaBusEvent

            # Get session_id from payload or agent metadata
            session_id = payload.get("session_id", "unknown")
            if agent_id in self._agents:
                _, metadata = self._agents[agent_id]
                session_id = metadata.session_id or session_id

            # Create proper DeltaBusEvent object
            event = DeltaBusEvent(
                event_type=event_type,
                session_id=session_id,
                payload=payload,
                trace_id=trace_id or uuid.uuid4().hex[:12],
            )

            # Publish via DeltaBus (if available)
            if hasattr(self.deltabus, "publish"):
                self.deltabus.publish(event)
            elif hasattr(self.deltabus, "publish_async"):
                await self.deltabus.publish_async(event)

            self._metrics["total_events_published"] += 1

        except Exception as e:
            logger.warning(
                "[AgentFabric] Failed to publish lifecycle event",
                event_type=event_type,
                agent_id=agent_id,
                error=str(e),
            )

    # ========================================================================
    # HEALTH & SHUTDOWN
    # ========================================================================

    async def shutdown_all(self, trace_id: Optional[str] = None) -> None:
        """Gracefully shutdown all agents"""
        logger.info("[AgentFabric] Shutting down all agents...", trace_id=trace_id)

        # Cancel consumer tasks first
        for agent_id in list(self._agents.keys()):
            try:
                _, metadata = self._agents[agent_id]
                consumer_task = metadata.custom_metadata.get("consumer_task")
                if consumer_task and not consumer_task.done():
                    consumer_task.cancel()
                    logger.debug(
                        "[AgentFabric] Cancelled consumer task",
                        agent_id=agent_id,
                    )
            except Exception as e:
                logger.warning(
                    "[AgentFabric] Failed to cancel consumer task",
                    agent_id=agent_id,
                    error=str(e),
                )

        # Transition all agents to DRAINING
        for agent_id in list(self._agents.keys()):
            try:
                await self.transition_to(agent_id, "DRAINING", trace_id=trace_id)
            except Exception as e:
                logger.warning(
                    "[AgentFabric] Failed to drain agent",
                    agent_id=agent_id,
                    error=str(e),
                )

        # Transition to TERMINATED
        for agent_id in list(self._agents.keys()):
            try:
                await self.transition_to(agent_id, "TERMINATED", trace_id=trace_id)
            except Exception as e:
                logger.warning(
                    "[AgentFabric] Failed to terminate agent",
                    agent_id=agent_id,
                    error=str(e),
                )

        # Clear registry
        self._agents.clear()
        self._mailboxes.clear()
        self._agents_by_type.clear()
        self._agents_by_state.clear()
        self._idle_pool.clear()

        logger.info("[AgentFabric] Shutdown complete", trace_id=trace_id)

    def get_stats(self) -> Dict[str, Any]:
        """Get AgentFabric statistics"""
        return {
            **self._metrics,
            "agents_registered": len(self._agents),
            "agents_by_type": {atype: len(aids) for atype, aids in self._agents_by_type.items()},
            "agents_by_state": {state: len(aids) for state, aids in self._agents_by_state.items()},
            "idle_pool_size": {atype: len(aids) for atype, aids in self._idle_pool.items()},
        }
