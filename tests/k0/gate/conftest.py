"""
Test fixtures for MinimalGate validation tests.

Provides complete test envelopes, provisioning data, schema records,
and cryptographic materials for comprehensive validate() testing.
"""

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from k0.gate.minimal_gate import MinimalGate
from k0.obs import MetricsExporter, ObservabilityEmitter


@pytest.fixture
def in_memory_db():
    """In-memory SQLite database for isolated testing."""
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def provisioning_ledger(in_memory_db):
    """Provisioning ledger with test data."""
    from unittest.mock import MagicMock

    from k0.storage.provisioning import DeviceKey, ProvisionedDevice

    # Create a mock ledger that returns proper device records
    ledger = MagicMock()

    # Create actual ProvisionedDevice instance
    device_record = ProvisionedDevice(
        device_id="test-device-001",
        tenant_id="test-tenant",
        space_id="test-space",
        mls_group_id="mls-group-123",
        provisioned_ts="2025-01-15T10:00:00Z"
    )

    ledger.lookup.return_value = device_record

    # Create actual DeviceKey instance
    key_record = DeviceKey(
        device_id="test-device-001",
        key_version="v1",
        key_state="ACTIVE",
        verify_key="test_verify_key_pem_data",
        registered_ts="2025-01-15T10:00:00Z",
        activated_ts="2025-01-15T10:00:00Z",
        rotated_ts=None,
        revoked_ts=None,
        grace_expires_ts=None,
        revocation_reason=None,
    )

    ledger.get_keys.return_value = [key_record]

    return ledger


@pytest.fixture
def schema_registry(in_memory_db):
    """Schema registry with test schemas."""
    from k0.gate.schema_registry import SchemaRecord

    # Create a mock registry that returns proper schema records
    registry = MagicMock()

    # Create actual SchemaRecord instances
    active_schema = SchemaRecord(
        uri="https://example.com/schemas/test",
        version="1.0.0",
        sha256="a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
        status="ACTIVE",
        operator_id="operator-123",
        blocked_ts=None,
        blocked_reason=None,
        unblocked_ts=None,
    )

    deprecated_schema = SchemaRecord(
        uri="https://example.com/schemas/test",
        version="2.0.0",
        sha256="b665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
        status="DEPRECATED",
        operator_id="operator-123",
        blocked_ts=None,
        blocked_reason=None,
        unblocked_ts=None,
    )

    blocked_schema = SchemaRecord(
        uri="https://example.com/schemas/blocked",
        version="1.0.0",
        sha256="c665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
        status="BLOCKED",
        operator_id="operator-123",
        blocked_ts="2025-01-15T12:00:00Z",
        blocked_reason="Test block",
        unblocked_ts=None,
    )

    def mock_get_schema(uri, version, connection=None):
        if uri == "https://example.com/schemas/test":
            if version == "1.0.0":
                return active_schema
            elif version == "2.0.0":
                return deprecated_schema
        elif uri == "https://example.com/schemas/blocked" and version == "1.0.0":
            return blocked_schema
        raise KeyError(f"Schema {uri}@{version} not found")

    registry.get.side_effect = mock_get_schema

    return registry


@pytest.fixture
def metrics_exporter():
    """Mock metrics exporter for testing."""
    return MetricsExporter()


@pytest.fixture
def observability_emitter():
    """Mock observability emitter for testing."""
    return ObservabilityEmitter()


@pytest.fixture
def gate_with_fixtures(provisioning_ledger, schema_registry, metrics_exporter, observability_emitter):
    """MinimalGate instance with all dependencies configured."""
    return MinimalGate(
        registry=schema_registry,
        provisioning=provisioning_ledger,
        metrics=metrics_exporter,
        observability=observability_emitter,
    )


@pytest.fixture
def valid_envelope(valid_body):
    """Complete valid envelope for testing."""
    # Use current time minus 1 minute to avoid clock skew
    current_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    # Compute actual payload hash
    payload_hash = hashlib.sha256(valid_body).hexdigest()
    return {
        "ver": "1.0",
        "tenant_id": "test-tenant",
        "space_id": "test-space",
        "device_id": "test-device-001",
        "actor": "test-actor",
        "topic": "test.topic",
        "schema_uri": "https://example.com/schemas/test",
        "schema_version": "1.0.0",
        "ts": current_time.isoformat().replace('+00:00', 'Z'),
        "payload_sha256": payload_hash,
        "sig": "test_signature_b64",
        "band": "GREEN",
    }


