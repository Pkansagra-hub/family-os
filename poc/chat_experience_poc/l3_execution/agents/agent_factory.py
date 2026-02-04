"""
Agent Factory - Dynamic Agent Spawning

Full implementation for Epic 6.5.2.2: Wire Orchestrator → Dynamic Specialist Agent Spawning.
Supports on-demand spawning of Tier 2 agents (HealthcareAgent, FinanceAgent, etc.)

Based on:
- ADR-0086: Dynamic Agent Creation Subsystem
- chat_experience_poc_plan.md: Issue 6.5.2.2
- chat_experience.md: ConciergeAgent.forward() flows

Features:
- Dynamic agent spawning with lifecycle management
- Prompt generation/caching for agent types
- Tool resolution from Tool Registry
- Agent reuse pool (5-min idle TTL)
- Full PENDING → WARMING → ACTIVE lifecycle
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from l3_execution.agents.agent_base import AgentBase, AgentState
from l4_runtime.deltabus.deltabus import DeltaBusEvent, get_deltabus
from l5_infrastructure.groq_client import GroqClient

logger = logging.getLogger(__name__)


# ========================================================================
# Dynamic Specialist Agent (Tier 2)
# ========================================================================


class SpecialistAgent(AgentBase):
    """
    Dynamically spawned Tier 2 specialist agent.

    Capabilities:
    - Processes specialized queries (healthcare, finance, research, etc.)
    - Uses domain-specific system prompt
    - Has access to specialized tools
    - Manages own lifecycle (PENDING → WARMING → ACTIVE → IDLE)
    """

    def __init__(
        self,
        agent_id: str,
        agent_type: str,
        session_id: str,
        groq_client: GroqClient,
        system_prompt: str,
        available_tools: List[Dict[str, Any]],
        mailbox: Optional[Any] = None,  # NEW: Accept mailbox from AgentFabric (Issue 2.2.2)
        trace_id: Optional[str] = None,
    ):
        """
        Initialize specialist agent.

        Args:
            agent_id: Unique agent identifier
            agent_type: Specialist type (healthcare, finance, researcher, etc.)
            session_id: Session identifier
            groq_client: Groq client for LLM calls
            system_prompt: Domain-specific system prompt
            available_tools: List of tools this agent can use
            mailbox: Optional mailbox from AgentFabric (Issue 2.2.2)
            trace_id: Cognitive trace identifier
        """
        super().__init__(
            agent_id=agent_id,
            agent_type=agent_type,
            session_id=session_id,
            groq_client=groq_client,
            mailbox=mailbox,  # Pass mailbox to AgentBase
            trace_id=trace_id,
        )

        self.system_prompt = system_prompt
        self.available_tools = available_tools

        # DeltaBus for publishing events (Issue 2.2.2)
        self.deltabus = get_deltabus()

        self.logger.info(
            f"[{agent_type}] Specialist initialized",
            agent_id=agent_id,
            tools_count=len(available_tools),
        )

    async def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming task message.

        Args:
            message: Task envelope with user_input, context, etc.

        Returns:
            Response dict with content, status, tokens_used
        """
        try:
            self.metrics["messages_received"] += 1
            user_input_raw = message.get("user_input", "")
            user_context = message.get("user_context", {})

            # Extract text from user_input (may be dict or string)
            if isinstance(user_input_raw, dict):
                user_input = user_input_raw.get("text", str(user_input_raw))
            else:
                user_input = str(user_input_raw)

            self.logger.info(
                f"[{self.agent_type}] Processing message",
                agent_id=self.agent_id,
                input_length=len(user_input),
            )

            # Build messages for LLM
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_input},
            ]

            # Call LLM via Groq client
            response = await self.groq_client.complete(
                messages=messages,
                agent_type=self.agent_type,
                temperature=0.3,
                max_tokens=500,
                trace_id=self.trace_id,
            )

            self.metrics["llm_calls"] += 1
            self.metrics["messages_sent"] += 1

            return {
                "status": "success",
                "content": response["content"],
                "tokens_used": response["tokens_used"],
                "agent_id": self.agent_id,
                "agent_type": self.agent_type,
            }

        except Exception as e:
            self.metrics["errors"] += 1
            self.logger.error(
                f"[{self.agent_type}] Message processing failed",
                agent_id=self.agent_id,
                error=str(e),
            )
            return {
                "status": "error",
                "content": f"Error processing request: {str(e)}",
                "agent_id": self.agent_id,
                "agent_type": self.agent_type,
            }

    async def run(self) -> None:
        """
        Main mailbox consumer loop - consumes messages from specialist mailbox.

        Issue 2.2.2 Step 3: Rely on mailboxes to deliver tasks and gather results.

        Flow:
        1. Wait for message from mailbox (blocks until message arrives)
        2. Publish agent.task_received event
        3. Process message (call LLM, generate response)
        4. Publish agent.task_completed event
        5. Publish response to DeltaBus for caller
        6. Repeat while ACTIVE

        This replaces direct process_message() calls.
        Concierge now sends to specialist mailbox, specialist consumes from mailbox.

        Lifecycle:
        - Starts when agent transitions to ACTIVE state
        - Runs until agent transitions to IDLE, DRAINING or TERMINATED state
        - Handles graceful shutdown (finishes current message)
        """
        self.logger.info(
            f"[{self.agent_type}] Mailbox consumer loop started",
            agent_id=self.agent_id,
        )

        try:
            while self.state in [AgentState.ACTIVE, AgentState.WARMING]:
                try:
                    # Step 1: Receive message from mailbox (blocks until message arrives)
                    message = await self.mailbox.receive()

                    self.logger.info(
                        f"[{self.agent_type}] Received message from mailbox",
                        agent_id=self.agent_id,
                        message_id=message.message_id,
                        sender_id=message.sender_id,
                        priority=message.priority.name,
                    )

                    # Step 2: Publish agent.task_received event
                    await self._publish_agent_event(
                        event_type="agent.task_received",
                        envelope_id=message.message_id,
                        metadata={
                            "agent_id": self.agent_id,
                            "agent_type": self.agent_type,
                            "sender_id": message.sender_id,
                        },
                    )

                    # Step 3: Process message
                    response = await self.process_message(message.payload)

                    # Step 4: Publish agent.task_completed event
                    await self._publish_agent_event(
                        event_type="agent.task_completed",
                        envelope_id=message.message_id,
                        metadata={
                            "agent_id": self.agent_id,
                            "agent_type": self.agent_type,
                            "status": response.get("status", "unknown"),
                        },
                    )

                    # Step 5: Publish response to DeltaBus for caller (using envelope_id pattern)
                    response_event = DeltaBusEvent(
                        event_type=f"response.{message.message_id}",
                        session_id=self.session_id,
                        payload=response,
                        trace_id=self.trace_id,
                    )
                    self.deltabus.publish(response_event)

                    self.logger.info(
                        f"[{self.agent_type}] Response published",
                        agent_id=self.agent_id,
                        envelope_id=message.message_id,
                    )

                except asyncio.CancelledError:
                    self.logger.info(
                        f"[{self.agent_type}] Mailbox consumer loop cancelled",
                        agent_id=self.agent_id,
                    )
                    break

                except Exception as e:
                    self.logger.error(
                        f"[{self.agent_type}] Error processing mailbox message",
                        agent_id=self.agent_id,
                        error=str(e),
                    )
                    # Continue loop - don't crash on single message failure

        finally:
            # Convert state to string safely for logging
            final_state = self.state.name if hasattr(self.state, "name") else str(self.state)
            self.logger.info(
                f"[{self.agent_type}] Mailbox consumer loop stopped",
                agent_id=self.agent_id,
                final_state=final_state,
            )

    async def _publish_agent_event(
        self,
        event_type: str,
        envelope_id: str,
        metadata: Dict[str, Any],
    ) -> None:
        """
        Publish agent lifecycle event to DeltaBus.

        Issue 2.2.2 Step 3: Publish lifecycle events along the way.

        Events published:
        - agent.task_received: When task starts processing
        - agent.task_completed: When task finishes (success or error)

        Args:
            event_type: Event type (agent.task_received, agent.task_completed)
            envelope_id: Envelope ID for correlation
            metadata: Event metadata (agent_id, status, etc.)
        """
        try:
            event = DeltaBusEvent(
                event_type=event_type,
                session_id=self.session_id,
                payload={
                    "envelope_id": envelope_id,
                    **metadata,
                },
                trace_id=self.trace_id,
            )

            self.deltabus.publish(event)

            self.logger.debug(
                f"[{self.agent_type}] Agent event published",
                event_type=event_type,
                envelope_id=envelope_id,
            )

        except Exception as e:
            self.logger.error(
                f"[{self.agent_type}] Failed to publish agent event",
                event_type=event_type,
                envelope_id=envelope_id,
                error=str(e),
            )


