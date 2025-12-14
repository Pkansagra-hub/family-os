"""Comprehensive tests for Issue 1.5 & 1.6 (V1 Envelope + Security Crypto).

Tests cover:
  - Issue 1.5: V1 Envelope model validation (sig_alg, sig_kid, envelope_sha256)
  - Issue 1.6: V1 crypto utilities (canonical_envelope, compute_envelope_sha256, verify_full_envelope_signature)
"""

from __future__ import annotations

import uuid

import pytest
from nacl.signing import SigningKey

from k0.ports.command import Envelope
from k0.security import (
    canonical_envelope,
    compute_envelope_sha256,
    encode_base64url,
    verify_full_envelope_signature,
)

# ============================================================================
# TestIssue15EnvelopeModel: V1 Envelope Pydantic validation
# ============================================================================


class TestIssue15EnvelopeModelV1Required:
    """Test V1 required fields in Envelope model."""

    def test_v1_envelope_with_all_required_fields(self) -> None:
        """Test V1 envelope with all required fields validates."""
        envelope = Envelope(
            cognitive_trace_id=uuid.uuid4(),
            tenant_id="tenant-001",
            space_id="space-001",
            topic="memory.event",
            schema_uri="https://schema.local/memory",
            schema_version="1.0",
            actor="alice",
            device_id="device-001",
            band="GREEN",
            policy_version="2025-11-01",
            ts="2025-11-10T10:00:00Z",
            sig="signature_bytes_here",
            sig_alg="Ed25519SHA512",
            sig_kid="did:device:device-001#2025-11-10",
            envelope_sha256="abc123def456" * 5 + "ab",
        )

        # Verify required fields present
        assert envelope.sig_alg == "Ed25519SHA512"
        assert envelope.sig_kid == "did:device:device-001#2025-11-10"
        assert envelope.envelope_sha256 == "abc123def456" * 5 + "ab"

    def test_v1_envelope_has_required_sig_alg(self) -> None:
        """Test V1 envelope has sig_alg as required field."""
        # Create valid envelope and verify sig_alg is present
        envelope = Envelope(
            cognitive_trace_id=uuid.uuid4(),
            tenant_id="tenant-001",
            space_id="space-001",
            topic="memory.event",
            schema_uri="https://schema.local/memory",
            schema_version="1.0",
            actor="alice",
            device_id="device-001",
            band="GREEN",
            policy_version="2025-11-01",
            ts="2025-11-10T10:00:00Z",
            sig="signature_bytes_here",
            sig_alg="Ed25519SHA512",
            sig_kid="did:device:device-001#2025-11-10",
            envelope_sha256="abc123def456" * 5 + "ab",
        )
        assert envelope.sig_alg is not None
        assert isinstance(envelope.sig_alg, str)

    def test_v1_envelope_has_required_sig_kid(self) -> None:
        """Test V1 envelope has sig_kid as required field."""
        envelope = Envelope(
            cognitive_trace_id=uuid.uuid4(),
            tenant_id="tenant-001",
            space_id="space-001",
            topic="memory.event",
            schema_uri="https://schema.local/memory",
            schema_version="1.0",
            actor="alice",
            device_id="device-001",
            band="GREEN",
            policy_version="2025-11-01",
            ts="2025-11-10T10:00:00Z",
            sig="signature_bytes_here",
            sig_alg="Ed25519SHA512",
            sig_kid="did:device:device-001#2025-11-10",
            envelope_sha256="abc123def456" * 5 + "ab",
        )
        assert envelope.sig_kid is not None
        assert isinstance(envelope.sig_kid, str)

    def test_v1_envelope_has_required_envelope_sha256(self) -> None:
        """Test V1 envelope has envelope_sha256 as required field."""
        envelope = Envelope(
            cognitive_trace_id=uuid.uuid4(),
            tenant_id="tenant-001",
            space_id="space-001",
            topic="memory.event",
            schema_uri="https://schema.local/memory",
            schema_version="1.0",
            actor="alice",
            device_id="device-001",
            band="GREEN",
            policy_version="2025-11-01",
            ts="2025-11-10T10:00:00Z",
            sig="signature_bytes_here",
            sig_alg="Ed25519SHA512",
            sig_kid="did:device:device-001#2025-11-10",
            envelope_sha256="a" * 64,  # 64 hex chars for SHA-256
        )
        assert envelope.envelope_sha256 is not None
        assert isinstance(envelope.envelope_sha256, str)
        assert len(envelope.envelope_sha256) == 64  # SHA-256 hex digest


