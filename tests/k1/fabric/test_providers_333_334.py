"""
Integration tests for Epic 3.3.3-3.3.4:

  - 3.3.3 WASMProvider (sandboxed WASM execution)
  - 3.3.4 BridgeProvider (K0 connector proxy)

Target: 50+ tests covering:
  - WASMProvider execute flow, health_check, capabilities, error paths
  - WASM module loading, sandbox config, memory limit, timeout
  - WASM message types (WASMModuleHandle, WASMSandboxConfig, WASMExecutionResult)
  - WASM runtime port (IWASMRuntime) compliance
  - WASM exception hierarchy
  - BridgeProvider execute flow, health_check, capabilities, error paths
  - Bridge offline fallback (LOCAL COLD), K0 health modes
  - Bridge operation routing (direct, IFL, query)
  - Bridge message types (BridgeCommand, BridgeResponse)
  - Bridge port (IBridgePort) compliance
  - Bridge exception hierarchy
  - __init__.py export validation for 3.3.3 + 3.3.4
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.providers.base_provider import (
    BaseProvider,
    CapabilityProvider,
    ProviderError,
    ProviderExecutionError,
)
from k1.fabric.providers.bridge_provider import (
    BRIDGE_OPERATIONS,
    BridgeCommand,
    BridgeOperationError,
    BridgeProvider,
    BridgeProviderError,
    BridgeResponse,
    BridgeUnavailableError,
    K0HealthMode,
    _classify_operation,
)
from k1.fabric.providers.wasm_provider import (
    DEFAULT_MAX_EXECUTION_MS,
    DEFAULT_SANDBOX_MEMORY_MB,
    WASMExecutionError,
    WASMExecutionResult,
    WASMMemoryLimitError,
    WASMModuleHandle,
    WASMModuleLoadError,
    WASMProvider,
    WASMProviderError,
    WASMSandboxConfig,
)
from k1.fabric.types import (
    CapabilityRequest,
    CapabilityResult,
    ExecutionContext,
    ProviderConfig,
    ProviderStatus,
)

# =========================================================================
# Helpers
# =========================================================================


def _request(
    capability_name: str = "tool.execute.calculator",
    params: Optional[Dict[str, Any]] = None,
    request_id: str = "req-1",
    trace_id: str = "trace-1",
    timeout_ms: int = 0,
) -> CapabilityRequest:
    """Build a minimal CapabilityRequest."""
    return CapabilityRequest(
        request_id=request_id,
        capability_name=capability_name,
        params=params or {"x": 1, "y": 2},
        caller="test",
        trace_id=trace_id,
        timeout_ms=timeout_ms,
    )


def _context(trace_id: str = "trace-1") -> ExecutionContext:
    """Build a minimal ExecutionContext."""
    return ExecutionContext(trace_id=trace_id)


def _profile_context(trace_id: str = "trace-1") -> ExecutionContext:
    """Build an ExecutionContext carrying M3 prompt/profile metadata."""
    return ExecutionContext(
        trace_id=trace_id,
        prompt="Use the calculator sandbox procedure.",
        session_sections={
            "context_override": {
                "activity_profile": "calculator.v1",
                "prompt_template": "calculator_activity_v1",
            }
        },
    )


def _wasm_config(
    provider_id: str = "calc_wasm",
    module_path: str = "k1/wasm/calc.wasm",
    sandbox_memory_mb: int = 64,
    max_execution_ms: int = 5000,
) -> ProviderConfig:
    """Build a ProviderConfig for WASM tests."""
    return ProviderConfig(
        provider_id=provider_id,
        provider_type="WASM",
        module_path=module_path,
        sandbox_memory_mb=sandbox_memory_mb,
        max_execution_ms=max_execution_ms,
    )


def _bridge_config(
    provider_id: str = "k0_memory_bridge",
    endpoint: str = "bridge://k0",
    max_execution_ms: int = 10000,
) -> ProviderConfig:
    """Build a ProviderConfig for Bridge tests."""
    return ProviderConfig(
        provider_id=provider_id,
        provider_type="BRIDGE",
        endpoint=endpoint,
        max_execution_ms=max_execution_ms,
    )


# =========================================================================
# Test doubles -- WASM
# =========================================================================


class FakeWASMRuntime:
    """
    Test double satisfying IWASMRuntime Protocol.

    Configurable module handles, execution results, and errors.
    """

    def __init__(
        self,
        *,
        handle: Optional[WASMModuleHandle] = None,
        result: Optional[WASMExecutionResult] = None,
        load_error: Optional[Exception] = None,
        exec_error: Optional[Exception] = None,
        available: bool = True,
    ):
        self._handle = handle or WASMModuleHandle(
            module_path="k1/wasm/calc.wasm",
            module_id="calc-v1",
            loaded=True,
        )
        self._result = result or WASMExecutionResult(
            success=True,
            output={"sum": 3},
            execution_ms=10,
        )
        self._load_error = load_error
        self._exec_error = exec_error
        self._available = available
        self.loaded_modules: List[str] = []
        self.executed_calls: List[Dict[str, Any]] = []

    async def load_module(self, module_path: str) -> WASMModuleHandle:
        self.loaded_modules.append(module_path)
        if self._load_error:
            raise self._load_error
        return self._handle

    async def execute(
        self,
        handle: WASMModuleHandle,
        function_name: str,
        params: Dict[str, Any],
        sandbox_config: WASMSandboxConfig,
    ) -> WASMExecutionResult:
        self.executed_calls.append(
            {
                "handle": handle,
                "function_name": function_name,
                "params": params,
                "sandbox_config": sandbox_config,
            }
        )
        if self._exec_error:
            raise self._exec_error
        return self._result

    def is_available(self) -> bool:
        return self._available


# =========================================================================
# Test doubles -- Bridge
# =========================================================================


class FakeBridgePort:
    """
    Test double satisfying canonical IBridgePort Protocol.

    Configurable responses, errors, availability, and K0 health mode.
    Updated to use canonical IBridgePort signature (ports/bridge_port.py):
      send_command(operation, payload, *, trace_id, timeout_ms) -> BridgeResponse
      query(operation, selectors, *, trace_id, timeout_ms) -> BridgeResponse
      get_health() -> BridgeHealth (from ports/bridge_port.py)
    """

    def __init__(
        self,
        *,
        cmd_response: Optional[BridgeResponse] = None,
        query_response: Optional[BridgeResponse] = None,
        cmd_error: Optional[Exception] = None,
        query_error: Optional[Exception] = None,
        available: bool = True,
        health: K0HealthMode = K0HealthMode.K0_FULL,
    ):
        self._cmd_response = cmd_response or BridgeResponse(
            success=True,
            data={"stored": True},
            latency_ms=5,
        )
        self._query_response = query_response or BridgeResponse(
            success=True,
            data={"memories": ["hello"]},
            latency_ms=3,
        )
        self._cmd_error = cmd_error
        self._query_error = query_error
        self._available = available
        self._health = health
        self.sent_commands: List[Dict[str, Any]] = []
        self.queries: List[Dict[str, Any]] = []

    async def send_command(
        self,
        operation: str,
        payload: Dict[str, Any],
        *,
        trace_id: str = "",
        timeout_ms: int = 0,
    ) -> BridgeResponse:
        self.sent_commands.append(
            {"operation": operation, "payload": payload, "trace_id": trace_id}
        )
        if self._cmd_error:
            raise self._cmd_error
        return self._cmd_response

    async def query(
        self,
        operation: str,
        selectors: Dict[str, Any],
        *,
        trace_id: str = "",
        timeout_ms: int = 0,
    ) -> BridgeResponse:
        self.queries.append(
            {
                "operation": operation,
                "selectors": selectors,
                "trace_id": trace_id,
            }
        )
        if self._query_error:
            raise self._query_error
        return self._query_response

    def is_available(self) -> bool:
        return self._available

    def get_health(self) -> Any:
        """Return BridgeHealth-compatible object with .mode attribute."""
        from k1.fabric.ports.bridge_port import BridgeHealth

        return BridgeHealth(
            available=self._available,
            mode=self._health.value,
        )


# =========================================================================
# 3.3.3 -- WASMProvider: Protocol compliance
# =========================================================================


class TestWASMProviderProtocol:
    """Verify WASMProvider satisfies CapabilityProvider Protocol."""

    def test_wasm_provider_satisfies_protocol(self) -> None:
        """WASMProvider is a valid CapabilityProvider."""
        runtime = FakeWASMRuntime()
        provider: CapabilityProvider = WASMProvider(
            _wasm_config(),
            runtime=runtime,
            capability_names=["tool.execute.calculator"],
        )
        assert hasattr(provider, "execute")
        assert hasattr(provider, "health_check")
        assert hasattr(provider, "capabilities")

    def test_wasm_provider_is_base_provider(self) -> None:
        """WASMProvider extends BaseProvider."""
        runtime = FakeWASMRuntime()
        provider = WASMProvider(_wasm_config(), runtime=runtime)
        assert isinstance(provider, BaseProvider)


# =========================================================================
# 3.3.3 -- WASMProvider: Capabilities
# =========================================================================


class TestWASMProviderCapabilities:
    """Test WASMProvider.capabilities()."""

    def test_capabilities_returns_configured_list(self) -> None:
        caps = ["tool.execute.calc", "tool.execute.hash"]
        provider = WASMProvider(
            _wasm_config(),
            runtime=FakeWASMRuntime(),
            capability_names=caps,
        )
        assert provider.capabilities() == caps

    def test_capabilities_default_empty(self) -> None:
        provider = WASMProvider(_wasm_config(), runtime=FakeWASMRuntime())
        assert provider.capabilities() == []

    def test_capabilities_returns_copy(self) -> None:
        """Returned list should be a copy, not a reference."""
        caps = ["tool.execute.calc"]
        provider = WASMProvider(
            _wasm_config(),
            runtime=FakeWASMRuntime(),
            capability_names=caps,
        )
        result = provider.capabilities()
        result.append("hacked")
        assert provider.capabilities() == ["tool.execute.calc"]


# =========================================================================
# 3.3.3 -- WASMProvider: Execute (success path)
# =========================================================================


class TestWASMProviderExecute:
    """Test WASMProvider._execute through BaseProvider.execute()."""

    async def test_execute_success(self) -> None:
        """Successful WASM execution returns CapabilityResult.success."""
        runtime = FakeWASMRuntime()
        provider = WASMProvider(
            _wasm_config(),
            runtime=runtime,
            capability_names=["tool.execute.calc"],
        )
        result = await provider.execute(_request(), _context(), "trace-1")
        assert result.success is True
        assert result.data == {"sum": 3}
        assert result.provider_id == "calc_wasm"

    async def test_execute_loads_module(self) -> None:
        """execute() loads the WASM module from config.module_path."""
        runtime = FakeWASMRuntime()
        provider = WASMProvider(
            _wasm_config(module_path="k1/wasm/custom.wasm"),
            runtime=runtime,
            capability_names=["tool.execute.calc"],
        )
        await provider.execute(_request(), _context(), "trace-1")
        assert runtime.loaded_modules == ["k1/wasm/custom.wasm"]

    async def test_execute_passes_params(self) -> None:
        """execute() passes request.params to WASM runtime."""
        runtime = FakeWASMRuntime()
        provider = WASMProvider(
            _wasm_config(),
            runtime=runtime,
            capability_names=["tool.execute.calc"],
        )
        req = _request(params={"a": 10, "b": 20})
        await provider.execute(req, _context(), "trace-1")
        assert len(runtime.executed_calls) == 1
        assert runtime.executed_calls[0]["params"] == {"a": 10, "b": 20}

    async def test_execute_passes_prompt_profile_metadata(self) -> None:
        """M3: prompt/profile metadata travels under reserved __metadata__."""
        runtime = FakeWASMRuntime()
        provider = WASMProvider(
            _wasm_config(),
            runtime=runtime,
            capability_names=["tool.execute.calc"],
        )

        await provider.execute(
            _request(params={"a": 10, "b": 20}),
            _profile_context(),
            "trace-profile",
        )

        params = runtime.executed_calls[0]["params"]
        assert params["a"] == 10
        assert params["b"] == 20
        assert params["__metadata__"] == {
            "__system_instructions__": "Use the calculator sandbox procedure.",
            "__activity_profile__": "calculator.v1",
            "__prompt_template__": "calculator_activity_v1",
        }

    async def test_execute_uses_function_name(self) -> None:
        """execute() uses the configured function_name."""
        runtime = FakeWASMRuntime()
        provider = WASMProvider(
            _wasm_config(),
            runtime=runtime,
            function_name="compute",
        )
        await provider.execute(_request(), _context(), "trace-1")
        assert runtime.executed_calls[0]["function_name"] == "compute"

    async def test_execute_default_function_name(self) -> None:
        """Default function_name is 'execute'."""
        runtime = FakeWASMRuntime()
        provider = WASMProvider(_wasm_config(), runtime=runtime)
        await provider.execute(_request(), _context(), "trace-1")
        assert runtime.executed_calls[0]["function_name"] == "execute"

    async def test_execute_sandbox_config_from_provider_config(self) -> None:
        """Sandbox config is built from ProviderConfig fields."""
        runtime = FakeWASMRuntime()
        provider = WASMProvider(
            _wasm_config(sandbox_memory_mb=128, max_execution_ms=10000),
            runtime=runtime,
        )
        await provider.execute(_request(), _context(), "trace-1")
        sc = runtime.executed_calls[0]["sandbox_config"]
        assert sc.memory_limit_mb == 128
        assert sc.timeout_ms == 10000
        assert sc.allow_network is False
        assert sc.allow_filesystem is False

    async def test_execute_empty_output_returns_none_result(self) -> None:
        """Empty WASM output -> {"result": None}."""
        runtime = FakeWASMRuntime(
            result=WASMExecutionResult(success=True, output={}, execution_ms=5)
        )
        provider = WASMProvider(_wasm_config(), runtime=runtime)
        result = await provider.execute(_request(), _context(), "trace-1")
        assert result.success is True
        assert result.data == {"result": None}


# =========================================================================
# 3.3.3 -- WASMProvider: Execute (error paths)
# =========================================================================


class TestWASMProviderErrors:
    """Test WASMProvider error handling."""

    async def test_runtime_unavailable(self) -> None:
        """Runtime not available -> failure result."""
        runtime = FakeWASMRuntime(available=False)
        provider = WASMProvider(_wasm_config(), runtime=runtime)
        result = await provider.execute(_request(), _context(), "trace-1")
        assert result.success is False
        assert "not available" in result.error.message.lower()

    async def test_module_load_error(self) -> None:
        """Module load failure -> failure result."""
        runtime = FakeWASMRuntime(load_error=RuntimeError("bad wasm"))
        provider = WASMProvider(_wasm_config(), runtime=runtime)
        result = await provider.execute(_request(), _context(), "trace-1")
        assert result.success is False
        assert "load" in result.error.message.lower() or "wasm" in result.error.message.lower()

    async def test_module_not_loaded_flag(self) -> None:
        """Module handle with loaded=False -> failure result."""
        handle = WASMModuleHandle(module_path="x.wasm", module_id="x", loaded=False)
        runtime = FakeWASMRuntime(handle=handle)
        provider = WASMProvider(_wasm_config(), runtime=runtime)
        result = await provider.execute(_request(), _context(), "trace-1")
        assert result.success is False

    async def test_execution_error(self) -> None:
        """WASM execution failure -> failure result."""
        runtime = FakeWASMRuntime(exec_error=RuntimeError("segfault"))
        provider = WASMProvider(_wasm_config(), runtime=runtime)
        result = await provider.execute(_request(), _context(), "trace-1")
        assert result.success is False

    async def test_memory_error_in_exec(self) -> None:
        """Memory-related exception -> failure result."""
        runtime = FakeWASMRuntime(exec_error=RuntimeError("out of memory"))
        provider = WASMProvider(_wasm_config(), runtime=runtime)
        result = await provider.execute(_request(), _context(), "trace-1")
        assert result.success is False

    async def test_wasm_result_failure(self) -> None:
        """WASMExecutionResult.success=False -> failure_result."""
        runtime = FakeWASMRuntime(
            result=WASMExecutionResult(
                success=False,
                error_message="division by zero",
                execution_ms=2,
            )
        )
        provider = WASMProvider(_wasm_config(), runtime=runtime)
        result = await provider.execute(_request(), _context(), "trace-1")
        assert result.success is False
        assert "division by zero" in result.error.message

    async def test_wasm_result_memory_exceeded(self) -> None:
        """Result shows memory usage >= limit -> WASMMemoryLimitError."""
        runtime = FakeWASMRuntime(
            result=WASMExecutionResult(
                success=False,
                error_message="memory exceeded",
                memory_used_mb=128,
                execution_ms=2,
            )
        )
        provider = WASMProvider(_wasm_config(sandbox_memory_mb=64), runtime=runtime)
        result = await provider.execute(_request(), _context(), "trace-1")
        assert result.success is False


# =========================================================================
# 3.3.3 -- WASMProvider: Health check
# =========================================================================


class TestWASMProviderHealth:
    """Test WASMProvider.health_check()."""

    async def test_healthy_when_runtime_available_and_module_loaded(self) -> None:
        runtime = FakeWASMRuntime()
        provider = WASMProvider(_wasm_config(), runtime=runtime)
        health = await provider.health_check()
        assert health.status == ProviderStatus.HEALTHY.value

    async def test_unhealthy_when_runtime_unavailable(self) -> None:
        runtime = FakeWASMRuntime(available=False)
        provider = WASMProvider(_wasm_config(), runtime=runtime)
        health = await provider.health_check()
        assert health.status == ProviderStatus.UNHEALTHY.value

    async def test_unhealthy_when_module_not_loaded(self) -> None:
        handle = WASMModuleHandle(loaded=False)
        runtime = FakeWASMRuntime(handle=handle)
        provider = WASMProvider(_wasm_config(), runtime=runtime)
        health = await provider.health_check()
        assert health.status == ProviderStatus.UNHEALTHY.value

    async def test_unhealthy_on_load_exception(self) -> None:
        runtime = FakeWASMRuntime(load_error=RuntimeError("corrupt"))
        provider = WASMProvider(_wasm_config(), runtime=runtime)
        health = await provider.health_check()
        assert health.status == ProviderStatus.UNHEALTHY.value
        assert health.error is not None


# =========================================================================
# 3.3.3 -- WASM types
# =========================================================================


class TestWASMTypes:
    """Test WASM data types."""

    def test_module_handle_frozen(self) -> None:
        handle = WASMModuleHandle(module_path="a.wasm", module_id="a", loaded=True)
        with pytest.raises(AttributeError):
            handle.loaded = False  # type: ignore[misc]

    def test_sandbox_config_defaults(self) -> None:
        sc = WASMSandboxConfig()
        assert sc.memory_limit_mb == DEFAULT_SANDBOX_MEMORY_MB
        assert sc.timeout_ms == DEFAULT_MAX_EXECUTION_MS
        assert sc.allow_network is False
        assert sc.allow_filesystem is False

    def test_sandbox_config_frozen(self) -> None:
        sc = WASMSandboxConfig()
        with pytest.raises(AttributeError):
            sc.memory_limit_mb = 999  # type: ignore[misc]

    def test_execution_result_defaults(self) -> None:
        r = WASMExecutionResult()
        assert r.success is True
        assert r.output == {}
        assert r.error_message == ""
        assert r.memory_used_mb == 0
        assert r.execution_ms == 0

    def test_execution_result_frozen(self) -> None:
        r = WASMExecutionResult()
        with pytest.raises(AttributeError):
            r.success = False  # type: ignore[misc]


# =========================================================================
# 3.3.3 -- WASM exceptions
# =========================================================================


class TestWASMExceptions:
    """Test WASM exception hierarchy."""

    def test_wasm_provider_error_is_execution_error(self) -> None:
        err = WASMProviderError("p1", "boom")
        assert isinstance(err, ProviderExecutionError)
        assert isinstance(err, ProviderError)
        assert err.provider_id == "p1"
        assert err.error_code == "wasm_error"

    def test_module_load_error(self) -> None:
        err = WASMModuleLoadError("p1", "/path/to/bad.wasm", "invalid magic")
        assert isinstance(err, WASMProviderError)
        assert err.module_path == "/path/to/bad.wasm"
        assert "bad.wasm" in str(err)
        assert "invalid magic" in str(err)

    def test_execution_error(self) -> None:
        err = WASMExecutionError("p1", "segfault")
        assert isinstance(err, WASMProviderError)
        assert err.retriable is False

    def test_memory_limit_error(self) -> None:
        err = WASMMemoryLimitError("p1", 64, 128)
        assert isinstance(err, WASMProviderError)
        assert err.limit_mb == 64
        assert err.used_mb == 128
        assert "128MB" in str(err) and "64MB" in str(err)

    def test_wasm_errors_not_retriable_by_default(self) -> None:
        err = WASMProviderError("p1", "boom")
        assert err.retriable is False


# =========================================================================
# 3.3.3 -- WASMProvider: repr
# =========================================================================


class TestWASMProviderRepr:
    """Test WASMProvider __repr__."""

    def test_repr_includes_key_info(self) -> None:
        provider = WASMProvider(
            _wasm_config(),
            runtime=FakeWASMRuntime(),
            capability_names=["tool.execute.calc"],
        )
        r = repr(provider)
        assert "WASMProvider" in r
        assert "calc_wasm" in r


# =========================================================================
# 3.3.4 -- BridgeProvider: Protocol compliance
# =========================================================================


class TestBridgeProviderProtocol:
    """Verify BridgeProvider satisfies CapabilityProvider Protocol."""

    def test_bridge_provider_satisfies_protocol(self) -> None:
        bridge = FakeBridgePort()
        provider: CapabilityProvider = BridgeProvider(
            _bridge_config(),
            bridge=bridge,
            capability_names=["memory.store"],
        )
        assert hasattr(provider, "execute")
        assert hasattr(provider, "health_check")
        assert hasattr(provider, "capabilities")

    def test_bridge_provider_is_base_provider(self) -> None:
        bridge = FakeBridgePort()
        provider = BridgeProvider(_bridge_config(), bridge=bridge)
        assert isinstance(provider, BaseProvider)


# =========================================================================
# 3.3.4 -- BridgeProvider: Capabilities
# =========================================================================


class TestBridgeProviderCapabilities:
    """Test BridgeProvider.capabilities()."""

    def test_capabilities_returns_configured_list(self) -> None:
        caps = ["memory.store", "memory.recall", "checkpoint"]
        provider = BridgeProvider(
            _bridge_config(),
            bridge=FakeBridgePort(),
            capability_names=caps,
        )
        assert provider.capabilities() == caps

    def test_capabilities_default_empty(self) -> None:
        provider = BridgeProvider(_bridge_config(), bridge=FakeBridgePort())
        assert provider.capabilities() == []

    def test_capabilities_returns_copy(self) -> None:
        caps = ["memory.store"]
        provider = BridgeProvider(_bridge_config(), bridge=FakeBridgePort(), capability_names=caps)
        result = provider.capabilities()
        result.append("hacked")
        assert provider.capabilities() == ["memory.store"]


# =========================================================================
# 3.3.4 -- BridgeProvider: Execute (success paths)
# =========================================================================


class TestBridgeProviderExecute:
    """Test BridgeProvider._execute through BaseProvider.execute()."""

    async def test_execute_memory_store(self) -> None:
        """memory.store sends command through bridge."""
        bridge = FakeBridgePort()
        provider = BridgeProvider(
            _bridge_config(),
            bridge=bridge,
            capability_names=["memory.store"],
        )
        req = _request(capability_name="memory.store", params={"key": "val"})
        result = await provider.execute(req, _context(), "trace-1")
        assert result.success is True
        assert result.data == {"stored": True}
        assert len(bridge.sent_commands) == 1
        assert bridge.sent_commands[0]["operation"] == "memory.store"

    async def test_execute_memory_recall_uses_query(self) -> None:
        """memory.recall uses bridge.query() instead of send_command()."""
        bridge = FakeBridgePort()
        provider = BridgeProvider(
            _bridge_config(),
            bridge=bridge,
            capability_names=["memory.recall"],
        )
        req = _request(capability_name="memory.recall", params={"q": "hello"})
        result = await provider.execute(req, _context(), "trace-1")
        assert result.success is True
        assert len(bridge.queries) == 1
        assert bridge.queries[0]["operation"] == "memory.recall"
        assert len(bridge.sent_commands) == 0

    async def test_execute_checkpoint(self) -> None:
        """checkpoint is a command operation."""
        bridge = FakeBridgePort()
        provider = BridgeProvider(_bridge_config(), bridge=bridge, capability_names=["checkpoint"])
        req = _request(capability_name="checkpoint", params={"session": "s1"})
        result = await provider.execute(req, _context(), "trace-1")
        assert result.success is True
        assert bridge.sent_commands[0]["operation"] == "checkpoint"

    async def test_execute_ifl_home_device(self) -> None:
        """IFL tool.execute.home.* routes as command."""
        bridge = FakeBridgePort()
        provider = BridgeProvider(
            _bridge_config(),
            bridge=bridge,
            capability_names=["tool.execute.home.lights"],
        )
        req = _request(
            capability_name="tool.execute.home.lights",
            params={"action": "on"},
        )
        result = await provider.execute(req, _context(), "trace-1")
        assert result.success is True
        assert bridge.sent_commands[0]["operation"] == "tool.execute.home.lights"

    async def test_execute_ifl_device(self) -> None:
        """IFL tool.execute.device.* routes as command."""
        bridge = FakeBridgePort()
        provider = BridgeProvider(
            _bridge_config(),
            bridge=bridge,
            capability_names=["tool.execute.device.phone"],
        )
        req = _request(
            capability_name="tool.execute.device.phone",
            params={"call": "mom"},
        )
        result = await provider.execute(req, _context(), "trace-1")
        assert result.success is True

    async def test_execute_command_has_topic(self) -> None:
        """Command operation is stored correctly for direct ops."""
        bridge = FakeBridgePort()
        provider = BridgeProvider(
            _bridge_config(), bridge=bridge, capability_names=["memory.store"]
        )
        req = _request(capability_name="memory.store")
        await provider.execute(req, _context(), "trace-1")
        assert bridge.sent_commands[0]["operation"] == "memory.store"

    async def test_execute_ifl_command_topic_is_raw(self) -> None:
        """IFL operation is the raw capability name."""
        bridge = FakeBridgePort()
        provider = BridgeProvider(
            _bridge_config(),
            bridge=bridge,
            capability_names=["tool.execute.home.thermostat"],
        )
        req = _request(capability_name="tool.execute.home.thermostat")
        await provider.execute(req, _context(), "trace-1")
        assert bridge.sent_commands[0]["operation"] == "tool.execute.home.thermostat"


# =========================================================================
# 3.3.4 -- BridgeProvider: K0 offline fallback
# =========================================================================


class TestBridgeProviderOffline:
    """Test BridgeProvider offline (LOCAL COLD) fallback."""

    async def test_offline_with_fallback(self) -> None:
        """K0_OFFLINE + fallback_fn -> use fallback."""
        bridge = FakeBridgePort(health=K0HealthMode.K0_OFFLINE)

        async def fallback(req: CapabilityRequest, ctx: ExecutionContext) -> CapabilityResult:
            return CapabilityResult.success_result(
                request_id=req.request_id,
                data={"source": "local_cold"},
                provider_id="k0_memory_bridge",
                trace_id=req.trace_id,
            )

        provider = BridgeProvider(
            _bridge_config(),
            bridge=bridge,
            capability_names=["memory.recall"],
            fallback_fn=fallback,
        )
        req = _request(capability_name="memory.recall")
        result = await provider.execute(req, _context(), "trace-1")
        assert result.success is True
        assert result.data == {"source": "local_cold"}

    async def test_offline_without_fallback(self) -> None:
        """K0_OFFLINE + no fallback -> failure result."""
        bridge = FakeBridgePort(health=K0HealthMode.K0_OFFLINE)
        provider = BridgeProvider(
            _bridge_config(),
            bridge=bridge,
            capability_names=["memory.store"],
        )
        req = _request(capability_name="memory.store")
        result = await provider.execute(req, _context(), "trace-1")
        assert result.success is False
        assert (
            "unavailable" in result.error.message.lower()
            or "offline" in result.error.message.lower()
        )

    async def test_unavailable_with_fallback(self) -> None:
        """Bridge unavailable + fallback_fn -> use fallback."""
        bridge = FakeBridgePort(available=False)

        async def fallback(req: CapabilityRequest, ctx: ExecutionContext) -> CapabilityResult:
            return CapabilityResult.success_result(
                request_id=req.request_id,
                data={"source": "local_cold"},
                provider_id="k0_memory_bridge",
            )

        provider = BridgeProvider(
            _bridge_config(),
            bridge=bridge,
            fallback_fn=fallback,
        )
        req = _request(capability_name="memory.store")
        result = await provider.execute(req, _context(), "trace-1")
        assert result.success is True
        assert result.data["source"] == "local_cold"

    async def test_unavailable_without_fallback(self) -> None:
        """Bridge unavailable + no fallback -> failure result."""
        bridge = FakeBridgePort(available=False)
        provider = BridgeProvider(_bridge_config(), bridge=bridge)
        req = _request(capability_name="memory.store")
        result = await provider.execute(req, _context(), "trace-1")
        assert result.success is False

    async def test_bridge_error_falls_back(self) -> None:
        """Bridge send_command raises -> fallback if available."""
        bridge = FakeBridgePort(cmd_error=ConnectionError("network down"))

        async def fallback(req: CapabilityRequest, ctx: ExecutionContext) -> CapabilityResult:
            return CapabilityResult.success_result(
                request_id=req.request_id,
                data={"source": "local_cold"},
                provider_id="k0_memory_bridge",
            )

        provider = BridgeProvider(
            _bridge_config(),
            bridge=bridge,
            fallback_fn=fallback,
        )
        req = _request(capability_name="memory.store")
        result = await provider.execute(req, _context(), "trace-1")
        assert result.success is True

    async def test_bridge_error_no_fallback(self) -> None:
        """Bridge send_command raises + no fallback -> failure result."""
        bridge = FakeBridgePort(cmd_error=ConnectionError("network down"))
        provider = BridgeProvider(_bridge_config(), bridge=bridge)
        req = _request(capability_name="memory.store")
        result = await provider.execute(req, _context(), "trace-1")
        assert result.success is False

    async def test_fallback_failure(self) -> None:
        """Fallback function raises -> failure result."""
        bridge = FakeBridgePort(health=K0HealthMode.K0_OFFLINE)

        async def bad_fallback(req: CapabilityRequest, ctx: ExecutionContext) -> CapabilityResult:
            raise RuntimeError("local storage corrupt")

        provider = BridgeProvider(
            _bridge_config(),
            bridge=bridge,
            fallback_fn=bad_fallback,
        )
        req = _request(capability_name="memory.store")
        result = await provider.execute(req, _context(), "trace-1")
        assert result.success is False


# =========================================================================
# 3.3.4 -- BridgeProvider: K0 degraded mode
# =========================================================================


class TestBridgeProviderDegraded:
    """Test BridgeProvider with K0_DEGRADED health mode."""

    async def test_degraded_still_executes(self) -> None:
        """K0_DEGRADED still sends commands normally."""
        bridge = FakeBridgePort(health=K0HealthMode.K0_DEGRADED)
        provider = BridgeProvider(
            _bridge_config(), bridge=bridge, capability_names=["memory.store"]
        )
        req = _request(capability_name="memory.store")
        result = await provider.execute(req, _context(), "trace-1")
        assert result.success is True
        assert len(bridge.sent_commands) == 1


# =========================================================================
# 3.3.4 -- BridgeProvider: Response parsing
# =========================================================================


class TestBridgeProviderResponseParsing:
    """Test BridgeProvider response -> CapabilityResult conversion."""

    async def test_failed_response(self) -> None:
        """BridgeResponse.success=False -> failure_result."""
        bridge = FakeBridgePort(
            cmd_response=BridgeResponse(
                success=False,
                error_message="storage full",
                latency_ms=10,
            )
        )
        provider = BridgeProvider(
            _bridge_config(), bridge=bridge, capability_names=["memory.store"]
        )
        req = _request(capability_name="memory.store")
        result = await provider.execute(req, _context(), "trace-1")
        assert result.success is False
        assert "storage full" in result.error.message

    async def test_empty_response_data(self) -> None:
        """Empty response data -> {"result": None}."""
        bridge = FakeBridgePort(cmd_response=BridgeResponse(success=True, data={}, latency_ms=1))
        provider = BridgeProvider(_bridge_config(), bridge=bridge, capability_names=["checkpoint"])
        req = _request(capability_name="checkpoint")
        result = await provider.execute(req, _context(), "trace-1")
        assert result.success is True
        assert result.data == {"result": None}


# =========================================================================
# 3.3.4 -- BridgeProvider: Health check
# =========================================================================


class TestBridgeProviderHealth:
    """Test BridgeProvider.health_check()."""

    async def test_healthy_when_k0_full(self) -> None:
        bridge = FakeBridgePort(health=K0HealthMode.K0_FULL)
        provider = BridgeProvider(_bridge_config(), bridge=bridge)
        health = await provider.health_check()
        assert health.status == ProviderStatus.HEALTHY.value

    async def test_degraded_when_k0_degraded(self) -> None:
        bridge = FakeBridgePort(health=K0HealthMode.K0_DEGRADED)
        provider = BridgeProvider(_bridge_config(), bridge=bridge)
        health = await provider.health_check()
        assert health.status == ProviderStatus.DEGRADED.value

    async def test_unhealthy_when_k0_offline(self) -> None:
        bridge = FakeBridgePort(health=K0HealthMode.K0_OFFLINE)
        provider = BridgeProvider(_bridge_config(), bridge=bridge)
        health = await provider.health_check()
        assert health.status == ProviderStatus.UNHEALTHY.value

    async def test_unhealthy_when_bridge_unavailable(self) -> None:
        bridge = FakeBridgePort(available=False)
        provider = BridgeProvider(_bridge_config(), bridge=bridge)
        health = await provider.health_check()
        assert health.status == ProviderStatus.UNHEALTHY.value
        assert health.error is not None


# =========================================================================
# 3.3.4 -- Bridge operation classification
# =========================================================================


class TestBridgeOperationClassification:
    """Test _classify_operation helper."""

    def test_direct_bridge_operations(self) -> None:
        for op in BRIDGE_OPERATIONS:
            assert _classify_operation(op) == op

    def test_ifl_home_prefix(self) -> None:
        assert _classify_operation("tool.execute.home.lights") == "tool.execute.home.lights"

    def test_ifl_device_prefix(self) -> None:
        assert _classify_operation("tool.execute.device.phone") == "tool.execute.device.phone"

    def test_unknown_passthrough(self) -> None:
        assert _classify_operation("custom.operation") == "custom.operation"


# =========================================================================
# 3.3.4 -- Bridge types
# =========================================================================


class TestBridgeTypes:
    """Test Bridge data types."""

    def test_bridge_command_frozen(self) -> None:
        cmd = BridgeCommand(operation="memory.store", topic="bridge.memory.store")
        with pytest.raises(AttributeError):
            cmd.operation = "x"  # type: ignore[misc]

    def test_bridge_response_defaults(self) -> None:
        r = BridgeResponse()
        assert r.success is True
        assert r.data == {}
        assert r.error_message == ""
        assert r.k0_health == K0HealthMode.K0_FULL.value
        assert r.latency_ms == 0

    def test_bridge_response_frozen(self) -> None:
        r = BridgeResponse()
        with pytest.raises(AttributeError):
            r.success = False  # type: ignore[misc]

    def test_k0_health_mode_values(self) -> None:
        assert K0HealthMode.K0_FULL.value == "K0_FULL"
        assert K0HealthMode.K0_DEGRADED.value == "K0_DEGRADED"
        assert K0HealthMode.K0_OFFLINE.value == "K0_OFFLINE"


# =========================================================================
# 3.3.4 -- Bridge exceptions
# =========================================================================


class TestBridgeExceptions:
    """Test Bridge exception hierarchy."""

    def test_bridge_provider_error_is_execution_error(self) -> None:
        err = BridgeProviderError("p1", "bridge down")
        assert isinstance(err, ProviderExecutionError)
        assert isinstance(err, ProviderError)
        assert err.provider_id == "p1"
        assert err.error_code == "bridge_error"

    def test_bridge_unavailable_error(self) -> None:
        err = BridgeUnavailableError("p1", "no connection", k0_health="K0_OFFLINE")
        assert isinstance(err, BridgeProviderError)
        assert err.k0_health == "K0_OFFLINE"
        assert "unavailable" in str(err).lower()
        assert err.retriable is True

    def test_bridge_operation_error(self) -> None:
        err = BridgeOperationError("p1", "memory.store", "disk full")
        assert isinstance(err, BridgeProviderError)
        assert err.operation == "memory.store"
        assert "memory.store" in str(err)
        assert "disk full" in str(err)

    def test_bridge_errors_retriable_by_default(self) -> None:
        err = BridgeProviderError("p1", "boom")
        assert err.retriable is True


# =========================================================================
# 3.3.4 -- BridgeProvider: repr
# =========================================================================


class TestBridgeProviderRepr:
    """Test BridgeProvider __repr__."""

    def test_repr_includes_key_info(self) -> None:
        provider = BridgeProvider(
            _bridge_config(),
            bridge=FakeBridgePort(),
            capability_names=["memory.store"],
        )
        r = repr(provider)
        assert "BridgeProvider" in r
        assert "k0_memory_bridge" in r


# =========================================================================
# __init__.py exports validation
# =========================================================================


class TestProvidersPackageExports:
    """Verify __init__.py exports all 3.3.3 and 3.3.4 symbols."""

    def test_wasm_exports(self) -> None:
        """All WASM symbols are importable from providers package."""
        from k1.fabric.providers import (
            IWASMRuntime,
            WASMExecutionError,
            WASMExecutionResult,
            WASMMemoryLimitError,
            WASMModuleHandle,
            WASMModuleLoadError,
            WASMProvider,
            WASMProviderError,
            WASMSandboxConfig,
        )

        assert WASMProvider is not None
        assert IWASMRuntime is not None
        assert WASMModuleHandle is not None
        assert WASMSandboxConfig is not None
        assert WASMExecutionResult is not None
        assert WASMProviderError is not None
        assert WASMModuleLoadError is not None
        assert WASMExecutionError is not None
        assert WASMMemoryLimitError is not None

    def test_bridge_exports(self) -> None:
        """All Bridge symbols are importable from providers package."""
        from k1.fabric.providers import (
            BridgeCommand,
            BridgeOperationError,
            BridgeProvider,
            BridgeProviderError,
            BridgeResponse,
            BridgeUnavailableError,
            IBridgePort,
            K0HealthMode,
        )

        assert BridgeProvider is not None
        assert IBridgePort is not None
        assert BridgeCommand is not None
        assert BridgeResponse is not None
        assert K0HealthMode is not None
        assert BridgeProviderError is not None
        assert BridgeUnavailableError is not None
        assert BridgeOperationError is not None

    def test_all_list_count(self) -> None:
        """__all__ has 75 symbols (5 base + 8 MCP + 9 WASM + 8 Bridge + 14 Workflow + 7 Concierge + 7 Agent stub + 10 Agent 4.3 + 7 Pool/Delta 4.3.3/4.3.4)."""
        import k1.fabric.providers as pkg

        assert len(pkg.__all__) == 78

    def test_existing_exports_still_work(self) -> None:
        """Pre-existing exports (base + MCP) still importable."""
        from k1.fabric.providers import BaseProvider, CapabilityProvider, MCPProvider

        assert CapabilityProvider is not None
        assert BaseProvider is not None
        assert MCPProvider is not None
