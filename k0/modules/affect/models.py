"""
Affect Module Data Models

Core data structures for affect sensing pipeline.
All models use Pydantic for validation and JSON serialization.

Reference: ADR-0012a (k003a - Affect Contracts & Storage Mapping)

Schemas: k0/contracts/jsonschema/affect/
"""

import time
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# =============================================================================
# Enums
# =============================================================================


class PolicyBand(str, Enum):
    """Policy band enum matching affect_annotation.json schema."""

    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"
    BLACK = "BLACK"


class MoodLabel(str, Enum):
    """Mood labels from Circumplex Model (affect_summary.json)."""

    CALM = "calm"
    HAPPY = "happy"
    EXCITED = "excited"
    STRESSED = "stressed"
    SAD = "sad"
    FRUSTRATED = "frustrated"


class Trend(str, Enum):
    """Affect trend (affect_summary.json)."""

    IMPROVING = "improving"
    DECLINING = "declining"
    STABLE = "stable"


class ActionType(str, Enum):
    """Counterfactual action types (counterfactual_input.json)."""

    SHARE = "share"
    NOTIFY = "notify"
    RECALL = "recall"
    SUGGEST = "suggest"


class Recommendation(str, Enum):
    """Counterfactual recommendation (counterfactual_result.json)."""

    PROCEED = "PROCEED"
    PROCEED_PARTIAL = "PROCEED_PARTIAL"
    DELAY = "DELAY"
    BLOCK_ALL = "BLOCK_ALL"


class SafetyRule(str, Enum):
    """Safety rules for counterfactual simulation."""

    PUSH_INTO_RED = "PUSH_INTO_RED"
    AMPLIFY_DISTRESS = "AMPLIFY_DISTRESS"
    SPIKE_AROUSAL_DURING_CONFLICT = "SPIKE_AROUSAL_DURING_CONFLICT"
    AROUSAL_OVERFLOW = "AROUSAL_OVERFLOW"
    PUSH_INTO_BLACK = "PUSH_INTO_BLACK"


class BehaviorMode(str, Enum):
    """K1 behavior modes (affect_summary.json)."""

    SLOW = "slow"
    GENTLE = "gentle"
    QUIET = "quiet"
    WIND_DOWN = "wind_down"
    OPPORTUNITY = "opportunity"


class ModalitySource(str, Enum):
    """Sources for modality scores fused in ADR-0012d."""

    TIER0 = "tier0"
    TIER1 = "tier1"
    BEHAVIOR = "behavior"


# =============================================================================
# Core Affect Models (Contract-compliant with JSON schemas)
# =============================================================================


class AffectAnnotation(BaseModel):
    """
    Affect classification result for a text event.

    Contract: k0/contracts/jsonschema/affect/affect_annotation.json
    Reference: ADR-0012a (k003a)

    Stored in st_hipp_store as 6 additional columns:
    - affect_valence, affect_arousal, affect_tags, affect_confidence,
      affect_band, affect_band_reasons
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "event_id": "evt_1234",
                "space_id": "space_family_alpha",
                "valence": -0.6,
                "arousal": 0.8,
                "tags": ["distress", "conflict"],
                "confidence": 0.85,
                "band": "RED",
                "band_reasons": ["Minor distress detected", "High arousal"],
                "model_version": "tier0_v1.0",
                "computed_at": 1699900000.0,
            }
        }
    )

    event_id: str = Field(..., min_length=1, max_length=255, description="Event identifier")
    space_id: str = Field(
        ..., min_length=1, max_length=255, description="Space/household identifier"
    )

    # Core affect dimensions (validated ranges)
    valence: float = Field(
        ..., ge=-1.0, le=1.0, description="Valence: -1.0 (negative) to +1.0 (positive)"
    )
    arousal: float = Field(..., ge=0.0, le=1.0, description="Arousal: 0.0 (calm) to 1.0 (aroused)")

    # Metadata
    tags: List[str] = Field(default_factory=list, max_length=20, description="Semantic tags")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Classification confidence")

    # Policy band
    band: PolicyBand = Field(..., description="Policy band (GREEN/AMBER/RED/BLACK)")
    band_reasons: List[str] = Field(
        default_factory=list, max_length=10, description="Reasons for band"
    )

    # Attribution
    model_version: str = Field(
        ..., pattern=r"^(tier0|tier1)_v[0-9]+\.[0-9]+(\.[0-9]+)?$", description="Model version"
    )
    computed_at: float = Field(default_factory=time.time, ge=0.0, description="Unix timestamp")

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags(cls, v: List[str]) -> List[str]:
        """Ensure unique tags, max 50 chars each."""
        if not v:
            return []
        unique_tags = []
        seen = set()
        for tag in v:
            if tag and len(tag) <= 50 and tag not in seen:
                unique_tags.append(tag)
                seen.add(tag)
        return unique_tags[:20]  # Max 20 tags


class ModalityScore(BaseModel):
    """Per-modality affect score used by fusion engine (ADR-0012d)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "valence": 0.65,
                "arousal": 0.55,
                "confidence": 0.85,
                "source": "tier1",
            }
        }
    )

    valence: float = Field(..., ge=-1.0, le=1.0, description="Valence contribution")
    arousal: float = Field(..., ge=0.0, le=1.0, description="Arousal contribution")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence weight")
    source: ModalitySource = Field(..., description="Modality source identifier")


