"""
Two-stage deduplication pipeline combining SimHash and embeddings.

Spec: Dossier Appendix C.4.1.2 - Two-stage deduplication pipeline

Epic 4.3.2 - Implement two-stage deduplication pipeline.

Problem Statement (from Dossier C.4.1.2):
SimHash alone has limitations:
1. False Positives: "I ate pizza" vs "I hate pizza" (Hamming = 2, but opposite meaning)
2. False Negatives: "Had pizza for dinner" vs "Ate pizza tonight" (Hamming > 3, but semantically identical)

Solution: Combine SimHash syntactic filtering with embedding semantic verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Protocol, Set, Tuple, runtime_checkable

import numpy as np

from k0.modules.consolidation.algorithms.simhasher import SimHasher


@runtime_checkable
class EventStateProtocol(Protocol):
    """
    Protocol for event state objects compatible with deduplication.

    This allows the deduplicator to work with any object that has the required
    attributes, not just P03EventState. Useful for testing with mock objects.
    """

    event_id: str
    simhash_hex: str
    content_type: str
    embedding_768: Optional[List[float]]


class DuplicateDecision(Enum):
    """
    Decision types from two-stage deduplication.

    From Dossier C.4.1.2:
    - DUPLICATE: High similarity (>= 0.85), merge immediately
    - LIKELY_DUPLICATE: Medium similarity (0.70-0.85), flag for review
    - NOT_DUPLICATE: Low similarity (< 0.70), SimHash false positive
    - SEMANTIC_DUPLICATE: Caught by embedding fallback (SimHash missed)
    - DISTINCT: Different content, process independently
    """

    DUPLICATE = "DUPLICATE"  # >= 0.85 similarity
    LIKELY_DUPLICATE = "LIKELY_DUPLICATE"  # 0.70-0.85 similarity
    NOT_DUPLICATE = "NOT_DUPLICATE"  # < 0.70 similarity
    SEMANTIC_DUPLICATE = "SEMANTIC_DUPLICATE"  # Caught by embedding fallback
    DISTINCT = "DISTINCT"  # Different content


@dataclass
class DuplicateMatch:
    """
    Result from duplicate detection.

    Attributes:
        event_id: ID of the matched (canonical) event
        hamming_distance: SimHash Hamming distance (None if embedding fallback)
        embedding_similarity: Cosine similarity between embeddings
        decision_type: DuplicateDecision enum value
        check_method: 'TWO_STAGE' or 'EMBEDDING_FALLBACK'
    """

    event_id: str
    hamming_distance: Optional[int]  # None if embedding fallback
    embedding_similarity: float
    decision_type: DuplicateDecision
    check_method: str  # 'TWO_STAGE' or 'EMBEDDING_FALLBACK'


class Stage1SimHashFilter:
    """
    Fast O(n) filter using SimHash.

    Spec: Dossier C.4.1.2 Stage 1

    This is the first pass that eliminates 99%+ of non-candidates,
    leaving only events with low Hamming distance for embedding verification.
    """

    def __init__(self, simhasher: SimHasher):
        self.simhasher = simhasher

    def find_candidates(
        self,
        new_event: EventStateProtocol,
        recent_events: List[EventStateProtocol],
        threshold: int = 3,
    ) -> List[Tuple[str, int]]:
        """
        Find events with Hamming distance <= threshold.

        Args:
            new_event: The new event to check for duplicates
            recent_events: List of recent events to compare against
            threshold: Maximum Hamming distance to consider

        Returns:
            List of (event_id, hamming_distance) tuples for candidates
        """
        if not new_event.simhash_hex:
            return []

        new_hash = self.simhasher.hex_to_simhash(new_event.simhash_hex)
        candidates: List[Tuple[str, int]] = []

        for event in recent_events:
            # Skip self and events without simhash
            if not event.simhash_hex or event.event_id == new_event.event_id:
                continue

            event_hash = self.simhasher.hex_to_simhash(event.simhash_hex)
            dist = self.simhasher.hamming_distance(new_hash, event_hash)

            if dist <= threshold:
                candidates.append((event.event_id, dist))

        return candidates


class Stage2EmbeddingVerifier:
    """
    Semantic verification using cosine similarity.

    Spec: Dossier C.4.1.2 Stage 2

    This catches SimHash false positives like "I ate pizza" vs "I hate pizza"
    which have low Hamming distance but opposite meanings.
    """

    # Thresholds from Dossier C.4.1.2
    DUPLICATE_THRESHOLD = 0.85
    LIKELY_DUPLICATE_THRESHOLD = 0.70
    SEMANTIC_FALLBACK_THRESHOLD = 0.90

    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """
        Compute cosine similarity between two vectors.

        Args:
            vec1: First embedding vector
            vec2: Second embedding vector

        Returns:
            Cosine similarity in range [-1, 1]
        """
        arr1 = np.array(vec1)
        arr2 = np.array(vec2)
        norm1 = np.linalg.norm(arr1)
        norm2 = np.linalg.norm(arr2)

        if norm1 < 1e-8 or norm2 < 1e-8:
            return 0.0

        return float(np.dot(arr1, arr2) / (norm1 * norm2))

    def verify_duplicate(
        self,
        event1: EventStateProtocol,
        event2: EventStateProtocol,
    ) -> Tuple[bool, float, DuplicateDecision]:
        """
        Verify if candidate pair is truly duplicate.

        Args:
            event1: First event (new event)
            event2: Second event (candidate from Stage 1)

        Returns:
            Tuple of (is_duplicate, similarity, decision_type)
        """
        if event1.embedding_768 is None or event2.embedding_768 is None:
            return (False, 0.0, DuplicateDecision.NOT_DUPLICATE)

        # Compute cosine similarity
        similarity = self.cosine_similarity(event1.embedding_768, event2.embedding_768)

        # Decision logic (from Dossier C.4.1.2)
        if similarity >= self.DUPLICATE_THRESHOLD:
            return (True, similarity, DuplicateDecision.DUPLICATE)
        elif similarity >= self.LIKELY_DUPLICATE_THRESHOLD:
            return (True, similarity, DuplicateDecision.LIKELY_DUPLICATE)
        else:
            return (False, similarity, DuplicateDecision.NOT_DUPLICATE)


class TwoStageDeduplicator:
    """
    Complete two-stage deduplication pipeline.

    Spec: Dossier Appendix C.4.1.2

    Algorithm:
    1. Stage 1: SimHash filter (fast O(n)) - eliminates 99%+ non-candidates
    2. Stage 2: Embedding verification (accurate) - confirms true duplicates
    3. Fallback: High embedding similarity even if SimHash missed

    Performance (from Dossier C.4.1.2):
    | Method       | Complexity | Precision | Recall | Best For        |
    |--------------|------------|-----------|--------|-----------------|
    | SimHash only | O(n)       | 0.85      | 0.90   | Fast, syntactic |
    | Embedding    | O(n^2)     | 0.95      | 0.98   | Accurate, slow  |
    | Two-stage    | O(n + k)   | 0.93      | 0.95   | Balanced        |

    Where k ~ 0.01n (candidates from Stage 1).
    """

    def __init__(self, simhasher: Optional[SimHasher] = None):
        """
        Initialize the two-stage deduplicator.

        Args:
            simhasher: Optional SimHasher instance (creates new if not provided)
        """
        self.simhasher = simhasher or SimHasher()
        self.stage1 = Stage1SimHashFilter(self.simhasher)
        self.stage2 = Stage2EmbeddingVerifier()

    def find_duplicates(
        self,
        new_event: EventStateProtocol,
        window_events: List[EventStateProtocol],
        include_fallback: bool = True,
    ) -> List[DuplicateMatch]:
        """
        Find all duplicates of new_event using two-stage pipeline.

        Algorithm (from Dossier C.4.1.2):
        1. Stage 1: SimHash filter (fast O(n))
        2. Stage 2: Embedding verification (accurate)
        3. Fallback: High embedding similarity even if SimHash missed

        Args:
            new_event: The new event to check for duplicates
            window_events: List of recent events in the dedup window
            include_fallback: Whether to check embedding fallback for missed duplicates

        Returns:
            List of DuplicateMatch objects for all found duplicates
        """
        matches: List[DuplicateMatch] = []

        # Get content-type threshold
        content_type = new_event.content_type or "CHAT_MESSAGE"
        threshold = self.simhasher.get_threshold(content_type)

        # Stage 1: SimHash filter
        candidates = self.stage1.find_candidates(new_event, window_events, threshold)

        # Build lookup for Stage 2
        event_map = {e.event_id: e for e in window_events}

        # Stage 2: Embedding verification
        for event_id, hamming_dist in candidates:
            event = event_map.get(event_id)
            if not event:
                continue

            is_dup, similarity, decision = self.stage2.verify_duplicate(new_event, event)

            if is_dup:
                matches.append(
                    DuplicateMatch(
                        event_id=event_id,
                        hamming_distance=hamming_dist,
                        embedding_similarity=similarity,
                        decision_type=decision,
                        check_method="TWO_STAGE",
                    )
                )

        # Fallback: Check high embedding similarity even if SimHash missed
        # This catches semantic duplicates like "Had pizza" vs "Ate pizza"
        if include_fallback:
            candidate_ids: Set[str] = {c[0] for c in candidates}
            fallback_matches = self._check_embedding_fallback(
                new_event, window_events, candidate_ids
            )
            matches.extend(fallback_matches)

        return matches

    def _check_embedding_fallback(
        self,
        new_event: EventStateProtocol,
        window_events: List[EventStateProtocol],
        already_checked: Set[str],
    ) -> List[DuplicateMatch]:
        """
        Check for semantic duplicates missed by SimHash.

        This catches paraphrases where the text is syntactically different
        but semantically identical.

        Args:
            new_event: The new event
            window_events: All events in the window
            already_checked: Event IDs already checked by Stage 1/2

        Returns:
            List of DuplicateMatch objects for semantic duplicates
        """
        matches: List[DuplicateMatch] = []

        if new_event.embedding_768 is None:
            return matches

        for event in window_events:
            # Skip already checked, self, and events without embeddings
            if event.event_id in already_checked:
                continue
            if event.event_id == new_event.event_id:
                continue
            if event.embedding_768 is None:
                continue

            # Quick cosine check
            similarity = Stage2EmbeddingVerifier.cosine_similarity(
                new_event.embedding_768, event.embedding_768
            )

            if similarity >= Stage2EmbeddingVerifier.SEMANTIC_FALLBACK_THRESHOLD:
                matches.append(
                    DuplicateMatch(
                        event_id=event.event_id,
                        hamming_distance=None,  # Not checked by SimHash
                        embedding_similarity=similarity,
                        decision_type=DuplicateDecision.SEMANTIC_DUPLICATE,
                        check_method="EMBEDDING_FALLBACK",
                    )
                )

        return matches

    def find_best_duplicate(
        self,
        new_event: EventStateProtocol,
        window_events: List[EventStateProtocol],
    ) -> Optional[DuplicateMatch]:
        """
        Find the single best duplicate match (highest similarity).

        Args:
            new_event: The new event
            window_events: Events in the dedup window

        Returns:
            Best DuplicateMatch or None if no duplicates found
        """
        matches = self.find_duplicates(new_event, window_events)

        if not matches:
            return None

        # Sort by similarity (descending)
        return max(matches, key=lambda m: m.embedding_similarity)


async def find_duplicates_async(
    deduplicator: TwoStageDeduplicator,
    new_event: EventStateProtocol,
    window_events: List[EventStateProtocol],
) -> List[DuplicateMatch]:
    """
    Async wrapper for find_duplicates (CPU-bound work is still sync).

    For true async, consider offloading to ProcessPool for large windows.

    Args:
        deduplicator: TwoStageDeduplicator instance
        new_event: The new event
        window_events: Events in the dedup window

    Returns:
        List of DuplicateMatch objects
    """
    # Currently the work is CPU-bound (numpy), so this is just a thin wrapper.
    # For production, consider ProcessPoolExecutor for large windows.
    return deduplicator.find_duplicates(new_event, window_events)
