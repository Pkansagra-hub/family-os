"""HTTP handlers for the query recall port (`/k0/query.recall`)."""

from __future__ import annotations

import json
import math
import uuid
from collections.abc import Iterable, Iterator
from contextlib import suppress
from typing import Any, Mapping, Sequence, cast

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from k0.kernel.dependencies import qos_context_dependency
from k0.obs import MetricsExporter, ObservabilityEmitter, TracerFactory, update_log_context
from k0.policy import evaluate_envelope
from k0.policy.pep_syscall import create_policy_stamp
from k0.ports.errors import (
    KERNEL_COMPONENT_POLICY,
    KERNEL_COMPONENT_QOS,
    KERNEL_COMPONENT_QUERY,
    ErrorEnvelope,
)
from k0.qos import (
    QoSBudgetError,
    QoSContext,
    QoSTightening,
    SchedulerCapacityError,
    SchedulerToken,
    apply_qos_obligations,
)
from k0.query.service import DEFAULT_SELECTOR_LIMIT, MAX_SELECTOR_LIMIT, QueryAggregator

router = APIRouter(prefix="/k0", tags=["query"])

DEFAULT_TIME_BUDGET_MS = 250


class RecallSelector(BaseModel):
    """Selector describing a recall instruction."""

    model_config = ConfigDict(extra="allow")

    type: str | None = Field(
        default=None,
        description="Logical selector type (episodic, semantic, etc).",
    )
    topic: str | None = Field(default=None, description="Topic filter applied during recall.")
    tenant_id: str | None = Field(
        default=None, description="Optional tenant override for the selector."
    )
    space_id: str | None = Field(
        default=None, description="Optional space override (must match request)."
    )
    limit: int | None = Field(
        default=None,
        ge=1,
        le=256,
        description="Maximum number of items to return for this selector.",
    )
    cursor: int | None = Field(
        default=None,
        ge=0,
        description="Return items before this WAL position (exclusive).",
    )
    after: int | None = Field(
        default=None,
        ge=0,
        description="Return items after this WAL position (exclusive).",
    )
    query: str | None = Field(
        default=None,
        description="Optional free-text query leveraged by downstream drivers.",
    )


class RecallRequest(BaseModel):
    """Subset of the query recall request schema used by the kernel."""

    model_config = ConfigDict(extra="allow")

    selectors: list[RecallSelector]
    space_id: str
    tenant_id: str | None = None
    fanout_hints: dict[str, Any] | None = None
    qos_hints: dict[str, Any] | None = None
    max_latency_ms: int | None = Field(
        default=None,
        ge=1,
        le=10_000,
        description="Client-provided bound on acceptable latency in milliseconds.",
    )
    fail_fast: bool = Field(
        default=False,
        description=(
            "When true, the kernel returns 429 if the time slice budget is exhausted "
            "before all selectors complete."
        ),
    )


class RecallResponse(BaseModel):
    """Successful recall bundle emitted by the query port."""

    bundle: dict[str, Any]
    trace: dict[str, Any]
    budgets: dict[str, Any]


