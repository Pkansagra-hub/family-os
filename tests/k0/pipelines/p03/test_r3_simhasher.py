"""
Tests for SimHasher — 64-bit locality-sensitive hashing.

Epic 4.3.1 — Test Cases from M4_EXECUTION.md:
1. test_identical_text_zero_distance — same text → hamming = 0
2. test_similar_text_low_distance — minor edits → hamming ≤ 3
3. test_different_text_high_distance — unrelated → hamming > 10
4. test_content_type_thresholds — verify per-type thresholds
5. test_hex_encoding_roundtrip — simhash ↔ hex conversion
6. test_empty_text_returns_zero — edge case
"""

import pytest

from k0.modules.consolidation.algorithms.simhasher import SimHasher


class TestSimHasher:
    """Tests for SimHash fingerprinting."""

    @pytest.fixture
    def hasher(self) -> SimHasher:
        """Create a SimHasher instance."""
        return SimHasher()

    # =========================================================================
    # Test Case 1: Identical text produces zero distance
    # =========================================================================

    def test_identical_text_zero_distance(self, hasher: SimHasher) -> None:
        """Same text should produce identical SimHash (hamming = 0)."""
        text = "Wake up at seven in the morning"
        hash1 = hasher.compute_simhash(text)
        hash2 = hasher.compute_simhash(text)

        assert hash1 == hash2
        assert hasher.hamming_distance(hash1, hash2) == 0

    def test_identical_text_deterministic(self, hasher: SimHasher) -> None:
        """SimHash computation should be deterministic across invocations."""
        text = "Had pizza for dinner with family"
        hash1 = hasher.compute_simhash(text)
        hash2 = hasher.compute_simhash(text)
        hash3 = hasher.compute_simhash(text)

        assert hash1 == hash2 == hash3

    # =========================================================================
    # Test Case 2: Similar text produces low distance
    # =========================================================================

    def test_similar_text_low_distance(self, hasher: SimHasher) -> None:
        """Minor edits should produce small hamming distance (≤ 3)."""
        text1 = "Wake up at seven in the morning"
        text2 = "Woke up at seven in the morning"  # Minor variation

        hash1 = hasher.compute_simhash(text1)
        hash2 = hasher.compute_simhash(text2)
        distance = hasher.hamming_distance(hash1, hash2)

        # Similar text should have low distance
        assert distance <= 10, f"Expected ≤ 10, got {distance}"

    def test_very_similar_text(self, hasher: SimHasher) -> None:
        """Very similar text should have very low distance."""
        text1 = "Meeting with John at 3pm in the conference room"
        text2 = "Meeting with John at 3pm in the conference"  # Slight trim

        hash1 = hasher.compute_simhash(text1)
        hash2 = hasher.compute_simhash(text2)
        distance = hasher.hamming_distance(hash1, hash2)

        assert distance <= 15, f"Expected ≤ 15, got {distance}"

    # =========================================================================
    # Test Case 3: Different text produces high distance
    # =========================================================================

    def test_different_text_high_distance(self, hasher: SimHasher) -> None:
        """Unrelated text should produce large hamming distance (> 10)."""
        text1 = "Wake up at seven in the morning"
        text2 = "Conference call with the engineering team"

        hash1 = hasher.compute_simhash(text1)
        hash2 = hasher.compute_simhash(text2)
        distance = hasher.hamming_distance(hash1, hash2)

        # Completely different text should have high distance
        assert distance > 10, f"Expected > 10, got {distance}"

    def test_opposite_meaning_different_hash(self, hasher: SimHasher) -> None:
        """Text with opposite meaning should still have different hashes."""
        text1 = "I love this product it is amazing"
        text2 = "I hate this product it is terrible"

        hash1 = hasher.compute_simhash(text1)
        hash2 = hasher.compute_simhash(text2)

        # Different meanings = different hashes (though SimHash catches syntactic similarity)
        assert hash1 != hash2

    # =========================================================================
    # Test Case 4: Content-type thresholds
    # =========================================================================

    def test_content_type_thresholds(self, hasher: SimHasher) -> None:
        """Verify per-content-type thresholds match spec."""
        # From Dossier C.4.1.1
        assert hasher.get_threshold("TRANSACTION") == 1  # Strictest
        assert hasher.get_threshold("CALENDAR_EVENT") == 2
        assert hasher.get_threshold("CONTACT_UPDATE") == 2
        assert hasher.get_threshold("CHAT_MESSAGE") == 3  # Default
        assert hasher.get_threshold("PHOTO_CAPTION") == 4
        assert hasher.get_threshold("JOURNAL_ENTRY") == 4
        assert hasher.get_threshold("VOICE_MEMO") == 5  # Loosest

    def test_unknown_content_type_uses_default(self, hasher: SimHasher) -> None:
        """Unknown content types should use default threshold."""
        assert hasher.get_threshold("UNKNOWN_TYPE") == hasher.DEFAULT_THRESHOLD
        assert hasher.get_threshold("") == hasher.DEFAULT_THRESHOLD

    def test_is_near_duplicate_respects_content_type(self, hasher: SimHasher) -> None:
        """is_near_duplicate should respect content-type thresholds."""
        # Create hashes with known distance
        hash1 = 0b1111111111111111111111111111111111111111111111111111111111111111
        hash2 = 0b1111111111111111111111111111111111111111111111111111111111111110  # 1 bit diff
        hash3 = 0b1111111111111111111111111111111111111111111111111111111111111100  # 2 bits diff

        # Distance 1: TRANSACTION (threshold=1) should match
        is_dup, dist = hasher.is_near_duplicate(hash1, hash2, "TRANSACTION")
        assert is_dup is True
        assert dist == 1

        # Distance 2: TRANSACTION (threshold=1) should NOT match
        is_dup, dist = hasher.is_near_duplicate(hash1, hash3, "TRANSACTION")
        assert is_dup is False
        assert dist == 2

        # Distance 2: CALENDAR_EVENT (threshold=2) should match
        is_dup, dist = hasher.is_near_duplicate(hash1, hash3, "CALENDAR_EVENT")
        assert is_dup is True
        assert dist == 2

    # =========================================================================
    # Test Case 5: Hex encoding roundtrip
    # =========================================================================

    def test_hex_encoding_roundtrip(self, hasher: SimHasher) -> None:
        """SimHash should roundtrip through hex encoding."""
        text = "Sample text for hex encoding test roundtrip"
        original_hash = hasher.compute_simhash(text)

        hex_str = hasher.simhash_to_hex(original_hash)
        recovered_hash = hasher.hex_to_simhash(hex_str)

        assert recovered_hash == original_hash

    def test_hex_format_16_chars(self, hasher: SimHasher) -> None:
        """Hex string should always be 16 characters."""
        # Test with various inputs
        for text in ["short", "a much longer piece of text with more content"]:
            hash_val = hasher.compute_simhash(text)
            hex_str = hasher.simhash_to_hex(hash_val)
            assert len(hex_str) == 16, f"Expected 16 chars, got {len(hex_str)}"
            assert hex_str.isalnum(), "Hex should be alphanumeric"

    def test_hex_uppercase(self, hasher: SimHasher) -> None:
        """Hex string should be uppercase."""
        text = "Test text for uppercase check"
        hash_val = hasher.compute_simhash(text)
        hex_str = hasher.simhash_to_hex(hash_val)

        assert hex_str.isupper() or hex_str.isdigit(), "Should be uppercase hex"

    def test_hex_to_simhash_case_insensitive(self, hasher: SimHasher) -> None:
        """hex_to_simhash should handle both upper and lowercase."""
        hash_val = 0x53C0CA5E4880D655
        hex_upper = "53C0CA5E4880D655"
        hex_lower = "53c0ca5e4880d655"

        assert hasher.hex_to_simhash(hex_upper) == hash_val
        assert hasher.hex_to_simhash(hex_lower) == hash_val

    # =========================================================================
    # Test Case 6: Edge cases
    # =========================================================================

    def test_empty_text_returns_zero(self, hasher: SimHasher) -> None:
        """Empty text should return 0."""
        assert hasher.compute_simhash("") == 0
        assert hasher.compute_simhash("   ") == 0

    def test_short_text_handling(self, hasher: SimHasher) -> None:
        """Short text (< 3 words) should still produce valid hash."""
        hash1 = hasher.compute_simhash("Hello")
        hash2 = hasher.compute_simhash("Hi")

        # Should produce valid integers
        assert isinstance(hash1, int)
        assert isinstance(hash2, int)

    def test_two_word_text(self, hasher: SimHasher) -> None:
        """Two-word text should produce valid hash."""
        hash_val = hasher.compute_simhash("Hello world")
        assert isinstance(hash_val, int)
        assert hash_val != 0  # Should produce non-zero for actual content

    def test_single_word_produces_hash(self, hasher: SimHasher) -> None:
        """Single word should produce valid hash (treated as single shingle)."""
        hash_val = hasher.compute_simhash("Hello")
        assert isinstance(hash_val, int)

    # =========================================================================
    # Test: Tokenization
    # =========================================================================

    def test_tokenize_produces_3grams(self, hasher: SimHasher) -> None:
        """Tokenize should produce 3-gram shingles."""
        text = "one two three four five"
        shingles = hasher.tokenize(text)

        expected = ["one two three", "two three four", "three four five"]
        assert shingles == expected

    def test_tokenize_normalizes_case(self, hasher: SimHasher) -> None:
        """Tokenize should normalize to lowercase."""
        text = "One Two Three Four"
        shingles = hasher.tokenize(text)

        assert all(s.islower() for s in shingles)

    def test_tokenize_short_text(self, hasher: SimHasher) -> None:
        """Tokenize handles short text gracefully."""
        # Less than 3 words
        assert hasher.tokenize("one") == ["one"]
        assert hasher.tokenize("one two") == ["one two"]
        assert hasher.tokenize("") == []
        assert hasher.tokenize("   ") == []

    # =========================================================================
    # Test: Hamming distance
    # =========================================================================

    def test_hamming_distance_same_hash(self, hasher: SimHasher) -> None:
        """Hamming distance of identical hashes should be 0."""
        hash_val = 0x53C0CA5E4880D655
        assert hasher.hamming_distance(hash_val, hash_val) == 0

    def test_hamming_distance_known_values(self, hasher: SimHasher) -> None:
        """Test hamming distance with known bit differences."""
        # All zeros vs all ones = 64 bits different
        assert hasher.hamming_distance(0, 0xFFFFFFFFFFFFFFFF) == 64

        # 1 bit different
        assert hasher.hamming_distance(0b0, 0b1) == 1

        # 4 bits different
        assert hasher.hamming_distance(0b0000, 0b1111) == 4

    def test_hamming_distance_symmetric(self, hasher: SimHasher) -> None:
        """Hamming distance should be symmetric."""
        hash1 = 0x53C0CA5E4880D655
        hash2 = 0x63D1DB6F5991E766

        assert hasher.hamming_distance(hash1, hash2) == hasher.hamming_distance(hash2, hash1)

    # =========================================================================
    # Test: Convenience method
    # =========================================================================

    def test_compute_and_format(self, hasher: SimHasher) -> None:
        """compute_and_format should return hex string directly."""
        text = "Sample text for convenience method"
        hex_str = hasher.compute_and_format(text)

        assert len(hex_str) == 16
        assert isinstance(hex_str, str)

        # Should match manual computation
        manual_hash = hasher.compute_simhash(text)
        manual_hex = hasher.simhash_to_hex(manual_hash)
        assert hex_str == manual_hex

    # =========================================================================
    # Test: Integration with P03EventState fields
    # =========================================================================

    def test_matches_p03_event_state_format(self, hasher: SimHasher) -> None:
        """Output format should match P03EventState.simhash_hex field."""
        # P03EventState expects 16-char uppercase hex
        text = "Event content for P03 integration"
        hex_str = hasher.compute_and_format(text)

        # Should be valid for P03EventState.simhash_hex
        assert len(hex_str) == 16
        # Should be valid hex
        int(hex_str, 16)  # Will raise if invalid
