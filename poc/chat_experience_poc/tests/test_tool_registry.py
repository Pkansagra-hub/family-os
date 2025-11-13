"""
Tests for Tool Registry and Mock MCP Server

Integration tests for:
- Tool Registry: registration, validation, listing
- Mock MCP Server: endpoints, validation, error handling
"""

from l5_infrastructure.registries.tool_registry import (
    ToolDefinition,
    ToolRegistry,
    get_tool_registry,
)


class TestToolRegistry:
    """Test Tool Registry functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.registry = ToolRegistry()

    def test_registry_initialized_with_default_tools(self):
        """Test registry has default tools."""
        assert len(self.registry.tools) >= 6
        assert "web_search" in self.registry.tools
        assert "calendar_add" in self.registry.tools
        assert "email_send" in self.registry.tools

    def test_get_tool(self):
        """Test retrieving tool by ID."""
        tool = self.registry.get_tool("web_search")
        assert tool is not None
        assert tool.tool_id == "web_search"
        assert tool.name == "Web Search"

    def test_get_nonexistent_tool(self):
        """Test getting non-existent tool."""
        tool = self.registry.get_tool("nonexistent")
        assert tool is None

    def test_get_tools_by_category(self):
        """Test filtering tools by category."""
        communication_tools = self.registry.get_tools_by_category("communication")
        assert len(communication_tools) > 0
        assert all(t.category == "communication" for t in communication_tools)

    def test_validate_valid_request(self):
        """Test validating valid request."""
        is_valid, error = self.registry.validate_tool_request(
            "web_search",
            {"query": "test query"},
        )
        assert is_valid
        assert error is None

    def test_validate_missing_required_field(self):
        """Test validation fails when required field missing."""
        is_valid, error = self.registry.validate_tool_request(
            "web_search",
            {"num_results": 5},  # Missing 'query'
        )
        assert not is_valid
        assert error is not None and "query" in error

    def test_validate_unexpected_field(self):
        """Test validation fails with unexpected fields."""
        is_valid, error = self.registry.validate_tool_request(
            "web_search",
            {"query": "test", "unknown_field": "value"},
        )
        assert not is_valid
        assert error is not None and ("unknown_field" in error or "Unexpected" in error)

    def test_validate_wrong_type(self):
        """Test validation fails with wrong field type."""
        is_valid, error = self.registry.validate_tool_request(
            "web_search",
            {"query": 123},  # Should be string
        )
        assert not is_valid

    def test_calendar_add_validation(self):
        """Test calendar_add tool validation."""
        # Valid request
        is_valid, error = self.registry.validate_tool_request(
            "calendar_add",
            {
                "event_title": "Meeting",
                "start_time": "2025-11-05T14:00:00Z",
                "end_time": "2025-11-05T15:00:00Z",
            },
        )
        assert is_valid

        # Missing required field
        is_valid, error = self.registry.validate_tool_request(
            "calendar_add",
            {
                "event_title": "Meeting",
                "start_time": "2025-11-05T14:00:00Z",
                # Missing end_time
            },
        )
        assert not is_valid

    def test_add_custom_tool(self):
        """Test adding custom tool."""
        custom_tool = ToolDefinition(
            tool_id="custom_tool",
            name="Custom Tool",
            description="A custom test tool",
            category="test",
            parameters={
                "type": "object",
                "properties": {
                    "param1": {"type": "string"},
                },
            },
            required_fields=["param1"],
            mock_endpoint="http://localhost:8001/tools/custom_tool",
        )

        self.registry.add_tool(custom_tool)
        assert self.registry.get_tool("custom_tool") is not None

    def test_list_all_tools(self):
        """Test listing all tools."""
        tools = self.registry.list_all_tools()
        assert isinstance(tools, list)
        assert len(tools) >= 6

    def test_registry_to_dict(self):
        """Test exporting registry to dict."""
        data = self.registry.to_dict()
        assert isinstance(data, dict)
        assert "web_search" in data
        assert data["web_search"]["name"] == "Web Search"


class TestToolDefinition:
    """Test ToolDefinition validation."""

    def test_tool_definition_creation(self):
        """Test creating tool definition."""
        tool = ToolDefinition(
            tool_id="test_tool",
            name="Test Tool",
            description="Test",
            category="test",
            parameters={
                "type": "object",
                "properties": {"param": {"type": "string"}},
            },
            required_fields=["param"],
            mock_endpoint="http://localhost:8001/tools/test",
        )

        assert tool.tool_id == "test_tool"
        assert tool.name == "Test Tool"

    def test_tool_to_dict(self):
        """Test tool to dict conversion."""
        tool = ToolDefinition(
            tool_id="test",
            name="Test",
            description="Test",
            category="test",
            parameters={},
            required_fields=[],
            mock_endpoint="http://localhost:8001/tools/test",
        )

        data = tool.to_dict()
        assert data["tool_id"] == "test"
        assert isinstance(data, dict)

    def test_validate_request_basic(self):
        """Test basic request validation."""
        tool = ToolDefinition(
            tool_id="test",
            name="Test",
            description="Test",
            category="test",
            parameters={
                "type": "object",
                "properties": {"required_param": {"type": "string"}},
            },
            required_fields=["required_param"],
            mock_endpoint="http://localhost:8001/tools/test",
        )

        # Valid
        is_valid, error = tool.validate_request({"required_param": "value"})
        assert is_valid

        # Missing
        is_valid, error = tool.validate_request({})
        assert not is_valid


def test_singleton_registry():
    """Test that get_tool_registry returns singleton."""
    reg1 = get_tool_registry()
    reg2 = get_tool_registry()
    assert reg1 is reg2
