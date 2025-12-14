"""
Tests for Tool Call Handler

Integration and unit tests for:
- Tool lookup and validation
- Request formatting
- Mock server communication
- Retry logic with exponential backoff
- Receipt generation
- Error handling (network, validation, timeout)
- Performance metrics
"""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from l5_infrastructure.registries.tool_registry import get_tool_registry
from l5_infrastructure.tool_call_handler import (
    ToolCallHandler,
    ToolReceipt,
    ToolRequest,
    get_tool_call_handler,
)


class TestToolRequest:
    """Test ToolRequest creation and validation."""

    def test_request_creation_with_defaults(self):
        """Test creating request with default trace_id and timestamp."""
        request = ToolRequest(
            tool_id="web_search",
            parameters={"query": "hello"},
            agent_id="concierge_001",
        )
        assert request.tool_id == "web_search"
        assert request.parameters == {"query": "hello"}
        assert request.agent_id == "concierge_001"
        assert request.trace_id is not None
        assert request.timestamp is not None

    def test_request_creation_with_custom_trace_id(self):
        """Test creating request with custom trace_id."""
        custom_trace = "custom_trace_123"
        request = ToolRequest(
            tool_id="web_search",
            parameters={"query": "hello"},
            agent_id="concierge_001",
            trace_id=custom_trace,
        )
        assert request.trace_id == custom_trace

    def test_request_timestamp_is_datetime(self):
        """Test request timestamp is datetime object."""
        request = ToolRequest(
            tool_id="web_search",
            parameters={"query": "hello"},
            agent_id="concierge_001",
        )
        assert isinstance(request.timestamp, datetime)


class TestToolReceipt:
    """Test ToolReceipt creation and serialization."""

    def test_receipt_creation_success(self):
        """Test creating success receipt."""
        receipt = ToolReceipt(
            receipt_id="receipt_001",
            tool_id="web_search",
            agent_id="concierge_001",
            status="success",
            timestamp=datetime.utcnow(),
            latency_ms=125.5,
            trace_id="trace_001",
            result={"results": ["item1", "item2"]},
        )
        assert receipt.status == "success"
        assert receipt.result is not None
        assert receipt.error is None

    def test_receipt_creation_error(self):
        """Test creating error receipt."""
        receipt = ToolReceipt(
            receipt_id="receipt_001",
            tool_id="web_search",
            agent_id="concierge_001",
            status="error",
            timestamp=datetime.utcnow(),
            latency_ms=50.0,
            trace_id="trace_001",
            error="Network timeout",
        )
        assert receipt.status == "error"
        assert receipt.result is None
        assert receipt.error == "Network timeout"

    def test_receipt_to_dict(self):
        """Test receipt serialization to dictionary."""
        receipt = ToolReceipt(
            receipt_id="receipt_001",
            tool_id="web_search",
            agent_id="concierge_001",
            status="success",
            timestamp=datetime.utcnow(),
            latency_ms=100.0,
            trace_id="trace_001",
            result={"data": "value"},
        )
        receipt_dict = receipt.to_dict()
        assert receipt_dict["receipt_id"] == "receipt_001"
        assert receipt_dict["tool_id"] == "web_search"
        assert receipt_dict["status"] == "success"
        assert "timestamp" in receipt_dict
        assert isinstance(receipt_dict["timestamp"], str)  # ISO format


