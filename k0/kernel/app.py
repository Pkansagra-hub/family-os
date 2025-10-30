"""FastAPI application factory for the K0 kernel."""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path
from time import perf_counter
from typing import Any, AsyncIterator, Awaitable, Callable, Mapping, Sequence, cast

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from nacl.signing import SigningKey
from opentelemetry.trace import SpanKind, Status, StatusCode
from prometheus_client import PlatformCollector, ProcessCollector
from starlette.responses import Response

from ..automation.migrate import MigrationError, apply_migrations
from ..bus import (
    BusDispatcher,
    BusMiddleware,
    latency_metrics_middleware,
    timestamp_middleware,
    tracing_middleware,
)
from ..drivers import AliasMap
from ..gate import MinimalGate
from ..gate.schema_registry import SchemaRegistry
from ..idem import IdempotencyLedger
from ..obs import (
    CONTENT_TYPE_LATEST,
    MetricsExporter,
    ObservabilityEmitter,
    TracerFactory,
    bind_log_context,
    reset_log_context,
    update_log_context,
)
from ..outbox import DriverWorkerPool, RetryScheduler
from ..ports import command, drivers, observe, query, sse
from ..receipts import ReceiptIssuer, ReceiptSigner
from ..storage import (
    OffsetStore,
    OutboxStore,
    ProvisioningLedger,
    ReceiptStore,
    WriteAheadLog,
)
from ..storage.dlq import DeadLetterQueue
from ..storage.replayer import Replayer, ReplayError
from ..uow import UnitOfWork
from ..uow.connection_pool import configure_pool, shutdown_pool
from .admission import AdmissionRecord, consume_admission_records
from .config import KernelSettings
from .dependencies import build_request_dependencies
from .readiness import ReadinessState

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


def _classify_operation(route_path: str, method: str) -> str:
    """Map HTTP route + method combinations to logical operations for SLO metrics."""

    normalized_path = route_path.lower()

    if normalized_path == "/k0/command.submit":
        return "command"
    if normalized_path == "/k0/query.recall":
        return "query"
    if normalized_path == "/k0/sse.subscribe":
        return "sse_subscribe"
    if normalized_path == "/k0/sse.ack":
        return "sse_ack"
    if normalized_path == "/k0/driver.handshake":
        return "driver_handshake"
    if normalized_path in {"/healthz", "/readyz", "/metrics"}:
        return "internal"

    return "other"


