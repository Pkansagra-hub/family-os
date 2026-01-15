"""
SimHash 64-bit locality-sensitive hashing for near-duplicate detection.

Scientific Basis: Charikar (2002) - Similarity estimation using random projections.
Spec: Dossier Appendix C.4.1

Epic 4.3.1 — Implement SimHash fingerprinting with per-content-type thresholds.
"""

from __future__ import annotations

import hashlib
from typing import List, Tuple


class SimHasher:
    """
    64-bit SimHash for near-duplicate detection.

    Scientific Basis: Charikar (2002) - Similarity estimation using random projections.
    Spec: Dossier Appendix C.4.1

    SimHash works by:
    1. Tokenizing text into 3-gram shingles
    2. Hashing each shingle to a 64-bit value
    3. For each bit position, summing +1 (if bit=1) or -1 (if bit=0)
    4. Final hash: bit=1 if sum > 0, else bit=0

    Two documents are near-duplicates if their Hamming distance is below a threshold.
    """

    HASH_BITS = 64

    # Per-content-type Hamming thresholds (from Dossier C.4.1.1)
    # Lower threshold = stricter matching (fewer false positives)
    # Higher threshold = looser matching (fewer false negatives)
    CONTENT_TYPE_THRESHOLDS = {
        "TRANSACTION": 1,  # Financial exactness required "$50.23" vs "$50.32"
        "CALENDAR_EVENT": 2,  # Structured, small variations matter "2pm" vs "3pm"
        "CONTACT_UPDATE": 2,  # Names/phones must match closely
        "CHAT_MESSAGE": 3,  # Default, mixed content
        "PHOTO_CAPTION": 4,  # Free-form, allow paraphrasing
        "JOURNAL_ENTRY": 4,  # Personal text, subjective
        "VOICE_MEMO": 5,  # ASR transcription has inherent noise
    }
    DEFAULT_THRESHOLD = 3

    def tokenize(self, text: str) -> List[str]:
        """
        Extract 3-gram shingles from text.

        Shingles are overlapping sequences of words, which capture local structure.
        3-grams balance between capturing enough context and being sensitive to changes.

        Args:
            text: Input text to tokenize

        Returns:
            List of 3-gram shingle strings
        """
        text = text.lower().strip()
        words = text.split()

        # Handle short texts (< 3 words)
        if len(words) < 3:
            return [" ".join(words)] if words else []

        # 3-gram shingles
        shingles = []
        for i in range(len(words) - 2):
            shingles.append(" ".join(words[i : i + 3]))

        return shingles

    def compute_simhash(self, text: str) -> int:
        """
        Compute 64-bit SimHash.

        Algorithm (from Dossier C.4.1):
        1. Tokenize text into 3-gram shingles
        2. Hash each shingle to 64-bit value using MD5 (deterministic)
        3. For each bit position, sum +1 (if bit=1) or -1 (if bit=0)
        4. Final hash: bit=1 if sum > 0, else bit=0

        Args:
            text: Input text to hash

        Returns:
            64-bit SimHash as integer
        """
        shingles = self.tokenize(text)
        if not shingles:
            return 0

        # Accumulator for each bit position
        bit_sums = [0] * self.HASH_BITS

        for shingle in shingles:
            # Hash shingle to 64-bit using MD5 (deterministic)
            # Take first 16 hex chars = 64 bits
            h = int(hashlib.md5(shingle.encode("utf-8")).hexdigest()[:16], 16)

            for i in range(self.HASH_BITS):
                if h & (1 << i):
                    bit_sums[i] += 1
                else:
                    bit_sums[i] -= 1

        # Build final hash: bit=1 if sum > 0, else bit=0
        simhash = 0
        for i in range(self.HASH_BITS):
            if bit_sums[i] > 0:
                simhash |= 1 << i

        return simhash

    def simhash_to_hex(self, simhash: int) -> str:
        """
        Convert simhash integer to 16-char hex string.

        Args:
            simhash: 64-bit SimHash as integer

        Returns:
            16-character uppercase hex string (e.g., "53C0CA5E4880D655")
        """
        return format(simhash, "016X")

    def hex_to_simhash(self, hex_str: str) -> int:
        """
        Convert 16-char hex string to simhash integer.

        Args:
            hex_str: 16-character hex string

        Returns:
            64-bit SimHash as integer
        """
        return int(hex_str, 16)

    def hamming_distance(self, hash1: int, hash2: int) -> int:
        """
        Count differing bits between two hashes (0-64).

        Hamming distance is the number of bit positions where the two hashes differ.
        Lower distance = more similar documents.

        Args:
            hash1: First 64-bit SimHash
            hash2: Second 64-bit SimHash

        Returns:
            Number of differing bits (0-64)
        """
        xor = hash1 ^ hash2
        return bin(xor).count("1")

    def get_threshold(self, content_type: str) -> int:
        """
        Get Hamming threshold for content type.

        From Dossier C.4.1.1:
        - TRANSACTION=1 (strictest) - financial data requires exact match
        - VOICE_MEMO=5 (loosest) - ASR errors create inherent noise

        Args:
            content_type: Content type string (e.g., "CHAT_MESSAGE")

        Returns:
            Hamming distance threshold for that content type
        """
        return self.CONTENT_TYPE_THRESHOLDS.get(content_type, self.DEFAULT_THRESHOLD)

    def is_near_duplicate(
        self,
        hash1: int,
        hash2: int,
        content_type: str = "CHAT_MESSAGE",
    ) -> Tuple[bool, int]:
        """
        Check if two hashes represent near-duplicates.

        Args:
            hash1: First 64-bit SimHash
            hash2: Second 64-bit SimHash
            content_type: Content type for threshold lookup

        Returns:
            Tuple of (is_duplicate, hamming_distance)
        """
        threshold = self.get_threshold(content_type)
        distance = self.hamming_distance(hash1, hash2)
        return (distance <= threshold, distance)

    def compute_and_format(self, text: str) -> str:
        """
        Convenience method: compute SimHash and return as hex string.

        Args:
            text: Input text

        Returns:
            16-character hex string
        """
        return self.simhash_to_hex(self.compute_simhash(text))