@router.post(
    "/query.recall",
    response_model=RecallResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid selector payload provided",
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": "QUERY_BAD_REQUEST",
                            "component": "kernel.query",
                            "reason": "SELECTORS_REQUIRED",
                            "trace_id": "35d8ce0f-221d-4060-8d97-1cd95cf11b9c",
                        }
                    }
                }
            },
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "QoS budgets or scheduler capacity exhausted",
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": "QOS_BUDGET_EXHAUSTED",
                            "component": "kernel.qos",
                            "reason": "FANOUT_BUDGET_EXHAUSTED",
                            "trace_id": "2cf024de-85a8-4167-83ec-951bf9f22424",
                            "budgets": {"fanout": 0, "top_k": 3},
                            "details": {"cap": "fanout"},
                        }
                    }
                }
            },
        },
    },
)
async def query_recall(
    payload: RecallRequest,
    request: Request,
    qos: QoSContext = Depends(qos_context_dependency),
) -> RecallResponse | JSONResponse | StreamingResponse:
    """Execute recall selectors against kernel storage within QoS budgets."""

    if not payload.selectors:
        return _error_response(
            request,
            status.HTTP_400_BAD_REQUEST,
            code="QUERY_BAD_REQUEST",
            reason="SELECTORS_REQUIRED",
            hint="Provide at least one selector to execute a recall request.",
        )

    for selector in payload.selectors:
        selector_space = selector.space_id
        if selector_space and selector_space != payload.space_id:
            return _error_response(
                request,
                status.HTTP_400_BAD_REQUEST,
                code="QUERY_BAD_REQUEST",
                reason="SELECTOR_SPACE_MISMATCH",
                hint="Selector space_id must match the request space_id.",
            )

        # Gap 24: Validate cursor boundaries
        if selector.cursor is not None:
            if selector.cursor < 0:
                return _error_response(
                    request,
                    status.HTTP_400_BAD_REQUEST,
                    code="QUERY_BAD_REQUEST",
                    reason="CURSOR_NEGATIVE",
                    hint=f"Cursor must be >= 0, got {selector.cursor}",
                )

        # Gap 24: Validate after position boundaries
        if selector.after is not None:
            if selector.after < 0:
                return _error_response(
                    request,
                    status.HTTP_400_BAD_REQUEST,
                    code="QUERY_BAD_REQUEST",
                    reason="AFTER_NEGATIVE",
                    hint=f"After position must be >= 0, got {selector.after}",
                )

        # Gap 24: Validate limit boundaries (beyond Pydantic validation)
        if selector.limit is not None:
            if selector.limit <= 0:
                return _error_response(
                    request,
                    status.HTTP_400_BAD_REQUEST,
                    code="QUERY_BAD_REQUEST",
                    reason="LIMIT_INVALID",
                    hint=f"Limit must be > 0, got {selector.limit}",
                )
            if selector.limit > MAX_SELECTOR_LIMIT:
                return _error_response(
                    request,
                    status.HTTP_400_BAD_REQUEST,
                    code="QUERY_BAD_REQUEST",
                    reason="LIMIT_EXCEEDED",
                    hint=f"Limit must be <= {MAX_SELECTOR_LIMIT}, got {selector.limit}",
                )

    topics = sorted(
        {
            selector.topic
            for selector in payload.selectors
            if selector.topic is not None and selector.topic.strip()
        }
    )
    update_log_context(
        tenant_id=payload.tenant_id,
        space_id=payload.space_id,
        query_selector_count=len(payload.selectors),
        query_topics=",".join(topics) if topics else None,
        query_fail_fast=payload.fail_fast,
    )

    app_state = request.app.state
    metrics_exporter = getattr(app_state, "metrics_exporter", None)
    observability_emitter = getattr(app_state, "observability_emitter", None)

    band = _resolve_band(payload)
    fanout_needed = len(payload.selectors)
    requested_top_k_budget = qos.top_k_budget
    time_budget_ms = _resolve_time_budget(payload)

    policy_envelope = _build_policy_envelope(
        payload,
        band=band,
        fanout_needed=fanout_needed,
        time_budget_ms=time_budget_ms,
        top_k_budget=requested_top_k_budget,
    )
    decision = evaluate_envelope(policy_envelope)
    if not decision.admit:
        return _error_response(
            request,
            status.HTTP_403_FORBIDDEN,
            code="PEP_DENY",
            component=KERNEL_COMPONENT_POLICY,
            reason=decision.deny_reason or "POLICY_DENIED",
            hint=(None if decision.deny_reason else "Policy enforcement denied the request."),
        )

    tightening = apply_qos_obligations(qos, decision.obligations)
    if tightening.time_slice_ms is not None:
        time_budget_ms = max(1, min(time_budget_ms, tightening.time_slice_ms))

    # Gap 20: Create policy_stamp for audit trail in query responses
    policy_stamp = create_policy_stamp(
        decision=decision,
        band=band,
    )

    policy_extras = _build_policy_metadata(decision, tightening)

    initial_fanout = qos.fanout_budget
    initial_top_k = qos.top_k_budget

    try:
        qos.consume_fanout(fanout_needed)
    except QoSBudgetError:
        return _budget_response(
            request,
            qos,
            component=KERNEL_COMPONENT_QOS,
            reason="FANOUT_BUDGET_EXHAUSTED",
            cap="fanout",
            extras=policy_extras,
        )

    scheduler_cost = _compute_scheduler_cost(
        fanout=fanout_needed,
        total_limit=_estimate_total_limit(payload.selectors, initial_top_k),
    )
    scheduler_token: SchedulerToken | None = None
    try:
        try:
            scheduler_token = qos.acquire(band=band, port="query", cost=scheduler_cost)
        except SchedulerCapacityError as exc:
            qos.fanout_budget = initial_fanout
            qos.top_k_budget = initial_top_k
            return _budget_response(
                request,
                qos,
                component=KERNEL_COMPONENT_QOS,
                reason="SCHEDULER_CAPACITY_EXHAUSTED",
                cap="scheduler",
                hint=str(exc),
                extras=policy_extras,
            )

        aggregator = QueryAggregator()
        execution_result = aggregator.execute(
            payload.selectors,
            space_id=payload.space_id,
            tenant_id=payload.tenant_id,
            time_budget_ms=time_budget_ms,
            top_k_budget=initial_top_k,
        )

        consumed_top_k = execution_result.consumed_top_k
        if consumed_top_k > 0:
            try:
                qos.consume_top_k(consumed_top_k)
            except QoSBudgetError:
                qos.fanout_budget = initial_fanout
                qos.top_k_budget = initial_top_k
                return _budget_response(
                    request,
                    qos,
                    component=KERNEL_COMPONENT_QOS,
                    reason="TOP_K_BUDGET_EXHAUSTED",
                    cap="top_k",
                    extras=policy_extras,
                )

        fanout_consumed = execution_result.processed_selectors
        qos.fanout_budget = max(0, initial_fanout - fanout_consumed)

        trace_id = _resolve_trace_id(request)
        latency_seconds = max(execution_result.elapsed_ms, 0.0) / 1000.0

        if metrics_exporter and isinstance(metrics_exporter, MetricsExporter):
            metrics_exporter.emit(
                "query_recall_requests_total",
                port="query",
                outcome="success",
            )
            metrics_exporter.observe(
                "query_recall_latency_seconds",
                latency_seconds,
                labels={"port": "query"},
            )

        if observability_emitter and isinstance(observability_emitter, ObservabilityEmitter):
            observability_emitter.emit(
                {
                    "event": "query_recall_completed",
                    "trace_id": trace_id,
                    "space_id": payload.space_id,
                    "tenant_id": payload.tenant_id,
                    "selectors": fanout_consumed,
                    "results": consumed_top_k,
                    "elapsed_ms": round(execution_result.elapsed_ms, 3),
                    "time_budget_ms": time_budget_ms,
                    "band": band,
                    "exhausted_time_budget": execution_result.exhausted_time_budget,
                }
            )

        stream_mode = _should_stream(payload, request)

        if execution_result.exhausted_time_budget and payload.fail_fast:
            return _budget_response(
                request,
                qos,
                component=KERNEL_COMPONENT_QOS,
                reason="TIME_SLICE_EXHAUSTED",
                cap="time_slice",
                hint="Time slice budget exhausted before all selectors completed.",
                include_time_slice=True,
                time_budget_ms=time_budget_ms,
                elapsed_ms=execution_result.elapsed_ms,
                extras=policy_extras,
            )

        time_remaining_ms = max(0, int(math.floor(time_budget_ms - execution_result.elapsed_ms)))

        bundle_payload = execution_result.bundle_payload()
        trace_nodes = list(execution_result.trace_nodes)
        trace_nodes.append(
            {
                "stage": "query.aggregate",
                "latency_ms": round(execution_result.elapsed_ms, 3),
            }
        )
        trace_payload: dict[str, Any] = {
            "mode": "stream" if stream_mode else "batch",
            "nodes": trace_nodes,
            "selectors_executed": fanout_consumed,
            "scheduler_cost": scheduler_cost,
            "exhausted_time_budget": execution_result.exhausted_time_budget,
        }
        if policy_extras and "policy" in policy_extras:
            trace_payload["policy"] = dict(cast(Mapping[str, Any], policy_extras["policy"]))
        if execution_result.exhausted_time_budget:
            trace_payload["fallback"] = {
                "mode": "sse",
                "endpoint": "/k0/sse.subscribe",
                "reason": "TIME_SLICE_EXHAUSTED",
            }

        budgets_payload: dict[str, Any] = {
            "fanout": max(0, int(qos.fanout_budget)),
            "time_slice": time_remaining_ms,
            "policy": "qos:v1/time",
        }
        if policy_extras and "policy" in policy_extras:
            policy_payload = cast(Mapping[str, Any], policy_extras["policy"])
            tightening_payload = policy_payload.get("tightening")
            if isinstance(tightening_payload, Mapping):
                budgets_payload["tightening"] = dict(cast(Mapping[str, Any], tightening_payload))

        # Gap 20: Include policy_stamp in response for audit trail
        if policy_stamp:
            budgets_payload["policy_stamp"] = policy_stamp

        if stream_mode:
            return StreamingResponse(
                _stream_query_response(
                    bundle_payload,
                    trace_payload,
                    budgets_payload,
                ),
                media_type="text/event-stream",
                headers={"X-Query-Response-Mode": "stream"},
            )

        response = RecallResponse(
            bundle=bundle_payload,
            trace=trace_payload,
            budgets=budgets_payload,
        )
        return response
    finally:
        if scheduler_token is not None:
            scheduler_token.release()


