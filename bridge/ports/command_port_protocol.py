"""IKernelCommandPort — K1→K0 fire-and-forget command submission.

Extracts the Protocol from the existing concrete KernelCommandPort in
bridge/kernel/command_port.py.  K1 components depend on THIS Protocol;
the concrete class implements it.

Methods:
  submit(topic, body, ...) → None
  submit_batch(envelopes) → None
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..core.envelope_builder import CommandEnvelope


@runtime_checkable
class IKernelCommandPort(Protocol):
    """Fire-and-forget command submission from K1 to K0.

    Topics are drawn from ``k0/contracts/taxonomies/command_topics.yaml``.
    Envelopes are signed, hashed, and submitted via HTTP transport.

    Offline behaviour:
        When K0 is unreachable (429/5xx), the implementation SHOULD
        enqueue to ``LocalOutbox`` and return silently.

    Raises:
        ContractViolationError — 400 from K0 Gate (caller bug).
        PolicyDeniedError      — 403 from K0 PEP (policy denied).
    """

    async def submit(
        self,
        topic: str,
        body: dict[str, Any],
        *,
        schema_uri: str | None = None,
        band: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        """Submit a single command envelope to K0.  Fire-and-forget."""
        ...  # pragma: no cover

    async def submit_batch(self, envelopes: list[CommandEnvelope]) -> None:
        """Submit multiple command envelopes with bounded concurrency.

        Max batch size: 50 envelopes.
        """
        ...  # pragma: no cover
