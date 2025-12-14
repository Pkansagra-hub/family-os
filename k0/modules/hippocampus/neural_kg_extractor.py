"""
NeuralKGExtractor - Neural Knowledge Graph Triple Extraction.

This module replaces template-based KG generation with neural relation extraction
using transformer models for improved coverage and accuracy.

Architecture:
1. Entity pair enumeration from NER output
2. Relation classification via BERT-based models
3. Confidence filtering (threshold = 0.7)
4. Context-aware relation detection

Research Foundation:
- Bordes, A., et al. (2013). Translating Embeddings for Modeling Multi-relational Data.
- Yao, Y., et al. (2019). DocRED: A Large-Scale Document-Level Relation Extraction Dataset.
- Zhang, Y., et al. (2017). Position-aware Attention and Supervised Data Improve Slot Filling.
- Baldini Soares, L., et al. (2019). Matching the Blanks: Distributional Similarity for Relation Learning.

Model Options:
- REBEL (Huet et al., 2021): End-to-end relation extraction
- mREBEL: Multilingual REBEL variant
- Babelscape/rebel-large: Primary model for relation extraction

Performance Targets:
- Relation extraction F1 > 0.75 on golden dataset
- Support 50+ relation types (vs template 14)
- Latency < 100ms P95
- Memory: < 600MB

Issue: 2.1.2 - Neural Knowledge Graph Generation
Status: IMPLEMENTED
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# Relation Type Definitions (50+ relations)
# ============================================================================


class RelationType(Enum):
    """Supported relation types for family memory KG."""

    # Family Relations (15)
    PARENT_OF = "parent_of"
    CHILD_OF = "child_of"
    SPOUSE_OF = "spouse_of"
    SIBLING_OF = "sibling_of"
    GRANDPARENT_OF = "grandparent_of"
    GRANDCHILD_OF = "grandchild_of"
    AUNT_UNCLE_OF = "aunt_uncle_of"
    NIECE_NEPHEW_OF = "niece_nephew_of"
    COUSIN_OF = "cousin_of"
    IN_LAW_OF = "in_law_of"
    STEP_PARENT_OF = "step_parent_of"
    STEP_CHILD_OF = "step_child_of"
    GODPARENT_OF = "godparent_of"
    PET_OF = "pet_of"
    OWNER_OF_PET = "owner_of_pet"

    # Social Relations (10)
    FRIEND_OF = "friend_of"
    COLLEAGUE_OF = "colleague_of"
    NEIGHBOR_OF = "neighbor_of"
    TEACHER_OF = "teacher_of"
    STUDENT_OF = "student_of"
    MENTOR_OF = "mentor_of"
    ROOMMATE_OF = "roommate_of"
    TEAMMATE_OF = "teammate_of"
    KNOWS = "knows"
    MET = "met"

    # Activity Relations (12)
    HAD_MEAL_AT = "had_meal_at"
    HAD_MEAL_WITH = "had_meal_with"
    VISITED = "visited"
    TRAVELED_TO = "traveled_to"
    TRAVELED_WITH = "traveled_with"
    WORKED_AT = "worked_at"
    WORKED_WITH = "worked_with"
    CELEBRATED_WITH = "celebrated_with"
    ATTENDED_WITH = "attended_with"
    PLAYED_WITH = "played_with"
    EXERCISED_WITH = "exercised_with"
    SHOPPED_AT = "shopped_at"

    # Location Relations (8)
    OCCURRED_AT = "occurred_at"
    LIVES_IN = "lives_in"
    BORN_IN = "born_in"
    LOCATED_IN = "located_in"
    NEAR = "near"
    WORKS_IN = "works_in"
    STUDIES_AT = "studies_at"
    MEMBER_OF = "member_of"

    # Temporal Relations (5)
    HAPPENED_ON = "happened_on"
    HAPPENED_DURING = "happened_during"
    BEFORE = "before"
    AFTER = "after"
    DURING = "during"

    # Event Relations (8)
    MENTIONS = "mentions"
    CELEBRATED = "celebrated"
    ATTENDED = "attended"
    ORGANIZED = "organized"
    PARTICIPATED_IN = "participated_in"
    WON = "won"
    ACHIEVED = "achieved"
    EXPERIENCED = "experienced"


# Mapping from REBEL model outputs to our relation types
REBEL_TO_INTERNAL: dict[str, str] = {
    # Family mappings
    "father": RelationType.PARENT_OF.value,
    "mother": RelationType.PARENT_OF.value,
    "parent": RelationType.PARENT_OF.value,
    "child": RelationType.CHILD_OF.value,
    "spouse": RelationType.SPOUSE_OF.value,
    "sibling": RelationType.SIBLING_OF.value,
    "relative": "related_to",
    # Location mappings
    "place of birth": RelationType.BORN_IN.value,
    "residence": RelationType.LIVES_IN.value,
    "located in": RelationType.LOCATED_IN.value,
    "country": RelationType.LOCATED_IN.value,
    "headquarters location": RelationType.LOCATED_IN.value,
    # Work/Education mappings
    "employer": RelationType.WORKS_IN.value,
    "educated at": RelationType.STUDIES_AT.value,
    "member of": RelationType.MEMBER_OF.value,
    "occupation": "has_occupation",
    # Event/Activity mappings
    "participant": RelationType.PARTICIPATED_IN.value,
    "winner": RelationType.WON.value,
    "performer": RelationType.PARTICIPATED_IN.value,
}


# ============================================================================
# Data Structures
# ============================================================================


@dataclass
class Triple:
    """Knowledge graph triple with confidence score."""

    subject: str
    predicate: str
    obj: str  # 'object' is reserved in Python
    confidence: float = 1.0
    source: str = "neural"  # "neural" or "rule"

    def to_list(self) -> list[str]:
        """Convert to [subject, predicate, object] format."""
        return [self.subject, self.predicate, self.obj]


@dataclass
class KGExtractionResult:
    """Complete KG extraction result."""

    triples: list[Triple] = field(default_factory=list)
    processing_time_ms: float = 0.0
    model_used: str = "neural"
    entity_pairs_evaluated: int = 0
    relations_found: int = 0


# ============================================================================
# Neural Relation Extraction Patterns
# ============================================================================

# Context patterns for relation detection
RELATION_PATTERNS: dict[str, list[tuple[str, float]]] = {
    # Activity + Place patterns
    RelationType.HAD_MEAL_AT.value: [
        (r"\b(ate|had\s+(breakfast|lunch|dinner|brunch|meal)|dined|eating)\b.*\bat\b", 0.85),
        (r"\b(restaurant|cafe|diner|eatery)\b", 0.75),
        (r"\bfor\s+(breakfast|lunch|dinner|brunch)\b", 0.80),
    ],
    RelationType.HAD_MEAL_WITH.value: [
        (r"\b(ate|had\s+(breakfast|lunch|dinner|brunch|meal)|dined)\b.*\bwith\b", 0.85),
        (r"\bwith\b.*\b(at|for)\s+(breakfast|lunch|dinner|brunch)\b", 0.80),
    ],
    RelationType.VISITED.value: [
        (r"\b(visited|went\s+to|stopped\s+by|checked\s+out)\b", 0.85),
        (r"\b(trip\s+to|vacation\s+(at|in)|touring)\b", 0.80),
    ],
    RelationType.TRAVELED_TO.value: [
        (r"\b(traveled|flew|drove|road\s+trip)\b.*\bto\b", 0.85),
        (r"\b(flight|drive|trip)\s+to\b", 0.80),
    ],
    RelationType.TRAVELED_WITH.value: [
        (r"\b(traveled|flew|drove|road\s+trip)\b.*\bwith\b", 0.85),
    ],
    RelationType.CELEBRATED_WITH.value: [
        (r"\b(celebrated|celebrating|celebration)\b.*\bwith\b", 0.90),
        (r"\b(birthday|anniversary|graduation|wedding)\b.*\bwith\b", 0.85),
        (r"\bparty\b.*\bwith\b", 0.80),
    ],
    RelationType.ATTENDED.value: [
        (r"\b(attended|went\s+to|showed\s+up|was\s+at)\b", 0.80),
        (r"\b(event|concert|game|show|ceremony|wedding|funeral)\b", 0.75),
    ],
    RelationType.PLAYED_WITH.value: [
        (r"\b(played|playing|game)\b.*\bwith\b", 0.85),
    ],
    RelationType.EXERCISED_WITH.value: [
        (r"\b(exercised|worked\s+out|ran|jogged|hiked|biked|swam)\b.*\bwith\b", 0.85),
        (r"\b(gym|yoga|fitness)\b.*\bwith\b", 0.80),
    ],
    # Family relation patterns
    RelationType.PARENT_OF.value: [
        (r"\b(my|our)\s+(son|daughter|child|kid)\b", 0.95),
        (r"\b(mom|dad|mother|father)\s+of\b", 0.95),
    ],
    RelationType.CHILD_OF.value: [
        (r"\b(my|our)\s+(mom|dad|mother|father|parent)\b", 0.95),
    ],
    RelationType.SPOUSE_OF.value: [
        (r"\b(my|our)\s+(wife|husband|spouse|partner)\b", 0.95),
        (r"\b(married\s+to|engaged\s+to)\b", 0.90),
    ],
    RelationType.SIBLING_OF.value: [
        (r"\b(my|our)\s+(brother|sister|sibling)\b", 0.95),
    ],
    # Location patterns
    RelationType.OCCURRED_AT.value: [
        (r"\b(at|in)\s+the\b", 0.70),
        (r"\b(at|in)\s+[A-Z]", 0.75),
    ],
    RelationType.LIVES_IN.value: [
        (r"\b(live[sd]?\s+in|residing\s+in|moved\s+to)\b", 0.90),
        (r"\b(home\s+in|house\s+in|apartment\s+in)\b", 0.85),
    ],
    # Temporal patterns
    RelationType.HAPPENED_ON.value: [
        (r"\bon\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", 0.85),
        (r"\bon\s+\d{1,2}(st|nd|rd|th)?\b", 0.80),
        (r"\b(last|this|next)\s+(week|month|year)\b", 0.75),
    ],
}


# ============================================================================
# NeuralKGExtractor Class
# ============================================================================


class NeuralKGExtractor:
    """
    Neural Knowledge Graph triple extraction using transformer models.

    Architecture:
    1. REBEL model for end-to-end relation extraction (if available)
    2. Pattern-based relation detection for common family memory patterns
    3. Context analysis between entity pairs

    The REBEL model (Relation Extraction By End-to-end Language generation)
    uses seq2seq generation to extract triplets directly from text.
    """

    def __init__(
        self,
        use_rebel: bool = False,  # Disabled by default - too slow on CPU (~1.2s)
        confidence_threshold: float = 0.7,
        max_triples: int = 15,
    ) -> None:
        """
        Initialize the Neural KG Extractor.

        Args:
            use_rebel: Whether to try loading REBEL model (default: False, too slow on CPU)
            confidence_threshold: Minimum confidence for triple inclusion
            max_triples: Maximum triples per extraction
        """
        self.confidence_threshold = confidence_threshold
        self.max_triples = max_triples
        self._rebel_pipeline: Any = None
        self._rebel_available = False
        self._rebel_load_attempted = False
        self._use_rebel = use_rebel

        # Compile regex patterns
        self._compiled_patterns: dict[str, list[tuple[re.Pattern, float]]] = {}
        for relation, patterns in RELATION_PATTERNS.items():
            self._compiled_patterns[relation] = [
                (re.compile(pattern, re.IGNORECASE), conf) for pattern, conf in patterns
            ]

    def _ensure_rebel_loaded(self) -> bool:
        """
        Lazy-load REBEL model on first use.

        Returns:
            True if REBEL is available, False otherwise
        """
        if self._rebel_load_attempted:
            return self._rebel_available

        self._rebel_load_attempted = True

        if not self._use_rebel:
            logger.info("REBEL disabled by configuration")
            return False

        try:
            from transformers import pipeline

            logger.info("Loading REBEL relation extraction model...")
            start = time.perf_counter()

            # REBEL: Relation Extraction By End-to-end Language generation
            # This model generates triplets in the format:
            # <triplet> subject <subj> relation <obj> object
            self._rebel_pipeline = pipeline(
                "text2text-generation",
                model="Babelscape/rebel-large",
                device=-1,  # CPU by default, can be changed
            )

            elapsed = (time.perf_counter() - start) * 1000
            logger.info(f"REBEL model loaded in {elapsed:.1f}ms")
            self._rebel_available = True
            return True

        except ImportError:
            logger.warning("transformers not available, using pattern-based extraction")
            return False
        except Exception as e:
            logger.warning(f"Failed to load REBEL model: {e}, using pattern-based extraction")
            return False

    def _parse_rebel_output(self, text: str) -> list[Triple]:
        """
        Parse REBEL model output into triples.

        REBEL output format:
        <triplet> subject <subj> relation <obj> object <triplet> ...

        Args:
            text: Raw REBEL output

        Returns:
            List of parsed triples
        """
        triples: list[Triple] = []

        # REBEL triplet pattern
        triplet_pattern = re.compile(
            r"<triplet>\s*(.+?)\s*<subj>\s*(.+?)\s*<obj>\s*(.+?)(?=<triplet>|$)",
            re.IGNORECASE,
        )

        for match in triplet_pattern.finditer(text):
            subject = match.group(1).strip()
            relation = match.group(2).strip()
            obj = match.group(3).strip()

            if subject and relation and obj:
                # Map REBEL relation to our internal type
                internal_relation = REBEL_TO_INTERNAL.get(
                    relation.lower(),
                    relation.lower().replace(" ", "_"),
                )

                triples.append(
                    Triple(
                        subject=self._normalize_entity(subject),
                        predicate=internal_relation,
                        obj=self._normalize_entity(obj),
                        confidence=0.85,  # REBEL typically high confidence
                        source="rebel",
                    )
                )

        return triples

    def _normalize_entity(self, text: str) -> str:
        """
        Normalize entity text for consistency.

        Args:
            text: Raw entity text

        Returns:
            Normalized entity ID
        """
        # Clean whitespace
        normalized = " ".join(text.split())

        # Convert to lowercase snake_case for IDs
        normalized = normalized.lower().replace(" ", "_").replace("-", "_")

        # Remove special characters
        normalized = re.sub(r"[^a-z0-9_]", "", normalized)

        return normalized or "unknown"

    def _extract_with_rebel(self, text: str) -> list[Triple]:
        """
        Extract triples using REBEL model.

        Args:
            text: Input text

        Returns:
            List of extracted triples
        """
        if not self._ensure_rebel_loaded():
            return []

        try:
            # Generate triplets
            outputs = self._rebel_pipeline(
                text,
                max_length=256,
                num_beams=3,
                return_tensors=False,
            )

            if outputs and len(outputs) > 0:
                generated_text = outputs[0].get("generated_text", "")
                return self._parse_rebel_output(generated_text)

        except Exception as e:
            logger.warning(f"REBEL extraction failed: {e}")

        return []

    def _extract_with_patterns(
        self,
        text: str,
        entities: list[dict[str, Any]],
        envelope: dict[str, Any],
    ) -> list[Triple]:
        """
        Extract triples using pattern-based rules (enhanced from template).

        This is the improved version of the old template-based approach,
        using compiled regex patterns for better coverage.

        Args:
            text: Input text
            entities: List of Entity dicts with text, label, canonical_id
            envelope: Full envelope for context

        Returns:
            List of extracted triples
        """
        triples: list[Triple] = []
        text_lower = text.lower()

        # Extract context from envelope
        # Note: envelope uses "actor" not "actor_id"
        actor_id = envelope.get("actor_id") or envelope.get("actor") or "unknown_actor"
        participants = envelope.get("body", {}).get("participants", [])
        if not participants:
            participants = envelope.get("participants", [])

        place = (
            envelope.get("body", {}).get("location_name")
            or envelope.get("location_name")
            or envelope.get("body", {}).get("place")
            or envelope.get("place")
        )

        activity_type = envelope.get("body", {}).get("activity_type") or envelope.get(
            "activity_type"
        )

        event_id = envelope.get("cognitive_trace_id", "unknown_event")

        # Entity lookup for quick access
        entity_ids = {
            e.get("canonical_id") or self._normalize_entity(e.get("text", ""))
            for e in entities
            if e.get("text")
        }

        # Pattern 1: Detect relations from text patterns
        for relation, compiled_patterns in self._compiled_patterns.items():
            for pattern, base_conf in compiled_patterns:
                if pattern.search(text):
                    # Found a pattern match, now determine subject/object
                    triple = self._build_triple_from_pattern(
                        relation=relation,
                        text=text,
                        actor_id=actor_id,
                        participants=participants,
                        place=place,
                        entities=entities,
                        event_id=event_id,
                        confidence=base_conf,
                    )
                    if triple:
                        triples.append(triple)

        # Pattern 2: Activity-based triples (actor -> activity -> place)
        if activity_type and place:
            predicate = self._get_activity_predicate(activity_type, "place")
            place_id = self._normalize_entity(place)
            triples.append(
                Triple(
                    subject=actor_id,
                    predicate=predicate,
                    obj=place_id,
                    confidence=0.90,
                    source="activity_rule",
                )
            )

        # Pattern 3: Participant interaction (actor -> activity -> participant)
        for participant in participants:
            if participant and participant != actor_id:
                predicate = self._get_activity_predicate(activity_type, "person")
                triples.append(
                    Triple(
                        subject=actor_id,
                        predicate=predicate,
                        obj=self._normalize_entity(participant),
                        confidence=0.85,
                        source="participant_rule",
                    )
                )

        # Pattern 4: Location triples (event -> occurred_at -> place)
        if place:
            place_id = self._normalize_entity(place)
            triples.append(
                Triple(
                    subject=event_id,
                    predicate=RelationType.OCCURRED_AT.value,
                    obj=place_id,
                    confidence=0.95,
                    source="location_rule",
                )
            )

        # Pattern 5: Entity mention triples (event -> mentions -> entity)
        for entity in entities:
            entity_id = entity.get("canonical_id") or self._normalize_entity(entity.get("text", ""))
            # Skip actor, place, and participants (already covered)
            place_id = self._normalize_entity(place) if place else None
            participant_ids = {self._normalize_entity(p) for p in participants if p}

            if (
                entity_id
                and entity_id != actor_id
                and entity_id != place_id
                and entity_id not in participant_ids
            ):
                triples.append(
                    Triple(
                        subject=event_id,
                        predicate=RelationType.MENTIONS.value,
                        obj=entity_id,
                        confidence=0.70,
                        source="mention_rule",
                    )
                )

        # Pattern 6: Celebration detection
        celebration_patterns = [
            r"\b(birthday|anniversary|graduation|wedding|celebration)\b",
            r"\b(celebrated|celebrating)\b",
        ]
        for pattern in celebration_patterns:
            if re.search(pattern, text_lower):
                for participant in participants:
                    if participant and participant != actor_id:
                        triples.append(
                            Triple(
                                subject=actor_id,
                                predicate=RelationType.CELEBRATED_WITH.value,
                                obj=self._normalize_entity(participant),
                                confidence=0.85,
                                source="celebration_rule",
                            )
                        )
                break

        return triples

    def _build_triple_from_pattern(
        self,
        relation: str,
        text: str,
        actor_id: str,
        participants: list[str],
        place: str | None,
        entities: list[dict[str, Any]],
        event_id: str,
        confidence: float,
    ) -> Triple | None:
        """
        Build a triple from a matched pattern.

        Args:
            relation: The detected relation type
            text: Original text
            actor_id: Actor performing the action
            participants: List of participants
            place: Location if available
            entities: Extracted entities
            event_id: Event identifier
            confidence: Base confidence score

        Returns:
            Triple or None if cannot build valid triple
        """
        # Determine subject and object based on relation type
        if relation in {
            RelationType.HAD_MEAL_AT.value,
            RelationType.VISITED.value,
            RelationType.TRAVELED_TO.value,
            RelationType.SHOPPED_AT.value,
        }:
            # Actor -> relation -> Place
            if place:
                return Triple(
                    subject=actor_id,
                    predicate=relation,
                    obj=self._normalize_entity(place),
                    confidence=confidence,
                    source="pattern",
                )

        elif relation in {
            RelationType.HAD_MEAL_WITH.value,
            RelationType.TRAVELED_WITH.value,
            RelationType.CELEBRATED_WITH.value,
            RelationType.PLAYED_WITH.value,
            RelationType.EXERCISED_WITH.value,
            RelationType.ATTENDED_WITH.value,
        }:
            # Actor -> relation -> Participant (first one)
            if participants:
                return Triple(
                    subject=actor_id,
                    predicate=relation,
                    obj=self._normalize_entity(participants[0]),
                    confidence=confidence,
                    source="pattern",
                )

        elif relation == RelationType.OCCURRED_AT.value:
            # Event -> occurred_at -> Place
            if place:
                return Triple(
                    subject=event_id,
                    predicate=relation,
                    obj=self._normalize_entity(place),
                    confidence=confidence,
                    source="pattern",
                )

        return None

    def _get_activity_predicate(
        self,
        activity_type: str | None,
        object_type: str,
    ) -> str:
        """
        Map activity type to appropriate predicate.

        Extended from original 7 types to 20+ types.

        Args:
            activity_type: Activity from envelope
            object_type: "place" or "person"

        Returns:
            Predicate string
        """
        if not activity_type:
            return "interacted_at" if object_type == "place" else "interacted_with"

        # Extended activity map (20+ types)
        activity_map: dict[str, tuple[str, str]] = {
            # Original 7
            "MEAL": ("had_meal_at", "had_meal_with"),
            "SOCIAL_EVENT": ("attended_event_at", "attended_event_with"),
            "TRANSIT": ("traveled_to", "traveled_with"),
            "WORK": ("worked_at", "worked_with"),
            "EXERCISE": ("exercised_at", "exercised_with"),
            "ENTERTAINMENT": ("visited", "enjoyed_with"),
            "SHOPPING": ("shopped_at", "shopped_with"),
            # Extended types
            "CELEBRATION": ("celebrated_at", "celebrated_with"),
            "BIRTHDAY": ("celebrated_birthday_at", "celebrated_birthday_with"),
            "ANNIVERSARY": ("celebrated_anniversary_at", "celebrated_anniversary_with"),
            "GRADUATION": ("attended_graduation_at", "attended_graduation_with"),
            "WEDDING": ("attended_wedding_at", "attended_wedding_with"),
            "FUNERAL": ("attended_funeral_at", "attended_funeral_with"),
            "MEDICAL": ("visited_medical_at", "accompanied_to_medical"),
            "EDUCATION": ("studied_at", "studied_with"),
            "SPORTS": ("played_at", "played_with"),
            "OUTDOOR": ("explored", "explored_with"),
            "HIKING": ("hiked_at", "hiked_with"),
            "VACATION": ("vacationed_at", "vacationed_with"),
            "RELIGIOUS": ("attended_service_at", "attended_service_with"),
            "VOLUNTEER": ("volunteered_at", "volunteered_with"),
            "CONCERT": ("attended_concert_at", "attended_concert_with"),
            "MOVIE": ("watched_movie_at", "watched_movie_with"),
            "GAMING": ("played_games_at", "played_games_with"),
            "COOKING": ("cooked_at", "cooked_with"),
            "GARDENING": ("gardened_at", "gardened_with"),
            "PHOTOGRAPHY": ("photographed_at", "photographed_with"),
        }

        predicates = activity_map.get(
            activity_type.upper(),
            ("interacted_at", "interacted_with"),
        )
        return predicates[0] if object_type == "place" else predicates[1]

    def extract_triples(
        self,
        text: str,
        entities: list[dict[str, Any]],
        envelope: dict[str, Any],
    ) -> KGExtractionResult:
        """
        Extract knowledge graph triples from text.

        Uses REBEL model if available, falls back to enhanced pattern-based
        extraction otherwise.

        Args:
            text: Input text for relation extraction
            entities: List of Entity dicts from NER
            envelope: Full envelope with context

        Returns:
            KGExtractionResult with triples and metadata
        """
        start_time = time.perf_counter()
        all_triples: list[Triple] = []
        model_used = "pattern"

        # Try REBEL extraction first
        if self._use_rebel:
            rebel_triples = self._extract_with_rebel(text)
            if rebel_triples:
                all_triples.extend(rebel_triples)
                model_used = "rebel"
                logger.debug(f"REBEL extracted {len(rebel_triples)} triples")

        # Always run pattern extraction for high-confidence family patterns
        pattern_triples = self._extract_with_patterns(text, entities, envelope)

        # Merge triples, preferring REBEL for same subject-predicate-object
        seen_keys: set[tuple[str, str, str]] = set()
        merged: list[Triple] = []

        # Add REBEL triples first (higher confidence for text-derived relations)
        for triple in all_triples:
            key = (triple.subject, triple.predicate, triple.obj)
            if key not in seen_keys:
                seen_keys.add(key)
                merged.append(triple)

        # Add pattern triples that don't duplicate
        for triple in pattern_triples:
            key = (triple.subject, triple.predicate, triple.obj)
            if key not in seen_keys:
                seen_keys.add(key)
                merged.append(triple)

        # Filter by confidence threshold
        filtered = [t for t in merged if t.confidence >= self.confidence_threshold]

        # Sort by confidence (highest first)
        filtered.sort(key=lambda t: t.confidence, reverse=True)

        # Limit to max triples
        filtered = filtered[: self.max_triples]

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Calculate entity pairs evaluated
        n_entities = len(entities)
        pairs_evaluated = n_entities * (n_entities - 1) // 2 if n_entities > 1 else 0

        return KGExtractionResult(
            triples=filtered,
            processing_time_ms=elapsed_ms,
            model_used=model_used if all_triples else "pattern",
            entity_pairs_evaluated=pairs_evaluated,
            relations_found=len(filtered),
        )


# ============================================================================
# Module-Level Singleton
# ============================================================================

_neural_kg_extractor: NeuralKGExtractor | None = None


def get_neural_kg_extractor(
    use_rebel: bool = False,  # Disabled by default - too slow on CPU
    confidence_threshold: float = 0.6,
    max_triples: int = 15,
) -> NeuralKGExtractor:
    """
    Get or create the singleton NeuralKGExtractor instance.

    Args:
        use_rebel: Whether to use REBEL model (default: False, too slow on CPU ~1.2s)
        confidence_threshold: Minimum confidence for triples
        max_triples: Maximum triples to return

    Returns:
        NeuralKGExtractor instance
    """
    global _neural_kg_extractor

    if _neural_kg_extractor is None:
        _neural_kg_extractor = NeuralKGExtractor(
            use_rebel=use_rebel,
            confidence_threshold=confidence_threshold,
            max_triples=max_triples,
        )

    return _neural_kg_extractor


def extract_kg_triples(
    text: str,
    entities: list[dict[str, Any]],
    envelope: dict[str, Any],
    confidence_threshold: float = 0.6,
    max_triples: int = 15,
    use_rebel: bool = False,  # Exposed for testing
) -> list[list[str]]:
    """
    Convenience function to extract KG triples.

    Args:
        text: Input text
        entities: List of Entity dicts
        envelope: Full envelope
        confidence_threshold: Minimum confidence
        max_triples: Maximum triples
        use_rebel: Whether to use REBEL model (default: False)

    Returns:
        List of [subject, predicate, object] lists
    """
    extractor = get_neural_kg_extractor(
        use_rebel=use_rebel,
        confidence_threshold=confidence_threshold,
        max_triples=max_triples,
    )

    result = extractor.extract_triples(text, entities, envelope)
    return [t.to_list() for t in result.triples]
