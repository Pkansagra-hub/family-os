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
    """Materialised receipt returned to clients after command commits."""

    receipt_id: str
    idem_key: str
    wal_pos: int
    commit_ts: str
    tenant_id: str
    space_id: str
    device_id: str
    payload_sha256: str
    mls_group_id: str
    key_version: str
    device_sig: str
    obligations: tuple[str, ...]
    manifest_fingerprint: str | None = None
    obligation_details: tuple[dict[str, str], ...] = ()


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
        payload_sha256: str,
        mls_group_id: str,
        key_version: str,
        obligations: Sequence[Obligation | str] = (),
        manifest_fingerprint: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> ReceiptDocument:
        """Create, sign, persist, and emit observability for a receipt."""

        names, detail_payloads = self._normalise_obligations(obligations)
        signature_payload: dict[str, object] = {
            "receipt_id": receipt_id,
            "idem_key": idem_key,
            "wal_pos": wal_pos,
            "commit_ts": commit_ts,
            "tenant_id": tenant_id,
            "space_id": space_id,
            "device_id": device_id,
            "payload_sha256": payload_sha256,
            "mls_group_id": mls_group_id,
            "key_version": key_version,
            "obligations": list(names),
        }
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
                "payload_sha256": payload_sha256,
                "mls_group_id": mls_group_id,
                "key_version": key_version,
                "obligations": list(names),
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
            payload_sha256=payload_sha256,
            mls_group_id=mls_group_id,
            key_version=key_version,
            device_sig=device_sig,
            obligations=names,
            manifest_fingerprint=manifest_fingerprint,
            obligation_details=tuple(detail_payloads),
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
