"""In-process HTTP transport for the bridge runtime.

Wraps an ASGI app (the K0 FastAPI app, or the test-only
:mod:`bridge.testing.dispatcher_app`) with ``httpx.ASGITransport`` so
that K1-side code under test can talk to a real handler stack without a
network. Used by the MS-2.5 exit-criterion test and any unit test that
needs a round-trip without live HTTP.
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel

from bridge.runtime import Transport

DISPATCH_PATH = "/bridge/v1/dispatch"


class InProcessHttpTransport(Transport):
    """Async HTTP client bound to an ASGI app via ``httpx.ASGITransport``.

    Designed for tests + the MS-2.5 round-trip. Production runtimes use
    :class:`bridge.core.transport.http.HttpTransport`.
    """

    def __init__(self, *, app: Any, base_url: str = "http://k0.test") -> None:
        self._app = app
        self._base_url = base_url
        self._client: httpx.AsyncClient | None = None

    async def open(self) -> None:
        if self._client is not None:
            return
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self._app),
            base_url=self._base_url,
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("InProcessHttpTransport not opened; call `await transport.open()`")
        return self._client

    async def publish(
        self,
        *,
        topic: str,
        schema_uri: str,
        payload: BaseModel,
        codec: str = "json",
    ) -> dict[str, Any]:
        """POST ``payload`` (serialised) to the bridge dispatcher endpoint.

        The call is intentionally lightweight: real envelope building +
        signing + ledger lookup happens on the K0 side. In MS-2.5 we
        forward the topic, schema_uri, and the Pydantic-dumped body and
        let the dispatcher app validate + route. MS-3a wraps this same
        path inside production K0 ``/k0/command.submit``.

        ``codec`` is accepted for signature parity with
        :class:`bridge.core.transport.HttpTransport.publish` (MS-4) but
        is intentionally a no-op here: the in-process dispatcher app
        always speaks JSON and its purpose is fast unit-test routing,
        not exercising on-the-wire codecs. The MS-4 codec round-trip is
        tested end-to-end against real K0 in
        ``tests/bridge/integration/test_codec_negotiation.py``.
        """
        del codec  # accepted for parity; no-op in-process
        await self.open()
        body = {
            "topic": topic,
            "schema_uri": schema_uri,
            "payload": payload.model_dump(mode="json", by_alias=True),
        }
        response = await self.client.post(DISPATCH_PATH, json=body)
        response.raise_for_status()
        return response.json()
