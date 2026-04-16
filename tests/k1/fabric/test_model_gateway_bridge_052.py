"""Tests for ModelGatewayBridgeAdapter + LLMHandleBridge (E-0.5.2).

Covers I-0.5.2.1, I-0.5.2.2, I-0.5.2.3:
  - ModelGatewayBridgeAdapter implements IModelGatewayPort
  - LLMHandleBridge implements ILLMHandle
  - All 4 IModelGatewayPort methods work through ModelHub
  - Token budget enforcement in LLMHandleBridge
  - ModelInfo translation (Hub -> Fabric)

References:
  - E-0.5.2: Fabric->ModelHub Missing Bridge Adapter
  - k1/fabric/ports/model_gateway.py (IModelGatewayPort, ILLMHandle)
  - k1/model_hub/ports/hub_port.py (IModelHubPort)
"""

from __future__ import annotations

from typing import AsyncIterator, Dict, List, Optional

import pytest

from k1.fabric.adapters.model_gateway_bridge import LLMHandleBridge, ModelGatewayBridgeAdapter
from k1.fabric.ports.model_gateway import ILLMHandle, IModelGatewayPort, ModelInfo
from k1.model_hub.types import CapabilityType, HubChunk, HubHealthReport, HubRequest, HubResponse
from k1.model_hub.types import ModelInfo as HubModelInfo
from k1.model_hub.types import ResponseMetadata, TokenUsage

# ---------------------------------------------------------------------------
# Fake IModelHubPort for testing
# ---------------------------------------------------------------------------


class FakeModelHubPort:
    """Minimal IModelHubPort stub for bridge adapter tests."""

    def __init__(
        self,
        *,
        response_text: str = "hello from hub",
        tokens_used: int = 10,
        models: Optional[List[HubModelInfo]] = None,
    ) -> None:
        self._response_text = response_text
        self._tokens_used = tokens_used
        self._models = models or []
        self.execute_calls: List[HubRequest] = []

    async def execute(self, request: HubRequest) -> HubResponse:
        self.execute_calls.append(request)
        metadata = ResponseMetadata(
            request_id=request.request_id,
            model_id="fake-model",
            provider_id="fake-provider",
            usage=TokenUsage(
                prompt_tokens=5,
                completion_tokens=self._tokens_used,
                total_tokens=self._tokens_used,
            ),
            cost_usd=0.001,
            latency_ms=50,
            cache_hit=False,
            capability=request.capability,
            trace_id=request.trace_id,
        )
        return HubResponse(result=self._response_text, metadata=metadata)

    async def stream_execute(self, request: HubRequest) -> AsyncIterator[HubChunk]:
        async def _gen() -> AsyncIterator[HubChunk]:
            yield HubChunk(content=self._response_text, done=True)

        return _gen()  # pragma: no cover

    async def discover_capabilities(self) -> Dict[CapabilityType, List[str]]:
        caps: Dict[CapabilityType, List[str]] = {}
        for m in self._models:
            for cap in m.capabilities:
                caps.setdefault(cap, []).append(m.provider_id)
        return caps

    async def discover_models(self, capability: CapabilityType | None = None) -> List[HubModelInfo]:
        if capability is None:
            return list(self._models)
        return [m for m in self._models if capability in m.capabilities]

    async def health(self) -> HubHealthReport:
        from k1.model_hub.types import HealthStatus

        return HubHealthReport(status=HealthStatus.HEALTHY)


# ---------------------------------------------------------------------------
# Helper: sample Hub models
# ---------------------------------------------------------------------------


def _hub_model(
    model_id: str = "gpt-4o",
    provider_id: str = "openai",
    capabilities: Optional[List[CapabilityType]] = None,
    max_context: int = 128000,
) -> HubModelInfo:
    return HubModelInfo(
        id=model_id,
        provider_id=provider_id,
        capabilities=capabilities or [CapabilityType.CHAT, CapabilityType.TOOL_CALL],
        max_context=max_context,
    )


# ===========================================================================
# I-0.5.2.1: ModelGatewayBridgeAdapter
# ===========================================================================


class TestModelGatewayBridgeAdapterProtocol:
    """ModelGatewayBridgeAdapter satisfies IModelGatewayPort."""

    def test_isinstance_check(self) -> None:
        hub = FakeModelHubPort()
        adapter = ModelGatewayBridgeAdapter(hub)
        assert isinstance(adapter, IModelGatewayPort)

    def test_create_handle_returns_llm_handle(self) -> None:
        hub = FakeModelHubPort()
        adapter = ModelGatewayBridgeAdapter(hub)
        handle = adapter.create_handle(budget_tokens=5000)
        assert isinstance(handle, ILLMHandle)

    def test_create_handle_with_preference(self) -> None:
        hub = FakeModelHubPort()
        adapter = ModelGatewayBridgeAdapter(hub)
        handle = adapter.create_handle(budget_tokens=3000, model_preference="gpt-4o")
        assert handle.model_id == "gpt-4o"

    def test_create_handle_default_model_id(self) -> None:
        hub = FakeModelHubPort()
        adapter = ModelGatewayBridgeAdapter(hub)
        handle = adapter.create_handle(budget_tokens=1000)
        assert handle.model_id == "auto"

    def test_create_handle_budget(self) -> None:
        hub = FakeModelHubPort()
        adapter = ModelGatewayBridgeAdapter(hub)
        handle = adapter.create_handle(budget_tokens=2500)
        assert handle.budget_tokens == 2500


