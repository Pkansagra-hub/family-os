"""Envelope validation and canonicalisation prior to WAL writes."""

from __future__ import annotations

import logging
import sqlite3
import string
from dataclasses import dataclass
from typing import Any, cast

from k0.idem import derive_idem_key
from k0.obs import MetricsExporter, ObservabilityEmitter
from k0.security import (
    SignatureVerificationError,
    canonical_envelope,
    canonical_json,
    hash_payload,
    verify_signature,
)
from k0.storage.provisioning import DeviceKey, ProvisionedDevice, ProvisioningLedger

from .schema_registry import SchemaRegistry

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GateOutcome:
    accepted: bool
    reason: str | None = None
    idem_key: str | None = None
    key_version: str | None = None
    key_state: str | None = None


DEFAULT_MAX_ENVELOPE_BYTES = 64_000
DEFAULT_MAX_BODY_BYTES = 4_194_304

MISSING_BINDINGS = "MISSING_ACTOR_BINDINGS"
DEVICE_NOT_PROVISIONED = "DEVICE_NOT_PROVISIONED"
NO_VALID_KEYS = "NO_VALID_KEYS_FOR_DEVICE"
SPACE_MISMATCH = "SPACE_TENANT_MISMATCH"
PAYLOAD_HASH_MISMATCH = "PAYLOAD_HASH_MISMATCH"
PAYLOAD_HASH_MISSING = "MISSING_PAYLOAD_HASH"
SIGNATURE_MISSING = "MISSING_SIGNATURE"
VERIFY_KEY_MISSING = "MISSING_VERIFY_KEY"
SIGNATURE_INVALID = "INVALID_SIGNATURE"
LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
CANONICALIZATION_ERROR = "CANONICALIZATION_ERROR"
SCHEMA_NOT_ACTIVE = "SCHEMA_NOT_ACTIVE"
SCHEMA_BLOCKED = "SCHEMA_BLOCKED"
SCHEMA_SUNSET = "SCHEMA_SUNSET"
IDEM_KEY_INVALID = "IDEM_KEY_INVALID"
IDEM_KEY_MISMATCH = "IDEM_KEY_MISMATCH"


