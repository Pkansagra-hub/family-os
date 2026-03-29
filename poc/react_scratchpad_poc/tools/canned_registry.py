"""
Canned (deterministic) tool registry for the ReactLoopScratchpad PoC.

Provides predictable tool responses keyed by arguments for reproducible benchmarking.
Tools cover: research, travel, data, calculation, error injection, and sub-agent management.

All responses come from response_bank.py -- no real API calls.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from core.models import ToolResult
from tools.response_bank import (
    FLAKY_COUNTER,
    get_api_result,
    get_calculation,
    get_database_query,
    get_flaky_response,
    get_flights,
    get_hotels,
    get_large_dataset,
    get_research_result,
    get_weather,
)

# ---------------------------------------------------------------------------
# Tool definition type
# ---------------------------------------------------------------------------


class ToolDefinition:
    """A registered tool with schema and handler."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable[..., Any],
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler

    def to_declaration(self) -> Dict[str, Any]:
        """Convert to Google AI function declaration format."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


# ---------------------------------------------------------------------------
# Canned Tool Registry
# ---------------------------------------------------------------------------


class CannedToolRegistry:
    """
    Deterministic tool registry with canned responses.

    Every tool returns predictable data from the response bank.
    Supports sequence responses for stress testing.
    """

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._call_counts: Dict[str, int] = {}
        self._register_all_tools()

    def _register_all_tools(self) -> None:
        """Register all built-in canned tools."""

        # --- Research tools ---
        self._register(
            "web_search",
            "Search the web for information on a topic. Returns a summary with key facts.",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query or topic to research"},
                },
                "required": ["query"],
            },
            self._handle_web_search,
        )

        self._register(
            "deep_research",
            "Perform deep research on a specific topic. Returns detailed analysis with structured facts.",
            {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to research in depth"},
                },
                "required": ["topic"],
            },
            self._handle_deep_research,
        )

        self._register(
            "wiki_lookup",
            "Look up a term in an encyclopedia/wiki. Returns factual summary.",
            {
                "type": "object",
                "properties": {
                    "term": {"type": "string", "description": "Term to look up"},
                },
                "required": ["term"],
            },
            self._handle_wiki_lookup,
        )

        # --- Travel tools ---
        self._register(
            "weather_api",
            "Get current weather for a city.",
            {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"},
                },
                "required": ["city"],
            },
            self._handle_weather,
        )

        self._register(
            "flight_search",
            "Search for flights between two cities.",
            {
                "type": "object",
                "properties": {
                    "from_city": {"type": "string", "description": "Departure city"},
                    "to_city": {"type": "string", "description": "Destination city"},
                    "date": {"type": "string", "description": "Travel date (YYYY-MM-DD)"},
                },
                "required": ["from_city", "to_city"],
            },
            self._handle_flight_search,
        )

        self._register(
            "hotel_search",
            "Search for hotels in a city.",
            {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City to search hotels in"},
                    "checkin": {"type": "string", "description": "Check-in date"},
                    "nights": {"type": "integer", "description": "Number of nights"},
                },
                "required": ["city"],
            },
            self._handle_hotel_search,
        )

        # --- Data tools ---
        self._register(
            "database_query",
            "Query a database for user data like preferences, booking history, or budget.",
            {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Database query (e.g., 'user_preferences', 'booking_history')",
                    },
                },
                "required": ["query"],
            },
            self._handle_database_query,
        )

        self._register(
            "api_fetch",
            "Fetch data from an API endpoint (exchange rates, travel advisories, visa requirements).",
            {
                "type": "object",
                "properties": {
                    "endpoint": {"type": "string", "description": "API endpoint to fetch"},
                },
                "required": ["endpoint"],
            },
            self._handle_api_fetch,
        )

        self._register(
            "calculate",
            "Compute a mathematical expression.",
            {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "Math expression to evaluate"},
                },
                "required": ["expression"],
            },
            self._handle_calculate,
        )

        # --- Large-payload tools (2,000-5,000 token outputs) ---
        self._register(
            "search_database_large",
            "Query a large database. Returns extensive records (200+ rows). Use for customer history, transaction logs, or detailed analytics.",
            {
                "type": "object",
                "properties": {
                    "dataset": {
                        "type": "string",
                        "description": "Dataset to query (customer_history, analytics_report, vector_search)",
                    },
                    "query": {
                        "type": "string",
                        "description": "Optional filter or query string",
                    },
                },
                "required": ["dataset"],
            },
            self._handle_search_database_large,
        )

        self._register(
            "analytics_report",
            "Generate a comprehensive analytics report with segments, trends, cohorts, and recommendations. Returns a large structured dataset.",
            {
                "type": "object",
                "properties": {
                    "report_type": {
                        "type": "string",
                        "description": "Report type (purchase_analytics, customer_segments, revenue_trends)",
                    },
                    "period": {
                        "type": "string",
                        "description": "Time period (e.g. '2024-Q4', 'last_12_months')",
                    },
                },
                "required": ["report_type"],
            },
            self._handle_analytics_report,
        )

        self._register(
            "vector_search",
            "Perform a vector similarity search across a large document corpus. Returns top-100 results with similarity scores and metadata.",
            {
                "type": "object",
                "properties": {
                    "query_text": {
                        "type": "string",
                        "description": "Natural language query to find similar documents",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default 100)",
                    },
                },
                "required": ["query_text"],
            },
            self._handle_vector_search,
        )

        # --- Error injection ---
        self._register(
            "flaky_api",
            "Call an unreliable API that may fail. Use for testing error recovery.",
            {
                "type": "object",
                "properties": {
                    "endpoint": {
                        "type": "string",
                        "description": "API endpoint (premium_flight_search, hotel_availability, weather_premium)",
                    },
                },
                "required": ["endpoint"],
            },
            self._handle_flaky_api,
        )

        # --- Sub-agent management ---
        self._register(
            "spawn_agent",
            "Spawn a sub-agent to perform a task independently with its own budget.",
            {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Task description for the sub-agent"},
                    "tool_budget": {
                        "type": "integer",
                        "description": "Number of tool calls to allocate to sub-agent",
                    },
                },
                "required": ["task"],
            },
            self._handle_spawn_agent,
        )

        self._register(
            "check_agent_status",
            "Check the status of a previously spawned sub-agent.",
            {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "ID of the agent to check"},
                },
                "required": ["agent_id"],
            },
            self._handle_check_agent_status,
        )

        self._register(
            "get_agent_result",
            "Get the final result from a completed sub-agent.",
            {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "ID of the completed agent"},
                },
                "required": ["agent_id"],
            },
            self._handle_get_agent_result,
        )

        # --- Final answer ---
        self._register(
            "final_answer",
            "Provide the final answer to the user's question. Call this when you have enough information to answer.",
            {
                "type": "object",
                "properties": {
                    "answer": {
                        "type": "string",
                        "description": "The complete answer to the user's question",
                    },
                    "confidence": {"type": "number", "description": "Confidence score 0-1"},
                },
                "required": ["answer"],
            },
            self._handle_final_answer,
        )

    def _register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable[..., Any],
    ) -> None:
        self._tools[name] = ToolDefinition(name, description, parameters, handler)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_tool_declarations(self) -> List[Dict[str, Any]]:
        """Get all tool declarations for LLM function calling."""
        return [t.to_declaration() for t in self._tools.values()]

    def get_tools_for_scenario(self, tool_names: List[str]) -> List[Dict[str, Any]]:
        """Get specific tool declarations by name."""
        return [self._tools[n].to_declaration() for n in tool_names if n in self._tools]

    async def execute(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        """Execute a tool by name with given arguments."""
        if name not in self._tools:
            return ToolResult(
                tool_name=name,
                ok=False,
                error_code="TOOL_NOT_FOUND",
                error_message=f"Unknown tool: {name}",
            )

        # Track call count
        self._call_counts[name] = self._call_counts.get(name, 0) + 1

        try:
            result = self._tools[name].handler(**arguments)
            if isinstance(result, dict) and result.get("ok") is False:
                return ToolResult(
                    tool_name=name,
                    ok=False,
                    output=result.get("output"),
                    error_code=result.get("error_code", "TOOL_ERROR"),
                    error_message=result.get("message", "Tool execution failed"),
                )
            return ToolResult(
                tool_name=name,
                ok=True,
                output=result,
            )
        except Exception as e:
            return ToolResult(
                tool_name=name,
                ok=False,
                error_code="EXECUTION_ERROR",
                error_message=str(e),
            )

    def get_tool_names(self) -> List[str]:
        """Get all registered tool names."""
        return list(self._tools.keys())

    def reset(self) -> None:
        """Reset call counters and flaky API state."""
        self._call_counts.clear()
        FLAKY_COUNTER.reset()

    # ------------------------------------------------------------------
    # Tool handlers
    # ------------------------------------------------------------------

    def _handle_web_search(self, query: str) -> Dict[str, Any]:
        result = get_research_result(query)
        if result:
            return {"query": query, "results": [result]}
        return {"query": query, "results": [], "message": "No results found"}

    def _handle_deep_research(self, topic: str) -> Dict[str, Any]:
        result = get_research_result(topic)
        if result:
            return {
                "topic": topic,
                "title": result["title"],
                "detailed_summary": result["summary"],
                "key_facts": result["facts"],
                "source_count": 5,
                "confidence": 0.92,
            }
        return {"topic": topic, "message": "Insufficient data for deep research"}

    def _handle_wiki_lookup(self, term: str) -> Dict[str, Any]:
        result = get_research_result(term)
        if result:
            return {
                "term": term,
                "article": result["title"],
                "extract": result["summary"][:200],
                "facts": result.get("facts", {}),
            }
        return {"term": term, "message": "Article not found"}

    def _handle_weather(self, city: str) -> Dict[str, Any]:
        return get_weather(city)

    def _handle_flight_search(
        self,
        from_city: str,
        to_city: str,
        date: str = "2025-06-01",
    ) -> Dict[str, Any]:
        flights = get_flights(from_city, to_city)
        return {
            "from": from_city,
            "to": to_city,
            "date": date,
            "flights": flights,
            "count": len(flights),
        }

    def _handle_hotel_search(
        self,
        city: str,
        checkin: str = "2025-06-01",
        nights: int = 3,
    ) -> Dict[str, Any]:
        hotels = get_hotels(city)
        return {
            "city": city,
            "checkin": checkin,
            "nights": nights,
            "hotels": hotels,
            "count": len(hotels),
        }

    def _handle_database_query(self, query: str) -> Dict[str, Any]:
        result = get_database_query(query)
        return {"query": query, "data": result}

    def _handle_api_fetch(self, endpoint: str) -> Dict[str, Any]:
        result = get_api_result(endpoint)
        return {"endpoint": endpoint, "data": result}

    def _handle_calculate(self, expression: str) -> Dict[str, Any]:
        result = get_calculation(expression)
        return {"expression": expression, "result": result}

    def _handle_search_database_large(self, dataset: str, query: str = "") -> Dict[str, Any]:
        data = get_large_dataset(dataset)
        if query:
            data["applied_filter"] = query
        return data

    def _handle_analytics_report(
        self, report_type: str, period: str = "last_12_months"
    ) -> Dict[str, Any]:
        # All analytics-type queries return the same large report
        data = get_large_dataset("analytics_report")
        data["requested_type"] = report_type
        data["requested_period"] = period
        return data

    def _handle_vector_search(self, query_text: str, top_k: int = 100) -> Dict[str, Any]:
        data = get_large_dataset("vector_search")
        data["original_query"] = query_text
        # Trim results if top_k is smaller
        if top_k < 100 and "results" in data:
            data["results"] = data["results"][:top_k]
            data["total_results"] = top_k
        return data

    def _handle_flaky_api(self, endpoint: str) -> Dict[str, Any]:
        return get_flaky_response(endpoint)

    def _handle_spawn_agent(
        self,
        task: str,
        tool_budget: int = 5,
    ) -> Dict[str, Any]:
        # Returns a placeholder -- actual spawning handled by the runner
        return {
            "action": "spawn_agent",
            "task": task,
            "tool_budget": tool_budget,
            "status": "pending",
            "message": "Agent spawn request recorded. Runner will handle execution.",
        }

    def _handle_check_agent_status(self, agent_id: str) -> Dict[str, Any]:
        return {
            "agent_id": agent_id,
            "status": "pending",
            "message": "Agent status tracked by runner.",
        }

    def _handle_get_agent_result(self, agent_id: str) -> Dict[str, Any]:
        return {
            "agent_id": agent_id,
            "status": "pending",
            "message": "Agent result tracked by runner.",
        }

    def _handle_final_answer(
        self,
        answer: str,
        confidence: float = 1.0,
    ) -> Dict[str, Any]:
        return {
            "action": "final_answer",
            "answer": answer,
            "confidence": confidence,
        }
