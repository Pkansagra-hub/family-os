"""
ResearcherAgent — Tier 2 Specialist for Information Lookup and Factual Questions.

Handles:
  - General information lookup
  - Factual questions
  - Definitions and explanations
  - Location-based queries (restaurants, stores, etc.)
  - Current events and news (mock for POC)

Architecture:
  - Inherits from AgentBase
  - Uses "researcher" prompt from Prompt Registry (temperature=0.5)
  - Minimal User KG queries (research is generally context-independent)
  - Calls mock MCP tool: query_web_search (mock search results)
  - Synthesizes conversational summary using Groq LLM
  - Returns natural language response to Concierge

Example Query: "What are the best Italian restaurants nearby?"
Example Response: "I found some great Italian restaurants near you! Bella Italia is highly
rated for authentic pasta dishes. Luigi's Pizzeria is perfect for casual dining.
Trattoria Roma offers a fine dining experience with excellent wine selection.
Would you like more details about any of these?"

References:
  - docs/whiteboard/chat_experience.md - Specialist agent patterns
  - Epic 4.3.3 - Researcher specialist implementation
"""

from typing import Any, Dict, Optional

import structlog
from l3_execution.agents.agent_base import AgentBase

logger = structlog.get_logger(__name__)


class ResearcherAgent(AgentBase):
    """
    ResearcherAgent - Tier 2 Specialist for information lookup and research queries.

    USER-FACING: Generates conversational summaries of research findings.
    """

    def __init__(
        self,
        agent_id: str,
        session_id: str,
        groq_client,
        trace_id: Optional[str] = None,
    ):
        """
        Initialize ResearcherAgent.

        Args:
            agent_id: Unique agent identifier
            session_id: Session ID for this conversation
            groq_client: Groq client for LLM calls
            trace_id: Optional trace ID
        """
        super().__init__(
            agent_id=agent_id,
            agent_type="researcher",
            session_id=session_id,
            groq_client=groq_client,
            trace_id=trace_id,
        )

        logger.info(
            "researcher_agent_initialized",
            agent_id=agent_id,
            session_id=session_id,
            trace_id=trace_id,
        )

    async def process_message(self, message: Dict[str, Any]):
        """
        Process research query from Concierge.

        Workflow:
          1. Extract user query from message
          2. (Optional) Query User KG for user location/preferences if needed
          3. Call query_web_search MCP tool (mock search results)
          4. Synthesize conversational summary using Groq LLM
          5. Return response to Concierge

        Args:
            message: Task message from Concierge
                {
                    "type": "specialist_task",
                    "payload": {
                        "user_query": "What are Italian restaurants nearby?",
                        "user_id": "user_123",
                        "task_id": "task_456"
                    }
                }

        Returns:
            Dict with response content
        """
        logger.info(
            "research_query_received",
            message=message,
            trace_id=self.trace_id,
        )

        # Extract query details
        payload = message.get("payload", {})
        user_query = payload.get("user_query", "")
        user_id = payload.get("user_id", "unknown")
        task_id = payload.get("task_id", "unknown")

        # Step 1: (Optional) Get user context if query is location-based
        user_location = await self._get_user_location(user_id)

        # Step 2: Call query_web_search MCP tool
        logger.info(
            "calling_mcp_tool_query_web_search",
            user_query=user_query,
            trace_id=self.trace_id,
        )

        search_results = await self._query_web_search(user_query, user_location)

        # Step 3: Synthesize response using Groq LLM
        logger.info(
            "synthesizing_research_response",
            user_query=user_query,
            result_count=len(search_results.get("results", [])),
            trace_id=self.trace_id,
        )

        # Get time context for freshness filtering (NEW: Time-aware)
        time_context = await self._get_time_context_from_session()

        # Build context for LLM (including time for freshness window)
        context_data = {
            "user_query": user_query,
            "search_results": search_results,
            "user_location": user_location,
            "user_id": user_id,
            "time_context": time_context,  # NEW: Include time for freshness window
        }

        # Call LLM with researcher prompt from Prompt Registry
        llm_response = await self.call_llm(
            user_input=user_query,
            context_data=context_data,
            temperature=0.5,  # Researcher agent temperature (balanced)
        )

        response_content = llm_response.get("content", "I'm sorry, I couldn't generate a response.")

        logger.info(
            "research_response_generated",
            response_length=len(response_content),
            task_id=task_id,
            trace_id=self.trace_id,
        )

        # Step 4: Update SessionState (placeholder for POC)
        await self._update_session_state_with_facts(response_content)

        # Step 5: Return response to Concierge
        return {
            "status": "success",
            "specialist": "researcher",
            "task_id": task_id,
            "response": response_content,
            "context_used": {
                "search_results": len(search_results.get("results", [])),
                "query_type": search_results.get("query_type", "general"),
            },
        }

    # ==============================
    # User KG Query Methods (Mock for POC)
    # ==============================

    async def _get_user_location(self, user_id: str) -> Dict[str, Any]:
        """
        Query User KG for user location (if query is location-based).

        POC: Returns mock location
        Production: Query User KG for actual location

        Args:
            user_id: User identifier

        Returns:
            Dict with location info
        """
        logger.debug(
            "user_kg_query_location",
            user_id=user_id,
            trace_id=self.trace_id,
        )

        # POC: Mock location
        return {
            "city": "San Francisco",
            "state": "CA",
            "zip": "94102",
        }

    # ==============================
    # MCP Tool Call (via ToolCallHandler)
    # ==============================

    async def _query_web_search(self, query: str, location: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call query_web_search MCP tool for information lookup.

        POC: Returns mock search results based on query type
        Production: Actual web search via MCP tool

        Args:
            query: User's research query
            location: User location for location-based queries

        Returns:
            Dict with search results
        """
        logger.info(
            "mcp_tool_query_web_search",
            query=query,
            location=location.get("city"),
            trace_id=self.trace_id,
        )

        # Use tool to fetch web search results
        tool_resp = await self.call_tool(
            "web_search",
            {"query": query, "num_results": 5},
        )

        # Mock MCP returns result at top-level or under 'result'
        result = tool_resp.get("result") if isinstance(tool_resp, dict) else None
        data = result if isinstance(result, dict) else tool_resp

        # Normalize to expected structure: {query_type, results}
        if isinstance(data, dict):
            # Prefer standardized keys if present
            if "results" in data:
                return {
                    "query_type": data.get("query_type", "general"),
                    "results": data.get("results", []),
                }
            # If the mock server returned {status, query, results, ...}
            if "query" in data and "results" in data:
                return {"query_type": "general", "results": data.get("results", [])}

        # Fallback empty
        return {"query_type": "general", "results": []}

    # ==============================
    # SessionState Update (Placeholder for POC)
    # ==============================

    async def _update_session_state_with_facts(self, response: str):
        """
        Update SessionState with research findings.

        POC: Just log the update
        Production: Update SessionState.Beliefs with factual entities

        Args:
            response: Research response containing facts
        """
        logger.debug(
            "session_state_update_research_facts",
            response_preview=response[:100],
            trace_id=self.trace_id,
        )

        # POC: Placeholder
        # In production:
        # await self.update_session_state(
        #     section="Beliefs",
        #     updates={
        #         "research_facts": extracted_facts,
        #         "entities": extracted_entities
        #     }
        # )

    # ==============================
    # Time Context (NEW: Time-Aware Research & Freshness)
    # ==============================

    async def _get_time_context_from_session(self) -> Dict[str, Any]:
        """
        Extract time context from session state for time-aware research.

        Uses time context for:
          - "This restaurant is open now" (time-based availability)
          - "Information from 3 days ago may be outdated"
          - "Peak hours at restaurants are typically 6-8pm"

        Returns:
            Dict with time context fields

        Example usage:
          - Filter search results by current business hours
          - Annotate "This info is X days old, may need refresh"
          - Suggest "Call before visiting during peak hours"
        """
        logger.debug(
            "extracting_time_context_for_research",
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
            "is_business_hours": 9 <= hour <= 17,
            "is_open_for_lunch": 11 <= hour <= 14,
            "is_open_for_dinner": 17 <= hour <= 21,
            "is_peak_hours": 18 <= hour <= 20,  # Typically 6-8pm for restaurants
        }
