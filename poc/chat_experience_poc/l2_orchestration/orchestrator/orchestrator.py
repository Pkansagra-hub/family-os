"""
Orchestrator - 3-Phase Contract Net Protocol Implementation

Pure Actor (NO LLM) for deterministic agent selection and task coordination.
Implements Smith 1980 Contract Net Protocol with 3 phases:
  - Phase 1: Negotiation (Task Announcement & Bidding) - <50ms P95
  - Phase 2: Selection (MADM Weighted Scoring) - <5ms P95
  - Phase 3: Execution (Single/Multi-Step with Saga) - Variable

Based on:
  - ADR-0006a: Contract Net Protocol Phase 1 (Negotiation)
  - ADR-0006b: Multi-Criteria Decision Making (MADM)
  - ADR-0006c: DAG Execution with barriers
  - chat_experience.md: Orchestrator 3-phase detailed flow
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog
from l3_execution.agents.agent_base import AgentState
from l4_runtime.deltabus.deltabus import DeltaBusEvent, get_deltabus

logger = structlog.get_logger()


class TaskType(Enum):
    """Task classification types"""

    QUERY = "query"  # Simple query requiring single agent
    PLANNING = "planning"  # Complex task requiring Planner
    TOOL_EXECUTION = "tool_execution"  # Direct tool execution


class TaskStatus(Enum):
    """Task execution status"""

    PENDING = "pending"
    NEGOTIATING = "negotiating"
    SELECTING = "selecting"
    EXECUTING = "executing"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"


@dataclass
class TaskAnnouncement:
    """
    Task announcement broadcast to candidate agents

    Attributes:
        task_id: Unique task identifier
        task_type: Type of task (query, planning, tool_execution)
        required_tools: List of tool names needed
        budget: Time and cost constraints
        deadline_ms: Bidding deadline (50ms)
        user_context: Context from User KG
        trace_id: Cognitive trace identifier
        user_input: Original user input
    """

    task_id: str
    task_type: TaskType
    required_tools: List[str]
    budget: Dict[str, Any]  # {time_ms: int, cost_credits: float}
    deadline_ms: int
    user_context: Dict[str, Any]
    trace_id: str
    user_input: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class Proposal:
    """
    Agent bid proposal in response to TaskAnnouncement

    Attributes:
        agent_id: Bidding agent identifier
        confidence: Confidence score (0.0-1.0, from 4 factors)
        estimated_latency_ms: Predicted execution time
        estimated_cost: Predicted cost in credits
        can_parallelize: Whether agent can handle parallel execution
        message: Explanation of suitability
        factor_breakdown: Confidence factor details for explainability
    """

    agent_id: str
    confidence: float
    estimated_latency_ms: int
    estimated_cost: float
    can_parallelize: bool
    message: str
    factor_breakdown: Dict[str, float] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class TaskAssignment:
    """
    Task assignment sent to winning agent

    Attributes:
        task_id: Task identifier
        agent_id: Winning agent identifier
        task_announcement: Full task context
        deadline_ms: Execution deadline
        priority: Message priority (INTERACTIVE = 2)
    """

    task_id: str
    agent_id: str
    task_announcement: TaskAnnouncement
    deadline_ms: int
    priority: int = 2  # INTERACTIVE priority


@dataclass
class TaskResult:
    """
    Task execution result

    Attributes:
        task_id: Task identifier
        status: Execution status (success, partial, failure)
        result: Output data
        latency_ms: Actual execution time
        agents_used: List of agents involved
        receipts: Tool call receipts
        error: Error message if failure
    """

    task_id: str
    status: TaskStatus
    result: Dict[str, Any]
    latency_ms: int
    agents_used: List[str]
    receipts: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


class Orchestrator:
    """
    Pure Actor orchestrator implementing 3-Phase Contract Net Protocol

    NO LLM - deterministic coordination only. Coordinates agent selection
    and task execution using Smith 1980 Contract Net Protocol.

    Performance Budgets:
      - Phase 1 (Negotiation): <50ms P95
      - Phase 2 (Selection): <5ms P95
      - Phase 3 (Execution): Variable (50ms-120s)
    """

    def __init__(
        self,
        agent_registry: Dict[str, Any],
        tool_registry: Dict[str, Any],
        session_state: Any,
        agent_factory: Any,
        mailbox_manager: Any,
        mailbox: Any,  # Orchestrator's own mailbox from AgentFabric
        session_state_manager: Optional[Any] = None,  # Epic 3.1 Issue 3.1.1
    ):
        """
        Initialize Orchestrator

        Args:
            agent_registry: Registry of available agent types and capabilities
            tool_registry: Registry of available tools and their schemas
            session_state: Current session state
            agent_factory: Factory for spawning new agents
            mailbox_manager: Manager for agent mailboxes
            mailbox: Orchestrator's mailbox for receiving task requests
            session_state_manager: SessionStateManager for delta-based updates (Epic 3.1)
        """
        self.agent_registry = agent_registry
        self.tool_registry = tool_registry
        self.session_state = session_state
        self.agent_factory = agent_factory
        self.mailbox_manager = mailbox_manager
        self.mailbox = mailbox
        self.session_state_manager = session_state_manager  # Epic 3.1 Issue 3.1.1
        self.deltabus = get_deltabus()

        # Active tasks tracking
        self.active_tasks: Dict[str, TaskAnnouncement] = {}
        self.task_proposals: Dict[str, List[Proposal]] = {}

        # Metrics
        self.metrics = {
            "tasks_received": 0,
            "phase1_latency_ms": [],
            "proposals_collected": [],
            "fallback_triggered": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
        }

        logger.info("orchestrator_initialized")

    async def run(self) -> None:
        """
        Main orchestrator run loop - consumes tasks from mailbox

        Mailbox-driven orchestration following AgentFabric lifecycle.
        Processes task requests from mailbox and coordinates 3-phase execution.

        Lifecycle: WARMING → ACTIVE → IDLE → DRAINING → TERMINATED
        """
        logger.info("orchestrator_run_started")

        try:
            while True:
                # Check if mailbox still exists (orchestrator not terminated)
                if not self.mailbox:
                    logger.warning("orchestrator_mailbox_closed")
                    break

                # Receive message from orchestrator mailbox (blocking)
                message = await self.mailbox.receive()

                if message is None:
                    # Mailbox closed or drained
                    logger.info("orchestrator_mailbox_drained")
                    break

                # Publish agent.task_received event
                await self._publish_agent_event(
                    event_type="agent.task_received",
                    agent_id="orchestrator",
                    state=AgentState.ACTIVE,
                    task_id=message.message_id,
                    trace_id=message.payload.get("trace_id", "unknown"),
                    session_id=message.payload.get("session_id", "default"),
                )

                logger.info(
                    "orchestrator_message_received",
                    message_id=message.message_id,
                    priority=message.priority.name if hasattr(message, "priority") else "UNKNOWN",
                    trace_id=message.payload.get("trace_id"),
                )

                # Process orchestration task
                try:
                    task_result = await self._process_orchestration_task(message.payload)

                    # Publish response to DeltaBus for await_response()
                    response_event = DeltaBusEvent(
                        event_type=f"response.{message.message_id}",
                        session_id=message.payload.get("session_id", "default"),
                        payload={
                            "message_id": message.message_id,
                            "task_id": task_result.task_id,
                            "status": task_result.status.value,
                            "result": task_result.result,
                            "latency_ms": task_result.latency_ms,
                            "agents_used": task_result.agents_used,
                            "receipts": task_result.receipts,
                            "error": task_result.error,
                            "trace_id": message.payload.get("trace_id"),
                        },
                        timestamp=datetime.utcnow(),
                        trace_id=message.payload.get("trace_id", "unknown"),
                    )
                    self.deltabus.publish(response_event)

                    # Publish agent.task_completed event
                    await self._publish_agent_event(
                        event_type="agent.task_completed",
                        agent_id="orchestrator",
                        state=AgentState.ACTIVE,
                        task_id=task_result.task_id,
                        trace_id=message.payload.get("trace_id", "unknown"),
                        session_id=message.payload.get("session_id", "default"),
                        result_status=task_result.status.value,
                        latency_ms=task_result.latency_ms,
                    )

                    logger.info(
                        "orchestrator_task_completed",
                        message_id=message.message_id,
                        task_id=task_result.task_id,
                        status=task_result.status.value,
                        latency_ms=task_result.latency_ms,
                        trace_id=message.payload.get("trace_id"),
                    )

                except Exception as e:
                    logger.error(
                        "orchestrator_task_error",
                        message_id=message.message_id,
                        error=str(e),
                        trace_id=message.payload.get("trace_id"),
                    )

                    # Publish error response
                    error_event = DeltaBusEvent(
                        event_type=f"response.{message.message_id}",
                        session_id=message.payload.get("session_id", "default"),
                        payload={
                            "message_id": message.message_id,
                            "status": "error",
                            "error": str(e),
                            "trace_id": message.payload.get("trace_id"),
                        },
                        timestamp=datetime.utcnow(),
                        trace_id=message.payload.get("trace_id", "unknown"),
                    )
                    self.deltabus.publish(error_event)

                    # Publish agent.task_completed with error
                    await self._publish_agent_event(
                        event_type="agent.task_completed",
                        agent_id="orchestrator",
                        state=AgentState.ACTIVE,
                        task_id=message.message_id,
                        trace_id=message.payload.get("trace_id", "unknown"),
                        session_id=message.payload.get("session_id", "default"),
                        result_status="error",
                        error=str(e),
                    )

        except asyncio.CancelledError:
            logger.info("orchestrator_run_cancelled")
            raise
        except Exception as e:
            logger.error("orchestrator_run_error", error=str(e))
            raise

    async def _publish_agent_event(
        self,
        event_type: str,
        agent_id: str,
        state: AgentState,
        task_id: str,
        trace_id: str,
        session_id: str = "default",
        result_status: Optional[str] = None,
        latency_ms: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Publish agent lifecycle event to DeltaBus

        Args:
            event_type: Event type (agent.task_received, agent.task_completed)
            agent_id: Agent identifier
            state: Current agent state
            task_id: Task identifier
            trace_id: Cognitive trace ID
            session_id: Session identifier
            result_status: Task result status (for task_completed)
            latency_ms: Task latency (for task_completed)
            error: Error message (for task_completed with error)
        """
        event = DeltaBusEvent(
            event_type=event_type,
            session_id=session_id,
            payload={
                "agent_id": agent_id,
                "agent_type": "orchestrator",
                "state": state.value,
                "task_id": task_id,
                "trace_id": trace_id,
                "timestamp": time.time(),
            },
            timestamp=datetime.utcnow(),
            trace_id=trace_id,
        )

        # Add optional fields for task_completed
        if result_status:
            event.payload["result_status"] = result_status
        if latency_ms:
            event.payload["latency_ms"] = latency_ms
        if error:
            event.payload["error"] = error

        self.deltabus.publish(event)

        logger.debug(
            "orchestrator_agent_event_published",
            event_type=event_type,
            agent_id=agent_id,
            task_id=task_id,
            trace_id=trace_id,
        )

    async def _publish_orchestration_event(
        self,
        phase: str,
        status: str,
        task_id: str,
        trace_id: str,
        session_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Publish orchestration phase event to DeltaBus

        Emits events for 3-phase coordination lifecycle:
        - orchestration.negotiation (start, complete)
        - orchestration.selection (start, complete)
        - orchestration.execution (start, complete)

        Args:
            phase: Phase name (negotiation, selection, execution)
            status: Phase status (start, complete, error)
            task_id: Task identifier
            trace_id: Cognitive trace ID
            session_id: Session identifier
            metadata: Optional phase-specific metadata (proposal counts, selected agent, etc.)
        """
        event = DeltaBusEvent(
            event_type=f"orchestration.{phase}",
            session_id=session_id,
            payload={
                "phase": phase,
                "status": status,
                "task_id": task_id,
                "trace_id": trace_id,
                "timestamp": time.time(),
                "metadata": metadata or {},
            },
            timestamp=datetime.utcnow(),
            trace_id=trace_id,
        )

        self.deltabus.publish(event)

        logger.debug(
            "orchestrator_phase_event_published",
            phase=phase,
            status=status,
            task_id=task_id,
            trace_id=trace_id,
        )

    async def _process_orchestration_task(self, task_envelope: Dict[str, Any]) -> TaskResult:
        """
        Process orchestration task (renamed from execute_task)

        Internal method called by run() loop to handle task execution.
        Orchestrates complete 3-phase workflow with event publishing.

        Args:
            task_envelope: Task request with requirements and context

        Returns:
            TaskResult with execution outcome
        """
        # Delegate to execute_task (will add phase event publishing there)
        return await self.execute_task(task_envelope)

    async def execute_task(self, task_envelope: Dict[str, Any]) -> TaskResult:
        """
        Main entry point for task execution

        Orchestrates complete 3-phase workflow:
          1. Negotiation: Broadcast announcement, collect proposals
          2. Selection: Score proposals, select best agent
          3. Execution: Coordinate task execution

        Args:
            task_envelope: Task request with requirements and context

        Returns:
            TaskResult with execution outcome
        """
        start_time = time.time()
        task_id = str(uuid.uuid4())

        self.metrics["tasks_received"] += 1

        logger.info(
            "orchestrator_task_received",
            task_id=task_id,
            task_type=task_envelope.get("task_type"),
            trace_id=task_envelope.get("trace_id"),
        )

        try:
            # Parse task requirements
            task_announcement = self._parse_task_requirements(task_id, task_envelope)
            self.active_tasks[task_id] = task_announcement

            # Phase 1: Negotiation (<50ms P95 budget)
            proposals = await self._phase1_negotiation(task_announcement)

            if not proposals:
                # No proposals received - task failed
                logger.warning(
                    "orchestrator_no_proposals",
                    task_id=task_id,
                    trace_id=task_announcement.trace_id,
                )
                self.metrics["tasks_failed"] += 1

                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.FAILURE,
                    result={},
                    latency_ms=int((time.time() - start_time) * 1000),
                    agents_used=[],
                    error="No agents available to handle task",
                )

            logger.info(
                "orchestrator_phase1_complete",
                task_id=task_id,
                proposal_count=len(proposals),
                trace_id=task_announcement.trace_id,
            )

            # Phase 2: Selection (<5ms P95 budget)
            selected_agent, task_assignment = await self._phase2_selection(
                proposals, task_announcement
            )

            if not selected_agent or not task_assignment:
                # Selection failed
                logger.error(
                    "orchestrator_selection_failed",
                    task_id=task_id,
                    trace_id=task_announcement.trace_id,
                )
                self.metrics["tasks_failed"] += 1

                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.FAILURE,
                    result={},
                    latency_ms=int((time.time() - start_time) * 1000),
                    agents_used=[],
                    error="Agent selection failed",
                )

            logger.info(
                "orchestrator_phase2_complete",
                task_id=task_id,
                selected_agent=selected_agent,
                trace_id=task_announcement.trace_id,
            )

            # Phase 3: Execution (Variable budget: 50ms-120s)
            task_result = await self._phase3_execution(selected_agent, task_assignment, start_time)

            logger.info(
                "orchestrator_phase3_complete",
                task_id=task_id,
                status=task_result.status.value,
                latency_ms=task_result.latency_ms,
                trace_id=task_announcement.trace_id,
            )

            self.metrics["tasks_completed"] += 1

            # Publish task.completed event for writer agents and K0 notifications
            task_completed_event = DeltaBusEvent(
                event_type="task.completed",
                session_id="default",  # TODO: Extract from task_envelope
                payload={
                    "task_id": task_id,
                    "status": task_result.status.value,
                    "result": task_result.result,
                    "latency_ms": task_result.latency_ms,
                    "agents_used": task_result.agents_used,
                    "receipts": task_result.receipts,
                    "error": task_result.error,
                    "trace_id": task_announcement.trace_id,
                    "timestamp": time.time(),
                },
                timestamp=datetime.utcnow(),
                trace_id=task_announcement.trace_id,
            )
            self.deltabus.publish(task_completed_event)

            logger.debug(
                "orchestrator_task_completed_event_published",
                task_id=task_id,
                status=task_result.status.value,
                trace_id=task_announcement.trace_id,
            )

            return task_result

        except Exception as e:
            logger.error(
                "orchestrator_task_error",
                task_id=task_id,
                error=str(e),
                trace_id=task_envelope.get("trace_id"),
            )
            self.metrics["tasks_failed"] += 1

            return TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILURE,
                result={},
                latency_ms=int((time.time() - start_time) * 1000),
                agents_used=[],
                error=str(e),
            )

    def _parse_task_requirements(
        self, task_id: str, task_envelope: Dict[str, Any]
    ) -> TaskAnnouncement:
        """
        Parse task envelope into structured TaskAnnouncement

        Extracts:
          - Required tools from task description
          - Task type classification
          - Budget constraints
          - User context from User KG

        Args:
            task_id: Generated task identifier
            task_envelope: Raw task request

        Returns:
            Structured TaskAnnouncement
        """
        # Extract task type
        task_type_str = task_envelope.get("task_type", "query")
        task_type = TaskType(task_type_str)

        # Extract required tools (simple keyword matching for POC)
        user_input = task_envelope.get("user_input", "")
        required_tools = self._extract_required_tools(user_input, task_type)

        # Extract budget (defaults if not specified)
        budget = task_envelope.get(
            "budget", {"time_ms": 5000, "cost_credits": 0.1}  # Default 5s  # Default cost
        )

        # Extract user context (would query User KG in full implementation)
        user_context = task_envelope.get("user_context", {})

        return TaskAnnouncement(
            task_id=task_id,
            task_type=task_type,
            required_tools=required_tools,
            budget=budget,
            deadline_ms=50,  # 50ms bidding deadline
            user_context=user_context,
            trace_id=task_envelope.get("trace_id", str(uuid.uuid4())),
            user_input=user_input,
        )

    def _extract_required_tools(self, user_input: str, task_type: TaskType) -> List[str]:
        """
        Extract required tools from user input using keyword matching

        POC implementation uses simple pattern matching.
        Production would use LLM or more sophisticated NLP.

        Args:
            user_input: User's input text
            task_type: Classified task type

        Returns:
            List of required tool names
        """
        tools = []
        input_lower = user_input.lower()

        # Health-related queries
        if any(
            kw in input_lower for kw in ["pt", "physical therapy", "recovery", "pain", "medication"]
        ):
            tools.append("query_k0_health")

        # Finance-related queries
        if any(kw in input_lower for kw in ["budget", "expense", "spending", "savings", "bill"]):
            tools.append("query_k0_finance")

        # Search/research queries
        if any(kw in input_lower for kw in ["search", "find", "look up", "research"]):
            tools.append("web_search")

        # User KG queries (always available)
        if not tools:  # Default tool
            tools.append("query_user_kg")

        return tools

    async def _phase1_negotiation(self, task_announcement: TaskAnnouncement) -> List[Proposal]:
        """
        Phase 1: Negotiation - Task Announcement & Bidding

        Workflow:
          1. Identify capable agents (registry + active roster)
          2. Broadcast task announcement to candidates
          3. Collect proposals with 50ms deadline
          4. Handle fallback if no proposals

        Performance Budget: <50ms P95

        Args:
            task_announcement: Task to announce

        Returns:
            List of agent proposals
        """
        phase1_start = time.time()

        # Publish orchestration.negotiation (start)
        await self._publish_orchestration_event(
            phase="negotiation",
            status="start",
            task_id=task_announcement.task_id,
            trace_id=task_announcement.trace_id,
            session_id="default",  # TODO: Extract from task_announcement
            metadata={"required_tools": task_announcement.required_tools},
        )

        logger.info(
            "orchestrator_phase1_start",
            task_id=task_announcement.task_id,
            required_tools=task_announcement.required_tools,
            trace_id=task_announcement.trace_id,
        )

        # Step 1: Identify capable agents
        candidate_agents = self._identify_capable_agents(task_announcement)

        if not candidate_agents:
            logger.warning(
                "orchestrator_no_capable_agents",
                task_id=task_announcement.task_id,
                required_tools=task_announcement.required_tools,
                trace_id=task_announcement.trace_id,
            )
            # Attempt fallback
            return await self._handle_no_proposals_fallback(task_announcement)

        logger.info(
            "orchestrator_candidates_identified",
            task_id=task_announcement.task_id,
            candidate_count=len(candidate_agents),
            candidates=candidate_agents,
            trace_id=task_announcement.trace_id,
        )

        # Step 2: Broadcast task announcement
        await self._broadcast_task_announcement(task_announcement, candidate_agents)

        # Step 3: Collect proposals (50ms deadline)
        proposals = await self._collect_proposals(
            task_announcement,
            candidate_agents,
            timeout=task_announcement.deadline_ms / 1000.0,  # Convert to seconds
        )

        # Step 4: Handle no proposals (fallback)
        if not proposals:
            logger.warning(
                "orchestrator_no_proposals_received",
                task_id=task_announcement.task_id,
                candidates_notified=len(candidate_agents),
                trace_id=task_announcement.trace_id,
            )
            proposals = await self._handle_no_proposals_fallback(task_announcement)

        # Record metrics
        phase1_latency = int((time.time() - phase1_start) * 1000)
        self.metrics["phase1_latency_ms"].append(phase1_latency)
        self.metrics["proposals_collected"].append(len(proposals))

        # Publish orchestration.negotiation (complete)
        await self._publish_orchestration_event(
            phase="negotiation",
            status="complete",
            task_id=task_announcement.task_id,
            trace_id=task_announcement.trace_id,
            session_id="default",  # TODO: Extract from task_announcement
            metadata={
                "proposal_count": len(proposals),
                "candidate_count": len(candidate_agents),
                "phase1_latency_ms": phase1_latency,
            },
        )

        logger.info(
            "orchestrator_phase1_complete",
            task_id=task_announcement.task_id,
            proposal_count=len(proposals),
            phase1_latency_ms=phase1_latency,
            trace_id=task_announcement.trace_id,
        )

        return proposals

    def _identify_capable_agents(self, task_announcement: TaskAnnouncement) -> List[str]:
        """
        Identify agents capable of handling task

        Checks:
          1. Agent Registry: Which agent types have required tools?
          2. Agent Roster: Which agents are already ACTIVE in session?
          3. Spawnable agents: Which types can be spawned?

        Args:
            task_announcement: Task requirements

        Returns:
            List of capable agent identifiers (type or instance ID)
        """
        capable_agents = []
        required_tools = set(task_announcement.required_tools)

        # Check Agent Registry for agent types with required tools
        for agent_type, agent_info in self.agent_registry.items():
            agent_tools = set(agent_info.get("tools", []))

            # Check if agent has all required tools
            if required_tools.issubset(agent_tools):
                # Check if agent already active in session
                active_agent_id = self._find_active_agent(agent_type)
                if active_agent_id:
                    capable_agents.append(active_agent_id)
                else:
                    # Agent type is spawnable
                    capable_agents.append(f"type:{agent_type}")

        return capable_agents

    def _find_active_agent(
        self, agent_type: str, session_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Find active agent of given type in session

        Queries SessionState.Control.agent_roster for ACTIVE agents via SessionStateManager.

        Args:
            agent_type: Agent type to find
            session_id: Session ID (optional, required for production queries)

        Returns:
            Agent ID if found, None otherwise
        """
        # Epic 3.1 Issue 3.1.1: Use SessionStateManager to query control.agent_roster
        if self.session_state_manager and session_id:
            try:
                control_section = self.session_state_manager.get_section(session_id, "control")
                if control_section:
                    agent_roster = control_section.get("agent_roster", {})
                    # Find ACTIVE agent of given type
                    for agent_id, agent_info in agent_roster.items():
                        if (
                            agent_info.get("agent_type") == agent_type
                            and agent_info.get("state") == "ACTIVE"
                        ):
                            return agent_id
            except Exception as e:
                logger.warning(
                    "failed_to_query_agent_roster",
                    error=str(e),
                    agent_type=agent_type,
                    session_id=session_id,
                )

        # POC fallback: Return None (no agents active yet)
        return None

    async def _broadcast_task_announcement(
        self, task_announcement: TaskAnnouncement, candidate_agents: List[str]
    ) -> None:
        """
        Broadcast task announcement to candidate agents

        Sends TaskAnnouncement to each candidate's mailbox with
        INTERACTIVE priority (non-blocking fire-and-forget).

        Args:
            task_announcement: Task to announce
            candidate_agents: List of agent IDs or types
        """
        logger.info(
            "orchestrator_broadcasting_announcement",
            task_id=task_announcement.task_id,
            candidate_count=len(candidate_agents),
            trace_id=task_announcement.trace_id,
        )

        # POC: Log announcement (no actual mailbox sending)
        # Production: Send to mailbox_manager for each candidate
        for agent_id in candidate_agents:
            logger.debug(
                "orchestrator_announcement_sent",
                task_id=task_announcement.task_id,
                agent_id=agent_id,
                priority="INTERACTIVE",
                trace_id=task_announcement.trace_id,
            )

        # Initialize proposal collection for this task
        self.task_proposals[task_announcement.task_id] = []

    async def _collect_proposals(
        self,
        task_announcement: TaskAnnouncement,
        candidate_agents: List[str],
        timeout: float = 0.05,  # 50ms default
    ) -> List[Proposal]:
        """
        Collect agent proposals with deadline

        Uses asyncio.wait_for to enforce 50ms deadline.
        Early exit if all expected agents respond.

        Args:
            task_announcement: Task announcement
            candidate_agents: Expected agents
            timeout: Collection deadline in seconds

        Returns:
            List of received proposals
        """
        task_id = task_announcement.task_id
        expected_count = len(candidate_agents)

        logger.info(
            "orchestrator_collecting_proposals",
            task_id=task_id,
            expected_count=expected_count,
            timeout_ms=int(timeout * 1000),
            trace_id=task_announcement.trace_id,
        )

        try:
            # POC: Simulate proposal collection
            # Production: Wait for mailbox responses
            await asyncio.wait_for(
                self._wait_for_proposals(task_id, expected_count), timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(
                "orchestrator_proposal_timeout",
                task_id=task_id,
                received_count=len(self.task_proposals.get(task_id, [])),
                expected_count=expected_count,
                trace_id=task_announcement.trace_id,
            )

        proposals = self.task_proposals.get(task_id, [])

        logger.info(
            "orchestrator_proposals_collected",
            task_id=task_id,
            received_count=len(proposals),
            expected_count=expected_count,
            trace_id=task_announcement.trace_id,
        )

        return proposals

    async def _wait_for_proposals(self, task_id: str, expected_count: int) -> None:
        """
        Wait for proposals to arrive (with early exit)

        Polls task_proposals dict until all expected agents respond
        or timeout occurs.

        Args:
            task_id: Task identifier
            expected_count: Number of expected proposals
        """
        # POC: No actual proposals arrive, so timeout will occur
        # Production: Check mailbox for incoming proposals
        while len(self.task_proposals.get(task_id, [])) < expected_count:
            await asyncio.sleep(0.001)  # 1ms poll interval

    async def _handle_no_proposals_fallback(
        self, task_announcement: TaskAnnouncement
    ) -> List[Proposal]:
        """
        Handle fallback when no proposals received

        4-Tier Fallback Strategy:
          1. Tier 1: Hire new agent from Agent Factory
          2. Tier 2: Simplify task (reduce tool count)
          3. Tier 3: Wait 100ms, retry announcement
          4. Tier 4: Graceful degradation (return empty)

        Args:
            task_announcement: Original task

        Returns:
            List of proposals (may be empty if all fallbacks fail)
        """
        self.metrics["fallback_triggered"] += 1

        logger.warning(
            "orchestrator_fallback_triggered",
            task_id=task_announcement.task_id,
            trace_id=task_announcement.trace_id,
        )

        # Tier 1: Try to spawn new agent
        if hasattr(self, "agent_factory") and self.agent_factory:
            logger.info(
                "orchestrator_fallback_tier1_spawn",
                task_id=task_announcement.task_id,
                trace_id=task_announcement.trace_id,
            )
            # POC: Don't actually spawn (Agent Factory may not be ready)
            # Production: Call agent_factory.spawn_agent()

        # Tier 2: Simplify task (reduce required tools)
        if len(task_announcement.required_tools) > 1:
            logger.info(
                "orchestrator_fallback_tier2_simplify",
                task_id=task_announcement.task_id,
                original_tools=task_announcement.required_tools,
                trace_id=task_announcement.trace_id,
            )
            # Reduce to most critical tool
            task_announcement.required_tools = [task_announcement.required_tools[0]]
            # Retry with simplified task
            candidate_agents = self._identify_capable_agents(task_announcement)
            if candidate_agents:
                await self._broadcast_task_announcement(task_announcement, candidate_agents)
                proposals = await self._collect_proposals(task_announcement, candidate_agents)
                if proposals:
                    return proposals

        # Tier 3: Wait and retry
        logger.info(
            "orchestrator_fallback_tier3_retry",
            task_id=task_announcement.task_id,
            trace_id=task_announcement.trace_id,
        )
        await asyncio.sleep(0.1)  # Wait 100ms
        candidate_agents = self._identify_capable_agents(task_announcement)
        if candidate_agents:
            await self._broadcast_task_announcement(task_announcement, candidate_agents)
            proposals = await self._collect_proposals(task_announcement, candidate_agents)
            if proposals:
                return proposals

        # Tier 4: Graceful degradation
        logger.error(
            "orchestrator_fallback_tier4_failed",
            task_id=task_announcement.task_id,
            trace_id=task_announcement.trace_id,
        )
        return []

    async def _phase2_selection(
        self, proposals: List[Proposal], task_announcement: TaskAnnouncement
    ) -> Tuple[Optional[str], Optional[TaskAssignment]]:
        """
        Phase 2: Selection - MADM Weighted Scoring & Tie-Breaking

        Uses Multi-Criteria Decision Analysis (MADM) to score all proposals
        and select the best agent. Deterministic selection with tie-breaking.

        Workflow:
          1. Normalize all factors to 0-1 scale
          2. Score proposals using weighted formula
          3. Rank by score (descending)
          4. Apply tie-breaking if needed
          5. Send TaskAssignment to winner

        Performance Budget: <5ms P95

        Args:
            proposals: List of agent proposals
            task_announcement: Original task announcement

        Returns:
            Tuple of (selected_agent_id, task_assignment) or (None, None) if failed
        """
        phase2_start = time.time()

        # Publish orchestration.selection (start)
        await self._publish_orchestration_event(
            phase="selection",
            status="start",
            task_id=task_announcement.task_id,
            trace_id=task_announcement.trace_id,
            session_id="default",  # TODO: Extract from task_announcement
            metadata={"proposal_count": len(proposals)},
        )

        logger.info(
            "orchestrator_phase2_start",
            task_id=task_announcement.task_id,
            proposal_count=len(proposals),
            trace_id=task_announcement.trace_id,
        )

        if not proposals:
            return None, None

        # Step 1 & 2: Normalize and score all proposals
        scored_proposals = []
        for proposal in proposals:
            score = self._compute_madm_score(proposal, task_announcement)
            scored_proposals.append((proposal, score))

            logger.debug(
                "orchestrator_proposal_scored",
                task_id=task_announcement.task_id,
                agent_id=proposal.agent_id,
                score=score,
                confidence=proposal.confidence,
                trace_id=task_announcement.trace_id,
            )

        # Step 3: Rank by score (descending, highest = best)
        scored_proposals.sort(key=lambda x: x[1], reverse=True)

        # Step 4: Tie-breaking (if multiple agents have same max score)
        max_score = scored_proposals[0][1]
        top_proposals = [p for p, s in scored_proposals if s == max_score]

        if len(top_proposals) > 1:
            logger.info(
                "orchestrator_tie_detected",
                task_id=task_announcement.task_id,
                tie_count=len(top_proposals),
                max_score=max_score,
                trace_id=task_announcement.trace_id,
            )
            selected_proposal = self._apply_tie_breaking(top_proposals, task_announcement)
        else:
            selected_proposal = top_proposals[0]

        # Step 5: Create and send TaskAssignment
        task_assignment = TaskAssignment(
            task_id=task_announcement.task_id,
            agent_id=selected_proposal.agent_id,
            task_announcement=task_announcement,
            deadline_ms=task_announcement.budget.get("time_ms", 5000),
            priority=2,  # INTERACTIVE priority
        )

        # POC: Log assignment (no actual mailbox sending)
        # Production: Send to mailbox_manager
        logger.info(
            "orchestrator_task_assigned",
            task_id=task_announcement.task_id,
            agent_id=selected_proposal.agent_id,
            score=max_score,
            confidence=selected_proposal.confidence,
            trace_id=task_announcement.trace_id,
        )

        # Record metrics
        phase2_latency = int((time.time() - phase2_start) * 1000)
        if "phase2_latency_ms" not in self.metrics:
            self.metrics["phase2_latency_ms"] = []
        self.metrics["phase2_latency_ms"].append(phase2_latency)

        # Publish orchestration.selection (complete)
        await self._publish_orchestration_event(
            phase="selection",
            status="complete",
            task_id=task_announcement.task_id,
            trace_id=task_announcement.trace_id,
            session_id="default",  # TODO: Extract from task_announcement
            metadata={
                "selected_agent": selected_proposal.agent_id,
                "max_score": max_score,
                "confidence": selected_proposal.confidence,
                "phase2_latency_ms": phase2_latency,
            },
        )

        logger.info(
            "orchestrator_phase2_complete",
            task_id=task_announcement.task_id,
            selected_agent=selected_proposal.agent_id,
            phase2_latency_ms=phase2_latency,
            trace_id=task_announcement.trace_id,
        )

        return selected_proposal.agent_id, task_assignment

    def _compute_madm_score(self, proposal: Proposal, task_announcement: TaskAnnouncement) -> float:
        """
        Compute MADM weighted score for proposal

        Formula (from chat_experience.md):
          score = (10.0 × confidence) + (8.0 × latency_norm) +
                  (-5.0 × cost_norm) + (3.0 × parallelism_norm) +
                  (2.0 × track_record) + (-4.0 × load_penalty)

        Typical range: -10 to +25

        Args:
            proposal: Agent proposal to score
            task_announcement: Task requirements

        Returns:
            MADM score (float)
        """
        budget_time = task_announcement.budget.get("time_ms", 5000)
        budget_cost = task_announcement.budget.get("cost_credits", 0.1)

        # Factor 1: Confidence (already 0-1 from agent)
        confidence = proposal.confidence

        # Factor 2: Latency normalization
        # 1.0 if latency ≤ 50% budget, decay to 0.5 at budget
        latency_ratio = proposal.estimated_latency_ms / budget_time
        if latency_ratio <= 0.5:
            latency_norm = 1.0
        elif latency_ratio >= 1.0:
            latency_norm = 0.5
        else:
            # Linear decay from 1.0 to 0.5 between 50% and 100%
            latency_norm = 1.0 - (latency_ratio - 0.5)

        # Factor 3: Cost normalization
        # 1.0 if cost ≤ 30% budget, decay to 0.5 at budget
        cost_ratio = proposal.estimated_cost / budget_cost if budget_cost > 0 else 0.0
        if cost_ratio <= 0.3:
            cost_norm = 1.0
        elif cost_ratio >= 1.0:
            cost_norm = 0.5
        else:
            # Linear decay from 1.0 to 0.5 between 30% and 100%
            cost_norm = 1.0 - ((cost_ratio - 0.3) / 0.7) * 0.5

        # Factor 4: Parallelism
        # 1.0 (yes) or 0.7 (partial) or 0.0 (no)
        parallelism_norm = 1.0 if proposal.can_parallelize else 0.0

        # Factor 5: Track record (from proposal factor breakdown)
        # Default to 0.7 if not available
        track_record = proposal.factor_breakdown.get("success_rate", 0.7)

        # Factor 6: Load penalty (from proposal factor breakdown)
        # 1.0 - (mailbox_depth / capacity)
        # Default to 0.2 (low load) if not available
        load_penalty = 1.0 - proposal.factor_breakdown.get("load_factor", 0.2)

        # Weighted sum formula
        score = (
            (10.0 * confidence)
            + (8.0 * latency_norm)
            + (-5.0 * cost_norm)
            + (3.0 * parallelism_norm)
            + (2.0 * track_record)
            + (-4.0 * load_penalty)
        )

        return score

    def _apply_tie_breaking(
        self, tied_proposals: List[Proposal], task_announcement: TaskAnnouncement
    ) -> Proposal:
        """
        Apply tie-breaking rules to select from tied proposals

        Tie-Breaking Strategy:
          - 60% prefer_resident: Agent already in session (context cached)
          - 20% prefer_fast: Lowest estimated latency
          - 10% prefer_cheap: Lowest cost
          - 10% random: For exploration (prevent local optima)

        Args:
            tied_proposals: Proposals with same max score
            task_announcement: Task requirements

        Returns:
            Selected proposal
        """
        import random

        # Check for resident agents (already in session)
        # POC: Assume none are resident
        # Production: Query SessionState.Control.agent_roster
        resident_proposals = []
        for proposal in tied_proposals:
            is_resident = self._is_agent_resident(proposal.agent_id)
            if is_resident:
                resident_proposals.append(proposal)

        # 60% prefer resident
        if resident_proposals and random.random() < 0.6:
            logger.debug(
                "orchestrator_tiebreak_resident",
                task_id=task_announcement.task_id,
                selected_agent=resident_proposals[0].agent_id,
                trace_id=task_announcement.trace_id,
            )
            return resident_proposals[0]

        # 20% prefer fast
        if random.random() < 0.2 / 0.4:  # 20% of remaining 40%
            fastest = min(tied_proposals, key=lambda p: p.estimated_latency_ms)
            logger.debug(
                "orchestrator_tiebreak_fast",
                task_id=task_announcement.task_id,
                selected_agent=fastest.agent_id,
                latency_ms=fastest.estimated_latency_ms,
                trace_id=task_announcement.trace_id,
            )
            return fastest

        # 10% prefer cheap
        if random.random() < 0.1 / 0.2:  # 10% of remaining 20%
            cheapest = min(tied_proposals, key=lambda p: p.estimated_cost)
            logger.debug(
                "orchestrator_tiebreak_cheap",
                task_id=task_announcement.task_id,
                selected_agent=cheapest.agent_id,
                cost=cheapest.estimated_cost,
                trace_id=task_announcement.trace_id,
            )
            return cheapest

        # 10% random (exploration)
        selected = random.choice(tied_proposals)
        logger.debug(
            "orchestrator_tiebreak_random",
            task_id=task_announcement.task_id,
            selected_agent=selected.agent_id,
            trace_id=task_announcement.trace_id,
        )
        return selected

    def _is_agent_resident(self, agent_id: str, session_id: Optional[str] = None) -> bool:
        """
        Check if agent is resident (already in session)

        Queries SessionState.Control.agent_roster via SessionStateManager.

        Args:
            agent_id: Agent identifier
            session_id: Session ID (optional, required for production queries)

        Returns:
            True if resident, False otherwise
        """
        # Epic 3.1 Issue 3.1.1: Use SessionStateManager to query control.agent_roster
        if self.session_state_manager and session_id:
            try:
                control_section = self.session_state_manager.get_section(session_id, "control")
                if control_section:
                    agent_roster = control_section.get("agent_roster", {})
                    # Check if agent_id exists in roster (any state means resident)
                    return agent_id in agent_roster
            except Exception as e:
                logger.warning(
                    "failed_to_query_agent_roster",
                    error=str(e),
                    agent_id=agent_id,
                    session_id=session_id,
                )

        # POC fallback: Return False (no resident agents yet)
        return False

    async def _generate_agent_prompt(
        self, agent_type: str, task_context: Dict[str, Any]
    ) -> "PromptTemplate":
        """
        Generate a specialized prompt for a new agent type.

        Workflow:
          1. Check cache (avoid duplicate generation)
          2. Generate specialized prompt via LLM (Groq)
          3. Parse LLM response
          4. Create PromptTemplate
          5. Cache in Prompt Registry (for reuse)

        Args:
            agent_type: e.g., "TicketBookingAgent", "FlightSearchAgent"
            task_context: Task details to inform prompt generation

        Returns:
            PromptTemplate with system_prompt, constraints, tools template

        Raises:
            Exception if generation fails
        """
        # Step 1: Check cache (avoid duplicate generation)
        try:
            cached_prompt = self.prompt_registry.get_prompt(agent_type)
            logger.debug(
                "orchestrator_prompt_cache_hit",
                agent_type=agent_type,
            )
            return cached_prompt
        except KeyError:
            # Agent type not in registry - will generate via Groq
            logger.debug(
                "orchestrator_prompt_cache_miss",
                agent_type=agent_type,
            )

        # Step 2: Generate specialized prompt via Groq LLM
        generation_prompt = f"""
Create a specialized system prompt for an AI agent.

Agent Type: {agent_type}
Task Domain: {task_context.get("domain", "general")}
Task Description: {task_context.get("description", "")}
Available Tools: {', '.join(task_context.get("tools", []))}

Requirements:
- Be specific about the agent's role and expertise
- Include constraints for the domain
- Reference available tools
- Keep tone professional and helpful
- Include 2-3 behavioral constraints

Format as JSON: {{
    "system_prompt": "...",
    "constraints": ["...", "...", "..."],
    "temperature": 0.7,
    "max_tokens": 1000
}}

Return ONLY valid JSON, no markdown backticks or extra text.
"""

        try:
            # Use Groq client to generate prompt
            messages = [{"role": "user", "content": generation_prompt}]

            response = await self.groq_client.complete(
                messages=messages,
                agent_type="planner",  # Use planner temperature (deterministic)
                temperature=0.3,  # Low temp for deterministic results
                max_tokens=600,
            )

            response_text = response.get("content", "")
            prompt_config = json.loads(response_text)
        except Exception as e:
            logger.error(
                "orchestrator_prompt_generation_error",
                agent_type=agent_type,
                error=str(e),
            )
            # Fallback: use generic prompt
            prompt_config = {
                "system_prompt": f"You are a {agent_type} specialized agent. Execute tasks accurately and report results.",
                "constraints": ["Follow user instructions", "Report errors clearly"],
                "temperature": 0.7,
                "max_tokens": 1000,
            }

        # Step 3: Create PromptTemplate
        from l5_infrastructure.registries.prompt_registry import PromptTemplate

        new_prompt = PromptTemplate(
            agent_type=agent_type,
            system_prompt=prompt_config.get(
                "system_prompt", f"You are a {agent_type} specialist agent."
            ),
            tool_prompt_template=self._build_tool_prompt_template(task_context.get("tools", [])),
            context_prompt_template="User Context: {{user_context}}",
            constraints=prompt_config.get("constraints", []),
            examples=[],
            temperature=prompt_config.get("temperature", 0.7),
            max_tokens=prompt_config.get("max_tokens", 1000),
            safety_rules=[
                "Do not execute unvalidated code",
                "Require user confirmation for irreversible actions",
            ],
        )

        # Step 4: Cache in Prompt Registry (for reuse)
        self.prompt_registry.add_prompt(new_prompt)
        # Note: In production, persist asynchronously
        # await self._save_prompt_registry()

        logger.info(
            "orchestrator_prompt_generated",
            agent_type=agent_type,
            temperature=new_prompt.temperature,
        )
        return new_prompt

    def _generate_prompt_mock(self, agent_type: str, task_context: Dict[str, Any]) -> str:
        """
        DEPRECATED - Mock LLM response for prompt generation (POC).

        This method is no longer used. Prompt generation now uses Groq directly.
        Kept for reference only.

        Args:
            agent_type: Agent type
            task_context: Task context

        Returns:
            JSON string with prompt config
        """
        # Mock responses for different agent types
        mock_prompts = {
            "ticketbookingagent": {
                "system_prompt": "You are a restaurant ticket booking specialist. Your role is to help users find, book, and manage restaurant reservations. Always provide clear booking confirmation details including restaurant name, date, time, party size, and confirmation number.",
                "constraints": [
                    "Verify availability before confirming booking",
                    "Collect all required patron information",
                    "Provide alternatives if requested date is unavailable",
                ],
                "temperature": 0.7,
                "max_tokens": 1000,
            },
            "flightsearchagent": {
                "system_prompt": "You are a flight search and booking specialist. Help users find flights, compare prices, and complete bookings. Always present multiple options and highlight the best value based on user preferences.",
                "constraints": [
                    "Compare at least 3 flight options",
                    "Show price and duration for each option",
                    "Confirm passenger details before final booking",
                ],
                "temperature": 0.7,
                "max_tokens": 1200,
            },
            "healthcareagent": {
                "system_prompt": "You are a healthcare information specialist. Provide medical guidance, symptom checking, and referrals to appropriate specialists. Always emphasize that your information is educational and not a substitute for professional medical advice.",
                "constraints": [
                    "Include disclaimer: not a medical professional",
                    "Recommend consulting healthcare provider for serious symptoms",
                    "Ask clarifying questions about symptoms",
                ],
                "temperature": 0.5,
                "max_tokens": 800,
            },
            "generalspecialist": {
                "system_prompt": f"You are a specialized agent for handling {task_context.get('description', 'general')} tasks. Execute the task systematically and report results clearly.",
                "constraints": [
                    "Follow instructions precisely",
                    "Report any errors or limitations",
                    "Ask for clarification if ambiguous",
                ],
                "temperature": 0.7,
                "max_tokens": 1000,
            },
        }

        agent_type_lower = agent_type.lower()
        prompt_config = mock_prompts.get(agent_type_lower, mock_prompts["generalspecialist"])
        return json.dumps(prompt_config)

    def _build_tool_prompt_template(self, tools: List[str]) -> str:
        """
        Build tool prompt template from tool list.

        Args:
            tools: List of tool names

        Returns:
            Formatted tool template string
        """
        if not tools:
            return "No tools available for this task."

        tool_desc = "\n".join([f"- {tool}: Describes what this tool does" for tool in tools])
        return f"""Available tools:
{tool_desc}

Use tools judiciously to accomplish the task."""

    def _infer_agent_type(self, task_assignment: "TaskAssignment") -> str:
        """
        Infer agent type from task description.

        Simple heuristic for POC: keyword matching in description.
        In production: Could use LLM classification or config-based routing.

        Args:
            task_assignment: Task assignment

        Returns:
            Agent type string (e.g., "TicketBookingAgent")
        """
        description_lower = task_assignment.task_announcement.user_input.lower()

        # Keyword mapping for agent type inference
        type_keywords = {
            "TicketBookingAgent": ["book", "ticket", "reservation", "restaurant", "table"],
            "FlightSearchAgent": ["flight", "travel", "airline", "airport", "booking"],
            "HealthcareAgent": ["health", "medical", "doctor", "symptom", "disease"],
            "FinancialAnalyst": ["stock", "financial", "invest", "market", "crypto"],
            "ResearchArticleAgent": ["research", "paper", "article", "study", "academic"],
        }

        for agent_type, keywords in type_keywords.items():
            if any(kw in description_lower for kw in keywords):
                logger.debug(
                    "agent_type_inferred",
                    inferred_type=agent_type,
                    keywords_matched=[kw for kw in keywords if kw in description_lower],
                )
                return agent_type

        # Default
        logger.debug(
            "agent_type_default",
            user_input=task_assignment.task_announcement.user_input[:50],
        )
        return "GeneralistAgent"

    async def _spawn_agent(
        self,
        agent_type: str,
        prompt: "PromptTemplate",
        tools: List["ToolDefinition"],
        task_context: Dict[str, Any],
        session_id: str,
        trace_id: str,
    ) -> str:
        """
        Spawn a new specialist agent with generated prompt and tools.

        Workflow:
          1. Generate unique agent_id
          2. Create AgentSpawnRequest envelope
          3. Call agent factory to spawn agent (POC stub)
          4. Track agent in session state with lifecycle
          5. Return agent_id

        Args:
            agent_type: Agent type identifier
            prompt: PromptTemplate with system prompt and constraints
            tools: List of available tools (ToolDefinition objects)
            task_context: Task details for agent initialization
            session_id: Session identifier
            trace_id: Trace ID for observability

        Returns:
            agent_id for newly spawned agent

        Raises:
            Exception if spawn fails
        """
        # Step 1: Generate unique agent_id
        agent_id = f"{agent_type}_{uuid.uuid4().hex[:8]}"

        # Step 2: Create AgentSpawnRequest envelope
        from models.envelope import AgentSpawnRequest

        agent_spawn_request = AgentSpawnRequest(
            agent_id=agent_id,
            agent_type=agent_type,
            system_prompt=prompt.system_prompt,
            available_tools=[t.to_dict() for t in tools],
            task_context=task_context,
            session_id=session_id,
            trace_id=trace_id,
            timestamp_ms=int(time.time() * 1000),
        )

        # Step 3: Spawn agent (POC: stub, production: factory call)
        try:
            # POC: Mock agent spawning (no actual factory yet)
            logger.info(
                "orchestrator_agent_spawn_request",
                agent_id=agent_id,
                agent_type=agent_type,
                num_tools=len(tools),
                trace_id=trace_id,
            )
            # In production: await self.agent_factory.spawn_agent(agent_spawn_request)
        except Exception as e:
            logger.error(
                "orchestrator_agent_spawn_error",
                agent_id=agent_id,
                agent_type=agent_type,
                error=str(e),
                trace_id=trace_id,
            )
            raise

        # Step 4: Track agent in session state with lifecycle state
        # Note: Will implement full lifecycle tracking in Phase 4
        logger.info(
            "orchestrator_agent_spawned",
            agent_id=agent_id,
            agent_type=agent_type,
            num_tools=len(tools),
            session_id=session_id,
            trace_id=trace_id,
        )

        return agent_id

    async def _phase3_execution(
        self, selected_agent: str, task_assignment: TaskAssignment, task_start_time: float
    ) -> TaskResult:
        """
        Phase 3: Execution - Single/Multi-Step Task Coordination

        Coordinates task execution:
          - Single-step: Agent executes directly
          - Multi-step: Hand off to DAG Executor (Epic 6.3)

        Performance Budgets:
          - Simple task: 50-500ms (LLM call)
          - Complex task: Variable (depends on wave count)
          - Max: 120s saga timeout

        Args:
            selected_agent: Selected agent ID
            task_assignment: Task assignment details
            task_start_time: Task start timestamp

        Returns:
            TaskResult with execution outcome
        """
        task_id = task_assignment.task_id

        # Publish orchestration.execution (start)
        await self._publish_orchestration_event(
            phase="execution",
            status="start",
            task_id=task_id,
            trace_id=task_assignment.task_announcement.trace_id,
            session_id="default",  # TODO: Extract from task_announcement
            metadata={
                "selected_agent": selected_agent,
                "task_type": task_assignment.task_announcement.task_type.value,
            },
        )

        logger.info(
            "orchestrator_phase3_start",
            task_id=task_id,
            agent_id=selected_agent,
            task_type=task_assignment.task_announcement.task_type.value,
            trace_id=task_assignment.task_announcement.trace_id,
        )

        # Determine execution path
        task_type = task_assignment.task_announcement.task_type

        if task_type == TaskType.PLANNING:
            # Multi-step execution: Hand off to Planner + DAG Executor
            logger.info(
                "orchestrator_multistep_execution",
                task_id=task_id,
                trace_id=task_assignment.task_announcement.trace_id,
            )
            task_result = await self._execute_multistep_task(
                selected_agent, task_assignment, task_start_time
            )
        else:
            # Single-step execution: Agent executes directly
            logger.info(
                "orchestrator_singlestep_execution",
                task_id=task_id,
                trace_id=task_assignment.task_announcement.trace_id,
            )
            task_result = await self._execute_singlestep_task(
                selected_agent, task_assignment, task_start_time
            )

        # Publish orchestration.execution (complete)
        await self._publish_orchestration_event(
            phase="execution",
            status="complete",
            task_id=task_id,
            trace_id=task_assignment.task_announcement.trace_id,
            session_id="default",  # TODO: Extract from task_announcement
            metadata={
                "status": task_result.status.value,
                "latency_ms": task_result.latency_ms,
                "agents_used": task_result.agents_used,
                "receipt_count": len(task_result.receipts),
            },
        )

        return task_result

    async def _execute_singlestep_task(
        self, agent_id: str, task_assignment: TaskAssignment, task_start_time: float
    ) -> TaskResult:
        """
        Execute single-step task via selected agent

        Workflow:
          1. Send task to agent's mailbox
          2. Wait for agent response (with timeout)
          3. Handle success/failure/timeout
          4. Return TaskResult

        Args:
            agent_id: Selected agent ID
            task_assignment: Task details
            task_start_time: Task start timestamp

        Returns:
            TaskResult with execution outcome
        """
        task_id = task_assignment.task_id
        timeout_ms = task_assignment.deadline_ms

        logger.info(
            "orchestrator_singlestep_start",
            task_id=task_id,
            agent_id=agent_id,
            timeout_ms=timeout_ms,
            trace_id=task_assignment.task_announcement.trace_id,
        )

        try:
            # POC: Simulate task execution
            # Production: Wait for agent response from mailbox
            result = await self._wait_for_agent_response(
                agent_id, task_id, timeout_ms / 1000.0  # Convert to seconds
            )

            total_latency = int((time.time() - task_start_time) * 1000)

            if result.get("status") == "success":
                logger.info(
                    "orchestrator_singlestep_success",
                    task_id=task_id,
                    agent_id=agent_id,
                    latency_ms=total_latency,
                    trace_id=task_assignment.task_announcement.trace_id,
                )

                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.SUCCESS,
                    result=result.get("data", {}),
                    latency_ms=total_latency,
                    agents_used=[agent_id],
                    receipts=result.get("receipts", []),
                )
            else:
                # Task failed
                logger.warning(
                    "orchestrator_singlestep_failure",
                    task_id=task_id,
                    agent_id=agent_id,
                    error=result.get("error"),
                    trace_id=task_assignment.task_announcement.trace_id,
                )

                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.FAILURE,
                    result={},
                    latency_ms=total_latency,
                    agents_used=[agent_id],
                    error=result.get("error", "Task execution failed"),
                )

        except asyncio.TimeoutError:
            # Task timed out
            total_latency = int((time.time() - task_start_time) * 1000)

            logger.error(
                "orchestrator_singlestep_timeout",
                task_id=task_id,
                agent_id=agent_id,
                timeout_ms=timeout_ms,
                trace_id=task_assignment.task_announcement.trace_id,
            )

            return TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILURE,
                result={},
                latency_ms=total_latency,
                agents_used=[agent_id],
                error=f"Task timed out after {timeout_ms}ms",
            )

        except Exception as e:
            # Unexpected error
            total_latency = int((time.time() - task_start_time) * 1000)

            logger.error(
                "orchestrator_singlestep_error",
                task_id=task_id,
                agent_id=agent_id,
                error=str(e),
                trace_id=task_assignment.task_announcement.trace_id,
            )

            return TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILURE,
                result={},
                latency_ms=total_latency,
                agents_used=[agent_id],
                error=str(e),
            )

    async def _execute_multistep_task(
        self, agent_id: str, task_assignment: TaskAssignment, task_start_time: float
    ) -> TaskResult:
        """
        Execute multi-step task via Planner + DAG Executor

        Workflow:
          1. Send task to Planner agent for plan generation
          2. Planner generates plan (4-stage pipeline: Sketch → Expand → Validate → Commit)
          3. Receive CommittedPlan from Planner
          4. Hand off plan to DAG Executor for parallel execution
          5. DAG Executor runs waves with barriers and returns aggregated result
          6. Collect all receipts and build final TaskResult

        Architecture:
          - Planner (Tier 2 AI Agent): Generates plan via 4-stage pipeline
          - DAG Executor (Pure Orchestrator): Executes waves in parallel
          - Saga Pattern: Compensation on critical step failure (LIFO)

        Performance Budget: Variable (depends on wave count)
          - Planner: <600ms P95
          - DAG Execution: Variable (multiple waves)
          - Max: 120s saga timeout

        Args:
            agent_id: Planner agent ID
            task_assignment: Task details
            task_start_time: Task start timestamp

        Returns:
            TaskResult with execution outcome, all receipts, agents used

        Based on:
            - ADR-0006c: DAG Execution with barriers
            - ADR-0007: 4-Stage Planning Pipeline
            - ADR-0008: Saga Pattern error recovery
        """
        task_id = task_assignment.task_id
        trace_id = task_assignment.task_announcement.trace_id

        logger.info(
            "orchestrator_multistep_start",
            task_id=task_id,
            planner_agent=agent_id,
            trace_id=trace_id,
        )

        try:
            # Step 1: Send task to Planner agent for plan generation
            logger.info(
                "orchestrator_planner_invocation",
                task_id=task_id,
                agent_id=agent_id,
                trace_id=trace_id,
            )

            # Wait for Planner response (timeout: 60s for full pipeline)
            planner_response = await self._wait_for_agent_response(
                agent_id, task_id, timeout=60.0  # 60s for Planner full pipeline
            )

            # Step 2: Extract CommittedPlan from Planner response
            if planner_response.get("status") != "success":
                # Planner failed to generate plan
                total_latency = int((time.time() - task_start_time) * 1000)

                logger.error(
                    "orchestrator_planner_failed",
                    task_id=task_id,
                    error=planner_response.get("error", "Unknown error"),
                    trace_id=trace_id,
                )

                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.FAILURE,
                    result={},
                    latency_ms=total_latency,
                    agents_used=[agent_id],
                    error=planner_response.get("error", "Planner failed to generate plan"),
                )

            # Extract CommittedPlan from response
            committed_plan_data = planner_response.get("data", {})
            if not committed_plan_data:
                total_latency = int((time.time() - task_start_time) * 1000)

                logger.error(
                    "orchestrator_no_plan_received",
                    task_id=task_id,
                    trace_id=trace_id,
                )

                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.FAILURE,
                    result={},
                    latency_ms=total_latency,
                    agents_used=[agent_id],
                    error="Planner did not return a plan",
                )

            logger.info(
                "orchestrator_plan_received",
                task_id=task_id,
                plan_id=committed_plan_data.get("plan_id"),
                step_count=len(committed_plan_data.get("steps", [])),
                trace_id=trace_id,
            )

            # Step 3: Hand off to DAG Executor for parallel execution
            logger.info(
                "orchestrator_dag_executor_invocation",
                task_id=task_id,
                plan_id=committed_plan_data.get("plan_id"),
                trace_id=trace_id,
            )

            # Import DAG Executor
            from l2_orchestration.executor.dag_executor import DAGExecutor

            # Initialize DAG Executor with registries
            dag_executor = DAGExecutor(
                agent_registry=self.agent_registry,
                tool_registry=self.tool_registry,
                max_concurrent=3,
            )

            # Create a CommittedPlan object from the response data
            # For POC: wrap the response data directly
            dag_result = await dag_executor.execute_plan(committed_plan_data)

            # Step 4: Process DAG Executor result
            total_latency = int((time.time() - task_start_time) * 1000)

            logger.info(
                "orchestrator_dag_execution_complete",
                task_id=task_id,
                dag_status=dag_result.get("status"),
                waves_executed=dag_result.get("waves", 0),
                total_latency_ms=total_latency,
                trace_id=trace_id,
            )

            # Step 5: Collect all receipts from all waves
            all_receipts = dag_result.get("receipts", [])
            step_results = dag_result.get("step_results", [])

            # Flatten wave results to get all agents used
            all_agents_used = [agent_id]  # Planner is first agent
            for wave_results in step_results if isinstance(step_results, list) else []:
                if isinstance(wave_results, list):
                    for step_result in wave_results:
                        if isinstance(step_result, dict) and step_result.get("agent_id"):
                            all_agents_used.append(step_result["agent_id"])

            # Step 6: Extract final output (result from last wave)
            final_output = {}
            if isinstance(step_results, list) and len(step_results) > 0:
                # Last wave's last step contains final output
                last_wave = step_results[-1] if isinstance(step_results[-1], list) else []
                if isinstance(last_wave, list) and len(last_wave) > 0:
                    last_step = last_wave[-1]
                    if isinstance(last_step, dict):
                        final_output = last_step.get("output_data", {})

            # Step 7: Build and return TaskResult
            if dag_result.get("status") == "SUCCESS":
                logger.info(
                    "orchestrator_multistep_success",
                    task_id=task_id,
                    plan_id=committed_plan_data.get("plan_id"),
                    latency_ms=total_latency,
                    agents_used=len(all_agents_used),
                    trace_id=trace_id,
                )

                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.SUCCESS,
                    result=final_output,
                    latency_ms=total_latency,
                    agents_used=all_agents_used,
                    receipts=all_receipts,
                )
            else:
                # Partial or failed execution
                logger.warning(
                    "orchestrator_multistep_failure",
                    task_id=task_id,
                    dag_status=dag_result.get("status"),
                    error=dag_result.get("error", "Unknown DAG execution error"),
                    trace_id=trace_id,
                )

                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.PARTIAL,
                    result=final_output,
                    latency_ms=total_latency,
                    agents_used=all_agents_used,
                    receipts=all_receipts,
                    error=dag_result.get("error", "DAG execution did not complete successfully"),
                )

        except asyncio.TimeoutError:
            # Planner or DAG execution timed out
            total_latency = int((time.time() - task_start_time) * 1000)

            logger.error(
                "orchestrator_multistep_timeout",
                task_id=task_id,
                timeout_ms=60000,
                trace_id=trace_id,
            )

            return TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILURE,
                result={},
                latency_ms=total_latency,
                agents_used=[agent_id],
                error="Multi-step execution timed out (60s budget)",
            )

        except Exception as e:
            # Unexpected error during multi-step execution
            total_latency = int((time.time() - task_start_time) * 1000)

            logger.error(
                "orchestrator_multistep_error",
                task_id=task_id,
                error=str(e),
                error_type=type(e).__name__,
                trace_id=trace_id,
            )

            return TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILURE,
                result={},
                latency_ms=total_latency,
                agents_used=[agent_id],
                error=f"Multi-step execution error: {str(e)}",
            )

    async def _wait_for_agent_response(
        self, agent_id: str, task_id: str, timeout: float
    ) -> Dict[str, Any]:
        """
        Wait for agent to complete task and return response

        POC: Simulates agent response
        Production: Listens to mailbox for agent response

        Args:
            agent_id: Agent ID
            task_id: Task ID
            timeout: Timeout in seconds

        Returns:
            Agent response dictionary
        """
        # POC: Simulate successful task execution
        await asyncio.sleep(0.1)  # Simulate processing time

        return {
            "status": "success",
            "data": {
                "message": f"Task {task_id} completed by {agent_id}",
                "result": "POC simulated result",
            },
            "receipts": [],
        }

    def add_proposal(self, task_id: str, proposal: Proposal) -> None:
        """
        Add received proposal to task's proposal list

        Called by agents when they submit bids.

        Args:
            task_id: Task identifier
            proposal: Agent's bid proposal
        """
        if task_id not in self.task_proposals:
            self.task_proposals[task_id] = []

        self.task_proposals[task_id].append(proposal)

        logger.info(
            "orchestrator_proposal_received",
            task_id=task_id,
            agent_id=proposal.agent_id,
            confidence=proposal.confidence,
            proposal_count=len(self.task_proposals[task_id]),
        )

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get orchestrator performance metrics

        Returns:
            Dictionary of metrics
        """
        metrics = self.metrics.copy()

        # Compute averages
        if metrics["phase1_latency_ms"]:
            metrics["avg_phase1_latency_ms"] = sum(metrics["phase1_latency_ms"]) / len(
                metrics["phase1_latency_ms"]
            )
            metrics["p95_phase1_latency_ms"] = (
                sorted(metrics["phase1_latency_ms"])[int(len(metrics["phase1_latency_ms"]) * 0.95)]
                if len(metrics["phase1_latency_ms"]) > 0
                else 0
            )

        if metrics["proposals_collected"]:
            metrics["avg_proposals_per_task"] = sum(metrics["proposals_collected"]) / len(
                metrics["proposals_collected"]
            )

        return metrics
        return metrics
