"""
Activity Module - Zero-Shot Activity Classification

Provides research-backed activity classification for the K0 kernel.

Research Foundation:
- Yin et al. (2019) - Benchmarking Zero-shot Text Classification
- Lewis et al. (2020) - BART: Denoising Sequence-to-Sequence Pre-training

Components:
- ZeroShotActivityClassifier: Main classifier with rule-based and ML tiers
- HierarchicalActivityResolver: Maps activities to taxonomy hierarchy
- ActivityClassification: Dataclass for classification results

Performance Targets:
- Rule-based: <5ms P95
- ML (BART): <50ms P95 (GPU), <150ms P95 (CPU)

Contract: k0/contracts/taxonomies/activity_taxonomy.yaml
"""

__version__ = "1.0.0"

from k0.modules.activity.taxonomy_resolver import (
    ActivityTaxonomy,
    HierarchicalActivityResolver,
    TaxonomyNode,
    get_resolver,
    resolve_activity_hierarchy,
)
from k0.modules.activity.zero_shot_classifier import (
    ACTIVITY_KEYWORDS,
    ACTIVITY_TO_CATEGORY,
    ZERO_SHOT_LABELS,
    ActivityClassification,
    ClassificationTier,
    ZeroShotActivityClassifier,
    classify_activity,
    get_classifier,
    get_metrics,
    map_legacy_activity,
    reset_metrics,
)

__all__ = [
    # Classifier
    "ZeroShotActivityClassifier",
    "ActivityClassification",
    "ClassificationTier",
    "classify_activity",
    "get_classifier",
    # Taxonomy
    "HierarchicalActivityResolver",
    "ActivityTaxonomy",
    "TaxonomyNode",
    "resolve_activity_hierarchy",
    "get_resolver",
    # Constants
    "ACTIVITY_KEYWORDS",
    "ACTIVITY_TO_CATEGORY",
    "ZERO_SHOT_LABELS",
    # Utilities
    "map_legacy_activity",
    "get_metrics",
    "reset_metrics",
]
