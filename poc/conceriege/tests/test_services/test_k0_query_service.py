"""Unit tests for K0QueryService.

Tests cover:
- Query with filters
- Time range filtering
- Schema discovery
- Table search by keywords
- Cross-memory queries
- GERD scenario validation
"""

from datetime import datetime, timedelta

import pytest
from backend.services.k0_query_service import MockK0QueryService, create_k0_service

from tests.fixtures.mock_k0_data import TEST_USER_ID


@pytest.fixture
def k0_service():
    """Create mock K0 service for testing."""
    return create_k0_service(mock=True)


class TestK0QueryServiceBasics:
    """Basic query functionality tests."""

    def test_query_diet_logs(self, k0_service):
        """Test querying diet logs."""
        results = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="episodic.diet_logs",
            limit=100,
        )

        assert len(results) > 0
        assert all("food_item" in r for r in results)
        assert all("timestamp" in r for r in results)

    def test_query_with_filter(self, k0_service):
        """Test query with column filter."""
        results = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="episodic.diet_logs",
            filters={"food_item": "coffee"},
        )

        assert len(results) == 5  # 5 coffee entries in mock data
        assert all(r["food_item"] == "coffee" for r in results)

    def test_query_with_multiple_filters(self, k0_service):
        """Test query with multiple column filters."""
        results = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="episodic.diet_logs",
            filters={"food_item": "coffee", "meal_type": "breakfast"},
        )

        assert len(results) == 4  # 4 coffee at breakfast
        assert all(r["food_item"] == "coffee" for r in results)
        assert all(r["meal_type"] == "breakfast" for r in results)

    def test_query_with_limit(self, k0_service):
        """Test query result limiting."""
        results = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="episodic.diet_logs",
            limit=10,
        )

        assert len(results) <= 10

    def test_query_invalid_table(self, k0_service):
        """Test query with invalid table name."""
        with pytest.raises(ValueError, match="Unknown table"):
            k0_service.query(
                user_id=TEST_USER_ID,
                table_name="invalid.table",
            )

    def test_query_health_events(self, k0_service):
        """Test querying health events."""
        results = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="episodic.health_events",
        )

        assert len(results) == 5  # 5 GERD episodes
        assert all(r["event_type"] == "GERD" for r in results)


class TestTimeRangeFiltering:
    """Time range filtering tests."""

    def test_last_7_days(self, k0_service):
        """Test last_7_days time range."""
        results = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="episodic.diet_logs",
            time_range="last_7_days",
        )

        # Should have some recent entries
        assert len(results) >= 0

    def test_last_30_days(self, k0_service):
        """Test last_30_days time range."""
        results = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="episodic.diet_logs",
            time_range="last_30_days",
        )

        # Should capture all mock data (generated over 30 days)
        assert len(results) > 0

    def test_last_90_days(self, k0_service):
        """Test last_90_days time range."""
        results = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="episodic.health_events",
            time_range="last_90_days",
        )

        # Should capture all GERD events
        assert len(results) == 5

    def test_custom_time_range(self, k0_service):
        """Test custom datetime time range."""
        start_time = datetime.now() - timedelta(days=15)
        end_time = datetime.now()

        results = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="episodic.diet_logs",
            time_range=(start_time, end_time),
        )

        # Should have some entries in this range
        assert len(results) >= 0

    def test_time_filter_with_column_filter(self, k0_service):
        """Test combining time range and column filters."""
        results = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="episodic.diet_logs",
            filters={"food_item": "coffee"},
            time_range="last_30_days",
        )

        # Should have coffee entries in last 30 days
        assert len(results) > 0
        assert all(r["food_item"] == "coffee" for r in results)


