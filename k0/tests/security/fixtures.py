"""Reusable fixtures and helpers for the security Ward suites (Issue 8.2.3)."""

from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Mapping

from nacl.signing import SigningKey
from ward import fixture  # type: ignore[attr-defined]

from k0.gate import MinimalGate, SchemaRecord, SchemaRegistry
from k0.idem import IdempotencyLedger
from k0.obs import MetricsExporter, ObservabilityEmitter
from k0.security import canonical_envelope, hash_payload
from k0.storage.provisioning import DeviceKey, ProvisionedDevice, ProvisioningLedger
from k0.uow.connection_pool import connection_scope
from k0.tests.storage.fixtures import sqlite_runtime  # type: ignore[misc]

__all__ = [
    "SignedPayload",
    "SecuritySuiteContext",
    "LedgerSuiteContext",
    "security_suite_context",
    "ledger_suite_context",
]


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iso_past(hours: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(
        timespec="seconds"
    )


def _iso_future(hours: int = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(
        timespec="seconds"
    )


def _invalidate_signature(value: str) -> str:
    if not value:
        return "A"
    return "A" * len(value)


@dataclass(slots=True)
class SignedPayload:
    envelope: Dict[str, Any]
    body: bytes | None = None

    def cloned_envelope(self) -> Dict[str, Any]:
        return deepcopy(self.envelope)


@dataclass(slots=True)
class SecuritySuiteContext:
    ledger: ProvisioningLedger
    registry: SchemaRegistry
    device: ProvisionedDevice
    attacker_device: ProvisionedDevice
    keys: Mapping[str, SigningKey]
    base_envelope: Dict[str, Any]
    metrics: MetricsExporter
    observability: ObservabilityEmitter

    def gate(self) -> MinimalGate:
        return MinimalGate(
            provisioning=self.ledger,
            registry=self.registry,
            metrics=self.metrics,
            observability=self.observability,
        )

    def sign(
        self,
        envelope: Mapping[str, Any] | None = None,
        *,
        signer: str = "active",
        body: bytes | None = None,
        include_payload_hash: bool = True,
    ) -> Dict[str, Any]:
        target = deepcopy(dict(envelope or self.base_envelope))
        target.pop("sig", None)
        target.pop("idem_key", None)
        if body is not None and include_payload_hash:
            target["payload_sha256"] = hash_payload(body)
        canonical = canonical_envelope(target)
        signature = self.keys[signer].sign(canonical).signature
        target["sig"] = _b64url(signature)
        return target

    def payload_library(self) -> Dict[str, SignedPayload]:
        body = b'{"data": "security-test"}'
        valid_active = SignedPayload(self.sign(body=body), body)
        valid_rotating = SignedPayload(self.sign(signer="rotating", body=body), body)
        tampered_signature_env = deepcopy(valid_active.envelope)
        tampered_signature_env["sig"] = _invalidate_signature(
            tampered_signature_env.get("sig", "")
        )
        tampered_payload_env = deepcopy(valid_active.envelope)
        tampered_payload_env["payload_sha256"] = "f" * 64
        replay_env = deepcopy(valid_active.envelope)
        replay_env["space_id"] = "space-adversary"
        idem_spoof_env = deepcopy(valid_active.envelope)
        idem_spoof_env["idem_key"] = "deadbeef" * 8
        missing_sig_env = deepcopy(valid_active.envelope)
        missing_sig_env.pop("sig", None)
        return {
            "valid_active": valid_active,
            "valid_rotating": valid_rotating,
            "tampered_signature": SignedPayload(tampered_signature_env, body),
            "tampered_payload_hash": SignedPayload(tampered_payload_env, body),
            "replay_cross_space": SignedPayload(replay_env, body),
            "idem_key_spoof": SignedPayload(idem_spoof_env, body),
            "missing_signature": SignedPayload(missing_sig_env, body),
        }

    def metric_value(self, metric_name: str, **labels: str) -> float | None:
        prom_metric = f"{self.metrics.namespace}_{metric_name}_total"
        return self.metrics.registry.get_sample_value(prom_metric, labels)

    def snapshot_metrics(self, destination: str | Path) -> Path:
        """Serialize captured Prometheus metrics to *destination*."""

        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.metrics.latest())
        return path


@dataclass(slots=True)
class LedgerSuiteContext:
    ledger: IdempotencyLedger
    metrics: MetricsExporter
    observability: ObservabilityEmitter

    def metric_value(self, metric_name: str, **labels: str) -> float | None:
        prom_metric = f"{self.metrics.namespace}_{metric_name}_total"
        return self.metrics.registry.get_sample_value(prom_metric, labels)

    def snapshot_metrics(self, destination: str | Path) -> Path:
        """Serialize ledger Prometheus metrics to *destination*."""

        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.metrics.latest())
        return path


