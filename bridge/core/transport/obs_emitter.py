"""K1 -> K0 obs/feedback HTTP emitter (MS-3e).

Bridges generated obs clients (``bridge._generated.k1.clients.<topic>``)
to the K0 ``/k0/obs.emit`` endpoint. Posts ``{kind, body}`` shaped JSON
using the runtime-shared ``httpx.AsyncClient`` so connection pooling,
TLS verification, and timeouts match the rest of the bridge transport.

Why a separate emitter (not :class:`HttpTransport.publish`)?

* ``/k0/obs.emit`` accepts unsigned ``{kind, body}`` payloads, not the
  signed bridge command envelope. Routing it through the command path
  would force every obs payload through the gate / QoS / WAL / receipt
  machinery — wrong cost model for fire-and-forget feedback / metrics.
* Obs is queueable on K0 outage; the same outbox decorator can wrap
  this emitter when 3b.4's ``OnlineFirstClient`` learns the obs shape.

This module is import-cycle-free against ``bridge.runtime``: it only
takes an already-built ``httpx.AsyncClient`` and a base URL, no runtime
import at module top level.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


@runtime_checkable
class IObsEmitter(Protocol):
    """Protocol used by generated obs clients to call into the runtime seam."""

    async def emit(
        self,
        *,
        topic: str,
        kind: str,
        schema_uri: str,
        payload: BaseModel,
    ) -> dict[str, Any]: ...


class ObsHttpEmitter:
    """Posts ``{kind, body}`` to ``/k0/obs.emit`` via a shared httpx client.

    The runtime owns one instance per K1 deployment and wires it as
    ``runtime._obs_emitter``. Generated obs clients reach through this
    seam; tests can substitute a stub implementing :class:`IObsEmitter`.
    """

    OBS_PATH = "/k0/obs.emit"

    def __init__(self, *, base_url: str, http_client: httpx.AsyncClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = http_client if http_client is not None else httpx.AsyncClient()
        self._owns_client = http_client is None

    async def aclose(self) -> None:
        """Close the underlying httpx client iff this emitter owns it."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def emit(
        self,
        *,
        topic: str,
        kind: str,
        schema_uri: str,
        payload: BaseModel,
    ) -> dict[str, Any]:
        """POST ``{"kind": kind, "body": payload.model_dump(...)}`` to ``/k0/obs.emit``.

        Returns the parsed JSON response on 2xx. Raises :class:`httpx.HTTPStatusError`
        on non-2xx so the caller (or an outbox-wrapping decorator) can decide
        whether to queue and retry.

        ``schema_uri`` is accepted for API symmetry with other generated
        clients but is not transmitted on the wire — the K0 endpoint
        re-validates the body via :class:`k0.feedback.FeedbackEnvelope`
        and ``FeedbackSchemaRegistry`` for ``kind=feedback``.
        """
        body = payload.model_dump(mode="json", by_alias=True, exclude_none=True)
        envelope = {"kind": kind, "body": body}
        url = f"{self._base_url}{self.OBS_PATH}"
        response = await self._client.post(
            url,
            json=envelope,
            headers={
                "Content-Type": "application/json",
                "X-Bridge-Topic": topic,
            },
        )
        response.raise_for_status()
        try:
            return response.json()
        except ValueError:
            return {}


__all__ = ["IObsEmitter", "ObsHttpEmitter"]
