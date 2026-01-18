"""
Integration tests for text generators with realistic input data.

GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING.md §4
Milestone: GAP_001_MILESTONE_2_SUMMARY_GENERATOR.md

Tests generators with real-world input scenarios that would come
from the actual P03 pipeline and truth writers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from k0.modules.consolidation.algorithms.text_generators import (
    GeneratedText,
    TextGenerationStrategy,
    get_all_generators,
    get_generator,
)


class TestRealisticEpisodicInputs:
    """Test EpisodicTextGenerator with realistic family event scenarios."""

    @pytest.fixture
    def generator(self):
        return get_generator("st_epi")

    def test_family_dinner_episode(self, generator):
        """Simulate a family dinner episode from real events."""
        # Realistic episode data from R2 clustering
        friday_6pm = datetime(2026, 1, 16, 18, 0, 0, tzinfo=timezone.utc)
        friday_830pm = datetime(2026, 1, 16, 20, 30, 0, tzinfo=timezone.utc)

        record_data = {
            "episode_id": "ep_2026-01-16_dinner_001",
            "tenant_id": "tenant_smith",
            "space_id": "space_family",
            "cluster_id": "cluster_dinner_2026w03",
            "source_events_json": '["evt_001", "evt_002", "evt_003"]',
            "started_at_ms": int(friday_6pm.timestamp() * 1000),
            "ended_at_ms": int(friday_830pm.timestamp() * 1000),
            "start_ts": int(friday_6pm.timestamp() * 1000),  # Alias for generator
            "end_ts": int(friday_830pm.timestamp() * 1000),
            "temporal_spread_ms": 9000000,  # 2.5 hours
            "confidence": 0.92,
            "observation_count": 3,
            "location_json": {
                "name": "Olive Garden - Downtown",
                "type": "restaurant",
                "category": "Italian",
            },
            "participants": ["Mom", "Dad", "Emma", "Jake"],
        }

        # Realistic source event texts from ingestion
        source_texts = [
            "Arrived at Olive Garden for family dinner",
            "Dad ordered the seafood alfredo, mom got chicken parm",
            "Emma talked about her science project at school",
            "Jake showed us funny videos on his phone",
            "Celebrated mom's promotion at work",
            "Took a family photo with the waiter",
        ]

        result = generator.generate(record_data, source_texts)

        # Validate output structure
        assert isinstance(result, GeneratedText)
        assert result.layer == "st_epi"
        assert result.record_id == "ep_2026-01-16_dinner_001"

        # Validate temporal context
        assert "Friday" in result.embedding_text
        assert "evening" in result.embedding_text
        assert "2h" in result.embedding_text  # 2.5 hours rounds

        # Validate location
        assert "Olive Garden" in result.embedding_text

        # Validate participants (4 participants - all listed since ≤5)
        assert "Mom" in result.embedding_text
        assert "Dad" in result.embedding_text
        assert "Emma" in result.embedding_text
        assert "Jake" in result.embedding_text

        # Validate strategy (6 events = NARRATIVE_ARC)
        assert result.strategy_used == TextGenerationStrategy.NARRATIVE_ARC

        # Validate source texts preserved
        parsed_sources = json.loads(result.source_texts_json)
        assert len(parsed_sources) == 6

        print(f"\n[Episodic dinner]: {result.embedding_text}")

    def test_morning_routine_episode(self, generator):
        """Simulate a morning routine episode."""
        tuesday_7am = datetime(2026, 1, 13, 7, 0, 0, tzinfo=timezone.utc)
        tuesday_8am = datetime(2026, 1, 13, 8, 0, 0, tzinfo=timezone.utc)

        record_data = {
            "episode_id": "ep_2026-01-13_morning_001",
            "start_ts": int(tuesday_7am.timestamp() * 1000),
            "end_ts": int(tuesday_8am.timestamp() * 1000),
            "location_json": {"name": "Home"},
            "participants": ["Self"],
        }

        source_texts = [
            "Woke up to alarm at 7am",
            "Made coffee with the new espresso machine",
            "Read news while having breakfast",
        ]

        result = generator.generate(record_data, source_texts)

        assert "Tuesday" in result.embedding_text
        assert "morning" in result.embedding_text
        assert result.strategy_used == TextGenerationStrategy.CONCATENATE

        print(f"\n[Episodic morning]: {result.embedding_text}")

    def test_weekend_activity_episode(self, generator):
        """Simulate a weekend outdoor activity."""
        saturday_10am = datetime(2026, 1, 18, 10, 0, 0, tzinfo=timezone.utc)
        saturday_3pm = datetime(2026, 1, 18, 15, 0, 0, tzinfo=timezone.utc)

        record_data = {
            "episode_id": "ep_2026-01-18_hike_001",
            "start_ts": int(saturday_10am.timestamp() * 1000),
            "end_ts": int(saturday_3pm.timestamp() * 1000),
            "location_json": {"name": "Eagle Creek Trail", "type": "hiking_trail"},
            "participants": ["Dad", "Emma"],
        }

        source_texts = [
            "Started the hike at Eagle Creek trailhead",
            "Saw a deer along the path",
            "Emma identified wildflowers from her nature book",
            "Had packed lunch by the waterfall",
            "Finished the 5-mile loop",
        ]

        result = generator.generate(record_data, source_texts)

        # Weekend day might vary by timezone interpretation
        assert "Saturday" in result.embedding_text or "Sunday" in result.embedding_text
        assert "Eagle Creek" in result.embedding_text
        assert "Eagle Creek" in result.embedding_text

        print(f"\n[Episodic hike]: {result.embedding_text}")


class TestRealisticSemanticInputs:
    """Test SemanticTextGenerator with realistic pattern scenarios."""

    @pytest.fixture
    def generator(self):
        return get_generator("st_sem")

    def test_food_preference_pattern(self, generator):
        """Simulate a discovered food preference pattern."""
        record_data = {
            "pattern_id": "pat_food_italian_pref_001",
            "tenant_id": "tenant_smith",
            "space_id": "space_family",
            "pattern_type": "preference",
            "canonical_name": "Italian cuisine preference",
            "source_episodes_json": '["ep_dinner_001", "ep_dinner_007", "ep_lunch_003"]',
            "initial_confidence": 0.75,
            "current_confidence": 0.89,
            "observation_count": 8,
            "description": "Family frequently chooses Italian restaurants and cooks Italian dishes at home",
            "exemplars": [
                {"summary": "Dinner at Olive Garden"},
                {"summary": "Made homemade pasta"},
                {"summary": "Pizza night at home"},
            ],
            "categories": ["food", "dining", "preferences"],
        }

        source_texts = [
            "Went to Italian restaurant again",
            "Dad made his famous spaghetti bolognese",
            "Kids requested pizza for movie night",
        ]

        result = generator.generate(record_data, source_texts)

        assert "Pattern" in result.embedding_text
        assert "preference" in result.embedding_text
        assert "Italian" in result.embedding_text
        assert "Examples" in result.embedding_text
        assert result.strategy_used == TextGenerationStrategy.TEMPLATE

        print(f"\n[Semantic food]: {result.embedding_text}")

    def test_sleep_habit_pattern(self, generator):
        """Simulate a sleep habit pattern."""
        record_data = {
            "pattern_id": "pat_sleep_schedule_001",
            "pattern_type": "habit",
            "canonical_name": "Consistent bedtime routine",
            "description": "Family maintains 10pm bedtime on weeknights",
            "exemplars": [
                {"summary": "Kids in bed by 9pm"},
                {"summary": "Parents read before sleep"},
            ],
            "categories": ["health", "routine", "sleep"],
        }

        result = generator.generate(record_data)

        assert "recurring habit" in result.embedding_text
        assert "bedtime" in result.embedding_text
        assert "Categories" in result.embedding_text

        print(f"\n[Semantic sleep]: {result.embedding_text}")


class TestRealisticSocialInputs:
    """Test SocialTextGenerator with realistic relationship scenarios."""

    @pytest.fixture
    def generator(self):
        return get_generator("st_social")

    def test_parent_child_relationship(self, generator):
        """Simulate a parent-child relationship record."""
        record_data = {
            "relationship_id": "rel_sarah_emma_parent",
            "tenant_id": "tenant_smith",
            "space_id": "space_family",
            "actor_a_id": "person_sarah",
            "actor_b_id": "person_emma",
            "person_a_name": "Sarah",
            "person_b_name": "Emma",
            "relationship_type": "mother",
            "strength": 0.95,
            "interaction_count": 1247,
            "sentiment_avg": 0.78,
            "communication_frequency": "daily",
            "shared_activities": ["cooking", "homework help", "bedtime stories", "shopping"],
            "description": "Close mother-daughter bond",
        }

        source_texts = [
            "Mom helped Emma with math homework",
            "Baked cookies together after school",
            "Had heart-to-heart talk before bed",
        ]

        result = generator.generate(record_data, source_texts)

        assert "Sarah" in result.embedding_text
        assert "mother of" in result.embedding_text
        assert "Emma" in result.embedding_text
        assert "very close" in result.embedding_text
        assert "daily contact" in result.embedding_text
        assert "shared activities" in result.embedding_text

        print(f"\n[Social parent-child]: {result.embedding_text}")

    def test_sibling_relationship(self, generator):
        """Simulate a sibling relationship record."""
        record_data = {
            "relationship_id": "rel_emma_jake_sibling",
            "person_a_name": "Emma",
            "person_b_name": "Jake",
            "relationship_type": "sibling",
            "strength": 0.72,
            "communication_frequency": "daily",
            "shared_activities": ["video games", "arguing", "movie nights"],
        }

        result = generator.generate(record_data)

        assert "Emma" in result.embedding_text
        assert "sibling of" in result.embedding_text
        assert "Jake" in result.embedding_text
        assert "close relationship" in result.embedding_text

        print(f"\n[Social siblings]: {result.embedding_text}")

    def test_friend_relationship(self, generator):
        """Simulate a friend relationship."""
        record_data = {
            "relationship_id": "rel_dad_mike_friend",
            "person_a_name": "Robert",
            "person_b_name": "Mike",
            "relationship_type": "friend",
            "strength": 0.65,
            "communication_frequency": "weekly",
            "shared_activities": ["golf", "poker nights"],
            "description": "College friends who reconnected",
        }

        result = generator.generate(record_data)

        assert "Robert" in result.embedding_text
        assert "friend of" in result.embedding_text
        assert "Mike" in result.embedding_text
        assert "weekly contact" in result.embedding_text

        print(f"\n[Social friends]: {result.embedding_text}")


class TestRealisticProceduralInputs:
    """Test ProceduralTextGenerator with realistic routine scenarios."""

    @pytest.fixture
    def generator(self):
        return get_generator("st_procedural")

    def test_morning_coffee_routine(self, generator):
        """Simulate a coffee-making routine."""
        record_data = {
            "routine_id": "rtn_morning_coffee_001",
            "routine_name": "Morning Coffee Ritual",
            "description": "Dad's daily pour-over coffee process",
            "steps": [
                {"action": "Grind 30g of beans"},
                {"action": "Boil water to 205°F"},
                {"action": "Bloom grounds for 30 seconds"},
                {"action": "Pour in circular motion"},
                {"action": "Wait 3-4 minutes for drip"},
            ],
            "frequency": "daily",
            "typical_time": "6:30am",
            "typical_duration": 10,  # minutes
            "triggers": [{"cue": "wake up"}, {"cue": "morning alarm"}],
        }

        result = generator.generate(record_data)

        assert "Routine" in result.embedding_text
        assert "Morning Coffee" in result.embedding_text
        assert "Steps" in result.embedding_text
        assert "Grind" in result.embedding_text
        assert "daily" in result.embedding_text
        assert "10min" in result.embedding_text

        print(f"\n[Procedural coffee]: {result.embedding_text}")

    def test_bedtime_routine(self, generator):
        """Simulate a kids' bedtime routine."""
        record_data = {
            "routine_id": "rtn_kids_bedtime_001",
            "routine_name": "Kids Bedtime Routine",
            "steps": [
                {"action": "Bath time"},
                {"action": "Brush teeth"},
                {"action": "Put on pajamas"},
                {"action": "Read bedtime story"},
                {"action": "Goodnight hugs"},
            ],
            "frequency": "daily",
            "typical_time": "8:00pm",
            "typical_duration": 45,
            "triggers": [{"cue": "8pm reminder"}],
        }

        result = generator.generate(record_data)

        assert "Bedtime" in result.embedding_text
        assert "Bath" in result.embedding_text or "steps" in result.embedding_text.lower()
        assert "daily" in result.embedding_text

        print(f"\n[Procedural bedtime]: {result.embedding_text}")


