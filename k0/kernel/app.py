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

from ..bus import (
    BusDispatcher,
    BusMessage,
    BusMiddleware,
    latency_metrics_middleware,
    timestamp_middleware,
    tracing_middleware,
)
from ..config.postgres import PostgresSettings
from ..db.pool import configure_pool, shutdown_pool
from ..drivers import AliasMap
from ..gate import MinimalGate
from ..gate.schema_registry import SchemaRegistry
from ..gate.topic_body_validator import TopicBodyValidator
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
from ..ports import admin, command, drivers, observe, query, sse
from ..ports.topic_router import TopicRouter
from ..qos import QoSMetrics
from ..receipts import ReceiptIssuer, ReceiptSigner
from ..storage import (
    DeadLetterQueue,
    ObligationStore,
    OffsetStore,
    OutboxStore,
    ProvisioningLedger,
    ReceiptStore,
    WriteAheadLog,
)
from ..storage.replayer import Replayer, ReplayError
from ..uow import UnitOfWork
from .admission import AdmissionRecord, consume_admission_records
from .config import KernelSettings
from .dependencies import build_request_dependencies
from .readiness import ReadinessState

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# Issue #046: Global counter for active HTTP connections
_active_connections = 0


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

    # Create QoS metrics instrumentation
    qos_metrics = QoSMetrics(metrics_exporter)

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
        "bus_dispatch_latency_seconds",
        "Event bus dispatch latency in seconds",
        labelnames=("topic", "outcome"),
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
    obligation_store = ObligationStore()
    offset_store = OffsetStore()
    receipt_store = ReceiptStore()
    receipt_signer = ReceiptSigner(SigningKey.generate())
    receipt_issuer = ReceiptIssuer(
        receipt_store=receipt_store,
        signer=receipt_signer,
        metrics_recorder=metrics_exporter.emit,
        observability_emitter=observability_emitter,
    )
    # M2 Epic 2.10/2.11: Topic-aware body validation
    topic_body_validator = TopicBodyValidator()

    minimal_gate = MinimalGate(
        registry=schema_registry,
        provisioning=provisioning_ledger,
        max_clock_skew_seconds=settings.gate.max_clock_skew_seconds,
        max_envelope_bytes=settings.gate.max_envelope_bytes,
        max_body_bytes=settings.gate.max_body_bytes,
        metrics=metrics_exporter,
        observability=observability_emitter,
        topic_body_validator=topic_body_validator,
    )
    idempotency_ledger = IdempotencyLedger(
        metrics=metrics_exporter,
        observability=observability_emitter,
    )

    alias_map = AliasMap.from_file()

    # Gap 38: Read DLQ max retry attempts from config
    dlq_settings = getattr(settings, "dlq", None)
    max_retry_attempts = (
        int(getattr(dlq_settings, "max_retry_attempts", 10)) if dlq_settings is not None else 10
    )

    driver_worker_pool = DriverWorkerPool(
        alias_map=alias_map,
        outbox_store=outbox_store,
        dead_letter_queue=dead_letter_queue,
        retry_scheduler_factory=lambda: RetryScheduler(),
        metrics_emitter=metrics_exporter.emit,
        max_retry_attempts=max_retry_attempts,
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
    app.state.qos_metrics = qos_metrics
    app.state.forwarded_metrics = observe.ForwardedMetricsBuffer()
    app.state.snapshot_watermark = snapshot_watermark
    app.state.active_connections = active_connections
    app.state.sse_active_subscriptions = sse_active_subscriptions
    app.state.sse_connection_count = 0  # Atomic counter for active SSE connections
    app.state.bus_dispatch_latency = bus_dispatch_latency
    app.state.process_collector = _process_collector
    app.state.platform_collector = _platform_collector

    # Inject QoS metrics into scheduler
    scheduler = dependency_provider.scheduler
    scheduler._qos_metrics = qos_metrics
    app.state.scheduler = scheduler
    app.state.readiness = ReadinessState()
    app.state.schema_registry = schema_registry
    app.state.provisioning_ledger = provisioning_ledger
    app.state.write_ahead_log = write_ahead_log
    app.state.outbox_store = outbox_store
    app.state.obligation_store = obligation_store
    app.state.dead_letter_queue = dead_letter_queue
    app.state.offset_store = offset_store
    app.state.receipt_store = receipt_store
    app.state.receipt_issuer = receipt_issuer
    app.state.minimal_gate = minimal_gate
    app.state.topic_body_validator = topic_body_validator
    app.state.topic_router = TopicRouter()
    app.state.idempotency_ledger = idempotency_ledger
    app.state.observability_emitter = observability_emitter
    app.state.alias_map = alias_map
    app.state.driver_worker_pool = driver_worker_pool
    app.state.bus_dispatcher = bus_dispatcher

    # Inject bus dispatcher into appropriate driver for WAL/outbox operations
    if settings.database.backend == "postgresql":
        from ..drivers.postgres import set_bus_dispatcher
    else:
        from ..drivers.archived.sqlite import set_bus_dispatcher

    set_bus_dispatcher(bus_dispatcher)

    # Register BusDispatcher sinks (Gap 1: Wire BusDispatcher Sinks)
    # M1 R1.2: Migrated from register_sink() to tap() / subscribe()

    # Sink 1: Observability - emit bus_dispatch events with trace_id
    async def observability_sink(message: BusMessage) -> None:
        """Emit observability events for bus dispatches with trace_id."""
        try:
            observability_emitter.emit(
                {
                    "event_type": "bus_dispatch",
                    "topic": message.topic,
                    "offset": message.offset,
                    "trace_id": message.trace_id,
                    "payload_size": len(message.payload),
                }
            )
        except Exception:  # pragma: no cover - defensive logging guard
            logger.exception("Failed to emit observability event for bus dispatch")

    # Sink 2: DriverWorkerPool trigger - trigger outbox processing
    async def driver_worker_pool_sink(message: BusMessage) -> None:
        """Trigger outbox processing when WAL commits occur."""
        # Note: This sink notifies the worker pool that new entries may be available.
        # Actual processing happens in background loop (Gap 19)
        try:
            # For now, this is a no-op placeholder. The background worker loop
            # will handle periodic processing. Future enhancement could add
            # event-driven triggers here if needed.
            pass
        except Exception:  # pragma: no cover - defensive logging guard
            logger.exception("Failed to trigger driver worker pool")

    # Sink 3: SSE fan-out - broadcasts bus events to SSE subscribers
    # Note: SSE server is initialized during lifespan startup, so we need to
    # lazily access it via app.state.sse_server
    async def sse_fan_out_sink(message: BusMessage) -> None:
        """Fan out WAL events to SSE subscribers via SSE server broadcast."""
        try:
            # Lazily get SSE server from app state (initialized in lifespan)
            sse_server = getattr(app.state, "sse_server", None)
            if sse_server is None:
                return  # SSE server not available yet or disabled

            # Only broadcast pipeline events (not internal system events)
            if not message.topic or message.topic.startswith("internal."):
                return

            # Import BroadcastEvent here to avoid circular import
            # Parse payload
            import json

            from ..sse.server import BroadcastEvent

            try:
                payload = json.loads(message.payload.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload = {"raw": message.payload.decode("utf-8", errors="replace")}

            # Create broadcast event
            event = BroadcastEvent(
                topic=message.topic,
                tenant_id=message.metadata.get("tenant_id", "default"),
                space_id=message.space_id or "default",
                op_kind=message.topic.upper().replace(".", "_"),
                payload=payload,
            )

            # Broadcast to subscribers
            await sse_server.broadcast(event)

        except Exception:  # pragma: no cover - defensive logging guard
            logger.exception("Failed to fan out to SSE subscribers")

    # M1 R1.2: Use tap() for observability (gets ALL messages)
    bus_dispatcher.tap(observability_sink)

    # M1 R1.2: Use subscribe("*") for driver worker pool (wildcard for all topics)
    bus_dispatcher.subscribe("*", driver_worker_pool_sink)

    # M1 R1.2: Use subscribe("*") for SSE fan-out (wildcard for all topics)
    bus_dispatcher.subscribe("*", sse_fan_out_sink)

    # M2 R2.3: Initialize pipelines state (will be populated during lifespan startup)
    app.state.pipelines = {}

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

    # Admin router - only in non-production mode
    # Security: Admin endpoints expose internal scheduler state and manual triggers
    # These should NEVER be accessible in production deployments
    if settings.environment.lower() != "production":
        app.include_router(admin.router)
        logger.info(
            "Admin router enabled (non-production mode)",
            extra={"environment": settings.environment},
        )

    # PostgreSQL settings for async pool initialization (done in lifespan)
    postgres_settings = PostgresSettings()
    app.state.postgres_settings = postgres_settings

    async def _bootstrap_runtime_async() -> None:
        """Async bootstrap: migrations and WAL replay."""
        readiness = getattr(app.state, "readiness", None)

        # Apply migrations using Alembic
        # Run in a thread pool to avoid event loop conflicts with Alembic's async migrations
        try:
            from concurrent.futures import ThreadPoolExecutor
            from pathlib import Path

            from alembic import command
            from alembic.config import Config

            def run_migrations_sync() -> None:
                """Run Alembic migrations in a separate thread with its own event loop."""
                alembic_cfg = Config()
                alembic_cfg.set_main_option(
                    "script_location", str(Path(__file__).parent.parent / "db" / "alembic")
                )
                alembic_cfg.set_main_option("sqlalchemy.url", postgres_settings.dsn)
                command.upgrade(alembic_cfg, "head")

            # Run migrations in a thread pool to get a fresh event loop
            loop = asyncio.get_running_loop()
            with ThreadPoolExecutor(max_workers=1) as pool:
                await loop.run_in_executor(pool, run_migrations_sync)

            if readiness is not None:
                readiness.mark_migrations_complete()
            logger.info("PostgreSQL migrations applied successfully")
        except Exception as e:
            logger.exception(
                "Database migration failed during startup",
                extra={"error": str(e)},
            )
            raise

        replayer = Replayer(
            schema_registry=getattr(app.state, "schema_registry"),
            metrics=getattr(app.state, "metrics_exporter", None),
            observability=getattr(app.state, "observability_emitter", None),
        )
        try:
            await replayer.run(from_position=0)
        except ReplayError:
            logger.exception("WAL replay failed during startup")
            raise
        if readiness is not None:
            readiness.mark_wal_replay_complete()

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

    async def _outbox_worker_loop() -> None:
        """Background task to process outbox with exponential backoff (Gap 19)."""
        worker_pool = getattr(app.state, "driver_worker_pool", None)
        alias_map = getattr(app.state, "alias_map", None)

        if worker_pool is None or alias_map is None:
            logger.warning("Outbox worker loop cannot start: missing worker_pool or alias_map")
            return

        logger.info("Starting outbox worker loop (processing interval: 5s)")

        while True:
            try:
                await asyncio.sleep(5)  # Process every 5 seconds

                # Get all registered driver aliases from alias_map
                driver_aliases = list(alias_map.bindings.keys())

                if not driver_aliases:
                    logger.debug("No driver aliases registered, skipping outbox processing")
                    continue

                # Process each registered driver - async-native, no thread pool
                for alias in driver_aliases:
                    try:
                        await worker_pool.process_driver_async(alias)
                        logger.debug(f"Processed outbox for driver: {alias}")
                    except RuntimeError as e:  # noqa: BLE001
                        # Gracefully skip drivers that aren't implemented yet
                        error_msg = str(e)
                        if (
                            "does not expose a known factory" in error_msg
                            or "must expose an 'apply' method" in error_msg
                        ):
                            logger.debug(f"Skipping unimplemented driver: {alias} ({error_msg})")
                        else:
                            logger.exception(f"Failed to process outbox for driver: {alias}")
                    except Exception:  # noqa: BLE001
                        logger.exception(f"Failed to process outbox for driver: {alias}")

            except asyncio.CancelledError:
                logger.info("Outbox worker loop cancelled")
                break
            except Exception:  # noqa: BLE001
                logger.exception("Outbox worker loop encountered error, backing off 30s")
                try:
                    await asyncio.sleep(30)  # 30s backoff on loop exceptions
                except asyncio.CancelledError:
                    logger.info("Outbox worker loop cancelled during backoff")
                    break

    # =========================================================================
    # DEPRECATED (M4 ADR-K003 — FAISS eliminated, pgvector native)
    # =========================================================================
    # The _p08_faiss_indexer_loop() function and all FAISS references removed.
    # P08 now uses declarative triggers via PipelineScheduler (Issue 5.2.1).
    # Embedding indexing now uses pgvector HNSW natively (ADR-K003 v2.0).
    # =========================================================================

    async def _init_model_registry() -> "ModelRegistry":
        """Initialize the centralized model registry at kernel startup.

        The ModelRegistry provides:
        - Lazy loading of ML models on first use
        - GPU memory management with CPU fallback
        - Thread-safe model access
        - Model versioning

        Returns:
            ModelRegistry: Initialized model registry
        """

        from ..runtime.model_registry import init_model_registry

        config_path = Path(__file__).parent.parent / "config" / "models.yaml"

        logger.info("Initializing model registry...")
        registry = await init_model_registry(
            config_path=config_path if config_path.exists() else None,
            gpu_memory_limit_mb=4096,
            cpu_memory_limit_mb=8192,
        )

        # Preload essential models for hot path performance
        preload_models = registry.get_preload_models(include_optional=True)
        logger.info(f"Preloading {len(preload_models)} models: {preload_models}")
        results = await registry.preload(preload_models)

        for model_name, success in results.items():
            if success:
                logger.info(f"Preloaded model: {model_name}")
            else:
                logger.warning(f"Failed to preload model: {model_name}")

        logger.info(
            "Model registry initialized",
            extra={"stats": registry.get_stats()},
        )

        return registry

    async def _init_feature_flags() -> "FeatureFlags":
        """Initialize the feature flags system for ML tier selection.

        The FeatureFlags system provides:
        - Module-level ML tier selection
        - Percentage-based rollouts
        - Automatic fallback on failures
        - A/B testing metrics

        Returns:
            FeatureFlags: Initialized feature flags
        """

        from ..config.feature_flags import init_feature_flags

        config_path = Path(__file__).parent.parent / "config" / "feature_flags.yaml"

        logger.info("Initializing feature flags...")
        flags = await init_feature_flags(config_path=config_path if config_path.exists() else None)

        logger.info(
            "Feature flags initialized",
            extra={
                "modules": flags.list_modules(),
                "flags": flags.get_all_flags(),
            },
        )

        return flags

    async def _preload_models() -> dict[str, any]:
        """Legacy function for backward compatibility.

        DEPRECATED: Use _init_model_registry() instead.

        Returns:
            dict: Preloaded models with keys 'spacy_nlp' and 'vader_analyzer'
        """
        models = {}

        try:
            import spacy

            logger.info("Preloading spaCy model (en_core_web_sm)...")
            models["spacy_nlp"] = spacy.load("en_core_web_sm")
            logger.info("spaCy model preloaded successfully")
        except Exception as e:
            logger.warning(f"Failed to preload spaCy model: {e}")
            models["spacy_nlp"] = None

        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

            logger.info("Preloading VADER sentiment analyzer...")
            models["vader_analyzer"] = SentimentIntensityAnalyzer()
            logger.info("VADER sentiment analyzer preloaded successfully")
        except Exception as e:
            logger.warning(f"Failed to preload VADER analyzer: {e}")
            models["vader_analyzer"] = None

        return models

    @asynccontextmanager
    async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Phase -1: Initialize PostgreSQL connection pool (MUST be first)
        logger.info("Initializing PostgreSQL connection pool...")
        try:
            await configure_pool(
                postgres_settings,
                metrics_exporter=metrics_exporter,
            )
            logger.info("PostgreSQL pool initialized successfully")
        except Exception as e:
            logger.exception(f"Failed to initialize PostgreSQL pool: {e}")
            raise

        # Phase -0.5: Run async bootstrap (migrations + WAL replay)
        try:
            await _bootstrap_runtime_async()
        except Exception:
            # Bootstrap failed - cleanup pool before re-raising
            await shutdown_pool()
            raise

        # Ensure bus dispatcher has the running loop
        if settings.database.backend == "postgresql":
            from ..drivers.postgres import set_bus_dispatcher
        else:
            from ..drivers.archived.sqlite import set_bus_dispatcher

        set_bus_dispatcher(bus_dispatcher)

        # Phase 0: Initialize Feature Flags system
        logger.info("Initializing feature flags system...")
        feature_flags = await _init_feature_flags()
        app.state.feature_flags = feature_flags

        # Phase 0.5: Initialize SSE Server for real-time event streaming
        logger.info("Initializing SSE Server...")
        try:
            from ..drivers.sse_outbox_driver import set_sse_server
            from ..sse.server import SSEServer

            sse_server = SSEServer(
                wal=write_ahead_log,
                offset_store=offset_store,
                observability=observability_emitter,
                acl_path=settings.sse_acl_path,
                qos=dependency_provider.qos,
            )
            app.state.sse_server = sse_server

            # Wire SSE server into outbox driver
            set_sse_server(sse_server)

            logger.info(
                "SSE Server initialized",
                extra={
                    "max_batch": sse_server.max_batch,
                    "max_pending_events": sse_server.max_pending_events,
                    "disconnect_threshold": sse_server.disconnect_threshold,
                },
            )
        except Exception as e:
            logger.error(f"Failed to initialize SSE Server: {e}", exc_info=True)
            app.state.sse_server = None

        # Phase 1: Initialize Model Registry (replaces legacy _preload_models)
        logger.info("Initializing model registry...")
        model_registry = await _init_model_registry()
        app.state.model_registry = model_registry

        # Phase 1.5: Initialize UltraBERT (primary unified model)
        # UltraBERT self-warms on init (warmup=True default), no manual warmup needed
        # This replaces 9 separate models (4.6GB) with one unified 500MB model:
        # - VADER, GoEmotions, clinical_safety, sentence_transformer
        # - TransformerNER, ZeroShotClassifier, etc.
        try:
            from ..runtime.ultrabert_adapter import get_ultrabert_client, is_ultrabert_available

            logger.info("Initializing UltraBERT unified model...")
            ultrabert_client = get_ultrabert_client()
            if ultrabert_client is not None and is_ultrabert_available():
                logger.info(
                    f"UltraBERT ready: version={ultrabert_client.VERSION}, "
                    f"capabilities={len(ultrabert_client.capabilities)}, "
                    f"backend={ultrabert_client.backend}"
                )
                app.state.ultrabert_client = ultrabert_client
            else:
                logger.error("UltraBERT not available - kernel cannot function without it")
                app.state.ultrabert_client = None
        except Exception as e:
            logger.error(f"Failed to initialize UltraBERT: {e}")
            app.state.ultrabert_client = None

        # Build minimal preloaded_models dict for backward compatibility
        # Only spaCy is kept for tokenization - all ML is via UltraBERT
        preloaded_models = {
            "spacy_nlp": model_registry.get_sync("spacy_nlp"),
        }
        app.state.preloaded_models = preloaded_models
        logger.info(
            "Model initialization complete",
            extra={
                "spacy_loaded": preloaded_models.get("spacy_nlp") is not None,
                "ultrabert_ready": app.state.ultrabert_client is not None,
                "registry_stats": model_registry.get_stats(),
            },
        )

        # Phase 2: Boot YAML-based declarative pipelines via runtime system
        from pathlib import Path

        from ..pipelines.protocol import PipelineContext
        from ..runtime import ModuleRegistry, PipelineSpec, set_module_registry

        try:
            logger.info("Loading declarative pipelines from YAML specifications...")

            # Initialize module registry
            registry = ModuleRegistry()
            contracts_dir = Path(__file__).parent.parent.parent / "k0" / "contracts" / "modules"
            await registry.load_contracts(contracts_dir)
            logger.info(
                f"Loaded {len(registry)} module contracts",
                extra={"module_count": len(registry), "modules": registry.list_modules()},
            )

            # Issue 2.2.3: Set global registry and register capabilities
            set_module_registry(registry)
            from ..fabric.loader import discover_and_register_capabilities
            from ..fabric.registry import get_capability_registry

            cap_count = discover_and_register_capabilities(registry)
            capability_registry = get_capability_registry()
            logger.info(
                f"Registered {cap_count} capability providers",
                extra={
                    "provider_count": cap_count,
                    "capability_stats": capability_registry.get_stats(),
                },
            )

            # Load pipeline specifications from YAML
            pipelines_contract_dir = (
                Path(__file__).parent.parent.parent / "k0" / "contracts" / "pipelines"
            )
            pipeline_specs = list(pipelines_contract_dir.glob("p*.yaml")) + list(
                pipelines_contract_dir.glob("p*.yml")
            )
            logger.info(
                f"Found {len(pipeline_specs)} pipeline specifications",
                extra={
                    "spec_count": len(pipeline_specs),
                    "specs": [p.name for p in pipeline_specs],
                },
            )

            pipelines = {}
            for spec_path in sorted(pipeline_specs):
                try:
                    # Load and validate spec
                    spec = PipelineSpec.load(spec_path)
                    logger.info(
                        f"Loading pipeline: {spec.pipeline_id}",
                        extra={
                            "pipeline_id": spec.pipeline_id,
                            "version": spec.version,
                            "runner_type": spec.runner_type,
                            "spec_path": str(spec_path),
                        },
                    )

                    # Create pipeline runner via factory (generic dispatch)
                    from ..runtime.runner_factory import create_runner

                    runner = create_runner(spec, registry)

                    # Create syscalls adapter with required capabilities
                    from ..kernel.syscalls import Syscalls

                    # SECURITY: Only grant capabilities explicitly declared in pipeline spec
                    granted_caps = set(spec.required_caps) if spec.required_caps else set()

                    # Fail-fast: Pipelines MUST declare required_caps (no default grants)
                    if not granted_caps:
                        logger.warning(
                            f"Pipeline {spec.pipeline_id} has empty required_caps - this may indicate misconfiguration",
                            extra={
                                "pipeline_id": spec.pipeline_id,
                                "spec_path": str(spec_path),
                            },
                        )

                    syscalls = Syscalls(spec.pipeline_id, granted_caps, _unit_of_work_factory)
                    logger.info(
                        f"Syscalls initialized for {spec.pipeline_id}",
                        extra={
                            "pipeline_id": spec.pipeline_id,
                            "granted_caps": list(granted_caps),
                            "capability_count": len(granted_caps),
                        },
                    )

                    # Create pipeline context
                    ctx = PipelineContext(
                        syscalls=syscalls,
                        config=spec.config,
                        logger=logger.getChild(spec.pipeline_id),
                        preloaded_models=preloaded_models,  # Pass preloaded models to pipeline
                        bus_dispatcher=bus_dispatcher,  # For internal pipeline communication
                    )

                    # Call on_startup
                    await runner.on_startup(ctx)
                    logger.info(
                        f"Called on_startup() for {spec.pipeline_id}",
                        extra={"pipeline_id": spec.pipeline_id},
                    )

                    # Subscribe to declared topics
                    for topic in spec.declared_topics:
                        bus_dispatcher.subscribe(topic, runner.handle)
                        logger.info(
                            f"Subscribed {spec.pipeline_id} to {topic}",
                            extra={"pipeline_id": spec.pipeline_id, "topic": topic},
                        )

                    pipelines[spec.pipeline_id] = runner
                    logger.info(
                        f"Booted pipeline: {spec.pipeline_id}",
                        extra={
                            "pipeline_id": spec.pipeline_id,
                            "topics": list(spec.declared_topics),
                            "concurrency": spec.concurrency,
                            "max_queue": spec.max_queue,
                        },
                    )

                except Exception as e:
                    logger.error(
                        f"Failed to load pipeline from {spec_path.name}: {e}",
                        extra={"spec_path": str(spec_path), "error": str(e)},
                        exc_info=True,
                    )
                    # Continue loading other pipelines
                    continue

            app.state.pipelines = pipelines
            logger.info(
                f"Booted {len(pipelines)} pipelines: {list(pipelines.keys())}",
                extra={"count": len(pipelines), "pipeline_ids": list(pipelines.keys())},
            )

            # Issue 3.2.1: Initialize PipelineScheduler for trigger-based activation
            from ..scheduler import PipelineScheduler, set_pipeline_scheduler

            # Create syscalls for scheduler (needs query_count for threshold triggers)
            scheduler_caps = {"st_vec.read", "st_hipp_events.read"}  # Threshold query tables
            scheduler_syscalls = Syscalls("scheduler", scheduler_caps, _unit_of_work_factory)

            # Create scheduler with pipeline execution callback
            async def execute_pipeline_async(scheduled: Any, event: Any) -> None:
                """Execute pipeline when trigger fires (async implementation)."""
                import json
                import uuid

                from ..bus.core import BusMessage

                pipeline_id = scheduled.pipeline_id
                # Debug: Log the pipelines dict state
                logger.debug(
                    f"execute_pipeline_async called, pipelines keys: {list(pipelines.keys())}",
                    extra={"pipeline_id": pipeline_id, "pipelines_count": len(pipelines)},
                )
                runner = pipelines.get(pipeline_id)
                if runner:
                    logger.info(
                        f"Trigger-based execution of {pipeline_id}",
                        extra={
                            "pipeline_id": pipeline_id,
                            "trigger_id": event.trigger_id,
                            "execution_count": scheduled.execution_count,
                        },
                    )
                    # Create synthetic BusMessage for trigger-based execution
                    # Use the pipeline's entry_topic (e.g., scheduled.p08.trigger.v1)
                    from datetime import datetime, timezone

                    # Convert fired_at: can be float (unix ts), datetime, or None
                    fired_at_iso = None
                    if event.fired_at:
                        if isinstance(event.fired_at, (int, float)):
                            fired_at_iso = datetime.fromtimestamp(
                                event.fired_at, tz=timezone.utc
                            ).isoformat()
                        elif hasattr(event.fired_at, "isoformat"):
                            fired_at_iso = event.fired_at.isoformat()
                        else:
                            fired_at_iso = str(event.fired_at)
                    trigger_payload = {
                        "trigger_id": event.trigger_id,
                        "trigger_type": (
                            event.context.get("trigger_type", "unknown")
                            if event.context
                            else "unknown"
                        ),
                        "execution_count": scheduled.execution_count,
                        "fired_at": fired_at_iso,
                        "batch_size": (
                            event.context.get("batch_size", 100) if event.context else 100
                        ),
                        # Pass trigger context (reason, options) to pipeline runner
                        # This enables tenant_id/space_id overrides from manual triggers
                        "context": event.context or {},
                    }
                    trigger_message = BusMessage(
                        topic=(
                            runner.declared_topics[0]
                            if runner.declared_topics
                            else f"scheduled.{pipeline_id.lower()}.trigger.v1"
                        ),
                        payload=json.dumps(trigger_payload).encode("utf-8"),
                        offset=scheduled.execution_count,
                        trace_id=str(uuid.uuid4()),
                        space_id="system",
                        metadata={"trigger_id": event.trigger_id, "port": "scheduler"},
                    )
                    try:
                        await runner.handle(trigger_message)
                        logger.info(
                            f"Pipeline {pipeline_id} completed (trigger: {event.trigger_id})",
                            extra={
                                "pipeline_id": pipeline_id,
                                "trigger_id": event.trigger_id,
                                "execution_count": scheduled.execution_count,
                            },
                        )
                    except Exception as e:
                        logger.exception(
                            f"Pipeline {pipeline_id} failed (trigger: {event.trigger_id}): {e}",
                            extra={
                                "pipeline_id": pipeline_id,
                                "trigger_id": event.trigger_id,
                                "error": str(e),
                            },
                        )
                else:
                    logger.warning(
                        f"No runner found for triggered pipeline {pipeline_id}",
                        extra={"pipeline_id": pipeline_id},
                    )

            def execute_pipeline(scheduled: Any, event: Any) -> None:
                """Execute pipeline when trigger fires (sync wrapper)."""
                # Schedule the async execution on the event loop
                asyncio.create_task(execute_pipeline_async(scheduled, event))

            scheduler = PipelineScheduler(scheduler_syscalls, execute_pipeline)

            # Register pipelines that have triggers defined
            trigger_count = 0
            for spec_path in sorted(pipeline_specs):
                try:
                    spec = PipelineSpec.load(spec_path)
                    if spec.triggers:
                        scheduler.register_pipeline(spec)
                        trigger_count += len(spec.triggers)
                        logger.info(
                            f"Registered {spec.pipeline_id} with {len(spec.triggers)} triggers",
                            extra={
                                "pipeline_id": spec.pipeline_id,
                                "trigger_count": len(spec.triggers),
                                "trigger_ids": [t.id for t in spec.triggers],
                            },
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to register triggers for {spec_path.name}: {e}",
                        extra={"spec_path": str(spec_path), "error": str(e)},
                    )

            # Set global scheduler instance
            set_pipeline_scheduler(scheduler)
            app.state.scheduler = scheduler

            logger.info(
                f"PipelineScheduler initialized with {len(scheduler.pipelines)} pipelines, {trigger_count} triggers",
                extra={
                    "pipeline_count": len(scheduler.pipelines),
                    "trigger_count": trigger_count,
                },
            )
        except Exception:
            logger.exception("Failed to boot pipelines during startup")
            # Don't prevent kernel from starting if no pipelines exist
            app.state.pipelines = {}

        # Start background tasks
        sse_metrics_task = asyncio.create_task(_report_sse_metrics_periodically())
        outbox_worker_task = asyncio.create_task(_outbox_worker_loop())
        # DEPRECATED (M4): p08_indexer_task removed - P08 now uses PipelineScheduler with pgvector

        # Issue 7.1.3: Start ActivityTracker for idle detection (Phase 2 - M7)
        from ..scheduler.activity import get_activity_tracker

        activity_tracker = get_activity_tracker()
        await activity_tracker.start()
        logger.info("ActivityTracker started for idle detection")

        # Issue 3.2.1: Start the scheduler for trigger-based pipeline activation
        scheduler = getattr(app.state, "scheduler", None)
        if scheduler:
            await scheduler.start()
            logger.info("PipelineScheduler started")

        try:
            yield
        finally:
            # Issue 3.2.1: Stop the scheduler first
            scheduler = getattr(app.state, "scheduler", None)
            if scheduler:
                logger.info("Stopping PipelineScheduler...")
                await scheduler.stop()
                logger.info("PipelineScheduler stopped")

            # Issue 7.1.3: Stop ActivityTracker
            logger.info("Stopping ActivityTracker...")
            await activity_tracker.stop()
            logger.info("ActivityTracker stopped")

            # M2 R2.3: Graceful shutdown - call on_shutdown for all pipelines
            logger.info("Shutting down pipelines...")
            pipelines = getattr(app.state, "pipelines", {})
            for pipeline_id, pipeline in pipelines.items():
                try:
                    await pipeline.on_shutdown()
                    logger.info(f"Shutdown pipeline: {pipeline_id}")
                except Exception:
                    logger.exception(f"Error shutting down {pipeline_id}")

            # Shutdown model registry
            model_registry = getattr(app.state, "model_registry", None)
            if model_registry:
                logger.info("Shutting down model registry...")
                try:
                    await model_registry.shutdown()
                    logger.info("Model registry shutdown complete")
                except Exception:
                    logger.exception("Error shutting down model registry")

            # Shutdown SSE Server - clear global reference
            logger.info("Shutting down SSE Server...")
            try:
                from ..drivers.sse_outbox_driver import set_sse_server

                set_sse_server(None)
                app.state.sse_server = None
                logger.info("SSE Server shutdown complete")
            except Exception:
                logger.exception("Error shutting down SSE Server")

            # M2 R2.3: Record clean shutdown timestamp (for crash fencing)
            import time

            try:
                with open("k0_runtime.shutdown_ts", "w") as f:
                    f.write(str(int(time.time())))
                logger.info("Recorded clean shutdown timestamp")
            except Exception:
                logger.exception("Failed to record shutdown timestamp")

            # Cancel background tasks
            logger.info("Shutting down background tasks")
            sse_metrics_task.cancel()
            outbox_worker_task.cancel()
            # DEPRECATED (M5): p08_indexer_task removed - P08 stopped via scheduler.stop()

            # Wait for tasks to complete cancellation
            try:
                await sse_metrics_task
            except asyncio.CancelledError:
                pass

            try:
                await outbox_worker_task
            except asyncio.CancelledError:
                pass

            # DEPRECATED (M5): p08_indexer_task await removed

            # Close PostgreSQL connection pool
            logger.info("Closing PostgreSQL connection pool...")
            await shutdown_pool()
            logger.info("PostgreSQL pool closed")

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
        global _active_connections

        # Issue #046: Track active connections
        _active_connections += 1
        metrics_exporter = getattr(app.state, "metrics_exporter", None)
        if isinstance(metrics_exporter, MetricsExporter):
            try:
                metrics_exporter.set_gauge("active_connections", float(_active_connections))
            except Exception:  # noqa: BLE001
                pass  # Don't fail request on metrics error

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
            # Issue #046: Decrement active connections
            _active_connections -= 1
            if isinstance(metrics_exporter, MetricsExporter):
                try:
                    metrics_exporter.set_gauge("active_connections", float(_active_connections))
                except Exception:  # noqa: BLE001
                    pass

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

            # NOTE: Receipt is already saved inside UnitOfWork transaction (command.py)
            # The receipt_issuer.issue() call saves to st_receipts within the semaphore-protected
            # transaction. Attempting to save again here would bypass the write semaphore
            # and cause "database is locked" errors under concurrent load.
            # See: k0/ports/command.py:769 - receipt_issuer.issue(connection=uow.connection)

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
    """Compose error response payload."""
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
    if budgets:
        error["budgets"] = budgets
    return {"error": error}
    if budgets:
        error["budgets"] = budgets
    return {"error": error}
