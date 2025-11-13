"""HTTP handlers for the command port (`/k0/command.submit`)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable, Literal, Mapping, Sequence, TypeVar, cast

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from k0.gate import MinimalGate
from k0.idem import IdempotencyLedger, LedgerEntry
from k0.kernel.admission import record_admission_decision
from k0.kernel.dependencies import qos_context_dependency
from k0.obs import MetricsExporter, ObservabilityEmitter, TracerFactory, update_log_context
from k0.outbox import compute_fingerprint
from k0.policy import PolicyConfigurationError, evaluate_envelope
from k0.policy.redaction import (
    RedactionDirective,
    RedactionError,
    apply_redactions,
    directives_from_obligations,
)
from k0.ports.errors import (
    KERNEL_COMPONENT_GATE,
    KERNEL_COMPONENT_POLICY,
    KERNEL_COMPONENT_QOS,
    ErrorEnvelope,
)
from k0.qos import (
    QoSBudgetError,
    QoSContext,
    SchedulerCapacityError,
    SchedulerToken,
    apply_qos_obligations,
    coerce_positive_int,
)
from k0.receipts import ReceiptDocument, ReceiptIssuer
from k0.security import canonical_json, hash_payload
from k0.storage.obligations import ObligationRecord, ObligationStore
from k0.storage.outbox import OutboxEntry
from k0.storage.provisioning import ProvisionedDevice, ProvisioningLedger
from k0.storage.receipts import Receipt
from k0.storage.wal import WalEntry
from k0.uow import UnitOfWork
from k0.uow.connection_pool import connection_scope

router = APIRouter(prefix="/k0", tags=["command"])
logger = logging.getLogger(__name__)

DEFAULT_OUTBOX_DRIVER = "st_epi"
DEFAULT_OUTBOX_OPERATION = "UPSERT"
OUTBOX_INLINE_BODY_LIMIT_BYTES = 4096

UnitOfWorkFactory = Callable[[], UnitOfWork]
T = TypeVar("T")


class Envelope(BaseModel):
    """Minimal representation of the command envelope schema (V1 with full envelope signature)."""

    model_config = ConfigDict(extra="allow")

    cognitive_trace_id: uuid.UUID = Field(..., description="Trace correlation identifier.")
    tenant_id: str
    space_id: str
    topic: str
    schema_uri: str
    schema_version: str
    actor: str
    device_id: str
    band: Literal["GREEN", "AMBER", "RED"]
    policy_version: str
    ts: str
    sig: str

    # V1 NEW: Algorithm agility fields
    sig_alg: str = Field(..., description="Signature algorithm (ECDSA_P256_SHA256, etc.)")
    sig_kid: str = Field(..., description="Key ID (did:device:device-name#timestamp)")

    # V1 NEW: Envelope integrity field
    envelope_sha256: str = Field(..., description="SHA-256 hash of full canonical envelope")

    # Optional fields
    idem_key: str | None = None
    payload_sha256: str | None = None
    payload_bytes: int | None = None
    policy: dict[str, Any] | None = None
    policy_ctx: dict[str, Any] | None = None
    pep: dict[str, Any] | None = None

    # V1 NEW: Time tracking fields (added by MinimalGate)
    ingested_at: str | None = None
    clock_skew_ms: int | None = None

    # V1.3 NEW: Policy stamp (attached by PolicyEvaluator)
    policy_stamp: dict[str, Any] | None = Field(
        default=None,
        description="Policy decision stamp with band, obligations, visible_to, decision",
    )

    # V1.3 NEW: Location privacy fields (geohash for AMBER/RED)
    location_geohash: str | None = Field(
        default=None, description="Geohash of location (GREEN=full precision, AMBER=5km, RED=25km)"
    )
    location_precision_m: int | None = Field(
        default=None, description="Precision in meters (GREEN=1, AMBER=5000, RED=25000)"
    )

    # V1.4 NEW: Async worker status tracking
    embedding_status: str | None = Field(
        default=None, description="Embedding worker status (PENDING, IN_PROGRESS, COMPLETE, FAILED)"
    )
    embedding_id: str | None = Field(default=None, description="ID of computed embedding vector")
    fts_status: str | None = Field(
        default=None,
        description="FTS indexing worker status (PENDING, IN_PROGRESS, COMPLETE, FAILED)",
    )
    fts_entry_id: str | None = Field(default=None, description="ID of FTS index entry")


class CommandResponse(BaseModel):
    """Response emitted after a successful command commit."""

    receipt_id: uuid.UUID = Field(..., description="Unique receipt identifier.")
    commit_ts: str = Field(..., description="ISO8601 timestamp of commit.")
    offsets: dict[str, int] = Field(..., description="Committed offsets keyed by topic.")
    idem_key: str = Field(..., description="Canonical idempotency key.")
    obligations: list[str] = Field(
        default_factory=list,
        description="Policy obligations applied during admission.",
    )
    policy_manifest_fingerprint: str | None = Field(
        default=None,
        description="Fingerprint of the policy manifest used for the decision.",
    )
    obligation_details: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Obligation detail payloads captured for auditing.",
    )


@router.post(
    "/command.submit",
    response_model=CommandResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Minimal Gate rejection",
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": "REJECTED_KERNEL_GATE",
                            "component": "kernel.gate",
                            "reason": "PAYLOAD_HASH_MISMATCH",
                            "trace_id": "0e1a2b3c-4d5e-6f70-8192-a3b4c5d6e7f8",
                        }
                    }
                }
            },
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Policy enforcement denied the command",
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": "PEP_DENY",
                            "component": "kernel.policy",
                            "reason": "ROLE_FORBIDDEN",
                            "trace_id": "0e1a2b3c-4d5e-6f70-8192-a3b4c5d6e7f8",
                        }
                    }
                }
            },
        },
        status.HTTP_409_CONFLICT: {
            "description": "Existing commit detected for the idem key",
            "content": {
                "application/json": {
                    "example": {
                        "receipt_id": "11111111-2222-3333-4444-555555555555",
                        "commit_ts": "2025-09-28T12:00:00Z",
                        "idem_key": "4f2a6b7c...",
                    }
                }
            },
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "QoS budgets or scheduler capacity exhausted",
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": "QOS_BUDGET_EXHAUSTED",
                            "component": "kernel.qos",
                            "reason": "FANOUT_BUDGET_EXHAUSTED",
                            "trace_id": "0e1a2b3c-4d5e-6f70-8192-a3b4c5d6e7f8",
                            "budgets": {"fanout": 0, "top_k": 8},
                            "details": {"cap": "fanout"},
                            "hint": "Reduce fanout request",
                        }
                    }
                }
            },
        },
    },
)
async def submit_command(
    request: Request,
    qos: QoSContext = Depends(qos_context_dependency),
) -> CommandResponse | JSONResponse:
    """Process a command submission through the Minimal Gate and UnitOfWork."""

    scheduler_token: SchedulerToken | None = None
    initial_fanout_budget = qos.fanout_budget
    initial_top_k_budget = qos.top_k_budget

    try:
        payload = await request.json()
        if not isinstance(payload, Mapping):
            return _error_response(
                request,
                status.HTTP_400_BAD_REQUEST,
                "REJECTED_KERNEL_GATE",
                component=KERNEL_COMPONENT_GATE,
                reason="INVALID_ENVELOPE",
                hint="Envelope payload must be a JSON object",
            )

        payload_mapping = cast(Mapping[str, Any], payload)
        try:
            envelope_data, body_bytes, body_snapshot = _extract_body(payload_mapping)
        except (TypeError, ValueError):
            return _error_response(
                request,
                status.HTTP_400_BAD_REQUEST,
                "REJECTED_KERNEL_GATE",
                component=KERNEL_COMPONENT_GATE,
                reason="CANONICALIZATION_ERROR",
                hint="Envelope body could not be canonicalised",
            )

        try:
            envelope_model = Envelope.model_validate(envelope_data)
        except ValidationError:
            return _error_response(
                request,
                status.HTTP_400_BAD_REQUEST,
                "REJECTED_KERNEL_GATE",
                component=KERNEL_COMPONENT_GATE,
                reason="ENVELOPE_VALIDATION_FAILED",
            )

        envelope_dict = {
            key: value for key, value in envelope_model.model_dump().items() if value is not None
        }
        if envelope_model.model_extra:
            for key, value in envelope_model.model_extra.items():
                if value is None:
                    continue
                envelope_dict[key] = value
        envelope_dict["cognitive_trace_id"] = str(envelope_model.cognitive_trace_id)

        request.state.cognitive_trace_id = str(envelope_model.cognitive_trace_id)
        update_log_context(
            cognitive_trace_id=str(envelope_model.cognitive_trace_id),
            tenant_id=envelope_model.tenant_id,
            space_id=envelope_model.space_id,
            device_id=envelope_model.device_id,
            topic=envelope_model.topic,
            schema_uri=envelope_model.schema_uri,
            actor=envelope_model.actor,
        )

        # Re-add body field for gate processing (gate expects body to be present for validation)
        if body_snapshot is not None:
            envelope_dict["body"] = body_snapshot

        minimal_gate = _get_state_component(request, "minimal_gate", MinimalGate)
        provisioning = _get_state_component(request, "provisioning_ledger", ProvisioningLedger)
        idem_ledger = _get_state_component(request, "idempotency_ledger", IdempotencyLedger)
        receipt_issuer = _get_state_component(request, "receipt_issuer", ReceiptIssuer)
        unit_of_work_factory = _get_unit_of_work_factory(request)

        with connection_scope() as gate_connection:
            outcome = minimal_gate.validate(
                dict(envelope_dict),
                body=body_bytes,
                connection=gate_connection,
            )
            if not outcome.accepted:
                return _error_response(
                    request,
                    status.HTTP_400_BAD_REQUEST,
                    "REJECTED_KERNEL_GATE",
                    component=KERNEL_COMPONENT_GATE,
                    reason=outcome.reason or "MINIMAL_GATE_REJECTION",
                    hint=(None if outcome.reason else "Envelope rejected by Minimal Gate"),
                )

            idem_key = outcome.idem_key
            if idem_key is None:
                return _error_response(
                    request,
                    status.HTTP_400_BAD_REQUEST,
                    "REJECTED_KERNEL_GATE",
                    component=KERNEL_COMPONENT_GATE,
                    reason="IDEMPOTENCY_KEY_MISSING",
                    hint="Minimal Gate did not produce an idempotency key",
                )

            # ADR-K002: Early idempotency check for fast duplicate rejection
            # This is an optimization to avoid expensive policy evaluation for known duplicates.
            # The authoritative check happens inside UoW transaction (line 619+) to prevent TOCTOU race.
            # Gap 41: Track TOCTOU metrics - record check timestamp and increment concurrent checks
            early_check_start = perf_counter()
            metrics_exporter = getattr(request.app.state, "metrics_exporter", None)
            concurrent_gauge = None
            if metrics_exporter is not None:
                # Increment concurrent checks gauge (will be decremented after transaction)
                concurrent_gauge = metrics_exporter.gauge(
                    "idem_concurrent_checks_active",
                    "Number of active concurrent idempotency checks",
                )
                concurrent_gauge.inc()

            duplicate = idem_ledger.lookup(idem_key, connection=gate_connection)
            if duplicate is not None:
                # Decrement concurrent checks on early exit
                if concurrent_gauge is not None:
                    concurrent_gauge.dec()
                _emit_duplicate_telemetry(request, envelope_dict, duplicate)
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content={
                        "receipt_id": duplicate.receipt_id,
                        "commit_ts": duplicate.first_seen_ts,
                        "idem_key": duplicate.idem_key,
                    },
                )

            device_record = provisioning.lookup(
                envelope_dict["tenant_id"],
                envelope_dict["space_id"],
                envelope_dict["device_id"],
                connection=gate_connection,
            )

        if not isinstance(device_record, ProvisionedDevice):
            return _error_response(
                request,
                status.HTTP_400_BAD_REQUEST,
                "REJECTED_KERNEL_GATE",
                component=KERNEL_COMPONENT_GATE,
                reason="DEVICE_NOT_PROVISIONED",
            )

        envelope_dict["idem_key"] = idem_key
        if body_bytes is not None:
            envelope_dict["payload_bytes"] = len(body_bytes)

        metrics_exporter = getattr(request.app.state, "metrics_exporter", None)
        sanitized_body: Mapping[str, Any] | None = None
        obligation_directives: Sequence[RedactionDirective] = ()
        eval_start = perf_counter()
        try:
            decision = evaluate_envelope(envelope_dict)
        except PolicyConfigurationError as exc:  # manifest missing or invalid
            return _error_response(
                request,
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "POLICY_UNAVAILABLE",
                component=KERNEL_COMPONENT_POLICY,
                reason=str(exc),
            )
        except RedactionError as exc:
            return _error_response(
                request,
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "POLICY_UNAVAILABLE",
                component=KERNEL_COMPONENT_POLICY,
                reason=str(exc),
            )
        evaluation_duration_ms = (perf_counter() - eval_start) * 1000.0

        # V1: Create and attach policy_stamp to envelope for audit trail
        from k0.policy.pep_syscall import create_policy_stamp, get_manifest_fingerprint

        policy_stamp = create_policy_stamp(
            decision,
            band=str(envelope_dict.get("band", "GREEN")),
            visible_to=None,  # Will be populated by Memory Steward based on space policy
        )
        envelope_dict["policy_stamp"] = policy_stamp

        # Gap 42: Track policy stamp attachment in command path
        if metrics_exporter is not None:
            metrics_exporter.emit(
                "policy_stamp_attached_total",
                tenant=str(envelope_dict.get("tenant_id", "unknown")),
                band=str(envelope_dict.get("band", "GREEN")),
            )

        # Check manifest fingerprint if provided in envelope
        envelope_fingerprint = envelope_dict.get("manifest_fingerprint")
        if envelope_fingerprint is not None:
            actual_fingerprint = get_manifest_fingerprint()
            if actual_fingerprint != envelope_fingerprint:
                return _error_response(
                    request,
                    status.HTTP_412_PRECONDITION_FAILED,
                    "POLICY_VERSION_MISMATCH",
                    component=KERNEL_COMPONENT_POLICY,
                    reason="Policy manifest fingerprint mismatch",
                )
        _record_pem_metrics(
            metrics_exporter,
            decision,
            evaluation_duration_ms,
            band=str(envelope_dict.get("band", "UNKNOWN")),
            schema_uri=envelope_dict.get("schema_uri", "unknown"),
            lane="command",
        )
        if not decision.admit:
            # V1: Include policy_stamp in denied response for audit
            record_admission_decision(
                request,
                decision=decision,
                envelope=_audit_envelope(envelope_dict, body_snapshot),
                receipt=None,
                port="command",
                sanitized_body=sanitized_body,
                original_body=body_snapshot,
                manifest_fingerprint=envelope_dict.get("manifest_fingerprint"),
            )
            # Return error response with policy_stamp for audit trail
            error_content = {
                "error": {
                    "code": "PEP_DENY",
                    "component": KERNEL_COMPONENT_POLICY,
                    "reason": decision.deny_reason or "POLICY_DENIED",
                    "trace_id": str(envelope_dict.get("cognitive_trace_id", "")),
                    "policy_stamp": policy_stamp,  # V1: Include policy context in denial
                }
            }
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content=error_content,
            )

        apply_qos_obligations(qos, decision.obligations)

        if body_snapshot is not None:
            try:
                obligation_directives = tuple(directives_from_obligations(decision.obligations))
                if obligation_directives:
                    sanitized_body = apply_redactions(body_snapshot, obligation_directives)
                else:
                    sanitized_body = body_snapshot
            except RedactionError as exc:
                return _error_response(
                    request,
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "POLICY_UNAVAILABLE",
                    component=KERNEL_COMPONENT_POLICY,
                    reason=str(exc),
                )

            # V1.3: Apply location masking based on privacy band (GDPR/CCPA compliance)
            from k0.policy.redaction import mask_location_for_band

            try:
                band = str(envelope_dict.get("band", "GREEN"))
                # Convert sanitized_body to dict for location masking
                body_dict = dict(sanitized_body) if isinstance(sanitized_body, Mapping) else {}
                sanitized_body = mask_location_for_band(body_dict, band)
            except RedactionError as exc:
                return _error_response(
                    request,
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "LOCATION_MASKING_ERROR",
                    component=KERNEL_COMPONENT_POLICY,
                    reason=str(exc),
                )

        elif body_snapshot is None:
            sanitized_body = None

        fanout_request = _resolve_cap_request(envelope_dict, "fanout") or 1
        fanout_request = max(1, fanout_request)
        top_k_request = _resolve_cap_request(envelope_dict, "top_k")
        latency_budget_ms = _resolve_cap_request(envelope_dict, "latency_ms")

        initial_fanout_budget = qos.fanout_budget
        initial_top_k_budget = qos.top_k_budget

        try:
            qos.consume_fanout(fanout_request)
        except QoSBudgetError:
            return _qos_budget_response(
                request,
                qos,
                envelope=envelope_dict,
                cap="fanout",
                reason="FANOUT_BUDGET_EXHAUSTED",
            )

        if top_k_request is not None and top_k_request > 0:
            try:
                qos.consume_top_k(top_k_request)
            except QoSBudgetError:
                qos.fanout_budget = initial_fanout_budget
                return _qos_budget_response(
                    request,
                    qos,
                    envelope=envelope_dict,
                    cap="top_k",
                    reason="TOP_K_BUDGET_EXHAUSTED",
                )

        scheduler_cost = _compute_scheduler_cost(
            fanout=fanout_request,
            payload_bytes=envelope_dict.get("payload_bytes"),
            top_k=top_k_request,
            latency_ms=latency_budget_ms,
        )

        try:
            scheduler_token = qos.acquire(
                band=str(envelope_dict.get("band", "GREEN")),
                port="command",
                cost=scheduler_cost,
            )
        except SchedulerCapacityError as exc:
            qos.fanout_budget = initial_fanout_budget
            qos.top_k_budget = initial_top_k_budget
            return _qos_budget_response(
                request,
                qos,
                envelope=envelope_dict,
                cap="scheduler",
                reason="SCHEDULER_CAPACITY_EXHAUSTED",
                hint=str(exc),
            )

        commit_ts = _utc_now()
        receipt_id = uuid.uuid4()

        if sanitized_body is not None:
            wal_body_bytes = canonical_json(sanitized_body).encode("utf-8")
        else:
            wal_body_bytes = body_bytes

        payload_digest = envelope_dict.get("payload_sha256")
        if payload_digest is None and wal_body_bytes is not None:
            payload_digest = hash_payload(wal_body_bytes)
        if payload_digest is None:
            payload_digest = hash_payload(b"") or "0" * 64

        body_was_redacted = (
            bool(obligation_directives)
            and sanitized_body is not None
            and body_snapshot is not None
            and sanitized_body is not body_snapshot
        )

        redacted_body_json = (
            canonical_json(sanitized_body)
            if body_was_redacted and sanitized_body is not None
            else None
        )

        # V1.3: Serialize policy_stamp for WAL persistence
        import json

        policy_stamp_json = (
            json.dumps(envelope_dict.get("policy_stamp"))
            if envelope_dict.get("policy_stamp")
            else None
        )

        wal_entry = WalEntry(
            tenant_id=envelope_dict["tenant_id"],
            space_id=envelope_dict["space_id"],
            topic=envelope_dict["topic"],
            envelope_json=canonical_json(_strip_body(envelope_dict)),
            schema_uri=envelope_dict["schema_uri"],
            schema_version=envelope_dict["schema_version"],
            device_id=envelope_dict["device_id"],
            commit_ts=commit_ts,
            body=wal_body_bytes,
            payload_sha256=payload_digest,
            idem_key=idem_key,
            redacted_body_json=redacted_body_json,
            policy_stamp_json=policy_stamp_json,  # V1.3: Policy audit trail
        )

        # Gap 42: Track policy stamp presence in WAL
        if metrics_exporter is not None and policy_stamp_json is not None:
            metrics_exporter.emit(
                "wal_policy_stamp_present_total",
                tenant=str(envelope_dict.get("tenant_id", "unknown")),
                band=str(envelope_dict.get("band", "GREEN")),
            )

        wal_pos: int | None = None
        receipt_doc: ReceiptDocument | None = None
        body_bytes_length = len(wal_body_bytes) if wal_body_bytes is not None else 0
        inline_body_allowed = (
            body_snapshot is not None
            and wal_body_bytes is not None
            and body_bytes_length <= OUTBOX_INLINE_BODY_LIMIT_BYTES
        )

        obligation_records: list[ObligationRecord] = []
        if obligation_directives:
            for directive in obligation_directives:
                details_payload: dict[str, Any] = {}
                if isinstance(directive.fields, str):
                    details_payload["fields"] = directive.fields
                else:
                    details_payload["fields"] = list(directive.fields)
                if directive.target is not None:
                    if isinstance(directive.target, str):
                        details_payload["target"] = directive.target
                    else:
                        details_payload["target"] = list(directive.target)
                details_payload["mask"] = directive.mask

                obligation_records.append(
                    ObligationRecord(
                        wal_pos=0,  # placeholder updated post-append
                        obligation=directive.obligation,
                        details_json=canonical_json(details_payload),
                        commit_ts=commit_ts,
                        tenant_id=envelope_dict["tenant_id"],
                        space_id=envelope_dict["space_id"],
                    )
                )

        obligation_store = _get_state_component_optional(
            request, "obligation_store", ObligationStore
        )

        with unit_of_work_factory() as uow:
            # ADR-K002: Check idempotency INSIDE transaction to prevent TOCTOU race
            # This ensures atomic CHECK+USE within single SQLite BEGIN IMMEDIATE...COMMIT
            # Gap 41: Track check-commit window and detect races
            duplicate = idem_ledger.lookup(idem_key, connection=uow.connection)

            # Calculate time window between early check and commit
            check_commit_window = perf_counter() - early_check_start
            if metrics_exporter is not None:
                metrics_exporter.observe(
                    "idem_check_commit_window_seconds",
                    check_commit_window,
                    labels={},
                )

            if duplicate is not None:
                # Gap 41: Detect TOCTOU race - if entry was created recently (< 1s), likely a race
                try:
                    duplicate_ts = datetime.fromisoformat(
                        duplicate.first_seen_ts.replace("Z", "+00:00")
                    )
                    now_ts = datetime.now(timezone.utc)
                    age_seconds = (now_ts - duplicate_ts).total_seconds()

                    if age_seconds < 1.0 and metrics_exporter is not None:
                        # Late arrival detected - increment race counter
                        metrics_exporter.emit(
                            "idem_toctou_race_detected_total",
                            tenant=str(envelope_dict.get("tenant_id", "unknown")),
                            band=str(envelope_dict.get("band", "GREEN")),
                        )
                        logger.warning(
                            "TOCTOU race detected",
                            extra={
                                "idem_key": idem_key,
                                "duplicate_age_seconds": age_seconds,
                                "check_commit_window_seconds": check_commit_window,
                            },
                        )
                except (ValueError, AttributeError):
                    # Timestamp parsing failed - ignore race detection
                    pass

                # Decrement concurrent checks gauge
                if concurrent_gauge is not None:
                    concurrent_gauge.dec()

                # Duplicate detected within transaction - emit telemetry and return 409
                _emit_duplicate_telemetry(request, envelope_dict, duplicate)
                # Transaction will rollback automatically on early return (no commit called)
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content={
                        "receipt_id": duplicate.receipt_id,
                        "commit_ts": duplicate.first_seen_ts,
                        "idem_key": duplicate.idem_key,
                    },
                )

            wal_pos = uow.append_wal(wal_entry)

            if obligation_store is not None and obligation_records:
                for record in obligation_records:
                    record.wal_pos = wal_pos
                obligation_store.bulk_save(obligation_records, connection=uow.connection)

            outbox_payload: dict[str, Any] = {
                "wal_pos": wal_pos,
                "topic": envelope_dict["topic"],
                "tenant_id": envelope_dict["tenant_id"],
                "space_id": envelope_dict["space_id"],
                "schema_uri": envelope_dict["schema_uri"],
                "schema_version": envelope_dict["schema_version"],
                "commit_ts": commit_ts,
                "idem_key": idem_key,
                "payload_sha256": payload_digest,
                "payload_bytes": body_bytes_length,
                "payload_inline_mode": ("embedded" if inline_body_allowed else "omitted"),
                "policy_stamp": envelope_dict.get("policy_stamp"),  # V1.3: Include policy context
            }
            if inline_body_allowed:
                body_for_outbox = sanitized_body if sanitized_body is not None else body_snapshot
                outbox_payload["body"] = _json_safe_body(body_for_outbox)

            outbox_bytes = canonical_json(outbox_payload).encode("utf-8")
            outbox_entry = OutboxEntry(
                id=None,
                wal_pos=wal_pos,
                tenant_id=envelope_dict["tenant_id"],
                space_id=envelope_dict["space_id"],
                driver=DEFAULT_OUTBOX_DRIVER,
                op_kind=DEFAULT_OUTBOX_OPERATION,
                payload=outbox_bytes,
                fingerprint=compute_fingerprint(
                    DEFAULT_OUTBOX_DRIVER,
                    DEFAULT_OUTBOX_OPERATION,
                    outbox_bytes,
                ),
                requeue_seq=0,
                retries=0,
                last_error=None,
            )
            uow.stage_outbox(outbox_entry)

            if outcome.key_version is None:
                raise RuntimeError("Minimal Gate did not return a key_version for accepted command")

            # V1: Extract obligations_applied from policy_stamp
            policy_stamp = envelope_dict.get("policy_stamp", {})
            obligations_applied_list = policy_stamp.get("obligations", [])

            receipt_doc = receipt_issuer.issue(
                receipt_id=str(receipt_id),
                idem_key=idem_key,
                wal_pos=wal_pos,
                commit_ts=commit_ts,
                tenant_id=envelope_dict["tenant_id"],
                space_id=envelope_dict["space_id"],
                device_id=envelope_dict["device_id"],
                envelope_sha256=envelope_dict["envelope_sha256"],  # V1: Full envelope hash
                mls_group_id=device_record.mls_group_id,
                key_version=outcome.key_version,
                obligations=decision.obligations,
                obligations_applied=obligations_applied_list,  # V1: Specific actions from policy_stamp
                manifest_fingerprint=envelope_dict.get("manifest_fingerprint"),
                payload_sha256=payload_digest,  # V1: Optional legacy field
                connection=uow.connection,
            )

            # Gap 42: Track policy stamp presence in receipts
            if metrics_exporter is not None and obligations_applied_list:
                metrics_exporter.emit(
                    "receipts_policy_stamp_present_total",
                    tenant=str(envelope_dict.get("tenant_id", "unknown")),
                    band=str(envelope_dict.get("band", "GREEN")),
                )

            ledger_entry = LedgerEntry(
                idem_key=idem_key,
                receipt_id=receipt_doc.receipt_id,
                first_seen_ts=commit_ts,
                state="COMMITTED",
                expiry_ts=None,
            )
            idem_ledger.upsert(ledger_entry, connection=uow.connection)

        # Gap 41: Decrement concurrent checks gauge after successful commit
        if concurrent_gauge is not None:
            concurrent_gauge.dec()

        if wal_pos is None or receipt_doc is None:
            raise RuntimeError("UnitOfWork failed to commit command artefacts")

        detail_payloads: list[dict[str, Any]] = []
        if obligation_directives:
            for directive in obligation_directives:
                payload: dict[str, Any] = {
                    "fields": (
                        directive.fields
                        if isinstance(directive.fields, str)
                        else list(directive.fields)
                    )
                }
                if directive.target is not None:
                    payload["target"] = (
                        directive.target
                        if isinstance(directive.target, str)
                        else list(directive.target)
                    )
                payload["mask"] = directive.mask
                detail_payloads.append(payload)

        receipt_model = Receipt(
            receipt_id=receipt_doc.receipt_id,
            idem_key=receipt_doc.idem_key,
            wal_pos=receipt_doc.wal_pos,
            commit_ts=receipt_doc.commit_ts,
            tenant_id=receipt_doc.tenant_id,
            space_id=receipt_doc.space_id,
            device_id=receipt_doc.device_id,
            mls_group_id=receipt_doc.mls_group_id,
            key_version=receipt_doc.key_version,
            device_sig=receipt_doc.device_sig,
        )

        audit_body = sanitized_body if sanitized_body is not None else body_snapshot
        record_admission_decision(
            request,
            decision=decision,
            envelope=_audit_envelope(envelope_dict, audit_body),
            receipt=receipt_model,
            port="command",
            sanitized_body=sanitized_body,
            original_body=body_snapshot,
            manifest_fingerprint=envelope_dict.get("manifest_fingerprint"),
        )

        response = CommandResponse(
            receipt_id=receipt_id,
            commit_ts=commit_ts,
            offsets={envelope_dict["topic"]: receipt_doc.wal_pos},
            idem_key=idem_key,
            obligations=list(receipt_doc.obligations),
            policy_manifest_fingerprint=receipt_doc.manifest_fingerprint,
            obligation_details=detail_payloads,
        )
        return response
    finally:
        if scheduler_token is not None:
            scheduler_token.release()


def _strip_body(envelope: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in envelope.items() if key != "body"}


def _json_safe_body(value: Any) -> Any:
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return cast(Any, value)
    return None


def _extract_body(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], bytes | None, Any]:
    working = {str(key): value for key, value in payload.items()}
    body_value = working.pop("body", None)
    if body_value is None:
        return working, None, None
    body_bytes = _normalise_body_bytes(body_value)
    return working, body_bytes, _json_safe_body(body_value)


def _normalise_body_bytes(body: Any) -> bytes:
    if isinstance(body, memoryview):
        return body.tobytes()
    if isinstance(body, (bytes, bytearray)):
        return bytes(body)
    if isinstance(body, str):
        return body.encode("utf-8")
    return canonical_json(body).encode("utf-8")


def _get_state_component(request: Request, attribute: str, expected_type: type[T]) -> T:
    component = getattr(request.app.state, attribute, None)
    if not isinstance(component, expected_type):
        raise RuntimeError(f"{attribute} is not configured on the application state")
    return component


def _get_state_component_optional(
    request: Request, attribute: str, expected_type: type[T]
) -> T | None:
    component = getattr(request.app.state, attribute, None)
    if component is None:
        return None
    if not isinstance(component, expected_type):
        raise RuntimeError(f"{attribute} is not configured on the application state")
    return component


def _get_unit_of_work_factory(request: Request) -> UnitOfWorkFactory:
    factory = getattr(request.app.state, "unit_of_work_factory", None)
    if not callable(factory):
        raise RuntimeError("UnitOfWork factory has not been configured")
    return cast(UnitOfWorkFactory, factory)


def _resolve_trace_id(request: Request) -> str:
    trace_id = getattr(request.state, "cognitive_trace_id", None)
    if trace_id:
        return str(trace_id)
    tracer_factory = getattr(request.app.state, "tracer_factory", None)
    if isinstance(tracer_factory, TracerFactory):
        trace_id = tracer_factory.new_trace_id()
    else:
        trace_id = str(uuid.uuid4())
    request.state.cognitive_trace_id = trace_id
    return trace_id


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    *,
    component: str,
    reason: str | None = None,
    hint: str | None = None,
    budgets: Mapping[str, int] | None = None,
    details: Mapping[str, Any] | None = None,
) -> JSONResponse:
    trace_id = _resolve_trace_id(request)
    envelope = ErrorEnvelope(
        code=code,
        component=component,
        trace_id=trace_id,
        reason=reason,
        hint=hint,
        budgets=budgets,
        details=details,
    )
    return JSONResponse(status_code=status_code, content=envelope.as_payload())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _audit_envelope(envelope: Mapping[str, Any], body: Any) -> dict[str, Any]:
    payload = dict(envelope)
    if body is not None:
        payload["body"] = body
    return payload


def _emit_duplicate_telemetry(
    request: Request,
    envelope: Mapping[str, Any],
    entry: LedgerEntry,
) -> None:
    metrics_exporter = getattr(request.app.state, "metrics_exporter", None)
    if isinstance(metrics_exporter, MetricsExporter):
        metrics_exporter.emit(
            "command_idempotency_duplicates_total",
            port="command",
            state=str(entry.state),
        )

    observability_emitter = getattr(request.app.state, "observability_emitter", None)
    if isinstance(observability_emitter, ObservabilityEmitter):
        event_payload: dict[str, Any] = {
            "event": "command_idem_duplicate",
            "trace_id": _resolve_trace_id(request),
            "idem_key": entry.idem_key,
            "receipt_id": entry.receipt_id,
            "state": entry.state,
            "tenant_id": envelope.get("tenant_id"),
            "space_id": envelope.get("space_id"),
        }
        if entry.first_seen_ts:
            event_payload["first_seen_ts"] = entry.first_seen_ts
        observability_emitter.emit(event_payload)


def _resolve_cap_request(envelope: Mapping[str, Any], cap: str) -> int | None:
    for root_key in ("policy", "pep", "policy_ctx"):
        root = envelope.get(root_key)
        if not isinstance(root, Mapping):
            continue
        root_mapping = cast(Mapping[str, Any], root)
        caps_section = cast(Mapping[str, Any] | None, root_mapping.get("caps"))
        if not isinstance(caps_section, Mapping):
            continue
        cap_entry = cast(Any, caps_section.get(cap))
        value = coerce_positive_int(cap_entry)
        if value is not None:
            return value
    return None


def _compute_scheduler_cost(
    *,
    fanout: int,
    payload_bytes: Any,
    top_k: int | None,
    latency_ms: int | None,
) -> int:
    payload_units = 0
    if isinstance(payload_bytes, (int, float)) and payload_bytes > 0:
        payload_units = max(1, int((int(payload_bytes) + 4095) // 4096))

    top_k_units = 0
    if top_k is not None and top_k > 0:
        top_k_units = max(1, int(top_k) // 8)

    latency_units = 0
    if latency_ms is not None and latency_ms > 0 and latency_ms < 150:
        latency_units = 1

    cost = fanout + payload_units + top_k_units + latency_units
    return max(1, cost)


def _serialize_qos_budgets(qos: QoSContext) -> dict[str, int]:
    return {
        "fanout": max(0, int(qos.fanout_budget)),
        "top_k": max(0, int(qos.top_k_budget)),
    }


def _emit_qos_budget_telemetry(
    request: Request,
    *,
    envelope: Mapping[str, Any],
    cap: str,
    reason: str,
    budgets: Mapping[str, int],
    hint: str | None,
) -> None:
    metrics_exporter = getattr(request.app.state, "metrics_exporter", None)
    if isinstance(metrics_exporter, MetricsExporter):
        metrics_exporter.emit(
            "qos_budget_exhausted_total",
            port="command",
            cap=cap,
            band=str(envelope.get("band", "UNKNOWN")),
        )

    observability_emitter = getattr(request.app.state, "observability_emitter", None)
    if isinstance(observability_emitter, ObservabilityEmitter):
        event: dict[str, Any] = {
            "event": "command_qos_budget_exhausted",
            "trace_id": _resolve_trace_id(request),
            "port": "command",
            "cap": cap,
            "reason": reason,
            "budgets": dict(budgets),
            "tenant_id": envelope.get("tenant_id"),
            "space_id": envelope.get("space_id"),
            "topic": envelope.get("topic"),
            "band": envelope.get("band"),
        }
        if hint:
            event["hint"] = hint
        observability_emitter.emit(event)


def _qos_budget_response(
    request: Request,
    qos: QoSContext,
    *,
    envelope: Mapping[str, Any],
    cap: str,
    reason: str,
    hint: str | None = None,
) -> JSONResponse:
    budgets = _serialize_qos_budgets(qos)
    _emit_qos_budget_telemetry(
        request,
        envelope=envelope,
        cap=cap,
        reason=reason,
        budgets=budgets,
        hint=hint,
    )
    return _error_response(
        request,
        status.HTTP_429_TOO_MANY_REQUESTS,
        "QOS_BUDGET_EXHAUSTED",
        component=KERNEL_COMPONENT_QOS,
        reason=reason,
        hint=hint,
        budgets=budgets,
        details={"cap": cap},
    )


def _record_pem_metrics(
    metrics_exporter: MetricsExporter | None,
    decision: Any,
    evaluation_latency_ms: float,
    *,
    band: str,
    schema_uri: str,
    lane: str,
) -> None:
    if not isinstance(metrics_exporter, MetricsExporter):
        return

    decision_label = "allow" if getattr(decision, "admit", False) else "deny"

    decisions_counter = metrics_exporter.counter(
        "k0_pep_decisions_total",
        "Total PEM decisions by outcome",
        labelnames=("decision", "band", "schema_uri", "lane"),
    )
    decisions_counter.labels(
        decision=decision_label,
        band=band,
        schema_uri=schema_uri,
        lane=lane,
    ).inc()

    obligations_counter = metrics_exporter.counter(
        "k0_pep_obligations_total",
        "Total PEM obligations emitted",
        labelnames=("obligation", "decision", "band"),
    )
    for obligation in getattr(decision, "obligations", ()):  # type: ignore[attr-defined]
        obligation_name = getattr(obligation, "name", str(obligation))
        obligations_counter.labels(
            obligation=obligation_name,
            decision=decision_label,
            band=band,
        ).inc()

    histogram = metrics_exporter.histogram(
        "k0_pep_evaluation_latency_ms",
        "PEM evaluation latency (milliseconds)",
        labelnames=("band", "schema_uri", "lane"),
        buckets=(1, 5, 10, 25, 50, 100, 250),
    )
    histogram.labels(band=band, schema_uri=schema_uri, lane=lane).observe(
        max(evaluation_latency_ms, 0.0)
    )
