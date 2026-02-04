"""
GapResolutionAgent - Proactive agent for resolving knowledge gaps

When K0 detects a knowledge gap (e.g., unknown entity "Sam" mentioned in conversation),
this agent is spawned to ask the user for clarification and persist the learned info.

Flow:
1. SSE event: knowledge.gap.detected arrives at ProactiveAgent
2. ProactiveAgent spawns GapResolutionAgent with gap details
3. GapResolutionAgent generates a friendly question to ask the user
4. User responds (via mailbox)
5. GapResolutionAgent extracts the learning and emits to DeltaBus
6. Writer agents persist the learned entity/relationship to K0

Example gap signal:
{
    "gap_id": "gap_sam_unknown",
    "gap_type": "entity_unknown",
    "entity_name": "Sam",
    "context": "User said 'Sam needs to pick up groceries'",
    "confidence": 0.85,
    "suggested_questions": [
        "Who is Sam?",
        "Is Sam a family member?"
    ]
}

References:
- ProactiveAgent SSE listener for knowledge.gap.detected events
- DeltaBus session.delta for learning signal emission
- Writer agents for K0 persistence
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog
from l3_execution.agents.agent_base import AgentBase, AgentState

logger = structlog.get_logger(__name__)


class GapResolutionAgent(AgentBase):
    """
    GapResolutionAgent - Tier 2 agent for resolving knowledge gaps.

    Spawned by ProactiveAgent when a knowledge gap is detected.
    Asks the user for clarification and persists learned information.

    Lifecycle:
      - WARMING: Prepare gap question
      - ACTIVE: Ask user, wait for response, process learning
      - DRAINING: Complete current resolution
      - TERMINATED: Cleanup
    """

    def __init__(
        self,
        agent_id: str,
        session_id: str,
        groq_client,
        gap_data: Dict[str, Any],
        mailbox: Optional[Any] = None,
        trace_id: Optional[str] = None,
    ):
        """
        Initialize GapResolutionAgent.

        Args:
            agent_id: Unique agent identifier
            session_id: Session ID
            groq_client: LLM client (Google/Groq)
            gap_data: Knowledge gap details from SSE event
            mailbox: Optional mailbox from AgentFabric
            trace_id: Optional trace ID
        """
        super().__init__(
            agent_id=agent_id,
            agent_type="gap_resolution",
            session_id=session_id,
            groq_client=groq_client,
            mailbox=mailbox,
            trace_id=trace_id,
        )

        self.gap_data = gap_data
        self.gap_id = gap_data.get("gap_id", f"gap_{uuid.uuid4().hex[:8]}")
        self.entity_name = gap_data.get("entity_name", "unknown")
        self.gap_type = gap_data.get("gap_type", "entity_unknown")
        self.context = gap_data.get("context", "")
        self.suggested_questions = gap_data.get("suggested_questions", [])

        # State for resolution flow
        self.question_asked: Optional[str] = None
        self.user_response: Optional[str] = None
        self.learned_facts: Dict[str, Any] = {}
        self.resolution_complete = False

        # Response event for async await
        self._response_event = asyncio.Event()

        logger.info(
            "gap_resolution_agent_initialized",
            agent_id=agent_id,
            gap_id=self.gap_id,
            entity_name=self.entity_name,
            gap_type=self.gap_type,
            trace_id=trace_id,
        )

    async def on_warming(self):
        """WARMING: Prepare the question to ask the user."""
        logger.info(
            "gap_resolution_warming",
            agent_id=self.agent_id,
            gap_id=self.gap_id,
            trace_id=self.trace_id,
        )

        # Generate a friendly question using LLM
        self.question_asked = await self._generate_gap_question()

        logger.info(
            "gap_question_prepared",
            question=self.question_asked,
            gap_id=self.gap_id,
            trace_id=self.trace_id,
        )

    async def on_active(self):
        """ACTIVE: Send question to user and wait for response."""
        logger.info(
            "gap_resolution_active",
            agent_id=self.agent_id,
            gap_id=self.gap_id,
            trace_id=self.trace_id,
        )

        # Stream question to user (for demo, we emit via DeltaBus)
        await self._stream_question_to_user()

    async def on_draining(self):
        """DRAINING: Complete any pending resolution."""
        logger.info(
            "gap_resolution_draining",
            agent_id=self.agent_id,
            gap_id=self.gap_id,
            resolution_complete=self.resolution_complete,
            trace_id=self.trace_id,
        )

    async def on_terminated(self):
        """TERMINATED: Cleanup."""
        logger.info(
            "gap_resolution_terminated",
            agent_id=self.agent_id,
            gap_id=self.gap_id,
            learned_facts=self.learned_facts,
            trace_id=self.trace_id,
        )

    async def _generate_gap_question(self) -> str:
        """
        Generate a friendly, contextual question to ask the user about the gap.

        Returns:
            Natural language question string
        """
        # Build prompt for LLM - direct and simple to avoid thinking tokens
        prompt = f"""Generate ONE friendly question to ask about "{self.entity_name}".
