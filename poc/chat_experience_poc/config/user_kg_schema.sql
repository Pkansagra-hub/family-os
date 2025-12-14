-- User Knowledge Graph Schema
-- Version: 1.0.0
-- Date: 2025-11-05
-- Purpose: SQLite schema for User KG with 7 node types and 6 edge types
-- Reference: docs/plans/chat_experience_poc_plan.md Epic 1.4

-- Enable foreign keys for referential integrity
PRAGMA foreign_keys = ON;

-- ============================================================================
-- Nodes Table
-- ============================================================================
-- Stores all node types with properties as JSON blob
-- Node types: person, health_metric, goal, relationship, preference, routine, memory

CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,                    -- Unique node identifier (UUID)
    node_type TEXT NOT NULL,                     -- Type: person, health_metric, etc.
    person_id TEXT,                              -- User this node belongs to (nullable for Person nodes)
    created_at TEXT NOT NULL,                    -- ISO timestamp (e.g., "2025-11-05T10:30:00Z")
    updated_at TEXT NOT NULL,                    -- ISO timestamp (last update)
    properties TEXT NOT NULL,                    -- JSON blob for node-specific properties
    FOREIGN KEY (person_id) REFERENCES nodes(node_id) ON DELETE CASCADE
);

-- Indexes for fast queries (<10ms P95 target)
CREATE INDEX IF NOT EXISTS idx_nodes_person_id ON nodes(person_id);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_nodes_person_type ON nodes(person_id, node_type);
CREATE INDEX IF NOT EXISTS idx_nodes_created ON nodes(created_at);
CREATE INDEX IF NOT EXISTS idx_nodes_updated ON nodes(updated_at);

-- ============================================================================
-- Edges Table
-- ============================================================================
-- Stores all relationships between nodes
-- Edge types: HAS_GOAL, TRACKS_METRIC, PREFERS, RELATED_TO, FOLLOWS_ROUTINE, RECALLS

CREATE TABLE IF NOT EXISTS edges (
    edge_id TEXT PRIMARY KEY,                    -- Unique edge identifier (UUID)
    edge_type TEXT NOT NULL,                     -- Type: HAS_GOAL, TRACKS_METRIC, etc.
    from_node_id TEXT NOT NULL,                  -- Source node (typically Person)
    to_node_id TEXT NOT NULL,                    -- Target node
    created_at TEXT NOT NULL,                    -- ISO timestamp
    properties TEXT,                             -- JSON blob for edge-specific properties (optional)
    FOREIGN KEY (from_node_id) REFERENCES nodes(node_id) ON DELETE CASCADE,
    FOREIGN KEY (to_node_id) REFERENCES nodes(node_id) ON DELETE CASCADE
);

-- Indexes for edge traversal queries
CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(edge_type);
CREATE INDEX IF NOT EXISTS idx_edges_from_type ON edges(from_node_id, edge_type);

-- ============================================================================
-- Full-Text Search (FTS5) for Advanced Queries
-- ============================================================================
-- Enables keyword search across node properties
-- Example: Search for "running" in goals, memories, routines

CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    node_id UNINDEXED,
    node_type UNINDEXED,
    person_id UNINDEXED,
    searchable_text
);

-- Triggers to keep FTS index in sync with nodes table
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

-- ============================================================================
-- Node Type Property Schemas (Documentation)
-- ============================================================================

-- Person Node:
-- {
--   "name": "John",
--   "age": 45,
--   "locale": "en_US",
--   "timezone": "US/Pacific"
-- }

-- HealthMetric Node:
-- {
--   "type": "knee_strength",
--   "value": 8.5,
--   "unit": "kg",
--   "date": "2025-11-05",
--   "confidence": 0.95
-- }

-- Goal Node:
-- {
--   "description": "Return to running by Dec 1, 2025",
--   "deadline": "2025-12-01",
--   "progress": 0.85,
--   "active": true
-- }

-- Relationship Node:
-- {
--   "person_name": "Mom",
--   "relation_type": "caregiver",
--   "closeness": 0.9,
--   "notes": "Lives nearby, helps with PT"
-- }

-- Preference Node:
-- {
--   "category": "food",
--   "value": "Italian",
--   "strength": 0.9,
--   "source": "stated"
-- }

-- Routine Node:
-- {
--   "activity": "PT exercises",
--   "schedule": "daily 8am",
--   "adherence_rate": 0.75,
--   "last_execution": "2025-11-05T08:15:00Z"
-- }

-- Memory Node:
-- {
--   "summary": "Started PT recovery",
--   "date": "2025-09-15",
--   "importance": 0.9,
--   "emotional_valence": -0.3
-- }

-- ============================================================================
-- Edge Type Examples (Documentation)
-- ============================================================================

-- HAS_GOAL: Person → Goal
-- TRACKS_METRIC: Person → HealthMetric
-- PREFERS: Person → Preference
-- RELATED_TO: Person → Relationship
-- FOLLOWS_ROUTINE: Person → Routine
-- RECALLS: Person → Memory

-- Example queries:
-- 1. Get all active goals for user:
--    SELECT * FROM nodes WHERE person_id = ? AND node_type = 'goal' AND json_extract(properties, '$.active') = 1;
--
-- 2. Get health metrics from last 30 days:
--    SELECT * FROM nodes WHERE person_id = ? AND node_type = 'health_metric'
--    AND date(json_extract(properties, '$.date')) >= date('now', '-30 days');
--
-- 3. Search memories by keyword:
--    SELECT n.* FROM nodes n JOIN nodes_fts f ON n.rowid = f.rowid
--    WHERE f.searchable_text MATCH 'running' AND n.node_type = 'memory';
