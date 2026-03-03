"""Bridge-side envelope construction for K0 command port.

Populates all required envelope fields from minimal K1 inputs,
computes integrity hashes, and signs the envelope.

Per bridge/contracts/command_port.protocol.yaml envelope_building section.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from blake3 import blake3  # type: ignore[import]

from .signing import SigningBackend

logger = logging.getLogger(__name__)

# Canonical JSON: sorted keys, no ASCII escape, minimal separators
# Must match k0/security/crypto.py canonical_json() for hash compatibility.
_CANONICAL_SEPARATORS = (",", ":")


def _canonical_json(payload: Any) -> str:
    """Produce canonical JSON identical to K0's ``canonical_json``."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=_CANONICAL_SEPARATORS,
    )


# ---------------------------------------------------------------------------
# Bridge configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BridgeConfig:
    """Static configuration injected from the Bridge runtime.

    Values come from environment or config file; they do not change
    per-request.
    """

    tenant_id: str
    space_id: str
    device_id: str
    actor: str = "bridge"
    policy_version: str = "1.0"
    default_band: str = "GREEN"


# ---------------------------------------------------------------------------
# CommandEnvelope (pre-built envelope for batch submission)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CommandEnvelope:
    """A fully-built envelope ready for submission to K0.

    Used by ``submit_batch`` in ``KernelCommandPort``.
    """

    topic: str
    body: dict[str, Any]
    schema_uri: str | None = None
    band: str | None = None
    trace_id: str | None = None


# ---------------------------------------------------------------------------
# EnvelopeBuilder
# ---------------------------------------------------------------------------


class EnvelopeBuilder:
    """Construct full K0 envelopes from minimal K1-provided fields.

    K1 callers provide: ``topic``, ``body``, and optionally ``schema_uri``,
    ``band``, ``trace_id``.  The builder fills in all remaining fields
    required by the K0 Gate.

    Parameters
    ----------
    config : BridgeConfig
        Static Bridge configuration (tenant, space, device, etc.).
    signer : SigningBackend
        Pluggable signing backend for envelope signature.
    """

    def __init__(self, config: BridgeConfig, signer: SigningBackend) -> None:
        self._config = config
        self._signer = signer

    def build(
        self,
        topic: str,
        body: dict[str, Any],
        *,
        schema_uri: str | None = None,
        band: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Build a complete K0 envelope from K1 inputs.

        Parameters
        ----------
        topic : str
            Command topic (e.g. ``memory.write``).
        body : dict
            Domain payload matching the per-topic body schema.
        schema_uri : str | None
            Explicit schema URI. Derived from topic if omitted.
        band : str | None
            Privacy band override. Uses config default if omitted.
        trace_id : str | None
            Cognitive trace ID. Generated if omitted.

        Returns
        -------
        dict[str, Any]
            Complete envelope dict ready for JSON serialisation and POST.
        """
        cfg = self._config

        # Resolve optional fields
        resolved_band = band or cfg.default_band
        resolved_trace_id = trace_id or str(uuid.uuid4())
        resolved_schema_uri = schema_uri or self._derive_schema_uri(topic)
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Canonical body for hashing
        body_json = _canonical_json(body)
        body_bytes = body_json.encode("utf-8")

        # Compute payload_sha256 (body-only hash)
        payload_sha256 = hashlib.sha256(body_bytes).hexdigest()

        # Compute deterministic idempotency key: BLAKE3(topic + body_json + device_id)
        idem_key = self._compute_idem_key(topic, body_json, cfg.device_id)

        # Schema version from topic schema (always "1.0" for now)
        schema_version = "1.0"

        # Build envelope (without sig fields yet)
        envelope: dict[str, Any] = {
            "cognitive_trace_id": resolved_trace_id,
            "tenant_id": cfg.tenant_id,
            "space_id": cfg.space_id,
            "actor": cfg.actor,
            "device_id": cfg.device_id,
            "topic": topic,
            "band": resolved_band,
            "ts": ts,
            "policy_version": cfg.policy_version,
            "schema_uri": resolved_schema_uri,
            "schema_version": schema_version,
            "body": body,
            "payload_sha256": payload_sha256,
            "idem_key": idem_key,
        }

        # Compute envelope_sha256 (full envelope hash, excluding sig fields)
        # This matches K0's compute_envelope_sha256 which uses canonical_envelope
        # with exclude_signature=True (excludes sig and envelope_sha256).
        canonical_bytes = _canonical_json(envelope).encode("utf-8")
        envelope_sha256 = hashlib.sha256(canonical_bytes).hexdigest()
        envelope["envelope_sha256"] = envelope_sha256

        # Sign the envelope_sha256
        sig_result = self._signer.sign(envelope_sha256.encode("utf-8"))
        envelope["sig"] = sig_result
        envelope["sig_alg"] = self._signer.algorithm
        envelope["sig_kid"] = self._signer.key_id

        return envelope

    def build_from_command_envelope(self, cmd: CommandEnvelope) -> dict[str, Any]:
        """Build from a pre-constructed ``CommandEnvelope``."""
        return self.build(
            topic=cmd.topic,
            body=cmd.body,
            schema_uri=cmd.schema_uri,
            band=cmd.band,
            trace_id=cmd.trace_id,
        )

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _derive_schema_uri(topic: str) -> str:
        """Derive schema URI from topic per convention.

        ``memory.write`` -> ``schema://k0/topics/memory_write.body.json``
        ``ifl.health.fitbit.heart_rate`` -> ``schema://k0/topics/ifl_event.body.json``
        """
        # For ifl.* glob topics, always use ifl_event as the base
        if topic.startswith("ifl."):
            base = "ifl_event"
        else:
            base = topic.replace(".", "_")
        return f"schema://k0/topics/{base}.body.json"

    @staticmethod
    def _compute_idem_key(topic: str, body_json: str, device_id: str) -> str:
        """BLAKE3(topic + canonical_json(body) + device_id) -> hex digest."""
        digest = blake3()  # type: ignore[call-arg]
        digest.update(topic.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(body_json.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(device_id.encode("utf-8"))
        return digest.hexdigest()
