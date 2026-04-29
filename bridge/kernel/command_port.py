"""Concrete IKernelCommandPort -- Bridge transport to K0 command port.

Implements fire-and-forget submission with per-envelope error handling
and automatic offline queueing on K0 unavailability.

Per bridge/contracts/command_port.protocol.yaml interface + errors sections.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from ..core.envelope_builder import CommandEnvelope, EnvelopeBuilder
from ..core.transport import HttpTransport

if TYPE_CHECKING:
    from ..ports.command_port_protocol import IKernelCommandPort

logger = logging.getLogger(__name__)

# Canonical JSON must match K0 and EnvelopeBuilder
_CANONICAL_SEPARATORS = (",", ":")

# Max envelopes in-flight for submit_batch (protocol contract)
_MAX_BATCH_CONCURRENCY = 3
_MAX_BATCH_SIZE = 50


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class ContractViolationError(Exception):
    """K0 Gate rejected the envelope (400/403) -- indicates a caller bug."""


class PolicyDeniedError(ContractViolationError):
    """K0 PEP denied the request (403) -- policy forbids this topic/band."""


# ---------------------------------------------------------------------------
# KernelCommandPort
# ---------------------------------------------------------------------------


class KernelCommandPort:
    """Bridge-side command port for submitting envelopes to K0.

    Orchestrates envelope building, HTTP transport, and offline queueing.

    Parameters
    ----------
    transport : HttpTransport
        HTTP client for K0 communication (must be opened before use).
    builder : EnvelopeBuilder
        Envelope construction and signing.
    outbox : LocalOutbox | None
        Optional offline queue.  When provided, 429/5xx responses
        trigger automatic enqueue instead of raising.
    """

    def __init__(
        self,
        transport: HttpTransport,
        builder: EnvelopeBuilder,
        outbox: Any | None = None,  # LocalOutbox (optional, avoids circular import)
    ) -> None:
        self._transport = transport
        self._builder = builder
        self._outbox = outbox

    async def submit(
        self,
        topic: str,
        body: dict[str, Any],
        *,
        schema_uri: str | None = None,
        band: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        """Submit a single command envelope to K0.

        Fire-and-forget semantics: returns ``None`` on success.

        Parameters
        ----------
        topic : str
            Command topic from command_topics.yaml.
        body : dict
            Domain payload matching the per-topic body schema.
        schema_uri : str | None
            Explicit schema URI.  Derived from topic if omitted.
        band : str | None
            Privacy band override.
        trace_id : str | None
            Cognitive trace ID.  Generated if omitted.

        Raises
        ------
        ContractViolationError
            On 400 from K0 Gate (invalid envelope -- caller bug).
        PolicyDeniedError
            On 403 from K0 PEP (policy denied this topic/band).
        """
        envelope = self._builder.build(
            topic=topic,
            body=body,
            schema_uri=schema_uri,
            band=band,
            trace_id=trace_id,
        )
        await self._send_envelope(envelope, topic)

    async def submit_batch(self, envelopes: list[CommandEnvelope]) -> None:
        """Submit multiple envelopes with bounded concurrency.

        Each envelope is processed individually with per-envelope error
        handling.  Contract violations (400/403) are collected and raised
        after all envelopes have been attempted.

        Parameters
        ----------
        envelopes : list[CommandEnvelope]
            Pre-built envelope descriptors.

        Raises
        ------
        ContractViolationError
            If any envelope was rejected by Gate (400/403).  Contains
            details of all rejected envelopes.
        """
        if len(envelopes) > _MAX_BATCH_SIZE:
            msg = f"Batch size {len(envelopes)} exceeds maximum {_MAX_BATCH_SIZE}"
            raise ValueError(msg)

        semaphore = asyncio.Semaphore(_MAX_BATCH_CONCURRENCY)
        errors: list[str] = []

        async def _submit_one(cmd: CommandEnvelope) -> None:
            async with semaphore:
                try:
                    envelope = self._builder.build_from_command_envelope(cmd)
                    await self._send_envelope(envelope, cmd.topic)
                except ContractViolationError as exc:
                    errors.append(f"{cmd.topic}: {exc}")

        await asyncio.gather(*[_submit_one(cmd) for cmd in envelopes])

        if errors:
            msg = f"Batch had {len(errors)} contract violation(s): {'; '.join(errors)}"
            raise ContractViolationError(msg)

    # -- internal submission -------------------------------------------------

    async def _send_envelope(self, envelope: dict[str, Any], topic: str) -> None:
        """Send a built envelope to K0 and handle the response."""
        envelope_json = json.dumps(
            envelope,
            ensure_ascii=False,
            sort_keys=True,
            separators=_CANONICAL_SEPARATORS,
        ).encode("utf-8")

        result = await self._transport.post_command(envelope_json)

        # 200: Success (fire-and-forget)
        if result.status_code == 200:
            logger.debug("K0 accepted envelope: topic=%s", topic)
            return

        # 409: Idempotent duplicate (safe to ignore)
        if result.status_code == 409:
            logger.info("K0 duplicate (409): topic=%s", topic)
            return

        # 400: Contract violation (caller bug)
        if result.status_code == 400:
            detail = result.body.get("reason", "unknown") if result.body else "unknown"
            logger.error("K0 rejected envelope (400): topic=%s reason=%s", topic, detail)
            raise ContractViolationError(f"Gate rejected: {detail}")

        # 403: Policy denied
        if result.status_code == 403:
            detail = result.body.get("reason", "policy_denied") if result.body else "policy_denied"
            logger.error("K0 policy denied (403): topic=%s reason=%s", topic, detail)
            raise PolicyDeniedError(f"Policy denied: {detail}")

        # 429 / 5xx: Enqueue to offline outbox
        if result.status_code == 429 or result.status_code >= 500 or result.status_code == 0:
            if self._outbox is not None:
                self._outbox.enqueue(
                    envelope_json=envelope_json.decode("utf-8"),
                    topic=topic,
                    priority=self._extract_priority(envelope),
                )
                logger.warning(
                    "K0 unavailable (status=%d): enqueued to LocalOutbox topic=%s",
                    result.status_code,
                    topic,
                )
                return
            # No outbox: log and return (fire-and-forget, best effort)
            logger.error(
                "K0 unavailable (status=%d) and no LocalOutbox configured: topic=%s LOST",
                result.status_code,
                topic,
            )
            return

        # Unexpected status
        logger.warning(
            "K0 unexpected status %d for topic=%s: %s",
            result.status_code,
            topic,
            result.body,
        )

    @staticmethod
    def _extract_priority(envelope: dict[str, Any]) -> int:
        """Extract numeric priority from envelope (default NORMAL=2)."""
        return 2


# P7.7: Static structural-conformance check. KernelCommandPort implements
# IKernelCommandPort (declared in bridge/ports/command_port_protocol.py).
# The assignment below is a no-op at runtime but causes mypy/pyright to
# verify the class satisfies the Protocol.
if TYPE_CHECKING:
    _proto_check: type[IKernelCommandPort] = KernelCommandPort  # type: ignore[assignment]
