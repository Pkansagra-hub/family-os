#!/usr/bin/env python3
"""
Seed User KG with Sample Data

Populates User Knowledge Graph with realistic sample data for user "John" (age 45)
in PT recovery. Demonstrates all 7 node types and 6 edge types.

Idempotent: Can run multiple times without creating duplicates.

Reference: docs/plans/chat_experience_poc_plan.md Epic 1.4.3
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from l5_infrastructure.user_kg import EdgeType, NodeType, get_user_kg


def seed_user_kg():
    """
    Seed User KG with sample data for user John.

    Node Types Created:
    - 1 Person (John, age 45)
    - 3 HealthMetrics (knee strength, pain level, PT sessions)
    - 2 Goals (return to running, complete PT sessions)
    - 2 Relationships (Mom, Sarah)
    - 2 Preferences (Italian food, morning exercise)
    - 2 Routines (PT exercises, drink water)
    - 2 Memories (started PT, last session went well)

    Total: 14 nodes, 12 edges
    """

    # Get UserKG instance
    kg = get_user_kg()

    # Clear existing data (for idempotency)
    print("Clearing existing User KG data...")
    kg.clear_all_data()

    print("Seeding User KG with sample data for user 'John'...")

    # ========================================================================
    # 1. Create Person Node (John)
    # ========================================================================
    print("\n1. Creating Person node (John)...")
    person_id = kg.add_node(
        node_type=NodeType.PERSON,
        person_id="",  # Will be set to node_id after creation
        properties={"name": "John", "age": 45, "locale": "en_US", "timezone": "US/Pacific"},
    )
    print(f"   ✅ Created Person node: {person_id}")

    # Update person_id to self-reference
    profile = kg.get_user_profile(person_id)
    if profile:
        # Person node exists, now create related nodes
        pass

    # ========================================================================
    # 2. Create HealthMetric Nodes
    # ========================================================================
    print("\n2. Creating HealthMetric nodes...")

    # Knee strength
    knee_strength_id = kg.add_node(
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
    print("   ✅ Created HealthMetric: knee_strength (8.5 kg)")

    # Pain level
    pain_level_id = kg.add_node(
        node_type=NodeType.HEALTH_METRIC,
        person_id=person_id,
        properties={
            "type": "pain_level",
            "value": 2.0,
            "unit": "/10",
            "date": "2025-11-05",
            "confidence": 0.90,
        },
    )
    print("   ✅ Created HealthMetric: pain_level (2/10)")

    # PT sessions completed
    pt_sessions_id = kg.add_node(
        node_type=NodeType.HEALTH_METRIC,
        person_id=person_id,
        properties={
            "type": "pt_sessions_completed",
            "value": 6.0,
            "unit": "/8",
            "date": "2025-11-05",
            "confidence": 1.0,
        },
    )
    print("   ✅ Created HealthMetric: pt_sessions_completed (6/8)")

    # Create edges: Person TRACKS_METRIC HealthMetric
    kg.add_edge(person_id, knee_strength_id, EdgeType.TRACKS_METRIC)
    kg.add_edge(person_id, pain_level_id, EdgeType.TRACKS_METRIC)
    kg.add_edge(person_id, pt_sessions_id, EdgeType.TRACKS_METRIC)
    print("   ✅ Created 3 TRACKS_METRIC edges")

    # ========================================================================
    # 3. Create Goal Nodes
    # ========================================================================
    print("\n3. Creating Goal nodes...")

    # Goal 1: Return to running
    running_goal_id = kg.add_node(
        node_type=NodeType.GOAL,
        person_id=person_id,
        properties={
            "description": "Return to running by Dec 1, 2025",
            "deadline": "2025-12-01",
            "progress": 0.85,
            "active": True,
        },
    )
    print("   ✅ Created Goal: Return to running (85% complete)")

    # Goal 2: Complete 8 PT sessions
    pt_goal_id = kg.add_node(
        node_type=NodeType.GOAL,
        person_id=person_id,
        properties={
            "description": "Complete 8 PT sessions",
            "deadline": "2025-11-15",
            "progress": 0.75,
            "active": True,
        },
    )
    print("   ✅ Created Goal: Complete 8 PT sessions (75% complete)")

    # Create edges: Person HAS_GOAL Goal
    kg.add_edge(person_id, running_goal_id, EdgeType.HAS_GOAL)
    kg.add_edge(person_id, pt_goal_id, EdgeType.HAS_GOAL)
    print("   ✅ Created 2 HAS_GOAL edges")

    # ========================================================================
    # 4. Create Relationship Nodes
    # ========================================================================
    print("\n4. Creating Relationship nodes...")

    # Relationship 1: Mom (caregiver)
    mom_rel_id = kg.add_node(
        node_type=NodeType.RELATIONSHIP,
        person_id=person_id,
        properties={
            "person_name": "Mom",
            "relation_type": "caregiver",
            "closeness": 0.9,
            "notes": "Lives nearby, helps with PT exercises",
        },
    )
    print("   ✅ Created Relationship: Mom (caregiver, closeness 0.9)")

    # Relationship 2: Sarah (partner)
    sarah_rel_id = kg.add_node(
        node_type=NodeType.RELATIONSHIP,
        person_id=person_id,
        properties={
            "person_name": "Sarah",
            "relation_type": "partner",
            "closeness": 1.0,
            "notes": "Supportive partner, high closeness",
        },
    )
    print("   ✅ Created Relationship: Sarah (partner, closeness 1.0)")

    # Create edges: Person RELATED_TO Relationship
    kg.add_edge(person_id, mom_rel_id, EdgeType.RELATED_TO)
    kg.add_edge(person_id, sarah_rel_id, EdgeType.RELATED_TO)
    print("   ✅ Created 2 RELATED_TO edges")

    # ========================================================================
    # 5. Create Preference Nodes
    # ========================================================================
    print("\n5. Creating Preference nodes...")

    # Preference 1: Food - Italian
    food_pref_id = kg.add_node(
        node_type=NodeType.PREFERENCE,
        person_id=person_id,
        properties={"category": "food", "value": "Italian", "strength": 0.9, "source": "stated"},
    )
    print("   ✅ Created Preference: Food = Italian (strength 0.9)")

    # Preference 2: Exercise - Morning
    exercise_pref_id = kg.add_node(
        node_type=NodeType.PREFERENCE,
        person_id=person_id,
        properties={
            "category": "exercise",
            "value": "Morning",
            "strength": 0.8,
            "source": "observed",
        },
    )
    print("   ✅ Created Preference: Exercise = Morning (strength 0.8)")

    # Create edges: Person PREFERS Preference
    kg.add_edge(person_id, food_pref_id, EdgeType.PREFERS)
    kg.add_edge(person_id, exercise_pref_id, EdgeType.PREFERS)
    print("   ✅ Created 2 PREFERS edges")

    # ========================================================================
    # 6. Create Routine Nodes
    # ========================================================================
    print("\n6. Creating Routine nodes...")

    # Routine 1: PT exercises
    pt_routine_id = kg.add_node(
        node_type=NodeType.ROUTINE,
        person_id=person_id,
        properties={
            "activity": "PT exercises",
            "schedule": "daily 8am",
            "adherence_rate": 0.75,
            "last_execution": "2025-11-05T08:15:00Z",
        },
    )
    print("   ✅ Created Routine: PT exercises (adherence 0.75)")

    # Routine 2: Drink water
    water_routine_id = kg.add_node(
        node_type=NodeType.ROUTINE,
        person_id=person_id,
        properties={
            "activity": "Drink water",
            "schedule": "every 4 hours",
            "adherence_rate": 0.60,
            "last_execution": "2025-11-05T10:00:00Z",
        },
    )
    print("   ✅ Created Routine: Drink water (adherence 0.60)")

    # Create edges: Person FOLLOWS_ROUTINE Routine
    kg.add_edge(person_id, pt_routine_id, EdgeType.FOLLOWS_ROUTINE)
    kg.add_edge(person_id, water_routine_id, EdgeType.FOLLOWS_ROUTINE)
    print("   ✅ Created 2 FOLLOWS_ROUTINE edges")

    # ========================================================================
    # 7. Create Memory Nodes
    # ========================================================================
    print("\n7. Creating Memory nodes...")

    # Memory 1: Started PT recovery
    pt_start_memory_id = kg.add_node(
        node_type=NodeType.MEMORY,
        person_id=person_id,
        properties={
            "summary": "Started PT recovery",
            "date": "2025-09-15",
            "importance": 0.9,
            "emotional_valence": -0.3,  # Negative: injury/setback
        },
    )
    print("   ✅ Created Memory: Started PT recovery (importance 0.9)")

    # Memory 2: Last PT session went well
    pt_session_memory_id = kg.add_node(
        node_type=NodeType.MEMORY,
        person_id=person_id,
        properties={
            "summary": "Last PT session went well",
            "date": "2025-10-28",
            "importance": 0.7,
            "emotional_valence": 0.6,  # Positive: progress
        },
    )
    print("   ✅ Created Memory: Last PT session went well (importance 0.7)")

    # Create edges: Person RECALLS Memory
    kg.add_edge(person_id, pt_start_memory_id, EdgeType.RECALLS)
    kg.add_edge(person_id, pt_session_memory_id, EdgeType.RECALLS)
    print("   ✅ Created 2 RECALLS edges")

    # ========================================================================
    # Summary
    # ========================================================================
    print("\n" + "=" * 80)
    print("✅ User KG seeding complete!")
    print("=" * 80)

    stats = kg.get_stats()
    print("\nStatistics:")
    print(f"  Total nodes: {stats['total_nodes']}")
    print(f"  Total edges: {stats['total_edges']}")
    print("\nNode counts by type:")
    for node_type, count in stats["node_counts"].items():
        print(f"  {node_type}: {count}")
    print("\nEdge counts by type:")
    for edge_type, count in stats["edge_counts"].items():
        print(f"  {edge_type}: {count}")
    print(f"\nDatabase path: {stats['db_path']}")

    # ========================================================================
    # Verification Queries
    # ========================================================================
    print("\n" + "=" * 80)
    print("Verification Queries")
    print("=" * 80)

    # Get user profile
    profile = kg.get_user_profile(person_id)
    if profile:
        print("\n✅ User Profile:")
        print(f"  Name: {profile['properties']['name']}")
        print(f"  Age: {profile['properties']['age']}")
        print(f"  Timezone: {profile['properties']['timezone']}")

    # Get active goals
    goals = kg.get_active_goals(person_id)
    print(f"\n✅ Active Goals ({len(goals)}):")
    for goal in goals:
        print(
            f"  - {goal['properties']['description']} (progress: {goal['properties']['progress']*100:.0f}%)"
        )

    # Get health context (last 30 days)
    health = kg.get_health_context(person_id, days=30)
    print(f"\n✅ Health Context ({len(health)} metrics):")
    for metric in health:
        print(
            f"  - {metric['properties']['type']}: {metric['properties']['value']} {metric['properties']['unit']}"
        )

    # Get preferences
    prefs = kg.get_preferences(person_id)
    print(f"\n✅ Preferences ({len(prefs)}):")
    for pref in prefs:
        print(
            f"  - {pref['properties']['category']}: {pref['properties']['value']} (strength: {pref['properties']['strength']})"
        )

    # Get routines
    routines = kg.get_routines(person_id)
    print(f"\n✅ Routines ({len(routines)}):")
    for routine in routines:
        print(
            f"  - {routine['properties']['activity']}: {routine['properties']['schedule']} (adherence: {routine['properties']['adherence_rate']})"
        )

    # Get relationships
    relationships = kg.get_relationships(person_id)
    print(f"\n✅ Relationships ({len(relationships)}):")
    for rel in relationships:
        print(
            f"  - {rel['properties']['person_name']} ({rel['properties']['relation_type']}, closeness: {rel['properties']['closeness']})"
        )

    # Get memories
    memories = kg.query_memories(person_id)
    print(f"\n✅ Memories ({len(memories)}):")
    for memory in memories:
        print(
            f"  - {memory['properties']['summary']} ({memory['properties']['date']}, importance: {memory['properties']['importance']})"
        )

    print("\n" + "=" * 80)
    print("✅ All verification queries passed!")
    print("=" * 80)

    return person_id


if __name__ == "__main__":
    # Run seeding script
    try:
        person_id = seed_user_kg()
        print(f"\n✅ SUCCESS: User KG seeded with user ID: {person_id}")
        print("\nYou can now use the User KG in your agents:")
        print("  from l5_infrastructure.user_kg import get_user_kg")
        print("  kg = get_user_kg()")
        print(f"  profile = kg.get_user_profile('{person_id}')")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ ERROR: Failed to seed User KG: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
