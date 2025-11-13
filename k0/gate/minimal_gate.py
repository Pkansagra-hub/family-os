"""Envelope validation and canonicalisation prior to WAL writes."""

from __future__ import annotations

import logging
import sqlite3
import string
from dataclasses import dataclass
from typing import Any, cast

from k0.idem import derive_hmac_idem_key, derive_idem_key
from k0.obs import MetricsExporter, ObservabilityEmitter
from k0.security import (
    SignatureVerificationError,
    canonical_envelope,
    canonical_json,
    compute_envelope_sha256,
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
BODY_REQUIRED = "BODY_REQUIRED"  # Gap 34
REVOKED_KEY = "REVOKED_KEY"  # Gap 35
ENVELOPE_REPLAY_DETECTED = "ENVELOPE_REPLAY_DETECTED"
ENVELOPE_SHA256_MISMATCH = "ENVELOPE_SHA256_MISMATCH"
CLOCK_SKEW_EXCESSIVE = "CLOCK_SKEW_EXCESSIVE"  # Gap 7


class MinimalGate:
    """Central gate enforcing envelope correctness contracts."""

    # Gap 7: Maximum acceptable clock skew (5 minutes = 300 seconds)
    MAX_CLOCK_SKEW_SECONDS = 300

    def __init__(
        self,
        *,
        registry: SchemaRegistry | None = None,
        provisioning: ProvisioningLedger | None = None,
        max_envelope_bytes: int = DEFAULT_MAX_ENVELOPE_BYTES,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
        max_clock_skew_seconds: int | None = None,  # Gap 7: Configurable clock skew
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
        self._max_clock_skew_seconds = (
            max_clock_skew_seconds
            if max_clock_skew_seconds is not None
            else self.MAX_CLOCK_SKEW_SECONDS
        )
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
            # Gap 47: Track gate rejections by reason
            if self._metrics is not None:
                tenant_id = self._extract_identifier(envelope, "tenant_id") or "unknown"
                self._metrics.emit(
                    "gate_rejections_total", reason=CANONICALIZATION_ERROR, tenant=tenant_id
                )
            return GateOutcome(False, CANONICALIZATION_ERROR)

        if len(canonical_bytes) > self._max_envelope_bytes:
            # Gap 47: Track gate rejections by reason
            if self._metrics is not None:
                tenant_id = self._extract_identifier(envelope, "tenant_id") or "unknown"
                self._metrics.emit("gate_rejections_total", reason=LIMIT_EXCEEDED, tenant=tenant_id)
            return GateOutcome(False, f"{LIMIT_EXCEEDED}:envelope")

        try:
            normalized_body = self._normalize_body(body)
        except TypeError:
            # Gap 47: Track gate rejections by reason
            if self._metrics is not None:
                tenant_id = self._extract_identifier(envelope, "tenant_id") or "unknown"
                self._metrics.emit(
                    "gate_rejections_total", reason=CANONICALIZATION_ERROR, tenant=tenant_id
                )
            return GateOutcome(False, CANONICALIZATION_ERROR)

        # Gap 34: Explicit null/empty body handling - bodies are required for K0
        if normalized_body is None or len(normalized_body) == 0:
            if self._metrics is not None:
                tenant_id = self._extract_identifier(envelope, "tenant_id") or "unknown"
                self._metrics.emit("gate_rejections_total", reason=BODY_REQUIRED, tenant=tenant_id)
            return GateOutcome(False, BODY_REQUIRED)

        if normalized_body is not None and len(normalized_body) > self._max_body_bytes:
            # Gap 47: Track gate rejections by reason
            if self._metrics is not None:
                tenant_id = self._extract_identifier(envelope, "tenant_id") or "unknown"
                self._metrics.emit("gate_rejections_total", reason=LIMIT_EXCEEDED, tenant=tenant_id)
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
            # Gap 47: Track gate rejections by reason
            if self._metrics is not None:
                tenant_id = self._extract_identifier(envelope, "tenant_id") or "unknown"
                self._metrics.emit(
                    "gate_rejections_total", reason=MISSING_BINDINGS, tenant=tenant_id
                )
            return GateOutcome(False, f"{MISSING_BINDINGS}:{missing_fields}")

        tenant = cast(str, tenant_id)
        space = cast(str, space_id)
        device = cast(str, device_id)

        assert schema_uri is not None  # for mypy; guarded by missing check
        assert schema_version is not None

        # Gap 7: Validate timestamp is within acceptable clock skew window
        ts_raw = self._extract_optional(envelope, "ts")
        if ts_raw is not None:
            try:
                # Parse ISO8601 timestamp
                if isinstance(ts_raw, str):
                    # Simple ISO8601 parsing (assumes format like "2025-01-15T10:30:00Z")
                    import datetime

                    # Strip 'Z' and parse
                    ts_str = ts_raw.rstrip("Zz")
                    envelope_time = datetime.datetime.fromisoformat(ts_str)
                    if envelope_time.tzinfo is None:
                        envelope_time = envelope_time.replace(tzinfo=datetime.timezone.utc)

                    server_time = datetime.datetime.now(datetime.timezone.utc)
                    time_diff_seconds = abs((envelope_time - server_time).total_seconds())

                    if time_diff_seconds > self._max_clock_skew_seconds:
                        if self._metrics is not None:
                            self._metrics.emit(
                                "gate_rejections_total", reason=CLOCK_SKEW_EXCESSIVE, tenant=tenant
                            )
                        return GateOutcome(
                            False, f"{CLOCK_SKEW_EXCESSIVE}:skew={int(time_diff_seconds)}s"
                        )
            except (ValueError, AttributeError):
                # Invalid timestamp format - continue without clock skew check
                pass

        record = self._provisioning.lookup(tenant, space, device, connection=connection)
        if record is None:
            # Gap 47: Track gate rejections by reason
            if self._metrics is not None:
                self._metrics.emit(
                    "gate_rejections_total", reason=DEVICE_NOT_PROVISIONED, tenant=tenant
                )
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

        schema_check = self._validate_schema(schema_uri, schema_version, connection=connection)
        if schema_check is not None:
            return schema_check

        try:
            expected_hash = self._normalize_hash(self._extract_optional(envelope, "payload_sha256"))
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

        # Gap 35: Explicit defensive check - reject if any key is REVOKED
        # (get_keys already filters by state, but this provides clear observability)
        for key in keys:
            if key.key_state == "REVOKED":
                if self._metrics is not None:
                    self._metrics.emit("gate_rejections_total", reason=REVOKED_KEY, tenant=tenant)
                return GateOutcome(False, REVOKED_KEY)

        try:
            message = canonical_envelope(envelope)
        except (TypeError, ValueError):
            return GateOutcome(False, CANONICALIZATION_ERROR)

        # V1 STEP 1: Compute envelope_sha256 from full canonical envelope
        try:
            envelope_sha256 = compute_envelope_sha256(envelope)
        except Exception as exc:
            logger.exception("Failed to compute envelope_sha256", exc_info=exc)
            return GateOutcome(False, CANONICALIZATION_ERROR)

        # Gap 4: Validate client-provided envelope_sha256 matches computed value
        client_provided_sha256 = self._extract_optional(envelope, "envelope_sha256")
        if client_provided_sha256 is not None:
            if not isinstance(client_provided_sha256, str):
                if self._metrics is not None:
                    self._metrics.emit(
                        "gate_rejections_total", reason=ENVELOPE_SHA256_MISMATCH, tenant=tenant
                    )
                return GateOutcome(False, f"{ENVELOPE_SHA256_MISMATCH}:invalid_type")

            if client_provided_sha256.strip() != envelope_sha256:
                if self._metrics is not None:
                    self._metrics.emit(
                        "gate_rejections_total", reason=ENVELOPE_SHA256_MISMATCH, tenant=tenant
                    )
                return GateOutcome(False, ENVELOPE_SHA256_MISMATCH)

        # V1 STEP 2: Check if envelope_sha256 exists in WAL (replay detection)
        if self._check_envelope_replay(envelope_sha256, connection=connection):
            self._emit_replay_attempt(
                tenant=tenant,
                space=space,
                device=device,
                envelope_sha256=envelope_sha256,
            )
            return GateOutcome(False, ENVELOPE_REPLAY_DETECTED)

        # Try verification with each key (ACTIVE keys first, then ROTATING)
        verified_key = self._verify_with_rotation_support(message, signature, keys)
        if verified_key is None:
            # Gap 47: Track gate rejections by reason
            if self._metrics is not None:
                self._metrics.emit("gate_rejections_total", reason=SIGNATURE_INVALID, tenant=tenant)
            self._emit_signature_failure(
                tenant=tenant,
                space=space,
                device=device,
                schema_uri=schema_uri,
                schema_version=schema_version,
                reason=SIGNATURE_INVALID,
            )
            return GateOutcome(False, SIGNATURE_INVALID)

        # ADR-0002: HMAC-based idempotency with device secrets (Gap 2)
        # Dual-mode support: Use HMAC if device has secret, fallback to BLAKE3
        try:
            # Try to get device HMAC secret for V1 idempotency
            device_secret = self._get_device_secret(device, connection=connection)

            if device_secret is not None:
                # V1 HMAC-based idempotency (60-second time bucket)
                # ADR Reference: Issue #009 - HMAC-SHA256 with device secrets
                ts = self._extract_optional(envelope, "ts")
                computed_idem_key = derive_hmac_idem_key(
                    envelope_sha256=envelope_sha256,
                    device_id=device,
                    device_secret=device_secret,
                    ts=ts,
                )
            else:
                # V0 fallback: BLAKE3-based idempotency (for legacy devices)
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

        # V1 STEP 3: Store envelope_sha256 and time metadata in envelope
        envelope["idem_key"] = computed_idem_key
        envelope["envelope_sha256"] = envelope_sha256

        # Gap 4: Validate location fields exist for AMBER/RED bands before masking
        band = self._extract_optional(envelope, "band")
        if band in ("AMBER", "RED"):
            location = self._extract_optional(envelope, "location")
            if location is None or (isinstance(location, dict) and not location):
                if self._metrics is not None:
                    self._metrics.emit(
                        "gate_rejections_total", reason="LOCATION_MISSING", tenant=tenant
                    )
                return GateOutcome(False, f"LOCATION_MISSING:band={band}")

        # Gap 4: Validate policy_stamp present if required by policy context
        # Note: This is a lightweight check - full policy evaluation happens in ports
        # We only validate structure here, not policy compliance
        policy_stamp = self._extract_optional(envelope, "policy_stamp")
        if policy_stamp is not None:
            if not isinstance(policy_stamp, dict):
                if self._metrics is not None:
                    self._metrics.emit(
                        "gate_rejections_total", reason="POLICY_STAMP_INVALID", tenant=tenant
                    )
                return GateOutcome(False, "POLICY_STAMP_INVALID:not_dict")

            # Validate required fields in policy_stamp
            required_fields = ["band", "obligations", "decision"]
            missing_fields = [f for f in required_fields if f not in policy_stamp]
            if missing_fields:
                if self._metrics is not None:
                    self._metrics.emit(
                        "gate_rejections_total", reason="POLICY_STAMP_INVALID", tenant=tenant
                    )
                return GateOutcome(
                    False, f"POLICY_STAMP_INVALID:missing_{','.join(missing_fields)}"
                )

        self._emit_signature_success(
            tenant=tenant,
            space=space,
            device=device,
            schema_uri=schema_uri,
            schema_version=schema_version,
            key=verified_key,
        )

        # Gap 47: Track gate acceptances by tenant
        if self._metrics is not None:
            self._metrics.emit("gate_accepted_total", tenant=tenant)

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
            record = self._registry.get(schema_uri, schema_version, connection=connection)
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
                self._format_schema_reason(SCHEMA_NOT_ACTIVE, schema_uri, schema_version),
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
        if len(normalized) != 64 or any(ch not in string.hexdigits for ch in normalized):
            raise ValueError("Invalid hex digest")
        return normalized

    def _check_envelope_replay(
        self,
        envelope_sha256: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> bool:
        """Check if envelope_sha256 already exists in WAL (replay detection).

        V1 Replay Detection: Query st_wal for exact duplicate envelope_sha256.
        Envelope_sha256 is SHA-256 hash of entire canonical envelope (headers + body).
        If found → return True (exact duplicate/replay)
        If not found → return False (new envelope)

        Args:
            envelope_sha256: SHA-256 hex digest of canonical envelope
            connection: Optional SQLite connection (if None, detection skipped)

        Returns:
            True if envelope_sha256 exists in WAL (replay detected)
            False if not found (new envelope) or connection unavailable
        """
        # If no connection provided, skip replay detection
        if connection is None:
            return False

        try:
            cursor = connection.execute(
                "SELECT 1 FROM st_wal WHERE envelope_sha256 = ? LIMIT 1",
                (envelope_sha256,),
            )
            row = cursor.fetchone()
            return row is not None
        except sqlite3.OperationalError as exc:
            # Table/column might not exist (pre-migration state)
            # Safely degrade: assume no replay (let DB UNIQUE constraint catch it)
            logger.debug(
                "Envelope replay check skipped (schema not updated)",
                extra={"error": str(exc)},
            )
            return False
        except Exception:
            logger.exception(
                "Unexpected error during replay detection",
                extra={"envelope_sha256": envelope_sha256},
            )
            # Fail-safe: return False to avoid blocking legitimate requests
            return False

    def _get_device_secret(
        self,
        device_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> bytes | None:
        """Retrieve HMAC secret for device from st_devices (V1 idempotency).

        HMAC secret is used to compute idempotency keys via:
            HMAC-SHA256(device_secret, envelope_sha256|device_id|time_bucket)

        Each device has a unique, time-limited HMAC secret. Secrets are rotated
        on device re-provisioning.

        Args:
            device_id: Device identifier (e.g., "dad-phone")
            connection: Optional SQLite connection (if None, returns None)

        Returns:
            32-byte HMAC secret if found and device is provisioned
            None if connection unavailable, device not found, or secret not set
        """
        # If no connection provided, can't look up device secret
        if connection is None:
            return None

        try:
            cursor = connection.execute(
                "SELECT hmac_secret FROM st_devices WHERE device_id = ? LIMIT 1",
                (device_id,),
            )
            row = cursor.fetchone()
            if row is None:
                # Device not found
                logger.debug(f"Device not found for secret lookup: {device_id}")
                return None

            hmac_secret = row[0]
            if hmac_secret is None:
                # Device found but secret not set (pre-provisioning or legacy device)
                logger.debug(f"Device found but hmac_secret not set: {device_id}")
                return None

            return hmac_secret
        except sqlite3.OperationalError as exc:
            # Table/column might not exist (pre-migration state)
            # Safely degrade: return None (HMAC-based idem unavailable)
            logger.debug(
                "Device secret lookup skipped (schema not updated)",
                extra={"error": str(exc)},
            )
            return None
        except Exception:
            logger.exception(
                "Unexpected error during device secret lookup",
                extra={"device_id": device_id},
            )
            # Fail-safe: return None to avoid blocking requests
            return None

    def _emit_replay_attempt(
        self,
        *,
        tenant: str,
        space: str,
        device: str,
        envelope_sha256: str,
    ) -> None:
        """Emit observability event for detected replay attempt."""
        if self._metrics is not None:
            try:
                self._metrics.emit(
                    "k0_envelope_replay_detected",
                    1.0,
                    envelope_sha256=envelope_sha256,
                )
            except Exception:  # pragma: no cover
                logger.exception(
                    "Failed to emit replay detection metric",
                    extra={
                        "device_id": device,
                        "envelope_sha256": envelope_sha256,
                    },
                )

        if self._observability is not None:
            payload: dict[str, Any] = {
                "event": "envelope_replay_detected",
                "tenant_id": tenant,
                "space_id": space,
                "device_id": device,
                "envelope_sha256": envelope_sha256,
            }
            try:
                self._observability.emit(payload)
            except Exception:  # pragma: no cover
                logger.exception(
                    "Failed to emit replay detection event",
                    extra={"envelope_sha256": envelope_sha256},
                )


__all__ = [
    "BODY_REQUIRED",
    "CANONICALIZATION_ERROR",
    "CLOCK_SKEW_EXCESSIVE",
    "DEVICE_NOT_PROVISIONED",
    "ENVELOPE_REPLAY_DETECTED",
    "ENVELOPE_SHA256_MISMATCH",
    "GateOutcome",
    "LIMIT_EXCEEDED",
    "MinimalGate",
    "MISSING_BINDINGS",
    "IDEM_KEY_INVALID",
    "IDEM_KEY_MISMATCH",
    "NO_VALID_KEYS",
    "REVOKED_KEY",
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
