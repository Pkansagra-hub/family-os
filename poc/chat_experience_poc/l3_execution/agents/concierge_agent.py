"""
Concierge Agent — Tier 1 Always-Active Master Coordinator

The Concierge is the "heart and soul" of the K1 system - a Tier 1 AI agent that:
  - Receives ALL user messages first
  - Uses LLM reasoning (via Prompt Registry + Groq) to classify intent
  - Routes specialized queries to appropriate specialists (Healthcare, Finance, Research)
  - Routes complex planning requests to PlannerAgent
  - Handles casual conversation (meta-intents) directly with quick LLM responses
  - Provides transparent "⏳ Looping in specialist..." feedback before routing

Key Architecture:
  - **AI Agent** - Uses LLM for ALL decisions, NO hardcoded classification logic
  - **Prompt Registry** - System prompts from config/prompt_registry.json
  - **Template Engine** - Merges prompts with user context, tools, history
  - **Groq Client** - LLM reasoning with temperature=0.2, seed=42 for determinism
  - **Agent Factory** - Spawns specialists with merged prompts (simulated in POC)

Intent Classification (LLM-based):
  - **meta-intent**: Greetings, small talk, acknowledgements → Handle directly
  - **query-intent**: Specialized knowledge → Route to specialist (Healthcare, Finance, Research)
  - **planning-intent**: Complex multi-step requests → Route to PlannerAgent

Meta-Intent Subtypes (11 patterns):
  - ACK: "ok", "thanks", "got it"
  - GREETING: "hey", "hi", "hello"
  - SMALL_TALK: "how are you?", "what's up?"
  - TIME_QUERY: "what time is it?"
  - STATUS: "what's my status?", "what are we doing?"
  - CLARIFICATION: "what do you mean?", "can you explain?"
  - AFFIRMATION, REJECTION, WAIT, CANCEL, HELP

References:
  - docs/whiteboard/chat_experience.md - Concierge decision making
  - docs/plans/chat_experience_poc_plan.md - Epic 4.1 (Issues 4.1.1-4.1.3)
  - ADR-0005 - Concierge role as Tier 1 AI Agent
  - config/prompt_registry.json - Concierge system prompt
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from l3_execution.agents.agent_base import AgentBase, AgentState
from l4_runtime.deltabus.deltabus import DeltaBusEvent, get_deltabus
from l4_runtime.mailbox.mailbox import Message, Priority
from utils.awaiters import AwaiterTimeout, await_response


class ConciergeAgent(AgentBase):
    """
    Tier 1 Always-Active Master Coordinator.

    Handles:
      - Intent classification (LLM-based, no hardcoded logic)
      - Meta-intent handling (casual conversation)
      - Specialist routing (Healthcare, Finance, Research)
      - Planner routing (complex multi-step tasks)
      - Transparent user feedback ("⏳ Looping in specialist...")

    Architecture:
      - Inherits from AgentBase (mailbox, lifecycle, LLM calls)
      - Uses Prompt Registry for system prompts
      - Uses Groq client for LLM reasoning
      - Uses Template Engine for prompt merging
      - No hardcoded classification logic
    """

    def __init__(
        self,
        agent_id: str,
        session_id: str,
        groq_client: Any,
        agent_factory: Optional[Any] = None,
        agent_fabric: Optional[Any] = None,  # NEW: Accept AgentFabric (Issue 2.2.2)
        mailbox: Optional[Any] = None,  # NEW: Accept mailbox from AgentFabric (Issue 1.2.2)
        trace_id: Optional[str] = None,
    ):
        """
        Initialize Concierge agent.

        Args:
            agent_id: Unique agent identifier
            session_id: Session ID for this conversation
            groq_client: Groq client for LLM calls
            agent_factory: Agent Factory for spawning specialists (optional, deprecated)
            agent_fabric: Agent Fabric for lifecycle-managed spawning (optional, Issue 2.2.2)
            mailbox: Optional mailbox from AgentFabric (Issue 1.2.2)
            trace_id: Optional trace ID
        """
        super().__init__(
            agent_id=agent_id,
            agent_type="concierge",
            session_id=session_id,
            groq_client=groq_client,
            mailbox=mailbox,  # Pass mailbox to AgentBase
            trace_id=trace_id,
        )

        # Agent Factory for dynamic spawning
        self.agent_factory = agent_factory
        self.agent_fabric = agent_fabric  # NEW: AgentFabric for mailbox-managed spawning

        # Concierge-specific metrics
        self.concierge_metrics = {
            "meta_intents_handled": 0,
            "specialists_routed": 0,
            "planner_routed": 0,
            "classification_errors": 0,
        }

        # DeltaBus for publishing responses
        self.deltabus = get_deltabus()

        # Track turn count and latencies for P95
        self._turn_count = 0
        self._query_latencies: list[float] = []
        self._planning_latencies: list[float] = []

        # Register with ComponentRegistry
        try:
            from monitoring.component_registry import ComponentRegistry

            reg = ComponentRegistry.inst()
            reg.register("Concierge Agent")
            reg.set("Concierge Agent", "RUNNING", details="Turn 0")
        except Exception:
            pass  # Registry optional for now

        self.logger.info(
            "ConciergeAgent initialized",
            agent_id=self.agent_id,
            session_id=self.session_id,
            has_agent_factory=agent_factory is not None,
        )

    # ========================================================================
    # LIFECYCLE HOOKS
    # ========================================================================

    async def on_active(self) -> None:
        """
        ACTIVE state hook - Concierge ready to receive user messages.

        Concierge is Tier 1 (always-active) - never goes IDLE or DRAINING.
        Stays ACTIVE for entire session.
        """
        await super().on_active()
        self.logger.info(
            "Concierge is ACTIVE and ready to handle user messages",
            agent_id=self.agent_id,
        )

    # ========================================================================
    # MAILBOX CONSUMER LOOP (Issue 2.2.1)
    # ========================================================================

    async def run(self) -> None:
        """
        Main mailbox consumer loop - consumes messages from Concierge mailbox.

        Issue 2.2.1 Step 1: Consume messages exclusively from mailbox.

        Flow:
        1. Wait for message from mailbox (blocks until message arrives)
        2. Process message (classify intent, route, respond)
        3. Publish response events to DeltaBus
        4. Repeat while ACTIVE

        This replaces direct process_message() calls from Intent Router.
        Intent Router now sends to mailbox, Concierge consumes from mailbox.

        Lifecycle:
        - Starts when agent transitions to ACTIVE state
        - Runs until agent transitions to DRAINING or TERMINATED state
        - Handles graceful shutdown (finishes current message)
        """
        self.logger.info(
            "Concierge mailbox consumer loop started",
            agent_id=self.agent_id,
        )

        try:
            while self.state in [AgentState.ACTIVE, AgentState.WARMING]:
                try:
                    # Step 1: Receive message from mailbox (blocks until message arrives)
                    message = await self.mailbox.receive()

                    self.logger.info(
                        "Received message from mailbox",
                        agent_id=self.agent_id,
                        message_id=message.message_id,
                        sender_id=message.sender_id,
                        priority=message.priority.name,
                    )

                    # Step 2: Process message (convert Message to dict format)
                    message_dict = {
                        "envelope_id": message.message_id,
                        "trace_id": message.trace_id,
                        "sender_id": message.sender_id,
                        "payload": message.payload,
                    }

                    # Step 3: Process message (response published inside process_message)
                    await self.process_message(message_dict)

                except asyncio.CancelledError:
                    self.logger.info(
                        "Mailbox consumer loop cancelled",
                        agent_id=self.agent_id,
                    )
                    break

                except Exception as e:
                    self.logger.error(
                        "Error processing mailbox message",
                        agent_id=self.agent_id,
                        error=str(e),
                    )
                    # Continue loop - don't crash on single message failure

        finally:
            self.logger.info(
                "Concierge mailbox consumer loop stopped",
                agent_id=self.agent_id,
                final_state=self.state.name,
            )

    # ========================================================================
    # MESSAGE PROCESSING (Main Entry Point)
    # ========================================================================

    async def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming user message.

        Workflow:
          1. Extract user input from message
          2. Classify intent using LLM (meta/query/planning)
          3. Route based on intent:
             - meta → handle_meta_intent() (direct response)
             - query → route_to_specialist() (spawn specialist)
             - planning → route_to_planner() (spawn planner)
          4. Publish response to DeltaBus for Intent Router
          5. Return response to caller

        Args:
            message: Message dict with 'payload', 'sender_id', 'trace_id', 'envelope_id'

        Returns:
            Response dict with 'content', 'intent', 'status', 'envelope_id'
        """
        start_time = datetime.utcnow()
        envelope_id = message.get("envelope_id", "unknown")

        # Issue 2.2.1 Step 2: Publish agent.task_received event
        await self._publish_agent_event(
            event_type="agent.task_received",
            envelope_id=envelope_id,
            metadata={
                "agent_id": self.agent_id,
                "agent_type": self.agent_type,
                "timestamp": start_time.isoformat(),
            },
        )

        try:
            # Extract user input from envelope structure
            # message["payload"] contains the full envelope dict: {"header": {...}, "payload": {...}}
            envelope_dict = message.get("payload", {})
            payload = envelope_dict.get("payload", {})
            content = payload.get("content", {})

            # Extract text from content dict (content may be {"text": str, "timestamp": str, "user_context": dict})
            if isinstance(content, dict):
                user_input = content.get("text", "")
            elif isinstance(content, str):
                user_input = content
            else:
                user_input = str(content)

            if not user_input:
                response = {
                    "status": "error",
                    "content": "Empty message received",
                }
                await self._publish_response(envelope_id, response, start_time)
                return response

            self.logger.info(
                "processing_user_message",
                agent_id=self.agent_id,
                envelope_id=envelope_id,
                user_input=str(user_input)[:100],  # Truncate for logging
            )

            # Step 1: Classify intent using LLM
            intent_result = await self._classify_intent(user_input)
            intent_type = intent_result["intent_type"]
            intent_subtype = intent_result.get("intent_subtype")
            confidence = intent_result.get("confidence", 0.0)

            self.logger.info(
                "Intent classified",
                intent_type=intent_type,
                intent_subtype=intent_subtype,
                confidence=confidence,
            )

            # Step 2: Route based on intent
            if intent_type == "meta":
                response = await self._handle_meta_intent(user_input, intent_subtype)
                self.concierge_metrics["meta_intents_handled"] += 1

            elif intent_type == "query":
                # Query Flow: Concierge → Specialist Agents (direct, no orchestrator)
                # Specialists query K0 independently
                specialist_type = intent_result.get("specialist_type", "healthcare")
                response = await self._spawn_and_query_specialist(
                    user_input=user_input,
                    specialist_type=specialist_type,
                    user_context=await self.query_user_kg("get_preferences"),
                )
                self.concierge_metrics["specialists_routed"] += 1

            elif intent_type == "planning":
                # Planning Flow: Concierge → Orchestrator (coordination required)
                # Orchestrator handles multi-step planning, agent selection, dag execution
                response = await self._delegate_to_orchestrator(
                    user_input=user_input,
                )
                self.concierge_metrics["planner_routed"] += 1

            else:
                # Fallback: handle as meta-intent
                response = await self._handle_meta_intent(user_input, "UNKNOWN")
                self.concierge_metrics["classification_errors"] += 1

            # Step 3: Track latency and P95 by intent type
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            # Track per-intent latencies (Prince's fix #5)
            if intent_type == "query":
                self._query_latencies.append(latency_ms)
                # Keep last 100 samples
                if len(self._query_latencies) > 100:
                    self._query_latencies = self._query_latencies[-100:]
            elif intent_type == "planning":
                self._planning_latencies.append(latency_ms)
                if len(self._planning_latencies) > 100:
                    self._planning_latencies = self._planning_latencies[-100:]

            # Increment turn count and update registry
            self._turn_count += 1
            try:
                from monitoring.component_registry import ComponentRegistry

                reg = ComponentRegistry.inst()
                # Calculate P95 for query intents
                if self._query_latencies and len(self._query_latencies) >= 2:
                    sorted_latencies = sorted(self._query_latencies)
                    p95_idx = int(len(sorted_latencies) * 0.95)
                    query_p95 = sorted_latencies[p95_idx]
                    reg.set(
                        "Concierge Agent",
                        "RUNNING",
                        p95_ms=query_p95,
                        details=f"Turn {self._turn_count}",
                    )
                else:
                    reg.set("Concierge Agent", "RUNNING", details=f"Turn {self._turn_count}")
            except Exception:
                pass  # Registry optional

            self.logger.info(
                "Message processing complete",
                agent_id=self.agent_id,
                intent_type=intent_type,
                latency_ms=latency_ms,
                turn=self._turn_count,
            )

            # Step 4: Publish response to DeltaBus for Intent Router
            await self._publish_response(envelope_id, response, start_time)

            # Issue 2.2.1 Step 2: Publish agent.task_completed event
            await self._publish_agent_event(
                event_type="agent.task_completed",
                envelope_id=envelope_id,
                metadata={
                    "agent_id": self.agent_id,
                    "agent_type": self.agent_type,
                    "intent_type": intent_type,
                    "status": response.get("status", "unknown"),
                    "latency_ms": latency_ms,
                },
            )

            # Step 5: Return response
            response["envelope_id"] = envelope_id
            return response

        except Exception as e:
            self.logger.error(
                "Error processing message",
                agent_id=self.agent_id,
                envelope_id=envelope_id,
                error=str(e),
            )
            response = {
                "status": "error",
                "content": "Sorry, I encountered an error processing your message.",
                "error": str(e),
            }
            await self._publish_response(envelope_id, response, start_time)

            # Issue 2.2.1 Step 2: Publish agent.task_completed event (error case)
            await self._publish_agent_event(
                event_type="agent.task_completed",
                envelope_id=envelope_id,
                metadata={
                    "agent_id": self.agent_id,
                    "agent_type": self.agent_type,
                    "status": "error",
                    "error": str(e),
                },
            )

            response["envelope_id"] = envelope_id
            return response

    # ========================================================================
    # RESPONSE PUBLISHING (Issue 6.5.1.2 - Wire to Intent Router)
    # ========================================================================

    async def _publish_response(
        self,
        envelope_id: str,
        response: Dict[str, Any],
        start_time: datetime,
    ) -> None:
        """
        Publish response to DeltaBus for Intent Router to receive.

        Implementation of Issue 6.5.1.2: Wire Intent Router → Concierge Communication

        Publishes to DeltaBus event: response.{envelope_id}

        Args:
            envelope_id: Envelope ID from incoming request
            response: Response dict with content, status, user_input, agent_chain, etc.
            start_time: Start time for latency calculation
        """
        try:
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            # Build response event payload
            response_payload = {
                "message": response.get("content", "No response"),
                "agent_id": self.agent_id,
                "latency_ms": latency_ms,
                "metadata": {
                    "status": response.get("status", "unknown"),
                    "intent": response.get("intent", "unknown"),
                    "intent_subtype": response.get("intent_subtype", "unknown"),
                    "specialist_type": response.get("specialist_type"),
                    "error": response.get("error"),
                },
            }

            # Publish to DeltaBus with event_type = response.{envelope_id}
            event_type = f"response.{envelope_id}"

            from l4_runtime.deltabus.deltabus import DeltaBusEvent

            event = DeltaBusEvent(
                event_type=event_type,
                session_id=self.session_id,
                payload=response_payload,
                trace_id=self.trace_id,
            )

            self.deltabus.publish(event)

            self.logger.info(
                "[Concierge] Response published to DeltaBus",
                envelope_id=envelope_id,
                event_type=event_type,
                latency_ms=latency_ms,
            )

            # Emit episodic memory delta (Issue 6.5.1.2 - Memory Formation)
            # Extract actual user text from user_input dict
            user_input_obj = response.get("user_input", {})
            if isinstance(user_input_obj, dict):
                user_text = user_input_obj.get("text", "")
            else:
                user_text = str(user_input_obj) if user_input_obj else ""

            assistant_text = response_payload.get("message", "")
            agent_chain = response.get("agent_chain", [self.agent_id])

            await self._publish_episodic_delta(
                envelope_id=envelope_id,
                user_text=user_text,
                assistant_text=assistant_text,
                agent_chain=agent_chain,
                latency_ms=latency_ms,
            )

            # Force flush for PATH-1 (Prince's fix #3)
            try:
                from l5_infrastructure.background_services_manager import BackgroundServicesManager

                bsm = await BackgroundServicesManager.get_manager()
                if bsm.batch_client and hasattr(bsm.batch_client, "flush_now"):
                    bsm.batch_client.flush_now()
            except Exception:
                pass  # Optional flush

        except Exception as e:
            self.logger.error(
                "[Concierge] Failed to publish response",
                envelope_id=envelope_id,
                error=str(e),
            )

    async def _publish_agent_event(
        self,
        event_type: str,
        envelope_id: str,
        metadata: Dict[str, Any],
    ) -> None:
        """
        Publish agent lifecycle event to DeltaBus.

        Issue 2.2.1 Step 2: Publish agent.task_received, agent.task_completed events.

        Events published:
        - agent.task_received: When task starts processing
        - agent.task_completed: When task finishes (success or error)
        - session.delta: When SessionState is updated (future)

        Args:
            event_type: Event type (agent.task_received, agent.task_completed, session.delta)
            envelope_id: Envelope ID for correlation
            metadata: Event metadata (agent_id, status, latency_ms, etc.)
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
                "Agent event published",
                event_type=event_type,
                envelope_id=envelope_id,
            )

        except Exception as e:
            self.logger.error(
                "Failed to publish agent event",
                event_type=event_type,
                envelope_id=envelope_id,
                error=str(e),
            )

    async def _publish_episodic_delta(
        self,
        envelope_id: str,
        user_text: str,
        assistant_text: str,
        agent_chain: List[str],
        latency_ms: float,
    ) -> None:
        """
        Publish episodic memory delta to DeltaBus for Writer Agents.

        Episodic deltas capture user-assistant interaction pairs for memory formation.

        Args:
            envelope_id: Envelope ID for correlation
            user_text: User's input message
            assistant_text: Assistant's response
            agent_chain: List of agents involved (e.g., ["concierge_001", "healthcare_512052e1"])
            latency_ms: Response latency in milliseconds
        """
        try:
            from l4_runtime.deltabus.deltabus import DeltaBusEvent

            episodic_payload = {
                "delta_type": "episodic",
                "session_id": self.session_id,
                "trace_id": self.trace_id,
                "timestamp": datetime.utcnow().isoformat(),
                "agent_chain": agent_chain,
                "user_text": user_text,
                "assistant_text": assistant_text,
                "latency_ms": latency_ms,
                "envelope_id": envelope_id,
            }

            event = DeltaBusEvent(
                event_type="session.delta",
                session_id=self.session_id,
                payload=episodic_payload,
                trace_id=self.trace_id,
            )

            self.deltabus.publish(event)

            self.logger.debug(
                "[Concierge] Episodic delta published",
                envelope_id=envelope_id,
                user_text_len=len(user_text),
                assistant_text_len=len(assistant_text),
            )

        except Exception as e:
            self.logger.warning(
                "[Concierge] Failed to publish episodic delta",
                envelope_id=envelope_id,
                error=str(e),
            )

    # ========================================================================
    # QUERY FLOW: Concierge → Specialist Agents (Direct, No Orchestrator)
    # ========================================================================

    async def _spawn_and_query_specialist(
        self,
        user_input: str,
        specialist_type: str,
        user_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Spawn and query specialist agent via AgentFabric (mailbox flow).

        Issue 2.2.1 Step 3 & Issue 2.2.2: Delegate via AgentFabric with mailboxes.

        Query Flow (Mailbox-based):
        1. Use AgentFabric to spawn specialist (gets mailbox automatically)
        2. Send task to specialist's mailbox
        3. Await response via DeltaBus (await_response utility)
        4. Return specialist insights to user

        This flow uses REAL specialist agents (not simulated).
        Specialists have mailboxes and consume tasks via run() loop.

        Args:
            user_input: User query
            specialist_type: "healthcare", "finance", or "research"
            user_context: User preferences/profile from KG

        Returns:
            Response dict with specialist insights
        """
        try:
            feedback_message = f"⏳ Querying {specialist_type} specialist for insights..."

            self.logger.info(
                "[Concierge] Spawning specialist agent via AgentFabric",
                specialist_type=specialist_type,
                user_input=str(user_input)[:100],
            )

            # Check if AgentFabric is available
            if not self.agent_fabric:
                # Fallback: Use simulated response if AgentFabric not available
                self.logger.warning(
                    "[Concierge] AgentFabric not available, using fallback",
                    specialist_type=specialist_type,
                )
                return {
                    "status": "success",
                    "intent": "query",
                    "specialist_type": specialist_type,
                    "content": f"[POC Fallback] I would consult a {specialist_type} specialist for this query: {str(user_input)[:100]}",
                    "feedback_message": feedback_message,
                    "user_input": user_input,  # Include for episodic delta
                    "agent_chain": [self.agent_id],
                }

            # Step 1: Spawn specialist via AgentFabric (gets mailbox automatically)
            specialist_agent = await self.agent_fabric.spawn_agent(
                agent_type=specialist_type,
                session_id=self.session_id,
                trace_id=self.trace_id,
            )

            if not specialist_agent:
                raise Exception(f"Failed to spawn {specialist_type} agent")

            # Step 2: Send task to specialist's mailbox
            task_envelope_id = f"task_{specialist_agent.agent_id}_{datetime.utcnow().timestamp()}"

            task_message = Message(
                message_id=task_envelope_id,
                sender_id=self.agent_id,
                receiver_id=specialist_agent.agent_id,
                priority=Priority.STANDARD,
                payload={
                    "user_input": user_input,
                    "user_context": user_context,
                },
                trace_id=self.trace_id,
            )

            # Send to specialist mailbox (use MailboxManager, not agent's private mailbox)
            specialist_mailbox = self.mailbox_manager.get_mailbox(specialist_agent.agent_id)
            if not specialist_mailbox:
                raise Exception(f"Mailbox not found for {specialist_agent.agent_id}")

            sent = await specialist_mailbox.send(task_message)

            if not sent:
                raise Exception(f"Failed to send task to {specialist_type} mailbox (full)")

            self.logger.info(
                "[Concierge] Task sent to specialist mailbox",
                specialist_type=specialist_type,
                task_envelope_id=task_envelope_id,
                specialist_agent_id=specialist_agent.agent_id,
            )

            # Step 3: Await response via DeltaBus (specialist publishes response.{task_envelope_id})
            try:
                response_data = await await_response(
                    envelope_id=task_envelope_id,
                    deltabus=self.deltabus,
                    timeout=10.0,  # 10s timeout for specialist response
                    trace_id=self.trace_id,
                )

                self.logger.info(
                    "[Concierge] Specialist response received",
                    specialist_type=specialist_type,
                    status=response_data.get("status", "unknown"),
                )

                # Step 4: Return insights to user
                return {
                    "status": "success",
                    "intent": "query",
                    "specialist_type": specialist_type,
                    "content": response_data.get("content", "No response from specialist"),
                    "feedback_message": feedback_message,
                    "specialist_agent_id": specialist_agent.agent_id,
                    "user_input": user_input,  # Include for episodic delta
                    "agent_chain": [self.agent_id, specialist_agent.agent_id],
                }

            except AwaiterTimeout as e:
                self.logger.error(
                    "[Concierge] Specialist response timeout",
                    specialist_type=specialist_type,
                    error=str(e),
                )
                return {
                    "status": "error",
                    "content": f"The {specialist_type} specialist took too long to respond. Please try again.",
                    "error": "timeout",
                    "user_input": user_input,  # Include for episodic delta
                    "agent_chain": [self.agent_id],
                }

        except Exception as e:
            self.logger.error(
                "[Concierge] Specialist query failed",
                specialist_type=specialist_type,
                error=str(e),
            )
            return {
                "status": "error",
                "content": f"Sorry, I had trouble querying the {specialist_type} specialist.",
                "error": str(e),
                "user_input": user_input,  # Include for episodic delta
                "agent_chain": [self.agent_id],
            }

    # ========================================================================
    # INTENT CLASSIFICATION (LLM-based, NO hardcoded logic)
    # ========================================================================

    async def _classify_intent(self, user_input: str) -> Dict[str, Any]:
        """
        Classify user intent using LLM reasoning.

        Uses Concierge prompt from Prompt Registry with few-shot examples.
        LLM decides intent type, subtype, specialist type, confidence.

        NO hardcoded classification logic - all decisions made by LLM.

        Args:
            user_input: User message

        Returns:
            Dict with:
              - intent_type: str (meta/query/planning)
              - intent_subtype: str (GREETING, SMALL_TALK, etc.)
              - specialist_type: str (healthcare, finance, research) for query-intents
              - confidence: float (0.0-1.0)
              - reasoning: str (LLM explanation)
        """
        try:
            # Get time context for smarter intent classification (NEW: Time-aware)
            time_context = await self._get_time_context_from_session()

            # Build context for template merging (including time context)
            context_data = {
                "user_context": await self.query_user_kg("get_preferences"),
                "tools": [],  # Tools not needed for classification
                "history": "",  # Chat history (simulated for POC)
                "time_context": time_context,  # NEW: Include time for context-aware classification
            }

            # Add classification instruction to user input
            classification_prompt = f"""Classify the following user message into one of these intent types:

1. **meta-intent**: Casual conversation, system queries, acknowledgements
   - Examples: "Hello", "Thanks", "What can you do?", "Help", "Cancel"
   - Subtypes: GREETING, SMALL_TALK, ACK, TIME_QUERY, STATUS, CLARIFICATION, AFFIRMATION, REJECTION, WAIT, CANCEL, HELP
   - NOTE: General status checks about the SYSTEM only, NOT about user's health/finances/data

2. **query-intent**: User asking about their personal data (health, finances, research)
   - Examples: "How's my recovery?", "What's my blood pressure?", "Show my spending", "What stocks do I own?"
   - Specialist types: healthcare (health/medical), finance (money/investments), research (general knowledge)
   - Use healthcare for ANY health/medical/wellness questions
   - Use finance for ANY money/spending/investment questions

3. **planning-intent**: Complex multi-step requests that need coordination
   - Examples: "Plan a dinner", "Book a trip", "Schedule my week", "Organize a party"

User message: "{user_input}"

Respond in JSON format:
{{
  "intent_type": "meta|query|planning",
  "intent_subtype": "GREETING|SMALL_TALK|ACK|...",
  "specialist_type": "healthcare|finance|research" (if query-intent),
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation"
}}"""

            # Call LLM with Concierge prompt + classification instruction
            response = await self.call_llm(
                user_input=classification_prompt,
                context_data=context_data,
                temperature=0.2,  # Low temperature for deterministic classification
            )

            # Parse LLM response (expecting JSON)
            import json

            llm_content = response["content"].strip()

            # Extract JSON from response (may be wrapped in markdown code blocks)
            if "```json" in llm_content:
                llm_content = llm_content.split("```json")[1].split("```")[0].strip()
            elif "```" in llm_content:
                llm_content = llm_content.split("```")[1].split("```")[0].strip()

            intent_result = json.loads(llm_content)

            self.logger.debug(
                "Intent classification result",
                intent_result=intent_result,
            )

            return intent_result

        except Exception as e:
            self.logger.error(
                "Intent classification failed",
                error=str(e),
            )
            # Fallback: treat as meta-intent
            return {
                "intent_type": "meta",
                "intent_subtype": "UNKNOWN",
                "confidence": 0.0,
                "reasoning": f"Classification error: {str(e)}",
            }

    # ========================================================================
    # META-INTENT HANDLING (Direct Response with LLM)
    # ========================================================================

    async def _handle_meta_intent(
        self, user_input: str, intent_subtype: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle meta-intent directly with quick LLM response.

        Meta-intents (greetings, small talk, acknowledgements) don't require
        orchestration or specialist routing. Concierge responds directly
        with persona-aware LLM response.

        For simple queries (TIME, STATUS), generate response without LLM.
        For conversational queries (GREETING, SMALL_TALK), use LLM with persona.

        Args:
            user_input: User message
            intent_subtype: Meta-intent subtype (GREETING, SMALL_TALK, etc.)

        Returns:
            Response dict with 'content', 'intent', 'status'
        """
        try:
            # Simple queries (no LLM needed)
            if intent_subtype == "TIME_QUERY":
                current_time = datetime.now().strftime("%I:%M %p")
                return {
                    "status": "success",
                    "intent": "meta",
                    "intent_subtype": intent_subtype,
                    "content": f"It's {current_time} right now.",
                }

            if intent_subtype == "STATUS":
                return {
                    "status": "success",
                    "intent": "meta",
                    "intent_subtype": intent_subtype,
                    "content": "I'm here and ready to help! How can I assist you today?",
                }

            # Conversational queries (use LLM with persona)
            context_data = {
                "user_context": await self.query_user_kg("get_preferences"),
                "tools": [],
                "history": "",
            }

            response = await self.call_llm(
                user_input=user_input,
                context_data=context_data,
                temperature=0.3,  # Slightly higher for natural conversation
                max_tokens=150,  # Keep responses brief
            )

            return {
                "status": "success",
                "intent": "meta",
                "intent_subtype": intent_subtype or "UNKNOWN",
                "content": response["content"],
                "tokens_used": response["tokens_used"],
            }

        except Exception as e:
            self.logger.error(
                "Meta-intent handling failed",
                error=str(e),
            )
            return {
                "status": "error",
                "content": "Sorry, I had trouble responding. Could you try again?",
                "error": str(e),
            }

    # ========================================================================
    # SPECIALIST ROUTING (Issue 4.1.2)
    # ========================================================================

    async def _route_to_specialist(self, user_input: str, specialist_type: str) -> Dict[str, Any]:
        """
        Route specialized query to appropriate specialist agent.

        Workflow (5 steps):
          1. Send immediate feedback to user: "⏳ Looping in {specialist_type} specialist..."
          2. Check agent factory availability
          3. Create task envelope with user input + context
          4. Spawn specialist agent (or reuse from pool)
          5. Send task to specialist and wait for response
          6. Relay specialist response back to user

        Args:
            user_input: User query
            specialist_type: Specialist type (healthcare, finance, research)

        Returns:
            Response dict with 'content', 'specialist_type', 'status'
        """
        try:
            # Step 1: Send immediate feedback to user
            feedback_message = (
                f"⏳ Looping in {specialist_type} specialist to give you better insights..."
            )
            self.logger.info(
                "Routing to specialist",
                specialist_type=specialist_type,
                user_input=str(user_input)[:100],
            )

            # Update SessionState (simulated for POC)
            await self.update_session_state(
                section="Scoreboard",
                updates={"pending_message": feedback_message},
            )

            # Step 2: Check if Agent Factory available
            if not self.agent_factory:
                # Fallback to simulation if no factory
                self.logger.warning(
                    "Agent Factory not available, using simulation", specialist_type=specialist_type
                )
                specialist_response = await self._simulate_specialist_response(
                    specialist_type, user_input, {}
                )
                return {
                    "status": "success",
                    "intent": "query",
                    "specialist_type": specialist_type,
                    "content": specialist_response["content"],
                    "feedback_message": feedback_message,
                    "tokens_used": specialist_response.get("tokens_used", 0),
                    "spawned": False,
                }

            # Step 3: Create task envelope
            task_envelope = {
                "task_id": self._generate_trace_id(),
                "user_input": user_input,
                "specialist_type": specialist_type,
                "user_context": await self.query_user_kg("get_preferences"),
                "session_id": self.session_id,
                "trace_id": self.trace_id,
            }

            # Step 4: Spawn specialist agent via Agent Factory
            self.logger.info(
                "Spawning specialist via Agent Factory", specialist_type=specialist_type
            )

            specialist_agent = await self.agent_factory.spawn_agent(
                agent_type=specialist_type,
                task_envelope=task_envelope,
                session_id=self.session_id,
                trace_id=self.trace_id,
            )

            if not specialist_agent:
                # Spawn failed, fallback to simulation
                self.logger.error(
                    "Specialist spawn failed, using simulation fallback",
                    specialist_type=specialist_type,
                )
                specialist_response = await self._simulate_specialist_response(
                    specialist_type, user_input, task_envelope
                )
                return {
                    "status": "success",
                    "intent": "query",
                    "specialist_type": specialist_type,
                    "content": specialist_response["content"],
                    "feedback_message": feedback_message,
                    "tokens_used": specialist_response.get("tokens_used", 0),
                    "spawned": False,
                }

            # Step 5: Send task to specialist and get response
            self.logger.info(
                "Sending task to specialist",
                specialist_type=specialist_type,
                agent_id=specialist_agent.agent_id,
            )

            specialist_response = await specialist_agent.process_message(task_envelope)

            # Update metrics
            self.concierge_metrics["specialists_routed"] += 1

            # Step 6: Relay response back to user
            return {
                "status": specialist_response.get("status", "success"),
                "intent": "query",
                "specialist_type": specialist_type,
                "content": specialist_response["content"],
                "feedback_message": feedback_message,
                "tokens_used": specialist_response.get("tokens_used", 0),
                "agent_id": specialist_agent.agent_id,
                "spawned": True,
            }

        except asyncio.TimeoutError:
            self.logger.error(
                "Specialist routing timeout",
                specialist_type=specialist_type,
            )
            return {
                "status": "error",
                "content": f"Sorry, {specialist_type} specialist took too long to respond. Please try again.",
            }

        except Exception as e:
            self.logger.error(
                "Specialist routing failed",
                specialist_type=specialist_type,
                error=str(e),
            )
            return {
                "status": "error",
                "content": f"Sorry, I had trouble reaching the {specialist_type} specialist.",
                "error": str(e),
            }

    async def _simulate_specialist_response(
        self, specialist_type: str, user_input: str, task_envelope: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Simulate specialist agent response (POC only).

        Uses specialist's prompt from Prompt Registry + Groq client to
        generate specialist-specific response.

        In full implementation (Milestone 3): This would be replaced with
        actual Agent Factory spawning specialist agent.

        Args:
            specialist_type: Specialist type (healthcare, finance, research)
            user_input: User query
            task_envelope: Task envelope with context

        Returns:
            Dict with 'content', 'tokens_used'
        """
        try:
            # Build context for specialist prompt
            context_data = {
                "user_context": task_envelope.get("user_context", {}),
                "tools": [],  # Tools would come from Tool Registry
                "history": "",  # Chat history from SessionState
            }

            # Fetch specialist prompt from registry
            specialist_prompt_template = self.prompt_registry.get_prompt(specialist_type)

            # Render specialist prompt with context
            specialist_prompt = self.template_engine.render_prompt(
                agent_type=specialist_type,
                context_data=context_data,
            )

            # Call Groq with specialist prompt
            messages = [
                {"role": "system", "content": specialist_prompt},
                {"role": "user", "content": user_input},
            ]

            response = await self.groq_client.complete(
                messages=messages,
                agent_type=specialist_type,
                temperature=specialist_prompt_template.temperature,
                max_tokens=specialist_prompt_template.max_tokens,
                trace_id=self.trace_id,
            )

            self.logger.info(
                "Specialist response generated",
                specialist_type=specialist_type,
                tokens_used=response["tokens_used"],
            )

            return {
                "content": response["content"],
                "tokens_used": response["tokens_used"],
            }

        except Exception as e:
            self.logger.error(
                "Specialist simulation failed",
                specialist_type=specialist_type,
                error=str(e),
            )
            return {
                "content": f"Sorry, the {specialist_type} specialist encountered an error.",
                "tokens_used": 0,
            }

    # ========================================================================
    # PLANNING FLOW - DELEGATE TO ORCHESTRATOR
    # ========================================================================

    async def _delegate_to_orchestrator(self, user_input: str) -> Dict[str, Any]:
        """
        Delegate complex planning request to Orchestrator.

        For planning-intent requests, Concierge delegates to Orchestrator
        for 3-phase coordination (negotiation, selection, execution).

        Flow:
        1. Create TaskRequest envelope with planning context
        2. Send to Orchestrator mailbox (Priority: INTERACTIVE)
        3. Subscribe to task completion event
        4. Wait for TaskResult response (10s timeout)
        5. Extract and relay response to user

        For POC: Stub implementation (returns placeholder).
        Full implementation in Milestone 6, Epic 6.2.

        Args:
            user_input: User request requiring planning/orchestration

        Returns:
            Response dict with 'status', 'content', 'task_id'
        """
        try:
            # Generate task_id for tracking
            import uuid

            task_id = str(uuid.uuid4())

            self.logger.info(
                "Delegating to orchestrator",
                user_input=str(user_input)[:100],
                task_id=task_id,
            )

            # Create TaskRequest envelope
            task_request = {
                "task_id": task_id,
                "user_input": user_input,
                "context": {
                    "user_preferences": await self.query_user_kg("get_preferences"),
                    "cognitive_trace_id": self.trace_id,
                },
                "priority": "INTERACTIVE",  # High priority for user-facing requests
            }

            # In full impl: Send to Orchestrator mailbox
            # self.mailbox.send_to("orchestrator", task_request, priority="INTERACTIVE")

            # In full impl: Subscribe to task completion event
            # event_key = f"orchestrator.task_completed.{task_id}"
            # response = await self.delta_bus.subscribe_once(event_key, timeout=10.0)

            # For POC: Return stub response with structured format
            feedback_message = "⏳ Breaking down your request with orchestrator coordination..."

            stub_response = {
                "status": "success",
                "intent": "planning",
                "task_id": task_id,
                "content": (
                    "I've coordinated a multi-step plan with specialized agents:\n"
                    "1. Agent negotiation phase completed (3 agents selected)\n"
                    "2. Task selection phase completed (optimal execution path found)\n"
                    "3. Execution phase initiated (2 sequential steps, 1 parallel step)\n\n"
                    "Expected outcome: Complete in ~30 seconds"
                ),
                "feedback_message": feedback_message,
                "estimated_duration": "30s",
                "agents_involved": ["HealthcareAgent", "DataAnalysisAgent"],
            }

            self.concierge_metrics["planning_requests"] = (
                self.concierge_metrics.get("planning_requests", 0) + 1
            )

            return stub_response

        except asyncio.TimeoutError:
            self.logger.error(
                "Orchestrator delegation timeout",
                task_id=task_id if "task_id" in locals() else None,
            )
            return {
                "status": "error",
                "content": "Sorry, the orchestration took too long. Please try again.",
            }

        except Exception as e:
            self.logger.error(
                "Orchestrator delegation failed",
                error=str(e),
            )
            return {
                "status": "error",
                "content": "Sorry, I had trouble delegating to the orchestrator.",
                "error": str(e),
            }

    # PLANNER ROUTING
    # ========================================================================

    async def _route_to_planner(self, user_input: str) -> Dict[str, Any]:
        """
        Route complex planning request to PlannerAgent.

        Similar workflow to specialist routing but routes to PlannerAgent
        for task decomposition.

        For POC: Simulate planner response.
        Full implementation in Milestone 5.

        Args:
            user_input: User request

        Returns:
            Response dict with 'content', 'status'
        """
        try:
            feedback_message = "⏳ Breaking down your request into steps..."

            self.logger.info(
                "Routing to planner",
                user_input=str(user_input)[:100],
            )

            # Simulate planner response (POC)
            return {
                "status": "success",
                "intent": "planning",
                "content": "I've broken down your request. Here's the plan:\n1. First step\n2. Second step\n3. Third step",
                "feedback_message": feedback_message,
            }

        except Exception as e:
            self.logger.error(
                "Planner routing failed",
                error=str(e),
            )
            return {
                "status": "error",
                "content": "Sorry, I had trouble creating a plan.",
                "error": str(e),
            }

    # ========================================================================
    # METRICS & STATS
    # ========================================================================

    def get_concierge_stats(self) -> Dict[str, Any]:
        """
        Get Concierge-specific statistics.

        Returns:
            Dict with Concierge metrics
        """
        base_stats = self.get_stats()
        base_stats.update(self.concierge_metrics)
        return base_stats

    # ========================================================================
    # TIME CONTEXT (NEW: Context-Aware Intent Classification)
    # ========================================================================

    async def _get_time_context_from_session(self) -> Dict[str, Any]:
        """
        Extract time context from session state for context-aware routing.

        Uses time context for smarter intent classification:
          - "How's my health?" at 9am → HealthcareAgent
          - "How's my budget?" at 5pm → FinanceAgent
          - Business hours queries prioritize relevant specialists

        Returns:
            Dict with time context fields

        Example usage:
          - Route evening queries to different agents (evening → personal topics)
          - Route morning queries to professional agents (morning → productivity)
          - Adjust response tone based on time of day
        """
        self.logger.debug(
            "extracting_time_context_for_concierge_routing",
            trace_id=self.trace_id,
        )

        # POC: Return mock time context
        # In production: session_state.get_time_context()
        from datetime import datetime

        now = datetime.now()
        hour = now.hour

        return {
            "current_time": now.isoformat(),
            "current_hour": hour,
            "day_of_week": now.strftime("%A"),
            "is_morning": 5 <= hour < 12,
            "is_afternoon": 12 <= hour < 17,
            "is_evening": 17 <= hour < 21,
            "is_business_hours": 9 <= hour <= 17,
            "time_of_day": (
                "morning"
                if 5 <= hour < 12
                else (
                    "afternoon" if 12 <= hour < 17 else ("evening" if 17 <= hour < 21 else "night")
                )
            ),
        }
