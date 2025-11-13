"""
Comprehensive tests for Affect Module Pydantic models.

Tests cover:
- Schema validation (valid/invalid inputs)
- Serialization/deserialization round-trips
- Range validation (valence, arousal)
- Enum validation
- Nested model validation
- Custom validators (tags, rule_ids)

Reference: ADR-0012a (k003a - Affect Contracts & Storage Mapping)
"""

import time

import pytest
from pydantic import ValidationError

from k0.modules.affect.models import (
    ActionType,
    AffectAnnotation,
    AffectEMAState,
    AffectSummary,
    BandingResult,
    BehaviorMode,
    CounterfactualContent,
    CounterfactualInput,
    CounterfactualResult,
    HouseholdAffectState,
    LifecycleContext,
    MoodLabel,
    PolicyBand,
    RecipientImpact,
    Recommendation,
    Relationship,
    SafetyRule,
    Trend,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def valid_affect_annotation():
    """Valid AffectAnnotation for testing."""
    return {
        "event_id": "evt_test_001",
        "space_id": "space_family_alpha",
        "valence": 0.5,
        "arousal": 0.6,
        "tags": ["happy", "content"],
        "confidence": 0.9,
        "band": "GREEN",
        "band_reasons": ["Positive affect", "Low arousal"],
        "model_version": "tier0_v1.0",
        "computed_at": time.time(),
    }


@pytest.fixture
def valid_ema_state():
    """Valid AffectEMAState for testing."""
    return {
        "person_id": "person_123",
        "space_id": "space_family_alpha",
        "v_fast": 0.2,
        "a_fast": 0.5,
        "v_slow": 0.1,
        "a_slow": 0.3,
        "last_update": time.time(),
        "n_observations": 15,
    }


@pytest.fixture
def valid_banding_result():
    """Valid BandingResult for testing."""
    return {
        "band": "RED",
        "confidence": 0.85,
        "reasons": ["Minor distress detected", "Parent-child conflict"],
        "rule_ids": ["RED_RULE_1", "RED_RULE_2"],
        "notify_guardian": True,
        "escalate": False,
    }


@pytest.fixture
def valid_household_state():
    """Valid HouseholdAffectState for testing."""
    return {
        "space_id": "space_family_alpha",
        "computed_at": time.time(),
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


# =============================================================================
# AffectAnnotation Tests
# =============================================================================


class TestAffectAnnotation:
    """Tests for AffectAnnotation model."""

    def test_valid_annotation(self, valid_affect_annotation):
        """Test creation with valid data."""
        annotation = AffectAnnotation(**valid_affect_annotation)
        assert annotation.event_id == "evt_test_001"
        assert annotation.valence == 0.5
        assert annotation.arousal == 0.6
        assert annotation.band == PolicyBand.GREEN
        assert len(annotation.tags) == 2

    def test_valence_range_validation(self, valid_affect_annotation):
        """Test valence must be in [-1.0, 1.0]."""
        # Test upper bound
        valid_affect_annotation["valence"] = 1.5
        with pytest.raises(ValidationError) as exc_info:
            AffectAnnotation(**valid_affect_annotation)
        assert "valence" in str(exc_info.value)
        assert "less than or equal to 1" in str(exc_info.value)

        # Test lower bound
        valid_affect_annotation["valence"] = -1.5
        with pytest.raises(ValidationError) as exc_info:
            AffectAnnotation(**valid_affect_annotation)
        assert "valence" in str(exc_info.value)
        assert "greater than or equal to -1" in str(exc_info.value)

    def test_arousal_range_validation(self, valid_affect_annotation):
        """Test arousal must be in [0.0, 1.0]."""
        # Test upper bound
        valid_affect_annotation["arousal"] = 1.5
        with pytest.raises(ValidationError) as exc_info:
            AffectAnnotation(**valid_affect_annotation)
        assert "arousal" in str(exc_info.value)

        # Test lower bound
        valid_affect_annotation["arousal"] = -0.5
        with pytest.raises(ValidationError) as exc_info:
            AffectAnnotation(**valid_affect_annotation)
        assert "arousal" in str(exc_info.value)

    def test_confidence_range_validation(self, valid_affect_annotation):
        """Test confidence must be in [0.0, 1.0]."""
        valid_affect_annotation["confidence"] = 1.2
        with pytest.raises(ValidationError) as exc_info:
            AffectAnnotation(**valid_affect_annotation)
        assert "confidence" in str(exc_info.value)

    def test_band_enum_validation(self, valid_affect_annotation):
        """Test band must be valid PolicyBand enum."""
        valid_affect_annotation["band"] = "INVALID_BAND"
        with pytest.raises(ValidationError) as exc_info:
            AffectAnnotation(**valid_affect_annotation)
        assert "band" in str(exc_info.value)

    def test_model_version_pattern(self, valid_affect_annotation):
        """Test model_version pattern validation."""
        # Valid patterns
        for version in ["tier0_v1.0", "tier1_v2.5", "tier0_v1.0.3"]:
            valid_affect_annotation["model_version"] = version
            annotation = AffectAnnotation(**valid_affect_annotation)
            assert annotation.model_version == version

        # Invalid pattern
        valid_affect_annotation["model_version"] = "invalid_version"
        with pytest.raises(ValidationError) as exc_info:
            AffectAnnotation(**valid_affect_annotation)
        assert "model_version" in str(exc_info.value)

    def test_tags_validation(self, valid_affect_annotation):
        """Test tags custom validation (unique, max 50 chars)."""
        # Test uniqueness
        valid_affect_annotation["tags"] = ["happy", "happy", "content"]
        annotation = AffectAnnotation(**valid_affect_annotation)
        assert len(annotation.tags) == 2  # Duplicates removed

        # Test max length per tag
        valid_affect_annotation["tags"] = ["a" * 60]  # 60 chars
        annotation = AffectAnnotation(**valid_affect_annotation)
        assert len(annotation.tags) == 0  # Tag too long, removed

        # Test max tags count
        valid_affect_annotation["tags"] = [f"tag_{i}" for i in range(25)]
        annotation = AffectAnnotation(**valid_affect_annotation)
        assert len(annotation.tags) == 20  # Max 20 tags

    def test_json_serialization_roundtrip(self, valid_affect_annotation):
        """Test JSON serialization/deserialization."""
        annotation = AffectAnnotation(**valid_affect_annotation)
        json_str = annotation.model_dump_json()
        reconstructed = AffectAnnotation.model_validate_json(json_str)

        assert reconstructed.event_id == annotation.event_id
        assert reconstructed.valence == annotation.valence
        assert reconstructed.arousal == annotation.arousal
        assert reconstructed.band == annotation.band

    def test_dict_serialization_roundtrip(self, valid_affect_annotation):
        """Test dict serialization/deserialization."""
        annotation = AffectAnnotation(**valid_affect_annotation)
        data_dict = annotation.model_dump()
        reconstructed = AffectAnnotation(**data_dict)

        assert reconstructed.event_id == annotation.event_id
        assert reconstructed.valence == annotation.valence


# =============================================================================
# AffectEMAState Tests
# =============================================================================


class TestAffectEMAState:
    """Tests for AffectEMAState model."""

    def test_valid_ema_state(self, valid_ema_state):
        """Test creation with valid data."""
        ema = AffectEMAState(**valid_ema_state)
        assert ema.person_id == "person_123"
        assert ema.v_fast == 0.2
        assert ema.v_slow == 0.1
        assert ema.n_observations == 15

    def test_valence_range_validation(self, valid_ema_state):
        """Test valence EMA ranges."""
        # v_fast out of range
        valid_ema_state["v_fast"] = 1.5
        with pytest.raises(ValidationError):
            AffectEMAState(**valid_ema_state)

        # v_slow out of range
        valid_ema_state["v_fast"] = 0.2
        valid_ema_state["v_slow"] = -1.5
        with pytest.raises(ValidationError):
            AffectEMAState(**valid_ema_state)

    def test_arousal_range_validation(self, valid_ema_state):
        """Test arousal EMA ranges."""
        # a_fast out of range
        valid_ema_state["a_fast"] = 1.5
        with pytest.raises(ValidationError):
            AffectEMAState(**valid_ema_state)

        # a_slow out of range
        valid_ema_state["a_fast"] = 0.5
        valid_ema_state["a_slow"] = -0.5
        with pytest.raises(ValidationError):
            AffectEMAState(**valid_ema_state)

    def test_n_observations_validation(self, valid_ema_state):
        """Test n_observations must be non-negative."""
        valid_ema_state["n_observations"] = -5
        with pytest.raises(ValidationError):
            AffectEMAState(**valid_ema_state)

    def test_json_serialization_roundtrip(self, valid_ema_state):
        """Test JSON serialization/deserialization."""
        ema = AffectEMAState(**valid_ema_state)
        json_str = ema.model_dump_json()
        reconstructed = AffectEMAState.model_validate_json(json_str)

        assert reconstructed.person_id == ema.person_id
        assert reconstructed.v_fast == ema.v_fast
        assert reconstructed.v_slow == ema.v_slow


# =============================================================================
# BandingResult Tests
# =============================================================================


class TestBandingResult:
    """Tests for BandingResult model."""

    def test_valid_banding_result(self, valid_banding_result):
        """Test creation with valid data."""
        result = BandingResult(**valid_banding_result)
        assert result.band == PolicyBand.RED
        assert result.confidence == 0.85
        assert result.notify_guardian is True

    def test_rule_ids_pattern_validation(self, valid_banding_result):
        """Test rule_ids pattern validation."""
        # Valid rule IDs
        valid_banding_result["rule_ids"] = ["BLACK_RULE_1", "RED_RULE_5", "AMBER_RULE_3"]
        result = BandingResult(**valid_banding_result)
        assert len(result.rule_ids) == 3

        # Invalid rule IDs (should be filtered out)
        valid_banding_result["rule_ids"] = ["INVALID_RULE", "RED_RULE_1", "bad_format"]
        result = BandingResult(**valid_banding_result)
        assert len(result.rule_ids) == 1  # Only RED_RULE_1 is valid

    def test_reasons_min_length(self, valid_banding_result):
        """Test reasons requires at least 1 reason."""
        valid_banding_result["reasons"] = []
        with pytest.raises(ValidationError) as exc_info:
            BandingResult(**valid_banding_result)
        assert "reasons" in str(exc_info.value)

    def test_json_serialization_roundtrip(self, valid_banding_result):
        """Test JSON serialization/deserialization."""
        result = BandingResult(**valid_banding_result)
        json_str = result.model_dump_json()
        reconstructed = BandingResult.model_validate_json(json_str)

        assert reconstructed.band == result.band
        assert reconstructed.confidence == result.confidence
        assert reconstructed.notify_guardian == result.notify_guardian


# =============================================================================
# HouseholdAffectState Tests
# =============================================================================


class TestHouseholdAffectState:
    """Tests for HouseholdAffectState model (with nested models)."""

    def test_valid_household_state(self, valid_household_state):
        """Test creation with valid nested data."""
        state = HouseholdAffectState(**valid_household_state)
        assert state.space_id == "space_family_alpha"
        assert state.n_members == 4
        assert state.conflict_active is True
        assert state.aggregates.valence_mean == -0.2
        assert state.conflict_details.severity == 0.7

    def test_aggregates_validation(self, valid_household_state):
        """Test nested HouseholdAggregates validation."""
        # Invalid valence_mean (out of range)
        valid_household_state["aggregates"]["valence_mean"] = 1.5
        with pytest.raises(ValidationError):
            HouseholdAffectState(**valid_household_state)

        # Invalid arousal_std (negative)
        valid_household_state["aggregates"]["valence_mean"] = 0.0
        valid_household_state["aggregates"]["arousal_std"] = -0.1
        with pytest.raises(ValidationError):
            HouseholdAffectState(**valid_household_state)

    def test_conflict_details_validation(self, valid_household_state):
        """Test nested ConflictDetails validation."""
        # Invalid severity (out of range)
        valid_household_state["conflict_details"]["severity"] = 1.5
        with pytest.raises(ValidationError):
            HouseholdAffectState(**valid_household_state)

        # Invalid participants (< 2)
        valid_household_state["conflict_details"]["severity"] = 0.7
        valid_household_state["conflict_details"]["participants"] = 1
        with pytest.raises(ValidationError):
            HouseholdAffectState(**valid_household_state)

    def test_optional_nested_models(self, valid_household_state):
        """Test optional nested models (conflict_details, family_moment_details)."""
        # Remove optional fields
        del valid_household_state["conflict_details"]
        state = HouseholdAffectState(**valid_household_state)
        assert state.conflict_details is None

    def test_json_serialization_roundtrip(self, valid_household_state):
        """Test JSON serialization with nested models."""
        state = HouseholdAffectState(**valid_household_state)
        json_str = state.model_dump_json()
        reconstructed = HouseholdAffectState.model_validate_json(json_str)

        assert reconstructed.space_id == state.space_id
        assert reconstructed.aggregates.valence_mean == state.aggregates.valence_mean
        assert reconstructed.conflict_details.severity == state.conflict_details.severity


# =============================================================================
# AffectSummary Tests
# =============================================================================


class TestAffectSummary:
    """Tests for AffectSummary model (K1 bridge)."""

    def test_valid_affect_summary(self):
        """Test creation with valid data."""
        summary = AffectSummary(
            person_id="person_123",
            space_id="space_test",
            valence=-0.4,
            arousal=0.7,
            band=PolicyBand.RED,
            mood_label=MoodLabel.STRESSED,
            trend=Trend.DECLINING,
            behavior_modes=[BehaviorMode.SLOW, BehaviorMode.GENTLE],
        )
        assert summary.mood_label == MoodLabel.STRESSED
        assert summary.trend == Trend.DECLINING
        assert len(summary.behavior_modes) == 2

    def test_enum_validation(self):
        """Test enum validation for mood_label, trend, behavior_modes."""
        with pytest.raises(ValidationError):
            AffectSummary(
                person_id="person_123",
                space_id="space_test",
                valence=0.0,
                arousal=0.5,
                band=PolicyBand.GREEN,
                mood_label="invalid_mood",  # Invalid
                trend=Trend.STABLE,
            )

    def test_behavior_modes_list(self):
        """Test behavior_modes list validation."""
        summary = AffectSummary(
            person_id="person_123",
            space_id="space_test",
            valence=0.0,
            arousal=0.5,
            band=PolicyBand.GREEN,
            mood_label=MoodLabel.CALM,
            trend=Trend.STABLE,
            behavior_modes=[BehaviorMode.SLOW, BehaviorMode.GENTLE, BehaviorMode.QUIET],
        )
        assert len(summary.behavior_modes) == 3

    def test_json_serialization_roundtrip(self):
        """Test JSON serialization with enums."""
        summary = AffectSummary(
            person_id="person_123",
            space_id="space_test",
            valence=-0.4,
            arousal=0.7,
            band=PolicyBand.RED,
            mood_label=MoodLabel.STRESSED,
            trend=Trend.DECLINING,
            behavior_modes=[BehaviorMode.SLOW],
        )
        json_str = summary.model_dump_json()
        reconstructed = AffectSummary.model_validate_json(json_str)

        assert reconstructed.mood_label == summary.mood_label
        assert reconstructed.trend == summary.trend
        assert reconstructed.behavior_modes == summary.behavior_modes


# =============================================================================
# Counterfactual Models Tests
# =============================================================================


class TestCounterfactualModels:
    """Tests for CounterfactualInput and CounterfactualResult."""

    def test_valid_counterfactual_input(self):
        """Test creation of CounterfactualInput."""
        input_data = CounterfactualInput(
            action_type=ActionType.SHARE,
            content=CounterfactualContent(
                text="Memory content...",
                content_affect={"valence": -0.5, "arousal": 0.6},
            ),
            recipients=["person_123", "person_456"],
            current_affect_states={
                "person_123": {"valence": -0.3, "arousal": 0.7, "band": "AMBER"},
                "person_456": {"valence": 0.2, "arousal": 0.4, "band": "GREEN"},
            },
        )
        assert input_data.action_type == ActionType.SHARE
        assert len(input_data.recipients) == 2

    def test_valid_counterfactual_result(self):
        """Test creation of CounterfactualResult."""
        result = CounterfactualResult(
            action_type=ActionType.SHARE,
            overall_safe=False,
            recipient_impacts={
                "person_123": RecipientImpact(
                    predicted_valence_delta=-0.2,
                    predicted_arousal_delta=0.1,
                    predicted_band=PolicyBand.RED,
                    safe=False,
                    violated_rules=[SafetyRule.PUSH_INTO_RED],
                    confidence=0.8,
                )
            },
            blocked_recipients=["person_123"],
            allowed_recipients=["person_456"],
            recommendation=Recommendation.PROCEED_PARTIAL,
            explanation="Blocked for person_123",
        )
        assert result.overall_safe is False
        assert result.recommendation == Recommendation.PROCEED_PARTIAL
        assert len(result.blocked_recipients) == 1

    def test_recipient_impact_validation(self):
        """Test RecipientImpact nested model validation."""
        # Valid deltas
        impact = RecipientImpact(
            predicted_valence_delta=-0.5,
            predicted_arousal_delta=0.2,
            predicted_band=PolicyBand.RED,
            safe=False,
            confidence=0.9,
        )
        assert impact.predicted_valence_delta == -0.5

        # Invalid delta (out of range)
        with pytest.raises(ValidationError):
            RecipientImpact(
                predicted_valence_delta=3.0,  # Out of range [-2, 2]
                predicted_arousal_delta=0.2,
                predicted_band=PolicyBand.RED,
                safe=False,
                confidence=0.9,
            )

    def test_json_serialization_roundtrip(self):
        """Test JSON serialization for counterfactual models."""
        input_data = CounterfactualInput(
            action_type=ActionType.NOTIFY,
            content=CounterfactualContent(
                text="Test content",
                content_affect={"valence": 0.3, "arousal": 0.4},
            ),
            recipients=["person_123"],
            current_affect_states={"person_123": {"valence": 0.1, "arousal": 0.3, "band": "GREEN"}},
        )
        json_str = input_data.model_dump_json()
        reconstructed = CounterfactualInput.model_validate_json(json_str)

        assert reconstructed.action_type == input_data.action_type
        assert len(reconstructed.recipients) == 1


# =============================================================================
# Additional Models Tests (Relationship, LifecycleContext)
# =============================================================================


class TestRelationship:
    """Tests for Relationship model."""

    def test_valid_relationship(self):
        """Test creation with valid data."""
        rel = Relationship(
            person_a="person_123",
            person_b="person_456",
            relationship_type="parent-child",
            direction="a→b",
            strength=1.0,
        )
        assert rel.relationship_type == "parent-child"
        assert rel.strength == 1.0

    def test_relationship_type_validation(self):
        """Test relationship_type pattern validation."""
        # Valid types
        for rel_type in [
            "parent-child",
            "partner",
            "sibling",
            "friend",
            "caregiver-dependent",
            "extended-family",
        ]:
            rel = Relationship(
                person_a="person_123",
                person_b="person_456",
                relationship_type=rel_type,
            )
            assert rel.relationship_type == rel_type

        # Invalid type
        with pytest.raises(ValidationError):
            Relationship(
                person_a="person_123",
                person_b="person_456",
                relationship_type="invalid-type",
            )


class TestLifecycleContext:
    """Tests for LifecycleContext model."""

    def test_valid_lifecycle_context(self):
        """Test creation with valid data."""
        context = LifecycleContext(
            time_of_day="morning",
            day_of_week="monday",
            is_weekend=False,
            is_school_hours=True,
            is_bedtime=False,
        )
        assert context.time_of_day == "morning"
        assert context.is_school_hours is True

    def test_time_of_day_validation(self):
        """Test time_of_day pattern validation."""
        # Valid times
        for time_period in ["morning", "afternoon", "evening", "night"]:
            context = LifecycleContext(
                time_of_day=time_period,
                day_of_week="monday",
                is_weekend=False,
            )
            assert context.time_of_day == time_period

        # Invalid time
        with pytest.raises(ValidationError):
            LifecycleContext(
                time_of_day="invalid_time",
                day_of_week="monday",
                is_weekend=False,
            )


# =============================================================================
# Schema Export Tests
# =============================================================================


class TestSchemaExport:
    """Test JSON schema export for all models."""

    def test_affect_annotation_schema_export(self):
        """Test AffectAnnotation JSON schema export."""
        schema = AffectAnnotation.model_json_schema()
        assert "properties" in schema
        assert "valence" in schema["properties"]
        assert "arousal" in schema["properties"]
        assert schema["properties"]["valence"]["minimum"] == -1.0
        assert schema["properties"]["valence"]["maximum"] == 1.0

    def test_all_models_schema_export(self):
        """Test that all models can export JSON schema."""
        models = [
            AffectAnnotation,
            AffectEMAState,
            BandingResult,
            HouseholdAffectState,
            AffectSummary,
            CounterfactualInput,
            CounterfactualResult,
            Relationship,
            LifecycleContext,
        ]

        for model in models:
            schema = model.model_json_schema()
            assert "properties" in schema
            assert "$defs" in schema or "properties" in schema  # Has definitions or properties