class AffectEMAState(BaseModel):
    """
    Dual EMA (Exponential Moving Average) state for person-level affect smoothing.

    Contract: k0/contracts/jsonschema/affect/affect_ema_state.json
    Reference: ADR-0012d (k003d - Multi-Modal Fusion, EMA & Calibration)

    Tracks fast (α=0.5, ~2-3 events) and slow (α=0.1, ~10-20 events) EMA.
    Cached in-memory with 5-minute TTL and LRU eviction.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "person_id": "person_123",
                "space_id": "space_family_alpha",
                "v_fast": 0.2,
                "a_fast": 0.5,
                "v_slow": 0.1,
                "a_slow": 0.3,
                "last_update": 1699900000.0,
                "n_observations": 15,
            }
        }
    )

    person_id: str = Field(..., min_length=1, max_length=255, description="Person identifier")
    space_id: str = Field(
        ..., min_length=1, max_length=255, description="Space/household identifier"
    )

    # Fast EMA (α=0.5, recent signal)
    v_fast: float = Field(..., ge=-1.0, le=1.0, description="Fast EMA for valence")
    a_fast: float = Field(..., ge=0.0, le=1.0, description="Fast EMA for arousal")

    # Slow EMA (α=0.1, long-term baseline)
    v_slow: float = Field(..., ge=-1.0, le=1.0, description="Slow EMA for valence (baseline mood)")
    a_slow: float = Field(
        ..., ge=0.0, le=1.0, description="Slow EMA for arousal (baseline activation)"
    )

    # Metadata
    last_update: float = Field(
        default_factory=time.time, ge=0.0, description="Unix timestamp of last update"
    )
    n_observations: int = Field(
        default=0, ge=0, description="Total observations (for confidence tracking)"
    )


class CalibrationParams(BaseModel):
    """Per-person calibration parameters managed via P06 feedback (ADR-0012d)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "person_id": "person_123",
                "valence_bias": 0.1,
                "arousal_bias": -0.05,
                "valence_temp": 1.05,
                "arousal_temp": 0.95,
                "alpha_fast": 0.5,
                "n_feedback_samples": 12,
                "last_updated": 1699900000.0,
            }
        }
    )

    person_id: str = Field(..., min_length=1, max_length=255, description="Person identifier")
    valence_bias: float = Field(..., ge=-0.3, le=0.3, description="Valence bias term")
    arousal_bias: float = Field(..., ge=-0.2, le=0.2, description="Arousal bias term")
    valence_temp: float = Field(..., ge=0.5, le=2.0, description="Valence temperature")
    arousal_temp: float = Field(..., ge=0.5, le=2.0, description="Arousal temperature")
    alpha_fast: float = Field(..., ge=0.3, le=0.7, description="Fast EMA smoothing α")
    n_feedback_samples: int = Field(..., ge=0, description="Feedback sample count")
    last_updated: float = Field(..., ge=0.0, description="Unix timestamp of last update")


