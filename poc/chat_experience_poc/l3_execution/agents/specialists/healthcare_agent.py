"""
HealthcareAgent — Tier 2 Specialist for Health-Related Queries.

Handles:
  - Physical therapy schedules and progress
  - Medication tracking and reminders
  - Recovery progress monitoring
  - Pain tracking and analysis
  - Health goal adherence

Architecture:
  - Inherits from AgentBase
  - Uses "healthcare" prompt from Prompt Registry (temperature=0.7)
  - Queries User KG for health context (HealthMetrics, Goals, Routines)
  - Calls mock MCP tool: query_k0_health (episodic PT sessions)
  - Synthesizes personalized insights using Groq LLM
  - Returns conversational response to Concierge

Example Query: "How's my knee recovery going?"
Example Response: "Your recovery is on track! You've completed 6/8 PT sessions this month.
Knee strength has improved 40% since you started. Your next PT is scheduled for Nov 12 at 2pm
with Sarah. Keep up the great work!"

References:
  - docs/whiteboard/chat_experience.md - HealthcareAgent example
  - Epic 4.3.1 - Healthcare specialist implementation
"""

from typing import Any, Dict, Optional

import structlog
from l3_execution.agents.agent_base import AgentBase

logger = structlog.get_logger(__name__)


class HealthcareAgent(AgentBase):
    """
    HealthcareAgent - Tier 2 Specialist for health and wellness queries.

    USER-FACING: Generates conversational, personalized health insights.
    """

    def __init__(
        self,
        agent_id: str,
        session_id: str,
        groq_client,
        trace_id: Optional[str] = None,
        mailbox: Optional[Any] = None,
    ):
        """
        Initialize HealthcareAgent.

        Args:
            agent_id: Unique agent identifier
            session_id: Session ID for this conversation
            groq_client: Groq client for LLM calls
            trace_id: Optional trace ID
            mailbox: Optional mailbox from AgentFabric
        """
        super().__init__(
            agent_id=agent_id,
            agent_type="healthcare",
            session_id=session_id,
            groq_client=groq_client,
            mailbox=mailbox,
            trace_id=trace_id,
        )

        logger.info(
            "healthcare_agent_initialized",
            agent_id=agent_id,
            session_id=session_id,
            trace_id=trace_id,
        )

    async def process_message(self, message: Dict[str, Any]):
        """
        Process healthcare query from Concierge.

        Workflow:
          1. Extract user query from message
          2. Query User KG for health context (HealthMetrics, Goals, Routines)
          3. Call query_k0_health MCP tool (episodic PT sessions)
          4. Synthesize personalized insight using Groq LLM
          5. Return response to Concierge

        Args:
            message: Task message from Concierge
                {
                    "type": "specialist_task",
                    "payload": {
                        "user_query": "How's my recovery?",
                        "user_id": "user_123",
                        "task_id": "task_456"
                    }
                }

        Returns:
            Dict with response content
        """
        logger.info(
            "healthcare_query_received",
            message=message,
            trace_id=self.trace_id,
        )

        # Extract query details
        payload = message.get("payload", {})
        user_query = payload.get("user_query", "")
        user_id = payload.get("user_id", "unknown")
        task_id = payload.get("task_id", "unknown")

        # Step 1: Query User KG for health context
        logger.info(
            "querying_user_kg_health_context",
            user_id=user_id,
            trace_id=self.trace_id,
        )

        health_context = await self._get_health_context(user_id)
        health_goals = await self._get_health_goals(user_id)
        pt_routines = await self._get_pt_routines(user_id)

        print(f"[DEBUG HEALTHCARE] health_context: {health_context}", flush=True)
        print(f"[DEBUG HEALTHCARE] health_goals: {health_goals}", flush=True)
        print(f"[DEBUG HEALTHCARE] pt_routines: {pt_routines}", flush=True)

        # Step 2: Call query_k0_health MCP tool
        logger.info(
            "calling_mcp_tool_query_k0_health",
            user_id=user_id,
            trace_id=self.trace_id,
        )

        k0_health_data = await self._query_k0_health(user_id, user_query)

        # Step 3: Synthesize response using Groq LLM
        logger.info(
            "synthesizing_healthcare_response",
            user_query=user_query,
            trace_id=self.trace_id,
        )

        # Build context for LLM - format for template engine which expects user_context and history
        # Convert health data to strings for template rendering
        user_context_str = f"""
Patient: John (recovering from knee injury)
Recent Health Metrics: {health_context.get('recent_metrics', [])}
Current PT Routines: {pt_routines}
Health Goals: {health_goals}
"""

        history_str = f"""
K0 Health Data (past sessions):
{k0_health_data}
"""

        context_data = {
            "user_context": user_context_str,
            "history": history_str,
            "tools": [],
            "has_health_data": True,
            # Also keep raw data for reference
            "health_context": health_context,
            "health_goals": health_goals,
            "pt_routines": pt_routines,
            "k0_health_data": k0_health_data,
            "user_id": user_id,
        }

        # Call LLM with healthcare prompt from Prompt Registry
        print(f"[DEBUG HEALTHCARE] user_context_str:\n{user_context_str}", flush=True)
        print(
            f"[DEBUG HEALTHCARE] Calling LLM with context_data keys: {list(context_data.keys())}",
            flush=True,
        )

        # CRITICAL: Prepend context to user query so model cannot ignore it
        # Gemini Flash sometimes ignores system prompts, so we force context into user message
        enhanced_query = f"""Based on the following patient data, answer the question.

PATIENT DATA:
- Name: John
- Condition: {health_context.get('condition', 'Right knee ACL reconstruction recovery')}
- Surgery Date: {health_context.get('surgery_date', '2025-10-15')}
- Current Phase: {health_context.get('current_phase', 'Phase 2 - Active Rehabilitation')}
- Therapist: {health_context.get('therapist', 'Sarah Johnson, PT')}
- Next Appointment: {health_context.get('next_appointment', '2025-11-12 at 2:00 PM')}

RECENT METRICS:
- Knee Flexion: 110 degrees (improving)
- Pain Level: 3/10 (decreasing)
- Swelling: minimal (stable)
- Quad Strength: 70% of normal (improving)

PT PROGRESS:
- Sessions Completed: 6/8
- Exercise Adherence: 85%
- Last Session: 2025-11-04

HEALTH GOALS:
1. Complete 8 PT sessions - 6/8 done (on track)
2. Achieve 120 degree knee flexion - currently 110 degrees (on track)
3. Return to light jogging - not started yet
4. Medication adherence - 95% (on track)

USER QUESTION: {user_query}

Provide a personalized, encouraging response using the specific data above. Reference actual numbers and dates."""

        llm_response = await self.call_llm(
            user_input=enhanced_query,
            context_data=context_data,
            temperature=0.7,  # Healthcare agent temperature from Prompt Registry
            max_tokens=1024,  # Explicitly set to ensure full response
        )
        print(
            f"[DEBUG HEALTHCARE] LLM response length: {len(llm_response.get('content', ''))}",
            flush=True,
        )

        response_content = llm_response.get("content", "I'm sorry, I couldn't generate a response.")

        logger.info(
            "healthcare_response_generated",
            response_length=len(response_content),
            task_id=task_id,
            trace_id=self.trace_id,
        )

        # Step 4: Update SessionState (placeholder for POC)
        await self._update_session_state_with_insights(response_content)

        # Step 5: Return response to Concierge
        return {
            "status": "success",
            "specialist": "healthcare",
            "task_id": task_id,
            "response": response_content,
            "context_used": {
                "health_metrics": len(health_context.get("recent_metrics", [])),
                "goals": len(health_goals),
                "pt_sessions": k0_health_data.get("session_count", 0),
            },
        }

    # ==============================
    # User KG Query Methods (via ToolCallHandler where available)
    # ==============================

    async def _get_health_context(self, user_id: str) -> Dict[str, Any]:
        """
        Query User KG for health context (HealthMetrics, recent measurements).

        POC: Returns mock data
        Production: Query User KG database

        Args:
            user_id: User identifier

        Returns:
            Dict with health metrics
        """
        logger.debug(
            "user_kg_query_health_context",
            user_id=user_id,
            trace_id=self.trace_id,
        )

        # Use tool passthrough to UserKG
        tool_resp = await self.call_tool(
            "get_health_context",
            {"user_id": user_id, "query_type": "all", "days": 30},
        )
        # Check if tool call failed (POC fallback with mock data)
        if tool_resp.get("status") == "error" or not tool_resp.get("result"):
            logger.warning("Tool call failed, using POC mock health data", user_id=user_id)
            return self._get_mock_health_context(user_id)

        # Normalize shapes:
        # - UserKG adapter: {result: {data: [HealthMetric nodes...]}}
        # - Mock generator: {result: {context: {...}}}
        result = tool_resp.get("result", {}) if isinstance(tool_resp, dict) else {}
        data = result.get("data") if isinstance(result, dict) else None
        if isinstance(data, list):
            return {"user_id": user_id, "recent_metrics": data}
        context = result.get("context") if isinstance(result, dict) else None
        if isinstance(context, dict):
            # Keep mock generator shape as-is but wrap into recent_metrics when possible
            recent = context.get("symptoms", {}).get("recent") or []
            return {
                "user_id": user_id,
                "recent_metrics": recent,
                **{k: v for k, v in context.items() if k != "symptoms"},
            }
        return {"user_id": user_id, "recent_metrics": []}

    async def _get_health_goals(self, user_id: str) -> list:
        """
        Query User KG for active health goals.

        Args:
            user_id: User identifier

        Returns:
            List of health goals
        """
        logger.debug(
            "user_kg_query_health_goals",
            user_id=user_id,
            trace_id=self.trace_id,
        )

        # Approximate via user preferences (health category) since no direct tool exists for goals in POC
        tool_resp = await self.call_tool(
            "get_user_preferences",
            {"user_id": user_id, "preference_category": "health"},
        )

        # Check if tool call failed (POC fallback with mock data)
        if tool_resp.get("status") == "error" or not tool_resp.get("result"):
            logger.warning("Tool call failed, using POC mock health goals", user_id=user_id)
            return self._get_mock_health_goals()

        result = tool_resp.get("result", {}) if isinstance(tool_resp, dict) else {}
        if "preferences" in result and isinstance(result["preferences"], dict):
            health = result["preferences"].get("health", {})
            goals = []
            if isinstance(health, dict) and "exercise_goals" in health:
                eg = health.get("exercise_goals") or {}
                goals.append({"goal_id": "exercise_goals", "details": eg})
            return goals
        if "data" in result and isinstance(result["data"], list):
            # UserKG adapter path: list of preference nodes → coerce into generic goals list
            return [
                {"goal_id": n.get("node_id"), "properties": n.get("properties", {})}
                for n in result["data"]
                if isinstance(n, dict)
            ]
        return []

    async def _get_pt_routines(self, user_id: str) -> Dict[str, Any]:
        """
        Query User KG for PT exercise routines and adherence.

        Args:
            user_id: User identifier

        Returns:
            Dict with PT routine information
        """
        logger.debug(
            "user_kg_query_pt_routines",
            user_id=user_id,
            trace_id=self.trace_id,
        )

        # POC: Use mock data directly (tools not available)
        return self._get_mock_pt_routines()

    # ==============================
    # MCP Tool Call (Mock for POC)
    # ==============================

    async def _query_k0_health(self, user_id: str, query: str) -> Dict[str, Any]:
        """
        Call query_k0
        lth MCP tool to search episodic memories for PT sessions.

        POC: Returns mock K0 health data
        Production: Actual MCP tool call to K0 episodic memory

        Args:
            user_id: User identifier
            query: User's health query

        Returns:
            Dict with K0 health data (PT sessions, therapist notes)
        """
        logger.info(
            "mcp_tool_query_k0_health",
            user_id=user_id,
            query=query,
            trace_id=self.trace_id,
        )

        # POC: Mock K0 health data
        return {
            "session_count": 6,
            "recent_sessions": [
                {
                    "date": "2025-11-04",
                    "exercises_completed": ["leg_raises", "knee_bends", "balance"],
                    "therapist_notes": "Good progress. Knee strength improving. Continue current routine.",
                    "pain_level": 3,
                },
                {
                    "date": "2025-11-01",
                    "exercises_completed": ["leg_raises", "knee_bends"],
                    "therapist_notes": "Patient showing improvement. Increase resistance next session.",
                    "pain_level": 4,
                },
                {
                    "date": "2025-10-28",
                    "exercises_completed": ["leg_raises", "assisted_walking"],
                    "therapist_notes": "First session post-surgery. Baseline measurements recorded.",
                    "pain_level": 5,
                },
            ],
            "improvement_metrics": {
                "knee_strength_change": "+40%",
                "pain_reduction": "-40%",
                "rom_improvement": "+25 degrees",
            },
        }

    # ==============================
    # SessionState Update (Placeholder for POC)
    # ==============================

    async def _update_session_state_with_insights(self, response: str):
        """
        Update SessionState with health insights.

        POC: Just log the update
        Production: Update SessionState.Beliefs with health entities

        Args:
            response: Healthcare response containing insights
        """
        logger.debug(
            "session_state_update_health_insights",
            response_preview=response[:100],
            trace_id=self.trace_id,
        )

        # POC: Placeholder
        # In production:
        # await self.update_session_state(
        #     section="Beliefs",
        #     updates={
        #         "health_facts": extracted_facts,
        #         "entities": ["PT", "knee", "Sarah Johnson"]
        #     }
        # )

    # ==============================
    # Time Context (NEW: Time-Aware Responses)
    # ==============================

    async def _get_time_context_from_session(self) -> Dict[str, Any]:
        """
        Extract time context from session state for time-aware health advice.

        Includes:
          - Current time (UTC and user timezone)
          - Day of week, hour of day
          - Business hours, peak hours
          - Session duration
          - Belief freshness information

        Returns:
            Dict with time context fields

        Example usage:
          - "It's after hours, book your PT session for tomorrow"
          - "You're 3 hours late for your afternoon medication reminder"
          - "Recovery belief is 2 weeks old, should refresh metrics"
        """
        logger.debug(
            "extracting_time_context_for_health_advice",
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
            "is_business_hours": 9 <= hour <= 17,  # 9am-5pm UTC
            "is_morning": 5 <= hour < 12,
            "is_afternoon": 12 <= hour < 17,
            "is_evening": 17 <= hour < 21,
            "is_night": hour >= 21 or hour < 5,
        }

    # ==============================
    # POC Mock Data (when tools unavailable)
    # ==============================

    def _get_mock_health_context(self, user_id: str) -> Dict[str, Any]:
        """Return mock health context for POC when tool calls fail."""
        return {
            "user_id": user_id,
            "patient_name": "John",
            "condition": "Right knee ACL reconstruction recovery",
            "surgery_date": "2025-10-15",
            "current_phase": "Phase 2 - Active Rehabilitation",
            "recent_metrics": [
                {
                    "date": "2025-11-04",
                    "metric": "knee_flexion",
                    "value": "110 degrees",
                    "trend": "improving",
                },
                {
                    "date": "2025-11-04",
                    "metric": "pain_level",
                    "value": "3/10",
                    "trend": "decreasing",
                },
                {"date": "2025-11-04", "metric": "swelling", "value": "minimal", "trend": "stable"},
                {
                    "date": "2025-11-02",
                    "metric": "quad_strength",
                    "value": "70% of normal",
                    "trend": "improving",
                },
            ],
            "therapist": "Sarah Johnson, PT",
            "next_appointment": "2025-11-12 at 2:00 PM",
        }

    def _get_mock_health_goals(self) -> list:
        """Return mock health goals for POC when tool calls fail."""
        return [
            {
                "goal_id": "g1",
                "description": "Complete 8 PT sessions",
                "progress": "6/8 sessions",
                "status": "on_track",
            },
            {
                "goal_id": "g2",
                "description": "Achieve 120 degree knee flexion",
                "progress": "110/120 degrees",
                "status": "on_track",
            },
            {
                "goal_id": "g3",
                "description": "Return to light jogging",
                "progress": "Not started",
                "status": "pending",
            },
            {
                "goal_id": "g4",
                "description": "Take medication as prescribed",
                "progress": "95% adherence",
                "status": "on_track",
            },
        ]

    def _get_mock_pt_routines(self) -> Dict[str, Any]:
        """Return mock PT routines for POC when tool calls fail."""
        return {
            "current_routine": "Phase 2 Home Exercise Program",
            "exercises": [
                {"name": "Quad sets", "reps": "10x3", "frequency": "daily"},
                {"name": "Straight leg raises", "reps": "10x3", "frequency": "daily"},
                {"name": "Heel slides", "reps": "15x2", "frequency": "daily"},
                {"name": "Balance exercises", "reps": "5 min", "frequency": "daily"},
            ],
            "adherence_rate": 0.85,
            "last_session": "2025-11-04",
            "next_session": {"date": "2025-11-12", "time": "2:00 PM", "therapist": "Sarah Johnson"},
        }