Context: {self.context}
Output only the question, nothing else. Example: "Who is Sam to you?"
Question:"""

        try:
            response = await self.call_llm(
                user_input=prompt,
                context_data={"gap_type": self.gap_type, "entity": self.entity_name},
                temperature=0.5,
                max_tokens=150,  # Increased for complete response
            )

            question = response.get("content", "").strip()
            # Clean up any "Question:" prefix if present
            if question.lower().startswith("question:"):
                question = question[9:].strip()

            if not question or len(question) < 10:
                # Fallback to first suggested question or default
                question = (
                    self.suggested_questions[0]
                    if self.suggested_questions
                    else f"Could you tell me more about {self.entity_name}?"
                )

            return question

        except Exception as e:
            logger.error(
                "gap_question_generation_error",
                error=str(e),
                gap_id=self.gap_id,
                trace_id=self.trace_id,
            )
            # Fallback
            return f"I noticed you mentioned {self.entity_name}. Could you tell me who that is?"

    async def _stream_question_to_user(self):
        """
        Stream the gap question to the user via DeltaBus.

        For the demo, this emits a proactive.question event that
        the frontend (or demo script) can display and respond to.
        """
        from l4_runtime.deltabus.deltabus import DeltaBusEvent, EventType, get_deltabus

        deltabus = get_deltabus()

        event = DeltaBusEvent(
            event_type=EventType.PROACTIVE_QUESTION.value,
            session_id=self.session_id,
            trace_id=self.trace_id or "unknown",
            payload={
                "agent_id": self.agent_id,
                "gap_id": self.gap_id,
                "entity_name": self.entity_name,
                "question": self.question_asked,
                "gap_type": self.gap_type,
                "context": self.context,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        deltabus.publish(event)

        logger.info(
            "gap_question_streamed",
            gap_id=self.gap_id,
            question=self.question_asked,
            trace_id=self.trace_id,
        )

    async def process_message(self, message: Dict[str, Any]):
        """
        Process incoming message (user response to gap question).

        Expected message format:
        {
            "type": "gap_response",
            "gap_id": "gap_sam_unknown",
            "user_response": "Sam is my brother"
        }
        """
        message_type = message.get("type", "unknown")

        logger.info(
            "gap_resolution_message_received",
            message_type=message_type,
            gap_id=self.gap_id,
            trace_id=self.trace_id,
        )

        if message_type == "gap_response":
            user_response = message.get("user_response", "")
            gap_id = message.get("gap_id", "")

            if gap_id != self.gap_id:
                logger.warning(
                    "gap_id_mismatch",
                    expected=self.gap_id,
                    received=gap_id,
                    trace_id=self.trace_id,
                )
                return

            self.user_response = user_response
            logger.info(
                "user_response_received",
                gap_id=self.gap_id,
                response=user_response,
                trace_id=self.trace_id,
            )

            # Extract learning from response
            await self._extract_learning_from_response()

            # Emit learning signal to session state / DeltaBus
            await self._emit_learning_signal()

            # Mark resolution complete
            self.resolution_complete = True
            self._response_event.set()

            # Transition to draining
            await self.transition_to(AgentState.DRAINING)

        else:
            logger.warning(
                "unknown_gap_message_type",
                message_type=message_type,
                trace_id=self.trace_id,
            )

    async def _extract_learning_from_response(self):
        """
        Use LLM to extract structured facts from user's response.

        Example:
            User: "Sam is my brother, he's 25 and lives in Austin"
            Extracted: {
                "entity": "Sam",
                "relationship": "brother",
                "attributes": {"age": 25, "location": "Austin"}
            }
        """
        if not self.user_response:
            return

        prompt = f"""Extract facts about "{self.entity_name}" from this response.