class TestModelGatewayBridgeIsModelLoaded:
    """is_model_loaded() via discover_models()."""

    async def test_model_found(self) -> None:
        hub = FakeModelHubPort(models=[_hub_model("gpt-4o")])
        adapter = ModelGatewayBridgeAdapter(hub)
        assert await adapter.is_model_loaded("gpt-4o") is True

    async def test_model_not_found(self) -> None:
        hub = FakeModelHubPort(models=[_hub_model("gpt-4o")])
        adapter = ModelGatewayBridgeAdapter(hub)
        assert await adapter.is_model_loaded("claude-3") is False

    async def test_empty_models(self) -> None:
        hub = FakeModelHubPort(models=[])
        adapter = ModelGatewayBridgeAdapter(hub)
        assert await adapter.is_model_loaded("any") is False


class TestModelGatewayBridgeListModels:
    """list_models() translates Hub ModelInfo -> Fabric ModelInfo."""

    async def test_empty(self) -> None:
        hub = FakeModelHubPort(models=[])
        adapter = ModelGatewayBridgeAdapter(hub)
        result = await adapter.list_models()
        assert result == []

    async def test_translation(self) -> None:
        hub = FakeModelHubPort(
            models=[
                _hub_model("gpt-4o", "openai", [CapabilityType.CHAT], 128000),
            ]
        )
        adapter = ModelGatewayBridgeAdapter(hub)
        result = await adapter.list_models()
        assert len(result) == 1
        m = result[0]
        assert isinstance(m, ModelInfo)
        assert m.model_id == "gpt-4o"
        assert m.capabilities == ["CHAT"]
        assert m.loaded is True
        assert m.max_tokens == 128000
        assert m.provider == "openai"

    async def test_multiple_models(self) -> None:
        hub = FakeModelHubPort(
            models=[
                _hub_model("gpt-4o"),
                _hub_model("claude-3", "anthropic"),
            ]
        )
        adapter = ModelGatewayBridgeAdapter(hub)
        result = await adapter.list_models()
        assert len(result) == 2
        ids = {m.model_id for m in result}
        assert ids == {"gpt-4o", "claude-3"}


class TestModelGatewayBridgeFindModel:
    """find_model() filters by capability."""

    async def test_find_by_single_cap(self) -> None:
        hub = FakeModelHubPort(
            models=[
                _hub_model("gpt-4o", capabilities=[CapabilityType.CHAT, CapabilityType.TOOL_CALL]),
            ]
        )
        adapter = ModelGatewayBridgeAdapter(hub)
        assert await adapter.find_model(["CHAT"]) == "gpt-4o"

    async def test_find_by_multiple_caps(self) -> None:
        hub = FakeModelHubPort(
            models=[
                _hub_model("gpt-4o", capabilities=[CapabilityType.CHAT, CapabilityType.TOOL_CALL]),
            ]
        )
        adapter = ModelGatewayBridgeAdapter(hub)
        assert await adapter.find_model(["CHAT", "TOOL_CALL"]) == "gpt-4o"

    async def test_no_match(self) -> None:
        hub = FakeModelHubPort(
            models=[
                _hub_model("gpt-4o", capabilities=[CapabilityType.CHAT]),
            ]
        )
        adapter = ModelGatewayBridgeAdapter(hub)
        assert await adapter.find_model(["VISION"]) is None

    async def test_empty_models(self) -> None:
        hub = FakeModelHubPort(models=[])
        adapter = ModelGatewayBridgeAdapter(hub)
        assert await adapter.find_model(["CHAT"]) is None


# ===========================================================================
# I-0.5.2.2: LLMHandleBridge
# ===========================================================================


class TestLLMHandleBridgeProtocol:
    """LLMHandleBridge satisfies ILLMHandle."""

    def test_isinstance_check(self) -> None:
        hub = FakeModelHubPort()
        handle = LLMHandleBridge(hub, model_id="test", budget_tokens=1000)
        assert isinstance(handle, ILLMHandle)

    def test_model_id_property(self) -> None:
        hub = FakeModelHubPort()
        handle = LLMHandleBridge(hub, model_id="gpt-4o", budget_tokens=1000)
        assert handle.model_id == "gpt-4o"

    def test_budget_tokens_property(self) -> None:
        hub = FakeModelHubPort()
        handle = LLMHandleBridge(hub, model_id="test", budget_tokens=5000)
        assert handle.budget_tokens == 5000


