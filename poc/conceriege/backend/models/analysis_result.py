"""
Analysis Result Models

Represents results from specialist agents (nutritionist, psychiatrist, etc.)
with insights, evidence, and confidence scores.

Research basis:
- Evidence-based reasoning
- Confidence scoring for uncertainty quantification
"""

from dataclasses import dataclass, field
from typing import List, Literal, Optional


@dataclass
class Insight:
    """
    Single insight from specialist analysis.

    Fields:
        summary: Brief insight summary (e.g., "Strong trigger: late night coffee")
        evidence: List of evidence supporting this insight
        severity: Strength of insight - strong, moderate, weak
        confidence: Confidence score (0.0-1.0)

    Examples:
        >>> insight = Insight(
        ...     summary="Strong trigger: late night coffee",
        ...     evidence=["3 out of 5 GERD episodes after coffee"],
        ...     severity="strong",
        ...     confidence=0.85
        ... )
        >>> insight.to_dict()
        {'summary': 'Strong trigger: late night coffee', ...}
    """

    summary: str
    evidence: List[str] = field(default_factory=list)
    severity: Literal["strong", "moderate", "weak"] = "moderate"
    confidence: float = 0.0

    def to_dict(self) -> dict:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of Insight
        """
        return {
            "summary": self.summary,
            "evidence": self.evidence,
            "severity": self.severity,
            "confidence": self.confidence,
        }


@dataclass
class AnalysisResult:
    """
    Complete analysis result from specialist agent.

    Fields:
        specialist_type: Type of specialist (nutritionist, psychiatrist, etc.)
        query: Original user query
        insights: List of insights discovered
        evidence: Supporting evidence for insights
        confidence: Overall confidence score (0.0-1.0)
        duration_ms: How long analysis took
        contradicts_user_hypothesis: Whether findings contradict user's assumption
        user_hypothesis: User's original hypothesis (if any)
        actual_finding: What specialist actually found

    Examples:
        >>> result = AnalysisResult(
        ...     specialist_type="nutritionist",
        ...     query="What triggers my GERD?",
        ...     insights=[
        ...         Insight(
        ...             summary="Strong trigger: coffee",
        ...             evidence=["3/5 episodes after coffee"],
        ...             severity="strong",
        ...             confidence=0.85
        ...         )
        ...     ],
        ...     confidence=0.85,
        ...     duration_ms=850,
        ...     contradicts_user_hypothesis=True,
        ...     user_hypothesis="milk",
        ...     actual_finding="late night coffee"
        ... )
        >>> result.has_contradiction()
        True
    """

    specialist_type: str
    query: str
    insights: List[Insight] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    confidence: float = 0.0
    duration_ms: int = 0
    contradicts_user_hypothesis: bool = False
    user_hypothesis: Optional[str] = None
    actual_finding: Optional[str] = None

    def to_dict(self) -> dict:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of AnalysisResult
        """
        return {
            "specialist_type": self.specialist_type,
            "query": self.query,
            "insights": [insight.to_dict() for insight in self.insights],
            "evidence": self.evidence,
            "confidence": self.confidence,
            "duration_ms": self.duration_ms,
            "contradicts_user_hypothesis": self.contradicts_user_hypothesis,
            "user_hypothesis": self.user_hypothesis,
            "actual_finding": self.actual_finding,
        }

    def get_primary_insight(self) -> Optional[Insight]:
        """
        Get primary (strongest) insight.

        Returns:
            Insight with highest confidence, or None if no insights
        """
        if not self.insights:
            return None

        return max(self.insights, key=lambda i: i.confidence)

    def has_contradiction(self) -> bool:
        """
        Check if result contradicts user hypothesis.

        Returns:
            True if contradiction exists
        """
        return self.contradicts_user_hypothesis