User's response: "{self.user_response}"
Original context: "{self.context}"

Return JSON with:
{{"entity": "<name>", "entity_type": "<person|place|thing|event>", "relationship": "<relationship to user if applicable>", "attributes": {{"<key>": "<value>", ...}}}}

Only output valid JSON, nothing else."""

        try:
            response = await self.call_llm(
                user_input=prompt,
                context_data={"entity": self.entity_name},
                temperature=0.2,
                max_tokens=300,
            )

            content = response.get("content", "").strip()

            # Parse JSON from response
            try:
                # Try direct parse
                self.learned_facts = json.loads(content)
            except json.JSONDecodeError:
                # Try extracting JSON from markdown
                if "```json" in content:
                    json_str = content.split("```json")[1].split("```")[0].strip()
                    self.learned_facts = json.loads(json_str)
                elif "```" in content:
                    json_str = content.split("```")[1].split("```")[0].strip()
                    self.learned_facts = json.loads(json_str)
                else:
                    # Fallback: create basic fact
                    self.learned_facts = {
                        "entity": self.entity_name,
                        "entity_type": "unknown",
                        "raw_response": self.user_response,
                    }

            logger.info(
                "learning_extracted",
                gap_id=self.gap_id,
                learned_facts=self.learned_facts,
                trace_id=self.trace_id,
            )

        except Exception as e:
            logger.error(
                "learning_extraction_error",
                error=str(e),
                gap_id=self.gap_id,
                trace_id=self.trace_id,
            )
            # Fallback
            self.learned_facts = {
                "entity": self.entity_name,
                "entity_type": "unknown",
                "raw_response": self.user_response,
            }

    async def _emit_learning_signal(self):
        """
        Emit learning signal to DeltaBus for writer agents to persist.

        This creates a session.delta event with delta_type="learning"
        that the LearningExtractorAgent and MemoryWriterAgent will process.
        """
        from l4_runtime.deltabus.deltabus import DeltaBusEvent, get_deltabus

        deltabus = get_deltabus()

        # Build learning delta payload
        learning_payload = {
            "delta_type": "learning",
            "session_id": self.session_id,
            "trace_id": self.trace_id or "unknown",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_chain": [self.agent_id],
            "source": "gap_resolution",
            "gap_id": self.gap_id,
            "entity_learned": self.entity_name,
            "learned_facts": self.learned_facts,
            "user_text": self.user_response or "",
            "question_text": self.question_asked or "",
            "confidence": 0.9,  # User-provided = high confidence
        }

        event = DeltaBusEvent(
            event_type="session.delta",
            session_id=self.session_id,
            trace_id=self.trace_id or "unknown",
            payload=learning_payload,
        )

        deltabus.publish(event)

        logger.info(
            "learning_signal_emitted",
            gap_id=self.gap_id,
            entity=self.entity_name,
            facts=self.learned_facts,
            trace_id=self.trace_id,
        )

    async def wait_for_response(self, timeout: float = 60.0) -> bool:
        """
        Wait for user response to gap question.

        Args:
            timeout: Max seconds to wait

        Returns:
            True if response received, False if timeout
        """
        try:
            await asyncio.wait_for(self._response_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logger.warning(
                "gap_response_timeout",
                gap_id=self.gap_id,
                timeout=timeout,
                trace_id=self.trace_id,
            )
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get GapResolutionAgent statistics."""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "state": self.state.value,
            "gap_id": self.gap_id,
            "entity_name": self.entity_name,
            "gap_type": self.gap_type,
            "question_asked": self.question_asked,
            "user_response": self.user_response,
            "learned_facts": self.learned_facts,
            "resolution_complete": self.resolution_complete,
        }
