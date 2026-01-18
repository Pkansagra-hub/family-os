"""
SemanticTextGenerator — GAP-001 Milestone 2

Generates embeddable text for st_sem (semantic memory) records.
Patterns represent recurring themes, preferences, and learned concepts.

GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING.md §4
Milestone: GAP_001_MILESTONE_2_SUMMARY_GENERATOR.md Issue 2.3

Template: "Pattern: {pattern_type} - {description}. Examples: {exemplars}"

Strategy: TEMPLATE (patterns are already structured)

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from k0.modules.consolidation.algorithms.embedding_text_generator import (
    EmbeddingTextGenerator,
    GeneratedText,
    TextGenerationStrategy,
)


class SemanticTextGenerator(EmbeddingTextGenerator):
    """
    Generate embedding text for st_sem (semantic memory) records.

    Patterns represent abstracted knowledge:
    - Pattern type (preference, habit, concept, belief)
    - Description of the pattern
    - Exemplar episodes that demonstrate the pattern
    - Confidence score

    Template:
        "Pattern: {pattern_type} - {description}. Examples: {exemplars}"

    Example Output:
        "Pattern: food preference - Prefers Thai cuisine, especially
        pad thai and green curry. Examples: Dinner at Thai Orchid,
        Ordered Thai takeout, Cooked Thai at home"
    """

    @property
    def layer(self) -> str:
        return "st_sem"

    def generate(
        self,
        record_data: Dict[str, Any],
        source_texts: Optional[List[str]] = None,
    ) -> GeneratedText:
        """
        Generate embedding text for a pattern record.

        Args:
            record_data: Pattern columns including:
                - pattern_id: Pattern identifier
                - family_id: Family context
                - pattern_type: Type of pattern (preference, habit, etc.)
                - description: Human-readable description
                - exemplars: Example episodes/events
                - confidence: Confidence score (0-1)
                - categories: Optional category tags
            source_texts: Original texts that led to pattern discovery

        Returns:
            GeneratedText with embedding_text and source_texts_json
        """
        texts = source_texts or []
        record_id = str(record_data.get("pattern_id", ""))

        # Build pattern type
        pattern_type = record_data.get("pattern_type", "general")
        pattern_type = self._humanize_pattern_type(pattern_type)

        # Get description (try both field names)
        description = (
            record_data.get("description")
            or record_data.get("pattern_description")
            or record_data.get("canonical_name")
            or record_data.get("pattern_name")
            or ""
        )
        if not description:
            description = self._infer_description(record_data)

        # Build exemplars string
        exemplars = self._build_exemplars(record_data)

        # Get categories if available
        categories = self._build_categories(record_data)

        # Assemble using template
        parts = [f"Pattern: {pattern_type}"]

        if description:
            parts[0] += f" - {description}"

        if exemplars:
            parts.append(f"Examples: {exemplars}")

        if categories:
            parts.append(f"Categories: {categories}")

        embedding_text = ". ".join(parts)
        embedding_text = self._truncate(self._clean_text(embedding_text))

        return GeneratedText(
            embedding_text=embedding_text,
            source_texts_json=self._source_texts_to_json(texts),
            strategy_used=TextGenerationStrategy.TEMPLATE,
            layer=self.layer,
            record_id=record_id,
        )

    def _humanize_pattern_type(self, pattern_type: str) -> str:
        """Convert pattern type to human-readable form."""
        mappings = {
            "preference": "preference",
            "habit": "recurring habit",
            "concept": "learned concept",
            "belief": "belief or value",
            "skill": "skill or ability",
            "routine": "routine pattern",
            "interest": "area of interest",
        }
        return mappings.get(pattern_type.lower(), pattern_type.replace("_", " "))

    def _infer_description(self, record_data: Dict[str, Any]) -> str:
        """Infer description from other fields if missing."""
        # Try to build from available fields
        subject = record_data.get("subject", "")
        predicate = record_data.get("predicate", "")
        obj = record_data.get("object", "")

        if subject and predicate:
            if obj:
                return f"{subject} {predicate} {obj}"
            return f"{subject} {predicate}"

        return ""

    def _build_exemplars(self, record_data: Dict[str, Any]) -> str:
        """Build exemplars string from record data."""
        exemplars = self._parse_json_field(record_data, "exemplars")

        if not exemplars:
            # Try alternative field names
            exemplars = self._parse_json_field(record_data, "examples")

        if isinstance(exemplars, list):
            # Take first 3 exemplars
            exemplar_strs = []
            for ex in exemplars[:3]:
                if isinstance(ex, dict):
                    # Extract summary or description from dict
                    ex_str = ex.get("summary") or ex.get("description") or ex.get("text", "")
                    if ex_str:
                        exemplar_strs.append(str(ex_str))
                elif isinstance(ex, str):
                    exemplar_strs.append(ex)

            if exemplar_strs:
                return ", ".join(exemplar_strs)

        return ""

    def _build_categories(self, record_data: Dict[str, Any]) -> str:
        """Build categories string."""
        categories = self._parse_json_field(record_data, "categories")

        if isinstance(categories, list) and categories:
            return ", ".join(str(c) for c in categories[:5])

        return ""
