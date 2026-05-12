"""scripts.pseudo_k0.models — Pydantic V2 models for pseudo-K0 HTTP wire.

Three model groups:

  1. K0Envelope          — the FULL signed envelope K1 sends to
                            POST /k0/command.submit (matches
                            ``bridge.core.envelope_builder.EnvelopeBuilder.build``).
                            Lenient: ``extra="ignore"`` so future envelope
                            field additions don't break pseudo-K0.

  2. RecallRequestBody / RecallSelectorBody / RecallResponseBody / RecallHit
                          — body shape for ``recall.request.v1`` /
                            ``recall.response.v1`` topics. Mirrors
                            ``bridge/_generated/k1/models/recall_request_v1.py``
                            and ``recall_response_v1.py`` but with
                            ``extra="ignore"`` so optional contract fields
                            we don't yet implement do not error.

  3. ObsPayload          — {kind, body} for ``POST /k0/obs.emit``
                            (matches ``ObsHttpEmitter.emit``).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# K0Envelope — full signed envelope from /k0/command.submit
# ---------------------------------------------------------------------------


class K0Envelope(BaseModel):
    """Full K0 envelope as built by ``bridge.core.envelope_builder``.

    Pseudo-K0 is a development server — it parses the envelope but does
    NOT verify ``sig`` / ``envelope_sha256``. All non-``topic``/``body``
    fields are accepted leniently.
    """

    model_config = ConfigDict(extra="ignore")

    # Routing keys — the only fields pseudo-K0 actually inspects.
    topic: str = Field(..., min_length=1)
    body: Dict[str, Any] = Field(default_factory=dict)

    # Provenance — recorded into the WAL but not validated.
    cognitive_trace_id: Optional[str] = None
    tenant_id: Optional[str] = None
    space_id: Optional[str] = None
    actor: Optional[str] = None
    device_id: Optional[str] = None
    band: Optional[str] = None
    ts: Optional[str] = None
    policy_version: Optional[str] = None
    schema_uri: Optional[str] = None
    schema_version: Optional[str] = None
    payload_sha256: Optional[str] = None
    envelope_sha256: Optional[str] = None
    sig_alg: Optional[str] = None
    sig_kid: Optional[str] = None
    # sig is intentionally untyped — we accept whatever the signer emits.
    sig: Optional[Any] = None
    policy: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# recall.request.v1 body
# ---------------------------------------------------------------------------


class RecallSelectorBody(BaseModel):
    """One selector inside a ``recall.request.v1`` body.

    Mirrors ``bridge._generated.k1.models.recall_request_v1.RecallSelector``
    but with ``extra="ignore"`` and ``type`` left as ``str`` (the canonical
    contract enum is ``episodic|semantic|session|device|belief|graph``).
    """

    model_config = ConfigDict(extra="ignore")

    type: str = Field(..., min_length=1)
    topic: Optional[str] = None
    limit: int = Field(default=10, ge=1, le=256)
    cursor: Optional[str] = None
    after: Optional[str] = None
    query: Optional[str] = None


class RecallRequestBody(BaseModel):
    """Body of a ``recall.request.v1`` envelope."""

    model_config = ConfigDict(extra="ignore")

    selectors: List[RecallSelectorBody] = Field(..., min_length=1, max_length=16)
    space_id: str = Field(..., min_length=1)
    tenant_id: Optional[str] = None
    max_latency_ms: int = Field(default=250, ge=1, le=10_000)
    fail_fast: bool = False
    max_results: int = Field(default=10, ge=1, le=256)
    vector_query: Optional[str] = None
    fts_query: Optional[str] = None
    trace_id: Optional[str] = None


# ---------------------------------------------------------------------------
# recall.response.v1 body (HTTP response body for recall.request.v1)
# ---------------------------------------------------------------------------


class RecallHit(BaseModel):
    """One hit in a ``recall.response.v1`` body."""

    model_config = ConfigDict(extra="ignore")

    atom_id: str = Field(..., min_length=1)
    content: Dict[str, Any] = Field(default_factory=dict)
    score: float = Field(..., ge=0.0, le=1.0)
    source: str = Field(..., min_length=1)
    selector_type: Optional[str] = None
    cursor: Optional[str] = None


class RecallResponseBody(BaseModel):
    """Synchronous HTTP response body for ``recall.request.v1``."""

    model_config = ConfigDict(extra="ignore")

    hits: List[RecallHit] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    truncated: bool = False
    trace_id: Optional[str] = None


# ---------------------------------------------------------------------------
# obs.emit body
# ---------------------------------------------------------------------------


class ObsPayload(BaseModel):
    """Body shape for ``POST /k0/obs.emit`` (unsigned).

    Matches ``bridge.core.transport.obs_emitter.ObsHttpEmitter.emit`` which
    POSTs ``{"kind": kind, "body": payload.model_dump(...)}``.
    """

    model_config = ConfigDict(extra="ignore")

    kind: str = Field(..., min_length=1)
    body: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "K0Envelope",
    "RecallSelectorBody",
    "RecallRequestBody",
    "RecallHit",
    "RecallResponseBody",
    "ObsPayload",
]
