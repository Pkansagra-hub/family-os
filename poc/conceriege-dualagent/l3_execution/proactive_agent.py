"""
Proactive LLM Agent - Fills conversation gaps, handles clarifications
"""

import asyncio
import logging
from typing import Any, Dict

from groq import AsyncGroq

from config.settings import settings
from contracts.messages import JobClarification, JobClarificationResponse
from l5_infrastructure.handoff_space import get_handoff_space

logger = logging.getLogger(__name__)


class ProactiveLLM:
    """
    Proactive LLM Agent:
    - Fills gaps while Reactive/Specialist work
    - Handles clarification requests from Specialist
    - Yields when Reactive returns with results
    - Maintains conversation flow
    """

    def __init__(self, thread_id: str, shared_context: Dict[str, Any]):
        self.thread_id = thread_id
        self.shared_context = shared_context  # Shared with Reactive
        self.client = AsyncGroq(api_key=settings.groq_api_key)
        self.handoff = get_handoff_space()

        # Subscribe to clarification requests
        self.clarification_queue = self.handoff.subscribe(f"job.clarification.{thread_id}")

        self.is_active = False
        self._background_task: asyncio.Task | None = None

        self.system_prompt = """You are the Proactive Agent in a dual-agent concierge system.

Your role:
1. Keep the conversation flowing naturally while specialists work
2. Handle clarification questions from specialists
3. Maintain context and empathy
4. Yield gracefully when Reactive agent returns with results

When a specialist is working, you might:
- Explain what's happening ("Let me check our records...")
- Ask engaging follow-up questions
- Provide reassurance
- Relay specialist's clarification questions naturally

Context: You have full conversation history shared with Reactive agent.
You know when Reactive is waiting (reactive_state in shared_context)."""

    async def start_background_conversation(self) -> list[str]:
        """
        Start proactive conversation while specialist works
        Returns list of messages to stream to user
        """
        logger.info("[Proactive] Starting background conversation")
        self.is_active = True

        messages = []

        # Initial transition message
        initial_msg = await self._generate_transition_message()
        messages.append(initial_msg)
        logger.info(f"[Proactive] Added initial transition message: {len(messages)} total messages")

        # Listen for clarifications while being conversational
        try:
            attempt_count = 0
            while (
                self.is_active
                and self.shared_context.get("reactive_state") == "waiting_for_specialist"
            ):
                attempt_count += 1
                logger.info(f"[Proactive] Listening for clarifications (attempt {attempt_count})...")

                # Check for clarification request (non-blocking with timeout)
                try:
                    clarification = await asyncio.wait_for(
                        self.clarification_queue.get(), timeout=2.0
                    )
                    logger.info(f"[Proactive] Received clarification request")

                    # Handle clarification
                    clarification_msg = await self._handle_clarification(clarification)
                    messages.append(clarification_msg)
                    logger.info(f"[Proactive] Added clarification message: {len(messages)} total messages")

                    # Wait for user response (would come from WebSocket)
                    # For now, this will be coordinated by Concierge

                except asyncio.TimeoutError:
                    # No clarification, keep conversation warm
                    if len(messages) == 1:  # Only sent initial message
                        logger.info("[Proactive] No clarification yet, adding warmth message...")
                        warm_msg = await self._generate_warmth_message()
                        messages.append(warm_msg)
                        logger.info(f"[Proactive] Added warmth message: {len(messages)} total messages")
                        await asyncio.sleep(2)  # Give specialist more time
                    else:
                        logger.info("[Proactive] Already sent messages, waiting for clarification or completion...")
                        await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"[Proactive] Error in background: {e}")

        logger.info(f"[Proactive] Background conversation ended with {len(messages)} total messages")
        return messages

    def stop(self):
        """Stop proactive conversation (Reactive has returned)"""
        logger.info("[Proactive] Yielding to Reactive")
        self.is_active = False

    async def _generate_transition_message(self) -> str:
        """Generate initial message when specialist is triggered"""

        prompt = f"""The user just asked: {self.shared_context['conversation_history'][-1]['content'] if self.shared_context['conversation_history'] else 'a health question'}

Generate a brief, natural transition message that:
- Acknowledges their question warmly
- Explains you're gathering relevant information
- Maintains a conversational, supportive tone

Examples:
- "Great question! Let me pull up our records and relevant information for you..."
- "I'll get our specialist to look into that for you right away..."
- "Let me gather the most relevant information to give you the best answer..."

Keep response under 30 words. Generate ONLY the transition message, nothing else:"""

        try:
            response = await self.client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=100,
            )

            msg = response.choices[0].message.content.strip()
            if not msg:
                msg = "Let me gather the relevant information for you..."
            logger.info(f"[Proactive] Transition: {msg}")
            return msg

        except Exception as e:
            logger.error(f"[Proactive] Error generating transition: {e}")
            return "Let me look into that for you..."

    async def _generate_warmth_message(self) -> str:
        """Generate a warm message to fill time"""

        prompt = """The specialist is still analyzing the user's health question.
Generate a brief, warm message that:
- Shows you're still engaged and working on their question
- Provides reassurance or helpful context
- Maintains conversational warmth
- Keeps the conversation flowing naturally

Examples:
- "Our specialist is gathering all the relevant information..."
- "Just pulling together the best guidance for your situation..."
- "Working on getting you the most helpful information..."

Keep it under 25 words. Generate ONLY the warmth message, nothing else:"""

        try:
            response = await self.client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
                max_tokens=80,
            )

            msg = response.choices[0].message.content.strip()
            if not msg:
                msg = "Still compiling the best information for you..."
            logger.info(f"[Proactive] Warmth: {msg}")
            return msg

        except Exception as e:
            logger.error(f"[Proactive] Error generating warmth: {e}")
            return "Still working on that..."

    async def _handle_clarification(self, clarification: JobClarification) -> str:
        """
        Handle clarification request from specialist
        Formats it naturally for the user
        """
        logger.info(f"[Proactive] Handling clarification: {clarification.question}")

        prompt = f"""The nutritionist specialist needs clarification from the user.

Specialist's question: "{clarification.question}"

Rephrase this naturally and conversationally, as if you're asking on behalf of the specialist.
Keep it friendly and clear. Under 40 words.

Your question to user:"""

        try:
            response = await self.client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=120,
            )

            msg = response.choices[0].message.content.strip()
            logger.info(f"[Proactive] Clarification question: {msg}")

            # Store clarification in shared context
            self.shared_context["pending_clarification"] = {
                "specialist": clarification.specialist_name,
                "round": clarification.clarification_round,
                "original_question": clarification.question,
            }

            return msg

        except Exception as e:
            logger.error(f"[Proactive] Error handling clarification: {e}")
            return clarification.question

    async def handle_user_clarification_response(self, user_answer: str):
        """
        User responded to clarification question
        Route back to specialist via handoff space
        """
        pending = self.shared_context.get("pending_clarification")
        if not pending:
            logger.warning("[Proactive] No pending clarification")
            return

        logger.info(f"[Proactive] Routing clarification response to {pending['specialist']}")

        response = JobClarificationResponse(
            thread_id=self.thread_id,
            specialist_name=pending["specialist"],
            answer=user_answer,
            clarification_round=pending["round"],
        )

        await self.handoff.publish(f"job.clarification_response.{self.thread_id}", response)

        # Clear pending
        self.shared_context.pop("pending_clarification", None)

        # Add to conversation history
        self.shared_context["conversation_history"].append(
            {"role": "user", "content": user_answer, "context": "clarification_response"}
        )
