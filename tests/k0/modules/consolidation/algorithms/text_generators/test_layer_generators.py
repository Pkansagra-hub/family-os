"""
Unit tests for layer-specific text generators.

GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING.md §4
Milestone: GAP_001_MILESTONE_2_SUMMARY_GENERATOR.md Issue 2.10

Tests for:
- SemanticTextGenerator
- ProceduralTextGenerator
- SocialTextGenerator
- ProspectiveTextGenerator
- KGEntityTextGenerator
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from k0.modules.consolidation.algorithms.embedding_text_generator import (
    TextGenerationStrategy,
)
from k0.modules.consolidation.algorithms.text_generators.kg_entity import (
    KGEntityTextGenerator,
)
from k0.modules.consolidation.algorithms.text_generators.procedural import (
    ProceduralTextGenerator,
)
from k0.modules.consolidation.algorithms.text_generators.prospective import (
    ProspectiveTextGenerator,
)
from k0.modules.consolidation.algorithms.text_generators.semantic import (
    SemanticTextGenerator,
)
from k0.modules.consolidation.algorithms.text_generators.social import (
    SocialTextGenerator,
)


class TestSemanticTextGenerator:
    """Tests for SemanticTextGenerator."""

    @pytest.fixture
    def generator(self) -> SemanticTextGenerator:
        """Create generator instance."""
        return SemanticTextGenerator()

    def test_layer_property(self, generator: SemanticTextGenerator) -> None:
        """Test layer property."""
        assert generator.layer == "st_sem"

    def test_basic_generation(self, generator: SemanticTextGenerator) -> None:
        """Test basic pattern generation."""
        record_data = {
            "pattern_id": "pat_123",
            "pattern_type": "preference",
            "description": "Prefers Thai cuisine",
        }

        result = generator.generate(record_data)

        assert result.layer == "st_sem"
        assert "Pattern" in result.embedding_text
        assert "preference" in result.embedding_text
        assert "Thai cuisine" in result.embedding_text
        assert result.strategy_used == TextGenerationStrategy.TEMPLATE

    def test_with_exemplars(self, generator: SemanticTextGenerator) -> None:
        """Test with exemplar episodes."""
        record_data = {
            "pattern_id": "pat_123",
            "pattern_type": "habit",
            "description": "Morning coffee routine",
            "exemplars": [
                {"summary": "Made pour-over coffee"},
                {"summary": "Used favorite mug"},
            ],
        }

        result = generator.generate(record_data)

        assert "habit" in result.embedding_text
        assert "Examples" in result.embedding_text
        assert "pour-over" in result.embedding_text

    def test_with_categories(self, generator: SemanticTextGenerator) -> None:
        """Test with categories."""
        record_data = {
            "pattern_id": "pat_123",
            "pattern_type": "interest",
            "description": "Likes gardening",
            "categories": ["hobbies", "outdoor", "nature"],
        }

        result = generator.generate(record_data)

        assert "Categories" in result.embedding_text
        assert "hobbies" in result.embedding_text

    def test_pattern_type_humanization(self, generator: SemanticTextGenerator) -> None:
        """Test that pattern types are humanized."""
        test_cases = [
            ("habit", "recurring habit"),
            ("concept", "learned concept"),
            ("belief", "belief or value"),
        ]

        for input_type, expected in test_cases:
            record_data = {
                "pattern_id": "test",
                "pattern_type": input_type,
                "description": "Test",
            }
            result = generator.generate(record_data)
            assert expected in result.embedding_text


class TestProceduralTextGenerator:
    """Tests for ProceduralTextGenerator."""

    @pytest.fixture
    def generator(self) -> ProceduralTextGenerator:
        """Create generator instance."""
        return ProceduralTextGenerator()

    def test_layer_property(self, generator: ProceduralTextGenerator) -> None:
        """Test layer property."""
        assert generator.layer == "st_procedural"

    def test_basic_generation(self, generator: ProceduralTextGenerator) -> None:
        """Test basic routine generation."""
        record_data = {
            "routine_id": "rtn_123",
            "routine_name": "Morning Coffee",
        }

        result = generator.generate(record_data)

        assert result.layer == "st_procedural"
        assert "Routine" in result.embedding_text
        assert "Morning Coffee" in result.embedding_text
        assert result.strategy_used == TextGenerationStrategy.TEMPLATE

    def test_with_steps(self, generator: ProceduralTextGenerator) -> None:
        """Test with ordered steps."""
        record_data = {
            "routine_id": "rtn_123",
            "routine_name": "Morning Coffee",
            "steps": [
                {"action": "Grind beans"},
                {"action": "Heat water"},
                {"action": "Pour over"},
            ],
        }

        result = generator.generate(record_data)

        assert "Steps" in result.embedding_text
        assert "Grind beans" in result.embedding_text

    def test_with_frequency(self, generator: ProceduralTextGenerator) -> None:
        """Test with frequency information."""
        record_data = {
            "routine_id": "rtn_123",
            "routine_name": "Exercise",
            "frequency": "daily",
            "typical_time": "7am",
            "typical_duration": 45,
        }

        result = generator.generate(record_data)

        assert "Frequency" in result.embedding_text
        assert "daily" in result.embedding_text
        assert "45min" in result.embedding_text

    def test_with_triggers(self, generator: ProceduralTextGenerator) -> None:
        """Test with triggers."""
        record_data = {
            "routine_id": "rtn_123",
            "routine_name": "Bedtime Routine",
            "triggers": [{"cue": "9pm alarm"}, {"cue": "yawning"}],
        }

        result = generator.generate(record_data)

        assert "Triggers" in result.embedding_text
        assert "9pm alarm" in result.embedding_text


class TestSocialTextGenerator:
    """Tests for SocialTextGenerator."""

    @pytest.fixture
    def generator(self) -> SocialTextGenerator:
        """Create generator instance."""
        return SocialTextGenerator()

    def test_layer_property(self, generator: SocialTextGenerator) -> None:
        """Test layer property."""
        assert generator.layer == "st_social"

    def test_basic_generation(self, generator: SocialTextGenerator) -> None:
        """Test basic relationship generation."""
        record_data = {
            "relationship_id": "rel_123",
            "person_a_name": "Sarah",
            "person_b_name": "Emma",
            "relationship_type": "mother",
        }

        result = generator.generate(record_data)

        assert result.layer == "st_social"
        assert "Sarah" in result.embedding_text
        assert "Emma" in result.embedding_text
        assert "mother of" in result.embedding_text
        assert result.strategy_used == TextGenerationStrategy.TEMPLATE

    def test_relationship_types(self, generator: SocialTextGenerator) -> None:
        """Test various relationship type humanizations."""
        test_cases = [
            ("parent", "is parent of"),
            ("sibling", "is sibling of"),
            ("friend", "is friend of"),
            ("colleague", "is colleague of"),
        ]

        for rel_type, expected in test_cases:
            record_data = {
                "relationship_id": "test",
                "person_a_name": "A",
                "person_b_name": "B",
                "relationship_type": rel_type,
            }
            result = generator.generate(record_data)
            assert expected in result.embedding_text

    def test_with_strength(self, generator: SocialTextGenerator) -> None:
        """Test with relationship strength."""
        record_data = {
            "relationship_id": "rel_123",
            "person_a_name": "A",
            "person_b_name": "B",
            "relationship_type": "friend",
            "strength": 0.9,
        }

        result = generator.generate(record_data)

        assert "very close" in result.embedding_text

    def test_with_shared_activities(self, generator: SocialTextGenerator) -> None:
        """Test with shared activities."""
        record_data = {
            "relationship_id": "rel_123",
            "person_a_name": "A",
            "person_b_name": "B",
            "relationship_type": "friend",
            "shared_activities": ["cooking", "hiking", "movies"],
        }

        result = generator.generate(record_data)

        assert "shared activities" in result.embedding_text
        assert "cooking" in result.embedding_text

    def test_with_communication_frequency(self, generator: SocialTextGenerator) -> None:
        """Test with communication frequency."""
        record_data = {
            "relationship_id": "rel_123",
            "person_a_name": "A",
            "person_b_name": "B",
            "relationship_type": "friend",
            "communication_frequency": "weekly",
        }

        result = generator.generate(record_data)

        assert "weekly contact" in result.embedding_text


class TestProspectiveTextGenerator:
    """Tests for ProspectiveTextGenerator."""

    @pytest.fixture
    def generator(self) -> ProspectiveTextGenerator:
        """Create generator instance."""
        return ProspectiveTextGenerator()

    def test_layer_property(self, generator: ProspectiveTextGenerator) -> None:
        """Test layer property."""
        assert generator.layer == "st_prospective"

    def test_basic_generation(self, generator: ProspectiveTextGenerator) -> None:
        """Test basic intention generation."""
        record_data = {
            "intention_id": "int_123",
            "action": "Call mom for birthday",
        }

        result = generator.generate(record_data)

        assert result.layer == "st_prospective"
        assert "Intention" in result.embedding_text
        assert "Call mom" in result.embedding_text
        assert result.strategy_used == TextGenerationStrategy.TEMPLATE

    def test_with_deadline(self, generator: ProspectiveTextGenerator) -> None:
        """Test with deadline timestamp."""
        # March 15 next year
        deadline = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
        record_data = {
            "intention_id": "int_123",
            "action": "Send gift",
            "deadline_ts": int(deadline.timestamp() * 1000),
        }

        result = generator.generate(record_data)

        assert "March 15" in result.embedding_text

    def test_with_priority(self, generator: ProspectiveTextGenerator) -> None:
        """Test with priority level."""
        record_data = {
            "intention_id": "int_123",
            "action": "Important task",
            "priority": "high",
        }

        result = generator.generate(record_data)

        assert "Priority: high" in result.embedding_text

    def test_with_conditions(self, generator: ProspectiveTextGenerator) -> None:
        """Test with triggering conditions."""
        record_data = {
            "intention_id": "int_123",
            "action": "Take medicine",
            "conditions": ["after breakfast", "with water"],
        }

        result = generator.generate(record_data)

        assert "Context" in result.embedding_text
        assert "after breakfast" in result.embedding_text

    def test_with_status(self, generator: ProspectiveTextGenerator) -> None:
        """Test with status."""
        record_data = {
            "intention_id": "int_123",
            "action": "Completed task",
            "status": "completed",
        }

        result = generator.generate(record_data)

        assert "Status: completed" in result.embedding_text


class TestKGEntityTextGenerator:
    """Tests for KGEntityTextGenerator."""

    @pytest.fixture
    def generator(self) -> KGEntityTextGenerator:
        """Create generator instance."""
        return KGEntityTextGenerator()

    def test_layer_property(self, generator: KGEntityTextGenerator) -> None:
        """Test layer property."""
        assert generator.layer == "st_kg_dom"

    def test_basic_generation(self, generator: KGEntityTextGenerator) -> None:
        """Test basic entity generation."""
        record_data = {
            "entity_id": "ent_123",
            "entity_type": "person",
            "name": "Grandma Rose",
        }

        result = generator.generate(record_data)

        assert result.layer == "st_kg_dom"
        assert "Person" in result.embedding_text
        assert "Grandma Rose" in result.embedding_text
        assert result.strategy_used == TextGenerationStrategy.TEMPLATE

    def test_with_aliases(self, generator: KGEntityTextGenerator) -> None:
        """Test with aliases."""
        record_data = {
            "entity_id": "ent_123",
            "entity_type": "person",
            "name": "Robert",
            "aliases": ["Bob", "Bobby"],
        }

        result = generator.generate(record_data)

        assert "also known as" in result.embedding_text
        assert "Bob" in result.embedding_text

    def test_with_description(self, generator: KGEntityTextGenerator) -> None:
        """Test with description."""
        record_data = {
            "entity_id": "ent_123",
            "entity_type": "place",
            "name": "Grandma's House",
            "description": "Victorian home with large garden",
        }

        result = generator.generate(record_data)

        assert "Victorian home" in result.embedding_text

    def test_with_relationships(self, generator: KGEntityTextGenerator) -> None:
        """Test with relationships."""
        record_data = {
            "entity_id": "ent_123",
            "entity_type": "person",
            "name": "Grandma",
            "relationships": [
                {"type": "mother of", "target": "Sarah"},
                {"type": "grandmother of", "target": "Emma"},
            ],
        }

        result = generator.generate(record_data)

        assert "Relationships" in result.embedding_text
        assert "mother of Sarah" in result.embedding_text

    def test_entity_type_humanization(self, generator: KGEntityTextGenerator) -> None:
        """Test entity type capitalization."""
        test_cases = [
            ("person", "Person"),
            ("place", "Place"),
            ("organization", "Organization"),
            ("event_type", "Event Type"),
        ]

        for input_type, expected in test_cases:
            record_data = {
                "entity_id": "test",
                "entity_type": input_type,
                "name": "Test",
            }
            result = generator.generate(record_data)
            assert expected in result.embedding_text

    def test_with_edges_field(self, generator: KGEntityTextGenerator) -> None:
        """Test with edges field instead of relationships."""
        record_data = {
            "entity_id": "ent_123",
            "entity_type": "person",
            "name": "John",
            "edges": [
                {"predicate": "works at", "object": "Acme Corp"},
            ],
        }

        result = generator.generate(record_data)

        assert "works at Acme Corp" in result.embedding_text