def _resolve_trace_id(request: Request) -> str:
    trace_id = getattr(request.state, "cognitive_trace_id", None)
    if trace_id:
        return str(trace_id)

    tracer_factory = getattr(request.app.state, "tracer_factory", None)
    if isinstance(tracer_factory, TracerFactory):
        trace_id = tracer_factory.new_trace_id()
    else:
        trace_id = uuid.uuid4().hex
    request.state.cognitive_trace_id = trace_id
    return str(trace_id)


def _error_response(
    request: Request,
    status_code: int,
    *,
    code: str,
    reason: str,
    hint: str | None = None,
    component: str = KERNEL_COMPONENT_QUERY,
) -> JSONResponse:
    trace_id = _resolve_trace_id(request)
    envelope = ErrorEnvelope(
        code=code,
        component=component,
        trace_id=trace_id,
        reason=reason,
        hint=hint,
    )
    return JSONResponse(status_code=status_code, content=envelope.as_payload())


def _budget_response(
    request: Request,
    qos: QoSContext,
    *,
    component: str,
    reason: str,
    cap: str,
    hint: str | None = None,
    include_time_slice: bool = False,
    time_budget_ms: int | None = None,
    elapsed_ms: float | None = None,
    extras: Mapping[str, Any] | None = None,
) -> JSONResponse:
    budgets = _serialize_qos_budgets(qos)
    if include_time_slice and time_budget_ms is not None:
        remaining = max(0, int(math.floor(time_budget_ms - (elapsed_ms or 0.0))))
        budgets["time_slice"] = remaining
    _emit_qos_budget_telemetry(
        request,
        cap=cap,
        reason=reason,
        budgets=budgets,
        hint=hint,
    )
    trace_id = _resolve_trace_id(request)
    envelope = ErrorEnvelope(
        code="QOS_BUDGET_EXHAUSTED",
        component=component,
        trace_id=trace_id,
        reason=reason,
        hint=hint,
        budgets=budgets,
        details={"cap": cap},
    )
    content = envelope.as_payload()
    if extras:
        for key, value in extras.items():
            content[str(key)] = value
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content=content,
    )