class BandingResult(BaseModel):
    """
    Policy band classification result with hierarchical rule evaluation.

    Contract: k0/contracts/jsonschema/affect/banding_result.json
    Reference: ADR-0012e (k003e - Policy Band Rules & P18 Integration)

    Used for sharing policy, notification timing, and guardian alerts.
    Evaluation order: BLACK → RED → AMBER → GREEN (first match wins).
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "band": "RED",
                "confidence": 0.9,
                "reasons": ["Minor distress detected", "Parent-child conflict"],
                "rule_ids": ["RED_RULE_1", "RED_RULE_2"],
                "notify_guardian": True,
                "escalate": False,
            }
        }
    )

    band: PolicyBand = Field(..., description="Assigned policy band")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in band assignment")
    reasons: List[str] = Field(
        ..., min_length=1, max_length=10, description="Human-readable reasons"
    )
    rule_ids: List[str] = Field(
        default_factory=list, max_length=27, description="Rule IDs that triggered"
    )

    # Actions
    notify_guardian: bool = Field(..., description="Send immediate guardian notification")
    escalate: bool = Field(..., description="Escalate for human review")

    # Optional P18 PolicyAction mapping
    policy_action: Optional[Dict] = Field(default=None, description="P18 PolicyAction mapping")

    @field_validator("rule_ids", mode="before")
    @classmethod
    def validate_rule_ids(cls, v: List[str]) -> List[str]:
        """Ensure rule IDs match pattern (BLACK|RED|AMBER|GREEN)_RULE_[0-9]+."""
        if not v:
            return []
        import re

        pattern = re.compile(r"^(BLACK|RED|AMBER|GREEN)_RULE_[0-9]+$")
        return [rid for rid in v if pattern.match(rid)][:27]


class HouseholdAggregates(BaseModel):
    """Household affect aggregates (nested in HouseholdAffectState)."""

    valence_mean: float = Field(..., ge=-1.0, le=1.0)
    valence_std: float = Field(..., ge=0.0, le=2.0)
    valence_min: float = Field(..., ge=-1.0, le=1.0)
    valence_max: float = Field(..., ge=-1.0, le=1.0)

    arousal_mean: float = Field(..., ge=0.0, le=1.0)
    arousal_std: float = Field(..., ge=0.0, le=1.0)
    arousal_min: float = Field(..., ge=0.0, le=1.0)
    arousal_max: float = Field(..., ge=0.0, le=1.0)


class ConflictDetails(BaseModel):
    """Conflict details (nested in HouseholdAffectState)."""

    severity: float = Field(..., ge=0.0, le=1.0, description="Conflict severity score")
    participants: int = Field(..., ge=2, description="Number of participants")
    duration_seconds: int = Field(..., ge=0, description="Conflict duration")


class FamilyMomentDetails(BaseModel):
    """Family moment details (nested in HouseholdAffectState)."""

    participants: int = Field(..., ge=3, description="Number of participants")
    type: str = Field(
        ..., pattern="^(celebration|bonding|shared_joy)$", description="Family moment type"
    )
    duration_seconds: int = Field(default=0, ge=0, description="Duration")


class ContagionDetails(BaseModel):
    """Emotional contagion details (nested in HouseholdAffectState)."""

    source_affect: str = Field(
        ..., pattern="^(distress|joy|anxiety|calm)$", description="Source affect type"
    )
    magnitude: float = Field(..., ge=0.0, le=1.0, description="Fraction of household affected")


class HouseholdAffectState(BaseModel):
    """
    Household-level affect dynamics with pattern detection.

    Contract: k0/contracts/jsonschema/affect/household_affect_state.json
    Reference: ADR-0012g (k003g - Household-Level Affect Dynamics)

    Includes:
    - Statistical aggregates (mean, std, min, max)
    - Conflict detection (≥2 members distressed within 5min)
    - Family moments (≥3 members positive within 10min)
    - Emotional contagion detection
    - Privacy-preserving (no individual person_ids exposed)
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "space_id": "space_family_alpha",
                "computed_at": 1699900000.0,
                "n_members": 4,
                "aggregates": {
                    "valence_mean": -0.2,
                    "valence_std": 0.4,
                    "valence_min": -0.6,
                    "valence_max": 0.3,
                    "arousal_mean": 0.6,
                    "arousal_std": 0.2,
                    "arousal_min": 0.4,
                    "arousal_max": 0.8,
                },
                "conflict_active": True,
                "conflict_details": {"severity": 0.7, "participants": 2, "duration_seconds": 180},
                "family_moment_active": False,
            }
        }
    )

    space_id: str = Field(
        ..., min_length=1, max_length=255, description="Space/household identifier"
    )
    computed_at: float = Field(default_factory=time.time, ge=0.0, description="Unix timestamp")
    n_members: int = Field(..., ge=1, description="Number of household members")

    # Statistical aggregates
    aggregates: HouseholdAggregates = Field(..., description="Statistical affect aggregates")

    # Pattern detection
    conflict_active: bool = Field(..., description="Conflict detected")
    conflict_details: Optional[ConflictDetails] = Field(
        default=None, description="Conflict metadata"
    )

    family_moment_active: bool = Field(..., description="Family moment detected")
    family_moment_details: Optional[FamilyMomentDetails] = Field(
        default=None, description="Family moment metadata"
    )

    contagion_detected: bool = Field(default=False, description="Emotional contagion detected")
    contagion_details: Optional[ContagionDetails] = Field(
        default=None, description="Contagion metadata"
    )


