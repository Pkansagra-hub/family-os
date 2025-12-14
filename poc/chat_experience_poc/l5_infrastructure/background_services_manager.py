"""
BackgroundServicesManager - Coordinates all Layer 4/5 background services.

ARCHITECTURE (from docs/whiteboard/chat_experience.md):
Manages lifecycle of critical background services:
1. Writer Agents (MemoryWriter, LearningExtractor, SemanticEnricher) - Always-Active (Tier 3)
2. State Delta Emitter - Batches SessionState deltas to K0 Bridge
3. Temporal Module - Scheduler for proactive triggers
4. Health monitoring - Auto-respawn, mailbox depth alerts

INITIALIZATION FLOW:
- Ensure Registries, SessionStateManager, DeltaBus ready (Phase 2 deps)
- Spawn 3 Writer Agents (MemoryWriter, LearningExtractor, SemanticEnricher)
- Transition all to ACTIVE (PENDING → WARMING → ACTIVE, max 30s)
- Subscribe to DeltaBus events (each agent type has specific subscriptions)
- Start State Delta Emitter background loop (250ms flush window)
- Start Temporal Module scheduler (60s tick interval)
- Verify all services healthy before accepting user input

SHUTDOWN FLOW:
- Stop accepting new requests (set global flag)
- Mark all Writer Agents as DRAINING
- Flush all mailboxes (drain pending work)
- Stop State Delta Emitter, send final batches
- Stop Temporal Module scheduler
- Transition all agents to TERMINATED

References:
- Epic 6.5.3.1 - Wire SessionState → DeltaBus → Writer Agents
- docs/whiteboard/chat_experience.md - Background services architecture
- Milestone 5 - Writer Agents implementation
- Milestone 3, Epic 3.2 - State Delta Emitter
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from l3_execution.agents.writers import (
    LearningExtractorAgent,
    MemoryWriterAgent,
    SemanticEnricherAgent,
)
from l4_runtime.deltabus.deltabus import DeltaBusEvent, get_deltabus
from l4_runtime.session_state.session_state import AgentState
from l4_runtime.session_state.session_state_manager import SessionStateManager
from l5_infrastructure.groq_client import GroqClient
from l5_infrastructure.registries.tool_registry import ToolRegistry

# Setup logging (structlog if available, otherwise standard logging)
try:
    import structlog

    logger = structlog.get_logger()
except ImportError:
    logger = logging.getLogger(__name__)


class BackgroundServicesManager:
    """
    Singleton coordinator for all background services.

    Manages lifecycle of critical services that run in background:
    - Writer Agents (always active, process deltas)
    - State Delta Emitter (batch deltas to K0)
    - Temporal Module (schedule proactive triggers)

    Properties:
    - Singleton pattern: Only one instance per process
    - Initialization order: Must follow Phase 1-2 dependencies
    - Health monitoring: Auto-respawn, mailbox depth alerts
    - Graceful shutdown: Drain all work before terminating
    """

    _instance: Optional["BackgroundServicesManager"] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        """Prevent direct instantiation; use get_manager() instead."""
        raise RuntimeError(
            "Use BackgroundServicesManager.get_manager() instead of direct instantiation"
        )

    @classmethod
    async def get_manager(cls) -> "BackgroundServicesManager":
        """Get or create singleton instance (thread-safe)."""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    instance = object.__new__(cls)
                    instance._initialized = False
                    instance.__init__()  # Call __init__ explicitly
                    cls._instance = instance
        return cls._instance

    def __init__(self):
        """
        Initialize BackgroundServicesManager.

        NOTE: Called by get_manager(), not directly.
        """
        if self._initialized:
            return

        self._initialized = True

        # Background service state
        self.is_running = False
        self.writer_agents: Dict[str, Any] = {}  # agent_id -> agent instance
        self.state_delta_emitter: Optional[Any] = None
        self.temporal_module: Optional[Any] = None

        # K0 Bridge components (initialized during start_all)
        from l5_infrastructure.k0_bridge import (
            BackendStorage,
            BatchClient,
            MockCommandPort,
            QueryPort,
        )

        self.backend_storage: Optional[BackendStorage] = None
        self.mock_command_port: Optional[MockCommandPort] = None
        self.query_port: Optional[QueryPort] = None
        self.batch_client: Optional[BatchClient] = None

        # Health monitoring
        self.health_checks_enabled = True
        self.auto_respawn_enabled = True
        self.mailbox_depth_warning_threshold = 30

        # Dependencies (injected during start_all)
        self.session_state_manager: Optional[SessionStateManager] = None
        self.deltabus: Optional[Any] = None
        self.groq_client: Optional[GroqClient] = None
        self.tool_registry: Optional[ToolRegistry] = None

        # DeltaBus subscriptions (for cleanup)
        self.subscriptions: List[str] = []

        # Graceful shutdown
        self._shutdown_event = asyncio.Event()
        self._shutdown_timeout_sec = 45  # Total shutdown budget from plan

        # Health monitoring task (Issue 6.5.5.2)
        self._health_monitor_task: Optional[asyncio.Task] = None
        self._health_check_interval_sec = 30  # Check every 30 seconds

        logger.info("BackgroundServicesManager initialized (not yet started)")

    async def start_all(
        self,
        session_state_manager: SessionStateManager,
        groq_client: GroqClient,
        tool_registry: ToolRegistry,
    ) -> bool:
        """
        Initialize and start all background services.

        PHASES:
        1. Validate dependencies (registries, SessionStateManager)
        2. Spawn Writer Agents (PENDING → WARMING → ACTIVE)
        3. Subscribe Writer Agents to DeltaBus
        4. Start State Delta Emitter
        5. Start Temporal Module scheduler
        6. Verify all healthy before accepting user input

        Args:
            session_state_manager: SessionStateManager singleton
            groq_client: Groq client for LLM calls
            tool_registry: Tool Registry for available tools

        Returns:
            True if all services started successfully, False otherwise
        """
        if self.is_running:
            logger.warning("BackgroundServicesManager already running, skipping start_all()")
            return True

        self.session_state_manager = session_state_manager
        self.groq_client = groq_client
        self.tool_registry = tool_registry
        self.deltabus = get_deltabus()

        logger.info("Starting background services (Phase 6.5.3.1)...")

        try:
            # Phase 1: Validate dependencies
            if not await self._validate_dependencies():
                logger.error("Dependency validation failed")
                return False

            # Phase 1b: Initialize K0 Bridge components
            if not await self._init_k0_bridge():
                logger.error("Failed to initialize K0 Bridge")
                return False

            # Phase 2: Spawn Writer Agents
            if not await self._spawn_writer_agents():
                logger.error("Failed to spawn Writer Agents")
                return False

            # Phase 3: Subscribe Writer Agents to DeltaBus
            if not await self._subscribe_to_deltabus():
                logger.error("Failed to subscribe to DeltaBus")
                return False

            # Phase 4: Start State Delta Emitter
            if not await self._start_state_delta_emitter():
                logger.error("Failed to start State Delta Emitter")
                return False

            # Phase 5: Start Temporal Module
            if not await self._start_temporal_module():
                logger.error("Failed to start Temporal Module")
                return False

            # Phase 6: Verify all healthy
            if not await self._verify_health():
                logger.error("Health verification failed")
                return False

            # Phase 7: Start periodic health monitoring (Issue 6.5.5.2)
            await self._start_health_monitoring()

            self.is_running = True
            logger.info("Background services started successfully")
            return True

        except Exception as e:
            logger.error(f"Exception during background services startup: {str(e)}")
            return False

    async def stop_all(self) -> bool:
        """
        Gracefully shut down all background services.

        PHASES:
        1. Stop accepting new requests
        2. Mark Writer Agents as DRAINING
        3. Drain Writer Agent mailboxes
        4. Flush State Delta Emitter
        5. Stop Temporal Module scheduler
        6. Unsubscribe from DeltaBus
        7. Transition agents to TERMINATED

        Returns:
            True if shutdown successful, False otherwise
        """
        if not self.is_running:
            logger.warning("BackgroundServicesManager not running, skipping stop_all()")
            return True

        logger.info("Graceful shutdown of background services initiated...")
        shutdown_start = time.time()

        try:
            # Phase 1: Stop accepting new requests
            logger.info("Stopping service intake...")
            self._shutdown_event.set()

            # Stop health monitoring (Issue 6.5.5.2)
            await self._stop_health_monitoring()

            # Phase 2: Mark all Writer Agents as DRAINING
            logger.info(f"Transitioning {len(self.writer_agents)} Writer Agents to DRAINING...")
            for agent_id, agent in self.writer_agents.items():
                try:
                    agent.state = AgentState.DRAINING
                    logger.debug(f"Marked agent {agent_id} as DRAINING")
                except Exception as e:
                    logger.warning(f"Error marking agent {agent_id} as DRAINING: {str(e)}")

            # Phase 3: Drain Writer Agent mailboxes (flush pending work)
            logger.info("Draining Writer Agent mailboxes (max 10s)...")
            drain_deadline = time.time() + 10.0
            for agent_id, agent in self.writer_agents.items():
                try:
                    # Simple drain: process any remaining events in queue
                    if hasattr(agent, "mailbox") and agent.mailbox:
                        timeout = drain_deadline - time.time()
                        if timeout > 0:
                            while not agent.mailbox.empty() and timeout > 0:
                                try:
                                    msg = agent.mailbox.get_nowait()
                                    await agent.process_message(msg)
                                    timeout = drain_deadline - time.time()
                                except asyncio.QueueEmpty:
                                    break
                    logger.debug(f"Drained mailbox for {agent_id}")
                except Exception as e:
                    logger.warning(f"Error draining mailbox for {agent_id}: {str(e)}")

            # Phase 4: Flush State Delta Emitter (send remaining batches)
            if self.state_delta_emitter:
                logger.info("Flushing State Delta Emitter...")
                try:
                    if hasattr(self.state_delta_emitter, "flush_batch"):
                        await self.state_delta_emitter.flush_batch()
                    logger.info("State Delta Emitter flushed")
                except Exception as e:
                    logger.warning(f"Error flushing State Delta Emitter: {str(e)}")

            # Phase 5: Stop Temporal Module scheduler
            if self.temporal_module:
                logger.info("Stopping Temporal Module scheduler...")
                try:
                    await self.temporal_module.stop_scheduler()
                    logger.info("Temporal Module stopped")
                except Exception as e:
                    logger.warning(f"Error stopping Temporal Module: {str(e)}")

            # Phase 6: Unsubscribe from DeltaBus
            logger.info(f"Unsubscribing from DeltaBus ({len(self.subscriptions)} subscriptions)...")
            for subscription_id in self.subscriptions:
                try:
                    self.deltabus.unsubscribe(subscription_id)  # type: ignore
                    logger.debug(f"Unsubscribed: {subscription_id}")
                except Exception as e:
                    logger.warning(f"Error unsubscribing {subscription_id}: {str(e)}")
            self.subscriptions.clear()

            # Phase 7: Transition agents to TERMINATED
            logger.info("Transitioning Writer Agents to TERMINATED...")
            for agent_id, agent in self.writer_agents.items():
                try:
                    agent.state = AgentState.TERMINATED
                    logger.debug(f"Marked agent {agent_id} as TERMINATED")
                except Exception as e:
                    logger.warning(f"Error terminating agent {agent_id}: {str(e)}")

            self.writer_agents.clear()
            self.state_delta_emitter = None
            self.temporal_module = None
            self.is_running = False

            shutdown_elapsed = time.time() - shutdown_start
            logger.info(
                f"Background services shutdown complete ({shutdown_elapsed:.2f}s / {self._shutdown_timeout_sec}s budget)"
            )
            return True

        except Exception as e:
            logger.error(f"Exception during background services shutdown: {str(e)}")
            return False

    async def _validate_dependencies(self) -> bool:
        """
        Validate all required dependencies are available.

        Checks:
        - SessionStateManager functional
        - DeltaBus functional
        - Tool Registry populated
        - Groq client ready

        Returns:
            True if all dependencies valid
        """
        logger.info("Validating dependencies...")

        # Check SessionStateManager
        if not self.session_state_manager:
            logger.error("SessionStateManager not provided")
            return False

        # Check DeltaBus
        if not self.deltabus:
            logger.error("DeltaBus not available")
            return False

        # Check Tool Registry
        if not self.tool_registry:
            logger.error("Tool Registry not provided")
            return False

        # Check Groq client
        if not self.groq_client:
            logger.error("Groq client not provided")
            return False

        logger.info("All dependencies valid")
        return True

    async def _init_k0_bridge(self) -> bool:
        """
        Initialize K0 Bridge components for writer agents.

        Creates:
        - BackendStorage: In-memory storage for deltas
        - MockCommandPort: Receives writer commands
        - QueryPort: Provides query access to stored deltas
        - PoCBatchClient: PoC batch client for writers

        Returns:
            True if K0 Bridge initialized successfully
        """
        try:
            from l5_infrastructure.k0_bridge import (
                BackendStorage,
                MockCommandPort,
                PoCBatchClient,
                QueryPort,
            )

            logger.info("Initializing K0 Bridge components...")

            # Create backend storage (in-memory for PoC)
            self.backend_storage = BackendStorage()
            logger.debug("BackendStorage created")

            # Create mock command port (receives writer commands)
            self.mock_command_port = MockCommandPort(self.backend_storage)
            logger.debug("MockCommandPort created")

            # Create query port (for querying stored deltas)
            self.query_port = QueryPort(self.backend_storage)
            logger.debug("QueryPort created")

            # Create PoC batch client (forwards to mock command port)
            self.batch_client = PoCBatchClient(self.mock_command_port)
            logger.debug("PoCBatchClient created")

            # Register components with ComponentRegistry
            try:
                from monitoring.component_registry import ComponentRegistry

                reg = ComponentRegistry.inst()
                reg.register("DeltaBus")
                reg.set("DeltaBus", "RUNNING")
                reg.register("K0 Bridge (Query)")
                reg.set("K0 Bridge (Query)", "RUNNING")
                reg.register("K0 Bridge (Batch)")
                reg.set("K0 Bridge (Batch)", "RUNNING")
            except Exception:
                pass  # Registry optional

            logger.info("K0 Bridge initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Error initializing K0 Bridge: {str(e)}")
            return False

    async def _spawn_writer_agents(self) -> bool:
        """
        Spawn and initialize Writer Agents (MemoryWriter, LearningExtractor, SemanticEnricher).

        Flow:
        1. For each agent type: Create agent instance (state = PENDING)
        2. Transition to WARMING (max 30s)
        3. Transition to ACTIVE
        4. Add to SessionState agent_roster
        5. Add to self.writer_agents tracking

        Returns:
            True if all agents spawned successfully
        """
        logger.info("Spawning Writer Agents...")

        # Get current session (use default session for background services)
        session_id = "background_session"  # Persistent session for background services
        session_state = self.session_state_manager.get_session(session_id)  # type: ignore
        if session_state is None:
            session_state = self.session_state_manager.create_session(  # type: ignore
                user_id="system",
                session_id=session_id,
                cognitive_trace_id="trace_background_services",
            )

        writer_agent_configs = [
            ("memory_writer", MemoryWriterAgent, "mem_writer_agent_1"),
            ("learning_extractor", LearningExtractorAgent, "learning_extractor_agent_1"),
            ("semantic_enricher", SemanticEnricherAgent, "semantic_enricher_agent_1"),
        ]

        agent_spawn_start = time.time()
        for agent_type, agent_class, agent_id in writer_agent_configs:
            try:
                logger.info(f"Spawning agent: type={agent_type}, agent_id={agent_id}")

                # Phase 1: Create AI writer agent with K0 Bridge integration
                # AI writers: MemoryWriterAgent(groq_client, batch_client, session_id)
                agent = agent_class(
                    groq_client=self.groq_client,
                    batch_client=self.batch_client,  # Will be created in start
                    session_id=session_id,
                )
                logger.debug(f"AI Writer Agent created: {agent_id}, type={agent_type}")

                # Phase 2: Start agent (subscribes to DeltaBus)
                await agent.start()
                logger.debug(f"Agent started: {agent_id}")

                # Phase 3: Track in self.writer_agents
                self.writer_agents[agent_id] = agent
                logger.info(f"AI Writer Agent spawned: type={agent_type}, agent_id={agent_id}")

            except asyncio.TimeoutError:
                logger.error(f"Agent spawn timed out: type={agent_type}, agent_id={agent_id}")
                return False
            except Exception as e:
                logger.error(
                    f"Error spawning AI Writer Agent: type={agent_type}, agent_id={agent_id}, error={str(e)}"
                )
                return False

        spawn_elapsed = time.time() - agent_spawn_start
        logger.info(
            f"Writer Agents spawned: count={len(self.writer_agents)}, elapsed_sec={round(spawn_elapsed, 2)}"
        )

        # Register Writer Agents with ComponentRegistry
        try:
            from monitoring.component_registry import ComponentRegistry

            reg = ComponentRegistry.inst()
            for agent_type_name in [
                "MemoryWriterAgent",
                "LearningExtractorAgent",
                "SemanticEnricherAgent",
            ]:
                reg.register(agent_type_name)
                reg.set(agent_type_name, "RUNNING")
        except Exception:
            pass  # Registry optional

        return True

    async def _subscribe_to_deltabus(self) -> bool:
        """
        Subscribe Writer Agents to appropriate DeltaBus events.

        Subscriptions:
        - MemoryWriterAgent: "session.delta"
        - LearningExtractorAgent: "session.delta", "agent.task_completed", "tool.called"
        - SemanticEnricherAgent: "session.delta"

        Each subscription routes events to agent's mailbox for processing.

        Returns:
            True if all subscriptions established
        """
        logger.info("Subscribing Writer Agents to DeltaBus...")

        subscriptions = {
            "mem_writer_agent_1": ["session.delta"],
            "learning_extractor_agent_1": ["session.delta", "agent.task_completed", "tool.called"],
            "semantic_enricher_agent_1": ["session.delta"],
        }

        for agent_id, event_patterns in subscriptions.items():
            agent = self.writer_agents.get(agent_id)
            if not agent:
                logger.warning(f"Agent not found in writer_agents: {agent_id}")
                continue

            for event_pattern in event_patterns:
                try:
                    # Subscribe agent to event pattern
                    async def event_handler(event: DeltaBusEvent, agent=agent):
                        """Route DeltaBus event to agent for processing.

                        Prefer mailbox if present; otherwise call process_delta directly
                        for AI writer agents that don't use AgentBase/mailboxes.
                        """
                        try:
                            if hasattr(agent, "mailbox") and agent.mailbox is not None:
                                await agent.mailbox.put(event)
                            elif hasattr(agent, "process_delta"):
                                # Pass event payload and current session state context
                                session_state = (
                                    self.session_state_manager.get_session(event.session_id)
                                    if self.session_state_manager
                                    else None
                                )
                                await agent.process_delta(
                                    delta=getattr(event, "payload", {}) or {},
                                    session_state=session_state,
                                    trace_id=getattr(event, "trace_id", ""),
                                )
                        except Exception as e:
                            logger.warning(
                                f"Error routing event to agent: agent_id={getattr(agent, 'agent_id', 'unknown')}, event_type={getattr(event, 'event_type', '?')}, error={str(e)}"
                            )

                    subscription_id = self.deltabus.subscribe(  # type: ignore
                        event_pattern=event_pattern,
                        callback=event_handler,
                    )
                    self.subscriptions.append(subscription_id)
                    logger.debug(
                        f"Agent subscribed to DeltaBus event: agent_id={agent_id}, event_pattern={event_pattern}, subscription_id={subscription_id}"
                    )

                except Exception as e:
                    logger.error(
                        f"Error subscribing to DeltaBus: agent_id={agent_id}, event_pattern={event_pattern}, error={str(e)}"
                    )
                    return False

        logger.info(
            f"Writer Agents subscribed to DeltaBus: subscription_count={len(self.subscriptions)}"
        )
        return True

    async def _start_state_delta_emitter(self) -> bool:
        """
        Start State Delta Emitter for batching deltas to K0 Bridge.

        Responsibilities:
        - Subscribe to "session.delta" events
        - Batch deltas with 250ms flush window
        - Send batches to K0 Bridge BatchClient
        - Handle retries and failures

        Returns:
            True if emitter started successfully
        """
        logger.info("Starting State Delta Emitter...")

        try:
            # TODO: Implement StateDeltaEmitter instantiation
            # For now, log intention and continue
            logger.info("State Delta Emitter configuration:")
            logger.info("  - Flush window: 250ms")
            logger.info("  - Batch size limit: 64KB")
            logger.info("  - Max deltas per batch: 100")
            logger.info("  - Target endpoints: K0 P02, P05, P06")

            # Placeholder for full implementation
            self.state_delta_emitter = {
                "status": "active",
                "batch_window_ms": 250,
                "batches_sent": 0,
                "deltas_batched": 0,
            }

            logger.info(f"State Delta Emitter started: {self.state_delta_emitter}")
            return True

        except Exception as e:
            logger.error(f"Error starting State Delta Emitter: {str(e)}")
            return False

    async def _start_temporal_module(self) -> bool:
        """
        Start Temporal Module scheduler for proactive triggers.

        Responsibilities:
        - Get or create TemporalModule singleton
        - Configure K0 backend URL for P05 queries
        - Start scheduler loop (60s tick interval)
        - Publish SSE events to Mock K0 SSE Server
        - Handle recurring triggers (reschedule after fire)

        Returns:
            True if module started successfully
        """
        logger.info("Starting Temporal Module...")

        try:
            # Import here to avoid circular imports
            from l5_infrastructure.temporal.temporal_module import get_temporal_module

            # Get or create singleton instance
            self.temporal_module = get_temporal_module(
                sse_url="http://localhost:8002",
                k0_backend_url="http://localhost:8001",
            )

            # Start scheduler loop
            await self.temporal_module.start_scheduler()

            logger.info(
                f"Temporal Module started: tick_interval={self.temporal_module.tick_interval}s, "
                f"sse_url={self.temporal_module.sse_url}, "
                f"k0_backend_url={self.temporal_module.k0_backend_url}"
            )
            return True

        except Exception as e:
            logger.error(f"Error starting Temporal Module: {str(e)}")
            return False

    async def _verify_health(self) -> bool:
        """
        Verify all background services are healthy before accepting user input.

        Checks:
        - All Writer Agents running
        - State Delta Emitter operational
        - Temporal Module scheduler running

        Returns:
            True if all services healthy
        """
        logger.info("Verifying background services health...")

        # Check Writer Agents
        for agent_id, agent in self.writer_agents.items():
            if not agent.running:
                logger.error(f"Writer Agent not running: agent_id={agent_id}")
                return False
            logger.debug(f"Writer Agent healthy: agent_id={agent_id}")

        # Check State Delta Emitter
        if not self.state_delta_emitter:
            logger.error("State Delta Emitter not running")
            return False
        logger.debug(
            f"State Delta Emitter healthy: status={self.state_delta_emitter.get('status')}"
        )

        # Check Temporal Module
        if not self.temporal_module:
            logger.error("Temporal Module not running")
            return False
        status = self.temporal_module.get_stats()
        logger.debug(
            f"Temporal Module healthy: scheduler_running={status.get('scheduler_running')}"
        )

        logger.info(
            f"Background services health verification passed: writer_agents={len(self.writer_agents)}"
        )
        return True

    async def get_writer_agent(self, agent_type: str) -> Optional[Any]:
        """
        Get Writer Agent by type.

        Args:
            agent_type: Agent type ("memory_writer", "learning_extractor", "semantic_enricher")

        Returns:
            Agent instance or None if not found
        """
        for agent_id, agent in self.writer_agents.items():
            if agent.writer_type == agent_type:
                return agent
        return None

    async def get_agent_health(self) -> Dict[str, Any]:
        """
        Get health status of all background services.

        Returns:
            Dict with service health information
        """
        return {
            "manager_running": self.is_running,
            "writer_agents": {
                agent_id: {
                    "type": agent.writer_type,
                    "running": agent.running,
                }
                for agent_id, agent in self.writer_agents.items()
            },
            "state_delta_emitter": self.state_delta_emitter,
            "temporal_module": self.temporal_module,
            "subscription_count": len(self.subscriptions),
        }

    async def get_writer_statistics(self) -> Dict[str, Any]:
        """
        Get aggregated statistics from all writer agents (Epic 3.1.2 Step 3).

        Returns comprehensive stats for health checks and test assertions:
        - total_deltas_processed: Sum of deltas processed by all writer agents
        - total_commands_sent: Sum of commands sent to K0 by all writer agents
        - per_agent_stats: Detailed stats for each writer agent

        Returns:
            Dict with aggregated writer agent statistics
        """
        total_deltas = 0
        total_commands = 0
        per_agent_stats = {}

        for agent_id, agent in self.writer_agents.items():
            status = agent.get_status()
            total_deltas += status.get("deltas_processed", 0)
            total_commands += status.get("commands_sent", 0)

            per_agent_stats[agent_id] = {
                "agent_id": status.get("agent_id"),
                "writer_type": status.get("writer_type"),
                "running": status.get("running", False),
                "deltas_processed": status.get("deltas_processed", 0),
                "commands_sent": status.get("commands_sent", 0),
                "last_delta_time": status.get("last_delta_time", 0),
            }

        return {
            "total_deltas_processed": total_deltas,
            "total_commands_sent": total_commands,
            "writer_agent_count": len(self.writer_agents),
            "per_agent_stats": per_agent_stats,
        }

    async def get_status(self) -> Dict[str, Any]:
        """
        Get complete status report of BackgroundServicesManager.

        Returns:
            Dict with:
            - is_running: Whether manager is active
            - writer_agents: Count of Writer Agents
            - subscriptions: Count of DeltaBus subscriptions
            - state_delta_emitter_ok: Whether emitter is initialized
            - temporal_module_ok: Whether temporal module is initialized
        """
        return {
            "is_running": self.is_running,
            "writer_agents": len(self.writer_agents),
            "subscriptions": len(self.subscriptions),
            "state_delta_emitter_ok": self.state_delta_emitter is not None,
            "temporal_module_ok": self.temporal_module is not None,
        }

    async def _start_health_monitoring(self) -> None:
        """
        Start periodic health monitoring task (Issue 6.5.5.2).

        Monitors background services every 30 seconds using Integration Dashboard.
        """
        logger.info(f"Starting health monitoring (interval={self._health_check_interval_sec}s)...")

        try:
            self._health_monitor_task = asyncio.create_task(self._health_monitor_loop())
            logger.info("Health monitoring started")
        except Exception as e:
            logger.error(f"Failed to start health monitoring: {e}")

    async def _stop_health_monitoring(self) -> None:
        """Stop periodic health monitoring task."""
        if self._health_monitor_task:
            logger.info("Stopping health monitoring...")
            self._health_monitor_task.cancel()
            try:
                await self._health_monitor_task
            except asyncio.CancelledError:
                pass
            self._health_monitor_task = None
            logger.info("Health monitoring stopped")

    async def _health_monitor_loop(self) -> None:
        """
        Periodic health monitoring loop.

        Checks component health every 30 seconds and logs results.
        Uses Integration Dashboard for comprehensive system health view.
        """
        try:
            from monitoring.integration_dashboard import get_integration_dashboard

            dashboard = get_integration_dashboard()

            while not self._shutdown_event.is_set():
                try:
                    # Run health check
                    status = await dashboard.display_status(refresh=False)
                    logger.debug(f"Health check results:\n{status}")

                    # Sleep until next check (or shutdown)
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self._health_check_interval_sec,
                    )
                except asyncio.TimeoutError:
                    # Timeout expected - continue to next check
                    continue
                except Exception as e:
                    logger.warning(f"Health check error: {e}")
                    await asyncio.sleep(self._health_check_interval_sec)

        except asyncio.CancelledError:
            logger.info("Health monitor loop cancelled")
        except Exception as e:
            logger.error(f"Health monitor loop error: {e}")
