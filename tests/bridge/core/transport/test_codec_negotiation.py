"""HttpTransport codec selection — MS-4 Epic 4.1 wire-format tests.

Asserts that ``HttpTransport.publish(codec=...)``:

* Wraps non-JSON bodies as ``{"_codec", "_b64"}`` inside the envelope JSON.
* Forwards the codec content-type via ``Accept`` so K0 can negotiate.
* Decodes msgpack / cbor response bodies based on the response's
  ``Content-Type`` header (so the K1 caller never sees raw bytes).
* Leaves the JSON-default path (``codec="json"``) byte-for-byte unchanged.

The tests use ``httpx.MockTransport`` so envelope construction, signing,
and POST shape are validated without standing up a real K0 process —
matching the pattern used by the existing
``tests/bridge/client/test_http_transport_publish.py`` suite.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from bridge.core.codecs import (
    BODY_WRAPPER_B64_KEY,
    BODY_WRAPPER_CODEC_KEY,
    CBORCodec,
    MsgpackCodec,
)
from bridge.core.envelope_builder import BridgeConfig, EnvelopeBuilder
from bridge.core.signing import HmacSigning
from bridge.core.transport import HttpTransport, TransportConfig


class _Payload(BaseModel):
    schema_version: str = "1.0"
    text: str
    n: int = 0


def _build_transport(handler: httpx.MockTransport) -> HttpTransport:
    cfg = TransportConfig(base_url="http://k0.test")
    builder = EnvelopeBuilder(
        config=BridgeConfig(tenant_id="t1", space_id="s1", device_id="d1"),
        signer=HmacSigning(secret=b"\x00" * 32, key_id="dev:test"),
    )
    transport = HttpTransport(config=cfg, envelope_builder=builder)
    transport._client = httpx.AsyncClient(  # type: ignore[attr-defined]
        transport=handler, base_url=cfg.base_url
    )
    return transport


# ---------------------------------------------------------------------------
# Body wrapping (request side)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_codec_json_leaves_body_unwrapped() -> None:
    """Default JSON path is byte-for-byte unchanged from MS-3a."""
    captured: dict[str, Any] = {}

    def handle(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode("utf-8"))
        captured["accept"] = req.headers.get("Accept")
        captured["content_type"] = req.headers.get("Content-Type")
        return httpx.Response(200, json={"ok": True})

    transport = _build_transport(httpx.MockTransport(handle))
    try:
        await transport.publish(
            topic="memory.write.v1",
            schema_uri="bridge://contracts/schemas/memory.write.v1.json",
            payload=_Payload(text="hello", n=1),
            codec="json",
        )
    finally:
        await transport.close()

    body = captured["body"]["body"]
    assert isinstance(body, dict)
    assert BODY_WRAPPER_CODEC_KEY not in body
    assert body == {"schema_version": "1.0", "text": "hello", "n": 1}
    # Outer envelope is always JSON.
    assert captured["content_type"] == "application/json"
    # JSON path declares JSON-only acceptance.
    assert captured["accept"] == "application/json"


@pytest.mark.asyncio
async def test_publish_codec_msgpack_wraps_body_and_sets_accept() -> None:
    captured: dict[str, Any] = {}

    def handle(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode("utf-8"))
        captured["accept"] = req.headers.get("Accept")
        captured["content_type"] = req.headers.get("Content-Type")
        return httpx.Response(200, json={"ok": True})

    transport = _build_transport(httpx.MockTransport(handle))
    try:
        await transport.publish(
            topic="memory.write.v1",
            schema_uri="bridge://contracts/schemas/memory.write.v1.json",
            payload=_Payload(text="hello", n=42),
            codec="msgpack",
        )
    finally:
        await transport.close()

    # Outer envelope still JSON-encoded for signing canonicalisation.
    assert captured["content_type"] == "application/json"
    body = captured["body"]["body"]
    assert set(body.keys()) == {BODY_WRAPPER_CODEC_KEY, BODY_WRAPPER_B64_KEY}
    assert body[BODY_WRAPPER_CODEC_KEY] == "msgpack"
    raw = base64.b64decode(body[BODY_WRAPPER_B64_KEY], validate=True)
    decoded = MsgpackCodec().decode(raw)
    assert decoded == {"schema_version": "1.0", "text": "hello", "n": 42}
    # Accept header advertises msgpack as preferred + JSON fallback.
    assert "application/msgpack" in captured["accept"]
    assert "application/json" in captured["accept"]


@pytest.mark.asyncio
async def test_publish_codec_cbor_wraps_body() -> None:
    captured: dict[str, Any] = {}

    def handle(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode("utf-8"))
        return httpx.Response(200, json={"ok": True})

    transport = _build_transport(httpx.MockTransport(handle))
    try:
        await transport.publish(
            topic="memory.write.v1",
            schema_uri="bridge://contracts/schemas/memory.write.v1.json",
            payload=_Payload(text="cb", n=7),
            codec="cbor",
        )
    finally:
        await transport.close()

    body = captured["body"]["body"]
    assert body[BODY_WRAPPER_CODEC_KEY] == "cbor"
    decoded = CBORCodec().decode(base64.b64decode(body[BODY_WRAPPER_B64_KEY]))
    assert decoded == {"schema_version": "1.0", "text": "cb", "n": 7}


# ---------------------------------------------------------------------------
# Response decoding (response side)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_decodes_msgpack_response_body() -> None:
    """When K0 replies with msgpack, post_command decodes by Content-Type."""
    expected = {"receipt_id": "rcpt-1", "ok": True}
    raw = MsgpackCodec().encode(expected)

    def handle(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=raw, headers={"Content-Type": "application/msgpack"})

    transport = _build_transport(httpx.MockTransport(handle))
    try:
        result = await transport.publish(
            topic="memory.write.v1",
            schema_uri="bridge://contracts/schemas/memory.write.v1.json",
            payload=_Payload(text="x"),
            codec="msgpack",
        )
    finally:
        await transport.close()

    assert result == expected


@pytest.mark.asyncio
async def test_publish_decodes_cbor_response_body() -> None:
    expected = {"receipt_id": "rcpt-cbor", "items": [1, 2, 3]}
    raw = CBORCodec().encode(expected)

    def handle(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=raw, headers={"Content-Type": "application/cbor"})

    transport = _build_transport(httpx.MockTransport(handle))
    try:
        result = await transport.publish(
            topic="memory.write.v1",
            schema_uri="bridge://contracts/schemas/memory.write.v1.json",
            payload=_Payload(text="x"),
            codec="cbor",
        )
    finally:
        await transport.close()

    assert result == expected


@pytest.mark.asyncio
async def test_publish_unknown_codec_raises() -> None:
    """Unknown codec name is a programmer error — surface it loudly."""

    def handle(req: httpx.Request) -> httpx.Response:  # pragma: no cover - never called
        return httpx.Response(500)

    transport = _build_transport(httpx.MockTransport(handle))
    try:
        with pytest.raises(LookupError):
            await transport.publish(
                topic="memory.write.v1",
                schema_uri="bridge://contracts/schemas/memory.write.v1.json",
                payload=_Payload(text="x"),
                codec="flatbuffers",  # listed in schema but unimplemented
            )
    finally:
        await transport.close()
