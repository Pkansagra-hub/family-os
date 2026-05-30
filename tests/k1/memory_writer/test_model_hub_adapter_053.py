"""Tests for ModelHubAdapter (E-0.5.3).

Covers I-0.5.3.1 + I-0.5.3.2:
  - ModelHubAdapter implements MW's IModelHubPort
  - chat() translates to K1 execute(HubRequest(CHAT))
  - Message dict -> Message object translation
  - System prompt extraction
  - Token budget mapping (MW-06: 2000)
    - concrete model_hint -> model_preference mapping
    - provider model_hint -> provider_preference mapping
  - Token usage extraction from ResponseMetadata
  - Priority.BACKGROUND for extraction work
  - trace_id propagation

References:
  - E-0.5.3: MemoryWriter->ModelHub Incompatible Port
  - k1/memory_writer/ports/model_hub_port.py (IModelHubPort)
  - k1/model_hub/ports/hub_port.py (IModelHubPort)
"""

from __future__ import annotations

from typing import AsyncIterator, Dict, List

from k1.memory_writer.adapters.model_hub_adapter import ModelHubAdapter
from k1.memory_writer.ports.model_hub_port import IModelHubPort
from k1.memory_writer.types import ChatResponse
from k1.model_hub.types import (
    CapabilityType,
    HubChunk,
    HubHealthReport,
    HubRequest,
    HubResponse,
)
from k1.model_hub.types import ModelInfo as HubModelInfo
from k1.model_hub.types import (
    Priority,
    ResponseMetadata,
    TokenUsage,
)

# ---------------------------------------------------------------------------
# Fake K1 IModelHubPort
# ---------------------------------------------------------------------------


class FakeK1Hub:
    """Minimal K1 IModelHubPort stub for adapter tests."""

    def __init__(
        self,
        *,
        response_text: str = "extracted memory atoms",
        prompt_tokens: int = 150,
        completion_tokens: int = 80,
        model_id: str = "gpt-4o-mini",
        latency_ms: int = 200,
    ) -> None:
        self._response_text = response_text
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self._model_id = model_id
        self._latency_ms = latency_ms
        self.execute_calls: List[HubRequest] = []

    async def execute(self, request: HubRequest) -> HubResponse:
        self.execute_calls.append(request)
        usage = TokenUsage(
            prompt_tokens=self._prompt_tokens,
            completion_tokens=self._completion_tokens,
            total_tokens=self._prompt_tokens + self._completion_tokens,
        )
        metadata = ResponseMetadata(
            request_id=request.request_id,
            model_id=self._model_id,
            provider_id="openai",
            usage=usage,
            cost_usd=0.001,
            latency_ms=self._latency_ms,
            cache_hit=False,
            capability=request.capability,
            trace_id=request.trace_id,
        )
        return HubResponse(result=self._response_text, metadata=metadata)

    async def stream_execute(self, request: HubRequest) -> AsyncIterator[HubChunk]:
        async def _gen() -> AsyncIterator[HubChunk]:
            yield HubChunk(content=self._response_text, done=True)

        return _gen()

    async def discover_capabilities(self) -> Dict[CapabilityType, List[str]]:
        return {}

    async def discover_models(self, capability: CapabilityType | None = None) -> List[HubModelInfo]:
        return []

    async def health(self) -> HubHealthReport:
        from k1.model_hub.types import HealthStatus

        return HubHealthReport(status=HealthStatus.HEALTHY)


# ===========================================================================
# Protocol conformance
# ===========================================================================


class TestModelHubAdapterProtocol:
    """ModelHubAdapter satisfies MW's IModelHubPort."""

    def test_isinstance_check(self) -> None:
        adapter = ModelHubAdapter(FakeK1Hub())
        assert isinstance(adapter, IModelHubPort)

    def test_has_chat_method(self) -> None:
        adapter = ModelHubAdapter(FakeK1Hub())
        assert callable(getattr(adapter, "chat", None))


# ===========================================================================
# Message translation
# ===========================================================================


