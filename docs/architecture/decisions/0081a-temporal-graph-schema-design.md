# ADR-0081a: Temporal Graph Schema Design

**Status:** Proposed
**Date:** 2025-10-22
**Parent ADR:** ADR-0081 (K0 Knowledge Graph Architecture)
**Implements:** Graph schema for K0::st_kg driver with temporal edges and version history

## Context

From **ADR-0081**, we need a **temporal graph schema** that tracks:

1. **Entities (Nodes):** People, locations, events, organizations, things
2. **Relationships (Edges):** Family, social, employment, location, temporal connections
3. **Temporal Validity:** Relationships change over time (Alice: single → married in 2020)
4. **Version History:** Track every change to relationships for temporal reasoning

**Key Requirements:**

- **Temporal Reasoning:** "Who was married to whom in 2020?" requires valid_from/valid_to timestamps
- **Relationship Evolution:** Alice's marital status: single (2015-2020) → married to Bob (2020-present)
- **Property Versioning:** Attributes change (occupation, location, preferences)
- **Performance:** <10ms P95 entity lookup, <50ms P95 relationship query

**From K0 Architecture Diagrams:**

- **D4 (project_architecture_part4.mmd):** K0_KG_INFRASTRUCTURE defines `KG_TEMPORAL_ENGINE` for temporal reasoning
- **D4:** `KG_VERSION_CONTROL` for knowledge versioning, `KG_CONCEPT_EVOLUTION` for concept evolution tracking
- **Storage:** K0::st_kg driver uses SQLite with temporal extensions

## Decision

Design **3-table temporal graph schema** in SQLite:

### Table 1: kg_nodes (Entities)

Stores **entities** with types, labels, and JSON properties.

```sql
CREATE TABLE kg_nodes (
    node_id TEXT PRIMARY KEY,           -- UUID v4
    entity_type TEXT NOT NULL,          -- Person, Location, Event, Organization, Thing
    label TEXT NOT NULL,                -- Display name (e.g., "Alice", "Seattle")
    created_at INTEGER NOT NULL,        -- Unix timestamp (ms)
    updated_at INTEGER NOT NULL,        -- Unix timestamp (ms)
    properties BLOB,                    -- JSON properties (see schema below)
    CONSTRAINT chk_entity_type CHECK (entity_type IN ('Person', 'Location', 'Event', 'Organization', 'Thing'))
);

-- Indexes for fast lookups
CREATE INDEX idx_kg_nodes_type ON kg_nodes(entity_type);
CREATE INDEX idx_kg_nodes_label ON kg_nodes(label);
CREATE INDEX idx_kg_nodes_updated ON kg_nodes(updated_at DESC);
```

**Entity Types:**

| Type | Description | Example Labels |
|------|-------------|----------------|
| **Person** | Family members, friends, colleagues | Alice, Bob, Mom, Dad, Dr. Smith |
| **Location** | Places, cities, addresses, landmarks | Seattle, Home, Office, Pike Place Market |
| **Event** | Milestones, meetings, trips, celebrations | Wedding2024, GraduationCeremony, FamilyReunion |
| **Organization** | Employers, schools, clubs, institutions | Microsoft, Harvard, BookClub |
| **Thing** | Pets, cars, devices, possessions | Fluffy (dog), TeslaCar, iPhone |

**Properties Schema (JSON):**

