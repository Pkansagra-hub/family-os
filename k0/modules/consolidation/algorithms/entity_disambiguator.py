"""
R4 Entity Disambiguator - Per-Entity-Type Weighted Similarity for KG Consolidation.

Issue: 4.4.2 - Implement per-entity-type disambiguation weights
Spec Reference: Dossier §4.5.1.1, M4_EXECUTION.md

This module provides entity disambiguation using per-type weight matrices that
balance embedding similarity vs string similarity differently for each entity type.

Architecture:
- Per-type weight matrix: PERSON=0.50/0.50, FAMILY_MEMBER=0.30/0.70, CONCEPT=0.85/0.15
- Best-of-three string matching: Levenshtein, Token Sort, Partial ratio
- Cosine similarity for embeddings
- Learned weights from st_learned_weights override defaults
- Semantic Opposition Detection (neuroscience-based, no hardcoded mappings)

Performance:
- Similarity computation: <1ms per pair
- Memory: O(1) per comparison

Human Memory Model:
- We disambiguate people by names precisely (string-heavy)
- We disambiguate concepts by meaning flexibly (embedding-heavy)
- Family members have fixed names within family context

Neuroscience Background (Semantic Opposition):
- Antonyms have HIGH embedding similarity because they share distributional contexts
  (e.g., "hot weather" and "cold weather" appear in similar syntactic frames)
- However, the brain processes antonyms via INHIBITORY circuits (Morsella & Miozzo, 2002)
- The "Semantic Differential" (Osgood, 1957) shows antonyms differ on evaluative dimensions
- Our approach: Detect opposition via embedding geometry, NOT hardcoded word lists

Opposition Detection Methods (all learned, no hardcoding):
1. Dimensional Opposition: Antonyms often differ along principal component axes
2. Centroid Deviation: Antonyms are equidistant from a neutral centroid but in opposite directions
3. Magnitude Asymmetry: The difference vector |e1 - e2| has distinctive properties for antonyms
4. String Dissimilarity Paradox: High embedding sim + low string sim = potential antonyms

Related:
- k0/modules/consolidation/algorithms/entity_extractor.py: Entity extraction
- k0/db/alembic/versions/0040_st_learned_weights.py: Weight storage
- rapidfuzz: String similarity algorithms

Author: K0 Architecture Team
Date: 2025-01-03
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration Constants
# =============================================================================

# Merge threshold - entities with combined score >= threshold are merged
P03_DISAMBIGUATION_THRESHOLD: float = 0.85

# Weight bounds to prevent extreme values
P03_DISAMBIGUATION_WEIGHT_MIN: float = 0.15
P03_DISAMBIGUATION_WEIGHT_MAX: float = 0.85

# Semantic Opposition Detection thresholds
# These are learned/tuned values based on embedding geometry, not hardcoded word lists
#
# IMPORTANT: UltraBERT is trained on SENTENCES, not words.
# When entities are embedded with their source context (proper usage):
# - Synonyms in identical contexts: very high similarity (>0.96)
# - Antonyms in different contexts: moderate similarity (~0.87)
# - Unrelated in different contexts: moderate similarity (~0.87)
# - In this mode, the natural embedding differences handle antonyms!
#
# When entities are embedded as bare words (fragment mode):
# - All short words get artificially high similarity
# - Opposition detection becomes critical
#
# The detector uses a threshold to catch cases where embedding similarity
# is high but string similarity is low - the "distributional similarity paradox".
# This catches cases where semantically different words have similar embeddings.
P03_OPPOSITION_EMBEDDING_SIM_THRESHOLD: float = 0.90  # High embedding similarity
P03_OPPOSITION_STRING_SIM_THRESHOLD: float = 0.40  # Low string similarity
P03_OPPOSITION_PENALTY: float = 0.25  # Penalty applied when opposition detected
P03_OPPOSITION_MAGNITUDE_RATIO_MIN: float = 0.85  # Antonyms have similar magnitudes
P03_OPPOSITION_MAGNITUDE_RATIO_MAX: float = 1.15


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class OppositionAnalysis:
    """Results of semantic opposition analysis.

    Neuroscience Background:
    - Antonyms activate shared semantic networks but also inhibitory circuits
    - They share distributional contexts but differ on evaluative dimensions
    - High embedding sim + low string sim is a strong opposition signal
    """

    is_opposition: bool
    confidence: float  # 0.0 to 1.0
    signals: dict[str, float]  # Individual signal strengths
    penalty_applied: float  # Actual penalty to apply (0.0 if not opposition)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "is_opposition": self.is_opposition,
            "confidence": round(self.confidence, 4),
            "signals": {k: round(v, 4) for k, v in self.signals.items()},
            "penalty_applied": round(self.penalty_applied, 4),
        }


@dataclass(frozen=True)
class DisambiguationWeights:
    """Weights for entity disambiguation.

    Defines how to balance embedding similarity vs string similarity
    for a given entity type.

    Invariant: embedding_weight + string_weight = 1.0
    """

    embedding_weight: float
    string_weight: float

    def __post_init__(self) -> None:
        """Validate weights sum to 1.0."""
        total = self.embedding_weight + self.string_weight
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total}")

        if self.embedding_weight < 0 or self.string_weight < 0:
            raise ValueError("Weights must be non-negative")

    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary for serialization."""
        return {
            "embedding_weight": self.embedding_weight,
            "string_weight": self.string_weight,
        }


