"""
Tier-0 Realtime Classifier

Lexicon-based affect classification with <2ms P95 latency.

Components:
    - Lexicon (~100 words with valence/arousal scores, inline in Phase 1)
    - Behavioral arousal detection (typing speed, pause duration)
    - Negation handling
    - Intensity modifiers

Reference: ADR-0012b (Tier-0 Realtime Classifier)
"""

from .classifier import Tier0Classifier
from .lexicon import AffectLexicon, load_lexicon

__all__ = ["Tier0Classifier", "AffectLexicon", "load_lexicon"]
