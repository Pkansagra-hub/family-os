from __future__ import annotations

import json
import logging
import uuid
from contextlib import contextmanager, nullcontext
from io import StringIO
from types import SimpleNamespace
from typing import Any, Callable, Iterator
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.requests import Request
from ward import test  # type: ignore[attr-defined]

from k0.bus.core import BusDispatchContext, BusMessage
from k0.bus.middleware import tracing_middleware
from k0.gate import MinimalGate
from k0.kernel.app import create_app
from k0.kernel.config import KernelSettings
from k0.obs.logging import (
    _LOG_CONTEXT,
    bind_log_context,
    configure_structured_logging,
    reset_log_context,
    update_log_context,
)
from k0.obs.tracing import TracerFactory
from k0.ports.command import submit_command
from k0.ports.sse import AckRequest, acknowledge
from k0.qos import QoSContext, Scheduler


def _build_request(
    *,
    app_state: SimpleNamespace,
    method: str,
    path: str,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> Request:
    headers_list: list[tuple[bytes, bytes]] = []
    if headers:
        headers_list = [
            (key.lower().encode("latin-1"), value.encode("latin-1"))
            for key, value in headers.items()
        ]

    scope: dict[str, Any] = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "headers": headers_list,
        "scheme": "http",
        "client": ("testclient", 80),
        "app": SimpleNamespace(state=app_state),
    }

    payload = body or b""
    sent = False

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if not sent:
            sent = True
            return {
                "type": "http.request",
                "body": payload,
                "more_body": False,
            }
        return {"type": "http.disconnect"}

    return Request(scope, receive)


