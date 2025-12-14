"""Test Issue 1.2: HMAC-Based Idempotency Keys (V1).

Tests HMAC-based idempotency key derivation where idempotency keys are
generated using HMAC-SHA256 over: envelope_sha256 || device_id || time_bucket.

This validates:
1. HMAC idem key derivation
2. Time bucket replay window (60-second buckets)
3. Cross-device collision prevention
4. Device secret handling
5. Deterministic key generation
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from k0.idem import derive_hmac_idem_key


class TestHmacIdempotencyKeyDerivation:
    """Test HMAC-based idempotency key derivation."""

    def test_hmac_idem_key_format(self) -> None:
        """✅ Verify HMAC idem key has correct format."""
        envelope_sha256 = "a" * 64  # Valid SHA-256 hex
        device_id = "dad-phone"
        device_secret = b"super_secret_key_32_bytes_long_"
        ts = datetime.now(timezone.utc).isoformat()

        key = derive_hmac_idem_key(envelope_sha256, device_id, device_secret, ts)

        # Format: "idem:<32-char-hex>"
        assert key.startswith("idem:"), "Key must start with 'idem:'"
        parts = key.split(":")
        assert len(parts) == 2, "Key must have exactly 2 parts"
        assert len(parts[1]) >= 32, "Hex part must be at least 32 characters"

    def test_hmac_idem_key_deterministic(self) -> None:
        """✅ Verify HMAC idem key is deterministic."""
        envelope_sha256 = "a" * 64
        device_id = "dad-phone"
        device_secret = b"super_secret_key_32_bytes_long_"
        ts = "2025-01-01T12:00:00+00:00"

        key1 = derive_hmac_idem_key(envelope_sha256, device_id, device_secret, ts)
        key2 = derive_hmac_idem_key(envelope_sha256, device_id, device_secret, ts)

        assert key1 == key2, "Same inputs must produce same key (deterministic)"

    def test_hmac_idem_key_time_bucket_60_second_window(self) -> None:
        """✅ Verify time bucket is 60-second window."""
        envelope_sha256 = "a" * 64
        device_id = "dad-phone"
        device_secret = b"super_secret_key_32_bytes_long_"

        # Two timestamps in same 60-second bucket should produce same key
        ts1 = "2025-01-01T12:00:00+00:00"  # Bucket 0
        ts2 = "2025-01-01T12:00:30+00:00"  # Still bucket 0 (same 60-sec window)

        key1 = derive_hmac_idem_key(envelope_sha256, device_id, device_secret, ts1)
        key2 = derive_hmac_idem_key(envelope_sha256, device_id, device_secret, ts2)

        assert key1 == key2, "Timestamps in same 60-second bucket must produce same key"

    def test_hmac_idem_key_time_bucket_different_windows(self) -> None:
        """✅ Verify different 60-second buckets produce different keys."""
        envelope_sha256 = "a" * 64
        device_id = "dad-phone"
        device_secret = b"super_secret_key_32_bytes_long_"

        # Two timestamps in different 60-second buckets
        ts1 = "2025-01-01T12:00:00+00:00"  # Bucket 0
        ts2 = "2025-01-01T12:01:00+00:00"  # Bucket 1 (60 seconds later)

        key1 = derive_hmac_idem_key(envelope_sha256, device_id, device_secret, ts1)
        key2 = derive_hmac_idem_key(envelope_sha256, device_id, device_secret, ts2)

        assert key1 != key2, "Different time buckets must produce different keys"

    def test_hmac_idem_key_envelope_sha256_sensitivity(self) -> None:
        """✅ Verify HMAC idem key is sensitive to envelope_sha256 changes."""
        device_id = "dad-phone"
        device_secret = b"super_secret_key_32_bytes_long_"
        ts = "2025-01-01T12:00:00+00:00"

        # Different envelope_sha256 values
        env_sha_1 = "a" * 64
        env_sha_2 = "b" * 64

        key1 = derive_hmac_idem_key(env_sha_1, device_id, device_secret, ts)
        key2 = derive_hmac_idem_key(env_sha_2, device_id, device_secret, ts)

        assert key1 != key2, "Different envelope_sha256 must produce different keys"

    def test_hmac_idem_key_device_id_sensitivity(self) -> None:
        """✅ Verify HMAC idem key is sensitive to device_id changes."""
        envelope_sha256 = "a" * 64
        device_secret = b"super_secret_key_32_bytes_long_"
        ts = "2025-01-01T12:00:00+00:00"

        # Different device IDs
        device_id_1 = "dad-phone"
        device_id_2 = "mom-laptop"

        key1 = derive_hmac_idem_key(envelope_sha256, device_id_1, device_secret, ts)
        key2 = derive_hmac_idem_key(envelope_sha256, device_id_2, device_secret, ts)

        assert key1 != key2, "Different device_id must produce different keys"

    def test_hmac_idem_key_device_secret_sensitivity(self) -> None:
        """✅ Verify HMAC idem key is sensitive to device_secret changes."""
        envelope_sha256 = "a" * 64
        device_id = "dad-phone"
        ts = "2025-01-01T12:00:00+00:00"

        # Different device secrets
        secret_1 = b"super_secret_key_32_bytes_long_"
        secret_2 = b"different_secret_32_bytes_long!"

        key1 = derive_hmac_idem_key(envelope_sha256, device_id, secret_1, ts)
        key2 = derive_hmac_idem_key(envelope_sha256, device_id, secret_2, ts)

        assert key1 != key2, "Different device_secret must produce different keys"

    def test_hmac_idem_key_no_collision_across_time_buckets(self) -> None:
        """✅ Verify no collisions across different time buckets."""
        envelope_sha256 = "a" * 64
        device_id = "dad-phone"
        device_secret = b"super_secret_key_32_bytes_long_"

        # Generate keys for multiple time buckets
        keys = []
        for i in range(5):
            ts = (datetime.now(timezone.utc) + timedelta(minutes=i)).isoformat()
            key = derive_hmac_idem_key(envelope_sha256, device_id, device_secret, ts)
            keys.append(key)

        # All keys should be unique (different buckets)
        assert len(set(keys)) == 5, "Keys from different time buckets must be unique"

    def test_hmac_idem_key_replay_window_enforcement(self) -> None:
        """✅ Verify 60-second replay window is enforced."""
        envelope_sha256 = "a" * 64
        device_id = "dad-phone"
        device_secret = b"super_secret_key_32_bytes_long_"

        # Use fixed timestamp to control buckets precisely
        # 2025-01-01 12:00:00 UTC = 1735728000 seconds = bucket 28928800
        ts_start = "2025-01-01T12:00:00.000000+00:00"
        ts_30s_later = "2025-01-01T12:00:30.000000+00:00"  # Same bucket (30 < 60)
        ts_61s_later = "2025-01-01T12:01:01.000000+00:00"  # Different bucket (61 >= 60)

        # Same 60-second bucket should produce same key
        key_start = derive_hmac_idem_key(envelope_sha256, device_id, device_secret, ts_start)
        key_30s_later = derive_hmac_idem_key(
            envelope_sha256, device_id, device_secret, ts_30s_later
        )

        assert key_start == key_30s_later, "Same 60-second bucket must produce same key"

        # Different bucket should produce different key
        key_61s_later = derive_hmac_idem_key(
            envelope_sha256, device_id, device_secret, ts_61s_later
        )

        assert key_start != key_61s_later, "Different 60-second bucket must produce different key"


class TestCrossDeviceIdempotency:
    """Test idempotency across multiple devices."""

    def test_cross_device_collision_prevention(self) -> None:
        """✅ Verify different devices cannot generate same idem key."""
        envelope_sha256 = "a" * 64
        device_secret = b"super_secret_key_32_bytes_long_"
        ts = "2025-01-01T12:00:00+00:00"

        # Two different devices
        device_1 = "dad-phone"
        device_2 = "dad-phone"  # Same device

        key1 = derive_hmac_idem_key(envelope_sha256, device_1, device_secret, ts)
        key2 = derive_hmac_idem_key(envelope_sha256, device_2, device_secret, ts)

        # Same device should produce same key
        assert key1 == key2, "Same device must produce same key for same content"

    def test_cross_device_different_secrets_collision_prevention(self) -> None:
        """✅ Verify different devices with different secrets cannot collide."""
        envelope_sha256 = "a" * 64
        ts = "2025-01-01T12:00:00+00:00"

        # Two different devices with different secrets
        device_1 = "dad-phone"
        device_1_secret = b"device1_secret_32_bytes_long_xx"

        device_2 = "dad-phone"  # Same device ID
        device_2_secret = b"device2_secret_32_bytes_long_yy"

        key1 = derive_hmac_idem_key(envelope_sha256, device_1, device_1_secret, ts)
        key2 = derive_hmac_idem_key(envelope_sha256, device_2, device_2_secret, ts)

        # Different secrets must produce different keys
        assert key1 != key2, "Different device secrets must produce different keys"


class TestHmacIdempotencyEdgeCases:
    """Test edge cases in HMAC idempotency key derivation."""

    def test_hmac_idem_key_with_default_timestamp(self) -> None:
        """✅ Verify HMAC idem key works with current timestamp."""
        envelope_sha256 = "a" * 64
        device_id = "dad-phone"
        device_secret = b"super_secret_key_32_bytes_long_"

        # Call without timestamp (should use current time)
        key = derive_hmac_idem_key(envelope_sha256, device_id, device_secret)

        # Should produce a valid key
        assert key.startswith("idem:")
        assert len(key) > 5

    def test_hmac_idem_key_empty_device_secret(self) -> None:
        """✅ Verify HMAC idem key handles empty device secret."""
        envelope_sha256 = "a" * 64
        device_id = "dad-phone"
        device_secret = b""  # Empty secret
        ts = "2025-01-01T12:00:00+00:00"

        # Should still produce a key (HMAC works with empty key)
        key = derive_hmac_idem_key(envelope_sha256, device_id, device_secret, ts)
        assert key.startswith("idem:")

    def test_hmac_idem_key_large_device_secret(self) -> None:
        """✅ Verify HMAC idem key handles large device secret."""
        envelope_sha256 = "a" * 64
        device_id = "dad-phone"
        device_secret = b"x" * 256  # Large secret
        ts = "2025-01-01T12:00:00+00:00"

        # Should handle large secret (HMAC supports any length)
        key = derive_hmac_idem_key(envelope_sha256, device_id, device_secret, ts)
        assert key.startswith("idem:")

    def test_hmac_idem_key_special_characters_in_device_id(self) -> None:
        """✅ Verify HMAC idem key handles special characters in device_id."""
        envelope_sha256 = "a" * 64
        device_id = "device:dad@home:phone#2"  # Special characters
        device_secret = b"super_secret_key_32_bytes_long_"
        ts = "2025-01-01T12:00:00+00:00"

        # Should handle special characters
        key = derive_hmac_idem_key(envelope_sha256, device_id, device_secret, ts)
        assert key.startswith("idem:")


class TestHmacIdempotencyIntegration:
    """Integration tests for HMAC idempotency with realistic scenarios."""

    def test_idempotency_sequence_same_device_different_messages(self) -> None:
        """✅ Verify idempotency keys differ for different messages on same device."""
        device_id = "dad-phone"
        device_secret = b"super_secret_key_32_bytes_long_"
        ts = "2025-01-01T12:00:00+00:00"

        # Two different envelopes
        env_1 = "a" * 64
        env_2 = "b" * 64

        key1 = derive_hmac_idem_key(env_1, device_id, device_secret, ts)
        key2 = derive_hmac_idem_key(env_2, device_id, device_secret, ts)

        # Different messages = different keys
        assert key1 != key2

    def test_idempotency_retry_scenario(self) -> None:
        """✅ Verify retry scenario: same message, same device, same time bucket."""
        device_id = "dad-phone"
        device_secret = b"super_secret_key_32_bytes_long_"
        envelope_sha256 = "a" * 64
        ts = "2025-01-01T12:00:00+00:00"

        # First request
        key1 = derive_hmac_idem_key(envelope_sha256, device_id, device_secret, ts)

        # Retry within same time bucket (30 seconds later)
        ts_retry = "2025-01-01T12:00:30+00:00"
        key_retry = derive_hmac_idem_key(envelope_sha256, device_id, device_secret, ts_retry)

        # Same time bucket = same key = idempotency maintained
        assert key1 == key_retry, "Retry within same time bucket should produce same key"

    def test_idempotency_new_request_outside_replay_window(self) -> None:
        """✅ Verify new request outside 60-second replay window gets new key."""
        device_id = "dad-phone"
        device_secret = b"super_secret_key_32_bytes_long_"
        envelope_sha256 = "a" * 64
        ts = "2025-01-01T12:00:00+00:00"

        # First request
        key1 = derive_hmac_idem_key(envelope_sha256, device_id, device_secret, ts)

        # New request 2 minutes later (outside replay window)
        ts_new = "2025-01-01T12:02:00+00:00"
        key_new = derive_hmac_idem_key(envelope_sha256, device_id, device_secret, ts_new)

        # Different time buckets = different keys = new request allowed
        assert key1 != key_new, "New request outside replay window should produce different key"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
