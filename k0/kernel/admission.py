"""Utilities for recording admission decisions during request handling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, cast

from fastapi import Request

from ..policy.pep_syscall import PolicyDecision
from ..storage.receipts import Receipt

_ADMISSION_STATE_KEY = "_k0_admission_records"


@dataclass(slots=True)
class AdmissionRecord:
    """Captured admission decision alongside contextual metadata."""

    decision: PolicyDecision
    envelope: dict[str, Any]
    receipt: Receipt | None
    port: str


def record_admission_decision(
    request: Request,
    *,
    decision: PolicyDecision,
    envelope: Mapping[str, Any],
    receipt: Receipt | None = None,
    port: str = "command",
) -> None:
    """Append an admission record to the request lifecycle."""

    payload = dict(envelope)
    record = AdmissionRecord(
        decision=decision, envelope=payload, receipt=receipt, port=port
    )
    records = getattr(request.state, _ADMISSION_STATE_KEY, None)
    if records is None:
        records_list: list[AdmissionRecord] = []
        setattr(request.state, _ADMISSION_STATE_KEY, records_list)
        records = records_list
    else:
        records = cast(list[AdmissionRecord], records)
    records.append(record)


def consume_admission_records(request: Request) -> list[AdmissionRecord]:
    """Return and clear any admission records attached to *request*."""

    records = getattr(request.state, _ADMISSION_STATE_KEY, None)
    if not records:
        return []
    records_list = cast(list[AdmissionRecord], records)
    try:
        delattr(request.state, _ADMISSION_STATE_KEY)
    except AttributeError:  # pragma: no cover - defensive guard
        setattr(request.state, _ADMISSION_STATE_KEY, [])
    return list(records_list)


__all__ = ["AdmissionRecord", "consume_admission_records", "record_admission_decision"]
