"""
Golden Dataset for Module Accuracy Benchmarking.

This package provides:
- Pydantic models for validated golden annotations
- Sample dataset loading utilities
- Benchmark accuracy scoring functions

Related ADRs: None (Testing Infrastructure)
Issue: 1.2.1 - Golden Dataset for Module Accuracy
"""

from .loader import get_golden_memories_by_tag, load_golden_dataset
from .models import (
    ActivityAnnotation,
    ActivityType,
    EmotionAnnotation,
    EmotionLabel,
    EntityAnnotation,
    EntityType,
    FamilyRole,
    GoldenDataset,
    GoldenMemory,
    GroundTruth,
    SocialAnnotation,
    SocialContext,
)

__all__ = [
    "GoldenMemory",
    "GoldenDataset",
    "EntityAnnotation",
    "EmotionAnnotation",
    "ActivityAnnotation",
    "SocialAnnotation",
    "GroundTruth",
    "EntityType",
    "EmotionLabel",
    "ActivityType",
    "SocialContext",
    "FamilyRole",
    "load_golden_dataset",
    "get_golden_memories_by_tag",
]
