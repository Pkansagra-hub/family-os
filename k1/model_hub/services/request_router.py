"""THE single entry point for all Model Hub traffic [F40].

Orchestrates the 9-step request pipeline: validate -> budget -> priority ->
route -> select -> cache -> normalize -> dispatch -> post-process.

Import graph (Layer 3 -- imports all layers)
----------------------------------------------
k1.model_hub.services.request_router
  -> k1.model_hub.types              (Layer 0)
  -> k1.model_hub.config             (Layer 0)
  -> k1.model_hub.plugins.base       (Layer 2)
  -> k1.model_hub.services.*         (Layer 3)
  -> k1.model_hub.ports.*            (Layer 1)
  -> stdlib only

NEVER import from any adapter or runtime module.

References
----------
- model_hub.mmd: RequestRouter service (THE single entry point)
- Invariant MH-03: trace_id required on every request
- Invariant MH-04: HARD rejection on budget exceeded
- Invariant MH-09: Cache TTL 5min default, LRU eviction
- Invariant MH-15: Priority-based timeouts
- Invariant MH-16: ALL traffic through RequestRouter
"""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator, Optional, Protocol, runtime_checkable

from k1.model_hub.events import (
    TOPIC_REQUEST_RECEIVED,
    TOPIC_RESPONSE_COMPLETE,
)
from k1.model_hub.plugins.base import NormalizedRequest
from k1.model_hub.ports.event_port import IEventPort
from k1.model_hub.ports.state_read_port import IStateReadPort
from k1.model_hub.services.audit_logger import AuditLogger
from k1.model_hub.services.capability_router import CapabilityRouter
from k1.model_hub.services.model_selector import ModelSelector
from k1.model_hub.services.normalization_layer import NormalizationLayer
from k1.model_hub.services.provider_dispatcher import ProviderDispatcher
from k1.model_hub.services.response_cache import ResponseCache
from k1.model_hub.types import (
    CapabilityType,
    FinishReason,
    HubChunk,
    HubRequest,
    HubResponse,
    NoEligibleProviderError,
    ResponseMetadata,
    TokenUsage,
    ValidationError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lightweight metrics protocol (avoids importing IMetricsPort at Layer 3)
# ---------------------------------------------------------------------------


@runtime_checkable
class _MetricsEmitter(Protocol):
    def emit(
        self, metric_name: str, value: float, labels: dict[str, Any] | None = None
    ) -> None: ...


# ===========================================================================
# RequestRouter
# ===========================================================================


class RequestRouter:
    """THE single entry point for all Model Hub traffic (MH-16).

    7-step request pipeline (family-os: no budget enforcement):
      1. Validate envelope (schema, trace_id MH-03).
      2. Classify priority -> set timeout (MH-15).
      3. CapabilityRouter -> eligible providers.
      4. ModelSelector -> provider + model + fallback chain.
      5. Check cache (MH-09).
      6. NormalizationLayer -> NormalizedRequest.
      7. ProviderDispatcher -> execute/stream + post-process (cache, audit).

    Constructor: all internal service dependencies injected.

    Methods:
      route(request) -> HubResponse
      stream_route(request) -> AsyncIterator[HubChunk]
    """

    def __init__(
        self,
        *,
        capability_router: CapabilityRouter,
        model_selector: ModelSelector,
        response_cache: ResponseCache,
        normalization_layer: NormalizationLayer,
        dispatcher: ProviderDispatcher,
        audit_logger: Optional[AuditLogger] = None,
        metrics_port: Optional[_MetricsEmitter] = None,
        event_port: Optional[IEventPort] = None,
        state_read_port: Optional[IStateReadPort] = None,
    ) -> None:
        self._capability_router = capability_router
        self._model_selector = model_selector
        self._response_cache = response_cache
        self._normalization = normalization_layer
        self._dispatcher = dispatcher
        self._audit_logger = audit_logger
        self._metrics = metrics_port
        self._event_port = event_port
        # 3.1.3: state_read_port wired through (was previously validated
        # in factory but silently discarded). Currently held for future
        # state-driven routing/policy decisions; not yet consumed in
        # route(). Per-request session_id is available on
        # ``HubRequest.session_id`` (3.1.1).
        self._state_read_port = state_read_port
        self._active_requests = 0

    # -- route() (MH-16) ------------------------------------------------------

    async def route(self, request: HubRequest) -> HubResponse:
        """Execute the 7-step request pipeline.

        Args:
            request: Hub-canonical request envelope.

        Returns:
            HubResponse with full ResponseMetadata.

        Raises:
            ValidationError: Invalid request (missing trace_id, etc.).
            NoEligibleProviderError: No provider supports capability.
        """
        # Step 1: Validate envelope
        self._validate(request)

        # Metric: active requests gauge
        self._active_requests += 1
        self._emit("model_hub.active_requests", self._active_requests)

        std_labels = {
            "capability": request.capability.value,
            "consumer": request.constraints.consumer_id,
            "priority": request.constraints.priority.value,
        }

        await self._publish(
            TOPIC_REQUEST_RECEIVED,
            {
                "request_id": request.request_id,
                "trace_id": request.trace_id,
                "consumer_id": request.constraints.consumer_id,
                "capability": request.capability.value,
                "budget_remaining_pct": 100.0,
            },
        )

        # Metric: requests_total counter
        self._emit("model_hub.requests_total", 1, std_labels)

        pipeline_start = time.monotonic()

        try:
            return await self._route_inner(request, std_labels)
        except NoEligibleProviderError:
            self._emit(
                "model_hub.errors_total", 1, {**std_labels, "error_type": "no_eligible_provider"}
            )
            await self._publish(
                "k1.model_hub.request.failed.v1",
                {
                    "request_id": request.request_id,
                    "trace_id": request.trace_id,
                    "error": "no_eligible_provider",
                    **std_labels,
                },
            )
            raise
        except Exception:
            self._emit("model_hub.errors_total", 1, {**std_labels, "error_type": "internal"})
            await self._publish(
                "k1.model_hub.request.failed.v1",
                {
                    "request_id": request.request_id,
                    "trace_id": request.trace_id,
                    "error": "internal",
                    **std_labels,
                },
            )
            raise
        finally:
            self._active_requests = max(0, self._active_requests - 1)
            self._emit("model_hub.active_requests", self._active_requests)
            elapsed = int((time.monotonic() - pipeline_start) * 1000)
            self._emit("model_hub.latency_ms", elapsed, std_labels)

    async def _route_inner(
        self,
        request: HubRequest,
        std_labels: dict[str, Any],
    ) -> HubResponse:
        """Inner route logic (extracted for metric wrapping)."""

        # Step 2: Priority -> timeout (MH-15) -- already in constraints
        # (timeout_ms set by caller or defaults from Priority tier)

        # Step 3: CapabilityRouter -> eligible providers
        eligible = self._capability_router.route(
            request.capability,
            request.constraints,
        )
        if not eligible:
            # Debug: dump registry state
            all_providers = self._capability_router._registry.list_providers()
            for pinfo in all_providers:
                cb_state = self._capability_router._circuit_breaker.get_state(pinfo.provider_id)
                has_cap = self._capability_router._registry.get_providers_for_capability(
                    request.capability
                )
                logger.warning(
                    "NoEligibleProvider: cap=%s provider=%s caps=%s cb=%s in_cap_index=%s",
                    request.capability.value,
                    pinfo.provider_id,
                    [c.value for c in pinfo.capabilities],
                    cb_state.value if cb_state else "N/A",
                    any(p.provider_id == pinfo.provider_id for p in has_cap),
                )
            raise NoEligibleProviderError(
                f"No eligible provider for {request.capability.value}",
                request_id=request.request_id,
                trace_id=request.trace_id,
                capability=request.capability,
            )

        # Step 4: ModelSelector -> provider + model + fallback chain
        choice = self._model_selector.select(eligible, request)
        if choice is None:
            raise NoEligibleProviderError(
                f"ModelSelector returned no choice for {request.capability.value}",
                request_id=request.request_id,
                trace_id=request.trace_id,
                capability=request.capability,
            )

        # Step 6: Check cache (MH-09)
        if self._response_cache.should_cache(request):
            cache_key = ResponseCache.build_cache_key(
                request.capability,
                request.payload,
                choice.model_id,
                request.constraints.temperature,
                request.session_id,
            )
            cache_result = self._response_cache.get(cache_key)
            if cache_result.hit and cache_result.response is not None:
                self._emit(
                    "model_hub.cache_hits_total",
                    1,
                    {
                        "capability": request.capability.value,
                    },
                )
                await self._publish_response_complete(
                    request,
                    cache_result.response,
                    latency_ms=0,
                    total_tokens=(
                        cache_result.response.metadata.usage.prompt_tokens
                        + cache_result.response.metadata.usage.completion_tokens
                    ),
                )
                return cache_result.response

        # Step 7: NormalizationLayer -> NormalizedRequest
        normalized = self._normalization.normalize(request, choice.provider_id)
        normalized = NormalizedRequest(
            capability=normalized.capability,
            messages=normalized.messages,
            system_prompt=normalized.system_prompt,
            tools=normalized.tools,
            tool_choice=normalized.tool_choice,
            output_schema=normalized.output_schema,
            max_tokens=normalized.max_tokens,
            timeout_ms=normalized.timeout_ms,
            temperature=normalized.temperature,
            model_id=choice.model_id,
            trace_id=normalized.trace_id,
            consumer_id=normalized.consumer_id,
            reasoning_effort=normalized.reasoning_effort,
            extra={
                **normalized.extra,
                "request_id": request.request_id,
                "session_id": request.session_id,
            },
        )

        # Step 8: ProviderDispatcher -> execute
        fallback_ids = [f.provider_id for f in choice.fallback_chain]
        start_time = time.monotonic()
        dispatch_result = await self._dispatcher.dispatch(
            normalized,
            choice.provider_id,
            fallback_chain=fallback_ids,
            token_estimate=request.constraints.max_tokens,
        )
        latency_ms = int((time.monotonic() - start_time) * 1000)

        # Metric: provider_latency_ms
        self._emit(
            "model_hub.provider_latency_ms",
            latency_ms,
            {
                "provider": dispatch_result.provider_id,
                "model": choice.model_id,
                "capability": request.capability.value,
            },
        )

        # Metric: fallbacks_total
        if dispatch_result.fallback_used:
            self._emit(
                "model_hub.fallbacks_total",
                1,
                {
                    "from_provider": choice.provider_id,
                    "to_provider": dispatch_result.provider_id,
                    "capability": request.capability.value,
                },
            )

        # Step 9: Post-process -- denormalize, cache, audit
        response = self._normalization.denormalize(
            dispatch_result.response,
            request,
            provider_id=dispatch_result.provider_id,
            latency_ms=latency_ms,
            cache_hit=False,
            fallback_used=dispatch_result.fallback_used,
        )

        # Cache response if cacheable
        if self._response_cache.should_cache(request):
            cache_key = ResponseCache.build_cache_key(
                request.capability,
                request.payload,
                choice.model_id,
                request.constraints.temperature,
                request.session_id,
            )
            self._response_cache.put(cache_key, response)

        # Audit log
        if self._audit_logger is not None:
            self._audit_logger.log(
                request,
                response,
                fallback_chain=dispatch_result.attempts,
            )

        # Metrics: tokens used
        result_labels = {
            **std_labels,
            "provider": dispatch_result.provider_id,
            "model": choice.model_id,
        }
        total_tokens = (
            response.metadata.usage.prompt_tokens + response.metadata.usage.completion_tokens
        )
        self._emit("model_hub.tokens_used", total_tokens, result_labels)

        await self._publish(
            "k1.model_hub.request.completed.v1",
            {
                "request_id": request.request_id,
                "trace_id": request.trace_id,
                "provider": dispatch_result.provider_id,
                "model": choice.model_id,
                "capability": request.capability.value,
                "latency_ms": latency_ms,
                "total_tokens": total_tokens,
                "fallback_used": dispatch_result.fallback_used,
            },
        )
        await self._publish_response_complete(
            request,
            response,
            latency_ms=latency_ms,
            total_tokens=total_tokens,
        )

        return response

    # -- stream_route() --------------------------------------------------------

    async def stream_route(self, request: HubRequest) -> AsyncIterator[HubChunk]:
        """Streaming variant of the request pipeline.

        Steps 1-6 same as route(). Step 7 delegates to
        ProviderDispatcher.stream(). Post-processing on final chunk.

        Args:
            request: Hub-canonical request envelope.

        Yields:
            HubChunk instances.

        Raises:
            ValidationError: Invalid request.
            NoEligibleProviderError: No eligible provider.
        """
        # Steps 1-4 same as route()
        self._validate(request)

        eligible = self._capability_router.route(
            request.capability,
            request.constraints,
        )
        if not eligible:
            # Debug: dump registry state to understand why no provider matches
            all_providers = self._capability_router._registry.list_providers()
            for pinfo in all_providers:
                cb_state = self._capability_router._circuit_breaker.get_state(pinfo.provider_id)
                has_cap = self._capability_router._registry.get_providers_for_capability(
                    request.capability
                )
                logger.warning(
                    "NoEligibleProvider: cap=%s provider=%s caps=%s cb=%s in_cap_index=%s",
                    request.capability.value,
                    pinfo.provider_id,
                    [c.value for c in pinfo.capabilities],
                    cb_state.value if cb_state else "N/A",
                    any(p.provider_id == pinfo.provider_id for p in has_cap),
                )
            raise NoEligibleProviderError(
                f"No eligible provider for {request.capability.value}",
                request_id=request.request_id,
                trace_id=request.trace_id,
                capability=request.capability,
            )

        choice = self._model_selector.select(eligible, request)
        if choice is None:
            raise NoEligibleProviderError(
                f"ModelSelector returned no choice for {request.capability.value}",
                request_id=request.request_id,
                trace_id=request.trace_id,
                capability=request.capability,
            )

        # Step 7: Normalize
        normalized = self._normalization.normalize(request, choice.provider_id)
        normalized = NormalizedRequest(
            capability=normalized.capability,
            messages=normalized.messages,
            system_prompt=normalized.system_prompt,
            tools=normalized.tools,
            tool_choice=normalized.tool_choice,
            output_schema=normalized.output_schema,
            max_tokens=normalized.max_tokens,
            timeout_ms=normalized.timeout_ms,
            temperature=normalized.temperature,
            model_id=choice.model_id,
            trace_id=normalized.trace_id,
            consumer_id=normalized.consumer_id,
            reasoning_effort=normalized.reasoning_effort,
            extra={**normalized.extra, "session_id": request.session_id},
        )

        # Step 8: Stream dispatch
        fallback_ids = [f.provider_id for f in choice.fallback_chain]

        accumulated_text = ""
        accumulated_tool_calls: list[Any] = []
        accumulated_thought = ""
        async for chunk in self._dispatcher.stream(
            normalized,
            choice.provider_id,
            fallback_chain=fallback_ids,
            token_estimate=request.constraints.max_tokens,
        ):
            accumulated_text += chunk.text
            thought_text = ""
            if isinstance(chunk.metadata, dict):
                thought_text = str(chunk.metadata.get("thought_text") or "")
            accumulated_thought += thought_text
            if chunk.tool_calls:
                accumulated_tool_calls.extend(chunk.tool_calls)
            if chunk.done:
                chunk_finish_reason = FinishReason.STOP
                if isinstance(chunk.metadata, dict) and chunk.metadata.get("finish_reason"):
                    raw_finish = chunk.metadata.get("finish_reason")
                    if isinstance(raw_finish, FinishReason):
                        chunk_finish_reason = raw_finish
                    else:
                        try:
                            chunk_finish_reason = FinishReason(str(raw_finish))
                        except ValueError:
                            logger.warning(
                                "RequestRouter.stream_route: unknown provider finish_reason=%r",
                                raw_finish,
                            )
                # Final chunk -- build metadata with accumulated content
                metadata = ResponseMetadata(
                    request_id=request.request_id,
                    model_id=choice.model_id,
                    provider_id=choice.provider_id,
                    usage=TokenUsage(
                        prompt_tokens=chunk.prompt_tokens,
                        completion_tokens=chunk.completion_tokens,
                    ),
                    cost_usd=0.0,
                    latency_ms=0,
                    cache_hit=False,
                    capability=request.capability,
                    trace_id=request.trace_id,
                    finish_reason=(
                        FinishReason.TOOL_CALLS if accumulated_tool_calls else chunk_finish_reason
                    ),
                )
                yield HubChunk(
                    content=accumulated_text,
                    thought=accumulated_thought,
                    done=True,
                    metadata=metadata,
                    tool_calls=accumulated_tool_calls or None,
                )
            else:
                yield HubChunk(content=chunk.text, thought=thought_text, done=False)

    # -- Metrics helper --------------------------------------------------------

    def _emit(
        self,
        metric_name: str,
        value: float,
        labels: dict[str, Any] | None = None,
    ) -> None:
        """Fire-and-forget metric emission. Never raises."""
        if self._metrics is None:
            return
        try:
            self._metrics.emit(metric_name, value, labels)
        except Exception:  # noqa: BLE001
            logger.debug("Metric emission failed: %s", metric_name, exc_info=True)

    async def _publish(self, topic: str, payload: Any) -> None:
        """Fire-and-forget event publication. Never raises."""
        if self._event_port is None:
            return
        try:
            await self._event_port.publish(topic, payload)
        except Exception:  # noqa: BLE001
            logger.debug("Event publish failed: %s", topic, exc_info=True)

    async def _publish_response_complete(
        self,
        request: HubRequest,
        response: HubResponse,
        *,
        latency_ms: int,
        total_tokens: int,
    ) -> None:
        """Publish the documented response-complete event."""
        metadata = response.metadata
        await self._publish(
            TOPIC_RESPONSE_COMPLETE,
            {
                "request_id": request.request_id,
                "trace_id": request.trace_id,
                "tokens_used": total_tokens,
                "latency_ms": latency_ms,
                "cost_usd": metadata.cost_usd,
                "provider_id": metadata.provider_id,
                "model_id": metadata.model_id,
                "capability": request.capability.value,
                "cache_hit": metadata.cache_hit,
            },
        )

    # -- Validation ------------------------------------------------------------

    @staticmethod
    def _validate(request: HubRequest) -> None:
        """Validate request envelope (Step 1).

        MH-03: trace_id must be non-empty (already enforced by HubRequest).
        Additional schema validation here.

        Raises:
            ValidationError: If request is invalid.
        """
        # trace_id already enforced by HubRequest.__post_init__
        # Validate capability is known
        if not isinstance(request.capability, CapabilityType):
            raise ValidationError(
                f"Unknown capability: {request.capability!r}",
                request_id=request.request_id,
                trace_id=request.trace_id,
            )


__all__ = [
    "RequestRouter",
]
