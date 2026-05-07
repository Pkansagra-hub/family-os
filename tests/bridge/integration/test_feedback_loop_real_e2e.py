"""End-to-end feedback emission test (MS-3e Epic 3e.4 EXIT criterion).

Wires K1 :class:`FeedbackEmitter` -> generated obs client ->
:class:`bridge.core.transport.obs_emitter.ObsHttpEmitter` -> real
``httpx`` POST -> live ``uvicorn`` server hosting a FastAPI app that
mounts a feedback-receiving endpoint mirroring the K0
``/k0/obs.emit`` contract.

The K0 ingestion path validates the body as a real
:class:`k0.feedback.envelope.FeedbackEnvelope` and applies the real
:class:`k0.feedback.schema_registry.FeedbackSchemaRegistry` for the
target pipeline (P02). This proves:

1. Wire shape: POST /k0/obs.emit with ``{kind, body}`` -> server.
2. K1 envelope passes K0-side ``FeedbackEnvelope`` validation.
3. K0 schema registry validates the per-pipeline payload (P02 here).
4. Trace/correlation fields survive the round-trip.

We do NOT exercise the full K0 storage stack (st_feedback_signals
INSERT) here — that requires Postgres and is covered by separate K0
integration tests. The bridge contract scope is "K1 emits a wire-valid
feedback envelope to the K0 obs port"; everything past
``FeedbackSchemaRegistry.validate`` is K0's concern.
"""

from __future__ import annotations

import asyncio
import socket
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi import FastAPI, Request, Response, status

from bridge.core.transport.obs_emitter import ObsHttpEmitter
from bridge.runtime import BridgeRuntime, Role
from k0.feedback import payloads as fb_payloads
from k0.feedback.envelope import FeedbackEnvelope
from k0.feedback.schema_registry import FeedbackSchemaRegistry
from k1.concierge.feedback import (
    ConversationContext,
    CorrectionDetector,
    FeedbackEmitter,
    ReformulationDetector,
    ValidationDetector,
)

CONTRACTS_PATH = Path(__file__).resolve().parents[3] / "bridge" / "contracts"


def _ensure_p02_schema_registered() -> None:
    """Mirror the lazy registration that K0 ports.observe performs.

    The real K0 endpoint calls ``_ensure_builtin_feedback_payload_schemas(P02)``
    before validating; we do the equivalent here so the schema registry is
    populated for our endpoint. Re-registration with the same JSON schema
    is idempotent.
    """
    schema = fb_payloads.P02FeedbackPayload.model_json_schema()
    try:
        FeedbackSchemaRegistry.register("P02", schema, version="1.0")
    except Exception:  # noqa: BLE001 - already registered is fine
        pass


def _build_k0_feedback_app() -> tuple[FastAPI, list[dict[str, Any]]]:
    """K0 stand-in that exercises the real K0-side validation path.

    Captures every accepted feedback envelope into ``received`` so the
    test can assert wire fidelity. Returns 204 on success and 400 on
    validation failure (mirroring real K0 ports.observe.emit semantics).
    """
    received: list[dict[str, Any]] = []
    app = FastAPI()

    _ensure_p02_schema_registered()

    @app.post("/k0/obs.emit", status_code=status.HTTP_204_NO_CONTENT)
    async def emit(request: Request) -> Response:
        wire = await request.json()
        if not isinstance(wire, dict):
            return Response(status_code=status.HTTP_400_BAD_REQUEST)
        kind = wire.get("kind")
        body = wire.get("body")
        if kind != "feedback" or not isinstance(body, dict):
            return Response(status_code=status.HTTP_400_BAD_REQUEST)

        # Real K0-side validation: parse as FeedbackEnvelope and run the
        # per-pipeline registry.
        try:
            envelope = FeedbackEnvelope.model_validate(body)
        except Exception:  # noqa: BLE001 - want 400 on bad envelope
            return Response(status_code=status.HTTP_400_BAD_REQUEST)
        ok, _err = FeedbackSchemaRegistry.validate(
            envelope.pipeline_id, envelope.payload, permissive_unregistered=True
        )
        if not ok:
            return Response(status_code=status.HTTP_400_BAD_REQUEST)
        received.append(
            {
                "kind": kind,
                "topic": request.headers.get("X-Bridge-Topic"),
                "envelope": envelope.model_dump(mode="json"),
            }
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return app, received


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@asynccontextmanager
async def _serve(app: FastAPI):
    port = _free_port()
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        lifespan="off",
    )
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    deadline = time.monotonic() + 5.0
    while not server.started and time.monotonic() < deadline:
        await asyncio.sleep(0.02)
    if not server.started:  # pragma: no cover - boot failure
        raise RuntimeError("uvicorn did not start in time")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await server_task


def _build_k1_runtime_with_obs(*, base_url: str) -> tuple[BridgeRuntime, ObsHttpEmitter]:
    """Construct a minimal K1 BridgeRuntime with a wired obs emitter and
    populated ``runtime.obs.feedback_envelope_v1`` slot (mirroring what
    ``BridgeRuntime.from_registry`` does for production callers)."""
    from types import SimpleNamespace

    from bridge._generated.k1.clients.feedback_envelope_v1 import (
        FeedbackEnvelopeV1Client,
    )

    runtime = BridgeRuntime(role=Role.K1, contracts_path=CONTRACTS_PATH)
    obs_emitter = ObsHttpEmitter(base_url=base_url)
    object.__setattr__(runtime, "_obs_emitter", obs_emitter)
    client = FeedbackEnvelopeV1Client(runtime=runtime)
    object.__setattr__(
        runtime,
        "obs",
        SimpleNamespace(feedback_envelope_v1=client),
    )
    return runtime, obs_emitter