class TestRealisticProspectiveInputs:
    """Test ProspectiveTextGenerator with realistic intention scenarios."""

    @pytest.fixture
    def generator(self):
        return get_generator("st_prospective")

    def test_birthday_reminder(self, generator):
        """Simulate a birthday reminder intention."""
        birthday = datetime(2026, 2, 15, 12, 0, 0, tzinfo=timezone.utc)

        record_data = {
            "intention_id": "int_mom_bday_reminder_001",
            "action": "Order birthday flowers for Grandma",
            "description": "Remember to order Grandma Rose's favorite lilies",
            "deadline_ts": int(birthday.timestamp() * 1000),
            "priority": "high",
            "status": "pending",
            "conditions": ["two days before birthday", "from local florist"],
        }

        source_texts = [
            "Need to remember grandma's birthday",
            "She loves stargazer lilies",
        ]

        result = generator.generate(record_data, source_texts)

        assert "Intention" in result.embedding_text
        assert "birthday flowers" in result.embedding_text
        assert "February 15" in result.embedding_text
        assert "Priority: high" in result.embedding_text

        print(f"\n[Prospective birthday]: {result.embedding_text}")

    def test_appointment_reminder(self, generator):
        """Simulate a doctor appointment reminder."""
        appt = datetime(2026, 1, 20, 14, 30, 0, tzinfo=timezone.utc)

        record_data = {
            "intention_id": "int_dentist_appt_001",
            "action": "Take Emma to dentist appointment",
            "deadline_ts": int(appt.timestamp() * 1000),
            "priority": "medium",
            "status": "pending",
            "conditions": {"when": "after school pickup", "where": "Dr. Smith's office"},
        }

        result = generator.generate(record_data)

        assert "dentist" in result.embedding_text
        assert "Emma" in result.embedding_text
        # Date formatting may vary - check it contains date info
        assert "January" in result.embedding_text or "Tuesday" in result.embedding_text

        print(f"\n[Prospective appointment]: {result.embedding_text}")


