"""
SubtypeClassifier — GAP-005 Fine-Grained Subtype Classification.

Classifies fine-grained subtypes for memory layer records:
- st_sem.pattern_subtype: HEALTH_THEME, WORK_THEME, RELATIONSHIP_THEME, etc.
- st_kg_dom.entity_subtype: FAMILY_MEMBER, FRIEND, PROFESSIONAL, etc.
- st_social.relationship_subtype: (enhanced from existing R4 logic)

Neurological Basis:
    Prefrontal Cortex (Category Hierarchies) + Temporal Lobe (Semantic Taxonomy)
    - Hierarchical categorization: Superordinate → Basic → Subordinate
    - Prototype theory: Brain stores prototypical examples of subcategories
    - Feature-based classification: Subtypes defined by distinctive feature bundles

References:
    - MEMORY_LAYER_GAPS_FIX_PLAN.md GAP-005
    - Dossier §6.4 st_sem (pattern_subtype column)
    - Dossier §6.8 st_kg_dom (entity_subtype column)
    - Dossier §6.6 st_social (relationship_subtype column)

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# SUBTYPE ENUMS
# =============================================================================


class PatternSubtype(str, Enum):
    """
    Fine-grained subtypes for st_sem.pattern_type.

    THEME subtypes:
        - HEALTH_THEME: Health, exercise, wellness, medical
        - WORK_THEME: Career, projects, meetings, deadlines
        - RELATIONSHIP_THEME: Friends, family, social dynamics
        - FINANCE_THEME: Money, budget, investments
        - LEISURE_THEME: Hobbies, entertainment, recreation
        - LEARNING_THEME: Education, skills, personal growth

    LESSON subtypes:
        - CAUTIONARY_TALE: Negative outcome, warning, regret
        - BEST_PRACTICE: Positive outcome, success, recommendation
        - INSIGHT: Neutral analysis, realization, connection

    EMOTIONAL_TREND subtypes:
        - STRESS_PATTERN: Increasing or sustained stress
        - JOY_PATTERN: Sustained positive emotions
        - ANXIETY_PATTERN: Worry, fear, uncertainty
        - BURNOUT_PATTERN: Exhaustion, overwhelm

    ROUTINE subtypes:
        - MORNING_ROUTINE: Morning habits
        - EVENING_ROUTINE: Evening/night habits
        - WORK_ROUTINE: Work-related habits
        - EXERCISE_ROUTINE: Fitness habits
        - SOCIAL_ROUTINE: Regular social activities
    """

    # THEME subtypes
    HEALTH_THEME = "HEALTH_THEME"
    WORK_THEME = "WORK_THEME"
    RELATIONSHIP_THEME = "RELATIONSHIP_THEME"
    FINANCE_THEME = "FINANCE_THEME"
    LEISURE_THEME = "LEISURE_THEME"
    LEARNING_THEME = "LEARNING_THEME"

    # LESSON subtypes
    CAUTIONARY_TALE = "CAUTIONARY_TALE"
    BEST_PRACTICE = "BEST_PRACTICE"
    INSIGHT = "INSIGHT"

    # EMOTIONAL_TREND subtypes
    STRESS_PATTERN = "STRESS_PATTERN"
    JOY_PATTERN = "JOY_PATTERN"
    ANXIETY_PATTERN = "ANXIETY_PATTERN"
    BURNOUT_PATTERN = "BURNOUT_PATTERN"

    # ROUTINE subtypes
    MORNING_ROUTINE = "MORNING_ROUTINE"
    EVENING_ROUTINE = "EVENING_ROUTINE"
    WORK_ROUTINE = "WORK_ROUTINE"
    EXERCISE_ROUTINE = "EXERCISE_ROUTINE"
    SOCIAL_ROUTINE = "SOCIAL_ROUTINE"

    # PREFERENCE subtypes
    FOOD_PREFERENCE = "FOOD_PREFERENCE"
    ACTIVITY_PREFERENCE = "ACTIVITY_PREFERENCE"
    LOCATION_PREFERENCE = "LOCATION_PREFERENCE"
    SOCIAL_PREFERENCE = "SOCIAL_PREFERENCE"

    # GOAL subtypes
    HEALTH_GOAL = "HEALTH_GOAL"
    CAREER_GOAL = "CAREER_GOAL"
    FINANCIAL_GOAL = "FINANCIAL_GOAL"
    PERSONAL_GOAL = "PERSONAL_GOAL"
    RELATIONSHIP_GOAL = "RELATIONSHIP_GOAL"

    # VALUE subtypes
    FAMILY_VALUE = "FAMILY_VALUE"
    CAREER_VALUE = "CAREER_VALUE"
    HEALTH_VALUE = "HEALTH_VALUE"
    SOCIAL_VALUE = "SOCIAL_VALUE"


class EntitySubtype(str, Enum):
    """
    Fine-grained subtypes for st_kg_dom.entity_type.

    PERSON subtypes:
        - FAMILY_MEMBER: Has FAMILY relationship
        - FRIEND: Has FRIEND relationship
        - PROFESSIONAL: Appears in work contexts
        - CELEBRITY: Public figure, not personally known
        - SERVICE_PROVIDER: Doctor, hairdresser, etc.

    LOCATION subtypes:
        - HOME: Frequent presence, domestic activities
        - WORKPLACE: Work activities, colleagues present
        - RECREATIONAL: Leisure activities
        - TRANSIT: Commute, travel
        - COMMERCIAL: Shopping, services
        - HEALTHCARE: Hospital, clinic, pharmacy

    ORGANIZATION subtypes:
        - EMPLOYER: Current/past employer
        - SCHOOL: Educational institution
        - BUSINESS: Commercial entity
        - GOVERNMENT: Government agency
        - HEALTHCARE_ORG: Hospital, clinic
        - NONPROFIT: Charity, community org
    """

    # PERSON subtypes
    FAMILY_MEMBER = "FAMILY_MEMBER"
    FRIEND = "FRIEND"
    PROFESSIONAL = "PROFESSIONAL"
    CELEBRITY = "CELEBRITY"
    SERVICE_PROVIDER = "SERVICE_PROVIDER"
    ACQUAINTANCE = "ACQUAINTANCE"

    # LOCATION subtypes
    HOME = "HOME"
    WORKPLACE = "WORKPLACE"
    RECREATIONAL = "RECREATIONAL"
    TRANSIT = "TRANSIT"
    COMMERCIAL = "COMMERCIAL"
    HEALTHCARE = "HEALTHCARE"
    EDUCATIONAL = "EDUCATIONAL"
    RELIGIOUS = "RELIGIOUS"

    # ORGANIZATION subtypes
    EMPLOYER = "EMPLOYER"
    SCHOOL = "SCHOOL"
    BUSINESS = "BUSINESS"
    GOVERNMENT = "GOVERNMENT"
    HEALTHCARE_ORG = "HEALTHCARE_ORG"
    NONPROFIT = "NONPROFIT"

    # THING subtypes
    VEHICLE = "VEHICLE"
    DEVICE = "DEVICE"
    FOOD = "FOOD"
    MEDIA = "MEDIA"
    DOCUMENT = "DOCUMENT"

    # EVENT subtypes
    HOLIDAY = "HOLIDAY"
    MEETING = "MEETING"
    CELEBRATION = "CELEBRATION"
    APPOINTMENT = "APPOINTMENT"


# =============================================================================
# KEYWORD DATABASES
# =============================================================================


@dataclass(frozen=True)
class KeywordDatabase:
    """
    Keyword-based classification database.

    Maps subtypes to sets of indicative keywords.
    """

    keywords: Dict[str, FrozenSet[str]] = field(default_factory=dict)

    def match(self, text: str) -> Optional[str]:
        """
        Find the best matching subtype for given text.

        Args:
            text: Text to classify

        Returns:
            Best matching subtype or None
        """
        if not text:
            return None

        text_lower = text.lower()
        words = set(re.findall(r"\b\w+\b", text_lower))

        best_subtype = None
        best_score = 0

        for subtype, keyword_set in self.keywords.items():
            # Count keyword matches
            matches = words & keyword_set
            score = len(matches)

            if score > best_score:
                best_score = score
                best_subtype = subtype

        return best_subtype if best_score > 0 else None


# Theme subtype keywords
THEME_KEYWORDS = KeywordDatabase(
    keywords={
        PatternSubtype.HEALTH_THEME.value: frozenset(
            {
                "health",
                "exercise",
                "workout",
                "gym",
                "fitness",
                "doctor",
                "medical",
                "sleep",
                "diet",
                "nutrition",
                "wellness",
                "therapy",
                "medication",
                "symptom",
                "illness",
                "recovery",
                "physical",
                "mental",
                "stress",
                "anxiety",
                "weight",
                "running",
                "yoga",
                "meditation",
                "hospital",
                "clinic",
                "appointment",
            }
        ),
        PatternSubtype.WORK_THEME.value: frozenset(
            {
                "work",
                "job",
                "office",
                "meeting",
                "project",
                "deadline",
                "boss",
                "colleague",
                "coworker",
                "career",
                "promotion",
                "salary",
                "client",
                "presentation",
                "report",
                "email",
                "conference",
                "team",
                "manager",
                "task",
                "productivity",
                "business",
                "company",
                "corporate",
                "professional",
            }
        ),
        PatternSubtype.RELATIONSHIP_THEME.value: frozenset(
            {
                "friend",
                "family",
                "mom",
                "dad",
                "wife",
                "husband",
                "partner",
                "child",
                "daughter",
                "son",
                "brother",
                "sister",
                "relationship",
                "love",
                "dating",
                "marriage",
                "anniversary",
                "birthday",
                "visit",
                "call",
                "together",
                "conflict",
                "support",
            }
        ),
        PatternSubtype.FINANCE_THEME.value: frozenset(
            {
                "money",
                "budget",
                "savings",
                "investment",
                "expense",
                "cost",
                "payment",
                "bill",
                "tax",
                "income",
                "salary",
                "debt",
                "loan",
                "mortgage",
                "credit",
                "bank",
                "financial",
                "retire",
                "stock",
            }
        ),
        PatternSubtype.LEISURE_THEME.value: frozenset(
            {
                "hobby",
                "game",
                "movie",
                "music",
                "book",
                "reading",
                "tv",
                "show",
                "concert",
                "travel",
                "vacation",
                "trip",
                "restaurant",
                "fun",
                "relax",
                "entertainment",
                "play",
                "sport",
                "art",
                "craft",
                "garden",
                "cook",
                "bake",
            }
        ),
        PatternSubtype.LEARNING_THEME.value: frozenset(
            {
                "learn",
                "study",
                "course",
                "class",
                "education",
                "skill",
                "training",
                "tutorial",
                "book",
                "research",
                "knowledge",
                "degree",
                "certificate",
                "practice",
                "improve",
                "growth",
            }
        ),
    }
)

# Routine subtype keywords (time-based patterns)
ROUTINE_KEYWORDS = KeywordDatabase(
    keywords={
        PatternSubtype.MORNING_ROUTINE.value: frozenset(
            {
                "morning",
                "breakfast",
                "wake",
                "coffee",
                "shower",
                "commute",
                "alarm",
                "early",
                "sunrise",
                "start",
            }
        ),
        PatternSubtype.EVENING_ROUTINE.value: frozenset(
            {
                "evening",
                "dinner",
                "night",
                "sleep",
                "bed",
                "late",
                "sunset",
                "wind",
                "relax",
                "home",
            }
        ),
        PatternSubtype.WORK_ROUTINE.value: frozenset(
            {
                "work",
                "office",
                "meeting",
                "email",
                "task",
                "project",
                "deadline",
                "report",
                "call",
                "lunch",
            }
        ),
        PatternSubtype.EXERCISE_ROUTINE.value: frozenset(
            {
                "gym",
                "workout",
                "exercise",
                "run",
                "jog",
                "yoga",
                "fitness",
                "training",
                "cardio",
                "weights",
                "stretch",
            }
        ),
        PatternSubtype.SOCIAL_ROUTINE.value: frozenset(
            {
                "call",
                "visit",
                "friend",
                "family",
                "dinner",
                "lunch",
                "coffee",
                "meet",
                "hangout",
                "party",
            }
        ),
    }
)

# Preference subtype keywords
PREFERENCE_KEYWORDS = KeywordDatabase(
    keywords={
        PatternSubtype.FOOD_PREFERENCE.value: frozenset(
            {
                "food",
                "eat",
                "restaurant",
                "cuisine",
                "meal",
                "dish",
                "taste",
                "favorite",
                "love",
                "prefer",
                "cook",
                "recipe",
            }
        ),
        PatternSubtype.ACTIVITY_PREFERENCE.value: frozenset(
            {
                "activity",
                "hobby",
                "sport",
                "game",
                "enjoy",
                "like",
                "fun",
                "prefer",
                "favorite",
            }
        ),
        PatternSubtype.LOCATION_PREFERENCE.value: frozenset(
            {
                "place",
                "location",
                "spot",
                "venue",
                "area",
                "neighborhood",
                "city",
                "country",
                "travel",
            }
        ),
        PatternSubtype.SOCIAL_PREFERENCE.value: frozenset(
            {
                "friend",
                "group",
                "alone",
                "introvert",
                "extrovert",
                "social",
                "party",
                "gathering",
                "quiet",
            }
        ),
    }
)

# Goal subtype keywords
GOAL_KEYWORDS = KeywordDatabase(
    keywords={
        PatternSubtype.HEALTH_GOAL.value: frozenset(
            {
                "health",
                "fitness",
                "weight",
                "exercise",
                "diet",
                "sleep",
                "wellness",
                "quit",
                "smoking",
                "drinking",
            }
        ),
        PatternSubtype.CAREER_GOAL.value: frozenset(
            {
                "career",
                "job",
                "promotion",
                "salary",
                "work",
                "professional",
                "skill",
                "business",
                "company",
            }
        ),
        PatternSubtype.FINANCIAL_GOAL.value: frozenset(
            {
                "money",
                "save",
                "invest",
                "retire",
                "budget",
                "debt",
                "pay",
                "income",
                "wealth",
            }
        ),
        PatternSubtype.PERSONAL_GOAL.value: frozenset(
            {
                "learn",
                "grow",
                "improve",
                "habit",
                "skill",
                "read",
                "travel",
                "experience",
            }
        ),
        PatternSubtype.RELATIONSHIP_GOAL.value: frozenset(
            {
                "relationship",
                "friend",
                "family",
                "partner",
                "connect",
                "marriage",
                "dating",
            }
        ),
    }
)

# Lesson subtype keywords
LESSON_KEYWORDS = KeywordDatabase(
    keywords={
        PatternSubtype.CAUTIONARY_TALE.value: frozenset(
            {
                "mistake",
                "regret",
                "should",
                "shouldn't",
                "avoid",
                "never",
                "warning",
                "lesson",
                "wrong",
                "bad",
                "fail",
                "error",
            }
        ),
        PatternSubtype.BEST_PRACTICE.value: frozenset(
            {
                "success",
                "worked",
                "recommend",
                "always",
                "best",
                "good",
                "effective",
                "helpful",
                "tip",
                "strategy",
            }
        ),
        PatternSubtype.INSIGHT.value: frozenset(
            {
                "realize",
                "understand",
                "connection",
                "pattern",
                "notice",
                "interesting",
                "learned",
                "discover",
            }
        ),
    }
)

# Emotional trend subtype keywords
EMOTIONAL_KEYWORDS = KeywordDatabase(
    keywords={
        PatternSubtype.STRESS_PATTERN.value: frozenset(
            {
                "stress",
                "pressure",
                "overwhelm",
                "tense",
                "nervous",
                "worry",
                "deadline",
                "rush",
                "busy",
                "hectic",
            }
        ),
        PatternSubtype.JOY_PATTERN.value: frozenset(
            {
                "happy",
                "joy",
                "excited",
                "grateful",
                "blessed",
                "wonderful",
                "amazing",
                "love",
                "celebrate",
                "fun",
            }
        ),
        PatternSubtype.ANXIETY_PATTERN.value: frozenset(
            {
                "anxious",
                "worry",
                "fear",
                "uncertain",
                "nervous",
                "panic",
                "dread",
                "scared",
            }
        ),
        PatternSubtype.BURNOUT_PATTERN.value: frozenset(
            {
                "exhausted",
                "tired",
                "burnout",
                "drained",
                "overwhelm",
                "quit",
                "break",
                "rest",
                "nothing",
            }
        ),
    }
)

# Value subtype keywords
VALUE_KEYWORDS = KeywordDatabase(
    keywords={
        PatternSubtype.FAMILY_VALUE.value: frozenset(
            {
                "family",
                "children",
                "parent",
                "tradition",
                "together",
                "support",
                "love",
                "care",
            }
        ),
        PatternSubtype.CAREER_VALUE.value: frozenset(
            {
                "career",
                "success",
                "achievement",
                "ambition",
                "growth",
                "professional",
                "work",
            }
        ),
        PatternSubtype.HEALTH_VALUE.value: frozenset(
            {
                "health",
                "wellness",
                "balance",
                "fitness",
                "mental",
                "physical",
                "self-care",
            }
        ),
        PatternSubtype.SOCIAL_VALUE.value: frozenset(
            {
                "friend",
                "community",
                "social",
                "connection",
                "belong",
                "help",
                "volunteer",
            }
        ),
    }
)


# Location subtype keywords
LOCATION_KEYWORDS = KeywordDatabase(
    keywords={
        EntitySubtype.HOME.value: frozenset(
            {
                "home",
                "house",
                "apartment",
                "residence",
                "living",
                "bedroom",
                "kitchen",
                "domestic",
            }
        ),
        EntitySubtype.WORKPLACE.value: frozenset(
            {
                "office",
                "work",
                "workplace",
                "company",
                "building",
                "desk",
                "conference",
                "meeting",
            }
        ),
        EntitySubtype.RECREATIONAL.value: frozenset(
            {
                "park",
                "beach",
                "gym",
                "pool",
                "cinema",
                "theater",
                "museum",
                "stadium",
                "restaurant",
                "cafe",
                "bar",
                "club",
            }
        ),
        EntitySubtype.TRANSIT.value: frozenset(
            {
                "airport",
                "station",
                "bus",
                "train",
                "subway",
                "metro",
                "terminal",
                "stop",
            }
        ),
        EntitySubtype.COMMERCIAL.value: frozenset(
            {
                "store",
                "shop",
                "mall",
                "market",
                "supermarket",
                "grocery",
                "retail",
                "outlet",
            }
        ),
        EntitySubtype.HEALTHCARE.value: frozenset(
            {
                "hospital",
                "clinic",
                "doctor",
                "pharmacy",
                "medical",
                "emergency",
                "urgent",
                "care",
            }
        ),
        EntitySubtype.EDUCATIONAL.value: frozenset(
            {
                "school",
                "university",
                "college",
                "campus",
                "library",
                "classroom",
                "academy",
            }
        ),
        EntitySubtype.RELIGIOUS.value: frozenset(
            {
                "church",
                "mosque",
                "temple",
                "synagogue",
                "chapel",
                "religious",
                "worship",
            }
        ),
    }
)

# Organization subtype keywords
ORGANIZATION_KEYWORDS = KeywordDatabase(
    keywords={
        EntitySubtype.EMPLOYER.value: frozenset(
            {
                "employer",
                "company",
                "corporation",
                "work",
                "job",
                "office",
            }
        ),
        EntitySubtype.SCHOOL.value: frozenset(
            {
                "school",
                "university",
                "college",
                "academy",
                "institute",
                "education",
            }
        ),
        EntitySubtype.BUSINESS.value: frozenset(
            {
                "store",
                "shop",
                "restaurant",
                "business",
                "service",
                "company",
            }
        ),
        EntitySubtype.GOVERNMENT.value: frozenset(
            {
                "government",
                "federal",
                "state",
                "city",
                "agency",
                "department",
                "municipal",
                "public",
            }
        ),
        EntitySubtype.HEALTHCARE_ORG.value: frozenset(
            {
                "hospital",
                "clinic",
                "medical",
                "healthcare",
                "health",
            }
        ),
        EntitySubtype.NONPROFIT.value: frozenset(
            {
                "charity",
                "nonprofit",
                "foundation",
                "volunteer",
                "community",
            }
        ),
    }
)


# =============================================================================
# PATTERN SUBTYPE CLASSIFIER
# =============================================================================


@dataclass
class PatternClassificationInput:
    """Input for pattern subtype classification."""

    pattern_type: str  # THEME, LESSON, ROUTINE, etc.
    pattern_name: str  # Human-readable pattern name
    pattern_description: Optional[str] = None
    source_texts: Optional[List[str]] = None  # Source event texts
    sentiment_avg: Optional[float] = None  # Average sentiment
    emotions: Optional[Dict[str, int]] = None  # Emotion counts


class PatternSubtypeClassifier:
    """
    Classifies st_sem.pattern_subtype based on pattern content.

    Uses keyword matching and optional sentiment analysis to determine
    fine-grained subtypes for semantic patterns.
    """

    # Mapping from pattern_type to keyword database
    TYPE_TO_DB: Dict[str, KeywordDatabase] = {
        "THEME": THEME_KEYWORDS,
        "ROUTINE": ROUTINE_KEYWORDS,
        "PREFERENCE": PREFERENCE_KEYWORDS,
        "GOAL": GOAL_KEYWORDS,
        "LESSON": LESSON_KEYWORDS,
        "EMOTIONAL_TREND": EMOTIONAL_KEYWORDS,
        "VALUE": VALUE_KEYWORDS,
    }

    def classify(self, input_data: PatternClassificationInput) -> Optional[str]:
        """
        Classify pattern subtype.

        Args:
            input_data: Pattern classification input

        Returns:
            Subtype string or None if no match
        """
        pattern_type = input_data.pattern_type.upper()

        # Get keyword database for this pattern type
        db = self.TYPE_TO_DB.get(pattern_type)
        if not db:
            logger.debug(f"No subtype database for pattern_type={pattern_type}")
            return None

        # Combine all text sources for matching
        texts = []
        if input_data.pattern_name:
            texts.append(input_data.pattern_name)
        if input_data.pattern_description:
            texts.append(input_data.pattern_description)
        if input_data.source_texts:
            texts.extend(input_data.source_texts)

        combined_text = " ".join(texts)

        # Match against keyword database
        subtype = db.match(combined_text)

        if subtype:
            logger.debug(
                f"Classified pattern subtype: {pattern_type} → {subtype}",
                extra={
                    "pattern_name": input_data.pattern_name[:50] if input_data.pattern_name else "",
                },
            )

        return subtype

    def classify_with_fallback(
        self,
        input_data: PatternClassificationInput,
    ) -> str:
        """
        Classify pattern subtype with fallback to generic subtype.

        Args:
            input_data: Pattern classification input

        Returns:
            Subtype string (never None)
        """
        subtype = self.classify(input_data)
        if subtype:
            return subtype

        # Fallback based on pattern_type
        fallbacks = {
            "THEME": PatternSubtype.LEISURE_THEME.value,
            "ROUTINE": PatternSubtype.WORK_ROUTINE.value,
            "PREFERENCE": PatternSubtype.ACTIVITY_PREFERENCE.value,
            "GOAL": PatternSubtype.PERSONAL_GOAL.value,
            "LESSON": PatternSubtype.INSIGHT.value,
            "EMOTIONAL_TREND": PatternSubtype.STRESS_PATTERN.value,
            "VALUE": PatternSubtype.PERSONAL_GOAL.value,
        }

        pattern_type = input_data.pattern_type.upper()
        return fallbacks.get(pattern_type, "")


# =============================================================================
# ENTITY SUBTYPE CLASSIFIER
# =============================================================================


@dataclass
class EntityClassificationInput:
    """Input for entity subtype classification."""

    entity_type: str  # PERSON, LOCATION, ORGANIZATION, THING, EVENT
    canonical_name: str
    aliases: Optional[List[str]] = None
    attributes_json: Optional[str] = None
    contexts: Optional[List[str]] = None  # Activity contexts
    relationship_types: Optional[List[str]] = None  # e.g., ["FAMILY", "FRIEND"]


class EntitySubtypeClassifier:
    """
    Classifies st_kg_dom.entity_subtype based on entity features.

    Uses keyword matching, relationship analysis, and contextual cues.
    """

    # Family/friend indicator names
    FAMILY_INDICATORS: FrozenSet[str] = frozenset(
        {
            "mom",
            "mother",
            "mama",
            "mum",
            "dad",
            "father",
            "papa",
            "wife",
            "husband",
            "spouse",
            "partner",
            "son",
            "daughter",
            "child",
            "kid",
            "brother",
            "sister",
            "sibling",
            "bro",
            "sis",
            "grandma",
            "grandpa",
            "grandmother",
            "grandfather",
            "aunt",
            "uncle",
            "cousin",
            "niece",
            "nephew",
        }
    )

    # Professional title indicators
    PROFESSIONAL_INDICATORS: FrozenSet[str] = frozenset(
        {
            "dr",
            "doctor",
            "prof",
            "professor",
            "mr",
            "mrs",
            "ms",
            "ceo",
            "manager",
            "director",
            "boss",
            "colleague",
        }
    )

    # Service provider indicators
    SERVICE_INDICATORS: FrozenSet[str] = frozenset(
        {
            "doctor",
            "dentist",
            "therapist",
            "lawyer",
            "accountant",
            "plumber",
            "mechanic",
            "hairdresser",
            "barber",
            "trainer",
        }
    )

    def classify(self, input_data: EntityClassificationInput) -> Optional[str]:
        """
        Classify entity subtype.

        Args:
            input_data: Entity classification input

        Returns:
            Subtype string or None if no match
        """
        entity_type = input_data.entity_type.upper()

        if entity_type == "PERSON":
            return self._classify_person(input_data)
        elif entity_type == "LOCATION":
            return self._classify_location(input_data)
        elif entity_type == "ORGANIZATION":
            return self._classify_organization(input_data)
        elif entity_type == "THING":
            return self._classify_thing(input_data)
        elif entity_type == "EVENT":
            return self._classify_event(input_data)

        return None

    def _classify_person(self, input_data: EntityClassificationInput) -> Optional[str]:
        """Classify PERSON entity subtype."""
        name_lower = input_data.canonical_name.lower()

        # Check relationship types first (most reliable)
        if input_data.relationship_types:
            if "FAMILY" in input_data.relationship_types:
                return EntitySubtype.FAMILY_MEMBER.value
            if "FRIEND" in input_data.relationship_types:
                return EntitySubtype.FRIEND.value
            if "COLLEAGUE" in input_data.relationship_types:
                return EntitySubtype.PROFESSIONAL.value

        # Check name-based indicators
        name_words = set(re.findall(r"\b\w+\b", name_lower))

        if name_words & self.FAMILY_INDICATORS:
            return EntitySubtype.FAMILY_MEMBER.value

        if name_words & self.SERVICE_INDICATORS:
            return EntitySubtype.SERVICE_PROVIDER.value

        if name_words & self.PROFESSIONAL_INDICATORS:
            return EntitySubtype.PROFESSIONAL.value

        # Check contexts
        if input_data.contexts:
            contexts_text = " ".join(input_data.contexts).lower()
            if "work" in contexts_text or "office" in contexts_text:
                return EntitySubtype.PROFESSIONAL.value
            if "friend" in contexts_text:
                return EntitySubtype.FRIEND.value

        # Default for unknown persons
        return EntitySubtype.ACQUAINTANCE.value

    def _classify_location(self, input_data: EntityClassificationInput) -> Optional[str]:
        """Classify LOCATION entity subtype."""
        # Combine name and contexts for matching
        texts = [input_data.canonical_name]
        if input_data.contexts:
            texts.extend(input_data.contexts)
        combined = " ".join(texts)

        return LOCATION_KEYWORDS.match(combined)

    def _classify_organization(self, input_data: EntityClassificationInput) -> Optional[str]:
        """Classify ORGANIZATION entity subtype."""
        # Combine name and contexts for matching
        texts = [input_data.canonical_name]
        if input_data.contexts:
            texts.extend(input_data.contexts)
        combined = " ".join(texts)

        return ORGANIZATION_KEYWORDS.match(combined)

    def _classify_thing(self, input_data: EntityClassificationInput) -> Optional[str]:
        """Classify THING entity subtype."""
        name_lower = input_data.canonical_name.lower()

        # Vehicle keywords
        if any(kw in name_lower for kw in ("car", "truck", "bike", "vehicle", "bus")):
            return EntitySubtype.VEHICLE.value

        # Device keywords
        if any(kw in name_lower for kw in ("phone", "laptop", "computer", "tablet", "device")):
            return EntitySubtype.DEVICE.value

        # Food keywords
        if any(kw in name_lower for kw in ("food", "meal", "dish", "recipe")):
            return EntitySubtype.FOOD.value

        # Media keywords
        if any(kw in name_lower for kw in ("book", "movie", "show", "song", "album")):
            return EntitySubtype.MEDIA.value

        return None

    def _classify_event(self, input_data: EntityClassificationInput) -> Optional[str]:
        """Classify EVENT entity subtype."""
        name_lower = input_data.canonical_name.lower()

        # Holiday keywords
        if any(kw in name_lower for kw in ("holiday", "christmas", "thanksgiving", "easter")):
            return EntitySubtype.HOLIDAY.value

        # Meeting keywords
        if any(kw in name_lower for kw in ("meeting", "conference", "call", "sync")):
            return EntitySubtype.MEETING.value

        # Celebration keywords
        if any(kw in name_lower for kw in ("birthday", "anniversary", "party", "wedding")):
            return EntitySubtype.CELEBRATION.value

        # Appointment keywords
        if any(kw in name_lower for kw in ("appointment", "checkup", "visit")):
            return EntitySubtype.APPOINTMENT.value

        return None


# =============================================================================
# UNIFIED SUBTYPE CLASSIFIER
# =============================================================================


class SubtypeClassifier:
    """
    Unified subtype classifier for all memory layers.

    Wraps PatternSubtypeClassifier and EntitySubtypeClassifier.
    """

    def __init__(self):
        """Initialize with sub-classifiers."""
        self._pattern_classifier = PatternSubtypeClassifier()
        self._entity_classifier = EntitySubtypeClassifier()

    @property
    def pattern_classifier(self) -> PatternSubtypeClassifier:
        """Get pattern subtype classifier."""
        return self._pattern_classifier

    @property
    def entity_classifier(self) -> EntitySubtypeClassifier:
        """Get entity subtype classifier."""
        return self._entity_classifier

    def classify_pattern(
        self,
        pattern_type: str,
        pattern_name: str,
        pattern_description: Optional[str] = None,
        source_texts: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Classify pattern subtype (convenience method).

        Args:
            pattern_type: THEME, ROUTINE, PREFERENCE, etc.
            pattern_name: Human-readable pattern name
            pattern_description: Optional description
            source_texts: Optional source event texts

        Returns:
            Subtype string or None
        """
        input_data = PatternClassificationInput(
            pattern_type=pattern_type,
            pattern_name=pattern_name,
            pattern_description=pattern_description,
            source_texts=source_texts,
        )
        return self._pattern_classifier.classify(input_data)

    def classify_entity(
        self,
        entity_type: str,
        canonical_name: str,
        aliases: Optional[List[str]] = None,
        contexts: Optional[List[str]] = None,
        relationship_types: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Classify entity subtype (convenience method).

        Args:
            entity_type: PERSON, LOCATION, ORGANIZATION, etc.
            canonical_name: Canonical entity name
            aliases: Optional aliases
            contexts: Optional activity contexts
            relationship_types: Optional relationship types

        Returns:
            Subtype string or None
        """
        input_data = EntityClassificationInput(
            entity_type=entity_type,
            canonical_name=canonical_name,
            aliases=aliases,
            contexts=contexts,
            relationship_types=relationship_types,
        )
        return self._entity_classifier.classify(input_data)


# =============================================================================
# SINGLETON
# =============================================================================

_classifier_instance: Optional[SubtypeClassifier] = None


def get_subtype_classifier() -> SubtypeClassifier:
    """Get or create singleton SubtypeClassifier instance."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = SubtypeClassifier()
    return _classifier_instance
