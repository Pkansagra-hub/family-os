"""Tests for k0/policy/pep_syscall.py"""

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from k0.policy.pep_syscall import (
    Obligation,
    PolicyConfigurationError,
    PolicyDecision,
    _build_obligations,
    _clear_manifest_fingerprint_cache,
    _deduplicate_obligations,
    create_policy_stamp,
    evaluate_envelope,
    get_manifest_fingerprint,
)


@pytest.fixture
def sample_policy_manifest():
    """Sample policy manifest for testing."""
    return {
        "bands": {
            "GREEN": {
                "max_fanout": 16,
                "max_throughput_pps": 512,
                "max_payload_bytes": 262144,
                "violation_obligation": {"name": "kernel.qos.tighten"}
            },
            "AMBER": {
                "max_fanout": 8,
                "max_throughput_pps": 256,
                "max_payload_bytes": 131072,
                "obligations": [{"name": "kernel.audit.log", "details": {"level": "amber"}}],
                "violation_obligation": {"name": "kernel.qos.tighten", "details": {"band": "AMBER"}}
            },
            "RED": {"deny": True, "obligations": [{"name": "kernel.security.notify", "details": {"severity": "critical"}}]}
        },
        "roles": [
            {
                "name": "coordinator",
                "allow_topics": ["memory.*", "events.*", "policy.*"],
                "max_band": "AMBER",
                "obligations": [{"name": "kernel.audit.trace", "details": {"role": "coordinator"}}]
            },
            {
                "name": "guest",
                "allow_topics": ["ui.*"],
                "max_band": "GREEN",
                "obligations": [{"name": "kernel.redact.enforce", "details": {"scope": "PII"}}]
            }
        ],
        "device_postures": {
            "revoked": {"deny": True, "obligations": [{"name": "kernel.device.reauth", "details": {"reason": "revoked"}}]}
        },
        "sunset_windows": {
            "schema://test/1.0": {
                "warn_after": "2025-12-01T00:00:00Z",
                "deny_after": "2026-01-01T00:00:00Z",
                "obligation": {"name": "kernel.schema.upgrade", "details": {"target": ">=1.1"}}
            }
        },
        "role_violation_obligation": {"name": "kernel.policy.review"},
        "default_obligations": [{"name": "kernel.audit.basic"}]
    }