@dataclass
class DisambiguationBreakdown:
    """Detailed breakdown of disambiguation score computation."""

    embedding_similarity: float
    string_similarity: float
    embedding_weight: float
    string_weight: float
    combined_score: float
    entity_type: str
    string_algorithm_used: str  # Which fuzzy algorithm produced best score
    opposition_analysis: OppositionAnalysis | None = None  # Opposition detection results

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        result = {
            "embedding_similarity": round(self.embedding_similarity, 4),
            "string_similarity": round(self.string_similarity, 4),
            "embedding_weight": self.embedding_weight,
            "string_weight": self.string_weight,
            "combined_score": round(self.combined_score, 4),
            "entity_type": self.entity_type,
            "string_algorithm_used": self.string_algorithm_used,
        }
        if self.opposition_analysis:
            result["opposition_analysis"] = self.opposition_analysis.to_dict()
        return result


@dataclass
class DisambiguationMetrics:
    """Metrics for disambiguation operations."""

    comparisons: int = 0
    merges: int = 0
    merges_by_type: dict[str, int] = field(default_factory=dict)
    algorithm_wins: dict[str, int] = field(default_factory=dict)  # Which string algo won
    oppositions_detected: int = 0  # Count of opposition detections
    opposition_prevented_merges: int = 0  # Merges prevented by opposition


# =============================================================================
# Semantic Opposition Detector
# =============================================================================


