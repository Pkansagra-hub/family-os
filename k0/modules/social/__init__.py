"""Social Module - Relationship Graph | Version: 0.2.0 | ADR: K008"""

from .family_graph_resolver import FamilyGraphResolver
from .relationship_inference import (
    CooccurrenceStats,
    InferredRelationship,
    RelationshipInferenceEngine,
    RelationType,
    get_inference_engine,
    infer_all_relationships,
    infer_relationship,
)
from .social_context_classifier import (
    DunbarLayer,
    IntimacyLevel,
    SocialContextClassifier,
    SocialContextResult,
    SocialContextType,
    classify_social_context,
    get_classifier,
    get_relationship_strength_for_role,
)

__version__ = "0.2.0"
__all__ = [
    # Legacy resolver
    "FamilyGraphResolver",
    # Issue 4.1.2: Relationship Inference
    "RelationshipInferenceEngine",
    "RelationType",
    "InferredRelationship",
    "CooccurrenceStats",
    "get_inference_engine",
    "infer_relationship",
    "infer_all_relationships",
    # Issue 4.1.3: Social Context Classifier
    "SocialContextClassifier",
    "SocialContextType",
    "IntimacyLevel",
    "DunbarLayer",
    "SocialContextResult",
    "get_classifier",
    "classify_social_context",
    "get_relationship_strength_for_role",
]
