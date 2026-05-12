"""Real component tests for EnvelopeBuilder.

Tests envelope construction, field population, idem_key determinism,
schema_uri derivation, hash integrity, and signing integration.
No mocks -- uses real HmacSigning backend.

Milestone: M2 Epic 2.15
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

import pytest

from bridge.core.envelope_builder import (
    BridgeConfig,
    CommandEnvelope,
    EnvelopeBuilder,
    _canonical_json,
)
from bridge.core.signing import HmacSigning

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> BridgeConfig:
    return BridgeConfig(
        tenant_id="tenant-test",
        space_id="space-test",
        device_id="device-test-001",
        actor="bridge",
        policy_version="1.0",
        default_band="GREEN",
    )


@pytest.fixture
def signer() -> HmacSigning:
    return HmacSigning(secret=os.urandom(32), key_id="did:device:test-001#2026-01-01")


@pytest.fixture
def builder(config: BridgeConfig, signer: HmacSigning) -> EnvelopeBuilder:
    return EnvelopeBuilder(config=config, signer=signer)


@pytest.fixture
def sample_body() -> dict[str, Any]:
    return {
        "schema_version": "2.0",
        "operation": "UPSERT",
        "text": "Test memory atom",
        "topics": ["testing"],
        "sentiment_label": "neutral",
        "affect": {"valence": 0.0, "arousal": 0.3, "dominance": 0.5},
        "source_type": "system_inferred",
        "novelty": "ROUTINE",
        "elaboration_depth": "MENTION",
        "temporal_orientation": "ONGOING",
        "confidence": 0.85,
        "session_id": "sess-test",
        "conversation_turn": 1,
        "language": "en",
    }


# ===========================================================================
# Envelope field population
# ===========================================================================


class TestEnvelopeFields:
    """Verify all required envelope fields are populated."""

    def test_all_required_fields_present(
        self, builder: EnvelopeBuilder, sample_body: dict[str, Any]
    ) -> None:
        envelope = builder.build("memory.write", sample_body)
        required_fields = {
            "cognitive_trace_id",
            "tenant_id",
            "space_id",
            "actor",
            "device_id",
            "topic",
            "band",
            "ts",
            "policy_version",
            "schema_uri",
            "schema_version",
            "body",
            "payload_sha256",
            "envelope_sha256",
            "sig",
            "sig_alg",
            "sig_kid",
        }
        assert required_fields.issubset(set(envelope.keys()))

    def test_config_fields_propagated(
        self, builder: EnvelopeBuilder, sample_body: dict[str, Any]
    ) -> None:
        envelope = builder.build("memory.write", sample_body)
        assert envelope["tenant_id"] == "tenant-test"
        assert envelope["space_id"] == "space-test"
        assert envelope["device_id"] == "device-test-001"
        assert envelope["actor"] == "bridge"
        assert envelope["policy_version"] == "1.0"

    def test_topic_preserved(self, builder: EnvelopeBuilder, sample_body: dict[str, Any]) -> None:
        envelope = builder.build("memory.write", sample_body)
        assert envelope["topic"] == "memory.write"

    def test_body_preserved(self, builder: EnvelopeBuilder, sample_body: dict[str, Any]) -> None:
        envelope = builder.build("memory.write", sample_body)
        assert envelope["body"] == sample_body

    def test_default_band_green(
        self, builder: EnvelopeBuilder, sample_body: dict[str, Any]
    ) -> None:
        envelope = builder.build("memory.write", sample_body)
        assert envelope["band"] == "GREEN"

    def test_explicit_band_override(
        self, builder: EnvelopeBuilder, sample_body: dict[str, Any]
    ) -> None:
        envelope = builder.build("memory.write", sample_body, band="RED")
        assert envelope["band"] == "RED"

    def test_explicit_trace_id(self, builder: EnvelopeBuilder, sample_body: dict[str, Any]) -> None:
        envelope = builder.build("memory.write", sample_body, trace_id="trace-explicit-001")
        assert envelope["cognitive_trace_id"] == "trace-explicit-001"

    def test_auto_generated_trace_id(
        self, builder: EnvelopeBuilder, sample_body: dict[str, Any]
    ) -> None:
        envelope = builder.build("memory.write", sample_body)
        assert len(envelope["cognitive_trace_id"]) > 0

    def test_timestamp_format(self, builder: EnvelopeBuilder, sample_body: dict[str, Any]) -> None:
        envelope = builder.build("memory.write", sample_body)
        ts = envelope["ts"]
        assert ts.endswith("Z")
        assert "T" in ts

    def test_schema_version_is_2_2(
        self, builder: EnvelopeBuilder, sample_body: dict[str, Any]
    ) -> None:
        envelope = builder.build("memory.write", sample_body)
        assert envelope["schema_version"] == "2.2"

    def test_sig_alg_matches_signer(
        self, builder: EnvelopeBuilder, sample_body: dict[str, Any]
    ) -> None:
        envelope = builder.build("memory.write", sample_body)
        assert envelope["sig_alg"] == "hmac-sha256"

    def test_sig_kid_matches_signer(
        self, builder: EnvelopeBuilder, sample_body: dict[str, Any]
    ) -> None:
        envelope = builder.build("memory.write", sample_body)
        assert envelope["sig_kid"] == "did:device:test-001#2026-01-01"


# ===========================================================================
# Schema URI derivation
# ===========================================================================


class TestSchemaUriDerivation:
    """Verify _derive_schema_uri logic for various topic patterns."""

    def test_memory_write(self, builder: EnvelopeBuilder, sample_body: dict[str, Any]) -> None:
        envelope = builder.build("memory.write", sample_body)
        assert envelope["schema_uri"] == "schema://k0/topics/memory_write.body.json"

    def test_session_snapshot(self, builder: EnvelopeBuilder, sample_body: dict[str, Any]) -> None:
        envelope = builder.build("session.snapshot", sample_body)
        assert envelope["schema_uri"] == "schema://k0/topics/session_snapshot.body.json"

    def test_sync_delta(self, builder: EnvelopeBuilder, sample_body: dict[str, Any]) -> None:
        envelope = builder.build("sync.delta", sample_body)
        assert envelope["schema_uri"] == "schema://k0/topics/sync_delta.body.json"

    def test_ifl_glob_uses_ifl_event(
        self, builder: EnvelopeBuilder, sample_body: dict[str, Any]
    ) -> None:
        envelope = builder.build("ifl.health.fitbit.hr", sample_body)
        assert envelope["schema_uri"] == "schema://k0/topics/ifl_event.body.json"

    def test_ifl_single_uses_ifl_event(
        self, builder: EnvelopeBuilder, sample_body: dict[str, Any]
    ) -> None:
        envelope = builder.build("ifl.weather", sample_body)
        assert envelope["schema_uri"] == "schema://k0/topics/ifl_event.body.json"

    def test_explicit_schema_uri_override(
        self, builder: EnvelopeBuilder, sample_body: dict[str, Any]
    ) -> None:
        custom_uri = "schema://custom/my_schema.json"
        envelope = builder.build("memory.write", sample_body, schema_uri=custom_uri)
        assert envelope["schema_uri"] == custom_uri


# ===========================================================================
# Idem key determinism
# ===========================================================================


class TestIdemKeyDeterminism:
    """Bridge does NOT produce idem_key; K0 gate owns derivation via HMAC."""

    def test_idem_key_absent_from_envelope(
        self, builder: EnvelopeBuilder, sample_body: dict[str, Any]
    ) -> None:
        """Bridge must not send idem_key so K0 can compute it via HMAC."""
        env = builder.build("memory.write", sample_body)
        assert "idem_key" not in env


# ===========================================================================
# Hash integrity
# ===========================================================================


class TestHashIntegrity:
    """Verify payload_sha256 and envelope_sha256 computations."""

    def test_payload_sha256_matches_body(
        self, builder: EnvelopeBuilder, sample_body: dict[str, Any]
    ) -> None:
        envelope = builder.build("memory.write", sample_body)
        body_json = _canonical_json(sample_body)
        expected = hashlib.sha256(body_json.encode("utf-8")).hexdigest()
        assert envelope["payload_sha256"] == expected

    def test_envelope_sha256_matches_canonical(
        self, builder: EnvelopeBuilder, sample_body: dict[str, Any]
    ) -> None:
        """envelope_sha256 = SHA-256 of canonical envelope (before sig fields)."""
        envelope = builder.build("memory.write", sample_body)
        # Reconstruct the pre-sig envelope: exclude only sig and envelope_sha256.
        # sig_alg and sig_kid are INCLUDED in the canonical hash — same as K0's
        # compute_envelope_sha256 (canonical_envelope(exclude_signature=True)).
        pre_sig = {k: v for k, v in envelope.items() if k not in ("envelope_sha256", "sig")}
        canonical_bytes = _canonical_json(pre_sig).encode("utf-8")
        expected = hashlib.sha256(canonical_bytes).hexdigest()
        assert envelope["envelope_sha256"] == expected

    def test_sig_covers_canonical_envelope(
        self, builder: EnvelopeBuilder, signer: HmacSigning, sample_body: dict[str, Any]
    ) -> None:
        """sig is the signer's signature of canonical envelope bytes (not the sha256 hex)."""
        envelope = builder.build("memory.write", sample_body)
        # The builder signs the canonical envelope (everything except sig+envelope_sha256).
        canonical = {k: v for k, v in envelope.items() if k not in ("sig", "envelope_sha256")}
        canonical_bytes = _canonical_json(canonical).encode("utf-8")
        assert signer.verify(canonical_bytes, envelope["sig"]) is True