class TestIssue15EnvelopeModelV1Optional:
    """Test V1 optional fields in Envelope model."""

    def test_v1_envelope_optional_fields_default_none(self) -> None:
        """Test V1 optional fields default to None."""
        envelope = Envelope(
            cognitive_trace_id=uuid.uuid4(),
            tenant_id="tenant-001",
            space_id="space-001",
            topic="memory.event",
            schema_uri="https://schema.local/memory",
            schema_version="1.0",
            actor="alice",
            device_id="device-001",
            band="GREEN",
            policy_version="2025-11-01",
            ts="2025-11-10T10:00:00Z",
            sig="signature_bytes_here",
            sig_alg="Ed25519SHA512",
            sig_kid="did:device:device-001#2025-11-10",
            envelope_sha256="abc123def456" * 5 + "ab",
        )

        # Verify optional fields are None
        assert envelope.ingested_at is None
        assert envelope.clock_skew_ms is None
        assert envelope.policy_stamp is None
        assert envelope.location_geohash is None
        assert envelope.location_precision_m is None

    def test_v1_envelope_optional_fields_can_be_set(self) -> None:
        """Test V1 optional fields can be set."""
        envelope = Envelope(
            cognitive_trace_id=uuid.uuid4(),
            tenant_id="tenant-001",
            space_id="space-001",
            topic="memory.event",
            schema_uri="https://schema.local/memory",
            schema_version="1.0",
            actor="alice",
            device_id="device-001",
            band="GREEN",
            policy_version="2025-11-01",
            ts="2025-11-10T10:00:00Z",
            sig="signature_bytes_here",
            sig_alg="Ed25519SHA512",
            sig_kid="did:device:device-001#2025-11-10",
            envelope_sha256="abc123def456" * 5 + "ab",
            ingested_at="2025-11-10T10:00:01Z",
            clock_skew_ms=1000,
            policy_stamp={"band": "GREEN", "decision": "ALLOW"},
            location_geohash="9q8yy6",
            location_precision_m=1,
        )

        # Verify optional fields set correctly
        assert envelope.ingested_at == "2025-11-10T10:00:01Z"
        assert envelope.clock_skew_ms == 1000
        assert envelope.policy_stamp == {"band": "GREEN", "decision": "ALLOW"}
        assert envelope.location_geohash == "9q8yy6"
        assert envelope.location_precision_m == 1


# ============================================================================
# TestIssue16CanonicalEnvelope: canonical_envelope() for V1
# ============================================================================