def create_app(settings: KernelSettings | None = None) -> FastAPI:
    """Create a FastAPI application configured for the kernel.

    The factory wires shared dependencies and registers the privileged
    routers. Concrete business logic is intentionally deferred; each
    router returns a standardized `501 NOT IMPLEMENTED` envelope until the
    corresponding milestone lands.
    """

    settings = settings or KernelSettings.default()
    telemetry_settings = settings.telemetry
    tracer_factory = TracerFactory(
        service_name="k0-kernel",
        service_version=settings.version,
        environment=settings.environment,
        otlp_endpoint=telemetry_settings.otlp_endpoint,
        otlp_headers=telemetry_settings.otlp_headers,
        sample_ratio=telemetry_settings.trace_sample_ratio,
    )

    observability_emitter = ObservabilityEmitter()
    metrics_exporter = MetricsExporter(
        namespace=telemetry_settings.metrics_namespace,
        observability_emitter=observability_emitter,
    )

    # Register process metrics collectors for CPU/Memory monitoring
    # CRITICAL: Must store collectors at module or app state level to prevent GC
    # ProcessCollector and PlatformCollector auto-register with the registry
    try:
        # Store collectors in a persistent location (app.state will hold them)
        logger.debug("Registering ProcessCollector to registry: %s", metrics_exporter.registry)
        _process_collector = ProcessCollector(registry=metrics_exporter.registry)
        logger.debug("Registering PlatformCollector to registry: %s", metrics_exporter.registry)
        _platform_collector = PlatformCollector(registry=metrics_exporter.registry)
        logger.info("Successfully registered ProcessCollector and PlatformCollector")
        logger.debug("ProcessCollector: %s", _process_collector)
        logger.debug("PlatformCollector: %s", _platform_collector)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to register process metrics collectors: %s", e)
        _process_collector = None
        _platform_collector = None

    # Register deployment info for Grafana annotations
    deployment_info = metrics_exporter.gauge(
        "deployment_info",
        "Deployment metadata for annotation tracking",
        labelnames=("version", "environment"),
    )
    deployment_info.labels(
        version=settings.version,
        environment=getattr(settings, "environment", "local"),
    ).set(1)

    # Register missing metrics for dashboard panels
    # WAL snapshot watermark (timestamp of latest snapshot)
    snapshot_watermark = metrics_exporter.gauge(
        "snapshot_watermark",
        "Unix timestamp of the latest WAL snapshot",
    )
    snapshot_watermark.set(0)  # Will be updated by snapshot jobs

    # Active HTTP connections gauge
    active_connections = metrics_exporter.gauge(
        "active_connections",
        "Number of active HTTP connections",
    )
    active_connections.set(0)  # Will be updated by middleware

    # Active SSE subscriptions gauge
    sse_active_subscriptions = metrics_exporter.gauge(
        "sse_active_subscriptions",
        "Number of active SSE subscription connections",
    )
    sse_active_subscriptions.set(0)  # Will be updated by SSE endpoint

    # Bus dispatch latency histogram
    bus_dispatch_latency = metrics_exporter.histogram(
        "bus_dispatch_latency",
        "Event bus dispatch latency in seconds",
        labelnames=("driver",),
        buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
    )

    dependency_provider = build_request_dependencies(
        settings=settings,
        tracer_factory=tracer_factory,
    )

    schema_registry = SchemaRegistry()
    provisioning_ledger = ProvisioningLedger()
    write_ahead_log = WriteAheadLog()
    outbox_store = OutboxStore(metrics=metrics_exporter)
    dead_letter_queue = DeadLetterQueue()
    offset_store = OffsetStore()
    receipt_store = ReceiptStore()
    receipt_signer = ReceiptSigner(SigningKey.generate())
    receipt_issuer = ReceiptIssuer(
        receipt_store=receipt_store,
        signer=receipt_signer,
        metrics_recorder=metrics_exporter.emit,
        observability_emitter=observability_emitter,
    )
    minimal_gate = MinimalGate(
        registry=schema_registry,
        provisioning=provisioning_ledger,
        metrics=metrics_exporter,
        observability=observability_emitter,
    )
    idempotency_ledger = IdempotencyLedger(
        metrics=metrics_exporter,
        observability=observability_emitter,
    )

    alias_map = AliasMap.from_file()
    driver_worker_pool = DriverWorkerPool(
        alias_map=alias_map,
        outbox_store=outbox_store,
        dead_letter_queue=dead_letter_queue,
        retry_scheduler_factory=lambda: RetryScheduler(),
        metrics_emitter=metrics_exporter.emit,
    )

    bus_settings = getattr(settings, "bus", None)
    middleware_settings = getattr(bus_settings, "middleware", None) if bus_settings else None
    timestamps_enabled = (
        bool(getattr(middleware_settings, "timestamps_enabled", True))
        if middleware_settings is not None
        else True
    )
    metrics_enabled = (
        bool(getattr(middleware_settings, "metrics_enabled", True))
        if middleware_settings is not None
        else True
    )
    tracing_enabled = (
        bool(getattr(middleware_settings, "tracing_enabled", True))
        if middleware_settings is not None
        else True
    )

    bus_middlewares: list[BusMiddleware] = []
    if timestamps_enabled:
        bus_middlewares.append(timestamp_middleware())
    if metrics_enabled:
        bus_middlewares.append(latency_metrics_middleware(metrics_exporter))
    if tracing_enabled:
        bus_middlewares.append(tracing_middleware(tracer_factory=tracer_factory))

    bus_dispatcher = BusDispatcher(
        scheduler=dependency_provider.scheduler,
        middlewares=bus_middlewares,
    )

    app = FastAPI(title="K0 Kernel", version=settings.version)
    app.state.settings = settings
    app.state.tracer_factory = tracer_factory
    app.state.metrics_exporter = metrics_exporter
    app.state.forwarded_metrics = observe.ForwardedMetricsBuffer()
    app.state.snapshot_watermark = snapshot_watermark
    app.state.active_connections = active_connections
    app.state.sse_active_subscriptions = sse_active_subscriptions
    app.state.sse_connection_count = 0  # Atomic counter for active SSE connections
    app.state.bus_dispatch_latency = bus_dispatch_latency
    app.state.process_collector = _process_collector
    app.state.platform_collector = _platform_collector
    app.state.scheduler = dependency_provider.scheduler
    app.state.readiness = ReadinessState()
    app.state.schema_registry = schema_registry
    app.state.provisioning_ledger = provisioning_ledger
    app.state.write_ahead_log = write_ahead_log
    app.state.outbox_store = outbox_store
    app.state.dead_letter_queue = dead_letter_queue
    app.state.offset_store = offset_store
    app.state.receipt_store = receipt_store
    app.state.receipt_issuer = receipt_issuer
    app.state.minimal_gate = minimal_gate
    app.state.idempotency_ledger = idempotency_ledger
    app.state.observability_emitter = observability_emitter
    app.state.alias_map = alias_map
    app.state.driver_worker_pool = driver_worker_pool
    app.state.bus_dispatcher = bus_dispatcher

    def _unit_of_work_factory() -> UnitOfWork:
        return UnitOfWork(
            outbox_store=outbox_store,
            write_ahead_log=write_ahead_log,
            receipt_store=receipt_store,
            offset_store=offset_store,
            metrics_emitter=metrics_exporter.emit,
            metrics_exporter=metrics_exporter,
            snapshot_watermark_gauge=lambda ts: snapshot_watermark.set(ts),
            wal_fsync_mode=settings.database.fsync_mode,
        )

    app.state.unit_of_work_factory = _unit_of_work_factory

    _install_middlewares(app, settings, tracer_factory)
    _register_exception_handlers(app)
    _register_operational_probes(app)

    app.dependency_overrides.update(dependency_provider.as_fastapi_overrides())

    app.include_router(command.router)
    app.include_router(query.router)
    app.include_router(sse.router)
    app.include_router(observe.router)
    app.include_router(drivers.router)

    database_path = Path(getattr(settings.database, "path"))
    configure_pool(database_path)

    def _bootstrap_runtime() -> None:
        readiness = getattr(app.state, "readiness", None)
        try:
            apply_migrations(database_path, logger=logger)
            if readiness is not None:
                readiness.mark_migrations_complete()
        except MigrationError:
            logger.exception(
                "Database migration failed during startup",
                extra={"database_path": str(database_path)},
            )
            raise

        replayer = Replayer(
            schema_registry=getattr(app.state, "schema_registry"),
            metrics=getattr(app.state, "metrics_exporter", None),
            observability=getattr(app.state, "observability_emitter", None),
        )
        try:
            replayer.run(from_position=0)
        except ReplayError:
            logger.exception("WAL replay failed during startup")
            raise
        if readiness is not None:
            readiness.mark_wal_replay_complete()

    try:
        _bootstrap_runtime()
    finally:
        shutdown_pool()

    configure_pool(database_path)

    async def _report_sse_metrics_periodically() -> None:
        """Background task to periodically report SSE connection metrics."""
        while True:
            try:
                await asyncio.sleep(15)  # Report every 15 seconds
                sse_gauge = getattr(app.state, "sse_active_subscriptions", None)
                sse_count = getattr(app.state, "sse_connection_count", 0)
                if sse_gauge is not None:
                    sse_gauge.set(sse_count)
            except asyncio.CancelledError:
                logger.debug("SSE metrics reporter cancelled")
                break
            except Exception:  # noqa: BLE001
                logger.exception("Failed to report SSE metrics")

    @asynccontextmanager
    async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Start background task for SSE metrics reporting
        sse_metrics_task = asyncio.create_task(_report_sse_metrics_periodically())
        try:
            yield
        finally:
            # Cancel background task
            sse_metrics_task.cancel()
            try:
                await sse_metrics_task
            except asyncio.CancelledError:
                pass
            shutdown_pool()

    app.router.lifespan_context = _lifespan

    return app