# ===========================================================================
# Canonical JSON
# ===========================================================================


class TestCanonicalJson:
    """Verify _canonical_json matches K0's canonical_json format."""

    def test_sorted_keys(self) -> None:
        data = {"z": 1, "a": 2, "m": 3}
        result = _canonical_json(data)
        assert result == '{"a":2,"m":3,"z":1}'

    def test_no_whitespace(self) -> None:
        data = {"key": "value"}
        result = _canonical_json(data)
        assert " " not in result

    def test_minimal_separators(self) -> None:
        data = {"a": [1, 2, 3]}
        result = _canonical_json(data)
        assert result == '{"a":[1,2,3]}'

    def test_unicode_not_escaped(self) -> None:
        data = {"name": "cafe\u0301"}
        result = _canonical_json(data)
        # ensure_ascii=False means unicode chars pass through
        assert "\\u" not in result

    def test_deterministic(self) -> None:
        data = {"b": 2, "a": 1}
        assert _canonical_json(data) == _canonical_json(data)


# ===========================================================================
# build_from_command_envelope
# ===========================================================================


class TestBuildFromCommandEnvelope:
    """Verify the CommandEnvelope convenience builder."""

    def test_delegates_to_build(
        self, builder: EnvelopeBuilder, sample_body: dict[str, Any]
    ) -> None:
        cmd = CommandEnvelope(
            topic="memory.write",
            body=sample_body,
            band="AMBER",
            trace_id="trace-cmd-001",
        )
        envelope = builder.build_from_command_envelope(cmd)
        assert envelope["topic"] == "memory.write"
        assert envelope["band"] == "AMBER"
        assert envelope["cognitive_trace_id"] == "trace-cmd-001"
        assert envelope["body"] == sample_body

    def test_none_optionals(self, builder: EnvelopeBuilder, sample_body: dict[str, Any]) -> None:
        cmd = CommandEnvelope(topic="memory.write", body=sample_body)
        envelope = builder.build_from_command_envelope(cmd)
        assert envelope["band"] == "GREEN"  # default
        assert len(envelope["cognitive_trace_id"]) > 0  # auto-generated


# ===========================================================================
# Ed25519 signer integration
# ===========================================================================


class TestEd25519Integration:
    """Verify EnvelopeBuilder works with Ed25519 signer."""

    def test_envelope_with_ed25519(self, config: BridgeConfig, sample_body: dict[str, Any]) -> None:
        from bridge.core.signing import Ed25519Signing

        seed = os.urandom(32)
        ed_signer = Ed25519Signing(signing_key_bytes=seed, key_id="ed-key-001")
        builder = EnvelopeBuilder(config=config, signer=ed_signer)
        envelope = builder.build("memory.write", sample_body)
        assert envelope["sig_alg"] == "Ed25519SHA512"
        assert envelope["sig_kid"] == "ed-key-001"
        # Builder signs canonical envelope bytes (all fields except sig+envelope_sha256).
        canonical = {k: v for k, v in envelope.items() if k not in ("sig", "envelope_sha256")}
        canonical_bytes = _canonical_json(canonical).encode("utf-8")
        assert ed_signer.verify(canonical_bytes, envelope["sig"]) is True