class TestRealisticKGEntityInputs:
    """Test KGEntityTextGenerator with realistic entity scenarios."""

    @pytest.fixture
    def generator(self):
        return get_generator("st_kg_dom")

    def test_person_entity(self, generator):
        """Simulate a person entity in the family graph."""
        record_data = {
            "entity_id": "ent_person_grandma_rose",
            "entity_type": "person",
            "name": "Grandma Rose",
            "aliases": ["Rose", "Grandma", "Nana"],
            "description": "Family matriarch, retired teacher, loves gardening",
            "attributes": {
                "age": 72,
                "occupation": "Retired Teacher",
                "hobbies": "Gardening, baking",
            },
            "relationships": [
                {"type": "mother of", "target": "Sarah"},
                {"type": "grandmother of", "target": "Emma"},
                {"type": "grandmother of", "target": "Jake"},
            ],
        }

        result = generator.generate(record_data)

        assert "Person" in result.embedding_text
        assert "Grandma Rose" in result.embedding_text
        assert "also known as" in result.embedding_text
        assert "Rose" in result.embedding_text
        assert "gardening" in result.embedding_text
        assert "Relationships" in result.embedding_text
        assert "mother of Sarah" in result.embedding_text

        print(f"\n[KG Entity person]: {result.embedding_text}")

    def test_place_entity(self, generator):
        """Simulate a place entity."""
        record_data = {
            "entity_id": "ent_place_grandma_house",
            "entity_type": "place",
            "name": "Grandma's House",
            "aliases": ["Nana's place"],
            "description": "Victorian home with large garden, gathering place for holidays",
            "attributes": {
                "address": "123 Oak Street",
                "rooms": 4,
            },
            "relationships": [
                {"type": "home of", "target": "Grandma Rose"},
                {"type": "location of", "target": "Thanksgiving Dinner"},
            ],
        }

        result = generator.generate(record_data)

        assert "Place" in result.embedding_text
        assert "Grandma's House" in result.embedding_text
        assert "Victorian" in result.embedding_text
        assert "Relationships" in result.embedding_text

        print(f"\n[KG Entity place]: {result.embedding_text}")

    def test_activity_entity(self, generator):
        """Simulate an activity/event type entity."""
        record_data = {
            "entity_id": "ent_activity_family_dinner",
            "entity_type": "activity",
            "name": "Weekly Family Dinner",
            "description": "Sunday tradition where extended family gathers",
            "attributes": {
                "frequency": "weekly",
                "day": "Sunday",
                "typical_attendees": 8,
            },
        }

        result = generator.generate(record_data)

        assert "Activity" in result.embedding_text
        assert "Family Dinner" in result.embedding_text
        assert "Sunday" in result.embedding_text

        print(f"\n[KG Entity activity]: {result.embedding_text}")


