"""Shim that adapts IBridgeClient (SinkBridgeClient) to BridgeWriteAdapter's
local IBridgeClient protocol (write/read).

BridgeWriteAdapter expects:
  write(channel, payload, *, trace_id) -> None
  read(channel, key) -> Any

SinkBridgeClient provides:
  submit_command(topic, body, *, schema_uri, band, trace_id) -> None
  (no read equivalent — returns empty for offline)

This shim maps between the two so the Orchestrator can use a real
bridge client instead of MockBridgeAdapter when offline.

Issue 3.10.3 (MS-3): Replace MockBridgeAdapter with real sink path.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class BridgeClientShim:
    """Adapts SinkBridgeClient to BridgeWriteAdapter's write/read protocol.

    Write operations are forwarded to submit_command (queued to LocalOutbox).
    Read operations return empty (K0 offline).
    """

    __slots__ = ("_client",)

    def __init__(self, client: Any) -> None:
        self._client = client

    async def write(
        self,
        channel: str,
        payload: dict[str, Any],
        *,
        trace_id: str,
    ) -> None:
        """Map write(channel, payload) → submit_command(topic=channel, body=payload)."""
        await self._client.submit_command(
            topic=channel,
            body=payload,
            trace_id=trace_id,
        )

    async def read(
        self,
        channel: str,
        key: str,
    ) -> Any:
        """Offline: no K0 available, return None."""
        logger.debug(
            "BridgeClientShim.read(%s, %s): offline — returning None",
            channel,
            key,
        )
        return None
