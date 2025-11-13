"""
Tool Registry

Centralized storage and query interface for MCP tool definitions.
Tools are external integrations (web_search, calendar_add, email_send, etc.)
- NOT K0 queries (those use K0 Bridge Query Port P01)
- NOT K0 commands (those use K0 Bridge Command Port P02)

Tool definitions include:
- Parameter schema (JSON Schema format)
- Required fields validation
- Mock MCP endpoint for validation
- Tool categories and capabilities

References:
- docs/whiteboard/chat_experience.md - Tool call flow
- MCP Protocol: https://modelcontextprotocol.io/
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class ToolDefinition:
    """Single tool definition with validation."""

    def __init__(
        self,
        tool_id: str,
        name: str,
        description: str,
        category: str,
        parameters: Dict[str, Any],
        required_fields: List[str],
        mock_endpoint: str,
    ):
        self.tool_id = tool_id
        self.name = name
        self.description = description
        self.category = category
        self.parameters = parameters  # JSON Schema
        self.required_fields = required_fields
        self.mock_endpoint = mock_endpoint

    def to_dict(self) -> dict:
        """Convert to dict for serialization."""
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "parameters": self.parameters,
            "required_fields": self.required_fields,
            "mock_endpoint": self.mock_endpoint,
        }

    def validate_request(self, request: dict) -> tuple[bool, Optional[str]]:
        """
        Validate request against tool's parameter schema.

        Returns:
            (is_valid, error_message)
        """
        # Check required fields
        for field in self.required_fields:
            if field not in request:
                return False, f"Missing required field: {field}"

        # Check for unexpected fields
        allowed_fields = set(self.parameters.get("properties", {}).keys())
        request_fields = set(request.keys())
        unexpected = request_fields - allowed_fields
        if unexpected:
            return False, f"Unexpected fields: {', '.join(unexpected)}"

        # Validate field types (basic validation)
        for field, value in request.items():
            if field in self.parameters.get("properties", {}):
                field_schema = self.parameters["properties"][field]
                expected_type = field_schema.get("type")

                # Type checking
                if expected_type == "string" and not isinstance(value, str):
                    return False, f"Field '{field}' must be string, got {type(value).__name__}"
                elif expected_type == "number" and not isinstance(value, (int, float)):
                    return False, f"Field '{field}' must be number, got {type(value).__name__}"
                elif expected_type == "array" and not isinstance(value, list):
                    return False, f"Field '{field}' must be array, got {type(value).__name__}"

        return True, None


class ToolRegistry:
    """Central registry for all MCP tools (external integrations)."""

    def __init__(self):
        self.tools: Dict[str, ToolDefinition] = {}
        self._initialize_default_tools()
        self._initialize_agent_type_tools_mapping()

    def _initialize_default_tools(self):
        """Initialize registry with default external tools."""

        # web_search tool
        self.add_tool(
            ToolDefinition(
                tool_id="web_search",
                name="Web Search",
                description="Search the web for information",
                category="search",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query",
                        },
                        "num_results": {
                            "type": "number",
                            "description": "Number of results to return",
                            "default": 10,
                        },
                    },
                },
                required_fields=["query"],
                mock_endpoint="http://localhost:8001/tools/web_search",
            )
        )

        # calendar_add tool
        self.add_tool(
            ToolDefinition(
                tool_id="calendar_add",
                name="Add Calendar Event",
                description="Add an event to the calendar",
                category="calendar",
                parameters={
                    "type": "object",
                    "properties": {
                        "event_title": {
                            "type": "string",
                            "description": "Title of the event",
                        },
                        "start_time": {
                            "type": "string",
                            "description": "Start time (ISO 8601 format)",
                        },
                        "end_time": {
                            "type": "string",
                            "description": "End time (ISO 8601 format)",
                        },
                        "description": {
                            "type": "string",
                            "description": "Event description",
                        },
                    },
                },
                required_fields=["event_title", "start_time", "end_time"],
                mock_endpoint="http://localhost:8001/tools/calendar_add",
            )
        )

        # email_send tool
        self.add_tool(
            ToolDefinition(
                tool_id="email_send",
                name="Send Email",
                description="Send an email message",
                category="communication",
                parameters={
                    "type": "object",
                    "properties": {
                        "to": {
                            "type": "string",
                            "description": "Email recipient",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Email subject",
                        },
                        "body": {
                            "type": "string",
                            "description": "Email body",
                        },
                        "cc": {
                            "type": "array",
                            "description": "CC recipients",
                        },
                    },
                },
                required_fields=["to", "subject", "body"],
                mock_endpoint="http://localhost:8001/tools/email_send",
            )
        )

        # reminder_set tool
        self.add_tool(
            ToolDefinition(
                tool_id="reminder_set",
                name="Set Reminder",
                description="Set a time-based reminder",
                category="temporal",
                parameters={
                    "type": "object",
                    "properties": {
                        "reminder_text": {
                            "type": "string",
                            "description": "Reminder message",
                        },
                        "trigger_time": {
                            "type": "string",
                            "description": "When to trigger (ISO 8601 or natural language)",
                        },
                        "recurrence": {
                            "type": "string",
                            "description": "Recurrence pattern (daily, weekly, monthly, etc.)",
                        },
                    },
                },
                required_fields=["reminder_text", "trigger_time"],
                mock_endpoint="http://localhost:8001/tools/reminder_set",
            )
        )

        # sms_send tool
        self.add_tool(
            ToolDefinition(
                tool_id="sms_send",
                name="Send SMS",
                description="Send a text message",
                category="communication",
                parameters={
                    "type": "object",
                    "properties": {
                        "phone_number": {
                            "type": "string",
                            "description": "Recipient phone number",
                        },
                        "message": {
                            "type": "string",
                            "description": "Message text",
                        },
                    },
                },
                required_fields=["phone_number", "message"],
                mock_endpoint="http://localhost:8001/tools/sms_send",
            )
        )

        # weather_get tool
        self.add_tool(
            ToolDefinition(
                tool_id="weather_get",
                name="Get Weather",
                description="Get current weather for a location",
                category="information",
                parameters={
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "Location name or coordinates",
                        },
                        "include_forecast": {
                            "type": "string",
                            "description": "Include forecast (daily, weekly, none)",
                        },
                    },
                },
                required_fields=["location"],
                mock_endpoint="http://localhost:8001/tools/weather_get",
            )
        )

        # --- K0 UserKG passthrough tools (POC) ---
        # These are validated here and served by Mock MCP with a real UserKG adapter
        self.add_tool(
            ToolDefinition(
                tool_id="get_health_context",
                name="Get Health Context",
                description="Query User KG for recent health metrics",
                category="health",
                parameters={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "User identifier"},
                        "query_type": {
                            "type": "string",
                            "description": "Health query subtype (ignored in POC)",
                        },
                        "days": {"type": "number", "description": "Lookback days (optional)"},
                    },
                },
                required_fields=["user_id", "query_type"],
                mock_endpoint="http://localhost:8001/tools/get_health_context",
            )
        )

        self.add_tool(
            ToolDefinition(
                tool_id="get_financial_context",
                name="Get Financial Context",
                description="Query User KG for financial-related context (POC mapping)",
                category="finance",
                parameters={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "User identifier"},
                        "time_range": {
                            "type": "string",
                            "description": "Time range (ignored in POC)",
                        },
                    },
                },
                required_fields=["user_id"],
                mock_endpoint="http://localhost:8001/tools/get_financial_context",
            )
        )

        # Dedicated finance query tool for episodic transactions (POC)
        self.add_tool(
            ToolDefinition(
                tool_id="query_k0_finance",
                name="Query K0 Finance",
                description="Query episodic finance data (transactions, category totals) for current month",
                category="finance",
                parameters={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "User identifier"},
                        "query": {
                            "type": "string",
                            "description": "Natural language finance query",
                        },
                        "month": {
                            "type": "string",
                            "description": "YYYY-MM for time scoping (optional)",
                        },
                    },
                },
                required_fields=["user_id", "query"],
                mock_endpoint="http://localhost:8001/tools/query_k0_finance",
            )
        )

        self.add_tool(
            ToolDefinition(
                tool_id="get_user_preferences",
                name="Get User Preferences",
                description="Retrieve user preferences from User KG",
                category="personalization",
                parameters={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "User identifier"},
                        "preference_category": {
                            "type": "string",
                            "description": "Preference category or 'all'",
                        },
                    },
                },
                required_fields=["user_id"],
                mock_endpoint="http://localhost:8001/tools/get_user_preferences",
            )
        )

        logger.info(
            "tool_registry_initialized",
            num_tools=len(self.tools),
            tools=list(self.tools.keys()),
        )

    def _initialize_agent_type_tools_mapping(self):
        """
        Initialize mapping of agent types to available tools.

        This mapping defines which tools are available to each agent type.
        Extensible: new agent types can be added to this mapping.
        """
        self.agent_type_tools: Dict[str, List[str]] = {
            "ticketbookingagent": ["web_search", "calendar_add", "email_send"],
            "flightsearchagent": ["web_search", "calendar_add", "email_send"],
            "healthcareagent": ["web_search"],
            "financialanalyst": ["web_search"],
            "researcharticleagent": ["web_search"],
            "generalistspecialist": ["web_search", "email_send"],
        }

        logger.debug(
            "agent_type_tools_mapping_initialized",
            num_agent_types=len(self.agent_type_tools),
        )

    def add_tool(self, tool: ToolDefinition):
        """Register a new tool."""
        self.tools[tool.tool_id] = tool
        logger.debug("tool_added", tool_id=tool.tool_id, tool_name=tool.name)

    def get_tool(self, tool_id: str) -> Optional[ToolDefinition]:
        """Get tool by ID."""
        return self.tools.get(tool_id)

    def get_tools_by_category(self, category: str) -> List[ToolDefinition]:
        """Get all tools in a category."""
        return [t for t in self.tools.values() if t.category == category]

    def get_tools_for_agent_type(self, agent_type: str) -> List[ToolDefinition]:
        """
        Get all tools available for a specific agent type.

        Workflow:
          1. Lookup agent_type in mapping (case-insensitive)
          2. Get tool names for this agent
          3. Resolve tool names to ToolDefinition objects
          4. Fallback to generic tools if no mapping found

        Args:
            agent_type: e.g., "TicketBookingAgent", "FlightSearchAgent"

        Returns:
            List of ToolDefinition objects available for this agent
        """
        # Step 1: Lookup agent_type in mapping (case-insensitive)
        agent_type_lower = agent_type.lower()

        # Step 2: Get tool names for this agent
        tool_names = self.agent_type_tools.get(agent_type_lower, [])

        if not tool_names:
            logger.warning(
                "agent_type_tools_not_configured",
                agent_type=agent_type,
            )
            # Fallback: return generic tools
            tool_names = ["web_search"]  # Basic fallback

        # Step 3: Resolve tool names to ToolDefinition objects
        tools = []
        for tool_name in tool_names:
            tool = self.tools.get(tool_name)
            if tool:
                tools.append(tool)
            else:
                logger.warning(
                    "tool_not_found_in_registry",
                    tool_name=tool_name,
                    agent_type=agent_type,
                )

        logger.debug(
            "agent_tools_resolved",
            agent_type=agent_type,
            num_tools=len(tools),
            tool_names=[t.name for t in tools],
        )

        return tools

    def list_all_tools(self) -> List[ToolDefinition]:
        """Get all registered tools."""
        return list(self.tools.values())

    def validate_tool_request(self, tool_id: str, request: dict) -> tuple[bool, Optional[str]]:
        """
        Validate request against tool's schema.

        Returns:
            (is_valid, error_message)
        """
        tool = self.get_tool(tool_id)
        if not tool:
            return False, f"Tool not found: {tool_id}"

        return tool.validate_request(request)

    def to_dict(self) -> dict:
        """Export registry as dict."""
        return {tool_id: tool.to_dict() for tool_id, tool in self.tools.items()}

    def to_json_file(self, filepath: str):
        """Export registry to JSON file."""
        data = {
            "version": "1.0",
            "generated": str(Path(__file__).stem),
            "tools": self.to_dict(),
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        logger.info("tool_registry_exported", filepath=filepath)


# Singleton instance
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get or create singleton tool registry instance."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
    return _registry
