# K0 Query Service Architecture - Redesigned

## Overview

The K0 Query Service now simulates a **realistic data access layer** that mirrors K0's 8 memory types architecture. This allows specialists to dynamically discover and query relevant data sources without hardcoded methods.

## Key Improvements

### Before (Too Specific)
```python
# Hardcoded methods - not scalable
k0_service.get_diet_entries(user_id, time_range)
k0_service.get_health_events(user_id, condition, time_range)
k0_service.get_user_profile(user_id)
```

### After (Generic & Discoverable)
```python
# Generic query interface - specialists discover tables dynamically
tables = k0_service.search_tables(["diet", "digestive", "health"])
# Returns: ["episodic.diet_logs", "episodic.health_events", "semantic.food_nutrition"]

data = k0_service.query(user_id, "episodic.diet_logs",
                        filters={"meal_type": "dinner"},
                        time_range="last_30_days")
```

## K0's 8 Memory Types

| Memory Type | Tables | Purpose | Example Queries |
|-------------|--------|---------|-----------------|
| **Episodic** | diet_logs, health_events, activities, sleep_logs | Time-stamped personal events | "What did I eat last week?" |
| **Semantic** | food_nutrition, health_conditions, medications, symptoms | General knowledge | "What's the caffeine in coffee?" |
| **Autobiographical** | user_profile, life_events, family_history | Personal history | "When was I diagnosed?" |
| **Working** | recent_conversations, active_goals, pending_tasks | Recent context | "What am I working on?" |
| **Prospective** | reminders, appointments, planned_activities | Future plans | "What's my next appointment?" |
| **Spatial** | places_visited, activity_locations, home_zones | Location data | "Where do I usually exercise?" |
| **Emotional** | mood_logs, stress_events, emotional_triggers | Affective states | "How was my mood this week?" |
| **Procedural** | routines, habit_patterns, learned_behaviors | Skills/habits | "What's my morning routine?" |

## Specialist Query Workflow

### Example: Nutritionist Analyzing GERD

```python
# Step 1: Discover relevant tables
tables = k0.search_tables(["diet", "digestive", "GERD", "food"])
# Returns: ["episodic.diet_logs", "episodic.health_events", "semantic.food_nutrition"]

# Step 2: Examine schema to understand columns/filters
schema = k0.get_schema("episodic")
# Returns table structures with available columns and filters

# Step 3: Query episodic data (when/what happened)
diet_logs = k0.query("user_123", "episodic.diet_logs",
                     filters={"meal_type": "dinner"},
                     time_range="last_30_days")

gerd_events = k0.query("user_123", "episodic.health_events",
                       filters={"event_type": "GERD"},
                       time_range="last_30_days")

# Step 4: Query semantic data (what's known about foods)
coffee_info = k0.query("user_123", "semantic.food_nutrition",
                       filters={"food_item": "coffee"})
# Returns: {"caffeine_mg": 95, "acidity": "high", "gerd_risk": "high"}

# Step 5: Correlate across memory types
# Nutritionist finds: coffee (high acidity) → GERD episodes (60% correlation)
```

### Example: Psychiatrist Analyzing Mood

```python
# Step 1: Discover mood-related tables
tables = k0.search_tables(["mood", "stress", "anxiety", "emotional"])
# Returns: ["emotional.mood_logs", "emotional.stress_events", "semantic.mental_health_conditions"]

# Step 2: Query emotional memory
mood_logs = k0.query("user_123", "emotional.mood_logs",
                     time_range="last_30_days")

stress_events = k0.query("user_123", "emotional.stress_events",
                         time_range="last_30_days")

# Step 3: Cross-reference with health events
health_events = k0.query("user_123", "episodic.health_events",
                         filters={"event_type": "GERD"},
                         time_range="last_30_days")

# Step 4: Find correlation
# Psychiatrist finds: stress events on 2/5 GERD days (confounding variable)
```

## Mock Data Structure

