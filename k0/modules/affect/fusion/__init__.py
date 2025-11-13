"""
Multi-Modal Fusion and EMA Smoothing

Fuses Tier-0/Tier-1 classifications with behavioral signals and smooths with dual EMA.

Reference: ADR-0012d (Multi-Modal Fusion, EMA & Calibration)
"""

from .engine import FusionEngine

__all__ = ["FusionEngine"]
