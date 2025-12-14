"""
Hierarchical Activity Taxonomy Resolver

Provides hierarchical classification and taxonomy navigation for activities.
Maps flat activity labels to 3-level hierarchy (category -> activity -> subtype).

Design Philosophy:
- Tree-based taxonomy with 16 top-level categories
- 50+ activity types with ~80 subtypes
- Supports hierarchy traversal (get parent, children, ancestors)
- Lazy-loads taxonomy from YAML for extensibility

Contract: k0/contracts/taxonomies/activity_taxonomy.yaml
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml

# Module version
__version__ = "1.0.0"

# Taxonomy file path
TAXONOMY_PATH = (
    Path(__file__).parent.parent.parent / "contracts" / "taxonomies" / "activity_taxonomy.yaml"
)


@dataclass
class TaxonomyNode:
    """
    Node in the activity taxonomy tree.

    Represents a single activity type at any level (category, activity, subtype).
    """

    id: str
    label: str
    description: str = ""
    keywords: List[str] = field(default_factory=list)
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    level: int = 0  # 0=category, 1=activity, 2=subtype

    @property
    def is_category(self) -> bool:
        """Check if node is a top-level category."""
        return self.level == 0

    @property
    def is_leaf(self) -> bool:
        """Check if node has no children."""
        return len(self.children_ids) == 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "keywords": self.keywords,
            "parent_id": self.parent_id,
            "children_ids": self.children_ids,
            "level": self.level,
        }


@dataclass
class ActivityTaxonomy:
    """
    Complete activity taxonomy with all nodes and relationships.

    Loaded from k0/contracts/taxonomies/activity_taxonomy.yaml.
    """

    version: str
    nodes: Dict[str, TaxonomyNode] = field(default_factory=dict)
    categories: List[str] = field(default_factory=list)
    legacy_mapping: Dict[str, str] = field(default_factory=dict)
    zero_shot_labels: List[str] = field(default_factory=list)

    def get_node(self, node_id: str) -> Optional[TaxonomyNode]:
        """Get node by ID."""
        return self.nodes.get(node_id)

    def get_children(self, node_id: str) -> List[TaxonomyNode]:
        """Get all children of a node."""
        node = self.nodes.get(node_id)
        if not node:
            return []
        return [self.nodes[cid] for cid in node.children_ids if cid in self.nodes]

    def get_ancestors(self, node_id: str) -> List[TaxonomyNode]:
        """Get all ancestors from leaf to root."""
        ancestors = []
        current = self.nodes.get(node_id)
        while current and current.parent_id:
            parent = self.nodes.get(current.parent_id)
            if parent:
                ancestors.append(parent)
            current = parent
        return ancestors

    def get_path(self, node_id: str) -> str:
        """Get full hierarchy path (e.g., 'sustenance.meal.dinner')."""
        path_parts = [node_id]
        ancestors = self.get_ancestors(node_id)
        for ancestor in ancestors:
            path_parts.insert(0, ancestor.id)
        return ".".join(path_parts)

    def get_all_keywords(self, node_id: str) -> Set[str]:
        """Get all keywords for node and its ancestors."""
        keywords: Set[str] = set()
        node = self.nodes.get(node_id)
        if node:
            keywords.update(node.keywords)
        for ancestor in self.get_ancestors(node_id):
            keywords.update(ancestor.keywords)
        return keywords


class HierarchicalActivityResolver:
    """
    Resolves activities to hierarchical taxonomy.

    Supports:
    - Map flat activity label to hierarchy path
    - Get parent category for any activity
    - Get all activities in a category
    - Check if activity exists in taxonomy
    - Get related activities (siblings, cousins)

    Performance: <1ms for all operations (in-memory lookups)
    """

    def __init__(self, taxonomy_path: Optional[Path] = None):
        """
        Initialize resolver.

        Args:
            taxonomy_path: Path to taxonomy YAML (default: contracts/taxonomies/activity_taxonomy.yaml)
        """
        self.taxonomy_path = taxonomy_path or TAXONOMY_PATH
        self._taxonomy: Optional[ActivityTaxonomy] = None

    @property
    def taxonomy(self) -> ActivityTaxonomy:
        """Lazy-load taxonomy."""
        if self._taxonomy is None:
            self._taxonomy = self._load_taxonomy()
        return self._taxonomy

    def _load_taxonomy(self) -> ActivityTaxonomy:
        """Load and parse taxonomy from YAML."""
        if not self.taxonomy_path.exists():
            return self._create_default_taxonomy()

        with open(self.taxonomy_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        taxonomy_data = data.get("activity_taxonomy", {})

        taxonomy = ActivityTaxonomy(
            version=taxonomy_data.get("version", "1.0.0"),
            legacy_mapping=taxonomy_data.get("legacy_mapping", {}),
            zero_shot_labels=taxonomy_data.get("zero_shot_labels", []),
        )

        # Parse categories and build tree
        categories = taxonomy_data.get("categories", [])
        for category in categories:
            taxonomy.categories.append(category["id"])
            self._parse_node(category, taxonomy, parent_id=None, level=0)

        return taxonomy

    def _parse_node(
        self,
        node_data: Dict[str, Any],
        taxonomy: ActivityTaxonomy,
        parent_id: Optional[str],
        level: int,
    ) -> None:
        """Recursively parse taxonomy node and children."""
        node_id = node_data.get("id", "")
        children_data = node_data.get("children", [])

        # Handle simple string children (leaf nodes)
        children_ids = []
        for child in children_data:
            if isinstance(child, str):
                # Simple leaf node (string ID only)
                leaf_node = TaxonomyNode(
                    id=child,
                    label=child.replace("_", " ").title(),
                    parent_id=node_id,
                    level=level + 1,
                )
                taxonomy.nodes[child] = leaf_node
                children_ids.append(child)
            elif isinstance(child, dict):
                # Full node with metadata
                children_ids.append(child.get("id", ""))
                self._parse_node(child, taxonomy, parent_id=node_id, level=level + 1)

        # Create node
        node = TaxonomyNode(
            id=node_id,
            label=node_data.get("label", node_id.replace("_", " ").title()),
            description=node_data.get("description", ""),
            keywords=node_data.get("keywords", []),
            parent_id=parent_id,
            children_ids=children_ids,
            level=level,
        )
        taxonomy.nodes[node_id] = node

    def _create_default_taxonomy(self) -> ActivityTaxonomy:
        """Create minimal default taxonomy if YAML not found."""
        taxonomy = ActivityTaxonomy(
            version="1.0.0",
            categories=["sustenance", "wellness", "social", "work", "routine"],
        )

        # Add basic nodes
        default_nodes = [
            TaxonomyNode(id="sustenance", label="Food & Drink", level=0),
            TaxonomyNode(id="wellness", label="Health & Wellness", level=0),
            TaxonomyNode(id="social", label="Social Activities", level=0),
            TaxonomyNode(id="work", label="Work & Career", level=0),
            TaxonomyNode(id="routine", label="Daily Routine", level=0),
            TaxonomyNode(id="meal", label="Meal", parent_id="sustenance", level=1),
            TaxonomyNode(id="exercise", label="Exercise", parent_id="wellness", level=1),
            TaxonomyNode(id="medical", label="Medical", parent_id="wellness", level=1),
        ]

        for node in default_nodes:
            taxonomy.nodes[node.id] = node

        return taxonomy

    def resolve(self, activity: str) -> Dict[str, Any]:
        """
        Resolve activity to full hierarchical context.

        Args:
            activity: Activity label (e.g., "meal", "breakfast", "work_meeting")

        Returns:
            Dict with hierarchy path, parent category, and metadata
        """
        # Normalize activity
        activity_lower = activity.lower().replace(" ", "_")

        # Check legacy mapping first
        if activity_lower in self.taxonomy.legacy_mapping:
            mapped = self.taxonomy.legacy_mapping[activity_lower]
            activity_lower = mapped.split(".")[-1]  # Get leaf

        # Find node
        node = self.taxonomy.get_node(activity_lower)

        if not node:
            # Try partial match
            for node_id, n in self.taxonomy.nodes.items():
                if activity_lower in node_id or node_id in activity_lower:
                    node = n
                    break

        if not node:
            return {
                "activity": activity,
                "hierarchy_path": activity,
                "parent_category": None,
                "level": -1,
                "is_valid": False,
                "keywords": [],
            }

        return {
            "activity": node.id,
            "hierarchy_path": self.taxonomy.get_path(node.id),
            "parent_category": self._get_category(node),
            "level": node.level,
            "is_valid": True,
            "keywords": list(self.taxonomy.get_all_keywords(node.id)),
            "label": node.label,
            "description": node.description,
        }

    def _get_category(self, node: TaxonomyNode) -> Optional[str]:
        """Get top-level category for node."""
        if node.level == 0:
            return node.id

        ancestors = self.taxonomy.get_ancestors(node.id)
        for ancestor in reversed(ancestors):
            if ancestor.level == 0:
                return ancestor.id

        return node.parent_id

    def get_category_activities(self, category: str) -> List[str]:
        """Get all activities (level 1) under a category."""
        node = self.taxonomy.get_node(category)
        if not node or node.level != 0:
            return []

        activities = []
        for child_id in node.children_ids:
            child = self.taxonomy.get_node(child_id)
            if child and child.level == 1:
                activities.append(child.id)
        return activities

    def get_subtypes(self, activity: str) -> List[str]:
        """Get all subtypes (level 2) under an activity."""
        node = self.taxonomy.get_node(activity)
        if not node:
            return []
        return node.children_ids

    def get_siblings(self, activity: str) -> List[str]:
        """Get sibling activities (same parent)."""
        node = self.taxonomy.get_node(activity)
        if not node or not node.parent_id:
            return []

        parent = self.taxonomy.get_node(node.parent_id)
        if not parent:
            return []

        return [cid for cid in parent.children_ids if cid != activity]

    def is_valid_activity(self, activity: str) -> bool:
        """Check if activity exists in taxonomy."""
        activity_lower = activity.lower().replace(" ", "_")
        return activity_lower in self.taxonomy.nodes

    def get_all_activities(self) -> List[str]:
        """Get all activity IDs at level 1."""
        return [node_id for node_id, node in self.taxonomy.nodes.items() if node.level == 1]

    def get_all_categories(self) -> List[str]:
        """Get all category IDs at level 0."""
        return self.taxonomy.categories

    def search_by_keyword(self, keyword: str) -> List[str]:
        """Find activities containing keyword."""
        keyword_lower = keyword.lower()
        matches = []

        for node_id, node in self.taxonomy.nodes.items():
            if keyword_lower in node.id or keyword_lower in node.label.lower():
                matches.append(node_id)
            elif any(keyword_lower in kw.lower() for kw in node.keywords):
                matches.append(node_id)

        return matches


# Module-level singleton
_resolver: Optional[HierarchicalActivityResolver] = None


def get_resolver() -> HierarchicalActivityResolver:
    """Get or create module-level resolver singleton."""
    global _resolver
    if _resolver is None:
        _resolver = HierarchicalActivityResolver()
    return _resolver


def resolve_activity_hierarchy(activity: str) -> Dict[str, Any]:
    """
    Convenience function to resolve activity to hierarchy.

    Args:
        activity: Activity label

    Returns:
        Dict with hierarchy path, parent category, and metadata
    """
    resolver = get_resolver()
    return resolver.resolve(activity)