class TestMessageTranslation:
    """chat() correctly translates Dict messages to K1 Message objects."""

    async def test_basic_messages(self) -> None:
        hub = FakeK1Hub()
        adapter = ModelHubAdapter(hub, trace_id="t-1")
        await adapter.chat(
            messages=[
                {"role": "user", "content": "extract memories"},
            ],
            budget_tokens=2000,
            model_hint="cheapest",
        )
        assert len(hub.execute_calls) == 1
        req = hub.execute_calls[0]
        payload = req.payload
        assert len(payload.messages) == 1
        assert payload.messages[0].role == "user"
        assert payload.messages[0].content == "extract memories"

    async def test_system_prompt_extracted(self) -> None:
        """System message is separated into system_prompt field."""
        hub = FakeK1Hub()
        adapter = ModelHubAdapter(hub, trace_id="t-2")
        await adapter.chat(
            messages=[
                {"role": "system", "content": "You are an extraction assistant."},
                {"role": "user", "content": "context data here"},
            ],
            budget_tokens=2000,
            model_hint="cheapest",
        )
        req = hub.execute_calls[0]
        payload = req.payload
        assert payload.system_prompt == "You are an extraction assistant."
        assert len(payload.messages) == 1
        assert payload.messages[0].role == "user"

    async def test_system_only_stays_in_messages(self) -> None:
        """If only a system message, it stays in messages (ChatPayload needs non-empty)."""
        hub = FakeK1Hub()
        adapter = ModelHubAdapter(hub, trace_id="t-3")
        await adapter.chat(
            messages=[{"role": "system", "content": "sys only"}],
            budget_tokens=2000,
            model_hint="cheapest",
        )
        req = hub.execute_calls[0]
        payload = req.payload
        assert payload.system_prompt is None
        assert len(payload.messages) == 1
        assert payload.messages[0].role == "system"

    async def test_multiple_messages(self) -> None:
        hub = FakeK1Hub()
        adapter = ModelHubAdapter(hub, trace_id="t-4")
        await adapter.chat(
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "q1"},
                {"role": "assistant", "content": "a1"},
                {"role": "user", "content": "q2"},
            ],
            budget_tokens=2000,
            model_hint="cheapest",
        )
        req = hub.execute_calls[0]
        payload = req.payload
        assert payload.system_prompt == "sys"
        assert len(payload.messages) == 3
        assert payload.messages[0].role == "user"
        assert payload.messages[1].role == "assistant"
        assert payload.messages[2].role == "user"


# ===========================================================================
# Request constraints
# ===========================================================================


class TestRequestConstraints:
    """Budget, priority, and routing hint are mapped correctly."""

    async def test_budget_mapped_to_max_tokens(self) -> None:
        hub = FakeK1Hub()
        adapter = ModelHubAdapter(hub, trace_id="t-5")
        await adapter.chat(
            messages=[{"role": "user", "content": "x"}],
            budget_tokens=2000,
            model_hint="cheapest",
        )
        req = hub.execute_calls[0]
        assert req.constraints.max_tokens == 2000

    async def test_priority_is_background(self) -> None:
        hub = FakeK1Hub()
        adapter = ModelHubAdapter(hub, trace_id="t-6")
        await adapter.chat(
            messages=[{"role": "user", "content": "x"}],
            budget_tokens=2000,
            model_hint="cheapest",
        )
        req = hub.execute_calls[0]
        assert req.constraints.priority == Priority.BACKGROUND

    async def test_timeout_is_60s(self) -> None:
        hub = FakeK1Hub()
        adapter = ModelHubAdapter(hub, trace_id="t-7")
        await adapter.chat(
            messages=[{"role": "user", "content": "x"}],
            budget_tokens=2000,
            model_hint="cheapest",
        )
        req = hub.execute_calls[0]
        assert req.constraints.timeout_ms == 60000

    async def test_model_hint_cheapest_no_preference(self) -> None:
        """'cheapest' hint does NOT set provider_preference (hub default routing)."""
        hub = FakeK1Hub()
        adapter = ModelHubAdapter(hub, trace_id="t-8")
        await adapter.chat(
            messages=[{"role": "user", "content": "x"}],
            budget_tokens=2000,
            model_hint="cheapest",
        )
        req = hub.execute_calls[0]
        assert req.constraints.provider_preference is None

    async def test_model_hint_specific_sets_preference(self) -> None:
        """Non-'cheapest' hint maps to provider_preference."""
        hub = FakeK1Hub()
        adapter = ModelHubAdapter(hub, trace_id="t-9")
        await adapter.chat(
            messages=[{"role": "user", "content": "x"}],
            budget_tokens=2000,
            model_hint="anthropic",
        )
        req = hub.execute_calls[0]
        assert req.constraints.provider_preference == "anthropic"

    async def test_model_hint_concrete_model_sets_model_preference(self) -> None:
        hub = FakeK1Hub()
        adapter = ModelHubAdapter(hub, trace_id="t-9b")
        await adapter.chat(
            messages=[{"role": "user", "content": "x"}],
            budget_tokens=2000,
            model_hint="gemini-2.5-flash",
        )
        req = hub.execute_calls[0]
        assert req.constraints.provider_preference is None
        assert req.constraints.model_preference is not None
        assert req.constraints.model_preference.preferred_model == "gemini-2.5-flash"

    async def test_consumer_id_default(self) -> None:
        hub = FakeK1Hub()
        adapter = ModelHubAdapter(hub, trace_id="t-10")
        await adapter.chat(
            messages=[{"role": "user", "content": "x"}],
            budget_tokens=2000,
            model_hint="cheapest",
        )
        req = hub.execute_calls[0]
        assert req.constraints.consumer_id == "memory_writer"

    async def test_consumer_id_custom(self) -> None:
        hub = FakeK1Hub()
        adapter = ModelHubAdapter(hub, trace_id="t-11", consumer_id="mw_test")
        await adapter.chat(
            messages=[{"role": "user", "content": "x"}],
            budget_tokens=2000,
            model_hint="cheapest",
        )
        req = hub.execute_calls[0]
        assert req.constraints.consumer_id == "mw_test"

    async def test_capability_is_chat(self) -> None:
        hub = FakeK1Hub()
        adapter = ModelHubAdapter(hub, trace_id="t-12")
        await adapter.chat(
            messages=[{"role": "user", "content": "x"}],
            budget_tokens=2000,
            model_hint="cheapest",
        )
        req = hub.execute_calls[0]
        assert req.capability == CapabilityType.CHAT