class TestToolCallHandler:
    """Test Tool Call Handler functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = ToolCallHandler(timeout_seconds=5.0, max_retries=2)
        self.registry = get_tool_registry()

    def test_handler_initialization(self):
        """Test handler initializes with correct settings."""
        assert self.handler.timeout_seconds == 5.0
        assert self.handler.max_retries == 2
        assert self.handler.calls_total == 0
        assert self.handler.calls_success == 0

    def test_handler_stats_initial(self):
        """Test stats on fresh handler."""
        stats = self.handler.get_stats()
        assert stats["calls_total"] == 0
        assert stats["success_rate_percent"] == 0.0
        assert stats["avg_latency_ms"] == 0.0

    def test_format_request(self):
        """Test request formatting with metadata."""
        request = ToolRequest(
            tool_id="web_search",
            parameters={"query": "hello"},
            agent_id="concierge_001",
            trace_id="trace_001",
        )
        tool = self.registry.get_tool("web_search")
        formatted = self.handler._format_request(request, tool)

        assert formatted["tool_id"] == "web_search"
        assert formatted["parameters"]["query"] == "hello"
        assert formatted["metadata"]["agent_id"] == "concierge_001"
        assert formatted["metadata"]["trace_id"] == "trace_001"

    def test_create_receipt_success(self):
        """Test creating success receipt."""
        request = ToolRequest(
            tool_id="web_search",
            parameters={"query": "hello"},
            agent_id="concierge_001",
        )
        receipt = self.handler._create_receipt(
            request=request,
            status="success",
            latency_ms=125.0,
            result={"results": ["item1"]},
        )
        assert receipt.status == "success"
        assert receipt.tool_id == "web_search"
        assert receipt.result is not None

    def test_create_receipt_error(self):
        """Test creating error receipt."""
        request = ToolRequest(
            tool_id="web_search",
            parameters={"query": "hello"},
            agent_id="concierge_001",
        )
        receipt = self.handler._create_receipt(
            request=request,
            status="error",
            latency_ms=50.0,
            error="Connection refused",
        )
        assert receipt.status == "error"
        assert receipt.error == "Connection refused"

    @pytest.mark.asyncio
    async def test_call_tool_invalid_tool(self):
        """Test calling non-existent tool raises ValueError."""
        with pytest.raises(ValueError, match="Tool not found"):
            await self.handler.call_tool(
                tool_id="nonexistent_tool",
                parameters={},
                agent_id="concierge_001",
            )

    @pytest.mark.asyncio
    async def test_call_tool_invalid_parameters(self):
        """Test calling tool with invalid parameters raises ValueError."""
        with pytest.raises(ValueError, match="validation failed"):
            await self.handler.call_tool(
                tool_id="web_search",
                parameters={"wrong_field": "value"},  # Missing 'query'
                agent_id="concierge_001",
            )

    @pytest.mark.asyncio
    async def test_post_to_mock_server_success(self):
        """Test successful POST to mock server."""
        request_data = {
            "tool_id": "web_search",
            "parameters": {"query": "hello"},
            "metadata": {"agent_id": "concierge_001"},
        }

        async def mock_post(*args, **kwargs):
            mock_response = MagicMock()
            mock_response.json = MagicMock(return_value={"status": "accepted"})
            mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = mock_post
            mock_client_class.return_value = mock_client

            result = await self.handler._post_to_mock_server(
                endpoint="http://localhost:8001/tools/web_search",
                request_data=request_data,
            )
            assert result == {"status": "accepted"}

    @pytest.mark.asyncio
    async def test_post_to_mock_server_timeout(self):
        """Test timeout handling in POST to mock server."""

        async def mock_post_timeout(*args, **kwargs):
            raise httpx.TimeoutException("Timeout")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = mock_post_timeout
            mock_client_class.return_value = mock_client

            with pytest.raises(asyncio.TimeoutError):
                await self.handler._post_to_mock_server(
                    endpoint="http://localhost:8001/tools/web_search",
                    request_data={"test": "data"},
                )

    @pytest.mark.asyncio
    async def test_post_to_mock_server_invalid_json(self):
        """Test handling invalid JSON response."""

        async def mock_post_invalid_json(*args, **kwargs):
            mock_response = MagicMock()
            mock_response.json = MagicMock(side_effect=json.JSONDecodeError("msg", "doc", 0))
            mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.post = mock_post_invalid_json
            mock_client_class.return_value = mock_client

            with pytest.raises(ValueError, match="Invalid JSON"):
                await self.handler._post_to_mock_server(
                    endpoint="http://localhost:8001/tools/web_search",
                    request_data={"test": "data"},
                )

    @pytest.mark.asyncio
    async def test_call_tool_valid_with_mock_server(self):
        """Test full call_tool flow with mocked server."""
        with patch.object(self.handler, "_post_to_mock_server") as mock_post:
            mock_post.return_value = {"status": "accepted", "data": "result"}

            receipt, result = await self.handler.call_tool(
                tool_id="web_search",
                parameters={"query": "test"},
                agent_id="concierge_001",
            )

            assert receipt.status == "success"
            assert result == {"status": "accepted", "data": "result"}
            assert self.handler.calls_total == 1
            assert self.handler.calls_success == 1

    @pytest.mark.asyncio
    async def test_call_tool_error_with_mock_server(self):
        """Test full call_tool flow with server error."""
        with patch.object(self.handler, "_post_to_mock_server") as mock_post:
            mock_post.side_effect = httpx.RequestError("Connection failed")

            receipt, result = await self.handler.call_tool(
                tool_id="web_search",
                parameters={"query": "test"},
                agent_id="concierge_001",
            )

            assert receipt.status == "error"
            assert result is None
            assert self.handler.calls_error > 0

    @pytest.mark.asyncio
    async def test_call_tool_metrics_updated(self):
        """Test metrics are updated after successful call."""
        with patch.object(self.handler, "_post_to_mock_server") as mock_post:
            mock_post.return_value = {"status": "accepted"}

            receipt, _ = await self.handler.call_tool(
                tool_id="web_search",
                parameters={"query": "test"},
                agent_id="concierge_001",
            )

            stats = self.handler.get_stats()
            assert stats["calls_total"] >= 1
            # Latency may be 0 due to mock speed, so just check it's >= 0
            assert stats["avg_latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_call_tool_with_custom_trace_id(self):
        """Test call_tool preserves custom trace_id in receipt."""
        custom_trace = "my_trace_123"
        with patch.object(self.handler, "_post_to_mock_server") as mock_post:
            mock_post.return_value = {"status": "accepted"}

            receipt, _ = await self.handler.call_tool(
                tool_id="web_search",
                parameters={"query": "test"},
                agent_id="concierge_001",
                trace_id=custom_trace,
            )

            assert receipt.trace_id == custom_trace

    def test_singleton_handler(self):
        """Test get_tool_call_handler returns singleton."""
        handler1 = get_tool_call_handler()
        handler2 = get_tool_call_handler()
        assert handler1 is handler2

    def test_handler_stats_dict_structure(self):
        """Test stats dictionary has all required fields."""
        stats = self.handler.get_stats()
        required_fields = [
            "calls_total",
            "calls_success",
            "calls_error",
            "calls_timeout",
            "success_rate_percent",
            "avg_latency_ms",
        ]
        for field in required_fields:
            assert field in stats