Properties are stored as JSON BLOB with schema validation:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "name": {"type": "string"},
    "age": {"type": "integer", "minimum": 0},
    "birthday": {"type": "string", "format": "date"},
    "email": {"type": "string", "format": "email"},
    "phone": {"type": "string", "pattern": "^\\+?[1-9]\\d{1,14}$"},
    "address": {"type": "string"},
    "occupation": {"type": "string"},
    "diet": {
      "type": "string",
      "enum": ["omnivore", "vegetarian", "vegan", "pescatarian", "gluten_free"]
    },
    "allergies": {
      "type": "array",
      "items": {"type": "string"}
    },
    "preferences": {
      "type": "object",
      "additionalProperties": true
    },
    "notes": {"type": "string"},
    "privacy_band": {
      "type": "string",
      "enum": ["GREEN", "AMBER", "RED"]
    }
  }
}
```

### Table 2: kg_edges (Relationships)

Stores **current relationships** with temporal validity (valid_from/valid_to).

```sql
CREATE TABLE kg_edges (
    edge_id TEXT PRIMARY KEY,           -- UUID v4
    source_id TEXT NOT NULL,            -- References kg_nodes(node_id)
    target_id TEXT NOT NULL,            -- References kg_nodes(node_id)
    rel_type TEXT NOT NULL,             -- Relationship type (see list below)
    valid_from INTEGER,                 -- Unix timestamp (ms), null = always valid
    valid_to INTEGER,                   -- Unix timestamp (ms), null = still valid
    confidence REAL DEFAULT 1.0,        -- 0.0 to 1.0 (entity resolution confidence)
    properties BLOB,                    -- JSON properties (optional metadata)
    created_at INTEGER NOT NULL,        -- Unix timestamp (ms)
    FOREIGN KEY(source_id) REFERENCES kg_nodes(node_id) ON DELETE CASCADE,
    FOREIGN KEY(target_id) REFERENCES kg_nodes(node_id) ON DELETE CASCADE,
    CONSTRAINT chk_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0),
    CONSTRAINT chk_valid_dates CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

-- Indexes for fast traversal
CREATE INDEX idx_kg_edges_source ON kg_edges(source_id);
CREATE INDEX idx_kg_edges_target ON kg_edges(target_id);
CREATE INDEX idx_kg_edges_rel_type ON kg_edges(rel_type);
CREATE INDEX idx_kg_edges_valid_from ON kg_edges(valid_from);
CREATE INDEX idx_kg_edges_valid_to ON kg_edges(valid_to);
CREATE INDEX idx_kg_edges_bidirectional ON kg_edges(source_id, target_id, rel_type);
```

**Relationship Types (Extensible):**

| Category | Relationship Types | Symmetric? | Temporal? |
|----------|-------------------|------------|-----------|
| **Family** | parent, child, sibling, spouse, grandparent, grandchild, aunt, uncle, cousin, in_law | No (parent ≠ child) | Yes (marriages end) |
| **Social** | friend, colleague, acquaintance, neighbor, mentor, mentee | Yes (friend ↔ friend) | Yes (friendships change) |
| **Employment** | employed_by, manages, reports_to, colleague_at | No | Yes (jobs change) |
| **Location** | lives_in, works_at, visits, born_in, studied_at | No | Yes (moves) |
| **Temporal** | married_to, divorced_from, dated, transitioned_to | No | Yes (always temporal) |
| **Affiliation** | member_of, attends, affiliated_with, graduated_from | No | Yes (memberships expire) |
| **Ownership** | owns, possesses, responsible_for | No | Yes (ownership transfers) |
| **Event** | participated_in, attended, organized, hosted | No | No (events are fixed) |

**Temporal Validity Rules:**

- **valid_from = null, valid_to = null:** Timeless fact (born_in, graduated_from)
- **valid_from = T1, valid_to = null:** Ongoing (married_to since 2020, still valid)
- **valid_from = T1, valid_to = T2:** Historical (employed_by 2018-2023)
- **valid_from > current_time:** Future scheduled (will move to Seattle in 2025)

**Example Edges:**

```sql
-- Alice is Mom's sister (timeless family relationship)
INSERT INTO kg_edges (edge_id, source_id, target_id, rel_type, valid_from, valid_to, confidence)
VALUES ('edge-001', 'node-alice', 'node-mom', 'sister_of', NULL, NULL, 1.0);

-- Alice married Bob on 2020-06-15 (ongoing)
INSERT INTO kg_edges (edge_id, source_id, target_id, rel_type, valid_from, valid_to, confidence)
VALUES ('edge-002', 'node-alice', 'node-bob', 'married_to', 1592179200000, NULL, 1.0);

