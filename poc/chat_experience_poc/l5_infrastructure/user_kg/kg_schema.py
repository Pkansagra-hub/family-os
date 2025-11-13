"""
User Knowledge Graph Schema Definition

Defines SQLite schema for User KG with 7 node types and 6 edge types.
This is a simplified graph database for PoC agent personalization.

Node Types:
- Person: User profile (name, age, locale, timezone)
- HealthMetric: Health data (type, value, unit, date, confidence)
- Goal: User goals (description, deadline, progress, active)
- Relationship: Social connections (person_name, relation_type, closeness, notes)
- Preference: User preferences (category, value, strength, source)
- Routine: Daily routines (activity, schedule, adherence_rate, last_execution)
- Memory: Important memories (summary, date, importance, emotional_valence)

Edge Types:
- HAS_GOAL: Person → Goal
- TRACKS_METRIC: Person → HealthMetric
- PREFERS: Person → Preference
- RELATED_TO: Person → Relationship
- FOLLOWS_ROUTINE: Person → Routine
- RECALLS: Person → Memory

Performance:
- Queries: <10ms P95 target
- Indexes on frequently queried fields (person_id, date, type)
- Foreign key constraints for referential integrity

Reference: docs/plans/chat_experience_poc_plan.md Epic 1.4
"""

from enum import Enum
from typing import Any, Dict


class NodeType(Enum):
    """Supported node types in User KG"""

    PERSON = "person"
    HEALTH_METRIC = "health_metric"
    GOAL = "goal"
    RELATIONSHIP = "relationship"
    PREFERENCE = "preference"
    ROUTINE = "routine"
    MEMORY = "memory"


class EdgeType(Enum):
    """Supported edge types in User KG"""

    HAS_GOAL = "HAS_GOAL"
    TRACKS_METRIC = "TRACKS_METRIC"
    PREFERS = "PREFERS"
    RELATED_TO = "RELATED_TO"
    FOLLOWS_ROUTINE = "FOLLOWS_ROUTINE"
    RECALLS = "RECALLS"


# SQL Schema Definition
SCHEMA_SQL = """
-- User Knowledge Graph Schema
-- Version: 1.0.0
-- Date: 2025-11-05

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- Nodes table (stores all node types)
CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    person_id TEXT,  -- Nullable for Person nodes (self-reference)
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    properties TEXT NOT NULL,  -- JSON blob for node-specific properties
    FOREIGN KEY (person_id) REFERENCES nodes(node_id) ON DELETE CASCADE
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_nodes_person_id ON nodes(person_id);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_nodes_person_type ON nodes(person_id, node_type);
CREATE INDEX IF NOT EXISTS idx_nodes_created ON nodes(created_at);

-- Edges table (stores all relationships)
CREATE TABLE IF NOT EXISTS edges (
    edge_id TEXT PRIMARY KEY,
    edge_type TEXT NOT NULL,
    from_node_id TEXT NOT NULL,
    to_node_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    properties TEXT,  -- JSON blob for edge-specific properties
    FOREIGN KEY (from_node_id) REFERENCES nodes(node_id) ON DELETE CASCADE,
    FOREIGN KEY (to_node_id) REFERENCES nodes(node_id) ON DELETE CASCADE
);

-- Indexes for edge queries
CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(edge_type);
CREATE INDEX IF NOT EXISTS idx_edges_from_type ON edges(from_node_id, edge_type);

-- Full-text search index for text fields (optional, for advanced queries)
CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    node_id UNINDEXED,
    node_type UNINDEXED,
    person_id UNINDEXED,
    searchable_text
);

-- Trigger to keep FTS index in sync
CREATE TRIGGER IF NOT EXISTS nodes_fts_insert AFTER INSERT ON nodes BEGIN
    INSERT INTO nodes_fts(node_id, node_type, person_id, searchable_text)
    VALUES (new.node_id, new.node_type, new.person_id, new.properties);
END;

CREATE TRIGGER IF NOT EXISTS nodes_fts_update AFTER UPDATE ON nodes BEGIN
    UPDATE nodes_fts SET searchable_text = new.properties
    WHERE node_id = new.node_id;
END;

CREATE TRIGGER IF NOT EXISTS nodes_fts_delete AFTER DELETE ON nodes BEGIN
    DELETE FROM nodes_fts WHERE node_id = old.node_id;
END;
"""


