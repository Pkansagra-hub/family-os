---
adr_number: 'K022'
affected_layers:
- storage
- pipelines
affected_modules:
- k0/drivers/neo4j_driver.py
- k0/modules/social/family_graph_resolve.py
- k0/pipelines/p03/phases/r4_kg_consolidator.py
authors:
- K0 Architecture Team
concerns:
- infrastructure-simplification
- maintainability
- operational-cost
date_created: '2026-01-13'
date_updated: '2026-01-13'
implementation_date: '2026-01-13'
implementation_phase: P1
implementation_status: ACCEPTED
propagation:
  affected_adrs:
  - ADR-0081 (superseded)
  - ADR-0081a (superseded)
  - ADR-0081b (superseded)
  - ADR-0081c (superseded)
  affected_contracts:
  - k0/contracts/cypher/* (deleted)
  - k0/drivers/alias_map.yaml (updated)
  affected_tests:
  - tests/k0/drivers/test_neo4j_driver.py (deleted)
  triggers:
  - Neo4j container unused in production
  - st_relationships table empty (no sync implemented)
  - Duplicate graph storage (PostgreSQL + Neo4j)
related_adrs:
- k003-inline-embedding-ultrabert.md
related_contracts:
- k0/contracts/modules/social.family_graph_resolve.v1.yaml
related_diagrams:
- architecture_diagrams/k0/k0_source_of_truth_postgresql.mmd
research_citations: []
status: ACCEPTED
superseded_by: []
supersedes:
- ADR-0081
- ADR-0081a
- ADR-0081b
- ADR-0081c
title: Remove Neo4j, Consolidate Knowledge Graph to PostgreSQL
---

# ADR-K022: Remove Neo4j, Consolidate Knowledge Graph to PostgreSQL

**Status**: Accepted

**Date**: 2026-01-13

**Authors**: K0 Architecture Team

## Context

The current architecture has redundant graph storage infrastructure:

### Current State (Problematic)

```
┌─────────────────────────────────────────────────────────────┐
│ PostgreSQL k0_kernel                                        │
│ ✅ st_kg_dom (73 entities) - Entity domains                 │
│ ✅ st_kg_edges (38 edges) - Co-occurrence relationships     │
│ ✅ st_social (56 rows) - Social relationships from P03      │
│ ❌ st_relationships (0 rows) - Never synced from Neo4j      │
└─────────────────────────────────────────────────────────────┘
                    ↑
                    │ (sync never implemented)
                    ↓
┌─────────────────────────────────────────────────────────────┐
│ Neo4j (k0-neo4j container)                                  │
│ ⚠️ NOT USED by any production pipeline                      │
│ ⚠️ Alias st_kg_dom → neo4j_driver but P03 writes PostgreSQL │
│ ⚠️ ~500MB memory for unused database                        │
└─────────────────────────────────────────────────────────────┘
```

### Problems Identified

1. **Neo4j is unused**: No production pipeline queries Neo4j
2. **Sync never implemented**: `st_relationships` was designed as Neo4j cache but sync worker doesn't exist
3. **Duplicate storage**: P03 writes graph data to PostgreSQL (`st_kg_dom`, `st_kg_edges`)
4. **Operational overhead**: Running Neo4j container for zero benefit
5. **Alias mismatch**: `alias_map.yaml` says `st_kg_dom: neo4j_driver` but actual writes go to PostgreSQL

### Scale Analysis

For a family memory system:
- Family graph: ~10-50 nodes (immediate family, extended family, close friends)
- Relationship edges: ~50-200 edges
- This is **trivially small** for PostgreSQL's recursive CTEs

## Decision

**Remove Neo4j entirely and consolidate all graph storage to PostgreSQL.**

### Architecture Changes

1. **Delete Neo4j infrastructure**:
   - `k0/drivers/neo4j_driver.py`
   - `k0/config/neo4j.yaml`
   - `k0/contracts/cypher/` folder
   - `tests/k0/drivers/test_neo4j_driver.py`

2. **Update driver alias**:
   ```yaml
   # k0/drivers/alias_map.yaml
   st_kg_dom: postgres  # Changed from neo4j_driver
   ```

3. **Use st_kg_edges for typed family relationships**:
   - Add family relation types: `SPOUSE_OF`, `PARENT_OF`, `CHILD_OF`, `SIBLING_OF`, `CARETAKER_OF`
   - P02's `social.family_graph_resolve` queries `st_kg_edges` instead of `st_relationships`
   - Deprecate `st_relationships` table (future migration to drop)

4. **Seed family data into st_kg_dom + st_kg_edges**:
   - Create seed script for initial family onboarding
   - User provides family structure during setup
   - Stored as typed edges in `st_kg_edges`

### New Graph Query Pattern

```sql
-- Find all family members of a person
WITH RECURSIVE family AS (
  -- Base: direct relationships
  SELECT target_entity_id, relation_type, 1 as depth
  FROM st_kg_edges
  WHERE source_entity_id = 'person_user_001'
    AND relation_type IN ('SPOUSE_OF', 'PARENT_OF', 'CHILD_OF', 'SIBLING_OF')
    AND archival_status = 'ACTIVE'

  UNION ALL

  -- Recursive: extended family (up to 3 hops)
  SELECT e.target_entity_id, e.relation_type, f.depth + 1
  FROM st_kg_edges e
  JOIN family f ON e.source_entity_id = f.target_entity_id
  WHERE f.depth < 3
    AND e.relation_type IN ('SPOUSE_OF', 'PARENT_OF', 'CHILD_OF', 'SIBLING_OF')
    AND e.archival_status = 'ACTIVE'
)
SELECT DISTINCT target_entity_id, relation_type FROM family;
```

### Migration Path

| Phase | Action |
|-------|--------|
| P1 (Now) | Delete Neo4j files, update alias_map, add seed script |
| P2 (Next sprint) | Deprecate `st_relationships`, migrate P02 queries to `st_kg_edges` |
| P3 (Future) | Drop `st_relationships` table |

## Consequences

### Positive

- **Simpler infrastructure**: One database instead of two
- **No sync bugs**: No Neo4j ↔ PostgreSQL sync to maintain
- **Lower resource usage**: ~500MB memory saved
- **Unified querying**: All data in PostgreSQL, single query language
- **Easier debugging**: One place to check for graph data

### Negative

- **No native graph traversal**: Must use recursive CTEs (acceptable for small graphs)
- **No Cypher**: Lose expressive graph query language (SQL sufficient for our needs)
- **No graph visualization**: Lose Neo4j Browser (can use other tools if needed)

### Risks

| Risk | Mitigation |
|------|------------|
| Graph queries become slow | PostgreSQL indexes + recursive CTEs handle <1000 nodes easily |
| Complex traversals needed | Can add pgRouting extension if needed (unlikely) |
| Cypher expertise lost | Team primarily uses SQL anyway |

## Implementation Checklist

- [x] Create ADR (this document)
- [ ] Delete `k0/drivers/neo4j_driver.py`
- [ ] Delete `k0/config/neo4j.yaml`
- [ ] Delete `k0/contracts/cypher/` folder
- [ ] Delete `tests/k0/drivers/test_neo4j_driver.py`
- [ ] Update `k0/drivers/alias_map.yaml`
- [ ] Create `k0/deploy/seed_family_graph.py`
- [ ] Update P02 social module to query `st_kg_edges`
- [ ] Add migration to deprecate `st_relationships`
- [ ] Remove Neo4j from `docker-compose.yml`