-- Alice worked at Microsoft 2018-2023 (historical)
INSERT INTO kg_edges (edge_id, source_id, target_id, rel_type, valid_from, valid_to, confidence)
VALUES ('edge-003', 'node-alice', 'node-microsoft', 'employed_by', 1514764800000, 1672531200000, 1.0);
```

### Table 3: kg_temporal_edges (Version History)

Stores **all versions** of relationships for temporal reasoning and rollback.

```sql
CREATE TABLE kg_temporal_edges (
    version_id TEXT PRIMARY KEY,        -- UUID v4
    edge_id TEXT NOT NULL,              -- References kg_edges(edge_id)
    version INTEGER NOT NULL,           -- Version number (1, 2, 3...)
    valid_from INTEGER NOT NULL,        -- Timestamp when this version became valid
    valid_to INTEGER,                   -- Timestamp when superseded (null = current)
    rel_type TEXT NOT NULL,             -- Relationship type at this version
    properties BLOB,                    -- JSON properties at this version
    confidence REAL DEFAULT 1.0,        -- Confidence at this version
    created_at INTEGER NOT NULL,        -- Unix timestamp (ms)
    FOREIGN KEY(edge_id) REFERENCES kg_edges(edge_id) ON DELETE CASCADE,
    CONSTRAINT chk_version CHECK (version > 0),
    CONSTRAINT chk_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0),
    CONSTRAINT chk_valid_dates CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

-- Indexes for temporal queries
CREATE INDEX idx_kg_temporal_edges_edge ON kg_temporal_edges(edge_id);
CREATE INDEX idx_kg_temporal_edges_valid_from ON kg_temporal_edges(valid_from);
CREATE INDEX idx_kg_temporal_edges_valid_to ON kg_temporal_edges(valid_to);
CREATE INDEX idx_kg_temporal_edges_version ON kg_temporal_edges(edge_id, version DESC);
```

**Versioning Workflow:**

When a relationship changes (e.g., Alice changes occupation):

1. **Current edge in kg_edges:** Update with new data, increment updated_at
2. **Archive old version in kg_temporal_edges:** Insert row with old data, set valid_to = now
3. **Query history:** `SELECT * FROM kg_temporal_edges WHERE edge_id = 'edge-003' ORDER BY version DESC`

**Example Version History:**

Alice's employment history:

| version | rel_type | target | valid_from | valid_to | confidence |
|---------|----------|--------|------------|----------|------------|
| 1 | employed_by | Microsoft | 2018-01-01 | 2023-01-01 | 1.0 |
| 2 | employed_by | Google | 2023-01-01 | NULL | 1.0 |

**Temporal Query Example:**

```sql
-- Query: Where did Alice work in 2020?
SELECT rel_type, target_id, valid_from, valid_to
FROM kg_temporal_edges
WHERE edge_id IN (
    SELECT edge_id FROM kg_edges
    WHERE source_id = 'node-alice' AND rel_type = 'employed_by'
)
AND valid_from <= 1577836800000  -- 2020-01-01
AND (valid_to IS NULL OR valid_to >= 1609459200000);  -- 2021-01-01

