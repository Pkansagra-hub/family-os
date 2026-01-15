"""
Tests for R4 Adaptive Causality Thresholds.

Issue: 4.4.10 - Implement adaptive causality thresholds by category

Spec Reference:
    - Dossier §4.5.4.1: Adaptive Causality Thresholds
    - M4_EXECUTION.md Issue 4.4.10

Test Cases (from M4_EXECUTION.md):
    1. test_classify_health_medical — "medication" → Health/Medical
    2. test_classify_financial — "budget" → Financial
    3. test_classify_social — "meeting" → Social/Routine
    4. test_classify_default_preference — Unknown → Preference/Habit
    5. test_health_high_threshold — 0.85 default
    6. test_should_create_above_threshold — 0.90 Health → True
    7. test_should_create_below_threshold — 0.80 Health → False
    8. test_adjust_wrong_prediction — +0.02 adjustment
    9. test_adjust_user_rejects — +0.05 adjustment
    10. test_adjust_missed_causation — -0.03 adjustment
    11. test_threshold_clamped_max — Cannot exceed category max
    12. test_persist_and_load — Round-trip to database

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

from typing import Dict, List

import pytest

from k0.modules.consolidation.algorithms.causality_thresholds import (
    CATEGORY_KEYWORDS,
    AdaptiveCausalityThresholds,
    CategoryThresholdBounds,
    CausalCategoryClassifier,
    CausalityCategory,
    generate_ulid,
    now_ms,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def classifier() -> CausalCategoryClassifier:
    """Category classifier instance."""
    return CausalCategoryClassifier()


@pytest.fixture
def thresholds() -> AdaptiveCausalityThresholds:
    """Adaptive thresholds instance with defaults."""
    return AdaptiveCausalityThresholds()


# =============================================================================
# Mock Database Connection
# =============================================================================


class MockDatabaseConnection:
    """Mock database connection for testing."""

    def __init__(self):
        self.weights: Dict[str, Dict] = {}
        self.queries_executed: List[str] = []

    async def execute(self, query: str, *args) -> None:
        """Execute query."""
        self.queries_executed.append(query)
        if "INSERT INTO st_learned_weights" in query and len(args) >= 4:
            param_id = args[0]
            param_key = args[1]
            value = args[2]
            self.weights[param_key] = {
                "param_id": param_id,
                "param_key": param_key,
                "current_value": value,
            }

    async def fetch(self, query: str, *args) -> List[Dict]:
        """Fetch multiple rows."""
        self.queries_executed.append(query)
        if "SELECT param_key, current_value FROM st_learned_weights" in query:
            return [
                {"param_key": k, "current_value": v["current_value"]}
                for k, v in self.weights.items()
                if k.startswith("causality_threshold_")
            ]
        return []


# =============================================================================
# Test: CausalCategoryClassifier
# =============================================================================


class TestCausalCategoryClassifier:
    """Tests for category classification."""

    def test_classify_health_medical(self, classifier: CausalCategoryClassifier):
        """
        Test Case 1: 'medication' → Health/Medical.
        """
        result = classifier.classify("medication", "symptom_relief", "causal")
        assert result == CausalityCategory.HEALTH_MEDICAL

    def test_classify_health_doctor(self, classifier: CausalCategoryClassifier):
        """Health keyword 'doctor' should classify as Health/Medical."""
        result = classifier.classify("doctor_visit", "diagnosis", "causal")
        assert result == CausalityCategory.HEALTH_MEDICAL

    def test_classify_health_exercise(self, classifier: CausalCategoryClassifier):
        """Health keyword 'exercise' should classify as Health/Medical."""
        result = classifier.classify("exercise", "good_mood", "causal")
        assert result == CausalityCategory.HEALTH_MEDICAL

    def test_classify_financial(self, classifier: CausalCategoryClassifier):
        """
        Test Case 2: 'budget' → Financial.
        """
        result = classifier.classify("budget", "stress", "causal")
        assert result == CausalityCategory.FINANCIAL

    def test_classify_financial_spending(self, classifier: CausalCategoryClassifier):
        """Financial keyword 'spending' should classify as Financial."""
        result = classifier.classify("spending", "budget_overrun", "causal")
        assert result == CausalityCategory.FINANCIAL

    def test_classify_financial_payment(self, classifier: CausalCategoryClassifier):
        """Financial keyword 'payment' should classify as Financial."""
        result = classifier.classify("payment_due", "anxiety", "causal")
        assert result == CausalityCategory.FINANCIAL

    def test_classify_social(self, classifier: CausalCategoryClassifier):
        """
        Test Case 3: 'meeting' → Social/Routine.
        """
        result = classifier.classify("meeting", "productivity", "causal")
        assert result == CausalityCategory.SOCIAL_ROUTINE

    def test_classify_social_family(self, classifier: CausalCategoryClassifier):
        """Social keyword 'family' should classify as Social/Routine."""
        result = classifier.classify("family_dinner", "happiness", "causal")
        assert result == CausalityCategory.SOCIAL_ROUTINE

    def test_classify_social_call(self, classifier: CausalCategoryClassifier):
        """Social keyword 'call' should classify as Social/Routine."""
        result = classifier.classify("call_mom", "feel_connected", "causal")
        assert result == CausalityCategory.SOCIAL_ROUTINE

    def test_classify_default_preference(self, classifier: CausalCategoryClassifier):
        """
        Test Case 4: Unknown → Preference/Habit.
        """
        result = classifier.classify("coffee", "work_start", "causal")
        assert result == CausalityCategory.PREFERENCE_HABIT

    def test_classify_default_generic(self, classifier: CausalCategoryClassifier):
        """Generic entities should default to Preference/Habit."""
        result = classifier.classify("alarm", "wakeup", "causal")
        assert result == CausalityCategory.PREFERENCE_HABIT

    def test_classify_priority_health_over_social(self, classifier: CausalCategoryClassifier):
        """Health keywords take priority over social keywords."""
        # "therapy" is health, "family" is social - health should win
        result = classifier.classify("family_therapy", "relationship", "causal")
        assert result == CausalityCategory.HEALTH_MEDICAL

    def test_classify_priority_financial_over_social(self, classifier: CausalCategoryClassifier):
        """Financial keywords take priority over social keywords."""
        # "payment" is financial, "family" is social
        result = classifier.classify("family_payment", "budget", "causal")
        assert result == CausalityCategory.FINANCIAL


# =============================================================================
# Test: AdaptiveCausalityThresholds - Default Values
# =============================================================================


class TestThresholdDefaults:
    """Tests for default threshold values."""

    def test_health_high_threshold(self, thresholds: AdaptiveCausalityThresholds):
        """
        Test Case 5: Health/Medical default is 0.85.
        """
        threshold = thresholds.get_threshold(CausalityCategory.HEALTH_MEDICAL)
        assert threshold == 0.85

    def test_financial_threshold(self, thresholds: AdaptiveCausalityThresholds):
        """Financial default threshold is 0.80."""
        threshold = thresholds.get_threshold(CausalityCategory.FINANCIAL)
        assert threshold == 0.80

    def test_social_threshold(self, thresholds: AdaptiveCausalityThresholds):
        """Social/Routine default threshold is 0.70."""
        threshold = thresholds.get_threshold(CausalityCategory.SOCIAL_ROUTINE)
        assert threshold == 0.70

    def test_preference_threshold(self, thresholds: AdaptiveCausalityThresholds):
        """Preference/Habit default threshold is 0.65."""
        threshold = thresholds.get_threshold(CausalityCategory.PREFERENCE_HABIT)
        assert threshold == 0.65

    def test_get_all_thresholds(self, thresholds: AdaptiveCausalityThresholds):
        """get_all_thresholds returns all four categories."""
        all_thresholds = thresholds.get_all_thresholds()
        assert len(all_thresholds) == 4
        assert all_thresholds[CausalityCategory.HEALTH_MEDICAL] == 0.85
        assert all_thresholds[CausalityCategory.FINANCIAL] == 0.80
        assert all_thresholds[CausalityCategory.SOCIAL_ROUTINE] == 0.70
        assert all_thresholds[CausalityCategory.PREFERENCE_HABIT] == 0.65


# =============================================================================
# Test: should_create_causal_edge
# =============================================================================


class TestShouldCreateCausalEdge:
    """Tests for should_create_causal_edge decision logic."""

    def test_should_create_above_threshold(self, thresholds: AdaptiveCausalityThresholds):
        """
        Test Case 6: 0.90 Health → True.

        Precedence ratio above category threshold creates edge.
        """
        should_create, confidence, category = thresholds.should_create_causal_edge(
            source_entity_name="medication_a",
            target_entity_name="symptom_relief",
            precedence_ratio=0.90,
        )

        assert should_create is True
        assert category == CausalityCategory.HEALTH_MEDICAL
        assert confidence > 0.70

    def test_should_create_below_threshold(self, thresholds: AdaptiveCausalityThresholds):
        """
        Test Case 7: 0.80 Health → False.

        Precedence ratio below category threshold (0.85) rejects edge.
        """
        should_create, confidence, category = thresholds.should_create_causal_edge(
            source_entity_name="medication_a",
            target_entity_name="symptom_relief",
            precedence_ratio=0.80,
        )

        assert should_create is False
        assert category == CausalityCategory.HEALTH_MEDICAL
        assert confidence == 0.0

    def test_should_create_exactly_at_threshold(self, thresholds: AdaptiveCausalityThresholds):
        """Exactly at threshold should create edge."""
        should_create, confidence, category = thresholds.should_create_causal_edge(
            source_entity_name="medication_a",
            target_entity_name="symptom_relief",
            precedence_ratio=0.85,  # Exactly at Health threshold
        )

        assert should_create is True
        assert category == CausalityCategory.HEALTH_MEDICAL

    def test_should_create_social_lower_threshold(self, thresholds: AdaptiveCausalityThresholds):
        """Social category has lower threshold (0.70)."""
        # 0.75 would fail Health (0.85) but pass Social (0.70)
        should_create, confidence, category = thresholds.should_create_causal_edge(
            source_entity_name="meeting",
            target_entity_name="productivity",
            precedence_ratio=0.75,
        )

        assert should_create is True
        assert category == CausalityCategory.SOCIAL_ROUTINE

    def test_should_create_preference_lowest_threshold(
        self, thresholds: AdaptiveCausalityThresholds
    ):
        """Preference/Habit has lowest threshold (0.65)."""
        should_create, confidence, category = thresholds.should_create_causal_edge(
            source_entity_name="coffee",
            target_entity_name="work_start",
            precedence_ratio=0.68,
        )

        assert should_create is True
        assert category == CausalityCategory.PREFERENCE_HABIT


# =============================================================================
# Test: adjust_threshold
# =============================================================================


class TestAdjustThreshold:
    """Tests for threshold adjustment based on feedback."""

    def test_adjust_wrong_prediction(self, thresholds: AdaptiveCausalityThresholds):
        """
        Test Case 8: CAUSAL_PREDICTION_WRONG adds +0.02.
        """
        new_threshold = thresholds.adjust_threshold(
            CausalityCategory.HEALTH_MEDICAL,
            "CAUSAL_PREDICTION_WRONG",
        )

        # 0.85 + 0.02 = 0.87
        assert new_threshold == 0.87

    def test_adjust_user_rejects(self, thresholds: AdaptiveCausalityThresholds):
        """
        Test Case 9: USER_REJECTS_CAUSATION adds +0.05.
        """
        new_threshold = thresholds.adjust_threshold(
            CausalityCategory.HEALTH_MEDICAL,
            "USER_REJECTS_CAUSATION",
        )

        # 0.85 + 0.05 = 0.90
        assert new_threshold == 0.90

    def test_adjust_missed_causation(self, thresholds: AdaptiveCausalityThresholds):
        """
        Test Case 10: MISSED_CAUSATION subtracts -0.03.
        """
        new_threshold = thresholds.adjust_threshold(
            CausalityCategory.HEALTH_MEDICAL,
            "MISSED_CAUSATION",
        )

        # 0.85 - 0.03 = 0.82
        assert new_threshold == 0.82

    def test_adjust_confirmed_no_change(self, thresholds: AdaptiveCausalityThresholds):
        """CAUSAL_PREDICTION_CONFIRMED makes no change."""
        new_threshold = thresholds.adjust_threshold(
            CausalityCategory.HEALTH_MEDICAL,
            "CAUSAL_PREDICTION_CONFIRMED",
        )

        # No change: 0.85
        assert new_threshold == 0.85

    def test_adjust_unknown_signal_no_change(self, thresholds: AdaptiveCausalityThresholds):
        """Unknown signal makes no change."""
        new_threshold = thresholds.adjust_threshold(
            CausalityCategory.HEALTH_MEDICAL,
            "UNKNOWN_SIGNAL",
        )

        # No change: 0.85
        assert new_threshold == 0.85


# =============================================================================
# Test: Threshold Clamping
# =============================================================================


class TestThresholdClamping:
    """Tests for threshold clamping to bounds."""

    def test_threshold_clamped_max(self, thresholds: AdaptiveCausalityThresholds):
        """
        Test Case 11: Cannot exceed category max.

        Health/Medical max is 0.95.
        """
        # First adjustment: 0.85 + 0.05 = 0.90
        thresholds.adjust_threshold(CausalityCategory.HEALTH_MEDICAL, "USER_REJECTS_CAUSATION")
        # Second adjustment: 0.90 + 0.05 = 0.95 (at max)
        thresholds.adjust_threshold(CausalityCategory.HEALTH_MEDICAL, "USER_REJECTS_CAUSATION")
        # Third adjustment: 0.95 + 0.05 = 1.00 → clamped to 0.95
        new_threshold = thresholds.adjust_threshold(
            CausalityCategory.HEALTH_MEDICAL, "USER_REJECTS_CAUSATION"
        )

        assert new_threshold == 0.95  # Max for Health/Medical

    def test_threshold_clamped_min(self, thresholds: AdaptiveCausalityThresholds):
        """Cannot go below category min."""
        # Health/Medical min is 0.80
        # 0.85 - 0.03 = 0.82
        thresholds.adjust_threshold(CausalityCategory.HEALTH_MEDICAL, "MISSED_CAUSATION")
        # 0.82 - 0.03 = 0.79 → clamped to 0.80
        new_threshold = thresholds.adjust_threshold(
            CausalityCategory.HEALTH_MEDICAL, "MISSED_CAUSATION"
        )

        assert new_threshold == 0.80  # Min for Health/Medical

    def test_preference_clamped_to_bounds(self, thresholds: AdaptiveCausalityThresholds):
        """Preference/Habit clamped to [0.55, 0.75]."""
        # Keep lowering until we hit min
        for _ in range(10):
            new_threshold = thresholds.adjust_threshold(
                CausalityCategory.PREFERENCE_HABIT, "MISSED_CAUSATION"
            )

        assert new_threshold == 0.55  # Min for Preference/Habit


# =============================================================================
# Test: Persistence and Loading
# =============================================================================


class TestPersistAndLoad:
    """Tests for database persistence."""

    @pytest.mark.asyncio
    async def test_persist_and_load(self):
        """
        Test Case 12: Round-trip to database.
        """
        db = MockDatabaseConnection()

        # Create thresholds and adjust
        thresholds = AdaptiveCausalityThresholds()
        thresholds.adjust_threshold(
            CausalityCategory.HEALTH_MEDICAL, "USER_REJECTS_CAUSATION"
        )  # 0.90
        thresholds.adjust_threshold(CausalityCategory.FINANCIAL, "MISSED_CAUSATION")  # 0.77

        # Persist
        await thresholds.persist_threshold(CausalityCategory.HEALTH_MEDICAL, db)
        await thresholds.persist_threshold(CausalityCategory.FINANCIAL, db)

        # Load
        loaded = await AdaptiveCausalityThresholds.load_from_database(db)

        # Verify
        assert loaded.get_threshold(CausalityCategory.HEALTH_MEDICAL) == 0.90
        assert loaded.get_threshold(CausalityCategory.FINANCIAL) == 0.77

    @pytest.mark.asyncio
    async def test_persist_only_modified(self):
        """Only persist thresholds that have been modified."""
        db = MockDatabaseConnection()

        thresholds = AdaptiveCausalityThresholds()
        # Don't adjust - no learned values

        # Persist should do nothing
        await thresholds.persist_threshold(CausalityCategory.HEALTH_MEDICAL, db)

        # No weights stored
        assert len(db.weights) == 0

    @pytest.mark.asyncio
    async def test_load_empty_uses_defaults(self):
        """Loading with no stored values uses defaults."""
        db = MockDatabaseConnection()

        loaded = await AdaptiveCausalityThresholds.load_from_database(db)

        # Should have default values
        assert loaded.get_threshold(CausalityCategory.HEALTH_MEDICAL) == 0.85
        assert loaded.get_threshold(CausalityCategory.FINANCIAL) == 0.80


# =============================================================================
# Test: Learned Threshold Override
# =============================================================================


class TestLearnedThresholdOverride:
    """Tests for learned threshold taking precedence."""

    def test_learned_overrides_default(self):
        """Learned threshold overrides default."""
        learned = {"causality_threshold_Health_Medical": 0.92}
        thresholds = AdaptiveCausalityThresholds(learned_thresholds=learned)

        assert thresholds.get_threshold(CausalityCategory.HEALTH_MEDICAL) == 0.92

    def test_adjustment_stores_learned(self, thresholds: AdaptiveCausalityThresholds):
        """Adjustment stores learned value."""
        thresholds.adjust_threshold(CausalityCategory.FINANCIAL, "CAUSAL_PREDICTION_WRONG")

        # Now the learned value should be used (0.80 + 0.02 = 0.82)
        result = thresholds.get_threshold(CausalityCategory.FINANCIAL)
        assert abs(result - 0.82) < 1e-9


# =============================================================================
# Test: CategoryThresholdBounds
# =============================================================================


class TestCategoryThresholdBounds:
    """Tests for CategoryThresholdBounds dataclass."""

    def test_valid_bounds(self):
        """Valid bounds should not raise."""
        bounds = CategoryThresholdBounds(0.80, 0.70, 0.90)
        bounds.validate()  # Should not raise

    def test_invalid_min_greater_than_max(self):
        """Min > max should raise."""
        bounds = CategoryThresholdBounds(0.80, 0.90, 0.70)
        with pytest.raises(ValueError, match="Invalid bounds"):
            bounds.validate()

    def test_invalid_default_outside_bounds(self):
        """Default outside bounds should raise."""
        bounds = CategoryThresholdBounds(0.60, 0.70, 0.90)  # 0.60 < 0.70
        with pytest.raises(ValueError, match="Default"):
            bounds.validate()


# =============================================================================
# Test: Utility Functions
# =============================================================================


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_generate_ulid_uniqueness(self):
        """Generated ULIDs should be unique."""
        ulids = [generate_ulid() for _ in range(100)]
        assert len(set(ulids)) == 100

    def test_generate_ulid_format(self):
        """Generated ULID should be 26 characters."""
        ulid = generate_ulid()
        assert len(ulid) == 26

    def test_now_ms(self):
        """now_ms should return current time in milliseconds."""
        import time

        before = int(time.time() * 1000)
        result = now_ms()
        after = int(time.time() * 1000)

        assert before <= result <= after


# =============================================================================
# Test: Category Keywords
# =============================================================================


class TestCategoryKeywords:
    """Tests for category keyword sets."""

    def test_health_keywords_exist(self):
        """Health keywords should be populated."""
        assert len(CATEGORY_KEYWORDS[CausalityCategory.HEALTH_MEDICAL]) >= 15
        assert "medication" in CATEGORY_KEYWORDS[CausalityCategory.HEALTH_MEDICAL]
        assert "doctor" in CATEGORY_KEYWORDS[CausalityCategory.HEALTH_MEDICAL]

    def test_financial_keywords_exist(self):
        """Financial keywords should be populated."""
        assert len(CATEGORY_KEYWORDS[CausalityCategory.FINANCIAL]) >= 15
        assert "budget" in CATEGORY_KEYWORDS[CausalityCategory.FINANCIAL]
        assert "spending" in CATEGORY_KEYWORDS[CausalityCategory.FINANCIAL]

    def test_social_keywords_exist(self):
        """Social keywords should be populated."""
        assert len(CATEGORY_KEYWORDS[CausalityCategory.SOCIAL_ROUTINE]) >= 15
        assert "meeting" in CATEGORY_KEYWORDS[CausalityCategory.SOCIAL_ROUTINE]
        assert "family" in CATEGORY_KEYWORDS[CausalityCategory.SOCIAL_ROUTINE]
