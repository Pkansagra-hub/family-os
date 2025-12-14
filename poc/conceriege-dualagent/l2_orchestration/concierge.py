"""
Concierge Coordinator - Orchestrates Reactive/Proactive lifecycle
"""

import asyncio
import logging
import uuid
from typing import Any, Dict

from config.settings import settings
from l3_execution.proactive_agent import ProactiveLLM
from l3_execution.reactive_agent import ReactiveLLM

logger = logging.getLogger(__name__)


class ConciergeCoordinator:
    """
    Orchestrates the dual-agent pattern:
    - Manages shared context between Reactive and Proactive
    - Coordinates message flow
    - Handles state transitions
    """

    def __init__(self, thread_id: str | None = None):
        self.thread_id = thread_id or f"{settings.thread_id_prefix}{uuid.uuid4().hex[:8]}"

        # Shared context between Reactive and Proactive
        self.shared_context: Dict[str, Any] = {
            "thread_id": self.thread_id,
            "conversation_history": [],
            "reactive_state": "idle",  # idle, active, waiting_for_specialist
            "proactive_state": "idle",  # idle, active
            "pending_clarification": None,
        }

        # Initialize agents
        self.reactive = ReactiveLLM(self.thread_id, self.shared_context)
        self.proactive = ProactiveLLM(self.thread_id, self.shared_context)

        logger.info(f"[Concierge] Initialized with thread_id: {self.thread_id}")

    async def process_user_message(self, message: str) -> list[str]:
        """
        Process user message through dual-agent system
        Returns list of messages to stream to user
        """
        logger.info(f"[Concierge] Processing user message: {message}")

        responses = []

        # Check if this is a clarification response
        if self.shared_context.get("pending_clarification"):
            logger.info("[Concierge] This is a clarification response")

            # Route to Proactive to handle
            await self.proactive.handle_user_clarification_response(message)

            # Proactive might send a warmth message
            warmth = await self.proactive._generate_warmth_message()
            responses.append(warmth)

            # Reactive is still waiting for final result
            # Continue waiting...
            return responses

        # Normal message flow
        # Start Reactive processing (which may trigger specialist)
        self.shared_context["reactive_state"] = "active"

        # Create task for Reactive
        reactive_task = asyncio.create_task(self.reactive.process_message(message))

        # Poll for specialist trigger (up to 2 seconds)
        proactive_task = None
        for i in range(20):  # Check 20 times over ~1 second
            if self.shared_context["reactive_state"] == "waiting_for_specialist":
                logger.info("[Concierge] Reactive triggered specialist, activating Proactive")

                # Start Proactive background conversation
                self.shared_context["proactive_state"] = "active"
                proactive_task = asyncio.create_task(self.proactive.start_background_conversation())
                logger.info("[Concierge] Proactive task started")
                break

            await asyncio.sleep(0.05)  # Check every 50ms

        # If Proactive was started, wait for its messages
        if proactive_task:
            try:
                logger.info("[Concierge] Waiting for Proactive messages...")
                proactive_messages = await asyncio.wait_for(proactive_task, timeout=60.0)
                logger.info(f"[Concierge] Received {len(proactive_messages)} proactive messages")
                responses.extend(proactive_messages)
            except asyncio.TimeoutError:
                logger.warning("[Concierge] Proactive conversation timeout")

            # Stop proactive when reactive returns
            self.proactive.stop()
            self.shared_context["proactive_state"] = "idle"
            logger.info("[Concierge] Proactive stopped")

        # Wait for Reactive to complete
        try:
            final_response = await reactive_task
            responses.append(final_response)

        except Exception as e:
            logger.error(f"[Concierge] Error in Reactive: {e}")
            responses.append("I'm sorry, I encountered an error processing your request.")

        self.shared_context["reactive_state"] = "idle"

        logger.info(f"[Concierge] Generated {len(responses)} response messages")
        return responses

    def get_conversation_history(self) -> list[Dict[str, Any]]:
        """Get conversation history"""
        return self.shared_context["conversation_history"]

    def get_state(self) -> Dict[str, Any]:
        """Get current state (for debugging)"""
        return {
            "thread_id": self.thread_id,
            "reactive_state": self.shared_context["reactive_state"],
            "proactive_state": self.shared_context["proactive_state"],
            "conversation_length": len(self.shared_context["conversation_history"]),
            "pending_clarification": self.shared_context.get("pending_clarification") is not None,
        }