-- Result: employed_by Microsoft (2018-2023)
```

## Schema Design Rationale

### Why 3 Tables (Not 1 or 2)?

**Option 1: Single table with version columns**
- ❌ Problem: Poor query performance (no clean separation of current vs. historical)
- ❌ Problem: Complex queries (always need WHERE valid_to IS NULL)

**Option 2: Two tables (nodes + versioned_edges)**
- ❌ Problem: Slow current relationship queries (always scan versions)
- ❌ Problem: No easy "give me current state" query

**✅ Chosen: Three tables (nodes + edges + temporal_edges)**
- ✅ Fast current state queries (kg_edges table)
- ✅ Fast temporal queries (kg_temporal_edges table with indexes)
- ✅ Clean separation: current vs. historical data

### Why JSON Properties (Not Columns)?

**Alternatives:**
1. **Separate columns:** age, occupation, address, diet, allergies...
   - ❌ Schema changes for every new property
   - ❌ 90% columns null for most entities

2. **Key-value table:** kg_node_properties(node_id, key, value, timestamp)
   - ❌ Slow queries (N+1 problem)
   - ❌ Complex property updates

**✅ Chosen: JSON BLOB with schema validation**
- ✅ Flexible schema (add properties without migrations)
- ✅ Single query per entity (no N+1)
- ✅ SQLite JSON1 extension for querying (`json_extract()`)
- ✅ Schema validation in Python (Pydantic models)

### Why UUID node_id (Not Integer)?

- ✅ Distributed system compatibility (no coordination)
- ✅ No sequential ID leakage (privacy)
- ✅ Merge-friendly (multiple sources can generate IDs)
- ✅ Consistent with K0 architecture (FlatBuffers use UUIDs)

### Indexing Strategy

**Indexes for Fast Queries:**

1. **Entity lookup:** `idx_kg_nodes_label` (B-tree index on label)
2. **Type filtering:** `idx_kg_nodes_type` (B-tree index on entity_type)
3. **Relationship traversal:** `idx_kg_edges_source`, `idx_kg_edges_target` (B-tree indexes)
4. **Temporal queries:** `idx_kg_edges_valid_from`, `idx_kg_edges_valid_to` (B-tree indexes)
5. **Version history:** `idx_kg_temporal_edges_version` (composite index on edge_id + version DESC)

**Index Size Estimation:**

For 1000 entities, 10000 edges:

- kg_nodes indexes: ~50 KB
- kg_edges indexes: ~500 KB (5 indexes × 100 KB each)
- kg_temporal_edges indexes: ~300 KB (3 indexes)
- **Total:** ~850 KB (minimal overhead)

## Consequences

### Positive

1. **✅ Fast Current Queries:** <10ms P95 entity lookup (kg_edges table optimized for current state)
2. **✅ Fast Temporal Queries:** <50ms P95 temporal queries (kg_temporal_edges with indexes)
3. **✅ Relationship Evolution:** Track every change (employment, location, relationships)
4. **✅ Flexible Properties:** JSON schema allows new attributes without migrations
5. **✅ Version History:** Complete audit trail for debugging and rollback
6. **✅ Privacy Enforcement:** privacy_band property for K0 P10 redaction

### Negative

1. **❌ Storage Overhead:** 3 tables + indexes (~2× storage vs. single table)
2. **❌ Write Complexity:** Updates must touch both kg_edges and kg_temporal_edges
3. **❌ Schema Migration:** Adding new relationship types requires code changes (extensible but not automatic)
4. **❌ JSON Query Performance:** json_extract() slower than native columns

### Mitigations

1. **Storage Overhead:** Acceptable (1000 entities × 10000 edges = ~10 MB total)
2. **Write Complexity:** Abstracted in SQLiteKGDriver (API: `upsert_relationship()`)
3. **Schema Migration:** Relationship types are extensible via configuration
4. **JSON Performance:** Cache frequently accessed properties in Python objects

## Implementation Notes

### SQLite Extensions Required

```sql
-- Enable foreign key constraints
PRAGMA foreign_keys = ON;

-- Enable JSON1 extension (temporal data)
PRAGMA compile_options;  -- Verify JSON1 support
```

### Property Querying (JSON1)

```sql
-- Query: Find all vegetarians
SELECT node_id, label
FROM kg_nodes
WHERE json_extract(properties, '$.diet') = 'vegetarian';

-- Query: Find people with allergies
SELECT node_id, label, json_extract(properties, '$.allergies') AS allergies
FROM kg_nodes
WHERE json_type(properties, '$.allergies') = 'array'
  AND json_array_length(properties, '$.allergies') > 0;