class TestEndToEndPipeline:
    """Test simulating full P03 pipeline flow through generators."""

    def test_event_to_episode_to_pattern_flow(self):
        """Simulate event → episode → pattern discovery flow."""
        # Step 1: Raw events come in (from ingestion)
        raw_events = [
            "Had pasta at Olive Garden",
            "Ordered tiramisu for dessert",
            "Kids loved the breadsticks",
        ]

        # Step 2: Events get clustered into an episode (R2)
        epi_gen = get_generator("st_epi")
        friday_7pm = datetime(2026, 1, 16, 19, 0, 0, tzinfo=timezone.utc)

        episode_data = {
            "episode_id": "ep_italian_dinner_001",
            "start_ts": int(friday_7pm.timestamp() * 1000),
            "end_ts": int((friday_7pm.timestamp() + 7200) * 1000),
            "location_json": {"name": "Olive Garden"},
            "participants": ["Mom", "Dad", "Kids"],
        }

        episode_result = epi_gen.generate(episode_data, raw_events)
        assert episode_result.embedding_text
        assert "episode" in episode_result.embedding_text.lower()

        # Step 3: Pattern discovered from multiple episodes (R4)
        sem_gen = get_generator("st_sem")

        pattern_data = {
            "pattern_id": "pat_italian_preference",
            "pattern_type": "preference",
            "description": "Family enjoys Italian food regularly",
            "exemplars": [
                {"summary": "Dinner at Olive Garden"},
                {"summary": "Made homemade lasagna"},
            ],
        }

        pattern_result = sem_gen.generate(pattern_data, raw_events)
        assert pattern_result.embedding_text
        assert "preference" in pattern_result.embedding_text

        # Step 4: Entity extracted (R6)
        kg_gen = get_generator("st_kg_dom")

        entity_data = {
            "entity_id": "ent_olive_garden",
            "entity_type": "place",
            "name": "Olive Garden",
            "description": "Family favorite Italian restaurant",
            "relationships": [
                {"type": "visited by", "target": "Smith Family"},
            ],
        }

        entity_result = kg_gen.generate(entity_data)
        assert entity_result.embedding_text
        assert "Olive Garden" in entity_result.embedding_text

        print("\n[OK] End-to-end flow:")
        print(f"   Episode: {episode_result.embedding_text[:60]}...")
        print(f"   Pattern: {pattern_result.embedding_text[:60]}...")
        print(f"   Entity:  {entity_result.embedding_text[:60]}...")

    def test_all_generators_handle_minimal_input(self):
        """Ensure all generators handle minimal/empty input gracefully."""
        generators = get_all_generators()

        for layer, gen in generators.items():
            # Minimal input - just an ID
            result = gen.generate({"id": "test_minimal"})

            assert result is not None
            assert isinstance(result.embedding_text, str)
            assert result.source_texts_json == "[]"
            print(f"   {layer}: {result.embedding_text[:50]}...")

    def test_all_generators_handle_unicode(self):
        """Ensure generators handle unicode/emoji content."""
        generators = get_all_generators()

        unicode_texts = [
            "Family dinner at 日本料理 🍣",
            "Emma said こんにちは to grandma",
            "Made crêpes with café au lait ☕",
        ]

        for layer, gen in generators.items():
            result = gen.generate({"id": "test_unicode"}, unicode_texts)

            # Should preserve unicode
            parsed = json.loads(result.source_texts_json)
            assert "日本料理" in parsed[0]
            assert "🍣" in parsed[0]


if __name__ == "__main__":
    # Run with verbose output to see generated texts
    pytest.main([__file__, "-v", "-s"])