@fixture
def ledger_suite_context(
    _sqlite_runtime: Any = sqlite_runtime,
) -> LedgerSuiteContext:
    _ = _sqlite_runtime

    metrics = MetricsExporter()
    observability = ObservabilityEmitter()
    ledger = IdempotencyLedger(metrics=metrics, observability=observability)

    with connection_scope() as conn:
        conn.execute("DELETE FROM idem_ledger")
        conn.commit()

    return LedgerSuiteContext(
        ledger=ledger,
        metrics=metrics,
        observability=observability,
    )


@fixture
def security_suite_context(
    _sqlite_runtime: Any = sqlite_runtime,
) -> SecuritySuiteContext:
    _ = _sqlite_runtime  # ensure pool initialised via fixture

    ledger = ProvisioningLedger(cache_size=64)
    registry = SchemaRegistry()
    metrics = MetricsExporter()
    observability = ObservabilityEmitter()

    active_key = SigningKey.generate()
    rotating_key = SigningKey.generate()
    revoked_key = SigningKey.generate()
    pending_key = SigningKey.generate()
    attacker_key = SigningKey.generate()

    device = ProvisionedDevice(
        device_id="device-security-fixture",
        tenant_id="tenant-alpha",
        space_id="space-omega",
        mls_group_id="mls-group-primary",
        provisioned_ts=_iso_past(48),
    )
    attacker_device = ProvisionedDevice(
        device_id="device-attacker",
        tenant_id="tenant-alpha",
        space_id="space-omega",
        mls_group_id="mls-group-attacker",
        provisioned_ts=_iso_now(),
    )

    with connection_scope() as conn:
        ledger.register(device, connection=conn)
        ledger.register(attacker_device, connection=conn)
        ledger.add_key(
            DeviceKey(
                device_id=device.device_id,
                key_version="v1-active",
                verify_key=_b64url(bytes(active_key.verify_key)),
                key_state="ACTIVE",
                registered_ts=_iso_past(72),
                activated_ts=_iso_past(48),
            ),
            connection=conn,
        )
        ledger.add_key(
            DeviceKey(
                device_id=device.device_id,
                key_version="v2-rotating",
                verify_key=_b64url(bytes(rotating_key.verify_key)),
                key_state="ROTATING",
                registered_ts=_iso_past(24),
                activated_ts=_iso_past(12),
                rotated_ts=_iso_past(6),
                grace_expires_ts=_iso_future(6),
            ),
            connection=conn,
        )
        ledger.add_key(
            DeviceKey(
                device_id=device.device_id,
                key_version="v0-revoked",
                verify_key=_b64url(bytes(revoked_key.verify_key)),
                key_state="REVOKED",
                registered_ts=_iso_past(120),
                activated_ts=_iso_past(96),
                revoked_ts=_iso_past(24),
                revocation_reason="Revoked for security fixture",
            ),
            connection=conn,
        )
        ledger.add_key(
            DeviceKey(
                device_id=device.device_id,
                key_version="v3-pending",
                verify_key=_b64url(bytes(pending_key.verify_key)),
                key_state="PENDING",
                registered_ts=_iso_now(),
            ),
            connection=conn,
        )
        ledger.add_key(
            DeviceKey(
                device_id=attacker_device.device_id,
                key_version="v1-attacker",
                verify_key=_b64url(bytes(attacker_key.verify_key)),
                key_state="ACTIVE",
                registered_ts=_iso_now(),
                activated_ts=_iso_now(),
            ),
            connection=conn,
        )

        registry.upsert(
            SchemaRecord(
                uri="schema://memory.delta",
                version="1.0",
                sha256="a" * 64,
                status="ACTIVE",
            ),
            connection=conn,
        )
        registry.upsert(
            SchemaRecord(
                uri="schema://memory.blocked",
                version="1.0",
                sha256="b" * 64,
                status="ACTIVE",
            ),
            connection=conn,
        )
        registry.block(
            "schema://memory.blocked",
            "1.0",
            operator_id="security@family-ai",
            reason="CVE-2025-SECURITY-001",
            connection=conn,
        )
        conn.commit()

    base_envelope: Dict[str, Any] = {
        "tenant_id": device.tenant_id,
        "space_id": device.space_id,
        "device_id": device.device_id,
        "actor": "user-alice",
        "topic": "memory.delta",
        "schema_uri": "schema://memory.delta",
        "schema_version": "1.0",
        "band": "GREEN",
        "ts": _iso_now(),
    }

    keys = {
        "active": active_key,
        "rotating": rotating_key,
        "revoked": revoked_key,
        "pending": pending_key,
        "attacker": attacker_key,
    }

    return SecuritySuiteContext(
        ledger=ledger,
        registry=registry,
        device=device,
        attacker_device=attacker_device,
        keys=keys,
        base_envelope=base_envelope,
        metrics=metrics,
        observability=observability,
    )

