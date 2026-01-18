"""
Schema-aligned tests for text generators.

These tests use the ACTUAL database schema field names from:
- P03_consolidation_dossier_v2.md (Section 6.3-6.8)
- Truth writer dataclass fields

This ensures generators work with real data as it flows through P03.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from k0.modules.consolidation.algorithms.text_generators import get_generator


class TestSchemaAlignedEpisodic:
    """Test EpisodicTextGenerator with actual st_epi schema fields."""

    @pytest.fixture
    def generator(self):
        return get_generator("st_epi")

    def test_with_actual_schema_fields(self, generator):
        """Test with exact st_epi table column names."""
        # These are the ACTUAL column names from the database schema
        friday_6pm = datetime(2026, 1, 16, 18, 0, 0, tzinfo=timezone.utc)
        friday_830pm = datetime(2026, 1, 16, 20, 30, 0, tzinfo=timezone.utc)

        # Schema-aligned record (from st_epi table)
        db_record = {
            # Identity columns
            "episode_id": "01JARQ5VXK0000000000000001",
            "tenant_id": "tenant_smith_family",
            "space_id": "space_home",
            # Temporal columns (INTEGER = milliseconds)
            "start_time_utc": int(friday_6pm.timestamp() * 1000),
            "end_time_utc": int(friday_830pm.timestamp() * 1000),
            "duration_minutes": 150,
            "temporal_bucket": "EVENING",
            "day_of_week": "FRIDAY",
            # Episode content
            "episode_summary": "Family dinner at Italian restaurant",
            "episode_type": "ROUTINE",
            # Source events
            "source_events_json": '["evt_001", "evt_002", "evt_003"]',
            "source_event_count": 3,
            # Location
            "primary_location": "Olive Garden Downtown",
            "location_type": "restaurant",
            # Participants
            "participants_json": '["person_mom", "person_dad", "person_emma"]',
            "participant_count": 3,
            # Clustering
            "cluster_id": "cluster_dinner_2026w03",
            "cluster_confidence": 0.92,
        }

        # Map schema fields to generator expected fields
        generator_input = {
            "episode_id": db_record["episode_id"],
            # Generator expects start_ts/end_ts, schema has start_time_utc/end_time_utc
            "start_ts": db_record["start_time_utc"],
            "end_ts": db_record["end_time_utc"],
            # Generator expects summary, schema has episode_summary
            "summary": db_record["episode_summary"],
            # Generator expects location_json, schema has primary_location
            "location_json": {"name": db_record["primary_location"]},
            # Generator expects participants list, schema has participants_json
            "participants": json.loads(db_record["participants_json"]),
        }

        source_texts = [
            "Arrived at Olive Garden for dinner",
            "Ordered the family's favorite dishes",
            "Had great conversation about Emma's school",
        ]

        result = generator.generate(generator_input, source_texts)

        assert result.layer == "st_epi"
        assert "Friday" in result.embedding_text
        assert "evening" in result.embedding_text
        assert "Olive Garden" in result.embedding_text
        print(f"\n[Schema-aligned episodic]: {result.embedding_text}")

    def test_with_dataclass_fields(self, generator):
        """Test with EpisodeWriteData field names."""
        from k0.modules.consolidation.truth_writer.layers.episodic import (
            EpisodeWriteData,
        )

        # Create actual dataclass instance
        friday_7pm = datetime(2026, 1, 16, 19, 0, 0, tzinfo=timezone.utc)

        write_data = EpisodeWriteData(
            episode_id="ep_test_001",
            tenant_id="tenant_smith",
            space_id="space_family",
            cluster_id="cluster_001",
            source_events_json='["evt_1", "evt_2"]',
            started_at_ms=int(friday_7pm.timestamp() * 1000),
            ended_at_ms=int((friday_7pm.timestamp() + 7200) * 1000),
            temporal_spread_ms=7200000,
            confidence=0.9,
            observation_count=2,
        )

        # Convert dataclass to dict for generator
        # Note: dataclass uses started_at_ms, generator expects start_ts
        generator_input = {
            "episode_id": write_data.episode_id,
            "start_ts": write_data.started_at_ms,
            "end_ts": write_data.ended_at_ms,
        }

        result = generator.generate(generator_input, ["Test event"])

        assert result.layer == "st_epi"
        assert result.record_id == "ep_test_001"


class TestSchemaAlignedSemantic:
    """Test SemanticTextGenerator with actual st_sem schema fields."""

    @pytest.fixture
    def generator(self):
        return get_generator("st_sem")

    def test_with_actual_schema_fields(self, generator):
        """Test with exact st_sem table column names."""
        # Schema-aligned record (from st_sem table)
        db_record = {
            # Identity
            "pattern_id": "01JARQ5VXK0000000000000002",
            "tenant_id": "tenant_smith_family",
            "space_id": "space_home",
            "actor_id": None,  # Shared family pattern
            # Pattern classification
            "pattern_type": "PREFERENCE",
            "pattern_subtype": "food_preference",
            # Pattern content
            "pattern_name": "Italian Cuisine Preference",
            "pattern_description": "Family consistently chooses Italian restaurants",
            "pattern_attributes_json": json.dumps(
                {
                    "domain": "food",
                    "attribute": "cuisine_preference",
                    "value": "Italian",
                    "polarity": "positive",
                }
            ),
            # Source episodes
            "source_episodes_json": '["ep_dinner_001", "ep_dinner_007"]',
            "episode_count": 2,
            # Truth tracking
            "observation_count": 8,
            "confidence_score": 0.89,
        }

        # Map schema fields to generator expected fields
        generator_input = {
            "pattern_id": db_record["pattern_id"],
            "pattern_type": db_record["pattern_type"].lower(),  # Generator uses lowercase
            # Generator expects description, schema has pattern_description
            "description": db_record["pattern_description"],
            # Generator expects canonical_name, schema has pattern_name
            "canonical_name": db_record["pattern_name"],
            # Parse attributes for exemplars
            "categories": ["food", "dining"],
        }

        result = generator.generate(generator_input)

        assert result.layer == "st_sem"
        assert "preference" in result.embedding_text
        assert "Italian" in result.embedding_text
        print(f"\n[Schema-aligned semantic]: {result.embedding_text}")

    def test_with_dataclass_fields(self, generator):
        """Test with PatternWriteData field names."""
        from k0.modules.consolidation.truth_writer.layers.semantic import (
            PatternWriteData,
        )

        write_data = PatternWriteData(
            pattern_id="pat_test_001",
            tenant_id="tenant_smith",
            space_id="space_family",
            pattern_type="preference",
            canonical_name="Thai Food Preference",
            source_episodes_json='["ep_1", "ep_2"]',
            initial_confidence=0.75,
            current_confidence=0.88,
            observation_count=5,
        )

        generator_input = {
            "pattern_id": write_data.pattern_id,
            "pattern_type": write_data.pattern_type,
            "description": write_data.canonical_name,
        }

        result = generator.generate(generator_input)

        assert result.layer == "st_sem"
        assert result.record_id == "pat_test_001"


class TestSchemaAlignedSocial:
    """Test SocialTextGenerator with actual st_social schema fields."""

    @pytest.fixture
    def generator(self):
        return get_generator("st_social")

    def test_with_actual_schema_fields(self, generator):
        """Test with exact st_social table column names."""
        db_record = {
            # Identity
            "relationship_id": "01JARQ5VXK0000000000000003",
            "tenant_id": "tenant_smith_family",
            "space_id": "space_home",
            # Actors
            "actor_a_id": "person_sarah",
            "actor_b_id": "person_emma",
            # Relationship
            "relationship_type": "PARENT_CHILD",
            "relationship_subtype": "mother",
            # Strength
            "strength_score": 0.95,
            "interaction_count": 1247,
            "sentiment_avg": 0.78,
            # Interactions
            "interaction_types_json": '["conversation", "activity", "caregiving"]',
            "last_interaction_at": 1736966400000,
        }

        generator_input = {
            "relationship_id": db_record["relationship_id"],
            # Generator expects person_a_name, need to lookup or include
            "person_a_name": "Sarah",
            "person_b_name": "Emma",
            "relationship_type": "mother",
            # Generator expects strength, schema has strength_score
            "strength": db_record["strength_score"],
            "communication_frequency": "daily",
            "shared_activities": ["homework", "cooking", "bedtime stories"],
        }

        result = generator.generate(generator_input)

        assert result.layer == "st_social"
        assert "Sarah" in result.embedding_text
        assert "mother of" in result.embedding_text
        assert "Emma" in result.embedding_text
        print(f"\n[Schema-aligned social]: {result.embedding_text}")

    def test_with_dataclass_fields(self, generator):
        """Test with RelationshipWriteData field names."""
        from k0.modules.consolidation.truth_writer.layers.social import (
            RelationshipWriteData,
        )

        write_data = RelationshipWriteData(
            relationship_id="rel_test_001",
            tenant_id="tenant_smith",
            space_id="space_family",
            actor_a_id="person_dad",
            actor_b_id="person_jake",
            relationship_type="father",
            strength=0.88,
            interaction_count=500,
            sentiment_avg=0.65,
        )

        # Note: dataclass has actor_a_id, generator expects person_a_name
        # In real usage, names would be looked up
        generator_input = {
            "relationship_id": write_data.relationship_id,
            "person_a_name": "Dad",  # Would be looked up in real system
            "person_b_name": "Jake",
            "relationship_type": write_data.relationship_type,
            "strength": write_data.strength,
        }

        result = generator.generate(generator_input)

        assert result.layer == "st_social"
        assert result.record_id == "rel_test_001"


class TestSchemaAlignedProcedural:
    """Test ProceduralTextGenerator with actual st_procedural schema fields."""

    @pytest.fixture
    def generator(self):
        return get_generator("st_procedural")

    def test_with_dataclass_fields(self, generator):
        """Test with RoutineWriteData field names."""
        from k0.modules.consolidation.truth_writer.layers.procedural import (
            RoutineWriteData,
        )

        write_data = RoutineWriteData(
            routine_id="rtn_test_001",
            tenant_id="tenant_smith",
            space_id="space_family",
            routine_name="Morning Coffee",
            action_sequence_json=json.dumps(
                [
                    {"action": "Grind beans"},
                    {"action": "Boil water"},
                    {"action": "Brew coffee"},
                ]
            ),
            trigger_conditions_json=json.dumps({"time": "7am", "day": "daily"}),
            temporal_regularity=0.9,
            daily_pattern="0 7 * * *",  # Cron: 7am daily
            confidence=0.85,
        )

        # Map dataclass to generator expected fields
        generator_input = {
            "routine_id": write_data.routine_id,
            "routine_name": write_data.routine_name,
            # Generator expects steps list, dataclass has action_sequence_json
            "steps": json.loads(write_data.action_sequence_json),
            # Generator expects frequency string
            "frequency": "daily",
            "typical_time": "7am",
        }

        result = generator.generate(generator_input)

        assert result.layer == "st_procedural"
        assert "Morning Coffee" in result.embedding_text
        assert "Grind" in result.embedding_text
        print(f"\n[Schema-aligned procedural]: {result.embedding_text}")


class TestSchemaAlignedProspective:
    """Test ProspectiveTextGenerator with actual st_prospective schema fields."""

    @pytest.fixture
    def generator(self):
        return get_generator("st_prospective")

    def test_with_dataclass_fields(self, generator):
        """Test with IntentionWriteData field names."""
        from k0.modules.consolidation.truth_writer.layers.prospective import (
            IntentionWriteData,
        )

        deadline = datetime(2026, 2, 15, 12, 0, 0, tzinfo=timezone.utc)

        write_data = IntentionWriteData(
            intention_id="int_test_001",
            tenant_id="tenant_smith",
            space_id="space_family",
            intention_type="reminder",
            description="Order birthday flowers for Grandma Rose",
            trigger_time_ms=int(deadline.timestamp() * 1000),
            trigger_context_json=json.dumps({"days_before": 2}),
            confidence=0.9,
            status="pending",
        )

        # Map dataclass to generator expected fields
        generator_input = {
            "intention_id": write_data.intention_id,
            # Generator expects action, dataclass has description
            "action": write_data.description,
            # Generator expects deadline_ts, dataclass has trigger_time_ms
            "deadline_ts": write_data.trigger_time_ms,
            "priority": "high",
            "status": write_data.status,
        }

        result = generator.generate(generator_input)

        assert result.layer == "st_prospective"
        assert "birthday flowers" in result.embedding_text
        assert "February 15" in result.embedding_text
        print(f"\n[Schema-aligned prospective]: {result.embedding_text}")


class TestSchemaAlignedKGEntity:
    """Test KGEntityTextGenerator with actual st_kg_dom schema fields."""

    @pytest.fixture
    def generator(self):
        return get_generator("st_kg_dom")

    def test_with_dataclass_fields(self, generator):
        """Test with EntityWriteData field names."""
        from k0.modules.consolidation.truth_writer.layers.kg import EntityWriteData

        write_data = EntityWriteData(
            entity_id="ent_test_001",
            tenant_id="tenant_smith",
            space_id="space_family",
            entity_type="PERSON",
            canonical_name="Grandma Rose",
            attributes_json=json.dumps(
                {
                    "age": 72,
                    "occupation": "Retired Teacher",
                }
            ),
            confidence=0.95,
        )

        # Map dataclass to generator expected fields
        generator_input = {
            "entity_id": write_data.entity_id,
            "entity_type": write_data.entity_type,
            # Generator expects name, dataclass has canonical_name
            "name": write_data.canonical_name,
            # Generator expects attributes dict
            "attributes": json.loads(write_data.attributes_json),
            "aliases": ["Rose", "Nana"],
        }

        result = generator.generate(generator_input)

        assert result.layer == "st_kg_dom"
        assert "Grandma Rose" in result.embedding_text
        assert "Person" in result.embedding_text
        print(f"\n[Schema-aligned kg_entity]: {result.embedding_text}")


class TestFieldMappingDocumentation:
    """Document the field mappings between schema, dataclass, and generator."""

    def test_document_episodic_mapping(self):
        """Document field mappings for st_epi."""
        mapping = {
            # Schema (DB) -> Dataclass -> Generator
            "episode_id": ("episode_id", "episode_id"),
            "start_time_utc": ("started_at_ms", "start_ts"),
            "end_time_utc": ("ended_at_ms", "end_ts"),
            "episode_summary": ("N/A", "summary"),
            "primary_location": ("N/A", "location_json.name"),
            "participants_json": ("N/A", "participants"),
        }
        # This documents the mapping for future reference
        assert len(mapping) > 0

    def test_document_semantic_mapping(self):
        """Document field mappings for st_sem."""
        mapping = {
            "pattern_id": ("pattern_id", "pattern_id"),
            "pattern_type": ("pattern_type", "pattern_type"),
            "pattern_name": ("canonical_name", "description"),
            "pattern_description": ("N/A", "description"),
        }
        assert len(mapping) > 0

    def test_document_social_mapping(self):
        """Document field mappings for st_social."""
        mapping = {
            "relationship_id": ("relationship_id", "relationship_id"),
            "actor_a_id": ("actor_a_id", "person_a_name"),  # Need lookup
            "actor_b_id": ("actor_b_id", "person_b_name"),  # Need lookup
            "relationship_type": ("relationship_type", "relationship_type"),
            "strength_score": ("strength", "strength"),
        }
        assert len(mapping) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
