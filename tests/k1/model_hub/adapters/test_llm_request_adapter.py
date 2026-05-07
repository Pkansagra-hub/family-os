"""TestLLMRequestAdapter -- test adapter for IModelHubPort [6.1.1].

Deterministic IModelHubPort implementation that injects requests and
captures responses for post-test assertion.

NO real network calls. NO external dependencies.
"""

from __future__ import annotations

from typing import AsyncIterator, Dict, List

from k1.model_hub.types import (
    CapabilityType,
    HealthStatus,
    HubChunk,
    HubHealthReport,
    HubRequest,
    HubResponse,
    ModelInfo,
    ResponseMetadata,
    TokenUsage,
)


class TestLLMRequestAdapter:
    """Deterministic IModelHubPort for testing.

    Configurable:
      - response_text: Default text in HubResponse (default "test-reply").
      - model_id: Model ID in response metadata.
      - provider_id: Provider ID in response metadata.

    Capture:
      - execute_requests: All HubRequests received via execute().
      - stream_requests: All HubRequests received via stream_execute().
      - responses: All HubResponses returned.

    isinstance(adapter, IModelHubPort) == True.
    """

    def __init__(
        self,
        *,
        response_text: str = "test-reply",
        model_id: str = "test-model",
        provider_id: str = "test-provider",
    ) -> None:
        self._response_text = response_text
        self._model_id = model_id
        self._provider_id = provider_id
        self._execute_requests: List[HubRequest] = []
        self._stream_requests: List[HubRequest] = []
        self._responses: List[HubResponse] = []

    async def execute(self, request: HubRequest) -> HubResponse:
        """Return deterministic HubResponse, capture request."""
        self._execute_requests.append(request)
        metadata = ResponseMetadata(
            request_id=request.request_id,
            model_id=self._model_id,
            provider_id=self._provider_id,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            cost_usd=0.001,
            latency_ms=50,
            cache_hit=False,
            capability=request.capability,
            trace_id=request.trace_id,
        )
        response = HubResponse(result=self._response_text, metadata=metadata)
        self._responses.append(response)
        return response

    async def stream_execute(self, request: HubRequest) -> AsyncIterator[HubChunk]:
        """Yield deterministic chunks, capture request."""
        self._stream_requests.append(request)
        yield HubChunk(content="chunk-1 ", done=False)
        metadata = ResponseMetadata(
            request_id=request.request_id,
            model_id=self._model_id,
            provider_id=self._provider_id,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            cost_usd=0.001,
            latency_ms=50,
            cache_hit=False,
            capability=request.capability,
            trace_id=request.trace_id,
        )
        yield HubChunk(content="chunk-2", done=True, metadata=metadata)

    async def discover_capabilities(self) -> Dict[CapabilityType, List[str]]:
        """Return empty capabilities map."""
        return {}

    async def discover_models(self, capability: CapabilityType | None = None) -> List[ModelInfo]:
        """Return empty models list."""
        return []

    async def health(self) -> HubHealthReport:
        """Return healthy status."""
        return HubHealthReport(status=HealthStatus.HEALTHY)

    # -- Test inspection -------------------------------------------------------

    @property
    def execute_requests(self) -> List[HubRequest]:
        return list(self._execute_requests)

    @property
    def stream_requests(self) -> List[HubRequest]:
        return list(self._stream_requests)

    @property
    def responses(self) -> List[HubResponse]:
        return list(self._responses)

    def reset(self) -> None:
        self._execute_requests.clear()
        self._stream_requests.clear()
        self._responses.clear()


__all__ = ["TestLLMRequestAdapter"]
