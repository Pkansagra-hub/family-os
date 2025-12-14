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
    ):
        """
        Initialize HealthcareAgent.

        Args:
            agent_id: Unique agent identifier
            session_id: Session ID for this conversation
            groq_client: Groq client for LLM calls
            trace_id: Optional trace ID
        """
        super().__init__(
            agent_id=agent_id,
            agent_type="healthcare",
            session_id=session_id,
            groq_client=groq_client,
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

        # Build context for LLM (including time context for time-aware responses)
        context_data = {
            "user_query": user_query,
            "health_context": health_context,
            "health_goals": health_goals,
            "pt_routines": pt_routines,
            "k0_health_data": k0_health_data,
            "user_id": user_id,
        }

        # Call LLM with healthcare prompt from Prompt Registry
        llm_response = await self.call_llm(
            user_input=user_query,
            context_data=context_data,
            temperature=0.7,  # Healthcare agent temperature from Prompt Registry
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

        # No direct tool in POC; attempt to infer from health context or fallback
        health_ctx = await self._get_health_context(user_id)
        # Synthesize a minimal routine summary if possible
        recent = health_ctx.get("recent_metrics", [])
        adherence = 0.85 if recent else 0.0
        return {
            "current_routine": "pt_recovery_plan",
            "exercises": [],
            "adherence_rate": adherence,
            "next_session": {},
        }

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