class AffectSummary(BaseModel):
    """
    Lightweight affect summary for K1 Planner/Concierge behavior mode adaptation.

    Contract: k0/contracts/jsonschema/affect/affect_summary.json
    Reference: ADR-0012f (k003f - Affect → K1 Planner & Concierge Bridge)

    Maps affect to mood labels (Circumplex Model) and suggests behavior modes:
    - slow: High arousal or RED/AMBER band
    - gentle: Negative valence or sad/frustrated mood
    - quiet: Household conflict active
    - wind_down: Minor + night + elevated arousal
    - opportunity: Positive valence + low arousal + GREEN band
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "person_id": "person_123",
                "space_id": "space_family_alpha",
                "valence": -0.4,
                "arousal": 0.7,
                "band": "RED",
                "mood_label": "stressed",
                "trend": "declining",
                "behavior_modes": ["slow", "gentle"],
                "computed_at": 1699900000.0,
            }
        }
    )

    person_id: str = Field(..., min_length=1, max_length=255, description="Person identifier")
    space_id: str = Field(
        ..., min_length=1, max_length=255, description="Space/household identifier"
    )

    # Current affect (from fast EMA)
    valence: float = Field(..., ge=-1.0, le=1.0, description="Current valence")
    arousal: float = Field(..., ge=0.0, le=1.0, description="Current arousal")
    band: PolicyBand = Field(..., description="Current policy band")

    # Mood interpretation
    mood_label: MoodLabel = Field(..., description="Mood label (Circumplex Model)")
    trend: Trend = Field(..., description="Affect trend (fast vs slow EMA)")

    # Optional household context
    household_state: Optional[Dict] = Field(
        default=None, description="Lightweight household context"
    )

    # K1 behavior modes
    behavior_modes: List[BehaviorMode] = Field(
        default_factory=list, max_length=5, description="Suggested behavior modes"
    )

    # Metadata
    computed_at: float = Field(default_factory=time.time, ge=0.0, description="Unix timestamp")


class CounterfactualContent(BaseModel):
    """Content for counterfactual simulation (nested in CounterfactualInput)."""

    text: str = Field(..., max_length=10000, description="Content text")
    content_affect: Dict = Field(..., description="Pre-computed affect of content")


class CounterfactualInput(BaseModel):
    """
    Input for counterfactual 'what if?' simulation.

    Contract: k0/contracts/jsonschema/affect/counterfactual_input.json
    Reference: ADR-0012i (k003i - Counterfactual Emotional Safety & Sharing)

    Predicts affect impact of actions: share, notify, recall, suggest.
    Used for proactive safety (prevent harmful sharing/notifications).
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "action_type": "share",
                "content": {
                    "text": "Memory content...",
                    "content_affect": {"valence": -0.5, "arousal": 0.6},
                },
                "recipients": ["person_123", "person_456"],
                "current_affect_states": {
                    "person_123": {"valence": -0.3, "arousal": 0.7, "band": "AMBER"},
                    "person_456": {"valence": 0.2, "arousal": 0.4, "band": "GREEN"},
                },
            }
        }
    )

    action_type: ActionType = Field(..., description="Action type")
    content: CounterfactualContent = Field(..., description="Content being evaluated")
    recipients: List[str] = Field(
        ..., min_length=1, max_length=20, description="Recipient person IDs"
    )
    current_affect_states: Dict[str, Dict] = Field(
        ..., min_length=1, description="Current affect states"
    )

    # Optional context
    context: Optional[Dict] = Field(default=None, description="Optional contextual information")