```python
MOCK_DATA = {
    "episodic": {
        "diet_logs": [
            {
                "id": 1,
                "timestamp": "2025-11-01T20:00:00",
                "food_item": "coffee",
                "meal_type": "dinner",
                "portion": "1 cup",
                "location": "home"
            },
            # ... 45 entries over 30 days
        ],
        "health_events": [
            {
                "id": 1,
                "timestamp": "2025-11-01T22:00:00",  # 2 hours after coffee
                "event_type": "GERD",
                "severity": "moderate",
                "symptoms": ["heartburn", "acid reflux"],
                "duration_minutes": 45
            },
            # ... 5 GERD episodes (3 after coffee, 2 after other triggers)
        ],
    },
    "semantic": {
        "food_nutrition": [
            {
                "food_item": "coffee",
                "caffeine_mg": 95,
                "acidity": "high",
                "ph_level": 4.85,
                "gerd_risk": "high",
                "trigger_compounds": ["caffeine", "chlorogenic acid"]
            },
            {
                "food_item": "milk",
                "caffeine_mg": 0,
                "acidity": "low",
                "ph_level": 6.7,
                "gerd_risk": "low",
                "notes": "Often recommended for GERD relief"
            },
            # ... nutrition database
        ],
    },
    "emotional": {
        "mood_logs": [
            {
                "timestamp": "2025-11-01T09:00:00",
                "mood": "anxious",
                "energy": 3,
                "stress_level": 7,
                "notes": "Work deadline approaching"
            },
            # ... 30 days of mood entries
        ],
        "stress_events": [
            {
                "timestamp": "2025-11-01T14:00:00",
                "event": "work_deadline",
                "severity": "high",
                "duration_minutes": 240
            },
            # ... stress events (2 overlap with GERD days)
        ],
    },
}
```

## Data Patterns (GERD Scenario)

### Primary Correlation: Coffee → GERD
- **Pattern**: 3 out of 5 GERD episodes occur 1-2 hours after evening coffee
- **Evidence**:
  - 2025-11-01: Coffee 8pm → GERD 10pm
  - 2025-11-05: Coffee 8:30pm → GERD 9:45pm
  - 2025-11-08: Coffee 7:45pm → GERD 9:30pm
- **Semantic context**: Coffee has high acidity (pH 4.85) + caffeine (95mg) = high GERD risk

### Red Herring: Milk (User's Hypothesis)
- **Pattern**: Milk appears 8 times in 30 days, **0 GERD correlation**
- **Evidence**: User drinks milk frequently, but no GERD episodes follow
- **Semantic context**: Milk is low acidity (pH 6.7), often recommended for GERD relief
- **Demonstrates**: Contradiction detection (user thinks milk, data shows coffee)

### Confounding Variable: Stress
- **Pattern**: 2 out of 5 GERD episodes coincide with high stress events
- **Evidence**:
  - 2025-11-01: Work deadline stress (7/10) + coffee → GERD
  - 2025-11-05: No stress + coffee → GERD
- **Shows**: Specialists can discover multi-factorial patterns across memory types

## Benefits of This Design

### For PoC Development
✅ **Realistic**: Mirrors actual K0 architecture with 8 memory types
✅ **Scalable**: Easy to add new tables/memory types without code changes
✅ **Discoverable**: Specialists learn to query dynamically, not hardcoded
✅ **Testable**: Can validate schema discovery, cross-memory queries
✅ **Demonstrable**: Shows K0 integration story clearly to stakeholders

### For Future K1 Integration
✅ **Drop-in replacement**: Same interface works with real K0 API
✅ **No refactoring**: Specialists already use generic query() method
✅ **Schema evolution**: New K0 tables automatically available
✅ **Multi-memory reasoning**: Already demonstrates cross-type correlations

## Implementation Summary

**Files Created:**
1. `backend/services/k0_query_service.py` - Abstract + Mock implementation
2. `tests/fixtures/mock_k0_data.py` - Mock data organized by memory type
3. `tests/fixtures/k0_schema.py` - Schema definitions for all tables

**Key Classes:**
- `K0QueryService` (abstract) - Generic query interface
- `MockK0QueryService` - Implements with in-memory mock data
- `K0Schema` - Defines 8 memory types + table structures

**API Methods:**
- `query(user_id, table_name, filters, time_range, limit)` - Generic data access
- `get_schema(memory_type)` - Schema discovery
- `search_tables(keywords)` - Find relevant tables by keywords
- `list_memory_types()` - List all 8 types

This design is **production-ready** for the K0 integration story! 🚀
