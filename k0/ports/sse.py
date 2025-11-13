"""HTTP handlers for the SSE port."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Mapping, Sequence, cast

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from k0.kernel.dependencies import qos_context_dependency
from k0.obs import MetricsExporter, ObservabilityEmitter, update_log_context
from k0.ports.errors import KERNEL_COMPONENT_QOS, KERNEL_COMPONENT_SSE, ErrorEnvelope
from k0.qos import QoSBudgetError, QoSContext, SchedulerCapacityError, SchedulerToken
from k0.sse import BackpressureMetrics, SSEServer

router = APIRouter(prefix="/k0", tags=["sse"])


class AckRequest(BaseModel):
    """Schema-aligned representation of the SSE ack payload."""

    subscriber_id: str
    topic: str
    space_id: str
    tenant_id: str
    offset: int = Field(ge=0)
    ack_ts: str | None = None


class SSETraceEvent(BaseModel):
    """Payload emitted as SSE `trace` events."""

    cursor: str
    topic: str
    wal_pos: int
    commit_ts: str
    policy_stamp: dict[str, Any] | None = None  # Gap 20: Include policy stamp for audit trail


def _resolve_subscriber_id(request: Request) -> str:
    header = request.headers.get("X-SSE-Subscriber")
    if not header:
        raise ValueError("missing X-SSE-Subscriber header")
    candidate = header.strip()
    if not candidate:
        raise ValueError("subscriber identifier must not be empty")
    return candidate


def _serialize_backpressure_advisory(
    *,
    metrics: BackpressureMetrics,
    advisory_type: str,
    subscriber_id: str,
    tenant_id: str,
    space_id: str,
    throttle_ratio: float | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": advisory_type,
        "subscriber_id": subscriber_id,
        "tenant_id": tenant_id,
        "space_id": space_id,
        "lag_ms": metrics.lag_ms,
        "pending_events": metrics.pending_events,
        "ack_offsets": {topic: int(offset) for topic, offset in metrics.ack_offsets.items()},
        "topics": [
            {
                "topic": topic_metric.topic,
                "pending_events": topic_metric.pending_events,
                "lag_ms": topic_metric.lag_ms,
                "cursor": topic_metric.cursor,
            }
            for topic_metric in metrics.topics
        ],
    }
    if throttle_ratio is not None:
        payload["throttle_ratio"] = throttle_ratio
    return payload


def _emit_backpressure_event(
    *,
    emitter: ObservabilityEmitter | None,
    trace_id: str,
    metrics: BackpressureMetrics,
    subscriber_id: str,
    tenant_id: str,
    space_id: str,
    action: str,
    throttle_ratio: float,
) -> None:
    if not isinstance(emitter, ObservabilityEmitter):
        return

    emitter.emit(
        {
            "event": "sse_backpressure",
            "trace_id": trace_id,
            "subscriber_id": subscriber_id,
            "tenant_id": tenant_id,
            "space_id": space_id,
            "level": metrics.level,
            "action": action,
            "lag_ms": metrics.lag_ms,
            "pending_events": metrics.pending_events,
            "throttle_ratio": throttle_ratio,
            "topics": [
                {
                    "topic": topic_metric.topic,
                    "pending_events": topic_metric.pending_events,
                    "lag_ms": topic_metric.lag_ms,
                }
                for topic_metric in metrics.topics
            ],
        }
    )


def _error_response(
    *,
    request: Request,
    status_code: int,
    code: str,
    component: str = KERNEL_COMPONENT_SSE,
    reason: str | None = None,
    hint: str | None = None,
    budgets: Mapping[str, int] | None = None,
    details: Mapping[str, Any] | None = None,
) -> JSONResponse:
    trace_id = _resolve_trace_id(request)
    envelope = ErrorEnvelope(
        code=code,
        component=component,
        trace_id=trace_id,
        reason=reason,
        hint=hint,
        budgets=budgets,
        details=details,
    )
    return JSONResponse(status_code=status_code, content=envelope.as_payload())


def _resolve_trace_id(request: Request) -> str:
    trace_id = getattr(request.state, "cognitive_trace_id", None)
    if trace_id:
        return str(trace_id)
    trace_id = uuid.uuid4().hex
    request.state.cognitive_trace_id = trace_id
    return trace_id


def _parse_topics(raw_topics: str) -> list[str]:
    topics = [topic.strip() for topic in raw_topics.split(",") if topic.strip()]
    if not topics:
        raise ValueError("At least one topic is required")
    return topics


def _serialize_qos_budgets(qos: QoSContext) -> dict[str, int]:
    return {
        "fanout": max(0, int(qos.fanout_budget)),
        "top_k": max(0, int(qos.top_k_budget)),
    }


def _emit_qos_budget_event(
    request: Request,
    *,
    payload: AckRequest,
    cap: str,
    reason: str,
    budgets: Mapping[str, int],
    hint: str | None = None,
) -> None:
    emitter = getattr(request.app.state, "observability_emitter", None)
    if not isinstance(emitter, ObservabilityEmitter):
        return

    event_payload: dict[str, Any] = {
        "event": "sse_ack_qos_budget_exhausted",
        "trace_id": _resolve_trace_id(request),
        "subscriber_id": payload.subscriber_id,
        "tenant_id": payload.tenant_id,
        "space_id": payload.space_id,
        "topic": payload.topic,
        "cap": cap,
        "reason": reason,
        "budgets": {str(key): int(value) for key, value in budgets.items()},
    }
    if hint:
        event_payload["hint"] = hint
    emitter.emit(event_payload)


def _resolve_band(request: Request) -> str:
    header = request.headers.get("X-SSE-Band")
    if not header:
        return "GREEN"
    candidate = header.strip().upper()
    if candidate in {"GREEN", "AMBER", "RED"}:
        return candidate
    return "GREEN"


def _parse_ack_timestamp(value: str) -> datetime:
    candidate = value.strip()
    if not candidate:
        raise ValueError("ack_ts must not be empty")
    if candidate.endswith("Z") or candidate.endswith("z"):
        candidate = f"{candidate[:-1]}+00:00"
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@router.get("/sse.subscribe")
async def subscribe(
    request: Request,
    topics: str = Query(..., description="Comma separated topic filters"),
    space_id: str = Query(...),
    tenant_id: str = Query(...),
    cursor_token: str | None = Query(None),
    qos: QoSContext = Depends(qos_context_dependency),
) -> Response:
    """Stream WAL entries as SSE events with ACL enforcement."""

    try:
        topic_list = _parse_topics(topics)
    except ValueError as exc:
        return _error_response(
            request=request,
            status_code=status.HTTP_400_BAD_REQUEST,
            code="SSE_BAD_REQUEST",
            reason="TOPICS_REQUIRED",
            hint=str(exc),
        )

    try:
        subscriber_id = _resolve_subscriber_id(request)
    except ValueError as exc:
        return _error_response(
            request=request,
            status_code=status.HTTP_400_BAD_REQUEST,
            code="SSE_BAD_REQUEST",
            reason="SUBSCRIBER_ID_REQUIRED",
            hint=str(exc),
        )

    update_log_context(
        tenant_id=tenant_id,
        space_id=space_id,
        subscriber_id=subscriber_id,
        sse_topics=",".join(topic_list),
    )

    observability_emitter = cast(ObservabilityEmitter, request.app.state.observability_emitter)
    wal = request.app.state.write_ahead_log
    offset_store = request.app.state.offset_store

    server = SSEServer(
        wal=wal,
        offset_store=offset_store,
        observability=observability_emitter,
        acl_path=request.app.state.settings.sse_acl_path,
        qos=qos,
    )

    roles = _resolve_roles(request)

    try:
        rows, permitted_topics = server.subscribe(
            tenant_id=tenant_id,
            space_id=space_id,
            subscriber_id=subscriber_id,
            topics=topic_list,
            roles=roles,
            cursor_token=cursor_token,
        )
    except ValidationError as exc:  # pragma: no cover - defensive clause
        return _error_response(
            request=request,
            status_code=status.HTTP_400_BAD_REQUEST,
            code="SSE_CURSOR_INVALID",
            reason="CURSOR_INVALID",
            hint=str(exc),
        )
    except Exception as exc:
        return _error_response(
            request=request,
            status_code=status.HTTP_400_BAD_REQUEST,
            code="SSE_CURSOR_INVALID",
            reason="CURSOR_INVALID",
            hint=str(exc),
        )

    trace_id = _resolve_trace_id(request)
    metrics = server.evaluate_backpressure(
        subscriber_id=subscriber_id,
        tenant_id=tenant_id,
        space_id=space_id,
        topics=permitted_topics,
    )

    metrics_exporter = getattr(request.app.state, "metrics_exporter", None)
    if isinstance(metrics_exporter, MetricsExporter):
        lag_seconds = max(metrics.lag_ms, 0) / 1000.0
        try:
            metrics_exporter.observe(
                "sse_delivery_lag_seconds",
                lag_seconds,
                labels={"port": "sse", "level": metrics.level},
            )
            metrics_exporter.set_gauge(
                "sse_pending_events",
                float(metrics.pending_events),
                port="sse",
                level=metrics.level,
            )
        except Exception:  # pragma: no cover - defensive metrics guard
            pass

    throttle_ratio = 1.0
    advisory_payload: dict[str, Any] | None = None

    if metrics.level == "shed":
        _emit_backpressure_event(
            emitter=observability_emitter,
            trace_id=trace_id,
            metrics=metrics,
            subscriber_id=subscriber_id,
            tenant_id=tenant_id,
            space_id=space_id,
            action="shed",
            throttle_ratio=0.0,
        )
        return _error_response(
            request=request,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="SSE_BACKPRESSURE",
            reason="BACKPRESSURE_SHED",
            details={
                "level": metrics.level,
                "lag_ms": metrics.lag_ms,
                "pending_events": metrics.pending_events,
                "ack_offsets": {
                    topic: int(offset) for topic, offset in metrics.ack_offsets.items()
                },
            },
        )

    if metrics.level == "throttle":
        throttle_ratio = 0.5
        advisory_payload = _serialize_backpressure_advisory(
            metrics=metrics,
            advisory_type="throttled",
            subscriber_id=subscriber_id,
            tenant_id=tenant_id,
            space_id=space_id,
            throttle_ratio=throttle_ratio,
        )
        _emit_backpressure_event(
            emitter=observability_emitter,
            trace_id=trace_id,
            metrics=metrics,
            subscriber_id=subscriber_id,
            tenant_id=tenant_id,
            space_id=space_id,
            action="throttled",
            throttle_ratio=throttle_ratio,
        )
    elif metrics.level == "warning":
        advisory_payload = _serialize_backpressure_advisory(
            metrics=metrics,
            advisory_type="lag-warning",
            subscriber_id=subscriber_id,
            tenant_id=tenant_id,
            space_id=space_id,
        )
        _emit_backpressure_event(
            emitter=observability_emitter,
            trace_id=trace_id,
            metrics=metrics,
            subscriber_id=subscriber_id,
            tenant_id=tenant_id,
            space_id=space_id,
            action="lag-warning",
            throttle_ratio=throttle_ratio,
        )
    else:
        _emit_backpressure_event(
            emitter=observability_emitter,
            trace_id=trace_id,
            metrics=metrics,
            subscriber_id=subscriber_id,
            tenant_id=tenant_id,
            space_id=space_id,
            action="normal",
            throttle_ratio=throttle_ratio,
        )

    deliver_rows = rows
    if throttle_ratio < 1.0 and rows:
        limited = max(1, int(len(rows) * throttle_ratio))
        deliver_rows = rows[:limited]

    async def event_stream() -> AsyncIterator[str]:
        # Issue #046: Track active SSE subscriptions
        sse_count_attr = "sse_connection_count"
        if hasattr(request.app.state, sse_count_attr):
            current_count = getattr(request.app.state, sse_count_attr, 0)
            setattr(request.app.state, sse_count_attr, current_count + 1)

            # Issue #046: Emit sse_active_subscriptions metric
            if isinstance(metrics_exporter, MetricsExporter):
                try:
                    metrics_exporter.set_gauge("sse_active_subscriptions", float(current_count + 1))
                except Exception:  # noqa: BLE001
                    pass  # Don't fail SSE on metrics error

        try:
            if advisory_payload is not None:
                advisory_data = json.dumps(advisory_payload)
                yield f"event: advisory\ndata: {advisory_data}\n\n"

            for entry in deliver_rows:
                cursor = server.build_cursor(
                    subscriber_id=subscriber_id,
                    tenant_id=tenant_id,
                    space_id=space_id,
                    topic=entry.topic,
                    offset=int(entry.position or 0),
                    commit_ts=str(entry.commit_ts),
                )

                # Gap 20: Parse policy_stamp from WAL entry for audit trail
                policy_stamp_dict = None
                if entry.policy_stamp_json:
                    try:
                        policy_stamp_dict = json.loads(entry.policy_stamp_json)
                    except json.JSONDecodeError:
                        pass  # Skip malformed policy stamps

                payload = SSETraceEvent(
                    cursor=cursor,
                    topic=entry.topic,
                    wal_pos=int(entry.position or 0),
                    commit_ts=str(entry.commit_ts),
                    policy_stamp=policy_stamp_dict,
                )
                event_data = json.dumps(payload.model_dump())
                yield f"event: trace\ndata: {event_data}\n\n"
        finally:
            # Issue #046: Track connection end - always runs even if client disconnects
            if hasattr(request.app.state, sse_count_attr):
                current_count = getattr(request.app.state, sse_count_attr, 0)
                new_count = max(0, current_count - 1)
                setattr(request.app.state, sse_count_attr, new_count)

                # Issue #046: Emit sse_active_subscriptions metric
                if isinstance(metrics_exporter, MetricsExporter):
                    try:
                        metrics_exporter.set_gauge("sse_active_subscriptions", float(new_count))
                    except Exception:  # noqa: BLE001
                        pass  # Don't fail SSE cleanup on metrics error

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _resolve_roles(request: Request) -> Sequence[str]:
    roles_header = request.headers.get("X-SSE-Roles")
    if not roles_header:
        return ["household_device"]
    roles = [role.strip() for role in roles_header.split(",") if role.strip()]
    return roles or ["household_device"]


@router.post(
    "/sse.ack",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def acknowledge(
    payload: AckRequest,
    request: Request,
    qos: QoSContext = Depends(qos_context_dependency),
) -> Response | JSONResponse:
    initial_fanout = qos.fanout_budget

    try:
        qos.consume_fanout(1)
    except QoSBudgetError:
        budgets = _serialize_qos_budgets(qos)
        _emit_qos_budget_event(
            request,
            payload=payload,
            cap="fanout",
            reason="FANOUT_BUDGET_EXHAUSTED",
            budgets=budgets,
        )
        return _error_response(
            request=request,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="QOS_BUDGET_EXHAUSTED",
            component=KERNEL_COMPONENT_QOS,
            reason="FANOUT_BUDGET_EXHAUSTED",
            budgets=budgets,
            details={"cap": "fanout"},
        )

    band = _resolve_band(request)
    scheduler_token: SchedulerToken | None = None

    try:
        try:
            update_log_context(
                tenant_id=payload.tenant_id,
                space_id=payload.space_id,
                subscriber_id=payload.subscriber_id,
                sse_topic=payload.topic,
            )
            trace_id = getattr(request.state, "cognitive_trace_id", None)
            if trace_id:
                update_log_context(cognitive_trace_id=str(trace_id))
            scheduler_token = qos.acquire(band=band, port="sse", cost=1)
        except SchedulerCapacityError as exc:
            qos.fanout_budget = initial_fanout
            budgets = _serialize_qos_budgets(qos)
            hint = str(exc)
            _emit_qos_budget_event(
                request,
                payload=payload,
                cap="scheduler",
                reason="SCHEDULER_CAPACITY_EXHAUSTED",
                budgets=budgets,
                hint=hint,
            )
            return _error_response(
                request=request,
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                code="QOS_BUDGET_EXHAUSTED",
                component=KERNEL_COMPONENT_QOS,
                reason="SCHEDULER_CAPACITY_EXHAUSTED",
                hint=hint,
                budgets=budgets,
                details={"cap": "scheduler"},
            )

        if payload.ack_ts:
            try:
                ack_ts = _parse_ack_timestamp(payload.ack_ts)
            except ValueError as exc:
                qos.fanout_budget = initial_fanout
                return _error_response(
                    request=request,
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="SSE_BAD_REQUEST",
                    reason="ACK_TS_INVALID",
                    hint=str(exc),
                )
        else:
            ack_ts = datetime.now(tz=timezone.utc)

        server = SSEServer(
            wal=request.app.state.write_ahead_log,
            offset_store=request.app.state.offset_store,
            observability=request.app.state.observability_emitter,
            acl_path=request.app.state.settings.sse_acl_path,
            qos=qos,
        )
        server.acknowledge(
            subscriber_id=payload.subscriber_id,
            tenant_id=payload.tenant_id,
            space_id=payload.space_id,
            topic=payload.topic,
            offset=payload.offset,
            ack_ts=ack_ts,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    finally:
        # Issue #011 (Gap 29): Ensure scheduler token released exactly once on all exit paths
        if scheduler_token is not None:
            scheduler_token.release()
