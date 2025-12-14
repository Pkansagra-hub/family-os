"""
Tool Call Handler - Unified API for agents to call external MCP tools

Responsibilities:
- Lookup tool definitions from Tool Registry
- Validate parameters against tool schema
- Format requests with metadata (agent_id, timestamp, trace_id)
- POST to mock MCP servers
- Handle responses and errors
- Generate receipts with call metadata
- Publish tool.called events to DeltaBus for observability
- Retry logic with exponential backoff (3 attempts)
- Observable: log all tool calls with latency metrics

Implements ADR-0008 Saga Pattern for error handling and receipt generation.
"""

import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import httpx
import structlog
from l4_runtime.deltabus.deltabus import DeltaBusEvent, get_deltabus
from l5_infrastructure.registries.tool_registry import get_tool_registry
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger(__name__)


@dataclass
class ToolRequest:
    """Request to call a tool with parameters."""

    tool_id: str
    parameters: Dict[str, Any]
    agent_id: str
    trace_id: Optional[str] = None
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        """Set defaults for optional fields."""
        if self.trace_id is None:
            self.trace_id = f"trace_{int(time.time() * 1000)}"
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class ToolReceipt:
    """Receipt for a tool call with metadata and result."""

    receipt_id: str
    tool_id: str
    agent_id: str
    status: str  # "success" or "error"
    timestamp: datetime
    latency_ms: float
    trace_id: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize receipt to dictionary."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


