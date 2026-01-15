"""
GapAutoResolver — Implicit Gap Resolution from User Context

When users naturally provide clarifying context (e.g., "Lincoln Elementary"),
this module automatically resolves pending AMBIGUOUS_ENTITY gaps without
requiring explicit user prompts.

Design Philosophy:
    - Don't ask users questions they've already answered
    - Monitor incoming events for implicit resolutions
    - Match extracted entities against pending gaps
    - Auto-resolve when confidence is high enough

Integration Points:
    - P02: After NER extraction, check entities against gaps
    - P03 R0: Re-check on batch init for late-arriving context

Gap Resolution Strategy:
    1. Query pending gaps from st_learning_queue
    2. For each incoming entity, fuzzy-match against gap candidates
    3. If match confidence >= threshold, mark gap RESOLVED
    4. Update entity in st_kg_dom with resolved value

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.

Author: K0 Architecture Team
Date: 2026-01-09
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from asyncpg import Pool

logger = logging.getLogger(__name__)


def _now_ms() -> int:
    """Current time in milliseconds since epoch."""
    return int(time.time() * 1000)


def _normalize_entity(text: str) -> str:
    """Normalize entity text for matching."""
    # Lowercase, strip, collapse whitespace
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    # Remove common stopwords for matching
    stopwords = {"the", "a", "an", "at", "in", "on", "of"}
    words = [w for w in text.split() if w not in stopwords]
    return " ".join(words)


def _similarity(s1: str, s2: str) -> float:
    """Simple Jaccard similarity for entity matching."""
    if not s1 or not s2:
        return 0.0

    words1 = set(s1.lower().split())
    words2 = set(s2.lower().split())

    if not words1 or not words2:
        return 0.0

    intersection = words1 & words2
    union = words1 | words2

    return len(intersection) / len(union)


@dataclass
class PendingGap:
    """A pending gap from st_learning_queue."""

    id: str
    gap_type: str
    entity_id: str
    candidate_values: List[str]
    confidence_score: float
    context_json: Optional[str] = None
    space_id: Optional[str] = None
    tenant_id: Optional[str] = None


@dataclass
class ResolutionCandidate:
    """A candidate for resolving a gap."""

    gap_id: str
    entity_id: str
    resolved_value: str
    confidence: float
    source_event_id: Optional[str] = None
    match_reason: str = "entity_match"


@dataclass
class GapAutoResolverStats:
    """Statistics for gap auto-resolution."""

    gaps_checked: int = 0
    entities_matched: int = 0
    gaps_resolved: int = 0
    gaps_skipped_low_confidence: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "gaps_checked": self.gaps_checked,
            "entities_matched": self.entities_matched,
            "gaps_resolved": self.gaps_resolved,
            "gaps_skipped_low_confidence": self.gaps_skipped_low_confidence,
        }


class GapAutoResolver:
    """
    Automatically resolves gaps from user context.

    When a user mentions "Lincoln Elementary" in a new event, we check
    pending gaps like "AMBIGUOUS_ENTITY: Lincoln School" and auto-resolve
    if the match is strong enough.
    """

    # Minimum confidence to auto-resolve
    AUTO_RESOLVE_THRESHOLD = 0.75

    # Minimum similarity score for entity matching
    MIN_SIMILARITY = 0.6

    def __init__(
        self,
        pool: Pool,
        tenant_id: str,
        space_id: Optional[str] = None,
        auto_resolve_threshold: float = 0.75,
    ):
        self._pool = pool
        self._tenant_id = tenant_id
        self._space_id = space_id
        self._threshold = auto_resolve_threshold
        self._stats = GapAutoResolverStats()
        self._pending_gaps: List[PendingGap] = []
        self._gap_cache_time: Optional[int] = None
        self._gap_cache_ttl_ms = 60000  # 1 minute cache

    @property
    def stats(self) -> GapAutoResolverStats:
        return self._stats

    async def load_pending_gaps(self, force_refresh: bool = False) -> List[PendingGap]:
        """Load pending AMBIGUOUS_ENTITY gaps from st_learning_queue."""
        now = _now_ms()

        # Use cached gaps if fresh enough
        if (
            not force_refresh
            and self._gap_cache_time
            and (now - self._gap_cache_time) < self._gap_cache_ttl_ms
            and self._pending_gaps
        ):
            return self._pending_gaps

        query = """
            SELECT
                id,
                gap_type,
                entity_id,
                context_json,
                confidence_score,
                space_id,
                tenant_id
            FROM st_learning_queue
            WHERE status = 'PENDING'
              AND gap_type = 'AMBIGUOUS_ENTITY'
              AND tenant_id = $1
              AND (expires_at IS NULL OR expires_at > $2)
            ORDER BY importance_score DESC
            LIMIT 100
        """

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, self._tenant_id, now)

        gaps = []
        for row in rows:
            context = row["context_json"]
            candidates = []

            if context:
                try:
                    ctx = json.loads(context)
                    candidates = ctx.get("candidate_values", [])
                except (json.JSONDecodeError, TypeError):
                    pass

            gaps.append(
                PendingGap(
                    id=row["id"],
                    gap_type=row["gap_type"],
                    entity_id=row["entity_id"] or "",
                    candidate_values=candidates,
                    confidence_score=row["confidence_score"] or 0.5,
                    context_json=context,
                    space_id=row["space_id"],
                    tenant_id=row["tenant_id"],
                )
            )

        self._pending_gaps = gaps
        self._gap_cache_time = now
        self._stats.gaps_checked = len(gaps)

        logger.debug(
            "Loaded %d pending AMBIGUOUS_ENTITY gaps",
            len(gaps),
            extra={"tenant_id": self._tenant_id},
        )

        return gaps

    def match_entity_to_gaps(
        self,
        entity_text: str,
        entity_label: str,
        source_event_id: Optional[str] = None,
    ) -> List[ResolutionCandidate]:
        """
        Match an extracted entity against pending gaps.

        Example:
            entity_text="Lincoln Elementary School"
            Pending gap: entity_id="cluster_LOCATION_lincoln school"
            candidates=["Lincoln School", "Lincoln High School"]

            This should match and resolve the gap to "Lincoln Elementary School"
        """
        if not self._pending_gaps:
            return []

        normalized_entity = _normalize_entity(entity_text)
        candidates = []

        for gap in self._pending_gaps:
            # Skip if space doesn't match (if specified)
            if self._space_id and gap.space_id and gap.space_id != self._space_id:
                continue

            # Check entity_id for partial match
            entity_id_norm = _normalize_entity(
                gap.entity_id.replace("cluster_", "").replace("_", " ")
            )

            # Check if the entity label matches the gap's entity type
            gap_type = ""
            if "_LOCATION_" in gap.entity_id.upper():
                gap_type = "LOCATION"
            elif "_PERSON_" in gap.entity_id.upper():
                gap_type = "PERSON"
            elif "_ORGANIZATION_" in gap.entity_id.upper():
                gap_type = "ORG"

            # Label match bonus
            label_match = (
                entity_label.upper() in ["GPE", "LOC", "LOCATION"] and gap_type == "LOCATION"
            )
            label_match = label_match or (
                entity_label.upper() in ["PERSON", "PER"] and gap_type == "PERSON"
            )
            label_match = label_match or (
                entity_label.upper() in ["ORG", "ORGANIZATION"] and gap_type == "ORGANIZATION"
            )

            # Calculate similarity
            sim_to_entity_id = _similarity(normalized_entity, entity_id_norm)

            # Also check against candidate values
            best_candidate_sim = 0.0
            for cand in gap.candidate_values:
                cand_sim = _similarity(normalized_entity, _normalize_entity(cand))
                best_candidate_sim = max(best_candidate_sim, cand_sim)

            # Overall match score
            base_sim = max(sim_to_entity_id, best_candidate_sim)

            # Boost if label matches
            if label_match:
                base_sim = min(1.0, base_sim + 0.1)

            # Check if the new entity is MORE SPECIFIC than candidates
            # e.g., "Lincoln Elementary" is more specific than "Lincoln School"
            specificity_bonus = 0.0
            for cand in gap.candidate_values:
                if normalized_entity.startswith(_normalize_entity(cand)):
                    # New entity extends the candidate (more specific)
                    specificity_bonus = 0.15
                    break
                if _normalize_entity(cand) in normalized_entity:
                    # Candidate is substring of new entity
                    specificity_bonus = 0.1
                    break

            final_score = min(1.0, base_sim + specificity_bonus)

            if final_score >= self.MIN_SIMILARITY:
                candidates.append(
                    ResolutionCandidate(
                        gap_id=gap.id,
                        entity_id=gap.entity_id,
                        resolved_value=entity_text,  # Use original case
                        confidence=final_score,
                        source_event_id=source_event_id,
                        match_reason=f"entity_match(sim={base_sim:.2f}, spec={specificity_bonus:.2f})",
                    )
                )

        self._stats.entities_matched += len(candidates)
        return candidates

    async def resolve_gaps(
        self,
        resolutions: List[ResolutionCandidate],
    ) -> int:
        """
        Mark gaps as RESOLVED in st_learning_queue.

        Returns number of gaps resolved.
        """
        if not resolutions:
            return 0

        resolved_count = 0
        now = _now_ms()

        async with self._pool.acquire() as conn:
            for res in resolutions:
                if res.confidence < self._threshold:
                    self._stats.gaps_skipped_low_confidence += 1
                    logger.debug(
                        "Skipping gap %s: confidence %.2f < threshold %.2f",
                        res.gap_id,
                        res.confidence,
                        self._threshold,
                    )
                    continue

                # Update gap to RESOLVED
                resolution_data = {
                    "resolved_value": res.resolved_value,
                    "source_event_id": res.source_event_id,
                    "match_reason": res.match_reason,
                    "confidence": res.confidence,
                    "resolved_at": now,
                    "resolution_type": "IMPLICIT_CONTEXT",
                }

                update_query = """
                    UPDATE st_learning_queue
                    SET status = 'RESOLVED',
                        resolution_type = 'IMPLICIT',
                        resolution_data_json = $1,
                        answered_at = $2
                    WHERE id = $3
                      AND status = 'PENDING'
                """

                result = await conn.execute(
                    update_query,
                    json.dumps(resolution_data),
                    now,
                    res.gap_id,
                )

                if "UPDATE 1" in result:
                    resolved_count += 1
                    logger.info(
                        "Auto-resolved gap %s -> '%s' (confidence=%.2f, reason=%s)",
                        res.gap_id,
                        res.resolved_value,
                        res.confidence,
                        res.match_reason,
                    )

        self._stats.gaps_resolved = resolved_count

        # Invalidate cache since we resolved some gaps
        if resolved_count > 0:
            self._pending_gaps = []
            self._gap_cache_time = None

        return resolved_count

    async def process_entities(
        self,
        entities: List[Dict[str, Any]],
        source_event_id: Optional[str] = None,
        event_texts: Optional[List[str]] = None,
    ) -> int:
        """
        Process a batch of extracted entities and auto-resolve matching gaps.

        Args:
            entities: List of entity dicts with 'text' and 'label' keys
            source_event_id: The event that provided these entities
            event_texts: Optional list of raw event texts for fallback matching

        Returns:
            Number of gaps resolved
        """
        # Load pending gaps
        await self.load_pending_gaps()

        if not self._pending_gaps:
            return 0

        all_candidates = []

        # First pass: NER-based matching
        for entity in entities:
            text = entity.get("text", "")
            label = entity.get("label", "UNKNOWN")

            if not text or len(text) < 3:
                continue

            candidates = self.match_entity_to_gaps(text, label, source_event_id)
            all_candidates.extend(candidates)

        # Second pass: Raw text matching (fallback when NER misses full entity names)
        if event_texts:
            text_candidates = self._match_text_to_gaps(event_texts, source_event_id)
            all_candidates.extend(text_candidates)

        if not all_candidates:
            return 0

        # Deduplicate by gap_id (keep highest confidence)
        best_by_gap: Dict[str, ResolutionCandidate] = {}
        for cand in all_candidates:
            existing = best_by_gap.get(cand.gap_id)
            if not existing or cand.confidence > existing.confidence:
                best_by_gap[cand.gap_id] = cand

        return await self.resolve_gaps(list(best_by_gap.values()))

    def _match_text_to_gaps(
        self,
        event_texts: List[str],
        source_event_id: Optional[str] = None,
    ) -> List[ResolutionCandidate]:
        """
        Fallback: search raw event text for gap keywords.

        If NER extracted "Elementary School" but text says "Lincoln Elementary School",
        we can still match against gap "lincoln school".
        """
        candidates = []

        for gap in self._pending_gaps:
            # Extract the core entity name from the gap entity_id
            # e.g., "cluster_LOCATION_lincoln school" -> "lincoln school"
            entity_id_parts = gap.entity_id.replace("cluster_", "")
            # Remove type prefix (LOCATION_, PERSON_, etc.)
            for prefix in ["LOCATION_", "PERSON_", "ORGANIZATION_", "CONCEPT_", "EVENT_"]:
                if entity_id_parts.upper().startswith(prefix):
                    entity_id_parts = entity_id_parts[len(prefix) :]
                    break

            gap_keywords = _normalize_entity(entity_id_parts)
            gap_words = set(gap_keywords.split())

            if not gap_words:
                continue

            for text in event_texts:
                text_lower = text.lower()

                # Check if ALL gap keywords appear in the text
                if all(word in text_lower for word in gap_words):
                    # Extract the more specific phrase from the text
                    # Try to find a substring that contains all keywords
                    resolved_value = self._extract_specific_phrase(text, gap_words)

                    if resolved_value and len(resolved_value) > len(gap_keywords):
                        # More specific than the gap - good candidate!
                        candidates.append(
                            ResolutionCandidate(
                                gap_id=gap.id,
                                entity_id=gap.entity_id,
                                resolved_value=resolved_value,
                                confidence=0.85,  # High confidence for text match
                                source_event_id=source_event_id,
                                match_reason="text_contains_keywords",
                            )
                        )

        return candidates

    def _extract_specific_phrase(self, text: str, keywords: set) -> Optional[str]:
        """
        Extract a more specific phrase containing all keywords.

        Example: text="Lincoln Elementary School on Oak Street", keywords={"lincoln", "school"}
        Returns: "Lincoln Elementary School"

        Strategy:
        1. Find capitalized proper noun phrases containing keywords
        2. If no proper noun phrase, extract minimal span between keywords
        3. Limit to reasonable entity name length (max 5 words)
        """
        import re

        # Strategy 1: Find capitalized proper noun phrases
        # Match sequences of capitalized words (proper nouns)
        proper_noun_pattern = r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+[A-Z][a-z]+)*)\b"
        proper_nouns = re.findall(proper_noun_pattern, text)

        for phrase in proper_nouns:
            phrase_lower = phrase.lower()
            # Check if ALL keywords are in this proper noun phrase
            if all(kw in phrase_lower for kw in keywords):
                # Found a capitalized phrase containing all keywords
                return phrase.strip()

        # Strategy 2: Find the minimal contiguous span containing all keywords
        words = text.split()
        words_lower = [w.lower().strip(".,;:!?()[]\"'") for w in words]

        # Find positions of keyword matches
        keyword_positions = []
        for i, w in enumerate(words_lower):
            for kw in keywords:
                if kw in w:
                    keyword_positions.append(i)
                    break

        if not keyword_positions:
            return None

        # Extract minimal span from first to last keyword (no extra context)
        start = min(keyword_positions)
        end = max(keyword_positions) + 1

        # Limit to max 5 words to prevent runaway phrases
        if end - start > 5:
            return None

        phrase = " ".join(words[start:end])

        # Clean up punctuation
        phrase = phrase.strip(".,;:!?()[]\"'")

        # Capitalize first letter of each word for proper entity name
        if phrase and not phrase[0].isupper():
            phrase = " ".join(w.capitalize() for w in phrase.split())

        return phrase if len(phrase) > 3 else None


async def try_auto_resolve_gaps(
    pool: Pool,
    tenant_id: str,
    entities: List[Dict[str, Any]],
    source_event_id: Optional[str] = None,
    space_id: Optional[str] = None,
) -> Tuple[int, GapAutoResolverStats]:
    """
    Convenience function to auto-resolve gaps from entities.

    Returns (resolved_count, stats).
    """
    resolver = GapAutoResolver(
        pool=pool,
        tenant_id=tenant_id,
        space_id=space_id,
    )

    resolved = await resolver.process_entities(entities, source_event_id)
    return resolved, resolver.stats
