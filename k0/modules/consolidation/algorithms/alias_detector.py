"""
R4 Alias Detector — Entity Coreference and Alias Detection for KG Consolidation.

GAP-004: Entity Alias Merging Missing
Spec Reference: MEMORY_LAYER_GAPS_FIX_PLAN.md §GAP-004

This module detects potential entity aliases (coreference) using multiple signals:
1. String Similarity: Levenshtein, token sort, partial ratio (via rapidfuzz)
2. Embedding Similarity: Cosine distance in embedding space
3. Nickname Database: Common first-name mappings (Bob↔Robert, Bill↔William)
4. Family Nickname Database: Kinship terms (Mom↔Mother, Dad↔Father)
5. Co-occurrence Exclusion: Entities that never appear together may be same

Neurological Foundation:
- Temporal Lobe semantic networks maintain unified representations
- Brain automatically resolves "Mom", "Mother", "Mama" to same concept
- This module mimics that coreference resolution for the knowledge graph

Architecture:
- AliasCandidate: Potential alias pair with confidence scores
- AliasDetector: Main class for detecting aliases
- FirstNameDatabase: English first-name nickname mappings
- AliasScorer: Multi-signal scoring with configurable weights

Performance:
- Alias detection: O(n²) for n entities (pairwise comparison)
- Individual comparison: <1ms per pair
- Batched comparison: Uses efficient filtering to reduce comparisons

Integration:
- Called from R4 KG Consolidator after entity extraction
- Outputs AliasCandidate list for entity merging
- Updates aliases_json field via EntityMerger

Author: K0 Architecture Team
Date: 2026-01-16
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration Constants
# =============================================================================

# Minimum combined score to consider entities as aliases
ALIAS_DETECTION_THRESHOLD: float = 0.70

# Individual signal thresholds
STRING_SIMILARITY_THRESHOLD: float = 0.75
EMBEDDING_SIMILARITY_THRESHOLD: float = 0.85
NICKNAME_MATCH_SCORE: float = 0.95  # High confidence for known nickname pairs

# Signal weights for combined score
WEIGHT_STRING_SIMILARITY: float = 0.25
WEIGHT_EMBEDDING_SIMILARITY: float = 0.30
WEIGHT_NICKNAME_MATCH: float = 0.25
WEIGHT_CO_OCCURRENCE: float = 0.20

# Minimum entity observations before considering for alias detection
MIN_OBSERVATIONS_FOR_ALIAS: int = 2


# =============================================================================
# Enums
# =============================================================================


class AliasType(str, Enum):
    """Type of alias relationship detected."""

    NICKNAME = "NICKNAME"  # Bob → Robert (first name nickname)
    FAMILY_ROLE = "FAMILY_ROLE"  # Mom → Mother (kinship term)
    DIMINUTIVE = "DIMINUTIVE"  # Johnny → John (diminutive form)
    SPELLING_VARIANT = "SPELLING_VARIANT"  # Cathy → Kathy
    ABBREVIATION = "ABBREVIATION"  # Dr. Smith → Doctor Smith
    SEMANTIC_EQUIVALENT = "SEMANTIC_EQUIVALENT"  # High embedding similarity
    CO_REFERENCE = "CO_REFERENCE"  # Never co-occur, same entity type


# =============================================================================
# First Name Nickname Database
# =============================================================================


class FirstNameDatabase:
    """
    Database of common English first name nicknames.

    Maps formal names to their common nicknames and vice versa.
    Bidirectional lookup: both Robert→Bob and Bob→Robert work.

    Source: Common English naming conventions.
    """

    # Formal name → list of nicknames
    _NICKNAME_MAP: Dict[str, List[str]] = {
        # Male names
        "Robert": ["Rob", "Bob", "Bobby", "Robbie", "Bert"],
        "William": ["Will", "Bill", "Billy", "Willy", "Liam"],
        "Richard": ["Rich", "Rick", "Dick", "Ricky"],
        "Michael": ["Mike", "Mikey", "Mick"],
        "James": ["Jim", "Jimmy", "Jamie"],
        "John": ["Johnny", "Jack", "Jon"],
        "Thomas": ["Tom", "Tommy"],
        "Joseph": ["Joe", "Joey"],
        "Charles": ["Charlie", "Chuck", "Chas"],
        "David": ["Dave", "Davey"],
        "Daniel": ["Dan", "Danny"],
        "Christopher": ["Chris", "Topher"],
        "Matthew": ["Matt", "Matty"],
        "Andrew": ["Andy", "Drew"],
        "Anthony": ["Tony", "Ant"],
        "Steven": ["Steve", "Stevie"],
        "Stephen": ["Steve", "Stevie"],
        "Edward": ["Ed", "Eddie", "Ted", "Teddy"],
        "Benjamin": ["Ben", "Benny", "Benji"],
        "Nicholas": ["Nick", "Nicky"],
        "Alexander": ["Alex", "Al", "Xander"],
        "Patrick": ["Pat", "Paddy"],
        "Peter": ["Pete"],
        "Timothy": ["Tim", "Timmy"],
        "Kenneth": ["Ken", "Kenny"],
        "Ronald": ["Ron", "Ronnie"],
        "Donald": ["Don", "Donnie"],
        "Gregory": ["Greg"],
        "Lawrence": ["Larry"],
        "Samuel": ["Sam", "Sammy"],
        "Jonathan": ["Jon", "Johnny"],
        "Raymond": ["Ray"],
        "Frederick": ["Fred", "Freddy", "Rick"],
        "Albert": ["Al", "Bert", "Bertie"],
        "Gerald": ["Jerry", "Gerry"],
        "Harold": ["Harry", "Hal"],
        "Jeffrey": ["Jeff"],
        "Leonard": ["Len", "Lenny", "Leo"],
        "Theodore": ["Ted", "Teddy", "Theo"],
        "Vincent": ["Vince", "Vinnie"],
        "Walter": ["Walt", "Wally"],
        "Zachary": ["Zach", "Zack"],
        # Female names
        "Elizabeth": ["Liz", "Lizzy", "Beth", "Betty", "Eliza", "Ellie"],
        "Katherine": ["Kate", "Katie", "Kathy", "Cathy", "Kit", "Kitty"],
        "Catherine": ["Kate", "Katie", "Kathy", "Cathy", "Cat"],
        "Margaret": ["Maggie", "Meg", "Peggy", "Marge", "Margie"],
        "Jennifer": ["Jen", "Jenny"],
        "Patricia": ["Pat", "Patty", "Trish"],
        "Barbara": ["Barb", "Barbie"],
        "Susan": ["Sue", "Susie", "Suzy"],
        "Jessica": ["Jess", "Jessie"],
        "Dorothy": ["Dot", "Dottie", "Dolly"],
        "Christine": ["Chris", "Chrissy", "Tina"],
        "Christina": ["Chris", "Chrissy", "Tina"],
        "Rebecca": ["Becky", "Becca"],
        "Victoria": ["Vicky", "Vikki", "Tori"],
        "Stephanie": ["Steph", "Stephie"],
        "Samantha": ["Sam", "Sammy"],
        "Alexandra": ["Alex", "Lexi", "Sandra"],
        "Jacqueline": ["Jackie"],
        "Deborah": ["Debbie", "Deb"],
        "Kimberly": ["Kim", "Kimmy"],
        "Melissa": ["Missy", "Mel", "Lissa"],
        "Michelle": ["Micky", "Shelly"],
        "Pamela": ["Pam"],
        "Rachel": ["Rach"],
        "Theresa": ["Terry", "Terri", "Tess"],
        "Teresa": ["Terry", "Terri", "Tess"],
        "Valerie": ["Val"],
        "Amanda": ["Mandy", "Amy"],
        "Abigail": ["Abby", "Gail"],
        "Allison": ["Ally", "Ali"],
        "Alison": ["Ally", "Ali"],
        "Beatrice": ["Bea", "Trixie"],
        "Carolyn": ["Carol", "Carrie", "Lynn"],
        "Caroline": ["Carol", "Carrie", "Caro"],
        "Francesca": ["Fran", "Frankie"],
        "Gabrielle": ["Gabby", "Gabi"],
        "Joanna": ["Jo", "Joanie"],
        "Josephine": ["Jo", "Josie"],
        "Madeline": ["Maddy", "Maddie"],
        "Madeleine": ["Maddy", "Maddie"],
        "Natalie": ["Nat", "Natty"],
        "Penelope": ["Penny"],
        "Priscilla": ["Cilla", "Prissy"],
        "Veronica": ["Ronnie", "Roni", "Vera"],
    }

    # Cache for reverse lookup (nickname → formal names)
    _REVERSE_MAP: Dict[str, List[str]] = {}

    @classmethod
    def _build_reverse_map(cls) -> None:
        """Build reverse lookup map on first use."""
        if cls._REVERSE_MAP:
            return

        for formal, nicknames in cls._NICKNAME_MAP.items():
            for nick in nicknames:
                nick_lower = nick.lower()
                if nick_lower not in cls._REVERSE_MAP:
                    cls._REVERSE_MAP[nick_lower] = []
                cls._REVERSE_MAP[nick_lower].append(formal)

    @classmethod
    def get_nicknames(cls, formal_name: str) -> List[str]:
        """Get nicknames for a formal name."""
        return cls._NICKNAME_MAP.get(formal_name, [])

    @classmethod
    def get_formal_names(cls, nickname: str) -> List[str]:
        """Get formal names for a nickname."""
        cls._build_reverse_map()
        return cls._REVERSE_MAP.get(nickname.lower(), [])

    @classmethod
    def are_aliases(cls, name1: str, name2: str) -> bool:
        """Check if two names are known aliases of each other."""
        name1_lower = name1.lower().strip()
        name2_lower = name2.lower().strip()

        # Same name
        if name1_lower == name2_lower:
            return False  # Not aliases, same name

        # Check if name1 is formal and name2 is nickname
        if name1 in cls._NICKNAME_MAP:
            if any(n.lower() == name2_lower for n in cls._NICKNAME_MAP[name1]):
                return True

        # Check if name2 is formal and name1 is nickname
        if name2 in cls._NICKNAME_MAP:
            if any(n.lower() == name1_lower for n in cls._NICKNAME_MAP[name2]):
                return True

        # Check reverse: both might be nicknames of same formal name
        cls._build_reverse_map()
        formal1 = set(cls._REVERSE_MAP.get(name1_lower, []))
        formal2 = set(cls._REVERSE_MAP.get(name2_lower, []))
        if formal1 & formal2:  # Intersection - share a formal name
            return True

        # Try with capitalized versions
        name1_cap = name1.capitalize()
        name2_cap = name2.capitalize()
        if name1_cap in cls._NICKNAME_MAP:
            if any(n.lower() == name2_lower for n in cls._NICKNAME_MAP[name1_cap]):
                return True
        if name2_cap in cls._NICKNAME_MAP:
            if any(n.lower() == name1_lower for n in cls._NICKNAME_MAP[name2_cap]):
                return True

        return False

    @classmethod
    def get_canonical_name(cls, name: str) -> str:
        """Get canonical (formal) name for a nickname, or return as-is."""
        cls._build_reverse_map()
        formal_names = cls._REVERSE_MAP.get(name.lower(), [])
        if formal_names:
            return formal_names[0]  # Return first formal name
        return name


# =============================================================================
# Family Role Nickname Database
# =============================================================================


class FamilyRoleDatabase:
    """
    Database of family role nicknames (kinship terms).

    Maps informal kinship terms to formal terms.
    Already exists in entity_extractor.py, but duplicated here for alias detection.
    """

    _ROLE_MAP: Dict[str, str] = {
        "mom": "mother",
        "mommy": "mother",
        "mama": "mother",
        "mum": "mother",
        "ma": "mother",
        "dad": "father",
        "daddy": "father",
        "papa": "father",
        "pa": "father",
        "pop": "father",
        "grandma": "grandmother",
        "granny": "grandmother",
        "nana": "grandmother",
        "nan": "grandmother",
        "grandpa": "grandfather",
        "gramps": "grandfather",
        "pops": "grandfather",
        "sis": "sister",
        "bro": "brother",
        "wifey": "wife",
        "hubby": "husband",
        "kiddo": "child",
        "kiddos": "children",
    }

    # Reverse map for bidirectional lookup
    _REVERSE_MAP: Dict[str, List[str]] = {}

    @classmethod
    def _build_reverse_map(cls) -> None:
        """Build reverse lookup map on first use."""
        if cls._REVERSE_MAP:
            return

        for informal, formal in cls._ROLE_MAP.items():
            if formal not in cls._REVERSE_MAP:
                cls._REVERSE_MAP[formal] = []
            cls._REVERSE_MAP[formal].append(informal)

    @classmethod
    def are_aliases(cls, name1: str, name2: str) -> bool:
        """Check if two names are family role aliases."""
        name1_lower = name1.lower().strip()
        name2_lower = name2.lower().strip()

        if name1_lower == name2_lower:
            return False

        # Get formal forms
        formal1 = cls._ROLE_MAP.get(name1_lower, name1_lower)
        formal2 = cls._ROLE_MAP.get(name2_lower, name2_lower)

        return formal1 == formal2

    @classmethod
    def get_canonical(cls, name: str) -> str:
        """Get canonical (formal) kinship term."""
        return cls._ROLE_MAP.get(name.lower().strip(), name)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class AliasCandidate:
    """
    Represents a potential alias relationship between two entities.

    Attributes:
        entity1_id: ID of first entity
        entity1_name: Name of first entity
        entity2_id: ID of second entity
        entity2_name: Name of second entity
        entity_type: Shared entity type (PERSON, FAMILY_MEMBER, etc.)
        alias_type: Type of alias relationship detected
        combined_score: Overall confidence score (0.0-1.0)
        string_score: String similarity score
        embedding_score: Embedding similarity score
        nickname_match: True if known nickname pair
        co_occurrence_score: Co-occurrence exclusion score
        recommended_primary: ID of entity to keep as primary
        recommended_aliases: Names to add to aliases_json
    """

    entity1_id: str
    entity1_name: str
    entity2_id: str
    entity2_name: str
    entity_type: str
    alias_type: AliasType
    combined_score: float
    string_score: float = 0.0
    embedding_score: float = 0.0
    nickname_match: bool = False
    co_occurrence_score: float = 0.0
    recommended_primary: str = ""
    recommended_aliases: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "entity1_id": self.entity1_id,
            "entity1_name": self.entity1_name,
            "entity2_id": self.entity2_id,
            "entity2_name": self.entity2_name,
            "entity_type": self.entity_type,
            "alias_type": self.alias_type.value,
            "combined_score": round(self.combined_score, 4),
            "string_score": round(self.string_score, 4),
            "embedding_score": round(self.embedding_score, 4),
            "nickname_match": self.nickname_match,
            "co_occurrence_score": round(self.co_occurrence_score, 4),
            "recommended_primary": self.recommended_primary,
            "recommended_aliases": self.recommended_aliases,
        }


@dataclass
class EntityInfo:
    """Entity information for alias detection."""

    entity_id: str
    canonical_name: str
    entity_type: str
    observation_count: int = 0
    embedding: Optional[np.ndarray] = None
    source_event_ids: List[str] = field(default_factory=list)
    aliases_json: str = "[]"

    @property
    def existing_aliases(self) -> List[str]:
        """Parse existing aliases from JSON."""
        try:
            return json.loads(self.aliases_json) if self.aliases_json else []
        except json.JSONDecodeError:
            return []


@dataclass
class AliasDetectionMetrics:
    """Metrics for alias detection operations."""

    entities_analyzed: int = 0
    pairs_compared: int = 0
    candidates_found: int = 0
    nickname_matches: int = 0
    family_role_matches: int = 0
    embedding_matches: int = 0
    string_matches: int = 0
    processing_time_ms: float = 0.0


# =============================================================================
# Alias Scorer
# =============================================================================


class AliasScorer:
    """
    Multi-signal scoring for alias detection.

    Combines multiple signals with configurable weights to produce
    a combined confidence score for potential aliases.
    """

    def __init__(
        self,
        weight_string: float = WEIGHT_STRING_SIMILARITY,
        weight_embedding: float = WEIGHT_EMBEDDING_SIMILARITY,
        weight_nickname: float = WEIGHT_NICKNAME_MATCH,
        weight_co_occurrence: float = WEIGHT_CO_OCCURRENCE,
    ):
        """Initialize scorer with weights."""
        self.weight_string = weight_string
        self.weight_embedding = weight_embedding
        self.weight_nickname = weight_nickname
        self.weight_co_occurrence = weight_co_occurrence

    def compute_string_similarity(self, name1: str, name2: str) -> Tuple[float, str]:
        """
        Compute string similarity using best-of-three matching.

        Uses Levenshtein ratio, token sort ratio, and partial ratio,
        returning the highest score.

        Returns:
            Tuple of (score, algorithm_used)
        """
        # Normalize names
        name1_norm = name1.lower().strip()
        name2_norm = name2.lower().strip()

        # Compute all three metrics
        levenshtein = fuzz.ratio(name1_norm, name2_norm) / 100.0
        token_sort = fuzz.token_sort_ratio(name1_norm, name2_norm) / 100.0
        partial = fuzz.partial_ratio(name1_norm, name2_norm) / 100.0

        # Return best score with algorithm name
        scores = [
            (levenshtein, "levenshtein"),
            (token_sort, "token_sort"),
            (partial, "partial"),
        ]
        return max(scores, key=lambda x: x[0])

    def compute_embedding_similarity(
        self,
        embedding1: Optional[np.ndarray],
        embedding2: Optional[np.ndarray],
    ) -> float:
        """
        Compute cosine similarity between embeddings.

        Returns 0.0 if either embedding is None.
        """
        if embedding1 is None or embedding2 is None:
            return 0.0

        # Ensure arrays
        e1 = np.asarray(embedding1).flatten()
        e2 = np.asarray(embedding2).flatten()

        # Check dimensions match
        if e1.shape != e2.shape:
            return 0.0

        # Compute cosine similarity
        dot = np.dot(e1, e2)
        norm1 = np.linalg.norm(e1)
        norm2 = np.linalg.norm(e2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot / (norm1 * norm2))

    def check_nickname_match(self, name1: str, name2: str, entity_type: str) -> bool:
        """
        Check if names are known nickname pairs.

        Checks both first-name nicknames and family role nicknames.
        """
        # Check first-name nicknames for PERSON entities
        if entity_type in ("PERSON", "FAMILY_MEMBER"):
            if FirstNameDatabase.are_aliases(name1, name2):
                return True

        # Check family role nicknames for FAMILY_MEMBER entities
        if entity_type == "FAMILY_MEMBER":
            if FamilyRoleDatabase.are_aliases(name1, name2):
                return True

        return False

    def compute_co_occurrence_score(
        self,
        events1: List[str],
        events2: List[str],
    ) -> float:
        """
        Compute co-occurrence exclusion score.

        Entities that NEVER appear together are more likely to be the same
        entity (mutual exclusion principle). This is a weak signal but
        useful as a confirmatory factor.

        Returns:
            0.0 if entities co-occur often (different entities)
            1.0 if entities never co-occur (may be same entity)
        """
        set1 = set(events1)
        set2 = set(events2)

        # If no events, return neutral score
        if not set1 or not set2:
            return 0.5

        # Count overlap
        overlap = len(set1 & set2)
        union = len(set1 | set2)

        if union == 0:
            return 0.5

        # Jaccard similarity - invert for exclusion score
        jaccard = overlap / union

        # 0 overlap = high exclusion score (may be same entity)
        # High overlap = low exclusion score (different entities)
        return 1.0 - jaccard

    def compute_combined_score(
        self,
        string_score: float,
        embedding_score: float,
        nickname_match: bool,
        co_occurrence_score: float,
    ) -> float:
        """
        Compute combined alias confidence score.

        Nickname matches get a boost since they're high-confidence signals.
        """
        # Nickname match is binary - use as boost
        nickname_score = NICKNAME_MATCH_SCORE if nickname_match else 0.0

        # Weighted combination
        combined = (
            self.weight_string * string_score
            + self.weight_embedding * embedding_score
            + self.weight_nickname * nickname_score
            + self.weight_co_occurrence * co_occurrence_score
        )

        # Clamp to [0, 1]
        return max(0.0, min(1.0, combined))


# =============================================================================
# Alias Detector
# =============================================================================


class AliasDetector:
    """
    Main class for detecting entity aliases.

    Analyzes a collection of entities and identifies potential alias
    relationships using multiple signals.
    """

    def __init__(
        self,
        threshold: float = ALIAS_DETECTION_THRESHOLD,
        min_observations: int = MIN_OBSERVATIONS_FOR_ALIAS,
    ):
        """
        Initialize detector.

        Args:
            threshold: Minimum combined score to consider as alias
            min_observations: Minimum observations before considering
        """
        self.threshold = threshold
        self.min_observations = min_observations
        self.scorer = AliasScorer()
        self._metrics = AliasDetectionMetrics()

    @property
    def metrics(self) -> AliasDetectionMetrics:
        """Return detection metrics."""
        return self._metrics

    def detect(
        self,
        entities: List[EntityInfo],
    ) -> List[AliasCandidate]:
        """
        Detect potential aliases among entities.

        Args:
            entities: List of EntityInfo objects to analyze

        Returns:
            List of AliasCandidate objects above threshold
        """
        import time

        start_time = time.time()
        self._metrics = AliasDetectionMetrics()
        self._metrics.entities_analyzed = len(entities)

        candidates: List[AliasCandidate] = []

        # Filter entities by minimum observations
        eligible = [e for e in entities if e.observation_count >= self.min_observations]

        # Group by entity type for efficient comparison
        by_type: Dict[str, List[EntityInfo]] = {}
        for entity in eligible:
            if entity.entity_type not in by_type:
                by_type[entity.entity_type] = []
            by_type[entity.entity_type].append(entity)

        # Compare within each type
        for entity_type, type_entities in by_type.items():
            type_candidates = self._detect_within_type(type_entities, entity_type)
            candidates.extend(type_candidates)

        # Sort by combined score descending
        candidates.sort(key=lambda c: c.combined_score, reverse=True)

        self._metrics.candidates_found = len(candidates)
        self._metrics.processing_time_ms = (time.time() - start_time) * 1000

        logger.info(
            "Alias detection complete",
            extra={
                "entities_analyzed": self._metrics.entities_analyzed,
                "pairs_compared": self._metrics.pairs_compared,
                "candidates_found": self._metrics.candidates_found,
                "processing_time_ms": round(self._metrics.processing_time_ms, 2),
            },
        )

        return candidates

    def _detect_within_type(
        self,
        entities: List[EntityInfo],
        entity_type: str,
    ) -> List[AliasCandidate]:
        """Detect aliases within a single entity type."""
        candidates: List[AliasCandidate] = []
        n = len(entities)

        for i in range(n):
            for j in range(i + 1, n):
                e1 = entities[i]
                e2 = entities[j]
                self._metrics.pairs_compared += 1

                candidate = self._evaluate_pair(e1, e2, entity_type)
                if candidate and candidate.combined_score >= self.threshold:
                    candidates.append(candidate)

        return candidates

    def _evaluate_pair(
        self,
        e1: EntityInfo,
        e2: EntityInfo,
        entity_type: str,
    ) -> Optional[AliasCandidate]:
        """Evaluate a single entity pair for alias relationship."""
        # Skip if same entity or already merged
        if e1.entity_id == e2.entity_id:
            return None

        # Skip if one is already an alias of the other
        if e1.canonical_name in e2.existing_aliases:
            return None
        if e2.canonical_name in e1.existing_aliases:
            return None

        # Compute signals
        string_score, _ = self.scorer.compute_string_similarity(
            e1.canonical_name, e2.canonical_name
        )

        embedding_score = self.scorer.compute_embedding_similarity(e1.embedding, e2.embedding)

        nickname_match = self.scorer.check_nickname_match(
            e1.canonical_name, e2.canonical_name, entity_type
        )

        co_occurrence_score = self.scorer.compute_co_occurrence_score(
            e1.source_event_ids, e2.source_event_ids
        )

        # Compute combined score
        combined_score = self.scorer.compute_combined_score(
            string_score=string_score,
            embedding_score=embedding_score,
            nickname_match=nickname_match,
            co_occurrence_score=co_occurrence_score,
        )

        # Early exit if below threshold
        if combined_score < self.threshold:
            return None

        # Update metrics
        if nickname_match:
            self._metrics.nickname_matches += 1
        if string_score >= STRING_SIMILARITY_THRESHOLD:
            self._metrics.string_matches += 1
        if embedding_score >= EMBEDDING_SIMILARITY_THRESHOLD:
            self._metrics.embedding_matches += 1

        # Determine alias type
        alias_type = self._determine_alias_type(
            e1.canonical_name,
            e2.canonical_name,
            entity_type,
            string_score,
            embedding_score,
            nickname_match,
        )

        # Determine primary entity (higher observation count wins)
        if e1.observation_count >= e2.observation_count:
            primary_id = e1.entity_id
            recommended_aliases = [e2.canonical_name]
        else:
            primary_id = e2.entity_id
            recommended_aliases = [e1.canonical_name]

        return AliasCandidate(
            entity1_id=e1.entity_id,
            entity1_name=e1.canonical_name,
            entity2_id=e2.entity_id,
            entity2_name=e2.canonical_name,
            entity_type=entity_type,
            alias_type=alias_type,
            combined_score=combined_score,
            string_score=string_score,
            embedding_score=embedding_score,
            nickname_match=nickname_match,
            co_occurrence_score=co_occurrence_score,
            recommended_primary=primary_id,
            recommended_aliases=recommended_aliases,
        )

    def _determine_alias_type(
        self,
        name1: str,
        name2: str,
        entity_type: str,
        string_score: float,
        embedding_score: float,
        nickname_match: bool,
    ) -> AliasType:
        """Determine the type of alias relationship."""
        # Check first-name nickname
        if nickname_match and entity_type in ("PERSON", "FAMILY_MEMBER"):
            if FirstNameDatabase.are_aliases(name1, name2):
                return AliasType.NICKNAME

        # Check family role
        if nickname_match and entity_type == "FAMILY_MEMBER":
            if FamilyRoleDatabase.are_aliases(name1, name2):
                return AliasType.FAMILY_ROLE

        # Check diminutive (e.g., Johnny → John)
        if self._is_diminutive(name1, name2):
            return AliasType.DIMINUTIVE

        # Check spelling variant (e.g., Cathy/Kathy)
        if string_score >= 0.85 and not nickname_match:
            return AliasType.SPELLING_VARIANT

        # Check semantic equivalent (high embedding similarity)
        if embedding_score >= EMBEDDING_SIMILARITY_THRESHOLD:
            return AliasType.SEMANTIC_EQUIVALENT

        # Default to co-reference
        return AliasType.CO_REFERENCE

    def _is_diminutive(self, name1: str, name2: str) -> bool:
        """Check if one name is a diminutive of the other (e.g., Johnny → John)."""
        n1 = name1.lower()
        n2 = name2.lower()

        # Common diminutive suffixes
        diminutive_suffixes = ["y", "ie", "ey", "ey"]

        for suffix in diminutive_suffixes:
            if n1.endswith(suffix) and n2 == n1[: -len(suffix)]:
                return True
            if n2.endswith(suffix) and n1 == n2[: -len(suffix)]:
                return True

        return False

    def detect_from_dicts(
        self,
        entity_dicts: List[Dict[str, Any]],
    ) -> List[AliasCandidate]:
        """
        Convenience method to detect aliases from dictionary format.

        Args:
            entity_dicts: List of entity dictionaries with keys:
                - entity_id: str
                - canonical_name: str
                - entity_type: str
                - observation_count: int (optional)
                - embedding: list[float] (optional)
                - source_event_ids: list[str] (optional)
                - aliases_json: str (optional)

        Returns:
            List of AliasCandidate objects
        """
        entities = []
        for d in entity_dicts:
            embedding = None
            if "embedding" in d and d["embedding"]:
                embedding = np.array(d["embedding"])

            entities.append(
                EntityInfo(
                    entity_id=d["entity_id"],
                    canonical_name=d["canonical_name"],
                    entity_type=d["entity_type"],
                    observation_count=d.get("observation_count", 1),
                    embedding=embedding,
                    source_event_ids=d.get("source_event_ids", []),
                    aliases_json=d.get("aliases_json", "[]"),
                )
            )

        return self.detect(entities)
