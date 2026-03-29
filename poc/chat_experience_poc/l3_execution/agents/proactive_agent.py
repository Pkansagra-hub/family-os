"""
ProactiveAgent — Tier 1 Always-Active SSE Listener for K0 Proactive Ticks.

ProactiveAgent connects to Mock K0 SSE Server and listens for proactive trigger events:
  - prospective.trigger.fired: User-defined triggers (e.g., "remind me to drink water")
  - prospective.pattern.detected: Pattern detection (e.g., "milk day detected")
  - prospective.anomaly.alert: Anomaly alerts (e.g., "unusual spending")

Architecture:
  - SSE client maintains persistent connection to Mock K0 SSE Server (port 8002)
  - Subscribe to "prospective.*" events
  - Parse SSE events and dispatch to handler methods
  - Auto-reconnection with exponential backoff on disconnect
  - Graceful shutdown on DRAINING state

Handlers:
  - _handle_trigger_tick(): Process fired triggers (notify_user, enrich_context, invoke_agent)
  - _handle_pattern_tick(): Process pattern detection events
  - _handle_anomaly_tick(): Process anomaly alerts

References:
  - docs/whiteboard/chat_experience.md - ProactiveAgent SSE listener
  - Epic 4.2.1 - SSE Client Connection
  - Epic 4.2.2 - Proactive Trigger Handlers
"""

import asyncio
import json
from typing import Any, Dict, Optional

import httpx
import structlog
from l3_execution.agents.agent_base import AgentBase, AgentState

logger = structlog.get_logger(__name__)


