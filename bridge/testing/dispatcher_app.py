"""ASGI app that routes incoming bridge requests to the runtime dispatcher.

This is the consumer-side counterpart to
:class:`bridge.core.transport.in_process_http.InProcessHttpTransport`. It
exposes a single endpoint ``POST /bridge/v1/dispatch`` that:

1. Accepts ``{"topic": str, "schema_uri": str, "payload": dict}``.
2. Forwards to :meth:`bridge.runtime.BridgeRuntime.dispatch`.
3. Returns the handler's result (JSON-serialisable ``dict``).

In MS-2.5 this is mounted as the K0 ASGI app for the round-trip test.
In MS-3a the same path is folded into production K0
``/k0/command.submit`` so the contract-bound dispatch surface stays
identical.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ValidationError

from bridge.obs.metrics import (
    memory_write_v1_accepted_total,
    memory_write_v1_latency_ms,
    memory_write_v1_rejected_total,
)
from bridge.runtime import BridgeRuntime

_log = logging.getLogger("bridge.dispatcher")


class DispatchRequest(BaseModel):
    """Wire shape sent by the bridge transport's ``publish``."""

    topic: str
    schema_uri: str
    payload: dict[str, Any]
    tenant_id: str = "unknown"


def _record_outcome(
    *, topic: str, tenant_id: str, started_ns: int, accepted: bool, reason: str = ""
) -> None:
    """Emit metrics + a structured boundary log for one dispatch."""
    elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000
    if topic == "memory.write.v1":
        memory_write_v1_latency_ms.labels(tenant_id=tenant_id).observe(elapsed_ms)
        if accepted:
            memory_write_v1_accepted_total.labels(tenant_id=tenant_id).inc()
        else:
            memory_write_v1_rejected_total.labels(
                tenant_id=tenant_id, reason=reason or "unknown"
            ).inc()
    _log.info(
        "bridge.dispatch.outcome",
        extra={
            "topic": topic,
            "tenant_id": tenant_id,
            "elapsed_ms": elapsed_ms,
            "accepted": accepted,
            "reason": reason,
        },
    )


def build_app(*, runtime: BridgeRuntime) -> FastAPI:
    """Create the dispatcher ASGI app bound to ``runtime``."""
    app = FastAPI(title="bridge-dispatcher", version="2.5")

    @app.post("/bridge/v1/dispatch")
    async def dispatch(req: DispatchRequest) -> dict[str, Any]:  # noqa: D401
        started = time.monotonic_ns()
        try:
            result = await runtime.dispatch(topic=req.topic, payload=req.payload)
        except KeyError as exc:
            _record_outcome(
                topic=req.topic,
                tenant_id=req.tenant_id,
                started_ns=started,
                accepted=False,
                reason="unknown_topic",
            )
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValidationError as exc:
            _record_outcome(
                topic=req.topic,
                tenant_id=req.tenant_id,
                started_ns=started,
                accepted=False,
                reason="schema_validation",
            )
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        _record_outcome(
            topic=req.topic,
            tenant_id=req.tenant_id,
            started_ns=started,
            accepted=True,
        )
        if not isinstance(result, dict):
            return {"result": result}
        return result

    return app