class TestLLMHandleBridgeGenerate:
    """generate() translates to HubRequest(CHAT) -> HubResponse."""

    async def test_returns_text(self) -> None:
        hub = FakeModelHubPort(response_text="Hello!")
        handle = LLMHandleBridge(hub, model_id="m", budget_tokens=10000)
        result = await handle.generate("Hi", {})
        assert result == "Hello!"

    async def test_sends_correct_hub_request(self) -> None:
        hub = FakeModelHubPort()
        handle = LLMHandleBridge(hub, model_id="m", budget_tokens=10000, trace_id="tr-1")
        await handle.generate("Hello", {"temperature": 0.5})
        assert len(hub.execute_calls) == 1
        req = hub.execute_calls[0]
        assert req.capability == CapabilityType.CHAT
        assert req.trace_id == "tr-1"
        assert req.constraints.temperature == 0.5

    async def test_budget_decrements(self) -> None:
        hub = FakeModelHubPort(tokens_used=100)
        handle = LLMHandleBridge(hub, model_id="m", budget_tokens=500)
        await handle.generate("Hello", {})
        assert handle.budget_tokens == 400

    async def test_budget_exhausted_raises(self) -> None:
        hub = FakeModelHubPort()
        handle = LLMHandleBridge(hub, model_id="m", budget_tokens=0)
        with pytest.raises(RuntimeError, match="budget exhausted"):
            await handle.generate("Hello", {})

    async def test_max_tokens_capped_by_budget(self) -> None:
        hub = FakeModelHubPort(tokens_used=5)
        handle = LLMHandleBridge(hub, model_id="m", budget_tokens=50)
        await handle.generate("Hello", {"max_tokens": 4096})
        req = hub.execute_calls[0]
        assert req.constraints.max_tokens == 50  # capped by budget

    async def test_dict_result_extraction(self) -> None:
        """HubResponse.result as dict extracts 'content' key."""
        hub = FakeModelHubPort()
        # Override to return dict result
        original_execute = hub.execute

        async def patched_execute(request: HubRequest) -> HubResponse:
            resp = await original_execute(request)
            return HubResponse(
                result={"content": "from dict"},
                metadata=resp.metadata,
            )

        hub.execute = patched_execute  # type: ignore[assignment]
        handle = LLMHandleBridge(hub, model_id="m", budget_tokens=10000)
        result = await handle.generate("Hi", {})
        assert result == "from dict"

    async def test_multiple_generate_calls(self) -> None:
        hub = FakeModelHubPort(response_text="reply", tokens_used=50)
        handle = LLMHandleBridge(hub, model_id="m", budget_tokens=200)
        r1 = await handle.generate("A", {})
        r2 = await handle.generate("B", {})
        assert r1 == "reply"
        assert r2 == "reply"
        assert handle.budget_tokens == 100
        assert len(hub.execute_calls) == 2


# ===========================================================================
# I-0.5.2.3: Integration -- Full round-trip
# ===========================================================================


class TestBridgeIntegrationRoundTrip:
    """End-to-end: create adapter -> create handle -> generate."""

    async def test_full_round_trip(self) -> None:
        hub = FakeModelHubPort(
            response_text="The weather is sunny",
            tokens_used=20,
            models=[_hub_model("gpt-4o")],
        )
        adapter = ModelGatewayBridgeAdapter(hub)

        # Verify model discovery
        models = await adapter.list_models()
        assert len(models) == 1
        assert models[0].model_id == "gpt-4o"

        # Verify model loaded
        assert await adapter.is_model_loaded("gpt-4o") is True
        assert await adapter.is_model_loaded("nonexistent") is False

        # Verify find_model
        found = await adapter.find_model(["CHAT"])
        assert found == "gpt-4o"

        # Create handle and generate
        handle = adapter.create_handle(
            budget_tokens=1000,
            model_preference="gpt-4o",
            trace_id="trace-abc",
        )
        assert handle.model_id == "gpt-4o"
        assert handle.budget_tokens == 1000

        result = await handle.generate("What's the weather?", {})
        assert result == "The weather is sunny"
        assert handle.budget_tokens == 980  # 1000 - 20

    async def test_budget_exhaustion_across_calls(self) -> None:
        hub = FakeModelHubPort(tokens_used=100)
        adapter = ModelGatewayBridgeAdapter(hub)
        handle = adapter.create_handle(budget_tokens=250)

        await handle.generate("Q1", {})
        assert handle.budget_tokens == 150

        await handle.generate("Q2", {})
        assert handle.budget_tokens == 50

        # Third call should still work (50 tokens left)
        await handle.generate("Q3", {})
        assert handle.budget_tokens == 0

        # Fourth call should fail (budget exhausted)
        with pytest.raises(RuntimeError, match="budget exhausted"):
            await handle.generate("Q4", {})