def _log_records(stream: StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


@test("structured formatter redacts PII and captures context")
def _() -> None:
    stream = StringIO()
    configure_structured_logging(stream=stream, level="DEBUG", force=True)

    logger = logging.getLogger("test.obs.logging.redaction")
    logger.debug(
        "Provisioning user foo@example.com with id 123456789",
        extra={
            "tenant_email": "foo@example.com",
            "phone": "1234567890",
            "nested": {"ssn": "123456789"},
        },
    )

    payload = json.loads(stream.getvalue().splitlines()[-1])
    assert payload["message"].count("[REDACTED]") >= 1
    context = payload["context"]
    assert context["tenant_email"] == "[REDACTED]"
    assert context["phone"] == "[REDACTED]"
    assert context["nested"]["ssn"] == "[REDACTED]"


@test("structured logging injects the active cognitive trace identifier")
def _() -> None:
    stream = StringIO()
    configure_structured_logging(stream=stream, level="INFO", force=True)

    tracer_factory = TracerFactory(
        service_name="test-service",
        service_version="0.0-test",
        environment="test",
        otlp_endpoint=None,
    )

    trace_id = tracer_factory.new_trace_id()
    token = tracer_factory.attach_cognitive_trace(trace_id)
    try:
        logging.getLogger("test.obs.logging.trace").info("Tracing log emission")
    finally:
        tracer_factory.detach(token)

    payload = json.loads(stream.getvalue().splitlines()[-1])
    assert payload["cognitive_trace_id"] == trace_id


@test("structured logging honours custom sensitive keys and mask overrides")
def _() -> None:
    stream = StringIO()
    configure_structured_logging(
        stream=stream,
        level="INFO",
        sensitive_keys=["tenant_id"],
        mask="***",
        force=True,
    )

    logger = logging.getLogger("test.obs.logging.custom_keys")
    logger.info("Logging with tenant context", extra={"tenant_id": "tenant-123"})

    payload = json.loads(stream.getvalue().splitlines()[-1])
    context = payload.get("context", {})
    assert context["tenant_id"] == "***"


@test("binding structured log context injects metadata and redacts sensitive fields")
def _() -> None:
    stream = StringIO()
    configure_structured_logging(stream=stream, level="INFO", force=True)

    token = bind_log_context(
        cognitive_trace_id="trace-ctx-123",
        http_route="/k0/test",
        tenant_id="tenant-xyz",
    )
    update_log_context(space_id="space-abc")

    try:
        logging.getLogger("test.obs.logging.context").info("Context-bound log")
    finally:
        reset_log_context(token)

    payload = json.loads(stream.getvalue().splitlines()[-1])
    assert payload["cognitive_trace_id"] == "trace-ctx-123"
    context = payload.get("context", {})
    assert context["http_route"] == "/k0/test"
    assert context["tenant_id"] == "[REDACTED]"
    assert context["space_id"] == "[REDACTED]"


@test("resetting log context clears bound metadata for subsequent records")
def _() -> None:
    stream = StringIO()
    configure_structured_logging(stream=stream, level="INFO", force=True)

    token = bind_log_context(tenant_id="tenant-123")
    logging.getLogger("test.obs.logging.reset").info("Before reset")
    reset_log_context(token)
    logging.getLogger("test.obs.logging.reset").info("After reset")

    lines = stream.getvalue().splitlines()
    first = json.loads(lines[-2])
    second = json.loads(lines[-1])

    assert first["context"]["tenant_id"] == "[REDACTED]"
    assert "tenant_id" not in second.get("context", {})


@test("bus tracing middleware propagates trace and context to structured logs")
async def _() -> None:
    stream = StringIO()
    configure_structured_logging(stream=stream, level="INFO", force=True)

    tracer_factory = TracerFactory(
        service_name="test-bus-service",
        service_version="0.0-test",
        environment="test",
        otlp_endpoint=None,
    )

    middleware = tracing_middleware(tracer_factory=tracer_factory)
    context = BusDispatchContext(
        message=BusMessage(
            topic="memory.command",
            payload=b"{}",
            offset=42,
            trace_id="trace-bus-abc",
        ),
        band="GREEN",
        port="bus",
        token_cost=1,
    )

    async def _handler(_: BusDispatchContext) -> None:
        logging.getLogger("test.obs.logging.bus").info("Dispatching message")

    await middleware(context, _handler)
    logging.getLogger("test.obs.logging.bus").info("Post-dispatch log")

    lines = stream.getvalue().splitlines()
    first = json.loads(lines[-2])
    second = json.loads(lines[-1])

    assert first["cognitive_trace_id"] == "trace-bus-abc"
    bus_context = first.get("context", {})
    assert bus_context["bus_topic"] == "memory.command"
    assert bus_context["bus_offset"] == 42
    assert bus_context["bus_port"] == "bus"

    assert "bus_topic" not in second.get("context", {})


@test("http telemetry middleware binds request context and clears post-response")
def _() -> None:
    stream = StringIO()
    configure_structured_logging(stream=stream, level="INFO", force=True)

    app = create_app(KernelSettings.default())

    @app.get("/__obs-http-test")
    async def _handler() -> dict[str, str]:
        logging.getLogger("test.obs.logging.http").info("HTTP middleware handler log")
        return {"status": "ok"}

    headers = {
        "X-Cognitive-Trace-Id": "trace-http-abc",
        "X-Tenant-Id": "tenant-http",
        "X-Space-Id": "space-http",
        "X-Device-Id": "device-http",
        "X-Subject-Id": "subject-http",
    }

    with TestClient(app) as client:
        response = client.get("/__obs-http-test", headers=headers)
        assert response.status_code == 200
        logging.getLogger("test.obs.logging.http").info("HTTP middleware post log")

    records = _log_records(stream)
    handler_record = next(
        record
        for record in records
        if record["message"] == "HTTP middleware handler log"
    )
    post_record = next(
        record for record in records if record["message"] == "HTTP middleware post log"
    )

    assert handler_record["cognitive_trace_id"] == "trace-http-abc"
    context = handler_record.get("context", {})
    assert context["http_method"] == "GET"
    assert context["http_route"] == "/__obs-http-test"
    assert context["tenant_id"] == "[REDACTED]"
    assert context["device_id"] == "[REDACTED]"
    assert post_record.get("context", {}).get("tenant_id") is None

    _LOG_CONTEXT.set({})


@test("command port binds envelope metadata into structured logs on rejection")
async def _() -> None:
    stream = StringIO()
    configure_structured_logging(stream=stream, level="INFO", force=True)

    tracer_factory = TracerFactory(
        service_name="test-command-service",
        service_version="0.0-test",
        environment="test",
        otlp_endpoint=None,
    )

    minimal_gate = MinimalGate()

    @contextmanager
    def _fake_connection_scope() -> Iterator[None]:
        yield None

    rejection = SimpleNamespace(accepted=False, reason="TEST_REJECTION", idem_key=None)

    with patch.object(minimal_gate, "validate", return_value=rejection):
        app_state = SimpleNamespace(
            minimal_gate=minimal_gate,
            tracer_factory=tracer_factory,
            metrics_exporter=None,
            observability_emitter=None,
        )
        provisioning_stub = object()
        receipt_stub = object()

        envelope: dict[str, object] = {
            "cognitive_trace_id": str(uuid.uuid4()),
            "tenant_id": "tenant-command",
            "space_id": "space-command",
            "topic": "memory.test",
            "schema_uri": "urn:schema:test",
            "schema_version": "1.0.0",
            "actor": "actor-1",
            "device_id": "device-1",
            "band": "GREEN",
            "policy_version": "1.0.0",
            "ts": "2025-10-01T12:00:00Z",
            "sig": "test-signature",
            "idem_key": None,
            "payload_sha256": "0" * 64,
        }

        body = json.dumps(envelope).encode()
        request = _build_request(
            app_state=app_state,
            method="POST",
            path="/k0/command.submit",
            headers={"content-type": "application/json"},
            body=body,
        )

        qos = QoSContext(scheduler=Scheduler(), fanout_budget=3, top_k_budget=8)

        def _fake_get_state_component(
            request_obj: Request, attribute: str, expected_type: type[Any]
        ) -> Any:
            if attribute == "minimal_gate":
                return minimal_gate
            if attribute == "provisioning_ledger":
                return provisioning_stub
            if attribute == "receipt_issuer":
                return receipt_stub
            if attribute == "idempotency_ledger":
                return object()  # Stub for idempotency_ledger
            raise RuntimeError(f"Unexpected component access: {attribute}")

        def _fake_get_unit_of_work_factory(_request_obj: Request) -> Callable[[], Any]:
            def _factory() -> Any:
                def _append_wal(*args: Any, **kwargs: Any) -> int:
                    return 0

                def _stage_outbox(*args: Any, **kwargs: Any) -> None:
                    return None

                unit_of_work = SimpleNamespace(
                    append_wal=_append_wal,
                    stage_outbox=_stage_outbox,
                    connection=None,
                )
                return nullcontext(unit_of_work)

            return _factory

        with patch("k0.ports.command.connection_scope", _fake_connection_scope), patch(
            "k0.ports.command._get_state_component", _fake_get_state_component
        ), patch(
            "k0.ports.command._get_unit_of_work_factory", _fake_get_unit_of_work_factory
        ):
            await submit_command(request, qos=qos)

    logging.getLogger("test.obs.logging.command").info(
        "Command port instrumentation log"
    )

    records = _log_records(stream)
    record = next(
        entry
        for entry in records
        if entry["message"] == "Command port instrumentation log"
    )

    assert record["cognitive_trace_id"] == envelope["cognitive_trace_id"]
    context = record.get("context", {})
    assert context["tenant_id"] == "[REDACTED]"
    assert context["space_id"] == "[REDACTED]"
    assert context["topic"] == "memory.test"
    assert context["schema_uri"] == "urn:schema:test"
    assert context["actor"] == "[REDACTED]"

    _LOG_CONTEXT.set({})


@test("sse acknowledge binds subscriber context to structured logs")
async def _() -> None:
    stream = StringIO()
    configure_structured_logging(stream=stream, level="INFO", force=True)

    tracer_factory = TracerFactory(
        service_name="test-sse-service",
        service_version="0.0-test",
        environment="test",
        otlp_endpoint=None,
    )

    class _Emitter:
        def __init__(self) -> None:
            self.events: list[dict[str, Any]] = []

        def emit(self, payload: dict[str, Any]) -> None:
            self.events.append(payload)

    app_state = SimpleNamespace(
        tracer_factory=tracer_factory,
        write_ahead_log=object(),
        offset_store=object(),
        observability_emitter=_Emitter(),
        settings=SimpleNamespace(sse_acl_path="tests/fixtures/acl.yaml"),
        metrics_exporter=None,
    )

    request = _build_request(
        app_state=app_state,
        method="POST",
        path="/k0/sse.ack",
        headers={
            "x-sse-band": "GREEN",
            "x-sse-subscriber": "subscriber-1",
        },
    )

    payload = AckRequest(
        subscriber_id="subscriber-1",
        topic="memory.topic",
        space_id="space-sse",
        tenant_id="tenant-sse",
        offset=42,
        ack_ts="2025-10-01T12:00:00Z",
    )

    qos = QoSContext(scheduler=Scheduler(), fanout_budget=5, top_k_budget=3)

    class _FakeServer:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.kwargs = kwargs
            self.ack_calls: list[dict[str, Any]] = []

        def acknowledge(self, **kwargs: Any) -> None:
            self.ack_calls.append(kwargs)

    fake_servers: list[_FakeServer] = []

    def _server_factory(*args: Any, **kwargs: Any) -> _FakeServer:
        server = _FakeServer(*args, **kwargs)
        fake_servers.append(server)
        return server

    with patch("k0.ports.sse.SSEServer", side_effect=_server_factory):
        request.state.cognitive_trace_id = "trace-sse-ack"
        await acknowledge(payload, request, qos)

    logging.getLogger("test.obs.logging.sse").info("SSE ack instrumentation log")

    records = _log_records(stream)
    record = next(
        entry for entry in records if entry["message"] == "SSE ack instrumentation log"
    )

    assert record["cognitive_trace_id"] == "trace-sse-ack"
    context = record.get("context", {})
    assert context["tenant_id"] == "[REDACTED]"
    assert context["space_id"] == "[REDACTED]"
    assert context["subscriber_id"] == "[REDACTED]"
    assert context["sse_topic"] == "memory.topic"

    _LOG_CONTEXT.set({})
