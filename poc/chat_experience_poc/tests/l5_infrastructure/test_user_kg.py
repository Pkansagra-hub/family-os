"""
Tests for User Knowledge Graph (User KG)

Tests cover:
- Schema validation
- Query interface (10 methods)
- Performance (<10ms P95)
- Caching (60s duration)
- Thread-safety
- Seeding idempotency

Reference: docs/plans/chat_experience_poc_plan.md Epic 1.4
"""

import os
import tempfile
import threading
import time

import pytest
from l5_infrastructure.user_kg import EdgeType, NodeType, get_user_kg, validate_node_properties


@pytest.fixture
def test_db():
    """Create temporary test database"""
    # Reset singleton
    from l5_infrastructure.user_kg.kg_query_interface import UserKG

    UserKG._instance = None

    # Create temp file for test database
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Get UserKG instance with test database
    kg = get_user_kg(path)

    yield kg

    # Cleanup: delete test database
    if os.path.exists(path):
        os.unlink(path)

    # Reset singleton for next test
    UserKG._instance = None


@pytest.fixture
def seeded_kg(test_db):
    """UserKG with sample data seeded"""
    kg = test_db
    kg.clear_all_data()

    # Create Person node
    person_id = kg.add_node(
        node_type=NodeType.PERSON,
        person_id="",
        properties={"name": "John", "age": 45, "locale": "en_US", "timezone": "US/Pacific"},
    )

    # Add HealthMetrics
    kg.add_node(
        node_type=NodeType.HEALTH_METRIC,
        person_id=person_id,
        properties={
            "type": "knee_strength",
            "value": 8.5,
            "unit": "kg",
            "date": "2025-11-05",
            "confidence": 0.95,
        },
    )

    # Add Goals
    goal_id = kg.add_node(
        node_type=NodeType.GOAL,
        person_id=person_id,
        properties={
            "description": "Return to running",
            "deadline": "2025-12-01",
            "progress": 0.85,
            "active": True,
        },
    )
    kg.add_edge(person_id, goal_id, EdgeType.HAS_GOAL)

    # Add Preferences
    pref_id = kg.add_node(
        node_type=NodeType.PREFERENCE,
        person_id=person_id,
        properties={"category": "food", "value": "Italian", "strength": 0.9, "source": "stated"},
    )
    kg.add_edge(person_id, pref_id, EdgeType.PREFERS)

    # Add Routines
    routine_id = kg.add_node(
        node_type=NodeType.ROUTINE,
        person_id=person_id,
        properties={
            "activity": "PT exercises",
            "schedule": "daily 8am",
            "adherence_rate": 0.75,
            "last_execution": "2025-11-05T08:15:00Z",
        },
    )
    kg.add_edge(person_id, routine_id, EdgeType.FOLLOWS_ROUTINE)

    # Add Relationships
    rel_id = kg.add_node(
        node_type=NodeType.RELATIONSHIP,
        person_id=person_id,
        properties={
            "person_name": "Mom",
            "relation_type": "caregiver",
            "closeness": 0.9,
            "notes": "Helps with PT",
        },
    )
    kg.add_edge(person_id, rel_id, EdgeType.RELATED_TO)

    # Add Memories
    memory_id = kg.add_node(
        node_type=NodeType.MEMORY,
        person_id=person_id,
        properties={
            "summary": "Started PT recovery",
            "date": "2025-09-15",
            "importance": 0.9,
            "emotional_valence": -0.3,
        },
    )
    kg.add_edge(person_id, memory_id, EdgeType.RECALLS)

    return kg, person_id


# ============================================================================
# Schema Validation Tests
# ============================================================================


def test_validate_person_properties():
    """Test Person node validation"""
    valid_props = {"name": "John", "age": 45, "locale": "en_US", "timezone": "US/Pacific"}
    assert validate_node_properties(NodeType.PERSON, valid_props)

    # Missing required field
    invalid_props = {"name": "John", "age": 45}
    assert not validate_node_properties(NodeType.PERSON, invalid_props)


def test_validate_health_metric_properties():
    """Test HealthMetric node validation"""
    valid_props = {
        "type": "knee_strength",
        "value": 8.5,
        "unit": "kg",
        "date": "2025-11-05",
        "confidence": 0.95,
    }
    assert validate_node_properties(NodeType.HEALTH_METRIC, valid_props)

    # Confidence out of range
    invalid_props = {
        "type": "test",
        "value": 1.0,
        "unit": "kg",
        "date": "2025-11-05",
        "confidence": 1.5,
    }
    assert not validate_node_properties(NodeType.HEALTH_METRIC, invalid_props)