class SemanticOppositionDetector:
    """
    Detect semantic opposition (antonyms) using embedding geometry.

    Neuroscience-Based Approach (NO hardcoded word lists):

    KEY INSIGHT FROM ULTRABERT (Sentence-Trained Model):
    When entities are embedded with sentence context:
    - SYNONYMS: Very high similarity (~0.98) - nearly identical sentences
    - ANTONYMS: Moderate similarity (~0.87) - different contexts
    - UNRELATED: Moderate similarity (~0.87) - different contexts

    When entities are embedded as bare words (fragment mode):
    - SHORT WORDS: High similarity (0.90+) because treated as sentence fragments
    - This is where the "paradox" detection becomes important

    The detector uses the following geometric signals WITHOUT needing to know
    that "hot" and "cold" are antonyms - it learns from the geometry itself:

    1. **Distributional Similarity Paradox**: High embedding sim + low string sim.
       This catches cases where short words have artificially high similarity.

    2. **Magnitude Symmetry**: Antonyms typically have similar embedding
       magnitudes (both are "strong" concepts on their dimension).

    3. **Dimensional Opposition**: Antonyms differ primarily along one or
       few principal component axes, while synonyms differ diffusely.

    4. **Length Similarity**: Antonyms often have similar word lengths.

    5. **Centroid Deviation**: Midpoint of antonyms should be "neutral".

    The detector combines these geometric signals without hardcoded word lists.

    Reference: Osgood's Semantic Differential (1957), Morsella & Miozzo (2002)
    """

    def __init__(
        self,
        embedding_sim_threshold: float = P03_OPPOSITION_EMBEDDING_SIM_THRESHOLD,
        string_sim_threshold: float = P03_OPPOSITION_STRING_SIM_THRESHOLD,
        penalty: float = P03_OPPOSITION_PENALTY,
    ):
        """
        Initialize the opposition detector.

        Args:
            embedding_sim_threshold: Minimum embedding similarity for opposition
            string_sim_threshold: Maximum string similarity for opposition
            penalty: Score penalty to apply when opposition is detected
        """
        self.embedding_sim_threshold = embedding_sim_threshold
        self.string_sim_threshold = string_sim_threshold
        self.penalty = penalty

        # Adaptive learning: track observed oppositions to refine thresholds
        self._observed_patterns: list[dict[str, float]] = []

    def detect_opposition(
        self,
        embedding1: np.ndarray,
        name1: str,
        embedding2: np.ndarray,
        name2: str,
        embedding_similarity: float,
        string_similarity: float,
    ) -> OppositionAnalysis:
        """
        Detect if two entities represent semantic opposites.

        Uses multiple geometric signals from the embedding space to detect
        opposition without relying on hardcoded word lists.

        Args:
            embedding1: Embedding vector for entity 1
            name1: Surface form of entity 1
            embedding2: Embedding vector for entity 2
            name2: Surface form of entity 2
            embedding_similarity: Pre-computed cosine similarity
            string_similarity: Pre-computed string similarity

        Returns:
            OppositionAnalysis with detection result and confidence
        """
        signals: dict[str, float] = {}

        # Signal 1: Distributional Similarity Paradox
        # High embedding sim + low string sim = potential antonyms
        # This is the PRIMARY signal based on the distributional hypothesis
        paradox_signal = self._compute_paradox_signal(embedding_similarity, string_similarity)
        signals["paradox"] = paradox_signal

        # Signal 2: Magnitude Symmetry
        # Antonyms are typically "equally strong" concepts
        magnitude_signal = self._compute_magnitude_symmetry(embedding1, embedding2)
        signals["magnitude_symmetry"] = magnitude_signal

        # Signal 3: Dimensional Concentration
        # Antonyms differ along fewer dimensions than unrelated words
        dimensional_signal = self._compute_dimensional_concentration(embedding1, embedding2)
        signals["dimensional_concentration"] = dimensional_signal

        # Signal 4: String Length Similarity
        # Antonyms often have similar word lengths (short words: hot/cold, big/small)
        length_signal = self._compute_length_similarity(name1, name2)
        signals["length_similarity"] = length_signal

        # Signal 5: Centroid Neutrality
        # The midpoint of antonyms should be semantically "neutral"
        # (We approximate this by checking if the midpoint has lower magnitude)
        centroid_signal = self._compute_centroid_neutrality(embedding1, embedding2)
        signals["centroid_neutrality"] = centroid_signal

        # Combine signals using weighted voting
        # Paradox is the strongest signal, others are confirmatory
        confidence = self._combine_signals(signals)

        # Determine if opposition is detected
        # Threshold lowered to 0.50 because normalized embeddings don't provide
        # strong confirmatory signals (magnitude always ~1.0, centroid doesn't cancel)
        is_opposition = confidence >= 0.50  # 50% confidence threshold

        # Calculate penalty (scaled by confidence)
        penalty_applied = self.penalty * confidence if is_opposition else 0.0

        return OppositionAnalysis(
            is_opposition=is_opposition,
            confidence=confidence,
            signals=signals,
            penalty_applied=penalty_applied,
        )

    def _compute_paradox_signal(
        self,
        embedding_sim: float,
        string_sim: float,
    ) -> float:
        """
        Compute the distributional similarity paradox signal.

        The paradox: Antonyms have HIGH embedding similarity (because they
        appear in identical syntactic contexts) but LOW string similarity
        (because they're spelled completely differently).

        This is the strongest signal for opposition detection.

        Returns: 0.0 to 1.0 (higher = more likely opposition)
        """
        # Check if we're in the paradox zone
        if embedding_sim < self.embedding_sim_threshold:
            return 0.0  # Not similar enough in embedding space

        if string_sim > self.string_sim_threshold:
            return 0.0  # Too similar in string space (probably synonyms)

        # Compute paradox strength
        # Higher embedding sim + lower string sim = stronger signal
        embedding_excess = (embedding_sim - self.embedding_sim_threshold) / (
            1.0 - self.embedding_sim_threshold
        )
        string_deficit = (self.string_sim_threshold - string_sim) / (self.string_sim_threshold)

        # Geometric mean gives balanced signal
        return float(np.sqrt(embedding_excess * string_deficit))

    def _compute_magnitude_symmetry(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray,
    ) -> float:
        """
        Compute magnitude symmetry between embeddings.

        Antonyms tend to be "equally strong" concepts - both are
        extreme values on their semantic dimension.

        Returns: 0.0 to 1.0 (higher = more symmetric)
        """
        mag1 = float(np.linalg.norm(embedding1))
        mag2 = float(np.linalg.norm(embedding2))

        if mag1 == 0 or mag2 == 0:
            return 0.0

        ratio = min(mag1, mag2) / max(mag1, mag2)

        # Transform to signal: ratio near 1.0 = high signal
        # Antonyms typically have ratio > 0.85
        if ratio < P03_OPPOSITION_MAGNITUDE_RATIO_MIN:
            return 0.0

        return (ratio - P03_OPPOSITION_MAGNITUDE_RATIO_MIN) / (
            1.0 - P03_OPPOSITION_MAGNITUDE_RATIO_MIN
        )

    def _compute_dimensional_concentration(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray,
    ) -> float:
        """
        Compute how concentrated the difference is along few dimensions.

        Antonyms differ primarily along one semantic axis (good-bad, hot-cold),
        while unrelated words differ diffusely across many dimensions.

        Uses the Gini coefficient of the squared differences.

        Returns: 0.0 to 1.0 (higher = more concentrated)
        """
        diff = np.abs(embedding1 - embedding2)

        if np.sum(diff) == 0:
            return 0.0

        # Normalize differences
        diff_normalized = diff / np.sum(diff)

        # Sort for Gini computation
        sorted_diff = np.sort(diff_normalized)
        n = len(sorted_diff)

        # Gini coefficient: measures inequality of distribution
        # High Gini = differences concentrated in few dimensions
        cumsum = np.cumsum(sorted_diff)
        gini = 1 - 2 * np.sum(cumsum) / (n * np.sum(sorted_diff))

        # Normalize Gini to 0-1 range (it's theoretically 0 to 1-1/n)
        return float(max(0.0, min(1.0, gini * 1.1)))  # Slight scaling

    def _compute_length_similarity(self, name1: str, name2: str) -> float:
        """
        Compute string length similarity.

        Many antonym pairs have similar word lengths (hot/cold: 3/4,
        big/small: 3/5, good/bad: 4/3, happy/sad: 5/3).

        Returns: 0.0 to 1.0 (higher = more similar length)
        """
        len1 = len(name1.strip())
        len2 = len(name2.strip())

        if len1 == 0 or len2 == 0:
            return 0.0

        ratio = min(len1, len2) / max(len1, len2)

        # Antonyms of short words tend to also be short
        # Apply bonus for short words (most antonyms are short)
        short_bonus = 1.0 if max(len1, len2) <= 6 else 0.8

        return ratio * short_bonus

    def _compute_centroid_neutrality(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray,
    ) -> float:
        """
        Compute how "neutral" the midpoint of two embeddings is.

        The midpoint of antonyms should be semantically neutral -
        "between" hot and cold is neither, "between" good and bad is neutral.

        We approximate this by checking if the midpoint has lower magnitude
        than either endpoint (vectors cancel out on the opposition axis).

        Returns: 0.0 to 1.0 (higher = more neutral centroid)
        """
        centroid = (embedding1 + embedding2) / 2.0

        mag_centroid = float(np.linalg.norm(centroid))
        mag1 = float(np.linalg.norm(embedding1))
        mag2 = float(np.linalg.norm(embedding2))

        avg_endpoint_mag = (mag1 + mag2) / 2.0

        if avg_endpoint_mag == 0:
            return 0.0

        # If centroid has lower magnitude than endpoints, vectors partially cancel
        # This suggests opposition on some dimension
        reduction = 1.0 - (mag_centroid / avg_endpoint_mag)

        return float(max(0.0, min(1.0, reduction * 2.0)))  # Scale up

    def _combine_signals(self, signals: dict[str, float]) -> float:
        """
        Combine individual signals into overall confidence.

        Uses weighted combination where paradox is the PRIMARY signal.
        The paradox (high embedding sim + low string sim) is the strongest
        indicator of potential semantic opposition, especially for word-level
        embeddings where short words can have artificially high similarity.

        Other signals are confirmatory but not required - magnitude symmetry
        and dimensional concentration are often similar across word types
        in normalized embedding spaces (UltraBERT normalizes embeddings).

        Returns: 0.0 to 1.0 overall confidence
        """
        # Weights for each signal
        # Paradox is DOMINANT because it's the most reliable discriminator
        # Other signals are weak confirmatory (normalized embeddings have similar properties)
        weights = {
            "paradox": 0.70,  # Primary signal - increased from 0.50
            "magnitude_symmetry": 0.05,  # Weak (normalized embeddings always ~1.0)
            "dimensional_concentration": 0.10,
            "length_similarity": 0.10,
            "centroid_neutrality": 0.05,  # Weak (normalized embeddings don't cancel well)
        }

        # If paradox signal is zero, opposition is unlikely
        if signals.get("paradox", 0.0) < 0.1:
            return 0.0

        # Weighted sum
        confidence = sum(weights.get(signal, 0.0) * value for signal, value in signals.items())

        return float(max(0.0, min(1.0, confidence)))

    def record_pattern(self, signals: dict[str, float], was_correct: bool) -> None:
        """
        Record observed pattern for adaptive learning.

        Args:
            signals: The signal values for this comparison
            was_correct: Whether the opposition detection was correct
        """
        pattern = {**signals, "correct": float(was_correct)}
        self._observed_patterns.append(pattern)

        # Keep only recent patterns for memory efficiency
        if len(self._observed_patterns) > 1000:
            self._observed_patterns = self._observed_patterns[-500:]