def _build_policy_envelope(
    payload: RecallRequest,
    *,
    band: str,
    fanout_needed: int,
    time_budget_ms: int,
    top_k_budget: int,
) -> dict[str, Any]:
    envelope: dict[str, Any] = {
        "band": band,
        "topic": "memory.query.recall",
        "space_id": payload.space_id,
    }
    if payload.tenant_id:
        envelope["tenant_id"] = payload.tenant_id

    policy_payload = _merge_policy_caps(
        _lookup_payload_extra(payload, "policy"),
        fanout_needed=fanout_needed,
        time_budget_ms=time_budget_ms,
        top_k_budget=top_k_budget,
        qos_hints=payload.qos_hints or {},
        default_roles=("coordinator",),
    )
    if policy_payload:
        envelope["policy"] = policy_payload

    for extra_key in ("policy_ctx", "pep"):
        extra_value = _lookup_payload_extra(payload, extra_key)
        if isinstance(extra_value, Mapping):
            envelope[extra_key] = _coerce_mapping(extra_value)

    return envelope


def _merge_policy_caps(
    policy: Any,
    *,
    fanout_needed: int,
    time_budget_ms: int,
    top_k_budget: int,
    qos_hints: Mapping[str, Any],
    default_roles: Sequence[str] | None = None,
) -> dict[str, Any]:
    policy_mapping = _coerce_mapping(policy)
    caps_mapping = _coerce_mapping(policy_mapping.get("caps"))

    caps_mapping["fanout"] = {"requested": max(1, int(fanout_needed))}
    if top_k_budget > 0:
        caps_mapping["top_k"] = {"requested": int(top_k_budget)}
    caps_mapping["latency_ms"] = {"requested": max(1, int(time_budget_ms))}

    policy_mapping["caps"] = caps_mapping

    band_hint = qos_hints.get("band") or qos_hints.get("priority")
    if isinstance(band_hint, str) and band_hint.strip():
        abac_mapping = _coerce_mapping(policy_mapping.get("abac"))
        abac_mapping["band_hint"] = band_hint.strip().upper()
        policy_mapping["abac"] = abac_mapping

    if default_roles:
        abac_mapping = _coerce_mapping(policy_mapping.get("abac"))
        if not abac_mapping.get("roles"):
            abac_mapping["roles"] = list(default_roles)
        policy_mapping["abac"] = abac_mapping

    return policy_mapping


