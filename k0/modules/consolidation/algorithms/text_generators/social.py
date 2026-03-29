"""
SocialTextGenerator — GAP-001 Milestone 2

Generates embeddable text for st_social (social memory) records.
Relationships represent connections between family members and others.

GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING.md §4
Milestone: GAP_001_MILESTONE_2_SUMMARY_GENERATOR.md Issue 2.5

Template: "{person_a} {relationship_type} {person_b}: {description}"

Strategy: TEMPLATE (relationships are already structured)

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from k0.modules.consolidation.algorithms.embedding_text_generator import (
    EmbeddingTextGenerator,
    GeneratedText,
    TextGenerationStrategy,
)


class SocialTextGenerator(EmbeddingTextGenerator):
    """
    Generate embedding text for st_social (social memory) records.

    Relationships capture:
    - Person identifiers (who is connected)
    - Relationship type (family, friend, colleague)
    - Relationship quality/strength
    - Key shared experiences
    - Communication patterns

    Template:
        "{person_a} {relationship_type} {person_b}: {description}"

    Example Output:
        "Sarah is mother of Emma: Close relationship, daily contact,
        shared activities include cooking and gardening"
    """

    @property
    def layer(self) -> str:
        return "st_social"

    def generate(
        self,
        record_data: Dict[str, Any],
        source_texts: Optional[List[str]] = None,
    ) -> GeneratedText:
        """
        Generate embedding text for a relationship record.

        Args:
            record_data: Relationship columns including:
                - relationship_id: Relationship identifier
                - family_id: Family context
                - person_a_id: First person ID
                - person_a_name: First person name
                - person_b_id: Second person ID
                - person_b_name: Second person name
                - relationship_type: Type of relationship
                - description: Optional description
                - strength: Relationship strength (0-1)
                - shared_activities: Activities done together
                - communication_frequency: How often they communicate
            source_texts: Original texts mentioning both people

        Returns:
            GeneratedText with embedding_text and source_texts_json
        """
        texts = source_texts or []
        record_id = str(record_data.get("relationship_id", ""))

        # Get person names - accept person_a_name, person_a_id, or actor_a_id (DB schema)
        person_a = (
            record_data.get("person_a_name")
            or record_data.get("person_a_id")
            or record_data.get("actor_a_id")
            or "Person A"
        )
        person_b = (
            record_data.get("person_b_name")
            or record_data.get("person_b_id")
            or record_data.get("actor_b_id")
            or "Person B"
        )

        # Get and humanize relationship type
        rel_type = record_data.get("relationship_type", "connected to")
        rel_type = self._humanize_relationship(rel_type)

        # Get description
        description = record_data.get("description", "")

        # Build shared activities
        activities = self._build_shared_activities(record_data)

        # Build communication pattern
        communication = self._build_communication_pattern(record_data)

        # Build strength descriptor
        strength_desc = self._build_strength_description(record_data)

        # Assemble using template
        parts = [f"{person_a} {rel_type} {person_b}"]

        detail_parts = []
        if strength_desc:
            detail_parts.append(strength_desc)
        if description:
            detail_parts.append(description)
        if communication:
            detail_parts.append(communication)
        if activities:
            detail_parts.append(f"shared activities include {activities}")

        if detail_parts:
            parts.append(", ".join(detail_parts))

        embedding_text = ": ".join(parts) if len(parts) > 1 else parts[0]
        embedding_text = self._truncate(self._clean_text(embedding_text))

        return GeneratedText(
            embedding_text=embedding_text,
            source_texts_json=self._source_texts_to_json(texts),
            strategy_used=TextGenerationStrategy.TEMPLATE,
            layer=self.layer,
            record_id=record_id,
        )

    def _humanize_relationship(self, rel_type: str) -> str:
        """Convert relationship type to natural language."""
        mappings = {
            "parent": "is parent of",
            "child": "is child of",
            "mother": "is mother of",
            "father": "is father of",
            "sibling": "is sibling of",
            "brother": "is brother of",
            "sister": "is sister of",
            "spouse": "is spouse of",
            "partner": "is partner of",
            "friend": "is friend of",
            "colleague": "is colleague of",
            "neighbor": "is neighbor of",
            "grandparent": "is grandparent of",
            "grandchild": "is grandchild of",
            "aunt": "is aunt of",
            "uncle": "is uncle of",
            "cousin": "is cousin of",
        }
        return mappings.get(rel_type.lower(), f"is {rel_type.replace('_', ' ')} of")

    def _build_shared_activities(self, record_data: Dict[str, Any]) -> str:
        """Build shared activities string."""
        # Accept both 'shared_activities' (expected) and 'typical_activities_json' (DB schema)
        activities = self._parse_json_field(record_data, "shared_activities")
        if not activities:
            activities = self._parse_json_field(record_data, "typical_activities_json")

        if isinstance(activities, list) and activities:
            activity_strs = [str(a) for a in activities[:4] if a]
            if len(activity_strs) == 1:
                return activity_strs[0]
            elif len(activity_strs) == 2:
                return f"{activity_strs[0]} and {activity_strs[1]}"
            else:
                return ", ".join(activity_strs[:-1]) + f", and {activity_strs[-1]}"

        return ""

    def _build_communication_pattern(self, record_data: Dict[str, Any]) -> str:
        """Build communication frequency description."""
        frequency = record_data.get("communication_frequency", "")

        if frequency:
            freq_lower = str(frequency).lower()
            if freq_lower in ("daily", "every day"):
                return "daily contact"
            elif freq_lower in ("weekly", "every week"):
                return "weekly contact"
            elif freq_lower in ("monthly", "every month"):
                return "monthly contact"
            elif freq_lower in ("rarely", "infrequent"):
                return "infrequent contact"
            return f"{frequency} contact"

        return ""

    def _build_strength_description(self, record_data: Dict[str, Any]) -> str:
        """Build relationship strength description."""
        # Accept 'strength' (expected), 'strength_score', or 'relationship_strength' (DB schema)
        strength = (
            record_data.get("strength")
            or record_data.get("strength_score")
            or record_data.get("relationship_strength")
        )

        if strength is not None:
            try:
                strength_val = float(strength)
                if strength_val >= 0.8:
                    return "very close relationship"
                elif strength_val >= 0.6:
                    return "close relationship"
                elif strength_val >= 0.4:
                    return "moderate relationship"
                elif strength_val >= 0.2:
                    return "distant relationship"
                else:
                    return "weak relationship"
            except (TypeError, ValueError):
                pass

        return ""
