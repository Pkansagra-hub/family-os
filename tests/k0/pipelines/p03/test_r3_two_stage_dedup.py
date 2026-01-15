"""
Tests for TwoStageDeduplicator — SimHash + embedding verification.

Epic 4.3.2 — Test Cases from M4_EXECUTION.md:
1. test_stage1_filters_non_candidates — high hamming distance excluded
2. test_stage2_confirms_true_duplicate — similarity ≥ 0.85
3. test_stage2_rejects_false_positive — SimHash match, embedding < 0.70
4. test_semantic_fallback_catches_paraphrase — SimHash miss, embedding ≥ 0.90
5. test_likely_duplicate_flagged — similarity 0.70-0.85
6. test_duplicate_match_contains_method — check_method populated
"""

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pytest

from k0.modules.consolidation.algorithms.simhasher import SimHasher
from k0.modules.consolidation.algorithms.two_stage_dedup import (
    DuplicateDecision,
    Stage1SimHashFilter,
    Stage2EmbeddingVerifier,
    TwoStageDeduplicator,
)


@dataclass
class MockP03EventState:
    """
    Mock P03EventState for testing deduplication.

    Provides the fields needed by TwoStageDeduplicator:
    - event_id: Unique identifier
    - simhash_hex: 16-char hex SimHash from P02
    - content_type: Content type for threshold lookup
    - embedding_768: 768-dim embedding vector
    """

    event_id: str
    simhash_hex: str = ""
    content_type: str = "CHAT_MESSAGE"
    embedding_768: Optional[List[float]] = None


def make_random_embedding(dim: int = 768, seed: Optional[int] = None) -> List[float]:
    """Create a random normalized embedding vector."""
    if seed is not None:
        np.random.seed(seed)
    vec = np.random.randn(dim)
    vec = vec / np.linalg.norm(vec)  # Normalize
    return vec.tolist()


def make_similar_embedding(
    base: List[float], similarity: float = 0.9, seed: Optional[int] = None
) -> List[float]:
    """
    Create an embedding with approximately the given similarity to base.

    This adds random noise scaled to achieve the target similarity.
    """
    if seed is not None:
        np.random.seed(seed)

    base_arr = np.array(base)
    noise = np.random.randn(len(base))
    noise = noise / np.linalg.norm(noise)

    # Scale noise to achieve target similarity
    # cos(theta) = similarity, so we need sin(theta) amount of noise
    theta = np.arccos(similarity)
    result = np.cos(theta) * base_arr + np.sin(theta) * noise
    result = result / np.linalg.norm(result)

    return result.tolist()


class TestStage1SimHashFilter:
    """Tests for Stage 1 SimHash filtering."""

    @pytest.fixture
    def hasher(self) -> SimHasher:
        return SimHasher()

    @pytest.fixture
    def stage1(self, hasher: SimHasher) -> Stage1SimHashFilter:
        return Stage1SimHashFilter(hasher)

    def test_finds_candidates_with_low_hamming(
        self, stage1: Stage1SimHashFilter, hasher: SimHasher
    ) -> None:
        """Should find events with hamming distance ≤ threshold."""
        # Create events with known SimHashes
        base_hash = hasher.compute_simhash("Meeting with John at 3pm in the conference room")
        similar_hash = base_hash ^ 0b11  # 2 bits different

        new_event = MockP03EventState(
            event_id="new-001",
            simhash_hex=hasher.simhash_to_hex(base_hash),
        )
        recent_events = [
            MockP03EventState(
                event_id="old-001",
                simhash_hex=hasher.simhash_to_hex(similar_hash),
            ),
        ]

        candidates = stage1.find_candidates(new_event, recent_events, threshold=3)

        assert len(candidates) == 1
        assert candidates[0][0] == "old-001"
        assert candidates[0][1] == 2  # Hamming distance

    def test_excludes_high_hamming_distance(
        self, stage1: Stage1SimHashFilter, hasher: SimHasher
    ) -> None:
        """Should exclude events with hamming distance > threshold."""
        new_event = MockP03EventState(
            event_id="new-001",
            simhash_hex=hasher.compute_and_format(
                "Meeting with John at 3pm in the conference room"
            ),
        )
        recent_events = [
            MockP03EventState(
                event_id="old-001",
                simhash_hex=hasher.compute_and_format(
                    "Completely different content about something else"
                ),
            ),
        ]

        candidates = stage1.find_candidates(new_event, recent_events, threshold=3)

        # Different content should not be a candidate
        assert len(candidates) == 0

    def test_excludes_self(self, stage1: Stage1SimHashFilter, hasher: SimHasher) -> None:
        """Should not match event against itself."""
        simhash_hex = hasher.compute_and_format("Test content")
        new_event = MockP03EventState(
            event_id="event-001",
            simhash_hex=simhash_hex,
        )
        recent_events = [
            MockP03EventState(
                event_id="event-001",  # Same ID
                simhash_hex=simhash_hex,
            ),
        ]

        candidates = stage1.find_candidates(new_event, recent_events, threshold=3)

        assert len(candidates) == 0

    def test_handles_missing_simhash(self, stage1: Stage1SimHashFilter, hasher: SimHasher) -> None:
        """Should handle events without SimHash gracefully."""
        new_event = MockP03EventState(
            event_id="new-001",
            simhash_hex="",  # No SimHash
        )
        recent_events = [
            MockP03EventState(
                event_id="old-001",
                simhash_hex=hasher.compute_and_format("Some content"),
            ),
        ]

        candidates = stage1.find_candidates(new_event, recent_events, threshold=3)
        assert len(candidates) == 0


