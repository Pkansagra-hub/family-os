"""
Tests for Fabric adapter issues 5.2.4, 5.2.5, 5.2.6.

5.2.4 -- TestBridgeAdapter (in-memory K0 bridge stub)
5.2.5 -- TestModelGatewayAdapter + TestLLMHandle (canned LLM)
5.2.6 -- TestPromptSystemAdapter (static prompt templates)

Coverage:
  - Protocol satisfaction (structural subtyping)
  - Core operations (canned responses, resolve, compile, generate)
  - Setup helpers (add/remove/clear)
  - Capture / introspection
  - Edge cases (unavailable, missing, budget exhaustion)
  - Thread safety (concurrent operations)
  - Package exports via adapters __init__
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List

import pytest

# -- Adapters under test (import from package) -----------------------------
from k1.fabric.adapters.test_bridge import CapturedBridgeCall
from k1.fabric.adapters.test_bridge import TestBridgeAdapter as TestBridgePkg
from k1.fabric.adapters.test_model_gateway import TestLLMHandle as TestLLMHandlePkg
from k1.fabric.adapters.test_model_gateway import TestModelGatewayAdapter as TestGatewayPkg
from k1.fabric.adapters.test_prompt_system import TestPromptSystemAdapter as TestPromptPkg

# -- Port protocols (for isinstance checks) --------------------------------
from k1.fabric.ports.bridge_port import BridgeCommandResult, BridgeHealth, IBridgePort, IFLRoute
from k1.fabric.ports.model_gateway import ILLMHandle, IModelGatewayPort, ModelInfo
from k1.fabric.ports.prompt_system import IPromptSystemPort, PromptTemplate

# ===========================================================================
# 5.2.4 -- TestBridgeAdapter
# ===========================================================================


class TestBridgeAdapterProtocol:
    """Protocol satisfaction checks."""

    def test_satisfies_protocol(self) -> None:
        adapter = TestBridgePkg()
        assert isinstance(adapter, IBridgePort)

    def test_has_send_command(self) -> None:
        assert hasattr(TestBridgePkg, "send_command")

    def test_has_query(self) -> None:
        assert hasattr(TestBridgePkg, "query")

    def test_has_route_ifl(self) -> None:
        assert hasattr(TestBridgePkg, "route_ifl")

    def test_has_is_available(self) -> None:
        assert hasattr(TestBridgePkg, "is_available")

    def test_has_get_health(self) -> None:
        assert hasattr(TestBridgePkg, "get_health")

    def test_runtime_checkable(self) -> None:
        assert isinstance(TestBridgePkg(), IBridgePort)


class TestBridgeAdapterAvailability:
    """Availability and health."""

    def test_default_available(self) -> None:
        adapter = TestBridgePkg()
        assert adapter.is_available() is True

    def test_construct_unavailable(self) -> None:
        adapter = TestBridgePkg(available=False)
        assert adapter.is_available() is False

    def test_set_available_toggle(self) -> None:
        adapter = TestBridgePkg(available=True)
        adapter.set_available(False)
        assert adapter.is_available() is False
        adapter.set_available(True)
        assert adapter.is_available() is True

    def test_default_health_full(self) -> None:
        adapter = TestBridgePkg()
        h = adapter.get_health()
        assert h.available is True
        assert h.mode == "K0_FULL"

    def test_default_health_offline_when_unavailable(self) -> None:
        adapter = TestBridgePkg(available=False)
        h = adapter.get_health()
        assert h.available is False
        assert h.mode == "K0_OFFLINE"

    def test_set_health_custom(self) -> None:
        adapter = TestBridgePkg()
        custom = BridgeHealth(
            available=True,
            mode="K0_DEGRADED",
            latency_ms=42,
        )
        adapter.set_health(custom)
        assert adapter.get_health() is custom
        assert adapter.is_available() is True

    def test_set_available_false_updates_health(self) -> None:
        adapter = TestBridgePkg()
        adapter.set_available(False)
        h = adapter.get_health()
        assert h.available is False
        assert h.mode == "K0_OFFLINE"

    def test_set_available_true_updates_health(self) -> None:
        adapter = TestBridgePkg(available=False)
        adapter.set_available(True)
        h = adapter.get_health()
        assert h.available is True
        assert h.mode == "K0_FULL"


class TestBridgeAdapterSendCommand:
    """send_command tests."""

    @pytest.mark.asyncio
    async def test_default_returns_ok(self) -> None:
        adapter = TestBridgePkg()
        result = await adapter.send_command("memory.store", {"key": "v"})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_canned_response(self) -> None:
        adapter = TestBridgePkg()
        canned = BridgeCommandResult.ok(data={"stored": True})
        adapter.add_response("memory.store", canned)
        result = await adapter.send_command("memory.store", {"k": "v"})
        assert result.success is True
        assert result.data == {"stored": True}

    @pytest.mark.asyncio
    async def test_unavailable_returns_fail(self) -> None:
        adapter = TestBridgePkg(available=False)
        result = await adapter.send_command("memory.store", {})
        assert result.success is False
        assert result.error_code == "k0_offline"

    @pytest.mark.asyncio
    async def test_trace_id_echoed(self) -> None:
        adapter = TestBridgePkg()
        result = await adapter.send_command("op", {}, trace_id="t-123")
        assert result.trace_id == "t-123"

    @pytest.mark.asyncio
    async def test_handler_called(self) -> None:
        adapter = TestBridgePkg()

        def echo_handler(op: str, payload: Dict, trace_id: str) -> BridgeCommandResult:
            return BridgeCommandResult.ok(data={"echo": payload})

        adapter.add_handler("echo_op", echo_handler)
        result = await adapter.send_command("echo_op", {"x": 1})
        assert result.data == {"echo": {"x": 1}}

    @pytest.mark.asyncio
    async def test_handler_priority_over_canned(self) -> None:
        adapter = TestBridgePkg()
        adapter.add_response("op", BridgeCommandResult.ok(data={"canned": True}))

        def handler(op: str, payload: Dict, trace_id: str) -> BridgeCommandResult:
            return BridgeCommandResult.ok(data={"handler": True})

        adapter.add_handler("op", handler)
        result = await adapter.send_command("op", {})
        assert result.data == {"handler": True}


class TestBridgeAdapterQuery:
    """query tests."""

    @pytest.mark.asyncio
    async def test_default_returns_ok(self) -> None:
        adapter = TestBridgePkg()
        result = await adapter.query("memory.recall", {"filter": "recent"})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_canned_query_response(self) -> None:
        adapter = TestBridgePkg()
        canned = BridgeCommandResult.ok(data={"memories": ["a", "b"]})
        adapter.add_response("memory.recall", canned)
        result = await adapter.query("memory.recall", {})
        assert result.data == {"memories": ["a", "b"]}

    @pytest.mark.asyncio
    async def test_unavailable_returns_fail(self) -> None:
        adapter = TestBridgePkg(available=False)
        result = await adapter.query("memory.recall", {})
        assert result.success is False


class TestBridgeAdapterIFL:
    """route_ifl tests."""

    @pytest.mark.asyncio
    async def test_default_returns_ok(self) -> None:
        adapter = TestBridgePkg()
        route = IFLRoute.parse("tool.execute.home.lights")
        result = await adapter.route_ifl(route, {"action": "on"})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_canned_ifl_response(self) -> None:
        adapter = TestBridgePkg()
        canned = BridgeCommandResult.ok(data={"lights": "on"})
        adapter.add_ifl_response("tool.execute.home.lights", canned)
        route = IFLRoute.parse("tool.execute.home.lights")
        result = await adapter.route_ifl(route, {})
        assert result.data == {"lights": "on"}

    @pytest.mark.asyncio
    async def test_unavailable_ifl_returns_fail(self) -> None:
        adapter = TestBridgePkg(available=False)
        route = IFLRoute.parse("tool.execute.home.lights")
        result = await adapter.route_ifl(route, {})
        assert result.success is False
        assert result.error_code == "k0_offline"

    @pytest.mark.asyncio
    async def test_ifl_fallback_to_operation_resolve(self) -> None:
        adapter = TestBridgePkg()
        canned = BridgeCommandResult.ok(data={"fallback": True})
        adapter.add_response("tool.execute.home.lights", canned)
        route = IFLRoute.parse("tool.execute.home.lights")
        result = await adapter.route_ifl(route, {})
        assert result.data == {"fallback": True}


class TestBridgeAdapterCapture:
    """Capture and introspection."""

    @pytest.mark.asyncio
    async def test_captures_send_command(self) -> None:
        adapter = TestBridgePkg()
        await adapter.send_command("memory.store", {"k": "v"}, trace_id="t1")
        captured = adapter.get_captured()
        assert len(captured) == 1
        assert captured[0].method == "send_command"
        assert captured[0].operation == "memory.store"
        assert captured[0].trace_id == "t1"

    @pytest.mark.asyncio
    async def test_captures_query(self) -> None:
        adapter = TestBridgePkg()
        await adapter.query("memory.recall", {})
        assert adapter.query_count == 1

    @pytest.mark.asyncio
    async def test_captures_route_ifl(self) -> None:
        adapter = TestBridgePkg()
        route = IFLRoute.parse("tool.execute.home.lights")
        await adapter.route_ifl(route, {})
        assert adapter.ifl_count == 1

    @pytest.mark.asyncio
    async def test_call_count(self) -> None:
        adapter = TestBridgePkg()
        await adapter.send_command("op1", {})
        await adapter.query("op2", {})
        route = IFLRoute.parse("tool.execute.home.x")
        await adapter.route_ifl(route, {})
        assert adapter.call_count == 3
        assert adapter.command_count == 1
        assert adapter.query_count == 1
        assert adapter.ifl_count == 1

    @pytest.mark.asyncio
    async def test_drain(self) -> None:
        adapter = TestBridgePkg()
        await adapter.send_command("op", {})
        await adapter.query("op2", {})
        drained = adapter.drain()
        assert len(drained) == 2
        assert adapter.call_count == 0

    @pytest.mark.asyncio
    async def test_assert_called_pass(self) -> None:
        adapter = TestBridgePkg()
        await adapter.send_command("memory.store", {})
        adapter.assert_called("memory.store", 1)

    @pytest.mark.asyncio
    async def test_assert_called_fail(self) -> None:
        adapter = TestBridgePkg()
        with pytest.raises(AssertionError, match="memory.store"):
            adapter.assert_called("memory.store", 1)

    @pytest.mark.asyncio
    async def test_get_captured_filtered(self) -> None:
        adapter = TestBridgePkg()
        await adapter.send_command("op", {})
        await adapter.query("op", {})
        commands = adapter.get_captured("send_command")
        queries = adapter.get_captured("query")
        assert len(commands) == 1
        assert len(queries) == 1

    def test_clear_responses(self) -> None:
        adapter = TestBridgePkg()
        adapter.add_response("op", BridgeCommandResult.ok())
        adapter.add_ifl_response("addr", BridgeCommandResult.ok())
        adapter.add_handler("op2", lambda *a: BridgeCommandResult.ok())
        adapter.clear_responses()
        # Canned responses cleared; defaults still work

    def test_repr(self) -> None:
        adapter = TestBridgePkg()
        r = repr(adapter)
        assert "TestBridgeAdapter" in r
        assert "available=True" in r

    def test_captured_bridge_call_fields(self) -> None:
        c = CapturedBridgeCall(
            method="send_command",
            operation="memory.store",
            payload={"k": "v"},
            trace_id="t1",
            timestamp_ms=1000,
        )
        assert c.method == "send_command"
        assert c.payload == {"k": "v"}


class TestBridgeAdapterConcurrency:
    """Thread safety."""

    @pytest.mark.asyncio
    async def test_concurrent_commands(self) -> None:
        adapter = TestBridgePkg()
        loop = asyncio.get_event_loop()

        async def fire(i: int) -> BridgeCommandResult:
            return await adapter.send_command(f"op.{i}", {"i": i})

        results = await asyncio.gather(*(fire(i) for i in range(20)))
        assert all(r.success for r in results)
        assert adapter.call_count == 20


# ===========================================================================
# 5.2.5 -- TestModelGatewayAdapter + TestLLMHandle
# ===========================================================================


class TestLLMHandleBasic:
    """TestLLMHandle unit tests."""

    @pytest.mark.asyncio
    async def test_satisfies_protocol(self) -> None:
        handle = TestLLMHandlePkg()
        assert isinstance(handle, ILLMHandle)

    @pytest.mark.asyncio
    async def test_generate_returns_canned(self) -> None:
        handle = TestLLMHandlePkg(responses=["hello world"])
        result = await handle.generate("prompt", {})
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_round_robin_responses(self) -> None:
        handle = TestLLMHandlePkg(responses=["a", "b", "c"])
        results = []
        for _ in range(6):
            results.append(await handle.generate("p", {}))
        assert results == ["a", "b", "c", "a", "b", "c"]

    @pytest.mark.asyncio
    async def test_model_id_property(self) -> None:
        handle = TestLLMHandlePkg(model_id="gpt-4")
        assert handle.model_id == "gpt-4"

    @pytest.mark.asyncio
    async def test_budget_tokens_decrements(self) -> None:
        handle = TestLLMHandlePkg(budget_tokens=100)
        initial = handle.budget_tokens
        await handle.generate("test prompt", {})
        assert handle.budget_tokens < initial

    @pytest.mark.asyncio
    async def test_budget_exhausted_raises(self) -> None:
        handle = TestLLMHandlePkg(budget_tokens=0)
        with pytest.raises(RuntimeError, match="budget exhausted"):
            await handle.generate("p", {})

    @pytest.mark.asyncio
    async def test_error_after(self) -> None:
        handle = TestLLMHandlePkg(error_after=2, budget_tokens=10000)
        await handle.generate("p1", {})
        await handle.generate("p2", {})
        with pytest.raises(RuntimeError, match="error_after"):
            await handle.generate("p3", {})

    @pytest.mark.asyncio
    async def test_call_count(self) -> None:
        handle = TestLLMHandlePkg()
        await handle.generate("a", {})
        await handle.generate("b", {})
        assert handle.call_count == 2

    @pytest.mark.asyncio
    async def test_prompts_recorded(self) -> None:
        handle = TestLLMHandlePkg()
        await handle.generate("hello", {})
        await handle.generate("world", {})
        assert handle.prompts == ["hello", "world"]


class TestModelGatewayAdapterProtocol:
    """Protocol satisfaction."""

    def test_satisfies_protocol(self) -> None:
        adapter = TestGatewayPkg()
        assert isinstance(adapter, IModelGatewayPort)

    def test_has_create_handle(self) -> None:
        assert hasattr(TestGatewayPkg, "create_handle")

    def test_has_is_model_loaded(self) -> None:
        assert hasattr(TestGatewayPkg, "is_model_loaded")

    def test_has_list_models(self) -> None:
        assert hasattr(TestGatewayPkg, "list_models")

    def test_has_find_model(self) -> None:
        assert hasattr(TestGatewayPkg, "find_model")

    def test_runtime_checkable(self) -> None:
        assert isinstance(TestGatewayPkg(), IModelGatewayPort)


class TestModelGatewayAdapterCreateHandle:
    """create_handle tests."""

    def test_returns_handle(self) -> None:
        adapter = TestGatewayPkg()
        h = adapter.create_handle(1000)
        assert isinstance(h, TestLLMHandlePkg)
        assert isinstance(h, ILLMHandle)

    def test_budget_passed(self) -> None:
        adapter = TestGatewayPkg()
        h = adapter.create_handle(5000)
        assert h.budget_tokens == 5000

    def test_model_preference_used(self) -> None:
        adapter = TestGatewayPkg()
        adapter.add_model(ModelInfo(model_id="gpt-4", loaded=True))
        h = adapter.create_handle(1000, model_preference="gpt-4")
        assert h.model_id == "gpt-4"

    def test_capability_routing(self) -> None:
        adapter = TestGatewayPkg()
        adapter.add_model(
            ModelInfo(
                model_id="llama",
                capabilities=["CHAT"],
                loaded=True,
            )
        )
        adapter.add_model(
            ModelInfo(
                model_id="gpt-4",
                capabilities=["CHAT", "TOOL_CALL"],
                loaded=True,
            )
        )
        h = adapter.create_handle(1000, capabilities=["CHAT", "TOOL_CALL"])
        assert h.model_id == "gpt-4"

    def test_default_responses_applied(self) -> None:
        adapter = TestGatewayPkg(default_responses=["custom reply"])
        h = adapter.create_handle(1000)
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(h.generate("p", {}))
        finally:
            loop.close()
        assert result == "custom reply"

    def test_handle_tracked(self) -> None:
        adapter = TestGatewayPkg()
        adapter.create_handle(1000)
        adapter.create_handle(2000)
        assert adapter.handle_count == 2
        assert len(adapter.get_handles()) == 2

    def test_error_after_propagates(self) -> None:
        adapter = TestGatewayPkg(error_after=1)
        h = adapter.create_handle(10000)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(h.generate("p1", {}))
            with pytest.raises(RuntimeError):
                loop.run_until_complete(h.generate("p2", {}))
        finally:
            loop.close()


class TestModelGatewayAdapterCatalog:
    """Model catalog operations."""

    def test_add_and_list(self) -> None:
        adapter = TestGatewayPkg()
        m = ModelInfo(model_id="test", loaded=True)
        adapter.add_model(m)
        models = adapter.list_models()
        assert len(models) == 1
        assert models[0].model_id == "test"

    def test_remove_model(self) -> None:
        adapter = TestGatewayPkg()
        adapter.add_model(ModelInfo(model_id="test", loaded=True))
        adapter.remove_model("test")
        assert adapter.list_models() == []

    def test_remove_nonexistent(self) -> None:
        adapter = TestGatewayPkg()
        adapter.remove_model("nope")  # no error

    def test_is_model_loaded_true(self) -> None:
        adapter = TestGatewayPkg()
        adapter.add_model(ModelInfo(model_id="m", loaded=True))
        assert adapter.is_model_loaded("m") is True

    def test_is_model_loaded_false_not_loaded(self) -> None:
        adapter = TestGatewayPkg()
        adapter.add_model(ModelInfo(model_id="m", loaded=False))
        assert adapter.is_model_loaded("m") is False

    def test_is_model_loaded_false_missing(self) -> None:
        adapter = TestGatewayPkg()
        assert adapter.is_model_loaded("nope") is False

    def test_find_model_match(self) -> None:
        adapter = TestGatewayPkg()
        adapter.add_model(
            ModelInfo(
                model_id="full",
                capabilities=["CHAT", "TOOL_CALL", "STRUCTURED"],
                loaded=True,
            )
        )
        result = adapter.find_model(["CHAT", "TOOL_CALL"])
        assert result == "full"

    def test_find_model_no_match(self) -> None:
        adapter = TestGatewayPkg()
        adapter.add_model(ModelInfo(model_id="m", capabilities=["CHAT"], loaded=True))
        assert adapter.find_model(["VISION"]) is None

    def test_find_model_prefers_loaded(self) -> None:
        adapter = TestGatewayPkg()
        adapter.add_model(ModelInfo(model_id="unloaded", capabilities=["CHAT"], loaded=False))
        adapter.add_model(ModelInfo(model_id="loaded", capabilities=["CHAT"], loaded=True))
        assert adapter.find_model(["CHAT"]) == "loaded"

    def test_find_model_falls_back_to_unloaded(self) -> None:
        adapter = TestGatewayPkg()
        adapter.add_model(ModelInfo(model_id="unloaded", capabilities=["CHAT"], loaded=False))
        assert adapter.find_model(["CHAT"]) == "unloaded"

    def test_clear(self) -> None:
        adapter = TestGatewayPkg()
        adapter.add_model(ModelInfo(model_id="m", loaded=True))
        adapter.create_handle(1000)
        adapter.clear()
        assert adapter.list_models() == []
        assert adapter.handle_count == 0

    def test_set_default_responses(self) -> None:
        adapter = TestGatewayPkg()
        adapter.set_default_responses(["new reply"])
        h = adapter.create_handle(1000)
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(h.generate("p", {}))
        finally:
            loop.close()
        assert result == "new reply"

    def test_repr(self) -> None:
        adapter = TestGatewayPkg()
        r = repr(adapter)
        assert "TestModelGatewayAdapter" in r


class TestModelGatewayAdapterConcurrency:
    """Thread safety."""

    def test_concurrent_create_handle(self) -> None:
        adapter = TestGatewayPkg()
        errors: List[Exception] = []

        def create(i: int) -> None:
            try:
                adapter.create_handle(1000 + i)
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(create, range(20)))

        assert not errors
        assert adapter.handle_count == 20


# ===========================================================================
# 5.2.6 -- TestPromptSystemAdapter
# ===========================================================================


class TestPromptAdapterProtocol:
    """Protocol satisfaction."""

    def test_satisfies_protocol(self) -> None:
        adapter = TestPromptPkg()
        assert isinstance(adapter, IPromptSystemPort)

    def test_has_resolve(self) -> None:
        assert hasattr(TestPromptPkg, "resolve")

    def test_has_compile(self) -> None:
        assert hasattr(TestPromptPkg, "compile")

    def test_runtime_checkable(self) -> None:
        assert isinstance(TestPromptPkg(), IPromptSystemPort)


class TestPromptAdapterResolve:
    """resolve() tests."""

    def test_resolve_existing(self) -> None:
        adapter = TestPromptPkg()
        adapter.add_template("greet", "Hello {name}!", variables=["name"])
        result = adapter.resolve("greet")
        assert result is not None
        assert result.name == "greet"
        assert result.template == "Hello {name}!"
        assert result.variables == ["name"]

    def test_resolve_missing_returns_none(self) -> None:
        adapter = TestPromptPkg()
        assert adapter.resolve("nope") is None

    def test_resolve_increments_counter(self) -> None:
        adapter = TestPromptPkg()
        adapter.resolve("a")
        adapter.resolve("b")
        assert adapter.resolve_count == 2

    def test_resolve_returns_prompt_template(self) -> None:
        adapter = TestPromptPkg()
        adapter.add_template("t", "body")
        result = adapter.resolve("t")
        assert isinstance(result, PromptTemplate)

    def test_resolve_version(self) -> None:
        adapter = TestPromptPkg()
        adapter.add_template("t", "body", version="2.0")
        result = adapter.resolve("t")
        assert result is not None
        assert result.version == "2.0"

    def test_resolve_metadata(self) -> None:
        adapter = TestPromptPkg()
        adapter.add_template("t", "body", metadata={"author": "test"})
        result = adapter.resolve("t")
        assert result is not None
        assert result.metadata == {"author": "test"}

    def test_add_template_obj(self) -> None:
        adapter = TestPromptPkg()
        pt = PromptTemplate(
            name="custom",
            template="Hi {user}",
            variables=["user"],
        )
        adapter.add_template_obj(pt)
        assert adapter.resolve("custom") is pt

    def test_overwrite_template(self) -> None:
        adapter = TestPromptPkg()
        adapter.add_template("t", "v1")
        adapter.add_template("t", "v2")
        result = adapter.resolve("t")
        assert result is not None
        assert result.template == "v2"


class TestPromptAdapterCompile:
    """compile() tests."""

    def test_simple_substitution(self) -> None:
        adapter = TestPromptPkg()
        result = adapter.compile("Hello {name}!", {"name": "World"})
        assert result == "Hello World!"

    def test_multiple_variables(self) -> None:
        adapter = TestPromptPkg()
        result = adapter.compile(
            "{greeting} {name}! Age: {age}",
            {"greeting": "Hi", "name": "Alice", "age": 30},
        )
        assert result == "Hi Alice! Age: 30"

    def test_unresolved_placeholder_left_as_is(self) -> None:
        adapter = TestPromptPkg()
        result = adapter.compile("Hello {name}!", {})
        assert result == "Hello {name}!"

    def test_extra_variables_ignored(self) -> None:
        adapter = TestPromptPkg()
        result = adapter.compile("Hello!", {"extra": "ignored"})
        assert result == "Hello!"

    def test_compile_increments_counter(self) -> None:
        adapter = TestPromptPkg()
        adapter.compile("t", {})
        adapter.compile("t", {})
        assert adapter.compile_count == 2

    def test_compile_with_empty_template(self) -> None:
        adapter = TestPromptPkg()
        assert adapter.compile("", {"x": "y"}) == ""

    def test_compile_repeated_variable(self) -> None:
        adapter = TestPromptPkg()
        result = adapter.compile("{x} and {x}", {"x": "A"})
        assert result == "A and A"


class TestPromptAdapterHelpers:
    """Setup helpers."""

    def test_remove_existing(self) -> None:
        adapter = TestPromptPkg()
        adapter.add_template("t", "body")
        assert adapter.remove_template("t") is True
        assert adapter.resolve("t") is None  # resolve_count incremented

    def test_remove_nonexistent(self) -> None:
        adapter = TestPromptPkg()
        assert adapter.remove_template("nope") is False

    def test_clear(self) -> None:
        adapter = TestPromptPkg()
        adapter.add_template("a", "body")
        adapter.add_template("b", "body")
        adapter.resolve("a")
        adapter.compile("x", {})
        adapter.clear()
        assert adapter.template_count == 0
        assert adapter.resolve_count == 0
        assert adapter.compile_count == 0

    def test_template_count(self) -> None:
        adapter = TestPromptPkg()
        assert adapter.template_count == 0
        adapter.add_template("a", "body")
        adapter.add_template("b", "body")
        assert adapter.template_count == 2

    def test_has_template(self) -> None:
        adapter = TestPromptPkg()
        adapter.add_template("x", "body")
        assert adapter.has_template("x") is True
        assert adapter.has_template("y") is False

    def test_list_names(self) -> None:
        adapter = TestPromptPkg()
        adapter.add_template("b", "body")
        adapter.add_template("a", "body")
        names = adapter.list_names()
        assert set(names) == {"a", "b"}

    def test_repr(self) -> None:
        adapter = TestPromptPkg()
        r = repr(adapter)
        assert "TestPromptSystemAdapter" in r
        assert "templates=0" in r


class TestPromptAdapterConcurrency:
    """Thread safety."""

    def test_concurrent_resolve_compile(self) -> None:
        adapter = TestPromptPkg()
        for i in range(10):
            adapter.add_template(f"t{i}", f"Hello {{name}} #{i}", variables=["name"])

        errors: List[Exception] = []

        def worker(i: int) -> None:
            try:
                t = adapter.resolve(f"t{i % 10}")
                if t:
                    adapter.compile(t.template, {"name": f"user-{i}"})
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(worker, range(50)))

        assert not errors
        assert adapter.resolve_count == 50
        assert adapter.compile_count == 50


# ===========================================================================
# Package exports
# ===========================================================================


class TestAdaptersExports524_526:
    """Verify adapters package exports include 5.2.4-5.2.6."""

    def test_all_count(self) -> None:
        import k1.fabric.adapters as pkg

        assert len(pkg.__all__) >= 8  # 3 from 5.2.1-3 + 5 from 5.2.4-6

    def test_bridge_adapter_in_all(self) -> None:
        import k1.fabric.adapters as pkg

        assert "TestBridgeAdapter" in pkg.__all__
        assert "CapturedBridgeCall" in pkg.__all__

    def test_gateway_adapter_in_all(self) -> None:
        import k1.fabric.adapters as pkg

        assert "TestModelGatewayAdapter" in pkg.__all__
        assert "TestLLMHandle" in pkg.__all__

    def test_prompt_adapter_in_all(self) -> None:
        import k1.fabric.adapters as pkg

        assert "TestPromptSystemAdapter" in pkg.__all__

    def test_all_importable(self) -> None:
        import k1.fabric.adapters as pkg

        for name in pkg.__all__:
            obj = getattr(pkg, name)
            assert obj is not None, f"{name} resolved to None"

    def test_direct_import_bridge(self) -> None:
        from k1.fabric.adapters import TestBridgeAdapter

        assert TestBridgeAdapter is TestBridgePkg

    def test_direct_import_gateway(self) -> None:
        from k1.fabric.adapters import TestModelGatewayAdapter

        assert TestModelGatewayAdapter is TestGatewayPkg

    def test_direct_import_prompt(self) -> None:
        from k1.fabric.adapters import TestPromptSystemAdapter

        assert TestPromptSystemAdapter is TestPromptPkg

    def test_direct_import_prompt(self) -> None:
        from k1.fabric.adapters import TestPromptSystemAdapter

        assert TestPromptSystemAdapter is TestPromptPkg
