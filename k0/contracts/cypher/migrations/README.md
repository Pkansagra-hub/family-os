# Neo4j Cypher Migrations

This directory contains versioned Cypher migration scripts for the K0 Knowledge Graph infrastructure (Neo4j).

## Overview

The K0 architecture uses a **two-tier storage system**:

- **Neo4j** (Knowledge Graph): Stores entities (Person, Location, Event, Organization) and relationships
- **SQLite** (Memory/Event Store): Stores memories and events that reference Neo4j entities via `person_id` fields

Migrations are applied automatically and idempotently via `k0/automation/migrate_neo4j.py`.

## Migration Files

### 0001_baseline.cypher

- **Status**: Applied 2025-11-10T19:07:23Z
- **Purpose**: Schema initialization (constraints and indexes)
- **Content**:
  - 6 uniqueness constraints (ensuring `node_id` is unique per entity type)
  - 47 property indexes (on common query paths: node_id, cognitive_trace_id, valid_from, etc.)
  - Full-text search indexes for entity search

### 0002_seed_family_data.cypher

- **Status**: Applied 2025-11-10T19:32:32Z
- **Purpose**: Seeds the graph with initial family entity data for development/testing
- **Content**:
  - **10 entity nodes**: 5 Person, 3 Location, 1 Organization
  - **14 relationships**: PARENT_OF, SPOUSE_OF, SIBLING_OF, LIVES_IN, WORKS_AT, EMPLOYED_BY
- **Entities Created**:

```text
Persons:
  person_user_001: Primary User (Software Engineer)
  person_mom_001: Mother (Retired Teacher)
  person_dad_001: Father (Retired Engineer)
  person_sibling_001: Sibling (Doctor)
  person_partner_001: Spouse (Marketing Manager)

Locations:
  location_home_001: 123 Main Street, Seattle (Primary residence)
  location_work_001: 456 Tech Avenue, Seattle (Office)
  location_seattle_001: Seattle (City reference)

Organizations:
  org_employer_001: TechCorp Inc. (Technology corporation)
```

## How Migrations Work

### Migration Execution Pipeline

1. **Discovery** - `migrate_neo4j.py` scans this folder for `*.cypher` files
2. **Versioning** - Version extracted from filename (e.g., `0001` from `0001_baseline.cypher`)
3. **Idempotency Check** - Queries `SchemaVersion` node to see if migration already applied
4. **Parsing** - Splits statements by semicolon (`;`), removes inline comments (`//`)
5. **Execution** - Runs each statement against Neo4j via Bolt driver (Python)
6. **Recording** - Creates/updates `SchemaVersion` node with version + applied_at timestamp

### Key Requirements

**Statement Format:**
- Each Cypher statement must end with a semicolon (`;`)
- Statements should be on **single lines** (avoids parser issues with newline handling)
- Inline comments (`//`) are stripped but should be avoided to prevent edge cases
- Long property chains are acceptable but keep statements readable

**Example Valid Statements:**
```cypher
CREATE (p:Person {node_id: "person_001", name: "User"});
CREATE CONSTRAINT person_node_id_unique FOR (p:Person) REQUIRE p.node_id IS UNIQUE;
CREATE INDEX person_node_id_idx FOR (p:Person) ON (p.node_id);
MATCH (a:Person {node_id: "person_001"}), (b:Person {node_id: "person_002"}) CREATE (a)-[:PARENT_OF]->(b);
```

**Important:**
- ❌ Do NOT use multi-line statements (breaks parser)
- ❌ Do NOT use SQL-style comments (`--`)
- ✅ DO use Cypher-style comments (`//`) if needed, but prefer statement clarity instead
- ✅ DO keep statements reasonably short to avoid driver communication issues

## Running Migrations

### Automated (Recommended)
```bash
python k0/automation/migrate_neo4j.py
```

This will:
1. Connect to Neo4j at `neo4j://localhost:7687`
2. Discover all `.cypher` files in this directory
3. Apply any unapplied migrations in version order
4. Print results (skipped vs. applied)

### Manual Testing
```bash
# Check current migration status
python
>>> from k0.automation.migrate_neo4j import apply_cypher_migrations
>>> results = apply_cypher_migrations('neo4j://localhost:7687', 'neo4j', 'test-password', 'neo4j')
>>> for r in results:
...     print(f'{r.version}: {r.action}')
```