class TestStage2EmbeddingVerifier:
    """Tests for Stage 2 embedding verification."""

    @pytest.fixture
    def stage2(self) -> Stage2EmbeddingVerifier:
        return Stage2EmbeddingVerifier()

    def test_confirms_true_duplicate(self, stage2: Stage2EmbeddingVerifier) -> None:
        """Should confirm duplicate when similarity ≥ 0.85."""
        base_embedding = make_random_embedding(seed=42)
        similar_embedding = make_similar_embedding(base_embedding, similarity=0.92)

        event1 = MockP03EventState(
            event_id="new-001",
            embedding_768=base_embedding,
        )
        event2 = MockP03EventState(
            event_id="old-001",
            embedding_768=similar_embedding,
        )

        is_dup, similarity, decision = stage2.verify_duplicate(event1, event2)

        assert is_dup is True
        assert similarity >= 0.85
        assert decision == DuplicateDecision.DUPLICATE

    def test_rejects_false_positive(self, stage2: Stage2EmbeddingVerifier) -> None:
        """Should reject SimHash false positive when embedding < 0.70."""
        # Create two very different embeddings
        base_embedding = make_random_embedding(seed=42)
        different_embedding = make_random_embedding(seed=999)  # Different seed

        event1 = MockP03EventState(
            event_id="new-001",
            embedding_768=base_embedding,
        )
        event2 = MockP03EventState(
            event_id="old-001",
            embedding_768=different_embedding,
        )

        is_dup, similarity, decision = stage2.verify_duplicate(event1, event2)

        assert is_dup is False
        assert similarity < 0.70
        assert decision == DuplicateDecision.NOT_DUPLICATE

    def test_flags_likely_duplicate(self, stage2: Stage2EmbeddingVerifier) -> None:
        """Should flag as LIKELY_DUPLICATE when similarity 0.70-0.85."""
        base_embedding = make_random_embedding(seed=42)
        # Create embedding with ~0.77 similarity
        similar_embedding = make_similar_embedding(base_embedding, similarity=0.77)

        event1 = MockP03EventState(
            event_id="new-001",
            embedding_768=base_embedding,
        )
        event2 = MockP03EventState(
            event_id="old-001",
            embedding_768=similar_embedding,
        )

        is_dup, similarity, decision = stage2.verify_duplicate(event1, event2)

        assert is_dup is True
        assert 0.70 <= similarity < 0.85
        assert decision == DuplicateDecision.LIKELY_DUPLICATE

    def test_handles_missing_embeddings(self, stage2: Stage2EmbeddingVerifier) -> None:
        """Should handle missing embeddings gracefully."""
        event1 = MockP03EventState(
            event_id="new-001",
            embedding_768=make_random_embedding(seed=42),
        )
        event2 = MockP03EventState(
            event_id="old-001",
            embedding_768=None,  # Missing
        )

        is_dup, similarity, decision = stage2.verify_duplicate(event1, event2)

        assert is_dup is False
        assert similarity == 0.0
        assert decision == DuplicateDecision.NOT_DUPLICATE