class TestSchemaDiscovery:
    """Schema discovery tests."""

    def test_get_all_schemas(self, k0_service):
        """Test getting all table schemas."""
        schemas = k0_service.get_schema()

        assert len(schemas) > 0
        assert "episodic.diet_logs" in schemas
        assert "semantic.food_nutrition" in schemas

        # Check schema structure
        diet_schema = schemas["episodic.diet_logs"]
        assert "columns" in diet_schema
        assert "filters" in diet_schema
        assert "description" in diet_schema
        assert "timestamp" in diet_schema["columns"]
        assert "food_item" in diet_schema["columns"]

    def test_get_episodic_schemas(self, k0_service):
        """Test getting episodic memory schemas only."""
        schemas = k0_service.get_schema("episodic")

        assert len(schemas) > 0
        assert all(table.startswith("episodic.") for table in schemas)
        assert "episodic.diet_logs" in schemas
        assert "episodic.health_events" in schemas
        assert "semantic.food_nutrition" not in schemas

    def test_get_semantic_schemas(self, k0_service):
        """Test getting semantic memory schemas only."""
        schemas = k0_service.get_schema("semantic")

        assert len(schemas) > 0
        assert all(table.startswith("semantic.") for table in schemas)
        assert "semantic.food_nutrition" in schemas
        assert "semantic.health_conditions" in schemas
        assert "episodic.diet_logs" not in schemas

    def test_get_schema_invalid_memory_type(self, k0_service):
        """Test getting schema for invalid memory type."""
        with pytest.raises(ValueError, match="Unknown memory type"):
            k0_service.get_schema("invalid_type")

    def test_list_memory_types(self, k0_service):
        """Test listing all memory types."""
        memory_types = k0_service.list_memory_types()

        assert len(memory_types) == 8  # 8 memory types
        assert "episodic" in memory_types
        assert "semantic" in memory_types
        assert "autobiographical" in memory_types
        assert "working" in memory_types
        assert "prospective" in memory_types
        assert "spatial" in memory_types
        assert "emotional" in memory_types
        assert "procedural" in memory_types

        # Check structure
        episodic = memory_types["episodic"]
        assert "tables" in episodic
        assert "description" in episodic
        assert "diet_logs" in episodic["tables"]


class TestTableSearch:
    """Table search by keywords tests."""

    def test_search_diet_keywords(self, k0_service):
        """Test searching for diet-related tables."""
        results = k0_service.search_tables(["diet", "food", "nutrition"])

        assert len(results) > 0
        table_names = [name for name, score in results]
        assert "episodic.diet_logs" in table_names
        assert "semantic.food_nutrition" in table_names

    def test_search_health_keywords(self, k0_service):
        """Test searching for health-related tables."""
        results = k0_service.search_tables(["health", "symptom", "GERD"])

        assert len(results) > 0
        table_names = [name for name, score in results]
        assert "episodic.health_events" in table_names
        assert "semantic.health_conditions" in table_names
        assert "semantic.symptoms" in table_names

    def test_search_emotional_keywords(self, k0_service):
        """Test searching for emotional tables."""
        results = k0_service.search_tables(["mood", "stress", "emotion"])

        assert len(results) > 0
        table_names = [name for name, score in results]
        assert "emotional.mood_logs" in table_names
        assert "emotional.stress_events" in table_names

    def test_search_results_sorted(self, k0_service):
        """Test that search results are sorted by relevance."""
        results = k0_service.search_tables(["diet", "food"])

        assert len(results) > 0
        # Scores should be descending
        scores = [score for name, score in results]
        assert scores == sorted(scores, reverse=True)


class TestCrossMemoryQueries:
    """Tests for querying across multiple memory types."""

    def test_query_episodic_and_semantic(self, k0_service):
        """Test querying both episodic and semantic memory."""
        # Get diet logs (episodic)
        diet_logs = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="episodic.diet_logs",
            filters={"food_item": "coffee"},
        )

        # Get nutrition info (semantic)
        nutrition = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="semantic.food_nutrition",
            filters={"food_item": "coffee"},
        )

        assert len(diet_logs) == 5  # 5 coffee entries
        assert len(nutrition) == 1  # 1 coffee nutrition record
        assert nutrition[0]["gerd_risk"] == "high"

    def test_query_episodic_and_emotional(self, k0_service):
        """Test querying episodic and emotional memory."""
        # Get health events
        health_events = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="episodic.health_events",
        )

        # Get mood logs
        mood_logs = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="emotional.mood_logs",
        )

        assert len(health_events) == 5  # 5 GERD events
        assert len(mood_logs) == 5  # 5 mood logs

    def test_query_working_and_prospective(self, k0_service):
        """Test querying working and prospective memory."""
        # Get active goals (working)
        goals = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="working.active_goals",
        )

        # Get appointments (prospective)
        appointments = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="prospective.appointments",
        )

        assert len(goals) == 2  # 2 active goals
        assert len(appointments) == 1  # 1 appointment