## Schema Information

### Node Types
- `:Person` - Human entities (node_id: `person_*`)
- `:Location` - Geographic/physical locations (node_id: `location_*`)
- `:Event` - Temporal events (node_id: `event_*`)
- `:Organization` - Groups/companies (node_id: `org_*`)
- `:Thing` - Generic entities (node_id: `thing_*`)
- `:SchemaVersion` - Tracks applied migrations (internal)

### Relationship Types
- `PARENT_OF` - Familial parent-child
- `SIBLING_OF` - Familial sibling
- `SPOUSE_OF` - Marital/partnership
- `LIVES_IN` - Residential location
- `WORKS_AT` - Employment location
- `EMPLOYED_BY` - Employment organization
- `ATTENDED` - Event attendance
- And others as defined in ADR-0081 (K0 Knowledge Graph Architecture)

### Common Properties
All entities include:
- `node_id` (String, unique) - Stable identifier for cross-database references
- `label` (String) - Display label
- `name` (String) - Human-readable name
- `created_at` (Timestamp) - Creation time (milliseconds)
- `updated_at` (Timestamp) - Last modification time (milliseconds)
- `valid_from` (Integer) - Temporal validity start (Unix timestamp in milliseconds)
- `valid_to` (Integer, optional) - Temporal validity end (null if ongoing)
- `confidence` (Float 0.0-1.0) - Assertion confidence
- `privacy_band` (String) - Privacy classification (GREEN/AMBER/RED)
- `cognitive_trace_id` (String) - Traceability identifier

## Integration with SQLite

SQLite memory tables reference Neo4j entities:

```sql
-- Episodic memory table (st_epi)
CREATE TABLE st_epi (
    id INTEGER PRIMARY KEY,
    author_id TEXT,  -- References Person.node_id
    location_ids TEXT,  -- JSON array of Location.node_id
    ...
);

-- Social memory table (st_social)
CREATE TABLE st_social (
    person_a_id TEXT,  -- References Person.node_id
    person_b_id TEXT,  -- References Person.node_id
    ...
);
```

Example Query:
```sql
-- Get all memories authored by person_user_001
SELECT * FROM st_epi WHERE author_id = 'person_user_001';
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Migration not applying | Check if migration is already applied: `SELECT * FROM neo4j.SchemaVersion` in Neo4j Browser |
| Cypher syntax error | Ensure all statements are on single lines and end with semicolon |
| Duplicate constraint error | Migration already applied; check `SchemaVersion` node |
| Neo4j connection refused | Verify Neo4j container is running: `docker ps \| grep neo4j` |
| Statement too long | Break into smaller statements (one entity/relationship per statement) |

## References

- **ADR-0081**: K0 Knowledge Graph Architecture ([docs/architecture/decisions/0081-k0-knowledge-graph.md](../../decisions/0081-k0-knowledge-graph.md))
- **Migration Runner**: `k0/automation/migrate_neo4j.py`
- **Neo4j Driver**: Neo4j Python driver (Bolt protocol)
- **Connection**: `neo4j://localhost:7687` (local development)

## Contributing

When adding new migrations:

1. **Naming**: Follow format `NNNN_description.cypher` (e.g., `0003_add_social_events.cypher`)
2. **Numbering**: Use next sequential version number
3. **Format**: Single-line Cypher statements, each ending with `;`
4. **Properties**: Include `cognitive_trace_id: "migration_NNNN"` for traceability
5. **Documentation**: Update this README with migration purpose
6. **Testing**: Verify on local Neo4j before committing
7. **Idempotency**: Ensure migration can be safely re-run (use `CREATE (... UNIQUE)` patterns)

Example:
```cypher
-- 0003_add_social_events.cypher
CREATE (e:Event {node_id: "event_001", name: "Family Reunion", valid_from: 1735689600000, created_at: timestamp(), cognitive_trace_id: "migration_0003"});
MATCH (e:Event {node_id: "event_001"}), (p:Person {node_id: "person_user_001"}) CREATE (p)-[:ATTENDED]->(e);
```