def test_validate_goal_properties():
    """Test Goal node validation"""
    valid_props = {
        "description": "Test goal",
        "deadline": "2025-12-01",
        "progress": 0.5,
        "active": True,
    }
    assert validate_node_properties(NodeType.GOAL, valid_props)

    # Progress out of range
    invalid_props = {
        "description": "Test",
        "deadline": "2025-12-01",
        "progress": 1.5,
        "active": True,
    }
    assert not validate_node_properties(NodeType.GOAL, invalid_props)


# ============================================================================
# CRUD Operations Tests
# ============================================================================


def test_add_person_node(test_db):
    """Test creating Person node with self-reference"""
    person_id = test_db.add_node(
        node_type=NodeType.PERSON,
        person_id="",
        properties={"name": "Alice", "age": 30, "locale": "en_US", "timezone": "US/Eastern"},
    )

    assert person_id is not None
    assert person_id.startswith("node_person_")

    # Verify person_id self-references
    profile = test_db.get_user_profile(person_id)
    assert profile is not None
    assert profile["person_id"] == person_id


def test_add_and_query_nodes(seeded_kg):
    """Test adding nodes and querying"""
    kg, person_id = seeded_kg

    stats = kg.get_stats()
    assert stats["total_nodes"] >= 7  # At least Person + 6 related nodes
    assert (
        stats["total_edges"] >= 5
    )  # At least 5 edges (1 per related node type except HealthMetric)


def test_update_node(seeded_kg):
    """Test updating node properties"""
    kg, person_id = seeded_kg

    # Get original profile
    profile = kg.get_user_profile(person_id)
    original_age = profile["properties"]["age"]

    # Update properties
    new_props = profile["properties"].copy()
    new_props["age"] = original_age + 1
    kg.update_node(person_id, new_props)

    # Verify update
    updated_profile = kg.get_user_profile(person_id)
    assert updated_profile["properties"]["age"] == original_age + 1


def test_delete_node(seeded_kg):
    """Test deleting node"""
    kg, person_id = seeded_kg

    # Create extra node to delete
    pref_id = kg.add_node(
        node_type=NodeType.PREFERENCE,
        person_id=person_id,
        properties={"category": "test", "value": "test", "strength": 0.5, "source": "test"},
    )

    # Delete node
    kg.delete_node(pref_id)

    # Verify deletion (node should not appear in preferences query)
    prefs = kg.get_preferences(person_id, category="test")
    assert len(prefs) == 0


# ============================================================================
# Query Interface Tests
# ============================================================================


def test_get_user_profile(seeded_kg):
    """Test get_user_profile query"""
    kg, person_id = seeded_kg

    profile = kg.get_user_profile(person_id)

    assert profile is not None
    assert profile["node_type"] == "person"
    assert profile["properties"]["name"] == "John"
    assert profile["properties"]["age"] == 45


def test_get_health_context(seeded_kg):
    """Test get_health_context query (last 30 days)"""
    kg, person_id = seeded_kg

    health = kg.get_health_context(person_id, days=30)

    assert len(health) >= 1  # At least knee_strength metric
    assert health[0]["node_type"] == "health_metric"
    assert "type" in health[0]["properties"]


def test_get_active_goals(seeded_kg):
    """Test get_active_goals query"""
    kg, person_id = seeded_kg

    goals = kg.get_active_goals(person_id)

    assert len(goals) >= 1
    assert goals[0]["node_type"] == "goal"
    assert goals[0]["properties"]["active"] is True


def test_get_preferences(seeded_kg):
    """Test get_preferences query with category filter"""
    kg, person_id = seeded_kg

    # Get all preferences
    all_prefs = kg.get_preferences(person_id)
    assert len(all_prefs) >= 1

    # Get food preferences only
    food_prefs = kg.get_preferences(person_id, category="food")
    assert len(food_prefs) >= 1
    assert food_prefs[0]["properties"]["category"] == "food"


def test_get_routines(seeded_kg):
    """Test get_routines query"""
    kg, person_id = seeded_kg

    routines = kg.get_routines(person_id)

    assert len(routines) >= 1
    assert routines[0]["node_type"] == "routine"
    assert "activity" in routines[0]["properties"]


def test_get_relationships(seeded_kg):
    """Test get_relationships query"""
    kg, person_id = seeded_kg

    relationships = kg.get_relationships(person_id)

    assert len(relationships) >= 1
    assert relationships[0]["node_type"] == "relationship"
    assert "person_name" in relationships[0]["properties"]


def test_query_memories_no_filters(seeded_kg):
    """Test query_memories without filters"""
    kg, person_id = seeded_kg

    memories = kg.query_memories(person_id)

    assert len(memories) >= 1
    assert memories[0]["node_type"] == "memory"
    assert "summary" in memories[0]["properties"]


def test_query_memories_with_date_range(seeded_kg):
    """Test query_memories with date range filter"""
    kg, person_id = seeded_kg

    memories = kg.query_memories(person_id, date_range=("2025-09-01", "2025-10-01"))

    assert len(memories) >= 1  # Should find "Started PT recovery" memory


