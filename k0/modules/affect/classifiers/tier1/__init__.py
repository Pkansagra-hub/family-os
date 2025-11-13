"""
Tier-1 Enhanced Classifier

Ensemble classifier with VADER, TextBlob, and ONNX transformer.

Performance: <60ms P95 latency

Reference: ADR-0012c (Tier-1 Enhanced Classifier & ONNX)
"""

from .classifier import Tier1Classifier

__all__ = ["Tier1Classifier"]
