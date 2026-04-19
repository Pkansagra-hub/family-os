"""BridgeCommandAdapter -- bridges MW's IBridgeCommandPort to Bridge's KernelCommandPort.

Translates:
  MW  submit(topic, schema_uri, body)
  ->  client.submit_command(topic, body, schema_uri=schema_uri, trace_id=body.get("trace_id"))

  MW  submit_batch(envelopes)
  ->  client.submit_command_batch(envelopes)

MW-03: This is the ONLY output path from MW to K0.
MW-09: KernelCommandPort already handles offline queueing via LocalOutbox.
MW-10: trace_id extracted from envelope body and passed to Bridge.

References:
  - E-MW-5.1: Production Adapters
  - k1/memory_writer/ports/bridge_command_port.py (IBridgeCommandPort)
  - bridge/kernel/command_port.py (KernelCommandPort)
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class _IKernelCommandPort(Protocol):
    """Minimal local Protocol for Bridge KernelCommandPort dependency (MW-03)."""

    async def submit_command(
        self,
        topic: str,
        body: dict,
        schema_uri: str,
        trace_id: str,
    ) -> Any: ...

    async def submit_command_batch(self, envelopes: list[dict]) -> Any: ...


class BridgeCommandAdapter:
    """Implements IBridgeCommandPort by wrapping Bridge's KernelCommandPort.

    Constructor Args:
        command_port: Bridge's KernelCommandPort instance (typed as Any
            to avoid import coupling, matching SessionReadAdapter pattern).
    """

    __slots__ = ("_command_port",)

    def __init__(self, command_port: _IKernelCommandPort) -> None:
        self._command_port = command_port

    async def submit(
        self,
        topic: str,
        schema_uri: str,
        body: dict,
    ) -> None:
        """Submit a single command envelope to K0 via Bridge.

        Delegates to KernelCommandPort.submit() with trace_id
        extracted from the body (MW-10).
        """
        trace_id = body.get("trace_id", "")
        await self._command_port.submit_command(
            topic=topic,
            body=body,
            schema_uri=schema_uri,
            trace_id=trace_id,
        )

    async def submit_batch(
        self,
        envelopes: list[dict],
    ) -> None:
        """Submit a batch of command envelopes to K0 via Bridge.

        Each envelope dict must contain: topic, schema_uri, body, trace_id.
        Translates to Bridge's CommandEnvelope format.
        """
        if not envelopes:
            return
        await self._command_port.submit_command_batch(envelopes)