@pytest.fixture
def valid_body():
    """Valid body content for envelope."""
    return b'{"data": "test payload content"}'


@pytest.fixture
def envelope_with_location(valid_body):
    """Envelope with location data for AMBER/RED band testing."""
    current_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    payload_hash = hashlib.sha256(valid_body).hexdigest()
    return {
        "ver": "1.0",
        "tenant_id": "test-tenant",
        "space_id": "test-space",
        "device_id": "test-device-001",
        "actor": "test-actor",
        "topic": "test.topic",
        "schema_uri": "https://example.com/schemas/test",
        "schema_version": "1.0.0",
        "ts": current_time.isoformat().replace('+00:00', 'Z'),
        "payload_sha256": payload_hash,
        "sig": "test_signature_b64",
        "band": "AMBER",
        "location": {"lat": 37.7749, "lon": -122.4194},
    }


@pytest.fixture
def envelope_with_policy_stamp(valid_body):
    """Envelope with policy stamp for testing."""
    current_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    payload_hash = hashlib.sha256(valid_body).hexdigest()
    return {
        "ver": "1.0",
        "tenant_id": "test-tenant",
        "space_id": "test-space",
        "device_id": "test-device-001",
        "actor": "test-actor",
        "topic": "test.topic",
        "schema_uri": "https://example.com/schemas/test",
        "schema_version": "1.0.0",
        "ts": current_time.isoformat().replace('+00:00', 'Z'),
        "payload_sha256": payload_hash,
        "sig": "test_signature_b64",
        "band": "GREEN",
        "policy_stamp": {
            "band": "GREEN",
            "obligations": [],
            "decision": "ALLOW",
        },
    }


@pytest.fixture
def invalid_envelope_missing_bindings(valid_body):
    """Envelope missing required bindings."""
    current_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    payload_hash = hashlib.sha256(valid_body).hexdigest()
    return {
        "ver": "1.0",
        # Missing tenant_id, space_id, device_id
        "actor": "test-actor",
        "topic": "test.topic",
        "schema_uri": "https://example.com/schemas/test",
        "schema_version": "1.0.0",
        "ts": current_time.isoformat().replace('+00:00', 'Z'),
        "payload_sha256": payload_hash,
        "sig": "test_signature_b64",
    }


@pytest.fixture
def invalid_envelope_missing_bindings_body():
    """Body for missing bindings test."""
    return b'{"data": "test"}'


@pytest.fixture
def invalid_envelope_clock_skew():
    """Envelope with excessive clock skew."""
    # 10 minutes in the future (exceeds 5 minute default tolerance)
    future_ts = datetime.now(timezone.utc) + timedelta(minutes=10)
    return {
        "ver": "1.0",
        "tenant_id": "test-tenant",
        "space_id": "test-space",
        "device_id": "test-device-001",
        "actor": "test-actor",
        "topic": "test.topic",
        "schema_uri": "https://example.com/schemas/test",
        "schema_version": "1.0.0",
        "ts": future_ts.isoformat(),
        "payload_sha256": "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
        "sig": "test_signature_b64",
    }


@pytest.fixture
def invalid_envelope_clock_skew_body():
    """Body for clock skew test."""
    return b'{"data": "test"}'


@pytest.fixture
def invalid_envelope_no_body():
    """Envelope with no body (required for K0)."""
    current_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    # For no body test, we need a hash that doesn't match any body
    return {
        "ver": "1.0",
        "tenant_id": "test-tenant",
        "space_id": "test-space",
        "device_id": "test-device-001",
        "actor": "test-actor",
        "topic": "test.topic",
        "schema_uri": "https://example.com/schemas/test",
        "schema_version": "1.0.0",
        "ts": current_time.isoformat().replace('+00:00', 'Z'),
        "payload_sha256": "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
        "sig": "test_signature_b64",
    }