class TestIssue16CanonicalEnvelopeV1:
    """Test canonical_envelope() includes body in V1 (prevents header tampering)."""

    def test_canonical_envelope_includes_body_v1(self) -> None:
        """Test V1 canonical_envelope includes body (not excluded like V0)."""
        envelope = {
            "cognitive_trace_id": "123e4567-e89b-12d3-a456-426614174000",
            "tenant_id": "tenant-001",
            "actor": "alice",
            "body": {"message": "Hello world"},
            "sig": "signature_here",
        }

        canonical = canonical_envelope(envelope, exclude_signature=True)
        canonical_str = canonical.decode("utf-8")

        # V1: body MUST be in canonical representation
        assert '"body"' in canonical_str
        assert '"message"' in canonical_str
        assert '"Hello world"' in canonical_str

        # sig MUST be excluded
        assert '"sig"' not in canonical_str

    def test_canonical_envelope_excludes_only_sig(self) -> None:
        """Test canonical_envelope excludes only sig field."""
        envelope = {
            "cognitive_trace_id": "123e4567-e89b-12d3-a456-426614174000",
            "tenant_id": "tenant-001",
            "space_id": "space-001",
            "actor": "alice",
            "band": "GREEN",
            "body": {"data": "test"},
            "sig": "signature_here",
        }

        canonical = canonical_envelope(envelope, exclude_signature=True)
        canonical_str = canonical.decode("utf-8")

        # All headers must be included
        assert '"cognitive_trace_id"' in canonical_str
        assert '"tenant_id"' in canonical_str
        assert '"space_id"' in canonical_str
        assert '"actor"' in canonical_str
        assert '"band"' in canonical_str
        assert '"body"' in canonical_str

        # sig excluded
        assert '"sig"' not in canonical_str

    def test_canonical_envelope_deterministic(self) -> None:
        """Test canonical_envelope is deterministic (sorted keys)."""
        envelope = {
            "z_field": "last",
            "a_field": "first",
            "m_field": "middle",
        }

        canonical1 = canonical_envelope(envelope, exclude_signature=False)
        canonical2 = canonical_envelope(envelope, exclude_signature=False)

        # Must be identical
        assert canonical1 == canonical2

        # Must be sorted
        canonical_str = canonical1.decode("utf-8")
        assert canonical_str.index('"a_field"') < canonical_str.index('"m_field"')
        assert canonical_str.index('"m_field"') < canonical_str.index('"z_field"')


# ============================================================================
# TestIssue16ComputeEnvelopeSha256: compute_envelope_sha256() for V1
# ============================================================================


class TestIssue16ComputeEnvelopeSha256:
    """Test compute_envelope_sha256() for V1 replay protection."""

    def test_compute_envelope_sha256_deterministic(self) -> None:
        """Test envelope_sha256 is deterministic."""
        envelope = {
            "cognitive_trace_id": "123e4567-e89b-12d3-a456-426614174000",
            "tenant_id": "tenant-001",
            "actor": "alice",
            "body": {"message": "Hello"},
            "sig": "signature_here",
        }

        hash1 = compute_envelope_sha256(envelope)
        hash2 = compute_envelope_sha256(envelope)

        # Must be identical
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest

    def test_compute_envelope_sha256_changes_with_body(self) -> None:
        """Test envelope_sha256 changes when body changes."""
        envelope1 = {
            "cognitive_trace_id": "123e4567-e89b-12d3-a456-426614174000",
            "tenant_id": "tenant-001",
            "body": {"message": "Hello"},
        }
        envelope2 = {
            "cognitive_trace_id": "123e4567-e89b-12d3-a456-426614174000",
            "tenant_id": "tenant-001",
            "body": {"message": "World"},
        }

        hash1 = compute_envelope_sha256(envelope1)
        hash2 = compute_envelope_sha256(envelope2)

        # Must be different (body changed)
        assert hash1 != hash2

    def test_compute_envelope_sha256_changes_with_headers(self) -> None:
        """Test envelope_sha256 changes when headers change."""
        envelope1 = {
            "cognitive_trace_id": "123e4567-e89b-12d3-a456-426614174000",
            "actor": "alice",
            "body": {"message": "Hello"},
        }
        envelope2 = {
            "cognitive_trace_id": "123e4567-e89b-12d3-a456-426614174000",
            "actor": "bob",  # Different actor
            "body": {"message": "Hello"},
        }

        hash1 = compute_envelope_sha256(envelope1)
        hash2 = compute_envelope_sha256(envelope2)

        # Must be different (header changed)
        assert hash1 != hash2

    def test_compute_envelope_sha256_ignores_sig_field(self) -> None:
        """Test envelope_sha256 ignores sig field (excluded from hash)."""
        envelope1 = {
            "cognitive_trace_id": "123e4567-e89b-12d3-a456-426614174000",
            "actor": "alice",
            "body": {"message": "Hello"},
            "sig": "signature1",
        }
        envelope2 = {
            "cognitive_trace_id": "123e4567-e89b-12d3-a456-426614174000",
            "actor": "alice",
            "body": {"message": "Hello"},
            "sig": "signature2",  # Different sig
        }

        hash1 = compute_envelope_sha256(envelope1)
        hash2 = compute_envelope_sha256(envelope2)

        # Must be identical (sig field ignored)
        assert hash1 == hash2