@pytest.fixture
def temp_policy_file(sample_policy_manifest):
    """Create a temporary policy manifest file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(sample_policy_manifest, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    os.unlink(temp_path)
    _clear_manifest_fingerprint_cache()


@pytest.fixture
def valid_envelope():
    """A valid envelope for testing."""
    return {
        "band": "GREEN",
        "topic": "memory.query",
        "tenant_id": "test-tenant",
        "space_id": "test-space",
        "schema_uri": "schema://test",
        "schema_version": "1.0",
        "ts": "2025-11-23T12:00:00Z",
        "payload_bytes": 1024,
        "policy": {
            "abac": {"roles": ["coordinator"]},
            "caps": {"fanout": 4}
        }
    }


class TestCreatePolicyStamp:
    """Test create_policy_stamp function."""

    def test_create_policy_stamp_allow_basic(self):
        """Test creating policy stamp for allow decision."""
        decision = PolicyDecision(admit=True, obligations=[Obligation("test.obligation")])
        with patch('k0.policy.pep_syscall.get_manifest_fingerprint', return_value=None):
            stamp = create_policy_stamp(decision, "GREEN")

        assert stamp == {
            "band": "GREEN",
            "obligations": ["test.obligation"],
            "decision": "ALLOW"
        }

    def test_create_policy_stamp_deny_with_reason(self):
        """Test creating policy stamp for deny decision with reason."""
        decision = PolicyDecision(admit=False, obligations=[], deny_reason="TEST_DENY")
        with patch('k0.policy.pep_syscall.get_manifest_fingerprint', return_value=None):
            stamp = create_policy_stamp(decision, "RED")

        assert stamp == {
            "band": "RED",
            "obligations": [],
            "decision": "DENY",
            "deny_reason": "TEST_DENY"
        }

    def test_create_policy_stamp_with_visible_to(self):
        """Test creating policy stamp with visible_to."""
        decision = PolicyDecision(admit=True, obligations=[])
        stamp = create_policy_stamp(decision, "AMBER", visible_to=["actor1", "actor2"])

        assert stamp["visible_to"] == ["actor1", "actor2"]

    def test_create_policy_stamp_with_policy_version(self):
        """Test creating policy stamp with explicit policy version."""
        decision = PolicyDecision(admit=True, obligations=[])
        with patch('k0.policy.pep_syscall.get_manifest_fingerprint', return_value=None):
            stamp = create_policy_stamp(decision, "GREEN", policy_version="test-version")

        assert stamp["policy_version"] == "test-version"


class TestEvaluateEnvelope:
    """Test evaluate_envelope function."""

    def test_evaluate_envelope_green_allow(self, temp_policy_file, valid_envelope):
        """Test evaluation allows GREEN band envelope."""
        with patch.dict(os.environ, {"K0_POLICY_MANIFEST_PATH": temp_policy_file}):
            decision = evaluate_envelope(valid_envelope)

        assert decision.admit is True
        assert len(decision.obligations) > 0
        assert decision.deny_reason is None

    def test_evaluate_envelope_red_deny(self, temp_policy_file, valid_envelope):
        """Test evaluation denies RED band envelope."""
        envelope = valid_envelope.copy()
        envelope["band"] = "RED"

        with patch.dict(os.environ, {"K0_POLICY_MANIFEST_PATH": temp_policy_file}):
            decision = evaluate_envelope(envelope)

        assert decision.admit is False
        assert decision.deny_reason == "BAND_BLOCKED"

    def test_evaluate_envelope_fanout_exceeded(self, temp_policy_file, valid_envelope):
        """Test evaluation denies when fanout cap exceeded."""
        envelope = valid_envelope.copy()
        envelope["policy"]["caps"]["fanout"] = 32  # Exceeds GREEN limit of 16

        with patch.dict(os.environ, {"K0_POLICY_MANIFEST_PATH": temp_policy_file}):
            decision = evaluate_envelope(envelope)

        assert decision.admit is False
        assert decision.deny_reason == "CAP_FANOUT_EXCEEDED"

    def test_evaluate_envelope_payload_too_large(self, temp_policy_file, valid_envelope):
        """Test evaluation denies when payload too large."""
        envelope = valid_envelope.copy()
        envelope["payload_bytes"] = 300000  # Exceeds GREEN limit

        with patch.dict(os.environ, {"K0_POLICY_MANIFEST_PATH": temp_policy_file}):
            decision = evaluate_envelope(envelope)

        assert decision.admit is False
        assert decision.deny_reason == "CAP_PAYLOAD_EXCEEDED"

    def test_evaluate_envelope_role_forbidden(self, temp_policy_file, valid_envelope):
        """Test evaluation denies when role not allowed for topic."""
        envelope = valid_envelope.copy()
        envelope["topic"] = "forbidden.topic"
        envelope["policy"]["abac"]["roles"] = ["guest"]  # guest only allows ui.*

        with patch.dict(os.environ, {"K0_POLICY_MANIFEST_PATH": temp_policy_file}):
            decision = evaluate_envelope(envelope)

        assert decision.admit is False
        assert decision.deny_reason == "ROLE_FORBIDDEN"

    def test_evaluate_envelope_device_posture_denied(self, temp_policy_file, valid_envelope):
        """Test evaluation denies revoked device posture."""
        envelope = valid_envelope.copy()
        envelope["policy"]["abac"]["device_posture"] = "revoked"

        with patch.dict(os.environ, {"K0_POLICY_MANIFEST_PATH": temp_policy_file}):
            decision = evaluate_envelope(envelope)

        assert decision.admit is False
        assert decision.deny_reason == "DEVICE_POSTURE_DENIED"

    def test_evaluate_envelope_schema_sunset_deny(self, temp_policy_file, valid_envelope):
        """Test evaluation denies sunset schema after deny_after."""
        envelope = valid_envelope.copy()
        envelope["ts"] = "2026-02-01T00:00:00Z"  # After deny_after

        with patch.dict(os.environ, {"K0_POLICY_MANIFEST_PATH": temp_policy_file}):
            decision = evaluate_envelope(envelope)

        assert decision.admit is False
        assert decision.deny_reason == "SCHEMA_SUNSET"

    def test_evaluate_envelope_missing_manifest(self):
        """Test evaluation fails safely when manifest missing."""
        with patch.dict(os.environ, {"K0_POLICY_MANIFEST_PATH": "/nonexistent/path.json"}):
            decision = evaluate_envelope({"band": "GREEN"})

        assert decision.admit is False
        assert decision.deny_reason == "POLICY_MANIFEST_CORRUPTED"

    def test_evaluate_envelope_invalid_band(self, temp_policy_file):
        """Test evaluation raises error for invalid band."""
        envelope = {"band": "INVALID"}

        with patch.dict(os.environ, {"K0_POLICY_MANIFEST_PATH": temp_policy_file}):
            with pytest.raises(PolicyConfigurationError, match="No policy configured for band 'INVALID'"):
                evaluate_envelope(envelope)

    def test_evaluate_envelope_throughput_exceeded(self, temp_policy_file, valid_envelope):
        """Test evaluation denies when throughput cap exceeded."""
        envelope = valid_envelope.copy()
        envelope["policy"]["caps"]["throughput_pps"] = 600  # Exceeds GREEN limit

        with patch.dict(os.environ, {"K0_POLICY_MANIFEST_PATH": temp_policy_file}):
            decision = evaluate_envelope(envelope)

        assert decision.admit is False
        assert decision.deny_reason == "CAP_THROUGHPUT_EXCEEDED"

    def test_evaluate_envelope_schema_sunset_warn(self, temp_policy_file, valid_envelope):
        """Test evaluation allows but adds obligation for schema sunset warning."""
        envelope = valid_envelope.copy()
        envelope["ts"] = "2025-12-15T00:00:00Z"  # After warn_after, before deny_after

        with patch.dict(os.environ, {"K0_POLICY_MANIFEST_PATH": temp_policy_file}):
            decision = evaluate_envelope(envelope)

        assert decision.admit is True
        obligation_names = [obl.name for obl in decision.obligations]
        assert "kernel.schema.upgrade" in obligation_names

    def test_evaluate_envelope_role_allowed(self, temp_policy_file, valid_envelope):
        """Test evaluation allows when role matches topic pattern."""
        with patch.dict(os.environ, {"K0_POLICY_MANIFEST_PATH": temp_policy_file}):
            decision = evaluate_envelope(valid_envelope)

        assert decision.admit is True

    def test_evaluate_envelope_no_roles(self, temp_policy_file, valid_envelope):
        """Test evaluation denies when no roles provided."""
        envelope = valid_envelope.copy()
        envelope["policy"]["abac"]["roles"] = []

        with patch.dict(os.environ, {"K0_POLICY_MANIFEST_PATH": temp_policy_file}):
            decision = evaluate_envelope(envelope)

        assert decision.admit is False
        assert decision.deny_reason == "ROLE_FORBIDDEN"

    def test_evaluate_envelope_device_posture_allowed(self, temp_policy_file, valid_envelope):
        """Test evaluation allows with valid device posture."""
        envelope = valid_envelope.copy()
        envelope["policy"]["abac"]["device_posture"] = "out_of_date"

        with patch.dict(os.environ, {"K0_POLICY_MANIFEST_PATH": temp_policy_file}):
            decision = evaluate_envelope(envelope)

        assert decision.admit is True  # out_of_date doesn't deny


class TestBuildObligations:
    """Test _build_obligations function."""

    def test_build_obligations_string_list(self):
        """Test building obligations from string list."""
        obligations = _build_obligations(["test.obligation1", "test.obligation2"])
        assert len(obligations) == 2
        assert obligations[0].name == "test.obligation1"
        assert obligations[1].name == "test.obligation2"

    def test_build_obligations_dict_list(self):
        """Test building obligations from dict list."""
        entries = [
            {"name": "test.obligation", "details": {"key": "value"}},
            {"name": "test.obligation2", "details": {"key2": "value2"}}
        ]
        obligations = _build_obligations(entries)
        assert len(obligations) == 2
        assert obligations[0].name == "test.obligation"
        assert obligations[0].details == {"key": "value"}

    def test_build_obligations_with_extra_details(self):
        """Test building obligations with extra details."""
        obligations = _build_obligations(["test.obligation"], {"extra": "detail"})
        assert len(obligations) == 1
        assert obligations[0].details == {"extra": "detail"}


class TestDeduplicateObligations:
    """Test _deduplicate_obligations function."""

    def test_deduplicate_identical_obligations(self):
        """Test deduplicating identical obligations."""
        obligations = [
            Obligation("test", {"a": "1", "b": "2"}),
            Obligation("test", {"a": "1", "b": "2"}),
            Obligation("other", {"c": "3"})
        ]
        deduped = _deduplicate_obligations(obligations)
        assert len(deduped) == 2
        assert deduped[0].name == "test"
        assert deduped[1].name == "other"

    def test_deduplicate_complex_details(self):
        """Test deduplicating obligations with complex details."""
        obligations = [
            Obligation("test", {"list": "[1, 2]", "dict": "{'nested': 'value'}"}),
            Obligation("test", {"list": "[1, 2]", "dict": "{'nested': 'value'}"})
        ]
        deduped = _deduplicate_obligations(obligations)
        assert len(deduped) == 1


class TestGetManifestFingerprint:
    """Test get_manifest_fingerprint function."""

    def test_get_manifest_fingerprint_success(self, temp_policy_file):
        """Test getting manifest fingerprint."""
        with patch.dict(os.environ, {"K0_POLICY_MANIFEST_PATH": temp_policy_file}):
            fingerprint = get_manifest_fingerprint()

        assert fingerprint is not None
        assert len(fingerprint) == 64  # SHA-256 hex length

    def test_get_manifest_fingerprint_missing_file(self):
        """Test getting fingerprint when file missing."""
        with patch.dict(os.environ, {"K0_POLICY_MANIFEST_PATH": "/nonexistent.json"}):
            fingerprint = get_manifest_fingerprint()

        assert fingerprint is None