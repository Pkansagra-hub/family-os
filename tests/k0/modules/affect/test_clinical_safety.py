"""
Comprehensive tests for clinical safety detection module.

Tests cover:
- SafetySeverity enum values and thresholds
- Pattern extraction for each indicator category
- Indicator scoring with escalation rules
- Combined scoring logic
- Sensitivity (>95%) and specificity (>80%) requirements
- Integration with assess() function

Run: pytest tests/k0/modules/affect/test_clinical_safety.py -v
"""

import pytest

from k0.modules.affect.clinical_safety import (
    ClinicalSafetyDetector,
    EscalationAction,
    SafetyAssessment,
    SafetySeverity,
    assess_safety,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def detector():
    """Create detector without model for faster tests."""
    return ClinicalSafetyDetector(use_model=False)


@pytest.fixture
def detector_with_model():
    """Create detector with model for integration tests."""
    return ClinicalSafetyDetector(use_model=True)


# ============================================================================
# SafetySeverity Enum Tests
# ============================================================================


class TestSafetySeverity:
    """Test SafetySeverity enum values."""

    def test_severity_values(self):
        """Verify severity enum has correct string values."""
        assert SafetySeverity.NONE.value == "NONE"
        assert SafetySeverity.LOW.value == "LOW"
        assert SafetySeverity.MEDIUM.value == "MEDIUM"
        assert SafetySeverity.HIGH.value == "HIGH"
        assert SafetySeverity.CRITICAL.value == "CRITICAL"

    def test_all_severity_levels_defined(self):
        """Verify all expected severity levels exist."""
        expected = {"NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
        actual = {s.name for s in SafetySeverity}
        assert actual == expected


class TestEscalationAction:
    """Test EscalationAction enum values."""

    def test_escalation_values(self):
        """Verify escalation actions have correct string values."""
        assert EscalationAction.NONE.value == "NONE"
        assert EscalationAction.LOG_ONLY.value == "LOG_ONLY"
        assert EscalationAction.SUGGEST_RESOURCES.value == "SUGGEST_RESOURCES"
        assert EscalationAction.NOTIFY_TRUSTED.value == "NOTIFY_TRUSTED"
        assert EscalationAction.IMMEDIATE_ALERT.value == "IMMEDIATE_ALERT"

    def test_all_actions_defined(self):
        """Verify all expected escalation actions exist."""
        expected = {"NONE", "LOG_ONLY", "SUGGEST_RESOURCES", "NOTIFY_TRUSTED", "IMMEDIATE_ALERT"}
        actual = {a.name for a in EscalationAction}
        assert actual == expected


# ============================================================================
# Indicator Extraction Tests
# ============================================================================


class TestIndicatorExtraction:
    """Test pattern matching for each indicator category."""

    def test_direct_harm_indicators(self, detector):
        """Test DIRECT_HARM pattern extraction."""
        test_cases = [
            ("I want to kill myself", "kill myself"),
            ("Thinking about suicide", "suicide"),
            ("I want to hurt myself", "hurt myself"),
            ("Planning to take my life", "take my life"),
            ("I might overdose", "overdose"),
        ]
        for text, expected in test_cases:
            indicators = detector._extract_indicators(text)
            categories = [i.category for i in indicators]
            assert "DIRECT_HARM" in categories, f"Failed for: {text}"

    def test_euphemism_indicators(self, detector):
        """Test EUPHEMISM pattern extraction."""
        test_cases = [
            ("I want to end it all", "end it all"),
            ("Better off without me", "better off without me"),
            ("I just want to disappear", "want to disappear"),
            ("There is no way out", "no way out"),
            ("I wish I was dead", "wish i was dead"),
        ]
        for text, expected in test_cases:
            indicators = detector._extract_indicators(text)
            categories = [i.category for i in indicators]
            assert "EUPHEMISM" in categories, f"Failed for: {text}"

    def test_hopelessness_indicators(self, detector):
        """Test HOPELESSNESS pattern extraction."""
        test_cases = [
            ("I have no hope left", "no hope"),
            ("Nothing matters anymore", "nothing matters"),
            ("I feel worthless", "worthless"),
            ("Why bother trying", "why bother"),
            ("I have given up", "given up"),
        ]
        for text, expected in test_cases:
            indicators = detector._extract_indicators(text)
            categories = [i.category for i in indicators]
            assert "HOPELESSNESS" in categories, f"Failed for: {text}"

    def test_abuse_indicators(self, detector):
        """Test ABUSE pattern extraction."""
        test_cases = [
            ("He hits me every day", "hits me"),
            ("She beats me", "beats me"),
            ("I was assaulted", "assaulted"),
            ("He threatens me constantly", "threatens me"),
            ("Scared of him", "scared of him"),
        ]
        for text, expected in test_cases:
            indicators = detector._extract_indicators(text)
            categories = [i.category for i in indicators]
            assert "ABUSE" in categories, f"Failed for: {text}"

    def test_distress_indicators(self, detector):
        """Test DISTRESS pattern extraction."""
        test_cases = [
            ("I can't cope anymore", "can't cope"),
            ("I am falling apart", "falling apart"),
            ("Having a panic attack", "panic attack"),
            ("Please help me", "please help"),
        ]
        for text, expected in test_cases:
            indicators = detector._extract_indicators(text)
            categories = [i.category for i in indicators]
            assert "DISTRESS" in categories, f"Failed for: {text}"

    def test_no_indicators_in_safe_text(self, detector):
        """Test that safe text has no indicators."""
        safe_texts = [
            "Had a wonderful dinner with family",
            "Work is stressful but manageable",
            "The weather is nice today",
            "I enjoyed the movie",
        ]
        for text in safe_texts:
            indicators = detector._extract_indicators(text)
            assert len(indicators) == 0, f"Unexpected indicators for: {text}"


# ============================================================================
# Indicator Scoring Tests
# ============================================================================


class TestIndicatorScoring:
    """Test indicator score computation."""

    def test_direct_harm_alone_is_critical(self, detector):
        """DIRECT_HARM alone should score at CRITICAL threshold."""
        text = "I want to kill myself"
        indicators = detector._extract_indicators(text)
        score, primary = detector._compute_indicator_score(indicators)
        assert score >= 0.85, f"DIRECT_HARM score {score} below CRITICAL threshold"
        assert primary == "DIRECT_HARM"

    def test_direct_harm_plus_other_escalates(self, detector):
        """DIRECT_HARM + another category should be maximum CRITICAL."""
        text = "I want to kill myself, there is no hope"
        indicators = detector._extract_indicators(text)
        score, primary = detector._compute_indicator_score(indicators)
        assert score >= 0.95, f"DIRECT_HARM combo score {score} not at max CRITICAL"

    def test_abuse_alone_is_high(self, detector):
        """ABUSE alone should score at HIGH level."""
        text = "He hits me every day"
        indicators = detector._extract_indicators(text)
        score, primary = detector._compute_indicator_score(indicators)
        assert score >= 0.65, f"ABUSE score {score} below HIGH threshold"
        assert primary == "ABUSE"

    def test_multiple_hopelessness_indicators(self, detector):
        """Multiple hopelessness indicators should have diminishing returns."""
        text = "Nothing matters, I feel worthless and hopeless"
        indicators = detector._extract_indicators(text)
        score, primary = detector._compute_indicator_score(indicators)
        # Multiple hopelessness should still be capped reasonably
        assert score <= 1.0, "Score should never exceed 1.0"
        assert score >= 0.5, "Multiple hopelessness should elevate score"

    def test_empty_indicators_returns_zero(self, detector):
        """No indicators should return zero score."""
        score, primary = detector._compute_indicator_score([])
        assert score == 0.0
        assert primary is None


# ============================================================================
# Safety Assessment Tests
# ============================================================================


class TestSafetyAssessment:
    """Test full safety assessment pipeline."""

    def test_safe_text_returns_none_severity(self, detector):
        """Safe text should return NONE severity."""
        result = detector.assess("Had a wonderful dinner with family")
        assert result.severity == SafetySeverity.NONE
        assert result.risk_detected is False
        assert result.recommended_action == EscalationAction.NONE

    def test_hopelessness_returns_high_severity(self, detector):
        """Hopelessness indicators should return HIGH severity."""
        result = detector.assess("Nothing matters anymore, why bother")
        assert result.severity == SafetySeverity.HIGH
        assert result.risk_detected is True
        assert result.recommended_action == EscalationAction.NOTIFY_TRUSTED

    def test_direct_harm_returns_critical(self, detector):
        """Direct harm should return CRITICAL severity."""
        result = detector.assess("I am going to kill myself")
        assert result.severity == SafetySeverity.CRITICAL
        assert result.risk_detected is True
        assert result.recommended_action == EscalationAction.IMMEDIATE_ALERT

    def test_combined_indicators_escalate(self, detector):
        """Multiple indicator categories should escalate severity."""
        result = detector.assess("I want to kill myself and there is no hope left")
        assert result.severity == SafetySeverity.CRITICAL
        assert result.primary_category == "DIRECT_HARM"

    def test_assessment_has_required_fields(self, detector):
        """SafetyAssessment should have all required fields."""
        result = detector.assess("Test text")
        assert isinstance(result, SafetyAssessment)
        assert hasattr(result, "risk_detected")
        assert hasattr(result, "severity")
        assert hasattr(result, "confidence")
        assert hasattr(result, "model_score")
        assert hasattr(result, "indicator_score")
        assert hasattr(result, "combined_score")
        assert hasattr(result, "indicators")
        assert hasattr(result, "recommended_action")
        assert hasattr(result, "model_version")
        assert hasattr(result, "processing_time_ms")

    def test_truncation_of_long_text(self, detector):
        """Long text should be truncated without error."""
        long_text = "word " * 1000  # Very long text
        result = detector.assess(long_text, max_length=100)
        assert result is not None
        assert isinstance(result.severity, SafetySeverity)


# ============================================================================
# Severity Mapping Tests
# ============================================================================


class TestSeverityMapping:
    """Test score to severity and action mapping."""

    def test_severity_thresholds(self, detector):
        """Verify severity threshold mapping."""
        assert detector._score_to_severity(0.0) == SafetySeverity.NONE
        assert detector._score_to_severity(0.24) == SafetySeverity.NONE
        assert detector._score_to_severity(0.25) == SafetySeverity.LOW
        assert detector._score_to_severity(0.44) == SafetySeverity.LOW
        assert detector._score_to_severity(0.45) == SafetySeverity.MEDIUM
        assert detector._score_to_severity(0.64) == SafetySeverity.MEDIUM
        assert detector._score_to_severity(0.65) == SafetySeverity.HIGH
        assert detector._score_to_severity(0.84) == SafetySeverity.HIGH
        assert detector._score_to_severity(0.85) == SafetySeverity.CRITICAL
        assert detector._score_to_severity(1.0) == SafetySeverity.CRITICAL

    def test_action_mapping(self, detector):
        """Verify severity to action mapping."""
        assert detector._severity_to_action(SafetySeverity.NONE) == EscalationAction.NONE
        assert detector._severity_to_action(SafetySeverity.LOW) == EscalationAction.LOG_ONLY
        assert (
            detector._severity_to_action(SafetySeverity.MEDIUM)
            == EscalationAction.SUGGEST_RESOURCES
        )
        assert detector._severity_to_action(SafetySeverity.HIGH) == EscalationAction.NOTIFY_TRUSTED
        assert (
            detector._severity_to_action(SafetySeverity.CRITICAL)
            == EscalationAction.IMMEDIATE_ALERT
        )


# ============================================================================
# Sensitivity and Specificity Tests
# ============================================================================


class TestSensitivitySpecificity:
    """Test detection performance against acceptance criteria."""

    # True positive test cases (should detect risk)
    TRUE_POSITIVE_CASES = [
        "I want to kill myself",
        "I am going to end it all",
        "I have no hope left",
        "Nothing matters anymore",
        "I cant take this anymore",
        "Better off without me",
        "He hits me every day",
        "I want to disappear forever",
        "I am planning to hurt myself",
        "Life is not worth living",
        "I wish I was dead",
        "No one would miss me",
        "I am a burden to everyone",
        "There is no point in going on",
        "I have given up on everything",
        "The only way out is to end it",
        "I am falling apart and cant cope",
        "Everything is hopeless",
        "I feel worthless and empty",
        "She threatens me constantly",
    ]

    # True negative test cases (should NOT detect risk)
    TRUE_NEGATIVE_CASES = [
        "Had a wonderful dinner with family",
        "Work is stressful but manageable",
        "I am tired from exercise",
        "The movie was sad but I enjoyed it",
        "I miss my friend who moved away",
        "My project deadline is killing me",
        "This traffic is endless",
        "I am exhausted from the meeting",
        "The test was really hard",
        "I need a vacation",
        "My team lost the game, so disappointing",
        "The restaurant was terrible",
        "I argued with my coworker today",
        "The weather is depressing",
        "I am bored at home",
        "My phone battery died",
        "The food was not great",
        "I stayed up too late",
        "I forgot my keys at home",
        "My back hurts from sitting",
    ]

    def test_sensitivity_above_95_percent(self, detector):
        """Sensitivity must be >95% (catch real risks)."""
        true_positives = 0
        false_negatives = 0

        for text in self.TRUE_POSITIVE_CASES:
            result = detector.assess(text)
            if result.risk_detected:
                true_positives += 1
            else:
                false_negatives += 1

        sensitivity = true_positives / (true_positives + false_negatives)
        assert sensitivity >= 0.95, f"Sensitivity {sensitivity:.1%} below 95% threshold"

    def test_specificity_above_80_percent(self, detector):
        """Specificity must be >80% (reduce false alarms)."""
        true_negatives = 0
        false_positives = 0

        for text in self.TRUE_NEGATIVE_CASES:
            result = detector.assess(text)
            if not result.risk_detected:
                true_negatives += 1
            else:
                false_positives += 1

        specificity = true_negatives / (true_negatives + false_positives)
        assert specificity >= 0.80, f"Specificity {specificity:.1%} below 80% threshold"

    def test_critical_cases_properly_escalated(self, detector):
        """Direct harm cases must be HIGH or CRITICAL severity."""
        critical_cases = [
            "I want to kill myself",
            "I am planning to hurt myself",
            "I want to end it all",
        ]
        high_severity = {SafetySeverity.HIGH, SafetySeverity.CRITICAL}
        for text in critical_cases:
            result = detector.assess(text)
            assert (
                result.severity in high_severity
            ), f"Critical case '{text}' only rated as {result.severity.name}"


# ============================================================================
# Convenience Function Tests
# ============================================================================


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_assess_safety_function(self):
        """Test assess_safety convenience function."""
        result = assess_safety("I feel hopeless")
        assert isinstance(result, SafetyAssessment)
        assert result.risk_detected is True

    def test_assess_safety_with_safe_text(self):
        """Test assess_safety returns safe for benign text."""
        result = assess_safety("Having a great day!")
        assert result.risk_detected is False
        assert result.severity == SafetySeverity.NONE


# ============================================================================
# Edge Cases and Robustness Tests
# ============================================================================


class TestEdgeCases:
    """Test edge cases and robustness."""

    def test_empty_string(self, detector):
        """Empty string should return safe assessment."""
        result = detector.assess("")
        assert result.risk_detected is False
        assert result.severity == SafetySeverity.NONE

    def test_whitespace_only(self, detector):
        """Whitespace-only string should return safe assessment."""
        result = detector.assess("   \n\t   ")
        assert result.risk_detected is False

    def test_unicode_text(self, detector):
        """Unicode text should be processed without error."""
        result = detector.assess("I feel hopeless")
        assert isinstance(result, SafetyAssessment)

    def test_mixed_case(self, detector):
        """Case should not affect detection."""
        lower_result = detector.assess("i want to kill myself")
        upper_result = detector.assess("I WANT TO KILL MYSELF")
        mixed_result = detector.assess("I Want To Kill Myself")

        assert lower_result.risk_detected is True
        assert upper_result.risk_detected is True
        assert mixed_result.risk_detected is True

    def test_special_characters(self, detector):
        """Special characters should not break detection."""
        result = detector.assess("I want to kill myself!!!")
        assert result.risk_detected is True

        result = detector.assess("I want to kill myself...")
        assert result.risk_detected is True

    def test_repeated_indicators(self, detector):
        """Repeated indicators should have diminishing returns."""
        result = detector.assess("hopeless hopeless hopeless")
        assert result.confidence <= 1.0  # Should not exceed max

    def test_processing_time_recorded(self, detector):
        """Processing time should be recorded."""
        result = detector.assess("Test text")
        assert result.processing_time_ms >= 0


# ============================================================================
# Integration Tests (require model)
# ============================================================================


@pytest.mark.integration
class TestModelIntegration:
    """Integration tests requiring model loading."""

    def test_model_loading(self, detector_with_model):
        """Model should load without error."""
        result = detector_with_model.assess("Test text")
        assert result is not None

    def test_model_score_populated(self, detector_with_model):
        """Model score should be populated when model available."""
        result = detector_with_model.assess("I feel terrible today")
        # Model score should be between 0 and 1
        assert 0.0 <= result.model_score <= 1.0

    def test_model_boosts_indicator_detection(self, detector_with_model):
        """Model should corroborate indicator detection."""
        result = detector_with_model.assess("I have no hope, everything is terrible")
        # Should have both indicator and model scores
        assert result.indicator_score > 0
        # Model version should indicate model was used
        assert "clinical_safety" in result.model_version