# ===========================================================================
# Trace ID
# ===========================================================================


class TestTraceId:
    """trace_id propagation and auto-generation."""

    async def test_trace_id_propagated(self) -> None:
        hub = FakeK1Hub()
        adapter = ModelHubAdapter(hub, trace_id="trace-abc-123")
        await adapter.chat(
            messages=[{"role": "user", "content": "x"}],
            budget_tokens=2000,
            model_hint="cheapest",
        )
        req = hub.execute_calls[0]
        assert req.trace_id == "trace-abc-123"

    async def test_trace_id_auto_generated(self) -> None:
        """If no trace_id provided, one is generated (non-empty)."""
        hub = FakeK1Hub()
        adapter = ModelHubAdapter(hub)  # no trace_id
        await adapter.chat(
            messages=[{"role": "user", "content": "x"}],
            budget_tokens=2000,
            model_hint="cheapest",
        )
        req = hub.execute_calls[0]
        assert req.trace_id  # non-empty
        assert len(req.trace_id) > 10  # UUID-ish


# ===========================================================================
# Response translation
# ===========================================================================


class TestResponseTranslation:
    """HubResponse -> ChatResponse extraction."""

    async def test_content_from_string_result(self) -> None:
        hub = FakeK1Hub(response_text='{"atoms": []}')
        adapter = ModelHubAdapter(hub, trace_id="t-20")
        resp = await adapter.chat(
            messages=[{"role": "user", "content": "x"}],
            budget_tokens=2000,
            model_hint="cheapest",
        )
        assert isinstance(resp, ChatResponse)
        assert resp.content == '{"atoms": []}'

    async def test_content_from_dict_result(self) -> None:
        """Dict result extracts 'content' key."""
        hub = FakeK1Hub()
        original_execute = hub.execute

        async def patched_execute(request: HubRequest) -> HubResponse:
            resp = await original_execute(request)
            return HubResponse(
                result={"content": "from dict", "extra": "ignored"},
                metadata=resp.metadata,
            )

        hub.execute = patched_execute  # type: ignore[assignment]
        adapter = ModelHubAdapter(hub, trace_id="t-21")
        resp = await adapter.chat(
            messages=[{"role": "user", "content": "x"}],
            budget_tokens=2000,
            model_hint="cheapest",
        )
        assert resp.content == "from dict"

    async def test_token_usage(self) -> None:
        hub = FakeK1Hub(prompt_tokens=150, completion_tokens=80)
        adapter = ModelHubAdapter(hub, trace_id="t-22")
        resp = await adapter.chat(
            messages=[{"role": "user", "content": "x"}],
            budget_tokens=2000,
            model_hint="cheapest",
        )
        assert resp.prompt_tokens == 150
        assert resp.completion_tokens == 80
        assert resp.total_tokens == 230

    async def test_model_id(self) -> None:
        hub = FakeK1Hub(model_id="gpt-4o-mini")
        adapter = ModelHubAdapter(hub, trace_id="t-23")
        resp = await adapter.chat(
            messages=[{"role": "user", "content": "x"}],
            budget_tokens=2000,
            model_hint="cheapest",
        )
        assert resp.model == "gpt-4o-mini"

    async def test_latency_ms_measured(self) -> None:
        hub = FakeK1Hub()
        adapter = ModelHubAdapter(hub, trace_id="t-24")
        resp = await adapter.chat(
            messages=[{"role": "user", "content": "x"}],
            budget_tokens=2000,
            model_hint="cheapest",
        )
        # Latency is measured locally, should be >= 0
        assert resp.latency_ms >= 0.0

    async def test_none_result(self) -> None:
        """None result returns empty string content."""
        hub = FakeK1Hub()
        original_execute = hub.execute

        async def patched_execute(request: HubRequest) -> HubResponse:
            resp = await original_execute(request)
            return HubResponse(result=None, metadata=resp.metadata)

        hub.execute = patched_execute  # type: ignore[assignment]
        adapter = ModelHubAdapter(hub, trace_id="t-25")
        resp = await adapter.chat(
            messages=[{"role": "user", "content": "x"}],
            budget_tokens=2000,
            model_hint="cheapest",
        )
        assert resp.content == ""