class ProactiveAgent(AgentBase):
    """
    ProactiveAgent - Tier 1 Always-Active SSE Listener.

    Listens for proactive trigger events from Mock K0 SSE Server and notifies users
    or enriches context based on trigger actions.

    Lifecycle:
      - WARMING: Check SSE server health
      - ACTIVE: Connect to SSE server, start listening loop
      - IDLE: Not used (ProactiveAgent is always active)
      - DRAINING: Close SSE connection gracefully
      - TERMINATED: Cleanup resources
    """

    def __init__(
        self,
        agent_id: str,
        session_id: str,
        groq_client,
        mailbox: Optional[Any] = None,  # NEW: Accept mailbox from AgentFabric (Issue 1.2.2)
        trace_id: Optional[str] = None,
        sse_url: str = "http://localhost:8002/sse/stream",
    ):
        """
        Initialize ProactiveAgent.

        Args:
            agent_id: Unique agent identifier
            session_id: Session ID for this conversation
            groq_client: Groq client for LLM calls (not heavily used by ProactiveAgent)
            mailbox: Optional mailbox from AgentFabric (Issue 1.2.2)
            trace_id: Optional trace ID
            sse_url: SSE server URL (default: Mock K0 SSE Server)
        """
        super().__init__(
            agent_id=agent_id,
            agent_type="proactive",
            session_id=session_id,
            groq_client=groq_client,
            mailbox=mailbox,  # Pass mailbox to AgentBase
            trace_id=trace_id,
        )

        self.sse_url = sse_url
        self.sse_client: Optional[httpx.AsyncClient] = None
        self.sse_listen_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()

        # Metrics
        self.ticks_received = 0
        self.trigger_ticks = 0
        self.pattern_ticks = 0
        self.anomaly_ticks = 0
        self.gap_ticks = 0
        self.reconnect_attempts = 0

        # Gap resolution agents spawned (for tracking)
        self.active_gap_agents: Dict[str, Any] = {}

        logger.info(
            "proactive_agent_initialized",
            agent_id=agent_id,
            session_id=session_id,
            sse_url=sse_url,
            trace_id=trace_id,
        )

    async def on_warming(self):
        """
        WARMING lifecycle hook - Check SSE server health.

        Validates that Mock K0 SSE Server is reachable before transitioning to ACTIVE.
        """
        logger.info("proactive_agent_warming", agent_id=self.agent_id, trace_id=self.trace_id)

        try:
            # Check if SSE server is reachable (quick health check)
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Try to connect briefly to validate server is up
                # Note: SSE endpoint may not respond to HEAD, so we'll just validate connection
                response = await client.get(
                    f"{self.sse_url.replace('/sse/stream', '')}/health",
                    timeout=5.0,
                )
                if response.status_code != 200:
                    logger.warning(
                        "sse_server_health_check_failed",
                        status_code=response.status_code,
                        trace_id=self.trace_id,
                    )
                else:
                    logger.info(
                        "sse_server_health_check_passed",
                        trace_id=self.trace_id,
                    )
        except Exception as e:
            logger.warning(
                "sse_server_health_check_error",
                error=str(e),
                trace_id=self.trace_id,
                # Non-fatal: we'll retry connection in ACTIVE
            )

    async def on_active(self):
        """
        ACTIVE lifecycle hook - Connect to SSE server and start listening.

        Creates persistent SSE connection and starts background task to process events.
        """
        logger.info("proactive_agent_active", agent_id=self.agent_id, trace_id=self.trace_id)

        # Start SSE listening loop as background task
        self.sse_listen_task = asyncio.create_task(self._sse_listen_loop())
        logger.info(
            "sse_listen_loop_started",
            agent_id=self.agent_id,
            trace_id=self.trace_id,
        )

    async def on_draining(self):
        """
        DRAINING lifecycle hook - Close SSE connection gracefully.

        Signals shutdown, waits for listening task to complete, closes HTTP client.
        """
        logger.info("proactive_agent_draining", agent_id=self.agent_id, trace_id=self.trace_id)

        # Signal shutdown
        self._shutdown_event.set()

        # Close SSE client immediately to interrupt blocking read
        if self.sse_client:
            try:
                await self.sse_client.aclose()
                self.sse_client = None
                logger.info(
                    "sse_client_closed_for_shutdown", agent_id=self.agent_id, trace_id=self.trace_id
                )
            except Exception as e:
                logger.warning("sse_client_close_error", agent_id=self.agent_id, error=str(e))

        # Wait for SSE listening task to finish (with reduced timeout)
        if self.sse_listen_task:
            try:
                await asyncio.wait_for(self.sse_listen_task, timeout=1.0)  # Reduced from 5s to 1s
                logger.info(
                    "sse_listen_loop_stopped",
                    agent_id=self.agent_id,
                    trace_id=self.trace_id,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "sse_listen_loop_shutdown_timeout",
                    agent_id=self.agent_id,
                    trace_id=self.trace_id,
                )
                self.sse_listen_task.cancel()
                try:
                    await self.sse_listen_task
                except asyncio.CancelledError:
                    pass
            logger.info("sse_client_closed", agent_id=self.agent_id, trace_id=self.trace_id)

    async def on_terminated(self):
        """
        TERMINATED lifecycle hook - Cleanup resources.
        """
        logger.info("proactive_agent_terminated", agent_id=self.agent_id, trace_id=self.trace_id)

        # Ensure SSE client is closed
        if self.sse_client:
            await self.sse_client.aclose()
            self.sse_client = None

    async def _sse_listen_loop(self):
        """
        Background task: Connect to SSE server and process events.

        Maintains persistent connection with auto-reconnection on failure.
        Parses SSE events and dispatches to appropriate handlers.

        Reconnection strategy:
          - Exponential backoff: 5s, 10s, 20s, 40s (max 60s)
          - Retry indefinitely until shutdown signal
        """
        reconnect_delay = 5.0  # Initial delay in seconds
        max_reconnect_delay = 60.0

        while not self._shutdown_event.is_set():
            try:
                # Create new HTTP client for this connection attempt
                self.sse_client = httpx.AsyncClient(timeout=None)  # No timeout for SSE streaming

                # Connect to SSE server with topic subscription
                sse_params = {"topics": "prospective.*"}
                logger.info(
                    "connecting_to_sse_server",
                    url=self.sse_url,
                    params=sse_params,
                    trace_id=self.trace_id,
                )

                async with self.sse_client.stream(
                    "GET",
                    self.sse_url,
                    params=sse_params,
                ) as response:
                    if response.status_code != 200:
                        logger.error(
                            "sse_connection_failed",
                            status_code=response.status_code,
                            trace_id=self.trace_id,
                        )
                        raise Exception(f"SSE connection failed with status {response.status_code}")

                    logger.info(
                        "sse_connected",
                        status_code=response.status_code,
                        trace_id=self.trace_id,
                    )
                    reconnect_delay = 5.0  # Reset delay on successful connection
                    self.reconnect_attempts = 0

                    # Process SSE events line by line
                    async for line in response.aiter_lines():
                        if self._shutdown_event.is_set():
                            logger.info("sse_listen_loop_shutdown_signal", trace_id=self.trace_id)
                            break

                        # Parse SSE event format
                        await self._parse_sse_event(line)

            except httpx.HTTPError as e:
                logger.error(
                    "sse_connection_http_error",
                    error=str(e),
                    error_type=type(e).__name__,
                    reconnect_delay=reconnect_delay,
                    trace_id=self.trace_id,
                )
            except Exception as e:
                logger.error(
                    "sse_listen_loop_error",
                    error=str(e),
                    error_type=type(e).__name__,
                    reconnect_delay=reconnect_delay,
                    trace_id=self.trace_id,
                )

            # Close client after error
            if self.sse_client:
                await self.sse_client.aclose()
                self.sse_client = None

            # Check shutdown before reconnecting
            if self._shutdown_event.is_set():
                logger.info("sse_listen_loop_shutdown_before_reconnect", trace_id=self.trace_id)
                break

            # Wait before reconnecting (exponential backoff)
            self.reconnect_attempts += 1
            logger.info(
                "sse_reconnecting",
                attempt=self.reconnect_attempts,
                delay_seconds=reconnect_delay,
                trace_id=self.trace_id,
            )
            await asyncio.sleep(reconnect_delay)

            # Increase backoff delay (exponential with max cap)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

        logger.info("sse_listen_loop_exited", trace_id=self.trace_id)

    async def _parse_sse_event(self, line: str):
        """
        Parse SSE event line and dispatch to handler.

        SSE format:
          event: prospective.trigger.fired
          data: {"trigger_id": "...", "time": "...", "message": "...", ...}

        Args:
            line: SSE event line (event: or data:)
        """
        line = line.strip()

        # Skip empty lines and comments
        if not line or line.startswith(":"):
            return

        # Parse event type
        if line.startswith("event:"):
            self._current_event_type = line[6:].strip()
            return

        # Parse data payload
        if line.startswith("data:"):
            data_str = line[5:].strip()

            try:
                # Parse JSON payload
                data = json.loads(data_str)

                # Dispatch to handler based on event type
                event_type = getattr(self, "_current_event_type", "unknown")

                logger.debug(
                    "sse_event_received",
                    event_type=event_type,
                    data=data,
                    trace_id=self.trace_id,
                )

                self.ticks_received += 1

                if event_type == "prospective.trigger.fired":
                    await self._handle_trigger_tick(data)
                elif event_type == "prospective.pattern.detected":
                    await self._handle_pattern_tick(data)
                elif event_type == "prospective.anomaly.alert":
                    await self._handle_anomaly_tick(data)
                elif event_type == "knowledge.gap.detected":
                    await self._handle_knowledge_gap(data)
                else:
                    logger.warning(
                        "unknown_sse_event_type",
                        event_type=event_type,
                        trace_id=self.trace_id,
                    )

            except json.JSONDecodeError as e:
                logger.error(
                    "sse_event_parse_error",
                    error=str(e),
                    data_str=data_str,
                    trace_id=self.trace_id,
                )

    async def _handle_trigger_tick(self, tick_data: Dict[str, Any]):
        """
        Handle prospective.trigger.fired event.

        ProactiveAgent is USER-FACING: generates natural LLM response and streams to user.

        Trigger tick payload:
          {
            "trigger_id": "trigger_123",
            "time": "2025-11-05T14:30:00Z",
            "message": "Time to drink water!",
            "action": "notify_user",  # or "enrich_context", "invoke_agent"
            "metadata": {
              "daily_progress": "4/8",
              "agent_type": "routine"  # (if action=invoke_agent)
            }
          }

        Actions:
          - notify_user: Generate conversational LLM response and stream to user
          - enrich_context: Add to SessionState for next turn
          - invoke_agent: Send message to specified agent's mailbox

        Args:
            tick_data: Trigger tick payload
        """
        logger.info(
            "trigger_tick_received",
            tick_data=tick_data,
            trace_id=self.trace_id,
        )

        self.trigger_ticks += 1

        trigger_id = tick_data.get("trigger_id", "unknown")
        message = tick_data.get("message", "")
        action = tick_data.get("action", "notify_user")
        metadata = tick_data.get("metadata", {})

        if action == "notify_user":
            # Generate conversational notification using LLM
            logger.info(
                "generating_proactive_notification",
                trigger_id=trigger_id,
                message=message,
                trace_id=self.trace_id,
            )

            # Query user context for personalization
            user_context = await self.query_user_kg("get_preferences")

            # Get time context for proactive scheduling awareness (NEW: Time-aware)
            time_context = await self._get_time_context_from_session()

            # Build context for LLM (including time context for trigger timing)
            context_data = {
                "trigger_message": message,
                "trigger_id": trigger_id,
                "user_context": user_context,
                "daily_progress": metadata.get("daily_progress", ""),
                "metadata": metadata,
                "time_context": time_context,  # NEW: Include time context
            }

            # Call LLM to generate natural, conversational notification
            llm_response = await self.call_llm(
                user_input=f"Proactive reminder: {message}",
                context_data=context_data,
                temperature=0.7,  # Natural, friendly tone
            )

            notification = llm_response.get("content", message)

            logger.info(
                "proactive_notification_generated",
                notification=notification,
                trigger_id=trigger_id,
                trace_id=self.trace_id,
            )

            # Stream notification to user (POC: log, production: SSE stream to frontend)
            await self._stream_notification_to_user(notification, trigger_id)

            # Update SessionState (placeholder for POC)
            await self._update_session_state_with_notification(trigger_id, notification)

        elif action == "enrich_context":
            logger.info(
                "enriching_context_with_trigger",
                trigger_id=trigger_id,
                message=message,
                trace_id=self.trace_id,
            )

            # Add to SessionState.Control.proactive_triggers (placeholder for POC)
            await self._enrich_session_context(trigger_id, tick_data)

        elif action == "invoke_agent":
            agent_type = metadata.get("agent_type", "unknown")
            logger.info(
                "invoking_agent_from_trigger",
                trigger_id=trigger_id,
                agent_type=agent_type,
                message=message,
                trace_id=self.trace_id,
            )

            # Send message to agent's mailbox (placeholder for POC)
            await self._invoke_agent(agent_type, message, trigger_id)

        else:
            logger.warning(
                "unknown_trigger_action",
                action=action,
                trigger_id=trigger_id,
                trace_id=self.trace_id,
            )

    async def _handle_pattern_tick(self, tick_data: Dict[str, Any]):
        """
        Handle prospective.pattern.detected event.

        ProactiveAgent is USER-FACING: generates conversational LLM response.

        Pattern tick payload:
          {
            "pattern_id": "pattern_milk_day",
            "pattern_name": "Milk Day",
            "confidence": 0.85,
            "message": "Looks like today is milk day based on your history",
            "suggestion": "Reminder to buy milk?"
          }

        Args:
            tick_data: Pattern tick payload
        """
        logger.info(
            "pattern_tick_received",
            tick_data=tick_data,
            trace_id=self.trace_id,
        )

        self.pattern_ticks += 1

        pattern_name = tick_data.get("pattern_name", "unknown pattern")
        confidence = tick_data.get("confidence", 0.0)
        message = tick_data.get("message", "")
        suggestion = tick_data.get("suggestion", "")

        logger.info(
            "generating_pattern_notification",
            pattern_name=pattern_name,
            confidence=confidence,
            trace_id=self.trace_id,
        )

        # Query user context for personalization
        user_context = await self.query_user_kg("get_preferences")

        # Build context for LLM
        context_data = {
            "pattern_name": pattern_name,
            "pattern_message": message,
            "confidence": confidence,
            "suggestion": suggestion,
            "user_context": user_context,
        }

        # Call LLM to generate natural, conversational notification
        llm_response = await self.call_llm(
            user_input=f"Pattern detected: {message}. {suggestion}",
            context_data=context_data,
            temperature=0.7,
        )

        notification = llm_response.get("content", f"📊 {message} {suggestion}")

        logger.info(
            "pattern_notification_generated",
            notification=notification,
            pattern_name=pattern_name,
            trace_id=self.trace_id,
        )

        # Stream notification to user
        await self._stream_notification_to_user(
            notification, tick_data.get("pattern_id", "unknown")
        )

        # Update SessionState with pattern detection
        await self._update_session_state_with_pattern(tick_data)

    async def _handle_anomaly_tick(self, tick_data: Dict[str, Any]):
        """
        Handle prospective.anomaly.alert event.

        ProactiveAgent is USER-FACING: generates conversational LLM response.

        Anomaly tick payload:
          {
            "anomaly_id": "anomaly_spending_123",
            "anomaly_type": "unusual_spending",
            "severity": "medium",  # low, medium, high, critical
            "message": "Unusual spending detected",
            "details": "Large transaction: $500 at restaurant",
            "timestamp": "2025-11-05T18:45:00Z"
          }

        Args:
            tick_data: Anomaly tick payload
        """
        logger.info(
            "anomaly_tick_received",
            tick_data=tick_data,
            trace_id=self.trace_id,
        )

        self.anomaly_ticks += 1

        anomaly_type = tick_data.get("anomaly_type", "unknown")
        severity = tick_data.get("severity", "medium")
        message = tick_data.get("message", "")
        details = tick_data.get("details", "")

        logger.info(
            "generating_anomaly_alert",
            anomaly_type=anomaly_type,
            severity=severity,
            trace_id=self.trace_id,
        )

        # Query user context for personalization
        user_context = await self.query_user_kg("get_preferences")

        # Build context for LLM
        context_data = {
            "anomaly_type": anomaly_type,
            "severity": severity,
            "anomaly_message": message,
            "details": details,
            "user_context": user_context,
        }

        # Call LLM to generate natural, conversational alert
        # Temperature lower for alerts (more factual, less creative)
        llm_response = await self.call_llm(
            user_input=f"Anomaly alert ({severity} severity): {message}. {details}",
            context_data=context_data,
            temperature=0.5,  # Balanced - informative but friendly
        )

        notification = llm_response.get("content", f"⚠️ {message}: {details}")

        logger.info(
            "anomaly_alert_generated",
            notification=notification,
            anomaly_type=anomaly_type,
            severity=severity,
            trace_id=self.trace_id,
        )

        # Stream notification to user
        await self._stream_notification_to_user(
            notification, tick_data.get("anomaly_id", "unknown")
        )

        # Update SessionState with anomaly alert
        await self._update_session_state_with_anomaly(tick_data)

    async def _handle_knowledge_gap(self, gap_data: Dict[str, Any]):
        """
        Handle knowledge.gap.detected event.

        Spawns a GapResolutionAgent to ask the user about the detected gap
        and persist the learned information.

        Knowledge gap payload:
          {
            "gap_id": "gap_sam_unknown",
            "gap_type": "entity_unknown",
            "entity_name": "Sam",
            "context": "User said 'Sam needs to pick up groceries'",
            "confidence": 0.85,
            "suggested_questions": ["Who is Sam?", "Is Sam a family member?"]
          }

        Args:
            gap_data: Knowledge gap payload from SSE
        """
        logger.info(
            "knowledge_gap_received",
            gap_data=gap_data,
            trace_id=self.trace_id,
        )

        self.gap_ticks += 1

        gap_id = gap_data.get("gap_id", "unknown")
        entity_name = gap_data.get("entity_name", "unknown")
        gap_type = gap_data.get("gap_type", "entity_unknown")

        logger.info(
            "spawning_gap_resolution_agent",
            gap_id=gap_id,
            entity_name=entity_name,
            gap_type=gap_type,
            trace_id=self.trace_id,
        )

        try:
            # Import GapResolutionAgent
            # Generate unique agent ID for this gap resolution
            import uuid

            from l3_execution.agents.gap_resolution_agent import GapResolutionAgent

            agent_id = f"gap_agent_{uuid.uuid4().hex[:8]}"

            # Spawn GapResolutionAgent
            gap_agent = GapResolutionAgent(
                agent_id=agent_id,
                session_id=self.session_id,
                groq_client=self.groq_client,
                gap_data=gap_data,
                mailbox=None,  # Will get mailbox from AgentFabric if available
                trace_id=self.trace_id,
            )

            # Track active gap agent
            self.active_gap_agents[gap_id] = gap_agent

            # Transition through lifecycle
            await gap_agent.transition_to(AgentState.WARMING)
            await gap_agent.transition_to(AgentState.ACTIVE)

            logger.info(
                "gap_resolution_agent_spawned",
                agent_id=agent_id,
                gap_id=gap_id,
                entity_name=entity_name,
                question=gap_agent.question_asked,
                trace_id=self.trace_id,
            )

        except Exception as e:
            logger.error(
                "gap_resolution_agent_spawn_error",
                error=str(e),
                gap_id=gap_id,
                trace_id=self.trace_id,
            )

    async def handle_gap_response(self, gap_id: str, user_response: str):
        """
        Route user response to the appropriate GapResolutionAgent.

        Called when user answers a gap question (via mailbox or direct).

        Args:
            gap_id: Gap ID to match with active agent
            user_response: User's answer to the gap question
        """
        logger.info(
            "routing_gap_response",
            gap_id=gap_id,
            response_preview=user_response[:50] if user_response else "",
            trace_id=self.trace_id,
        )

        gap_agent = self.active_gap_agents.get(gap_id)
        if not gap_agent:
            logger.warning(
                "gap_agent_not_found",
                gap_id=gap_id,
                active_gaps=list(self.active_gap_agents.keys()),
                trace_id=self.trace_id,
            )
            return

        # Send response to gap agent
        await gap_agent.process_message(
            {
                "type": "gap_response",
                "gap_id": gap_id,
                "user_response": user_response,
            }
        )

        # Wait for resolution to complete
        resolved = await gap_agent.wait_for_response(timeout=30.0)

        if resolved:
            logger.info(
                "gap_resolved",
                gap_id=gap_id,
                learned_facts=gap_agent.learned_facts,
                trace_id=self.trace_id,
            )
            # Cleanup
            del self.active_gap_agents[gap_id]
        else:
            logger.warning(
                "gap_resolution_timeout",
                gap_id=gap_id,
                trace_id=self.trace_id,
            )

    # ==============================
    # SessionState & Notification Helpers (Placeholder for POC)
    # ==============================

    async def _stream_notification_to_user(self, notification: str, event_id: str):
        """
        Stream notification to user (user-facing SSE stream).

        ProactiveAgent is USER-FACING: streams LLM-generated notifications directly to user.

        POC: Log the notification with streaming simulation
        Production: Stream to frontend via SSE endpoint (POST /sse/proactive_notification)

        Args:
            notification: LLM-generated conversational notification
            event_id: Trigger/pattern/anomaly ID for tracking
        """
        logger.info(
            "streaming_notification_to_user",
            notification=notification,
            event_id=event_id,
            agent_id=self.agent_id,
            trace_id=self.trace_id,
        )

        # POC: Log as if streaming (simulate chunked delivery)
        chunks = [notification[i : i + 50] for i in range(0, len(notification), 50)]
        for i, chunk in enumerate(chunks):
            logger.debug(
                "notification_chunk",
                chunk_index=i,
                chunk=chunk,
                total_chunks=len(chunks),
                event_id=event_id,
                trace_id=self.trace_id,
            )

        logger.info(
            "notification_streamed_complete",
            event_id=event_id,
            notification_length=len(notification),
            trace_id=self.trace_id,
        )

        # In production:
        # async for chunk in self.groq_client.stream(
        #     messages=[{"role": "user", "content": prompt}],
        #     agent_type="proactive",
        #     trace_id=self.trace_id
        # ):
        #     # Send SSE chunk to frontend
        #     await sse_manager.send_event(
        #         session_id=self.session_id,
        #         event_type="proactive_notification",
        #         data={"chunk": chunk, "event_id": event_id}
        #     )

    async def _update_session_state_with_notification(self, trigger_id: str, notification: str):
        """
        Update SessionState with notification (placeholder for POC).

        Args:
            trigger_id: Trigger ID
            notification: Notification message
        """
        logger.debug(
            "session_state_update_notification",
            trigger_id=trigger_id,
            notification=notification,
            trace_id=self.trace_id,
        )

        # POC: Placeholder
        # In production:
        # await self.update_session_state(
        #     section="Scoreboard",
        #     updates={"proactive_notifications": [notification]}
        # )
        # await self.update_session_state(
        #     section="Meta",
        #     updates={"proactive_ticks_received": self.ticks_received}
        # )

    async def _enrich_session_context(self, trigger_id: str, tick_data: Dict[str, Any]):
        """
        Add trigger data to SessionState for context enrichment (placeholder for POC).

        Args:
            trigger_id: Trigger ID
            tick_data: Trigger tick payload
        """
        logger.debug(
            "session_context_enriched",
            trigger_id=trigger_id,
            trace_id=self.trace_id,
        )

        # POC: Placeholder
        # In production:
        # await self.update_session_state(
        #     section="Control",
        #     updates={"proactive_triggers": [tick_data]}
        # )

    async def _invoke_agent(self, agent_type: str, message: str, trigger_id: str):
        """
        Send message to specified agent's mailbox (placeholder for POC).

        Args:
            agent_type: Agent type to invoke (e.g., "routine")
            message: Message to send
            trigger_id: Trigger ID
        """
        logger.info(
            "agent_invocation",
            agent_type=agent_type,
            message=message,
            trigger_id=trigger_id,
            trace_id=self.trace_id,
        )

        # POC: Placeholder
        # In production:
        # await self.send_message(
        #     receiver_id=f"{agent_type}_agent",
        #     message_type="trigger_invocation",
        #     payload={"message": message, "trigger_id": trigger_id},
        #     priority=MessagePriority.STANDARD
        # )

    async def _update_session_state_with_pattern(self, tick_data: Dict[str, Any]):
        """Update SessionState with pattern detection (placeholder for POC)."""
        logger.debug(
            "session_state_update_pattern",
            pattern_id=tick_data.get("pattern_id"),
            trace_id=self.trace_id,
        )

    async def _update_session_state_with_anomaly(self, tick_data: Dict[str, Any]):
        """Update SessionState with anomaly alert (placeholder for POC)."""
        logger.debug(
            "session_state_update_anomaly",
            anomaly_id=tick_data.get("anomaly_id"),
            trace_id=self.trace_id,
        )

    # ==============================
    # AgentBase Abstract Method Implementation
    # ==============================

    async def process_message(self, message: Dict[str, Any]):
        """
        Process incoming message (required by AgentBase).

        ProactiveAgent primarily listens to SSE, not mailbox messages.
        This method handles control messages (e.g., "shutdown", "get_stats").

        Args:
            message: Incoming message from mailbox
        """
        message_type = message.get("type", "unknown")

        logger.info(
            "proactive_agent_message_received",
            message_type=message_type,
            trace_id=self.trace_id,
        )

        if message_type == "get_stats":
            # Return proactive agent statistics
            stats = {
                "ticks_received": self.ticks_received,
                "trigger_ticks": self.trigger_ticks,
                "pattern_ticks": self.pattern_ticks,
                "anomaly_ticks": self.anomaly_ticks,
                "reconnect_attempts": self.reconnect_attempts,
                "state": self.state.value,
            }
            logger.info("proactive_agent_stats", stats=stats, trace_id=self.trace_id)
            return stats

        elif message_type == "shutdown":
            logger.info("proactive_agent_shutdown_requested", trace_id=self.trace_id)
            await self.transition_to(AgentState.DRAINING)

        else:
            logger.warning(
                "unknown_message_type",
                message_type=message_type,
                trace_id=self.trace_id,
            )

    def get_stats(self) -> Dict[str, Any]:
        """
        Get ProactiveAgent statistics.

        Returns:
            Dict with metrics (ticks received, by type, reconnections)
        """
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "state": self.state.value,
            "ticks_received": self.ticks_received,
            "trigger_ticks": self.trigger_ticks,
            "pattern_ticks": self.pattern_ticks,
            "anomaly_ticks": self.anomaly_ticks,
            "gap_ticks": self.gap_ticks,
            "active_gap_agents": len(self.active_gap_agents),
            "reconnect_attempts": self.reconnect_attempts,
        }

    # ==============================
    # Time Context (NEW: Proactive Trigger Awareness)
    # ==============================

    async def _get_time_context_from_session(self) -> Dict[str, Any]:
        """
        Extract time context from session state for proactive trigger awareness.

        Uses time context for:
          - "It's 2pm, time for your afternoon break"
          - "You triggered this reminder for 7pm, it's only 3pm now"
          - "Notification arriving at peak activity time"

        Returns:
            Dict with time context fields for trigger scheduling

        Example usage:
          - "Your 8am workout reminder - great way to start the day!"
          - "It's after work hours, moving your evening meditation reminder"
          - Defer low-priority notifications to business hours
        """
        logger.debug(
            "extracting_time_context_for_proactive_trigger",
            trace_id=self.trace_id,
        )

        # POC: Return mock time context
        # In production: session_state.get_time_context()
        from datetime import datetime, timezone

        now_utc = datetime.now(timezone.utc)
        hour = now_utc.hour

        return {
            "current_time_utc": now_utc.isoformat(),
            "current_hour": hour,
            "day_of_week": now_utc.strftime("%A"),
            "is_morning": 5 <= hour < 12,
            "is_afternoon": 12 <= hour < 17,
            "is_evening": 17 <= hour < 21,
            "is_business_hours": 9 <= hour <= 17,
            "trigger_context": "scheduled on time" if 9 <= hour <= 17 else "off-hours trigger",
        }
