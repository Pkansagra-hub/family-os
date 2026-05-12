"""scripts.pseudo_k0 — Pseudo-K0 local server for development/demo.

Satisfies the K0 HTTP API surface so K1 can use the real
``HttpBridgeClient`` + ``BridgeRuntime`` without standing up a full K0
deployment. **Not** for production use — request signatures are parsed
but NOT cryptographically verified.

Production wire format (traced from
``bridge/core/transport/__init__.py``, ``obs_emitter.py``,
``sse_client.py``):

    POST /k0/command.submit
        Body: full signed K0 envelope (see bridge.core.envelope_builder).
        Dispatched by ``body["topic"]``:
            * recall.request.v1 → SQLiteK0Store.recall(...) → RecallResponseV1
            * memory.write.v1   → SQLiteK0Store.write_envelope(...) → {"ok": True}
            * other             → SQLiteK0Store.write_envelope(...) (best-effort)

    POST /k0/obs.emit
        Body: {"kind": <str>, "body": <dict>}  -- unsigned (per
        ObsHttpEmitter contract).

    GET /k0/sse/{topic}
        text/event-stream keep-alive.

    GET /healthz
        {"status": "ok", "mode": "K0_LOCAL"}

Usage::

    python -m scripts.pseudo_k0 --port 8090 --db data/pseudo_k0.db
"""

from scripts.pseudo_k0.models import (
    K0Envelope,
    ObsPayload,
    RecallHit,
    RecallRequestBody,
    RecallResponseBody,
    RecallSelectorBody,
)
from scripts.pseudo_k0.store import SQLiteK0Store

__all__ = [
    "K0Envelope",
    "ObsPayload",
    "RecallHit",
    "RecallRequestBody",
    "RecallResponseBody",
    "RecallSelectorBody",
    "SQLiteK0Store",
]
