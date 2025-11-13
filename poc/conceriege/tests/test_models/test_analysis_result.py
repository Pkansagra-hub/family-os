"""
Unit tests for AnalysisResult and Insight dataclasses.

Tests:
- Insight creation and serialization
- AnalysisResult creation
- get_primary_insight() method
- has_contradiction() method
- Serialization
"""

import pytest
from backend.models.analysis_result import AnalysisResult, Insight


class TestInsight:
    """Test Insight dataclass."""

    def test_insight_creation(self):
        """Test creating insight."""
        insight = Insight(
            summary="Strong trigger: late night coffee",
            evidence=["3 out of 5 GERD episodes after coffee"],
            severity="strong",
            confidence=0.85,
        )

        assert insight.summary == "Strong trigger: late night coffee"
        assert len(insight.evidence) == 1
        assert insight.severity == "strong"
        assert insight.confidence == 0.85

    def test_insight_default_values(self):
        """Test insight with default values."""
        insight = Insight(summary="Test insight")

        assert insight.evidence == []
        assert insight.severity == "moderate"
        assert insight.confidence == 0.0

    def test_insight_all_severity_levels(self):
        """Test all severity levels."""
        strong = Insight(summary="Strong", severity="strong", confidence=0.9)
        moderate = Insight(summary="Moderate", severity="moderate", confidence=0.6)
        weak = Insight(summary="Weak", severity="weak", confidence=0.3)

        assert strong.severity == "strong"
        assert moderate.severity == "moderate"
        assert weak.severity == "weak"

    def test_insight_to_dict(self):
        """Test insight serialization."""
        insight = Insight(
            summary="Test insight",
            evidence=["evidence1", "evidence2"],
            severity="strong",
            confidence=0.85,
        )

        data = insight.to_dict()

        assert data["summary"] == "Test insight"
        assert data["evidence"] == ["evidence1", "evidence2"]
        assert data["severity"] == "strong"
        assert data["confidence"] == 0.85


class TestAnalysisResult:
    """Test AnalysisResult dataclass."""

    def test_analysis_result_creation(self):
        """Test creating analysis result."""
        result = AnalysisResult(
            specialist_type="nutritionist",
            query="What triggers my GERD?",
            confidence=0.85,
            duration_ms=850,
        )

        assert result.specialist_type == "nutritionist"
        assert result.query == "What triggers my GERD?"
        assert result.confidence == 0.85
        assert result.duration_ms == 850

    def test_analysis_result_with_insights(self):
        """Test analysis result with insights."""
        insights = [
            Insight(
                summary="Strong trigger: coffee",
                evidence=["3/5 episodes after coffee"],
                severity="strong",
                confidence=0.85,
            ),
            Insight(
                summary="Weak trigger: pizza",
                evidence=["1/4 episodes after pizza"],
                severity="weak",
                confidence=0.25,
            ),
        ]

        result = AnalysisResult(
            specialist_type="nutritionist",
            query="What triggers GERD?",
            insights=insights,
            confidence=0.85,
        )

        assert len(result.insights) == 2
        assert result.insights[0].severity == "strong"
        assert result.insights[1].severity == "weak"

    def test_analysis_result_with_contradiction(self):
        """Test analysis result with contradiction."""
        result = AnalysisResult(
            specialist_type="nutritionist",
            query="Is milk causing my GERD?",
            insights=[Insight(summary="Trigger: coffee", confidence=0.85)],
            confidence=0.85,
            duration_ms=850,
            contradicts_user_hypothesis=True,
            user_hypothesis="milk",
            actual_finding="late night coffee",
        )

        assert result.contradicts_user_hypothesis is True
        assert result.user_hypothesis == "milk"
        assert result.actual_finding == "late night coffee"

    def test_analysis_result_get_primary_insight(self):
        """Test getting primary insight."""
        insights = [
            Insight(summary="Insight 1", confidence=0.6),
            Insight(summary="Insight 2", confidence=0.9),  # Highest
            Insight(summary="Insight 3", confidence=0.7),
        ]

        result = AnalysisResult(specialist_type="nutritionist", query="Test", insights=insights)

        primary = result.get_primary_insight()

        assert primary is not None
        assert primary.summary == "Insight 2"
        assert primary.confidence == 0.9

    def test_analysis_result_get_primary_insight_no_insights(self):
        """Test get_primary_insight with no insights."""
        result = AnalysisResult(specialist_type="nutritionist", query="Test")

        primary = result.get_primary_insight()

        assert primary is None

    def test_analysis_result_has_contradiction(self):
        """Test has_contradiction method."""
        with_contradiction = AnalysisResult(
            specialist_type="nutritionist", query="Test", contradicts_user_hypothesis=True
        )

        without_contradiction = AnalysisResult(
            specialist_type="nutritionist", query="Test", contradicts_user_hypothesis=False
        )

        assert with_contradiction.has_contradiction() is True
        assert without_contradiction.has_contradiction() is False

    def test_analysis_result_to_dict(self):
        """Test analysis result serialization."""
        insights = [Insight(summary="Test", confidence=0.8)]

        result = AnalysisResult(
            specialist_type="nutritionist",
            query="What triggers GERD?",
            insights=insights,
            evidence=["evidence1", "evidence2"],
            confidence=0.85,
            duration_ms=850,
            contradicts_user_hypothesis=True,
            user_hypothesis="milk",
            actual_finding="coffee",
        )

        data = result.to_dict()

        assert data["specialist_type"] == "nutritionist"
        assert data["query"] == "What triggers GERD?"
        assert len(data["insights"]) == 1
        assert data["insights"][0]["summary"] == "Test"
        assert data["evidence"] == ["evidence1", "evidence2"]
        assert data["confidence"] == 0.85
        assert data["duration_ms"] == 850
        assert data["contradicts_user_hypothesis"] is True
        assert data["user_hypothesis"] == "milk"
        assert data["actual_finding"] == "coffee"

    def test_analysis_result_complete_gerd_scenario(self):
        """Test complete GERD analysis scenario."""
        result = AnalysisResult(
            specialist_type="nutritionist",
            query="What is causing my GERD symptoms?",
            insights=[
                Insight(
                    summary="Strong trigger: late night coffee",
                    evidence=[
                        "3 out of 5 GERD episodes occurred after evening coffee",
                        "Correlation score: 60%",
                        "Last occurrence: 2025-11-05 10pm",
                    ],
                    severity="strong",
                    confidence=0.85,
                ),
                Insight(
                    summary="Weak correlation: milk",
                    evidence=["0 out of 8 times milk was consumed", "No correlation detected"],
                    severity="weak",
                    confidence=0.1,
                ),
            ],
            evidence=[
                "2025-11-01: Coffee at 9pm → GERD at 10pm",
                "2025-11-03: Coffee at 8:30pm → GERD at 9:15pm",
                "2025-11-05: Coffee at 10pm → GERD at 11pm",
            ],
            confidence=0.85,
            duration_ms=850,
            contradicts_user_hypothesis=True,
            user_hypothesis="milk",
            actual_finding="late night coffee",
        )

        # Verify primary insight
        primary = result.get_primary_insight()
        assert primary is not None
        assert primary.summary == "Strong trigger: late night coffee"
        assert primary.confidence == 0.85

        # Verify contradiction
        assert result.has_contradiction() is True

        # Verify serialization
        data = result.to_dict()
        assert data["specialist_type"] == "nutritionist"
        assert len(data["insights"]) == 2
        assert data["contradicts_user_hypothesis"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
