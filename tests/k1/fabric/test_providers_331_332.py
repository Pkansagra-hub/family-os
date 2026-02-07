"""
Integration tests for Epic 3.3.1-3.3.2:

  - 3.3.1 CapabilityProvider Protocol + BaseProvider ABC
  - 3.3.2 MCPProvider (MCP tool execution)

Target: 40+ tests covering:
  - CapabilityProvider protocol compliance
  - BaseProvider timing/logging wrapper, error handling, health_check, _check_timeout
  - MCPProvider execute flow, health_check, capabilities, error paths
  - MCP message types (MCPRequest, MCPResponse)
  - Transport port (IMCPTransport) compliance
  - Exception hierarchy
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.providers.base_provider import (
    BaseProvider,
    CapabilityProvider,
    ProviderError,
    ProviderExecutionError,
    ProviderTimeoutError,
)
from k1.fabric.providers.mcp_provider import (
    IMCPTransport,
    MCPProvider,
    MCPProviderError,
    MCPRequest,
    MCPResponse,
    MCPServerNotFoundError,
    MCPToolNotFoundError,
    MCPTransportError,
)
from k1.fabric.types import (
    CapabilityRequest,
    CapabilityResult,
    ExecutionContext,
    ProviderConfig,
    ProviderHealth,
    ProviderStatus,
)

# =========================================================================
# Helpers
# =========================================================================


def _request(
    capability_name: str = "tool.execute.weather",
    params: Optional[Dict[str, Any]] = None,
    request_id: str = "req-1",
    trace_id: str = "trace-1",
) -> CapabilityRequest:
    """Build a minimal CapabilityRequest."""
    return CapabilityRequest(
        request_id=request_id,
        capability_name=capability_name,
        params=params or {"city": "London"},
        caller="test",
        trace_id=trace_id,
    )


def _context(trace_id: str = "trace-1") -> ExecutionContext:
    """Build a minimal ExecutionContext."""
    return ExecutionContext(trace_id=trace_id)


def _config(
    provider_id: str = "mcp-weather",
    provider_type: str = "MCP",
    endpoint: str = "http://localhost:8080",
    transport: str = "sse",
    max_execution_ms: int = 30000,
) -> ProviderConfig:
    """Build a ProviderConfig for tests."""
    return ProviderConfig(
        provider_id=provider_id,
        provider_type=provider_type,
        endpoint=endpoint,
        transport=transport,
        max_execution_ms=max_execution_ms,
    )


# =========================================================================
# Test doubles
# =========================================================================


class FakeTransport:
    """
    Test double satisfying IMCPTransport Protocol.

    Configurable responses, errors, connection state, and ping results.
    """

    def __init__(
        self,
        *,
        response: Optional[MCPResponse] = None,
        error: Optional[Exception] = None,
        connected: bool = True,
        ping_result: bool = True,
        ping_error: Optional[Exception] = None,
        latency_ms: int = 0,
    ):
        self._response = response
        self._error = error
        self._connected = connected
        self._ping_result = ping_result
        self._ping_error = ping_error
        self._latency_ms = latency_ms
        self.sent_requests: List[MCPRequest] = []
        self.closed = False

    async def send(self, request: MCPRequest) -> MCPResponse:
        self.sent_requests.append(request)
        if self._latency_ms > 0:
            await asyncio.sleep(self._latency_ms / 1000.0)
        if self._error:
            raise self._error
        return self._response or MCPResponse(
            success=True,
            content=[{"type": "text", "text": "ok"}],
        )

    async def ping(self) -> bool:
        if self._ping_error:
            raise self._ping_error
        return self._ping_result

    def is_connected(self) -> bool:
        return self._connected

    async def close(self) -> None:
        self.closed = True


class ConcreteProvider(BaseProvider):
    """Minimal BaseProvider subclass for testing the ABC."""

    def __init__(
        self,
        config: ProviderConfig,
        *,
        result: Optional[CapabilityResult] = None,
        error: Optional[Exception] = None,
        capability_list: Optional[List[str]] = None,
    ):
        super().__init__(config)
        self._result = result
        self._error = error
        self._capability_list = capability_list or ["test.capability"]

    async def _execute(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str,
    ) -> CapabilityResult:
        if self._error:
            raise self._error
        return self._result or CapabilityResult.success_result(
            request_id=request.request_id,
            data={"result": "ok"},
            provider_id=self.config.provider_id,
            trace_id=trace_id,
        )

    def capabilities(self) -> List[str]:
        return list(self._capability_list)


# =========================================================================
# 3.3.1 -- CapabilityProvider Protocol
# =========================================================================


class TestCapabilityProviderProtocol:
    """Verify CapabilityProvider Protocol compliance."""

    def test_concrete_provider_satisfies_protocol(self) -> None:
        """ConcreteProvider (BaseProvider subclass) satisfies CapabilityProvider."""
        provider: CapabilityProvider = ConcreteProvider(_config())
        assert hasattr(provider, "execute")
        assert hasattr(provider, "health_check")
        assert hasattr(provider, "capabilities")

    def test_mcp_provider_satisfies_protocol(self) -> None:
        """MCPProvider satisfies CapabilityProvider Protocol."""
        transport = FakeTransport()
        provider: CapabilityProvider = MCPProvider(
            _config(),
            transport=transport,
            capability_names=["tool.execute.weather"],
        )
        assert hasattr(provider, "execute")
        assert hasattr(provider, "health_check")
        assert hasattr(provider, "capabilities")

    def test_protocol_is_structural(self) -> None:
        """Any class with the right methods satisfies CapabilityProvider."""

        class AdHocProvider:
            async def execute(
                self, request: CapabilityRequest, context: ExecutionContext, trace_id: str
            ) -> CapabilityResult:
                return CapabilityResult.success_result(
                    request_id="r1", data={}, provider_id="adhoc", trace_id=trace_id
                )

            async def health_check(self) -> ProviderHealth:
                return ProviderHealth(provider_id="adhoc")

            def capabilities(self) -> List[str]:
                return []

        p: CapabilityProvider = AdHocProvider()
        assert p.capabilities() == []


# =========================================================================
# 3.3.1 -- BaseProvider ABC
# =========================================================================


class TestBaseProvider:
    """Test BaseProvider template method pattern."""

    async def test_execute_returns_result(self) -> None:
        """Successful _execute returns CapabilityResult via execute()."""
        provider = ConcreteProvider(_config(provider_id="bp-1"))
        result = await provider.execute(_request(), _context(), "trace-1")
        assert result.success is True
        assert result.data == {"result": "ok"}
        assert result.provider_id == "bp-1"

    async def test_execute_catches_timeout_error(self) -> None:
        """ProviderTimeoutError -> timeout_result."""
        provider = ConcreteProvider(
            _config(provider_id="bp-2"),
            error=ProviderTimeoutError("bp-2", 5000),
        )
        result = await provider.execute(_request(), _context(), "trace-2")
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "timeout"
        assert result.error.retriable is True

    async def test_execute_catches_execution_error(self) -> None:
        """ProviderExecutionError -> failure_result with correct error_code."""
        provider = ConcreteProvider(
            _config(provider_id="bp-3"),
            error=ProviderExecutionError(
                "bp-3", "disk full", retriable=True, error_code="storage_error"
            ),
        )
        result = await provider.execute(_request(), _context(), "trace-3")
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "storage_error"
        assert result.error.retriable is True

    async def test_execute_catches_unexpected_exception(self) -> None:
        """Unexpected Exception -> failure_result with 'provider_error'."""
        provider = ConcreteProvider(
            _config(provider_id="bp-4"),
            error=RuntimeError("segfault simulator"),
        )
        result = await provider.execute(_request(), _context(), "trace-4")
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "provider_error"
        assert result.error.retriable is False
        assert "RuntimeError" in result.error.message

    async def test_default_health_check_returns_unknown(self) -> None:
        """Default health_check returns UNKNOWN status."""
        provider = ConcreteProvider(_config(provider_id="bp-5"))
        health = await provider.health_check()
        assert health.status == ProviderStatus.UNKNOWN.value
        assert health.provider_id == "bp-5"

    def test_config_property(self) -> None:
        """BaseProvider exposes config, provider_id, provider_type."""
        cfg = _config(provider_id="bp-6", provider_type="MCP")
        provider = ConcreteProvider(cfg)
        assert provider.config is cfg
        assert provider.provider_id == "bp-6"
        assert provider.provider_type == "MCP"

    def test_capabilities_delegates_to_subclass(self) -> None:
        """capabilities() returns what the subclass provides."""
        provider = ConcreteProvider(
            _config(),
            capability_list=["a.b.c", "x.y.z"],
        )
        assert provider.capabilities() == ["a.b.c", "x.y.z"]

    def test_check_timeout_does_not_raise_within_budget(self) -> None:
        """_check_timeout does not raise if within max_execution_ms."""
        provider = ConcreteProvider(_config(max_execution_ms=30000))
        provider._check_timeout(time.monotonic())  # just started, should not raise

    def test_check_timeout_raises_past_deadline(self) -> None:
        """_check_timeout raises ProviderTimeoutError if past deadline."""
        provider = ConcreteProvider(_config(max_execution_ms=100))
        # Simulate a start time far in the past
        past = time.monotonic() - 1.0  # 1 second ago, way past 100ms
        with pytest.raises(ProviderTimeoutError) as exc_info:
            provider._check_timeout(past)
        assert exc_info.value.timeout_ms == 100

    def test_repr(self) -> None:
        """BaseProvider __repr__ is informative."""
        provider = ConcreteProvider(_config(provider_id="bp-repr", provider_type="MCP"))
        r = repr(provider)
        assert "ConcreteProvider" in r
        assert "bp-repr" in r
        assert "MCP" in r


# =========================================================================
# 3.3.1 -- Exception hierarchy
# =========================================================================


class TestProviderExceptions:
    """Test provider exception classes."""

    def test_provider_error_basic(self) -> None:
        err = ProviderError("p1", "something broke")
        assert err.provider_id == "p1"
        assert "[p1]" in str(err)
        assert "something broke" in str(err)

    def test_provider_execution_error_attributes(self) -> None:
        err = ProviderExecutionError("p2", "bad input", retriable=True, error_code="validation")
        assert err.provider_id == "p2"
        assert err.retriable is True
        assert err.error_code == "validation"
        assert isinstance(err, ProviderError)

    def test_provider_timeout_error_attributes(self) -> None:
        err = ProviderTimeoutError("p3", 5000)
        assert err.provider_id == "p3"
        assert err.timeout_ms == 5000
        assert "5000ms" in str(err)
        assert isinstance(err, ProviderError)

    def test_exception_hierarchy(self) -> None:
        """All provider errors inherit from ProviderError -> Exception."""
        assert issubclass(ProviderExecutionError, ProviderError)
        assert issubclass(ProviderTimeoutError, ProviderError)
        assert issubclass(ProviderError, Exception)


# =========================================================================
# 3.3.2 -- MCPRequest / MCPResponse
# =========================================================================


class TestMCPMessageTypes:
    """Test MCP protocol message dataclasses."""

    def test_mcp_request_defaults(self) -> None:
        req = MCPRequest()
        assert req.method == "tools/call"
        assert req.tool_name == ""
        assert req.arguments == {}
        assert req.timeout_ms == 30000
        assert req.trace_id == ""

    def test_mcp_request_custom(self) -> None:
        req = MCPRequest(
            method="tools/call",
            tool_name="get_weather",
            arguments={"city": "London"},
            timeout_ms=5000,
            trace_id="t-42",
        )
        assert req.tool_name == "get_weather"
        assert req.arguments == {"city": "London"}
        assert req.timeout_ms == 5000
        assert req.trace_id == "t-42"

    def test_mcp_request_is_frozen(self) -> None:
        req = MCPRequest(tool_name="test")
        with pytest.raises(AttributeError):
            req.tool_name = "changed"  # type: ignore[misc]

    def test_mcp_response_success(self) -> None:
        resp = MCPResponse(
            success=True,
            content=[{"type": "text", "text": "sunny"}],
            latency_ms=42,
        )
        assert resp.success is True
        assert resp.content[0]["text"] == "sunny"
        assert resp.latency_ms == 42

    def test_mcp_response_error(self) -> None:
        resp = MCPResponse(
            success=False,
            error_message="tool crashed",
        )
        assert resp.success is False
        assert resp.error_message == "tool crashed"

    def test_mcp_response_is_frozen(self) -> None:
        resp = MCPResponse()
        with pytest.raises(AttributeError):
            resp.success = False  # type: ignore[misc]


# =========================================================================
# 3.3.2 -- MCPProvider exceptions
# =========================================================================


class TestMCPExceptions:
    """Test MCP-specific exception hierarchy."""

    def test_mcp_provider_error_inherits(self) -> None:
        assert issubclass(MCPProviderError, ProviderExecutionError)
        assert issubclass(MCPProviderError, ProviderError)

    def test_mcp_server_not_found(self) -> None:
        err = MCPServerNotFoundError("p1", "http://localhost:8080")
        assert err.endpoint == "http://localhost:8080"
        assert err.retriable is True
        assert err.error_code == "mcp_error"
        assert "not found" in str(err).lower()

    def test_mcp_tool_not_found(self) -> None:
        err = MCPToolNotFoundError("p2", "get_weather")
        assert err.tool_name == "get_weather"
        assert err.retriable is False
        assert "get_weather" in str(err)

    def test_mcp_transport_error(self) -> None:
        err = MCPTransportError("p3", "connection reset", retriable=True)
        assert err.retriable is True
        assert "connection reset" in str(err)

    def test_mcp_transport_error_non_retriable(self) -> None:
        err = MCPTransportError("p4", "protocol error", retriable=False)
        assert err.retriable is False


# =========================================================================
# 3.3.2 -- MCPProvider construction
# =========================================================================


class TestMCPProviderConstruction:
    """Test MCPProvider initialization."""

    def test_basic_construction(self) -> None:
        transport = FakeTransport()
        provider = MCPProvider(
            _config(provider_id="mcp-1"),
            transport=transport,
            capability_names=["tool.execute.weather"],
        )
        assert provider.provider_id == "mcp-1"
        assert provider.capabilities() == ["tool.execute.weather"]

    def test_construction_with_tool_name_map(self) -> None:
        transport = FakeTransport()
        provider = MCPProvider(
            _config(),
            transport=transport,
            capability_names=["tool.execute.weather"],
            tool_name_map={"tool.execute.weather": "get_weather"},
        )
        assert provider._resolve_tool_name("tool.execute.weather") == "get_weather"
        assert provider._resolve_tool_name("unmapped") == "unmapped"

    def test_construction_default_capabilities(self) -> None:
        transport = FakeTransport()
        provider = MCPProvider(_config(), transport=transport)
        assert provider.capabilities() == []

    def test_capabilities_returns_copy(self) -> None:
        transport = FakeTransport()
        provider = MCPProvider(
            _config(),
            transport=transport,
            capability_names=["a", "b"],
        )
        caps = provider.capabilities()
        caps.append("c")
        assert provider.capabilities() == ["a", "b"]  # original unchanged

    def test_repr(self) -> None:
        transport = FakeTransport()
        provider = MCPProvider(
            _config(provider_id="mcp-repr", endpoint="http://localhost"),
            transport=transport,
            capability_names=["a", "b"],
        )
        r = repr(provider)
        assert "MCPProvider" in r
        assert "mcp-repr" in r

    def test_kwargs_passthrough(self) -> None:
        """Extra kwargs are ignored (ProviderFactory port_deps pass-through)."""
        transport = FakeTransport()
        provider = MCPProvider(
            _config(),
            transport=transport,
            capability_names=["test"],
            some_extra_arg="ignored",
        )
        assert provider.capabilities() == ["test"]


# =========================================================================
# 3.3.2 -- MCPProvider.execute (happy path)
# =========================================================================


class TestMCPProviderExecute:
    """Test MCPProvider execution flow."""

    async def test_successful_execute_single_text(self) -> None:
        """Single text content block returns {"result": text}."""
        transport = FakeTransport(
            response=MCPResponse(
                success=True,
                content=[{"type": "text", "text": "Sunny, 22C"}],
                latency_ms=50,
            ),
        )
        provider = MCPProvider(
            _config(provider_id="mcp-exec-1"),
            transport=transport,
            capability_names=["tool.execute.weather"],
        )
        result = await provider.execute(
            _request(capability_name="tool.execute.weather"),
            _context(),
            "trace-exec-1",
        )
        assert result.success is True
        assert result.data == {"result": "Sunny, 22C"}
        assert result.provider_id == "mcp-exec-1"
        assert result.trace_id == "trace-exec-1"

    async def test_successful_execute_multiple_blocks(self) -> None:
        """Multiple content blocks return {"content": [blocks]}."""
        blocks = [
            {"type": "text", "text": "part1"},
            {"type": "image", "url": "http://example.com/img.png"},
        ]
        transport = FakeTransport(
            response=MCPResponse(success=True, content=blocks),
        )
        provider = MCPProvider(
            _config(),
            transport=transport,
            capability_names=["multi"],
        )
        result = await provider.execute(_request(capability_name="multi"), _context(), "t-2")
        assert result.success is True
        assert result.data == {"content": blocks}

    async def test_successful_execute_empty_content(self) -> None:
        """Empty content returns {"result": None}."""
        transport = FakeTransport(
            response=MCPResponse(success=True, content=[]),
        )
        provider = MCPProvider(
            _config(),
            transport=transport,
            capability_names=["empty"],
        )
        result = await provider.execute(_request(capability_name="empty"), _context(), "t-3")
        assert result.success is True
        assert result.data == {"result": None}

    async def test_transport_receives_correct_mcp_request(self) -> None:
        """Verify the MCPRequest sent to transport has correct fields."""
        transport = FakeTransport()
        provider = MCPProvider(
            _config(max_execution_ms=5000),
            transport=transport,
            capability_names=["tool.execute.weather"],
            tool_name_map={"tool.execute.weather": "get_weather"},
        )
        await provider.execute(
            _request(
                capability_name="tool.execute.weather",
                params={"city": "Paris"},
            ),
            _context(),
            "trace-verify",
        )
        assert len(transport.sent_requests) == 1
        mcp_req = transport.sent_requests[0]
        assert mcp_req.method == "tools/call"
        assert mcp_req.tool_name == "get_weather"
        assert mcp_req.arguments == {"city": "Paris"}
        assert mcp_req.timeout_ms == 5000
        assert mcp_req.trace_id == "trace-verify"

    async def test_tool_name_map_used(self) -> None:
        """When tool_name_map has a mapping, it is used instead of capability_name."""
        transport = FakeTransport()
        provider = MCPProvider(
            _config(),
            transport=transport,
            capability_names=["tool.execute.translate"],
            tool_name_map={"tool.execute.translate": "translate_text"},
        )
        await provider.execute(
            _request(capability_name="tool.execute.translate"),
            _context(),
            "t-map",
        )
        assert transport.sent_requests[0].tool_name == "translate_text"

    async def test_no_tool_name_map_uses_capability_name(self) -> None:
        """Without tool_name_map, capability_name is used as tool name."""
        transport = FakeTransport()
        provider = MCPProvider(
            _config(),
            transport=transport,
            capability_names=["tool.execute.weather"],
        )
        await provider.execute(
            _request(capability_name="tool.execute.weather"),
            _context(),
            "t-no-map",
        )
        assert transport.sent_requests[0].tool_name == "tool.execute.weather"


# =========================================================================
# 3.3.2 -- MCPProvider.execute (error paths)
# =========================================================================


class TestMCPProviderErrors:
    """Test MCPProvider error handling in execute()."""

    async def test_disconnected_transport_returns_failure(self) -> None:
        """Not connected -> MCPServerNotFoundError -> failure_result."""
        transport = FakeTransport(connected=False)
        provider = MCPProvider(
            _config(provider_id="mcp-disc", endpoint="http://example:8080"),
            transport=transport,
            capability_names=["test"],
        )
        result = await provider.execute(_request(), _context(), "t-disc")
        # BaseProvider catches ProviderExecutionError (MCPServerNotFoundError)
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "mcp_error"
        assert result.error.retriable is True

    async def test_transport_error_returns_failure(self) -> None:
        """Transport exception -> MCPTransportError -> failure_result."""
        transport = FakeTransport(error=ConnectionError("connection reset"))
        provider = MCPProvider(
            _config(provider_id="mcp-terr"),
            transport=transport,
            capability_names=["test"],
        )
        result = await provider.execute(_request(), _context(), "t-terr")
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "mcp_error"

    async def test_mcp_tool_error_response(self) -> None:
        """MCP response with success=False -> failure_result with mcp_tool_error."""
        transport = FakeTransport(
            response=MCPResponse(
                success=False,
                error_message="calculator overflow",
            ),
        )
        provider = MCPProvider(
            _config(),
            transport=transport,
            capability_names=["calc"],
        )
        result = await provider.execute(_request(capability_name="calc"), _context(), "t-mcperr")
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "mcp_tool_error"
        assert "calculator overflow" in result.error.message

    async def test_mcp_tool_not_found_response(self) -> None:
        """MCP response with 'not found' error -> MCPToolNotFoundError."""
        transport = FakeTransport(
            response=MCPResponse(
                success=False,
                error_message="Tool 'missing_tool' not found on server",
            ),
        )
        provider = MCPProvider(
            _config(provider_id="mcp-tnf"),
            transport=transport,
            capability_names=["missing_tool"],
        )
        result = await provider.execute(
            _request(capability_name="missing_tool"), _context(), "t-tnf"
        )
        # MCPToolNotFoundError is a ProviderExecutionError -> caught by BaseProvider
        assert result.success is False
        assert result.error is not None
        assert result.error.code == "mcp_error"  # MCPToolNotFoundError uses mcp_error
        assert result.error.retriable is False

    async def test_mcp_unknown_tool_response(self) -> None:
        """MCP response with 'unknown tool' also triggers MCPToolNotFoundError."""
        transport = FakeTransport(
            response=MCPResponse(
                success=False,
                error_message="Unknown tool: xyz",
            ),
        )
        provider = MCPProvider(
            _config(),
            transport=transport,
            capability_names=["xyz"],
        )
        result = await provider.execute(_request(capability_name="xyz"), _context(), "t-unknown")
        assert result.success is False
        assert result.error is not None
        assert result.error.retriable is False


# =========================================================================
# 3.3.2 -- MCPProvider.health_check
# =========================================================================


class TestMCPProviderHealthCheck:
    """Test MCPProvider health_check via transport.ping()."""

    async def test_healthy_ping(self) -> None:
        transport = FakeTransport(ping_result=True)
        provider = MCPProvider(
            _config(provider_id="mcp-h1"),
            transport=transport,
            capability_names=["test"],
        )
        health = await provider.health_check()
        assert health.status == ProviderStatus.HEALTHY.value
        assert health.provider_id == "mcp-h1"
        assert health.latency_ms >= 0

    async def test_unhealthy_ping_false(self) -> None:
        transport = FakeTransport(ping_result=False)
        provider = MCPProvider(
            _config(provider_id="mcp-h2"),
            transport=transport,
        )
        health = await provider.health_check()
        assert health.status == ProviderStatus.UNHEALTHY.value
        assert health.error == "ping returned false"

    async def test_unhealthy_ping_exception(self) -> None:
        transport = FakeTransport(ping_error=ConnectionError("refused"))
        provider = MCPProvider(
            _config(provider_id="mcp-h3"),
            transport=transport,
        )
        health = await provider.health_check()
        assert health.status == ProviderStatus.UNHEALTHY.value
        assert "refused" in (health.error or "")


# =========================================================================
# 3.3.2 -- IMCPTransport Protocol compliance
# =========================================================================


class TestIMCPTransportProtocol:
    """Verify FakeTransport satisfies IMCPTransport Protocol."""

    def test_fake_transport_satisfies_protocol(self) -> None:
        transport: IMCPTransport = FakeTransport()
        assert hasattr(transport, "send")
        assert hasattr(transport, "ping")
        assert hasattr(transport, "is_connected")
        assert hasattr(transport, "close")

    async def test_transport_close(self) -> None:
        transport = FakeTransport()
        await transport.close()
        assert transport.closed is True

    def test_transport_is_connected(self) -> None:
        assert FakeTransport(connected=True).is_connected() is True
        assert FakeTransport(connected=False).is_connected() is False


# =========================================================================
# 3.3.2 -- MCPProvider._extract_data
# =========================================================================


class TestMCPExtractData:
    """Test static _extract_data helper."""

    def test_empty_content(self) -> None:
        assert MCPProvider._extract_data([]) == {"result": None}

    def test_single_text_block(self) -> None:
        content = [{"type": "text", "text": "hello"}]
        assert MCPProvider._extract_data(content) == {"result": "hello"}

    def test_single_non_text_block(self) -> None:
        content = [{"type": "image", "url": "http://img.png"}]
        assert MCPProvider._extract_data(content) == {"content": content}

    def test_multiple_blocks(self) -> None:
        content = [
            {"type": "text", "text": "a"},
            {"type": "text", "text": "b"},
        ]
        assert MCPProvider._extract_data(content) == {"content": content}


# =========================================================================
# 3.3.2 -- MCPProvider wiring verification
# =========================================================================


class TestMCPProviderWiring:
    """Verify MCPProvider integrates correctly with ProviderFactory."""

    def test_can_register_with_provider_factory(self) -> None:
        """MCPProvider constructor is compatible with ProviderFactory.register_handler."""
        from k1.fabric.provider_resolution.provider_factory import ProviderFactory

        factory = ProviderFactory()
        transport = FakeTransport()

        def mcp_constructor(config: ProviderConfig) -> MCPProvider:
            return MCPProvider(
                config,
                transport=transport,
                capability_names=["tool.execute.weather"],
            )

        factory.register_handler("MCP", mcp_constructor)
        provider = factory.create(_config(provider_type="MCP"))
        assert isinstance(provider, MCPProvider)
        assert provider.capabilities() == ["tool.execute.weather"]

    async def test_factory_created_provider_executes(self) -> None:
        """Provider from factory can execute requests end-to-end."""
        from k1.fabric.provider_resolution.provider_factory import ProviderFactory

        transport = FakeTransport(
            response=MCPResponse(
                success=True,
                content=[{"type": "text", "text": "rainy"}],
                latency_ms=10,
            ),
        )
        factory = ProviderFactory()
        factory.register_handler(
            "MCP",
            lambda config: MCPProvider(
                config,
                transport=transport,
                capability_names=["tool.execute.weather"],
            ),
        )
        provider = factory.create(_config(provider_type="MCP"))
        result = await provider.execute(_request(), _context(), "trace-wired")
        assert result.success is True
        assert result.data == {"result": "rainy"}


# =========================================================================
# Module exports verification
# =========================================================================


class TestModuleExports:
    """Verify providers/__init__.py exports correct symbols."""

    def test_providers_init_exports(self) -> None:
        import k1.fabric.providers as providers_pkg

        expected = [
            "BaseProvider",
            "CapabilityProvider",
            "IMCPTransport",
            "MCPProvider",
            "MCPProviderError",
            "MCPRequest",
            "MCPResponse",
            "MCPServerNotFoundError",
            "MCPToolNotFoundError",
            "MCPTransportError",
            "ProviderError",
            "ProviderExecutionError",
            "ProviderTimeoutError",
        ]
        for name in expected:
            assert hasattr(providers_pkg, name), f"Missing export: {name}"

    def test_provider_resolution_still_exports_capability_provider(self) -> None:
        """provider_resolution/__init__.py still exports CapabilityProvider."""
        from k1.fabric.provider_resolution import CapabilityProvider as ResCP

        assert ResCP is CapabilityProvider