def _lookup_payload_extra(payload: RecallRequest, key: str) -> Any:
    extra = getattr(payload, "model_extra", None)
    if isinstance(extra, Mapping):
        extra_mapping = _coerce_mapping(extra)
        return extra_mapping.get(key)
    return None


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        typed_mapping = cast(Mapping[Any, Any], value)
        result: dict[str, Any] = {}
        for key, val in typed_mapping.items():
            result[str(key)] = val
        return result
    return {}


def _build_policy_metadata(
    decision: Any,
    tightening: QoSTightening,
) -> dict[str, Any] | None:
    policy_payload: dict[str, Any] = {}

    admit = getattr(decision, "admit", None)
    if isinstance(admit, bool):
        policy_payload["decision"] = "ADMIT" if admit else "DENY"

    deny_reason = getattr(decision, "deny_reason", None)
    if isinstance(deny_reason, str) and deny_reason:
        policy_payload["deny_reason"] = deny_reason

    obligations_payload: list[dict[str, Any]] = []
    raw_obligations = getattr(decision, "obligations", None)
    if isinstance(raw_obligations, Iterable):
        for obligation in cast(Iterable[Any], raw_obligations):
            name = getattr(obligation, "name", None)
            if not isinstance(name, str) or not name:
                continue
            entry: dict[str, Any] = {"name": name}
            details = getattr(obligation, "details", None)
            if isinstance(details, Mapping):
                entry["details"] = {
                    str(k): str(v) for k, v in cast(Mapping[Any, Any], details).items()
                }
            elif details is not None:
                entry["details"] = str(details)
            obligations_payload.append(entry)
    if obligations_payload:
        policy_payload["obligations"] = obligations_payload

    tightening_payload: dict[str, int] = {}
    if tightening.fanout is not None:
        tightening_payload["fanout"] = int(tightening.fanout)
    if tightening.top_k is not None:
        tightening_payload["top_k"] = int(tightening.top_k)
    if tightening.time_slice_ms is not None:
        tightening_payload["time_slice_ms"] = int(tightening.time_slice_ms)
    if tightening_payload:
        policy_payload["tightening"] = tightening_payload

    if not policy_payload:
        return None

    return {"policy": policy_payload}


def _serialize_qos_budgets(qos: QoSContext) -> dict[str, int]:
    return {
        "fanout": max(0, int(qos.fanout_budget)),
        "top_k": max(0, int(qos.top_k_budget)),
    }


def _emit_qos_budget_telemetry(
    request: Request,
    *,
    cap: str,
    reason: str,
    budgets: Mapping[str, int],
    hint: str | None,
) -> None:
    app_state = request.app.state
    metrics_exporter = getattr(app_state, "metrics_exporter", None)
    if isinstance(metrics_exporter, MetricsExporter):
        metrics_exporter.emit(
            "qos_budget_exhausted_total",
            port="query",
            cap=cap,
        )

    observability_emitter = getattr(app_state, "observability_emitter", None)
    if isinstance(observability_emitter, ObservabilityEmitter):
        payload: dict[str, Any] = {
            "event": "query_qos_budget_exhausted",
            "trace_id": _resolve_trace_id(request),
            "port": "query",
            "cap": cap,
            "reason": reason,
            "budgets": dict(budgets),
        }
        if hint:
            payload["hint"] = hint
        with suppress(Exception):  # pragma: no cover - defensive logging guard
            observability_emitter.emit(payload)