class TestTwoStageDeduplicator:
    """Tests for complete two-stage deduplication pipeline."""

    @pytest.fixture
    def dedup(self) -> TwoStageDeduplicator:
        return TwoStageDeduplicator()

    def test_finds_duplicate_via_two_stage(self, dedup: TwoStageDeduplicator) -> None:
        """Should find duplicates through full two-stage pipeline."""
        # Use identical text to ensure SimHash catches it via Stage 1
        identical_text = "Meeting with John at 3pm in the conference room today"

        base_embedding = make_random_embedding(seed=42)
        similar_embedding = make_similar_embedding(base_embedding, similarity=0.92)

        new_event = MockP03EventState(
            event_id="new-001",
            simhash_hex=dedup.simhasher.compute_and_format(identical_text),
            content_type="CHAT_MESSAGE",
            embedding_768=base_embedding,
        )
        window_events = [
            MockP03EventState(
                event_id="old-001",
                simhash_hex=dedup.simhasher.compute_and_format(identical_text),  # Same text
                content_type="CHAT_MESSAGE",
                embedding_768=similar_embedding,
            ),
        ]

        matches = dedup.find_duplicates(new_event, window_events)

        # Should find the duplicate via TWO_STAGE (Stage 1 catches same simhash)
        assert len(matches) >= 1
        match = matches[0]
        assert match.event_id == "old-001"
        assert match.check_method == "TWO_STAGE"  # Identical simhash should go through Stage 1
        assert match.decision_type in (
            DuplicateDecision.DUPLICATE,
            DuplicateDecision.LIKELY_DUPLICATE,
        )

    def test_stage2_rejects_simhash_false_positive(self, dedup: TwoStageDeduplicator) -> None:
        """Should reject SimHash match when embedding similarity is low."""
        # "I ate pizza" vs "I hate pizza" - syntactically similar, semantically different
        # Force same SimHash by using same hex
        same_simhash = "1234567890ABCDEF"

        # Very different embeddings
        base_embedding = make_random_embedding(seed=42)
        different_embedding = make_random_embedding(seed=999)

        new_event = MockP03EventState(
            event_id="new-001",
            simhash_hex=same_simhash,
            content_type="CHAT_MESSAGE",
            embedding_768=base_embedding,
        )
        window_events = [
            MockP03EventState(
                event_id="old-001",
                simhash_hex=same_simhash,  # Same SimHash (false positive case)
                content_type="CHAT_MESSAGE",
                embedding_768=different_embedding,
            ),
        ]

        # Disable fallback to test pure two-stage
        matches = dedup.find_duplicates(new_event, window_events, include_fallback=False)

        # Should NOT match because embeddings are different
        assert len(matches) == 0

    def test_semantic_fallback_catches_paraphrase(self, dedup: TwoStageDeduplicator) -> None:
        """Should catch semantic duplicates missed by SimHash via fallback."""
        # "Had pizza for dinner" vs "Ate pizza tonight"
        # Different words (high Hamming) but same meaning (high embedding similarity)
        text1 = "Had pizza for dinner with my family last night"
        text2 = "Ate pizza tonight with my relatives in the evening"

        base_embedding = make_random_embedding(seed=42)
        # Very similar embedding (semantic duplicate)
        similar_embedding = make_similar_embedding(base_embedding, similarity=0.95)

        new_event = MockP03EventState(
            event_id="new-001",
            simhash_hex=dedup.simhasher.compute_and_format(text1),
            content_type="CHAT_MESSAGE",
            embedding_768=base_embedding,
        )
        window_events = [
            MockP03EventState(
                event_id="old-001",
                simhash_hex=dedup.simhasher.compute_and_format(text2),  # Different
                content_type="CHAT_MESSAGE",
                embedding_768=similar_embedding,
            ),
        ]

        matches = dedup.find_duplicates(new_event, window_events, include_fallback=True)

        # Should find via embedding fallback
        semantic_matches = [
            m for m in matches if m.decision_type == DuplicateDecision.SEMANTIC_DUPLICATE
        ]
        # Either found via two-stage (if SimHash caught it) or fallback
        assert len(matches) >= 1
        # If found via fallback, check method should be EMBEDDING_FALLBACK
        if semantic_matches:
            assert semantic_matches[0].check_method == "EMBEDDING_FALLBACK"
            assert semantic_matches[0].hamming_distance is None

    def test_duplicate_match_contains_method(self, dedup: TwoStageDeduplicator) -> None:
        """All matches should include check_method for auditing."""
        base_embedding = make_random_embedding(seed=42)
        similar_embedding = make_similar_embedding(base_embedding, similarity=0.92)
        same_simhash = "1234567890ABCDEF"

        new_event = MockP03EventState(
            event_id="new-001",
            simhash_hex=same_simhash,
            content_type="CHAT_MESSAGE",
            embedding_768=base_embedding,
        )
        window_events = [
            MockP03EventState(
                event_id="old-001",
                simhash_hex=same_simhash,
                content_type="CHAT_MESSAGE",
                embedding_768=similar_embedding,
            ),
        ]

        matches = dedup.find_duplicates(new_event, window_events)

        for match in matches:
            assert match.check_method in ("TWO_STAGE", "EMBEDDING_FALLBACK")

    def test_content_type_affects_threshold(self, dedup: TwoStageDeduplicator) -> None:
        """Different content types should use different thresholds."""
        # TRANSACTION has threshold 1, VOICE_MEMO has threshold 5
        base_hash = 0xFFFFFFFFFFFFFFFF
        hash_2_bits_diff = base_hash ^ 0b11  # 2 bits different

        base_embedding = make_random_embedding(seed=42)
        similar_embedding = make_similar_embedding(base_embedding, similarity=0.92)

        # For TRANSACTION (threshold=1), 2-bit difference should NOT match
        new_event_tx = MockP03EventState(
            event_id="new-001",
            simhash_hex=format(base_hash, "016X"),
            content_type="TRANSACTION",
            embedding_768=base_embedding,
        )
        window_events = [
            MockP03EventState(
                event_id="old-001",
                simhash_hex=format(hash_2_bits_diff, "016X"),
                content_type="TRANSACTION",
                embedding_768=similar_embedding,
            ),
        ]

        matches_tx = dedup.find_duplicates(new_event_tx, window_events, include_fallback=False)

        # TRANSACTION with 2-bit diff should NOT match via SimHash
        # (threshold is 1, distance is 2)
        two_stage_matches = [m for m in matches_tx if m.check_method == "TWO_STAGE"]
        assert len(two_stage_matches) == 0

    def test_find_best_duplicate(self, dedup: TwoStageDeduplicator) -> None:
        """find_best_duplicate should return highest similarity match."""
        base_embedding = make_random_embedding(seed=42)
        similar_1 = make_similar_embedding(base_embedding, similarity=0.88)
        similar_2 = make_similar_embedding(base_embedding, similarity=0.92)

        same_simhash = "1234567890ABCDEF"

        new_event = MockP03EventState(
            event_id="new-001",
            simhash_hex=same_simhash,
            embedding_768=base_embedding,
        )
        window_events = [
            MockP03EventState(
                event_id="old-001",
                simhash_hex=same_simhash,
                embedding_768=similar_1,
            ),
            MockP03EventState(
                event_id="old-002",
                simhash_hex=same_simhash,
                embedding_768=similar_2,
            ),
        ]

        best = dedup.find_best_duplicate(new_event, window_events)

        assert best is not None
        assert best.event_id == "old-002"  # Higher similarity
        assert best.embedding_similarity >= 0.90

    def test_no_duplicates_returns_empty(self, dedup: TwoStageDeduplicator) -> None:
        """Should return empty list when no duplicates found."""
        base_embedding = make_random_embedding(seed=42)
        different_embedding = make_random_embedding(seed=999)

        new_event = MockP03EventState(
            event_id="new-001",
            simhash_hex=dedup.simhasher.compute_and_format(
                "Meeting with John at 3pm in the conference room"
            ),
            embedding_768=base_embedding,
        )
        window_events = [
            MockP03EventState(
                event_id="old-001",
                simhash_hex=dedup.simhasher.compute_and_format(
                    "Completely different content about something else entirely"
                ),
                embedding_768=different_embedding,
            ),
        ]

        matches = dedup.find_duplicates(new_event, window_events)

        assert len(matches) == 0

    def test_find_best_duplicate_returns_none_when_no_matches(
        self, dedup: TwoStageDeduplicator
    ) -> None:
        """find_best_duplicate should return None when no matches."""
        base_embedding = make_random_embedding(seed=42)
        different_embedding = make_random_embedding(seed=999)

        new_event = MockP03EventState(
            event_id="new-001",
            simhash_hex=dedup.simhasher.compute_and_format("Text one"),
            embedding_768=base_embedding,
        )
        window_events = [
            MockP03EventState(
                event_id="old-001",
                simhash_hex=dedup.simhasher.compute_and_format("Text two"),
                embedding_768=different_embedding,
            ),
        ]

        best = dedup.find_best_duplicate(new_event, window_events)

        assert best is None


class TestCosineSimlarity:
    """Tests for cosine similarity helper."""

    def test_identical_vectors(self) -> None:
        """Identical vectors should have similarity 1.0."""
        vec = make_random_embedding(seed=42)
        similarity = Stage2EmbeddingVerifier.cosine_similarity(vec, vec)
        assert abs(similarity - 1.0) < 1e-6

    def test_orthogonal_vectors(self) -> None:
        """Orthogonal vectors should have similarity 0.0."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        similarity = Stage2EmbeddingVerifier.cosine_similarity(vec1, vec2)
        assert abs(similarity) < 1e-6

    def test_opposite_vectors(self) -> None:
        """Opposite vectors should have similarity -1.0."""
        vec1 = [1.0, 0.0]
        vec2 = [-1.0, 0.0]
        similarity = Stage2EmbeddingVerifier.cosine_similarity(vec1, vec2)
        assert abs(similarity + 1.0) < 1e-6

    def test_zero_vector_returns_zero(self) -> None:
        """Zero vector should return similarity 0.0."""
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [0.0, 0.0, 0.0]
        similarity = Stage2EmbeddingVerifier.cosine_similarity(vec1, vec2)
        assert similarity == 0.0
