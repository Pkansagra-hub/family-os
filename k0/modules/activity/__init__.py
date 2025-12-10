"""
Activity Module - Activity Classification and Taxonomy

Provides activity classification and taxonomy resolution for K0 kernel.
UltraBERT now handles zero-shot classification - this module provides
taxonomy mapping and backward compatibility.

Components:
- HierarchicalActivityResolver: Maps activities to taxonomy hierarchy
- ActivityTaxonomy: Full activity taxonomy tree
- TaxonomyNode: Individual taxonomy node

Related:
- k0/runtime/ultrabert_adapter.py: classify_activity() for ML classification
- k0/modules/context/ingress_classify.py: Unified ingress classification

Contract: k0/contracts/taxonomies/activity_taxonomy.yaml
"""

__version__ = "2.0.0"

from k0.modules.activity.taxonomy_resolver import (
    ActivityTaxonomy,
    HierarchicalActivityResolver,
    TaxonomyNode,
    get_resolver,
    resolve_activity_hierarchy,
)

__all__ = [
    # Taxonomy
    "HierarchicalActivityResolver",
    "ActivityTaxonomy",
    "TaxonomyNode",
    "resolve_activity_hierarchy",
    "get_resolver",
]