def validate_node_properties(node_type: NodeType, properties: Dict[str, Any]) -> bool:
    """
    Validate that node properties match schema for node type.

    Args:
        node_type: Type of node
        properties: Properties dictionary

    Returns:
        True if valid, False otherwise
    """
    required_fields = {
        NodeType.PERSON: ["name", "age", "locale", "timezone"],
        NodeType.HEALTH_METRIC: ["type", "value", "unit", "date", "confidence"],
        NodeType.GOAL: ["description", "deadline", "progress", "active"],
        NodeType.RELATIONSHIP: ["person_name", "relation_type", "closeness", "notes"],
        NodeType.PREFERENCE: ["category", "value", "strength", "source"],
        NodeType.ROUTINE: ["activity", "schedule", "adherence_rate", "last_execution"],
        NodeType.MEMORY: ["summary", "date", "importance", "emotional_valence"],
    }

    if node_type not in required_fields:
        return False

    # Check all required fields present
    for field in required_fields[node_type]:
        if field not in properties:
            return False

    # Type-specific validation
    if node_type == NodeType.HEALTH_METRIC:
        if not (0.0 <= properties["confidence"] <= 1.0):
            return False

    if node_type == NodeType.GOAL:
        if not (0.0 <= properties["progress"] <= 1.0):
            return False
        if not isinstance(properties["active"], bool):
            return False

    if node_type == NodeType.RELATIONSHIP:
        if not (0.0 <= properties["closeness"] <= 1.0):
            return False

    if node_type == NodeType.PREFERENCE:
        if not (0.0 <= properties["strength"] <= 1.0):
            return False

    if node_type == NodeType.ROUTINE:
        if not (0.0 <= properties["adherence_rate"] <= 1.0):
            return False

    if node_type == NodeType.MEMORY:
        if not (0.0 <= properties["importance"] <= 1.0):
            return False
        if not (-1.0 <= properties["emotional_valence"] <= 1.0):
            return False

    return True


def get_schema_documentation() -> str:
    """
    Return human-readable schema documentation.

    Returns:
        Formatted schema documentation string
    """
    doc = """
User Knowledge Graph Schema
============================

Node Types:
-----------
1. Person
   - name: str (user's name)
   - age: int (user's age)
   - locale: str (e.g., "en_US")
   - timezone: str (e.g., "US/Pacific")

2. HealthMetric
   - type: str (e.g., "knee_strength", "pain_level")
   - value: float (metric value)
   - unit: str (e.g., "kg", "/10")
   - date: str (ISO format, e.g., "2025-11-05")
   - confidence: float (0.0-1.0, measurement confidence)

3. Goal
   - description: str (goal description)
   - deadline: str (ISO date, e.g., "2025-12-01")
   - progress: float (0.0-1.0, completion percentage)
   - active: bool (is goal still active)

4. Relationship
   - person_name: str (related person's name)
   - relation_type: str (e.g., "mother", "partner", "caregiver")
   - closeness: float (0.0-1.0, relationship strength)
   - notes: str (additional context)

5. Preference
   - category: str (e.g., "food", "exercise")
   - value: str (preference value, e.g., "Italian")
   - strength: float (0.0-1.0, preference strength)
   - source: str (how preference learned: "stated", "inferred", "observed")

6. Routine
   - activity: str (routine description, e.g., "PT exercises")
   - schedule: str (schedule description, e.g., "daily 8am")
   - adherence_rate: float (0.0-1.0, how often followed)
   - last_execution: str (ISO datetime, last time executed)

7. Memory
   - summary: str (memory summary)
   - date: str (ISO date, when memory occurred)
   - importance: float (0.0-1.0, memory importance)
   - emotional_valence: float (-1.0 to 1.0, negative to positive emotion)

Edge Types:
-----------
1. HAS_GOAL: Person → Goal
2. TRACKS_METRIC: Person → HealthMetric
3. PREFERS: Person → Preference
4. RELATED_TO: Person → Relationship
5. FOLLOWS_ROUTINE: Person → Routine
6. RECALLS: Person → Memory

Performance Targets:
-------------------
- Query latency: <10ms P95
- Concurrent access: Thread-safe
- Cache duration: 60s for repeated queries
- Index coverage: person_id, node_type, date, created_at

Example Usage:
--------------
from kg_schema import NodeType, EdgeType, validate_node_properties

# Validate Person node
person_props = {
    "name": "John",
    "age": 45,
    "locale": "en_US",
    "timezone": "US/Pacific"
}
is_valid = validate_node_properties(NodeType.PERSON, person_props)

# Validate HealthMetric node
metric_props = {
    "type": "knee_strength",
    "value": 8.5,
    "unit": "kg",
    "date": "2025-11-05",
    "confidence": 0.95
}
is_valid = validate_node_properties(NodeType.HEALTH_METRIC, metric_props)
"""
    return doc


if __name__ == "__main__":
    # Print schema documentation
    print(get_schema_documentation())

    # Print SQL schema
    print("\nSQL Schema:")
    print("=" * 80)
    print(SCHEMA_SQL)
