"""
FinanceAgent — Tier 2 Specialist for Finance-Related Queries.

Handles:
  - Budget tracking and analysis
  - Expense categorization and trends
  - Savings goals progress
  - Upcoming bill reminders
  - Financial health insights

Architecture:
  - Inherits from AgentBase
  - Uses "finance" prompt from Prompt Registry (temperature=0.3)
  - Queries User KG for budget limits and savings goals
  - Calls mock MCP tool: query_k0_finance (episodic transactions)
  - Synthesizes financial insights using Groq LLM
  - Returns conversational response to Concierge

Example Query: "What's my spending this month?"
Example Response: "You've spent $1,200 this month, which is 80% of your $1,500 budget.
Here's the breakdown: Groceries $400, Dining $300, Transportation $200, Entertainment $150,
Other $150. You're on track for your $500 savings goal this month. Great job staying within budget!"

References:
  - docs/whiteboard/chat_experience.md - Specialist agent patterns
  - Epic 4.3.2 - Finance specialist implementation
"""

from typing import Any, Dict, Optional

import structlog
from l3_execution.agents.agent_base import AgentBase

logger = structlog.get_logger(__name__)


class FinanceAgent(AgentBase):
    """
    FinanceAgent - Tier 2 Specialist for financial management queries.

    USER-FACING: Generates conversational, actionable financial insights.
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
        Initialize FinanceAgent.

        Args:
            agent_id: Unique agent identifier
            session_id: Session ID for this conversation
            groq_client: Groq client for LLM calls
            trace_id: Optional trace ID
            mailbox: Optional mailbox from AgentFabric
        """
        super().__init__(
            agent_id=agent_id,
            agent_type="finance",
            session_id=session_id,
            groq_client=groq_client,
            mailbox=mailbox,
            trace_id=trace_id,
        )

        logger.info(
            "finance_agent_initialized",
            agent_id=agent_id,
            session_id=session_id,
            trace_id=trace_id,
        )

    async def process_message(self, message: Dict[str, Any]):
        """
        Process finance query from Concierge.

        Workflow:
          1. Extract user query from message
          2. Query User KG for budget limits and savings goals
          3. Call query_k0_finance MCP tool (episodic transactions)
          4. Synthesize financial insight using Groq LLM
          5. Return response to Concierge

        Args:
            message: Task message from Concierge
                {
                    "type": "specialist_task",
                    "payload": {
                        "user_query": "What's my spending this month?",
                        "user_id": "user_123",
                        "task_id": "task_456"
                    }
                }

        Returns:
            Dict with response content
        """
        logger.info(
            "finance_query_received",
            message=message,
            trace_id=self.trace_id,
        )

        # Extract query details
        payload = message.get("payload", {})
        user_query = payload.get("user_query", "")
        user_id = payload.get("user_id", "unknown")
        task_id = payload.get("task_id", "unknown")

        # Step 1: Query User KG (via tools) for budget, goals and preferences
        logger.info(
            "querying_user_kg_finance_context",
            user_id=user_id,
            trace_id=self.trace_id,
        )

        budget_limits = await self._get_budget_limits(user_id)
        savings_goals = await self._get_savings_goals(user_id)
        financial_preferences = await self._get_financial_preferences(user_id)

        # Step 2: Call query_k0_finance MCP tool
        logger.info(
            "calling_mcp_tool_query_k0_finance",
            user_id=user_id,
            trace_id=self.trace_id,
        )

        k0_finance_data = await self._query_k0_finance(user_id, user_query)

        # Step 3: Synthesize response using Groq LLM
        logger.info(
            "synthesizing_finance_response",
            user_query=user_query,
            trace_id=self.trace_id,
        )

        # Get time context for month/day-of-month calculations (NEW: Time-aware)
        time_context = await self._get_time_context_from_session()

        # Build context for LLM (including time for month progression)
        context_data = {
            "user_query": user_query,
            "budget_limits": budget_limits,
            "savings_goals": savings_goals,
            "financial_preferences": financial_preferences,
            "k0_finance_data": k0_finance_data,
            "user_id": user_id,
            "time_context": time_context,  # NEW: Include time context for "day X of Y" calculations
        }

        # Call LLM with finance prompt from Prompt Registry
        llm_response = await self.call_llm(
            user_input=user_query,
            context_data=context_data,
            temperature=0.3,  # Finance agent temperature (more factual, less creative)
        )

        response_content = llm_response.get("content", "I'm sorry, I couldn't generate a response.")

        logger.info(
            "finance_response_generated",
            response_length=len(response_content),
            task_id=task_id,
            trace_id=self.trace_id,
        )

        # Step 4: Update SessionState (placeholder for POC)
        await self._update_session_state_with_insights(response_content)

        # Step 5: Return response to Concierge
        return {
            "status": "success",
            "specialist": "finance",
            "task_id": task_id,
            "response": response_content,
            "context_used": {
                "budgets": len(budget_limits.get("categories", [])),
                "goals": len(savings_goals),
                "transactions": k0_finance_data.get("transaction_count", 0),
            },
        }

    # ==============================
    # User KG Query Methods (via ToolCallHandler)
    # ==============================

    async def _get_budget_limits(self, user_id: str) -> Dict[str, Any]:
        """
        Query User KG for budget limits by category.

        POC: Returns mock data
        Production: Query User KG database

        Args:
            user_id: User identifier

        Returns:
            Dict with budget limits
        """
        logger.debug(
            "user_kg_query_budget_limits",
            user_id=user_id,
            trace_id=self.trace_id,
        )

        # Call tool to fetch financial context (UserKG passthrough)
        tool_resp = await self.call_tool(
            "get_financial_context",
            {"user_id": user_id, "time_range": "current_month"},
        )

        # Normalize across possible mock paths
        # Case A (Mock generator): {'result': {... 'context': {'budget': {'categories': {...}}}}}
        # Case B (UserKG adapter): {'result': {'data': {'preferences_finance': [...], 'goals': [...]}}}
        result = tool_resp.get("result", {}) if isinstance(tool_resp, dict) else {}
        context = result.get("context", {})
        data = result.get("data", {})

        categories_list = []
        monthly_budget = None

        # Try mock generator structure first
        try:
            categories = context.get("budget", {}).get("categories", {})
            if isinstance(categories, dict):
                for name, vals in categories.items():
                    categories_list.append(
                        {
                            "name": name,
                            "limit": vals.get("budget"),
                            "spent": vals.get("spent"),
                        }
                    )
            total_budget = context.get("budget", {}).get("total_monthly_budget")
            if isinstance(total_budget, (int, float)):
                monthly_budget = total_budget
        except Exception:
            pass

        # Fallback: derive categories from preferences_finance (UserKG path)
        if not categories_list and isinstance(data, dict):
            prefs = data.get("preferences_finance")
            if isinstance(prefs, list):
                # Pull any category hints if present in properties
                for node in prefs:
                    props = node.get("properties", {}) if isinstance(node, dict) else {}
                    cat = props.get("name") or props.get("category")
                    if cat:
                        categories_list.append({"name": cat, "limit": None})

        return {
            "user_id": user_id,
            "monthly_budget": monthly_budget or 1500,
            "categories": categories_list,
        }

    async def _get_savings_goals(self, user_id: str) -> list:
        """
        Query User KG for active savings goals.

        Args:
            user_id: User identifier

        Returns:
            List of savings goals
        """
        logger.debug(
            "user_kg_query_savings_goals",
            user_id=user_id,
            trace_id=self.trace_id,
        )

        # Reuse financial context call and extract goals when available
        tool_resp = await self.call_tool(
            "get_financial_context",
            {"user_id": user_id, "time_range": "current_month"},
        )

        result = tool_resp.get("result", {}) if isinstance(tool_resp, dict) else {}
        # UserKG adapter path
        data = result.get("data") if isinstance(result, dict) else None
        if isinstance(data, dict) and "goals" in data:
            return data.get("goals") or []

        # Mock generator path (no explicit goals field)
        return []

    async def _get_financial_preferences(self, user_id: str) -> Dict[str, Any]:
        """
        Query User KG for financial preferences and settings.

        Args:
            user_id: User identifier

        Returns:
            Dict with financial preferences
        """
        logger.debug(
            "user_kg_query_financial_preferences",
            user_id=user_id,
            trace_id=self.trace_id,
        )

        # Call tool to fetch user preferences (finance category)
        tool_resp = await self.call_tool(
            "get_user_preferences",
            {"user_id": user_id, "preference_category": "finance"},
        )

        result = tool_resp.get("result", {}) if isinstance(tool_resp, dict) else {}
        # Two possible shapes:
        # - Mock generator: {result: {status, preferences: {finance: {...}}}}
        # - UserKG adapter: {result: {data: [Preference nodes...]}}
        prefs = {}
        if "preferences" in result:
            # Mock generator path
            finance = (
                result["preferences"].get("finance", {})
                if isinstance(result.get("preferences"), dict)
                else {}
            )
            prefs = finance
        elif "data" in result:
            # UserKG adapter path → normalize into simple list of names/categories
            data = result.get("data")
            if isinstance(data, list):
                categories = []
                for node in data:
                    props = node.get("properties", {}) if isinstance(node, dict) else {}
                    nm = props.get("name") or props.get("category")
                    if nm:
                        categories.append(nm)
                prefs = {"spending_categories": categories}

        return prefs

    # ==============================
    # MCP Tool Call (via ToolCallHandler)
    # ==============================

    async def _query_k0_finance(self, user_id: str, query: str) -> Dict[str, Any]:
        """
        Call query_k0_finance MCP tool to search episodic memories for transactions.

        POC: Returns mock K0 finance data
        Production: Actual MCP tool call to K0 episodic memory

        Args:
            user_id: User identifier
            query: User's finance query

        Returns:
            Dict with K0 finance data (transactions, spending trends)
        """
        logger.info(
            "mcp_tool_query_k0_finance",
            user_id=user_id,
            query=query,
            trace_id=self.trace_id,
        )

        # Use dedicated finance tool for episodic transactions (POC)
        tool_resp = await self.call_tool(
            "query_k0_finance",
            {"user_id": user_id, "query": query},
        )

        result = tool_resp.get("result", {}) if isinstance(tool_resp, dict) else {}
        if isinstance(result, dict) and result.get("status") == "success":
            # Pass through standardized fields
            return {
                "transaction_count": result.get("transaction_count", 0),
                "current_month_total": result.get("current_month_total"),
                "category_spending": result.get("category_spending", []),
                "recent_transactions": result.get("recent_transactions", []),
                "budget_utilization": result.get("budget_utilization"),
            }

        # Fallback: safe defaults
        return {
            "transaction_count": 0,
            "current_month_total": None,
            "category_spending": [],
            "recent_transactions": [],
            "budget_utilization": None,
        }

    # ==============================
    # SessionState Update (Placeholder for POC)
    # ==============================

    async def _update_session_state_with_insights(self, response: str):
        """
        Update SessionState with financial insights.

        POC: Just log the update
        Production: Update SessionState.Beliefs with financial entities

        Args:
            response: Finance response containing insights
        """
        logger.debug(
            "session_state_update_finance_insights",
            response_preview=response[:100],
            trace_id=self.trace_id,
        )

        # POC: Placeholder
        # In production:
        # await self.update_session_state(
        #     section="Beliefs",
        #     updates={
        #         "finance_facts": extracted_facts,
        #         "entities": ["budget", "groceries", "dining"]
        #     }
        # )

    # ==============================
    # Time Context (NEW: Time-Aware Financial Advice)
    # ==============================

    async def _get_time_context_from_session(self) -> Dict[str, Any]:
        """
        Extract time context from session state for time-aware financial advice.

        Uses time context for:
          - "You've spent $1,200 (80%) with 7 days left in month"
          - "Budget resets in 26 days on Dec 1"
          - "Peak spending hour is typically 6pm, check back then"

        Returns:
            Dict with time context fields including day-of-month calculation

        Example usage:
          - Compare spending patterns by time of day/day of week
          - Calculate "days remaining in budget period"
          - Time-based spending predictions
        """
        logger.debug(
            "extracting_time_context_for_finance_advice",
            trace_id=self.trace_id,
        )

        # POC: Return mock time context with month progression
        # In production: session_state.get_time_context()
        from datetime import datetime

        now = datetime.now()
        days_in_month = 30 if now.month == 11 else 31
        day_of_month = now.day
        days_remaining = days_in_month - day_of_month

        return {
            "current_date": now.isoformat(),
            "day_of_month": day_of_month,
            "days_remaining": days_remaining,
            "month": now.strftime("%B"),
            "is_month_end": days_remaining <= 3,
            "percent_month_elapsed": (day_of_month / days_in_month) * 100,
            "day_of_week": now.strftime("%A"),
            "is_weekend": now.weekday() >= 5,
        }