def _install_middlewares(
    app: FastAPI,
    settings: KernelSettings,
    tracer_factory: TracerFactory,
) -> None:
    cors_origins = _resolve_cors_origins(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Cognitive-Trace-Id"],
    )

    @app.middleware("http")
    async def telemetry_chain(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming_trace_id = request.headers.get("X-Cognitive-Trace-Id")
        trace_id = incoming_trace_id.strip() if incoming_trace_id else tracer_factory.new_trace_id()
        request.state.cognitive_trace_id = trace_id

        extracted_context = tracer_factory.extract(request.headers)
        baggage_token = tracer_factory.attach_cognitive_trace(trace_id)

        route = request.scope.get("route")
        route_path = str(getattr(route, "path", request.url.path))
        operation = _classify_operation(route_path, request.method)

        tenant_header = request.headers.get("X-Tenant-Id")
        space_header = request.headers.get("X-Space-Id")
        device_header = request.headers.get("X-Device-Id")
        subject_header = request.headers.get("X-Subject-Id")

        log_context_token = bind_log_context(
            cognitive_trace_id=trace_id,
            http_method=request.method,
            http_route=route_path,
            http_operation=operation,
            tenant_id=tenant_header,
            space_id=space_header,
            device_id=device_header,
            subject_id=subject_header,
        )

        attributes: dict[str, Any] = {
            "http.method": request.method,
            "http.route": route_path,
            "http.scheme": request.url.scheme,
            "http.target": request.url.path,
            "http.url": str(request.url),
            "k0.cognitive_trace_id": trace_id,
        }
        if request.client:
            attributes["net.peer.ip"] = request.client.host
            attributes["net.peer.port"] = request.client.port
        user_agent = request.headers.get("user-agent")
        if user_agent:
            attributes["http.user_agent"] = user_agent

        metrics_exporter = getattr(app.state, "metrics_exporter", None)
        start_time = perf_counter()
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

        try:
            with tracer_factory.span(
                f"{request.method} {route_path}",
                kind=SpanKind.SERVER,
                attributes=attributes,
                context_override=extracted_context,
            ) as span:
                try:
                    response = await call_next(request)
                    status_code = response.status_code
                    update_log_context(http_status=status_code)
                except Exception as exc:  # pragma: no cover - recorded below
                    span.record_exception(exc)
                    span.set_attribute("http.status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
                    span.set_status(Status(status_code=StatusCode.ERROR))
                    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
                    raise

                span.set_attribute("http.status_code", response.status_code)
                if response.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
                    span.set_status(Status(status_code=StatusCode.ERROR))
                else:
                    span.set_status(Status(status_code=StatusCode.OK))
            response.headers.setdefault("X-Cognitive-Trace-Id", trace_id)
            return response
        finally:
            tracer_factory.detach(baggage_token)
            if isinstance(metrics_exporter, MetricsExporter):
                duration = max(perf_counter() - start_time, 0.0)
                labels: dict[str, str] = {
                    "route": route_path,
                    "method": request.method,
                    "operation": operation,
                }
                try:
                    metrics_exporter.observe(
                        "http_request_latency_seconds",
                        duration,
                        labels=labels,
                    )
                    outcome_label = "success" if 200 <= status_code < 400 else "error"
                    metrics_exporter.emit(
                        "http_requests_total",
                        1.0,
                        route=route_path,
                        method=request.method,
                        status=str(status_code),
                        outcome=outcome_label,
                        operation=operation,
                    )
                except Exception:  # pragma: no cover - defensive metrics guard
                    logger.exception(
                        "Failed to emit HTTP request metric",
                        extra={"route": route_path, "method": request.method},
                    )
            reset_log_context(log_context_token)

    _ = telemetry_chain

    def _process_admission_records(request: Request, error: Exception | None = None) -> None:
        records: list[AdmissionRecord] = consume_admission_records(request)
        if not records:
            return

        receipt_store = getattr(app.state, "receipt_store", None)
        observability_emitter = getattr(app.state, "observability_emitter", None)
        metrics_exporter = getattr(app.state, "metrics_exporter", None)
        receipt_saver = getattr(receipt_store, "save", None) if receipt_store else None
        observability_emit = (
            getattr(observability_emitter, "emit", None) if observability_emitter else None
        )
        metrics_emit = getattr(metrics_exporter, "emit", None) if metrics_exporter else None
        trace_id = _ensure_trace_id(request)

        for record in records:
            decision_label = "allow" if record.decision.admit else "deny"
            obligations = [obligation.name for obligation in record.decision.obligations]
            obligation_details = [
                dict(obligation.details) for obligation in record.decision.obligations
            ]

            update_log_context(
                tenant_id=record.envelope.get("tenant_id"),
                space_id=record.envelope.get("space_id"),
                device_id=record.envelope.get("device_id"),
                admission_port=record.port,
                admission_decision=decision_label,
            )

            if record.receipt and callable(receipt_saver):
                try:
                    receipt_saver(record.receipt)
                except Exception:  # pragma: no cover - logging guard
                    logger.exception(
                        "Failed to persist receipt for admission decision",
                        extra={"receipt_id": record.receipt.receipt_id},
                    )

            event_payload: dict[str, Any] = {
                "trace_id": trace_id,
                "port": record.port,
                "decision": decision_label,
                "deny_reason": record.decision.deny_reason,
                "obligations": obligations,
                "obligation_details": obligation_details,
                "tenant_id": record.envelope.get("tenant_id"),
                "space_id": record.envelope.get("space_id"),
                "band": record.envelope.get("band"),
            }
            if record.receipt:
                event_payload["receipt_id"] = record.receipt.receipt_id
                event_payload["wal_pos"] = record.receipt.wal_pos
            if error is not None:
                event_payload["error"] = error.__class__.__name__

            if callable(observability_emit):
                try:
                    observability_emit(event_payload)
                except Exception:  # pragma: no cover - logging guard
                    logger.exception(
                        "Failed to emit observability admission event",
                        extra={"decision": decision_label},
                    )

            if callable(metrics_emit):
                try:
                    metrics_emit(
                        "admission_decisions_total",
                        1.0,
                        port=record.port,
                        decision=decision_label,
                    )
                except Exception:  # pragma: no cover - logging guard
                    logger.exception(
                        "Failed to emit admission decision metric",
                        extra={"decision": decision_label},
                    )

    @app.middleware("http")
    async def admission_audit_chain(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        error: Exception | None = None
        try:
            response = await call_next(request)
            return response
        except Exception as exc:  # pragma: no cover - bubbling to exception handlers
            error = exc
            raise
        finally:
            try:
                _process_admission_records(request, error=error)
            except Exception:  # pragma: no cover - logging guard
                logger.exception("Admission audit processing failed")

    _ = admission_audit_chain


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        trace_id = _ensure_trace_id(request)
        default_code = _status_code_to_kernel_code(exc.status_code)
        default_reason = _default_reason(exc.status_code)
        payload = _normalize_error_payload(exc.detail, trace_id, default_code, default_reason)

        headers = exc.headers if exc.headers else None
        if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            logger.exception("HTTPException triggered internal error response", exc_info=exc)
        return JSONResponse(status_code=exc.status_code, content=payload, headers=headers)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        trace_id = _ensure_trace_id(request)
        logger.exception("Unhandled exception bubbled to FastAPI", exc_info=exc)
        payload = _compose_error("UNEXPECTED_ERROR", "Internal server error", trace_id)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=payload)

    _ = (http_exception_handler, unhandled_exception_handler)


def _register_operational_probes(app: FastAPI) -> None:
    @app.get("/healthz", summary="Kernel liveness probe")
    async def healthz() -> dict[str, str]:
        settings_obj = getattr(app.state, "settings", KernelSettings.default())
        metrics_exporter = getattr(app.state, "metrics_exporter", None)
        if isinstance(metrics_exporter, MetricsExporter):
            metrics_exporter.set_gauge(
                "kernel_health_status",
                1.0,
                version=settings_obj.version,
            )
        return {
            "status": "ok",
            "version": settings_obj.version,
        }

    @app.get(
        "/readyz",
        summary="Kernel readiness probe",
        responses={
            status.HTTP_200_OK: {"description": "Kernel is ready"},
            status.HTTP_503_SERVICE_UNAVAILABLE: {
                "description": "Kernel is not ready",
            },
        },
    )
    async def readyz() -> JSONResponse:
        readiness_state = getattr(app.state, "readiness", None)
        if not isinstance(readiness_state, ReadinessState):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "code": "READINESS_STATE_UNAVAILABLE",
                    "reason": "Readiness tracker not initialized",
                },
            )

        snapshot = readiness_state.snapshot()
        metrics_exporter = getattr(app.state, "metrics_exporter", None)
        if isinstance(metrics_exporter, MetricsExporter):
            metrics_exporter.set_gauge(
                "kernel_ready_state",
                1.0 if snapshot.ready else 0.0,
            )
            metrics_exporter.set_gauge(
                "kernel_readiness_component_state",
                1.0 if snapshot.migrations_applied else 0.0,
                component="migrations_applied",
            )
            metrics_exporter.set_gauge(
                "kernel_readiness_component_state",
                1.0 if snapshot.wal_replay_complete else 0.0,
                component="wal_replay_complete",
            )

        payload: dict[str, Any] = {
            "ready": snapshot.ready,
            "components": snapshot.asdict(),
        }
        status_code = status.HTTP_200_OK if snapshot.ready else status.HTTP_503_SERVICE_UNAVAILABLE
        return JSONResponse(status_code=status_code, content=payload)

    @app.get("/metrics", summary="Prometheus metrics endpoint")
    async def metrics() -> Response:
        metrics_exporter = getattr(app.state, "metrics_exporter", None)
        if isinstance(metrics_exporter, MetricsExporter):
            latest = metrics_exporter.latest()
            forwarded_buffer = getattr(app.state, "forwarded_metrics", None)
            forwarded_snapshot = (
                forwarded_buffer.render()
                if isinstance(forwarded_buffer, observe.ForwardedMetricsBuffer)
                else ""
            )
            content = latest
            if forwarded_snapshot:
                forwarded_bytes = forwarded_snapshot.encode("utf-8")
                if not content.endswith(b"\n"):
                    content += b"\n"
                content += forwarded_bytes
            return Response(content=content, media_type=CONTENT_TYPE_LATEST)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "METRICS_EXPORTER_UNAVAILABLE",
                "reason": "Metrics exporter not configured",
            },
        )

    _ = (healthz, readyz, metrics)


