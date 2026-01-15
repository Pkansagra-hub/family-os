"""
R4 UltraBERT Entity Extractor - KG Entity Normalization for P03 Consolidation.

Issue: 4.4.1 - Integrate UltraBERT NER entity extraction from P02
Spec Reference: M4_EXECUTION.md, Dossier Section 4.5.1

This module processes the 3 UltraBERT NER heads (ner_family, ner_general, temporal)
and maps entities to canonical KG types for knowledge graph population.

Architecture:
- Receives raw UltraBERT NER outputs from P02 (stored in st_hipp_events.entities_json)
- Maps UltraBERT labels to KGEntityType enum
- Applies priority-based deduplication (KINSHIP beats PERSON for same text)
- Normalizes entity names with nickname handling

HYBRID NER MODE (P03 only):
- UltraBERT v2-checkpoint-18000 has trained ner_family but ner_general was only
  used for replay/distillation (produces garbage like "Drove", "Fur", "authentication")
- When use_bert_ner=True, we ignore UltraBERT ner_general and instead run
  dslim/bert-base-NER on the source text during P03 consolidation
- This adds ~3.8ms/event but P03 is nightly batch, not hot path
- Edge device friendly: no model inference during active user hours

Performance:
- Processing latency: <5ms per event (pure Python, no model inference)
- With BERT-NER: +3.8ms per event (or ~1.5ms/event in batch mode)
- Memory: O(n) where n = entity count

Input: UltraBERT analyze() output with ner_family, ner_general, temporal heads
Output: List of ExtractedEntity with kg_type, priority, normalized_text

Related:
- k0/runtime/ultrabert_adapter.py: UltraBERT client singleton
- k0/modules/consolidation/algorithms/bert_ner_adapter.py: BERT-NER for general NER
- k0/modules/hippocampus/semantic_project.py: P02 entity extraction
- k0/db/alembic/versions/0022_st_hipp_events.py: entities_json column

Author: K0 Architecture Team
Date: 2025-06-10
Updated: 2025-01-09 - Added hybrid NER mode with BERT-NER
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class KGEntityType(Enum):
    """Canonical KG entity types for knowledge graph population.

    These are the target types used in st_hipp_events.entities_json
    and for R4 KG consolidation.
    """

    FAMILY_MEMBER = "FAMILY_MEMBER"
    PERSON = "PERSON"
    LOCATION = "LOCATION"
    ORGANIZATION = "ORGANIZATION"
    EVENT = "EVENT"
    OBJECT = "OBJECT"
    TEMPORAL = "TEMPORAL"
    CONCEPT = "CONCEPT"


@dataclass
class UltraBERTEntity:
    """Raw entity from UltraBERT NER head.

    Matches the output format from familyos_ultrabert Client.analyze():
    - text: Entity text span
    - label: UltraBERT label (KINSHIP, PERSON, ORG, etc.)
    - start_token: Start token position
    - end_token: End token position
    - source_head: Which head produced this entity
    """

    text: str
    label: str
    start_token: int
    end_token: int
    source_head: str  # 'ner_family', 'ner_general', or 'temporal'


@dataclass
class ExtractedEntity:
    """Normalized entity for KG population.

    This is the output format for R4 consolidation, containing:
    - Canonical KG type (mapped from UltraBERT label)
    - Priority score for disambiguation
    - Normalized text for matching
    """

    text: str
    kg_type: KGEntityType
    normalized_text: str
    source_label: str  # Original UltraBERT label
    source_head: str  # Which head it came from
    priority: float  # Derived from label mapping (0.0-1.0)
    start_token: int
    end_token: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "text": self.text,
            "kg_type": self.kg_type.value,
            "normalized": self.normalized_text,
            "source_label": self.source_label,
            "source_head": self.source_head,
            "priority": self.priority,
            "start_token": self.start_token,
            "end_token": self.end_token,
        }


@dataclass
class EntityExtractionMetrics:
    """Metrics for entity extraction operations."""

    entities_extracted: int = 0
    entities_by_head: dict[str, int] = field(default_factory=dict)
    entities_by_type: dict[str, int] = field(default_factory=dict)
    unknown_labels: int = 0
    duplicates_removed: int = 0
    processing_time_ms: float = 0.0


class UltraBERTEntityExtractor:
    """
    Process UltraBERT NER outputs (3 heads) for KG population.

    Issue: 4.4.1 - Integrate UltraBERT NER entity extraction from P02
    Spec: M4_EXECUTION.md, Dossier Section 4.5.1

    Features:
    - Merges 3 NER heads: ner_family, ner_general, temporal
    - Maps UltraBERT labels to KG entity types
    - Canonical name normalization with nickname handling
    - Entity deduplication with priority-based selection
    """

    # === NER_FAMILY LABEL FILTERING ===
    # Based on empirical testing of UltraBERT v3.0.2 ner_family head
    # See: k0/deploy/test_ner_outputs.py for test results

    # Labels to accept without question (family-specific, BERT-NER can't provide)
    TRUSTED_NER_FAMILY: frozenset[str] = frozenset(
        {
            "KINSHIP",  # Mom, Dad, wife, kids - reliable
            "NICKNAME",  # Buddy, Sweetie, Honey - reliable
            "TRADITION",  # Italian, Hanukkah - reliable
            "HOME_LOC",  # home, grandma's house - reliable
        }
    )

    # Labels to reject entirely from ner_family (BERT-NER provides better coverage)
    REJECTED_NER_FAMILY: frozenset[str] = frozenset(
        {
            "PERSON",  # Tags "Microsoft", "authentication" - use BERT-NER PER instead
        }
    )

    # Labels that need text validation (filter garbage but keep good ones)
    VALIDATED_NER_FAMILY: frozenset[str] = frozenset(
        {
            "MILESTONE",  # Tags verbs like "learned", "new"
            "FAMILY_EVENT",  # Tags "our", numbers, verbs
            "HEIRLOOM",  # Tags "old", "to", "in"
            "PET",  # Tags "the" in "Fur the cat"
            "ROUTINE",  # Generally ok but validate
        }
    )

    # Words that BERT-NER misclassifies as PERSON - filter these out
    # These are common nouns/verbs that get capitalized in sentences
    BERT_NER_PERSON_STOPWORDS: frozenset[str] = frozenset(
        {
            # Programming/tech terms often capitalized
            "code",
            "module",
            "switch",
            "team",
            "api",
            "app",
            "data",
            "web",
            "git",
            "repo",
            # Common verbs/adverbs mistagged
            "got",
            "went",
            "came",
            "took",
            "made",
            "met",
            "saw",
            "put",
            "said",
            "told",
            "asked",
            "called",
            # Temporal words
            "when",
            "next",
            "last",
            "first",
            "today",
            "tomorrow",
            "yesterday",
            # Other common mistagged words
            "dr",  # Often tags "Dr." without name
            "mr",
            "mrs",
            "ms",
            "authentication",
            "authorization",
        }
    )

    # Words that BERT-NER misclassifies as LOC (location) - filter these out
    BERT_NER_LOC_STOPWORDS: frozenset[str] = frozenset(
        {
            # Temporal words often capitalized
            "when",
            "next",
            "last",
            "first",
            "now",
            "then",
            "here",
            "there",
            # Common mistagged words
            "the",
            "a",
            "an",
            "it",
        }
    )

    # Garbage words that should never be entities (function words, common verbs)
    GARBAGE_ENTITY_WORDS: frozenset[str] = frozenset(
        {
            # Articles and determiners
            "the",
            "a",
            "an",
            "this",
            "that",
            "these",
            "those",
            # Pronouns and possessives
            "our",
            "my",
            "your",
            "his",
            "her",
            "its",
            "their",
            "i",
            "me",
            "we",
            "us",
            "you",
            "he",
            "she",
            "it",
            "they",
            "them",
            # Conjunctions and prepositions
            "and",
            "or",
            "but",
            "to",
            "from",
            "in",
            "on",
            "at",
            "for",
            "with",
            "of",
            "by",
            "as",
            "into",
            "onto",
            "upon",
            # Common verbs (often mistagged as PERSON, MILESTONE, etc.)
            "is",
            "was",
            "are",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "met",
            "fixed",
            "deployed",
            "updated",
            "attended",
            "learned",
            "made",
            "took",
            "got",
            "went",
            "came",
            "saw",
            "put",
            "called",
            "helped",
            "picked",
            "wore",
            "found",
            "passed",
            # Common adjectives mistagged by MILESTONE/HEIRLOOM
            "new",
            "old",
            "first",
            "last",
            "next",
            "other",
            # Short fragments (tokenization artifacts)
            "s",
            "'s",
            "ed",
            "ing",
            "ly",
        }
    )

    # UltraBERT label -> (KGEntityType, priority)
    # Priority determines which label wins during deduplication
    LABEL_MAPPING: dict[str, tuple[KGEntityType, float]] = {
        # ner_family labels (highest priority for family context)
        "KINSHIP": (KGEntityType.FAMILY_MEMBER, 0.95),
        "FAMILY_EVENT": (KGEntityType.EVENT, 0.90),
        "HOME_LOC": (KGEntityType.LOCATION, 0.90),  # Family home/school locations
        "FAMILY_LOC": (KGEntityType.LOCATION, 0.90),  # Family-related locations
        # ner_general labels
        "PERSON": (KGEntityType.PERSON, 0.85),
        "PER": (KGEntityType.PERSON, 0.85),  # Alternate label
        "ORG": (KGEntityType.ORGANIZATION, 0.80),
        "ORGANIZATION": (KGEntityType.ORGANIZATION, 0.80),
        "LOC": (KGEntityType.LOCATION, 0.80),
        "LOCATION": (KGEntityType.LOCATION, 0.80),
        "GPE": (KGEntityType.LOCATION, 0.80),  # Geo-political entity
        "FAC": (KGEntityType.LOCATION, 0.75),  # Facility
        "PRODUCT": (KGEntityType.OBJECT, 0.70),
        "EVENT": (KGEntityType.EVENT, 0.75),
        "WORK_OF_ART": (KGEntityType.CONCEPT, 0.65),
        "NORP": (KGEntityType.CONCEPT, 0.65),  # Nationality/religious/political
        "MISC": (KGEntityType.CONCEPT, 0.60),  # Miscellaneous
        # temporal labels
        "DATE_REL": (KGEntityType.TEMPORAL, 0.90),
        "DATE": (KGEntityType.TEMPORAL, 0.90),
        "DATE_ABS": (KGEntityType.TEMPORAL, 0.90),
        "TIME": (KGEntityType.TEMPORAL, 0.90),
        "TIME_REL": (KGEntityType.TEMPORAL, 0.90),
        "DURATION": (KGEntityType.TEMPORAL, 0.85),
    }

    # Nickname normalization map (family context)
    NICKNAME_MAP: dict[str, str] = {
        "wifey": "wife",
        "hubby": "husband",
        "kiddo": "child",
        "kiddos": "children",
        "grandma": "grandmother",
        "grandpa": "grandfather",
        "mom": "mother",
        "mommy": "mother",
        "mama": "mother",
        "mum": "mother",
        "dad": "father",
        "daddy": "father",
        "papa": "father",
        "sis": "sister",
        "bro": "brother",
        "granny": "grandmother",
        "gramps": "grandfather",
        "nana": "grandmother",
        "pop": "grandfather",
        "pa": "father",
        "ma": "mother",
    }

    def __init__(self) -> None:
        """Initialize the entity extractor."""
        self._metrics = EntityExtractionMetrics()

    @property
    def metrics(self) -> EntityExtractionMetrics:
        """Get current extraction metrics."""
        return self._metrics

    def reset_metrics(self) -> None:
        """Reset extraction metrics."""
        self._metrics = EntityExtractionMetrics()

    def extract_from_ultrabert(
        self,
        ner_family_output: dict[str, Any] | None = None,
        ner_general_output: dict[str, Any] | None = None,
        temporal_output: dict[str, Any] | None = None,
    ) -> list[ExtractedEntity]:
        """
        Extract and merge entities from all 3 UltraBERT NER heads.

        Args:
            ner_family_output: Output from ner_family head
                Format: {"entities": [{"text": "...", "label": "KINSHIP", ...}]}
            ner_general_output: Output from ner_general head
                Format: {"entities": [{"text": "...", "label": "PERSON", ...}]}
            temporal_output: Output from temporal head
                Format: {"entities": [{"text": "...", "label": "DATE_REL", ...}]}

        Returns:
            Merged, deduplicated list of ExtractedEntity objects
        """
        start_time = time.perf_counter()
        all_entities: list[ExtractedEntity] = []

        # Process ner_family head
        if ner_family_output:
            for entity in ner_family_output.get("entities", []):
                mapped = self._map_entity(entity, "ner_family")
                if mapped:
                    all_entities.append(mapped)
                    self._track_entity(mapped)

        # Process ner_general head
        if ner_general_output:
            for entity in ner_general_output.get("entities", []):
                mapped = self._map_entity(entity, "ner_general")
                if mapped:
                    all_entities.append(mapped)
                    self._track_entity(mapped)

        # Process temporal head
        if temporal_output:
            for entity in temporal_output.get("entities", []):
                mapped = self._map_entity(entity, "temporal")
                if mapped:
                    all_entities.append(mapped)
                    self._track_entity(mapped)

        # Deduplicate, keeping highest priority
        before_dedup = len(all_entities)
        entities = self._deduplicate_entities(all_entities)
        self._metrics.duplicates_removed = before_dedup - len(entities)
        self._metrics.entities_extracted = len(entities)
        self._metrics.processing_time_ms = (time.perf_counter() - start_time) * 1000

        logger.debug(
            "Entity extraction complete",
            extra={
                "entities_extracted": len(entities),
                "duplicates_removed": self._metrics.duplicates_removed,
                "processing_time_ms": round(self._metrics.processing_time_ms, 2),
            },
        )

        return entities

    def extract_from_full_result(
        self,
        ultrabert_result: dict[str, Any],
    ) -> list[ExtractedEntity]:
        """
        Extract entities from full UltraBERT analyze() result.

        Convenience method that extracts the 3 heads from the full result.

        Args:
            ultrabert_result: Full output from UltraBERT Client.analyze()

        Returns:
            Merged, deduplicated list of ExtractedEntity objects
        """
        # Handle both dict and object-style access
        if hasattr(ultrabert_result, "entities"):
            # Object-style (ClientResult)
            ner_family = {"entities": ultrabert_result.entities or []}
            ner_general = {"entities": ultrabert_result.general_entities or []}
            temporal = {"entities": ultrabert_result.temporal or []}
        else:
            # Dict-style
            ner_family = ultrabert_result.get("ner_family", {"entities": []})
            ner_general = ultrabert_result.get("ner_general", {"entities": []})
            temporal = ultrabert_result.get("temporal", {"entities": []})

        return self.extract_from_ultrabert(
            ner_family_output=ner_family,
            ner_general_output=ner_general,
            temporal_output=temporal,
        )

    def extract_hybrid(
        self,
        source_text: str,
        ner_family_output: dict[str, Any] | None = None,
        temporal_output: dict[str, Any] | None = None,
    ) -> list[ExtractedEntity]:
        """
        Extract entities using hybrid approach: UltraBERT for family + BERT-NER for general.

        This method is designed for P03 consolidation where we can afford the extra
        latency of running BERT-NER. It bypasses UltraBERT's broken ner_general head.

        Architecture:
        - ner_family: From UltraBERT (stored in st_hipp_events from P02)
        - temporal: From UltraBERT (stored in st_hipp_events from P02)
        - ner_general: From dslim/bert-base-NER (run fresh on source_text)

        This adds ~3.8ms latency per event but produces correct general NER.

        Args:
            source_text: Original event text to run BERT-NER on
            ner_family_output: UltraBERT ner_family output from P02
            temporal_output: UltraBERT temporal output from P02

        Returns:
            Merged, deduplicated list of ExtractedEntity objects
        """
        from k0.modules.consolidation.algorithms.bert_ner_adapter import get_bert_ner

        start_time = time.perf_counter()
        all_entities: list[ExtractedEntity] = []

        # Process ner_family from UltraBERT (this head is properly trained)
        if ner_family_output:
            for entity in ner_family_output.get("entities", []):
                mapped = self._map_entity(entity, "ner_family")
                if mapped:
                    all_entities.append(mapped)
                    self._track_entity(mapped)

        # Process temporal from UltraBERT (this head is properly trained)
        if temporal_output:
            for entity in temporal_output.get("entities", []):
                mapped = self._map_entity(entity, "temporal")
                if mapped:
                    all_entities.append(mapped)
                    self._track_entity(mapped)

        # Get general NER from BERT-NER instead of UltraBERT ner_general
        if source_text and source_text.strip():
            bert_ner = get_bert_ner()
            bert_results = bert_ner.extract(source_text)
            ner_general_output = bert_ner.to_ultrabert_format(bert_results)

            for entity in ner_general_output.get("entities", []):
                mapped = self._map_entity(entity, "bert_ner")  # Track source
                if mapped:
                    all_entities.append(mapped)
                    self._track_entity(mapped)

        # Deduplicate, keeping highest priority
        before_dedup = len(all_entities)
        entities = self._deduplicate_entities(all_entities)
        self._metrics.duplicates_removed = before_dedup - len(entities)
        self._metrics.entities_extracted = len(entities)
        self._metrics.processing_time_ms = (time.perf_counter() - start_time) * 1000

        logger.debug(
            "Hybrid entity extraction complete",
            extra={
                "entities_extracted": len(entities),
                "duplicates_removed": self._metrics.duplicates_removed,
                "processing_time_ms": round(self._metrics.processing_time_ms, 2),
                "mode": "hybrid",
            },
        )

        return entities

    def extract_hybrid_batch(
        self,
        events: list[tuple[str, dict[str, Any] | None, dict[str, Any] | None]],
    ) -> list[list[ExtractedEntity]]:
        """
        Batch hybrid extraction for multiple events.

        More efficient than calling extract_hybrid() in a loop because BERT-NER
        can process texts in batch (~1.5ms/event vs ~3.8ms/event).

        Args:
            events: List of (source_text, ner_family_output, temporal_output) tuples

        Returns:
            List of entity lists, one per input event
        """
        from k0.modules.consolidation.algorithms.bert_ner_adapter import get_bert_ner

        if not events:
            return []

        start_time = time.perf_counter()

        # Collect source texts for batch BERT-NER
        source_texts = [e[0] for e in events]

        # Run BERT-NER in batch
        bert_ner = get_bert_ner()
        batch_bert_results = bert_ner.extract_batch(source_texts)

        # Process each event
        results: list[list[ExtractedEntity]] = []

        for i, (source_text, ner_family_output, temporal_output) in enumerate(events):
            all_entities: list[ExtractedEntity] = []

            # Process ner_family from UltraBERT
            if ner_family_output:
                for entity in ner_family_output.get("entities", []):
                    mapped = self._map_entity(entity, "ner_family")
                    if mapped:
                        all_entities.append(mapped)
                        self._track_entity(mapped)

            # Process temporal from UltraBERT
            if temporal_output:
                for entity in temporal_output.get("entities", []):
                    mapped = self._map_entity(entity, "temporal")
                    if mapped:
                        all_entities.append(mapped)
                        self._track_entity(mapped)

            # Add BERT-NER results for this event
            bert_results = batch_bert_results[i]
            ner_general_output = bert_ner.to_ultrabert_format(bert_results)

            for entity in ner_general_output.get("entities", []):
                mapped = self._map_entity(entity, "bert_ner")
                if mapped:
                    all_entities.append(mapped)
                    self._track_entity(mapped)

            # Deduplicate per event
            entities = self._deduplicate_entities(all_entities)
            results.append(entities)

        total_ms = (time.perf_counter() - start_time) * 1000
        logger.debug(
            "Hybrid batch extraction complete",
            extra={
                "events_processed": len(events),
                "total_time_ms": round(total_ms, 2),
                "avg_time_ms": round(total_ms / len(events), 2) if events else 0,
                "mode": "hybrid_batch",
            },
        )

        return results

    # Location affordance keywords - phrases that indicate physical places
    # Used to reclassify ORGANIZATION -> LOCATION when appropriate
    LOCATION_AFFORDANCES: frozenset[str] = frozenset(
        {
            # Physical structures
            "park",
            "plaza",
            "square",
            "center",
            "centre",
            "complex",
            "building",
            "tower",
            "hall",
            "house",
            "home",
            "office",
            "school",
            "university",
            "college",
            "academy",
            "institute",
            "hospital",
            "clinic",
            "medical",
            "dental",
            "church",
            "temple",
            "mosque",
            "synagogue",
            "stadium",
            "arena",
            "gym",
            "field",
            "court",
            "pool",
            "restaurant",
            "cafe",
            "coffee",
            "bar",
            "pub",
            "grill",
            "diner",
            "hotel",
            "motel",
            "inn",
            "resort",
            "lodge",
            "store",
            "shop",
            "mall",
            "market",
            "supermarket",
            "station",
            "airport",
            "terminal",
            "port",
            "dock",
            "bridge",
            "tunnel",
            "road",
            "street",
            "avenue",
            "boulevard",
            "beach",
            "lake",
            "river",
            "mountain",
            "forest",
            "garden",
            # Geographic indicators
            "downtown",
            "uptown",
            "midtown",
            "north",
            "south",
            "east",
            "west",
        }
    )

    def _has_location_affordance(self, text: str) -> bool:
        """Check if entity text contains location-indicating words."""
        words = set(text.lower().split())
        return bool(words & self.LOCATION_AFFORDANCES)

    def is_complete_word(self, entity_text: str, source_text: str) -> bool:
        """Check if entity appears as a complete word in source text.

        This filters sub-word tokenization artifacts like:
        - "Fur" from "Fur Elise" (music title, not a word)
        - "San" from "San Francisco" (partial city name)
        - "Bella" from "Bella Notte" (partial restaurant name)

        Args:
            entity_text: The extracted entity text
            source_text: The original source text to validate against

        Returns:
            True if entity appears with word boundaries, False if it's a sub-word fragment
        """
        if not entity_text or not source_text:
            return True  # Can't validate, assume ok

        # Escape special regex chars and match as whole word
        # \b matches word boundaries (between \w and \W)
        pattern = r"\b" + re.escape(entity_text) + r"\b"
        return bool(re.search(pattern, source_text, re.IGNORECASE))

    def _is_valid_ner_family_entity(self, label: str, text: str, normalized: str) -> bool:
        """
        Validate ner_family entities that need text-based filtering.

        Called for labels in VALIDATED_NER_FAMILY to filter garbage extractions
        while keeping legitimate family-related entities.

        Args:
            label: The ner_family label (MILESTONE, FAMILY_EVENT, etc.)
            text: Original entity text
            normalized: Normalized entity text

        Returns:
            True if entity should be kept, False if it's garbage
        """
        # Check against garbage words
        if normalized.lower() in self.GARBAGE_ENTITY_WORDS:
            logger.debug(f"Filtered garbage entity: '{text}' ({label}) - in garbage list")
            return False

        # Filter single-character entities (tokenization artifacts)
        if len(normalized) <= 1:
            logger.debug(f"Filtered short entity: '{text}' ({label}) - too short")
            return False

        # Filter purely numeric entities ("10th", "2024")
        if normalized.replace(" ", "").isdigit():
            logger.debug(f"Filtered numeric entity: '{text}' ({label}) - purely numeric")
            return False

        # Label-specific validation
        if label == "MILESTONE":
            # Milestones should be nouns/noun phrases, not verbs
            # Keep: "graduation", "first steps", "wedding anniversary"
            # Reject: "learned", "accepted", "new"
            milestone_keywords = {
                "graduation",
                "wedding",
                "anniversary",
                "birthday",
                "birth",
                "baptism",
                "confirmation",
                "bar mitzvah",
                "bat mitzvah",
                "retirement",
                "promotion",
                "engagement",
                "divorce",
                "first steps",
                "first word",
                "first day",
                "license",
            }
            # Check if any keyword is in the normalized text
            if not any(kw in normalized.lower() for kw in milestone_keywords):
                # Also allow if it's a multi-word phrase (likely legitimate)
                if " " not in normalized:
                    logger.debug(f"Filtered milestone: '{text}' - no milestone keywords")
                    return False

        elif label == "HEIRLOOM":
            # Heirlooms should be physical objects
            # Keep: "ring", "watch", "Bible", "china set"
            # Reject: "to", "in", "old"
            heirloom_keywords = {
                "ring",
                "watch",
                "necklace",
                "bracelet",
                "earring",
                "jewelry",
                "bible",
                "book",
                "photo",
                "photograph",
                "album",
                "letter",
                "china",
                "silver",
                "crystal",
                "quilt",
                "blanket",
                "knife",
                "sword",
                "medal",
                "coin",
                "clock",
                "furniture",
                "painting",
                "portrait",
                "heirloom",
                "keepsake",
                "memento",
            }
            if not any(kw in normalized.lower() for kw in heirloom_keywords):
                logger.debug(f"Filtered heirloom: '{text}' - no heirloom keywords")
                return False

        elif label == "PET":
            # Pet should be animal names or species
            # Keep: "Buddy", "Max", "cat", "dog", "golden retriever"
            # Reject: "the", "for", "this"
            pet_keywords = {
                "dog",
                "cat",
                "bird",
                "fish",
                "hamster",
                "rabbit",
                "bunny",
                "parrot",
                "turtle",
                "snake",
                "lizard",
                "guinea pig",
                "retriever",
                "terrier",
                "poodle",
                "labrador",
                "shepherd",
                "siamese",
                "persian",
                "tabby",
                "kitten",
                "puppy",
            }
            # Accept if text is capitalized (likely a name) or contains pet keyword
            is_likely_name = text[0].isupper() and len(normalized) >= 2
            has_pet_keyword = any(kw in normalized.lower() for kw in pet_keywords)
            if not is_likely_name and not has_pet_keyword:
                logger.debug(f"Filtered pet: '{text}' - not a name or pet type")
                return False

        return True

    def _map_entity(
        self,
        raw: dict[str, Any],
        source_head: str,
    ) -> ExtractedEntity | None:
        """
        Map UltraBERT entity to KG entity type.

        Applies NER label filtering for ner_family head:
        - TRUSTED labels: Accept without question
        - REJECTED labels: Skip entirely (use BERT-NER instead)
        - VALIDATED labels: Apply text-based filtering

        Args:
            raw: Raw entity dict from UltraBERT
            source_head: Which NER head produced this entity

        Returns:
            ExtractedEntity or None if invalid/empty after normalization
        """
        label = raw.get("label", "")
        text = raw.get("text", "")

        if not label or not text:
            return None

        # === NER_FAMILY LABEL FILTERING ===
        # Only apply to ner_family head (not bert_ner or temporal)
        if source_head == "ner_family":
            # REJECTED: Skip entirely - BERT-NER provides better coverage
            if label in self.REJECTED_NER_FAMILY:
                logger.debug(f"Rejected ner_family PERSON: '{text}' - use BERT-NER instead")
                return None

            # VALIDATED: Check text quality before accepting
            if label in self.VALIDATED_NER_FAMILY:
                normalized_check = self.normalize_name(text)
                if not self._is_valid_ner_family_entity(label, text, normalized_check):
                    return None

            # TRUSTED: Accept without additional validation
            # (KINSHIP, NICKNAME, TRADITION, HOME_LOC fall through to normal processing)

        # === BERT-NER PERSON FILTERING ===
        # Filter common words that BERT-NER misclassifies as PERSON
        if source_head == "bert_ner" and label == "PERSON":
            normalized_check = self.normalize_name(text)
            if normalized_check.lower() in self.BERT_NER_PERSON_STOPWORDS:
                logger.debug(f"Filtered BERT-NER PERSON stopword: '{text}'")
                return None
            # Also filter single-character entities
            if len(normalized_check) <= 2:
                logger.debug(f"Filtered short BERT-NER PERSON: '{text}'")
                return None

        # === BERT-NER LOC FILTERING ===
        # Filter common words that BERT-NER misclassifies as LOC
        if source_head == "bert_ner" and label == "LOC":
            normalized_check = self.normalize_name(text)
            if normalized_check.lower() in self.BERT_NER_LOC_STOPWORDS:
                logger.debug(f"Filtered BERT-NER LOC stopword: '{text}'")
                return None
            # Also filter single-character entities
            if len(normalized_check) <= 2:
                logger.debug(f"Filtered short BERT-NER LOC: '{text}'")
                return None

        # Normalize first to catch empty results
        normalized = self.normalize_name(text)
        if not normalized:
            return None  # Cleaned to empty string (e.g., just punctuation)

        # Look up mapping
        mapping = self.LABEL_MAPPING.get(label)
        if not mapping:
            # Unknown label, default to CONCEPT with low priority
            mapping = (KGEntityType.CONCEPT, 0.50)
            self._metrics.unknown_labels += 1
            logger.debug(f"Unknown UltraBERT label: {label}")

        kg_type, priority = mapping

        # Reclassify ORGANIZATION -> LOCATION if text has location affordance
        # This fixes "City Sports Complex" being marked as ORG instead of LOCATION
        if kg_type == KGEntityType.ORGANIZATION and self._has_location_affordance(normalized):
            kg_type = KGEntityType.LOCATION
            logger.debug(f"Reclassified ORG->LOCATION: {normalized}")

        return ExtractedEntity(
            text=text,
            kg_type=kg_type,
            normalized_text=normalized,
            source_label=label,
            source_head=source_head,
            priority=priority,
            start_token=raw.get("start_token", 0),
            end_token=raw.get("end_token", 0),
        )

    def _track_entity(self, entity: ExtractedEntity) -> None:
        """Track entity in metrics."""
        # By head
        head_key = entity.source_head
        self._metrics.entities_by_head[head_key] = (
            self._metrics.entities_by_head.get(head_key, 0) + 1
        )

        # By type
        type_key = entity.kg_type.value
        self._metrics.entities_by_type[type_key] = (
            self._metrics.entities_by_type.get(type_key, 0) + 1
        )

    def normalize_name(self, name: str) -> str:
        """
        Normalize entity name for matching.

        Steps:
        1. Lowercase
        2. Strip whitespace
        3. Remove trailing possessives ('s, ')
        4. Remove trailing conjunctions (and, or)
        5. Remove punctuation
        6. Collapse multiple spaces
        7. Handle common nicknames (wifey -> wife)

        Args:
            name: Raw entity name

        Returns:
            Normalized entity name, or empty string if cleaned to nothing
        """
        normalized = name.lower().strip()

        # Remove trailing possessives: "sofia's" -> "sofia", "james'" -> "james"
        normalized = re.sub(r"'s$", "", normalized)
        normalized = re.sub(r"'$", "", normalized)

        # Remove trailing conjunctions: "emma and" -> "emma"
        normalized = re.sub(r"\s+(and|or|with)$", "", normalized)

        # Remove punctuation (but keep spaces)
        normalized = re.sub(r"[^\w\s]", "", normalized)

        # Collapse multiple spaces
        normalized = re.sub(r"\s+", " ", normalized).strip()

        # Apply nickname normalization
        if normalized in self.NICKNAME_MAP:
            normalized = self.NICKNAME_MAP[normalized]

        return normalized

    def _deduplicate_entities(
        self,
        entities: list[ExtractedEntity],
    ) -> list[ExtractedEntity]:
        """
        Remove duplicate entities, keeping highest priority.

        Duplicates defined by same normalized_text (regardless of kg_type).
        When duplicates found, keep the one with highest priority.
        This means KINSHIP "mom" beats PERSON "mom" since KINSHIP has higher priority.

        Args:
            entities: List of entities to deduplicate

        Returns:
            Deduplicated list
        """
        seen: dict[str, ExtractedEntity] = {}

        for entity in entities:
            # Key by normalized text only - same text should be deduplicated
            # even if labeled differently by different heads
            key = entity.normalized_text

            if key not in seen:
                seen[key] = entity
            elif entity.priority > seen[key].priority:
                # Keep higher priority (e.g., KINSHIP over PERSON)
                seen[key] = entity

        return list(seen.values())

    def to_entities_json(
        self,
        entities: list[ExtractedEntity],
    ) -> str:
        """
        Convert extracted entities to JSON for st_hipp_events.entities_json.

        Args:
            entities: List of extracted entities

        Returns:
            JSON string in the format expected by st_hipp_events
        """
        return json.dumps(
            {
                "entities": [e.to_dict() for e in entities],
                "extraction_version": "2.0",  # Matches UltraBERT v2.x
                "extractor": "UltraBERTEntityExtractor",
            }
        )

    async def process_event(
        self,
        event_id: str,
        ultrabert_result: dict[str, Any],
        db_conn: Any,
    ) -> int:
        """
        Process UltraBERT full result and store entities.

        Args:
            event_id: Event to update in st_hipp_events
            ultrabert_result: Full UltraBERT analyze() output with all heads
            db_conn: Database connection (asyncpg or similar)

        Returns:
            Count of extracted entities
        """
        entities = self.extract_from_full_result(ultrabert_result)
        entities_json = self.to_entities_json(entities)

        await db_conn.execute(
            """
            UPDATE st_hipp_events
            SET entities_json = $1,
                updated_at = $2
            WHERE event_id = $3
            """,
            entities_json,
            int(time.time() * 1000),  # now_ms
            event_id,
        )

        logger.debug(
            "Entity extraction stored",
            extra={
                "event_id": event_id,
                "entity_count": len(entities),
                "metrics": {
                    "by_head": self._metrics.entities_by_head,
                    "by_type": self._metrics.entities_by_type,
                },
            },
        )

        return len(entities)


def get_entity_extractor() -> UltraBERTEntityExtractor:
    """Get a new entity extractor instance.

    Returns:
        Fresh UltraBERTEntityExtractor instance
    """
    return UltraBERTEntityExtractor()