# ===========================================================================
# MW-06: Budget enforcement
# ===========================================================================


class TestBudgetEnforcement:
    """MW-06: budget_tokens maps to max_tokens correctly."""

    async def test_mw06_budget_2000(self) -> None:
        """Standard MW extraction budget of 2000 tokens."""
        hub = FakeK1Hub()
        adapter = ModelHubAdapter(hub, trace_id="t-30")
        await adapter.chat(
            messages=[{"role": "user", "content": "x"}],
            budget_tokens=2000,
            model_hint="cheapest",
        )
        req = hub.execute_calls[0]
        assert req.constraints.max_tokens == 2000

    async def test_custom_budget(self) -> None:
        """Non-standard budget still passes through."""
        hub = FakeK1Hub()
        adapter = ModelHubAdapter(hub, trace_id="t-31")
        await adapter.chat(
            messages=[{"role": "user", "content": "x"}],
            budget_tokens=500,
            model_hint="cheapest",
        )
        req = hub.execute_calls[0]
        assert req.constraints.max_tokens == 500


# ===========================================================================
# Integration round-trip
# ===========================================================================


class TestIntegrationRoundTrip:
    """End-to-end: adapter chat() -> hub execute() -> ChatResponse."""

    async def test_full_extraction_flow(self) -> None:
        """Simulate a real MW extraction call."""
        hub = FakeK1Hub(
            response_text='[{"type":"episodic","content":"went to park"}]',
            prompt_tokens=180,
            completion_tokens=45,
            model_id="gpt-4o-mini",
        )
        adapter = ModelHubAdapter(hub, trace_id="cog-trace-001")

        resp = await adapter.chat(
            messages=[
                {"role": "system", "content": "Extract memory atoms from context."},
                {"role": "user", "content": '{"turns":[...],"persona":"helpful"}'},
            ],
            budget_tokens=2000,
            model_hint="cheapest",
        )

        # Verify response
        assert resp.content == '[{"type":"episodic","content":"went to park"}]'
        assert resp.total_tokens == 225
        assert resp.prompt_tokens == 180
        assert resp.completion_tokens == 45
        assert resp.model == "gpt-4o-mini"
        assert resp.latency_ms >= 0.0

        # Verify request was correct
        req = hub.execute_calls[0]
        assert req.capability == CapabilityType.CHAT
        assert req.trace_id == "cog-trace-001"
        assert req.constraints.max_tokens == 2000
        assert req.constraints.priority == Priority.BACKGROUND
        assert req.constraints.consumer_id == "memory_writer"
        assert req.payload.system_prompt == "Extract memory atoms from context."
        assert len(req.payload.messages) == 1
        assert req.payload.messages[0].role == "user"

    async def test_multiple_calls(self) -> None:
        """Multiple chat() calls all pass through correctly."""
        hub = FakeK1Hub(response_text="result")
        adapter = ModelHubAdapter(hub, trace_id="multi-trace")

        r1 = await adapter.chat(
            messages=[{"role": "user", "content": "q1"}],
            budget_tokens=2000,
            model_hint="cheapest",
        )
        r2 = await adapter.chat(
            messages=[{"role": "user", "content": "q2"}],
            budget_tokens=2000,
            model_hint="cheapest",
        )

        assert r1.content == "result"
        assert r2.content == "result"
        assert len(hub.execute_calls) == 2
        assert hub.execute_calls[0].payload.messages[0].content == "q1"
        assert hub.execute_calls[1].payload.messages[0].content == "q2"
