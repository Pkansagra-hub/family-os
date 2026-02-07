"""
Write Gate - Deduplication and Quality Gate for Session State Writes
=====================================================================

Prevents redundant LLM tool writes by checking if the data already exists
in session state. This is a Tier-1 gate (fast, deterministic).

Gate Decisions:
- ACCEPT: Write proceeds (new data, confidence upgrade, or enhancement)
- REJECT: Write blocked (duplicate, lower confidence, no improvement)
- UPGRADE: Write proceeds with modification (merged data)

Benefits:
- Reduces tool calls and API latency
- Reduces state growth / memory pressure
- Improves belief quality (no spam)
- Makes LLM behavior production-ready

Usage:
    gate = WriteGate(session_manager)

    # Check before writing
    decision = gate.check_belief("has two children ages 8 and 12", "family", 0.8)
    if decision.allowed:
        # proceed with write
    else:
        # skip (decision.reason explains why)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Optional, Set, Tuple

if TYPE_CHECKING:
    from k1.sessionstate.manager import SessionStateManager


class GateDecision(Enum):
    """Possible gate decisions."""

    ACCEPT = "accept"  # New data, proceed with write
    REJECT = "reject"  # Duplicate or lower quality, block write
    UPGRADE = "upgrade"  # Merge/enhance existing data


@dataclass
class WriteDecision:
    """Result of a write gate check."""

    decision: GateDecision
    allowed: bool
    reason: str
    existing_data: Optional[Dict[str, Any]] = None
    similarity_score: float = 0.0

    @property
    def is_duplicate(self) -> bool:
        return self.decision == GateDecision.REJECT and "duplicate" in self.reason.lower()


@dataclass
class GateStats:
    """Statistics about gate decisions."""

    total_checks: int = 0
    accepted: int = 0
    rejected: int = 0
    upgraded: int = 0
    bytes_saved: int = 0  # Estimated bytes saved by rejecting duplicates

    @property
    def rejection_rate(self) -> float:
        if self.total_checks == 0:
            return 0.0
        return self.rejected / self.total_checks


# =============================================================================
# SIMILARITY UTILITIES
# =============================================================================


def normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    return " ".join(text.lower().split())


def tokenize(text: str) -> Set[str]:
    """Simple word tokenization."""
    normalized = normalize_text(text)
    # Remove common punctuation
    for char in ".,;:!?()[]{}\"'":
        normalized = normalized.replace(char, " ")
    return set(normalized.split())


def jaccard_similarity(text1: str, text2: str) -> float:
    """
    Compute Jaccard similarity between two texts.

    Returns value between 0.0 (no overlap) and 1.0 (identical).
    """
    tokens1 = tokenize(text1)
    tokens2 = tokenize(text2)

    if not tokens1 or not tokens2:
        return 0.0

    intersection = tokens1 & tokens2
    union = tokens1 | tokens2

    return len(intersection) / len(union)


def is_semantic_duplicate(text1: str, text2: str, threshold: float = 0.7) -> bool:
    """
    Check if two texts are semantic duplicates.

    Uses Jaccard similarity as a fast approximation.
    For production, could use embeddings.
    """
    return jaccard_similarity(text1, text2) >= threshold


def extract_key_facts(text: str) -> Set[str]:
    """
    Extract key facts from text for comparison.

    Identifies numbers, proper nouns (capitalized), and key patterns.
    """
    result: Set[str] = set()
    word_list = text.split()

    for i, word in enumerate(word_list):
        # Numbers (ages, prices, counts)
        if any(c.isdigit() for c in word):
            # Include context word before number if exists
            if i > 0:
                result.add(f"{word_list[i-1].lower()}_{word}")
            result.add(word)

        # Capitalized words (proper nouns, places)
        if word[0].isupper() and len(word) > 1:
            result.add(word.lower())

    return result


def facts_overlap(text1: str, text2: str) -> float:
    """
    Compute overlap of key facts between texts.

    More precise than Jaccard for structured facts.
    """
    facts1 = extract_key_facts(text1)
    facts2 = extract_key_facts(text2)

    if not facts1 or not facts2:
        return 0.0

    intersection = facts1 & facts2
    smaller = min(len(facts1), len(facts2))

    return len(intersection) / smaller if smaller > 0 else 0.0


# =============================================================================
# WRITE GATE
# =============================================================================


class WriteGate:
    """
    Tier-1 gate that prevents redundant writes to session state.

    Checks:
    - Exact duplicates (normalized string match)
    - Semantic duplicates (high Jaccard similarity)
    - Fact duplicates (same key facts like ages, names, numbers)
    - Confidence upgrades (allow if new confidence is higher)

    Configuration:
    - similarity_threshold: Jaccard threshold for semantic duplicates (default 0.7)
    - facts_threshold: Facts overlap threshold (default 0.8)
    - confidence_upgrade_margin: Min increase to allow upgrade (default 0.1)
    """

    def __init__(
        self,
        manager: "SessionStateManager",
        similarity_threshold: float = 0.7,
        facts_threshold: float = 0.8,
        confidence_upgrade_margin: float = 0.1,
    ):
        self._manager = manager
        self._similarity_threshold = similarity_threshold
        self._facts_threshold = facts_threshold
        self._confidence_margin = confidence_upgrade_margin
        self._stats = GateStats()

        # Cache of known beliefs for fast lookup
        self._belief_cache: Dict[str, Dict[str, Any]] = {}
        self._persona_cache: Dict[str, Any] = {}
        self._cache_valid = False

    def refresh_cache(self) -> None:
        """Refresh the internal cache from session state."""
        self._belief_cache.clear()
        self._persona_cache.clear()

        try:
            # Load beliefs
            beliefs = self._manager.get_section("beliefs_active")
            if hasattr(beliefs, "get_all_facts"):
                for fact in beliefs.get_all_facts():
                    key = normalize_text(str(fact))
                    self._belief_cache[key] = {
                        "fact": str(fact),
                        "confidence": getattr(fact, "confidence", 0.8),
                        "category": getattr(fact, "predicate", "general"),
                    }
            elif hasattr(beliefs, "_facts"):
                # _facts is a Dict[str, Fact] with UUID keys
                for fact_id, fact in beliefs._facts.items():
                    # Fact object uses 'object' attribute (not 'obj')
                    if hasattr(fact, "object"):
                        obj_text = fact.object
                        key = normalize_text(obj_text)
                        self._belief_cache[key] = {
                            "fact": obj_text,
                            "confidence": getattr(fact, "confidence", 0.8),
                            "category": getattr(fact, "predicate", "general"),
                        }
                    elif hasattr(fact, "obj"):
                        key = normalize_text(fact.obj)
                        self._belief_cache[key] = {
                            "fact": fact.obj,
                            "confidence": getattr(fact, "confidence", 0.8),
                            "category": getattr(fact, "predicate", "general"),
                        }
                    elif isinstance(fact, dict):
                        obj = fact.get("object", fact.get("obj", fact.get("fact", "")))
                        key = normalize_text(obj)
                        self._belief_cache[key] = {
                            "fact": obj,
                            "confidence": fact.get("confidence", 0.8),
                            "category": fact.get("category", fact.get("predicate", "general")),
                        }
        except Exception:
            pass

        try:
            # Load persona traits
            persona = self._manager.get_section("persona")
            if hasattr(persona, "_traits"):
                self._persona_cache = dict(persona._traits)
        except Exception:
            pass

        self._cache_valid = True

    def _ensure_cache(self) -> None:
        """Ensure cache is populated."""
        if not self._cache_valid:
            self.refresh_cache()

    # =========================================================================
    # BELIEF CHECKS
    # =========================================================================

    def check_belief(
        self,
        fact: str,
        category: str,
        confidence: float = 0.8,
    ) -> WriteDecision:
        """
        Check if a belief should be written.

        Args:
            fact: The fact text to add
            category: Category of the fact
            confidence: Confidence level (0.0-1.0)

        Returns:
            WriteDecision with allowed=True if write should proceed
        """
        self._stats.total_checks += 1
        self._ensure_cache()

        normalized = normalize_text(fact)

        # Check 1: Exact match (normalized)
        if normalized in self._belief_cache:
            existing = self._belief_cache[normalized]
            existing_conf = existing.get("confidence", 0.8)

            # Allow if confidence is significantly higher
            if confidence > existing_conf + self._confidence_margin:
                self._stats.upgraded += 1
                return WriteDecision(
                    decision=GateDecision.UPGRADE,
                    allowed=True,
                    reason=f"Confidence upgrade: {existing_conf:.1f} -> {confidence:.1f}",
                    existing_data=existing,
                    similarity_score=1.0,
                )

            # Reject exact duplicate
            self._stats.rejected += 1
            self._stats.bytes_saved += len(fact) + 50
            return WriteDecision(
                decision=GateDecision.REJECT,
                allowed=False,
                reason=f"Exact duplicate (confidence {existing_conf:.1f})",
                existing_data=existing,
                similarity_score=1.0,
            )

        # Check 2: Semantic similarity with existing beliefs
        best_match: Optional[Tuple[str, Dict[str, Any], float]] = None

        for key, existing in self._belief_cache.items():
            existing_fact = existing.get("fact", key)

            # Jaccard similarity
            sim = jaccard_similarity(fact, existing_fact)
            if sim >= self._similarity_threshold:
                if best_match is None or sim > best_match[2]:
                    best_match = (key, existing, sim)

            # Also check facts overlap (more precise for structured facts)
            if sim < self._similarity_threshold:
                facts_sim = facts_overlap(fact, existing_fact)
                if facts_sim >= self._facts_threshold:
                    if best_match is None or facts_sim > best_match[2]:
                        best_match = (key, existing, facts_sim)

        if best_match:
            key, existing, sim = best_match
            existing_conf = existing.get("confidence", 0.8)

            # Allow if confidence upgrade
            if confidence > existing_conf + self._confidence_margin:
                self._stats.upgraded += 1
                return WriteDecision(
                    decision=GateDecision.UPGRADE,
                    allowed=True,
                    reason=f"Similar fact upgrade ({sim:.0%}): confidence {existing_conf:.1f} -> {confidence:.1f}",
                    existing_data=existing,
                    similarity_score=sim,
                )

            # Reject semantic duplicate
            self._stats.rejected += 1
            self._stats.bytes_saved += len(fact) + 50
            return WriteDecision(
                decision=GateDecision.REJECT,
                allowed=False,
                reason=f"Semantic duplicate ({sim:.0%}): '{existing.get('fact', '')[:40]}...'",
                existing_data=existing,
                similarity_score=sim,
            )

        # Check 3: New fact - accept
        self._stats.accepted += 1

        # Add to cache immediately for same-batch dedup
        self._belief_cache[normalized] = {
            "fact": fact,
            "confidence": confidence,
            "category": category,
        }

        return WriteDecision(
            decision=GateDecision.ACCEPT,
            allowed=True,
            reason="New belief",
            similarity_score=0.0,
        )

    # =========================================================================
    # PERSONA CHECKS
    # =========================================================================

    def check_persona(
        self,
        preference_name: str,
        preference_value: str,
        context: Optional[str] = None,
    ) -> WriteDecision:
        """
        Check if a persona preference should be written.

        Args:
            preference_name: Name of the preference
            preference_value: Value to set
            context: Optional context

        Returns:
            WriteDecision with allowed=True if write should proceed
        """
        self._stats.total_checks += 1
        self._ensure_cache()

        # Build the trait key (matching how bridge stores it)
        trait_key = f"{preference_name}_{preference_value}"
        normalized_key = normalize_text(trait_key)

        # Check 1: Exact trait already exists
        for existing_key in self._persona_cache:
            if normalize_text(existing_key) == normalized_key:
                self._stats.rejected += 1
                self._stats.bytes_saved += len(trait_key) + 20
                return WriteDecision(
                    decision=GateDecision.REJECT,
                    allowed=False,
                    reason=f"Exact preference duplicate: {existing_key}",
                    existing_data={"key": existing_key, "value": self._persona_cache[existing_key]},
                    similarity_score=1.0,
                )

        # Check 2: Similar preference name with same value
        norm_name = normalize_text(preference_name)
        norm_value = normalize_text(preference_value)

        for existing_key in self._persona_cache:
            existing_normalized = normalize_text(existing_key)

            # Check if same preference_name pattern
            if norm_name in existing_normalized:
                # Extract value part (after underscore)
                parts = existing_key.split("_", 1)
                if len(parts) > 1:
                    existing_value = normalize_text(parts[1])

                    # Similar values?
                    value_sim = jaccard_similarity(norm_value, existing_value)
                    if value_sim >= self._similarity_threshold:
                        self._stats.rejected += 1
                        self._stats.bytes_saved += len(trait_key) + 20
                        return WriteDecision(
                            decision=GateDecision.REJECT,
                            allowed=False,
                            reason=f"Similar preference ({value_sim:.0%}): {existing_key}",
                            existing_data={
                                "key": existing_key,
                                "value": self._persona_cache[existing_key],
                            },
                            similarity_score=value_sim,
                        )

        # Check 3: New preference - accept
        self._stats.accepted += 1

        # Add to cache immediately for same-batch dedup
        self._persona_cache[trait_key] = 1.0

        return WriteDecision(
            decision=GateDecision.ACCEPT,
            allowed=True,
            reason="New preference",
            similarity_score=0.0,
        )

    # =========================================================================
    # EMOTION CHECKS
    # =========================================================================

    def check_emotion(
        self,
        emotion: str,
        intensity: float = 0.5,
    ) -> WriteDecision:
        """
        Check if an emotion update should be written.

        Emotions are more transient, so we're more permissive.
        Only reject if exact same emotion at similar intensity.

        Args:
            emotion: Emotion name
            intensity: Intensity (0.0-1.0)

        Returns:
            WriteDecision (usually allowed)
        """
        self._stats.total_checks += 1

        try:
            affective = self._manager.get_section("affective_now")
            current_emotion = getattr(affective, "_dominant_emotion", None)
            current_intensity = getattr(affective, "_emotion_intensity", 0.5)

            if current_emotion == emotion:
                # Same emotion - check intensity difference
                intensity_diff = abs(intensity - current_intensity)
                if intensity_diff < 0.1:
                    self._stats.rejected += 1
                    return WriteDecision(
                        decision=GateDecision.REJECT,
                        allowed=False,
                        reason=f"Same emotion at similar intensity ({intensity_diff:.0%} diff)",
                        existing_data={"emotion": current_emotion, "intensity": current_intensity},
                        similarity_score=1.0 - intensity_diff,
                    )
        except Exception:
            pass

        # Allow emotion updates (they're transient)
        self._stats.accepted += 1
        return WriteDecision(
            decision=GateDecision.ACCEPT,
            allowed=True,
            reason="Emotion update",
            similarity_score=0.0,
        )

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def get_stats(self) -> GateStats:
        """Get gate statistics."""
        return self._stats

    def reset_stats(self) -> None:
        """Reset statistics."""
        self._stats = GateStats()

    def invalidate_cache(self) -> None:
        """Mark cache as invalid (call after writes)."""
        self._cache_valid = False