@pytest.mark.asyncio
async def test_correction_signal_round_trips_to_k0_obs_port_real_e2e() -> None:
    """End-to-end: detector -> emitter -> wire -> K0 obs port -> K0 validator."""
    app, received = _build_k0_feedback_app()
    async with _serve(app) as base_url:
        runtime, obs_emitter = _build_k1_runtime_with_obs(base_url=base_url)
        try:
            # Stage K1 conversation context as if a turn just happened.
            ctx = ConversationContext(
                session_id="sess-e2e",
                last_bot_response="You had coffee with Rachel on Tuesday.",
                response_id="resp-e2e",
                grounded_event_ids=["evt-rachel-tuesday"],
            )
            ctx.record_recall(recall_id="rec-1", event_ids=["evt-rachel-tuesday"])

            sig = CorrectionDetector().detect("no, I actually had tea, not coffee", context=ctx)
            assert sig is not None, "correction detector must fire on this fixture"

            emitter = FeedbackEmitter(runtime, tenant_id="tenant-e2e", space_id="space-e2e")
            ok = await emitter.emit_correction(sig, context=ctx)
            assert ok, "emit_correction must report success on a 204"

            # Server must have received exactly one envelope.
            assert len(received) == 1, f"expected 1 received envelope, got {received}"
            entry = received[0]
            assert entry["kind"] == "feedback"
            assert entry["topic"] == "feedback.envelope.v1"

            envelope = entry["envelope"]
            assert envelope["pipeline_id"] == "P02"
            assert envelope["signal_class"] == "CORRECTION"
            assert envelope["tenant_id"] == "tenant-e2e"
            assert envelope["space_id"] == "space-e2e"
            assert envelope["source"] == "K1"
            # Correlation propagated.
            corr = envelope["correlation"]
            assert corr["session_id"] == "sess-e2e"
            assert corr["recall_id"] == "rec-1"
            assert corr["response_id"] == "resp-e2e"
            assert "evt-rachel-tuesday" in corr["event_ids"]
            assert corr["target_entity_type"] == "event"
            assert corr["target_entity_id"] == "evt-rachel-tuesday"
            # Payload shaped per P02.
            payload = envelope["payload"]
            assert payload["extraction_quality"] == "poor"
            assert payload["user_correction"]["field"] == "memory"
            assert "tea" in payload["user_correction"]["expected"]
        finally:
            await obs_emitter.aclose()


@pytest.mark.asyncio
async def test_validation_signal_round_trips_to_k0_obs_port_real_e2e() -> None:
    """Validation detector emits a P08 wire envelope that K0 accepts."""
    app, received = _build_k0_feedback_app()
    # Pre-register P08 schema for completeness.
    schema = fb_payloads.P08FeedbackPayload.model_json_schema()
    try:
        FeedbackSchemaRegistry.register("P08", schema, version="1.0")
    except Exception:  # noqa: BLE001
        pass

    async with _serve(app) as base_url:
        runtime, obs_emitter = _build_k1_runtime_with_obs(base_url=base_url)
        try:
            ctx = ConversationContext(
                session_id="sess-v",
                response_id="resp-v",
                grounded_event_ids=["evt-v"],
            )
            sig = ValidationDetector().detect("yes, that's right", context=ctx)
            assert sig is not None
            emitter = FeedbackEmitter(runtime, tenant_id="t", space_id="s")
            ok = await emitter.emit_validation(sig, context=ctx)
            assert ok
            assert len(received) == 1
            envelope = received[0]["envelope"]
            assert envelope["pipeline_id"] == "P08"
            assert envelope["signal_class"] == "VALIDATION"
            assert envelope["payload"]["retrieval_hit"] is True
            assert envelope["payload"]["user_relevance"] == "relevant"
        finally:
            await obs_emitter.aclose()


@pytest.mark.asyncio
async def test_reformulation_signal_round_trips_to_k0_obs_port_real_e2e() -> None:
    """Reformulation detector emits a P03 wire envelope that K0 accepts."""
    app, received = _build_k0_feedback_app()
    schema = fb_payloads.P03FeedbackPayload.model_json_schema()
    try:
        FeedbackSchemaRegistry.register("P03", schema, version="1.0")
    except Exception:  # noqa: BLE001
        pass

    async with _serve(app) as base_url:
        runtime, obs_emitter = _build_k1_runtime_with_obs(base_url=base_url)
        try:
            ctx = ConversationContext(
                session_id="sess-r",
                last_user_message="show me my meetings with Rachel last Tuesday",
                response_id="resp-r",
                grounded_event_ids=["evt-r"],
            )
            sig = ReformulationDetector().detect(
                "tell me about meetings Rachel Tuesday", context=ctx
            )
            assert sig is not None
            emitter = FeedbackEmitter(runtime, tenant_id="t", space_id="s")
            ok = await emitter.emit_reformulation(sig, context=ctx)
            assert ok
            assert len(received) == 1
            envelope = received[0]["envelope"]
            assert envelope["pipeline_id"] == "P03"
            assert envelope["signal_class"] == "IMPLICIT"
            payload = envelope["payload"]
            assert payload["feedback_type"] == "SALIENCE_ADJUSTMENT"
            assert payload["was_retrieved"] is True
            assert payload["was_helpful"] is False
            assert -1.0 <= payload["salience_delta"] <= 0.0
        finally:
            await obs_emitter.aclose()