def _resolve_cors_origins(settings: KernelSettings) -> list[str]:
    origins = getattr(settings, "allowed_origins", None)
    if origins is None:
        return ["*"]
    if isinstance(origins, str):
        return [origins]
    if isinstance(origins, Sequence):
        origins_seq = cast(Sequence[Any], origins)
        return [str(origin) for origin in origins_seq]
    return [str(origins)]


def _ensure_trace_id(request: Request) -> str:
    trace_id = getattr(request.state, "cognitive_trace_id", None)
    if trace_id:
        return trace_id
    tracer_factory = getattr(getattr(request.app, "state", None), "tracer_factory", None)
    if isinstance(tracer_factory, TracerFactory):
        trace_id = tracer_factory.new_trace_id()
    else:
        trace_id = uuid.uuid4().hex
    request.state.cognitive_trace_id = trace_id
    return trace_id


def _status_code_to_kernel_code(status_code: int) -> str:
    mapping = {
        status.HTTP_400_BAD_REQUEST: "REJECTED_KERNEL_GATE",
        status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
        status.HTTP_403_FORBIDDEN: "PEP_DENY",
        status.HTTP_404_NOT_FOUND: "NOT_FOUND",
        status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
        status.HTTP_409_CONFLICT: "IDEMPOTENT_DUPLICATE",
        status.HTTP_429_TOO_MANY_REQUESTS: "QOS_BUDGET_EXCEEDED",
    }
    return mapping.get(status_code, "HTTP_ERROR")