# ============================================================================
# TestIssue16VerifyFullEnvelopeSignature: verify_full_envelope_signature()
# ============================================================================


class TestIssue16VerifyFullEnvelopeSignature:
    """Test verify_full_envelope_signature() for V1 full envelope verification."""

    def test_verify_valid_signature(self) -> None:
        """Test verifying valid V1 full envelope signature."""
        # Generate signing key
        signing_key = SigningKey.generate()
        verify_key_bytes = bytes(signing_key.verify_key)
        verify_key_b64 = encode_base64url(verify_key_bytes)

        # Create envelope
        envelope = {
            "cognitive_trace_id": "123e4567-e89b-12d3-a456-426614174000",
            "tenant_id": "tenant-001",
            "actor": "alice",
            "body": {"message": "Hello world"},
        }

        # Sign full envelope
        canonical = canonical_envelope(envelope, exclude_signature=True)
        signed = signing_key.sign(canonical)
        signature_b64 = encode_base64url(signed.signature)

        # Add signature to envelope
        envelope["sig"] = signature_b64

        # Verify signature
        result = verify_full_envelope_signature(envelope, verify_key_b64)
        assert result is True

    def test_verify_invalid_signature_fails(self) -> None:
        """Test verifying invalid signature fails."""
        # Generate signing key
        signing_key = SigningKey.generate()
        verify_key_bytes = bytes(signing_key.verify_key)
        verify_key_b64 = encode_base64url(verify_key_bytes)

        # Create envelope with invalid signature
        envelope = {
            "cognitive_trace_id": "123e4567-e89b-12d3-a456-426614174000",
            "tenant_id": "tenant-001",
            "actor": "alice",
            "body": {"message": "Hello world"},
            "sig": "invalid_signature_base64url",
        }

        # Verify signature (should fail)
        result = verify_full_envelope_signature(envelope, verify_key_b64)
        assert result is False

    def test_verify_header_tampering_detected(self) -> None:
        """Test header tampering is detected (V1 improvement over V0)."""
        # Generate signing key
        signing_key = SigningKey.generate()
        verify_key_bytes = bytes(signing_key.verify_key)
        verify_key_b64 = encode_base64url(verify_key_bytes)

        # Create original envelope
        envelope = {
            "cognitive_trace_id": "123e4567-e89b-12d3-a456-426614174000",
            "tenant_id": "tenant-001",
            "actor": "alice",
            "band": "RED",
            "body": {"message": "Sensitive data"},
        }

        # Sign full envelope
        canonical = canonical_envelope(envelope, exclude_signature=True)
        signed = signing_key.sign(canonical)
        signature_b64 = encode_base64url(signed.signature)
        envelope["sig"] = signature_b64

        # ATTACKER: Modify header (band RED → GREEN to bypass privacy)
        envelope["band"] = "GREEN"

        # Verify signature (should fail - header tampering detected)
        result = verify_full_envelope_signature(envelope, verify_key_b64)
        assert result is False

    def test_verify_body_tampering_detected(self) -> None:
        """Test body tampering is detected."""
        # Generate signing key
        signing_key = SigningKey.generate()
        verify_key_bytes = bytes(signing_key.verify_key)
        verify_key_b64 = encode_base64url(verify_key_bytes)

        # Create original envelope
        envelope = {
            "cognitive_trace_id": "123e4567-e89b-12d3-a456-426614174000",
            "tenant_id": "tenant-001",
            "actor": "alice",
            "body": {"message": "Original"},
        }

        # Sign full envelope
        canonical = canonical_envelope(envelope, exclude_signature=True)
        signed = signing_key.sign(canonical)
        signature_b64 = encode_base64url(signed.signature)
        envelope["sig"] = signature_b64

        # ATTACKER: Modify body
        envelope["body"]["message"] = "Tampered"

        # Verify signature (should fail - body tampering detected)
        result = verify_full_envelope_signature(envelope, verify_key_b64)
        assert result is False

    def test_verify_missing_signature_fails(self) -> None:
        """Test missing signature returns False."""
        verify_key_b64 = "fake_key"

        envelope = {
            "cognitive_trace_id": "123e4567-e89b-12d3-a456-426614174000",
            "tenant_id": "tenant-001",
            # sig MISSING
        }

        result = verify_full_envelope_signature(envelope, verify_key_b64)
        assert result is False