class ToolCallHandler:
    """
    Handles tool calls from agents to external MCP services.

    Workflow:
    1. Lookup tool definition in registry
    2. Validate parameters against schema
    3. Format request with metadata
    4. POST to mock MCP server with retry logic
    5. Handle response (success/error)
    6. Generate receipt with latency metrics
    7. Log all calls with latency

    Performance budget: <500ms P95 for external tool calls (including network)
    """

    def __init__(
        self,
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        base_delay_ms: int = 100,
    ):
        """
        Initialize Tool Call Handler.

        Args:
            timeout_seconds: HTTP request timeout (default 10s)
            max_retries: Number of retry attempts (default 3)
            base_delay_ms: Base delay for exponential backoff (default 100ms)
        """
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.base_delay_ms = base_delay_ms
        self.tool_registry = get_tool_registry()
        self.deltabus = get_deltabus()

        # Metrics
        self.calls_total = 0
        self.calls_success = 0
        self.calls_error = 0
        self.calls_timeout = 0
        self.total_latency_ms = 0.0

    def _publish_tool_called_event(
        self,
        receipt: ToolReceipt,
        tool_name: str,
        session_id: str = "default",
    ) -> None:
        """
        Publish tool.called event to DeltaBus for observability

        Guarantees every tool invocation emits a DeltaBus event with:
        - Receipt ID (unique identifier)
        - Tool metadata (tool_id, tool_name)
        - Trace ID (for distributed tracing)
        - Agent ID (caller)
        - Status (success/error)
        - Latency metrics
        - Error message (if applicable)

        This enables:
        - Writer agents to capture receipts for K0 persistence
        - Orchestrator to track tool execution progress
        - Observability dashboards to monitor tool usage

        Args:
            receipt: ToolReceipt with call metadata
            tool_name: Tool name (e.g., "web_search", "book_restaurant")
            session_id: Session identifier for event routing
        """
        event = DeltaBusEvent(
            event_type="tool.called",
            session_id=session_id,
            payload={
                "receipt_id": receipt.receipt_id,
                "tool_id": receipt.tool_id,
                "tool_name": tool_name,
                "agent_id": receipt.agent_id,
                "trace_id": receipt.trace_id,
                "status": receipt.status,
                "latency_ms": receipt.latency_ms,
                "timestamp": receipt.timestamp.isoformat(),
            },
            timestamp=receipt.timestamp,
            trace_id=receipt.trace_id,
        )

        # Add error details if tool call failed
        if receipt.error:
            event.payload["error"] = receipt.error

        # Add result summary if tool call succeeded
        if receipt.result:
            event.payload["has_result"] = True
            # Don't include full result in event (could be large), just flag

        self.deltabus.publish(event)

    async def call_tool(
        self,
        tool_id: str,
        parameters: Dict[str, Any],
        agent_id: str,
        trace_id: Optional[str] = None,
        session_id: str = "default",
    ) -> Tuple[ToolReceipt, Optional[Dict[str, Any]]]:
        """
        Call an external MCP tool with parameters.

        Args:
            tool_id: Unique tool identifier (e.g., "web_search")
            parameters: Tool parameters as dictionary
            agent_id: ID of agent making the call
            trace_id: Optional trace ID for request tracing
            session_id: Session identifier for DeltaBus event routing

        Returns:
            Tuple of (receipt, result_data)
            - receipt: ToolReceipt with call metadata and status
            - result_data: Tool response data (if successful), None on error

        Raises:
            ValueError: If tool not found or parameters invalid
            asyncio.TimeoutError: If call exceeds timeout
        """
        start_time = time.time()
        request = ToolRequest(
            tool_id=tool_id,
            parameters=parameters,
            agent_id=agent_id,
            trace_id=trace_id,
        )

        # Step 1: Lookup tool definition
        tool = self.tool_registry.get_tool(tool_id)
        if tool is None:
            error_msg = f"Tool not found in registry: {tool_id}"
            latency_ms = (time.time() - start_time) * 1000
            receipt = self._create_receipt(
                request=request,
                status="error",
                latency_ms=latency_ms,
                error=error_msg,
            )
            logger.warning("tool_call_failed", receipt=receipt.to_dict(), reason="not_found")
            self.calls_error += 1

            # Publish tool.called event for observability
            self._publish_tool_called_event(receipt, tool_id, session_id)

            raise ValueError(error_msg)

        # Step 2: Validate parameters against schema
        is_valid, validation_error = self.tool_registry.validate_tool_request(tool_id, parameters)
        if not is_valid:
            latency_ms = (time.time() - start_time) * 1000
            error_msg = f"Parameter validation failed: {validation_error}"
            receipt = self._create_receipt(
                request=request,
                status="error",
                latency_ms=latency_ms,
                error=error_msg,
            )
            logger.warning(
                "tool_call_failed",
                receipt=receipt.to_dict(),
                reason="validation_error",
                validation_error=validation_error,
            )
            self.calls_error += 1

            # Publish tool.called event for observability
            self._publish_tool_called_event(receipt, tool_id, session_id)

            raise ValueError(error_msg)

        # Step 3: Format request with metadata
        formatted_request = self._format_request(request, tool)

        # Step 4: POST to mock MCP server with retry logic
        result = None
        last_error = None
        attempt_count = 0

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self.max_retries),
                wait=wait_exponential(multiplier=1, min=self.base_delay_ms / 1000, max=10),
                retry=retry_if_exception_type((httpx.RequestError, asyncio.TimeoutError)),
                reraise=True,
            ):
                with attempt:
                    attempt_count = attempt.retry_state.attempt_number
                    logger.debug(
                        "tool_call_attempt",
                        tool_id=tool_id,
                        attempt=attempt_count,
                        max_retries=self.max_retries,
                    )
                    result = await self._post_to_mock_server(
                        endpoint=tool.mock_endpoint,
                        request_data=formatted_request,
                    )
        except asyncio.TimeoutError:
            last_error = "Request timeout"
            self.calls_timeout += 1
            logger.error(
                "tool_call_timeout",
                tool_id=tool_id,
                timeout_seconds=self.timeout_seconds,
                attempts=attempt_count,
            )
        except RetryError as e:
            last_error = str(e.last_attempt.exception())
            logger.error(
                "tool_call_retry_exhausted",
                tool_id=tool_id,
                max_retries=self.max_retries,
                error=last_error,
            )
        except Exception as e:
            last_error = str(e)
            logger.error("tool_call_unexpected_error", tool_id=tool_id, error=last_error)

        # Step 5: Generate receipt with latency metrics
        latency_ms = (time.time() - start_time) * 1000
        self.total_latency_ms += latency_ms
        self.calls_total += 1

        if last_error:
            receipt = self._create_receipt(
                request=request,
                status="error",
                latency_ms=latency_ms,
                error=last_error,
            )
            self.calls_error += 1
            logger.warning(
                "tool_call_failed",
                receipt=receipt.to_dict(),
                reason="network_error",
            )

            # Publish tool.called event for observability
            self._publish_tool_called_event(receipt, tool_id, session_id)

            return receipt, None

        # Success case
        receipt = self._create_receipt(
            request=request,
            status="success",
            latency_ms=latency_ms,
            result=result,
        )
        self.calls_success += 1

        # Step 7: Log success with latency
        logger.info(
            "tool_call_success",
            receipt=receipt.to_dict(),
            latency_ms=latency_ms,
        )

        # Publish tool.called event for observability
        self._publish_tool_called_event(receipt, tool_id, session_id)

        # TODO (Milestone 3): Mailbox-based response routing
        # Future enhancement: Instead of returning receipt directly,
        # publish response event to requesting agent's mailbox:
        #   response_event = DeltaBusEvent(
        #       event_type=f"tool.response.{receipt.receipt_id}",
        #       session_id=session_id,
        #       payload={"receipt": receipt.to_dict(), "result": result},
        #       trace_id=receipt.trace_id,
        #   )
        #   self.deltabus.publish(response_event)
        # This enables async tool execution and better decoupling.

        return receipt, result

    def _format_request(self, request: ToolRequest, tool: Any) -> Dict[str, Any]:
        """
        Format tool request with metadata for mock MCP server.

        Request format:
        {
            "tool_id": "web_search",
            "parameters": {...},
            "metadata": {
                "agent_id": "concierge_001",
                "timestamp": "2025-11-05T12:34:56Z",
                "trace_id": "trace_1731234896000"
            }
        }

        Args:
            request: ToolRequest object
            tool: ToolDefinition object

        Returns:
            Formatted request dictionary
        """
        return {
            "tool_id": request.tool_id,
            "parameters": request.parameters,
            "metadata": {
                "agent_id": request.agent_id,
                "timestamp": request.timestamp.isoformat(),
                "trace_id": request.trace_id,
            },
        }

    async def _post_to_mock_server(
        self,
        endpoint: str,
        request_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        POST request to mock MCP server endpoint.

        Args:
            endpoint: Full URL of mock MCP endpoint
            request_data: Request payload as dictionary

        Returns:
            Response data from mock server

        Raises:
            httpx.RequestError: On network errors
            asyncio.TimeoutError: On timeout
            ValueError: On invalid response format
        """
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            try:
                response = await client.post(
                    endpoint,
                    json=request_data,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()

                response_data = response.json()
                logger.debug(
                    "mock_server_response",
                    endpoint=endpoint,
                    status_code=response.status_code,
                    response=response_data,
                )
                return response_data

            except httpx.TimeoutException as e:
                logger.error("mock_server_timeout", endpoint=endpoint, error=str(e))
                raise asyncio.TimeoutError(f"Mock server timeout: {endpoint}") from e
            except httpx.RequestError as e:
                logger.error("mock_server_request_error", endpoint=endpoint, error=str(e))
                raise
            except json.JSONDecodeError as e:
                error_msg = f"Invalid JSON response from mock server: {e}"
                logger.error("mock_server_invalid_response", endpoint=endpoint, error=error_msg)
                raise ValueError(error_msg) from e

    def _create_receipt(
        self,
        request: ToolRequest,
        status: str,
        latency_ms: float,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> ToolReceipt:
        """
        Create a receipt for a tool call.

        Receipt includes:
        - Unique receipt ID (uuid)
        - Tool ID and agent ID
        - Call status (success/error)
        - Timestamp and latency metrics
        - Trace ID for distributed tracing
        - Result or error message

        Args:
            request: ToolRequest object
            status: "success" or "error"
            latency_ms: Call latency in milliseconds
            result: Optional result data (on success)
            error: Optional error message (on failure)

        Returns:
            ToolReceipt object
        """
        return ToolReceipt(
            receipt_id=str(uuid.uuid4()),
            tool_id=request.tool_id,
            agent_id=request.agent_id,
            status=status,
            timestamp=datetime.utcnow(),
            latency_ms=latency_ms,
            trace_id=request.trace_id,
            result=result,
            error=error,
        )

    def get_stats(self) -> Dict[str, Any]:
        """
        Get performance metrics for tool calls.

        Returns:
            Dictionary with:
            - calls_total: Total calls made
            - calls_success: Successful calls
            - calls_error: Failed calls
            - calls_timeout: Timed out calls
            - success_rate: Success percentage
            - avg_latency_ms: Average latency
        """
        success_rate = (
            (self.calls_success / self.calls_total * 100) if self.calls_total > 0 else 0.0
        )
        avg_latency = (self.total_latency_ms / self.calls_total) if self.calls_total > 0 else 0.0

        return {
            "calls_total": self.calls_total,
            "calls_success": self.calls_success,
            "calls_error": self.calls_error,
            "calls_timeout": self.calls_timeout,
            "success_rate_percent": success_rate,
            "avg_latency_ms": avg_latency,
        }


# Singleton instance
_handler: Optional[ToolCallHandler] = None


def get_tool_call_handler() -> ToolCallHandler:
    """
    Get singleton instance of ToolCallHandler.

    Returns:
        Global ToolCallHandler instance
    """
    global _handler
    if _handler is None:
        _handler = ToolCallHandler()
    return _handler