class RecipientImpact(BaseModel):
    """Per-recipient impact prediction (nested in CounterfactualResult)."""

    predicted_valence_delta: float = Field(
        ..., ge=-2.0, le=2.0, description="Predicted valence change"
    )
    predicted_arousal_delta: float = Field(
        ..., ge=-1.0, le=1.0, description="Predicted arousal change"
    )
    predicted_band: PolicyBand = Field(..., description="Predicted policy band")
    safe: bool = Field(..., description="Safe for this recipient")
    violated_rules: List[SafetyRule] = Field(
        default_factory=list, max_length=5, description="Violated safety rules"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Prediction confidence")


class CounterfactualResult(BaseModel):
    """
    Result of counterfactual simulation with per-recipient impact predictions.

    Contract: k0/contracts/jsonschema/affect/counterfactual_result.json
    Reference: ADR-0012i (k003i)

    5 safety rules:
    1. Don't push into RED band
    2. Don't amplify distress
    3. Don't spike arousal during conflict
    4. Don't push arousal >0.85
    5. Don't push into BLACK band
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "action_type": "share",
                "overall_safe": False,
                "recipient_impacts": {
                    "person_123": {
                        "predicted_valence_delta": -0.2,
                        "predicted_arousal_delta": 0.1,
                        "predicted_band": "RED",
                        "safe": False,
                        "violated_rules": ["PUSH_INTO_RED"],
                        "confidence": 0.8,
                    }
                },
                "blocked_recipients": ["person_123"],
                "allowed_recipients": ["person_456"],
                "recommendation": "PROCEED_PARTIAL",
                "explanation": "Blocked for person_123: would push into RED band",
                "computed_at": 1699900000.0,
            }
        }
    )

    action_type: ActionType = Field(..., description="Action type")
    overall_safe: bool = Field(..., description="Safe for ALL recipients")
    recipient_impacts: Dict[str, RecipientImpact] = Field(
        ..., min_length=1, description="Per-recipient impacts"
    )

    blocked_recipients: List[str] = Field(default_factory=list, description="Blocked recipient IDs")
    allowed_recipients: List[str] = Field(default_factory=list, description="Allowed recipient IDs")

    recommendation: Recommendation = Field(..., description="Overall recommendation")
    explanation: str = Field(default="", max_length=500, description="Human-readable explanation")

    computed_at: float = Field(default_factory=time.time, ge=0.0, description="Unix timestamp")


# =============================================================================
# Additional Models (not in JSON schemas, internal use only)
# =============================================================================


class Relationship(BaseModel):
    """
    Relationship between two people.

    Reference: ADR-0012h (k003h - Social Cognition & Relationship Context Modifiers)

    Used by social context engine for affect modifiers.
    Stored encrypted with MLS household key.
    """

    person_a: str = Field(..., min_length=1, max_length=255)
    person_b: str = Field(..., min_length=1, max_length=255)
    relationship_type: str = Field(
        ...,
        pattern="^(parent-child|partner|sibling|friend|caregiver-dependent|extended-family)$",
        description="Relationship type",
    )

    direction: Optional[str] = Field(
        default=None, description="Directional relationship (e.g., 'a→b' for parent-child)"
    )
    strength: float = Field(default=1.0, ge=0.0, le=1.0, description="Relationship strength")

    created_at: float = Field(default_factory=time.time, ge=0.0)
    last_interaction: float = Field(default=0.0, ge=0.0)


class LifecycleContext(BaseModel):
    """
    Lifecycle context for affect interpretation.

    Reference: ADR-0012h (k003h - Social Cognition & Relationship Context Modifiers)

    Used for lifecycle-aware affect modifiers (school hours, bedtime, special events).
    """

    time_of_day: str = Field(
        ..., pattern="^(morning|afternoon|evening|night)$", description="Time of day"
    )
    day_of_week: str = Field(
        ...,
        pattern="^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$",
        description="Day of week",
    )
    is_weekend: bool = Field(...)
    is_holiday: bool = Field(default=False)
    special_event: Optional[str] = Field(
        default=None, max_length=100, description="Special event name"
    )

    # Context for minors
    is_school_hours: bool = Field(
        default=False, description="School hours (8am-3pm weekdays for minors)"
    )
    is_bedtime: bool = Field(default=False, description="Bedtime (age-dependent)")
