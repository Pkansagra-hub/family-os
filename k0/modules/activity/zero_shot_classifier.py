"""
Zero-Shot Activity Classification Module

Research Foundation:
- Yin et al. (2019) - Benchmarking Zero-shot Text Classification
- Lewis et al. (2020) - BART: Denoising Sequence-to-Sequence Pre-training

Architecture:
- Rule-based keyword matching (fast, deterministic baseline)
- ML-ready interface for BART-MNLI zero-shot classification
- Multi-label support (activities can overlap: "dinner party" = meal + social)
- Confidence scoring for uncertainty quantification

Performance Targets:
- Rule-based: <5ms P95 latency
- ML (BART): <50ms P95 latency (GPU), <150ms P95 (CPU)

Contract: k0/contracts/taxonomies/activity_taxonomy.yaml
ADR: docs/architecture/decisions-K0/modules/k007.4-activity-taxonomy.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

# Module version
__version__ = "1.0.0"

# Taxonomy file path (relative to this module)
TAXONOMY_PATH = (
    Path(__file__).parent.parent.parent / "contracts" / "taxonomies" / "activity_taxonomy.yaml"
)


class ClassificationTier(Enum):
    """Classification method tier (for feature flags and A/B testing)."""

    RULE_BASED = "rule_based"  # Keyword matching (default)
    ZERO_SHOT_ML = "zero_shot_ml"  # BART-MNLI model
    HYBRID = "hybrid"  # Rule-based with ML fallback


@dataclass(frozen=True)
class ActivityClassification:
    """
    Result of activity classification.

    Attributes:
        primary_activity: Most likely activity type
        confidence: Confidence score (0.0 to 1.0)
        secondary_activities: Other possible activities (multi-label)
        is_multi_activity: Whether multiple activities detected
        classification_tier: Method used (rule_based/zero_shot_ml/hybrid)
        hierarchy_path: Full taxonomy path (e.g., "sustenance.meal.dinner")
        parent_category: Top-level category (e.g., "sustenance")
        classified_at_utc: ISO 8601 timestamp
    """

    primary_activity: str
    confidence: float
    secondary_activities: Tuple[str, ...] = field(default_factory=tuple)
    is_multi_activity: bool = False
    classification_tier: str = ClassificationTier.RULE_BASED.value
    hierarchy_path: Optional[str] = None
    parent_category: Optional[str] = None
    classified_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "primary_activity": self.primary_activity,
            "confidence": self.confidence,
            "secondary_activities": list(self.secondary_activities),
            "is_multi_activity": self.is_multi_activity,
            "classification_tier": self.classification_tier,
            "hierarchy_path": self.hierarchy_path,
            "parent_category": self.parent_category,
            "classified_at_utc": self.classified_at_utc,
        }


# Expanded activity keywords (20+ activity types vs original 7)
# Priority-ordered: high-specificity first
ACTIVITY_KEYWORDS: Dict[str, List[str]] = {
    # High specificity (check first)
    "meal": [
        "breakfast",
        "lunch",
        "dinner",
        "supper",
        "brunch",
        "ate",
        "eating",
        "food",
        "meal",
        "snack",
        "restaurant",
        "hungry",
        "cook",
        "recipe",
        "delicious",
        "tasty",
        "yummy",
    ],
    "celebration": [
        "birthday",
        "anniversary",
        "graduation",
        "wedding",
        "promotion",
        "achievement",
        "milestone",
        "engaged",
        "engagement",
        "baby shower",
        "retirement",
        "celebrate",
        "congratulations",
    ],
    "medical_appointment": [
        "doctor",
        "dentist",
        "hospital",
        "clinic",
        "appointment",
        "checkup",
        "therapy",
        "therapist",
        "medical",
        "health",
        "prescription",
        "vet",
        "vaccination",
        "exam",
        "diagnosis",
    ],
    "exercise": [
        "workout",
        "gym",
        "running",
        "jogging",
        "yoga",
        "pilates",
        "swimming",
        "cycling",
        "hiking",
        "walking",
        "fitness",
        "training",
        "exercise",
        "marathon",
        "weights",
        "cardio",
        "tennis",
        "golf",
    ],
    "work_meeting": [
        "meeting",
        "conference",
        "standup",
        "presentation",
        "client",
        "interview",
        "deadline",
        "project",
        "office",
        "work",
        "colleague",
        "boss",
        "manager",
        "sync",
        "1:1",
        "review",
    ],
    "family_gathering": [
        "family dinner",
        "family reunion",
        "thanksgiving",
        "christmas",
        "easter",
        "holiday",
        "relatives",
        "grandparents",
        "cousins",
        "family event",
        "family time",
    ],
    "social_event": [
        "party",
        "gathering",
        "reunion",
        "hangout",
        "get-together",
        "picnic",
        "barbeque",
        "bbq",
        "potluck",
        "game night",
        "friends",
    ],
    "shopping": [
        "shopping",
        "store",
        "mall",
        "grocery",
        "market",
        "bought",
        "purchase",
        "errand",
        "amazon",
        "online shopping",
        "clothes shopping",
    ],
    "travel": [
        "vacation",
        "trip",
        "flight",
        "airport",
        "hotel",
        "resort",
        "road trip",
        "travel",
        "journey",
        "destination",
        "sightseeing",
        "tourist",
        "beach vacation",
        "getaway",
    ],
    "entertainment": [
        "movie",
        "cinema",
        "concert",
        "show",
        "theater",
        "netflix",
        "streaming",
        "watched",
        "gaming",
        "video game",
        "music",
        "performance",
        "festival",
    ],
    "education": [
        "class",
        "school",
        "university",
        "college",
        "lecture",
        "studying",
        "homework",
        "course",
        "learning",
        "tutor",
        "exam",
        "test",
    ],
    "outdoor_recreation": [
        "park",
        "beach",
        "camping",
        "hiking",
        "nature",
        "garden",
        "outdoor",
        "picnic",
        "playground",
        "trail",
        "fishing",
        "kayak",
    ],
    "household_chore": [
        "cleaning",
        "laundry",
        "dishes",
        "vacuum",
        "mop",
        "organize",
        "declutter",
        "repair",
        "fix",
        "maintenance",
        "yardwork",
        "lawn",
    ],
    "personal_care": [
        "spa",
        "massage",
        "haircut",
        "salon",
        "grooming",
        "manicure",
        "pedicure",
        "facial",
        "self-care",
        "relaxation",
    ],
    "creative_activity": [
        "painting",
        "drawing",
        "art",
        "craft",
        "photography",
        "writing",
        "knitting",
        "woodworking",
        "diy",
        "creative",
        "design",
    ],
    "sports": [
        "soccer",
        "football",
        "basketball",
        "baseball",
        "tennis",
        "golf",
        "volleyball",
        "hockey",
        "game",
        "match",
        "team",
        "league",
        "practice",
    ],
    "religious_activity": [
        "church",
        "temple",
        "mosque",
        "synagogue",
        "prayer",
        "worship",
        "baptism",
        "communion",
        "service",
        "religious",
        "spiritual",
    ],
    "pet_care": [
        "dog walk",
        "pet",
        "cat",
        "dog",
        "vet",
        "grooming",
        "feed",
        "walk the dog",
        "puppy",
        "kitten",
        "animal",
    ],
    "commute": [
        "commute",
        "drive to work",
        "bus",
        "train",
        "subway",
        "metro",
        "traffic",
        "carpool",
        "uber",
        "lyft",
    ],
    "routine": [
        "morning",
        "evening",
        "wake",
        "sleep",
        "shower",
        "bath",
        "bedtime",
        "nap",
        "routine",
        "daily",
        "usual",
        "regular",
    ],
    # Conversation (medium specificity)
    "conversation": [
        "chat",
        "talked",
        "discussed",
        "conversation",
        "call",
        "phone",
        "text",
        "message",
        "video call",
        "zoom",
        "facetime",
        "whatsapp",
    ],
    # Reading and relaxation
    "reading": [
        "read",
        "book",
        "magazine",
        "article",
        "novel",
        "kindle",
        "audiobook",
        "library",
    ],
    "relaxation": [
        "relax",
        "rest",
        "chill",
        "unwind",
        "lazy",
        "couch",
        "tv",
        "television",
        "series",
        "binge",
    ],
}

# Category mapping (activity → parent category)
ACTIVITY_TO_CATEGORY: Dict[str, str] = {
    "meal": "sustenance",
    "celebration": "celebration",
    "medical_appointment": "wellness",
    "exercise": "wellness",
    "work_meeting": "work",
    "family_gathering": "social",
    "social_event": "social",
    "shopping": "shopping",
    "travel": "travel",
    "entertainment": "entertainment",
    "education": "education",
    "outdoor_recreation": "outdoor",
    "household_chore": "household",
    "personal_care": "wellness",
    "creative_activity": "creative",
    "sports": "sports",
    "religious_activity": "celebration",
    "pet_care": "pet",
    "commute": "work",
    "routine": "routine",
    "conversation": "social",
    "reading": "entertainment",
    "relaxation": "routine",
}

# Zero-shot labels for BART-MNLI (from taxonomy)
ZERO_SHOT_LABELS: List[str] = [
    "meal",
    "exercise",
    "work meeting",
    "medical appointment",
    "family gathering",
    "shopping",
    "travel",
    "entertainment",
    "education",
    "religious activity",
    "household chore",
    "outdoor recreation",
    "social event",
    "personal care",
    "creative activity",
    "sports",
    "celebration",
    "routine",
    "commute",
    "pet care",
    "cooking",
    "gaming",
    "reading",
    "relaxation",
]

# Multi-activity patterns (text patterns that suggest multiple activities)
MULTI_ACTIVITY_PATTERNS: List[Tuple[str, List[str]]] = [
    (r"\b(dinner|lunch|breakfast)\s+(party|celebration)", ["meal", "social_event"]),
    (r"\b(birthday|anniversary)\s+(dinner|lunch)", ["celebration", "meal"]),
    (r"\b(work|office)\s+(lunch|dinner)", ["work_meeting", "meal"]),
    (r"\b(family)\s+(picnic|bbq|barbeque)", ["family_gathering", "outdoor_recreation"]),
    (r"\b(gym|exercise)\s+(class)", ["exercise", "education"]),
    (r"\b(dog)\s+(walk|hike)", ["pet_care", "outdoor_recreation"]),
    (r"\b(beach)\s+(vacation|trip)", ["travel", "outdoor_recreation"]),
    (r"\b(game)\s+(night)", ["entertainment", "social_event"]),
]

# Module-level metrics
_metrics: Dict[str, int] = {
    "total_classifications": 0,
    "rule_based_classifications": 0,
    "ml_classifications": 0,
    "multi_activity_detected": 0,
    "unknown_classifications": 0,
}


class ZeroShotActivityClassifier:
    """
    Zero-shot activity classifier with rule-based fallback.

    Research Foundation:
    - Yin et al. (2019) - Benchmarking Zero-shot Text Classification
    - Lewis et al. (2020) - BART: Denoising Sequence-to-Sequence Pre-training

    Supports three classification tiers:
    1. RULE_BASED: Fast keyword matching (default)
    2. ZERO_SHOT_ML: BART-MNLI model for novel activities
    3. HYBRID: Rule-based with ML fallback for low-confidence

    Performance:
    - Rule-based: <5ms P95
    - ML (BART): <50ms P95 (GPU), <150ms P95 (CPU)
    """

    def __init__(
        self,
        tier: ClassificationTier = ClassificationTier.RULE_BASED,
        confidence_threshold: float = 0.5,
        multi_label_threshold: float = 0.3,
        taxonomy_path: Optional[Path] = None,
    ):
        """
        Initialize classifier.

        Args:
            tier: Classification tier (rule_based/zero_shot_ml/hybrid)
            confidence_threshold: Minimum confidence for primary activity
            multi_label_threshold: Threshold for secondary activities
            taxonomy_path: Path to activity taxonomy YAML
        """
        self.tier = tier
        self.confidence_threshold = confidence_threshold
        self.multi_label_threshold = multi_label_threshold
        self.taxonomy_path = taxonomy_path or TAXONOMY_PATH

        # Load taxonomy (lazy, on first use)
        self._taxonomy: Optional[Dict[str, Any]] = None

        # ML model (lazy loaded)
        self._ml_classifier: Optional[Any] = None

    @property
    def taxonomy(self) -> Dict[str, Any]:
        """Lazy-load taxonomy from YAML."""
        if self._taxonomy is None:
            self._taxonomy = self._load_taxonomy()
        return self._taxonomy

    def _load_taxonomy(self) -> Dict[str, Any]:
        """Load activity taxonomy from YAML file."""
        if self.taxonomy_path.exists():
            with open(self.taxonomy_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        # Return default if file not found
        return {
            "activity_taxonomy": {
                "zero_shot_labels": ZERO_SHOT_LABELS,
                "legacy_mapping": {},
            }
        }

    def _get_ml_classifier(self) -> Any:
        """
        Lazy-load ML classifier (BART-MNLI).

        Returns HuggingFace pipeline for zero-shot classification.
        Falls back to None if transformers not available.
        """
        if self._ml_classifier is None:
            try:
                from transformers import pipeline

                self._ml_classifier = pipeline(
                    "zero-shot-classification",
                    model="facebook/bart-large-mnli",
                    device=-1,  # CPU by default, use 0 for GPU
                )
            except ImportError:
                # Transformers not installed, ML tier unavailable
                self._ml_classifier = None
        return self._ml_classifier

    def classify(self, text: str) -> ActivityClassification:
        """
        Classify activity from text.

        Args:
            text: Input text to classify

        Returns:
            ActivityClassification with primary activity and metadata
        """
        if not text or not text.strip():
            return self._create_default_classification()

        # Update metrics
        _metrics["total_classifications"] += 1

        # Select classification method based on tier
        if self.tier == ClassificationTier.RULE_BASED:
            return self._classify_rule_based(text)
        elif self.tier == ClassificationTier.ZERO_SHOT_ML:
            return self._classify_ml(text)
        else:  # HYBRID
            return self._classify_hybrid(text)

    def _classify_rule_based(self, text: str) -> ActivityClassification:
        """
        Rule-based keyword classification.

        Performance: <5ms P95
        """
        _metrics["rule_based_classifications"] += 1

        text_lower = text.lower()
        matches: List[Tuple[str, float]] = []

        # Step 1: Check multi-activity patterns first
        multi_activities = self._detect_multi_activity(text_lower)
        if multi_activities:
            _metrics["multi_activity_detected"] += 1
            primary = multi_activities[0]
            secondary = tuple(multi_activities[1:])
            return ActivityClassification(
                primary_activity=primary,
                confidence=0.85,  # High confidence for pattern match
                secondary_activities=secondary,
                is_multi_activity=True,
                classification_tier=ClassificationTier.RULE_BASED.value,
                hierarchy_path=self._get_hierarchy_path(primary),
                parent_category=ACTIVITY_TO_CATEGORY.get(primary),
            )

        # Step 2: Single activity keyword matching
        for activity_type, keywords in ACTIVITY_KEYWORDS.items():
            match_count = 0
            for keyword in keywords:
                # Word boundary matching
                pattern = r"\b" + re.escape(keyword) + r"\b"
                if re.search(pattern, text_lower):
                    match_count += 1

            if match_count > 0:
                # Confidence based on number of matching keywords
                confidence = min(0.9, 0.5 + (match_count * 0.1))
                matches.append((activity_type, confidence))

        if not matches:
            _metrics["unknown_classifications"] += 1
            return ActivityClassification(
                primary_activity="routine",  # Default fallback
                confidence=0.3,
                classification_tier=ClassificationTier.RULE_BASED.value,
                hierarchy_path="routine",
                parent_category="routine",
            )

        # Sort by confidence
        matches.sort(key=lambda x: x[1], reverse=True)

        primary_activity = matches[0][0]
        primary_confidence = matches[0][1]

        # Check for multi-activity (second match above threshold)
        secondary_activities: Tuple[str, ...] = ()
        is_multi = False
        if len(matches) > 1 and matches[1][1] >= self.multi_label_threshold:
            secondary_activities = tuple(m[0] for m in matches[1:3])
            is_multi = True
            _metrics["multi_activity_detected"] += 1

        return ActivityClassification(
            primary_activity=primary_activity,
            confidence=primary_confidence,
            secondary_activities=secondary_activities,
            is_multi_activity=is_multi,
            classification_tier=ClassificationTier.RULE_BASED.value,
            hierarchy_path=self._get_hierarchy_path(primary_activity),
            parent_category=ACTIVITY_TO_CATEGORY.get(primary_activity),
        )

    def _classify_ml(self, text: str) -> ActivityClassification:
        """
        ML-based zero-shot classification using BART-MNLI.

        Performance: <50ms P95 (GPU), <150ms P95 (CPU)
        """
        classifier = self._get_ml_classifier()

        if classifier is None:
            # Fallback to rule-based if ML not available
            return self._classify_rule_based(text)

        _metrics["ml_classifications"] += 1

        # Get labels from taxonomy
        labels = self.taxonomy.get("activity_taxonomy", {}).get(
            "zero_shot_labels", ZERO_SHOT_LABELS
        )

        # Run zero-shot classification
        result = classifier(
            text,
            candidate_labels=labels,
            multi_label=True,
        )

        primary_activity = self._normalize_label(result["labels"][0])
        primary_confidence = result["scores"][0]

        # Secondary activities above threshold
        secondary: List[str] = []
        for i, (label, score) in enumerate(zip(result["labels"][1:4], result["scores"][1:4])):
            if score >= self.multi_label_threshold:
                secondary.append(self._normalize_label(label))

        is_multi = len(secondary) > 0 or (
            len(result["scores"]) > 1 and result["scores"][1] >= self.multi_label_threshold
        )

        return ActivityClassification(
            primary_activity=primary_activity,
            confidence=primary_confidence,
            secondary_activities=tuple(secondary),
            is_multi_activity=is_multi,
            classification_tier=ClassificationTier.ZERO_SHOT_ML.value,
            hierarchy_path=self._get_hierarchy_path(primary_activity),
            parent_category=ACTIVITY_TO_CATEGORY.get(primary_activity),
        )

    def _classify_hybrid(self, text: str) -> ActivityClassification:
        """
        Hybrid classification: rule-based with ML fallback.

        Uses rule-based first, falls back to ML if:
        - Confidence below threshold
        - Activity is "unknown"
        """
        rule_result = self._classify_rule_based(text)

        # Use ML fallback if low confidence or unknown
        if (
            rule_result.confidence < self.confidence_threshold
            or rule_result.primary_activity == "routine"
            and rule_result.confidence < 0.5
        ):
            ml_result = self._classify_ml(text)
            if ml_result.confidence > rule_result.confidence:
                return ActivityClassification(
                    primary_activity=ml_result.primary_activity,
                    confidence=ml_result.confidence,
                    secondary_activities=ml_result.secondary_activities,
                    is_multi_activity=ml_result.is_multi_activity,
                    classification_tier=ClassificationTier.HYBRID.value,
                    hierarchy_path=ml_result.hierarchy_path,
                    parent_category=ml_result.parent_category,
                )

        return ActivityClassification(
            primary_activity=rule_result.primary_activity,
            confidence=rule_result.confidence,
            secondary_activities=rule_result.secondary_activities,
            is_multi_activity=rule_result.is_multi_activity,
            classification_tier=ClassificationTier.HYBRID.value,
            hierarchy_path=rule_result.hierarchy_path,
            parent_category=rule_result.parent_category,
        )

    def _detect_multi_activity(self, text_lower: str) -> List[str]:
        """Detect multi-activity patterns (e.g., "birthday dinner")."""
        for pattern, activities in MULTI_ACTIVITY_PATTERNS:
            if re.search(pattern, text_lower):
                return activities
        return []

    def _get_hierarchy_path(self, activity: str) -> str:
        """Get full taxonomy hierarchy path for activity."""
        category = ACTIVITY_TO_CATEGORY.get(activity)
        if category:
            return f"{category}.{activity}"
        return activity

    def _normalize_label(self, label: str) -> str:
        """Normalize ML label to internal activity type."""
        # Map zero-shot labels to internal format
        label_map = {
            "work meeting": "work_meeting",
            "medical appointment": "medical_appointment",
            "family gathering": "family_gathering",
            "religious activity": "religious_activity",
            "household chore": "household_chore",
            "outdoor recreation": "outdoor_recreation",
            "social event": "social_event",
            "personal care": "personal_care",
            "creative activity": "creative_activity",
            "pet care": "pet_care",
        }
        return label_map.get(label.lower(), label.lower().replace(" ", "_"))

    def _create_default_classification(self) -> ActivityClassification:
        """Create default classification for empty input."""
        _metrics["unknown_classifications"] += 1
        return ActivityClassification(
            primary_activity="routine",
            confidence=0.3,
            classification_tier=self.tier.value,
            hierarchy_path="routine",
            parent_category="routine",
        )


# Module-level singleton
_classifier: Optional[ZeroShotActivityClassifier] = None


def get_classifier(
    tier: ClassificationTier = ClassificationTier.RULE_BASED,
) -> ZeroShotActivityClassifier:
    """
    Get or create module-level classifier singleton.

    Args:
        tier: Classification tier to use

    Returns:
        ZeroShotActivityClassifier instance
    """
    global _classifier
    if _classifier is None or _classifier.tier != tier:
        _classifier = ZeroShotActivityClassifier(tier=tier)
    return _classifier


def classify_activity(
    text: str,
    tier: ClassificationTier = ClassificationTier.RULE_BASED,
) -> ActivityClassification:
    """
    Convenience function for activity classification.

    Args:
        text: Input text to classify
        tier: Classification tier (default: rule_based)

    Returns:
        ActivityClassification with primary activity and metadata
    """
    classifier = get_classifier(tier)
    return classifier.classify(text)


def get_metrics() -> Dict[str, Any]:
    """Get module metrics for observability."""
    return _metrics.copy()


def reset_metrics() -> None:
    """Reset all metrics (for testing)."""
    global _metrics
    _metrics = {
        "total_classifications": 0,
        "rule_based_classifications": 0,
        "ml_classifications": 0,
        "multi_activity_detected": 0,
        "unknown_classifications": 0,
    }


# Legacy compatibility mapping (new activity type -> legacy 7-type)
LEGACY_ACTIVITY_MAP: Dict[str, str] = {
    # Sustenance -> meal
    "meal": "meal",
    "cooking": "meal",
    "dining_out": "meal",
    # Celebration/Milestone -> milestone
    "celebration": "milestone",
    "birthday": "milestone",
    "anniversary": "milestone",
    "graduation": "milestone",
    "wedding": "milestone",
    "religious_activity": "milestone",
    # Work -> work
    "work_meeting": "work",
    "project_work": "work",
    "commute": "work",
    "networking": "work",
    # Social -> social
    "family_gathering": "social",
    "social_event": "social",
    "party": "social",
    "hangout": "social",
    "date": "social",
    # Conversation -> conversation
    "conversation": "conversation",
    "phone_call": "conversation",
    "video_call": "conversation",
    # Entertainment -> social (closest match)
    "entertainment": "social",
    "travel": "social",
    # Wellness and others -> routine
    "exercise": "routine",
    "medical_appointment": "routine",
    "personal_care": "routine",
    "outdoor_recreation": "routine",
    "shopping": "routine",
    "household_chore": "routine",
    "education": "routine",
    "creative_activity": "routine",
    "sports": "routine",
    "pet_care": "routine",
    "routine": "routine",
    "reading": "routine",
    "relaxation": "routine",
}


def map_legacy_activity(activity: str) -> str:
    """
    Map enhanced activity type to legacy 7-type system.

    Enhanced types: 20+ activities (meal, exercise, celebration, etc.)
    Legacy types: meal, milestone, work, social, conversation, routine, unknown

    Args:
        activity: Enhanced activity type from ZeroShotActivityClassifier

    Returns:
        Legacy activity type (one of 7 types)
    """
    return LEGACY_ACTIVITY_MAP.get(activity, "unknown")