def _default_reason(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "HTTP error"


def _normalize_error_payload(
    detail: Any,
    trace_id: str,
    default_code: str,
    default_reason: str,
) -> dict[str, Any]:
    if isinstance(detail, Mapping):
        detail_mapping = cast(Mapping[str, Any], detail)
        if "error" in detail_mapping and isinstance(detail_mapping["error"], Mapping):
            error_mapping = cast(Mapping[str, Any], detail_mapping["error"])
            error_content = dict(error_mapping)
            error_content.setdefault("code", default_code)
            error_content.setdefault("reason", default_reason)
            error_content["trace_id"] = trace_id
            return {"error": error_content}
        code = str(detail_mapping.get("code", default_code))
        reason = str(
            detail_mapping.get("reason") or detail_mapping.get("message") or default_reason
        )
        hint = detail_mapping.get("hint")
        budgets = detail_mapping.get("budgets")
        return _compose_error(code, reason, trace_id, hint=hint, budgets=budgets)
    reason = str(detail) if detail else default_reason
    return _compose_error(default_code, reason, trace_id)


def _compose_error(
    code: str,
    reason: str,
    trace_id: str,
    *,
    hint: Any | None = None,
    budgets: Any | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "reason": reason,
        "trace_id": trace_id,
    }
    if hint:
        error["hint"] = hint
    if budgets:
        error["budgets"] = budgets
    return {"error": error}
