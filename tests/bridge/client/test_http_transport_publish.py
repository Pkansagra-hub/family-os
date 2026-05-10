"""Tests for HttpTransport.publish() — MS-3a real-HTTP envelope path.

Exercises the publish surface using ``httpx.MockTransport`` so we
validate envelope construction, signing, and POST shape without
spinning up a real K0 process. The K0 receiver itself is tested
end-to-end in ``tests/integration/test_command_port.py``.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from bridge.core.envelope_builder import BridgeConfig, EnvelopeBuilder
from bridge.core.signing import HmacSigning
from bridge.core.transport import BridgeTransportError, HttpTransport, TransportConfig


class _Payload(BaseModel):
    """Tiny Pydantic model standing in for a real generated contract model."""

    schema_version: str = "1.0"
    text: str


def _build_transport(
    handler: httpx.MockTransport,
    *,
    with_envelope_builder: bool = True,
) -> HttpTransport:
    """HttpTransport whose internal client is overridden with a MockTransport."""
    cfg = TransportConfig(base_url="http://k0.test")
    builder = (
        EnvelopeBuilder(
            config=BridgeConfig(
                tenant_id="t1",
                space_id="s1",
                device_id="d1",
            ),
            signer=HmacSigning(secret=b"\x00" * 32, key_id="dev:test"),
        )
        if with_envelope_builder
        else None
    )
    transport = HttpTransport(config=cfg, envelope_builder=builder)
    transport._client = httpx.AsyncClient(transport=handler, base_url=cfg.base_url)  # type: ignore[attr-defined]
    return transport


@pytest.mark.asyncio
async def test_publish_posts_signed_envelope_to_command_path() -> None:
    """publish() builds an envelope, signs it, and POSTs to /k0/command.submit."""
    captured: dict[str, Any] = {}

    def _handle(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["body"] = json.loads(req.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "receipt_id": "00000000-0000-0000-0000-000000000001",
                "commit_ts": "2026-05-08T00:00:00Z",
                "offsets": {"memory.write.v1": 1},
                "obligations": [],
            },
        )

    transport = _build_transport(httpx.MockTransport(_handle))
    try:
        result = await transport.publish(
            topic="memory.write.v1",
            schema_uri="bridge://contracts/schemas/memory.write.v1.json",
            payload=_Payload(text="hello"),
        )
    finally:
        await transport.close()

    assert result["receipt_id"] == "00000000-0000-0000-0000-000000000001"
    assert captured["url"].endswith("/k0/command.submit")

    env = captured["body"]
    # All envelope-required fields land on the wire.
    for field in (
        "topic",
        "tenant_id",
        "space_id",
        "device_id",
        "actor",
        "ts",
        "policy_version",
        "schema_uri",
        "schema_version",
        "body",
        "payload_sha256",
        "envelope_sha256",
        "sig",
        "sig_alg",
        "sig_kid",
    ):
        assert field in env, f"envelope missing required field: {field}"
    assert "idem_key" not in env, "bridge must not supply idem_key; K0 owns it"
    assert env["topic"] == "memory.write.v1"
    assert env["sig_alg"] == "hmac-sha256"
    assert env["sig_kid"] == "dev:test"


@pytest.mark.asyncio
async def test_publish_without_envelope_builder_raises() -> None:
    """publish() requires an envelope_builder; raises RuntimeError otherwise."""
    transport = _build_transport(
        httpx.MockTransport(lambda r: httpx.Response(200, json={})),
        with_envelope_builder=False,
    )
    try:
        with pytest.raises(RuntimeError, match="envelope_builder"):
            await transport.publish(
                topic="memory.write.v1",
                schema_uri="bridge://contracts/schemas/memory.write.v1.json",
                payload=_Payload(text="hi"),
            )
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_publish_raises_on_non_2xx_response() -> None:
    """K0 returning 4xx/5xx is surfaced as BridgeTransportError."""

    def _handle(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"code": "REJECTED_KERNEL_GATE"}})

    transport = _build_transport(httpx.MockTransport(_handle))
    try:
        with pytest.raises(BridgeTransportError) as exc_info:
            await transport.publish(
                topic="memory.write.v1",
                schema_uri="bridge://contracts/schemas/memory.write.v1.json",
                payload=_Payload(text="bad"),
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.body == {"error": {"code": "REJECTED_KERNEL_GATE"}}
    finally:
        await transport.close()