# ============================================================================
# TestIssue1516Integration: Combined tests for V1 envelope + crypto
# ============================================================================


class TestIssue1516Integration:
    """Integration tests combining Issue 1.5 (Envelope) + Issue 1.6 (Crypto)."""

    def test_full_v1_envelope_with_signature_verification(self) -> None:
        """Test complete V1 envelope creation and verification."""
        # Generate signing key
        signing_key = SigningKey.generate()
        verify_key_bytes = bytes(signing_key.verify_key)
        verify_key_b64 = encode_base64url(verify_key_bytes)

        # Create V1 envelope dict
        envelope_dict = {
            "cognitive_trace_id": "123e4567-e89b-12d3-a456-426614174000",
            "tenant_id": "tenant-001",
            "space_id": "space-001",
            "topic": "memory.event",
            "schema_uri": "https://schema.local/memory",
            "schema_version": "1.0",
            "actor": "alice",
            "device_id": "device-001",
            "band": "GREEN",
            "policy_version": "2025-11-01",
            "ts": "2025-11-10T10:00:00Z",
            "sig_alg": "Ed25519SHA512",
            "sig_kid": "did:device:device-001#2025-11-10",
            "body": {"message": "Hello K0 V1"},
        }

        # Compute envelope_sha256
        envelope_sha256 = compute_envelope_sha256(envelope_dict)
        envelope_dict["envelope_sha256"] = envelope_sha256

        # Sign full envelope
        canonical = canonical_envelope(envelope_dict, exclude_signature=True)
        signed = signing_key.sign(canonical)
        signature_b64 = encode_base64url(signed.signature)
        envelope_dict["sig"] = signature_b64

        # Create Pydantic envelope
        envelope = Envelope(**envelope_dict)

        # Verify all V1 fields present
        assert envelope.sig_alg == "Ed25519SHA512"
        assert envelope.sig_kid.startswith("did:device:")
        assert envelope.envelope_sha256 == envelope_sha256

        # Verify signature
        result = verify_full_envelope_signature(envelope_dict, verify_key_b64)
        assert result is True

    def test_v1_replay_detection_with_envelope_sha256(self) -> None:
        """Test replay detection using envelope_sha256."""
        # Create two identical envelopes
        envelope1 = {
            "cognitive_trace_id": "123e4567-e89b-12d3-a456-426614174000",
            "tenant_id": "tenant-001",
            "actor": "alice",
            "body": {"message": "Hello"},
        }
        envelope2 = {
            "cognitive_trace_id": "123e4567-e89b-12d3-a456-426614174000",
            "tenant_id": "tenant-001",
            "actor": "alice",
            "body": {"message": "Hello"},
        }

        # Compute hashes
        hash1 = compute_envelope_sha256(envelope1)
        hash2 = compute_envelope_sha256(envelope2)

        # Identical envelopes → identical hashes (replay detection)
        assert hash1 == hash2

        # In production: Check if hash1 exists in WAL → reject as replay


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
