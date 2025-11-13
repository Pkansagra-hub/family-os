"""
K0 Affect Module - On-Device Affect Sensing & Policy Engine

This module implements the complete affect sensing pipeline as specified in ADR-0012 (k003a-k003i):
- Tier-0/Tier-1 affect classifiers (valence, arousal, tags)
- Multi-modal fusion and EMA smoothing
- Policy band rules (BLACK/RED/AMBER/GREEN)
- Social cognition (relationship context, developmental stages)
- Household dynamics (conflict detection, family moments)
- Counterfactual safety (proactive harm prevention)

Architecture:
    Event → Tier-0 (2ms) → Tier-1 (60ms) → Fusion → EMA → Policy Banding → Storage

Performance Budgets:
    - Tier-0: <2ms P95
    - Tier-1: <60ms P95 (optional)
    - Policy Banding: <5ms P95
    - Total: <70ms P95 (with Tier-1)

Related ADRs:
    - k003a: Affect Contracts & Storage Mapping
    - k003b: Tier-0 Realtime Classifier
    - k003c: Tier-1 Enhanced Classifier & ONNX
    - k003d: Multi-Modal Fusion, EMA & Calibration
    - k003e: Policy Band Rules & P18 Integration
    - k003f: Affect → K1 Planner & Concierge Bridge
    - k003g: Household-Level Affect Dynamics
    - k003h: Social Cognition & Relationship Context Modifiers
    - k003i: Counterfactual Emotional Safety & Sharing
"""

from .models import (
    AffectAnnotation,
    AffectEMAState,
    AffectSummary,
    BandingResult,
    HouseholdAffectState,
)

# Lazy import to avoid circular dependencies and missing modules during testing
try:
    from .service import AffectService

    __all__ = [
        "AffectService",
        "AffectAnnotation",
        "AffectEMAState",
        "BandingResult",
        "HouseholdAffectState",
        "AffectSummary",
    ]
except ImportError:
    # Service not available (dependencies not yet implemented)
    __all__ = [
        "AffectAnnotation",
        "AffectEMAState",
        "BandingResult",
        "HouseholdAffectState",
        "AffectSummary",
    ]

__version__ = "1.0.0"