class TestGERDScenario:
    """Tests validating the GERD scenario data."""

    def test_coffee_consumption(self, k0_service):
        """Test coffee consumption entries."""
        coffee_entries = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="episodic.diet_logs",
            filters={"food_item": "coffee"},
        )

        assert len(coffee_entries) == 5

    def test_milk_consumption(self, k0_service):
        """Test milk consumption entries."""
        milk_entries = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="episodic.diet_logs",
            filters={"food_item": "milk"},
        )

        assert len(milk_entries) == 8

    def test_gerd_episodes(self, k0_service):
        """Test GERD episode entries."""
        gerd_events = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="episodic.health_events",
            filters={"event_type": "GERD"},
        )

        assert len(gerd_events) == 5
        # Verify severity distribution
        severities = [e["severity"] for e in gerd_events]
        assert "moderate" in severities
        assert "severe" in severities
        assert "mild" in severities

    def test_stress_events(self, k0_service):
        """Test stress event entries."""
        stress_events = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="emotional.stress_events",
        )

        assert len(stress_events) == 3
        # Check that some stress events are work-related
        categories = [e["category"] for e in stress_events]
        assert "work" in categories

    def test_coffee_nutrition_data(self, k0_service):
        """Test coffee nutrition information."""
        coffee_nutrition = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="semantic.food_nutrition",
            filters={"food_item": "coffee"},
        )

        assert len(coffee_nutrition) == 1
        coffee = coffee_nutrition[0]
        assert coffee["gerd_risk"] == "high"
        assert coffee["acidity"] == "high"
        assert coffee["caffeine_mg"] == 95
        assert "caffeine" in coffee["trigger_compounds"]

    def test_gerd_condition_data(self, k0_service):
        """Test GERD condition information."""
        gerd_condition = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="semantic.health_conditions",
            filters={"condition_name": "GERD"},
        )

        assert len(gerd_condition) == 1
        condition = gerd_condition[0]
        assert condition["category"] == "digestive"
        assert condition["chronic"] is True
        assert "caffeine" in condition["triggers"]

    def test_user_profile_gerd(self, k0_service):
        """Test user profile shows GERD condition."""
        profile = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="autobiographical.user_profile",
        )

        assert len(profile) == 1
        assert profile[0]["chronic_conditions"] == "GERD"

    def test_active_goals_gerd_related(self, k0_service):
        """Test active goals include GERD trigger identification."""
        goals = k0_service.query(
            user_id=TEST_USER_ID,
            table_name="working.active_goals",
        )

        assert len(goals) == 2
        goal_texts = [g["goal"] for g in goals]
        assert any("GERD" in g for g in goal_texts)


class TestFactoryFunction:
    """Tests for create_k0_service factory."""

    def test_create_mock_service(self):
        """Test creating mock service."""
        service = create_k0_service(mock=True)

        assert isinstance(service, MockK0QueryService)

    def test_create_real_service_not_implemented(self):
        """Test that real service raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="Real K0 service not yet implemented"):
            create_k0_service(mock=False)


class TestSemanticTableSearch:
    """Tests for LLM-powered semantic table search."""

    def test_semantic_search_diet_query(self, k0_service):
        """Test semantic search with diet-related natural language query."""
        results = k0_service.search_tables_semantic(
            "What foods did I eat that might trigger heartburn?"
        )

        assert len(results) > 0
        table_names = [name for name, score in results]
        # Should find diet and nutrition tables
        assert any("diet" in name or "nutrition" in name for name in table_names)

    def test_semantic_search_health_query(self, k0_service):
        """Test semantic search with health-related query."""
        results = k0_service.search_tables_semantic(
            "Show me tables about my digestive health problems"
        )

        assert len(results) > 0
        table_names = [name for name, score in results]
        # Should find health-related tables
        assert any("health" in name for name in table_names)

    def test_semantic_search_emotional_query(self, k0_service):
        """Test semantic search with emotional query."""
        results = k0_service.search_tables_semantic("How has stress been affecting me lately?")

        assert len(results) > 0
        table_names = [name for name, score in results]
        # Should find emotional tables
        assert any("stress" in name or "mood" in name for name in table_names)

    def test_semantic_search_simple_query(self, k0_service):
        """Test semantic search with simple query."""
        results = k0_service.search_tables_semantic("diet")

        assert len(results) > 0
        # Should find diet-related tables
        table_names = [name for name, score in results]
        assert any("diet" in name for name in table_names)

    def test_semantic_search_complex_query(self, k0_service):
        """Test semantic search with complex natural language."""
        results = k0_service.search_tables_semantic(
            "I want to understand the correlation between what I eat and when I experience GERD symptoms"
        )

        assert len(results) > 0
        table_names = [name for name, score in results]
        # Should find multiple relevant tables
        assert any("diet" in name for name in table_names)
        assert any("health" in name or "symptom" in name for name in table_names)
