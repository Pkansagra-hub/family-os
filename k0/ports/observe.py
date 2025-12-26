"""HTTP handlers for the observability port (`/k0/obs.emit`)."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from contextlib import nullcontext
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from opentelemetry.trace import SpanKind, Status, StatusCode
from pydantic import BaseModel, Field

from k0.obs.tracing import TracerFactory
from k0.ports.errors import KERNEL_COMPONENT_OBSERVE, ErrorEnvelope

router = APIRouter(prefix="/k0", tags=["observability"])


try:  # pragma: no cover - structlog optional in tests
    import structlog  # type: ignore

    logger = structlog.get_logger(__name__)
except ImportError:  # pragma: no cover - fallback to stdlib logging
    logger = logging.getLogger(__name__)


class ForwardedMetricsBuffer:
    """Keep the most recent forwarded metrics snapshot in Prometheus format."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._snapshot: str | None = None
        self._captured_at: str | None = None
        self._source: str | None = None
        self._received_at: datetime | None = None
        self._trace_id: str | None = None

    def update(
        self,
        *,
        snapshot: str,
        captured_at: str | None = None,
        source: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        stripped = snapshot.strip()
        with self._lock:
            if not stripped:
                self._snapshot = None
                self._captured_at = None
                self._source = None
                self._received_at = datetime.now(timezone.utc)
                self._trace_id = trace_id
                return
            self._snapshot = stripped
            self._captured_at = captured_at
            self._source = source
            self._received_at = datetime.now(timezone.utc)
            self._trace_id = trace_id

    def render(self) -> str:
        with self._lock:
            snapshot = self._snapshot
            captured_at = self._captured_at
            source = self._source
            received_at = self._received_at
            trace_id = self._trace_id
        if not snapshot:
            return ""

        metadata = [f"# forwarded_metrics source={source or 'k1_bridge'}"]
        if captured_at:
            metadata.append(f" captured_at={captured_at}")
        if received_at:
            metadata.append(f" received_at={received_at.isoformat()}")
        if trace_id:
            metadata.append(f" trace_id={trace_id}")
        header_line = "".join(metadata)
        payload = snapshot.rstrip("\n") + "\n"
        return f"{header_line}\n{payload}"


class ObservabilityPayload(BaseModel):
    """Envelope used to carry metrics/spans/log batches."""

    kind: str = Field(..., description="telemetry batch type")
    body: dict[str, Any]


@router.post("/obs.emit", status_code=status.HTTP_204_NO_CONTENT)
async def emit(payload: ObservabilityPayload, request: Request) -> Response:
    """Accept telemetry batches from K1 bridge."""

    app_state = getattr(request, "app", None)
    tracer_factory = getattr(getattr(app_state, "state", None), "tracer_factory", None)
    trace_header = request.headers.get("X-Cognitive-Trace-Id")
    trace_id = trace_header.strip() if trace_header else None
    token = None

    if isinstance(tracer_factory, TracerFactory):
        extracted_context = tracer_factory.extract(request.headers)
        trace_id = trace_id or tracer_factory.new_trace_id()
        token = tracer_factory.attach_cognitive_trace(trace_id)
        span_cm = tracer_factory.span(
            "k0.observe.emit",
            kind=SpanKind.SERVER,
            attributes={"telemetry.kind": payload.kind},
            context_override=extracted_context,
        )
    else:
        trace_id = trace_id or uuid.uuid4().hex
        span_cm = nullcontext(None)

    request.state.cognitive_trace_id = trace_id

    error_payload: ErrorEnvelope | None = None
    status_code = status.HTTP_204_NO_CONTENT

    with span_cm as span:
        try:
            if payload.kind == "metrics":
                body = payload.body if isinstance(payload.body, dict) else {}
                snapshot = body.get("snapshot")
                if not isinstance(snapshot, str) or not snapshot.strip():
                    error_payload = ErrorEnvelope(
                        code="INVALID_PAYLOAD",
                        component=KERNEL_COMPONENT_OBSERVE,
                        trace_id=trace_id,
                        reason="MISSING_SNAPSHOT",
                        hint="Metrics payload must include non-empty 'snapshot' string.",
                    )
                    status_code = status.HTTP_400_BAD_REQUEST
                else:
                    buffer = getattr(request.app.state, "forwarded_metrics", None)
                    if isinstance(buffer, ForwardedMetricsBuffer):
                        captured_at = body.get("captured_at")
                        source = body.get("source") or "k1_bridge"
                        buffer.update(
                            snapshot=snapshot,
                            captured_at=(str(captured_at) if captured_at is not None else None),
                            source=str(source),
                            trace_id=trace_id,
                        )
                        if span is not None:
                            span.set_attribute("telemetry.metrics_forwarded", True)
                    else:
                        logger.warning(
                            "forwarded_metrics_buffer_missing",
                            component=KERNEL_COMPONENT_OBSERVE,
                        )
            elif payload.kind == "logs":
                body = payload.body if isinstance(payload.body, dict) else {}
                entries = body.get("entries")
                if not isinstance(entries, list):
                    error_payload = ErrorEnvelope(
                        code="INVALID_PAYLOAD",
                        component=KERNEL_COMPONENT_OBSERVE,
                        trace_id=trace_id,
                        reason="MISSING_ENTRIES",
                        hint="Log payload must include an 'entries' list.",
                    )
                    status_code = status.HTTP_400_BAD_REQUEST
                else:
                    _ingest_forwarded_logs(entries, trace_id)
                    if span is not None:
                        span.set_attribute("telemetry.log_entries", len(entries))
            elif payload.kind == "feedback":
                body = payload.body if isinstance(payload.body, dict) else {}
                if not body:
                    error_payload = ErrorEnvelope(
                        code="INVALID_PAYLOAD",
                        component=KERNEL_COMPONENT_OBSERVE,
                        trace_id=trace_id,
                        reason="MISSING_ENVELOPE",
                        hint="Feedback payload body must be a non-empty feedback envelope object.",
                    )
                    status_code = status.HTTP_400_BAD_REQUEST
                else:
                    from k0.db.connection import connection_scope
                    from k0.feedback.envelope import FeedbackEnvelope
                    from k0.feedback.schema_registry import FeedbackSchemaRegistry

                    try:
                        envelope = FeedbackEnvelope.model_validate(body)
                    except Exception as exc:  # noqa: BLE001 - surface validation error
                        error_payload = ErrorEnvelope(
                            code="INVALID_PAYLOAD",
                            component=KERNEL_COMPONENT_OBSERVE,
                            trace_id=trace_id,
                            reason="INVALID_FEEDBACK_ENVELOPE",
                            hint=str(exc),
                        )
                        status_code = status.HTTP_400_BAD_REQUEST
                    else:
                        if envelope.tenant_id is None or envelope.space_id is None:
                            error_payload = ErrorEnvelope(
                                code="INVALID_PAYLOAD",
                                component=KERNEL_COMPONENT_OBSERVE,
                                trace_id=trace_id,
                                reason="MISSING_TENANT_SPACE",
                                hint="Feedback envelope must include tenant_id and space_id.",
                            )
                            status_code = status.HTTP_400_BAD_REQUEST
                        else:
                            _ensure_builtin_feedback_payload_schemas(envelope.pipeline_id)

                            registered_schema = FeedbackSchemaRegistry.get_schema(
                                envelope.pipeline_id
                            )
                            payload_validation_status = "unvalidated"
                            payload_validation_error: str | None = None

                            if registered_schema is not None:
                                ok, err = FeedbackSchemaRegistry.validate(
                                    envelope.pipeline_id,
                                    envelope.payload,
                                    permissive_unregistered=False,
                                )
                                if ok:
                                    payload_validation_status = "valid"
                                else:
                                    payload_validation_status = "invalid"
                                    payload_validation_error = _truncate_error(err)

                            trace_to_store = envelope.trace_id or trace_id
                            session_to_store = envelope.session_id
                            if session_to_store is None:
                                session_to_store = envelope.correlation.session_id

                            correlation = envelope.correlation.model_dump(mode="json")
                            provenance = envelope.provenance or {}
                            metadata = envelope.metadata or {}

                            payload_hash = _sha256_json(envelope.payload)
                            event_ts = envelope.event_timestamp or envelope.timestamp

                            try:
                                async with connection_scope() as conn:
                                    await conn.execute(
                                        """
                                        INSERT INTO st_feedback_signals (
                                            feedback_id,
                                            pipeline_id,
                                            tenant_id,
                                            space_id,
                                            signal_class,
                                            signal_subtype,
                                            source,
                                            source_component,
                                            session_id,
                                            trace_id,
                                            correlation,
                                            provenance,
                                            payload,
                                            payload_hash,
                                            metadata,
                                            payload_validation_status,
                                            payload_validation_error,
                                            priority,
                                            event_timestamp
                                        ) VALUES (
                                            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19
                                        )
                                        ON CONFLICT (feedback_id) DO NOTHING
                                        """,
                                        str(envelope.feedback_id),
                                        envelope.pipeline_id,
                                        envelope.tenant_id,
                                        envelope.space_id,
                                        str(envelope.signal_class),
                                        envelope.signal_subtype,
                                        (
                                            str(envelope.source)
                                            if envelope.source is not None
                                            else None
                                        ),
                                        envelope.source_component,
                                        session_to_store,
                                        trace_to_store,
                                        correlation,
                                        provenance,
                                        envelope.payload,
                                        payload_hash,
                                        metadata,
                                        payload_validation_status,
                                        payload_validation_error,
                                        float(envelope.priority),
                                        event_ts,
                                    )
                            except Exception as exc:  # noqa: BLE001 - defensive guard
                                logger.exception("feedback_ingest_failed")
                                error_payload = ErrorEnvelope(
                                    code="INGESTION_FAILED",
                                    component=KERNEL_COMPONENT_OBSERVE,
                                    trace_id=trace_id,
                                    reason="DB_WRITE_FAILED",
                                    hint=str(exc),
                                )
                                status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
                            else:
                                if span is not None:
                                    span.set_attribute("feedback.pipeline_id", envelope.pipeline_id)
                                    span.set_attribute(
                                        "feedback.payload_validation", payload_validation_status
                                    )
            else:
                error_payload = ErrorEnvelope(
                    code="UNSUPPORTED_KIND",
                    component=KERNEL_COMPONENT_OBSERVE,
                    trace_id=trace_id,
                    reason="UNSUPPORTED_KIND",
                    hint="Supported kinds: metrics, logs, feedback.",
                )
                status_code = status.HTTP_400_BAD_REQUEST

            if error_payload and span is not None:
                span.set_status(
                    Status(status_code=StatusCode.ERROR, description=error_payload.reason)
                )
        finally:
            if isinstance(tracer_factory, TracerFactory) and token is not None:
                tracer_factory.detach(token)

    if error_payload:
        return JSONResponse(status_code=status_code, content=error_payload.as_payload())

    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _sha256_json(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _truncate_error(error: str | None, max_len: int = 512) -> str | None:
    if not error:
        return None
    error = str(error)
    if len(error) <= max_len:
        return error
    return error[: max_len - 3] + "..."


def _ensure_builtin_feedback_payload_schemas(pipeline_id: str) -> None:
    """Register builtin payload schemas for implemented pipelines.

    The registry is intentionally not auto-populated at import time because
    tests and future rollouts rely on being able to reset the registry.
    """

    from k0.feedback.schema_registry import FeedbackSchemaRegistry

    pid = pipeline_id.strip().upper()
    if pid not in {"P02", "P08"}:
        return

    if FeedbackSchemaRegistry.get_schema(pid) is not None:
        return

    from k0.feedback.payloads import P02FeedbackPayload, P08FeedbackPayload

    if pid == "P02":
        FeedbackSchemaRegistry.register_pydantic(pid, P02FeedbackPayload)
    elif pid == "P08":
        FeedbackSchemaRegistry.register_pydantic(pid, P08FeedbackPayload)


def _ingest_forwarded_logs(entries: list[Any], fallback_trace_id: str) -> None:
    for entry in entries:
        if not isinstance(entry, dict):
            logger.warning(
                "forwarded_log_invalid",
                component=KERNEL_COMPONENT_OBSERVE,
                cognitive_trace_id=fallback_trace_id,
                entry_type=type(entry).__name__,
            )
            continue

        message = str(entry.get("message", ""))
        level = str(entry.get("level", "INFO")).lower()
        event_name = entry.get("event") or "k1_forwarded_log"
        log_callable = getattr(logger, level, None)
        if not callable(log_callable):
            log_callable = logger.info

        extras = {k: v for k, v in entry.items() if k not in {"message", "level", "event"}}
        extras.setdefault(
            "cognitive_trace_id", entry.get("cognitive_trace_id") or fallback_trace_id
        )
        extras.setdefault("forwarded", True)

        log_target = getattr(log_callable, "__self__", None)
        if isinstance(log_target, logging.Logger):
            extra_payload = dict(extras)
            extra_payload["forwarded_message"] = message
            log_callable(event_name, extra=extra_payload)
        else:
            log_callable(event_name, forwarded_message=message, **extras)
