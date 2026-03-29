"""
TextRank Extractive Summarization — GAP-001 Milestone 2

Implements TextRank algorithm for extracting key sentences
from a collection of source texts. Used when episodes have
too many events to concatenate directly.

GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING.md §4
Milestone: GAP_001_MILESTONE_2_SUMMARY_GENERATOR.md Issue 2.8

Algorithm:
    1. Build TF-IDF vectors for each sentence
    2. Compute cosine similarity matrix
    3. Run PageRank on similarity graph
    4. Return top-k sentences by rank

Dependencies:
    - numpy (already in requirements.txt)
    - sklearn (TfidfVectorizer) - needs to be added if missing
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

try:
    import numpy as np
    from numpy.typing import NDArray
except ImportError:
    np = None  # type: ignore
    NDArray = None  # type: ignore

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


def textrank_summarize(
    texts: List[str],
    top_k: int = 3,
    damping: float = 0.85,
    max_iterations: int = 100,
    convergence_threshold: float = 1e-4,
) -> List[str]:
    """
    Extract the most representative sentences using TextRank.

    Args:
        texts: List of source texts (sentences or short paragraphs)
        top_k: Number of sentences to return
        damping: PageRank damping factor (0.85 is standard)
        max_iterations: Maximum PageRank iterations
        convergence_threshold: Stop when scores change less than this

    Returns:
        List of top_k most representative texts in original order

    Example:
        >>> texts = [
        ...     "Had dinner with mom at Thai restaurant",
        ...     "Ordered pad thai and green curry",
        ...     "Mom talked about her garden",
        ...     "Really enjoyed the spring rolls",
        ...     "Drove home after dinner",
        ...     "Called dad to check in",
        ... ]
        >>> summary = textrank_summarize(texts, top_k=2)
        >>> # Returns most representative sentences
    """
    if not texts:
        return []

    if len(texts) <= top_k:
        return texts

    # Fallback if sklearn/numpy not available
    if not SKLEARN_AVAILABLE or np is None:
        return _fallback_summarize(texts, top_k)

    # Clean and prepare texts
    clean_texts = [_clean_for_tfidf(t) for t in texts]

    # Filter out empty texts but keep index mapping
    valid_indices = [i for i, t in enumerate(clean_texts) if t.strip()]
    valid_texts = [clean_texts[i] for i in valid_indices]

    if len(valid_texts) <= top_k:
        return [texts[i] for i in valid_indices[:top_k]]

    try:
        # Build TF-IDF matrix
        vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=1000,
            ngram_range=(1, 2),
        )
        tfidf_matrix = vectorizer.fit_transform(valid_texts)

        # Compute similarity matrix
        similarity_matrix = cosine_similarity(tfidf_matrix)

        # Run PageRank
        scores = _pagerank(
            similarity_matrix,
            damping=damping,
            max_iterations=max_iterations,
            convergence_threshold=convergence_threshold,
        )

        # Get top-k indices by score
        ranked_indices = np.argsort(scores)[::-1][:top_k]

        # Sort by original order
        sorted_indices = sorted(ranked_indices)

        # Map back to original indices and return
        return [texts[valid_indices[i]] for i in sorted_indices]

    except Exception:
        # Fallback on any error
        return _fallback_summarize(texts, top_k)


def _pagerank(
    similarity_matrix: "NDArray[np.floating]",
    damping: float = 0.85,
    max_iterations: int = 100,
    convergence_threshold: float = 1e-4,
) -> "NDArray[np.floating]":
    """
    Run PageRank algorithm on similarity matrix.

    Args:
        similarity_matrix: NxN similarity matrix
        damping: Damping factor (probability of following link)
        max_iterations: Maximum iterations
        convergence_threshold: Convergence threshold

    Returns:
        Array of PageRank scores for each node
    """
    n = similarity_matrix.shape[0]

    # Initialize scores uniformly
    scores = np.ones(n) / n

    # Normalize similarity matrix by row sums
    row_sums = similarity_matrix.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1  # Avoid division by zero
    transition_matrix = similarity_matrix / row_sums

    # Power iteration
    for _ in range(max_iterations):
        prev_scores = scores.copy()

        # PageRank formula: (1-d)/N + d * sum(transition * scores)
        scores = (1 - damping) / n + damping * transition_matrix.T.dot(scores)

        # Check convergence
        if np.abs(scores - prev_scores).sum() < convergence_threshold:
            break

    return scores


def _clean_for_tfidf(text: str) -> str:
    """Clean text for TF-IDF vectorization."""
    # Remove URLs
    text = re.sub(r"https?://\S+", "", text)
    # Remove special characters but keep spaces
    text = re.sub(r"[^\w\s]", " ", text)
    # Normalize whitespace
    text = " ".join(text.split())
    return text.lower()


def _fallback_summarize(texts: List[str], top_k: int) -> List[str]:
    """
    Fallback when sklearn is not available.

    Uses simple heuristics:
    - Prefer longer texts (more information)
    - Prefer texts with more unique words
    """
    if len(texts) <= top_k:
        return texts

    # Score by length and word diversity
    scores: List[Tuple[int, float]] = []
    for i, text in enumerate(texts):
        words = text.lower().split()
        unique_ratio = len(set(words)) / max(len(words), 1)
        length_score = min(len(text), 200) / 200  # Cap length score
        score = length_score * 0.4 + unique_ratio * 0.6
        scores.append((i, score))

    # Sort by score and get top-k indices
    ranked = sorted(scores, key=lambda x: x[1], reverse=True)[:top_k]

    # Return in original order
    indices = sorted([idx for idx, _ in ranked])
    return [texts[i] for i in indices]


def narrative_arc_summarize(
    texts: List[str],
    emotion_scores: Optional[List[float]] = None,
) -> List[str]:
    """
    Extract narrative arc: first event, peak emotion, last event.

    Used for long episodes to capture the story structure.

    Args:
        texts: List of source texts in chronological order
        emotion_scores: Optional emotion intensity scores per text

    Returns:
        List of 3 texts representing the narrative arc
    """
    if not texts:
        return []

    if len(texts) <= 3:
        return texts

    result: List[str] = []

    # First event (opening)
    result.append(texts[0])

    # Peak emotion (middle)
    if emotion_scores and len(emotion_scores) == len(texts):
        # Find peak emotion (excluding first and last)
        middle_scores = emotion_scores[1:-1]
        if middle_scores:
            peak_idx = middle_scores.index(max(middle_scores)) + 1
            if texts[peak_idx] not in result:
                result.append(texts[peak_idx])
    else:
        # Without emotion scores, take middle text
        mid_idx = len(texts) // 2
        if texts[mid_idx] not in result:
            result.append(texts[mid_idx])

    # Last event (conclusion)
    if texts[-1] not in result:
        result.append(texts[-1])

    return result
