"""
Tests for Epic 5.1 -- Port Interfaces (5.1.4, 5.1.5, 5.1.6).

Covers:
  5.1.4 IModelGatewayPort + ILLMHandle + ModelCapability + ModelInfo
  5.1.5 IPromptSystemPort + PromptTemplate
  5.1.6 IDeltaBusPort + DeltaPayload

Test structure:
  TestModelCapability -- Enum values, string subtype, membership
  TestModelInfo -- Frozen dataclass, has_capability, has_all, to_dict
  TestILLMHandleProtocol -- Protocol shape, runtime_checkable
  TestILLMHandleStructural -- Structural subtyping with fake
  TestIModelGatewayPortProtocol -- Protocol shape, runtime_checkable
  TestIModelGatewayPortStructural -- Structural subtyping with fake
  TestPromptTemplate -- Frozen dataclass, has_variable, to_dict
  TestIPromptSystemPortProtocol -- Protocol shape, runtime_checkable
  TestIPromptSystemPortStructural -- Structural subtyping with fake
  TestDeltaPayload -- Frozen dataclass, to_dict, from_args
  TestIDeltaBusPortProtocol -- Protocol shape, runtime_checkable
  TestIDeltaBusPortStructural -- Structural subtyping with fake
  TestPortsExports514_516 -- __all__ count and presence
  TestCrossInlineCompat -- Verify protocols match inline previews
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.ports import (
    DeltaPayload,
    IDeltaBusPort,
    ILLMHandle,
    IModelGatewayPort,
    IPromptSystemPort,
    ModelCapability,
    ModelInfo,
    PromptTemplate,
)
from k1.fabric.ports.delta_bus import DeltaPayload as DeltaPayloadDirect
from k1.fabric.ports.delta_bus import IDeltaBusPort as IDeltaBusPortDirect
from k1.fabric.ports.model_gateway import ILLMHandle as ILLMHandleDirect
from k1.fabric.ports.model_gateway import IModelGatewayPort as IModelGatewayPortDirect
from k1.fabric.ports.model_gateway import ModelCapability as ModelCapabilityDirect
from k1.fabric.ports.model_gateway import ModelInfo as ModelInfoDirect
from k1.fabric.ports.prompt_system import IPromptSystemPort as IPromptSystemPortDirect
from k1.fabric.ports.prompt_system import PromptTemplate as PromptTemplateDirect

# ---------------------------------------------------------------------------
# Fakes for structural subtyping verification
# ---------------------------------------------------------------------------


class FakeLLMHandle:
    """Satisfies ILLMHandle protocol structurally."""

    def __init__(self, model_id: str = "test-model", budget_tokens: int = 1000) -> None:
        self._model_id = model_id
        self._budget_tokens = budget_tokens
        self._calls: list[tuple[str, Dict[str, Any]]] = []

    async def generate(self, prompt: str, params: Dict[str, Any]) -> str:
        self._calls.append((prompt, params))
        self._budget_tokens -= len(prompt)
        return f"response-to-{prompt[:20]}"

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def budget_tokens(self) -> int:
        return self._budget_tokens


class FakeModelGateway:
    """Satisfies IModelGatewayPort protocol structurally."""

    def __init__(self) -> None:
        self._models: Dict[str, ModelInfo] = {}
        self._handles_created: list[tuple[int, Optional[str]]] = []

    def register_model(self, info: ModelInfo) -> None:
        self._models[info.model_id] = info

    def create_handle(
        self,
        budget_tokens: int,
        model_preference: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        trace_id: str = "",
    ) -> FakeLLMHandle:
        self._handles_created.append((budget_tokens, model_preference))
        mid = model_preference or "default-model"
        return FakeLLMHandle(model_id=mid, budget_tokens=budget_tokens)

    async def is_model_loaded(self, model_id: str) -> bool:
        info = self._models.get(model_id)
        return info.loaded if info else False

    async def list_models(self) -> List[ModelInfo]:
        return list(self._models.values())

    async def find_model(self, required_capabilities: List[str]) -> Optional[str]:
        for info in self._models.values():
            if info.has_all_capabilities(required_capabilities):
                return info.model_id
        return None


class FakePromptSystem:
    """Satisfies IPromptSystemPort protocol structurally."""

    def __init__(self) -> None:
        self._templates: Dict[str, PromptTemplate] = {}

    def add_template(self, t: PromptTemplate) -> None:
        self._templates[t.name] = t

    def resolve(self, template_name: str) -> Optional[PromptTemplate]:
        return self._templates.get(template_name)

    def compile(self, template: str, variables: Dict[str, Any]) -> str:
        result = template
        for k, v in variables.items():
            result = result.replace(f"{{{k}}}", str(v))
        return result


class FakeDeltaBus:
    """Satisfies IDeltaBusPort protocol structurally."""

    def __init__(self) -> None:
        self.deltas: list[DeltaPayload] = []

    def emit_delta(
        self,
        agent_id: str,
        delta_type: str,
        section: str,
        data: Dict[str, Any],
    ) -> None:
        self.deltas.append(
            DeltaPayload(
                agent_id=agent_id,
                delta_type=delta_type,
                section=section,
                data=data,
            )
        )


# ===========================================================================
# 5.1.4 -- ModelCapability
# ===========================================================================


class TestModelCapability:
    """ModelCapability enum tests."""

    def test_all_values_exist(self) -> None:
        expected = {"CHAT", "TOOL_CALL", "STRUCTURED", "EMBED", "VISION", "BATCH"}
        actual = {m.value for m in ModelCapability}
        assert actual == expected

    def test_is_str_subclass(self) -> None:
        assert isinstance(ModelCapability.CHAT, str)

    def test_string_comparison(self) -> None:
        assert ModelCapability.CHAT == "CHAT"
        assert ModelCapability.TOOL_CALL == "TOOL_CALL"

    def test_enum_identity(self) -> None:
        assert ModelCapability("CHAT") is ModelCapability.CHAT

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            ModelCapability("INVALID")

    def test_iteration(self) -> None:
        caps = list(ModelCapability)
        assert len(caps) == 6

    def test_name_matches_value(self) -> None:
        for cap in ModelCapability:
            assert cap.name == cap.value


# ===========================================================================
# 5.1.4 -- ModelInfo
# ===========================================================================


class TestModelInfo:
    """ModelInfo frozen dataclass tests."""

    def test_defaults(self) -> None:
        info = ModelInfo()
        assert info.model_id == ""
        assert info.capabilities == []
        assert info.loaded is False
        assert info.max_tokens == 0
        assert info.provider == ""

    def test_construction(self) -> None:
        info = ModelInfo(
            model_id="gpt-4",
            capabilities=["CHAT", "TOOL_CALL"],
            loaded=True,
            max_tokens=8192,
            provider="openai",
        )
        assert info.model_id == "gpt-4"
        assert info.loaded is True
        assert info.max_tokens == 8192

    def test_frozen(self) -> None:
        info = ModelInfo(model_id="m1")
        with pytest.raises(AttributeError):
            info.model_id = "m2"  # type: ignore[misc]

    def test_has_capability_true(self) -> None:
        info = ModelInfo(capabilities=["CHAT", "TOOL_CALL"])
        assert info.has_capability("CHAT") is True

    def test_has_capability_false(self) -> None:
        info = ModelInfo(capabilities=["CHAT"])
        assert info.has_capability("VISION") is False

    def test_has_all_capabilities_true(self) -> None:
        info = ModelInfo(capabilities=["CHAT", "TOOL_CALL", "EMBED"])
        assert info.has_all_capabilities(["CHAT", "EMBED"]) is True

    def test_has_all_capabilities_false(self) -> None:
        info = ModelInfo(capabilities=["CHAT"])
        assert info.has_all_capabilities(["CHAT", "VISION"]) is False

    def test_has_all_capabilities_empty(self) -> None:
        info = ModelInfo(capabilities=["CHAT"])
        assert info.has_all_capabilities([]) is True

    def test_to_dict(self) -> None:
        info = ModelInfo(
            model_id="m1",
            capabilities=["CHAT"],
            loaded=True,
            max_tokens=4096,
            provider="local",
        )
        d = info.to_dict()
        assert d["model_id"] == "m1"
        assert d["capabilities"] == ["CHAT"]
        assert d["loaded"] is True
        assert d["max_tokens"] == 4096
        assert d["provider"] == "local"

    def test_to_dict_return_type(self) -> None:
        info = ModelInfo()
        assert isinstance(info.to_dict(), dict)

    def test_equality(self) -> None:
        a = ModelInfo(model_id="m1", capabilities=["CHAT"])
        b = ModelInfo(model_id="m1", capabilities=["CHAT"])
        assert a == b

    def test_inequality(self) -> None:
        a = ModelInfo(model_id="m1")
        b = ModelInfo(model_id="m2")
        assert a != b


# ===========================================================================
# 5.1.4 -- ILLMHandle Protocol
# ===========================================================================


class TestILLMHandleProtocol:
    """ILLMHandle protocol shape and runtime_checkable tests."""

    def test_runtime_checkable(self) -> None:
        assert isinstance(FakeLLMHandle(), ILLMHandle)

    def test_has_generate_method(self) -> None:
        assert hasattr(ILLMHandle, "generate")

    def test_has_model_id_property(self) -> None:
        assert hasattr(ILLMHandle, "model_id")

    def test_has_budget_tokens_property(self) -> None:
        assert hasattr(ILLMHandle, "budget_tokens")

    def test_non_conforming_rejected(self) -> None:
        class Bad:
            pass

        assert not isinstance(Bad(), ILLMHandle)

    def test_partial_conforming_rejected(self) -> None:
        class Partial:
            async def generate(self, prompt: str, params: dict) -> str:
                return ""

        # Missing model_id and budget_tokens properties
        assert not isinstance(Partial(), ILLMHandle)

    def test_direct_import_same(self) -> None:
        assert ILLMHandle is ILLMHandleDirect


class TestILLMHandleStructural:
    """ILLMHandle structural subtyping with FakeLLMHandle."""

    def test_fake_satisfies_protocol(self) -> None:
        handle: ILLMHandle = FakeLLMHandle()
        assert isinstance(handle, ILLMHandle)

    async def test_generate_returns_string(self) -> None:
        handle = FakeLLMHandle()
        result = await handle.generate("hello", {"temperature": 0.7})
        assert isinstance(result, str)
        assert "hello" in result

    def test_model_id_property(self) -> None:
        handle = FakeLLMHandle(model_id="gpt-4")
        assert handle.model_id == "gpt-4"

    def test_budget_tokens_property(self) -> None:
        handle = FakeLLMHandle(budget_tokens=5000)
        assert handle.budget_tokens == 5000

    async def test_generate_decrements_budget(self) -> None:
        handle = FakeLLMHandle(budget_tokens=1000)
        await handle.generate("test", {})
        assert handle.budget_tokens < 1000

    async def test_generate_tracks_calls(self) -> None:
        handle = FakeLLMHandle()
        await handle.generate("prompt1", {"a": 1})
        await handle.generate("prompt2", {"b": 2})
        assert len(handle._calls) == 2
        assert handle._calls[0] == ("prompt1", {"a": 1})


# ===========================================================================
# 5.1.4 -- IModelGatewayPort Protocol
# ===========================================================================


class TestIModelGatewayPortProtocol:
    """IModelGatewayPort protocol shape and runtime_checkable tests."""

    def test_runtime_checkable(self) -> None:
        assert isinstance(FakeModelGateway(), IModelGatewayPort)

    def test_has_create_handle(self) -> None:
        assert hasattr(IModelGatewayPort, "create_handle")

    def test_has_is_model_loaded(self) -> None:
        assert hasattr(IModelGatewayPort, "is_model_loaded")

    def test_has_list_models(self) -> None:
        assert hasattr(IModelGatewayPort, "list_models")

    def test_has_find_model(self) -> None:
        assert hasattr(IModelGatewayPort, "find_model")

    def test_non_conforming_rejected(self) -> None:
        class Bad:
            pass

        assert not isinstance(Bad(), IModelGatewayPort)

    def test_direct_import_same(self) -> None:
        assert IModelGatewayPort is IModelGatewayPortDirect


class TestIModelGatewayPortStructural:
    """IModelGatewayPort structural subtyping with FakeModelGateway."""

    def test_fake_satisfies_protocol(self) -> None:
        gw: IModelGatewayPort = FakeModelGateway()
        assert isinstance(gw, IModelGatewayPort)

    def test_create_handle_returns_llm_handle(self) -> None:
        gw = FakeModelGateway()
        handle = gw.create_handle(budget_tokens=2000)
        assert isinstance(handle, ILLMHandle)

    def test_create_handle_with_preference(self) -> None:
        gw = FakeModelGateway()
        handle = gw.create_handle(budget_tokens=1000, model_preference="gpt-4")
        assert handle.model_id == "gpt-4"

    def test_create_handle_with_capabilities(self) -> None:
        gw = FakeModelGateway()
        handle = gw.create_handle(budget_tokens=500, capabilities=["CHAT", "TOOL_CALL"])
        assert handle.budget_tokens == 500

    def test_create_handle_with_trace_id(self) -> None:
        gw = FakeModelGateway()
        handle = gw.create_handle(budget_tokens=1000, trace_id="trace-abc")
        assert isinstance(handle, ILLMHandle)

    async def test_is_model_loaded_true(self) -> None:
        gw = FakeModelGateway()
        gw.register_model(ModelInfo(model_id="m1", loaded=True))
        assert await gw.is_model_loaded("m1") is True

    async def test_is_model_loaded_false(self) -> None:
        gw = FakeModelGateway()
        gw.register_model(ModelInfo(model_id="m1", loaded=False))
        assert await gw.is_model_loaded("m1") is False

    async def test_is_model_loaded_unknown(self) -> None:
        gw = FakeModelGateway()
        assert await gw.is_model_loaded("unknown") is False

    async def test_list_models_empty(self) -> None:
        gw = FakeModelGateway()
        assert await gw.list_models() == []

    async def test_list_models_with_entries(self) -> None:
        gw = FakeModelGateway()
        gw.register_model(ModelInfo(model_id="m1"))
        gw.register_model(ModelInfo(model_id="m2"))
        assert len(await gw.list_models()) == 2

    async def test_find_model_success(self) -> None:
        gw = FakeModelGateway()
        gw.register_model(ModelInfo(model_id="m1", capabilities=["CHAT", "TOOL_CALL"]))
        assert await gw.find_model(["CHAT"]) == "m1"

    async def test_find_model_all_caps(self) -> None:
        gw = FakeModelGateway()
        gw.register_model(ModelInfo(model_id="m1", capabilities=["CHAT", "TOOL_CALL"]))
        assert await gw.find_model(["CHAT", "TOOL_CALL"]) == "m1"

    async def test_find_model_none_when_missing(self) -> None:
        gw = FakeModelGateway()
        gw.register_model(ModelInfo(model_id="m1", capabilities=["CHAT"]))
        assert await gw.find_model(["VISION"]) is None

    async def test_find_model_empty_registry(self) -> None:
        gw = FakeModelGateway()
        assert await gw.find_model(["CHAT"]) is None

    def test_tracks_created_handles(self) -> None:
        gw = FakeModelGateway()
        gw.create_handle(1000, model_preference="gpt")
        gw.create_handle(2000)
        assert len(gw._handles_created) == 2


# ===========================================================================
# 5.1.4 -- Inline Compatibility (agent_provider.py)
# ===========================================================================


class TestModelGatewayInlineCompat:
    """Verify structural compatibility with agent_provider.py inline protocols."""

    def test_inline_create_handle_signature(self) -> None:
        """create_handle(budget_tokens, model_preference, capabilities, trace_id)."""
        gw = FakeModelGateway()
        # All four parameters from inline preview
        handle = gw.create_handle(
            budget_tokens=1000,
            model_preference=None,
            capabilities=None,
            trace_id="",
        )
        assert isinstance(handle, ILLMHandle)

    async def test_inline_is_model_loaded_signature(self) -> None:
        """is_model_loaded(model_id) -> bool."""
        gw = FakeModelGateway()
        result = await gw.is_model_loaded("any")
        assert isinstance(result, bool)

    async def test_inline_llm_handle_generate(self) -> None:
        """ILLMHandle.generate(prompt, params) -> str."""
        handle = FakeLLMHandle()
        result = await handle.generate("hello", {})
        assert isinstance(result, str)

    def test_inline_llm_handle_model_id(self) -> None:
        """ILLMHandle.model_id -> str property."""
        handle = FakeLLMHandle(model_id="test")
        assert isinstance(handle.model_id, str)

    def test_inline_llm_handle_budget_tokens(self) -> None:
        """ILLMHandle.budget_tokens -> int property."""
        handle = FakeLLMHandle(budget_tokens=999)
        assert isinstance(handle.budget_tokens, int)


# ===========================================================================
# 5.1.5 -- PromptTemplate
# ===========================================================================


class TestPromptTemplate:
    """PromptTemplate frozen dataclass tests."""

    def test_defaults(self) -> None:
        t = PromptTemplate()
        assert t.name == ""
        assert t.template == ""
        assert t.version == "1.0"
        assert t.variables == []
        assert t.metadata == {}

    def test_construction(self) -> None:
        t = PromptTemplate(
            name="greeting",
            template="Hello {name}!",
            version="2.0",
            variables=["name"],
            metadata={"author": "test"},
        )
        assert t.name == "greeting"
        assert t.template == "Hello {name}!"
        assert t.version == "2.0"

    def test_frozen(self) -> None:
        t = PromptTemplate(name="x")
        with pytest.raises(AttributeError):
            t.name = "y"  # type: ignore[misc]

    def test_has_variable_true(self) -> None:
        t = PromptTemplate(variables=["name", "age"])
        assert t.has_variable("name") is True

    def test_has_variable_false(self) -> None:
        t = PromptTemplate(variables=["name"])
        assert t.has_variable("age") is False

    def test_to_dict(self) -> None:
        t = PromptTemplate(
            name="greet",
            template="Hi {name}",
            version="1.0",
            variables=["name"],
            metadata={"x": 1},
        )
        d = t.to_dict()
        assert d["name"] == "greet"
        assert d["template"] == "Hi {name}"
        assert d["variables"] == ["name"]
        assert d["metadata"] == {"x": 1}

    def test_to_dict_return_type(self) -> None:
        t = PromptTemplate()
        assert isinstance(t.to_dict(), dict)

    def test_equality(self) -> None:
        a = PromptTemplate(name="x", template="y")
        b = PromptTemplate(name="x", template="y")
        assert a == b

    def test_inequality(self) -> None:
        a = PromptTemplate(name="x")
        b = PromptTemplate(name="y")
        assert a != b

    def test_to_dict_compatible_with_inline_resolve(self) -> None:
        """Inline IPromptSystemPort.resolve returns Optional[Dict].
        PromptTemplate.to_dict() produces that dict form."""
        t = PromptTemplate(name="sys", template="You are {role}")
        d = t.to_dict()
        assert isinstance(d, dict)
        assert "template" in d


# ===========================================================================
# 5.1.5 -- IPromptSystemPort Protocol
# ===========================================================================


class TestIPromptSystemPortProtocol:
    """IPromptSystemPort protocol shape and runtime_checkable tests."""

    def test_runtime_checkable(self) -> None:
        assert isinstance(FakePromptSystem(), IPromptSystemPort)

    def test_has_resolve(self) -> None:
        assert hasattr(IPromptSystemPort, "resolve")

    def test_has_compile(self) -> None:
        assert hasattr(IPromptSystemPort, "compile")

    def test_non_conforming_rejected(self) -> None:
        class Bad:
            pass

        assert not isinstance(Bad(), IPromptSystemPort)

    def test_partial_conforming_rejected(self) -> None:
        class Partial:
            def resolve(self, template_name: str) -> Optional[PromptTemplate]:
                return None

        assert not isinstance(Partial(), IPromptSystemPort)

    def test_direct_import_same(self) -> None:
        assert IPromptSystemPort is IPromptSystemPortDirect


class TestIPromptSystemPortStructural:
    """IPromptSystemPort structural subtyping with FakePromptSystem."""

    def test_fake_satisfies_protocol(self) -> None:
        ps: IPromptSystemPort = FakePromptSystem()
        assert isinstance(ps, IPromptSystemPort)

    def test_resolve_returns_template(self) -> None:
        ps = FakePromptSystem()
        t = PromptTemplate(name="greet", template="Hi {name}")
        ps.add_template(t)
        result = ps.resolve("greet")
        assert result is not None
        assert result.name == "greet"

    def test_resolve_returns_none_for_unknown(self) -> None:
        ps = FakePromptSystem()
        assert ps.resolve("nonexistent") is None

    def test_compile_substitutes_variables(self) -> None:
        ps = FakePromptSystem()
        result = ps.compile("Hello {name}, age {age}", {"name": "Alice", "age": 30})
        assert result == "Hello Alice, age 30"

    def test_compile_no_variables(self) -> None:
        ps = FakePromptSystem()
        result = ps.compile("Static text", {})
        assert result == "Static text"

    def test_compile_missing_variable_left_as_is(self) -> None:
        ps = FakePromptSystem()
        result = ps.compile("Hi {name}", {})
        assert result == "Hi {name}"


# ===========================================================================
# 5.1.5 -- Inline Compatibility (context_builder.py)
# ===========================================================================


class TestPromptSystemInlineCompat:
    """Verify structural compatibility with context_builder.py inline."""

    def test_inline_resolve_signature(self) -> None:
        """resolve(template_name) -> Optional[Dict] or Optional[PromptTemplate]."""
        ps = FakePromptSystem()
        result = ps.resolve("any")
        assert result is None or isinstance(result, PromptTemplate)

    def test_inline_compile_signature(self) -> None:
        """compile(template, variables) -> str."""
        ps = FakePromptSystem()
        result = ps.compile("text", {})
        assert isinstance(result, str)

    def test_resolve_result_convertible_to_dict(self) -> None:
        """Inline returns Dict; PromptTemplate.to_dict() provides that."""
        ps = FakePromptSystem()
        ps.add_template(PromptTemplate(name="test", template="hi"))
        result = ps.resolve("test")
        assert result is not None
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "template" in d


# ===========================================================================
# 5.1.6 -- DeltaPayload
# ===========================================================================


class TestDeltaPayload:
    """DeltaPayload frozen dataclass tests."""

    def test_defaults(self) -> None:
        p = DeltaPayload()
        assert p.agent_id == ""
        assert p.delta_type == ""
        assert p.section == ""
        assert p.data == {}
        assert p.trace_id == ""

    def test_construction(self) -> None:
        p = DeltaPayload(
            agent_id="agent-1",
            delta_type="plan_update",
            section="plan",
            data={"step": 3},
            trace_id="tr-001",
        )
        assert p.agent_id == "agent-1"
        assert p.delta_type == "plan_update"
        assert p.section == "plan"
        assert p.data == {"step": 3}
        assert p.trace_id == "tr-001"

    def test_frozen(self) -> None:
        p = DeltaPayload(agent_id="x")
        with pytest.raises(AttributeError):
            p.agent_id = "y"  # type: ignore[misc]

    def test_to_dict(self) -> None:
        p = DeltaPayload(
            agent_id="a1",
            delta_type="ctx",
            section="context",
            data={"k": "v"},
            trace_id="t1",
        )
        d = p.to_dict()
        assert d["agent_id"] == "a1"
        assert d["delta_type"] == "ctx"
        assert d["section"] == "context"
        assert d["data"] == {"k": "v"}
        assert d["trace_id"] == "t1"

    def test_to_dict_return_type(self) -> None:
        assert isinstance(DeltaPayload().to_dict(), dict)

    def test_from_args(self) -> None:
        p = DeltaPayload.from_args(
            agent_id="a1",
            delta_type="plan",
            section="plan",
            data={"x": 1},
            trace_id="t",
        )
        assert p.agent_id == "a1"
        assert p.delta_type == "plan"

    def test_from_args_matches_emit_signature(self) -> None:
        """from_args matches emit_delta(agent_id, delta_type, section, data)."""
        p = DeltaPayload.from_args("ag", "type", "sec", {"a": 1})
        assert p.agent_id == "ag"
        assert p.trace_id == ""  # default

    def test_from_args_with_trace(self) -> None:
        p = DeltaPayload.from_args("ag", "t", "s", {}, trace_id="trace-x")
        assert p.trace_id == "trace-x"

    def test_equality(self) -> None:
        a = DeltaPayload(agent_id="a", delta_type="t")
        b = DeltaPayload(agent_id="a", delta_type="t")
        assert a == b

    def test_inequality(self) -> None:
        a = DeltaPayload(agent_id="a")
        b = DeltaPayload(agent_id="b")
        assert a != b


# ===========================================================================
# 5.1.6 -- IDeltaBusPort Protocol
# ===========================================================================


class TestIDeltaBusPortProtocol:
    """IDeltaBusPort protocol shape and runtime_checkable tests."""

    def test_runtime_checkable(self) -> None:
        assert isinstance(FakeDeltaBus(), IDeltaBusPort)

    def test_has_emit_delta(self) -> None:
        assert hasattr(IDeltaBusPort, "emit_delta")

    def test_non_conforming_rejected(self) -> None:
        class Bad:
            pass

        assert not isinstance(Bad(), IDeltaBusPort)

    def test_direct_import_same(self) -> None:
        assert IDeltaBusPort is IDeltaBusPortDirect


class TestIDeltaBusPortStructural:
    """IDeltaBusPort structural subtyping with FakeDeltaBus."""

    def test_fake_satisfies_protocol(self) -> None:
        bus: IDeltaBusPort = FakeDeltaBus()
        assert isinstance(bus, IDeltaBusPort)

    def test_emit_delta_basic(self) -> None:
        bus = FakeDeltaBus()
        bus.emit_delta("agent-1", "plan_update", "plan", {"step": 1})
        assert len(bus.deltas) == 1
        assert bus.deltas[0].agent_id == "agent-1"

    def test_emit_delta_multiple(self) -> None:
        bus = FakeDeltaBus()
        bus.emit_delta("a1", "t1", "s1", {})
        bus.emit_delta("a2", "t2", "s2", {"x": 1})
        assert len(bus.deltas) == 2

    def test_emit_delta_returns_none(self) -> None:
        bus = FakeDeltaBus()
        result = bus.emit_delta("a", "t", "s", {})
        assert result is None

    def test_emit_delta_data_preserved(self) -> None:
        bus = FakeDeltaBus()
        data = {"nested": {"key": [1, 2, 3]}}
        bus.emit_delta("a", "t", "s", data)
        assert bus.deltas[0].data == data

    def test_emit_delta_empty_data(self) -> None:
        bus = FakeDeltaBus()
        bus.emit_delta("a", "t", "s", {})
        assert bus.deltas[0].data == {}


# ===========================================================================
# 5.1.6 -- Inline Compatibility (agent_provider.py)
# ===========================================================================


class TestDeltaBusInlineCompat:
    """Verify structural compatibility with agent_provider.py inline IDeltaBusPort."""

    def test_inline_emit_delta_signature(self) -> None:
        """emit_delta(agent_id, delta_type, section, data) -> None."""
        bus = FakeDeltaBus()
        result = bus.emit_delta("agent-1", "plan_update", "plan", {"step": 1})
        assert result is None

    def test_inline_four_positional_args(self) -> None:
        """Inline uses exactly 4 positional: agent_id, delta_type, section, data."""
        bus = FakeDeltaBus()
        bus.emit_delta("a", "b", "c", {"d": 1})
        p = bus.deltas[0]
        assert p.agent_id == "a"
        assert p.delta_type == "b"
        assert p.section == "c"
        assert p.data == {"d": 1}


# ===========================================================================
# Package-level exports
# ===========================================================================


class TestPortsExports514_516:
    """Verify __all__ exports for 5.1.4, 5.1.5, 5.1.6."""

    def test_model_gateway_in_all(self) -> None:
        from k1.fabric.ports import __all__

        for name in [
            "IModelGatewayPort",
            "ILLMHandle",
            "ModelCapability",
            "ModelInfo",
        ]:
            assert name in __all__, f"{name} missing from __all__"

    def test_prompt_system_in_all(self) -> None:
        from k1.fabric.ports import __all__

        assert "IPromptSystemPort" in __all__
        assert "PromptTemplate" in __all__

    def test_delta_bus_in_all(self) -> None:
        from k1.fabric.ports import __all__

        assert "IDeltaBusPort" in __all__
        assert "DeltaPayload" in __all__

    def test_total_exports_count(self) -> None:
        """8 (5.1.1-5.1.3) + 4 + 2 + 2 = 16 total."""
        from k1.fabric.ports import __all__

        assert len(__all__) == 16

    def test_all_importable(self) -> None:
        """Every name in __all__ is importable from the package."""
        import k1.fabric.ports as pkg
        from k1.fabric.ports import __all__

        for name in __all__:
            assert hasattr(pkg, name), f"{name} not importable from k1.fabric.ports"

    def test_direct_import_identity(self) -> None:
        """Direct module imports resolve to same objects as package imports."""
        assert ModelCapability is ModelCapabilityDirect
        assert ModelInfo is ModelInfoDirect
        assert PromptTemplate is PromptTemplateDirect
        assert DeltaPayload is DeltaPayloadDirect
