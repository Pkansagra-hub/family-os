"""HTTP transport for K0 command port communication.

Implements connection pooling, timeouts, and TLS configuration per
bridge/contracts/command_port.protocol.yaml transport section.

MS-3a addition: ``HttpTransport.publish(*, topic, schema_uri, payload)``
matches the ASGI shape exposed by
:class:`bridge.core.transport.in_process_http.InProcessHttpTransport`,
so the generated K1 clients (``MemoryWriteV1Client`` and successors)
work against either transport without code changes. Real-HTTP publish
builds a fully-signed K0 envelope via
:class:`bridge.core.envelope_builder.EnvelopeBuilder` and posts to
``/k0/command.submit``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel

from bridge.core.codecs import (
    Codec,
    CodecRegistry,
    encode_wrapped_body,
)
from bridge.core.envelope_builder import EnvelopeBuilder

logger = logging.getLogger(__name__)


# Shared registry instance — codec lookups are stateless so a module-level
# singleton is safe and cheap. Tests can construct their own if isolation
# matters; the registry is immutable after construction.
_DEFAULT_CODEC_REGISTRY = CodecRegistry()


class BridgeTransportError(RuntimeError):
    """Raised when the K0 receiver responds with a non-2xx status to publish."""

    def __init__(self, status_code: int, body: dict[str, Any] | None, error: str | None) -> None:
        self.status_code = status_code
        self.body = body
        self.error = error
        msg = f"K0 publish failed: status={status_code} error={error!r} body={body!r}"
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HttpResult:
    """Outcome of an HTTP request to K0."""

    status_code: int
    body: dict[str, Any] | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Transport configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TransportConfig:
    """Configuration for the K0 HTTP transport layer."""

    base_url: str = "http://localhost:8080"
    connect_timeout_s: float = 5.0
    read_timeout_s: float = 30.0
    tls_verify: bool = False
    max_keepalive_connections: int = 5
    max_connections: int = 10


# ---------------------------------------------------------------------------
# HttpTransport
# ---------------------------------------------------------------------------


class HttpTransport:
    """Async HTTP client for communicating with the K0 command port.

    Provides connection pooling, configurable timeouts, and a lightweight
    health-check endpoint.  Designed for reuse across the Bridge lifetime.
    """

    COMMAND_PATH = "/k0/command.submit"
    HEALTH_PATH = "/healthz"

    def __init__(
        self,
        config: TransportConfig | None = None,
        *,
        envelope_builder: EnvelopeBuilder | None = None,
    ) -> None:
        self._config = config or TransportConfig()
        self._client: httpx.AsyncClient | None = None
        self._envelope_builder = envelope_builder

    # -- lifecycle -----------------------------------------------------------

    async def open(self) -> None:
        """Create the underlying ``httpx.AsyncClient`` with pooling."""
        if self._client is not None:
            return
        timeout = httpx.Timeout(
            connect=self._config.connect_timeout_s,
            read=self._config.read_timeout_s,
            write=self._config.read_timeout_s,
            pool=self._config.connect_timeout_s,
        )
        limits = httpx.Limits(
            max_keepalive_connections=self._config.max_keepalive_connections,
            max_connections=self._config.max_connections,
        )
        self._client = httpx.AsyncClient(
            base_url=self._config.base_url,
            timeout=timeout,
            limits=limits,
            verify=self._config.tls_verify,
        )

    async def close(self) -> None:
        """Shut down the HTTP client and release connections."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # -- public API ----------------------------------------------------------

    async def post_command(
        self,
        envelope_json: bytes,
        *,
        accept: str = "application/json",
    ) -> HttpResult:
        """POST an envelope to ``/k0/command.submit``.

        ``envelope_json`` is always JSON-encoded (the outer envelope is
        canonical JSON for signing). The optional ``accept`` header is
        forwarded so K0 can negotiate a non-JSON response codec; the
        response body is decoded by ``Content-Type`` rather than
        unconditionally as JSON.
        """
        client = self._ensure_client()
        try:
            response = await client.post(
                self.COMMAND_PATH,
                content=envelope_json,
                headers={
                    "Content-Type": "application/json",
                    "Accept": accept,
                },
            )
            body = self._decode_response_body(response)
            return HttpResult(status_code=response.status_code, body=body)
        except httpx.TimeoutException as exc:
            logger.warning("K0 command port timeout: %s", exc)
            return HttpResult(status_code=0, error=f"timeout: {exc}")
        except httpx.ConnectError as exc:
            logger.warning("K0 command port connection error: %s", exc)
            return HttpResult(status_code=0, error=f"connection_error: {exc}")
        except httpx.HTTPError as exc:
            logger.error("K0 command port HTTP error: %s", exc)
            return HttpResult(status_code=0, error=f"http_error: {exc}")

    @staticmethod
    def _decode_response_body(response: httpx.Response) -> dict[str, Any] | None:
        """Decode an HTTP response body using its declared ``Content-Type``.

        JSON is parsed via stdlib (preserves prior behaviour); msgpack /
        cbor are routed to the codec registry. Any decode failure returns
        ``None`` so callers can still surface the status code without
        crashing on malformed bodies.
        """
        content_type = response.headers.get("Content-Type", "application/json")
        media = content_type.split(";", 1)[0].strip().lower()
        try:
            if media == "application/json":
                try:
                    return response.json()
                except Exception:  # noqa: BLE001
                    return None
            codec = _DEFAULT_CODEC_REGISTRY.by_content_type(media)
            return codec.decode(response.content)
        except Exception:  # noqa: BLE001
            return None

    async def check_health(self) -> bool:
        """Lightweight health probe against ``/healthz``.

        Returns True if K0 responds with 200, False on any failure.
        """
        client = self._ensure_client()
        try:
            response = await client.get(self.HEALTH_PATH)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def publish(
        self,
        *,
        topic: str,
        schema_uri: str,
        payload: BaseModel,
        trace_id: str | None = None,
        band: str | None = None,
        codec: str = "json",
    ) -> dict[str, Any]:
        """Build, sign, and POST a K0 envelope; return the parsed response.

        Mirrors the ASGI shape of
        :meth:`bridge.core.transport.in_process_http.InProcessHttpTransport.publish`
        so the generated client code is transport-agnostic.

        ``codec`` selects the **body** wire format (the outer envelope is
        always canonical JSON because signing depends on it). When
        ``codec != "json"`` the body is wrapped as
        ``{"_codec": codec, "_b64": <base64>}`` inside the envelope; the
        K0 ingress detects the wrapper and unwraps before validation.

        Raises:
            RuntimeError: if no ``EnvelopeBuilder`` was injected at construction.
            BridgeTransportError: on non-2xx K0 responses or transport errors.
        """
        if self._envelope_builder is None:
            raise RuntimeError(
                "HttpTransport.publish requires an envelope_builder; "
                "construct HttpTransport(config=..., envelope_builder=...)"
            )
        await self.open()
        body_dict = payload.model_dump(mode="json", by_alias=True)
        accept = "application/json"
        if codec != "json":
            codec_obj = _DEFAULT_CODEC_REGISTRY.get(codec)
            body_dict = encode_wrapped_body(codec=codec_obj, body=body_dict)
            accept = f"{codec_obj.content_type}, application/json;q=0.9"
        envelope = self._envelope_builder.build(
            topic,
            body_dict,
            schema_uri=schema_uri,
            band=band,
            trace_id=trace_id,
        )
        envelope_bytes = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        result = await self.post_command(envelope_bytes, accept=accept)
        if result.status_code < 200 or result.status_code >= 300:
            raise BridgeTransportError(
                status_code=result.status_code,
                body=result.body,
                error=result.error,
            )
        return result.body or {}

    # -- internals -----------------------------------------------------------

    def build_envelope_bytes(
        self,
        *,
        topic: str,
        schema_uri: str,
        payload: BaseModel,
        trace_id: str | None = None,
        band: str | None = None,
        codec: str = "json",
    ) -> bytes:
        """Build + sign the envelope bytes without posting them.

        Used by the MS-3b ``OnlineFirstClient`` decorator (epic 3b.4) to
        serialise an envelope at the moment the caller publishes (so
        idempotency keys and signing timestamps reflect the original
        intent) before stashing the bytes in the local outbox. The
        :class:`bridge.sync.drain_worker.DrainWorker` later POSTs them
        unmodified via :meth:`post_command`.

        ``codec`` selects the body wire format identically to
        :meth:`publish` — the outer envelope is always canonical JSON.
        """
        if self._envelope_builder is None:
            raise RuntimeError("HttpTransport.build_envelope_bytes requires an envelope_builder")
        body_dict = payload.model_dump(mode="json", by_alias=True)
        if codec != "json":
            codec_obj = _DEFAULT_CODEC_REGISTRY.get(codec)
            body_dict = encode_wrapped_body(codec=codec_obj, body=body_dict)
        envelope = self._envelope_builder.build(
            topic,
            body_dict,
            schema_uri=schema_uri,
            band=band,
            trace_id=trace_id,
        )
        return json.dumps(envelope, ensure_ascii=False).encode("utf-8")

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            msg = "HttpTransport not opened. Call await transport.open() first."
            raise RuntimeError(msg)
        return self._client
