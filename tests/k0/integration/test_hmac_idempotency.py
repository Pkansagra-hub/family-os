"""Integration tests for HMAC-based idempotency (Gap 2, Issue #009).

Tests cover:
- Dual-mode fallback (HMAC vs BLAKE3)
- Time bucket differentiation (60-second windows)
- Replay window enforcement (60s vs 24h)
- Same envelope + different time buckets → different idem_keys

ADR Reference: Issue #009 - HMAC-Based Idempotency
Epic: 2.2 - Cryptographic Security
"""

import os
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from k0.gate.minimal_gate import MinimalGate
from k0.idem.derive import derive_hmac_idem_key, derive_idem_key
from k0.security import compute_envelope_sha256


@pytest.fixture
def temp_db():
    """Create temporary SQLite database with K0 schema."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row  # Enable dict-style access

        # Create minimal schema for tests
        conn.executescript(
            """
            CREATE TABLE st_devices (
                device_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                space_id TEXT NOT NULL,
                mls_group_id TEXT,
                hmac_secret BLOB,
                provisioned_ts TEXT
            );

            CREATE TABLE st_device_keys (
                device_id TEXT NOT NULL,
                key_version TEXT NOT NULL,
                verify_key TEXT NOT NULL,
                key_state TEXT NOT NULL DEFAULT 'ACTIVE',
                registered_ts TEXT NOT NULL,
                activated_ts TEXT,
                rotated_ts TEXT,
                revoked_ts TEXT,
                grace_expires_ts TEXT,
                revocation_reason TEXT,
                PRIMARY KEY (device_id, key_version)
            );

            CREATE TABLE schema_registry (
                schema_uri TEXT NOT NULL,
                version TEXT NOT NULL,
                sha256 TEXT,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                operator_id TEXT,
                blocked_ts TEXT,
                blocked_reason TEXT,
                unblocked_ts TEXT,
                PRIMARY KEY (schema_uri, version)
            );

            CREATE TABLE st_wal (
                offset INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                space_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                topic TEXT NOT NULL,
                schema_uri TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                envelope_sha256 TEXT UNIQUE,
                ingested_at TEXT,
                clock_skew_ms INTEGER
            );

            CREATE UNIQUE INDEX idx_wal_envelope_sha256 ON st_wal(envelope_sha256)
            WHERE envelope_sha256 IS NOT NULL;
        """
        )
        conn.commit()

        yield db_path
        conn.close()


@pytest.fixture
def provisioned_device_with_hmac_secret(temp_db: Path):
    """Create device with HMAC secret provisioned."""
    conn = sqlite3.connect(str(temp_db))

    # Generate 32-byte HMAC secret
    hmac_secret = os.urandom(32)

    # Insert device with HMAC secret
    conn.execute(
        """
        INSERT INTO st_devices (device_id, tenant_id, space_id, hmac_secret, provisioned_ts)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "test-device",
            "test-tenant",
            "test-space",
            hmac_secret,
            datetime.now(timezone.utc).isoformat(),
        ),
    )

    # Insert ACTIVE key
    conn.execute(
        """
        INSERT INTO st_device_keys (device_id, key_version, verify_key, key_state, registered_ts)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("test-device", "v1", "test-verify-key", "ACTIVE", datetime.now(timezone.utc).isoformat()),
    )

    conn.commit()
    conn.close()

    return {
        "device_id": "test-device",
        "tenant_id": "test-tenant",
        "space_id": "test-space",
        "hmac_secret": hmac_secret,
        "db_path": temp_db,
    }


@pytest.fixture
def legacy_device_without_hmac(temp_db: Path):
    """Create legacy device WITHOUT HMAC secret (pre-V1)."""
    conn = sqlite3.connect(str(temp_db))

    # Insert device WITHOUT hmac_secret (NULL)
    conn.execute(
        """
        INSERT INTO st_devices (device_id, tenant_id, space_id, hmac_secret, provisioned_ts)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "legacy-device",
            "test-tenant",
            "test-space",
            None,
            datetime.now(timezone.utc).isoformat(),
        ),
    )

    # Insert ACTIVE key
    conn.execute(
        """
        INSERT INTO st_device_keys (device_id, key_version, verify_key, key_state, registered_ts)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "legacy-device",
            "v1",
            "test-verify-key",
            "ACTIVE",
            datetime.now(timezone.utc).isoformat(),
        ),
    )

    conn.commit()
    conn.close()

    return {
        "device_id": "legacy-device",
        "tenant_id": "test-tenant",
        "space_id": "test-space",
        "db_path": temp_db,
    }


class TestHMACIdempotencyDualMode:
    """Test dual-mode support: HMAC for provisioned devices, BLAKE3 fallback for legacy."""

    def test_device_with_hmac_secret_uses_hmac_idem_key(self, provisioned_device_with_hmac_secret):
        """Device with hmac_secret → uses HMAC-based idempotency."""
        device_info = provisioned_device_with_hmac_secret
        conn = sqlite3.connect(str(device_info["db_path"]))
        conn.row_factory = sqlite3.Row  # Enable dict-style access

        # Insert test schema
        conn.execute(
            """
            INSERT INTO schema_registry (schema_uri, version, status)
            VALUES (?, ?, ?)
            """,
            ("test://schema", "1.0", "ACTIVE"),
        )
        conn.commit()

        gate = MinimalGate()

        # Create test envelope
        ts = datetime.now(timezone.utc).isoformat()
        envelope = {
            "tenant_id": device_info["tenant_id"],
            "space_id": device_info["space_id"],
            "device_id": device_info["device_id"],
            "actor": "test-actor",
            "topic": "test-topic",
            "schema_uri": "test://schema",
            "schema_version": "1.0",
            "ts": ts,
            "sig": "test-signature",
        }

        # Compute envelope_sha256
        envelope_sha256 = compute_envelope_sha256(envelope)

        # Mock signature verification (bypass actual crypto for this test)
        from unittest.mock import patch

        with patch.object(gate, "_verify_with_rotation_support") as mock_verify:
            from k0.storage.provisioning import DeviceKey

            mock_verify.return_value = DeviceKey(
                device_id=device_info["device_id"],
                key_version="v1",
                verify_key="test-verify-key",
                key_state="ACTIVE",
                registered_ts=datetime.now(timezone.utc).isoformat(),
            )

            outcome = gate.validate(envelope, body=None, connection=conn)

        assert outcome.accepted is True
        assert outcome.idem_key is not None

        # Verify idem_key uses HMAC format (starts with "idem:")
        assert outcome.idem_key.startswith("idem:")

        # Verify it matches HMAC derivation
        expected_idem_key = derive_hmac_idem_key(
            envelope_sha256=envelope_sha256,
            device_id=device_info["device_id"],
            device_secret=device_info["hmac_secret"],
            ts=ts,
        )
        assert outcome.idem_key == expected_idem_key

        conn.close()

    def test_legacy_device_without_hmac_uses_blake3_fallback(self, legacy_device_without_hmac):
        """Legacy device without hmac_secret → falls back to BLAKE3 idempotency."""
        device_info = legacy_device_without_hmac
        conn = sqlite3.connect(str(device_info["db_path"]))
        conn.row_factory = sqlite3.Row  # Enable dict-style access

        # Insert test schema
        conn.execute(
            """
            INSERT INTO schema_registry (schema_uri, version, status)
            VALUES (?, ?, ?)
            """,
            ("test://schema", "1.0", "ACTIVE"),
        )
        conn.commit()

        gate = MinimalGate()

        # Create test envelope
        envelope = {
            "tenant_id": device_info["tenant_id"],
            "space_id": device_info["space_id"],
            "device_id": device_info["device_id"],
            "actor": "test-actor",
            "topic": "test-topic",
            "schema_uri": "test://schema",
            "schema_version": "1.0",
            "ts": datetime.now(timezone.utc).isoformat(),
            "sig": "test-signature",
        }

        # Mock signature verification
        from unittest.mock import patch

        with patch.object(gate, "_verify_with_rotation_support") as mock_verify:
            from k0.storage.provisioning import DeviceKey

            mock_verify.return_value = DeviceKey(
                device_id=device_info["device_id"],
                key_version="v1",
                verify_key="test-verify-key",
                key_state="ACTIVE",
                registered_ts=datetime.now(timezone.utc).isoformat(),
            )

            outcome = gate.validate(envelope, body=None, connection=conn)

        assert outcome.accepted is True
        assert outcome.idem_key is not None

        # Verify idem_key uses BLAKE3 format (64-char hex, no "idem:" prefix)
        assert not outcome.idem_key.startswith("idem:")
        assert len(outcome.idem_key) == 64

        # Verify it matches BLAKE3 derivation (payload_hash=None since no body)
        expected_idem_key = derive_idem_key(envelope, payload_hash=None)
        assert outcome.idem_key == expected_idem_key

        conn.close()


class TestHMACTimeBucketDifferentiation:
    """Test that same envelope + different time buckets → different idem_keys."""

    def test_same_envelope_different_60s_buckets_different_idem_keys(
        self, provisioned_device_with_hmac_secret
    ):
        """Same envelope + 61 seconds apart → different idem_keys (different buckets)."""
        device_info = provisioned_device_with_hmac_secret

        # Timestamp 1: now
        ts1 = datetime.now(timezone.utc)

        # Timestamp 2: 61 seconds later (crosses 60s bucket boundary)
        ts2 = ts1 + timedelta(seconds=61)

        envelope_sha256 = "f" * 64  # Arbitrary test hash

        idem_key1 = derive_hmac_idem_key(
            envelope_sha256=envelope_sha256,
            device_id=device_info["device_id"],
            device_secret=device_info["hmac_secret"],
            ts=ts1.isoformat(),
        )

        idem_key2 = derive_hmac_idem_key(
            envelope_sha256=envelope_sha256,
            device_id=device_info["device_id"],
            device_secret=device_info["hmac_secret"],
            ts=ts2.isoformat(),
        )

        # Different time buckets → different idem_keys
        assert idem_key1 != idem_key2

    def test_same_envelope_within_60s_bucket_same_idem_key(
        self, provisioned_device_with_hmac_secret
    ):
        """Same envelope + 30 seconds apart (same bucket) → same idem_key."""
        device_info = provisioned_device_with_hmac_secret

        # Timestamp 1: Use a fixed bucket boundary (e.g., 1234560 seconds)
        # This ensures both timestamps land in same 60s bucket
        ts1_epoch = 1234560  # 60s bucket: 20576 (1234560 // 60)
        ts1 = datetime.fromtimestamp(ts1_epoch, tz=timezone.utc)

        # Timestamp 2: 30 seconds later (still within same 60s bucket 20576)
        ts2_epoch = ts1_epoch + 30
        ts2 = datetime.fromtimestamp(ts2_epoch, tz=timezone.utc)

        # Verify both are in same 60s bucket
        bucket1 = ts1_epoch // 60
        bucket2 = ts2_epoch // 60
        assert bucket1 == bucket2, f"Timestamps must be in same bucket: {bucket1} vs {bucket2}"

        envelope_sha256 = "f" * 64

        idem_key1 = derive_hmac_idem_key(
            envelope_sha256=envelope_sha256,
            device_id=device_info["device_id"],
            device_secret=device_info["hmac_secret"],
            ts=ts1.isoformat(),
        )

        idem_key2 = derive_hmac_idem_key(
            envelope_sha256=envelope_sha256,
            device_id=device_info["device_id"],
            device_secret=device_info["hmac_secret"],
            ts=ts2.isoformat(),
        )

        # Same time bucket → same idem_key (replay window allows)
        assert idem_key1 == idem_key2


class TestHMACReplayWindowEnforcement:
    """Test 60-second replay window vs 24-hour BLAKE3 window."""

    def test_hmac_replay_window_60_seconds(self, provisioned_device_with_hmac_secret):
        """HMAC idempotency enforces 60-second replay window."""
        device_info = provisioned_device_with_hmac_secret

        # Generate idem_key for now
        ts_now = datetime.now(timezone.utc)
        envelope_sha256 = "f" * 64

        idem_key_now = derive_hmac_idem_key(
            envelope_sha256=envelope_sha256,
            device_id=device_info["device_id"],
            device_secret=device_info["hmac_secret"],
            ts=ts_now.isoformat(),
        )

        # Generate idem_key 5 minutes later (should be different bucket)
        ts_5min_later = ts_now + timedelta(minutes=5)
        idem_key_5min = derive_hmac_idem_key(
            envelope_sha256=envelope_sha256,
            device_id=device_info["device_id"],
            device_secret=device_info["hmac_secret"],
            ts=ts_5min_later.isoformat(),
        )

        # Different buckets → replay prevented after 60s
        assert idem_key_now != idem_key_5min

    def test_blake3_replay_window_no_time_component(self, legacy_device_without_hmac):
        """BLAKE3 idempotency has no time component (24h replay window)."""
        # BLAKE3 derives from envelope fields only (no time bucket)
        envelope = {
            "tenant_id": "test-tenant",
            "space_id": "test-space",
            "actor": "test-actor",
            "topic": "test-topic",
            "schema_uri": "test://schema",
            "schema_version": "1.0",
        }

        # Same envelope → same idem_key regardless of time
        idem_key1 = derive_idem_key(envelope)
        time.sleep(0.1)  # Simulate time passing
        idem_key2 = derive_idem_key(envelope)

        # BLAKE3 has no time component → always same key
        assert idem_key1 == idem_key2


class TestHMACCryptographicProperties:
    """Test HMAC-SHA256 cryptographic properties."""

    def test_hmac_requires_device_secret(self, provisioned_device_with_hmac_secret):
        """HMAC idem_key requires device_secret (non-predictable)."""
        device_info = provisioned_device_with_hmac_secret

        ts = datetime.now(timezone.utc).isoformat()
        envelope_sha256 = "f" * 64

        # Correct secret
        idem_key_correct = derive_hmac_idem_key(
            envelope_sha256=envelope_sha256,
            device_id=device_info["device_id"],
            device_secret=device_info["hmac_secret"],
            ts=ts,
        )

        # Wrong secret
        wrong_secret = os.urandom(32)
        idem_key_wrong = derive_hmac_idem_key(
            envelope_sha256=envelope_sha256,
            device_id=device_info["device_id"],
            device_secret=wrong_secret,
            ts=ts,
        )

        # Different secrets → different idem_keys
        assert idem_key_correct != idem_key_wrong

    def test_hmac_format_idem_prefix_32char_hex(self, provisioned_device_with_hmac_secret):
        """HMAC idem_key format: idem:<32-char hex>."""
        device_info = provisioned_device_with_hmac_secret

        ts = datetime.now(timezone.utc).isoformat()
        envelope_sha256 = "f" * 64

        idem_key = derive_hmac_idem_key(
            envelope_sha256=envelope_sha256,
            device_id=device_info["device_id"],
            device_secret=device_info["hmac_secret"],
            ts=ts,
        )

        # Format: idem:<32-char hex>
        assert idem_key.startswith("idem:")
        assert len(idem_key) == len("idem:") + 32

        # Verify hex characters only after prefix
        hex_part = idem_key[len("idem:") :]
        assert all(c in "0123456789abcdef" for c in hex_part)


class TestHMACEndToEndIntegration:
    """End-to-end tests for HMAC idempotency in MinimalGate."""

    def test_envelope_with_hmac_device_rejected_on_replay(
        self, provisioned_device_with_hmac_secret
    ):
        """Envelope submitted twice within 60s → second rejected (replay)."""
        device_info = provisioned_device_with_hmac_secret
        conn = sqlite3.connect(str(device_info["db_path"]))
        conn.row_factory = sqlite3.Row  # Enable dict-style access

        # Insert test schema
        conn.execute(
            """
            INSERT INTO schema_registry (schema_uri, version, status)
            VALUES (?, ?, ?)
            """,
            ("test://schema", "1.0", "ACTIVE"),
        )
        conn.commit()

        gate = MinimalGate()

        ts = datetime.now(timezone.utc).isoformat()
        envelope = {
            "tenant_id": device_info["tenant_id"],
            "space_id": device_info["space_id"],
            "device_id": device_info["device_id"],
            "actor": "test-actor",
            "topic": "test-topic",
            "schema_uri": "test://schema",
            "schema_version": "1.0",
            "ts": ts,
            "sig": "test-signature",
        }

        # Compute envelope_sha256
        envelope_sha256 = compute_envelope_sha256(envelope)

        # Mock signature verification
        from unittest.mock import patch

        with patch.object(gate, "_verify_with_rotation_support") as mock_verify:
            from k0.storage.provisioning import DeviceKey

            mock_verify.return_value = DeviceKey(
                device_id=device_info["device_id"],
                key_version="v1",
                verify_key="test-verify-key",
                key_state="ACTIVE",
                registered_ts=datetime.now(timezone.utc).isoformat(),
            )

            # First submission: accepted
            outcome1 = gate.validate(envelope, body=None, connection=conn)
            assert outcome1.accepted is True

            # Insert into WAL to simulate replay detection
            conn.execute(
                """
                INSERT INTO st_wal (
                    tenant_id, space_id, device_id, topic,
                    schema_uri, schema_version, envelope_sha256
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_info["tenant_id"],
                    device_info["space_id"],
                    device_info["device_id"],
                    "test-topic",
                    "test://schema",
                    "1.0",
                    envelope_sha256,
                ),
            )
            conn.commit()

            # Second submission (fresh envelope copy with same content): rejected as replay
            envelope2 = {
                "tenant_id": device_info["tenant_id"],
                "space_id": device_info["space_id"],
                "device_id": device_info["device_id"],
                "actor": "test-actor",
                "topic": "test-topic",
                "schema_uri": "test://schema",
                "schema_version": "1.0",
                "ts": ts,
                "sig": "test-signature",
            }
            outcome2 = gate.validate(envelope2, body=None, connection=conn)
            assert outcome2.accepted is False
            assert outcome2.reason == "ENVELOPE_REPLAY_DETECTED"

        conn.close()

    def test_different_devices_same_envelope_different_idem_keys(
        self, provisioned_device_with_hmac_secret, temp_db: Path
    ):
        """Same envelope from different devices → different idem_keys."""
        device1_info = provisioned_device_with_hmac_secret

        # Create second device with different HMAC secret
        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row  # Enable dict-style access
        hmac_secret2 = os.urandom(32)
        conn.execute(
            """
            INSERT INTO st_devices (device_id, tenant_id, space_id, hmac_secret)
            VALUES (?, ?, ?, ?)
            """,
            ("device2", "test-tenant", "test-space", hmac_secret2),
        )
        conn.commit()

        ts = datetime.now(timezone.utc).isoformat()
        envelope_sha256 = "f" * 64

        idem_key1 = derive_hmac_idem_key(
            envelope_sha256=envelope_sha256,
            device_id=device1_info["device_id"],
            device_secret=device1_info["hmac_secret"],
            ts=ts,
        )

        idem_key2 = derive_hmac_idem_key(
            envelope_sha256=envelope_sha256,
            device_id="device2",
            device_secret=hmac_secret2,
            ts=ts,
        )

        # Different devices → different idem_keys (device_id + secret in HMAC)
        assert idem_key1 != idem_key2

        conn.close()
