"""
Concierge Agent - Front-line conversational interface for FamilyOS

This agent sits in front of the Planning Pipeline and provides:
1. Natural conversation for casual queries
2. Intent detection (chat vs actionable planning)
3. Chat history management
4. Clarification proxy between user and planner
5. Plan history tracking for context

Architecture:
┌─────────────────────────────────────────────────────────────┐
│                    CONCIERGE AGENT                          │
│  User ←→ [Chat History] ←→ [Intent Detection] ←→ Response  │
│                              ↓                               │
│                    [Chat Mode | Plan Mode]                  │
│                              ↓                               │
│                    Planning Pipeline (stateless)            │
└─────────────────────────────────────────────────────────────┘

Flow:
1. User sends message
2. Concierge adds to chat history
3. LLM decides: "chat" or "plan"
4. Chat mode: Generate conversational response
5. Plan mode: Invoke planner, handle clarifications
6. Return response to user

References:
- M5: HITL Integration Testing
- ADR-0054d: Dialogue Repair & Clarification
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

# Configure logging
logger = logging.getLogger(__name__)


class IntentType(Enum):
    """Intent classification for user messages"""

    CHAT = "chat"  # Casual conversation, no action needed
    PLAN = "plan"  # Actionable task requiring planning


@dataclass
class ChatMessage:
    """Single message in chat history"""

    role: str  # "user" or "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlanRecord:
    """Record of a completed plan for context"""

    flow_id: str
    intent: str
    summary: str
    status: str  # "COMMITTED", "REJECTED", etc.
    timestamp: float = field(default_factory=time.time)


class ConciergeAgent:
    """
    Concierge Agent - Conversational front-end for Planning Pipeline

    Responsibilities:
    - Maintain chat history with user
    - Detect intent: chat vs actionable planning
    - Handle casual conversation via LLM
    - Invoke Planning Pipeline for actionable tasks
    - Proxy clarification requests between planner and user
    - Track plan history for contextual awareness

    Usage:
        concierge = ConciergeAgent(llm_provider, planning_pipeline)
        response = await concierge.process_message("Book dinner at 7pm")
    """

    def __init__(
        self,
        llm_provider,
        planning_pipeline=None,
        max_history: int = 20,
    ):
        """
        Initialize Concierge Agent

        Args:
            llm_provider: LLM provider for chat and intent detection
            planning_pipeline: Planning pipeline instance (optional, for dependency injection)
            max_history: Maximum chat messages to retain
        """
        self.llm_provider = llm_provider
        self.planning_pipeline = planning_pipeline

        # Chat history (user ↔ concierge)
        self.chat_history: List[ChatMessage] = []
        self.max_history = max_history

        # Plan history (for contextual awareness)
        self.plan_history: List[PlanRecord] = []
        self.max_plan_history = 10

        # State tracking
        self.active_planning = False  # Currently in planning mode
        self.pending_clarification = None  # Waiting for clarification response

        logger.info("ConciergeAgent initialized")

    def add_message(self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Add message to chat history

        Args:
            role: "user" or "assistant"
            content: Message content
            metadata: Optional metadata (intent, plan_id, etc.)
        """
        message = ChatMessage(role=role, content=content, metadata=metadata or {})
        self.chat_history.append(message)

        # Trim history if needed
        if len(self.chat_history) > self.max_history:
            self.chat_history = self.chat_history[-self.max_history :]

        logger.debug(f"Added {role} message: {content[:50]}...")

    def get_time_context(self) -> str:
        """
        Get current time context for LLM awareness

        Returns:
            Formatted time context string
        """
        now = datetime.now()
        day_name = now.strftime("%A")
        date_str = now.strftime("%B %d, %Y")
        time_str = now.strftime("%I:%M %p")

        return f"Current Time: {day_name}, {date_str}, {time_str}"

    def get_chat_context(self, last_n: int = 10) -> str:
        """
        Get recent chat history as formatted string

        Args:
            last_n: Number of recent messages to include

        Returns:
            Formatted chat history
        """
        recent = self.chat_history[-last_n:]
        context = ""
        for msg in recent:
            context += f"{msg.role.upper()}: {msg.content}\n"
        return context.strip()

    async def detect_intent(self, user_message: str) -> IntentType:
        """
        Use LLM to detect if message requires planning or just chat

        Args:
            user_message: User's message

        Returns:
            IntentType.CHAT or IntentType.PLAN
        """
        # Build context from recent chat
        chat_context = self.get_chat_context(last_n=5)
        time_context = self.get_time_context()

        # Intent detection prompt
        intent_prompt = f"""You are an intent classifier. Given a user message and chat history, determine if the user wants:
- CHAT: Casual conversation, asking questions, or general interaction (no action needed)
- PLAN: Actionable task requiring planning (booking, scheduling, ordering, etc.)

{time_context}

Chat History:
{chat_context}

Current Message:
USER: {user_message}

Rules:
1. CHAT examples: "Hi", "How are you?", "What's the weather?", "Tell me about...", "Thanks", "Goodbye"
2. PLAN examples: "Book dinner", "Schedule meeting", "Order pizza", "Remind me to...", "Set timer"
3. If user asks a question that needs external data (weather, news), return CHAT (concierge can answer)
4. Only return PLAN if user wants to CREATE/MODIFY/DELETE something

Output ONLY one word: CHAT or PLAN"""

        try:
            # Call LLM for intent classification
            response = await asyncio.to_thread(
                self.llm_provider.call_llm,
                prompt=intent_prompt,
                max_tokens=10,
                system_message="You are an intent classifier. Respond with only CHAT or PLAN.",
            )

            intent_str = response.strip().upper()

            if "PLAN" in intent_str:
                logger.info(f"Intent detected: PLAN for '{user_message[:50]}...'")
                return IntentType.PLAN
            else:
                logger.info(f"Intent detected: CHAT for '{user_message[:50]}...'")
                return IntentType.CHAT

        except Exception as e:
            logger.error(f"Intent detection failed: {e}, defaulting to CHAT")
            return IntentType.CHAT

    async def handle_chat(self, user_message: str) -> str:
        """
        Handle casual conversation with LLM

        Args:
            user_message: User's message

        Returns:
            Assistant's conversational response
        """
        # Build chat context
        chat_context = self.get_chat_context(last_n=10)
        time_context = self.get_time_context()

        # Add plan context if available
        plan_context = ""
        if self.plan_history:
            recent_plans = self.plan_history[-3:]
            plan_context = "\n\nRecent Plans:\n"
            for plan in recent_plans:
                plan_context += f"- {plan.intent}: {plan.summary} ({plan.status})\n"

        # Chat prompt
        chat_prompt = f"""You are a friendly, helpful AI assistant. Have a natural conversation with the user.

{time_context}

Chat History:
{chat_context}
USER: {user_message}{plan_context}

Guidelines:
- Be warm, friendly, and conversational
- Keep responses concise (2-3 sentences max)
- If user asks about planning/tasks, remind them you can help plan things
- Use their name if they provided it in history
- Show personality and empathy
- Use the current time context to answer time-related questions accurately

Generate a natural response:"""

        try:
            # Call LLM for conversational response
            response = await asyncio.to_thread(
                self.llm_provider.call_llm,
                prompt=chat_prompt,
                max_tokens=150,
                system_message="You are a friendly AI assistant. Be conversational and helpful.",
            )

            return response.strip()

        except Exception as e:
            logger.error(f"Chat generation failed: {e}")
            return "I'm here to help! What would you like to do?"

    async def handle_planning(
        self, user_message: str, session=None, trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Invoke Planning Pipeline for actionable tasks

        Args:
            user_message: User's actionable request
            session: Optional database session
            trace_id: Optional trace ID

        Returns:
            Planning result dict with status, flow_id, or clarification request
        """
        if not self.planning_pipeline:
            logger.error("Planning pipeline not configured")
            return {
                "status": "ERROR",
                "message": "Planning system not available",
            }

        try:
            self.active_planning = True

            # Create default session if not provided
            if session is None:
                print("[Concierge] Creating default session for planning")
                try:
                    # Import SessionFixture for creating default session
                    from poc_planning_pipeline import SessionFixture

                    session = SessionFixture(
                        session_id="concierge_session",
                        band="GREEN",
                        caps=None,
                    )
                    print(f"[Concierge] Created session: {session.id}, budget: {session.budget}")
                except Exception as import_error:
                    print(f"[Concierge] Failed to import SessionFixture: {import_error}")

                    # Create a minimal mock session
                    class MinimalSession:
                        def __init__(self):
                            self.id = "concierge_session"
                            self.band = "GREEN"
                            self.budget = {"latency_ms": 10000, "cost": 1.0}
                            self.available_tools = set()
                            self.available_caps = set()

                    session = MinimalSession()
                    print("[Concierge] Created minimal mock session")
            else:
                print(
                    f"[Concierge] Using provided session: {session.id if hasattr(session, 'id') else 'unknown'}"
                )

            print(
                f"[Concierge] Invoking planner with session: {session}, budget: {getattr(session, 'budget', 'N/A')}"
            )

            # Invoke planning pipeline
            result = await self.planning_pipeline.plan(
                user_input=user_message,
                session=session,
                trace_id=trace_id,
            )

            self.active_planning = False

            # Check if planner needs clarification
            if result.get("status") == "NEEDS_CLARIFICATION":
                # Planner is asking for clarification
                self.pending_clarification = {
                    "original_message": user_message,
                    "question": result.get("question", "Can you provide more details?"),
                    "context": result.get("context", {}),
                    "session": session,  # Store session for reuse
                }
                return result

            # Plan completed (COMMITTED or REJECTED)
            if result.get("status") == "COMMITTED":
                # Track successful plan
                plan_record = PlanRecord(
                    flow_id=result.get("flow_id", "unknown"),
                    intent=result.get("intent", "unknown"),
                    summary=result.get("summary", user_message[:100]),
                    status="COMMITTED",
                )
                self.plan_history.append(plan_record)

                # Trim plan history
                if len(self.plan_history) > self.max_plan_history:
                    self.plan_history = self.plan_history[-self.max_plan_history :]

            return result

        except Exception as e:
            logger.error(f"Planning failed: {e}")
            self.active_planning = False
            return {
                "status": "ERROR",
                "message": f"Planning error: {str(e)}",
            }

    async def process_message(
        self, user_message: str, session=None, trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Main entry point: Process user message and return response

        Flow:
        1. Add message to chat history
        2. Check if responding to clarification
        3. Detect intent (chat vs plan)
        4. Route to appropriate handler
        5. Return structured response

        Args:
            user_message: User's message
            session: Optional database session for planning
            trace_id: Optional trace ID for planning

        Returns:
            Response dict:
            - mode: "chat" or "plan"
            - response: String response for chat, or plan result dict
            - status: Success indicator
        """
        start_time = time.time()

        # Add user message to history
        self.add_message("user", user_message)

        # Check if this is a clarification response
        if self.pending_clarification:
            logger.info("Processing clarification response")
            clarification_data = self.pending_clarification
            self.pending_clarification = None

            # Add clarification response to planner's clarification manager
            if self.planning_pipeline and self.planning_pipeline.clarification_manager:
                self.planning_pipeline.clarification_manager.add_user_response(user_message)
                print("[Concierge] Added clarification response to planner's history")

            # Resume planning with clarification - use accumulated context
            # The planner will see the full conversation history
            combined_message = f"{clarification_data['original_message']}. {user_message}"

            # Reuse the same session if provided, or create once
            if session is None and hasattr(clarification_data, "session"):
                session = clarification_data.get("session")

            result = await self.handle_planning(combined_message, session, trace_id)

            # Check if planner needs MORE clarification
            if result.get("status") == "NEEDS_CLARIFICATION":
                # Still need more info
                return {
                    "mode": "clarification",
                    "response": result.get("question"),
                    "status": "pending",
                    "latency_ms": (time.time() - start_time) * 1000,
                }

            # Planning complete
            assistant_response = self._format_plan_result(result)
            self.add_message("assistant", assistant_response, metadata={"plan_result": result})

            return {
                "mode": "plan",
                "response": assistant_response,
                "plan_result": result,
                "status": "success",
                "latency_ms": (time.time() - start_time) * 1000,
            }

        # Detect intent: chat or plan
        intent = await self.detect_intent(user_message)

        if intent == IntentType.CHAT:
            # Handle as conversation
            response = await self.handle_chat(user_message)
            self.add_message("assistant", response)

            return {
                "mode": "chat",
                "response": response,
                "status": "success",
                "latency_ms": (time.time() - start_time) * 1000,
            }

        else:  # IntentType.PLAN
            # Invoke planning pipeline
            result = await self.handle_planning(user_message, session, trace_id)

            # Check if needs clarification
            if result.get("status") == "NEEDS_CLARIFICATION":
                # Store clarification context
                return {
                    "mode": "clarification",
                    "response": result.get("question"),
                    "status": "pending",
                    "latency_ms": (time.time() - start_time) * 1000,
                }

            # Planning complete
            assistant_response = self._format_plan_result(result)
            self.add_message("assistant", assistant_response, metadata={"plan_result": result})

            return {
                "mode": "plan",
                "response": assistant_response,
                "plan_result": result,
                "status": "success",
                "latency_ms": (time.time() - start_time) * 1000,
            }

    def _format_plan_result(self, result: Dict[str, Any]) -> str:
        """
        Format plan result into natural language response

        Args:
            result: Plan result dict from pipeline

        Returns:
            Natural language summary
        """
        status = result.get("status", "UNKNOWN")

        if status == "COMMITTED":
            flow_id = result.get("flow_id", "unknown")
            intent = result.get("intent", "task")
            return f"✅ Great! I've planned your {intent}. Flow ID: {flow_id[:8]}..."

        elif status == "REJECTED":
            reason = result.get("reason", "Unknown reason")
            return f"❌ Sorry, I couldn't complete that plan. Reason: {reason}"

        elif status == "ERROR":
            message = result.get("message", "Unknown error")
            return f"⚠️ Something went wrong: {message}"

        else:
            return f"Plan status: {status}"

    def reset_chat(self):
        """Clear chat history (useful for testing)"""
        self.chat_history.clear()
        logger.info("Chat history cleared")

    def get_stats(self) -> Dict[str, Any]:
        """Get concierge statistics"""
        return {
            "chat_messages": len(self.chat_history),
            "plans_completed": len(self.plan_history),
            "active_planning": self.active_planning,
            "pending_clarification": self.pending_clarification is not None,
        }


# Utility for testing
def create_test_concierge(llm_provider, planning_pipeline=None) -> ConciergeAgent:
    """Create a concierge agent for testing"""
    return ConciergeAgent(
        llm_provider=llm_provider,
        planning_pipeline=planning_pipeline,
        max_history=20,
    )


if __name__ == "__main__":
    print("ConciergeAgent module loaded successfully")
    print("Use create_test_concierge() to instantiate for testing")
