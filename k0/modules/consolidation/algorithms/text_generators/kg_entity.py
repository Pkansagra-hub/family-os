"""
KGEntityTextGenerator — GAP-001 Milestone 2

Generates embeddable text for st_kg_dom (knowledge graph domain) records.
Entities represent people, places, things, and concepts in the family's world.

GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING.md §4
Milestone: GAP_001_MILESTONE_2_SUMMARY_GENERATOR.md Issue 2.7

Template: "{entity_type}: {name}. {description}. Relationships: {relations}"

Strategy: TEMPLATE (entities are already structured)

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from k0.modules.consolidation.algorithms.embedding_text_generator import (
    EmbeddingTextGenerator,
    GeneratedText,
    TextGenerationStrategy,
)


class KGEntityTextGenerator(EmbeddingTextGenerator):
    """
    Generate embedding text for st_kg_dom (knowledge graph) records.

    Entities represent nodes in the family knowledge graph:
    - Entity type (person, place, thing, concept)
    - Entity name and aliases
    - Description and attributes
    - Relationships to other entities
    - Provenance (source events/episodes)

    Template:
        "{entity_type}: {name}. {description}. Relationships: {relations}"

    Example Output:
        "Person: Grandma Rose. Family matriarch, loves gardening and
        baking. Relationships: mother of Sarah, grandmother of Emma,
        lives at 123 Oak Street"
    """

    @property
    def layer(self) -> str:
        return "st_kg_dom"

    def generate(
        self,
        record_data: Dict[str, Any],
        source_texts: Optional[List[str]] = None,
    ) -> GeneratedText:
        """
        Generate embedding text for an entity record.

        Args:
            record_data: Entity columns including:
                - entity_id: Entity identifier
                - family_id: Family context
                - entity_type: Type of entity (person, place, etc.)
                - name: Entity name
                - aliases: Alternative names
                - description: Human-readable description
                - attributes: Key-value attributes
                - relationships: Connections to other entities
            source_texts: Original texts mentioning this entity

        Returns:
            GeneratedText with embedding_text and source_texts_json
        """
        texts = source_texts or []
        record_id = str(record_data.get("entity_id", ""))

        # Get entity type
        entity_type = record_data.get("entity_type", "Entity")
        entity_type = self._humanize_entity_type(entity_type)

        # Get name and aliases - accept 'name', 'label', or 'canonical_name' (schema)
        name = (
            record_data.get("name")
            or record_data.get("label")
            or record_data.get("canonical_name")
            or "Unknown"
        )
        # Pass name to exclude from aliases (avoid "parents (also known as parents)")
        aliases = self._build_aliases(record_data, exclude_name=name)

        # Get description
        description = record_data.get("description", "")
        if not description:
            description = self._build_description_from_attributes(record_data)

        # Build relationships string
        relationships = self._build_relationships(record_data)

        # Assemble using template
        name_part = name
        if aliases:
            name_part += f" (also known as {aliases})"

        parts = [f"{entity_type}: {name_part}"]

        if description:
            parts.append(description)

        if relationships:
            parts.append(f"Relationships: {relationships}")

        embedding_text = ". ".join(parts)
        embedding_text = self._truncate(self._clean_text(embedding_text))

        return GeneratedText(
            embedding_text=embedding_text,
            source_texts_json=self._source_texts_to_json(texts),
            strategy_used=TextGenerationStrategy.TEMPLATE,
            layer=self.layer,
            record_id=record_id,
        )

    def _humanize_entity_type(self, entity_type: str) -> str:
        """Convert entity type to capitalized form."""
        mappings = {
            "person": "Person",
            "place": "Place",
            "location": "Location",
            "thing": "Thing",
            "object": "Object",
            "concept": "Concept",
            "event_type": "Event Type",
            "organization": "Organization",
            "animal": "Animal",
            "food": "Food",
            "activity": "Activity",
        }
        return mappings.get(entity_type.lower(), entity_type.title().replace("_", " "))

    def _build_aliases(self, record_data: Dict[str, Any], exclude_name: str = "") -> str:
        """Build aliases string, excluding the canonical name to avoid redundancy."""
        aliases = self._parse_json_field(record_data, "aliases")
        if not aliases:
            aliases = self._parse_json_field(record_data, "aliases_json")

        if isinstance(aliases, list) and aliases:
            # Filter out the canonical name and empty values
            exclude_lower = exclude_name.lower() if exclude_name else ""
            alias_strs = [str(a) for a in aliases[:4] if a and str(a).lower() != exclude_lower]
            if alias_strs:
                return ", ".join(alias_strs[:3])

        return ""

    def _build_description_from_attributes(self, record_data: Dict[str, Any]) -> str:
        """Build description from attributes if no explicit description."""
        # Accept both 'attributes' (expected) and 'attributes_json' (schema)
        attributes = self._parse_json_field(record_data, "attributes", default={})
        if not attributes:
            attributes = self._parse_json_field(record_data, "attributes_json", default={})

        if not isinstance(attributes, dict):
            return ""

        desc_parts = []
        for key, value in list(attributes.items())[:5]:
            if value and key not in ("id", "created_at", "updated_at"):
                # Convert snake_case to readable
                readable_key = key.replace("_", " ")
                desc_parts.append(f"{readable_key}: {value}")

        return ", ".join(desc_parts)

    def _build_relationships(self, record_data: Dict[str, Any]) -> str:
        """Build relationships string."""
        relationships = self._parse_json_field(record_data, "relationships")

        if isinstance(relationships, list):
            rel_strs = []
            for rel in relationships[:5]:
                if isinstance(rel, dict):
                    rel_type = rel.get("type", "") or rel.get("relationship_type", "")
                    target = (
                        rel.get("target", "") or rel.get("target_name", "") or rel.get("name", "")
                    )
                    if rel_type and target:
                        rel_strs.append(f"{rel_type} {target}")
                    elif target:
                        rel_strs.append(f"connected to {target}")
                elif isinstance(rel, str):
                    rel_strs.append(rel)

            if rel_strs:
                return ", ".join(rel_strs)

        # Try edges field (alternative name)
        edges = self._parse_json_field(record_data, "edges")
        if isinstance(edges, list) and edges:
            edge_strs = []
            for edge in edges[:5]:
                if isinstance(edge, dict):
                    predicate = edge.get("predicate", "")
                    obj = edge.get("object", "") or edge.get("target", "")
                    if predicate and obj:
                        edge_strs.append(f"{predicate} {obj}")

            if edge_strs:
                return ", ".join(edge_strs)

        return ""