```

### Migration Path from Existing K0 Storage

**Phase 1:** Import from K0::st_sqlite (episodic memories)
- Parse episodic memories for entity mentions
- Extract entities via NER (Named Entity Recognition)
- Create nodes in kg_nodes

**Phase 2:** Import from K0::st_social (social beliefs - D3)
- Convert social beliefs → relationships
- Create edges in kg_edges

**Phase 3:** Backfill temporal data
- Estimate valid_from from episodic memory timestamps
- Mark valid_to = null for ongoing relationships

## Validation & Testing

### Schema Validation Tests

```python
# tests/k0/drivers/test_sqlite_kg_schema.py
import pytest
from k0.drivers.sqlite_kg import SQLiteKGDriver

async def test_insert_node_valid_entity_type():
    driver = SQLiteKGDriver(":memory:")
    node_id = await driver.insert_node(
        entity_type="Person",
        label="Alice",
        properties={"age": 30, "diet": "vegetarian"}
    )
    assert node_id is not None

async def test_insert_node_invalid_entity_type():
    driver = SQLiteKGDriver(":memory:")
    with pytest.raises(ValueError, match="Invalid entity_type"):
        await driver.insert_node(
            entity_type="InvalidType",
            label="Alice",
            properties={}
        )

async def test_temporal_edge_versioning():
    driver = SQLiteKGDriver(":memory:")
    # Insert initial edge
    edge_id = await driver.insert_edge(
        source_id="node-alice",
        target_id="node-microsoft",
        rel_type="employed_by",
        valid_from=1514764800000  # 2018-01-01
    )

    # Update edge (job change)
    await driver.update_edge(
        edge_id=edge_id,
        target_id="node-google",
        valid_from=1672531200000  # 2023-01-01
    )

    # Verify version history
    history = await driver.get_edge_history(edge_id)
    assert len(history) == 2
    assert history[0]["target_id"] == "node-microsoft"
    assert history[1]["target_id"] == "node-google"
```

### Performance Tests

```python
# tests/k0/drivers/test_sqlite_kg_performance.py
import pytest
import time

async def test_entity_lookup_performance():
    driver = SQLiteKGDriver(":memory:")
    # Insert 1000 entities
    for i in range(1000):
        await driver.insert_node(f"Person", f"Person{i}", {})

    # Measure lookup time
    start = time.perf_counter()
    for i in range(100):
        await driver.get_node(f"node-person{i}")
    elapsed_ms = (time.perf_counter() - start) * 1000

    # Verify <10ms P95
    assert elapsed_ms / 100 < 10, f"Entity lookup too slow: {elapsed_ms/100:.2f}ms"

async def test_relationship_query_performance():
    driver = SQLiteKGDriver(":memory:")
    # Insert 100 entities with 1000 edges
    # ... setup code ...

    # Measure relationship query time
    start = time.perf_counter()
    relationships = await driver.get_relationships("node-person0")
    elapsed_ms = (time.perf_counter() - start) * 1000

    # Verify <50ms P95
    assert elapsed_ms < 50, f"Relationship query too slow: {elapsed_ms:.2f}ms"
```

## References

**Research:**
- [1] SQLite Temporal Tables: https://www.sqlite.org/lang_altertable.html
- [2] Bitemporal Data Modeling: https://martinfowler.com/articles/bitemporal-history.html
- [3] Neo4j Temporal Properties: https://neo4j.com/docs/cypher-manual/current/syntax/temporal/
- [4] SQL:2011 Temporal Features: https://en.wikipedia.org/wiki/SQL:2011

**Related ADRs:**
- ADR-0081: K0 Knowledge Graph Architecture (parent)
- ADR-0081b: Query API & Traversal Algorithms
- ADR-0081c: Episodic Memory → KG Integration

**Implementation Files:**
- `k0/drivers/sqlite_kg.py`: SQLiteKGDriver with schema creation
- `k0/kg/schema.py`: Pydantic models for validation
- `k0/kg/temporal_edges.py`: Versioning logic

---

**Status:** Proposed (2025-10-22)
**Next Steps:**
1. Implement schema in SQLiteKGDriver.initialize()
2. Create Pydantic models for validation
3. Write schema validation tests
4. Write performance tests