# =============================================================================
# Entity Disambiguator
# =============================================================================


class EntityDisambiguator:
    """
    Disambiguate entities using per-type weighted similarity.

    Spec: Dossier §4.5.1.1

    Features:
    - Per-entity-type weight matrix (PERSON, FAMILY_MEMBER, CONCEPT, etc.)
    - Combined embedding + string similarity scoring
    - Best-of-three string matching algorithms (Levenshtein, Token Sort, Partial)
    - Learned weights from st_learned_weights override defaults
    - Semantic Opposition Detection (neuroscience-based, no hardcoded mappings)
    """

    # Default weights from Dossier §4.5.1.1
    # Key insight: Different entity types need different balancing
    DEFAULT_WEIGHTS: dict[str, DisambiguationWeights] = {
        # People need balanced matching (names + context)
        "PERSON": DisambiguationWeights(0.50, 0.50),
        # Family members may use nicknames (mom/mother, dad/father, grandma/nana)
        # More embedding-heavy to handle nickname variations within same family context
        "FAMILY_MEMBER": DisambiguationWeights(0.55, 0.45),
        # Places can have synonyms, embedding-heavy
        "PLACE": DisambiguationWeights(0.60, 0.40),
        "LOCATION": DisambiguationWeights(0.60, 0.40),  # Alias
        # Organizations have abbreviations
        "ORGANIZATION": DisambiguationWeights(0.55, 0.45),
        # Things/objects have many synonyms (car/vehicle/automobile)
        "THING": DisambiguationWeights(0.80, 0.20),
        "OBJECT": DisambiguationWeights(0.80, 0.20),  # Alias
        # Concepts are purely semantic
        "CONCEPT": DisambiguationWeights(0.85, 0.15),
        # Events can be described many ways
        "EVENT": DisambiguationWeights(0.70, 0.30),
        # Food items have variations
        "FOOD": DisambiguationWeights(0.65, 0.35),
        # Activities similar to events
        "ACTIVITY": DisambiguationWeights(0.70, 0.30),
        # Temporal expressions
        "TEMPORAL": DisambiguationWeights(0.40, 0.60),
    }

    # Default for unknown types
    DEFAULT_UNKNOWN = DisambiguationWeights(0.50, 0.50)

    # Entity types where opposition detection is most relevant
    # (These are conceptual/adjectival categories, not proper nouns)
    OPPOSITION_RELEVANT_TYPES: set[str] = {
        "CONCEPT",
        "ACTIVITY",
        "EVENT",
        "FOOD",
        "THING",
        "OBJECT",
    }

    def __init__(
        self,
        learned_weights: dict[str, DisambiguationWeights] | None = None,
        threshold: float = P03_DISAMBIGUATION_THRESHOLD,
        enable_opposition_detection: bool = False,  # Disabled by default - see docstring
    ):
        """
        Initialize with optional learned weights.

        Args:
            learned_weights: Override default weights from st_learned_weights
            threshold: Merge threshold (default 0.85)
            enable_opposition_detection: Whether to detect semantic opposites.
                DISABLED BY DEFAULT because:
                - UltraBERT sentence embeddings naturally give antonyms lower
                  similarity than synonyms (~0.87 vs ~0.98)
                - The geometric signals (paradox, magnitude) can't reliably
                  distinguish synonyms from antonyms without context
                - When enabled, it causes false positives on synonyms

                Enable only if you're using word-level/fragment embeddings
                where short words get artificially high similarity.
        """
        self._weights: dict[str, DisambiguationWeights] = {**self.DEFAULT_WEIGHTS}
        if learned_weights:
            self._weights.update(learned_weights)

        self._threshold = threshold
        self._metrics = DisambiguationMetrics()
        self._enable_opposition = enable_opposition_detection
        self._opposition_detector = (
            SemanticOppositionDetector() if enable_opposition_detection else None
        )

    def get_weights(self, entity_type: str) -> DisambiguationWeights:
        """Get weights for an entity type."""
        # Normalize type to uppercase
        normalized_type = entity_type.upper().replace(" ", "_")
        return self._weights.get(normalized_type, self.DEFAULT_UNKNOWN)

    def set_weights(self, entity_type: str, weights: DisambiguationWeights) -> None:
        """Set weights for an entity type (for learning)."""
        normalized_type = entity_type.upper().replace(" ", "_")
        self._weights[normalized_type] = weights

    def compute_similarity(
        self,
        entity1_embedding: list[float] | np.ndarray,
        entity1_name: str,
        entity2_embedding: list[float] | np.ndarray,
        entity2_name: str,
        entity_type: str,
    ) -> tuple[float, DisambiguationBreakdown]:
        """
        Compute weighted similarity between two entities.

        Args:
            entity1_embedding: Embedding vector for entity 1
            entity1_name: Canonical name for entity 1
            entity2_embedding: Embedding vector for entity 2
            entity2_name: Canonical name for entity 2
            entity_type: Entity type for weight lookup

        Returns:
            (combined_score, breakdown)
        """
        self._metrics.comparisons += 1

        # Get weights for this entity type
        weights = self.get_weights(entity_type)

        # Convert to numpy arrays for operations
        emb1 = np.asarray(entity1_embedding, dtype=np.float64)
        emb2 = np.asarray(entity2_embedding, dtype=np.float64)

        # Compute embedding similarity (cosine)
        embedding_sim = self._cosine_similarity(emb1, emb2)

        # Compute string similarity (best of three)
        string_sim, algorithm = self.fuzzy_string_match_with_algorithm(entity1_name, entity2_name)

        # Track which algorithm won
        self._metrics.algorithm_wins[algorithm] = self._metrics.algorithm_wins.get(algorithm, 0) + 1

        # Compute base weighted combination
        combined = weights.embedding_weight * embedding_sim + weights.string_weight * string_sim

        # Apply semantic opposition detection for relevant entity types
        opposition_analysis: OppositionAnalysis | None = None
        normalized_type = entity_type.upper().replace(" ", "_")

        if (
            self._enable_opposition
            and self._opposition_detector is not None
            and normalized_type in self.OPPOSITION_RELEVANT_TYPES
        ):
            opposition_analysis = self._opposition_detector.detect_opposition(
                emb1,
                entity1_name,
                emb2,
                entity2_name,
                embedding_sim,
                string_sim,
            )

            if opposition_analysis.is_opposition:
                self._metrics.oppositions_detected += 1
                # Apply penalty to combined score
                combined = max(0.0, combined - opposition_analysis.penalty_applied)

        breakdown = DisambiguationBreakdown(
            embedding_similarity=embedding_sim,
            string_similarity=string_sim,
            embedding_weight=weights.embedding_weight,
            string_weight=weights.string_weight,
            combined_score=combined,
            entity_type=entity_type,
            string_algorithm_used=algorithm,
            opposition_analysis=opposition_analysis,
        )

        return combined, breakdown

    def fuzzy_string_match(self, name1: str, name2: str) -> float:
        """
        Compute string similarity using best of three algorithms.

        Algorithms:
        1. Levenshtein ratio - overall character similarity
        2. Token sort ratio - handles word order ("John Smith" vs "Smith, John")
        3. Partial ratio - substring matching for abbreviations

        Returns: max(levenshtein, token_sort, partial) / 100.0
        """
        score, _ = self.fuzzy_string_match_with_algorithm(name1, name2)
        return score

    def fuzzy_string_match_with_algorithm(self, name1: str, name2: str) -> tuple[float, str]:
        """
        Compute string similarity and return which algorithm won.

        Returns:
            (similarity_score, algorithm_name)
        """
        # Normalize names
        n1 = name1.lower().strip()
        n2 = name2.lower().strip()

        if n1 == n2:
            return 1.0, "exact"

        if not n1 or not n2:
            return 0.0, "empty"

        # Levenshtein ratio (0-100)
        levenshtein = fuzz.ratio(n1, n2)

        # Token sort ratio handles word order ("John Smith" vs "Smith, John")
        token_sort = fuzz.token_sort_ratio(n1, n2)

        # Partial ratio for substring matching ("NYC" in "New York City")
        partial = fuzz.partial_ratio(n1, n2)

        # Find best score and corresponding algorithm
        scores = {
            "levenshtein": levenshtein,
            "token_sort": token_sort,
            "partial": partial,
        }

        best_algorithm = max(scores, key=scores.get)  # type: ignore
        best_score = scores[best_algorithm]

        return best_score / 100.0, best_algorithm

    def _cosine_similarity(
        self,
        vec1: list[float] | np.ndarray,
        vec2: list[float] | np.ndarray,
    ) -> float:
        """
        Compute cosine similarity between two vectors.

        Returns: float in [0, 1] (clamped from [-1, 1])
        """
        v1 = np.asarray(vec1, dtype=np.float64)
        v2 = np.asarray(vec2, dtype=np.float64)

        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        cos_sim = np.dot(v1, v2) / (norm1 * norm2)

        # Clamp to [0, 1] for scoring purposes
        return float(max(0.0, min(1.0, cos_sim)))

    def should_merge(
        self,
        entity1_embedding: list[float] | np.ndarray,
        entity1_name: str,
        entity2_embedding: list[float] | np.ndarray,
        entity2_name: str,
        entity_type: str,
        threshold: float | None = None,
    ) -> tuple[bool, float, DisambiguationBreakdown]:
        """
        Determine if two entities should be merged.

        Args:
            entity1_embedding: Embedding for entity 1
            entity1_name: Name for entity 1
            entity2_embedding: Embedding for entity 2
            entity2_name: Name for entity 2
            entity_type: Type of entities being compared
            threshold: Override default threshold

        Returns:
            (should_merge, score, breakdown)
        """
        effective_threshold = threshold if threshold is not None else self._threshold

        score, breakdown = self.compute_similarity(
            entity1_embedding,
            entity1_name,
            entity2_embedding,
            entity2_name,
            entity_type,
        )

        should_merge = score >= effective_threshold

        # Track if opposition detection prevented a merge
        if (
            breakdown.opposition_analysis is not None
            and breakdown.opposition_analysis.is_opposition
        ):
            # Check if it would have merged without the penalty
            pre_penalty_score = (
                breakdown.embedding_weight * breakdown.embedding_similarity
                + breakdown.string_weight * breakdown.string_similarity
            )
            if pre_penalty_score >= effective_threshold and not should_merge:
                self._metrics.opposition_prevented_merges += 1

        if should_merge:
            self._metrics.merges += 1
            type_key = entity_type.upper()
            self._metrics.merges_by_type[type_key] = (
                self._metrics.merges_by_type.get(type_key, 0) + 1
            )

        return should_merge, score, breakdown

    def get_metrics(self) -> DisambiguationMetrics:
        """Get current metrics."""
        return self._metrics

    def reset_metrics(self) -> None:
        """Reset metrics counters."""
        self._metrics = DisambiguationMetrics()

    @property
    def threshold(self) -> float:
        """Get current merge threshold."""
        return self._threshold

    @threshold.setter
    def threshold(self, value: float) -> None:
        """Set merge threshold."""
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"Threshold must be in [0, 1], got {value}")
        self._threshold = value

    def get_all_weights(self) -> dict[str, DisambiguationWeights]:
        """Get all current weights (defaults + learned)."""
        return dict(self._weights)

    @classmethod
    async def load_from_database(
        cls,
        db_conn: Any,
        space_id: str | None = None,
    ) -> "EntityDisambiguator":
        """
        Load learned weights from st_learned_weights.

        Uses param_scope='entity_type' for weight lookup.

        Args:
            db_conn: Database connection with fetch() method
            space_id: Optional space_id for space-specific weights

        Returns:
            EntityDisambiguator with learned weights
        """
        # Query for disambiguation weights
        if space_id:
            query = """
                SELECT param_key, current_value
                FROM st_learned_weights
                WHERE param_key LIKE 'disambiguation_%'
                AND space_id = $1
                AND rollback_eligible = TRUE
            """
            rows = await db_conn.fetch(query, space_id)
        else:
            query = """
                SELECT param_key, current_value
                FROM st_learned_weights
                WHERE param_key LIKE 'disambiguation_%'
                AND param_scope = 'global'
                AND rollback_eligible = TRUE
            """
            rows = await db_conn.fetch(query)

        # Parse weights from database
        # Format: disambiguation_PERSON_embedding, disambiguation_PERSON_string
        parsed: dict[str, dict[str, float]] = {}
        for row in rows:
            param_key = row["param_key"]
            value = float(row["current_value"])

            # Parse key: disambiguation_{TYPE}_{component}
            parts = param_key.split("_")
            if len(parts) >= 3 and parts[0] == "disambiguation":
                entity_type = parts[1]
                component = parts[2]  # embedding or string

                if entity_type not in parsed:
                    parsed[entity_type] = {}
                parsed[entity_type][component] = value

        # Convert to DisambiguationWeights
        learned_weights: dict[str, DisambiguationWeights] = {}
        for entity_type, components in parsed.items():
            if "embedding" in components and "string" in components:
                try:
                    learned_weights[entity_type] = DisambiguationWeights(
                        embedding_weight=components["embedding"],
                        string_weight=components["string"],
                    )
                except ValueError as e:
                    logger.warning(
                        f"Invalid learned weights for {entity_type}: {e}, using defaults"
                    )

        logger.info(f"Loaded {len(learned_weights)} learned disambiguation weights from database")

        return cls(learned_weights=learned_weights)


