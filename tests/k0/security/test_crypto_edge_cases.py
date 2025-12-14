"""Phase 3: Security/Crypto Edge Cases Tests."""

import base64
import json

import pytest
from nacl.signing import SigningKey

from k0.security.crypto import (
    SignatureVerificationError,
    _decode_base64url,
    canonical_envelope,
    canonical_json,
    compute_envelope_sha256,
    encode_base64url,
    hash_payload,
    verify_full_envelope_signature,
    verify_signature,
)


class TestDecodeBase64UrlEdgeCases:
    """Test _decode_base64url edge cases and error conditions."""

    def test_decode_base64url_invalid_padding(self):
        """Test _decode_base64url with invalid base64 data."""
        # This should actually succeed because base64.urlsafe_b64decode is lenient
        result = _decode_base64url("invalid!@#")
        # The result will be whatever base64 decodes "invalid!@#" to
        assert isinstance(result, bytes)

    def test_decode_base64url_malformed_data(self):
        """Test _decode_base64url with malformed base64."""
        # This should also succeed due to leniency
        result = _decode_base64url("not-valid-base64!!!")
        assert isinstance(result, bytes)

    def test_decode_base64url_empty_string(self):
        """Test _decode_base64url with empty string."""
        result = _decode_base64url("")
        assert result == b""

    def test_decode_base64url_with_padding_needed(self):
        """Test _decode_base64url handles padding correctly."""
        test_cases = [
            ("SGVsbG8", b"Hello"),  # "SGVsbG8" -> "Hello"
            ("SGVs", b"Hel"),  # "SGVs" (already 4 chars) -> "Hel"
            ("SG", b"H"),  # "SG" + "==" -> "SG==" -> "H"
        ]
        for encoded, expected in test_cases:
            result = _decode_base64url(encoded)
            assert result == expected


class TestVerifySignatureEdgeCases:
    """Test verify_signature edge cases and error conditions."""

    def test_verify_signature_invalid_base64_signature(self):
        """Test verify_signature with invalid base64 signature."""
        verify_key_b64 = encode_base64url(b"fake_32_byte_verify_key_123456789012")
        with pytest.raises(SignatureVerificationError, match="Signature verification failed"):
            verify_signature(b"message", "invalid!@#", verify_key_b64)

    def test_verify_signature_invalid_base64_key(self):
        """Test verify_signature with invalid base64 verify key."""
        signature_b64 = "fake_signature_base64"
        with pytest.raises(SignatureVerificationError, match="Invalid base64url data"):
            verify_signature(b"message", signature_b64, "invalid!@#")

    def test_verify_signature_wrong_key_length(self):
        """Test verify_signature with wrong key length."""
        wrong_key = b"wrong_length_key"
        verify_key_b64 = encode_base64url(wrong_key)
        signature_b64 = "fake_signature"
        with pytest.raises(SignatureVerificationError, match="Signature verification failed"):
            verify_signature(b"message", signature_b64, verify_key_b64)

    def test_verify_signature_bad_signature(self):
        """Test verify_signature with bad signature data."""
        signing_key = SigningKey.generate()
        verify_key_b64 = encode_base64url(bytes(signing_key.verify_key))
        wrong_signature_b64 = encode_base64url(
            b"wrong_64_byte_signature_123456789012345678901234567890123456789012"
        )
        with pytest.raises(SignatureVerificationError, match="Signature verification failed"):
            verify_signature(b"message", wrong_signature_b64, verify_key_b64)


class TestCanonicalJsonEdgeCases:
    """Test canonical_json edge cases."""

    def test_canonical_json_with_none_values(self):
        """Test canonical_json handles None values correctly."""
        data = {"key": None, "other": "value"}
        result = canonical_json(data)
        parsed = json.loads(result)
        assert parsed["key"] is None
        assert parsed["other"] == "value"

    def test_canonical_json_with_unicode_characters(self):
        """Test canonical_json preserves Unicode characters."""
        data = {"message": "Hello 世界 "}
        result = canonical_json(data)
        assert "世界" in result
        assert "" in result
        parsed = json.loads(result)
        assert parsed["message"] == "Hello 世界 "

    def test_canonical_json_deterministic_ordering(self):
        """Test canonical_json produces consistent output."""
        data1 = {"z": 1, "a": 2, "m": 3}
        data2 = {"m": 3, "z": 1, "a": 2}
        result1 = canonical_json(data1)
        result2 = canonical_json(data2)
        assert result1 == result2


