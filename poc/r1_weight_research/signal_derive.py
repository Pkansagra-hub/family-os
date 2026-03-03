"""Phase 1: Signal Derivation Layer.

Converts raw FamilyOS event JSON (K1 UltraBERT output) into R1-compatible
signal vectors that the importance scoring formula can consume.

Each derivation function is independent and documented with its quality
rating from the research plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .config import (
    ELABORATION_THRESHOLDS,
    FUTURE_INGRESS,
    FUTURE_INTENTS,
    IDENTITY_NER_LABELS,
    IDENTITY_NER_MAX,
    INGRESS_TO_ACTIVITY,
    PAST_TEMPORAL_LABELS,
    RELATION_INTIMACY,
    SENTIMENT_MAP,
    SOURCE_RELIABILITY_USER_STATED,
)
from .nrc_vad_lexicon import emotions_to_vad

# ---------------------------------------------------------------------------
# Signal vector dataclass -- output of derivation
# ---------------------------------------------------------------------------


@dataclass
class R1SignalVector:
    """All signals needed by the R1 importance formula.

    Every field corresponds to a row in the research plan Phase 1 table.
    """

    # Event identity
    event_id: str

    # --- Core numeric signals ---
    sentiment_score: float  # [-1, 1]
    affect_valence: float  # [-1, 1]
    affect_arousal: float  # [0, 1]
    affect_dominance: float  # [0, 1]
    surprise_level: float  # [0, 1]

    # --- Social signals ---
    num_participants: int  # >= 1
    social_intimacy: str  # LOW / MEDIUM / HIGH

    # --- Categorical signals ---
    activity_type: str  # maps to EVENT_TYPE_MULTIPLIERS
    intent: str  # maps to INTENT_BOOST_MULTIPLIERS
    novelty: str  # ROUTINE / EXPECTED / NOVEL / SURPRISING
    elaboration_depth: str  # MENTION / DISCUSSED / ELABORATED / DEEPLY_PROCESSED
    temporal_orientation: str  # PAST / ONGOING / FUTURE_COMMITMENT

    # --- Identity signals ---
    identity_relevance: float  # [0, 1]

    # --- Constants for this dataset ---
    source_type: str = "user_stated"
    source_reliability: float = SOURCE_RELIABILITY_USER_STATED
    narrative_is_goal_event: bool = False
    narrative_arc_position: str = "EXPOSITION"
    memory_tier: str = "routine"

    # --- Proxy label (filled by proxy_labels.py, not derivation) ---
    proxy_tier: str = ""

    # --- Raw text length (for debugging) ---
    word_count: int = 0


# ---------------------------------------------------------------------------
# Derivation functions -- one per signal
# ---------------------------------------------------------------------------


def derive_sentiment_score(tasks: Dict[str, Any]) -> float:
    """Categorical sentiment -> numeric score. Quality: HIGH."""
    label = tasks.get("sentiment", "neutral")
    return SENTIMENT_MAP.get(label, 0.0)


def derive_affect(tasks: Dict[str, Any]) -> tuple[float, float, float]:
    """Emotion labels -> (valence [-1,1], arousal [0,1], dominance [0,1]).

    Uses NRC-VAD lexicon averaging. Quality: HIGH.
    """
    emotions = tasks.get("emotions", [])
    vad = emotions_to_vad(emotions)
    # Convert NRC valence [0,1] to R1 valence [-1,1]
    valence_r1 = 2.0 * vad.valence - 1.0
    return valence_r1, vad.arousal, vad.dominance


def derive_surprise_level(tasks: Dict[str, Any]) -> float:
    """Emotion list -> surprise float. Quality: LOW (coarse binary).

    1.0 if 'surprise' in emotion list, else 0.0.
    """
    emotions = tasks.get("emotions", [])
    if "surprise" in emotions:
        return 1.0
    return 0.0


def derive_num_participants(tasks: Dict[str, Any]) -> int:
    """NER family entities -> participant count. Quality: HIGH.

    Counts unique KINSHIP + PERSON entities + 1 (for user). Minimum 1.
    """
    ner = tasks.get("ner_family", [])
    people = set()
    for ent in ner:
        if ent.get("label") in ("KINSHIP", "PERSON", "NICKNAME"):
            people.add(ent.get("token", "").lower())
    return max(1, len(people) + 1)  # +1 for the user


def derive_social_intimacy(tasks: Dict[str, Any]) -> str:
    """Relation predicates -> highest intimacy level. Quality: MEDIUM.

    Uses predicate hierarchy. Falls back to LOW if no relations.
    """
    relations = tasks.get("relations", [])
    if not relations:
        return "LOW"

    hierarchy = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    best = "LOW"
    best_rank = 1
    for rel in relations:
        pred = rel.get("predicate", "")
        level = RELATION_INTIMACY.get(pred, "LOW")
        rank = hierarchy.get(level, 1)
        if rank > best_rank:
            best = level
            best_rank = rank
    return best


def derive_activity_type(tasks: Dict[str, Any]) -> str:
    """Ingress -> activity_type enum. Quality: HIGH.

    Special case: if MILESTONE NER present, override to 'milestone'.
    """
    ingress = tasks.get("ingress", "")
    # Check for milestone NER override
    ner = tasks.get("ner_family", [])
    for ent in ner:
        if ent.get("label") == "MILESTONE":
            return "milestone"
    return INGRESS_TO_ACTIVITY.get(ingress, "message")


def derive_novelty(tasks: Dict[str, Any]) -> str:
    """Ingress + NER + safety -> novelty enum. Quality: MEDIUM (heuristic).

    Rules:
      SURPRISING: safety = CRISIS or RED
      NOVEL: MILESTONE NER or CELEBRATION ingress or FAMILY_EVENT NER
      EXPECTED: RELATIONSHIP/MEMORY/HEALTH ingress
      ROUTINE: DIARY/TASK/WORK/META/FINANCE + neutral sentiment
    """
    safety = tasks.get("safety_familyos", "GREEN")
    if safety in ("CRISIS", "RED"):
        return "SURPRISING"

    ingress = tasks.get("ingress", "")
    ner_labels = {ent.get("label") for ent in tasks.get("ner_family", [])}

    if "MILESTONE" in ner_labels or ingress == "CELEBRATION" or "FAMILY_EVENT" in ner_labels:
        return "NOVEL"

    if ingress in ("RELATIONSHIP", "MEMORY", "HEALTH", "GRATITUDE", "CONCERN"):
        return "EXPECTED"

    return "ROUTINE"


def derive_identity_relevance(tasks: Dict[str, Any]) -> float:
    """Identity-activating NER density -> [0, 1]. Quality: MEDIUM.

    Counts KINSHIP, TRADITION, HEIRLOOM, MILESTONE, NICKNAME entities
    and normalizes by IDENTITY_NER_MAX.
    """
    ner = tasks.get("ner_family", [])
    count = sum(1 for ent in ner if ent.get("label") in IDENTITY_NER_LABELS)
    return min(1.0, count / IDENTITY_NER_MAX)


def derive_elaboration_depth(text: str) -> tuple[str, int]:
    """Text length -> elaboration depth enum + word count. Quality: LOW.

    Thresholds: <8 MENTION, 8-19 DISCUSSED, 20-39 ELABORATED, 40+ DEEPLY_PROCESSED.
    """
    words = len(text.split())
    if words >= ELABORATION_THRESHOLDS["DEEPLY_PROCESSED"]:
        return "DEEPLY_PROCESSED", words
    if words >= ELABORATION_THRESHOLDS["ELABORATED"]:
        return "ELABORATED", words
    if words >= ELABORATION_THRESHOLDS["DISCUSSED"]:
        return "DISCUSSED", words
    return "MENTION", words


def derive_temporal_orientation(tasks: Dict[str, Any]) -> str:
    """Temporal labels + intent -> orientation enum. Quality: MEDIUM.

    FUTURE_COMMITMENT: set_reminder/make_plan intent or PLANNING/TASK ingress
    PAST: has DATE_REL or DATE_ABS or AGE temporal labels
    ONGOING: default
    """
    intent = tasks.get("intent", "")
    ingress = tasks.get("ingress", "")

    if intent in FUTURE_INTENTS or ingress in FUTURE_INGRESS:
        return "FUTURE_COMMITMENT"

    temporal = tasks.get("temporal", [])
    if temporal:
        labels = {t.get("label") for t in temporal}
        if labels & PAST_TEMPORAL_LABELS:
            return "PAST"

    return "ONGOING"


# ---------------------------------------------------------------------------
# Main derivation entry point
# ---------------------------------------------------------------------------


def derive_signal_vector(event: Dict[str, Any]) -> R1SignalVector:
    """Convert a raw FamilyOS event JSON object into an R1SignalVector.

    This is the single entry point for Phase 1 signal derivation.
    """
    event_id = event.get("id", "unknown")
    text = event.get("text", "")
    tasks = event.get("tasks", {})

    sentiment_score = derive_sentiment_score(tasks)
    valence, arousal, dominance = derive_affect(tasks)
    surprise_level = derive_surprise_level(tasks)
    num_participants = derive_num_participants(tasks)
    social_intimacy = derive_social_intimacy(tasks)
    activity_type = derive_activity_type(tasks)
    intent = tasks.get("intent", "other")
    novelty = derive_novelty(tasks)
    identity_relevance = derive_identity_relevance(tasks)
    elaboration_depth, word_count = derive_elaboration_depth(text)
    temporal_orientation = derive_temporal_orientation(tasks)

    return R1SignalVector(
        event_id=event_id,
        sentiment_score=sentiment_score,
        affect_valence=valence,
        affect_arousal=arousal,
        affect_dominance=dominance,
        surprise_level=surprise_level,
        num_participants=num_participants,
        social_intimacy=social_intimacy,
        activity_type=activity_type,
        intent=intent,
        novelty=novelty,
        elaboration_depth=elaboration_depth,
        temporal_orientation=temporal_orientation,
        identity_relevance=identity_relevance,
        word_count=word_count,
    )
