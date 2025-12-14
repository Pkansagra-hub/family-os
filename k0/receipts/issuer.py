"""Receipt issuance pipeline integrating signing and observability."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import Mapping, MutableSequence, Protocol, Sequence

from nacl.signing import SigningKey

from k0.obs.events import ObservabilityEmitter
from k0.policy.pep_syscall import Obligation
from k0.security.crypto import canonical_json, encode_base64url
from k0.storage.receipts import Receipt, ReceiptStore

logger = logging.getLogger(__name__)


class MetricsRecorder(Protocol):
    """Callable protocol mirroring the kernel-wide metrics emitter signature."""

    def __call__(self, metric_name: str, value: float, **labels: str) -> None: ...


@dataclass(slots=True)
class ReceiptDocument:
    """V1 receipt with envelope integrity and obligation proof."""

    receipt_id: str
    idem_key: str
    wal_pos: int
    commit_ts: str
    tenant_id: str
    space_id: str
    device_id: str

    # V1 NEW FIELD: Full envelope hash for integrity verification
    envelope_sha256: str  # SHA-256 of canonical envelope (not just body)

    mls_group_id: str
    key_version: str
    device_sig: str
    obligations: tuple[str, ...]

    # V1 NEW FIELD: Proof of applied obligations (GDPR/CCPA compliance)
    obligations_applied: tuple[
        str, ...
    ] = ()  # Specific actions taken (e.g., "kernel.mask.location.AMBER")

    manifest_fingerprint: str | None = None
    obligation_details: tuple[dict[str, str], ...] = ()

    # Legacy field (deprecated in V1)
    payload_sha256: str | None = None  # DEPRECATED: Use envelope_sha256 instead


class ReceiptSigner:
    """Wrapper around an Ed25519 signing key producing base64url signatures."""

    def __init__(self, signing_key: SigningKey) -> None:
        self._signing_key = signing_key

    def sign(self, payload: Mapping[str, object]) -> str:
        canonical = canonical_json(payload).encode("utf-8")
        signature = self._signing_key.sign(canonical).signature
        return encode_base64url(signature)


class ReceiptIssuer:
    """Issue signed receipts, persist them, and fan-out observability signals."""

    def __init__(
        self,
        *,
        receipt_store: ReceiptStore,
        signer: ReceiptSigner,
        metrics_recorder: MetricsRecorder | None = None,
        observability_emitter: ObservabilityEmitter | None = None,
    ) -> None:
        self._store = receipt_store
        self._signer = signer
        self._metrics = metrics_recorder
        self._observability = observability_emitter

    def issue(
        self,
        *,
        receipt_id: str,
        idem_key: str,
        wal_pos: int,
        commit_ts: str,
        tenant_id: str,
        space_id: str,
        device_id: str,
        envelope_sha256: str,  # V1: Full envelope hash (REQUIRED)
        mls_group_id: str,
        key_version: str,
        obligations: Sequence[Obligation | str] = (),
        obligations_applied: Sequence[str] = (),  # V1: Specific actions taken
        manifest_fingerprint: str | None = None,
        payload_sha256: str | None = None,  # V1: Optional (legacy, deprecated)
        connection: sqlite3.Connection | None = None,
    ) -> ReceiptDocument:
        """Create, sign, persist, and emit observability for a receipt.

        V1 CHANGES:
        - envelope_sha256 (REQUIRED): SHA-256 hash of full canonical envelope
        - obligations_applied (optional): List of specific obligation actions applied
        - payload_sha256 (optional): DEPRECATED - Use envelope_sha256 for integrity verification
        """

        names, detail_payloads = self._normalise_obligations(obligations)
        signature_payload: dict[str, object] = {
            "receipt_id": receipt_id,
            "idem_key": idem_key,
            "wal_pos": wal_pos,
            "commit_ts": commit_ts,
            "tenant_id": tenant_id,
            "space_id": space_id,
            "device_id": device_id,
            "envelope_sha256": envelope_sha256,  # V1: Full envelope hash
            "mls_group_id": mls_group_id,
            "key_version": key_version,
            "obligations": list(names),
        }
        # V1: Include specific obligation actions if provided
        if obligations_applied:
            signature_payload["obligations_applied"] = list(obligations_applied)

        if manifest_fingerprint is not None:
            signature_payload["policy_manifest_fingerprint"] = manifest_fingerprint
        device_sig = self._signer.sign(signature_payload)

        stored_receipt = Receipt(
            receipt_id=receipt_id,
            idem_key=idem_key,
            wal_pos=wal_pos,
            commit_ts=commit_ts,
            tenant_id=tenant_id,
            space_id=space_id,
            device_id=device_id,
            mls_group_id=mls_group_id,
            key_version=key_version,
            device_sig=device_sig,
            manifest_fingerprint=manifest_fingerprint,
        )

        try:
            self._store.save(stored_receipt, connection=connection)
        except Exception as exc:  # noqa: BLE001
            self._emit_metric(
                "receipt_issue_total",
                1.0,
                outcome="failure",
                error=exc.__class__.__name__,
            )
            raise
        else:
            self._emit_metric(
                "receipt_issue_total",
                1.0,
                outcome="success",
            )

        self._emit_observability_event(
            {
                "event": "receipt_issued",
                "receipt_id": receipt_id,
                "idem_key": idem_key,
                "wal_pos": wal_pos,
                "commit_ts": commit_ts,
                "tenant_id": tenant_id,
                "space_id": space_id,
                "device_id": device_id,
                "envelope_sha256": envelope_sha256,  # V1: Full envelope hash
                "mls_group_id": mls_group_id,
                "key_version": key_version,
                "obligations": list(names),
                "obligations_applied": list(obligations_applied),  # V1: Specific actions
                "obligation_details": detail_payloads,
                "policy_manifest_fingerprint": manifest_fingerprint,
            }
        )

        return ReceiptDocument(
            receipt_id=receipt_id,
            idem_key=idem_key,
            wal_pos=wal_pos,
            commit_ts=commit_ts,
            tenant_id=tenant_id,
            space_id=space_id,
            device_id=device_id,
            envelope_sha256=envelope_sha256,  # V1: Full envelope hash
            mls_group_id=mls_group_id,
            key_version=key_version,
            device_sig=device_sig,
            obligations=names,
            obligations_applied=tuple(obligations_applied),  # V1: Specific actions
            manifest_fingerprint=manifest_fingerprint,
            obligation_details=tuple(detail_payloads),
            payload_sha256=payload_sha256,  # V1: Optional legacy field
        )

    def _normalise_obligations(
        self, obligations: Sequence[Obligation | str]
    ) -> tuple[tuple[str, ...], list[dict[str, str]]]:
        names: MutableSequence[str] = []
        details: list[dict[str, str]] = []
        for entry in obligations:
            if isinstance(entry, Obligation):
                names.append(entry.name)
                details.append(dict(entry.details))
            else:
                names.append(str(entry))
                details.append({})
        return tuple(names), details

    def _emit_metric(self, metric_name: str, value: float, **labels: str) -> None:
        if self._metrics is None:
            return
        try:
            self._metrics(metric_name, value, **labels)
        except Exception:  # pragma: no cover - defensive logging guard  # noqa: BLE001
            logger.exception("Failed to record metric", extra={"metric": metric_name})

    def _emit_observability_event(self, payload: Mapping[str, object]) -> None:
        if self._observability is None:
            return
        try:
            self._observability.emit(payload)
        except Exception:  # pragma: no cover - defensive logging guard  # noqa: BLE001
            logger.exception(
                "Failed to emit receipt observability event",
                extra={"event": payload.get("event")},
            )


__all__ = [
    "ReceiptDocument",
    "ReceiptIssuer",
    "ReceiptSigner",
]