@pytest.fixture
def invalid_envelope_oversized(valid_body):
    """Envelope exceeding size limits."""
    current_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    payload_hash = hashlib.sha256(valid_body).hexdigest()
    return {
        "ver": "1.0",
        "tenant_id": "test-tenant",
        "space_id": "test-space",
        "device_id": "test-device-001",
        "actor": "test-actor",
        "topic": "test.topic",
        "schema_uri": "https://example.com/schemas/test",
        "schema_version": "1.0.0",
        "ts": current_time.isoformat().replace('+00:00', 'Z'),
        "payload_sha256": payload_hash,
        "sig": "test_signature_b64",
        "large_field": "x" * 100000,  # Make envelope oversized
    }


@pytest.fixture
def invalid_envelope_bad_hash():
    """Envelope with invalid payload hash."""
    current_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    return {
        "ver": "1.0",
        "tenant_id": "test-tenant",
        "space_id": "test-space",
        "device_id": "test-device-001",
        "actor": "test-actor",
        "topic": "test.topic",
        "schema_uri": "https://example.com/schemas/test",
        "schema_version": "1.0.0",
        "ts": current_time.isoformat().replace('+00:00', 'Z'),
        "payload_sha256": "invalid_hash_not_64_chars",
        "sig": "test_signature_b64",
    }


@pytest.fixture
def invalid_envelope_missing_sig(valid_body):
    """Envelope missing signature."""
    current_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    payload_hash = hashlib.sha256(valid_body).hexdigest()
    return {
        "ver": "1.0",
        "tenant_id": "test-tenant",
        "space_id": "test-space",
        "device_id": "test-device-001",
        "actor": "test-actor",
        "topic": "test.topic",
        "schema_uri": "https://example.com/schemas/test",
        "schema_version": "1.0.0",
        "ts": current_time.isoformat().replace('+00:00', 'Z'),
        "payload_sha256": payload_hash,
        # Missing sig field
    }


@pytest.fixture
def invalid_envelope_replay(valid_body):
    """Envelope that would be detected as replay."""
    current_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    payload_hash = hashlib.sha256(valid_body).hexdigest()
    return {
        "ver": "1.0",
        "tenant_id": "test-tenant",
        "space_id": "test-space",
        "device_id": "test-device-001",
        "schema_uri": "https://example.com/schemas/test",
        "schema_version": "1.0.0",
        "ts": current_time.isoformat().replace('+00:00', 'Z'),
        "payload_sha256": payload_hash,
        "sig": "test_signature_b64",
    }


@pytest.fixture
def invalid_envelope_bad_schema(valid_body):
    """Envelope with blocked schema."""
    current_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    payload_hash = hashlib.sha256(valid_body).hexdigest()
    return {
        "ver": "1.0",
        "tenant_id": "test-tenant",
        "space_id": "test-space",
        "device_id": "test-device-001",
        "schema_uri": "https://example.com/schemas/blocked",
        "schema_version": "1.0.0",
        "ts": current_time.isoformat().replace('+00:00', 'Z'),
        "payload_sha256": payload_hash,
        "sig": "test_signature_b64",
    }


@pytest.fixture
def invalid_envelope_location_missing(valid_body):
    """AMBER band envelope missing required location."""
    current_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    payload_hash = hashlib.sha256(valid_body).hexdigest()
    return {
        "ver": "1.0",
        "tenant_id": "test-tenant",
        "space_id": "test-space",
        "device_id": "test-device-001",
        "schema_uri": "https://example.com/schemas/test",
        "schema_version": "1.0.0",
        "ts": current_time.isoformat().replace('+00:00', 'Z'),
        "payload_sha256": payload_hash,
        "sig": "test_signature_b64",
        "band": "AMBER",
        # Missing location field
    }


@pytest.fixture
def invalid_envelope_bad_policy_stamp(valid_body):
    """Envelope with invalid policy stamp."""
    current_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    payload_hash = hashlib.sha256(valid_body).hexdigest()
    return {
        "ver": "1.0",
        "tenant_id": "test-tenant",
        "space_id": "test-space",
        "device_id": "test-device-001",
        "schema_uri": "https://example.com/schemas/test",
        "schema_version": "1.0.0",
        "ts": current_time.isoformat().replace('+00:00', 'Z'),
        "payload_sha256": payload_hash,
        "sig": "test_signature_b64",
        "band": "GREEN",
        "policy_stamp": "not_a_dict",  # Invalid - should be dict
    }
