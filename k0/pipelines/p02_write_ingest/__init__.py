"""K0 P02 write-ingest pipeline (MS-2.5 minimal stub).

In MS-2.5 the P02 pipeline only needs to acknowledge a memory atom write
deterministically so the bridge dispatch path can be exercised end-to-end.
The full path (validation, sanitization, write-amplification, idempotent
sink, retention tagging) lands in MS-3a / Epic 3a.3.

The ``ingest`` function takes a ``MemoryAtom``-shaped Pydantic model and
returns a small ack dict. It is intentionally side-effect-free in MS-2.5
so contract tests can run hermetically without a database.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def _atom_id_for(payload: BaseModel) -> str:
    """Deterministic ack id for the round-trip test.

    Uses a SHA-256 over the canonical JSON serialisation so the same
    payload → same id, distinct payloads → distinct ids. Production
    P02 generates atom ids from the K0 idempotent-write ledger.
    """
    body = json.dumps(
        payload.model_dump(mode="json", by_alias=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "atom-" + hashlib.sha256(body).hexdigest()[:16]


def ingest(payload: BaseModel) -> dict[str, Any]:
    """Acknowledge a memory write and return an ack envelope.

    The contract handler calls this synchronously. The return shape is
    locked here for MS-2.5: ``{"ack": True, "atom_id": str, "topic":
    "memory.write.v1"}``. MS-3a adds ``ledger_offset`` and
    ``write_amplification_factor``.
    """
    return {
        "ack": True,
        "atom_id": _atom_id_for(payload),
        "topic": "memory.write.v1",
    }