def _resolve_time_budget(payload: RecallRequest) -> int:
    candidates: list[int] = []
    if payload.max_latency_ms is not None:
        candidates.append(payload.max_latency_ms)
    hints = payload.qos_hints or {}
    hint_budget = _coerce_positive_int(hints.get("target_latency_ms"))
    if hint_budget is not None:
        candidates.append(hint_budget)
    if not candidates:
        return DEFAULT_TIME_BUDGET_MS
    return max(1, min(candidates))


def _resolve_band(payload: RecallRequest) -> str:
    hints = payload.qos_hints or {}
    candidate = hints.get("band") or hints.get("priority")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip().upper()
    return "GREEN"


def _coerce_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        integer_value = int(value)
        return integer_value if integer_value > 0 else None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            integer_value = int(float(text))
        except ValueError:
            return None
        return integer_value if integer_value > 0 else None
    if isinstance(value, Mapping):
        mapping_value = cast(Mapping[str, Any], value)
        for candidate_key in ("requested", "value", "target", "max", "limit"):
            candidate_val = mapping_value.get(candidate_key)
            coerced = _coerce_positive_int(candidate_val)
            if coerced is not None:
                return coerced
    return None


def _estimate_total_limit(
    selectors: Sequence[RecallSelector],
    initial_top_k: int,
) -> int:
    if initial_top_k <= 0:
        remaining = len(selectors) * DEFAULT_SELECTOR_LIMIT
        unlimited = True
    else:
        remaining = max(0, int(initial_top_k))
        unlimited = False

    total = 0
    for selector in selectors:
        requested = selector.limit or DEFAULT_SELECTOR_LIMIT
        requested = max(1, min(int(requested), MAX_SELECTOR_LIMIT))
        if unlimited:
            total += requested
            continue

        allowed = min(requested, remaining)
        total += allowed
        remaining -= allowed
        if remaining <= 0:
            break

    return max(total, len(selectors))


def _compute_scheduler_cost(*, fanout: int, total_limit: int) -> int:
    if total_limit <= 0:
        total_limit = fanout
    base_cost = fanout + max(1, total_limit // 4)
    return max(1, base_cost)


def _coerce_stream_value(candidate: Any) -> bool:
    if isinstance(candidate, bool):
        return candidate
    if isinstance(candidate, (int, float)):
        return candidate != 0
    if isinstance(candidate, str):
        return candidate.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _should_stream(payload: RecallRequest, request: Request) -> bool:
    stream_param = request.query_params.get("stream")
    if stream_param and _coerce_stream_value(stream_param):
        return True

    hints = payload.qos_hints or {}
    qos_stream = hints.get("stream") or hints.get("stream_mode")
    if _coerce_stream_value(qos_stream):
        return True

    extra_data = getattr(payload, "model_extra", None)
    if isinstance(extra_data, dict):
        extra_mapping = cast(dict[str, Any], extra_data)
        extra_stream = extra_mapping.get("stream")
        if _coerce_stream_value(extra_stream):
            return True

    return False


def _stream_query_response(
    bundle_payload: Mapping[str, Any],
    trace_payload: Mapping[str, Any],
    budgets_payload: Mapping[str, Any],
) -> Iterator[bytes]:
    def event(event_name: str, data: Mapping[str, Any]) -> bytes:
        json_data = json.dumps(data, separators=(",", ":"))
        return (f"event: {event_name}\n" f"data: {json_data}\n\n").encode("utf-8")

    def generator() -> Iterator[bytes]:
        yield event("trace", trace_payload)
        for selector_payload in bundle_payload.get("selectors", []):
            yield event("selector", selector_payload)
        yield event("budgets", budgets_payload)
        yield event(
            "complete",
            {
                "selectors": len(bundle_payload.get("selectors", [])),
                "mode": trace_payload.get("mode", "batch"),
            },
        )

    return generator()
