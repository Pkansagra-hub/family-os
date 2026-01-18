"""
Tests using ACTUAL database field names from PostgreSQL st_* tables.

These tests verify that the generators work with the real column names
as they exist in the database, not hypothetical field names.

Database Schema (as of 2026-01-15):
- st_epi: episode_summary, start_time_utc, end_time_utc, primary_location, participants_json
- st_sem: pattern_name, pattern_description, pattern_type
- st_social: actor_a_id, actor_b_id, relationship_type, relationship_strength, typical_activities_json, interaction_frequency
- st_prospective: intention_description, target_date, status
- st_kg_dom: canonical_name, entity_type, aliases_json, attributes_json
"""

from k0.modules.consolidation.algorithms.text_generators.episodic import (
    EpisodicTextGenerator,
)
from k0.modules.consolidation.algorithms.text_generators.kg_entity import (
    KGEntityTextGenerator,
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


class TestRealDBEpisodic:
    """Test episodic generator with real st_epi column names."""

    def test_real_db_row_routine_at_home(self):
        """
        Simulate actual database row:
        episode_summary='Routine at Home', episode_type='routine',
        start_time_utc=1768496936000, end_time_utc=1768496949000,
        primary_location='Home', participants_json='["Panda", "Prince"]'
        """
        generator = EpisodicTextGenerator()
        # Exact column names from st_epi table
        record = {
            "episode_id": "weak-234c582099954a5b9ee30586c0",
            "episode_summary": "Routine at Home",
            "episode_type": "routine",
            "start_time_utc": 1768496936000,
            "end_time_utc": 1768496949000,
            "primary_location": "Home",
            "participants_json": '["Panda", "Prince"]',
            "duration_minutes": None,
        }

        result = generator.generate(record)

        print(f"\n[Real DB st_epi]: {result.embedding_text}")
        assert result.embedding_text
        assert "Home" in result.embedding_text
        # Should mention participants
        assert "Panda" in result.embedding_text or "Prince" in result.embedding_text

    def test_real_db_row_with_multiple_participants(self):
        """
        Simulate: participants_json='["Mom", "Panda", "Prince"]'
        """
        generator = EpisodicTextGenerator()
        record = {
            "episode_id": "weak-ffe04fdfde4b4e268dd0065e02",
            "episode_summary": "Routine at Home",
            "episode_type": "routine",
            "start_time_utc": 1768496936000,
            "end_time_utc": 1768496938000,
            "primary_location": "Home",
            "participants_json": '["Mom", "Panda", "Prince"]',
        }

        result = generator.generate(record)

        print(f"\n[Real DB st_epi multi-participant]: {result.embedding_text}")
        assert result.embedding_text
        # Should mention at least participant count
        assert "3" in result.embedding_text or "Mom" in result.embedding_text


class TestRealDBSemantic:
    """Test semantic generator with real st_sem column names."""

    def test_real_db_row_theme_pattern(self):
        """
        Simulate actual database row:
        pattern_type='THEME', pattern_name='Pattern from 089c94e0...',
        pattern_description=NULL
        """
        generator = SemanticTextGenerator()
        # Exact column names from st_sem table
        record = {
            "pattern_id": "sem_089c94e0-a3fa-407f-81e9-f0c2c9d146e9",
            "pattern_type": "THEME",
            "pattern_name": "Pattern from 089c94e0-a3fa-407f-81e9-f0c2c9d146e9",
            "pattern_description": None,
            "pattern_subtype": None,
            "pattern_attributes_json": None,
        }

        result = generator.generate(record)

        print(f"\n[Real DB st_sem]: {result.embedding_text}")
        assert result.embedding_text
        assert "THEME" in result.embedding_text or "theme" in result.embedding_text.lower()

    def test_real_db_row_with_description(self):
        """
        Simulate row with pattern_description populated.
        """
        generator = SemanticTextGenerator()
        record = {
            "pattern_id": "sem_test123",
            "pattern_type": "PREFERENCE",
            "pattern_name": "Italian Food Preference",
            "pattern_description": "Family consistently chooses Italian restaurants for special occasions",
        }

        result = generator.generate(record)

        print(f"\n[Real DB st_sem with description]: {result.embedding_text}")
        assert result.embedding_text
        assert "Italian" in result.embedding_text


class TestRealDBSocial:
    """Test social generator with real st_social column names."""

    def test_real_db_row_friend_relationship(self):
        """
        Simulate actual database row:
        actor_a_id='Prince', actor_b_id='Mom', relationship_type='FRIEND',
        relationship_strength=0.65, typical_activities_json='["routine"]'
        """
        generator = SocialTextGenerator()
        # Exact column names from st_social table
        record = {
            "relationship_id": "social_3eb2fcd01922074d",
            "actor_a_id": "Prince",
            "actor_b_id": "Mom",
            "relationship_type": "FRIEND",
            "relationship_strength": 0.65,
            "interaction_count": 3,
            "typical_activities_json": '["routine"]',
            "interaction_frequency": None,
        }

        result = generator.generate(record)

        print(f"\n[Real DB st_social]: {result.embedding_text}")
        assert result.embedding_text
        # Should use actor names as person names
        assert "Prince" in result.embedding_text
        assert "Mom" in result.embedding_text
        assert "friend" in result.embedding_text.lower()

    def test_real_db_row_with_strength_score(self):
        """
        Test with relationship_strength (actual DB field).
        """
        generator = SocialTextGenerator()
        record = {
            "relationship_id": "social_cdbc50bfb1f015b8",
            "actor_a_id": "Prince",
            "actor_b_id": "Dad",
            "relationship_type": "FRIEND",
            "relationship_strength": 0.55,
            "interaction_count": 1,
        }

        result = generator.generate(record)

        print(f"\n[Real DB st_social with strength]: {result.embedding_text}")
        assert result.embedding_text
        # 0.55 should be "moderate relationship"
        assert "relationship" in result.embedding_text.lower()


class TestRealDBProspective:
    """Test prospective generator with real st_prospective column names."""

    def test_real_db_row_reminder(self):
        """
        Simulate actual database row:
        intention_type='REMINDER', intention_description='take Mom to botanical garden',
        target_date=NULL, status='ACTIVE'
        """
        generator = ProspectiveTextGenerator()
        # Exact column names from st_prospective table
        record = {
            "intention_id": "reminder_089c94e0-a3fa-407f-81e9-f0c2c9d146e9",
            "actor_id": "system",
            "intention_type": "REMINDER",
            "intention_description": "take Mom to the botanical garden",
            "target_date": None,
            "status": "ACTIVE",
        }

        result = generator.generate(record)

        print(f"\n[Real DB st_prospective]: {result.embedding_text}")
        assert result.embedding_text
        assert "botanical garden" in result.embedding_text.lower()
        # Generator maps ACTIVE status to "pending" for readability
        assert "pending" in result.embedding_text.lower()

    def test_real_db_row_with_target_date(self):
        """
        Test with target_date populated (actual DB field).
        """
        generator = ProspectiveTextGenerator()
        record = {
            "intention_id": "reminder_test123",
            "actor_id": "Prince",
            "intention_type": "REMINDER",
            "intention_description": "buy HDMI 2.1 cables from Micro Center",
            "target_date": 1737043200000,  # 2025-01-16
            "status": "ACTIVE",
        }

        result = generator.generate(record)

        print(f"\n[Real DB st_prospective with target_date]: {result.embedding_text}")
        assert result.embedding_text
        assert "HDMI" in result.embedding_text or "cables" in result.embedding_text


class TestRealDBKGEntity:
    """Test KG entity generator with real st_kg_dom column names."""

    def test_real_db_row_family_member(self):
        """
        Simulate actual database row:
        entity_type='FAMILY_MEMBER', canonical_name='parents',
        aliases_json="['parents']", attributes_json=NULL
        """
        generator = KGEntityTextGenerator()
        # Exact column names from st_kg_dom table
        record = {
            "entity_id": "cluster_FAMILY_MEMBER_parents",
            "entity_type": "FAMILY_MEMBER",
            "canonical_name": "parents",
            "aliases_json": "['parents']",
            "attributes_json": None,
        }

        result = generator.generate(record)

        print(f"\n[Real DB st_kg_dom]: {result.embedding_text}")
        assert result.embedding_text
        assert "parents" in result.embedding_text.lower()

    def test_real_db_row_organization(self):
        """
        Simulate: entity_type='ORGANIZATION', canonical_name='adobe'
        """
        generator = KGEntityTextGenerator()
        record = {
            "entity_id": "cluster_ORGANIZATION_adobe",
            "entity_type": "ORGANIZATION",
            "canonical_name": "adobe",
            "aliases_json": "['Adobe']",
            "attributes_json": None,
        }

        result = generator.generate(record)

        print(f"\n[Real DB st_kg_dom organization]: {result.embedding_text}")
        assert result.embedding_text
        assert "adobe" in result.embedding_text.lower() or "Adobe" in result.embedding_text

    def test_real_db_row_location(self):
        """
        Simulate: entity_type='LOCATION', canonical_name='staging'
        """
        generator = KGEntityTextGenerator()
        record = {
            "entity_id": "cluster_LOCATION_staging",
            "entity_type": "LOCATION",
            "canonical_name": "staging",
            "aliases_json": "['staging']",
            "attributes_json": None,
        }

        result = generator.generate(record)

        print(f"\n[Real DB st_kg_dom location]: {result.embedding_text}")
        assert result.embedding_text
        assert "staging" in result.embedding_text.lower()


class TestFieldNameMappingVerification:
    """
    Verify that generators accept BOTH the old expected names AND the real DB names.
    This ensures backward compatibility while supporting actual database schema.
    """

    def test_episodic_accepts_both_timestamp_formats(self):
        """Verify episodic accepts start_ts AND start_time_utc."""
        generator = EpisodicTextGenerator()

        # Using expected field name (start_ts)
        result1 = generator.generate(
            {
                "episode_id": "test1",
                "start_ts": 1768496936000,
                "end_ts": 1768496949000,
                "summary": "Test episode",
            }
        )

        # Using actual DB field name (start_time_utc)
        result2 = generator.generate(
            {
                "episode_id": "test2",
                "start_time_utc": 1768496936000,
                "end_time_utc": 1768496949000,
                "episode_summary": "Test episode",
            }
        )

        # Both should produce valid output
        assert result1.embedding_text
        assert result2.embedding_text
        print(f"\n[start_ts format]: {result1.embedding_text}")
        print(f"[start_time_utc format]: {result2.embedding_text}")

    def test_social_accepts_both_strength_formats(self):
        """Verify social accepts strength AND relationship_strength."""
        generator = SocialTextGenerator()

        # Using expected field name (strength)
        result1 = generator.generate(
            {
                "relationship_id": "test1",
                "person_a_name": "Alice",
                "person_b_name": "Bob",
                "relationship_type": "friend",
                "strength": 0.8,
            }
        )

        # Using actual DB field name (relationship_strength)
        result2 = generator.generate(
            {
                "relationship_id": "test2",
                "actor_a_id": "Alice",
                "actor_b_id": "Bob",
                "relationship_type": "friend",
                "relationship_strength": 0.8,
            }
        )

        # Both should produce valid output with strength description
        assert result1.embedding_text
        assert result2.embedding_text
        assert (
            "close" in result1.embedding_text.lower()
            or "relationship" in result1.embedding_text.lower()
        )
        assert (
            "close" in result2.embedding_text.lower()
            or "relationship" in result2.embedding_text.lower()
        )
        print(f"\n[strength format]: {result1.embedding_text}")
        print(f"[relationship_strength format]: {result2.embedding_text}")

    def test_prospective_accepts_both_deadline_formats(self):
        """Verify prospective accepts deadline_ts AND target_date."""
        generator = ProspectiveTextGenerator()

        # Using expected field name (deadline_ts)
        result1 = generator.generate(
            {
                "intention_id": "test1",
                "action": "Buy groceries",
                "deadline_ts": 1737043200000,
            }
        )

        # Using actual DB field name (target_date)
        result2 = generator.generate(
            {
                "intention_id": "test2",
                "intention_description": "Buy groceries",
                "target_date": 1737043200000,
            }
        )

        # Both should produce valid output
        assert result1.embedding_text
        assert result2.embedding_text
        print(f"\n[deadline_ts format]: {result1.embedding_text}")
        print(f"[target_date format]: {result2.embedding_text}")

    def test_kg_entity_accepts_both_name_formats(self):
        """Verify kg_entity accepts name AND canonical_name."""
        generator = KGEntityTextGenerator()

        # Using expected field name (name)
        result1 = generator.generate(
            {
                "entity_id": "test1",
                "entity_type": "person",
                "name": "John Smith",
            }
        )

        # Using actual DB field name (canonical_name)
        result2 = generator.generate(
            {
                "entity_id": "test2",
                "entity_type": "person",
                "canonical_name": "John Smith",
            }
        )

        # Both should produce valid output with the name
        assert result1.embedding_text
        assert result2.embedding_text
        assert "John Smith" in result1.embedding_text
        assert "John Smith" in result2.embedding_text
        print(f"\n[name format]: {result1.embedding_text}")
        print(f"[canonical_name format]: {result2.embedding_text}")