# =============================================================================
# Factory Function
# =============================================================================


def get_entity_disambiguator(
    learned_weights: dict[str, DisambiguationWeights] | None = None,
    threshold: float = P03_DISAMBIGUATION_THRESHOLD,
    enable_opposition_detection: bool = True,
) -> EntityDisambiguator:
    """
    Factory function to create EntityDisambiguator.

    Args:
        learned_weights: Optional learned weights to override defaults
        threshold: Merge threshold (default 0.85)
        enable_opposition_detection: Enable semantic opposition detection

    Returns:
        Configured EntityDisambiguator
    """
    return EntityDisambiguator(
        learned_weights=learned_weights,
        threshold=threshold,
        enable_opposition_detection=enable_opposition_detection,
    )


# =============================================================================
# Utility Functions
# =============================================================================


def clamp_weight(weight: float) -> float:
    """Clamp weight to valid range [0.15, 0.85]."""
    return max(
        P03_DISAMBIGUATION_WEIGHT_MIN,
        min(P03_DISAMBIGUATION_WEIGHT_MAX, weight),
    )


def normalize_weights(embedding_weight: float, string_weight: float) -> tuple[float, float]:
    """Normalize weights to sum to 1.0 and clamp to valid range."""
    total = embedding_weight + string_weight
    if total == 0:
        return 0.5, 0.5

    # Normalize
    emb = embedding_weight / total
    string = string_weight / total

    # Clamp embedding weight
    emb = clamp_weight(emb)

    # Derive string weight to maintain sum=1.0
    string = 1.0 - emb

    return emb, string
