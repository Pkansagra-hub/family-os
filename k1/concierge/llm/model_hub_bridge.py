"""
ModelHubPOCBridge -- IModelHubPort → Existing POC Adapter
==========================================================

Bridge that implements IModelHubPort (K1 types) but delegates
to the existing GeminiConciergeAdapter / TestConciergeAdapter
(POC types). Translates HubRequest ↔ ConciergeModelRequest and
ConciergeModelResponse ↔ HubResponse using the M1 mapping table.

After M5 (Big Copy), the bridge swaps for the real Model Hub (M7).
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from k1.concierge.llm.types import (
    Capability,
    ConciergeModelRequest,
    ConciergeModelResponse,
    ModelMessage,
    StreamChunk,
    ThinkingLevel,
    ToolSchema,
)
from k1.concierge.llm.types import ToolCallResult as POCToolCallResult
from k1.model_hub.types import (
    CapabilityResult,
    CapabilityType,
    ChatPayload,
    ChatResult,
    HubChunk,
    HubHealthReport,
    HubRequest,
    HubResponse,
    ModelInfo,
    ModelTier,
    ProviderHealthStatus,
    ReasonPayload,
    ReasonResult,
    ResponseMetadata,
    StructuredOutputPayload,
    StructuredResult,
    TokenUsage,
    ToolCallPayload,
    ToolCallResultSet,
    ToolDefinition,
)
from k1.model_hub.types import FinishReason as HubFinishReason
from k1.model_hub.types import ToolCallResult as HubToolCallResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Capability mapping: K1 CapabilityType → POC Capability
# ---------------------------------------------------------------------------

_K1_TO_POC_CAPABILITY: dict[CapabilityType, str] = {
    CapabilityType.CHAT: Capability.CHAT,
    CapabilityType.TOOL_CALL: Capability.TOOL_CALL,
    CapabilityType.STRUCTURED: Capability.STRUCTURED,
    CapabilityType.REASON: Capability.REASON,
}

# POC Day 1 capabilities (what the bridge can handle)
_POC_CAPABILITIES: set[CapabilityType] = {
    CapabilityType.CHAT,
    CapabilityType.TOOL_CALL,
    CapabilityType.STRUCTURED,
    CapabilityType.REASON,
}

# FinishReason mapping: POC → K1
_POC_TO_HUB_FINISH: dict[str, HubFinishReason] = {
    "stop": HubFinishReason.STOP,
    "tool_calls": HubFinishReason.TOOL_CALLS,
    "length": HubFinishReason.LENGTH,
    "error": HubFinishReason.ERROR,
    "safety": HubFinishReason.SAFETY,
}

# ThinkingLevel mapping: ReasonPayload.reasoning_effort → POC ThinkingLevel
_EFFORT_TO_THINKING: dict[str, ThinkingLevel] = {
    "low": ThinkingLevel.LOW,
    "medium": ThinkingLevel.MEDIUM,
    "high": ThinkingLevel.HIGH,
}


class ModelHubPOCBridge:
    """Implements IModelHubPort by delegating to a POC adapter.

    Constructor accepts any object with generate() and generate_stream()
    methods (GeminiConciergeAdapter or TestConciergeAdapter).
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    # ------------------------------------------------------------------
    # IModelHubPort: execute
    # ------------------------------------------------------------------

    async def execute(self, request: HubRequest) -> HubResponse:
        poc_req = self._hub_to_poc_request(request)
        poc_resp = await self._inner.generate(poc_req)
        return self._poc_to_hub_response(poc_resp, request.capability, request.trace_id)

    # ------------------------------------------------------------------
    # IModelHubPort: stream_execute
    # ------------------------------------------------------------------

    async def stream_execute(self, request: HubRequest) -> AsyncIterator[HubChunk]:
        poc_req = self._hub_to_poc_request(request)
        async for chunk in self._inner.generate_stream(poc_req):
            yield self._translate_chunk(chunk, request.capability, request.trace_id)

    # ------------------------------------------------------------------
    # IModelHubPort: discover_capabilities
    # ------------------------------------------------------------------

    async def discover_capabilities(self) -> dict[CapabilityType, list[str]]:
        return {cap: ["poc-bridge"] for cap in _POC_CAPABILITIES}

    # ------------------------------------------------------------------
    # IModelHubPort: discover_models
    # ------------------------------------------------------------------

    async def discover_models(self, capability: CapabilityType | None = None) -> list[ModelInfo]:
        from k1.concierge.llm.model_selection import MODEL_SELECTION_TABLE

        seen: set[str] = set()
        models: list[ModelInfo] = []
        for (_cap, _actor), model_id in MODEL_SELECTION_TABLE.items():
            if model_id not in seen:
                seen.add(model_id)
                models.append(
                    ModelInfo(
                        id=model_id,
                        provider_id="google",
                        capabilities=list(_POC_CAPABILITIES),
                        tier=ModelTier.STANDARD,
                    )
                )
        return models

    # ------------------------------------------------------------------
    # IModelHubPort: health
    # ------------------------------------------------------------------

    async def health(self) -> HubHealthReport:
        return HubHealthReport(
            status="HEALTHY",
            providers=[
                ProviderHealthStatus(
                    provider_id="poc-bridge",
                    status="HEALTHY",
                )
            ],
        )

    # ------------------------------------------------------------------
    # Translation: HubRequest → ConciergeModelRequest
    # ------------------------------------------------------------------

    def _hub_to_poc_request(self, hub_req: HubRequest) -> ConciergeModelRequest:
        payload = hub_req.payload
        constraints = hub_req.constraints

        # Capability
        poc_capability = _K1_TO_POC_CAPABILITY.get(hub_req.capability, Capability.CHAT)

        # Messages: K1 Message → POC ModelMessage
        messages: list[ModelMessage] = []
        system_prompt: str = ""
        tools: list[ToolSchema] | None = None
        tool_choice: str = "auto"
        response_schema: dict[str, Any] | None = None
        thinking: ThinkingLevel | None = None

        if isinstance(payload, ChatPayload):
            system_prompt = payload.system_prompt or ""
            messages = [self._k1_msg_to_poc(m) for m in payload.messages]

        elif isinstance(payload, ToolCallPayload):
            messages = [self._k1_msg_to_poc(m) for m in payload.messages]
            tools = [self._k1_tool_to_poc(t) for t in payload.tools]
            tool_choice = payload.tool_choice

        elif isinstance(payload, StructuredOutputPayload):
            messages = [self._k1_msg_to_poc(m) for m in payload.messages]
            response_schema = payload.output_schema

        elif isinstance(payload, ReasonPayload):
            messages = [self._k1_msg_to_poc(m) for m in payload.messages]
            thinking = _EFFORT_TO_THINKING.get(payload.reasoning_effort, ThinkingLevel.MEDIUM)

        # Consumer ID → actor (parse "concierge.front" → "front")
        actor = constraints.consumer_id
        if "." in actor:
            actor = actor.rsplit(".", 1)[-1]

        # Model hint from preference
        model_hint: str | None = None
        if constraints.model_preference:
            model_hint = constraints.model_preference.preferred_model

        return ConciergeModelRequest(
            capability=poc_capability,
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            response_schema=response_schema,
            max_tokens=constraints.max_tokens,
            timeout_ms=constraints.timeout_ms,
            temperature=constraints.temperature,
            thinking=thinking,
            trace_id=hub_req.trace_id,
            actor=actor,
            scenario="",  # POC scenario derived from context, not from hub
            model_hint=model_hint,
        )

    # ------------------------------------------------------------------
    # Translation: ConciergeModelResponse → HubResponse
    # ------------------------------------------------------------------

    def _poc_to_hub_response(
        self,
        poc_resp: ConciergeModelResponse,
        capability: CapabilityType,
        trace_id: str,
    ) -> HubResponse:
        result = self._build_capability_result(poc_resp, capability)
        finish = _POC_TO_HUB_FINISH.get(poc_resp.finish_reason, HubFinishReason.STOP)

        metadata = ResponseMetadata(
            request_id=trace_id or "bridge-req",
            model_id=poc_resp.model_id,
            provider_id="poc-bridge",
            usage=TokenUsage(
                prompt_tokens=poc_resp.tokens_in,
                completion_tokens=poc_resp.tokens_out,
                total_tokens=poc_resp.tokens_in + poc_resp.tokens_out + poc_resp.tokens_thoughts,
            ),
            cost_usd=0.0,
            latency_ms=poc_resp.latency_ms,
            cache_hit=False,
            capability=capability,
            trace_id=trace_id,
            finish_reason=finish,
        )
        return HubResponse(result=result, metadata=metadata)

    def _build_capability_result(
        self, poc_resp: ConciergeModelResponse, capability: CapabilityType
    ) -> CapabilityResult:
        if capability == CapabilityType.TOOL_CALL and poc_resp.has_tool_calls:
            import json

            return ToolCallResultSet(
                text=poc_resp.text,
                tool_calls=[
                    HubToolCallResult(
                        id=tc.id,
                        name=tc.name,
                        arguments=(
                            json.dumps(tc.arguments)
                            if isinstance(tc.arguments, dict)
                            else str(tc.arguments)
                        ),
                    )
                    for tc in poc_resp.tool_calls
                ],
            )
        if capability == CapabilityType.STRUCTURED and poc_resp.has_json:
            return StructuredResult(json_output=poc_resp.json_output or {})
        if capability == CapabilityType.REASON:
            return ReasonResult(text=poc_resp.text, thinking=poc_resp.thought_text)
        return ChatResult(text=poc_resp.text)

    # ------------------------------------------------------------------
    # Translation: StreamChunk → HubChunk
    # ------------------------------------------------------------------

    def _translate_chunk(
        self,
        chunk: StreamChunk,
        capability: CapabilityType,
        trace_id: str,
    ) -> HubChunk:
        import json

        if chunk.chunk_type == "done" and chunk.response:
            hub_resp = self._poc_to_hub_response(chunk.response, capability, trace_id)
            return HubChunk(content="", done=True, metadata=hub_resp.metadata)

        if chunk.chunk_type == "tool_call_delta" and chunk.tool_call_partial:
            tc = chunk.tool_call_partial
            return HubChunk(
                tool_calls=[
                    HubToolCallResult(
                        id=tc.id,
                        name=tc.name,
                        arguments=(
                            json.dumps(tc.arguments)
                            if isinstance(tc.arguments, dict)
                            else str(tc.arguments)
                        ),
                    )
                ],
            )

        return HubChunk(content=chunk.text or "")

    # ------------------------------------------------------------------
    # Helpers: K1 → POC type conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _k1_msg_to_poc(msg: Any) -> ModelMessage:
        """Convert K1 Message → POC ModelMessage."""
        tool_calls = None
        if msg.tool_calls:
            tool_calls = [
                POCToolCallResult(id=tc.id, name=tc.name, arguments=tc.arguments)
                for tc in msg.tool_calls
            ]
        return ModelMessage(
            role=msg.role,
            content=msg.content,
            tool_call_id=msg.tool_call_id,
            name=msg.name,
            tool_calls=tool_calls,
        )

    @staticmethod
    def _k1_tool_to_poc(tool: ToolDefinition) -> ToolSchema:
        """Convert K1 ToolDefinition → POC ToolSchema."""
        return ToolSchema(
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters,
        )