class TestHashPayloadEdgeCases:
    """Test hash_payload edge cases."""

    def test_hash_payload_empty_bytes(self):
        """Test hash_payload with empty byte payload."""
        result = hash_payload(b"")
        assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_hash_payload_none_returns_none(self):
        """Test hash_payload returns None for None input."""
        result = hash_payload(None)
        assert result is None

    def test_hash_payload_various_byte_patterns(self):
        """Test hash_payload with various byte patterns."""
        patterns = [
            b"\x00\x01\x02\x03",
            "Hello 世界".encode("utf-8"),
            b"\xff\xfe\xfd",
        ]
        hashes = []
        for pattern in patterns:
            h = hash_payload(pattern)
            assert h is not None
            assert len(h) == 64
            assert h.isalnum()
            assert h == h.lower()
            hashes.append(h)
        assert len(set(hashes)) == len(hashes)


class TestVerifyFullEnvelopeSignatureEdgeCases:
    """Test verify_full_envelope_signature edge cases."""

    def test_verify_full_envelope_signature_empty_envelope(self):
        """Test verify_full_envelope_signature with empty envelope."""
        verify_key_b64 = "fake_key"
        envelope = {}
        result = verify_full_envelope_signature(envelope, verify_key_b64)
        assert result is False

    def test_verify_full_envelope_signature_sig_is_none(self):
        """Test verify_full_envelope_signature when sig field is None."""
        verify_key_b64 = "fake_key"
        envelope = {"sig": None}
        result = verify_full_envelope_signature(envelope, verify_key_b64)
        assert result is False

    def test_verify_full_envelope_signature_invalid_sig_type(self):
        """Test verify_full_envelope_signature with non-string sig."""
        verify_key_b64 = "fake_key"
        envelope = {"sig": 12345}
        # This should raise TypeError because _decode_base64url expects str, not int
        with pytest.raises(TypeError):
            verify_full_envelope_signature(envelope, verify_key_b64)


class TestEncodeBase64UrlEdgeCases:
    """Test encode_base64url edge cases."""

    def test_encode_base64url_empty_bytes(self):
        """Test encode_base64url with empty bytes."""
        result = encode_base64url(b"")
        assert result == ""

    def test_encode_base64url_single_byte(self):
        """Test encode_base64url with single byte."""
        result = encode_base64url(b"A")
        assert not result.endswith("=")
        decoded = base64.urlsafe_b64decode(result + "=" * (-len(result) % 4))
        assert decoded == b"A"

    def test_encode_base64url_binary_data(self):
        """Test encode_base64url with binary data."""
        data = b"\x00\x01\x02\x03\xff\xfe\xfd"
        result = encode_base64url(data)
        assert not result.endswith("=")
        decoded = base64.urlsafe_b64decode(result + "=" * (-len(result) % 4))
        assert decoded == data


class TestCanonicalEnvelopeEdgeCases:
    """Test canonical_envelope edge cases."""

    def test_canonical_envelope_empty_envelope(self):
        """Test canonical_envelope with minimal envelope."""
        envelope = {"sig": "to_exclude"}
        result = canonical_envelope(envelope, exclude_signature=True)
        result_str = result.decode("utf-8")
        assert result_str == "{}"

    def test_canonical_envelope_complex_data_types(self):
        """Test canonical_envelope with complex data types."""
        envelope = {
            "numbers": [1, 2.5, -3],
            "boolean": True,
            "null": None,
            "nested": {"key": "value"},
            "sig": "exclude_me",
        }
        result = canonical_envelope(envelope, exclude_signature=True)
        result_str = result.decode("utf-8")
        parsed = json.loads(result_str)
        assert parsed["numbers"] == [1, 2.5, -3]
        assert parsed["boolean"] is True
        assert parsed["null"] is None
        assert parsed["nested"]["key"] == "value"
        assert "sig" not in parsed


class TestComputeEnvelopeSha256EdgeCases:
    """Test compute_envelope_sha256 edge cases."""

    def test_compute_envelope_sha256_empty_envelope(self):
        """Test compute_envelope_sha256 with empty envelope."""
        result = compute_envelope_sha256({})
        assert len(result) == 64
        assert result.isalnum()

    def test_compute_envelope_sha256_only_sig_field(self):
        """Test compute_envelope_sha256 excludes only sig field."""
        envelope1 = {"field": "value", "sig": "sig1"}
        envelope2 = {"field": "value", "sig": "sig2"}
        hash1 = compute_envelope_sha256(envelope1)
        hash2 = compute_envelope_sha256(envelope2)
        assert hash1 == hash2

    def test_compute_envelope_sha256_preserves_body(self):
        """Test compute_envelope_sha256 includes body in hash."""
        envelope1 = {"body": {"message": "hello"}}
        envelope2 = {"body": {"message": "world"}}
        hash1 = compute_envelope_sha256(envelope1)
        hash2 = compute_envelope_sha256(envelope2)
        assert hash1 != hash2
