"""
Affect Module - Emotional Classification System

Provides fast affect classification for episodic memories.
Version: 0.1.0

ADRs: K004, K004.1, K004.2, K004.3
"""

from .affect_service import AffectService
from .affect_types import AffectAnnotation, AffectBand, AffectConfig, EmotionTag

__version__ = "0.1.0"
__all__ = [
    "AffectService",
    "AffectAnnotation",
    "AffectConfig",
    "AffectBand",
    "EmotionTag",
]
