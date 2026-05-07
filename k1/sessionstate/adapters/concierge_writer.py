"""ConciergeWriterAdapter -- Concierge-routed mutation writer [E-0.5.11 stub].

Replaces ``DirectWriterAdapter`` when Concierge is the single writer.
Routes mutations through Concierge FSM queue so sub-agents propose deltas
to Concierge rather than writing directly (ADR-0017 enforcement).

Blocked by: Concierge factory / wiring (MS-2+, see also E-0.5.21).
Current stand-in: ``DirectWriterAdapter`` (direct mutation, standalone).
"""

from __future__ import annotations

from ..ports.writer import (
    BatchRequest,
    BatchResult,
    IWriterPort,
    MutationRequest,
    MutationResponse,
    WriterAuthorization,
)

_BLOCKED = "ConciergeWriterAdapter blocked by Concierge wiring — target: MS-2+"


class ConciergeWriterAdapter(IWriterPort):
    """Stub IWriterPort for Concierge-routed mutations.

    All methods raise ``NotImplementedError`` until Concierge factory
    and session wiring exist.
    """

    __slots__ = ()

    @property
    def writer_id(self) -> str:  # noqa: D102
        return "concierge"

    @property
    def is_connected(self) -> bool:  # noqa: D102
        return False

    def request_mutation(
        self,
        request: MutationRequest,
    ) -> MutationResponse:  # noqa: D102
        raise NotImplementedError(_BLOCKED)

    def batch_mutations(
        self,
        batch: BatchRequest,
    ) -> BatchResult:  # noqa: D102
        raise NotImplementedError(_BLOCKED)

    def validate_writer(self, writer_id: str) -> WriterAuthorization:  # noqa: D102
        raise NotImplementedError(_BLOCKED)