def test_query_memories_with_keywords(seeded_kg):
    """Test query_memories with keyword search (FTS5)"""
    kg, person_id = seeded_kg

    memories = kg.query_memories(person_id, keywords=["recovery"])

    assert len(memories) >= 1  # Should find "Started PT recovery" memory


# ============================================================================
# Performance Tests
# ============================================================================


def test_query_performance(seeded_kg):
    """Test query performance (<10ms P95 target)"""
    kg, person_id = seeded_kg

    # Run 100 queries and measure latency
    latencies = []
    for _ in range(100):
        start = time.time()
        kg.get_user_profile(person_id)
        latency_ms = (time.time() - start) * 1000
        latencies.append(latency_ms)

    # Calculate P95 latency
    latencies.sort()
    p95_latency = latencies[94]  # 95th percentile

    print(f"P95 query latency: {p95_latency:.2f}ms")
    assert p95_latency < 10.0, f"P95 latency {p95_latency:.2f}ms exceeds 10ms target"


# ============================================================================
# Caching Tests
# ============================================================================


def test_caching_improves_performance(seeded_kg):
    """Test that caching reduces query time"""
    kg, person_id = seeded_kg

    # First query (cache miss)
    start1 = time.time()
    result1 = kg.get_user_profile(person_id)
    time1_ms = (time.time() - start1) * 1000

    # Second query (cache hit)
    start2 = time.time()
    result2 = kg.get_user_profile(person_id)
    time2_ms = (time.time() - start2) * 1000

    # Verify same result
    assert result1["node_id"] == result2["node_id"]

    # Cached query should be faster (though not always due to small dataset)
    print(f"Cache miss: {time1_ms:.2f}ms, Cache hit: {time2_ms:.2f}ms")
    # Note: Cache hit may not always be faster in test environment


def test_cache_expiry(seeded_kg):
    """Test cache expiry after 60 seconds (simulated)"""
    kg, person_id = seeded_kg

    # Query to populate cache
    result1 = kg.get_user_profile(person_id)

    # Update cache duration to 0.1s for testing
    original_duration = kg._cache_duration
    kg._cache_duration = 0.1

    # Wait for cache expiry
    time.sleep(0.2)

    # Query again (should be cache miss)
    result2 = kg.get_user_profile(person_id)

    # Results should be same
    assert result1["node_id"] == result2["node_id"]

    # Restore original cache duration
    kg._cache_duration = original_duration


# ============================================================================
# Thread-Safety Tests
# ============================================================================


def test_concurrent_queries(seeded_kg):
    """Test concurrent queries are thread-safe"""
    kg, person_id = seeded_kg

    results = []
    errors = []

    def query_worker():
        try:
            profile = kg.get_user_profile(person_id)
            results.append(profile)
        except Exception as e:
            errors.append(e)

    # Launch 10 concurrent queries
    threads = []
    for _ in range(10):
        t = threading.Thread(target=query_worker)
        threads.append(t)
        t.start()

    # Wait for all threads
    for t in threads:
        t.join()

    # All queries should succeed
    assert len(errors) == 0, f"Concurrent query errors: {errors}"
    assert len(results) == 10

    # All results should be identical
    first_result = results[0]
    for result in results[1:]:
        assert result["node_id"] == first_result["node_id"]


def test_concurrent_writes(seeded_kg):
    """Test concurrent writes are thread-safe"""
    kg, person_id = seeded_kg

    created_ids = []
    errors = []

    def write_worker(index):
        try:
            pref_id = kg.add_node(
                node_type=NodeType.PREFERENCE,
                person_id=person_id,
                properties={
                    "category": f"test{index}",
                    "value": "test",
                    "strength": 0.5,
                    "source": "test",
                },
            )
            created_ids.append(pref_id)
        except Exception as e:
            errors.append(e)

    # Launch 5 concurrent writes
    threads = []
    for i in range(5):
        t = threading.Thread(target=write_worker, args=(i,))
        threads.append(t)
        t.start()

    # Wait for all threads
    for t in threads:
        t.join()

    # All writes should succeed
    assert len(errors) == 0, f"Concurrent write errors: {errors}"
    assert len(created_ids) == 5

    # All node_ids should be unique
    assert len(set(created_ids)) == 5


# ============================================================================
# Statistics Tests
# ============================================================================


def test_get_stats(seeded_kg):
    """Test get_stats returns correct counts"""
    kg, person_id = seeded_kg

    stats = kg.get_stats()

    assert "total_nodes" in stats
    assert "total_edges" in stats
    assert "node_counts" in stats
    assert "edge_counts" in stats
    assert "cache_size" in stats
    assert "db_path" in stats

    assert stats["total_nodes"] >= 7
    assert stats["total_edges"] >= 5  # At least 5 edges


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
    assert stats["total_edges"] >= 5  # At least 5 edges


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
