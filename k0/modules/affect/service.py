"""
Affect Service - Main Entry Point for Affect Module

Orchestrates the complete affect sensing pipeline:
1. Classify text/behavior (Tier-0 or Tier-1)
2. Apply social context modifiers (relationships, lifecycle)
3. Fuse modalities and smooth with EMA
4. Compute policy band (GREEN/AMBER/RED/BLACK)
5. Store in st_hipp_store

Reference: ADR-0012 (Affect Module)
"""

import time
from typing import Any, Dict, Optional

from .classifiers.tier0 import Tier0Classifier
from .classifiers.tier1 import Tier1Classifier
from .counterfactual import CounterfactualSimulator
from .fusion import FusionEngine
from .household import HouseholdDynamicsEngine
from .models import (
    AffectAnnotation,
    AffectEMAState,
    AffectSummary,
    HouseholdAffectState,
    PolicyBand,
)
from .policy import PolicyEngine
from .social import SocialContextEngine
from .storage import AffectStorage


class AffectService:
    """
    Main affect service orchestrating the complete pipeline.

    Usage:
        affect_service = AffectService()

        # Classify text
        affect = affect_service.classify_text("I'm feeling stressed")

        # Get EMA state
        state = affect_service.get_ema_state(person_id, space_id)

        # Get household state
        household = affect_service.get_household_state(space_id)
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize affect service.

        Args:
            config: Optional configuration dict
        """
        self.config = config or {}

        # Phase 1: Initialize components
        self.model_version = "tier0_v0.1.0"
        self.tier0_classifier = Tier0Classifier()
        self.tier1_classifier = (
            Tier1Classifier() if self.config.get("enable_tier1", False) else None
        )
        self.fusion_engine = FusionEngine()
        self.policy_engine = PolicyEngine()
        self.social_context = SocialContextEngine()
        self.household_dynamics = HouseholdDynamicsEngine()
        self.counterfactual = CounterfactualSimulator()
        self.storage = AffectStorage()

    def classify_text(self, text: str, context: Optional[Dict] = None) -> AffectAnnotation:
        """
        Classify text affect (valence, arousal, tags).

        Args:
            text: Input text to classify
            context: Optional context (person_id, space_id, behavior, etc.)

        Returns:
            AffectAnnotation with valence, arousal, tags, band
        """
        # Extract behavioral signals from context
        behavior = context.get("behavior") if context else None

        # Use Tier0Classifier to get valence, arousal, tags, confidence
        valence, arousal, tags, confidence = self.tier0_classifier.classify(
            text=text, behavior=behavior
        )

        # Phase 1: Always GREEN band (no policy rules yet)
        band = PolicyBand.GREEN
        band_reasons = []

        return AffectAnnotation(
            valence=valence,
            arousal=arousal,
            tags=tags,
            confidence=confidence,
            band=band,
            band_reasons=band_reasons,
            model_version=self.model_version,
            computed_at=time.time(),  # Unix timestamp
            event_id=(
                context.get("event_id", f"evt_{int(time.time())}")
                if context
                else f"evt_{int(time.time())}"
            ),
            space_id=context.get("space_id", "default") if context else "default",
        )

    def get_ema_state(self, person_id: str, space_id: str) -> Optional[AffectEMAState]:
        """
        Get current EMA state for person in space.

        Args:
            person_id: Person identifier
            space_id: Space identifier

        Returns:
            AffectEMAState or None if not found
        """
        return self.storage.get_ema_state(person_id, space_id)

    def get_household_state(self, space_id: str) -> HouseholdAffectState:
        """
        Get current household affect state.

        Args:
            space_id: Space identifier

        Returns:
            HouseholdAffectState with aggregates and conflict detection
        """
        return self.household_dynamics.compute_household_state(space_id)

    def get_affect_summary(self, person_id: str, space_id: str) -> AffectSummary:
        """
        Get affect summary for K1 consumption.

        Args:
            person_id: Person identifier
            space_id: Space identifier

        Returns:
            AffectSummary for K1 Planner/Concierge
        """
        # TODO: Implement
        raise NotImplementedError("get_affect_summary not yet implemented")


# ===================================================================
# Convenience Functions for P02 Integration
# ===================================================================


def analyze_text_for_p02(
    text: str,
    context: Optional[Dict] = None,
    event_id: Optional[str] = None,
    space_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function for P02 Write Pipeline Step 7.

    One-shot affect analysis that returns a dict ready for st_hipp_store insertion.

    Args:
        text: Input text to analyze
        context: Optional context dict
        event_id: Optional event identifier
        space_id: Optional space identifier

    Returns:
        Dict with 6 keys for st_hipp_store columns:
            - affect_valence: float
            - affect_arousal: float
            - affect_tags: List[str]
            - affect_confidence: float
            - affect_model_version: str
            - affect_computed_at: float (Unix timestamp)

    Example:
        >>> result = analyze_text_for_p02("I love this!", space_id="space_123")
        >>> # result = {
        >>> #   "affect_valence": 0.8,
        >>> #   "affect_arousal": 0.3,
        >>> #   "affect_tags": ["positive", "low_arousal"],
        >>> #   "affect_confidence": 0.7,
        >>> #   "affect_model_version": "tier0_v0.1.0",
        >>> #   "affect_computed_at": 1699900000.0
        >>> # }
    """
    service = AffectService()
    annotation = service.classify_text(
        text=text,
        context=context or {},
    )

    return {
        "affect_valence": annotation.valence,
        "affect_arousal": annotation.arousal,
        "affect_tags": annotation.tags,
        "affect_confidence": annotation.confidence,
        "affect_model_version": annotation.model_version,
        "affect_computed_at": annotation.computed_at,
    }
