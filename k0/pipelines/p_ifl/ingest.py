"""IFL ingest orchestrator (MS-5 PR#4).

Drives the existing P02 write-ingest pipeline once per IFL atom.
Adapter-specific normalizers (Google Calendar, GitHub, etc.) live in
sibling modules and produce one ``MemoryAtom``-shaped dict per
upstream record. This orchestrator validates each dict against the
generated ``MemoryWriteV1`` Pydantic model so we get one consistent
contract surface, then forwards to ``k0.pipelines.p02_write_ingest``.

Locked decision #7 (per the MS-5 plan): ingestion drives the
existing memory.write.v1 *bus contract*, no new K0 HTTP route.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from bridge._generated.k0.models.memory_write_v1 import MemoryWriteV1
from k0.pipelines import p02_write_ingest


@dataclass(frozen=True, slots=True)
class IFLIngestResult:
    """One ack envelope per ingested atom."""

    atom_id: str
    topic: str
    ack: bool


def ingest_atoms(
    atom_payloads: Sequence[dict[str, Any]],
) -> list[IFLIngestResult]:
    """Validate and ingest a batch of MemoryAtom payloads via P02.

    Each payload must satisfy v2.2 ``memory.write.v1``. Validation
    errors raise :class:`pydantic.ValidationError`; the orchestrator
    is intentionally fail-fast so a single malformed event aborts
    the batch and surfaces the error to the caller (the IFL adapter
    side, where it gets recorded against the consent ledger).
    """
    results: list[IFLIngestResult] = []
    for raw in atom_payloads:
        atom = MemoryWriteV1.model_validate(raw)
        ack = p02_write_ingest.ingest(atom)
        results.append(
            IFLIngestResult(
                atom_id=str(ack["atom_id"]),
                topic=str(ack["topic"]),
                ack=bool(ack["ack"]),
            )
        )
    return results
