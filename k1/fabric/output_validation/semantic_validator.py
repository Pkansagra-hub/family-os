"""
k1.fabric.output_validation.semantic_validator -- Tier 3: Semantic Validation.

Issue 3.5.3 -- SemanticValidator with HallucinationDetector.

Semantic validation for agent/LLM-generated outputs.  This is the
OPTIONAL tier -- only runs for agent/prompt provider types.

HallucinationDetector checks:
  1. Factual grounding against provided context.
  2. Consistency with SessionState beliefs (via ISessionStateReader).
  3. Confidence scoring.

Returns ValidationResult{valid, confidence, issues}.

Design:
  - This tier is rule-based (no LLM).  It uses heuristic detectors
    that flag suspicious patterns.  A full LLM-based factual grounding
    check belongs in a future iteration.
  - Soft failure: does NOT reject, only annotates confidence + warnings.

Dependencies:
  - ISessionStateReader (5.1.1) -- reads SessionState beliefs.
  - ProviderType -- determines if semantic check applies.

References:
  - fabric-implementation-plan.md Issue 3.5.3
  - Epic 3.5 wiring: only for agent/prompt providers
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Set

from .structural_validator import (
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
    ValidationTier,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Port protocol (matches ISessionStateReader in policy/ports.py)
# ---------------------------------------------------------------------------


class ISessionStateReader(Protocol):
    """
    Read-only access to SessionState sections.

    Structural subtype of ``k1.fabric.policy.ports.ISessionStateReader``.
    Re-declared here to avoid cross-package import from policy subsystem.
    """

    def read_section(
        self,
        session_id: str,
        section: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a named section from SessionState."""
        ...


# ---------------------------------------------------------------------------
# Provider types that require semantic validation
# ---------------------------------------------------------------------------

#: Provider types that produce LLM-generated content and need semantic checks.
SEMANTIC_PROVIDER_TYPES: Set[str] = {"AGENT", "WORKFLOW"}


# ---------------------------------------------------------------------------
# HallucinationDetector configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HallucinationDetectorConfig:
    """
    Configuration for the HallucinationDetector.

    Attributes:
        confidence_threshold: Below this confidence, issues are raised.
        max_context_items: Max number of context items to check against.
        check_factual_grounding: Enable factual grounding checks.
        check_session_consistency: Enable SessionState consistency checks.
        check_confidence_markers: Enable confidence/uncertainty marker check.
    """

    confidence_threshold: float = 0.7
    max_context_items: int = 50
    check_factual_grounding: bool = True
    check_session_consistency: bool = True
    check_confidence_markers: bool = True


# ---------------------------------------------------------------------------
# Confidence / uncertainty marker patterns
# ---------------------------------------------------------------------------

#: Patterns that indicate the output expresses uncertainty
_UNCERTAINTY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bi(?:'m| am) not sure\b", re.IGNORECASE),
    re.compile(r"\bi(?:'m| am) uncertain\b", re.IGNORECASE),
    re.compile(r"\bi don(?:'t| not) know\b", re.IGNORECASE),
    re.compile(r"\bI think\b", re.IGNORECASE),
    re.compile(r"\bprobably\b", re.IGNORECASE),
    re.compile(r"\bperhaps\b", re.IGNORECASE),
    re.compile(r"\bmight be\b", re.IGNORECASE),
    re.compile(r"\bcould be\b", re.IGNORECASE),
    re.compile(r"\bnot certain\b", re.IGNORECASE),
    re.compile(r"\bI believe\b", re.IGNORECASE),
    re.compile(r"\bapproximately\b", re.IGNORECASE),
]