class MinimalGate:
    """Central gate enforcing envelope correctness contracts."""

    def __init__(
        self,
        *,
        registry: SchemaRegistry | None = None,
        provisioning: ProvisioningLedger | None = None,
        max_envelope_bytes: int = DEFAULT_MAX_ENVELOPE_BYTES,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
        metrics: MetricsExporter | None = None,
        observability: ObservabilityEmitter | None = None,
    ) -> None:
        self._registry = registry or SchemaRegistry()
        self._provisioning = provisioning or ProvisioningLedger()
        if max_envelope_bytes <= 0:
            msg = "max_envelope_bytes must be positive"
            raise ValueError(msg)
        if max_body_bytes <= 0:
            msg = "max_body_bytes must be positive"
            raise ValueError(msg)
        self._max_envelope_bytes = max_envelope_bytes
        self._max_body_bytes = max_body_bytes
        self._metrics = metrics
        self._observability = observability

    def validate(
        self,
        envelope: dict[str, object],
        body: bytes | None = None,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> GateOutcome:
        """Validate the provided envelope.

        Implementation will cover signature verification, payload hashes, size
        caps, schema status checks, and provisioning lookups. The scaffold simply
        ensures provisioning bindings are present and valid.
        """

        canonical_bytes = self._canonicalise_for_limits(envelope)
        if canonical_bytes is None:
            return GateOutcome(False, CANONICALIZATION_ERROR)

        if len(canonical_bytes) > self._max_envelope_bytes:
            return GateOutcome(False, f"{LIMIT_EXCEEDED}:envelope")

        try:
            normalized_body = self._normalize_body(body)
        except TypeError:
            return GateOutcome(False, CANONICALIZATION_ERROR)
        if normalized_body is not None and len(normalized_body) > self._max_body_bytes:
            return GateOutcome(False, f"{LIMIT_EXCEEDED}:body")

        tenant_id = self._extract_identifier(envelope, "tenant_id")
        space_id = self._extract_identifier(envelope, "space_id")
        device_id = self._extract_identifier(envelope, "device_id")
        schema_uri = self._extract_identifier(envelope, "schema_uri")
        schema_version = self._extract_identifier(envelope, "schema_version")

        missing = [
            field
            for field, value in (
                ("tenant_id", tenant_id),
                ("space_id", space_id),
                ("device_id", device_id),
                ("schema_uri", schema_uri),
                ("schema_version", schema_version),
            )
            if value is None
        ]
        if missing:
            missing_fields = ",".join(sorted(missing))
            return GateOutcome(False, f"{MISSING_BINDINGS}:{missing_fields}")

        tenant = cast(str, tenant_id)
        space = cast(str, space_id)
        device = cast(str, device_id)

        assert schema_uri is not None  # for mypy; guarded by missing check
        assert schema_version is not None

        record = self._provisioning.lookup(tenant, space, device, connection=connection)
        if record is None:
            self._emit_provisioning_failure(
                reason=DEVICE_NOT_PROVISIONED,
                tenant=tenant,
                space=space,
                device=device,
                binding=None,
            )
            return GateOutcome(False, DEVICE_NOT_PROVISIONED)

        if not self._binding_matches(record, tenant, space):
            self._emit_provisioning_failure(
                reason=SPACE_MISMATCH,
                tenant=tenant,
                space=space,
                device=device,
                binding=record,
            )
            return GateOutcome(False, SPACE_MISMATCH)

        schema_check = self._validate_schema(
            schema_uri, schema_version, connection=connection
        )
        if schema_check is not None:
            return schema_check

        try:
            expected_hash = self._normalize_hash(
                self._extract_optional(envelope, "payload_sha256")
            )
        except ValueError:
            return GateOutcome(False, PAYLOAD_HASH_MISMATCH)

        computed_hash = hash_payload(normalized_body)
        if normalized_body is not None:
            if expected_hash is None:
                return GateOutcome(False, PAYLOAD_HASH_MISSING)
            if computed_hash != expected_hash:
                return GateOutcome(False, PAYLOAD_HASH_MISMATCH)
        elif expected_hash is not None:
            return GateOutcome(False, PAYLOAD_HASH_MISMATCH)

        signature = self._extract_optional(envelope, "sig")
        if signature is None:
            return GateOutcome(False, SIGNATURE_MISSING)

        # Query all verification-eligible keys (ACTIVE + ROTATING states)
        keys = self._provisioning.get_keys(
            device,
            states=["ACTIVE", "ROTATING"],
            connection=connection,
        )
        if not keys:
            self._emit_signature_failure(
                tenant=tenant,
                space=space,
                device=device,
                schema_uri=schema_uri,
                schema_version=schema_version,
                reason=NO_VALID_KEYS,
            )
            return GateOutcome(False, NO_VALID_KEYS)

        try:
            message = canonical_envelope(envelope)
        except (TypeError, ValueError):
            return GateOutcome(False, CANONICALIZATION_ERROR)

        # Try verification with each key (ACTIVE keys first, then ROTATING)
        verified_key = self._verify_with_rotation_support(message, signature, keys)
        if verified_key is None:
            self._emit_signature_failure(
                tenant=tenant,
                space=space,
                device=device,
                schema_uri=schema_uri,
                schema_version=schema_version,
                reason=SIGNATURE_INVALID,
            )
            return GateOutcome(False, SIGNATURE_INVALID)

        try:
            computed_idem_key = derive_idem_key(envelope, payload_hash=computed_hash)
        except ValueError:
            return GateOutcome(False, IDEM_KEY_INVALID)

        provided_idem_key_raw = self._extract_optional(envelope, "idem_key")
        try:
            provided_idem_key = self._normalize_hash(provided_idem_key_raw)
        except ValueError:
            return GateOutcome(False, IDEM_KEY_INVALID)

        if provided_idem_key is not None and provided_idem_key != computed_idem_key:
            return GateOutcome(False, IDEM_KEY_MISMATCH)

        envelope["idem_key"] = computed_idem_key
        self._emit_signature_success(
            tenant=tenant,
            space=space,
            device=device,
            schema_uri=schema_uri,
            schema_version=schema_version,
            key=verified_key,
        )
        return GateOutcome(
            True,
            None,
            idem_key=computed_idem_key,
            key_version=verified_key.key_version,
            key_state=verified_key.key_state,
        )

    @staticmethod
    def _binding_matches(
        record: ProvisionedDevice,
        tenant_id: str,
        space_id: str,
    ) -> bool:
        return record.tenant_id == tenant_id and record.space_id == space_id

    @staticmethod
    def _verify_with_rotation_support(
        message: bytes,
        signature_b64: str,
        keys: list[DeviceKey],
    ) -> DeviceKey | None:
        """Verify signature using multi-key rotation support.

        Tries verification with ACTIVE keys first, then ROTATING keys.
        Returns the key_version that successfully verified, or None if all failed.

        Args:
            message: Canonical envelope bytes to verify
            signature_b64: URL-safe base64 encoded signature
            keys: List of DeviceKey records to try (already filtered by state)

        Returns:
            key_version string if verification succeeded, None otherwise
        """
        # Separate keys by state (ACTIVE first for performance)
        active_keys = [k for k in keys if k.key_state == "ACTIVE"]
        rotating_keys = [k for k in keys if k.key_state == "ROTATING"]

        # Try verification with each key
        for key in active_keys + rotating_keys:
            try:
                verify_signature(message, signature_b64, key.verify_key)
                # Success - return the key version that verified
                return key
            except SignatureVerificationError:
                # This key failed, try next one
                continue

        # All keys failed verification
        return None

    def _emit_signature_success(
        self,
        *,
        tenant: str,
        space: str,
        device: str,
        schema_uri: str,
        schema_version: str,
        key: DeviceKey,
    ) -> None:
        if self._metrics is not None:
            try:
                self._metrics.emit(
                    "k0_signature_verified",
                    1.0,
                    key_version=key.key_version,
                    key_state=key.key_state,
                )
            except Exception:  # pragma: no cover - defensive guard  # noqa: BLE001
                logger.exception(
                    "Failed to emit signature verification metric",
                    extra={
                        "device_id": device,
                        "key_version": key.key_version,
                        "key_state": key.key_state,
                    },
                )

        if self._observability is not None:
            payload: dict[str, Any] = {
                "event": "signature_verification",
                "outcome": "success",
                "tenant_id": tenant,
                "space_id": space,
                "device_id": device,
                "schema_uri": schema_uri,
                "schema_version": schema_version,
                "key_version": key.key_version,
                "key_state": key.key_state,
            }
            try:
                self._observability.emit(payload)
            except Exception:  # pragma: no cover - defensive guard  # noqa: BLE001
                logger.exception(
                    "Failed to emit signature verification event",
                    extra={
                        "device_id": device,
                        "key_version": key.key_version,
                        "key_state": key.key_state,
                    },
                )

    def _emit_signature_failure(
        self,
        *,
        tenant: str,
        space: str,
        device: str,
        schema_uri: str,
        schema_version: str,
        reason: str,
    ) -> None:
        if self._metrics is not None:
            try:
                self._metrics.emit(
                    "k0_signature_verification_failed",
                    1.0,
                    device_id=device,
                    reason=reason,
                )
            except Exception:  # pragma: no cover - defensive guard  # noqa: BLE001
                logger.exception(
                    "Failed to emit signature failure metric",
                    extra={
                        "device_id": device,
                        "reason": reason,
                    },
                )

        if self._observability is not None:
            payload: dict[str, Any] = {
                "event": "signature_verification",
                "outcome": "failure",
                "reason": reason,
                "tenant_id": tenant,
                "space_id": space,
                "device_id": device,
                "schema_uri": schema_uri,
                "schema_version": schema_version,
            }
            try:
                self._observability.emit(payload)
            except Exception:  # pragma: no cover - defensive guard  # noqa: BLE001
                logger.exception(
                    "Failed to emit signature failure event",
                    extra={
                        "device_id": device,
                        "reason": reason,
                    },
                )

    def _emit_provisioning_failure(
        self,
        *,
        reason: str,
        tenant: str,
        space: str,
        device: str,
        binding: ProvisionedDevice | None,
    ) -> None:
        if self._metrics is not None:
            try:
                self._metrics.emit(
                    "k0_provisioning_denial",
                    1.0,
                    device_id=device,
                    reason=reason,
                )
            except Exception:  # pragma: no cover - defensive guard  # noqa: BLE001
                logger.exception(
                    "Failed to emit provisioning denial metric",
                    extra={
                        "device_id": device,
                        "reason": reason,
                    },
                )

        if self._observability is not None:
            payload: dict[str, Any] = {
                "event": "provisioning_check",
                "outcome": "failure",
                "reason": reason,
                "tenant_id": tenant,
                "space_id": space,
                "device_id": device,
            }
            if binding is not None:
                payload["binding"] = {
                    "tenant_id": binding.tenant_id,
                    "space_id": binding.space_id,
                    "mls_group_id": binding.mls_group_id,
                }
            try:
                self._observability.emit(payload)
            except Exception:  # pragma: no cover - defensive guard  # noqa: BLE001
                logger.exception(
                    "Failed to emit provisioning observability event",
                    extra={
                        "device_id": device,
                        "reason": reason,
                    },
                )

    def _emit_schema_failure(
        self,
        *,
        reason: str,
        schema_uri: str,
        schema_version: str,
        status: str | None,
        operator_id: str | None,
    ) -> None:
        if self._metrics is not None:
            try:
                self._metrics.emit(
                    "k0_schema_denial",
                    1.0,
                    reason=reason,
                    schema_uri=schema_uri,
                    schema_version=schema_version,
                )
            except Exception:  # pragma: no cover - defensive guard  # noqa: BLE001
                logger.exception(
                    "Failed to emit schema denial metric",
                    extra={
                        "schema_uri": schema_uri,
                        "schema_version": schema_version,
                        "reason": reason,
                    },
                )

        if self._observability is not None:
            payload: dict[str, Any] = {
                "event": "schema_validation",
                "outcome": "failure",
                "reason": reason,
                "schema_uri": schema_uri,
                "schema_version": schema_version,
            }
            if status is not None:
                payload["status"] = status
            if operator_id is not None:
                payload["operator_id"] = operator_id
            try:
                self._observability.emit(payload)
            except Exception:  # pragma: no cover - defensive guard  # noqa: BLE001
                logger.exception(
                    "Failed to emit schema observability event",
                    extra={
                        "schema_uri": schema_uri,
                        "schema_version": schema_version,
                        "reason": reason,
                    },
                )

    @staticmethod
    def _extract_identifier(
        envelope: dict[str, object],
        field: str,
    ) -> str | None:
        value = envelope.get(field)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _extract_optional(
        envelope: dict[str, object],
        field: str,
    ) -> str | None:
        value = envelope.get(field)
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None

    def _canonicalise_for_limits(self, envelope: dict[str, object]) -> bytes | None:
        try:
            return canonical_json(envelope).encode("utf-8")
        except (TypeError, ValueError):
            return None

    def _validate_schema(
        self,
        schema_uri: str,
        schema_version: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> GateOutcome | None:
        try:
            record = self._registry.get(
                schema_uri, schema_version, connection=connection
            )
        except KeyError:
            self._emit_schema_failure(
                reason=SCHEMA_NOT_ACTIVE,
                schema_uri=schema_uri,
                schema_version=schema_version,
                status=None,
                operator_id=None,
            )
            return GateOutcome(
                False,
                self._format_schema_reason(
                    SCHEMA_NOT_ACTIVE, schema_uri, schema_version
                ),
            )

        status = record.status.upper()
        if status == "ACTIVE":
            return None
        if status == "DEPRECATED":
            self._emit_schema_failure(
                reason=SCHEMA_SUNSET,
                schema_uri=schema_uri,
                schema_version=schema_version,
                status=status,
                operator_id=record.operator_id,
            )
            return GateOutcome(
                False,
                self._format_schema_reason(SCHEMA_SUNSET, schema_uri, schema_version),
            )
        if status == "BLOCKED":
            self._emit_schema_failure(
                reason=SCHEMA_BLOCKED,
                schema_uri=schema_uri,
                schema_version=schema_version,
                status=status,
                operator_id=record.operator_id,
            )
            return GateOutcome(
                False,
                self._format_schema_reason(SCHEMA_BLOCKED, schema_uri, schema_version),
            )
        self._emit_schema_failure(
            reason=SCHEMA_NOT_ACTIVE,
            schema_uri=schema_uri,
            schema_version=schema_version,
            status=status,
            operator_id=record.operator_id,
        )
        return GateOutcome(
            False,
            self._format_schema_reason(SCHEMA_NOT_ACTIVE, schema_uri, schema_version),
        )

    @staticmethod
    def _format_schema_reason(reason: str, uri: str, version: str) -> str:
        return f"{reason}:{uri}@{version}"

    @staticmethod
    def _normalize_body(body: Any) -> bytes | None:
        if body is None:
            return None
        if isinstance(body, memoryview):
            return body.tobytes()
        if isinstance(body, (bytes, bytearray)):
            return bytes(body)
        if isinstance(body, str):
            return body.encode("utf-8")
        raise TypeError("body must be bytes-like or string")

    @staticmethod
    def _normalize_hash(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            return None
        if len(normalized) != 64 or any(
            ch not in string.hexdigits for ch in normalized
        ):
            raise ValueError("Invalid hex digest")
        return normalized


__all__ = [
    "CANONICALIZATION_ERROR",
    "DEVICE_NOT_PROVISIONED",
    "GateOutcome",
    "LIMIT_EXCEEDED",
    "MinimalGate",
    "MISSING_BINDINGS",
    "IDEM_KEY_INVALID",
    "IDEM_KEY_MISMATCH",
    "NO_VALID_KEYS",
    "SPACE_MISMATCH",
    "PAYLOAD_HASH_MISMATCH",
    "PAYLOAD_HASH_MISSING",
    "SIGNATURE_INVALID",
    "SIGNATURE_MISSING",
    "SCHEMA_BLOCKED",
    "SCHEMA_NOT_ACTIVE",
    "SCHEMA_SUNSET",
    "VERIFY_KEY_MISSING",
]
