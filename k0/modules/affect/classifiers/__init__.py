"""
Affect Classifiers - Tier-0 and Tier-1

Tier-0: Realtime lexicon-based classifier (<2ms P95)
Tier-1: Enhanced ensemble classifier (<60ms P95, optional)

Reference:
    - ADR-0012b (Tier-0 Realtime Classifier)
    - ADR-0012c (Tier-1 Enhanced Classifier & ONNX)
"""

from .tier0 import Tier0Classifier
from .tier1 import Tier1Classifier

__all__ = ["Tier0Classifier", "Tier1Classifier"]
