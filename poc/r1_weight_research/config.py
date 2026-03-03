"""R1 Weight Research -- configuration constants and mapping tables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

# ---------------------------------------------------------------------------
# Weight configurations (from Discovery doc Section 16.6.3)
# All 6 additive components sum to 1.0
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WeightConfig:
    """Additive component weights for the R1 formula."""

    name: str
    # emotional = sentiment_w + affect_w + arousal_w (sub-splits below)
    sentiment_w: float
    affect_w: float
    arousal_w: float
    surprise_w: float
    novelty_w: float
    social_w: float
    identity_w: float
    recency_w: float

    @property
    def emotional_total(self) -> float:
        return self.sentiment_w + self.affect_w + self.arousal_w

    @property
    def total(self) -> float:
        return (
            self.emotional_total
            + self.surprise_w
            + self.novelty_w
            + self.social_w
            + self.identity_w
            + self.recency_w
        )


CONFIG_A = WeightConfig(
    name="A_balanced",
    sentiment_w=0.07,
    affect_w=0.07,
    arousal_w=0.06,  # emotional = 0.20
    surprise_w=0.15,
    novelty_w=0.20,
    social_w=0.15,
    identity_w=0.15,
    recency_w=0.15,
)

CONFIG_B = WeightConfig(
    name="B_emotion_heavy",
    sentiment_w=0.10,
    affect_w=0.12,
    arousal_w=0.08,  # emotional = 0.30
    surprise_w=0.15,
    novelty_w=0.15,
    social_w=0.15,
    identity_w=0.10,
    recency_w=0.15,
)

CONFIG_C = WeightConfig(
    name="C_social_identity",
    sentiment_w=0.07,
    affect_w=0.07,
    arousal_w=0.06,  # emotional = 0.20
    surprise_w=0.10,
    novelty_w=0.15,
    social_w=0.20,
    identity_w=0.20,
    recency_w=0.15,
)

CONFIG_D = WeightConfig(
    name="D_novelty_surprise",
    sentiment_w=0.05,
    affect_w=0.05,
    arousal_w=0.05,  # emotional = 0.15
    surprise_w=0.20,
    novelty_w=0.25,
    social_w=0.10,
    identity_w=0.15,
    recency_w=0.15,
)

ALL_CONFIGS = [CONFIG_A, CONFIG_B, CONFIG_C, CONFIG_D]

# ---------------------------------------------------------------------------
# Sentiment categorical -> numeric map
# ---------------------------------------------------------------------------

SENTIMENT_MAP: Dict[str, float] = {
    "very_negative": -0.90,
    "negative": -0.50,
    "neutral": 0.00,
    "positive": 0.50,
    "very_positive": 0.90,
}

# ---------------------------------------------------------------------------
# Ingress -> activity_type map (aligns with production EVENT_TYPE_MULTIPLIERS)
# ---------------------------------------------------------------------------

INGRESS_TO_ACTIVITY: Dict[str, str] = {
    "CELEBRATION": "celebration",
    "CONCERN": "message",
    "RELATIONSHIP": "message",
    "DIARY": "message",
    "MEMORY": "message",
    "GRATITUDE": "message",
    "HEALTH": "message",
    "PLANNING": "calendar",
    "TASK": "routine",
    "WORK": "routine",
    "FINANCE": "transaction",
    "META": "chat",
}

# ---------------------------------------------------------------------------
# Event type multipliers (mirrors production importance_scorer.py)
# ---------------------------------------------------------------------------

EVENT_TYPE_MULTIPLIERS: Dict[str, float] = {
    "message": 1.0,
    "chat": 1.0,
    "photo": 1.2,
    "image": 1.2,
    "video": 1.3,
    "milestone": 2.0,
    "celebration": 2.0,
    "routine": 0.5,
    "location": 0.8,
    "voice": 1.1,
    "audio": 1.1,
    "calendar": 0.9,
    "transaction": 0.6,
}

# ---------------------------------------------------------------------------
# Intent boost multipliers (mirrors production importance_scorer.py)
# ---------------------------------------------------------------------------

INTENT_BOOST_MULTIPLIERS: Dict[str, float] = {
    "query_memory": 1.20,
    "share_news": 1.20,
    "set_reminder": 1.15,
    "make_plan": 1.15,
    "seek_advice": 1.10,
    "reflect": 1.10,
    "express_feeling": 1.00,
    "casual_chat": 0.90,
    "log_memory": 1.15,
    "other": 1.00,
}

# ---------------------------------------------------------------------------
# Elaboration depth from word count
# ---------------------------------------------------------------------------

ELABORATION_THRESHOLDS = {
    # (min_words, label)
    "DEEPLY_PROCESSED": 40,
    "ELABORATED": 20,
    "DISCUSSED": 8,
    "MENTION": 0,
}

ELABORATION_BOOST: Dict[str, float] = {
    "MENTION": 1.00,
    "DISCUSSED": 1.05,
    "ELABORATED": 1.10,
    "DEEPLY_PROCESSED": 1.15,
}

# ---------------------------------------------------------------------------
# Novelty categorical -> numeric map
# ---------------------------------------------------------------------------

NOVELTY_NUMERIC: Dict[str, float] = {
    "ROUTINE": 0.10,
    "EXPECTED": 0.30,
    "NOVEL": 0.70,
    "SURPRISING": 1.00,
}

# ---------------------------------------------------------------------------
# Social intimacy from relation predicates
# ---------------------------------------------------------------------------

RELATION_INTIMACY: Dict[str, str] = {
    "spouse_of": "HIGH",
    "parent_of": "HIGH",
    "child_of": "HIGH",
    "sibling_of": "MEDIUM",
    "grandparent_of": "MEDIUM",
    "grandchild_of": "MEDIUM",
    "aunt_uncle_of": "MEDIUM",
    "niece_nephew_of": "MEDIUM",
    "cousin_of": "MEDIUM",
    "pet_of": "MEDIUM",
    "owns": "LOW",
    "lives_at": "LOW",
    "friend_of": "LOW",
    "colleague_of": "LOW",
    "family_of": "MEDIUM",
    "child_in_law_of": "MEDIUM",
    "no_relation": "LOW",
}

INTIMACY_SCALE: Dict[str, float] = {
    "HIGH": 1.20,
    "MEDIUM": 1.00,
    "LOW": 0.80,
}

# ---------------------------------------------------------------------------
# Temporal orientation heuristic signals
# ---------------------------------------------------------------------------

FUTURE_INTENTS = {"set_reminder", "make_plan"}
FUTURE_INGRESS = {"PLANNING", "TASK"}
PAST_TEMPORAL_LABELS = {"DATE_REL", "DATE_ABS", "AGE"}

# ---------------------------------------------------------------------------
# Identity-activating NER labels
# ---------------------------------------------------------------------------

IDENTITY_NER_LABELS = {"KINSHIP", "TRADITION", "HEIRLOOM", "MILESTONE", "NICKNAME"}

# Max identity NER count for normalization (observed ~6 in dense events)
IDENTITY_NER_MAX = 6.0

# ---------------------------------------------------------------------------
# Source reliability (constant for this dataset -- all user_stated)
# ---------------------------------------------------------------------------

SOURCE_RELIABILITY_USER_STATED = 0.95

# ---------------------------------------------------------------------------
# Recency lambda candidates (for Phase 5)
# ---------------------------------------------------------------------------

LAMBDA_VALUES = [0.005, 0.01, 0.02, 0.05]

# ---------------------------------------------------------------------------
# Reliability floor candidates (for Phase 5)
# ---------------------------------------------------------------------------

RELIABILITY_FLOORS = [0.0, 0.30, 0.50, 0.70]

# ---------------------------------------------------------------------------
# Temporal orientation boost
# ---------------------------------------------------------------------------

TEMPORAL_BOOST: Dict[str, float] = {
    "PAST": 1.00,
    "ONGOING": 1.05,
    "FUTURE_COMMITMENT": 1.10,
}

# log2(10) for social factor normalization (matches production)
LOG2_10 = 3.321928
