"""Utilities for recording admission decisions during request handling."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, cast

from fastapi import Request

from ..policy.pep_syscall import PolicyDecision
from ..storage.receipts import Receipt
from ..security import canonical_json

_ADMISSION_STATE_KEY = "_k0_admission_records"


@dataclass(slots=True)
class AdmissionRecord:
    """Captured admission decision alongside contextual metadata."""

    decision: PolicyDecision
    envelope: dict[str, Any]
    receipt: Receipt | None
    port: str
    sanitized_body_sha256: str | None
    original_body_sha256: str | None


def record_admission_decision(
    request: Request,
    *,
    decision: PolicyDecision,
    envelope: Mapping[str, Any],
    receipt: Receipt | None = None,
    port: str = "command",
    sanitized_body: Mapping[str, Any] | None = None,
    original_body: Mapping[str, Any] | None = None,
    manifest_fingerprint: str | None = None,
) -> None:
    """Append an admission record to the request lifecycle."""

    observability_emitter = getattr(request.app.state, "observability_emitter", None)

    sanitized_hash = _hash_body(sanitized_body)
    original_hash = _hash_body(original_body)

    payload = dict(envelope)
    record = AdmissionRecord(
        decision=decision,
        envelope=payload,
        receipt=receipt,
        port=port,
        sanitized_body_sha256=sanitized_hash,
        original_body_sha256=original_hash,
    )
    records = getattr(request.state, _ADMISSION_STATE_KEY, None)
    if records is None:
        records_list: list[AdmissionRecord] = []
        setattr(request.state, _ADMISSION_STATE_KEY, records_list)
        records = records_list
    else:
        records = cast(list[AdmissionRecord], records)
    records.append(record)

    if observability_emitter is not None:
        decision_label = "allow" if decision.admit else "deny"
        obligation_names: list[str] = []
        obligation_detail_payloads: list[dict[str, Any]] = []
        for obligation in decision.obligations:
            obligation_names.append(getattr(obligation, "name", str(obligation)))
            details = getattr(obligation, "details", {})
            if isinstance(details, Mapping):
                obligation_detail_payloads.append(
                    {str(key): value for key, value in details.items()}
                )
            else:
                obligation_detail_payloads.append({})

        event_payload: dict[str, Any] = {
            "event": f"{port}_policy_decision",
            "port": port,
            "decision": decision_label,
            "deny_reason": decision.deny_reason,
            "obligations": obligation_names,
            "obligation_details": obligation_detail_payloads,
            "manifest_fingerprint": manifest_fingerprint,
            "sanitized_body_sha256": sanitized_hash,
            "original_body_sha256": original_hash,
        }

        envelope_summary_keys = (
            "tenant_id",
            "space_id",
            "topic",
            "schema_uri",
            "schema_version",
            "policy_version",
            "band",
            "idem_key",
            "payload_sha256",
            "payload_bytes",
        )
        for key in envelope_summary_keys:
            if key in payload:
                event_payload[key] = payload[key]

        if receipt is not None:
            event_payload.update(
                {
                    "receipt_id": receipt.receipt_id,
                    "wal_pos": receipt.wal_pos,
                    "idem_key": receipt.idem_key,
                }
            )

        trace_id = getattr(request.state, "cognitive_trace_id", None)
        if trace_id:
            event_payload.setdefault("trace_id", trace_id)
        observability_emitter.emit(event_payload)


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


def _hash_body(body: Any | None) -> str | None:
    if body is None:
        return None
    try:
        canonical = canonical_json(body).encode("utf-8")
    except Exception:
        return None
    digest = hashlib.sha256()
    digest.update(canonical)
    return digest.hexdigest()