class AgentFactory:
    """
    Agent Factory - Dynamic Tier 2 Agent Spawning

    Lifecycle:
    - Phase 6: Pre-allocated (lazy init, ready but not spawning)
    - Runtime: Spawns agents on-demand when Orchestrator assigns tasks

    Agent Types (Tier 2 Specialists):
    - HealthcareAgent: Medical queries, appointment scheduling
    - FinanceAgent: Budget tracking, expense analysis
    - ResearcherAgent: Deep research, multi-source synthesis
    - TravelAgent: Trip planning, booking assistance
    - DeveloperAgent: Code generation, debugging

    Features (Minimal for Phase 6):
    - Agent spawning: Create new agent instances
    - Agent reuse pool: Track idle agents (5min TTL)
    - Prompt generation: LLM call for agent system prompts (cached)
    - Tool resolution: Link agents to required tools
    """

    def __init__(
        self,
        prompt_registry: Dict[str, Any],
        tool_registry: Any,
        groq_client: Any,
    ):
        """
        Initialize Agent Factory (lazy, not spawning yet)

        Args:
            prompt_registry: Prompt templates for agent types
            tool_registry: Tool specifications (name → schema)
            groq_client: AsyncGroq client for LLM calls
        """
        self.prompt_registry = prompt_registry
        self.tool_registry = tool_registry
        self.groq_client = groq_client

        # Agent pool (for reuse)
        self.agent_pool: Dict[str, List[Any]] = {}  # agent_type → [agent instances]
        self.active_agents: Dict[str, Any] = {}  # agent_id → agent instance

        # Stats
        self.spawn_count = 0
        self.reuse_count = 0

        logger.info(
            f"[AgentFactory] Initialized (lazy): "
            f"prompt_templates={len(prompt_registry)}, "
            f"tools={len(tool_registry.tools) if hasattr(tool_registry, 'tools') else 0}"
        )

    async def spawn_agent(
        self,
        agent_type: str,
        task_envelope: Dict[str, Any],
        session_id: str,
        trace_id: str,
        mailbox: Optional[Any] = None,  # NEW: Accept mailbox from AgentFabric (Issue 2.2.2)
    ) -> Optional[Any]:
        """
        Spawn Tier 2 specialist agent on-demand

        Issue 2.2.2 Step 1: Accept mailbox from AgentFabric when spawning.

        Args:
            agent_type: Type of agent to spawn (healthcare, finance, researcher, etc.)
            task_envelope: Task specification with user input, required tools, budget
            session_id: Session identifier
            trace_id: Cognitive trace identifier
            mailbox: Mailbox allocated by AgentFabric (REQUIRED for mailbox flow)

        Returns:
            SpecialistAgent instance if successful, None if spawn failed

        Flow:
        1. Check agent pool for idle agent (reuse) - REMOVED (handled by AgentFabric)
        2. Resolve tools from tool_registry
        3. Generate/retrieve system prompt (LLM call if new, cached if exists)
        4. Create SpecialistAgent instance with mailbox
        5. Transition agent: PENDING → WARMING → ACTIVE
        6. Return agent instance
        """
        spawn_start = time.time()

        logger.info(
            f"[AgentFactory] Spawn requested: agent_type={agent_type}, "
            f"session_id={session_id}, trace_id={trace_id}, has_mailbox={mailbox is not None}"
        )

        try:
            # Note: Reuse pool logic removed - now handled by AgentFabric
            # AgentFabric checks for idle agents before calling spawn_agent()

            # Step 1: Create new agent instance
            agent_id = f"{agent_type}_{self.spawn_count + 1}"
            self.spawn_count += 1

            # Step 2: Resolve tools from tool_registry
            available_tools = self._resolve_tools_for_agent(agent_type, task_envelope)
            logger.info(f"[AgentFactory] Tools resolved: count={len(available_tools)}")

            # Step 3: Generate/retrieve system prompt
            system_prompt = await self._get_or_generate_prompt(agent_type, available_tools)
            logger.info(f"[AgentFactory] System prompt prepared: length={len(system_prompt)}")

            # Step 4: Create agent instance
            # Use specialized agent classes when available, otherwise generic SpecialistAgent
            if agent_type == "healthcare":
                from l3_execution.agents.specialists.healthcare_agent import (
                    HealthcareAgent,
                )

                agent = HealthcareAgent(
                    agent_id=agent_id,
                    session_id=session_id,
                    groq_client=self.groq_client,
                    trace_id=trace_id,
                    mailbox=mailbox,  # Pass mailbox from AgentFabric
                )
            elif agent_type == "finance":
                from l3_execution.agents.specialists.finance_agent import FinanceAgent

                agent = FinanceAgent(
                    agent_id=agent_id,
                    session_id=session_id,
                    groq_client=self.groq_client,
                    trace_id=trace_id,
                    mailbox=mailbox,  # Pass mailbox from AgentFabric
                )
            else:
                # Generic SpecialistAgent for other types
                agent = SpecialistAgent(
                    agent_id=agent_id,
                    agent_type=agent_type,
                    session_id=session_id,
                    groq_client=self.groq_client,
                    system_prompt=system_prompt,
                    available_tools=available_tools,
                    mailbox=mailbox,  # Pass mailbox from AgentFabric
                    trace_id=trace_id,
                )

            # Step 5: Lifecycle transitions
            # PENDING (default) → WARMING
            await agent.transition_to(AgentState.WARMING)
            # Simulate warming (resource validation, model loading)
            await asyncio.sleep(0.1)  # POC: Quick warm-up

            # WARMING → ACTIVE
            await agent.transition_to(AgentState.ACTIVE)

            # Note: Agent tracking removed - now handled by AgentFabric
            # AgentFabric registers agent and tracks in _agents registry

            spawn_duration = time.time() - spawn_start
            logger.info(
                f"[AgentFactory] Agent spawned successfully: "
                f"agent_id={agent_id}, duration={spawn_duration:.3f}s"
            )

            return agent

        except Exception as e:
            logger.error(f"[AgentFactory] Spawn failed: agent_type={agent_type}, error={str(e)}")
            return None

    def _resolve_tools_for_agent(
        self, agent_type: str, task_envelope: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Resolve tools for agent type from tool registry.

        Args:
            agent_type: Specialist type
            task_envelope: Task with potential tool hints

        Returns:
            List of tool specifications
        """
        # Tool mapping for specialist types
        tool_map = {
            "healthcare": ["query_user_kg", "search_medical_records", "schedule_appointment"],
            "finance": ["query_user_kg", "get_budget_summary", "analyze_expenses"],
            "researcher": ["web_search", "query_k0", "synthesize_sources"],
            "travel": ["search_flights", "search_hotels", "book_reservation"],
            "developer": ["generate_code", "debug_code", "run_tests"],
        }

        tool_names = tool_map.get(agent_type, ["query_user_kg"])

        # Resolve from tool_registry
        available_tools = []
        if hasattr(self.tool_registry, "tools"):
            for tool_name in tool_names:
                tool_spec = self.tool_registry.tools.get(tool_name)
                if tool_spec:
                    available_tools.append(tool_spec)

        # If no tools found, return basic query tool
        if not available_tools:
            available_tools = [
                {"name": "query_user_kg", "description": "Query user knowledge graph"}
            ]

        return available_tools

    async def _get_or_generate_prompt(
        self, agent_type: str, available_tools: List[Dict[str, Any]]
    ) -> str:
        """
        Get cached prompt or generate new one for agent type.

        Prompt generation caching:
        - First TicketBookingAgent task: Generate prompt (1 LLM call), save to registry
        - Subsequent TicketBookingAgent tasks: Use cached prompt (0 LLM calls)
        - Key: Agent type (not individual instance) has stable prompt

        Args:
            agent_type: Specialist type
            available_tools: Tools this agent can use

        Returns:
            System prompt string
        """
        # Check if prompt exists in registry
        try:
            prompt_template = self.prompt_registry.get(agent_type)
            if prompt_template:
                # Use existing prompt from registry
                logger.info(f"[AgentFactory] Using cached prompt for {agent_type}")

                # Get base prompt content
                if hasattr(prompt_template, "prompt"):
                    return prompt_template.prompt
                elif isinstance(prompt_template, dict) and "prompt" in prompt_template:
                    return prompt_template["prompt"]
                else:
                    return str(prompt_template)
        except (KeyError, AttributeError):
            pass

        # Generate new prompt (LLM call)
        logger.info(f"[AgentFactory] Generating new prompt for {agent_type}")

        # Use fallback template-based approach for POC
        tool_descriptions = "\n".join(
            [
                f"- {tool.get('name', 'unknown')}: {tool.get('description', 'No description')}"
                for tool in available_tools
            ]
        )

        prompt = f"""You are a {agent_type} specialist agent in the K1 Intelligence system.

Your role:
- Answer user queries related to {agent_type} domain
- Provide accurate, helpful, and context-aware responses
- Use available tools when needed

Available tools:
{tool_descriptions}

Guidelines:
- Be professional and concise
- Prioritize user needs and preferences
- Cite sources when providing factual information
- If uncertain, acknowledge limitations clearly

Respond naturally and helpfully to user queries."""

        # Cache prompt in registry for reuse
        try:
            self.prompt_registry[agent_type] = {"prompt": prompt, "generated": True}
        except Exception:
            pass  # Continue even if caching fails

        return prompt

    async def get_idle_agent(self, agent_type: str) -> Optional[Any]:
        """
        Get idle agent from pool for reuse

        Args:
            agent_type: Type of agent needed

        Returns:
            Agent instance if available, None otherwise
        """
        if agent_type in self.agent_pool and self.agent_pool[agent_type]:
            agent = self.agent_pool[agent_type].pop(0)
            self.reuse_count += 1
            logger.info(
                f"[AgentFactory] Agent reused from pool: "
                f"agent_type={agent_type}, agent_id={getattr(agent, 'agent_id', 'unknown')}"
            )
            return agent
        return None

    async def return_agent_to_pool(self, agent_id: str, agent: Any) -> None:
        """
        Return agent to pool for reuse (after 5min idle)

        Args:
            agent_id: Agent identifier
            agent: Agent instance
        """
        agent_type = getattr(agent, "agent_type", "unknown")
        if agent_type not in self.agent_pool:
            self.agent_pool[agent_type] = []
        self.agent_pool[agent_type].append(agent)

        logger.info(
            f"[AgentFactory] Agent returned to pool: "
            f"agent_id={agent_id}, agent_type={agent_type}"
        )

    def get_stats(self) -> Dict[str, Any]:
        """
        Get factory statistics

        Returns:
            Dict with spawn_count, reuse_count, active_agents, pool_size
        """
        return {
            "spawn_count": self.spawn_count,
            "reuse_count": self.reuse_count,
            "active_agents": len(self.active_agents),
            "pool_size": sum(len(agents) for agents in self.agent_pool.values()),
        }