#: Patterns that indicate fabricated authority / hallucination risk
_FABRICATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\baccording to (?:my|the) (?:knowledge|training)\b", re.IGNORECASE),
    re.compile(r"\bas of my (?:last|latest) (?:update|training)\b", re.IGNORECASE),
    re.compile(r"\bI was trained\b", re.IGNORECASE),
    re.compile(r"\bmy training data\b", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# 3.5.3 -- HallucinationDetector
# ---------------------------------------------------------------------------


class HallucinationDetector:
    """
    Rule-based hallucination / confidence detector.

    Analyses text content in result data for:
    - Uncertainty markers (reduces confidence)
    - Fabrication patterns (raises SOFT issues)
    - Contradiction with SessionState beliefs

    Stateless.  Thread-safe.  No LLM calls.
    """

    __slots__ = ("_config",)

    def __init__(self, config: Optional[HallucinationDetectorConfig] = None) -> None:
        self._config = config or HallucinationDetectorConfig()

    def detect(
        self,
        data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        session_beliefs: Optional[Dict[str, Any]] = None,
    ) -> "HallucinationReport":
        """
        Analyse *data* for hallucination indicators.

        Args:
            data: The result.data dict to analyse.
            context: Execution context that was provided to the agent.
            session_beliefs: SessionState beliefs for consistency check.

        Returns:
            HallucinationReport with confidence and issues.
        """
        issues: List[ValidationIssue] = []
        confidence = 1.0

        # Extract all text content from data for analysis
        text_content = self._extract_text(data)

        if not text_content:
            return HallucinationReport(confidence=1.0, issues=[])

        # Check 1: Uncertainty markers
        if self._config.check_confidence_markers:
            uncertainty_hits = self._check_uncertainty(text_content)
            if uncertainty_hits:
                # Each uncertainty marker reduces confidence
                penalty = min(0.05 * len(uncertainty_hits), 0.3)
                confidence -= penalty
                issues.append(
                    ValidationIssue(
                        tier=ValidationTier.SEMANTIC,
                        severity=ValidationSeverity.SOFT,
                        code="uncertainty_detected",
                        message=(
                            f"Output contains {len(uncertainty_hits)} uncertainty "
                            f"marker(s): {', '.join(uncertainty_hits[:3])}"
                        ),
                    )
                )

        # Check 2: Fabrication patterns
        if self._config.check_factual_grounding:
            fabrication_hits = self._check_fabrication(text_content)
            if fabrication_hits:
                penalty = min(0.1 * len(fabrication_hits), 0.4)
                confidence -= penalty
                issues.append(
                    ValidationIssue(
                        tier=ValidationTier.SEMANTIC,
                        severity=ValidationSeverity.SOFT,
                        code="fabrication_risk",
                        message=(
                            f"Output contains {len(fabrication_hits)} fabrication "
                            f"pattern(s): {', '.join(fabrication_hits[:3])}"
                        ),
                    )
                )

        # Check 3: SessionState belief consistency
        if self._config.check_session_consistency and session_beliefs:
            contradictions = self._check_belief_consistency(text_content, session_beliefs)
            if contradictions:
                penalty = min(0.15 * len(contradictions), 0.4)
                confidence -= penalty
                issues.extend(contradictions)

        # Clamp confidence to [0, 1]
        confidence = max(0.0, min(1.0, confidence))

        return HallucinationReport(confidence=confidence, issues=issues)

    # ---- internal helpers --------------------------------------------------

    @staticmethod
    def _extract_text(data: Dict[str, Any], max_depth: int = 5) -> str:
        """Recursively extract string values from data into one blob."""
        parts: List[str] = []

        def _walk(obj: Any, depth: int) -> None:
            if depth > max_depth:
                return
            if isinstance(obj, str):
                parts.append(obj)
            elif isinstance(obj, dict):
                for v in obj.values():
                    _walk(v, depth + 1)
            elif isinstance(obj, (list, tuple)):
                for item in obj:
                    _walk(item, depth + 1)

        _walk(data, 0)
        return " ".join(parts)

    @staticmethod
    def _check_uncertainty(text: str) -> List[str]:
        """Find uncertainty markers in text."""
        hits: List[str] = []
        for pattern in _UNCERTAINTY_PATTERNS:
            match = pattern.search(text)
            if match:
                hits.append(match.group(0))
        return hits

    @staticmethod
    def _check_fabrication(text: str) -> List[str]:
        """Find fabrication risk patterns in text."""
        hits: List[str] = []
        for pattern in _FABRICATION_PATTERNS:
            match = pattern.search(text)
            if match:
                hits.append(match.group(0))
        return hits

    @staticmethod
    def _check_belief_consistency(
        text: str,
        beliefs: Dict[str, Any],
    ) -> List[ValidationIssue]:
        """
        Check text for contradictions with session beliefs.

        This is a heuristic check:  if a belief has a ``value`` and a
        ``negation`` key, we check whether the negation appears in text.
        """
        issues: List[ValidationIssue] = []

        for belief_name, belief_data in beliefs.items():
            if not isinstance(belief_data, dict):
                continue
            negation = belief_data.get("negation")
            if negation and isinstance(negation, str):
                if negation.lower() in text.lower():
                    issues.append(
                        ValidationIssue(
                            tier=ValidationTier.SEMANTIC,
                            severity=ValidationSeverity.SOFT,
                            code="belief_contradiction",
                            message=(
                                f"Output may contradict session belief "
                                f"'{belief_name}': found '{negation}'"
                            ),
                        )
                    )

        return issues


# ---------------------------------------------------------------------------
# HallucinationReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HallucinationReport:
    """
    Output from HallucinationDetector.detect().

    Attributes:
        confidence: 0..1 score -- 1.0 = high confidence, 0.0 = likely hallucinated.
        issues: List of semantic issues found.
    """

    confidence: float = 1.0
    issues: List[ValidationIssue] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 3.5.3 -- SemanticValidator
# ---------------------------------------------------------------------------


class SemanticValidator:
    """
    Tier 3 -- semantic validation of agent/LLM-generated output.

    Optional tier: only runs when ``provider_type`` is in
    SEMANTIC_PROVIDER_TYPES and ``skip_semantic`` is not True.

    Uses HallucinationDetector for rule-based analysis.
    Reads SessionState beliefs via ISessionStateReader (when provided).

    Produces SOFT failures only (annotate, do not reject).

    Usage::

        validator = SemanticValidator(state_reader=reader)
        result = validator.validate(
            data=capability_result.data,
            provider_type="AGENT",
            session_id="sess-123",
            execution_context={"prompt": "..."},
        )
        # result.valid may be False with SOFT issues
    """

    __slots__ = ("_detector", "_state_reader")

    def __init__(
        self,
        state_reader: Optional[ISessionStateReader] = None,
        config: Optional[HallucinationDetectorConfig] = None,
    ) -> None:
        self._detector = HallucinationDetector(config)
        self._state_reader = state_reader

    @property
    def detector(self) -> HallucinationDetector:
        """Access the underlying HallucinationDetector."""
        return self._detector

    def validate(
        self,
        data: Dict[str, Any],
        provider_type: str,
        session_id: Optional[str] = None,
        execution_context: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """
        Run semantic validation on *data*.

        Args:
            data: The result.data dict.
            provider_type: The provider type string (e.g. "AGENT").
            session_id: Session ID for belief lookup.
            execution_context: Context provided to the agent.

        Returns:
            ValidationResult with tier=SEMANTIC.
            Always SOFT severity -- never causes rejection.
        """
        # Skip for non-semantic provider types
        if provider_type not in SEMANTIC_PROVIDER_TYPES:
            return ValidationResult(
                valid=True,
                tier=ValidationTier.SEMANTIC,
                confidence=1.0,
                metadata={"skipped": True, "reason": "non_semantic_provider"},
            )

        # Read session beliefs if state reader available
        session_beliefs: Optional[Dict[str, Any]] = None
        if self._state_reader is not None and session_id:
            try:
                session_beliefs = self._state_reader.read_section(session_id, "beliefs")
            except Exception:
                logger.warning(
                    "Failed to read session beliefs for %s",
                    session_id,
                    exc_info=True,
                )

        # Run hallucination detection
        report = self._detector.detect(
            data=data,
            context=execution_context,
            session_beliefs=session_beliefs,
        )

        # Determine validity based on confidence threshold
        threshold = self._detector._config.confidence_threshold
        is_valid = report.confidence >= threshold

        metadata: Dict[str, Any] = {
            "confidence": report.confidence,
            "threshold": threshold,
            "provider_type": provider_type,
            "beliefs_checked": session_beliefs is not None,
        }

        return ValidationResult(
            valid=is_valid,
            tier=ValidationTier.SEMANTIC,
            issues=list(report.issues),
            confidence=report.confidence,
            metadata=metadata,
        )
