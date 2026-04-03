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

from k1.model_hub.plugins.base import NormalizedRequest
from k1.model_hub.services.audit_logger import AuditLogger
from k1.model_hub.services.budget_enforcer import BudgetEnforcer
from k1.model_hub.services.capability_router import CapabilityRouter
from k1.model_hub.services.cost_tracker import CostTracker
from k1.model_hub.services.model_selector import ModelSelector
from k1.model_hub.services.normalization_layer import NormalizationLayer
from k1.model_hub.services.provider_dispatcher import ProviderDispatcher
from k1.model_hub.services.response_cache import ResponseCache
from k1.model_hub.types import (
    BudgetDecision,
    BudgetExceededError,
    CapabilityType,
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

    9-step request pipeline:
      1. Validate envelope (schema, trace_id MH-03).
      2. Check daily budget (MH-04, MH-08).
      3. Classify priority -> set timeout (MH-15).
      4. CapabilityRouter -> eligible providers.
      5. ModelSelector -> provider + model + fallback chain.
      6. Check cache (MH-09).
      7. NormalizationLayer -> NormalizedRequest.
      8. ProviderDispatcher -> execute/stream.
      9. Post-process: cache, cost, audit, metrics.

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
        budget_enforcer: BudgetEnforcer,
        response_cache: ResponseCache,
        normalization_layer: NormalizationLayer,
        dispatcher: ProviderDispatcher,
        cost_tracker: Optional[CostTracker] = None,
        audit_logger: Optional[AuditLogger] = None,
        metrics_port: Optional[_MetricsEmitter] = None,
    ) -> None:
        self._capability_router = capability_router
        self._model_selector = model_selector
        self._budget_enforcer = budget_enforcer
        self._response_cache = response_cache
        self._normalization = normalization_layer
        self._dispatcher = dispatcher
        self._cost_tracker = cost_tracker
        self._audit_logger = audit_logger
        self._metrics = metrics_port
        self._active_requests = 0

    # -- route() (MH-16) ------------------------------------------------------

    async def route(self, request: HubRequest) -> HubResponse:
        """Execute the 9-step request pipeline.

        Args:
            request: Hub-canonical request envelope.

        Returns:
            HubResponse with full ResponseMetadata.

        Raises:
            ValidationError: Invalid request (missing trace_id, etc.).
            BudgetExceededError: Budget exceeded (MH-04).
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

        # Metric: requests_total counter
        self._emit("model_hub.requests_total", 1, std_labels)

        pipeline_start = time.monotonic()

        try:
            return await self._route_inner(request, std_labels)
        except BudgetExceededError:
            self._emit(
                "model_hub.budget_rejections_total",
                1,
                {
                    "capability": request.capability.value,
                    "consumer": request.constraints.consumer_id,
                },
            )
            self._emit("model_hub.errors_total", 1, {**std_labels, "error_type": "budget_exceeded"})
            raise
        except NoEligibleProviderError:
            self._emit(
                "model_hub.errors_total", 1, {**std_labels, "error_type": "no_eligible_provider"}
            )
            raise
        except Exception:
            self._emit("model_hub.errors_total", 1, {**std_labels, "error_type": "internal"})
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

        # Step 2: Check budget (MH-04, MH-08)
        budget_result = self._budget_enforcer.check(request)
        if budget_result.decision == BudgetDecision.REJECT:
            raise BudgetExceededError(
                budget_result.reason,
                budget_pct=budget_result.usage_pct,
                daily_limit=budget_result.daily_budget_usd,
                request_id=request.request_id,
                trace_id=request.trace_id,
                capability=request.capability,
            )

        # Step 3: Priority -> timeout (MH-15) -- already in constraints
        # (timeout_ms set by caller or defaults from Priority tier)

        # Step 4: CapabilityRouter -> eligible providers
        eligible = self._capability_router.route(
            request.capability,
            request.constraints,
        )
        if not eligible:
            raise NoEligibleProviderError(
                f"No eligible provider for {request.capability.value}",
                request_id=request.request_id,
                trace_id=request.trace_id,
                capability=request.capability,
            )

        # Step 5: ModelSelector -> provider + model + fallback chain
        # Update budget usage for cost-aware selection
        self._model_selector.budget_usage_pct = self._budget_enforcer.usage_pct
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
            extra=normalized.extra,
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

        # Step 9: Post-process -- denormalize, cache, cost, audit
        response = self._normalization.denormalize(
            dispatch_result.response,
            request,
            provider_id=dispatch_result.provider_id,
            latency_ms=latency_ms,
            cache_hit=False,
            fallback_used=dispatch_result.fallback_used,
        )

        # Track budget
        self._budget_enforcer.track(response)

        # Cache response if cacheable
        if self._response_cache.should_cache(request):
            cache_key = ResponseCache.build_cache_key(
                request.capability,
                request.payload,
                choice.model_id,
                request.constraints.temperature,
            )
            self._response_cache.put(cache_key, response)

        # Audit log
        if self._audit_logger is not None:
            self._audit_logger.log(
                request,
                response,
                fallback_chain=dispatch_result.attempts,
            )

        # Metrics: tokens used, cost, budget gauge
        result_labels = {
            **std_labels,
            "provider": dispatch_result.provider_id,
            "model": choice.model_id,
        }
        total_tokens = (
            response.metadata.usage.prompt_tokens + response.metadata.usage.completion_tokens
        )
        self._emit("model_hub.tokens_used", total_tokens, result_labels)
        self._emit("model_hub.cost_usd", response.metadata.cost_usd, result_labels)
        self._emit("model_hub.budget_pct", self._budget_enforcer.usage_pct)

        return response

    # -- stream_route() --------------------------------------------------------

    async def stream_route(self, request: HubRequest) -> AsyncIterator[HubChunk]:
        """Streaming variant of the request pipeline.

        Steps 1-7 same as route(). Step 8 delegates to
        ProviderDispatcher.stream(). Post-processing on final chunk.

        Args:
            request: Hub-canonical request envelope.

        Yields:
            HubChunk instances.

        Raises:
            ValidationError: Invalid request.
            BudgetExceededError: Budget exceeded.
            NoEligibleProviderError: No eligible provider.
        """
        # Steps 1-5 same as route()
        self._validate(request)

        budget_result = self._budget_enforcer.check(request)
        if budget_result.decision == BudgetDecision.REJECT:
            raise BudgetExceededError(
                budget_result.reason,
                budget_pct=budget_result.usage_pct,
                daily_limit=budget_result.daily_budget_usd,
                request_id=request.request_id,
                trace_id=request.trace_id,
                capability=request.capability,
            )

        eligible = self._capability_router.route(
            request.capability,
            request.constraints,
        )
        if not eligible:
            raise NoEligibleProviderError(
                f"No eligible provider for {request.capability.value}",
                request_id=request.request_id,
                trace_id=request.trace_id,
                capability=request.capability,
            )

        self._model_selector.budget_usage_pct = self._budget_enforcer.usage_pct
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
            extra=normalized.extra,
        )

        # Step 8: Stream dispatch
        fallback_ids = [f.provider_id for f in choice.fallback_chain]

        accumulated_text = ""
        async for chunk in self._dispatcher.stream(
            normalized,
            choice.provider_id,
            fallback_chain=fallback_ids,
            token_estimate=request.constraints.max_tokens,
        ):
            accumulated_text += chunk.text
            if chunk.done:
                # Final chunk -- build metadata
                metadata = ResponseMetadata(
                    request_id=request.request_id,
                    model_id=choice.model_id,
                    provider_id=choice.provider_id,
                    usage=TokenUsage(),
                    cost_usd=0.0,
                    latency_ms=0,
                    cache_hit=False,
                    capability=request.capability,
                    trace_id=request.trace_id,
                )
                yield HubChunk(
                    content=chunk.text,
                    done=True,
                    metadata=metadata,
                    tool_calls=chunk.tool_calls,
                )
            else:
                yield HubChunk(content=chunk.text, done=False)

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
